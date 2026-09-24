# Show available recipes
default:
    @just --list

# Install JS dependencies
install:
    pnpm install

# Fetch the sing-box binary into ./bin/
fetch-binaries:
    bash infra/fetch-binaries.sh

# Build plugin zip (fetches sing-box, packs via Decky CLI)
build-plugin:
    bash infra/build-plugin.sh

# Release (bump version, build, publish GitHub release)
release bump="patch":
    pnpm release:{{ bump }}
