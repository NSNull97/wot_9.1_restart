# Границы игровой инфраструктуры

Карточка 2026-10-06. Цель владельца: самостоятельная инфраструктура «Стального
рубежа» (GAYmDev Stutio), постепенно доведённая до настоящих сетевых боёв **15×15**
на проверенном родном клиенте 0.9.1. Эта карточка реализует первый изолированный
срез identity/account; приёмка native и переключение работающих служб отдельно.

## Фактическая исходная система

**VERIFIED (source):** `web/src/app.mjs` пишет `users`, `sessions`, `rate_limits`
через `web/src/store.mjs`. Email — login, UUID `users.id` — account_id, ник отдельно.
`server/identity/service.mjs` импортирует `web/src/game-adapter.mjs`: bridge читает
парольную БД сайта read-only, проверяет пароль, пишет game DB, генерирует native
fixtures. Rust `gateway/src/account/identity.rs` получает UUID/native ID/name/path
через `/internal/native/login`. Сайт импортирует game-adapter для HTTP overview;
этот импорт подтягивает реализацию игрового хранилища и frozen encoders.

**OBSERVED (read-only status):** supervisor 96576, identity 81748, gateway 5192,
run `local/server/run-20261006T061506-d7a679`, capture=false; сайт отдельный,
website_owned=false. Текущий executable — прежний `p01-wg-probe.exe`.
Предыдущая приёмка `PASS_SERVER_SOURCE_LAYOUT`: final-audit-02/result.json SHA256
`64640f29fbf1a502a318e110c34f89fd76440c6ada2afdbb131c8dc9cda03b6f`.
Это свидетельство старого рабочего пути, а не native проверка новой архитектуры.

## Владение и зависимости

| Компонент | Единственный владелец записи | Разрешённый контракт |
|---|---|---|
| Identity/accounts | email, password hashes, стабильный account_id, ник, публичные поля профиля, auth sessions и ограничения попыток | versioned HTTP account API; service roles portal/game |
| Portal | представление, формы, cookie транспорт; позже собственные новости/настройки сайта | identity API; read-only game overview API; никаких игровых таблиц/encoder imports |
| Game account/session | native ID mapping, гараж, ресурсы, игровая статистика, игровая сессия | identity assertion по account_id; typed game read/commands |
| Native gateway | соединения, framing/ACK, native IDs и перевод команд | identity/game session и доменные команды; без парольных таблиц |
| Lobby/orchestration/matchmaking (позже) | очередь, reservation, состав матча | account_id + vehicle reservation + battle allocation |
| Battle worker (позже) | один авторитетный мир боя | доменные команды, разрешённые каждому клиенту события |
| Persistence/results (позже) | durable результаты/прогресс, idempotency ledger | один result_id, атомарное применение один раз |

Боевой worker определяет движение, боеприпасы, попадания, HP, видимость и итоги.
Скрытые позиции противника не покидают разрешённую репликацию. Native wire IDs не
попадают в физику/экономику. Один бой принадлежит одному процессу симуляции.
Логические границы пока размещаются на одном хосте; SQLite сохраняется. Новые
платформы, PostgreSQL, Kafka/Kubernetes и зависимости этой карточке не нужны.

## Рабочий срез и контракт

1. Сохранить before sources/SHA и read-only runtime evidence в отдельном
   `local/evidence/20261006-infrastructure-boundaries/`; live SQLite не открывать.
2. Реализовать независимый `server/identity` account service на закреплённом Node,
   SQLite schema/migration ledger с digest; HTTP envelope `identity.account.v1`.
   Loopback numeric origin, отдельные service roles, bounded JSON, deadlines,
   bounded scrypt. Регистрация/email login/browser session/profile/game verify.
   Game assertion содержит account_id/ник/created_at, не email/hash/session token.
3. Подключить реальный портал через opt-in remote adapter. Legacy запуск остаётся
   существующим режимом. Новый режим не открывает DB и не импортирует game runtime;
   неподключённые game resources явно unavailable/not_connected, без fake гаража.
4. Проверить регистрацию через HTML формы → отдельный login → game credential
   verification → profile persistence после restart. Проверить чужой аккаунт,
   неверный пароль, service unavailable, contract mismatch, CSRF/session revoke.
   HTTP доказывает account boundary; native client compatibility **NOT_RUN**.
