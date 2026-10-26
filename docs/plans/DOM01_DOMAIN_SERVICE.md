# DOM-01 — долгоживущий Domain/Account service

Ветка `codex/dom-01-domain-service` от main `e4296af`. Основание:
[ADR-002](../decisions/ADR_ARCH01_TARGET.md) (Domain/Account, внутренний обмен),
[ARCH01_MIGRATION](ARCH01_MIGRATION.md) шаг 5, [текущее состояние](../research/ARCH01_CURRENT_STATE.md),
[FULL_TEST_BRIDGE_LATENCY](FULL_TEST_BRIDGE_LATENCY.md), [FULL_TEST_PER_ACCOUNT_LOGIN](FULL_TEST_PER_ACCOUNT_LOGIN.md).
Метки VERIFIED/OBSERVED/INFERRED/UNKNOWN — как в AGENTS.

## Что есть сейчас (VERIFIED, `e4296af`)

- Bridge на каждую операцию порождает `python -B -X utf8 tools/p08b_battle_service.py … <operation>`
  (`web/src/p04d-crew.mjs:72-101` `run`), запрос — stdin, ответ — канонический JSON в stdout.
  Очередь аккаунта — `createAccountLane(2)` (1 выполняется + 1 ждёт, `account-worker-lane.mjs:6-17`).
- Выбор скрипта и профиля — цепочка `p04d…p04k → p09e → p08b` (`p04d-crew.mjs:52-53`); для
  profile13 (battle задан) всегда `p08b_battle_service.py`, который сам выбирает класс стора по флагам
  `--mixed-ammo/--ammo-rack-loss/--owner-battle-hold` (`p08b_battle_service.py:73-78`):
  `PoolStore → MixedAmmoStore → AmmoLossStore → OwnerHoldStore`.
- Каждый запуск: `catalog_v1.activate`, `load_catalog`, `audit` клиента, открытие стора, одна операция.
- Шлюз ходит в bridge HTTP POST с Bearer-токеном через единственную точку
  `Config::post_with_budget` (`server/gateway/src/account/identity.rs:511`), пути
  `/internal/native/{ammo,crew,crew-*,research,battle,battle-results,profile,login,…}`.
- Идемпотентность уже есть в сторах: ledger по `command_key`, повтор → тот же итог с `replayed=true`
  (`tests/test_p08b_battle_store.py:322`).

## Решение

### 1. Процесс Domain (`server/domain/service.py`)

- Один процесс Python (стенд — Python 3.14), запускается отдельно от bridge, слушает **только**
  `127.0.0.1:<port>` (TCP, loopback). Конфиг `domain.json` (≤ 8 KiB, точные поля, пути без ссылок):
  `version=1`, `endpoint`, `secret_file`, `database`, `bundle`, `original_root`, `fixture_root`,
  опционально `mixed {shell_catalog, terminal_policy}`, `catalog_sha256`, `accounts[]`
  `{account_id, pool, mixed, ammo_loss, owner_hold}` (≤ 64), лимиты.
- Старт: проверка конфига → `catalog_v1.activate` (если задан) → **один** `load_catalog` и `audit` →
  чтение `game_profiles` для настроенных аккаунтов (только SELECT, native_database_id) → строка
  `{"event":"domain_ready",…}` в stdout. Каталог и проверка клиента — один раз на процесс
  (ADR-002); смена ресурсов клиента/каталога требует перезапуска (INFERRED приемлемо: пины те же).
- Исполнение операций — **тот же код**, что CLI: `main()` из `p08b_battle_service.py` выносится в
  `execute(context, operation, raw_request)`; CLI вызывает его же. Отсюда байтовая идентичность
  ответов (проверяется тестом, см. ниже). Стор открывается на запрос (как сейчас), SQLite-соединение
  живёт в пределах операции.
- Параллелизм: пул из `workers` потоков (по умолчанию 4). На аккаунт — очередь «1 выполняется + 1 ждёт»
  (как `createAccountLane(2)`), третий — `busy`. Разные аккаунты идут параллельно; запись в SQLite
  по-прежнему сериализуется `BEGIN IMMEDIATE`.
- Сторож: операция дольше бюджета (`activate` 60 с, прочие 15 с — больше `POOL_WORKER_TIMEOUT_MS=7 с`
  и окна шлюза 20 с не превышает) → лог + `os._exit(75)`: как `child.kill()` сегодня, незавершённая
  транзакция SQLite откатывается. Прервать поток Python нельзя — поэтому fail-closed процессом.
- Остановка: SIGINT/SIGTERM/закрытие stdin → не принимать новые, дождаться текущих (≤ 20 с), выход.

### 2. Протокол `wot091-domain.v1`

