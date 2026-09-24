"""Diagnostics - connectivity probes for VPN troubleshooting."""

import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

import decky

from ._utils import clean_env


DEFAULT_TARGETS: List[Dict] = [
    {"name": "1.1.1.1", "kind": "ping", "host": "1.1.1.1"},
    {"name": "google.com", "kind": "http", "url": "https://www.google.com"},
    # show_body: ifconfig.me's whole response IS the externally-visible IP,
    # which is the actual point of this probe - display it, not just "OK".
    {"name": "ifconfig.me", "kind": "http", "url": "https://ifconfig.me", "show_body": True},
    # claude.ai redirects to a 200 OK "app-unavailable-in-region" page when
    # geo-blocked (not an HTTP error), so a plain status-code check would
    # report "ok" even while actually blocked - block_if_url_contains
    # inspects the final followed-redirect URL instead.
    {
        "name": "claude.ai",
        "kind": "http",
        "url": "https://claude.ai",
        "block_if_url_contains": "app-unavailable-in-region",
    },
]


class Diagnostics:
    def check(self, targets: Optional[List[Dict]] = None) -> List[Dict]:
        probes = targets if targets else DEFAULT_TARGETS
        if not probes:
            return []
        with ThreadPoolExecutor(max_workers=len(probes)) as pool:
            return list(pool.map(self._probe, probes))

    def _probe(self, t: Dict) -> Dict:
        kind = t.get("kind")
        name = t.get("name") or t.get("host") or t.get("url") or "?"
        if kind == "ping":
            return self._ping(name, t["host"])
        if kind == "http":
            return self._http(name, t["url"], t.get("block_if_url_contains"), t.get("show_body", False))
        return {"name": name, "kind": kind or "unknown", "ok": False, "detail": f"unknown kind: {kind}", "target": "", "latency_ms": None}

    @staticmethod
    def _ping(name: str, host: str) -> Dict:
        try:
            r = subprocess.run(
                ["ping", "-c", "3", "-W", "2", "-n", host],
                capture_output=True, text=True, timeout=12, check=False,
                env=clean_env(),
            )
            ok = r.returncode == 0
            avg_ms = None
            if ok:
                m = re.search(r"min/avg/max/\S+\s*=\s*[\d.]+/([\d.]+)/", r.stdout)
                if m:
                    avg_ms = float(m.group(1))
            detail = f"avg {avg_ms:.1f} ms" if avg_ms is not None else (r.stderr.strip() or "no response")
            return {"name": name, "kind": "ping", "target": host, "ok": ok, "detail": detail, "latency_ms": avg_ms}
        except subprocess.TimeoutExpired:
            return {"name": name, "kind": "ping", "target": host, "ok": False, "detail": "timeout", "latency_ms": None}
        except FileNotFoundError:
            decky.logger.warning("ping not found for diagnostics")
            return {"name": name, "kind": "ping", "target": host, "ok": False, "detail": "ping not found", "latency_ms": None}

    @staticmethod
    def _http(name: str, url: str, block_if_url_contains: Optional[str] = None, show_body: bool = False) -> Dict:
        try:
            # Body goes to stdout (no -o /dev/null) followed by a stats line
            # prefixed with a newline, so `rsplit("\n", 1)` cleanly separates
            # the two regardless of how many lines the body itself has.
            r = subprocess.run(
                ["curl", "-sS", "-L", "--max-time", "8", "-w", "\n%{http_code} %{time_total} %{url_effective}", url],
                capture_output=True, text=True, timeout=12, check=False,
                env=clean_env(),
            )
            output = r.stdout
            if "\n" in output:
                body, stats_line = output.rsplit("\n", 1)
            else:
                body, stats_line = "", output
            body = body.strip()

            parts = stats_line.strip().split(maxsplit=2)
            code = parts[0] if parts else "0"
            time_s = float(parts[1]) if len(parts) > 1 else None
            effective_url = parts[2] if len(parts) > 2 else url
            ok = code.startswith(("2", "3"))
            blocked = bool(block_if_url_contains) and block_if_url_contains in effective_url
            if blocked:
                ok = False
            detail = f"HTTP {code}" + (f", {time_s:.2f}s" if time_s is not None else "")
            if blocked:
                detail += " (заблокировано по региону)"
            elif not ok and r.stderr:
                detail += f" ({r.stderr.strip().splitlines()[-1]})"
            elif show_body and ok and body:
                snippet = body if len(body) <= 200 else body[:200] + "…"
                detail += f" — {snippet}"
            return {"name": name, "kind": "http", "target": url, "ok": ok, "detail": detail, "latency_ms": time_s * 1000 if time_s else None}
        except subprocess.TimeoutExpired:
            return {"name": name, "kind": "http", "target": url, "ok": False, "detail": "timeout", "latency_ms": None}
        except FileNotFoundError:
            decky.logger.warning("curl not found for diagnostics")
            return {"name": name, "kind": "http", "target": url, "ok": False, "detail": "curl not found", "latency_ms": None}
