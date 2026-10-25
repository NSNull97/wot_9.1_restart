# CREW-ANY: экипаж и БК для любой машины каталога (план карточки)

Ветка `codex/crew-any` от main `4b46f7e`. Шаг 4 [ARCH01_MIGRATION](ARCH01_MIGRATION.md)
(после CAT-01). Пункты CREW-V2 и CREW-UI-POOL из [NEXT_AFTER_FULL_TEST](NEXT_AFTER_FULL_TEST.md).
Удалить после слияния; факты — в research + STATUS.

Статус: реализовано на ветке, проверки — [CREW_ANY](../research/CREW_ANY.md); native — владелец.

## Цель

1. Ёмкость экипажа аккаунта пула > 16 (контракт `p04m-pool-crew.v2`, 192),
   с версионируемой обратимой миграцией SQLite.
2. Клиентские окна экипажа (P04F–P04K) и БК (P09D) обслуживают любую машину
   каталога CAT-01 (сейчас ms1, is7, t26, t34, t3485) за явным флагом установки.
3. Сервер проверяет команды экипажа/БК по каталогу (роли мест, снаряды, ёмкость),
   а не по утверждениям клиента; новых закрытых списков машин не появляется.

## Закреплённые места (VERIFIED по файлу:строке на `4b46f7e`)

| Слой | Где | Что |
|---|---|---|
| Python | `tools/p04m_pool_crew.py:21,62-65,93,100-101,180,186` | `CAPACITY = 16`, паспорт `id ≤ 16`, `next_native_id ≤ 17`, `free = 16 - id` |
| Python | `tools/p04m_pool_store.py:136-137,296` | `LIMIT 17`, `CHECK(native_id BETWEEN 1 AND 16)` (`_rebuild_crew_tables`) |
| Python | `tools/p04h_crew_store.py:191-192` | `p04d_crew_meta` `next_native_id BETWEEN 4 AND 17`, `free_left BETWEEN 0 AND 13` |
| Python | `tools/p04m_pool_projection.py:110` | компаньон шлюза `crew_capacity=16` |
| bridge | `web/src/p04m-pool.mjs:145-147,152-156,224,245,256` | схема `p04m-pool-crew.v1`, `free ≤ 13`, `id 4..16`, `16 - id` |
| шлюз | `account/p04m_companion.rs:71,119,134,142`; `crew_dismissal.rs:22`, `crew_progression.rs:24` | `crew_capacity == 16`, `1..=16`, `16 - id`; увольнение/навык пула идут через проверку P04J (`≤ 16`) |
| клиент | `p04h:24-28`, `p04i:26-30`, `p04j:25-26`, `p04k:29,64-76,151,232,280-281,431` | `MAX_TANKMEN = 16`, `VEHICLES` по инвентарным 1/2, снимок `ms1_crew/is7_crew`, `berths 16`, `unlocked_vehicle_types=[3329,7169]` |
| клиент | `p09d_ammo_ui.py:14-17` | `MOUNTS` {3329, 7169} |

## Решения

- **Ёмкость 192.** Требование ≥ 192; ровно 192 держит все номера и остаток
  бесплатного найма (`192 - id`) в одном байте pickle `K` — кодеры шлюза/bridge
  не меняют форму. Места в казарме (`stats.berths`) остаются 16: клиент
  проверяет `berthsNeeded <= tankmenBerthsCount - незанятые`; 192 — пожизненный
  аллокатор аккаунта, 16 — одновременно незанятых.
- **Паспорт v2:** имя/фамилия/иконка `((n-1) mod 112)+1`, `((n-1) mod 1036)+1`,
  `((n-1) mod 30)+1` (границы `p04h_tankman_descriptor.CATALOG_BOUNDS`); для
  №1–16 совпадает с v1 байт в байт.
- **Маркер версии — отдельная таблица `p04m_crew_contract`.** Политика активации
  пула (`p04m_schema.policy_sha256`, `POOL_POLICY_SHA256` bridge/шлюза, конфиги
  стендов) не меняется. Версию выбирают данные: нет строки → v1; строка v2 →
  `CrewContractV2`. Миграция — команда с записью в журнал и ревизией +1 (как
  активация пула): пересоздание таблиц с `native_id BETWEEN 1 AND 192`,
  `next_native_id ≤ 193`, `free_left ≤ 189`, `free_left = 193 - next`.
  Откат — обратная команда; отказ, если выдан номер > 16.
