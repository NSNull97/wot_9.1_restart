# P04M — источник первого пула из пяти машин (#717)

2026-10-16. **READ-ONLY / VERIFIED_STATIC_SOURCE; реализация и native-приёмка NOT_RUN.**
Подготовлено отдельно от выполняемых P08C/P05C. Единственное изменение этого
исследования — этот документ. Оригинал, клиентские копии, БД, генераторы и runtime
не менялись; ресурсы из пакетов на диск не извлекались.

## Предлагаемый состав

**INFERRED, предложение для P04M:** оставить принятые MS-1/ИС-7 и импортировать
ровно stock **Т-26, Т-34, Т-34-85**. Это три обычных советских сборки, уже известных
P09E, с одним местом башни, без барабана и с обычным ББ. Их девять выбранных
collision-примитивов реально читаются существующим `geometry_spike.collision_mesh`.
Это уменьшает новый бинарный разбор. Не выбирать альтернативные орудия или
«топовые» модули без отдельной записи сборки.

КВ-1 также проверен как кандидат тяжёлого танка, но пока хуже для минимального
пути: все три stock collision-компонента имеют формат `xyznuvtb`, который
существующий декодер честно отвергает. Подробности ниже. Это не отсутствие
ресурсов и не основание подставлять геометрию ИС-7.

**Допуск:** у новых машин `battle_admission` остаётся **false** до отдельной
ручной проверки владельцем каждой машины, как требует IMPLEMENTATION_ORDER.
Наличие в каталоге, успешный импорт или реальные worker-тесты этот gate не заменяют.

## Проверенный источник и метод

Оригинал из `config/project.local.json`:
`C:/WoT_0.9.1_RU_0717_original`. Применены только чтение, SHA256,
`packed_xml.decode/walk`, существующий `load_catalog` и ограниченное чтение
конкретных ZIP members. `.pyc` клиента в этой работе не исполнялись и не
импортировались. Современные Tankopedia/Blitz/Lesta/другие патчи не использовались.

`p09e_research_catalog.load_catalog(original_root)` повторно проверил исходные
pin-файлы и вернул 374 машины; SHA256 каталога:
`b6baecd204444d1e894253fa6c19c61478993b8ae87c71373633989d3a8ee460`.
Все три предложенные машины имеют `acquisition_allowed=true`, одну позицию
башни и `battle_eligibility=UNSUPPORTED_UNTIL_EXACT_RUNTIME_PROFILE`.

Ниже пути относительно оригинала. Все hashes здесь **проверены чтением сейчас**.

| Файл | Байт | SHA256 |
|---|---:|---|
| `res/scripts/item_defs/vehicles/ussr/t-26.xml` | 11010 | `ade0230c2511d64ef38d7e3f7bb850ede2004e0f2f39648031d763a884cfe3f8` |
| `res/scripts/item_defs/vehicles/ussr/t-34.xml` | 11912 | `eb83065dace1ca39e93c225c319b3ab857d790f8ea34abcabeb58d6e7138183b` |
| `res/scripts/item_defs/vehicles/ussr/t-34-85.xml` | 18759 | `3b69621a659e3369eddaefd078e7a6d3dbc52f8271c2c3318839956d3021cb92` |
| `res/scripts/item_defs/vehicles/ussr/components/guns.xml` | 58493 | `889fe1564987566478c474ddfef21cbc7742d23bebd19f6a200c59bfafd7d87b` |
| `res/scripts/item_defs/vehicles/ussr/components/shells.xml` | 20468 | `ed301edbe07a72b04dc6c6d799bc563de55d0d1f26bd35798354a9f6769e7a96` |
| `res/scripts/item_defs/vehicles/ussr/components/engines.xml` | 16153 | `196e52561bd04d2d4e5838442f62704456f4b901627248e04b2c9bd37d32f60d` |
| `res/scripts/item_defs/vehicles/ussr/components/fueltanks.xml` | 457 | `1f182b76fceeabf2ff1d828cc5b2aea37b94585f78488bd2dd7c195f8862b013` |
| `res/scripts/item_defs/vehicles/ussr/components/radios.xml` | 3986 | `099292b8b5f5e250b2cd506419d18620f4f2504950776b54983bc303b2ca201a` |
| `res/packages/vehicles_russian.pkg` | 1182066680 | `c2e16aef6fe7a7e44e476e2cb96e009b9f4eb7edab55fda2861601ba783415aa` |

