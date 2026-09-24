"""
singbox_config - pure functions converting a normalized profile dict
(see uri_parsers.py) into a sing-box outbound object, and assembling the
full sing-box run config (tun inbound + routing).
"""

from typing import Any, Dict, List, Optional

TUN_INTERFACE_NAME = "singbox-tun0"


def _tls_block(profile: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    tls = profile.get("tls") or {}
    if not tls.get("enabled"):
        return None

    block: Dict[str, Any] = {"enabled": True}
    if tls.get("sni"):
        block["server_name"] = tls["sni"]
    if tls.get("alpn"):
        block["alpn"] = tls["alpn"]
    if tls.get("insecure"):
        block["insecure"] = True

    reality = profile.get("reality") or {}
    if reality.get("enabled"):
        block["reality"] = {
            "enabled": True,
            "public_key": reality.get("public_key", ""),
            "short_id": reality.get("short_id", ""),
        }
        fingerprint = reality.get("fingerprint")
        if fingerprint:
            block["utls"] = {"enabled": True, "fingerprint": fingerprint}

    return block


def _transport_block(profile: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    transport = profile.get("transport") or {}
    t_type = transport.get("type", "tcp")
    if t_type in ("", "tcp", "raw"):
        return None
    if t_type == "grpc":
        return {"type": "grpc", "service_name": transport.get("service_name", "")}
    if t_type in ("ws", "httpupgrade", "xhttp", "splithttp"):
        block: Dict[str, Any] = {"type": t_type, "path": transport.get("path", "")}
        host = transport.get("host", "")
        if host:
            block["headers"] = {"Host": host}
        return block
    return None


def profile_to_outbound(profile: Dict[str, Any], tag: str = "proxy") -> Dict[str, Any]:
    """Converts a normalized profile dict into a sing-box outbound object."""
    protocol = profile["protocol"]

    if protocol == "vless":
        outbound: Dict[str, Any] = {
            "type": "vless",
            "tag": tag,
            "server": profile["server"],
            "server_port": profile["port"],
            "uuid": profile["uuid"],
        }
        if profile.get("flow"):
            outbound["flow"] = profile["flow"]
        tls = _tls_block(profile)
        if tls:
            outbound["tls"] = tls
        transport = _transport_block(profile)
        if transport:
            outbound["transport"] = transport
        return outbound

    if protocol == "vmess":
        outbound = {
            "type": "vmess",
            "tag": tag,
            "server": profile["server"],
            "server_port": profile["port"],
            "uuid": profile["uuid"],
            "security": "auto",
            "alter_id": 0,
        }
        tls = _tls_block(profile)
        if tls:
            outbound["tls"] = tls
        transport = _transport_block(profile)
        if transport:
            outbound["transport"] = transport
        return outbound

    if protocol == "trojan":
        outbound = {
            "type": "trojan",
            "tag": tag,
            "server": profile["server"],
            "server_port": profile["port"],
            "password": profile["password"],
        }
        tls = _tls_block(profile) or {"enabled": True}
        outbound["tls"] = tls
        transport = _transport_block(profile)
        if transport:
            outbound["transport"] = transport
        return outbound

    if protocol == "shadowsocks":
        return {
            "type": "shadowsocks",
            "tag": tag,
            "server": profile["server"],
            "server_port": profile["port"],
            "method": profile["method"],
            "password": profile["password"],
        }

    if protocol == "hysteria2":
        outbound = {
            "type": "hysteria2",
            "tag": tag,
            "server": profile["server"],
            "server_port": profile["port"],
            "password": profile["password"],
        }
        tls = _tls_block(profile) or {"enabled": True}
        outbound["tls"] = tls
        obfs = profile.get("obfs")
        if obfs:
            outbound["obfs"] = {"type": obfs.get("type", "salamander"), "password": obfs.get("password", "")}
        return outbound

    raise ValueError(f"unsupported protocol for sing-box outbound: {protocol}")


def build_config(outbound: Dict[str, Any], log_path: Optional[str] = None, dns_server_host: str = "1.1.1.1") -> Dict[str, Any]:
    """Assembles the full sing-box JSON run config for a single active tunnel."""
    log: Dict[str, Any] = {"level": "info"}
    if log_path:
        log["output"] = log_path

    return {
        "log": log,
        "dns": {
            # sing-box >= 1.12 dns.servers format: explicit `type` per server
            # (the old single-string `address: "https://..."` form was
            # removed entirely in 1.14.0 - see
            # https://sing-box.sagernet.org/migration/#migrate-to-new-dns-server-formats).
            # No `detour` set (defaults to a plain direct connection), NOT
            # "proxy": resolving DNS through the same tunnel that carries
            # general traffic creates a circular/nested connection for every
            # single lookup (each DoH query opens another logical stream
            # inside the already-open proxy tunnel), which measured 8-20s+
            # per query in practice and made every domain-based check time
            # out while IP-literal probes (no DNS needed) stayed fast.
            # Explicitly setting `"detour": "direct"` is rejected by
            # sing-box ("detour to an empty direct outbound makes no
            # sense") - omitting the field is the correct way to get the
            # same plain-direct behavior. Resolving via the real network
            # directly is fast and still encrypted (DoH); only the resolved
            # app traffic itself needs to go through the tunnel
            # (route.final below), not the DNS lookup.
            "servers": [
                {
                    "type": "https",
                    "tag": "remote",
                    "server": dns_server_host,
                    "server_port": 443,
                    "path": "/dns-query",
                },
            ],
            "final": "remote",
        },
        "inbounds": [
            {
                "type": "tun",
                "tag": "tun-in",
                "interface_name": TUN_INTERFACE_NAME,
                "address": ["172.19.0.1/30"],
                "auto_route": True,
                # strict_route intentionally False: it captures ALL traffic
                # at the kernel routing level (including LAN/SSH return
                # traffic to the Deck itself), and in live testing this
                # broke the very SSH session used to manage the device -
                # even though route.rules already sends ip_is_private
                # traffic through "direct" at the app layer, strict_route's
                # kernel-level capture happened before that rule could save
                # it. Not needed for this plugin's goal (route app traffic
                # through the VPN), only for stricter anti-leak hardening.
                "strict_route": False,
                "stack": "system",
                "mtu": 1500,
            }
        ],
        "outbounds": [
            outbound,
            {"type": "direct", "tag": "direct"},
            {"type": "block", "tag": "block"},
        ],
        "route": {
            "auto_detect_interface": True,
            "rules": [
                {"ip_is_private": True, "outbound": "direct"},
                {"protocol": "dns", "outbound": "direct"},
            ],
            "final": outbound["tag"],
        },
    }
