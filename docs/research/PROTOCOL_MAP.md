# PROTOCOL_MAP — статические контракты клиента #717

Runs: `20261002-p00-p01`, `20261002-p01-bootstrap`, `20261002-p02-login-redirect`,
`20261004-p02-baseapp-reply`, `20261004-p02-channel-ack`, `20261004-p02-server-reliable`, `20261004-p02-session-gateway`.
**PASS узкого native login/rejection и LoginSuccess → первый BaseApp request**.
Также PASS BaseApp reply → первый encrypted client frame и callback LOGGED_ON.
PASS ACK первого sequence=0 и limited keepalive до 21.61 s; общий канал NOT_RUN.
PASS server seq0 и duplicate → native transport-only ACK cumulative1/1.
Полная сессия/Account/arena NOT_RUN. Статические схемы отделены от выполнявшихся сценариев.
Новый corpus и смещения: [BOOTSTRAP_AND_NATIVE_LOGIN](P01_BOOTSTRAP_AND_NATIVE_LOGIN.md).

## Definitions

`res/scripts/entities.xml` содержит **44 имени**, включая Account, Avatar,
Arena, Vehicle, Login, AreaDestructibles, DetachedTurret. SHA-256:
`5613d3affa600b80a2c04418cc5bc8549dd7e0ecf77c04efee11fb42e4061004`.
Это порядок имён в файле, **не доказанная таблица wire IDs**.
`entity_defs/alias.xml` содержит **23 alias**, SHA-256:
`14d5fcce8d979de6c24c50b3ff94d3ddf464f4ad27f2ef68c063407b4bbbc746`.

| Файл | ClientMethods | BaseMethods | CellMethods | Properties |
|---|---:|---:|---:|---:|
| account.def | 35 | 101 | 0 | 26 |
| avatar.def | 30 | 48 | 18 | 20 |
| vehicle.def | 8 | 6 | 39 | 30 |
| arena.def | 0 | 25 | 9 | 19 |
| login.def | 2 | 3 | 0 | 2 |

Это локальные записи файла без разворачивания `Implements`; их количество
нельзя выдавать за число доступных удалённому игроку RPC.
Полные имена, Exposed, типы аргументов, flags и интерфейсы сохранены в
[contracts.json](../../local/evidence/20261002-p00-p01/summary/contracts.json).
Хеши каждого исходника — соседний `sources.json`.

VERIFIED: Account implements Chat, AccountEditor, TransactionUser. Схемы
содержат числовые скаляры, STRING, VECTOR3, ARRAY, TUPLE, FIXED_DICT, MAILBOX
и PYTHON. Среди aliases есть PUBLIC_ARENA_INFO, PUBLIC_VEHICLE_INFO,
POSITION_AND_RADIO, ATTACK_RESULTS, ARENA_ADDPLAYER_INFO. Последний включает
vehCompDescr, vehAmmo, vehCrew. Полный wire encoding этих полей — UNKNOWN.

## Статический путь входа

`res/scripts/client/connectionmanager.pyc`, SHA-256
`84deb9fbacb295991ae332df520c54a48fad62dcfee5d854eb7637bf402c0d20`:
`ConnectionManager.connect`, исходная line 115, bytecode offsets 323–389
заполняют LoginInfo.username через JSON/UTF-8, password, inactivityTimeout
и optional publicKeyPath. Offsets 469–502 вызывают
`BigWorld.connect(url, loginInfo, partial(connectionWatcher, ...))`.
Это локальный API движка; JSON внутри username не является нашим новым
сетевым JSON/WebSocket-протоколом.

В `scripts_config.xml/login/host` присутствуют RU login hosts и public_key_path;
использовались только как статические данные. Эксперименты задавали
`127.0.0.1:20014`, тестовый ключ проекта и отдельные тестовые credentials.
Callback проверяет stages/status; в bytecode есть LOGGED_ON,
LOGIN_BAD_PROTOCOL_VERSION и LOGIN_REJECTED_BAD_DIGEST. Наличие строк не
доказывает числовые wire-значения, шифрование или успешный вход.

Доказательства: `decoded/connectionmanager.bytecode.json`,
`decoded/res__scripts_config.xml.flat.json`; воспроизведение —
`python -X utf8 tools/static_extract.py --out <новый local-каталог>`.

