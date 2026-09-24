# ultimate-vpn-deck — Decky-плагин для VPN-туннеля (vless/vmess/trojan/ss/hysteria2 + подписки)

## Context

Пользователь хочет плагин для Decky Loader (Steam Deck), который включает/выключает VPN-профиль так же удобно, как это делает клиент **Happ**. Happ на Linux — закрытый Qt6 GUI поверх Xray-core, без CLI и без какого-либо API для внешней автоматизации (подтверждено: официальный репозиторий `happ-desktop` содержит только `.deb`/`.rpm`/`.pkg.tar.zst` бинарники, исходников нет, в организации `happ-proxy` нет ни одного cli/daemon репозитория). Значит "включать/выключать Happ" физически невозможно — вместо этого плагин реализует **независимый VPN-клиент**, совместимый с форматами ссылок и подписок, которые использует Happ и вся Xray/V2Ray-экосистема (это открытые де-факто стандарты, не Happ-специфика).

В качестве образца архитектуры используется уже существующий рабочий плагин `/home/meduzik/projects/fun/vpn-deck` (тоггл AmneziaWG-профилей) — тот же паттерн `main.py` + `py_modules/` + `@_rpc`-декоратор + `src/index.tsx`, тот же способ получения root (`flags: ["root"]` в `plugin.json`, без sudo/polkit), тот же способ сборки/релиза через `decky plugin build` + GitHub Actions по тегу.

Ключевое архитектурное решение — **движок туннеля: sing-box**, а не Xray-core+tun2socks:
- Один статический Go-бинарник (в отличие от связки xray+tun2socks).
- Сам создаёт TUN-интерфейс (`auto_route: true`) — не нужны ручные iptables/ip route.
- Нативно поддерживает vless/vmess/trojan/shadowsocks/hysteria2/tuic — весь набор протоколов, который заявляет Happ.
- Официально признанный самим Happ core: в их доках у desktop-клиента есть параметр `tun-type: singbox/tun2proxy/default/xray`.
- Публикует official prebuilt `linux-amd64` бинарники в GitHub Releases — не нужен Docker-компайл, как для amneziawg-go в vpn-deck.

Подписки: поддерживаются **только обычные HTTP(S)-подписки** (base64 тела со списком ссылок + заголовки `profile-title`/`subscription-userinfo`/`announce`/`support-url`/`profile-update-interval`). Формат подтверждён вживую на реальном примере `https://sub.comrad-tech.site:8443/3b0346da051447ef8be4350a5dd6e2f7` — тело оказалось обычным base64 двух `vless://...` ссылок, никакой Happ-специфики. Проприетарные `happ://crypt4/`/`happ://crypt5/` ссылки **не поддерживаются** — расшифровка требует приватных ключей, зашитых в закрытый Happ-клиент, реверс-инжиниринг которых вне разумного скоупа.

Каталог `/home/meduzik/projects/fun/happ-deck` пока не git-репозиторий. Проект переименовывается в **ultimate-vpn-deck** (Happ — лишь один из источников профилей/подписок, а не единственная цель). Автор — `kintawer` (GitHub: `kintawer`, репозиторий будет `https://github.com/kintawer/ultimate-vpn-deck`). Git-тег релиза — голый `x.y.z` (без `v`).

## Changes

