# ARCH-01: текущая архитектура процессов и данных (main `d3ffab6`, 2026-10-20)

Карточка ARCH-01 — только документ. Описывает то, что **есть в коде**, а не план
[02_ARCHITECTURE](../02_ARCHITECTURE.md). Метки: VERIFIED (файл:строка в `d3ffab6`
или замер с источником), OBSERVED, INFERRED, UNKNOWN. Это архитектура нашего
сервера, а не сведения о внутренностях WG/«Ориона».

## Итог в одном абзаце

Сегодня один процесс шлюза = одна боевая арена на 2 (до 6) машин; вход — по одному
за раз; все доменные операции ангара идут цепочкой шлюз → HTTP → Node bridge →
**новый процесс Python на каждый запрос** (не больше 2 одновременно) → SQLite; физика —
отдельный C#-процесс на бой. Справочник машин/снарядов/экипажа существует минимум в
пяти закрытых копиях на четырёх языках. Для ~200 CCU ни одно из этих ограничений не
снимается добавлением железа — это ограничения программы.

## Процессы

| Процесс | Исходник | Роль сейчас | Статус |
|---|---|---|---|
| Gateway (Rust, `sr-gateway`/`p01-wg-probe.exe`) | `server/gateway/src` (~68 тыс. строк) | UDP login+base, native-сессии, **и** мир боя, и оркестрация доменных вызовов | VERIFIED |
| Physics worker (C#/.NET, Jolt) | `server/physics` (~3,6 тыс. строк) | одна сцена `--battle-scene` на бой, JSON-IPC по stdin/stdout | VERIFIED `drive/scene_worker.rs:296-299` |
| Bridge / сайт (Node) | `web/src` (~5,4 тыс. строк), `server/identity` | identity (вход по email), кабинет, HTTP-API игровых операций для шлюза | VERIFIED |
| Domain workers (Python 3) | `tools/*.py` (202 файла, ~64 тыс. строк) | магазин, исследования, экипаж, БК, допуск в бой, итоги — порождаются на запрос | VERIFIED `web/src/p04d-crew.mjs:54,75` |
| Client patch (Python 2.7.3 в клиенте) | `client_patch` (~22 тыс. строк) | UI-подсказки, трассы, допуски на стороне клиента | VERIFIED |
| Control | `server/control`, стенды `local/stands/*/services.ps1` | запуск/остановка набора процессов стенда | VERIFIED |

## Шлюз: одна арена, один цикл

- **Один мир на процесс.** `World` создаётся один раз до цикла
  (`shared/server.rs:1297`); цикл `loop` (`:1368`) последовательно читает login и base
  сокеты (`:1435`), шагает мир, публикует, спит 5 мс (`:1818`). Один поток на всё —
  VERIFIED. Паузы этого цикла (`SHARED_DRIVE_LAG_RESYNC`) — причина UNKNOWN (STATUS).
- **Ёмкость сессий.** `Table.capacity = config.battle_players` либо
  `training091::domain::MAX_ACCOUNTS` (`shared/server.rs:1284`); `battle_players` по
  умолчанию 2, допустимо 2..6 и только для profile13 (`account/identity.rs:306-310`);
  `MAX_ACCOUNTS = 24` (`training/domain.rs:11`). Отказ при `sessions.len() >= capacity`
  (`shared/server.rs:620`). Т.е. **игроки в ангаре занимают места боя** — VERIFIED.
- **Размер арены зашит.** `MAX_ACTORS = 6` объявлен независимо в пяти модулях
  (`shared/model.rs:8`, `shared/lifecycle.rs:6`, `shared/dynamic_destructible.rs:14`,
  `drive/scene_worker.rs:12`, плюс массивы `[_; MAX_ACTORS]` в `impact.rs:361-369`,
  `model.rs:189-206`); legacy drive-путь — массивы `[_; model::CAPACITY]` с
  `CAPACITY = 2` (`shared/model.rs:7`, `server.rs:92-110`). 15v15 = 30 машин — это не
  настройка, а переписывание типов — VERIFIED.
- **Вход по одному.** Одна `auth: Option<AuthJob>` (`:1359`); пока она занята, новый
  вход — отказ 73 (`:1453-1457`); также 73, если занят `battle_dispatch`,
  `result_manager`, `ammo_job`, хост тренировочной комнаты, или с прошлого входа
  прошло < 250 мс (`:1459-1460`). Очереди нет. `AuthJob` выполняется в отдельном потоке
  (`session.rs:1574-1580`) и последовательно грузит фикстуры, БК и экипаж аккаунта.
  Один profile13 identity-job = 10,6–11,0 с, окно native-клиента ~17,2 с (OBSERVED, одна
  выборка, ветка `codex/full-test-pending-login-queue`, research
  `FULL_TEST_LOGIN_QUEUE_20261020.md` на той ветке). Код 73 = `SERVER_NOT_READY`, у
  клиента нет авто-повтора (VERIFIED там же по байткоду `LoginDispatcher`).
- **Шаг мира 100 мс** (`shared/model.rs:10`, 10 Гц); scene IPC тоже 100 мс, ответ
  физики ≤ 500 мс, старт сцены ≤ 120 с (`drive/scene_worker.rs:17-19`) — VERIFIED.
  Архитектурные 30/60 Гц из 02_ARCHITECTURE не реализованы.
- **Время жизни.** profile13-сервис 12 ч, прочие 1 ч (`shared/server.rs:138`,
  `shared/model.rs:9`) — процесс задуман как лабораторный, не как служба.
- **Имена модулей по карточкам.** В `shared/` десятки файлов `p06t_*`, `p10b_*`,
  `late_results_*`, флаги конфигурации по карточкам (`identity.rs:232`) — правило 2
  [SOURCE_LAYOUT](../SOURCE_LAYOUT.md) нарушено ростом карточек — VERIFIED (листинг).
  `python -B -X utf8 server/check_layout.py` на `d3ffab6` падает: `Version/phase in
  canonical file name: gateway\srcattle\p08b_hold_policy_v1.json` — VERIFIED 2026-10-20.

## Доменная логика: процесс на запрос

- Шлюз обращается к bridge синхронным HTTP POST на loopback `identity_endpoint`
  (`account/identity.rs:464-466`, `:503`; таймауты 0,5–20 с, тело ≤ 4 KiB, кроме итогов).
- Bridge на каждую операцию порождает `python tools/<store>.py ... <operation>`
  (`web/src/p04d-crew.mjs:75-80`) с таймаутом 3,5 с / pool / 15 с (`:83`), и пускает
  **не больше двух одновременно**, третий получает `Crew worker busy` (`:68-70`) —
  VERIFIED. Генерация профиля — тоже отдельный процесс `tools/hangar_state.py`
  (`web/src/game-adapter.mjs:207`).
- Скрипт выбирается цепочкой версий карточек `p04d…p04k`, `p08b`, `p09e`
  (`p04d-crew.mjs:54`): каждая новая карточка добавила новую копию стора — VERIFIED.
- Стоимость: одна read-only операция ~3,7–4,1 с, из них ~2,87 с —
  `p09e_research_catalog.load_catalog`, заново читающий пины (`tools/p09e_source_pins.json`:
  426 источников, по профилю — 423 packed XML) при каждом запуске. OBSERVED профилем
  родительской сессии 2026-10-20; в репозитории подтверждено формулировкой «каталог
  ~2,9 с из ~4 с» ([FULL_TEST_20261020](FULL_TEST_20261020.md):145-148). Отдельный
  evidence-файл профиля в репозитории — нет.
- Следствие (INFERRED): пропускная способность всех доменных операций сервера ≈ 2 / 4 с
  = **~0,5 оп/с**; медленный старт bridge под нагрузкой — причина единственного FAIL
  gate `p08b_restart_cas_composition02` (FULL_TEST_20261020.md:142-148).

## Данные и владение

| Данные | Хранилище | Писатель | Статус |
|---|---|---|---|
| Пользователи, пароли | SQLite identity DB | `server/identity` (Node) | VERIFIED, bridge читает read-only (02_ARCHITECTURE:98-104) |
| Игровой профиль, лимиты | SQLite game DB (`game_profiles`, `game_meta`) | bridge, `node:sqlite` (`game-adapter.mjs:3,123,156-169`) | VERIFIED |
| Инвентарь, исследования, экипаж, БК, допуск, итоги | SQLite (13 Python-модулей с `sqlite3`) | порождённый Python-процесс, `BEGIN IMMEDIATE` (`p09e_research_store.py:435`, `p04d_crew_store.py:126`) | VERIFIED |
| Состояние боя | память шлюза (`World`) | цикл шлюза | VERIFIED |
| Позы/контакты | память physics worker | Jolt-сцена | VERIFIED |
| Каталог клиента | pinned XML клиента, парсится на запрос | — | VERIFIED |

Писатель SQLite формально один (сериализация `BEGIN IMMEDIATE` + максимум 2 процесса),
но это **много короткоживущих процессов на один файл**, а не один владелец. Схема
ограничена историей карточек: `CHECK(native_id BETWEEN 1 AND 16)` для экипажа
(`tools/p04h_crew_store.py:178`, повторено в `p04i:247`, `p04j:292`) — VERIFIED.

## Дублированные контракты (машины/снаряды/экипаж)

| Слой | Где | Что знает |
|---|---|---|
| Клиент, кнопка «В бой» | `client_patch/map_drive_client.py:26` `PROFILE13_VEHICLES` | MS-1, ИС-7, + пул по compact descriptor |
| Клиент, UI экипажа/БК | `client_patch/p04h_crew_ui.py:24-28` `VEHICLES={1,2}`, `MAX_TANKMEN=16` (то же `p04i:26`, `p04j:25`, `p04k:29`) | только MS-1/ИС-7 |
| Bridge, допуск mixed | `web/src/p06t-mixed.mjs:24` `TYPES` | ms1/is7 + пул (комментарий: «mirror gateway vehicle_profile/p06t_device_caps и tools/p04m_pool_store.SHELL_ROWS») |
| Bridge, пул | `web/src/p04m-pool.mjs:27` `TYPES` | 5 машин, роли, ёмкость |
| Python | `tools/p06t_mixed_store.py:173` `freeze_mixed`, `tools/p04m_pool_store.py` | допуск, раскладка БК |
| Шлюз | `shared/vehicle_profile.rs:7` `enum VehicleKind` (7 видов), `p06t_device_caps.rs`, `*.json` политики | физика/броня/снаряды |
| Физика | `server/physics/Profiles/{stock,extended}-definitions.json` | параметры ходовой |

2026-10-20 купленный Т-34 прошёл до боя только после правки **четырёх** слоёв по
очереди: клиент `PROFILE13_VEHICLES` (`6235ddb`), порядок мест (`30f5765`), bridge
`p06t-mixed.mjs` `TYPES` (`ad0cd1e`), Python `freeze_mixed` + шлюз `parse_frozen`
([FULL_TEST_20261020](FULL_TEST_20261020.md):46-62) — VERIFIED. Каждый новый тип
машины сегодня — правка кода на 4 языках; сверки «все слои согласны» нет.

## Жёсткие пределы (сводка)

| Предел | Значение | Источник |
|---|---|---|
| Арен на процесс шлюза | 1 | `shared/server.rs:1297` |
| Сессий на процесс | 2..6 (бой) / 24 (тренировка) | `server.rs:1284`, `identity.rs:307`, `training/domain.rs:11` |
| Машин в арене | 6 (типы), 2 в legacy drive | `model.rs:7-8` |
| Одновременных входов | 1, без очереди, отказ 73 | `server.rs:1453-1460` |
| Время входа | 10,6–11 с (окно клиента ~17 с) | OBSERVED, ветка pending-login-queue |
| Одновременных доменных операций | 2 на весь сервер | `p04d-crew.mjs:68-70` |
| Задержка доменной операции | ~4 с (из них ~2,9 с каталог) | OBSERVED / FULL_TEST_20261020.md:146 |
| Танкистов на аккаунт за всё время | 16 | `p04h_crew_store.py:178` |
| Частота мира | 10 Гц | `model.rs:10` |
| Адреса | только loopback | SOURCE_LAYOUT, NET-02 не сделан |

## Неизвестно (UNKNOWN)

- CPU-мс на шаг одной арены и Jolt-сцены на 30 машин; RSS процесса шлюза и физики.
- Трафик/PPS на игрока в бою (оценки [CAPACITY_1000_CCU](CAPACITY_1000_CCU.md) — допущения).
- Причина пауз цикла шлюза; поведение клиента #717 при переносе base-канала на другой
  адрес посреди сессии (нужно для будущего разнесения по машинам).
- Сколько времени займёт identity-job без порождения процессов (после карточки bridge).