## Аккаунт, арена, машины

| VERIFIED: найденный клиентский обработчик | Расположение исходной строки в code record | Что остаётся UNKNOWN |
|---|---|---|
| PlayerAccount.onBecomePlayer / showGUI | account.pyc:210 / 573 | Минимальное содержимое аккаунта и порядок серверных сообщений |
| PlayerAvatar.onBecomePlayer / onEnterWorld | avatar.pyc:147 / 388 | Как native session передаёт управление новой сущности |
| PlayerAvatar.vehicle_onEnterWorld | avatar.pyc:995 | Порядок создания Vehicle, space, appearance, prerequisites |
| PlayerAvatar.updateArena | avatar.pyc:1776 | Полная семантика updateType/payload, обязательный seed арены |
| PlayerAvatar.moveVehicle / shoot | avatar.pyc:2130 / 2226 | Реальный входящий wire payload, частоты, доверенные поля |
| Vehicle.onEnterWorld / set_health / onHealthChanged | vehicle.pyc:126 / 363 / 385 | Wire IDs, порядок update/event, фактические звуки и UI |

Локальные классы PlayerAccount/PlayerAvatar не следует путать с именами entity
types Account/Avatar. Таблица содержит координаты из code records, а не
выдуманные строки декомпилированного исходника. Полные ссылки —
`summary/lifecycle-static.json` и `decoded/*.bytecode.json`.

INFERRED: возможный необходимый путь — native login → player Account →
передача управления Avatar + space → Vehicle и аренные обновления. Этот граф
служит планом эксперимента; выполнение и достаточность не доказаны.
Сервер обязан интерпретировать реальную семантику движения, а не просто
доверять полученным координатам. Готовый API доменных команд не придуман.

## Транспорт: граница подтверждений

| Область | Статус для этого клиента | Следующее доказательство |
|---|---|---|
| Начальный login request/reply framing | VERIFIED: без 4-byte prefix, flags=1, request ID и footer; negative/success reply приняты | Не обобщать на дальнейшие channels/fragmentation/ACK |
| RSA и login request | VERIFIED: два RSA-1024 OAEP/SHA1 блока, тестовые credentials; отдельный encryption bool отсутствует | Lab credential/digest rejection VERIFIED; общая авторизация UNKNOWN |
| LoginSuccess | VERIFIED: status=1; 28 B reply; Blowfish, previous plaintext XOR, 12-byte redirect + zero padding | Полная семантика двух нулевых address bytes UNKNOWN |
| Первый BaseApp request | VERIFIED: 21 B, ID=0, length=8, request ID, echoed handoff token, четыре байта tail; static writer дважды пишет 4 bytes | Смысл tail как attempt counter INFERRED |
| BaseApp reply | VERIFIED: encrypted 24 B, clear 15 B, reply ID=255, length=8, request ID + новый 4-byte token | Полный session lifecycle UNKNOWN |
| Первый encrypted client frame | VERIFIED: wire 24 B, clear 16 B, flags=0x0458, ID=1 + echo token, byte 09, seq0 и cumulative0 | Значение 09 и общий dispatch UNKNOWN |
| Первый ACK / keepalive | VERIFIED: clear `08 04 01 00 00 00`, wire 16 B; ACK1 прекращает повтор seq0, ACK0 сохраняет повторы, оба удерживают связь в окне опыта | Общие окна/потери/wraparound/fragmentation NOT_RUN |
| Protocol value / login IDs | OBSERVED: protocol=0x02030000, login ID=0, reply ID=255, SERVER_NOT_READY=73; VERIFIED Account create message5/type0 в новой карточке | Остальные entity/method IDs UNKNOWN |
| Base/Cell lifecycle, переход в арену | Native Account creation VERIFIED; original Python bootstrap FAIL; Cell/arena UNKNOWN | Сначала original Settings bootstrap на собственном endpoint |
| Предсказание, correction, client clock | UNKNOWN | Измерения своего и удалённого Vehicle |
| PYTHON/упакованные STRING | UNKNOWN | Корпус реальных разрешённых форм; ограниченный парсер данных без pickle-execution |

