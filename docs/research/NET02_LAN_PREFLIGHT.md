# NET-02: preflight двух ПК и закрытого LAN-стенда

Дата исследования: 2026-10-16. Это **подготовка по исходникам**, не реализация и не
приёмка NET-02. Сеть, firewall, процессы и настройки стендов не изменялись. Игровой
запуск с двух ПК, удалённый native login, UDP redirect и хостинг: **NOT_RUN**.

Контекст чтения: `HEAD 8d2d0826dfa3a48d217c0d37ce86087e1da21a82`, затем shared
checkout `codex/p05c-shared-physics`; параллельная P05C может менять исходники.
Перед реализацией повторно сверить перечисленные функции и актуальный head.
Прочитаны ACTIVE_GATE, IMPLEMENTATION_ORDER §9, STATUS, DEV_NOTES, ночное
разрешение `docs/plans/NIGHT_20261016.md` и применимый IDENTITY_BOUNDARY.
Разрешение ночной последовательности не делает native NOT_RUN выполненным.

Метки: **VERIFIED_STATIC** — установленное чтением конкретного исходника;
**OBSERVED** — факт этой проверки файлов; **INFERRED/PROPOSED** — предлагаемое
решение; **UNKNOWN** — требуется отдельное измерение/решение. Ни один новый
автоматический или native тест в рамках этого исследования не запускался.

## 1. Практический вывод

Сейчас недостаточно заменить `127.0.0.1` в JSON. Есть три независимые блокировки:

1. `Config::load` одним валидатором запрещает nonloopback для игровых bind и
   приватного identity endpoint.
2. Действующий receive loop shared gateway отбрасывает любой nonloopback peer.
3. `redirect::reply_to` запрещает nonloopback, причём переданный адрес сейчас
   равен `config.base_bind` — отдельного публикуемого BaseApp адреса нет.

**PROPOSED минимальный первый этап:** один существующий хост A со всей серверной
БД/физикой/ресурсами и клиент B на втором принадлежащем владельцу ПК. Оба клиента
подключаются к одному конкретному LAN IPv4 хоста A. Открываются только два
игровых UDP-порта для двух точных IP. Приватные HTTP, SQLite, исходные bundle,
служебные токены и RSA private key остаются на A. Сайт для первого теста не
обязательно выводить в LAN: собственные аккаунты можно подготовить локально на A.

Это подготовка к проверяемому LAN transport gate. Публичный Internet/NAT-хостинг
нельзя объявлять пройденным по результату этого gate.

## 2. Где именно стоят ограничения

Все пути ниже относительно корня репозитория; номера строк — ориентир на дату
чтения, имена функций устойчивее при параллельных изменениях.

