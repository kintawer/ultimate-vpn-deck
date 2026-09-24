"""
SubscriptionManager - fetch & parse standard HTTP(S) VPN subscriptions.

Subscription response body is base64 of a newline-separated list of sharing
links (vless://, vmess://, ...). Metadata comes from response headers:
profile-title, subscription-userinfo, announce, support-url,
profile-update-interval. This is a generic Xray/V2Ray-ecosystem convention,
verified live against a real Happ-compatible subscription endpoint - not
Happ-proprietary. Proprietary `happ://crypt4/`/`happ://crypt5/` links are
out of scope (require private keys embedded in the closed-source Happ app).
"""

import base64
import binascii
import glob
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

import decky

from .profile_manager import ProfileManager

REQUEST_TIMEOUT_SEC = 10
USER_AGENT = "ultimate-vpn-deck/1.0 (SteamDeck; sing-box)"


def _maybe_b64decode_text(value: str) -> str:
    """Decodes a `base64:<...>` prefixed header value; passes plain text through."""
    if not value:
        return value
    if value.startswith("base64:"):
        payload = value[len("base64:"):]
        try:
            return base64.b64decode(payload + "=" * (-len(payload) % 4)).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            return value
    return value


def _parse_userinfo(value: str) -> Dict[str, Optional[int]]:
    result: Dict[str, Optional[int]] = {"upload": None, "download": None, "total": None, "expire": None}
    for part in value.split(";"):
        part = part.strip()
        if "=" not in part:
            continue
        key, _, raw = part.partition("=")
        key = key.strip()
        if key in result:
            try:
                result[key] = int(raw.strip())
            except ValueError:
                pass
    return result


class SubscriptionManager:
    def __init__(self, profile_manager: ProfileManager):
        self.profile_manager = profile_manager
        self.settings_dir = decky.DECKY_PLUGIN_SETTINGS_DIR
        self.subs_dir = os.path.join(self.settings_dir, "subscriptions")
        os.makedirs(self.subs_dir, mode=0o700, exist_ok=True)

    @staticmethod
    def _generate_id(url: str) -> str:
        return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]

    def _sub_path(self, sub_id: str) -> str:
        return os.path.join(self.subs_dir, f"{sub_id}.json")

    def list_subscriptions(self) -> List[Dict[str, Any]]:
        subs = []
        for path in sorted(glob.glob(os.path.join(self.subs_dir, "*.json"))):
            try:
                with open(path, "r") as f:
                    subs.append(json.load(f))
            except (OSError, ValueError) as e:
                decky.logger.warning(f"Skipping unreadable subscription file {path}: {e}")
        return subs

    def get_subscription(self, sub_id: str) -> Optional[Dict[str, Any]]:
        path = self._sub_path(sub_id)
        if not os.path.isfile(path):
            return None
        try:
            with open(path, "r") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    # ── fetch / parse ───────────────────────────────────────────

    def _fetch(self, url: str) -> Tuple[bytes, Dict[str, str]]:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SEC) as resp:
            body = resp.read()
            headers = {k.lower(): v for k, v in resp.headers.items()}
        return body, headers

    def _parse_body(self, body: bytes) -> List[str]:
        text = body.decode("utf-8", errors="ignore").strip()
        decoded = text
        try:
            decoded = base64.b64decode(text + "=" * (-len(text) % 4)).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            decoded = text  # already plain text
        links = [line.strip() for line in decoded.splitlines()]
        return [line for line in links if "://" in line]

    def _parse_headers(self, headers: Dict[str, str]) -> Dict[str, Any]:
        return {
            "title": _maybe_b64decode_text(headers.get("profile-title", "")),
            "announce": _maybe_b64decode_text(headers.get("announce", "")),
            "support_url": headers.get("support-url", ""),
            "update_interval_hours": headers.get("profile-update-interval", ""),
            "userinfo": _parse_userinfo(headers.get("subscription-userinfo", "")),
        }

    # ── CRUD ─────────────────────────────────────────────────────

    def add_subscription(self, url: str) -> Dict[str, Any]:
        url = (url or "").strip()
        if not url:
            return {"success": False, "sub_id": None, "error": "empty url"}

        sub_id = self._generate_id(url)
        try:
            body, headers = self._fetch(url)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            return {"success": False, "sub_id": None, "error": f"fetch failed: {e}"}

        links = self._parse_body(body)
        if not links:
            return {"success": False, "sub_id": None, "error": "subscription contains no links"}

        meta = self._parse_headers(headers)
        profile_ids = []
        for link in links:
            result = self.profile_manager.add_profile_from_uri(link, source=f"subscription:{sub_id}")
            if result["success"]:
                profile_ids.append(result["profile_id"])
            else:
                decky.logger.warning(f"Skipping unparseable subscription link: {result['error']}")

        record = {
            "id": sub_id,
            "url": url,
            "last_refreshed": time.time(),
            "profile_ids": profile_ids,
            **meta,
        }
        with open(self._sub_path(sub_id), "w") as f:
            json.dump(record, f, indent=2)
        os.chmod(self._sub_path(sub_id), 0o600)
        return {"success": True, "sub_id": sub_id, "error": None, "profiles_added": len(profile_ids)}

    def refresh_subscription(self, sub_id: str) -> Dict[str, Any]:
        existing = self.get_subscription(sub_id)
        if not existing:
            return {"success": False, "error": "subscription not found"}

        try:
            body, headers = self._fetch(existing["url"])
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            return {"success": False, "error": f"fetch failed: {e}"}

        links = self._parse_body(body)
        if not links:
            return {"success": False, "error": "subscription contains no links"}

        meta = self._parse_headers(headers)

        # Replace this subscription's profiles. Stable ids (hash of raw_uri)
        # mean unchanged links keep their id, so an active tunnel on an
        # unchanged link survives the refresh.
        self.profile_manager.delete_profiles_by_source_prefix(f"subscription:{sub_id}")
        profile_ids = []
        for link in links:
            result = self.profile_manager.add_profile_from_uri(link, source=f"subscription:{sub_id}")
            if result["success"]:
                profile_ids.append(result["profile_id"])

        record = {
            "id": sub_id,
            "url": existing["url"],
            "last_refreshed": time.time(),
            "profile_ids": profile_ids,
            **meta,
        }
        with open(self._sub_path(sub_id), "w") as f:
            json.dump(record, f, indent=2)
        os.chmod(self._sub_path(sub_id), 0o600)
        return {"success": True, "error": None, "profiles_added": len(profile_ids)}

    def delete_subscription(self, sub_id: str, delete_profiles: bool = True) -> Dict[str, Any]:
        path = self._sub_path(sub_id)
        if not os.path.isfile(path):
            return {"success": False, "error": "subscription not found"}
        if delete_profiles:
            self.profile_manager.delete_profiles_by_source_prefix(f"subscription:{sub_id}")
        os.remove(path)
        return {"success": True, "error": None}