### Корень
- `plugin.json` — `{"name": "ultimate-vpn-deck", "author": "kintawer", "flags": ["root"], "api_version": 1, "publish": {"tags": ["vpn","sing-box","vless","vmess","trojan","shadowsocks","hysteria2","root"], "description": "...", "image": "..."}}`.
- `package.json` — `name: "ultimate-vpn-deck"`, `author: "kintawer"`, `repository`/`homepage`: `https://github.com/kintawer/ultimate-vpn-deck`, стандартные decky devDeps/deps (`@decky/rollup`, `@decky/ui`, `@decky/api`, `react-icons`, `tslib`, `rollup`, `typescript`), скрипты `build`=`rollup -c`, `watch`, `release`/`release:patch`/`release:minor`/`release:major` = `release-it [bump]`.
- `rollup.config.js` — копия из template/vpn-deck без изменений (`export default deckyPlugin({})`).
- `tsconfig.json`, `decky.pyi`, `src/types.d.ts` — копия verbatim из vpn-deck.
- `.release-it.json` — как у vpn-deck, но теги без `v`: `tagName: "${version}"`, `releaseName: "${version}"`, `assets: ["./out/ultimate-vpn-deck-*.zip"]`, `hooks.before:release: ["bash infra/build-plugin.sh ${version}"]`, `hooks.before:init` — проверка ветки `main`.
- `justfile` — `install` (pnpm i), `test` (`PYTHONPATH=py_modules python3 test_unit.py && PYTHONPATH=py_modules python3 test_profile_manager.py`), `test-smoke` (`bash infra/test-smoke.sh`), `fetch-binaries`, `build-plugin`, `release bump="patch"`. Без `build-image`/`push-image` — Docker-сборщик не нужен.
- `deck.json`, `.vscode/{build.sh,config.sh,setup.sh,defsettings.json,tasks.json}` — копия из vpn-deck/template (стандартная dev-deploy обвязка на реальный Deck по SSH), `pluginname` в `defsettings.json` → `ultimate-vpn-deck`.
- `LICENSE` — тот же формат, что у vpn-deck (свой текст лицензии сверху + оригинальный BSD-3-Clause decky-plugin-template снизу), copyright-имя `kintawer`.
- `README.md`, `CLAUDE.md` — README с описанием поддерживаемых форматов ссылок/подписок и инструкцией по установке; CLAUDE.md коротко указывает на `main.py`/`src/index.tsx` как точки входа (по образцу vpn-deck).
- `.gitignore` — `node_modules`, `dist`, `out`, `bin/sing-box`, `cli/`, `*.zip`, `.vscode/settings.json`.

### Backend — `main.py`
`Plugin` класс, тот же `@_rpc`-декоратор что в vpn-deck (лог + `self.errors` ring buffer на 50 записей + `{"success": False, "error": ...}` вместо исключения наружу).

RPC-методы:
```python
# Binary
get_binaries_info() -> dict
check_binaries() -> dict

# Profiles
list_profiles() -> list[dict]
add_profile(uri: str) -> dict
delete_profile(profile_id: str) -> dict
get_profile(profile_id: str) -> dict | None

# Subscriptions
list_subscriptions() -> list[dict]
add_subscription(url: str) -> dict
refresh_subscription(sub_id: str) -> dict
delete_subscription(sub_id: str, delete_profiles: bool = True) -> dict

# Connection (единственный активный туннель)
connect(profile_id: str) -> dict
disconnect() -> dict
status() -> dict

# Diagnostics / errors
diagnose_connectivity(targets=None) -> list[dict]
get_errors() -> list[dict]
clear_errors() -> bool
```
Lifecycle: `_main()` — при старте читает pidfile и, если процесс жив, восстанавливает состояние (аналог `repair_symlinks()` в vpn-deck, но здесь "сверка pidfile с реальностью", т.к. symlink-трюк не нужен — sing-box принимает явный `-c <path>`, не требует файла в системной директории). `_unload()` — **намеренно не останавливает** sing-box (чтобы перезагрузка плагина/QAM не рвала соединение), только логирует. `_uninstall()` — останавливает sing-box и подчищает состояние. `_migration()` — заглушка.

`connect(profile_id)`: строит sing-box outbound из профиля → полный конфиг → пишет `DECKY_PLUGIN_RUNTIME_DIR/singbox-config.json` → `service_manager.start()` (который сам сначала останавливает предыдущий процесс — так обеспечивается семантика "только один активный туннель") → при успехе сохраняет `active_profile_id`.

### Backend — `py_modules/ultimate_vpn_deck/`
- `_utils.py` — `clean_env()` копия verbatim из vpn-deck (чистит `/tmp/_MEI*` из `LD_LIBRARY_PATH` перед любым subprocess).
- `binary_manager.py` — `BinaryManager`, аналог vpn-deck, но `binary_names = ["sing-box"]`; `check_binary_version()` парсит `sing-box version`.
- `uri_parsers.py` — чистые функции без импорта `decky` (удобно тестировать изолированно):
  - `parse_uri(uri) -> dict` — диспетчер по схеме.
  - `parse_vless`, `parse_vmess` (base64 JSON v2rayN-формат), `parse_trojan`, `parse_shadowsocks` (обе формы: `ss://base64(method:pass)@host:port#name` и полностью-base64), `parse_hysteria2` (+ алиас `hy2://`).
  - Общий формат результата: `{protocol, name, server, port, uuid/password, flow, tls:{enabled,sni,alpn,insecure}, reality:{enabled,public_key,short_id,fingerprint}, transport:{type,path,host,service_name}, raw_uri}`.
