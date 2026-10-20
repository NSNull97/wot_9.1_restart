# NET-02 — private native transport boundary

Карточка в `codex/net-02-private-lan`, зависимая от P10B6c6b7b7/e55ba01.
Ночное разрешение позволяет реализацию; native/twoPC NOT_RUN не разрешает merge.
План — [NET-02](../plans/NET-02.md). Оригинал #717 остаётся read-only.

## Verified implementation and source evidence

Серверный optional game_network имеет exact4 fields: version1/mode lan_test,
advertised_base и allowed_peer_cidrs. Concrete canonical RFC1918 IPv4,
Login/Base один host/разные порты1024..65535; advertise строго Basebind,
1..24 уникальных /32. Нет DNS/public/wildcard/IPv6. Parser не доказывает,
что address принадлежит OS; фактический bind и отдельный interface inventory
остаются обязательными. .0/.255 не объявляются broadcast без actualprefix.

`account/game_network.rs` — typed private-field GameBind/AdvertisedBase/Network.
`account/identity.rs` — config-only streaming visitor, который декодирует
LanWire до serde_json::Value и сохраняет evidence nested duplicate keys.
4096bytes/top23/HTTP16/fixture64 limits сохранены. Отсутствующий game_network
сохраняет старые loopback binds/redirect. Identity HTTP validator не расширен.

Все12 production Config loaders и общие runtime entrypoints проверяют mode
до bind/capture/worker. LAN допускается только в shared owned profile13 с
полным p04m_pool/p06t_mixed_ammo chain. Qualification/диагностика остаются
loopback. Allowlist проверяется до accepted-rate/capture/fragments/crypto;
aggregate256datagrams/s сохранён, per-IP fairness не обещается. First Base
сопоставляет IP authenticated Login; different sourceport допускается,
token/key/live peer/retirement проверки сохранены. Из allowlisted IP не следует
авторизация владельца. Redirect принимает только validated AdvertisedBase.

`client_patch/project_network.py` — чистый CPython2.7.3 policy helper.
`tools/interactive_client.py prepare --network-policy lan-test-v1` и runtime
используют один validator; exact submitted host сравнивается с подготовленным
endpoint. LAN требует explicitprofile13/mixed. Original LoginDispatcher и
ConnectionManager остаются транспортом. LAN registrationURL пустой; own
аккаунты заранее созданы. Статический original #717 proof подтверждает
LoginView.onRegister→OpenLinkEvent.REGISTRATION→ExternalLinksHandler→emptyURL
return до wg_openWebBrowser. Flash visibility/clicks пока native NOT_RUN.
Client pack не получает private HTTP/token/DB/fixture/ключи сервера.

## Actual checks on promoted source

Hash-checked promotion16files: все frozen receipt и baseline hashes совпали;
15files exactcandidate, отдельный tracked preparetest адаптирован только
на active root paths при неизменных assertions. Receipt:
local/evidence/20261016-net02-integration01/promotion01.json,
SHA73a83b72d391956e096d49f412ed4e1b064fce9f17f8975d2a95d2b27f326c37.

Actual focused gateway **17PASS/0FAIL/0ignored/buildPASS**:
local/build/server/gateway-net02-focused01/result.json, exe
682fad6c58f6399fe5162a635ea509c1c90a8c7ea6d172722396761b3076e415.
Это actual Config/Table/entrypoint/redirect tests: raw duplicate/budget,
24vs25 peers, exactunsupported guard errors до missingresources, sameLoginIP,
две Sessions с одного IP и независимые redirect literals.
Canonical full01 на608bb239e06810cd7c17b7097e1e3e268f9945db:
**1414PASS/0FAIL/5oldignored/buildPASS**,542.04с/794rawsource exact до/после;
tag net02-private-lan-20261016-01, exe
28e9589f0bfa88cf9d0ec821f8989582dbab201ccc64e71a5035616348cd3f0b.
Evidence local/evidence/20261016-net02-full01 и fresh gateway-net02-full01.

