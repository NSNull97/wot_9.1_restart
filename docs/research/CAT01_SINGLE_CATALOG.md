# CAT-01: единый каталог машин/снарядов/экипажа/допуска (2026-10-20)

Ветка `codex/cat-01-single-catalog` от main `2b835b7`. План — [CAT01_SINGLE_CATALOG](../plans/CAT01_SINGLE_CATALOG.md),
решение — ADR-002 «Единый источник контрактов». Native-приёмка — владелец (NOT_RUN).

## Что сделано

- `tools/catalog_build.py` — одна утилита: `build --original <клиент>` пересобирает
  `config/catalog/catalog.v1.json` и четыре генерации; `verify-source` сверяет с клиентом;
  `check` (без клиента) сверяет генерации с закоммиченным каталогом.
- Вход: закреплённые ресурсы клиента #717 через существующие ограниченные читатели
  (`p09e_research_catalog.load_catalog`, ussr `guns.xml`/`shells.xml` по пинам P09C,
  `p06t_device_source_caps.json` по SHA) + `config/catalog/server_profiles.v1.json`
  (вид, `battle_admission`, legacy-инвентарь, UI-подсказки клиента). Код клиента не исполняется.
- SHA-256 каталога — по точным байтам файла (канонический JSON + LF):
  **`a6bd44f4169221e4be301e0de7fb9ce390602383e42abc34deb78dabbd3a8e3b`**; research-каталог
  клиента `b6baecd2…`. Пять видов: ms1, is7 (`always`), t26, t34, t3485 (`zero_economy_policy`).
- Генерации с тем же хешем: Rust `server/gateway/src/shared/vehicle_catalog.rs`, Python
  `tools/catalog_v1_data.py` (+ доступ `tools/catalog_v1.py`), JS `web/src/catalog-v1.mjs`,
  Py2.7 `client_patch/catalog_v1_hints.py` (только UI-подсказки).

## Факты из клиента (VERIFIED по пинам, пересборка = закоммиченный файл)

Для пяти видов из клиента выведены и совпали со всеми прежними списками: compact ID машины
и штатных модулей, дескриптор (и его SHA для клиента), HP корпуса+башни, `maxAmmo` штатного
орудия (96/30/160/77/68), места и роли экипажа в порядке XML, упорядоченные снаряды
штатного орудия (`shared`-shots, id/kind из `shells.xml`, compact = `id<<8 | nation<<4 | 10`).

## Флаги (по умолчанию выключены; откат — убрать флаг)

| Слой | Флаг | Что читает из каталога |
|---|---|---|
| шлюз | `"catalog":{"version":1,"sha256":…}` в gateway.json (только mixed profile13) | `profile13_v2::parse_frozen`: вид, допуск, legacy-инвентарь, суффиксы снарядов; факты сверяются с боевым профилем |
| bridge | опция `catalog` того же вида (требует `mixed_service`) | `p06t-mixed.mjs` TYPES, `p04m-pool.mjs` TYPES; передаёт `--catalog-sha256` воркеру |
| Python | `p08b_battle_service.py --catalog-sha256` (только `--mixed-ammo`) | `StockRegistry` пины, `inventory_id`, `freeze_mixed`/`_mixed_reservation` допуск, `SHELL_ROWS` |
| клиент | `interactive_client.py prepare --catalog-v1` (только profile13) | `map_drive_client` таблица кнопки «В бой» |

Чужой хеш — отказ запуска (шлюз: конфиг; bridge: исключение конфигурации; Python: `parser.error`).
Совпадение прежних списков с каталогом проверяется в обоих режимах; расхождение —
`CAT01_CATALOG_DISAGREES` / «catalog disagrees with battle profile», а не тихая подмена.

## Проверки (реально выполнены)

- `tools/catalog_build.py build|check` PASS; `tests/test_catalog_v1.py` 16/16 PASS
  (контракт хеша/набора всех генераций, равенство прежним спискам Python/клиента/P09C/SPECS/caps,
  допуск как данные, пересборка из клиента, `StockRegistry` одинаков в обоих режимах).
- Те же сторы в двух режимах (`p04m_stock_registry`, `p04m_pool_store`, `p06t_mixed_store`,
  `p04m_pool_crew`, `full_test_stand`): legacy 35 run / 0 fail / 1 skip, catalog 35 / 0 / 1.
- Rust (инкрементально, вне канонического gate): `vehicle_catalog` 4/4, `cat01` конфиг 1/1,
  `profile13_v2091` 3/3. JS: `catalog-v1.test.mjs` 5/5 (включая 13 реальных P06T-векторов в режиме каталога).
- CPython 2.7.3: компиляция 43 файлов `client_patch`; `catalog_profile13_vehicles(hints) == PROFILE13_VEHICLES`.

## Не сделано / ограничения

- Канонический gate шлюза в основном checkout — см. STATUS (родительская сессия; стенд `-06` не трогался).
- Не переключены (сверены тестом): UI экипажа `p04g…p04k` и БК `p09d` клиента — карточка
  CREW-ANY; P10B `p10b-selection*.mjs`, hold `p08b-owner-hold.mjs`, воркеры P10B/P08C (ms1/is7) — MM-01/hold.
- Новый вид машины ещё требует: боевой профиль физики/брони/баллистики (Rust `VehicleKind`,
  `p06t_shell_data`, `p06t_device_caps`, physics JSON) и миграцию маркера `registry_sha256`
  в `p04m_schema`/пина bridge `POOL_REGISTRY_SHA256` (хеш реестра меняется с набором видов).
  Четыре слоя допуска больше не правятся; это — следующие узкие места (INFERRED: DOM-01/CREW-ANY).
- Каталог v1 — только ussr (пины `shells.xml` есть только для ussr); wt128/fv183 не входят
  (= `none`). 374 машины клиента в каталог не выгружаются — расширение под CREW-ANY.
- ADR называл `content/catalog`; выбран `config/catalog` из-за allowlist слияния.
