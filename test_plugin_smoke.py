#!/usr/bin/env python3
"""
Smoke test for Plugin class - exercises every public RPC method end-to-end.

Uses the REAL ultimate_vpn_deck package (only `decky` is mocked, pointed at
temp directories) rather than mocking the manager classes: since the
sing-box binary is not bundled in the repo (fetched only at build time via
infra/fetch-binaries.sh, gitignored otherwise), BinaryManager naturally
reports it as missing and ServiceManager.start() fails gracefully with
"sing-box binary not found" without ever spawning a subprocess - this
exercises the exact same failure path a build-without-binaries would hit,
while still not needing a real sing-box binary or Docker.
"""

import asyncio
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TEMP_BASE = tempfile.mkdtemp(prefix="ultimate-vpn-deck-smoke-")


class _MockLogger:
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass
    def debug(self, msg): pass


class _MockDecky:
    logger = _MockLogger()
    DECKY_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
    DECKY_PLUGIN_SETTINGS_DIR = os.path.join(TEMP_BASE, "settings")
    DECKY_PLUGIN_RUNTIME_DIR = os.path.join(TEMP_BASE, "runtime")
    DECKY_PLUGIN_LOG_DIR = os.path.join(TEMP_BASE, "logs")


for d in (_MockDecky.DECKY_PLUGIN_SETTINGS_DIR, _MockDecky.DECKY_PLUGIN_RUNTIME_DIR, _MockDecky.DECKY_PLUGIN_LOG_DIR):
    os.makedirs(d, exist_ok=True)

sys.modules["decky"] = _MockDecky()

from main import Plugin  # noqa: E402

VLESS_URI = "vless://uuid-1@1.2.3.4:443?security=none#test-profile"

PASS = 0
FAIL = 0


def ok(name):
    global PASS
    PASS += 1
    print(f"  PASS  {name}")


def fail(name, reason):
    global FAIL
    FAIL += 1
    print(f"  FAIL  {name}: {reason}")


def assert_dict(result, name):
    if isinstance(result, dict):
        ok(name)
    else:
        fail(name, f"expected dict, got {type(result).__name__}: {result!r}")


def assert_list(result, name):
    if isinstance(result, list):
        ok(name)
    else:
        fail(name, f"expected list, got {type(result).__name__}: {result!r}")


def assert_bool(result, name):
    if isinstance(result, bool):
        ok(name)
    else:
        fail(name, f"expected bool, got {type(result).__name__}: {result!r}")


def assert_success_false(result, name):
    if isinstance(result, dict) and result.get("success") is False and result.get("error"):
        ok(name)
    else:
        fail(name, f"expected {{success: False, error: ...}}, got {result!r}")


def assert_success_true(result, name):
    if isinstance(result, dict) and result.get("success") is True:
        ok(name)
    else:
        fail(name, f"expected {{success: True, ...}}, got {result!r}")


async def run_tests():
    plugin = Plugin()

    print("\n[binaries]")
    assert_dict(await plugin.get_binaries_info(), "get_binaries_info()")
    assert_dict(await plugin.check_binaries(), "check_binaries()")

    print("\n[profiles: empty state]")
    assert_list(await plugin.list_profiles(), "list_profiles() empty")

    print("\n[profiles: add]")
    add_result = await plugin.add_profile(VLESS_URI)
    assert_success_true(add_result, "add_profile(valid uri)")
    profile_id = add_result.get("profile_id")

    profiles = await plugin.list_profiles()
    if len(profiles) == 1 and profiles[0]["id"] == profile_id:
        ok("list_profiles() reflects added profile")
    else:
        fail("list_profiles() reflects added profile", f"got {profiles!r}")

    print("\n[profiles: add invalid]")
    assert_success_false(await plugin.add_profile("not-a-valid-uri"), "add_profile(invalid uri)")

    print("\n[profiles: dict coercion]")
    r = await plugin.add_profile({"uri": VLESS_URI})
    assert_success_true(r, "add_profile({uri: ...}) dict-coercion")

    print("\n[profiles: get]")
    got = await plugin.get_profile(profile_id)
    assert_dict(got, "get_profile(existing)")
    none_result = await plugin.get_profile("nonexistent-id")
    if none_result is None:
        ok("get_profile(nonexistent) -> None")
    else:
        fail("get_profile(nonexistent) -> None", f"got {none_result!r}")

    print("\n[connection: connect without binary]")
    connect_result = await plugin.connect(profile_id)
    assert_success_false(connect_result, "connect() fails gracefully without sing-box binary")

    print("\n[connection: connect missing profile]")
    assert_success_false(await plugin.connect("does-not-exist"), "connect(missing profile_id)")

    print("\n[connection: connect empty profile_id]")
    assert_success_false(await plugin.connect(""), "connect('')")

    print("\n[connection: status / disconnect]")
    assert_dict(await plugin.status(), "status()")
    assert_dict(await plugin.disconnect(), "disconnect()")

    print("\n[subscriptions: empty state]")
    assert_list(await plugin.list_subscriptions(), "list_subscriptions() empty")

    print("\n[subscriptions: add with unreachable url]")
    sub_result = await plugin.add_subscription("http://127.0.0.1:1/nonexistent-subscription")
    assert_success_false(sub_result, "add_subscription(unreachable url)")

    print("\n[subscriptions: refresh missing]")
    assert_success_false(await plugin.refresh_subscription("nonexistent-sub"), "refresh_subscription(missing)")

    print("\n[subscriptions: delete missing]")
    assert_success_false(await plugin.delete_subscription("nonexistent-sub"), "delete_subscription(missing)")

    print("\n[diagnostics / errors]")
    assert_list(await plugin.diagnose_connectivity([]), "diagnose_connectivity([])")
    assert_list(await plugin.get_errors(), "get_errors()")
    assert_bool(await plugin.clear_errors(), "clear_errors()")

    print("\n[profiles: delete]")
    del_result = await plugin.delete_profile(profile_id)
    assert_success_true(del_result, "delete_profile(existing)")
    assert_success_false(await plugin.delete_profile("nonexistent-id"), "delete_profile(missing)")

    print("\n[REGRESSION: _rpc decorator catches exceptions]")
    orig = plugin.profile_manager.get_profile

    def boom(profile_id):
        raise RuntimeError("forced error")

    plugin.profile_manager.get_profile = boom
    r = await plugin.connect("anything")
    plugin.profile_manager.get_profile = orig
    assert_success_false(r, "_rpc catches exception -> {success: False, error: ...}")


async def main():
    print("=" * 60)
    print("Plugin Smoke Test")
    print("=" * 60)

    try:
        await run_tests()
    except Exception as e:
        import traceback
        print(f"\nUNHANDLED EXCEPTION: {e}")
        traceback.print_exc()
        shutil.rmtree(TEMP_BASE, ignore_errors=True)
        sys.exit(1)

    shutil.rmtree(TEMP_BASE, ignore_errors=True)

    print("\n" + "=" * 60)
    if FAIL == 0:
        print(f"ALL {PASS} TESTS PASSED")
    else:
        print(f"{PASS} passed, {FAIL} FAILED")
    print("=" * 60)

    if FAIL > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