`common/vehicle.xml` повторно проверен:
`599ea82e48e98bf9a00c10256030097da31ce5d5889fa03737bc3b79230d256a`.
В нём `/miscParams[1]/projectileSpeedFactor[1] = 0.8`.
Для armor/material defaults дополнительно необходимы уже закреплённые
`ms1_contact_bundle.FILE_PINS`, `PACKAGE_PINS` и `KINDS_KEY`: общий
`vehicles.pyc`, `material_kinds.pyc`, `Vehicle.pyc` и
`misc.pkg!system/data/material_kinds.xml`. Их свежий полный повторный audit
для новых экспортов здесь **NOT_RUN**; исходные pins и readers уже существуют.

## Точные stock-сборки и боевые значения

**VERIFIED_STATIC.** Имена — исходные resource names. Порядок модулей для CD ниже:
шасси / двигатель / бак / радио / башня / орудие.

| Поле | Т-26 | Т-34 | Т-34-85 |
|---|---|---|---|
| Vehicle key P09E | `vehicle:ussr:T-26` | `vehicle:ussr:T-34` | `vehicle:ussr:T-34-85` |
| Type compact ID | 4609 | 1 | 2561 |
| Шасси | `T-26` | `T-34_mod_1941` | `T-34-85` |
| Двигатель | `T-26` | `V-2` | `V-2-34` |
| Бак / радио | `Small` / `_71-TK-1` | `Average` / `_9R` | `Average` / `_9R` |
| Башня | `T-26_cylindrical` | `T-34_mod_1940` | `T-34-85` |
| Орудие | `_37mm_B-3` | `_76mm_L-11` | `_76mm_S-54` |
| Модульные compact IDs | 9218 / 4869 / 51462 / 263 / 7683 / 4100 | 2 / 5 / 51974 / 775 / 3 / 4 | 5122 / 261 / 51974 / 775 / 4355 / 1540 |
| Plain descriptor hex | `011224001300c90001001e00100000` | `010000000000cb0003000000000000` | `010a14000100cb0003001100060000` |
| HP hull + выбранная turret | 120 + 30 = **150** | 320 + 80 = **400** | 536 + 134 = **670** |
| Сумма source mass, без оборудования | **9302 kg** | **27940 kg** | **32370 kg** |
| Power | 90 hp | 480 hp | 500 hp |
| Forward / reverse source km/h | 36 / 15 | 56 / 20 | 54 / 20 |
| Chassis / turret yaw deg/s | 50 / 44 | 37 / 40 | 36 / 46 |
| Shared gun rotation deg/s | 43.75 | 39.375 | 39.375 |
| Mounted reload / aiming s | 2.3 / 2.3 | 6 / 2.9 | 4.1 / 2.9 |
| Mounted maxAmmo | **160** | **77** | **68** |
| Mounted shotDispersionRadius | .46 | .51 | .41 |
| Mounted raw pitchLimits | `-25 8` | `-17 6` | `-22 7` |
| AP resource | `_37mm_UBR-160` | `_76mm_UBR-354A` | `_76mm_UBR-354MA` |
| AP compact ID / caliber | 1034 / 37 mm | 7178 / 76 mm | 7946 / 76 mm |
| AP damage / penetration pair | 36 / `40 33` | 110 / `68 62` | 115 / `125 115` |
| AP raw speed / speed × .8 m/s | 670 / 536 | 612 / 489.6 | 816 / 652.8 |

Для всех трёх AP исходные gravity9.81 и maxDistance720. Название shell нельзя
выводить из названия танка: Т-34 использует `_76mm_UBR-354A`, но его shot
скорость/пробитие отличаются от КВ-1 с тем же shell resource — читать mount's
`guns.xml/shared/<gun>/shots/<shell>`, а не переносить параметры другой пушки.
У трёх выбранных mounted gun нет локального `shots` override.