- `singbox_config.py` — чистые функции:
  - `profile_to_outbound(profile, tag="proxy") -> dict` — маппинг протокол→sing-box outbound JSON (vless/vmess/trojan → TLS+Reality+transport(grpc/ws/tcp) блоки; shadowsocks → `{type,server,server_port,method,password}` без TLS; hysteria2 → `{type,server,server_port,password,tls,obfs}`).
  - `build_config(outbound, dns_servers=None) -> dict` — полный конфиг: `tun`-inbound (`auto_route: true`, `strict_route: true`, `auto_detect_interface: true`), outbounds `[profile, direct, block]`, `route.rules` с `ip_is_private → direct` (не рвать SSH/LAN на самом Deck) и `protocol: dns → direct`, `route.final: "proxy"`.
- `profile_manager.py` — `ProfileManager`: CRUD профилей, хранение в `DECKY_PLUGIN_SETTINGS_DIR/profiles/<id>.json`, `_generate_id()` — стабильный хэш от `raw_uri` (дедуп при повторном импорте/рефреше подписки), `state.json` с `active_profile_id`.
- `subscription_manager.py` — `SubscriptionManager`: `add_subscription`/`refresh_subscription`/`delete_subscription`, хранение в `DECKY_PLUGIN_SETTINGS_DIR/subscriptions/<id>.json`. Фетч через `urllib.request` (timeout 10s, browser-like User-Agent — проверить на живом примере подписки). `_parse_body()` — base64-decode → split по строкам → список URI. `_parse_headers()` — `profile-title`/`announce` (base64 или plain — пробовать decode, при ошибке брать как есть), `subscription-userinfo` (`upload=N; download=N; total=N; expire=UNIXTS`), `support-url`, `profile-update-interval`. При рефреше профили этой подписки (помечены `source="subscription:<id>"`) заменяются новым набором; профили с неизменным `raw_uri` сохраняют тот же `id` (не рвут активное соединение, если рефрешнули активную подписку).
- `service_manager.py` — `ServiceManager`, самая отличающаяся от vpn-deck часть: sing-box — долгоживущий foreground-процесс, а не daemonizing-скрипт как `awg-quick`, поэтому `subprocess.Popen` + pidfile-трекинг (`DECKY_PLUGIN_LOG_DIR/sing-box.pid`), а не `awg show`-подобный опрос состояния.
  - `start(config_path)`: сначала `self.stop()` (обеспечивает единственный активный туннель), затем `Popen([binary, "run", "-c", config_path], stdout=log_file, stderr=log_file, start_new_session=True, env=clean_env())`, короткая пауза (~0.7s) + `proc.poll()` для быстрого обнаружения падения (bad config/port busy/TUN permission) с хвостом лога в ошибке.
  - `stop()`: SIGTERM → короткий poll-wait до ~5s → SIGKILL если жив → удалить pidfile.
  - `status()`: `{running, pid, uptime_s}` на основе pidfile + `os.kill(pid, 0)`.
- `diagnostics.py` — `Diagnostics`, копия паттерна vpn-deck почти verbatim (`ping`/`curl` через `clean_env()`, `ThreadPoolExecutor`).

