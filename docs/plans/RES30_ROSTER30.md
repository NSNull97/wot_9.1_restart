# RES-30 — итоги, терминал, потери и late results для боёв до 30 машин

Ветка `codex/res-30-roster-30` на main `9ae5862`. Карточка разрешена владельцем 2026-10-28 (после SPAWN-15/BOT-01).

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

(заполняется после реализации)
