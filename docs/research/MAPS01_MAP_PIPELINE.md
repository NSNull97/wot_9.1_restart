# MAPS-01 — конвейер экспорта карт и реестр карт

Карточка MAPS-01 (одобрена владельцем 2026-10-20), ветка `codex/maps-01-map-pipeline` от
main `2b835b7`. План — [MAPS01_MAP_PIPELINE](../plans/MAPS01_MAP_PIPELINE.md).
Evidence: `local/evidence/20261020-maps01/` (итоговый прогон `final01/`).
Native-приёмка владельцем — **NOT_RUN**.

## Что сделано

1. **`tools/map_package.py`** — один экспортёр «клиент → пакет карты». Обобщённый
   перенос принятых evidence-скриптов (`collect_surface`, `export_terrain_mesh`,
   `obstacle_read`, `export_projectile_obstacles`) без изменения арифметики и порядка
   экземпляров; фиксированные границы 12×12/64 стали проверяемыми параметрами карты.
   Пакет `<map>/`: `terrain/` (сетка высот, шахматная триангуляция `heightAt`),
   `physics/` (маска 18 — вход Jolt), `projectile/` (маска 128 + флаги треугольников),
   `arena.json` (границы, базы, точки спавна, точки захвата по типам боя),
   `surface.json`, `destructibles/static-index.json` и `inventory.json`, `package.json`
   (SHA-256 каждого файла, пины всех прочитанных пакетов клиента, `paths.xml`,
   `destructibles.xml`, `_list_.xml`, хеш экспортёра). Оригинал клиента только читается.
   Команды: `export`, `batch`, `report`, `verify`, `regression`, `compare-native`,
   `registry-entry`.
2. **Реестр карт как данные** — `server/contracts/map_registry.json`, вкомпилирован в
   gateway (`drive/map_profile.rs`, `include_str!`) и в физику (`EmbeddedResource`
   `MapDrive.MapRegistry`). `MapId` — индекс записи реестра, а не ветка enum;
   `MapId::Karelia`/`Prohorovka` — константы на первые две записи (порядок проверяется).
   Убраны все зашитые пары `01_karelia/05_prohorovka`: `world.rs`, `worker.rs`,
   `scene_worker.rs`, `terrain.rs` (сетка из профиля), `fragiles.rs` (диапазон чанков из
   профиля), `profile13_templates.rs` + `server.rs` (карта боя — поле `map` манифеста
   battle-profiles), `lifecycle.rs` (`Rules::for_map`: ctf-базы и длина раунда клиента),
   CLI integrated-lab, `Program.cs`, `BattleSceneInput.cs`, `CheckedInput.CatalogProfile`.
3. **Каталог разрушаемого для любой карты** — `destructible_catalog.py` /
   `tree_contact_catalog.py` / `compound_destructible_catalog.py` принимают пакет
   (`--package <dir> --static-index`). Принятый каталог Прохоровки сохраняет прежние
   границы; остальные карты — «generalized»-политика (пустое семейство допустимо,
   ≤ 2048 объектов, ≤ 144 area-контроллеров, незарегистрированные деревья / вне-u32
   здоровье / повтор ресурс+матрица в чанке — исключение объекта с причиной).
4. **`tools/map_physics_probe.py`** — оседание и езда настоящего Jolt-воркера на пакете
   карты; конфиг машины копируется из принятого без изменения коэффициентов.

## Факты (VERIFIED / OBSERVED / INFERRED / UNKNOWN)

