# BATTLE-ANY: боевой профиль любой машины каталога (этапы 1–2) — 2026-10-27

Ветка `codex/battle-any`, перенесена на main `75a9437` (после ARENA-01; исходно от `2da4baa`). План — [BATTLE_ANY](../plans/BATTLE_ANY.md).
Native-приёмка — владелец (NOT_RUN). Метки — как в AGENTS.

## Что сделано

- `tools/battle_any_profiles.py` — один генератор для штатной сборки **любой** из 374 машин
  каталога #717: `build --original C --out local/evidence/<новый>` (без `--update` отказывается менять
  закоммиченную таблицу), `check` (без клиента). Те же читатели и правила, что у закрытых P04M
  (`p04m_battle_profiles`), P06T снарядов (`p06t_shell_catalog`) и P06T физики (`p06t_extended_profiles`);
  рукописных `SPECS` нет. Байткод клиента читается как данные, не исполняется.
- `config/catalog/battle_profiles.v1.json` (канонический JSON + LF, 1 563 914 байт), SHA-256
  **`2a75cf8365e80b7f876f7f6b409503c8071734cf5a164fa8196fb8922d5e107e`**; генерация
  `tools/battle_any_data.py` держит этот хеш, `tools/battle_any.py` (`table/profile/readiness`)
  отказывается грузить другие байты. Таблица пинит каждый прочитанный файл клиента и каждый пакет
  (байты + SHA-256), а по каждой сгенерированной машине — SHA бандла геометрии/брони.
- Бандлы (`battle-any-source.v1`, компоненты в форме `p04m-battle-source.v1` + пины членов пакета и
  исходные колёса) — 246 файлов, 37 МБ, только в evidence (ресурсы клиента в git не кладутся).

## Факты (VERIFIED по пинам, пересборка = закоммиченный файл)

Для каждой машины: compact ID машины/модулей и дескриптор, HP корпус+башня, масса сборки, мощность,
скорости, повороты корпуса/башни/орудия, `maxAmmo`, перезарядка, сведение, разброс, барабан/очередь,
углы орудия (+ `extraPitchLimits`), горизонтальная наводка (`turretYawLimits`), обзор башни, экипаж,
позиции корпуса/башни/орудия, все снаряды штатного орудия (вид, калибр, урон, урон модулям,
пробитие 100/500 м, скорость, гравитация ×0,8², дальность, радиус фугаса, премиум-признак), сетки
коллизии (xyznuv и xyznuvtb, раскладка P06T vertex01) и броня материалов.

**Нация (VERIFIED, найдено этим запуском):** порядок наций оригинального `nations.pyc` —
ussr, germany, usa, **china, france, uk**, japan (та же проверка, что в P06T). Research-каталог P09E
(`p09e_research_catalog.NATIONS`) нумерует france=3, uk=4, china=5, поэтому его compact ID для
этих трёх наций **не совпадают** с клиентом (FV215b: каталог 9281, клиент/Rust 9297). Таблица строит
идентичность по оригинальному порядку и хранит `research_catalog_nation_id` и
`catalog_nation_correction_required` (true у 67 сгенерированных машин). Сам каталог не правится
(версионированная коррекция — отдельная карточка; P06T уже называла её). INFERRED: ангарные окна
CREW-ANY для china/france/uk опираются на значения каталога — native там не проверялся.

## Политики test_lab (INFERRED, явные)

Физика — та же `p06t-extended-six-support-v2`, что у wt/fv (`MAPPING` в таблице совпадает с
`extended-definitions.json`): бокс по AABB коллизии корпуса, шесть опор по `topRightCarryingPoint`,
радиус — равная пара групп `W_L/W_R`, иначе равная пара колёс `W_L0/W_R0`; огибающая — пределы
`server/physics/ExtendedVehicleProfiles.cs` (масса 1000..100000 кг, вперёд ≤ 20 м/с, тормоз ≤ 300000…).
Значение вне огибающей — отказ, не обрезка. Урон — нынешняя P06T single-plate на proxy AABB
(не перерабатывается). Нулевые по площади треугольники (точный ноль векторного произведения) —
перечисляются в `excluded_degenerate_triangle_ids` (150 у 44 машин); у ИС-7 правило даёт ровно
`[107, 157]` = `IS7_EXCLUDED_IDS` в `geometry.rs`, у т-26/т-34/т-34-85 — ни одного (их компоненты
совпадают с P04M).

## Решения по машинам

246 `generated`, 128 `refused`; ни одна строка не даёт допуск (`battle_admission=false`,
`readiness_code=BATTLE_PROFILE_UNSUPPORTED` — код, который понимают все парсеры).

