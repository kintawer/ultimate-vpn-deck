#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:-}"

echo "==> Building plugin"

./infra/fetch-binaries.sh
./cli/decky plugin build

if [[ -n "$VERSION" ]]; then
    mv ./out/ultimate-vpn-deck.zip "./out/ultimate-vpn-deck-${VERSION}.zip"
    echo "==> Renamed to ultimate-vpn-deck-${VERSION}.zip"
fi