- **Шлюз/bridge принимают v1 или v2 по данным** (пара политика экипажа +
  ёмкость в компаньоне/профиле); конфиг стенда не меняется.
- **Клиент:** флаг `prepare --crew-any` (требует `--catalog-v1`), настройка
  `enable_crew_any`. Один модуль `client_patch/crew_vehicles.py`: таблица
  обслуживаемых машин — из `catalog_v1_hints` (места, роли по местам, класс,
  тип, снаряды, ёмкость), сверенная с дескриптором машины клиента; граница
  номера танкиста 192. Флаг выключен → прежние `VEHICLES`/`MAX_TANKMEN`/снимок
  `ms1_crew/is7_crew`, байт-в-байт. Флаг включён → снимок `crews`/`vehicles` по
  инвентарным ID. Сценарии автоматических доказательств (`STEPS`) остаются
  MS-1/ИС-7 и при флаге явно недоступны.
- Генерация py2.7-подсказок дополняется ролями по местам (`crew_roles`) из того
  же `catalog.v1.json`; хеш каталога не меняется. Поле `client_ui` остаётся
  «покрыто прежним UI без флага».
- Не трогаем: стенд `local/stands/full-test-20261021-09`, клиенты
  `local/clients/p03f/*`, исходный клиент.

## Проверки

- Python: тесты контракта v2, сторов (режимы legacy и каталог), миграции v1→v2→v1
  на копии БД, отказ отката с номером > 16, 17-й…192-й найм, отказ 193-го.
- JS: `p04m-pool` v1/v2. Rust: компаньон v1/v2, увольнение/навык пула > 16.
- Клиент: Python 3 тесты модулей при флаге выкл./вкл.; CPython 2.7.3 компиляция.
- Шлюз изменён → канонический gate (чистое дерево, `--cargo-temp-target`);
  в worktree сравнение множества FAIL с базой `4b46f7e`.
- Native-приёмка 2026-10-24: T-26/P04M/profile13 бой PASS на стенде crew-any-native-t26-20261024-03; native UI CMD303 для T-26 PASS. Raw profile13 layout `[5,4609,3,0]` нормализуется gateway в внутренний `[3,4609,3,0]`; evidence: `local/stands/crew-any-native-t26-20261024-03/evidence-native-ui-cmd303-t26-20261024.json`.
- Native capacity boundary 2026-10-25: на изолированном стенде `crew-any-native-t26-capacity-20261025-01` настоящий native CMD303 принял 17-го T-26 tankman (`result=0`, `inventory_id=17`), `next_native_id 17→18`, `free_left 176→175`, `configuration_revision 16→17`; evidence: `local/stands/crew-any-native-t26-capacity-20261025-01/evidence-native-capacity-id17-20261025.json`. Это PASS только для boundary `#17`; native `#18..#192` и отказ `#193` остаются NOT_RUN.
- Native lifetime attempt 2026-10-25: login/hangar и Barracks list для B PASS/OBSERVED (`total=17`, `unassigned=2`), но original virtualized renderer pool остался `ready=false` (`p04k_barracks_renderers_pending`), поэтому `CMD303 #18` не отправлялся. Evidence: `local/stands/crew-any-native-t26-lifetime-20261025-01/evidence-native-lifetime-blocked-20261025.json`; `#18..#192` и `#193` остаются NOT_RUN до исправления UI renderer lifecycle.
- Native lifetime retry 2026-10-25 после tail-only renderer fix: `p04k_barracks_window_ready` PASS/OBSERVED, но selector input остановился после `updateNationDropdown`; `buyTankman`, `CMD303 #18`, lifetime `#18..#192` и отказ `#193` не достигнуты. Evidence: `local/stands/crew-any-native-t26-lifetime-fix-20261025-01/evidence-native-lifetime-fix-blocked-20261025.json`; DB unchanged.

## Откат

Клиент: переустановить без `--crew-any`. Сервер: `p04m_crew_v2.py rollback`
(если номера ≤ 16) или копия БД до миграции; код v1 остаётся по умолчанию.
