#!/usr/bin/env python3
"""
Unit tests for uri_parsers / singbox_config / subscription body+header parsing.
No real network/binaries/decky needed - `decky` is mocked because
subscription_manager.py imports it at module level.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class MockLogger:
    def info(self, msg): pass
    def debug(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass


class MockDecky:
    logger = MockLogger()
    DECKY_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
    DECKY_PLUGIN_SETTINGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".test_settings")
    DECKY_PLUGIN_RUNTIME_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".test_runtime")
    DECKY_PLUGIN_LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".test_logs")


sys.modules["decky"] = MockDecky()

from ultimate_vpn_deck import uri_parsers, singbox_config  # noqa: E402
from ultimate_vpn_deck.subscription_manager import SubscriptionManager  # noqa: E402

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


def check(name, condition, detail=""):
    if condition:
        ok(name)
    else:
        fail(name, detail)


# ---------------------------------------------------------------------------
# vless
# ---------------------------------------------------------------------------

def test_vless_reality_grpc():
    uri = (
        "vless://08b170a5-8606-4b89-b17b-10b28e843b50@news.comrad-tech.site:8052"
        "?type=grpc&security=reality&pbk=GVfGGMn8gxiL1bWdlfjhWxfwm-zcRqLhWMefd5KOonU"
        "&fp=firefox&sni=eh.vk.com&sid=6b2f4e6ac9b1d2f0&spx=%2F&serviceName=grpc"
        "#%F0%9F%87%A9%F0%9F%87%AA%D0%93%D0%B5%D1%80%D0%BC%D0%B0%D0%BD%D0%B8%D1%8F-1"
    )
    p = uri_parsers.parse_uri(uri)
    check("vless: protocol", p["protocol"] == "vless")
    check("vless: server", p["server"] == "news.comrad-tech.site")
    check("vless: port", p["port"] == 8052)
    check("vless: uuid", p["uuid"] == "08b170a5-8606-4b89-b17b-10b28e843b50")
    check("vless: name url-decoded", p["name"] == "🇩🇪Германия-1", p["name"])
    check("vless: reality enabled", p["reality"]["enabled"] is True)
    check("vless: pbk", p["reality"]["public_key"] == "GVfGGMn8gxiL1bWdlfjhWxfwm-zcRqLhWMefd5KOonU")
    check("vless: sid", p["reality"]["short_id"] == "6b2f4e6ac9b1d2f0")
    check("vless: fp", p["reality"]["fingerprint"] == "firefox")
    check("vless: sni", p["tls"]["sni"] == "eh.vk.com")
    check("vless: transport grpc", p["transport"]["type"] == "grpc")
    check("vless: serviceName", p["transport"]["service_name"] == "grpc")

    outbound = singbox_config.profile_to_outbound(p)
    check("vless outbound: type", outbound["type"] == "vless")
    check("vless outbound: reality", outbound["tls"]["reality"]["enabled"] is True)
    check("vless outbound: transport", outbound["transport"]["type"] == "grpc")


def test_vless_ws():
    uri = "vless://uuid-1@1.2.3.4:443?type=ws&security=tls&sni=example.com&path=%2Fpath&host=example.com#name"
    p = uri_parsers.parse_uri(uri)
    check("vless ws: transport type", p["transport"]["type"] == "ws")
    check("vless ws: path", p["transport"]["path"] == "/path")
    check("vless ws: host", p["transport"]["host"] == "example.com")
    check("vless ws: tls enabled", p["tls"]["enabled"] is True)


def test_vless_missing_uuid_raises():
    try:
        uri_parsers.parse_uri("vless://@host:443")
        fail("vless missing uuid raises", "did not raise")
    except ValueError:
        ok("vless missing uuid raises")


# ---------------------------------------------------------------------------
# vmess
# ---------------------------------------------------------------------------

def test_vmess():
    import base64
    import json

    payload = {
        "v": "2", "ps": "test-vmess", "add": "1.2.3.4", "port": "443",
        "id": "abc-uuid", "aid": "0", "net": "ws", "type": "none",
        "host": "example.com", "path": "/ws", "tls": "tls", "sni": "example.com",
    }
    b64 = base64.b64encode(json.dumps(payload).encode()).decode()
    uri = f"vmess://{b64}"
    p = uri_parsers.parse_uri(uri)
    check("vmess: protocol", p["protocol"] == "vmess")
    check("vmess: server", p["server"] == "1.2.3.4")
    check("vmess: port", p["port"] == 443)
    check("vmess: uuid", p["uuid"] == "abc-uuid")
    check("vmess: name", p["name"] == "test-vmess")
    check("vmess: transport type", p["transport"]["type"] == "ws")
    check("vmess: tls enabled", p["tls"]["enabled"] is True)

    outbound = singbox_config.profile_to_outbound(p)
    check("vmess outbound: type", outbound["type"] == "vmess")


# ---------------------------------------------------------------------------
# trojan
# ---------------------------------------------------------------------------

def test_trojan():
    uri = "trojan://mypassword@1.2.3.4:443?sni=example.com&allowInsecure=1#trojan-name"
    p = uri_parsers.parse_uri(uri)
    check("trojan: protocol", p["protocol"] == "trojan")
    check("trojan: password", p["password"] == "mypassword")
    check("trojan: sni", p["tls"]["sni"] == "example.com")
    check("trojan: insecure", p["tls"]["insecure"] is True)

    outbound = singbox_config.profile_to_outbound(p)
    check("trojan outbound: type", outbound["type"] == "trojan")
    check("trojan outbound: tls enabled", outbound["tls"]["enabled"] is True)


# ---------------------------------------------------------------------------
# shadowsocks
# ---------------------------------------------------------------------------

def test_shadowsocks_sip002():
    import base64
    userinfo = base64.b64encode(b"aes-256-gcm:secretpass").decode()
    uri = f"ss://{userinfo}@1.2.3.4:8388#ss-name"
    p = uri_parsers.parse_uri(uri)
    check("ss sip002: method", p["method"] == "aes-256-gcm")
    check("ss sip002: password", p["password"] == "secretpass")
    check("ss sip002: server", p["server"] == "1.2.3.4")
    check("ss sip002: port", p["port"] == 8388)


def test_shadowsocks_legacy():
    import base64
    full = base64.b64encode(b"aes-256-gcm:secretpass@1.2.3.4:8388").decode()
    uri = f"ss://{full}#legacy-name"
    p = uri_parsers.parse_uri(uri)
    check("ss legacy: method", p["method"] == "aes-256-gcm")
    check("ss legacy: password", p["password"] == "secretpass")
    check("ss legacy: server", p["server"] == "1.2.3.4")
    check("ss legacy: port", p["port"] == 8388)


# ---------------------------------------------------------------------------
# hysteria2
# ---------------------------------------------------------------------------

def test_hysteria2():
    uri = "hysteria2://mypass@1.2.3.4:443?sni=example.com&obfs=salamander&obfs-password=obfspass#hy2-name"
    p = uri_parsers.parse_uri(uri)
    check("hy2: protocol", p["protocol"] == "hysteria2")
    check("hy2: password", p["password"] == "mypass")
    check("hy2: sni", p["tls"]["sni"] == "example.com")
    check("hy2: obfs type", p["obfs"]["type"] == "salamander")
    check("hy2: obfs password", p["obfs"]["password"] == "obfspass")

    outbound = singbox_config.profile_to_outbound(p)
    check("hy2 outbound: type", outbound["type"] == "hysteria2")
    check("hy2 outbound: obfs", outbound["obfs"]["type"] == "salamander")


def test_hy2_alias():
    uri = "hy2://mypass@1.2.3.4:443#name"
    p = uri_parsers.parse_uri(uri)
    check("hy2 alias: protocol", p["protocol"] == "hysteria2")


def test_malformed_uri_raises():
    try:
        uri_parsers.parse_uri("not-a-valid-uri")
        fail("malformed uri raises", "did not raise")
    except ValueError:
        ok("malformed uri raises")

    try:
        uri_parsers.parse_uri("ftp://host:21")
        fail("unsupported scheme raises", "did not raise")
    except ValueError:
        ok("unsupported scheme raises")


# ---------------------------------------------------------------------------
# singbox_config.build_config structure
# ---------------------------------------------------------------------------

def test_build_config_structure():
    p = uri_parsers.parse_uri("vless://uuid-1@1.2.3.4:443?security=none#name")
    outbound = singbox_config.profile_to_outbound(p)
    config = singbox_config.build_config(outbound)

    check("config: one tun inbound", len(config["inbounds"]) == 1 and config["inbounds"][0]["type"] == "tun")
    check("config: auto_route", config["inbounds"][0]["auto_route"] is True)
    outbound_types = {o["type"] for o in config["outbounds"]}
    check("config: has direct+block+proxy", {"direct", "block", "vless"} <= outbound_types)
    rule_targets = [r.get("outbound") for r in config["route"]["rules"]]
    check("config: has ip_is_private bypass rule", "direct" in rule_targets)
    check("config: final route is proxy", config["route"]["final"] == outbound["tag"])


# ---------------------------------------------------------------------------
# Real subscription fixture (captured live from
# https://sub.comrad-tech.site:8443/3b0346da051447ef8be4350a5dd6e2f7)
# ---------------------------------------------------------------------------

SUBSCRIPTION_BODY_B64 = (
    "dmxlc3M6Ly8wOGIxNzBhNS04NjA2LTRiODktYjE3Yi0xMGIyOGU4NDNiNTBAbmV3cy5jb21yYWQtdGVjaC5zaXRlOjgwNTI/"
    "dHlwZT1ncnBjJnNlY3VyaXR5PXJlYWxpdHkmcGJrPUdWZkdHTW44Z3hpTDFiV2RsZmpoV3hmd20temNScUxoV01lZmQ1S09v"
    "blUmZnA9ZmlyZWZveCZzbmk9ZWgudmsuY29tJnNpZD02YjJmNGU2YWM5YjFkMmYwJnNweD0lMkYmc2VydmljZU5hbWU9Z3Jw"
    "YyMlRjAlOUYlODclQTklRjAlOUYlODclQUElRDAlOTMlRDAlQjUlRDElODAlRDAlQkMlRDAlQjAlRDAlQkQlRDAlQjglRDEl"
    "OEYtMQp2bGVzczovLzczNDEzZDYxLTZiMzktNDRkNC04ZWRhLTI4ZmRlNmJlZTUzOUAxNzguMjUwLjE4Ni4xMDQ6ODUwMj90"
    "eXBlPWdycGMmc2VjdXJpdHk9cmVhbGl0eSZwYms9UVdGOWpWLWlLNDJ0N0JYcnBkUU5IV3BvTnBhZ2luSk1KZnlsQ0F3aXAw"
    "dyZmcD1jaHJvbWUmc25pPXhuLS1kMWFjcGp4M2YueG4tLXAxYWkmc2lkPWNmNWZiMSZzcHg9JTJGcGhpUVkxTTJMeHBSekNC"
    "JnNlcnZpY2VOYW1lPWdycGMjJUYwJTlGJTg3JUE5JUYwJTlGJTg3JUFBJUQwJTkzJUQwJUI1JUQxJTgwJUQwJUJDJUQwJUIw"
    "JUQwJUJEJUQwJUI4JUQxJThGLTI="
)


def test_real_subscription_body():
    import base64

    body = base64.b64decode(SUBSCRIPTION_BODY_B64)
    links = SubscriptionManager._parse_body(None, body)
    check("subscription body: 2 links", len(links) == 2, str(links))
    check("subscription body: both vless", all(l.startswith("vless://") for l in links))

    parsed = [uri_parsers.parse_uri(l) for l in links]
    check("subscription body: name 1", parsed[0]["name"] == "🇩🇪Германия-1", parsed[0]["name"])
    check("subscription body: name 2", parsed[1]["name"] == "🇩🇪Германия-2", parsed[1]["name"])


def test_real_subscription_headers():
    headers = {
        "profile-title": "base64:Q29tcmFkZSAyMjE0MDAyMDE=",
        "subscription-userinfo": "upload=0; download=0; total=0; expire=1836367549",
        "support-url": "https://t.me/comradeVPN_support",
        "profile-update-interval": "1",
    }
    meta = SubscriptionManager._parse_headers(None, headers)
    check("headers: title decoded", meta["title"] == "Comrade 221400201", meta["title"])
    check("headers: support_url", meta["support_url"] == "https://t.me/comradeVPN_support")
    check("headers: userinfo upload", meta["userinfo"]["upload"] == 0)
    check("headers: userinfo expire", meta["userinfo"]["expire"] == 1836367549)


def main():
    print("=" * 60)
    print("Unit Tests")
    print("=" * 60)

    test_vless_reality_grpc()
    test_vless_ws()
    test_vless_missing_uuid_raises()
    test_vmess()
    test_trojan()
    test_shadowsocks_sip002()
    test_shadowsocks_legacy()
    test_hysteria2()
    test_hy2_alias()
    test_malformed_uri_raises()
    test_build_config_structure()
    test_real_subscription_body()
    test_real_subscription_headers()

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