Mounted reload/maxAmmo/aiming читаются из
`/turrets0/<stock turret>/guns/<stock gun>` с разрешённым shared fallback,
как делает P09E `installable()`/`gun_parameters`. Например, для Т-34-85 mounted
4.1s/68 важнее shared S-54 4.571428...s/52; для Т-26 mounted2.3s/160 важнее
shared B-3 2.285714...s/84. Не копировать shared defaults поверх mount.

Т-34 имеет настоящий vehicle index0, поэтому type CD1 и почти нулевые module
indices/descriptor — нормальные данные #717. Это не пустая машина. Descriptor
получен существующим `p09e_research_projection.descriptor` из проверенного каталога.

Source crew по слотам:

- Т-26: commander+radioman, driver, gunner+loader — три настоящих члена.
- Т-34: commander+gunner, radioman, driver, loader — четыре.
- Т-34-85: commander, gunner, radioman, driver, loader — пять.

P04M не даёт права создавать фальшивые crew/ammo записи. Старый P04G roster
ограничен native inventory1/2; покупка новой машины P09E сама экипаж не выдаёт.

## Геометрия, броня и движение

Все paths ниже — точные ZIP members в проверенном `vehicles_russian.pkg`.
Префикс `vehicles/russian/`, далее указанный vehicle folder и `/collision/`.
Выбранные parts имеют `.model`, `.visual`, `.primitives`; всего прочитано 27
маленьких members. Никакой `normal/lod0` не подставляется вместо collision.

| Folder / part | Primitives bytes | Vertices / triangles | SHA256 primitives |
|---|---:|---:|---|
| `R09_T-26/Hull` | 15120 | 211 / 142 | `9801de66b588d46233ca89878a89b2d77cb342638f0acb181eb163361f506072` |
| `R09_T-26/Turret_01` | 18464 | 228 / 190 | `301bebeb30a526247a02a9c445a99ca56237043b6576325112ea8c7be5b5d019` |
| `R09_T-26/Gun_02` | 14900 | 217 / 128 | `7757345d1c4b9d4e4536b616e636d4f965de84d98dd8a5dca273c18a9cd3c82a` |
| `R04_T-34/Hull` | 18220 | 266 / 172 | `9749e22f38d55d7df1ecf5df9c9bcb3c540d737841b37a742f006e96b28bf0c3` |
| `R04_T-34/Turret_01` | 27844 | 382 / 264 | `bb39b0b18d07180912bbc6106d0ced50f7a468ad6587bc3ef63fd432f6bee51b` |
| `R04_T-34/Gun_01` | 18412 | 195 / 181 | `1d43878445526f453a34b8b9685c02095294f15b9751c438faf6014c6abd35af` |
| `R07_T-34-85/Hull` | 20892 | 301 / 198 | `5a735d6651370c035e63029e9a0e42f17f23c496f0992135f7abc20cda33119f` |
| `R07_T-34-85/Turret_01` | 44280 | 575 / 429 | `a5f9f6db6078fa68500179579cdf0aad20f4d718f69728b297e3511515db3206` |
| `R07_T-34-85/Gun_01` | 16668 | 199 / 160 | `2860d9e3a391ffcdc6d32aae865c16cd036acc36b55834204e1bb1ebc2052b2c` |

**VERIFIED_STATIC:** все девять meshes — поддерживаемый `xyznuv`,32-byte stride;
в каждом отдельно проверены все triangles на точную нулевую площадь: **0**.
Нельзя переносить исключения IS-7 Hull107/157 на другие модели.

`visual.boundingBox` и фактический vertex AABB — разные source facts. Они
отличаются у всех трёх stock turret, а также Hull Т-26. Пример: Т-26 turret
visual minY−.462558, mesh minY0; Т-34 turret visual minY−.381615,
mesh minY−.000115773. Native hitTester bbox для них **UNKNOWN / NOT_RUN**.
Нельзя «исправлять» vertices или чужой bbox ради равенства; хранить оба исходных
набора отдельно, как допускает текущий IS-7 путь component bounds.

Точные origin paths: `chassis/<chassis>/hullPosition`,
`hull/turretPositions/turret`, `turrets0/<turret>/gunPosition`.