```text
frame   = u32 BE length (1..=73728) ‖ payload
payload = u16 BE header_length (1..=1024) ‖ header (ASCII JSON, уникальные ключи) ‖ body (raw bytes)
```

- Рукопожатие: сервер шлёт `{"schema","nonce"}` (32 случайных байта hex), клиент — `op="hello"`,
  `proof = hex HMAC-SHA256(secret, "wot091-domain.v1:" ‖ nonce)`; сравнение постоянного времени.
  Секрет — файл 43 символа base64url (как identity token). Без верного hello любой другой кадр →
  закрытие соединения.
- Запрос: header `{"schema":"wot091-domain.v1","id":u32,"op":str,"account_id":uuid,"key":str|null}`;
  body — **те же байты**, что сегодня уходят в HTTP POST / stdin воркера.
- Ответ: header `{"schema":…,"id":…,"status":200|400|403|404|503,"error":null|code}`; body при 200 —
  ровно stdout воркера без перевода строки (канонический JSON).
- `key` — ключ идемпотентности: для изменяющих операций обязателен и равен `body.command_key`,
  для чтений — `null`. Долговечная идемпотентность — ledger сторов (переживает рестарт Domain);
  кэша ответов в памяти нет, чтобы повтор давал тот же ответ, что сегодня (`replayed=true`).
- Ограничения: кадр ≤ 72 KiB, header ≤ 1 KiB и ≤ 8 полей, body по операции (4096 / 65536 и
  `json_value(nodes, depth=4)` — как в воркере), ≤ 16 соединений, на соединение ≤ 64 запроса/с,
  глобально ≤ 256 запросов/с, таймаут чтения кадра 5 с, простой соединения 30 с.
- Версионирование: `schema` в каждом заголовке; несовпадение → 400 и закрытие. Новая версия —
  новое имя схемы, старая поддерживается, пока её шлёт хоть один клиент.
- Ошибки: `invalid_request` (400), `forbidden` (403: аккаунт не настроен, чужой
  native_database_id, версия боевого запроса не того класса), `not_found` (404: операция выключена),
  `busy`/`rate_limited`/`unavailable` (503; исключение стора — `unavailable` + тип ошибки в stderr,
  без тела запроса). Совпадает с тем, что шлюз сегодня получает от bridge: любой не-200 → отказ.

### 3. Потребители

- **Шлюз** — флаг `"domain_service":{"version":1,"endpoint":"127.0.0.1:N","secret_file":"…"}` в
  gateway.json (файл секрета — внутри `local_root`). Требует `profile13_battle`; несовместим с
  `p08c_late_results` и `training_rooms` (их писатели остаются в bridge). При флаге `post_with_budget`
  для путей `ammo, crew, crew-transfer, crew-recruit-barracks, crew-dismiss, crew-learn, research,
  battle, battle-results` идёт кадром в Domain с теми же байтами тела, бюджетами ответа и
  дедлайном. `login`/`profile` остаются в bridge (identity, scrypt, проекция fixture).
  **Флаг не задан → код пути не меняется (откат).**
- **Bridge** — опция `"domain_service":{…}`: `run(operation, request)` из `p04d-crew.mjs` шлёт
  кадр вместо `spawn`. При старте `describe` от Domain сверяется с конфигурацией bridge по каждому
  аккаунту (pool/mixed/loss/hold, catalog sha); расхождение → bridge не стартует. С опцией bridge
  отказывается стартовать вместе с `late_result_service`, `room_selection*_service` (это отдельные
  порождаемые писатели) — так при включённом Domain он единственный писатель агрегатов.
  JS-проверки ответов bridge остаются на пути login/profile/website.

### 4. Цепочка версий сторов

Domain использует только последние классы profile13 (`PoolStore…OwnerHoldStore`) — те же, что bridge
уже порождает для profile13. Схема БД не меняется, миграция данных для единого процесса **не нужна**
(VERIFIED тестом: Domain на БД, созданной CLI-воркером, и наоборот). Скрипты `p04d…p04k`,
`p09e_research_service.py` остаются для флага «выкл.» и исторических профилей < 13; свёртка
иерархии классов в один модуль — отдельная карточка (рефакторинг без пользы для этой цели, риск
регрессий в 13 сторах). Исторические квитанции ledger воспроизводимы через Domain (тест повтора).

### 5. Замеры

`tools/domain_latency_bench.py`: для каждой операции (вход/fixture, overview, research, purchase,
установка модуля, экипаж, БК, бой admit/finish) — медиана N прогонов «воркер на запрос» против
«Domain», ответы сравниваются побайтно; БД — свежая копия на прогон (для изменяющих операций).
Evidence: `local/evidence/20261026-dom01-latency/`. Цель: read-only < 300 мс.