| Граница | VERIFIED_STATIC источник | Нынешнее поведение / следствие |
| --- | --- | --- |
| Общая проектная настройка | `config/project.local.example.json:15`, `tools/client_audit.py::config` | Поле называется `connection.listen_host`, не `network.listen_host`. В просмотренных `tools/`, `server/`, `web/` не найден runtime consumer `listen_host`/`allow_external_targets`; `config()` читает paths. Правка этого поля сама gateway не переключает. |
| Gateway config | `server/gateway/src/account/identity.rs:44`, `Config::load` | `local_address` принимает только числовой IPv4 `127.0.0.1` и ненулевой порт. Его вызывают для `login_bind`, `base_bind`, `identity_endpoint`; DNS и wildcard запрещены. JSON ограничен4096байт, уникальными ключами и16 top-level полями; оставшиеся обязательные поля проверяются точно. |
| Игровые сокеты | `server/gateway/src/shared/server.rs::serve_profile13`, `serve_with_pool` | Два `UdpSocket::bind(config.login_bind/base_bind)`; после них запускается auth/run recovery. В receive loop до capture/reassembly/crypto: `peer.ip()!=LOCALHOST`, общий лимит256 входящих datagram/с, Login до1553 логических байт и Base до1024. |
| Login redirect | `server/gateway/src/shared/server.rs:1051`, `server/gateway/src/protocol/redirect.rs::reply_to` | Отправляется `config.base_bind`. `reply_to` допускает только loopback+ненулевой порт; native LoginSuccess кодируется существующим codec, шифруется ключом сессии. Ручной новый формат redirect не нужен. |
| Старые режимы | `server/gateway/src/session.rs::serve*`, `protocol/{login,baseapp,redirect}.rs::serve*` | Есть отдельные loopback defaults/peer guards диагностик и интерактивного single-account пути. Не путать их с фактическим `legacy091-profile13`; расширение одной функции не расширяет остальные автоматически. |
| Приватный game bridge | `web/src/game-adapter.mjs::createIdentityBridge`, request handler | Всегда `server.listen(port,'127.0.0.1')`. До маршрутов: exact remoteAddress127.0.0.1, exact Host127.0.0.1:port, запрещён Origin. `/health` без токена, остальные запросы требуют constant-time Bearer check; maxConnections16, active4, bounded body/deadline. |
| Gateway→bridge | `account/identity.rs::post_with_budget` | Только заранее заданный numeric endpoint, фиксированные внутренние paths, TCP connect500мс, write2с, общий deadline и response bounds. Host и Bearer формируются на сервере. Клиент не выбирает URL и не получает токен. |
| Site→identity | `server/contracts/identity_client.mjs::endpoint`, `server/identity/account_service.mjs::createIdentityService` | Numeric loopback HTTP; service listener тоже loopback, role/token/origin checks. Это opt-in infrastructure boundary; сам `account_service.mjs` явно сообщает, что legacy native bridge не мигрирован на него автоматически. Не перестраивать авторизацию ради NET-02. |
| Сайт | `web/src/network.mjs::readNetworkConfig/validateOrigins` | Legacy web уже умеет explicit `WEB_HOST=0.0.0.0` с обязательным точным `WEB_ORIGINS` (до8). По умолчанию127.0.0.1. Это capability сайта, не gateway/identity. Тест `network.test.mjs` эмулирует Host на loopback и не доказывает физическую LAN-доступность. |
| Новый account portal | `web/src/account_server.mjs`, `web/src/account_portal.mjs::originOf` | Конфигурация/identity URL/portal origin сейчас толькоloopback. Включение legacy WEB_HOST не распространяется на этот путь. |
| Client prepare | `tools/interactive_client.py::prepare:158` | Только regex127.0.0.1:port1024..65535; registration URL тоже только http://127.0.0.1:port/register. Публичный PEM отдельно проверяется на отсутствие PRIVATE. Profile13 требует isolated copy и полный предыдущий набор hangar flags. |
| Ввод native login | `client_patch/project_auth.py::install/submit` | Exact match `host==configured endpoint`, canonical project email, password UTF-8 bytes сохраняются через старый `.strip()`, credential debug string редактируется. Здесь нет отдельного IP parser: ошибка называет loopback, но реальный запрет адреса находится в prepare. Не отключать exact match при LAN. |
| Подготовленные client settings | `tools/interactive_client.py:270`, `client_patch/sr_interactive.py::init` | В settings входят абсолютные profile/trace/local/screenshot/control paths; install имеет before/after hashes и rollback. Нельзя просто перенести готовый settings/plan с A на B. |
| Обычный supervisor | `server/control/service.py::read_config/reserve_check/recovery_port_check/start` | Жёстко проверяет старый deployed p01 executable, login20014/base20016/identity20020, bind127.0.0.1, стартует interactive/map-drive, не нынешний profile13 manifest путь. `server/manage.py` нельзя обещать готовым LAN/profile13 launcher. |
| Другие stand helpers | `web/src/test-garage.mjs`, `web/src/ms1-ammo.mjs`, `web/src/ms1-crew.mjs`, `tools/{manual_client_run,diagnostic_client_run,client_probe}.py` | Встречаются отдельные numericloopback validators/port leases/proxy20014→20015,20016→20017. Они не нужны как прокси первого прямого profile13 LAN запуска; старую диагностику сохранять отдельной. |

