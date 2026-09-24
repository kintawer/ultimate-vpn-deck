"""
uri_parsers - pure functions converting sharing-link URIs (vless://, vmess://,
trojan://, ss://, hysteria2://) into a normalized "profile dict".

These are generic Xray/V2Ray-ecosystem sharing-link formats (not Happ-specific).
No `decky` import here on purpose - keeps this module trivially unit-testable.

Normalized profile dict shape:
{
    "protocol": "vless" | "vmess" | "trojan" | "shadowsocks" | "hysteria2",
    "name": str,                 # url-decoded fragment / remark
    "server": str,
    "port": int,
    "uuid": str | None,          # vless/vmess
    "password": str | None,      # trojan/ss/hysteria2
    "method": str | None,        # shadowsocks cipher
    "flow": str,                 # vless
    "tls": {"enabled": bool, "sni": str, "alpn": list[str], "insecure": bool},
    "reality": {"enabled": bool, "public_key": str, "short_id": str, "fingerprint": str},
    "transport": {"type": str, "path": str, "host": str, "service_name": str},
    "obfs": {"type": str, "password": str} | None,   # hysteria2
    "raw_uri": str,
}
"""

import base64
import binascii
import json
from typing import Any, Dict, List
from urllib.parse import parse_qs, unquote, urlparse


def _b64decode(data: str) -> bytes:
    """Decodes base64 that may be URL-safe and/or missing padding."""
    data = data.strip()
    data = data.replace("-", "+").replace("_", "/")
    padding = len(data) % 4
    if padding:
        data += "=" * (4 - padding)
    return base64.b64decode(data)


def _qs(query: str) -> Dict[str, str]:
    parsed = parse_qs(query, keep_blank_values=True)
    return {k: v[0] for k, v in parsed.items() if v}


def _split_alpn(value: str) -> List[str]:
    return [a for a in value.split(",") if a] if value else []


def _base_envelope(protocol: str, name: str, server: str, port: int, raw_uri: str) -> Dict[str, Any]:
    return {
        "protocol": protocol,
        "name": name or server,
        "server": server,
        "port": port,
        "uuid": None,
        "password": None,
        "method": None,
        "flow": "",
        "tls": {"enabled": False, "sni": "", "alpn": [], "insecure": False},
        "reality": {"enabled": False, "public_key": "", "short_id": "", "fingerprint": ""},
        "transport": {"type": "tcp", "path": "", "host": "", "service_name": ""},
        "obfs": None,
        "raw_uri": raw_uri,
    }


def parse_vless(uri: str) -> Dict[str, Any]:
    parsed = urlparse(uri)
    if not parsed.hostname or not parsed.username:
        raise ValueError("vless:// link is missing host or uuid")
    q = _qs(parsed.query)
    name = unquote(parsed.fragment)

    profile = _base_envelope("vless", name, parsed.hostname, parsed.port or 443, uri)
    profile["uuid"] = parsed.username
    profile["flow"] = q.get("flow", "")

    security = q.get("security", "none")
    profile["tls"]["enabled"] = security in ("tls", "reality")
    profile["tls"]["sni"] = q.get("sni", "")
    profile["tls"]["alpn"] = _split_alpn(q.get("alpn", ""))
    profile["tls"]["insecure"] = q.get("allowInsecure", q.get("insecure", "0")) in ("1", "true")

    if security == "reality":
        profile["reality"]["enabled"] = True
        profile["reality"]["public_key"] = q.get("pbk", "")
        profile["reality"]["short_id"] = q.get("sid", "")
        profile["reality"]["fingerprint"] = q.get("fp", "")

    net_type = q.get("type", "tcp")
    profile["transport"]["type"] = net_type
    if net_type == "grpc":
        profile["transport"]["service_name"] = q.get("serviceName", "")
    elif net_type in ("ws", "httpupgrade", "xhttp", "splithttp"):
        profile["transport"]["path"] = q.get("path", "")
        profile["transport"]["host"] = q.get("host", "")

    return profile


def parse_vmess(uri: str) -> Dict[str, Any]:
    payload = uri[len("vmess://"):]
    try:
        raw = _b64decode(payload)
        data = json.loads(raw.decode("utf-8"))
    except (binascii.Error, ValueError, UnicodeDecodeError) as e:
        raise ValueError(f"malformed vmess:// payload: {e}") from e

    server = data.get("add", "")
    port = int(data.get("port", 443) or 443)
    if not server:
        raise ValueError("vmess:// payload is missing 'add' (server)")

    name = data.get("ps", "")
    profile = _base_envelope("vmess", name, server, port, uri)
    profile["uuid"] = data.get("id", "")

    tls = data.get("tls", "")
    profile["tls"]["enabled"] = tls in ("tls", "reality")
    profile["tls"]["sni"] = data.get("sni", "") or data.get("host", "")
    profile["tls"]["alpn"] = _split_alpn(data.get("alpn", ""))

    net_type = data.get("net", "tcp")
    profile["transport"]["type"] = net_type
    if net_type == "grpc":
        profile["transport"]["service_name"] = data.get("path", "") or data.get("serviceName", "")
    elif net_type in ("ws", "httpupgrade", "xhttp", "splithttp"):
        profile["transport"]["path"] = data.get("path", "")
        profile["transport"]["host"] = data.get("host", "")

    return profile


