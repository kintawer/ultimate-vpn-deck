"""
ProfileManager - CRUD storage for VPN profiles parsed from sharing links.

Profiles persist under DECKY_PLUGIN_SETTINGS_DIR (survives plugin reloads
and SteamOS updates - unlike vpn-deck's /etc symlink trick, sing-box takes
an explicit `-c <path>` config file, so no fixed system directory is needed).
"""

import glob
import hashlib
import json
import os
import time
from typing import Any, Dict, List, Optional

import decky

from .uri_parsers import parse_uri


class ProfileManager:
    def __init__(self):
        self.settings_dir = decky.DECKY_PLUGIN_SETTINGS_DIR
        self.profiles_dir = os.path.join(self.settings_dir, "profiles")
        self.state_path = os.path.join(self.settings_dir, "state.json")
        os.makedirs(self.profiles_dir, mode=0o700, exist_ok=True)

    # ── ids / paths ──────────────────────────────────────────────

    @staticmethod
    def _generate_id(raw_uri: str) -> str:
        return hashlib.sha1(raw_uri.encode("utf-8")).hexdigest()[:16]

    def _profile_path(self, profile_id: str) -> str:
        return os.path.join(self.profiles_dir, f"{profile_id}.json")

    # ── CRUD ─────────────────────────────────────────────────────

    def list_profiles(self) -> List[Dict[str, Any]]:
        profiles = []
        for path in sorted(glob.glob(os.path.join(self.profiles_dir, "*.json"))):
            try:
                with open(path, "r") as f:
                    profiles.append(json.load(f))
            except (OSError, ValueError) as e:
                decky.logger.warning(f"Skipping unreadable profile file {path}: {e}")
        return profiles

    def get_profile(self, profile_id: str) -> Optional[Dict[str, Any]]:
        path = self._profile_path(profile_id)
        if not os.path.isfile(path):
            return None
        try:
            with open(path, "r") as f:
                return json.load(f)
        except (OSError, ValueError) as e:
            decky.logger.warning(f"Failed to read profile {profile_id}: {e}")
            return None

    def add_profile_from_uri(self, uri: str, source: str = "manual") -> Dict[str, Any]:
        uri = (uri or "").strip()
        if not uri:
            return {"success": False, "profile_id": None, "error": "empty uri"}

        try:
            parsed = parse_uri(uri)
        except ValueError as e:
            return {"success": False, "profile_id": None, "error": str(e)}

        profile_id = self._generate_id(uri)
        existing = self.get_profile(profile_id)
        record = {
            "id": profile_id,
            "protocol": parsed["protocol"],
            "name": parsed["name"],
            "server": parsed["server"],
            "port": parsed["port"],
            "raw_uri": uri,
            "source": source,
            "added_at": existing["added_at"] if existing else time.time(),
            "profile": parsed,
        }
        with open(self._profile_path(profile_id), "w") as f:
            json.dump(record, f, indent=2)
        os.chmod(self._profile_path(profile_id), 0o600)
        return {"success": True, "profile_id": profile_id, "error": None}

    def delete_profile(self, profile_id: str) -> Dict[str, Any]:
        path = self._profile_path(profile_id)
        if not os.path.isfile(path):
            return {"success": False, "error": "profile not found"}
        os.remove(path)
        if self.get_active_profile_id() == profile_id:
            self.clear_active()
        return {"success": True, "error": None}

    def delete_profiles_by_source_prefix(self, prefix: str) -> List[str]:
        """Removes every profile whose `source` starts with `prefix`. Returns removed ids."""
        removed = []
        for profile in self.list_profiles():
            if profile.get("source", "").startswith(prefix):
                self.delete_profile(profile["id"])
                removed.append(profile["id"])
        return removed

    # ── active profile state ────────────────────────────────────

    def _read_state(self) -> Dict[str, Any]:
        if not os.path.isfile(self.state_path):
            return {}
        try:
            with open(self.state_path, "r") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _write_state(self, state: Dict[str, Any]) -> None:
        with open(self.state_path, "w") as f:
            json.dump(state, f)

    def get_active_profile_id(self) -> Optional[str]:
        return self._read_state().get("active_profile_id")

    def set_active(self, profile_id: str) -> None:
        self._write_state({"active_profile_id": profile_id})

    def clear_active(self) -> None:
        self._write_state({"active_profile_id": None})
