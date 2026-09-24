# ultimate-vpn-deck

Decky Loader plugin for Steam Deck: toggle a VPN tunnel from gaming mode.

Supports the same sharing-link and subscription formats as the [Happ](https://www.happ.su/main)
proxy client (and the wider Xray/V2Ray ecosystem in general) — **VLESS**, **VMess**, **Trojan**,
**Shadowsocks**, **Hysteria2** links, plus standard HTTP(S) subscriptions. Happ itself is a
closed-source desktop GUI with no CLI or automation surface, so this plugin does not drive Happ —
it's an independent client, powered by [sing-box](https://github.com/SagerNet/sing-box), that
understands the same link/subscription formats.

Only one profile can be the active tunnel at a time — connecting a new one automatically
disconnects the previous one.

## Supported links

- `vless://` (incl. Reality: `pbk`/`fp`/`sni`/`sid`, and `grpc`/`ws` transports)
- `vmess://` (base64 JSON payload)
- `trojan://`
- `ss://` (both SIP002 and legacy fully-base64 forms)
- `hysteria2://` / `hy2://`

## Subscriptions

Standard HTTP(S) subscription URLs are supported: the response body is base64 of a
newline-separated list of the links above, and metadata is read from response headers
(`profile-title`, `subscription-userinfo`, `announce`, `support-url`).

Proprietary `happ://crypt4/` / `happ://crypt5/` encrypted subscription links are **not**
supported — decrypting them requires private keys embedded in the closed-source Happ client.

## Install

Grab the latest release zip from the [Releases](https://github.com/kintawer/ultimate-vpn-deck/releases)
page and install it via Decky Loader's "Install from zip" option, or drop it into
`homebrew/plugins/ultimate-vpn-deck` on your Deck and restart the `plugin_loader` service.

## Development

```bash
just install        # pnpm install
just test            # run unit tests (no binary/network required)
just fetch-binaries  # download the pinned sing-box release into ./bin/
just build-plugin    # produce out/ultimate-vpn-deck.zip
```

See `.vscode/tasks.json` for live-deploy-to-Deck tasks (`builddeploy`, `restartdecky`, ...).

## Release

Tag pushes matching `x.y.z` (no `v` prefix) trigger `.github/workflows/release.yml`, which builds
the plugin zip and attaches it to a GitHub Release. `just release [patch|minor|major]` drives this
locally via `release-it`.
