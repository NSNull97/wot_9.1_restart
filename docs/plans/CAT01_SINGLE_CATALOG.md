# CAT-01: единый каталог машин, снарядов, экипажа и допуска (план карточки)

Ветка `codex/cat-01-single-catalog` от main `2b835b7`. Шаг 3 [ARCH01_MIGRATION](ARCH01_MIGRATION.md),
ADR-002 «Единый источник контрактов». Удалить после слияния; факты — в research + STATUS.

## Цель

Один версионированный каталог с SHA-256, собранный одной утилитой из закреплённых
ресурсов клиента #717 (через `p09e_research_catalog.load_catalog`, read-only) и
серверных профилей; сгенерированные данные для Rust / Python 3 / JS / Python 2.7.
Допуск в бой — поле `battle_admission`. Потребители читают каталог **за флагом**;
старые списки остаются до приёмки владельца (откат = выключить флаг).

## Закрытые списки (инвентаризация, VERIFIED по файлу:строке на `2b835b7`)

| Слой | Где | Переключается в CAT-01 |
|---|---|---|
| клиент, «В бой» | `client_patch/map_drive_client.py:26` `PROFILE13_VEHICLES` | да, `--catalog-v1` установки |
| клиент, UI экипажа | `p04h_crew_ui.py:24-28`, `p04i:26-30`, `p04j:25-26`, `p04k:29-30`, `p04g:15` `ROLES` | нет — CREW-ANY (снимок `ms1_crew/is7_crew`); сверка тестом |
| клиент, UI БК | `p09d_ammo_ui.py:14` `MOUNTS` | нет — CREW-ANY; сверка тестом |
| bridge, допуск mixed | `web/src/p06t-mixed.mjs:24` `TYPES` | да, опция bridge `catalog` |
| bridge, пул | `web/src/p04m-pool.mjs:27` `TYPES` | да, та же опция |
| bridge, P10B/hold | `p10b-selection.mjs:43`, `p10b-selection-loss.mjs:45`, `p08b-owner-hold.mjs:34,42` (ms1/is7) | нет — MM-01/hold; записано как остаток |
| Python | `p04m_stock_registry.py:19-30` `NEW_KINDS`/`PINS`, `p04m_pool_store.py:22` `SHELL_ROWS`, `p06t_mixed_store.py:177,215` допуск, `p09c_ammo_catalog.py:71-91` | да, `--catalog-sha256` воркера |
| шлюз | `battle/profile13_v2.rs:67-101` `parse_frozen`, `shared/vehicle_profile.rs`, `shared/p06t_device_caps.rs` | `parse_frozen` — да, ключ конфигурации `catalog`; физика/броня — нет (боевой профиль) |

## Решения

- Каталог: `config/catalog/catalog.v1.json` (канонический JSON) + вход
  `config/catalog/server_profiles.v1.json`. ADR называл `content/catalog`; путь
  `config/` выбран из-за allowlist слияния (DEV_NOTES), отклонение записано.
- Из клиента выводятся и сверяются: compact ID машины и модулей, дескриптор
  (`p09e_research_projection.descriptor`), HP корпуса+башни, места/роли экипажа,
  `maxAmmo` штатного орудия, compact ID снарядов (`item_id<<8 | nation<<4 | 10`).
  Серверные поля (вид, допуск, legacy-инвентарь, суффиксы/семейства снарядов,
  пределы модулей) — из профилей; сверяются контрактным тестом со старыми списками.
- Охват v1: пять видов пула (ms1, is7, t26, t34, t3485). wt128/fv183 — только
  физическая квалификация без допуска, в каталог v1 не входят (= `none`).
- Флаги: шлюз `"catalog":{"version":1,"sha256":…}`, bridge-опция `catalog` того же
  вида (передаёт `--catalog-sha256` Python-воркеру боя), установка клиента
  `--catalog-v1`. Чужой хеш — отказ старта. Без флага — прежние списки.
- Не меняются: исторические характеристики, native-протокол, схема ёмкости экипажа,
  хеши политик (`DEFINITION_SHA256` и т. п. считаются от прежних списков).

## Проверки

- `python -B -X utf8 tools/catalog_build.py check` (генерация = закоммиченные байты, хеш);
  `verify-source --original <клиент>` (пересборка из клиента = каталог).
- `tests/test_catalog_v1.py` — контракт: один хеш и набор у всех генераторов; каталог =
  старые списки; допуск по полю данных; Python 2.7.3 компиляция client_patch.
- `web/tests/catalog-v1.test.mjs`; Rust `shared/catalog_v1_tests.rs` в каноническом gate.
- Native (владелец, NOT_RUN): стенд с флагами — купить машину пула, бой; окна ангара MS-1/ИС-7 без изменений.

Откат: убрать ключи `catalog` из конфигураций шлюза/bridge и переустановить клиента без `--catalog-v1`.