| Отказ | Число | Почему |
|---|---:|---|
| `SPG_INDIRECT_FIRE_OUT_OF_SCOPE` | 52 | все SPG (напр. Объект 261): навесная стрельба и арт-прицел вне объёма |
| `SUPPORT_SOURCE_UNRESOLVED` | 37 | нет точно равной пары W_L/W_R или W_L0/W_R0 (часто L/R различаются в 6-м знаке, у B1 три группы W_R) |
| `AUTOMATIC_GUN_UNSUPPORTED` | 21 | `burst` или барабан > 6 (автопушки); `armament.rs` держит барабан ≤ 6 без очередей |
| `PHYSICS_ENVELOPE_EXCEEDED` | 8 | E-100, Jagdpanzer E 100, Maus, VK 72.01, KV-5 (> 100 т); M18, А-20, МТ-25 (72 км/ч > 20 м/с) |
| `COLLISION_SOURCE_UNSUPPORTED` | 8 | материал `turretRotator` (A-44), привязка model/visual (VK 45.02 P, Comet), броня вне общего читателя (Dicker Max, M10, T40, Об. 263, ИС) |
| `COLLISION_SOURCE_UNRESOLVED` | 1 | Т-50-2: коллизия башни — модель окружения `content/MilitaryEnvironment/…` |
| `MOUNTED_SHOT_OVERRIDE_UNSUPPORTED` | 1 | служебная `Observer` |

По классам сгенерировано: ЛТ 53/79, СТ 84/103, ТТ 48/65, ПТ-САУ 61/75, САУ 0/52.

**Частные случаи AGENTS (VERIFIED):** Waffenträger auf E 100 — штатное `_128mm_K44_2_L61`,
барабан 6 / 30 в мин (интервал 2 с), 60 снарядов, перезарядка 60 с; 150-мм `_150mm_Rohr_L38` не
штатное, ни одна строка его не профилирует, его собственный барабан в клиенте — 4. FV215b (183):
`_183mm_HESH` — пробитие 275/275, золото, только у `_183mm_AT_Gun` этой машины, compact 21082.
Waffenträger в таблице `generated` (тормоз 242 888 Н·м — внутри огибающей Extended, как в
`extended-definitions.json`).

## Проверки (реально выполнены)

- `python -B -X utf8 -m unittest tests.test_battle_any` — **18/18 PASS**, в т.ч. пересборка
  из клиента = закоммиченная таблица и SHA всех 246 бандлов; бандлы т-26/т-34/т-34-85 = P04M
  `local/evidence/20261016-p04m-source-import01` (компоненты, позиции); физика/handling/AABB =
  `stock-definitions.json` (3) и `extended-definitions.json` (2); факты = P04M `SPECS`; снаряды
  7 штатных орудий = `tests/fixtures/p06t-shell-catalog.json`; compact ID/HP/масса/обзор/БК/
  перезарядка/снаряд/дескриптор = `VehicleKind` в `vehicle_profile.rs` для всех семи; каталог v1 (5).
- Соседи: `tests.test_catalog_v1 tests.test_p04m_battle_profiles tests.test_p06t_shell_catalog
  tests.test_p04m_stock_registry tests.test_battle_any` — 49 run, 1 error, 1 skip. Error —
  `test_p06t_shell_catalog.OriginalShellCatalogTests` setUpClass: нет пинованного
  `local/vendor/cpython-2.7.3/opcode.py` (утрачен при чистке 2026-10-24; копия в
  `toolchains-py27-20261019` имеет другой SHA) — окружение, файл карточкой не тронут.
- Те же четыре соседних набора на чистом worktree базы `75a9437`: 32 run, та же одна ошибка
  (`test_p06t_shell_catalog` setUpClass) — FAIL-набор ветки равен базе.