`DEV_NOTES` фиксирует текущий P08B стенд: private bridge3481,
login20130/base20131, CLI `legacy091-profile13 KEY DIGEST GATEWAY MANIFEST CAPTURE`.
Это существующий loopback стенд, а не выбранные/проверенные порты будущего LAN.

## 3. Вход, ключи и привязка peer

**VERIFIED_STATIC** native цепочка:

1. `tools/interactive_client.py::prepare` правит только исследовательскую копию:
   allowlisted login endpoint, путь `sr_local.pubkey`, disabled token login,
   remember-password false, локальные ресурсные настройки. Оригинал не меняется.
   `project_auth.install` передаёт ввод дальше оригинальным
   LoginView/LoginDispatcher/ConnectionManager; свой HTTP/game transport вместо
   native не вводится.
2. `protocol/login.rs::{load_key,decode_interactive,decode_profile}` читает
   server private PKCS8 PEM (до16384байт), требует RSA1024, расшифровывает блоки
   RSA-OAEP/SHA1 по128байт. Число/размер блоков ограничены (interactive до12).
   LoginFragments допускает только измеренные два фрагмента, до4 pending sets,
   TTL5с; не универсальный UDP fragment assembler.
3. Login содержит client digest16, key16 и nonce. Digest проверяет совместимость
   конкретного клиента, не заменяет credential authentication. Shared gateway
   сверяет digest; `Config::authenticate` передаёт только bounded email/password
   приватному `/internal/native/login`.
4. Bridge проверяет scrypt password через текущий identity store, global60/min и
   email10/15min limits; profile13 login разрешён только configured owner registry.
   Ответ связывает account UUID/native DB ID/fixture_dir; gateway проверяет
   источник профиля, metadata, policy/catalog hashes. Приватный fixture path
   не предназначен для передачи remote browser/native client.
5. До выдачи redirect auth result повторно проходит admission; создаются
   случайные handoff32/session token32. `Table::admissible` ограничивает sessions
   общей capacity и retained32, не допускает совпадающий key/peer другой сессии.
   LoginAttempt включает key,nonce,login peer; идентичность аккаунта проверяется
   отдельно, nonce/IP не считаются аккаунтом.
6. `Table::route` для21B Base request ищет ровно один handoff token;
   `protocol/baseapp.rs::base_request` проверяет точный wire shape/token/attempt≤5.
   **Сейчас он не сравнивает IP Base peer с IP login peer**. После bind остальные
   datagram маршрутизируются по точному SocketAddr и декодируются только ключом
   этой сессии. `route_never_tries_another_key_or_rebinds_a_live_peer` — существующий
   unit test. Для loopback все peer IP одинаковы; этот факт не является LAN gate.
7. `session.rs::RetirementWindow` сохраняет32 retired attempts до120с и защищает
   старые Login/Base peers при повторно использованном ключе. Проверка до auth,
   после auth и до Base receive должна сохраниться. Account→Avatar→Account не
   создаёт новый game login key и не даёт права обходить retirement.

**PROPOSED:** добавить для нового LAN режима same-IP login→first Base binding до
изменения session state. **Не требовать равенства UDP source ports**: LoginApp и
BaseApp — разные endpoints; существующая модель хранит их раздельно. Чужой IP с
подсмотренным/угаданным handoff не должен занять peer. Точная native LAN/NAT
семантика пока UNKNOWN; для первого LAN без relay требование одного source IP
проверяемо. Не вводить незаметный автоматический peer rebind после network change.

Существующий Base cipher — Blowfish с footer MAGIC, не новый проектный защищённый
протокол. Наличие native шифрования/RSA1024 не означает готовность к враждебному
Internet. В рамках NET-02 сначала проверять закрытую LAN; публичный хостинг
потребует отдельного решения о защищённом доступе, abuse control и perimeter.
Ключ клиента только **public**; private PEM, Bearer token, user hashes/DB, login
controls не включаются в клиентский пакет или публичный evidence.

