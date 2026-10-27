# BATTLE-ANY — бой на любой машине каталога 0.9.1

Ветка `codex/battle-any` от main `2da4baa`, перенесена на `75a9437` (ARENA-01). Основание: [ADR-002](../decisions/ADR_ARCH01_TARGET.md)
(единый источник контрактов), [CAT01](../research/CAT01_SINGLE_CATALOG.md), [CREW_ANY](../research/CREW_ANY.md),
[P04M_FIVE_PROFILES](../research/P04M_FIVE_PROFILES.md), P06T (урон/снаряды), P05 (ходовая).
Метки — как в AGENTS. Итог и доказательства — [BATTLE_ANY](../research/BATTLE_ANY.md).

## Что есть сейчас (VERIFIED, `2da4baa`)

Каждый слой держит **закрытый** список видов; данные машины вписаны руками и сверены пинами.

| Слой | Где перечислены виды / где отказ |
|---|---|
| Rust вид | `server/gateway/src/shared/vehicle_profile.rs:7` `enum VehicleKind` (7), `:30` `ALL` (5), `:46` `battle_admission` = только ms1/is7; HP/масса/обзор/БК/перезарядка/наведение/снаряд — `match` по виду (`:54-180`) |
| Rust геометрия/броня | `shared/geometry.rs:9-25` пины бандлов, `:60-66` `SourceSpec`; `shared/materials.rs:12,39-41,178` ID материалов |
| Rust снаряды/урон | `shared/p06t_shell_data.rs:8` `enum Mount` (8), `shared/p06t_device_caps.rs:6`, `battle/armament.rs` (`PROFILES[mount]`, барабан ≤ 6) |
| Rust физика | `drive/scene_worker.rs:79` `enum Kind` + `include_bytes!` профилей `drive/worker/*-qualified-profile.json`; `shared/ram_proof.rs:13` биты инерции Jolt по виду |
| Rust допуск | `battle/profile13_v2.rs:82-90` (`owner acceptance required/unknown kind`), `account/p04m_companion.rs:99-103,177` (`BATTLE_PROFILE_UNSUPPORTED`/`OWNER_ACCEPTANCE_REQUIRED`), `session.rs:1264` |
| C# физика | `server/physics/StockVehicleProfiles.cs:59,63` (ровно t26/t34/t3485), `ExtendedVehicleProfiles.cs:59` (ровно wt/fv); `Profiles/*.json` вшиты ресурсом ≤ 32 КБ |
| Python | `tools/p04m_stock_registry.py:19` `NEW_KINDS`, `:140,160,178,189`; `tools/p06t_mixed_store.py:177`; `tools/p06t_owned_store_v3.py:603`; `tools/p08b_battle_store.py:85,108`; `tools/p08b_owner_hold_store.py:341` |
| JS bridge | `web/src/p04m-pool.mjs:43` `TYPES`, `web/src/p06t-mixed.mjs` `TYPES` |
| Источники данных | `tools/p04m_battle_profiles.py` (`SPECS`, 3 вида, факты сверяются с руками вписанными), `tools/p06t_shell_catalog.py` (`MOUNTS`, 8 орудий), `tools/p06t_extended_profiles.py` (wt/fv физика) |

Readiness-коды, понимаемые всеми парсерами: `BATTLE_PROFILE_UNSUPPORTED`, `OWNER_ACCEPTANCE_REQUIRED`
(+ экипаж/БК). Новый код на проводе потребовал бы правки ~12 белых списков — не вводится; причина
отказа хранится в сгенерированной таблице и логах.

Пробник по всем 374 машинам клиента (OBSERVED, этот запуск): 52 SPG; 20 орудий с `burst` и 19 барабанов > 6
(автопушки); 150 стоковых орудий с ограничением горизонтальной наводки; 5 машин > 100 т (предел
лаборатории физики 1000..100000 кг); 3 машины ссылаются на коллизию вне своего пакета (Sexton I,
Type 59 Gold, Т-50-2); вершины `xyznuv` (933 компонента) и `xyznuvtb` (182, раскладка подтверждена
P06T vertex01).

## Решение

Один генератор `tools/battle_any_profiles.py` выводит боевой профиль **штатной сборки** любой машины
каталога из ресурсов #717 по тем же правилам, что P04M/P06T, но без рукописных `SPECS`:

1. `pin --original` — считает пины (байты+SHA-256) всех прочитанных файлов и членов пакетов и пишет
   `config/catalog/battle_any_source_pins.v1.json` (один раз; повтор = сверка).
2. `build --original --out local/evidence/<новый>` — проверяет все пины **до** разбора, пишет
   закрытую таблицу `config/catalog/battle_profiles.v1.json` (скалярные факты, проекция физики,
   набор снарядов, пины геометрии, решение о допуске) и полные бандлы геометрии/брони по машине
   (формы `p04m-battle-source.v1`) в evidence, с SHA каждого бандла в таблице.
3. `check` (без клиента) — сверяет канонические байты таблицы с её SHA и самосогласованность.