- Gateway gate (Rust), physics (C#), web (JS) — **NOT_RUN**: `git diff 75a9437 -- server web client_patch`
  пуст, рантайм этой карточкой не изменён; канонический gate main `75a9437` (1737 PASS / 2 FAIL / 8 ignored)
  относится к ветке без изменений по построению.

Evidence: `local/evidence/20261027-battleany-final01/` (receipt, таблица, 246 бандлов, логи тестов) и
`local/evidence/20261027-battleany-rebase75a9437/` (повтор после переноса и база).

## Этап 2: шлюз читает сгенерированные машины (`84c621e`)

Разделы выше описывают этап 1 (таблица `2a75cf83…`, 246/128). Текущая таблица — `d965b809…`
(1 968 964 байт): **232 `generated`, 142 `refused`**. Отказы: SPG 52, опоры 35, автопушка 21,
снаряды (меньше трёх / неподдержанный вид) 13, огибающая физики 9, источник коллизии 7+1,
`AIM_ENVELOPE_UNSUPPORTED` 3, служебная 1. Изменение против этапа 1 — новые проверки этапа 2
(три стека снарядов, предел поворота, бандл ≤ 512 КБ = `geometry::MAX_BYTES`, огибающая наведения).

- Rust: `VehicleKind`, `Mount`, `ram_proof::Profile` и `scene_worker::Kind` получили вариант
  `Generated(id)`; данные — из `shared/generated_vehicles.rs`. Таблица и запись квалификации
  вшиты байтами и проверяются по SHA (`battle_any_pins.rs`, пишет генератор), разбор один раз и
  «всё или ничего»; `GeneratedId` выдаёт только проверенный реестр. Пять закрытых видов
  (ms1/is7/t26/t34/t3485) остаются рукописными ветками; WT/FV есть и как закрытые P06T виды, и как
  строки реестра — тест держит их равенство (дескриптор, compact ID, HP, БК, панель, перезарядка,
  обзор, масса, снаряд).
- Геометрия/броня — из бандла машины по SHA реестра (`Geometry::from_generated_source`,
  `Catalog::from_generated`): имена частей Hull/Turret_NN/Gun_NN, позиции = таблица, нулевые
  треугольники исключаются по списку источника. Устройства, места экипажа, огибающая наведения,
  снаряды и `effectsIndex` — из строки таблицы.
- C#: `GeneratedVehicleProfiles.cs` грузит `Profiles/generated-definitions.json`; воркер
  `--qualify-generated-profiles` квалифицирует каждую машину (биты инерции Jolt), запись —
  `config/catalog/battle_qualification.v1.json` `fc5877a0…`, 227 профилей (232 − 5 закрытых),
  DLL `9d980677…` (`local/build/server/physics-battleany-05`, Release, сборка без запуска боя).
- Сцена manifest2: сгенерированный вид принимается по метке реестра, его source profile читается
  по пинованному пути (у закрытых видов — вшитый ресурс).
- **Допуск не открыт**: `battle_admission()` по-прежнему только ms1/is7, P04M/P08B сторы и bridge
  виды из таблицы не берут — это этап 3.

**Найдено этим запуском (VERIFIED, тест):** на настоящей таблице реестр не собирался —
AMX 13 90 (`front 75°`, `back 105°`) и AMX M4 1945 (`front 120°`, `back 30°`) при переходе
0,4 рад дают `front + back + 2·transition > π`, что отвергает `SourceEnvelope::validate`;
сборка «всё или ничего» закрывала **все** сгенерированные виды, и 85 тестов падали. Как #717
разрешает перекрытие секторов — UNKNOWN, поэтому генератор отказывает этим машинам кодом
`AIM_ENVELOPE_UNSUPPORTED` по тому же правилу в f32 (`aim_envelope_supported`), без подгонки углов.

### Проверки этапа 2 (реально выполнены)

- `tools/battle_any_profiles.py build --original C:/WoT_0.9.1_RU_0717_original --out
  local/evidence/20261027-battleany-envelope01 --update` → `PASS_PINNED_SOURCE_EXPORT`, 232 бандла;
  `server/build.py physics --out local/build/server/physics-battleany-05` → `PASS_ISOLATED_BUILD`;
  `qualify --out local/evidence/20261027-battleany-qualify06` → `PASS_GENERATED_QUALIFIED` (227);
  `check` → PASS.
- `python -B -X utf8 -m unittest tests.test_battle_any` — 20 run, OK, 1 skip (нет P04M evidence
  `20261016-p04m-source-import01` после чистки 24.10).
- Rust `generated_vehicles` — 4/4 PASS: реестр 227 и отсутствие двух отказанных; WT барабан 6 /
  60 / пушка 23060; FV HESH 21082 HE 275/275 золото / пушка 13908; сгенерированные WT/FV = закрытые
  виды; порча байтов таблицы/квалификации и чужие байты отвергаются.
- Полный набор шлюза (инкрементальная цель на C:, не канонический gate): ветка в worktree
  1649 PASS / 94 FAIL / 8 ignored. База `75a9437` в worktree того же вида — 1449/290/8; **FAIL
  ветки ⊂ FAIL базы**, новых падений нет. База в `D:/WoT_9.1_Server` — 1730/9/8: 85 тестов с
  фикстурами требуют именно этот путь (`portable_test_fixtures.rs`), в worktree не сравнимы.
  Логи и списки — `local/evidence/20261027-battleany-s2tests01/` (+ `SHA256SUMS`).
- Канонический gate, native — **NOT_RUN**.

## Не сделано / ограничения

- **Цель карточки (бой на любой машине) не достигнута.** Шлюз и физика читают таблицу (этап 2),
  но допуск закрыт: этап 3 — Python-сторы (`NEW_KINDS`), JS bridge (`TYPES`), `battle_admission`
  по данным, клиентская кнопка «В бой»; этап 4 — native владельца. Живой бой на сгенерированной
  машине не запускался ни разу.
- AMX 13 90, AMX M4 1945 (+ одна уже отказанная) — `AIM_ENVELOPE_UNSUPPORTED` до исследования
  поведения клиента при перекрытии секторов наводки.
- Версионированная коррекция наций каталога P09E/CAT-01 для china/france/uk — отдельная карточка.
- Кандидат новой политики опор (L/R отличаются в 6-м знаке) — 37 машин; не вводилась без решения.
- Профилируется только штатная сборка; нештатные модули — нет.
