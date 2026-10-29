# RES-30 — итоги, терминал, потери и late results для боёв до 30 машин

Ветка `codex/res-30-roster-30` (worktree-ветка `claude/res-30-roster-30-a64a3e`) на main `6f3882a` (с BOT-01). Карточка разрешена владельцем 2026-10-28 (после SPAWN-15/BOT-01).

## Цель

Бой 7..30 машин (`MAX_ACTORS = 30`, SPAWN-15) должен записывать итог, терминал выхода игрока, loss-событие
(подрыв БК) и late results так же, как бой 2..6. Сегодня любой бой > 6 мест падает в `contain_battle_failure`
(шлюз) или отвергается Domain (`P06T terminal rejected`), машина может остаться «в бою».

## Исследование

| Факт | Источник | Статус |
|---|---|---|
| Клиент: 15 на команду | `arena_defs/_default_.xml` `maxPlayersInTeam=15` (ARENA-01) | VERIFIED |
| Потребители итога не ограничивают число участников | инертный разбор marshal (без импорта) `battle_results_shared.pyc` `9fc1ef0d…`, `battleresultscache.pyc` `8f818406…`, `battleresultswindow.pyc` `00a48371…`, `avatar.pyc` `c13cd58a…`: в коде итогов нет констант ростера (6/15/30), только `len`/`sorted`; `VehicleInteractionDetails` — `struct`, поля u16 (`65535`) и u32 | VERIFIED_STATIC (`local/evidence/20261028-res30-01/client-bounds.json`, скрипт `client_bounds.py`) |
| Окно итогов показывает 15 строк на команду | Scaleform-ресурсы не разбирались | INFERRED (клиент рассчитан на 15×15) |
| Компактный pickle итога для 30 участников < 32 КиБ | расчёт: 30 × (41 поле ≤ 5 байт) + игроки ≤ 65 байт + личные 81 поле + детали 24 × 30 | VERIFIED тестом (`res30_compact_result_for_thirty_fits_native_stream`) |
| Native 15×15 итог в окне клиента | — | NOT_RUN (стенд, владелец) |

Дизассемблер `py27_static` требует `local/vendor/cpython-2.7.3/opcode.py` — файл утрачен при чистке 2026-10-24,
поэтому чтение только констант/имён кода (достаточно для поиска границ), без инструкций.

## Где была граница 6

Шлюз (Rust):
- `lifecycle_wire.rs`: `MAX_PARTICIPANTS = 6` (DTO и `validate`), `kills ≤ 6`, детали `Bounded<Row,6>`/`Bounded<Target,6>`.
- `lifecycle_details.rs`: журналы проекции `shots/direct/pierced ≤ 960`, `damage ≤ 15360`, `splash ≤ 5760` (6 машин).
- `ammo_detonation.rs`: журнал подрыва БК — ростер 2..6, ≤ 6 событий, выстрел ≤ 960 (на стенде включён).
- `p06t_device_state.rs`: модульное попадание — атакующий слот < 6, выстрел ≤ 960.
- `profile13_v2.rs` `validate_terminal_json`: `roster_size ≤ 6`; `profile13_loss.rs` `LossEvent`: слоты < 6, выстрел ≤ 960.
- `late_results_capture.rs`: слот < 6, ≤ 6 ссылок, `releases[6]`, ростер 2..6, seal ≤ 32 КиБ.
- Бюджеты байт: JSON итога ≤ 32 КиБ (`profile13.rs`, `profile13_v2.rs`, `profile13_loss.rs`, `results_session.rs`,
  `from_json_p06t`), запросы с итогом ≤ 64 КиБ (`identity.rs`, `identity_loss.rs`, `bounded_json`), кадр Domain 72 КиБ.

Domain (Python): `p08c_battle_results.results_value` 2..6 строк, `kills ≤ 6`, 32/64 КиБ; `p06t_terminal` `roster_size 0..6`;
`p06t_ammo_loss_store` слоты 0..5, выстрел ≤ 960; `p08c_late_results` слот 0..5, ростер 2..6, seal 32 КиБ, запрос 64 КиБ;
`server/domain/protocol.py` кадр 72 КиБ.

