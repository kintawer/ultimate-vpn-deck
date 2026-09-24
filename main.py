import functools
import json
import os
import time
import traceback as _traceback
from typing import Any, Dict, List, Optional

from ultimate_vpn_deck import (
    BinaryManager,
    Diagnostics,
    ProfileManager,
    ServiceManager,
    SubscriptionManager,
    singbox_config,
)

import decky


def _rpc(func):
    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs):
        try:
            return await func(self, *args, **kwargs)
        except Exception as e:
            tb = _traceback.format_exc()
            decky.logger.error(f"{func.__name__} exception: {tb}")
            if hasattr(self, "_add_error"):
                self._add_error(func.__name__, type(e).__name__, str(e), {"traceback": tb})
            return {"success": False, "error": f"{type(e).__name__}: {e}"}
    return wrapper


class Plugin:
    def __init__(self):
        self.errors: List[dict] = []
        self.max_errors = 50

        self.binary_manager = BinaryManager()
        self.profile_manager = ProfileManager()
        self.subscription_manager = SubscriptionManager(self.profile_manager)
        self.service_manager = ServiceManager(self.binary_manager)
        self.diagnostics = Diagnostics()

    def _add_error(self, operation: str, error_type: str, message: str, details: dict = None):
        error = {
            "timestamp": time.time(),
            "operation": operation,
            "error_type": error_type,
            "message": message,
            "details": details or {},
        }
        self.errors.append(error)
        if len(self.errors) > self.max_errors:
            self.errors = self.errors[-self.max_errors:]
        decky.logger.error(f"VPN Error [{error_type}] in {operation}: {message}")

    # ── lifecycle ────────────────────────────────────────────────

    async def _main(self):
        decky.logger.info("Ultimate VPN Deck plugin initialized")
        try:
            status = self.service_manager.reconcile()
            decky.logger.info(f"sing-box reconcile: {status}")
        except Exception as e:
            decky.logger.error(f"sing-box reconcile failed: {e}")

    async def _unload(self):
        # Deliberately does NOT stop sing-box: a plugin reload / QAM toggle
        # should not drop an active VPN connection.
        decky.logger.info("Ultimate VPN Deck plugin unloading")

    async def _uninstall(self):
        decky.logger.info("Ultimate VPN Deck plugin uninstalling")
        try:
            self.service_manager.stop()
        except Exception as e:
            decky.logger.error(f"Failed to stop sing-box on uninstall: {e}")

    async def _migration(self):
        decky.logger.info("Ultimate VPN Deck plugin migrating")

    # ── binaries ─────────────────────────────────────────────────

    @_rpc
    async def get_binaries_info(self) -> Dict[str, Dict[str, Optional[str]]]:
        return self.binary_manager.get_binaries_info()

    @_rpc
    async def check_binaries(self) -> Dict[str, bool]:
        binaries = self.binary_manager.detect_binaries()
        return {name: (path is not None) for name, path in binaries.items()}

    # ── profiles ─────────────────────────────────────────────────

    @_rpc
    async def list_profiles(self) -> List[Dict[str, Any]]:
        # Gate "active" by the real sing-box process status, not just the
        # stored active_profile_id: if a connect() attempt fails, the
        # previous tunnel has already been stopped (ServiceManager.start()
        # always stops first) but nothing new is running - without this
        # check the old profile's toggle would stay stuck "on".
        running = self.service_manager.status()["running"]
        active_id = self.profile_manager.get_active_profile_id() if running else None
        profiles = self.profile_manager.list_profiles()
        for p in profiles:
            p["active"] = p["id"] == active_id
        return profiles

    @_rpc
    async def get_profile(self, profile_id: str) -> Optional[Dict[str, Any]]:
        return self.profile_manager.get_profile(profile_id)

    @_rpc
    async def add_profile(self, uri: str) -> Dict[str, Any]:
        if isinstance(uri, dict):
            uri = uri.get("uri", "")
        result = self.profile_manager.add_profile_from_uri(uri, source="manual")
        if not result["success"]:
            self._add_error("add_profile", "ParseError", result["error"] or "unknown", {"uri": uri})
        return result

    @_rpc
    async def read_text_file(self, path: str) -> Dict[str, Any]:
        """Reads a small text file chosen via the frontend's file picker
        (link or subscription URL saved to a .txt file - avoids typing long
        links via the on-screen keyboard)."""
        if isinstance(path, dict):
            path = path.get("path", "")
        if not path or not os.path.isfile(path):
            return {"success": False, "content": None, "error": "file not found"}
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except OSError as e:
            return {"success": False, "content": None, "error": str(e)}
        return {"success": True, "content": content.strip(), "error": None}

    @_rpc
    async def delete_profile(self, profile_id: str) -> Dict[str, Any]:
        if isinstance(profile_id, dict):
            profile_id = profile_id.get("profile_id", "")
        if not profile_id:
            return {"success": False, "error": "profile_id is required"}
        if self.profile_manager.get_active_profile_id() == profile_id:
            self.service_manager.stop()
            self.profile_manager.clear_active()
        return self.profile_manager.delete_profile(profile_id)

    # ── subscriptions ────────────────────────────────────────────

    @_rpc
    async def list_subscriptions(self) -> List[Dict[str, Any]]:
        return self.subscription_manager.list_subscriptions()

    @_rpc
    async def add_subscription(self, url: str) -> Dict[str, Any]:
        if isinstance(url, dict):
            url = url.get("url", "")
        result = self.subscription_manager.add_subscription(url)
        if not result["success"]:
            self._add_error("add_subscription", "SubscriptionError", result["error"] or "unknown", {"url": url})
        return result

    @_rpc
    async def refresh_subscription(self, sub_id: str) -> Dict[str, Any]:
        if isinstance(sub_id, dict):
            sub_id = sub_id.get("sub_id", "")
        result = self.subscription_manager.refresh_subscription(sub_id)
        if not result["success"]:
            self._add_error("refresh_subscription", "SubscriptionError", result["error"] or "unknown", {"sub_id": sub_id})
        return result

    @_rpc
    async def delete_subscription(self, sub_id: str, delete_profiles: bool = True) -> Dict[str, Any]:
        if isinstance(sub_id, dict):
            delete_profiles = sub_id.get("delete_profiles", True)
            sub_id = sub_id.get("sub_id", "")
        active_id = self.profile_manager.get_active_profile_id()
        if active_id and delete_profiles:
            active_profile = self.profile_manager.get_profile(active_id)
            if active_profile and active_profile.get("source") == f"subscription:{sub_id}":
                self.service_manager.stop()
                self.profile_manager.clear_active()
        return self.subscription_manager.delete_subscription(sub_id, delete_profiles)

    # ── connection lifecycle (single active tunnel) ─────────────

    @_rpc
    async def connect(self, profile_id: str) -> Dict[str, Any]:
        if isinstance(profile_id, dict):
            profile_id = profile_id.get("profile_id", "")
        if not profile_id:
            return {"success": False, "error": "profile_id is required"}

        record = self.profile_manager.get_profile(profile_id)
        if not record:
            return {"success": False, "error": "profile not found"}

        try:
            outbound = singbox_config.profile_to_outbound(record["profile"])
        except ValueError as e:
            self._add_error("connect", "ConfigError", str(e), {"profile_id": profile_id})
            return {"success": False, "error": str(e)}

        core_log_path = os.path.join(decky.DECKY_PLUGIN_LOG_DIR, "sing-box-core.log")
        config = singbox_config.build_config(outbound, log_path=core_log_path)
        config_path = os.path.join(decky.DECKY_PLUGIN_RUNTIME_DIR, "singbox-config.json")
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)

        result = self.service_manager.start(config_path)
        if result["success"]:
            self.profile_manager.set_active(profile_id)
        else:
            self.profile_manager.clear_active()
            self._add_error("connect", "ServiceError", result["error"] or "unknown", {"profile_id": profile_id})
        return result

    @_rpc
    async def disconnect(self) -> Dict[str, Any]:
        result = self.service_manager.stop()
        self.profile_manager.clear_active()
        return result

    @_rpc
    async def status(self) -> Dict[str, Any]:
        svc_status = self.service_manager.status()
        active_id = self.profile_manager.get_active_profile_id()
        active_profile = self.profile_manager.get_profile(active_id) if active_id else None
        return {
            **svc_status,
            "active_profile_id": active_id if svc_status["running"] else None,
            "active_profile_name": active_profile["name"] if (svc_status["running"] and active_profile) else None,
        }

    # ── diagnostics / errors ─────────────────────────────────────

    @_rpc
    async def diagnose_connectivity(self, targets: Optional[List[Dict]] = None) -> List[Dict]:
        return self.diagnostics.check(targets)

    @_rpc
    async def get_errors(self) -> List[dict]:
        return list(self.errors)

    @_rpc
    async def clear_errors(self) -> bool:
        self.errors = []
        decky.logger.info("Error history cleared")
        return True
