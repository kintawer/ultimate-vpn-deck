"""
BinaryManager - Manages detection and access to the bundled sing-box binary
"""

import os
import re
import subprocess
from typing import Dict, Optional

import decky


class BinaryManager:
    """Manages detection and access to the sing-box binary"""

    binary_names = ["sing-box"]

    def __init__(self):
        self.plugin_dir = os.path.dirname(os.path.abspath(__file__))
        self.bin_dir = os.path.join(self.plugin_dir, "..", "..", "bin")
        self.binary_cache: Optional[Dict[str, Optional[str]]] = None

    def detect_binaries(self) -> Dict[str, Optional[str]]:
        """
        Detects where the sing-box binary is located.

        Returns:
            Dictionary mapping binary name to path (or None if not found)
        """
        if self.binary_cache is not None:
            return self.binary_cache

        binaries: Dict[str, Optional[str]] = {}

        for binary_name in self.binary_names:
            potential_path = os.path.join(self.bin_dir, binary_name)

            if os.path.isfile(potential_path) and os.access(potential_path, os.X_OK):
                decky.logger.info(f"Found {binary_name} at {potential_path}")
                binaries[binary_name] = potential_path
            else:
                decky.logger.error(f"Binary {binary_name} not found in {self.bin_dir}")
                binaries[binary_name] = None

        self.binary_cache = binaries
        return binaries

    def get_binary_path(self, name: str = "sing-box") -> Optional[str]:
        """Gets the path to a specific binary (defaults to sing-box)."""
        if self.binary_cache is None:
            self.detect_binaries()

        return self.binary_cache.get(name) if self.binary_cache else None

    @staticmethod
    def _extract_version(output: str) -> Optional[str]:
        """Extracts a version string like 'v1.2.3' or '1.2.3' from command output."""
        match = re.search(r'v?(\d+\.\d+\.\d+|\d+\.\d+)', output)
        if match:
            return match.group(0)
        return output.split('\n')[0] if output else None

    def check_binary_version(self, path: str) -> Optional[str]:
        """Checks the version of a binary via `<binary> version`."""
        if not os.path.isfile(path):
            return None

        try:
            for args in (["version"], ["--version"], ["-v"]):
                result = subprocess.run(
                    [path, *args],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    check=False,
                )
                if result.returncode == 0 and result.stdout:
                    return self._extract_version(result.stdout.strip())

            decky.logger.warning(f"Could not determine version for {path}")
            return "unknown"

        except subprocess.TimeoutExpired:
            decky.logger.error(f"Timeout checking version for {path}")
            return None
        except Exception as e:
            decky.logger.error(f"Error checking version for {path}: {e}")
            return None

    def invalidate_cache(self):
        """Invalidates the binary cache, forcing a re-detection on next access"""
        self.binary_cache = None
        decky.logger.info("Binary cache invalidated")

    def get_binaries_info(self) -> Dict[str, Dict[str, Optional[str]]]:
        """
        Gets detailed information about all binaries.

        Returns:
            Dictionary with binary info including path and version, e.g.:
            {"sing-box": {"path": "/path/to/bin/sing-box", "version": "1.14.1"}}
        """
        binaries = self.detect_binaries()
        info = {}

        for name, path in binaries.items():
            if path:
                version = self.check_binary_version(path)
                info[name] = {"path": path, "version": version}
            else:
                info[name] = {"path": None, "version": None}

        return info