Web (бридж без Domain, путь отката): `p06t-mixed.mjs` `roster_size 0..6`, итог 32 КиБ; `p06t-ammo-loss.mjs` слоты 0..5,
выстрел ≤ 960; `p08b-battle.mjs`/`game-adapter.mjs` итог 32 КиБ, тело 64 КиБ.

Не меняются (вне карточки, ≤ 6 по смыслу): owner-hold (`profile13_hold*`, `p08b_owner_hold*`, ms1/is7, 4 владельца),
списки сконфигурированных владельцев (`accounts ≤ 6`).

## Схема и бюджеты

Размер JSON итога (канонический, структурный максимум, тест `res30_result_json_budget_covers_structural_maximum`):
6 строк — 11,3 КБ, 30 строк — 207 КБ. Поэтому **схема итога остаётся `p08c-battle-results.v1` (те же поля), а бюджет
зависит от числа строк**:

| Строк | JSON итога | Запрос/ответ с итогом | Seal late results |
|---|---|---|---|
| 2..6 (как было) | ≤ 32 768 | прежние ≤ 65 536 проверяются содержимым | ≤ 32 768 |
| 7..30 (`roster30`) | ≤ 262 144 | ≤ 655 360 | ≤ 655 360 |

Записи 2..6 валидируются и хешируются байт-в-байт как прежде (тот же canonical, те же `results_sha256`), hash-pinned
векторы (`tests/fixtures/*vectors*.json`, `.gitattributes`) не меняются — новые проверки только новыми тестами.
Транспорт (кадр Domain, HTTP шлюза и бриджа, `bounded_json`) поднят до 655 360 + заголовок; содержимое отвергается
по бюджету своего числа строк. Таблицы SQLite (`p08c_result.results_json TEXT`) без ограничения длины — **миграция БД
не нужна**, `p08c_schema` не меняется.

Остальные пределы — от `MAX_ACTORS`/`MAX_BATTLE_SHOTS` (30 × 160 = 4800): kills ≤ 29, слоты 0..29, `roster_size 0..30`,
выстрел ≤ 4800, журнал подрыва ≤ 30 событий, журналы проекции × 5.

Боты BOT-01 (`bot01:<n>`, dbid ≥ `0x7F000000`) — обычные строки итога: Domain пишет только строку запрашивающего
владельца (`p08c_result` по `account_id`), по остальным участникам ничего в аккаунты не пишется (тест
`test_roster30_one_owner_and_29_rows_store_only_owner`). Late results с ботами остаются явно неподдержанными
(BOT-01: `late results capture unsupported`, бой не ломается) — у бота нет резерва/ссылки; это следующий шаг.

## Откат

Код: `git revert` merge-коммита. Данные: записи 7..30 строк читаются только новым кодом — старый шлюз/Domain отвергнет
их при повторном чтении (`INVALID_INPUT`/`CORRUPT_STORE`) у этих владельцев; перед стендом — копия `game.sqlite`
(Domain остановлен), откат — вернуть копию. Конфиг стенда не меняется.

## Проверки

- Rust: тесты `res30_*` (итог 1+29, kills/детали 30, терминал `roster_size 30`, loss-слоты 29, подрыв БК в 30-ростере,
  seal late results на 30 ссылок, бюджеты), полный набор шлюза против `9ae5862`.
- Python: `tests/test_res30_roster30.py` (итог/терминал/loss/late 7..30, 1+29 записывается и повторный query/ack без ошибок,
  старые 2..6 и > 30 отвергаются как прежде), полный набор против `9ae5862`.
- Web: `web/tests/res30-roster30.test.mjs`, полный набор против `9ae5862`.

## Итог

Ветка перенесена на main `6f3882a` (BOT-01 влит) — rebase без конфликтов. Коммиты: `781761e` (код и тесты), `2eb4de4` (старые тесты границы 6 → 30, тест World 30), `f7dcf11` (бои BOT-01 на 30 мест).