5. Проверить offline импорт только специально созданной legacy test DB в новый
   destination: UUID/ник/hash/profile неизменны, источник read-only, backup/SHA,
   unknown schema/conflict отказ. Auth sessions при реальном переходе инвалидировать
   явно; автоматического переноса активных cookie и второго writer нет.

HTTP envelope имеет точный вид `{contract:"identity.account.v1", operation,
payload}` и ответ `{contract, operation, ok, data|error:{code}}`. Portal operations:
`session/open`, `session/read`, `register`, `login`, `profile/update`,
`session/revoke`; game operation: `credentials/verify`. Portal profile DTO
содержит только `account_id`, `nickname`, `nickname_key`, `email`,
`display_name`, `bio`, `created_at`, `updated_at`. Game DTO содержит только
`account_id`, `nickname`, `created_at`. Ни один DTO не несёт password hash,
browser session в game response, или filesystem/fixture path. Клиент проверяет
operation-specific DTO shape до принятия успешного ответа; contract mismatch,
invalid credentials/session, rate limit и unavailable имеют отдельные bounded
коды/HTTP статусы.

## Поэтапная миграция и откат

**A — эта карточка:** новый независимый service и opt-in portal на изолированных
портах/пустой SQLite. Native game consumer только проверяет учётку. Действующие
config/EXE/DLL, клиенты, live DB, старые receipts и 13 frozen anchors сохраняются.

**B — отдельная карточка content/encoder export:** versioned manifest с ruleset,
client manifest digest, encoder revision, источниками/лицензиями, входными blobs
и digest каждого файла. Локальный экспорт из проверенных ресурсов → переносимый
server content bundle; генератор читает bundle без установки клиента. Старые
profile1/profile4 validators и absolute provenance остаются frozen. Новая версия
provenance хранит относительные content IDs плюс связь с исходным receipt; нужно
доказать эквивалентность bytes/UUID/native IDs. Старые pins массово не переписывать.

**C — game boundary:** извлечь владельца game DB и encoder API; native credential
flow вызывает новый identity, затем game profile. Новый API для portal overview
сохраняет версию и авторизованный account_id. Только после настоящего повторного
входа/ангара/поездки разрешено обсуждать переключение. Никакого credential DB read
у gateway и никакой зависимости нового game service от внутренних web modules.

**D — согласованное переключение:** отдельно утверждённое окно, остановить writers,
создать consistent SQLite backups (включая WAL), проверить hashes/количество/UUID,
импортировать offline и сменить config. Не запускать старый и новый writer на одну
БД. При отказе до новых записей вернуть старые config и исходные snapshots. После
новых записей откат требует отдельного reverse export/сверки; слепо возвращать
старую БД нельзя. Никаких dual writes или фоновой миграции рабочих данных.

**E — игровые срезы:** game session/ангар → lobby/reservation → два настоящих
клиента в одном авторитетном мире → стрельба/урон/видимость/results → измеренный
переход к 15×15. Каждый шаг со своей приёмкой и откатом; пустые сервисы не создаём.

Параллельный `battle_progress` трек владельца продолжает native/battle evidence
рядом с этой веткой. Он не делит исходники, live SQLite, configs или evidence
receipts с identity/account карточкой; координация между треками идёт только через
принятые versioned contracts и отдельные before/after evidence/rollback. Его
результаты не являются доказательством account boundary, а этот срез не меняет
battle evidence, клиент или действующий runtime.

Source откат этой карточки: собственные before/after manifests; отказ при новых
изменениях файлов, удалять только собственные новые files с совпавшим SHA.
`git restore` непригоден: исходное дерево untracked. Live runtime откат не нужен,
поскольку его переключение не выполняется. Старый layout rollback после этих
правок закономерно не применим.

## Неопределённость и ограничения

- **INFERRED:** одного локального identity writer достаточно для текущего стенда;
  масштабирование и нагрузочная ёмкость не измерены.
- **UNKNOWN:** Linux ABI/build, native remote login, публичная transport security;
  нынешние loopback endpoints наружу не открывать, worker loader требует `.exe`.
- Map-drive ограничен profile4; pivot, cruise25/50, динамические деревья и историческая
  физика остаются отдельными карточками. Многосессионность, стрельба и 15×15 не готовы.
- Новые profile encoders ещё используют client resources/evidence paths до этапа B.
- Границы владения — проектное решение, не описание исследованной архитектуры WG.

## Приёмка

До исполнения: **NOT_RUN**. Итоговые команды, результаты, независимый audit и
точный source rollback будут записаны в `docs/research/IDENTITY_BOUNDARY.md`.
