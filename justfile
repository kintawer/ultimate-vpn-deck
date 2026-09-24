# Show available recipes
default:
    @just --list

# Install JS dependencies
install:
    pnpm install

# Run unit tests (no binaries required)
test:
    PYTHONPATH=py_modules python3 test_unit.py
    PYTHONPATH=py_modules python3 test_profile_manager.py

# Run smoke tests inside a Steam Deck OS container (holo-base)
test-smoke:
    bash infra/test-smoke.sh

# Fetch the sing-box binary into ./bin/
fetch-binaries:
    bash infra/fetch-binaries.sh

# Build plugin zip (fetches sing-box, packs via Decky CLI)
build-plugin:
    bash infra/build-plugin.sh

# Release (bump version, build, publish GitHub release)
release bump="patch":
    pnpm release:{{ bump }}