## 4. Минимальный контракт будущей LAN-конфигурации

Ни один новый ключ ниже **пока не реализован**. Это рекомендация для одной
versioned NET-02 карточки, без нового service framework.

Сохранить текущую loopback config shape и поведение по умолчанию. Для opt-in
режима добавить **один bounded объект**, например `game_network`, version1:

```json
{
  "game_network": {
    "version": 1,
    "mode": "lan_test",
    "advertised_base": "192.168.50.10:20131",
    "allowed_peer_ips": ["192.168.50.10", "192.168.50.11"]
  }
}
```

Адреса здесь **только пример**, не обнаруженные адреса пользователя. Существующие
`login_bind`/`base_bind` в том же будущем конфиге должны быть явными
`192.168.50.10:20130` и `192.168.50.10:20131`; identity остаётся
`127.0.0.1:<private_port>`. Клиент A также использует LAN login endpoint A, чтобы
оба запуска проходили один путь. Вариант A-local loopback требует явного
дополнительного bind/правила, сейчас его не предполагать.

Почему один объект: текущие6 обязательных+10 опциональных полей исчерпывают
top-level JSON budget16. Простое добавление ещё трёх плоских полей сломает
`Bounded<REQUEST_FIELDS>` до config parsing. Можно дать config собственный
обоснованный budget17 и точные вложенные поля/array limits; не увеличивать общий
HTTP request budget ради конфигурации. Обновить и `Config` constructors/tests.

Предлагаемые ограничения:

- Numeric IPv4, ненулевые разные игровые порты; для первого LAN только точный
  локальный RFC1918 адрес интерфейса A, без DNS, broadcast/multicast,0.0.0.0,
  Internet/public IPv4, IPv6 и автоматического определения внешнего IP.
- `advertised_base` — точный доступный клиенту A-LAN IPv4 с base port. Сокет bind
  и advertised address — разные типы/поля. В первом режиме конкретного интерфейса
  IP совпадают; отдельное поле предотвращает будущую рекламу0.0.0.0. Поддержку
  wildcard/NAT не открывать через то же ослабление валидатора.
- `allowed_peer_ips`: от1 до6 уникальных точных numeric IPv4; первоначально два
  /32 по фактическим адресам. Не вводить `*`, hostname, `/0`, широкий LAN subnet
  или произвольную unbounded CIDR библиотеку ради двух ПК. IP gate — ограничение
  доступа к стенду, не authentication account.
- Loopback absence/default сохраняет старые проверки. LAN mode требует явного
  profile13 runtime; старая probe/default redirect остаётся loopback.
- Identity parse/Host/Bearer/remoteAddress checks не меняются. Не подменять общий
  `local_address` на разрешающий всё: разделить `private_identity_address` и
  `game_bind/advertised` validators.
- Проверять allowlist в обоих игровых receive paths **до capture, fragment
  allocation, RSA и lookup**, затем отдельные authenticated peer checks. Сейчас
  счётчик общий256/с; непринятый peer увеличивает его до фильтра. Для LAN нужен
  bounded per-allowed-IP rate budget с общей верхней границей; мусор с чужого IP
  не должен съедать все trusted client slots/crypto budget. Не назначать новые
  throughput значения без trace двух/шести клиентов.
- Конфигурация отдельно ограничена размером/ключами; дубликаты, empty/oversized
  allowlist, unsupported mode, advertised port mismatch, identity nonloopback
  и несовместимые flags дают явный startup reject, без fallback на0.0.0.0.