### Frontend — `src/index.tsx`
Один файл (по образцу vpn-deck), полностью новый, но повторяющий проверенные паттерны:
- `callable<Args,Ret>()`-обвязки под каждый RPC метод.
- `PanelSection "Соединение"` — статус (подключено/нет, имя активного профиля, аптайм).
- `PanelSection "Профили"` — список профилей, каждый — `ToggleField`; `checked = profile.id === status.active_profile_id`. **Важное отличие от vpn-deck**: это не N независимых тумблеров, а "радио"-поведение — включение одного профиля вызывает `connect(id)`, который на бэкенде сам гасит предыдущий; после ответа фронт перезапрашивает статус и перерисовывает все строки. Профили из подписок помечены лейблом с именем подписки. У каждой строки — кнопка удаления через `DeleteProfileModal` (confirm + toast, по образцу `DeleteConfigModal` из vpn-deck).
- `PanelSection "Подписки"` — список подписок (заголовок, инфо о трафике/сроке из `subscription-userinfo`, `announce`-баннер), кнопки "Обновить" (`refresh_subscription`) и удаления (`DeleteSubscriptionModal`).
- `ImportModal` (`showModal`+`ModalRoot`) — режим "Вставить ссылку" (`TextField` под любой `vless/vmess/trojan/ss/hysteria2` URI → `add_profile`) и режим "Добавить подписку" (`TextField` под URL → `add_subscription`); опционально — импорт из файла (`.txt` со списком ссылок) через `openFilePicker`, по образцу vpn-deck.
- Диагностика — идентично vpn-deck (кнопка "Проверить соединение" → `diagnose_connectivity` → цветные полоски результатов). Кнопка "repair symlinks" не переносится (не актуальна — нет symlink-трюка).
- Сворачиваемый лог ошибок — идентично vpn-deck (`showErrors` toggle, `<details>` JSON, кнопка очистки).
- Поллинг: статус каждые 3s, ошибки каждые 10s; профили/подписки обновляются по факту мутации + кнопка ручного refresh.
- `definePlugin`: `name: "Ultimate VPN Deck"`, иконка `FaShieldAlt` (react-icons/fa), `content: <Content/>`.