Toolkit на закреплённом commit описывает часть новых IDs как исследованные
на **v2.3.1.3 (2026)** (`app/login/element.rs`), поэтому эти числа не назначены
клиенту 0.9.1 без проверки. Измерено несовпадение: modern SERVER_NOT_READY=74,
но клиент #717 трактует 74 как UPDATER_NOT_READY; 73 подтверждён EXE и callback.
Stock reader не принимает реальный packet. Собственный профиль `legacy091`
ограниченно разбирает измеренный request; toolkit Bundle writer формирует
reply с проектной исторической константой. Vendor не изменён. Проверенные
native-04/05 завершаются отрицательным ответом, без Account или arena.

Отдельный профиль `legacy091-redirect` использует LoginSuccess encoder toolkit,
проверенный в этой узкой форме настоящим клиентом. Это не совместимость всего
toolkit. Его BaseApp LoginKey — Fixed(7), тогда как наши реальные datagrams
имеют заголовок длины и 8-byte payload. Последний tail наблюдался как 0…5 при
чтении u32 LE; INFERRED счётчик попыток. Новый static writer `0xd76260`
подтверждает две 4-byte записи; семантика второго поля ещё ограниченно известна.
Точные offsets, хеши и независимая корреляция токена —
[P02_LOGIN_REDIRECT](P02_LOGIN_REDIRECT.md). Это не wire IDs entity RPC.

В [P02_BASEAPP_REPLY](P02_BASEAPP_REPLY.md) измерено packet encryption:
Blowfish с previous-plaintext XOR, footer `EF BE AD DE` и wastage byte.
Ключ тот же, что в LoginRequest; modern clear prefix отсутствует. Callback
LOGGED_ON получен без создания Account. Следующие flags 0x045a/0x0458 и
callback 6/NOT_SET сохранены; остатки сообщений не dispatch-ятся. Значения
flag bits первоначально были кандидатами до отдельного legacy channel experiment.

[P02_CHANNEL_ACK](P02_CHANNEL_ACK.md) подтвердил cumulative ACK bit 0x0400
через EXE branch/call и реальные controls ACK=0/1. Footer первого packet:
seq0 на offset 8, cumulative0 на offset 12. Вложенные повторы прочитаны
bounded parser с i16 ones' complement длиной последнего piggyback. Общий
parser всех flags не заявлен. Native LOGGED_ON удержался до planned quit
через 16.59/21.61 s; неизвестные application bytes не dispatch-ятся.

[P02_SERVER_RELIABLE](P02_SERVER_RELIABLE.md) опроверг предположение, что каждый
client channel frame содержит ID1/token. Transport-only ACK — clear10 B,
flags0x0448 + sequence + cumulative, без body. Он распознаётся отдельно
после установленного peer/key/first-token handshake и фактической server send.
Первый server seq0 и identical duplicate оба подтверждены cumulative1;
общий parser/dispatch этим не заменён.

[P02_LAB_GATEWAY](P02_LAB_GATEWAY.md) подтвердил selective ACK flags0x044c:
footer sequence + u32 ACK list + u8 count + cumulative. В реальном corpus
count=1; остальные значения ограниченно проверены controls. При gap1→0
cumulative0/selective[1] сменяется cumulative2. Автоматический retry после
proxy drop, 10 native cycles одного gateway и native отказы67/69 проверены.
Body `01 <token> 0b 00` измерен на native disconnect; gateway закрывает сессию.
На момент gateway карточки общие RPC/fragments, Account, game UI и арена NOT_RUN.

[P02_NATIVE_ACCOUNT](P02_NATIVE_ACCOUNT.md) затем подтвердил message ID5/VAR2
`createBasePlayer`, entity type0=Account, u32 entity ID + u16 type + три
length-prefixed свойства: requiredVersion_9100, name, serverSettings. Реальный
`Account.PlayerAccount` прочитал все поля в пяти runs; no-creation control
оставил player пустым, потеря Account packet устранена автоматическим retry.
Проверена только форма коротких STRING и fixed PYTHON empty-dict literal,
остальные объекты/длинные lengths UNKNOWN. Original Python lifecycle FAIL
на Settings.g_instance/userPrefs → отсутствующий syncData; UI/арена NOT_RUN.
Остальные entity IDs и RPC numbers не выводятся автоматически из этого результата.

Граница будущей реализации: native packet/types/IDs принадлежат compatibility;
в simulation допускаются только проверенные доменные команды. Публичные
названия независимы от обеих систем ID: [NAMING](../NAMING.md).