def parse_trojan(uri: str) -> Dict[str, Any]:
    parsed = urlparse(uri)
    if not parsed.hostname or not parsed.username:
        raise ValueError("trojan:// link is missing host or password")
    q = _qs(parsed.query)
    name = unquote(parsed.fragment)

    profile = _base_envelope("trojan", name, parsed.hostname, parsed.port or 443, uri)
    profile["password"] = unquote(parsed.username)

    profile["tls"]["enabled"] = q.get("security", "tls") != "none"
    profile["tls"]["sni"] = q.get("sni", q.get("peer", ""))
    profile["tls"]["alpn"] = _split_alpn(q.get("alpn", ""))
    profile["tls"]["insecure"] = q.get("allowInsecure", q.get("insecure", "0")) in ("1", "true")

    net_type = q.get("type", "tcp")
    profile["transport"]["type"] = net_type
    if net_type == "grpc":
        profile["transport"]["service_name"] = q.get("serviceName", "")
    elif net_type in ("ws", "httpupgrade", "xhttp", "splithttp"):
        profile["transport"]["path"] = q.get("path", "")
        profile["transport"]["host"] = q.get("host", "")

    return profile


def parse_shadowsocks(uri: str) -> Dict[str, Any]:
    body = uri[len("ss://"):]
    fragment = ""
    if "#" in body:
        body, fragment = body.split("#", 1)
    name = unquote(fragment)

    if "@" in body:
        # SIP002: ss://BASE64(method:password)@host:port[/?plugin=...]
        userinfo, hostinfo = body.split("@", 1)
        hostinfo = hostinfo.split("/", 1)[0].split("?", 1)[0]
        try:
            decoded = _b64decode(userinfo).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            decoded = unquote(userinfo)  # some generators leave it plain
        if ":" not in decoded:
            raise ValueError("malformed ss:// userinfo (expected method:password)")
        method, password = decoded.split(":", 1)
        if ":" not in hostinfo:
            raise ValueError("malformed ss:// host:port")
        host, port_str = hostinfo.rsplit(":", 1)
    else:
        # legacy: ss://BASE64(method:password@host:port)
        try:
            decoded = _b64decode(body).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError) as e:
            raise ValueError(f"malformed ss:// payload: {e}") from e
        if "@" not in decoded or ":" not in decoded:
            raise ValueError("malformed legacy ss:// payload")
        cred, hostinfo = decoded.rsplit("@", 1)
        method, password = cred.split(":", 1)
        host, port_str = hostinfo.rsplit(":", 1)

    profile = _base_envelope("shadowsocks", name, host, int(port_str), uri)
    profile["method"] = method
    profile["password"] = password
    return profile


def parse_hysteria2(uri: str) -> Dict[str, Any]:
    # normalize the hy2:// alias to hysteria2:// for urlparse's scheme handling
    normalized = uri
    if normalized.startswith("hy2://"):
        normalized = "hysteria2://" + normalized[len("hy2://"):]

    parsed = urlparse(normalized)
    if not parsed.hostname:
        raise ValueError("hysteria2:// link is missing host")
    q = _qs(parsed.query)
    name = unquote(parsed.fragment)

    profile = _base_envelope("hysteria2", name, parsed.hostname, parsed.port or 443, uri)
    profile["password"] = unquote(parsed.username or "")

    profile["tls"]["enabled"] = True
    profile["tls"]["sni"] = q.get("sni", q.get("peer", ""))
    profile["tls"]["insecure"] = q.get("insecure", "0") in ("1", "true")

    obfs_type = q.get("obfs", "")
    if obfs_type:
        profile["obfs"] = {
            "type": obfs_type,
            "password": q.get("obfs-password", q.get("obfsParam", "")),
        }

    return profile


_PARSERS = {
    "vless": parse_vless,
    "vmess": parse_vmess,
    "trojan": parse_trojan,
    "ss": parse_shadowsocks,
    "hysteria2": parse_hysteria2,
    "hy2": parse_hysteria2,
}


def parse_uri(uri: str) -> Dict[str, Any]:
    """Dispatches a sharing-link URI to the matching protocol parser."""
    uri = uri.strip()
    if "://" not in uri:
        raise ValueError("not a valid sharing link (missing scheme)")
    scheme = uri.split("://", 1)[0].lower()
    parser = _PARSERS.get(scheme)
    if parser is None:
        raise ValueError(f"unsupported protocol scheme: {scheme}")
    return parser(uri)