Actual CPython2.7.3: auth6/network9/training15/mapdrive61PASS и3 прежних host-only
skips. Эти3 sourceboundary проверки выполнены Python3: mapdrive64PASS;
дополнительно manualrunner14/replayverifier59PASS. Active prepare/resource5PASS;
3owned modules compiled CPython2.7.3. Node network/identity/portal7PASS/0skip
использовали собственные временные loopback listeners, не удалённую LAN.
Команды/логи: local/evidence/20261016-net02-integration01.

Сохранён первый diagnostic FAIL: слишком широкий CPython2.7 glob включил
host-only Python3 greeting suite (SyntaxError) и одну temp-dependent skip.
Это ошибка выбора набора; exact auth/network suites затем прошли отдельно.
`server/check_layout.py` FAIL на уже существующем server/__pycache__; файлы
cache не удалялись и guard не ослаблялся. Это отдельный прежний layout-долг,
не PASS. Полный Python/legacy/rustfmt долг не объявляется исправленным.

## Observations, unknowns and morning activation

OBSERVED read-only OS inventory: один eligible RFC1918 IPv4/24, interface7,
Preferred/SkipAsSourcefalse, Windows Public category. Private-only firewall
rule на нём не действует. Адрес сохраняется только local; в public docs не
выбирать выдуманный IP второго PC. Сеть/брандмауэр/профиль не изменялись.
Старый room runner pins127.0.0.1 и A-local credential preflight, поэтому не
подходит для remoteB. Settings schema1 отдельно от map_drive VERSION8.

INFERRED: validated LAN advertisement и narrow client policy сохраняют родной
transport. UNKNOWN/NOT_RUN: actual native LAN Login/Base, remoteB/interface/
firewall, комнаты/бой/возврат двух PC, latency/6players, hosting/WAN/NAT.
Нужен новый source/exe/config/publicPEM paired manifest и per-PC local plans;
полная server preparation не должна попадать в client pack. Текущий coreV7
установлен и сохранён, новый overlay не готовился и не ставился.

Откат: P10Btag p10b-host-20261016-02 + exactsource restore; own service receipts,
own firewall rule и overlay ledger. Durable SQL recovery без ручной очистки
резервов. Приёмка: focused/offline source checks PASS с перечисленным FAIL;
native/twoPC NOT_RUN. Новый ownhost stand C43/D44/80existingrefs подготовлен
SQLite backup API и actual existing writer fixture publication; source raw/
logical hashes unchanged, no grants/activation. Он ещё UNBOUND/NO_NETWORK.
Первый prepare attempt отказал до создания папки из-за convenience helper,
требовавшего livePID; исправлен read-only Process.snapshot None contract для
заведомо остановленных своих процессов, attempt сохранён отдельно. Следующий
шаг — actual bound ownhost socket gate при сохранении NOT_RUN для двух ПК.

## Actual own-host socket result and retained operator failure

OBSERVED first ownhost01 attempt: operator wait30s expired before final BOUND;
five templates/geometry/terrain/catalog present, stderr0, capture packetrecords0,
no Login. Both actual own children stopped by compensation, no cleanup errors;
SQL C43/D44/reserves0/full logical state unchanged. Failed attempt retained.
This was not a runtime PASS and did not change a server/HTTP/auth deadline.

New frozen services02/context03 use fresh binding-startup02.json; original
binding.json/source-restore-binding.json/retained4files remain unchanged. Fixed
operator90s budget never extends on progress. Actual startup net02-ownhost02
PASS: gateway BOUND30.736466s, total42.717854s. Thus this measured run exceeded
the previous operator30s limit. Source/runtime remained608bb23/794exact.

OBSERVED actual synthetic own-IP Login→exact advertised LAN Base→two Account
sync/run_open→Create/Join→two real HTTP/SQL Ready→both native-shaped Leave and
actual Session retirements PASS45.391s. Receipt
local/stands/net02-ownhost-20261016-01/runs/net02-ownhost02/net02-ownhost-smoke.json,
SHA7ca2881a23c442f683e9a62eafb7b191faabc3ffbf760182d8a9ac09c945d4f7.
New NET DB C44/D45, ammo[0,4,10]unchanged/active0; afterlogin exactly+1revision/
ledger per owner and no Ready/Leave writes. No411/reserve/Worldstart occurred.
Original P10B DBs/fixtures/client ledgers remain preserved separately.