## Проверки

- Python: протокол (размер, глубина, поля, схема, hello/HMAC, rate), очередь аккаунта
  (busy на третьем), два аккаунта параллельно, повтор = тот же ответ, рестарт Domain → повтор
  из ledger, сторож, байтовое равенство ответов CLI и Domain на последовательности операций.
- Node: bridge c `domain_service` — `run` через кадр, отказ при расхождении `describe`,
  запрет сочетаний с late/selection.
- Rust: разбор конфига (флаг выкл. = прежний конфиг), кодек кадров, HMAC (вектор RFC 4231),
  обмен с поддельным Domain на loopback, сопоставление путей.
- Наборы: FAIL-набор head ⊆ FAIL-набор base `e4296af` в той же среде (Python, web, gateway).
- Native (владелец, NOT_RUN): полный ангарный сценарий + бой на пересобранном стенде с
  `domain_service` у шлюза и bridge.

## Откат

Убрать `domain_service` из gateway.json и bridge.json, остановить Domain — прежний путь
(HTTP → bridge → процесс на запрос). Данные и схема не меняются. Код — `git revert` коммитов карточки.

## Результат (2026-10-26, ветка на main `e61a385`)

Сделано по плану, с одним расширением: Domain владеет и записями late-owner'ов (`late_result_service`), иначе
текущие стенды не могли бы его включить. Тренировочные комнаты (`room_selection*`) — по-прежнему отказ.
Пункт 4: миграция не нужна (обоснование — [исследование](../research/DOM01_DOMAIN_SERVICE.md)).

### Замеры (OBSERVED, медиана 5 прогонов, Windows/Python 3.14; worker = процесс на запрос, Domain = новое соединение + операция)

| Операция | Сид тестов: worker → Domain | Стенд -10, аккаунт A (CAT-01): worker → Domain | Тяжёлый аккаунт (192/162 уволенных): worker → Domain |
|---|---|---|---|
| вход (fixture) | 1,09 с → 0,34 с | 1,11 → 0,38 | 2,79 → 0,74 |
| overview / pool-overview | 0,86 → 0,13 / 0,84 → 0,12 | 0,90 → 0,17 / 0,87 → 0,16 | 2,41 → 0,39 / 2,39 → 0,36 |
| исследование / покупка / установка модуля | 1,20 / 1,18 / 1,16 → 0,45 / 0,44 / 0,47 (приняты) | 0,99 → 0,27 (отклонены) | 2,69 → 0,68 (отклонены) |
| экипаж (казарма) | 1,09 → 0,36 (принят) | 1,12 → 0,38 (отклонён) | 3,00 → 1,02 (отклонён) |
| БК | 1,16 → 0,42 (принят) | 1,11 → 0,40 (отклонён) | 2,98 → 1,02 (отклонён) |
| бой run_open / admit / inspect / finish | 0,99 / 1,01 / 0,87 / 1,02 → 0,26 / 0,26 / 0,15 / 0,28 | inspect (late) 0,82 → 0,17 | inspect (late) 2,31 → 0,38 |
| итоги query / ack, late pending | 0,87 / 0,88 → 0,14 / 0,14 | query 0,81 → 0,17; pending 0,82 → 0,18 | 2,30 → 0,38; 2,32 → 0,38 |

Ответы Domain побайтно равны ответам воркера во всех строках. Цель «чтение < 300 мс» — **PASS** для сида и
аккаунта A стенда -10, **FAIL** для тяжёлого аккаунта (0,36–0,39 с; остаток — в исследовании).
Evidence: `local/evidence/20261026-dom01-latency/` (`seed-bench.json`, `stand10-account-a.json`,
`heavy-account-192.json`, `rehearsal-02.json`).

### Проверки

| Проверка | Статус |
|---|---|
| Python DOM-01 (12) + memo/tamper (2) | PASS |
| Node domain-client (8) | PASS |
| Rust domain (6) + interop с настоящим Python Domain (ignored, отдельно) | PASS |
| Наборы против main `e61a385` в этой среде: gateway 1659/62 vs 1653/62, web 131/84/37 vs 123/76/37, Python 3328 (7F/116E) vs 3314 (7F/119E) | FAIL-наборы head ⊆ main, новых нет |
| Канонический gate в `D:/WoT_9.1_Server` | NOT_RUN (не мой checkout; 60 из 62 — workspace-guard'ы worktree, 2 — `scene_worker::tests_p04m`) |
| Репетиция bridge без/с Domain на копии стенда CREW-ANY | PASS (14 запросов равны, конфиги восстановлены) |
| Native: полный ангарный сценарий + бой | NOT_RUN (владелец) |