Реализовано по плану: все пределы итога/терминала/потерь/late results идут от `MAX_ACTORS = 30`; бюджет байт JSON
итога зависит от числа строк (2..6 — 32 768 как прежде, 7..30 — 262 144); носители одного журнала — 655 360
(HTTP шлюза и бриджа, кадр Domain `MAX_FRAME = 655360 + 8192` с обеих сторон, ledger'ы и ответы Domain);
seal late results 7..30 — 393 216. Разбор JSON итога в loss-пути — отдельный `bounded_result_json` (16 384 узла).

Старые тесты, закреплявшие прежнюю границу, переведены на новую (не скрыты): `p08c_personal_nested_bounds…` (31
строка), `p10b_loss_roster_N2_to6…` (+7, 30; отказ 31), `module_replays_are_idempotent…` (выстрел 4801),
`p06t_ammo_detonation_bounds…` (ростер 31), `test_canonical_utf8_duplicate_keys…` и web `request and response … poison`
(seal > 393 216), BOT-01 `bot01_results_keep_natives_exact…` (30 мест теперь строят полный итог).

### Тесты карточки

- Rust (`cargo test res30 bot01 …`): 32 PASS / 1 ignored — итог 1+29 и все ростеры 2..30, kills ≤ 29, 30 строк деталей,
  компактный итог 30 машин в 32 КиБ потока клиента (имена 48 байт), бюджеты по структурному максимуму, журнал
  подрыва 30 событий, проекция 4800 выстрелов, терминал `roster_size` 30 / killer 29, loss-событие слот 29 / выстрел 4800,
  **настоящий World на 30 машин** → итог + терминал владельца + запрос писателя (`res30_thirty_actor_world_…`),
  **бои BOT-01 на 30 мест (1 и 2 игрока + боты)** строят полный итог, боты — строки без аккаунта.
- Python (`tests/test_res30_roster30.py`): 7 PASS — 1 владелец + 29 строк в настоящем SQLite-хранилище: финиш,
  store, replay, **повторное открытие хранилища, query, ack, повтор ack без ошибок**, запись только по владельцу
  (`p08c_result` = 1 строка, `game_snapshot` без новых аккаунтов); ростеры 2..30, отказ 31; бюджеты 32/256 КиБ;
  структурный максимум 30×30 (≈207 КБ) в бюджете; терминал 30; loss-событие; vehicle_id/seal late results.
- Web (`web/tests/res30-roster30.test.mjs`): 2 PASS — loss-бридж: натуральный финиш 30 машин, слот подрыва 29,
  `roster_size` 30; бюджеты журнала/запроса.

### Сравнение наборов (один worktree, один `local/`, один cargo target `C:/wot091-res30-target`)

| Набор | Ветка | База `6f3882a` | FAIL-множества |
|---|---|---|---|
| gateway (`cargo test --no-fail-fast`) | 1701 / 83 / 12 ign | 1691 / 83 / 12 ign | равны |
| web (`node --test`) | 76 pass / 49 fail / 10 skip | 74 / 49 / 10 | равны |
| python (`unittest discover`) | 3274 тестов: 14 F / 184 E / 99 skip | 3267: 14 F / 184 E / 99 skip | равны (198 = 198) |

Логи: `local/test-runs/res30-compare-6f3882a/` (worktree `res-30-roster-30-a64a3e`); предыдущее сравнение против
`9ae5862` — `local/test-runs/res30-compare-9ae5862/` (gateway 1686/83/11 против 1676/83/11, web равны).
83 FAIL шлюза, web-FAIL и Python-ERROR (105 из них `reparse path forbidden` — junction-ссылки `local/` worktree) — окружение worktree (нет exe/стенда, нет `express`, удалённый Codex worktree), одинаковы на базе.

### Стек (найдено каноническим gate общей сборки `e78764b`)

`p10b_loss_composition09_actual_http_host` переполнял стек потока теста: `late_results_capture::Capture.releases`
и `Entry.owners` стали встроенными массивами `[_;30]` (`Capture` 4,2 → 20,9 КБ), а late-наблюдатель клонирует их по
значению на главном потоке шлюза (Windows: 1 МБ). Кадры debug по машинному коду (`__chkstk`), gate-exe → `7ddf07f`:
`register_world_inner` 267 096 → 6 472, `stage_finished_v2/_loss` 218 248 → 1 544, `deliver_training_finished_loss`
165 832 → 3 304, `poll_mixed` 90 392 → 9 128, `stage_install` 75 880 → 840. Исправлено: строки на куче
(`Box<[_]>`), без увеличения стека потока. Тесты: размеры `Capture` ≤ 512 / `Entry`, `Install` ≤ 1024;
late-путь (install/register/select) в потоке 256 КиБ (старый код переполнил бы); бой 30 мест (1 игрок + 29 ботов)
с итогом — в потоке 1 МБ (debug). Release `96743bb` против release `f1de7ba` (без RES-30): ни один кадр
итога/терминала/late не вырос (выросли лишь `World::enable_original_spotting` 2→34 КБ и `baseapp::encrypt`
0→12,5 КБ — инлайнинг, вне пути итога). Самые большие кадры главного цикла — прежние и одинаковые
(`serve_with_pool_policy` 343 КБ, `Host::poll` 159 → 141 КБ, `poll_with_native_start` 103 КБ); их сумма
по цепочке — существующий запас главного потока, отдельной карточкой. Composition09 в worktree не запускается
(контроллер отвергает junction-пути и сид из `D:/…/local`) — проверка только каноническим gate в D:.
Шлюз на `96743bb`: 1705 / 83 / 12 ign, множество FAIL равно базе `6f3882a`.

### Не проверено

- Native: окно итогов клиента с 30 строками, выход из боя 15×15 на стенде — NOT_RUN (владелец).
- Late results для боя с ботами — неподдержаны (guard BOT-01, бой не ломается); 7..30 связанных людей — только
  тестами границ (полного сценария с 30 настоящими резервами нет).
- Owner-hold (`profile13_hold*`, 4 владельца ms1/is7) оставлен ≤ 6.
- Канонический gate в `D:/WoT_9.1_Server` — NOT_RUN (родительская сессия).

## Шаги для стенда -11 (родительская сессия, с согласия владельца)

Миграция БД **не нужна** (схемы `p08c_schema`/`p06t_*` не меняются, `results_json TEXT` без ограничения длины).
Но шлюз, Domain и (если используется) бридж должны быть новыми **вместе**: кадр Domain вырос с 72 КиБ — старый
Domain отвергнет итог > 6 машин, итоги ≤ 6 работают при любой комбинации.

1. Канонический gate на вершине RES-30 в `D:/WoT_9.1_Server` (D: detached на SHA — Domain и бридж берут Python/JS отсюда),
   затем release: `python -B -X utf8 server/build.py gateway --release --cargo-temp-target --out local/build/server/gateway-res30-release-<sha>`.
2. Если клиенты запущены — спросить владельца. `services.ps1 stop`, затем `domain.ps1 stop`.
3. Копии: `game.sqlite` → `game.before-res30.sqlite` (Domain остановлен), `gateway.json` → `gateway.before-res30.json`,
   `services.ps1` → `services.before-res30.ps1`.
4. В `services.ps1` — новый exe. Для 15×15 в `gateway.json`: `"battle_players": 30`, `bots.human_places` = число
   клиентов (остальное как этап BOT-01); карта — Прохоровка (Малиновка 30: пики шага ≈ 90 мс, SPAWN-15).
5. Старт Domain, затем services. Проверка: бой 1 игрок + 29 ботов до конца → окно итогов (30 строк), выход в ангар,
   машина не «в бою», повторный вход; второй бой — выход в середине боя (терминал manual_leave) и подрыв БК.
   В логах нет `contain_battle_failure`/`P06T terminal rejected`.
6. Откат: старый exe/`services.before-res30.ps1`/`gateway.before-res30.json`, `game.before-res30.sqlite` на место,
   D: на прежний SHA. Записи итогов 7..30 строк, сделанные новым кодом, старый код читать не будет — поэтому копия БД.
