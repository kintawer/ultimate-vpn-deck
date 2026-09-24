# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Decky Loader plugin for Steam Deck that toggles a VPN tunnel (VLESS/VMess/Trojan/Shadowsocks/Hysteria2 profiles and standard HTTP(S) subscriptions) from the gaming mode UI. TypeScript/React frontend communicates with a Python 3 backend via Decky's RPC system. The actual tunneling is done by a bundled `sing-box` binary, not by the closed-source Happ client — this plugin is an independent implementation compatible with the same link/subscription formats.

## Key Files

| File | Purpose |
|------|---------|
| `src/index.tsx` | Entire frontend |
| `main.py` | Plugin class and all RPC endpoint definitions |
| `py_modules/ultimate_vpn_deck/uri_parsers.py` | vless/vmess/trojan/ss/hysteria2 URI → normalized profile dict |
| `py_modules/ultimate_vpn_deck/singbox_config.py` | profile dict → sing-box outbound/config JSON |
| `py_modules/ultimate_vpn_deck/service_manager.py` | sing-box subprocess lifecycle (single active tunnel) |
| `py_modules/ultimate_vpn_deck/subscription_manager.py` | HTTP(S) subscription fetch/parse |

Only one profile can be an active tunnel at a time — connecting a new one stops the previous sing-box process first.