- VERIFIED (44 `.pkg` клиента #717): все карты — чанк 100 м, без hole-членов; тайл высот
  64 (69×69, поле 2), у `06_ensk` — 32 (37×37); пространства 8×8…14×14 чанков;
  у `04_himmelsdorf`, `86_himmelsdorf_winter`, `99_himmelball` 19 крайних чанков без
  блока terrain (рельеф экспортируется по полному прямоугольнику чанков с terrain,
  игровая зона внутри; земля не выдумывается).
- VERIFIED (`paths.xml` клиента): ресурсы ищутся по упорядоченному списку первым
  совпадением (`res_mods/0.9.1` пуст, затем shared/misc/gui/shaders, пакеты карт, машин,
  `res`, `res_bw`). Экспортёр следует этому порядку и пишет пакет-источник каждого ресурса.
- VERIFIED: `.visual` может ссылаться на другой `.primitives` через `/primitivesName`
  (у Карелии/Прохоровки не встречается — регрессия это подтверждает).
- **VERIFIED (регрессия порта):** для `01_karelia` и `05_prohorovka` новый экспортёр даёт
  побайтно те же буферы рельефа, физики (маска 18) и снарядной геометрии (маска 128 +
  флаги), те же счётчики и тот же список экземпляров, что закреплены в рантайме
  (`map_package.py regression` PASS; `tests/test_map_package.py`). Экспорт детерминирован.
- **OBSERVED (native-индекс разрушаемого):** индекс элемента в чанке у клиента = порядок
  в XML чанка элементов `model`/`speedtree`, зарегистрированных как разрушаемые
  (ресурс в `destructibles.xml` или `model` с `destructibleState`). Совпадение имени и
  f32-матрицы — 100 % на трёх различных записанных native-экспортах: Карелия 11 чанков /
  329 элементов, Прохоровка 44 / 2156 и 119 / 3662 (`compare-native` PASS). Для других
  карт правило **INFERRED**; native-подтверждение новой карты — NOT_RUN (тот же пассивный
  probe `client_patch/destructible_catalog_probe.py` + `compare-native` его закроют).
- VERIFIED: каталог Прохоровки, собранный по статическому индексу, совпадает с принятым
  native-joined каталогом (`1dca4feb…`, 1038 объектов) во всех полях, кроме поля
  происхождения индекса; inventory `e7bb87e6…` и worker `41c0d9cc…` побайтно равны.
  Путь с native-экспортом по-прежнему выдаёт `1dca4feb…` побайтно.
- Каталог v7 теперь явно указывает источник индекса: либо `native_exports_sha256`, либо
  `native_index_source = {rule: static-chunk-order-v1, static_index_sha256,
  classification: INFERRED_STATIC_RULE_NATIVE_CONFIRMATION_NOT_RUN}`; смешение и иные
  значения gateway отвергает.
- UNKNOWN: точки спавна ctf в клиенте отсутствуют (серверные у оригинала). Для проверок
  — явная test_lab-политика `test_lab-ctf-base-spawn-terrain-plus-accepted-clearance-v1`
  (центр ctf-базы команды, высота рельефа + 1,11 м как у принятого спавна Прохоровки).
  Бой профиля 13 по-прежнему ставит обе команды в точку `spawn_origin` пула ± 4 м.
- UNKNOWN: коллизия единственной модели без секции `bsp2` (`07_lakeville`, яхта) —
  треугольников не даёт, перечислена в манифесте, не заменена халлом.

### `fallingAtoms` (столбы и т. п.) — исключены, контракт частично VERIFIED

- VERIFIED (байткод `destructiblescache.pyc`): `encodeFallenColumn(destrIndex, fallYaw,
  fallSpeed) = destrIndex<<8 | (int(64·(yaw+π)/2π) mod 64)<<2 | clamp(fallSpeed,0,3)`;
  `decodeFallenColumn` — обратная. `__readFallingAtom` читает `filename, health,
  kineticDamageCorrection, type, preferredTiltDirections, физ. параметры, эффекты`.
- VERIFIED (`areadestructibles.def`): клиентское свойство `fallenColumns: ARRAY<UINT16>`
  объявлено между `destroyedFragiles` и `fallenTrees`; `AreaDestructibles.set_fallenColumns`
  есть в клиенте. INFERRED: индекс свойства 0xa0 (соседи 0x9f/0xa1 закреплены P06N).
- UNKNOWN: правило сервера, когда и куда падает столб (порог урона/энергии, выбор yaw и
  скорости), смысл семи чисел `physicParams`. Поэтому реализация в рантайме не делается
  этой карточкой; семейство остаётся статическим препятствием с причиной.

## Доказательство на трёх картах

| Карта | Экспорт | Регрессия | Каталог | Физика (MS-1/ИС-7) | Gateway |
|---|---|---|---|---|---|
| 01_karelia | PASS | буферы = рантайм | static, 1376 объектов / 134 area (новая возможность; не принят) | принятый конфиг: вывод воркера побайтно = принятому | реестр = прежние пины (тест) |
| 05_prohorovka | PASS | буферы = рантайм | static = принятый 1038 (кроме поля источника) | принятый конфиг: побайтно = принятому | реестр = прежние пины (тест) |
| 02_malinovka | PASS | — (новая) | static, 1385 (989 деревьев, 391 забор, 5 фрагилов) / 129 area | ctf-база team1/team2: оседание, езда 6–45 м, остановка, 1–49 см над рельефом; у team2 путь 6–7 м — танк упирается в препятствие (INFERRED, визуально не проверено) | реальная загрузка рельефа, препятствий, каталога, проекции воркера, правил боя (тест) |

Исключения Малиновки по семействам: деревья без movement-треугольников 1322;
фрагилы (кандидаты-заборы) — смешанные/заменяющие материалы 266, неполный span 81,
не movement-материал 59, есть снарядная геометрия 26; projectile-фрагилы — 5 допущены;
`fallingAtoms` 18 и `structures` 79 — не реализованы (см. выше); `undefined` 124 —
статический мир.

## Пакетный отчёт по 44 картам

См. `local/evidence/20261020-maps01/final01/catalogs/report.json` и таблицу ниже
(обновляется командой `map_package.py report`).

| Карта | id | Сетка | Вердикт | Не проходит | Каталог |
|---|---|---|---|---|---|
| 00_tank_tutorial | 53 | 513, шаг 1.5625 | NEEDS_WORK | ctf_two_bases | 1141 / 57 area |
| 01_karelia | 1 | 769, шаг 1.5625 | READY_FOR_REGISTRY | — | 1376 / 134 area |
| 02_malinovka | 2 | 769, шаг 1.5625 | READY_FOR_REGISTRY | — | 1385 / 129 area |
| 03_campania | 27 | 513, шаг 1.5625 | READY_FOR_REGISTRY | — | 545 / 55 area |
| 04_himmelsdorf | 3 | 577, шаг 1.5625 | NEEDS_WORK | worker_physics_vertices | нет: source file bound |
| 05_prohorovka | 4 | 769, шаг 1.5625 | READY_FOR_REGISTRY | — | 1038 / 119 area |
| 06_ensk | 6 | 257, шаг 3.125 | NEEDS_WORK | worker_physics_vertices | нет: source file bound |
| 07_lakeville | 5 | 641, шаг 1.5625 | READY_FOR_REGISTRY | — | 988 / 89 area |
| 08_ruinberg | 20 | 641, шаг 1.5625 | NEEDS_WORK | worker_physics_vertices | нет: JSON node/depth bound |
| 10_hills | 9 | 641, шаг 1.5625 | READY_FOR_REGISTRY | — | 771 / 81 area |
| 11_murovanka | 7 | 641, шаг 1.5625 | READY_FOR_REGISTRY | — | 1493 / 93 area |
| 13_erlenberg | 8 | 769, шаг 1.5625 | READY_FOR_REGISTRY | — | 1053 / 128 area |
| 14_siegfried_line | 21 | 769, шаг 1.5625 | READY_FOR_REGISTRY | — | 1043 / 120 area |
| 15_komarin | 10 | 641, шаг 1.5625 | NEEDS_WORK | — | нет: P06R object count bound |
| 17_munchen | 28 | 513, шаг 1.5625 | NEEDS_WORK | worker_physics_vertices | 507 / 56 area |
| 18_cliff | 11 | 769, шаг 1.5625 | READY_FOR_REGISTRY | — | 1131 / 85 area |
| 19_monastery | 12 | 769, шаг 1.5625 | READY_FOR_REGISTRY | — | 1430 / 126 area |
| 22_slough | 22 | 769, шаг 1.5625 | READY_FOR_REGISTRY | — | 1408 / 129 area |
| 23_westfeld | 23 | 769, шаг 1.5625 | READY_FOR_REGISTRY | — | 1657 / 131 area |
| 28_desert | 13 | 769, шаг 1.5625 | READY_FOR_REGISTRY | — | 987 / 83 area |
| 29_el_hallouf | 24 | 769, шаг 1.5625 | READY_FOR_REGISTRY | — | 414 / 68 area |
| 31_airfield | 26 | 769, шаг 1.5625 | READY_FOR_REGISTRY | — | 929 / 77 area |
| 33_fjord | 16 | 769, шаг 1.5625 | NEEDS_WORK | — | нет: tree objects per chunk exceed native probe budget |
| 34_redshire | 17 | 769, шаг 1.5625 | READY_FOR_REGISTRY | — | 1231 / 134 area |
| 35_steppes | 14 | 769, шаг 1.5625 | READY_FOR_REGISTRY | — | 860 / 94 area |
| 36_fishing_bay | 18 | 769, шаг 1.5625 | READY_FOR_REGISTRY | — | 1089 / 128 area |
| 37_caucasus | 15 | 769, шаг 1.5625 | READY_FOR_REGISTRY | — | 1272 / 76 area |
| 38_mannerheim_line | 19 | 769, шаг 1.5625 | NEEDS_WORK | — | нет: bounded nonempty combined catalog |
| 39_crimea | 32 | 769, шаг 1.5625 | READY_FOR_REGISTRY | — | 1040 / 93 area |
| 43_north_america | 33 | 897, шаг 1.5625 | NEEDS_WORK | worker_terrain_triangles | 1719 / 127 area |
| 44_north_america | 31 | 769, шаг 1.5625 | READY_FOR_REGISTRY | — | 1158 / 124 area |
| 45_north_america | 34 | 769, шаг 1.5625 | READY_FOR_REGISTRY | — | 1172 / 125 area |
| 47_canada_a | — | — | BLOCKED_EXPORT | surface missing data or inconsistent seam | — |
| 51_asia | 44 | 897, шаг 1.5625 | NEEDS_WORK | worker_terrain_triangles | нет: native target chunk bound |
| 53_japan | 43 | 897, шаг 1.5625 | NEEDS_WORK | worker_terrain_triangles | 903 / 95 area |
| 60_asia_miao | 52 | 769, шаг 1.5625 | READY_FOR_REGISTRY | — | 905 / 113 area |
| 63_tundra | 55 | 641, шаг 1.5625 | NEEDS_WORK | — | нет: bounded nonempty combined catalog |
| 73_asia_korea | — | — | BLOCKED_EXPORT | map is not in the client arena list (_list_.xml): not playable in this build | — |
| 83_kharkiv | 60 | 897, шаг 1.5625 | NEEDS_WORK | worker_terrain_triangles, worker_physics_vertices | 1820 / 135 area |
| 84_winter | 56 | 769, шаг 1.5625 | READY_FOR_REGISTRY | — | 722 / 83 area |
| 85_winter | 50 | 897, шаг 1.5625 | NEEDS_WORK | worker_terrain_triangles | нет: P06R object count bound |
| 86_himmelsdorf_winter | 57 | 577, шаг 1.5625 | NEEDS_WORK | worker_physics_vertices | 379 / 50 area |
| 87_ruinberg_on_fire | 58 | 641, шаг 1.5625 | NEEDS_WORK | worker_physics_vertices | нет: source file bound |
| 99_himmelball | 61 | 577, шаг 1.5625 | NEEDS_WORK | ctf_two_bases | 89 / 12 area |

## Проверки

- `python -B -X utf8 -m unittest tests.test_map_package -v` — 12/12 PASS
  (регрессия буферов, равенство native-индексу, детерминизм, каталог Прохоровки,
  реестр, общий список заборов и правило индекса с gateway).
- Наборы `tests.test_destructible_catalog`, `test_compound_destructible_catalog`,
  `test_tree_contact_catalog`, `test_map_geometry`: тот же набор FAIL/ERROR, что на базе
  `2b835b7` в той же среде worktree (существующий долг окружения), новых падений нет.
- Gateway, полный набор в worktree (`server/build.py gateway --test --out local/build/server/maps01-full-final`):
  1414 PASS / 281 FAIL / 5 ignored; база `2b835b7` в той же среде (`local/tmp/maps01-base-2b835b7`):
  1410 / 281 / 5. Набор FAIL совпадает поимённо (среда worktree: фикстуры `local/server`,
  `web`, HTTP-композиции); новых падений нет, +4 новых теста PASS. Один старый тест
  (`profile13_templates_require_two_exact_homogeneous_source_profiles`) изменён: Карелия как
  карта battle-profiles теперь допустима, отвергается незарегистрированная карта.
- Физика: `server/build.py physics` PASS; `map_physics_probe.py` — см. таблицу.
- Канонический gate в `D:/WoT_9.1_Server` — NOT_RUN (тот checkout обслуживает стенд -06).

## Ограничения и откат

Реестр включает Карелию, Прохоровку и Малиновку; остальные READY-карты добавляются
командой `registry-entry` (пины из пакета) без правки кода. Экспорты и каталоги лежат в
ignored `local/`. Откат — не сливать ветку; Карелия/Прохоровка используют прежние пины и
пути; прежние evidence-экспорты не изменялись.