Actual Windows endpoint observation: gateway's two UDP listeners on selected
RFC1918 host20240/20241; bridge's sole TCP listener127.0.0.1:3492. This does not
prove B-to-A reachability or remote TCP refusal. Both own processes stopped by
receipt after PASS. No firewall/profile change, B/native/WAN remain NOT_RUN.

New source restore helper:15isolatedGit PASS, actual capture4ownraw/audit794/
changes0 PASS, applyNOT_RUN. Separate P10B native companion10PASS promoted;
actual wrong-NET runtime bind refusal PASS, positiveP10Binstall/native NOT_RUN.
Operator commands were versioned to wait real90s gateway startup before clientA.

Final evidence local/evidence/20261016-net02-integration01/checkpoint02.json,
SHA708730d58ba81e7ea249a4fafd992f62a1f8b136fe321d3cf593eeddc0ac0014.
This ownhost initial43/44 binding is consumed: do not rerun it against44/45 or
rewrite initial_state/SQL. Actual twoPC needs new paired stand from current
actual data and realB/interface/per-PC overlays. Next owner step is the saved
coreV7 native matrix, then later qualification/P10B/paired LAN; no tail before
the first battle milestone. Acceptance: FULL_AND_OWNHOST_PASS; native/twoPC/
firewall/hostingNOT_RUN, no main merge.
## Дополнение: наблюдаемый UDP ingress-size gate

Heartbeat после full/ownhost checkpoint использован для отдельного
pre-auth gateway-only стенда. Production source/runtime608/794/full1414 и80
ресурсных ссылок прежние; standalone binding не содержит owner/initial_state/
credentials/DB. Derived config меняет только Login/Base20242/20243 и advertised
Base. Служебный HTTP3492 блокируется exclusive socket без listen; Node/bridge,
auth, SQL, fixtures и клиентские overlay не запускаются и не меняются.

VERIFIED source: shared/server.rs вызывает admit_datagram до Recorder.observe;
Login bound1553 и Base1024. ASCII marker не соответствует ни целому Login,
ни measured fragments1437/142, а пустая Session Table отвергает Base. Helper
frozen01 SHA b8264b6bd22f56b33997da4a0dcc6457174f1f1a38b3ae1ffc2569760904b643,
23 authored component tests PASS на fake sockets/Popen; это отдельно от actual
сети. Source/exe pin проверяется перед spawn, точный собственный Popen handle
закрывается при любом postspawn failure; окончательный capture/log читается
после stop, затем повторяется полный source/resource/config audit.

OBSERVED Windows own run ingress-size01:34.445с/BOUND30.221626с; Login1553 и
Base1024 записались по одному до/после, всего4точных peer/channel/payloadSHA.
Пакеты1554/1025 не попали в capture, responses0. Own-IP canary доставлен;
loopback→ownIP sendto получил WinError10051. Поэтому allowlist-negative
NOT_RUN_ROUTE_UNAVAILABLE, запрещённые source-пакеты не отправлялись. Первый
предварительный canary FAIL также сохранён; его молчание не считается отказом
gateway. Никаких IP/profile/firewall изменений или source-rebind fallback.

Root after05 проверяет protected15файлов,96installed nonmutable coreV7 файлов
и794runtime source hashes unchanged. Gateway OWN_POPEN_TERMINATED/PIDabsent,
HTTP interlock закрыт с процессом helper. Actual result SHA
f9dae74c2cb32b26340e09d0c4606776a34684bcc67e1cbbfaa91017c35ff431;
Rootclosure SHA06a11ceb7645caa658308eb5693aa8bed4fbdf6f0200aa04c30d9c3cc1f12d92.
Evidence — `local/evidence/20261016-net02-ingress01` и отдельный ingress stand.

Это OBSERVED configured datagram-size-before-capture на данном Windows.
FirstBase cross-IP, native fragment semantics, remote MTU, twoPC/native/WAN
остаются NOT_RUN/UNKNOWN. В live capture reader есть fail-closed окно: raw file
появляется перед JSONL record; оно может дать ложный FAIL, но не PASS. Actualrun
его не встретил, frozen helper не ослаблялся. Эта дополнительная диагностика
не закрывает карточку NET-02 и не разрешает main merge или хвост.
