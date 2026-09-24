#!/usr/bin/env bash
set -euo pipefail

# Pin to a known-good sing-box stable release. Check
# https://github.com/SagerNet/sing-box/releases for the current tag before
# bumping this - do not track "latest" for build reproducibility.
SINGBOX_VERSION="${SINGBOX_VERSION:-v1.14.1}"
VERSION_NUM="${SINGBOX_VERSION#v}"
ASSET="sing-box-${VERSION_NUM}-linux-amd64.tar.gz"
URL="https://github.com/SagerNet/sing-box/releases/download/${SINGBOX_VERSION}/${ASSET}"

mkdir -p bin
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

echo "==> Downloading sing-box ${SINGBOX_VERSION}"
curl -fL -o "$TMPDIR/$ASSET" "$URL"
tar -xzf "$TMPDIR/$ASSET" -C "$TMPDIR"
cp "$TMPDIR/sing-box-${VERSION_NUM}-linux-amd64/sing-box" bin/sing-box
chmod +x bin/sing-box

echo "==> sing-box ${SINGBOX_VERSION} fetched to ./bin/sing-box"
./bin/sing-box version || true
