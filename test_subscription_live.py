#!/usr/bin/env python3
"""
Live regression test for subscription import against a real endpoint:
https://sub.comrad-tech.site:8443/3b0346da051447ef8be4350a5dd6e2f7

Requires real network access, so it's not wired into CI/justfile - run it
manually: `PYTHONPATH=py_modules python3 test_subscription_live.py`.

Covers the actual bug hit on-device: Decky's PyInstaller-bundled Python
runtime can set SSL_CERT_FILE/SSL_CERT_DIR to point inside its own
(possibly stale/missing) certificate bundle, which breaks HTTPS
verification for otherwise-valid endpoints even though the same code works
fine on a plain dev machine. `system_ssl_context()` (py_modules/
ultimate_vpn_deck/_utils.py) is the fix - this test simulates the polluted
env vars to prove `add_subscription` still works despite them.
"""

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SUBSCRIPTION_URL = "https://sub.comrad-tech.site:8443/3b0346da051447ef8be4350a5dd6e2f7"


class MockLogger:
    def info(self, msg): pass
    def debug(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass


class MockDecky:
    logger = MockLogger()
    DECKY_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
    DECKY_PLUGIN_SETTINGS_DIR = ""  # set per-test
    DECKY_PLUGIN_RUNTIME_DIR = ""
    DECKY_PLUGIN_LOG_DIR = ""


mock_decky = MockDecky()
sys.modules["decky"] = mock_decky

from ultimate_vpn_deck.profile_manager import ProfileManager  # noqa: E402
from ultimate_vpn_deck.subscription_manager import SubscriptionManager  # noqa: E402

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


def make_managers():
    temp_base = tempfile.mkdtemp(prefix="ultimate-vpn-deck-sub-test-")
    mock_decky.DECKY_PLUGIN_SETTINGS_DIR = temp_base
    pm = ProfileManager()
    sm = SubscriptionManager(pm)
    return pm, sm, temp_base


def test_normal_fetch():
    print("\n[normal environment]")
    pm, sm, temp = make_managers()
    try:
        result = sm.add_subscription(SUBSCRIPTION_URL)
        check("add_subscription: success", result["success"] is True, result)
        check("add_subscription: 2 profiles", result.get("profiles_added") == 2, result)

        subs = sm.list_subscriptions()
        check("list_subscriptions: one entry", len(subs) == 1, subs)
        if subs:
            check("subscription: title parsed", bool(subs[0]["title"]), subs[0])
            check("subscription: userinfo.expire parsed", subs[0]["userinfo"]["expire"] is not None, subs[0])

        profiles = pm.list_profiles()
        check("profiles: 2 imported", len(profiles) == 2, profiles)
        check(
            "profiles: all vless",
            all(p["protocol"] == "vless" for p in profiles),
            profiles,
        )
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def test_fetch_survives_pyinstaller_style_ssl_env_pollution():
    """Simulates Decky's PyInstaller bundle pointing SSL_CERT_FILE/DIR at a
    bogus location - the actual root cause of the on-device import error."""
    print("\n[simulated PyInstaller-polluted SSL env]")
    pm, sm, temp = make_managers()
    old_cert_file = os.environ.get("SSL_CERT_FILE")
    old_cert_dir = os.environ.get("SSL_CERT_DIR")
    bogus_dir = tempfile.mkdtemp(prefix="fake-mei-bundle-")
    try:
        os.environ["SSL_CERT_FILE"] = os.path.join(bogus_dir, "does-not-exist.pem")
        os.environ["SSL_CERT_DIR"] = bogus_dir

        result = sm.add_subscription(SUBSCRIPTION_URL)
        check(
            "add_subscription survives polluted SSL_CERT_FILE/DIR",
            result["success"] is True,
            result,
        )
    finally:
        if old_cert_file is None:
            os.environ.pop("SSL_CERT_FILE", None)
        else:
            os.environ["SSL_CERT_FILE"] = old_cert_file
        if old_cert_dir is None:
            os.environ.pop("SSL_CERT_DIR", None)
        else:
            os.environ["SSL_CERT_DIR"] = old_cert_dir
        shutil.rmtree(temp, ignore_errors=True)
        shutil.rmtree(bogus_dir, ignore_errors=True)


def test_refresh():
    print("\n[refresh]")
    pm, sm, temp = make_managers()
    try:
        add_result = sm.add_subscription(SUBSCRIPTION_URL)
        sub_id = add_result["sub_id"]
        refresh_result = sm.refresh_subscription(sub_id)
        check("refresh_subscription: success", refresh_result["success"] is True, refresh_result)
        check("refresh_subscription: still 2 profiles", refresh_result.get("profiles_added") == 2, refresh_result)
        check("profiles: still 2 after refresh (no duplicates)", len(pm.list_profiles()) == 2)
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def main():
    print("=" * 60)
    print(f"Live Subscription Import Test\n{SUBSCRIPTION_URL}")
    print("=" * 60)

    test_normal_fetch()
    test_fetch_survives_pyinstaller_style_ssl_env_pollution()
    test_refresh()

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
