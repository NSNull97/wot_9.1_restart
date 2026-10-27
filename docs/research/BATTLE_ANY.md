# BATTLE-ANY: боевой профиль любой машины каталога (этап 1) — 2026-10-27

Ветка `codex/battle-any` от main `2da4baa`. План — [BATTLE_ANY](../plans/BATTLE_ANY.md).
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
- Gateway gate (Rust), physics (C#), web (JS) — **NOT_RUN**: `git diff 2da4baa -- server web client_patch`
  пуст, рантайм этой карточкой не изменён, исполняемые файлы идентичны базе по построению.

Evidence: `local/evidence/20261027-battleany-final01/` (receipt, таблица, 246 бандлов, логи тестов).

## Не сделано / ограничения

- **Цель карточки (бой на любой машине) этим этапом не достигнута.** Ни один рантайм-слой не
  читает таблицу; открыть допуск сейчас = фальшивый успех. Что осталось — этапы 2–4 плана:
  Rust `VehicleKind` по данным (сейчас 7 вариантов, `match` в 75 файлах), геометрия/броня из бандлов,
  `Mount`/`armament` из таблицы, C# загрузка сгенерированных определений и квалификация native
  binding Jolt (биты инерции `ram_proof.rs`) по каждой машине, Python-сторы/JS bridge по таблице,
  клиентская кнопка «В бой». Native — владелец.
- Версионированная коррекция наций каталога P09E/CAT-01 для china/france/uk — отдельная карточка.
- Кандидат новой политики опор (L/R отличаются в 6-м знаке) — 37 машин; не вводилась без решения.
- Профилируется только штатная сборка; нештатные модули — нет.