Файлы минимального будущего изменения: `account/identity.rs` (config types и
validators), `shared/server.rs` (receive policy/redirect source/firstBase IP),
`protocol/redirect.rs` (явно проверенный LAN success address), узкие Rust tests;
`tools/interactive_client.py` (versioned explicit LAN endpoint prepare),
`client_patch/project_auth.py` (точное имя политики/сообщение, exact-match intact),
client/prepare tests и отдельный owned profile13 stand launcher/config schema.
Web/Python writer gameplay API/SQLite schema от одного LAN bind не меняются.
`service.py` менять только если он действительно выбран владельцем запуска;
не обещать старый supervisor как готовый orchestration слой дляprofile13.

## 5. Клиент B и регистрация без публикации identity

**PROPOSED последовательность**, не выполненные действия:

1. На B установить/проверить собственную локальную копию того же#717 из разрешённого
   источника. Hash EXE/resources и origin/research paths проверяются на B. Не
   пересылать оригинал с A и не подгонять client digest под неизвестный билд.
2. Передать только project-auth/compatibility исходники, manifest/hash pins,
   public PEM и template настроек без credentials. Сгенерировать local paths/
   install plan на B; CPython2.7 compiler/source provenance сохранить. Не брать
   чужие ready-made `.pyc`/перепакованный game client.
3. В новой explicit LAN prepare указать exact A login endpoint; сохранить полный
   принятый profile13 service flag chain. Никаких shared-lab/map-drive смешений.
   Оригинальные ресурсы изменяются только в исследовательской копии по existing
   verified before/after/rollback процедуре.
4. Подготовить два собственных account/owner mapping на A существующим accepted
   источником. Не писать напрямую случайные owner IDs в БД и не подменять crew/
   ammo/profile source. Клиент B вводит свои project credentials в native UI.
5. Registration URL — отдельное решение. Первый game LAN test может сохранить
   неиспользуемую локальную ссылку и явно указать регистрацию на A; нажатие её
   на B не будет работать и не считается проверкой сайта. Если нужна рабочая
   LAN registration: либо отдельный принятый legacy web origin configuration,
   либо explicit account portal LAN extension с CSRF/Host/cookie tests. **Не**
   направлять `/register` на `/internal/native/login` и не раскрывать identity
   service или Bearer B.

## 6. Firewall/NAT и измерения

Текущие адреса, Windows network profile, топология/роутер, адрес B и права firewall
**UNKNOWN**: исследование не опрашивало интерфейсы и не меняло правила. Следующая
карточка сначала фиксирует точные A/B IPv4 и Private profile в owned evidence.

Для первого запуска планируется одна именованная inbound rule только для
собственного `sr-gateway.exe`, UDP login/base ports, Private profile и exact B IP
(при необходимости A IP для собственного local LAN client). Правило с
RemoteAddress Any/Public profile и отключение firewall целиком не нужны.
Порты private bridge/identity/portal, worker, БД/SMB не добавляются. Проверка с B
должна подтвердить не только открытый игровой путь, но и недоступность private
TCP endpoints. `Test-NetConnection -Port` проверяет TCP и не доказывает UDP login.
Неизвестный UDP timeout не лечить широким отключением firewall.

Публичный NAT/UPnP/port forwarding не делать в первом этапе. Для отдельного
хостинга после LAN нужен approved advertised/public endpoint policy, адресация,
ограниченный доступ (например, явно выбранный VPN), журналирование/secret
rotation и повторная модель угроз. Подстановка public IP вместо RFC1918 в первом
режиме должна быть reject, а не скрытая публикация.

Измерения будущего native gate: timestamps/peer IP:port на A и B, login RTT,
redirect destination, Base bound/ACK, loss/retransmit counts, receive gaps,
медиана/p95 задержек state delivery, distinction network vs worker stalls.
Текущий `transport.rs` хранит RETRY700мс, interactive liveness30с,
INTERACTIVE_MAX_SEQUENCE1_000_000; эти значения не равны измеренному LAN RTT.
Не увеличивать timeout, чтобы скрыть потерянный redirect/неверный bind.
Existing `tools/gateway_faults.py` — loopback delivery controls, не готовый
удалённый LAN impairment proxy. Synthetic loss tests отдельно от native LAN.

## 7. Пакет стенда без game client resources