| Параметр | Т-26 | Т-34 | Т-34-85 |
|---|---|---|---|
| Hull position | `[0,.978368,-.10165]` | `[-.012,.7449,0]` | `[0,.9230780005,0]` |
| Turret position относительно hull | `[-.1449889988,.5241559744,.0537180007]` | `[.0182930008,.7911549807,.6135830283]` | `[.00155699998,.6163769960,.6951969862]` |
| Gun position относительно turret | `[.0153810000,.3696619868,.6166329980]` | `[-.0170920007,.3186540008,.6391170025]` | `[-.001609,.456677,1.02193]` |
| topRightCarryingPoint | `[1.02922,1.36129]` | `[1.22718,1.88347]` | `[1.24521,1.85515]` |
| brakeForce | 33000 | 33000 | 36500 |
| terrainResistance | `1.1 1.4 2.3` | `1.3 1.7 2.3` | `1.2 1.5 2.3` |

Физический box collider, шесть опор, выбор radius/support mapping, torque при
2500RPM, suspension/friction и P05B yaw control остаются **явной test_lab policy**.
Исходные массы/точки/максимальные скорости не доказывают реконструкцию родной
динамики WoT. Не переносить ИС-7 mass68190/collider на новые машины.

## Какие существующие функции переиспользовать

| Этап | Уже есть | Ограничение / требуемое изменение P04M |
|---|---|---|
| Пинованный каталог и stock assembly | `tools/p09e_research_catalog.py::load_catalog/_load_catalog`, `installable`, `Catalog` | Каталог не даёт runtime profile и ownership. `p09e_research_projection.py::descriptor` уже строит plain descriptor любой поддержанной assembly. |
| Разбор collision | `tools/geometry_spike.py::primitive_sections/collision_mesh` | Готовый bounded reader для выбранных9 `xyznuv`; `main()` hardcoded Т-34-85 и пишет сырые assets, его не запускать как новый importer. |
| Source bundle и group/material binding | `tools/is7_collision_bundle.py::read_members/_component/build_bundle/validate_bundle`, `tools/ms1_collision_bundle.py` | Сам exporter закрыт на IS-7 и точные pins/counts/pivots. Нужна отдельная версия P04M с декларацией каждой stock assembly; не ослаблять старые validators. |
| Effective armor/materials | `tools/is7_contact_bundle.py::component_materials/material_catalog/build_bundle`; `tools/ms1_contact_bundle.py::_loader_defaults/_kind_mapping/_common_materials` | Для каждого part читать его `armor` и overrides, а не одну фронтальную толщину. Отсутствующая effective запись отличается от armor0; gun/surveyingDevice и vehicleDamageFactor0 сохраняются. |
| Физические значения и pool | `tools/vehicle_physics_profile.py::build_profile/project_config/export` | Только IS-7 и pinned six-support policy. Выделить вычисление из переданного stock source spec, с source-based mass и отдельным approved digest на результат. |
| Управление | `tools/tracked_handling_profile.py::build_profile/project_config/verify_projection/export`; `tracked_handling_matrix.py` | Только ms1/is7 choices и закрытые SHA. Новые source rotation50/37/36 и P05B policy должны быть отдельными версиями/fixtures. |
| AP/loadout | `tools/p09c_ammo_catalog.py::_validate_fields/audit_sources`; `server/gateway/src/shared/vehicle_profile.rs::ShellSpec/AimSpec/VehicleKind` | Сейчас только два mount и шесть shell definitions; добавить точные три mounts/AP source rows, не просто увеличить vehicle enum. |
| Runtime resources | `shared/geometry.rs::Bundle::load`, `materials.rs::Catalog`, `drive/worker/profile.rs::VehicleProfile::load`, `shared/profile13_templates.rs::parse/load` | Закрыты на два вида, точные SHA и `[Profile;2]`. Нужны versioned curated5 manifest и пять approved bindings; неизвестные kinds/hashes по-прежнему отвергать. |
| Owned admission | `tools/p08b_battle_store.py::freeze_loadout/_reservation`, `p08b_battle_projection.py::capabilities`, `battle/profile13.rs::Frozen` | Native inventory ID — ID принадлежащего экземпляра, а не type CD/VehicleKind. Старое 1→MS1/2→IS7 нельзя продолжить простым3→Т26; новые покупки P09E уже используют native IDs>2. |