Факты (VERIFIED по пинам): идентичность (compact ID машины/модулей, дескриптор), HP корпус+башня,
масса сборки, мощность, скорости, поворот корпуса/башни/орудия, `maxAmmo`, `reloadTime`, `aimingTime`,
`shotDispersionRadius`, `clip`/`burst`, углы орудия, ограничение горизонтальной наводки, обзор башни
(`circularVisionRadius`), экипаж, позиции корпуса/башни/орудия, все снаряды штатного орудия
(вид, калибр, урон, урон модулям, пробитие 100/500 м, скорость, гравитация, дальность, радиус фугаса,
премиум-признак), сетки коллизии и броня материалов.

Политики test_lab (INFERRED, явно версионированы, не историческая физика): шесть опор и проекция
двигатель/тормоз — та же `p06t-extended-six-support-v2`, что у wt/fv; бокс корпуса по AABB коллизии;
модель урона — нынешняя P06T single-plate на proxy AABB (не перерабатывается: отдельная карточка).

### Обязательные частные случаи

- Waffenträger auf E 100: штатное 128-мм `_128mm_K44_2_L61` — барабан **6** (`clip count=6, rate=30`)
  из XML; 150-мм `_150mm_Rohr_L38` в клиенте 0.9.1 имеет `clip 4` — генератор читает ёмкость из
  монтажа конкретного орудия, 6 не переносится; тест держит оба значения.
- FV215b (183): премиум HESH `_183mm_HESH` — пробитие **275** мм номинально, привязано к
  `_183mm_AT_Gun` этой машины; тест сверяет по снаряду и орудию.
- SPG (52 машины, напр. Объект 261): навесная стрельба/артиллерийский прицел вне объёма —
  `refused: SPG_INDIRECT_FIRE_OUT_OF_SCOPE`, на проводе `BATTLE_PROFILE_UNSUPPORTED`.
- Автопушки (`burst`, барабан > 6): нынешний `armament.rs` держит барабан ≤ 6 и без очередей —
  `refused: AUTOMATIC_GUN_UNSUPPORTED`.
- Масса > 100 т, коллизия вне своего пакета, неизвестный формат сетки — отдельные коды отказа
  (`PHYSICS_ENVELOPE_EXCEEDED`, `COLLISION_SOURCE_UNRESOLVED`, `MESH_FORMAT_UNSUPPORTED`), без подстановок.
- Ограничение горизонтальной наводки: факт сохраняется; рантайм ПТ-САУ уже моделирует его у wt/fv
  (`SourceAim`). Машина допускается в таблице как `generated`, рантайм-допуск — после этапа 2.

### Регрессия (то, чем доказывается правильность генератора)

Для t26/t34/t3485 генератор должен дать те же факты, что `SPECS` P04M, и **побайтно** ту же
проекцию физики, что `server/physics/Profiles/stock-definitions.json` (физическая часть); для wt/fv —
те же физика/handling, что `extended-definitions.json`; снаряды восьми орудий — те же, что
`p06t_shell_catalog`; HP/БК/снаряд/обзор/перезарядка — те же, что `VehicleKind` в Rust для всех семи.
Сегодняшние пять видов во всех слоях не меняются (байт в байт; генератор их не перезаписывает).

## Этапы

1. **(сделано, `dfd5257`)** Генератор, пины, таблица, коды отказа, регрессия, Python-доступ
   `tools/battle_any.py` (`profile(vehicle_id)`, `readiness(vehicle_id)`), тесты.
   Допуск сгенерированных машин **остаётся закрытым** (`BATTLE_PROFILE_UNSUPPORTED`): ни один
   рантайм-слой ещё не умеет загрузить такой профиль, открыть допуск сейчас = фальшивый успех.
2. **(сделано, `fe9a03b`..`84c621e`)** Рантайм читает таблицу: Rust `VehicleKind::Generated(id)` с данными из сгенерированного модуля
   (как `vehicle_catalog.rs`), геометрия/броня из бандлов по SHA, `Mount` снарядов из таблицы;
   C# — загрузка сгенерированных определений; квалификация native binding Jolt (биты инерции) для
   каждой машины на закреплённой платформе. Итог и найденный отказ `AIM_ENVELOPE_UNSUPPORTED` —
   [исследование](../research/BATTLE_ANY.md#этап-2-шлюз-читает-сгенерированные-машины-84c621e).
3. Допуск по данным: Python-сторы и JS bridge берут виды из таблицы (вместо `NEW_KINDS`/`TYPES`),
   клиентская подсказка кнопки «В бой» из каталога; канонический Gateway gate против `75a9437`
   (в `D:/WoT_9.1_Server`: фикстурные тесты привязаны к этому пути).
4. Native (владелец): купить несколько новых машин, в т.ч. Waffenträger и FV215b, бой на каждой.

## Откат

Этап 1 только добавляет файлы (генератор, пины, таблица, доступ, тесты); рантайм их не читает.
Откат — удалить их / откатить коммиты ветки.