**VERIFIED_STATIC:** `server/README.md` прямо говорит, что нынешняя структура не
является готовым remote deployment package. `server/build.py` создаёт свежие
ignored isolated outputs, pins Rust1.90.0 Windows GNU, offline locked build;
physics — .NET9/JoltPhysicsSharp2.22.0. Он не делает portable installer/publish.
Physics worker общается по private stdin/stdout, game listener у него отсутствует.
NET-02 не требует TCP service для физики.

Первый LAN test разумно оставляет A текущим хостом. Второму ПК нужен клиентский
project patch, не копия server repository/local. Будущий runtime pack A включает:

| Группа | Содержимое / ограничение |
| --- | --- |
| Разрешённый код проекта | Проверенный sr-gateway binary + собственный source/runtime manifest, server/web/tools зависимости **по реальному transitive import graph**. `p04d-crew.mjs` запускает `tools/p08b_battle_service.py` от repository ROOT; требуется согласованный layout, не один executable. |
| Runtime | Проверенные Node24.x/Python3/physics .NET9/Jolt runtime dependencies и notices после отдельной проверки лицензий. `dotnet build` не гарантирует наличие .NET runtime на новом хосте. Не копировать SDK/cache/toolchains/target ради запуска. |
| Публичные templates | Новые config examples без абсолютных чужих paths/секретов/account data; hash manifest own binaries/versions. Production/generated config создаётся в private local/ целевой установки. |
| Local-only provision на A | Keys/tokens/SQLite/owner mappings, verified source bundle, client-derived map terrain/obstacles/geometry/descriptors и fixtures остаются private на A; не вкладываются в распространяемый runtime pack. |
| Client B patch | Только project-auth sources/manifest + public PEM, новый локальный prepare. EXE, res/, packages/, textures/models, исходные game `.pyc`, готовые mutated original resource files не передаются пакетом проекта. |

**Нельзя утверждать**, что весь backend уже работает без доступа к клиентским
ресурсам: `tools/p08b_battle_service.py::main` каждый вызов делает
`load_catalog(original_root)`/`audit(original_root)` и получает `--bundle`/
`--original-root`. Portable research bundle тоже содержит fixtures/native exports
и оригинальные encoder artifacts; расширение `.blob` не делает его кодом проекта.
Строго runtime-only package требует отдельного source-bound content provisioning
или заранее проверенного resource boundary. В NET-02 minimal LAN это решается
оставлением ресурсов на A, а не ослаблением source gates.

`profile13_templates.rs::load/owned/pin` проверяет absolute paths строго внутри
local_root, no symlink/reparse, SHA и size; manifest закрепляет pool/geometry/
catalog и их worker dependencies. Это обязательные runtime assets A, не повод
их публиковать. Лицензия на распространение производной geometry/terrain/source
exports здесь **UNKNOWN**. Не переносить их в git или общий zip.

Relocation pitfalls: Web/identity/tools вычисляют ROOT из location исходников и
допускают SQLite/config только под ROOT/local; gateway manifest/pools содержат
absolute paths и hashes. Новое место требует **генерации** новых конфигов с
сохранением SHA содержимого и записи old→new mapping, не global string replace
в source/pins. SQLite копировать штатным backup API при согласованной остановке,
а не выдёргивать `.sqlite` из WAL. Чужие работающие процессы не останавливать.
Crash-active reserve обслуживает существующий run_open recovery, это не повод
править таблицы или переиспользовать старый run UUID.

Raw captures (`protocol/capture.rs::Recorder`) содержат native wire и peer,
хотя private HTTP не записывается; shared/integrated cap48000packets/32MiB.
В сочетании с private key логин и payload могут раскрыться. Эти файлы, snapshots,
credentials controls, SQL backup, токены/PEM не входят в runtime/client/public zip.

## 8. Проверки и команды для будущей карточки

Команды ниже — **рекомендованные, NOT_RUN в этом исследовании**. Запускать из
корня в свежий output; exact runtime head и выходные SHA записывать. Они не
открывают LAN и не доказывают двухмашинный native gate.

