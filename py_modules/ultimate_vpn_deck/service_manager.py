"""
ServiceManager - manages the sing-box subprocess lifecycle.

Unlike vpn-deck's `awg-quick up/down` (a fire-and-forget daemonizing script
whose state is queried via `awg show`), sing-box is a long-running foreground
process (`sing-box run -c <config>`), so we track it ourselves via
subprocess.Popen + a pidfile, rather than asking an external tool "what's
running".
"""

import os
import signal
import subprocess
import time
from datetime import datetime
from typing import Any, Dict, Optional

import decky

from ._utils import clean_env

START_STOP_TIMEOUT_SEC = 60
STOP_POLL_INTERVAL_SEC = 0.2


class ServiceManager:
    def __init__(self, binary_manager):
        self.binary_manager = binary_manager
        self.pid_path = os.path.join(decky.DECKY_PLUGIN_LOG_DIR, "sing-box.pid")
        self.log_path = os.path.join(decky.DECKY_PLUGIN_LOG_DIR, "sing-box.log")
        self._start_time: Optional[float] = None

    # ── pidfile helpers ─────────────────────────────────────────

    def _write_pidfile(self, pid: int) -> None:
        with open(self.pid_path, "w") as f:
            f.write(str(pid))

    def _read_pidfile(self) -> Optional[int]:
        if not os.path.isfile(self.pid_path):
            return None
        try:
            with open(self.pid_path, "r") as f:
                return int(f.read().strip())
        except (OSError, ValueError):
            return None

    def _clear_pidfile(self) -> None:
        if os.path.isfile(self.pid_path):
            try:
                os.remove(self.pid_path)
            except OSError:
                pass

    @staticmethod
    def _is_process_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
        except ProcessLookupError:
            return False

    def _tail_log(self, lines: int = 20) -> str:
        if not os.path.isfile(self.log_path):
            return ""
        try:
            with open(self.log_path, "r") as f:
                return "".join(f.readlines()[-lines:]).strip()
        except OSError:
            return ""

    # ── lifecycle ────────────────────────────────────────────────

    def start(self, config_path: str) -> Dict[str, Any]:
        # Enforces "only one active tunnel at a time".
        self.stop()

        binary = self.binary_manager.get_binary_path("sing-box")
        if not binary:
            return {"success": False, "pid": None, "error": "sing-box binary not found"}

        try:
            with open(self.log_path, "a") as log_file:
                log_file.write(f"\n--- {datetime.now().isoformat()} | starting with {config_path} ---\n")
                log_file.flush()
                proc = subprocess.Popen(
                    [binary, "run", "-c", config_path],
                    stdout=log_file,
                    stderr=log_file,
                    start_new_session=True,
                    env=clean_env(),
                )
        except FileNotFoundError:
            return {"success": False, "pid": None, "error": "sing-box binary not found"}
        except OSError as e:
            return {"success": False, "pid": None, "error": f"failed to spawn sing-box: {e}"}

        # Fast-fail detection: bad config / port busy / missing TUN permission.
        time.sleep(0.7)
        if proc.poll() is not None:
            tail = self._tail_log(20)
            return {
                "success": False,
                "pid": None,
                "error": f"sing-box exited immediately (rc={proc.returncode}): {tail}",
            }

        self._write_pidfile(proc.pid)
        self._start_time = time.time()
        decky.logger.info(f"sing-box started, pid={proc.pid}")
        return {"success": True, "pid": proc.pid, "error": None}

    def stop(self) -> Dict[str, Any]:
        pid = self._read_pidfile()
        if pid is None or not self._is_process_alive(pid):
            self._clear_pidfile()
            self._start_time = None
            return {"success": True, "error": None}

        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            self._clear_pidfile()
            self._start_time = None
            return {"success": True, "error": None}

        waited = 0.0
        while waited < START_STOP_TIMEOUT_SEC / 12 and self._is_process_alive(pid):
            time.sleep(STOP_POLL_INTERVAL_SEC)
            waited += STOP_POLL_INTERVAL_SEC

        if self._is_process_alive(pid):
            decky.logger.warning(f"sing-box pid={pid} did not exit on SIGTERM, sending SIGKILL")
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            time.sleep(0.3)

        self._clear_pidfile()
        self._start_time = None
        decky.logger.info(f"sing-box stopped (pid={pid})")
        return {"success": True, "error": None}

    def status(self) -> Dict[str, Any]:
        pid = self._read_pidfile()
        running = pid is not None and self._is_process_alive(pid)
        if not running:
            if pid is not None:
                # stale pidfile (crashed without cleanup)
                self._clear_pidfile()
            return {"running": False, "pid": None, "uptime_s": None}

        uptime = (time.time() - self._start_time) if self._start_time else None
        return {"running": True, "pid": pid, "uptime_s": uptime}

    def reconcile(self) -> Dict[str, Any]:
        """Called on plugin `_main()` startup: sync in-memory state with a
        potentially still-running sing-box process left over from before a
        plugin reload (we deliberately don't kill it in `_unload`)."""
        pid = self._read_pidfile()
        if pid is not None and self._is_process_alive(pid) and self._start_time is None:
            decky.logger.info(f"Reconciled running sing-box process, pid={pid}")
            self._start_time = time.time()  # uptime becomes approximate after a reload
        return self.status()
