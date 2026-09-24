"""Shared helpers used across ultimate_vpn_deck modules."""

import os
import ssl
from typing import Dict


def clean_env() -> Dict[str, str]:
    """Strips PyInstaller / Decky MEI paths from LD_LIBRARY_PATH.

    Decky bundles the plugin runtime via PyInstaller, which injects
    /tmp/_MEI* into LD_LIBRARY_PATH. Child processes like `sing-box`,
    `ping`, `curl` must not inherit these or they pick up bundled libs
    that conflict with the system ones.
    """
    env = os.environ.copy()
    if "LD_LIBRARY_PATH" in env:
        paths = [p for p in env["LD_LIBRARY_PATH"].split(":") if "/tmp/" not in p and "_MEI" not in p]
        if paths:
            env["LD_LIBRARY_PATH"] = ":".join(paths)
        else:
            del env["LD_LIBRARY_PATH"]
    return env


# Real system CA bundle locations, in order of preference. SteamOS/Arch and
# most Debian-derived distros use the first one.
_SYSTEM_CA_BUNDLE_PATHS = (
    "/etc/ssl/certs/ca-certificates.crt",  # Arch / SteamOS / Debian / Ubuntu
    "/etc/pki/tls/certs/ca-bundle.crt",  # RHEL / Fedora
    "/etc/ssl/cert.pem",  # Alpine / OpenBSD / some musl builds
)


def system_ssl_context() -> ssl.SSLContext:
    """Builds an SSLContext from the real system CA bundle.

    ssl.create_default_context() honors the SSL_CERT_FILE/SSL_CERT_DIR
    environment variables. Decky's PyInstaller-bundled runtime can set these
    to point inside its own (temporary, possibly stale) bundle, which then
    breaks certificate verification for otherwise-valid HTTPS endpoints -
    this bit subscription fetching in practice. This is the HTTPS analog of
    clean_env()'s LD_LIBRARY_PATH fix: load the real system bundle
    explicitly instead of trusting whatever the bundled env vars point at.
    """
    for path in _SYSTEM_CA_BUNDLE_PATHS:
        if os.path.isfile(path):
            return ssl.create_default_context(cafile=path)
    return ssl.create_default_context()