Отдельные подтверждённые hardcodes для будущего изменения:
`battle/fire.rs::State::with_loadout` ammo≤96;
`p08b_battle_store.validate_request` remaining_ap≤96;
`battle/profile13.rs` remaining_ap≤96 и закрытые frozen kind/descriptors;
`shared/model.rs::MAX_SHOTS = CAPACITY*96` в исследованной P08C версии.
Т-26 нужен160, поэтому обрезать его до96 нельзя. Bound следует получать из
пинованной assembly capacity и пересчитать общий журнал выстрелов; учесть
P05C capacity6 и сохранение bounded memory. P08C result bound shots192 покрывает
один стартовый stock БК160, но это не разрешение на безграничное пополнение.
P04G `SEAT_ROLES`/policy и старые P09D native-layout adapters также закрыты на1/2;
их точные source gates сохраняются, нужен новый opt-in adapter новых owned rows.

## Практическая последовательность реализации

Это **план, не выполненные изменения**. Разрешение ночного исследования не
означает закрытие P04M или принятие профилей владельцем.

1. В отдельной ветке P04M создать маленький source-spec/pin manifest ровно для
   `t26-stock`, `t34-stock`, `t3485-stock`. Ссылаться на проверенный P09E каталог,
   точные turret/gun/shot names и ZIP members выше. Не копировать1.18GB package,
   модели/текстуры или клиентский код в git.
2. Добавить один bounded source importer, например
   **проектируемый** `tools/p04m_vehicle_profile.py`: переиспользовать readers
   выше; проверить исходные `.model → .visual → primitives` ссылки, identity
   transforms, primitiveGroup coverage, finite bounds, точные material kinds и
   нулевую площадь. Выходы — небольшие derived physics/contact JSON только под
   `local/evidence`, metadata/digests — в git. Этот CLI пока **не существует**.
3. Сначала получить три неизменяемые source audit/projection записи без допуска,
   затем добавить versioned runtime resource loader и stock gun/AP/aim facts.
   Старые MS-1/ИС-7 byte/hash-bound fixtures должны пройти без регенерации.
4. Обобщить новые owned mount/crew/layout bindings через настоящий P09E vehicle
   row. Полные actual crew и owned AP обязательны. Если crew recruitment/layout
   ещё не умеет новый mount — явный отказ; тестовый временный танк не закрывает
   ангарную приёмку. Сохранить writer transaction/replay/restart и новые P08C
   atomic results с shots==consumedAP.
5. Автоматически проверить source tamper, неизвестный mount/HE/APCR, неверные
   geometry/physics kinds, вместимость160, два полных БК/scene capacity, реальные
   worker straight/reverse/pivot/brake/slope/collision/replay, AP side plate,
   damage/death/wreck и оба ангарных цикла. Native renders/aim/marker/controls,
   bbox и каждое `battle_admission=true` остаются отдельными owner gates.

Из существующих команд (здесь **не запускались**, они пишут новые outputs):

```powershell
# Повторный каталог-аудит — обычный существующий CLI, путь вывода свежий.
python -B -X utf8 tools/p09e_research_catalog.py --original C:\WoT_0.9.1_RU_0717_original --out local/evidence/<fresh-p04m-audit>
# Baseline exporters: только IS-7, не умеют --vehicle t26.
python -B -X utf8 tools/is7_contact_bundle.py --out local/evidence/<fresh-p04m-baseline>/is7-contact.json
# После появления пинованного нового worker config — существующая real-worker matrix.
python -B -X utf8 tools/tracked_handling_matrix.py --worker <owned-PhysicsWorker.dll> --local-root D:\WoT_9.1_Server\local --config <new-config.json> --config-sha256 <sha> --out local/evidence/<fresh-p04m-matrix> --repeats 2 --diagnostics
# Регрессия существующих импортеров и полный gateway на свежем output.
python -B -X utf8 -m unittest tests.test_vehicle_physics_profile tests.test_is7_contact_bundle tests.test_ms1_contact_bundle tests.test_p09c_ammo_catalog -v
python -B -X utf8 server/build.py gateway --test --out local/build/server/<fresh-p04m>
```

