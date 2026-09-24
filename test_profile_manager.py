#!/usr/bin/env python3
"""
Unit tests for ProfileManager (+ SubscriptionManager refresh semantics) -
uses temp directories, mocked decky module.
"""

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class MockLogger:
    def info(self, msg): pass
    def debug(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass


class MockDecky:
    logger = MockLogger()
    DECKY_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
    DECKY_PLUGIN_SETTINGS_DIR = ""  # overridden per-test
    DECKY_PLUGIN_RUNTIME_DIR = ""
    DECKY_PLUGIN_LOG_DIR = ""


mock_decky = MockDecky()
sys.modules["decky"] = mock_decky

from ultimate_vpn_deck.profile_manager import ProfileManager  # noqa: E402
from ultimate_vpn_deck.subscription_manager import SubscriptionManager  # noqa: E402

VLESS_1 = "vless://uuid-1@1.2.3.4:443?security=none#server-1"
VLESS_2 = "vless://uuid-2@5.6.7.8:443?security=none#server-2"


def make_managers():
    temp_base = tempfile.mkdtemp(prefix="ultimate-vpn-deck-test-")
    mock_decky.DECKY_PLUGIN_SETTINGS_DIR = temp_base
    pm = ProfileManager()
    sm = SubscriptionManager(pm)
    return pm, sm, temp_base


PASS = 0
FAIL = 0


def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}: {detail}")


def test_add_and_list():
    pm, _sm, temp = make_managers()
    try:
        result = pm.add_profile_from_uri(VLESS_1)
        check("add: success", result["success"] is True, result)
        profiles = pm.list_profiles()
        check("add: appears in list", len(profiles) == 1)
        check("add: name parsed", profiles[0]["name"] == "server-1")
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def test_dedupe_same_uri():
    pm, _sm, temp = make_managers()
    try:
        r1 = pm.add_profile_from_uri(VLESS_1)
        r2 = pm.add_profile_from_uri(VLESS_1)
        check("dedupe: same profile_id", r1["profile_id"] == r2["profile_id"])
        check("dedupe: only one file", len(pm.list_profiles()) == 1)
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def test_delete_profile():
    pm, _sm, temp = make_managers()
    try:
        r = pm.add_profile_from_uri(VLESS_1)
        pm.set_active(r["profile_id"])
        del_result = pm.delete_profile(r["profile_id"])
        check("delete: success", del_result["success"] is True)
        check("delete: gone from list", len(pm.list_profiles()) == 0)
        check("delete: clears active", pm.get_active_profile_id() is None)
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def test_delete_missing_profile():
    pm, _sm, temp = make_managers()
    try:
        result = pm.delete_profile("nonexistent")
        check("delete missing: fails", result["success"] is False)
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def test_invalid_uri_rejected():
    pm, _sm, temp = make_managers()
    try:
        result = pm.add_profile_from_uri("not-a-uri")
        check("invalid uri: rejected", result["success"] is False)
        check("invalid uri: no file written", len(pm.list_profiles()) == 0)
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def test_subscription_refresh_replaces_only_own_profiles():
    pm, sm, temp = make_managers()
    try:
        # a manually-added profile, unrelated to any subscription
        manual = pm.add_profile_from_uri(VLESS_2, source="manual")

        sub_id = "fakesub123456789"
        r1 = pm.add_profile_from_uri(VLESS_1, source=f"subscription:{sub_id}")

        removed = pm.delete_profiles_by_source_prefix(f"subscription:{sub_id}")
        check("refresh sim: removed only subscription profile", removed == [r1["profile_id"]])
        remaining = pm.list_profiles()
        check("refresh sim: manual profile untouched", len(remaining) == 1 and remaining[0]["id"] == manual["profile_id"])
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def test_subscription_refresh_preserves_id_for_unchanged_link():
    pm, sm, temp = make_managers()
    try:
        sub_id = "stablesub00000001"
        r1 = pm.add_profile_from_uri(VLESS_1, source=f"subscription:{sub_id}")
        pm.set_active(r1["profile_id"])

        # simulate a refresh: same link re-added under the same subscription id
        pm.delete_profiles_by_source_prefix(f"subscription:{sub_id}")
        r2 = pm.add_profile_from_uri(VLESS_1, source=f"subscription:{sub_id}")

        check("refresh: stable id across refresh", r1["profile_id"] == r2["profile_id"])
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def main():
    print("=" * 60)
    print("ProfileManager / SubscriptionManager Unit Tests")
    print("=" * 60)

    test_add_and_list()
    test_dedupe_same_uri()
    test_delete_profile()
    test_delete_missing_profile()
    test_invalid_uri_rejected()
    test_subscription_refresh_replaces_only_own_profiles()
    test_subscription_refresh_preserves_id_for_unchanged_link()

    print("\n" + "=" * 60)
    if FAIL == 0:
        print(f"ALL {PASS} TESTS PASSED")
    else:
        print(f"{PASS} passed, {FAIL} FAILED")
    print("=" * 60)

    if FAIL > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