```powershell
python -B -X utf8 server/check_layout.py
python -B -X utf8 -m unittest discover -s tests -p test_project_auth.py
python -B -X utf8 -m unittest discover -s tests -p test_retired_base_replay_verifier.py
node --test --test-concurrency=1 web/tests/network.test.mjs tests/identity_boundary.test.mjs tests/account_portal.test.mjs
node --test --test-concurrency=1 web/tests/p08b-battle.test.mjs web/tests/p08b-bridge.test.mjs
python -B -X utf8 server/build.py gateway --test --test-filter only_loopback_without_dns_and_unique_json_keys --out local/build/net02-loopback-regression-01
```

Для bridge test нужен существующий verified bundle; сейчас default
`local/stands/p09e-main-01/source-bundle-05` и original
`C:\WoT_0.9.1_RU_0717_original`, optional env `P04D_TEST_BUNDLE/P04D_TEST_ORIGINAL`.
Если источник отсутствует, тест может skip; считать такой запуск **NOT_RUN**, не
PASS. Не создавать фиктивный source, чтобы убрать skip. Все HTTP тесты используют
собственные ephemeral loopback servers и свежие isolated SQLite, не stand DB.
Старый `game-adapter.test.mjs` требует verified native descriptor file (есть
`WOT091_TEST_NATIVE`); не назначать ему произвольный JSON.

После реализации добавить meaningful tests (пока их нет):

- Gateway config matrix: oldloopback unchanged, LAN exact keys/size/IPs, duplicate
  and oversized list, private identity nonloopback reject, wildcard/public/DNS
  reject; bind vs advertised address explicitly проверяются независимо.
- Redirect fixture: source-bound native codec field address A/base port и
  encrypted success shape; wrong advertised fails before socket bind.
- UDP admission: nonallowlisted доfragment/crypto/no new session; allowed Login
  and Base from different source ports одного IP; other allowed IP with correct
  handoff cannot bind чужую сессию; retired peer/token/retry paths unchanged.
- Bounded bad traffic from one allowed peer не лишает second peer обработки;
  this is protocol/resource test, не обещание общего DDoS protection.
- Client prepare: explicit LAN target, exact connect whitelist, public-only PEM,
  rollback and per-PC paths; no change to original client and no secret fields
  in generated pack/logs.
- Private bridge/identity current403/bounds/Host/Origin/owner/replay tests remain
  green; LAN feature не расширяет их listener.

Финальные сборка/full gateway suite плюс применимый writer/Web regression — на
итоговом NET-02 head после card changes. Не ссылаться на старый P08B/P08C PASS
как на проверку новой сетевой конфигурации.

## 9. Native gate на двух ПК (весь NOT_RUN)

1. Зафиксировать оба#717 client hashes, A runtime head/binary hashes, actual A/B
   LAN IP, exact login/base/advertised, explicit allowlist и private endpoints.
   A слушает конкретный LAN interface; private HTTP слушает только127.0.0.1.
2. Wrong password и незарегистрированный owner не создают Session/reservation;
   correct project credentials обоих возвращают собственный profile13.
3. B получает redirect на A LAN/baseport, отправляет Base request; A записывает
   правильный peer IP:port, затем real native Account loaded/cache/model ACK.
   Нет fallback на B-loopback, P01 proxy или чужой public operator.
4. Native Fight обоих → общий бой; waiting/countdown/READY/движение/прицел/shot/
   AP/HP проверяются по актуальным принятым карточкам. Проверить, что local A
   успешно проходит тот же advertised path. Sourcebound automated simulation
   отдельно от реальных UI/audio/ощущений.
5. Поочерёдный Esc→Hangar и повторный общий бой; одна потеря client network не
   закрывает чужую сессию/сервер. Durable AP/terminal results/repair policy и
   atomic natural result проверяются в owned SQL/evidence, не только по GUI.