### Бинарник sing-box
- `infra/fetch-binaries.sh` — скачивает pinned релиз sing-box (на момент планирования актуальный стабильный тег `v1.14.1`; **на этапе реализации свериться с https://github.com/SagerNet/sing-box/releases на самый свежий stable тег**, не считать `v1.14.1` окончательным), `sing-box-<ver>-linux-amd64.tar.gz`, распаковывает бинарник в `bin/sing-box`, `chmod +x`. Никакого Docker/компиляции не нужно — sing-box публикует официальные прекомпилированные `linux-amd64` бинарники.
- `infra/build-plugin.sh` — `fetch-binaries.sh` → `./cli/decky plugin build` → переименование `out/ultimate-vpn-deck.zip` → `out/ultimate-vpn-deck-<version>.zip` (без `v`-префикса).
- `bin/.gitkeep`, `defaults/defaults.txt` — копия структуры vpn-deck.

### CI — `.github/workflows/release.yml`
Триггер — push тега `x.y.z` без `v` (GitHub Actions tag-glob, не regex — на этапе реализации подобрать корректный паттерн, например `'[0-9]+.[0-9]+.[0-9]+'`, и проверить его реальное поведение). Шаги: checkout → `pnpm/action-setup@v4` → `actions/setup-node@v4` (node 20, cache pnpm) → `pnpm install --frozen-lockfile` → скачать Decky CLI (`cli/decky`) → `./infra/build-plugin.sh "${GITHUB_REF_NAME}"` (без `#v`-стриппинга — версии и так без `v`) → `softprops/action-gh-release@v2` с `files: out/ultimate-vpn-deck-*.zip`.

### Тесты
- `test_unit.py` — чистый парсинг без mock `decky` где возможно: `parse_vless`/`parse_vmess`/`parse_trojan`/`parse_shadowsocks` (обе формы)/`parse_hysteria2`(+`hy2://`) на валидных ссылках (включая реальные Reality-параметры `pbk/fp/sni/sid`, `type=grpc/ws`), невалидный URI → ошибка; `profile_to_outbound`/`build_config` — структурные проверки (один `tun` inbound, `ip_is_private`-правило, outbounds содержат `direct`+`block`+профиль). **Фикстура на реальных данных**: захардкодить тело/заголовки настоящей подписки `https://sub.comrad-tech.site:8443/3b0346da051447ef8be4350a5dd6e2f7` (2 `vless://...#<url-encoded emoji+имя>` строки + `subscription-userinfo`/`profile-title`/`announce`) и проверить, что `_parse_body`/`_parse_headers` разбирают их в 2 профиля с корректными именами/полями.
- `test_profile_manager.py` — mock `decky`, temp dir: добавление/удаление/дедуп профилей по `raw_uri`, рефреш подписки заменяет только "свои" профили и сохраняет id для неизменных ссылок.
- `test_plugin_smoke.py` — mock `decky` + mock manager-классы (по образцу vpn-deck), вызов всех RPC методов `Plugin` (включая regression-кейс "исключение внутри менеджера → `_rpc` возвращает `{success:false,...}`").
- `infra/test-smoke.sh` — копия паттерна vpn-deck (прогон `test_unit.py`+`test_plugin_smoke.py` внутри `ghcr.io/steamdeckhomebrew/holo-base:latest`).

### После реализации (не в рамках правки кода, но обязательно)
- Переименовать локальную папку `/home/meduzik/projects/fun/happ-deck` и создать GitHub-репозиторий `kintawer/ultimate-vpn-deck`.
- `git init`, первый коммит — только после того как код готов и проверен.

## For QA

### Что меняется
Создаётся новый Decky-плагин **ultimate-vpn-deck** для Steam Deck: тоггл VPN-профилей (VLESS/VMess/Trojan/Shadowsocks/Hysteria2) и обычных HTTP-подписок прямо из Quick Access меню в игровом режиме. Раньше такого функционала не было — задача целиком новая. Внутри — sing-box как VPN-движок (создаёт системный TUN-интерфейс), собственный парсер ссылок/подписок, root-права через `flags: ["root"]` в `plugin.json` (без sudo/polkit).

### Как проверить
API-поверхности в привычном REST-смысле нет — это Decky RPC (вызовы Python-методов из React через `@decky/api`). Проверка руками на реальном Steam Deck (или SteamOS-подобной машине) с установленным Decky Loader:

1. **Установка**: собрать zip (`just build-plugin` или дождаться релиза в GitHub Actions по тегу `x.y.z`), закинуть в `homebrew/plugins/ultimate-vpn-deck` на Deck (или через `.vscode` deploy-таск), перезапустить `plugin_loader`.
2. **Импорт одиночной ссылки**: открыть плагин в QAM → "Добавить" → "Вставить ссылку" → вставить `vless://...` (например, взять одну из строк примера подписки выше) → профиль должен появиться в списке "Профили".
3. **Импорт подписки**: "Добавить" → "Добавить подписку" → вставить `https://sub.comrad-tech.site:8443/3b0346da051447ef8be4350a5dd6e2f7` → должны появиться 2 профиля с именами "🇩🇪Германия-1"/"🇩🇪Германия-2", а в разделе "Подписки" — карточка с названием "Comrade 221400201" и информацией о сроке действия.
4. **Подключение**: включить тумблер у профиля → через несколько секунд статус должен показать "подключено" + имя профиля; проверить реальную смену внешнего IP (например, через diagnostics-секцию или `curl ifconfig.me` по SSH на Deck).
5. **Переключение**: включить другой профиль, пока первый активен → первый должен автоматически выключиться (тумблер снимется), новый — подключиться. Одновременно два профиля активными быть не должны.
6. **Отключение**: выключить тумблер активного профиля → статус "отключено", системный трафик идёт напрямую (без VPN).
7. **Обновление подписки**: нажать "Обновить" на подписке → список профилей подписки актуализируется, активное соединение (если было на этой подписке) не должно разрываться, если ссылка не изменилась.
8. **Удаление**: удалить неактивный профиль/подписку → пропадает из списка; попытка удалить активный профиль — сначала должен произойти disconnect.
9. **Диагностика**: кнопка "Проверить соединение" в разделе "Диагностика" → должны появиться результаты ping/HTTP проверок (зелёная/красная полоска).
10. **Устойчивость к перезагрузке плагина**: перезапустить Decky Loader (или сам плагин) при активном соединении → VPN не должен разрываться (проверить `_unload` не глушит sing-box); после `_uninstall` плагина — VPN обязан быть выключен.
11. **Ошибки**: попытаться подключить профиль с заведомо неверными данными (битый UUID/недоступный сервер) → в разделе "Ошибки" должна появиться запись с деталями, тумблер должен вернуться в выключенное состояние (не зависнуть в "включается").

### Внутренние изменения (без прямого API)
Если правится, например, только `singbox_config.py` (маппинг протокол→outbound) — проверить косвенно через `test_unit.py` (юнит-тесты на парсинг реальных ссылок) и через ручное подключение к серверу этого протокола с последующей проверкой внешнего IP.