## Узкие UNKNOWN и отложенный КВ-1

- Native bbox/model/pivot/aim readback новых трёх машин — **NOT_RUN**. Source
  visual/vertex bounds и pivots проверены статически; это разные уровни доказательства.
- Effective MaterialInfo для всех новых material slots через существующий
  loader-default resolver ещё не экспортирован/сопоставлен с native — **NOT_RUN**.
- Повторный #717 reader audit исправил первоначальное неполное наблюдение:
  у stock Т-34 mounted `extraPitchLimits/back = -17 1 42`, transition0.4rad.
  У выбранных Т-26/Т-34-85 extra rear отсутствует; Т-34-85 mounted `-22 7`
  перекрывает shared `-26 8`. Нельзя переносить rear35°/45° от MS-1/ИС-7.
  Свежие исходные записи — worktree P04M preparation01/source-facts.json,
  команды audit.py/propose.py; runtime clamp и native квалификация отдельно.
- Историческая suspension/track/drivetrain law — **UNKNOWN**, как у baseline;
  P05B/Jolt mapping остаётся версионированным приближением с проверкой поведения.
- Реальная стоимость/удобство crew/layout extension для purchased native IDs>2
  требует отдельного реализации-аудита, а не фиктивного гранта для приёмки.

КВ-1: `kv1.xml`,12430B,
`0db08af1461e25c3325fe9890bd0783a63df94a11564c6b42189cd5a974a1f82`;
stock `Chassis_KV1 / M-17T / Average / _10R / Turret_1_KV1 / _76mm_ZiS-5`,
type11777,590HP,47405kg,450hp,34/10km/h,capacity114,reload4s.
`R80_KV1/collision/{Hull,Turret_01,Gun_01}.primitives` действительно существуют,
но все имеют header `xyznuvtb`, и исходный `collision_mesh` завершился
`ValueError: only observed 32-byte xyznuv layout supported`.
Hull23356B SHA`db5f9661a664d3376c4c8a95f877d2698a2ca9f1cdf7798c796146b03be6565b`;
turret32832B SHA`a1826d3e0c05fd6cfc3a103fe8f3c4256d28dfb3d66b645ee6fa69ed7f4b307d`;
gun16544B SHA`a9f0ba0018505a8ca3916112bd2dd11cfb6440e40c39e19dae5404468b47ca64`.
Семантика этого layout здесь **не восстановлена**. Кроме того, первые wheel
groups имеют разные radii .20648 и .3025020063: IS-7 проверка равного radius
первой пары не переносится. КВ-1 пригоден для следующего расширения после
отдельного layout/support audit, а не для маскировки нового parser gap.

## Реально выполненные проверки, откат и следующий шаг

**PASS_STATIC:** повторный hash-bound каталог374; packed-XML чтение выбранных
stock assemblies; SHA256 полного `vehicles_russian.pkg`;27 bounded ZIP members
выбранных трёх машин;9 mesh parses;9 проверок exact-zero-area (везде0);
HP/mass/module/shot/crew/descriptor извлечение и common projectileSpeedFactor.
**OBSERVED_FAIL:** честный отказ `collision_mesh` на всех3 `xyznuvtb` КВ-1.
Runtime/worker/build/native tests — **NOT_RUN**, Battle admission не менялся.

Исходные команды были read-only PowerShell here-strings → `python -B -X utf8 -`,
которые вызывали указанные `load_catalog`, `decode/walk`, `ZipFile.read`,
`collision_mesh`, `primitive_sections`, `hashlib.file_digest`. Временных exports,
копий package и отдельных ignored evidence-файлов не создавалось; проверенные
пути, hashes, значения и фактический отказ сохранены в этом документе.
Откат — удалить этот единственный документ. Статус P04M — **RESEARCH_READY,
IMPLEMENTATION_NOT_RUN, OWNER_ACCEPTANCE_NOT_RUN**.

Единственный следующий шаг после зависимых карточек: начать P04M с нового
source-spec/importer для указанных трёх stock assemblies, сохраняя допуск false.