6. Закрытие/restart gateway с active reservation: существующий recovery policy
   и old-run fence; stale Base packets/ACK не влияют на новый аккаунт/бой.
7. Отдельно измерить умеренные loss/jitter/stall (owned controlled setup) и
   восстановление/timeout. Указать условия, пределы и реальный outcome;
   обычный LAN PASS не означает WAN/PAT/CGNAT/VPN tested.
8. С B private TCP routes недоступны; с A остаются exactHost/Bearer checks.
   Неуспешный forbidden UDP peer не расходует состояние/бесконечный лог.

Evidence будущего gate: redacted config+binary manifest, client prepares/rollback
receipts, launch/stop ownership, raw capture private, summarized native traces,
server events и SQLite backup/result query. Никогда не публиковать credentials/
privatekey/token. Каждый пункт имеет PASS/FAIL/NOT_RUN; незапущенные UI/audio
сохраняются NOT_RUN, карточка в main не принимается от одного документа.

## 10. Узкие неизвестные, откат и следующий шаг

**UNKNOWN до реализации/измерения:** A/B адреса/profile/firewall и фактический UDP
route; native redirect на nonloopback в обоих процессах; IP binding/NAT semantics;
реальный packet rate двух/шести peers и влияние existing256/с; loss/jitter envelope;
готовность portable Python/catalog/encoder resource boundary; third-party notices
и право распространять client-derived assets; accepted runtime head предыдущих
ночных карточек. Это не предположения, которые можно закрыть mock ACK.

**Откат этого исследования:** удалить только этот новый Markdown; code/config/DB/
original client не менялись. Root может включить его в очередной research commit.
**Откат будущего LAN:** owned stop и receipts → убрать только именованное новое
firewall правило → вернуть прежний loopback config/runtime → client rollback на
каждой research copy → existing single-gateway recovery/snapshot verification.
Schema downgrade/ручная чистка reservation не требуются от transport feature.
Private RSA/token rotate при факте раскрытия; не уничтожать forensic evidence.

Статус: **READ_ONLY_PREFLIGHT_COMPLETE; NET02_IMPLEMENTATION/TESTS/NATIVE NOT_RUN**.
Единственный рекомендуемый следующий шаг: после зависимых карт открыть NET-02
как отдельную карточку и реализовать bounded versioned game network config с
separate advertised Base и двумя exact peers, оставив private identity loopback;
сначала автоматические отрицательные/config/redirect проверки, затем owned
двухмашинный запуск по матрице выше.

## Контрольные SHA исходников при чтении

Это pins доказательства статического чтения, не gate финальной сборки; последующие
изменения P05C могут законно поменять bytes. Конфиги с секретами не хешировались
и не публиковались в этом документе.

| Файл | SHA256 |
| --- | --- |
| server/gateway/src/account/identity.rs | 4d9e282f867921c96361e6e54627c90cf1db1a20c4c7330be6114e828f9bda16 |
| server/gateway/src/shared/server.rs | 19371662d17b791322ccb2f1037b3883399c6d634fd21f27011d0b4e2579d6b7 |
| server/gateway/src/protocol/redirect.rs | 457beeb99708a72acea7ceb6f4943a5c384936ded93ae8a6ff553063bf3454cc |
| server/gateway/src/protocol/baseapp.rs | eb6f7994ba52e942ebde4c351efae8a0ed00629c8d548a767cd705eef838003f |
| web/src/game-adapter.mjs | ab3619f7099d03782d850f47e31e5d0d8e326f30bc417b1535c965754a0b6892 |
| tools/interactive_client.py | a91a5b670a12ff4f15bd5683efc373f1a6c8b20f6b95df0a493f42508d861b42 |
| client_patch/project_auth.py | 11e96cb527414c3ec3c2171e11ecd1ccee696c98c918258b01020faa3c6f5bb8 |
| server/control/service.py | 8d6afb383b4abe28313b971271671402a18bf876b5c97590cc6890770a553733 |
