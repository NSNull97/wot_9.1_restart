# P06T — исходный контракт снарядов, модулей, экипажа и пожара #717

Дата: 2026-10-16. Исследование пункта 7
[IMPLEMENTATION_ORDER](../IMPLEMENTATION_ORDER.md) по ночному разрешению владельца.
Текущая ветка `codex/p06t-mixed-shell-damage` после P04M runtime483bb2b.
Ниже сохранены исходные факты и границы их подтверждения; runtime-результаты
учитываются отдельно. Оригинал клиента только прочитан, native/UI/audio — **NOT_RUN**.

## Текущий кандидат реализации

**OBSERVED AUTOMATIC:** первый общий focused02 скомпилировался,63PASS/1FAIL
в новом тесте, который ошибочно вызывал legacy fire API для typed armament.
Старый guard сохранён, тест исправлен на typed command. Полные логи в
`local/build/server/gateway-p06t-focused02/`; это не PASS всего P06T.
Focused03 сохранил compile failures в новых publication tests; focused04 —
72PASS/2FAIL в подготовке World fixtures. Ошибки исправлены без ослабления
production guards и source contact assertions. Focused05 в
`local/build/server/gateway-p06t-focused05/`: **74PASS/0FAIL/0ignored/buildPASS**,
31.88с tests; exe SHA256
`bb451571bb4f85b0a3222d83688701f45c858ebec838356ad14ba63eb2ac6959`.
Полный canonical source gate пока **NOT_RUN**.

Включение только явным `p06t_mixed_ammo=true` и client prepare флагом
`--enable-p06t-mixed-ammo` вместе с profile13/P04M. Старый v1/AP режим сохраняется.
Новый v2 writer хранит истинные три stack, current/next, source catalogue,
reserve/finish/restart и atomic full result с terminal module/crew journal.
Снаряд замораживается при admission; trajectory, source FX, урон и Trace
используют ту же запись после последующего выбора другого типа.

**EXPLICIT LAB, не VERIFIED HISTORICAL:** single-plate solver AP/APCR/HEAT/HE,
HE attenuation/actual first-surface LOS, нормализованные внутренние AABB proxy,
не более двух module/seat hits, SplitMix64 ignition draws, десять fire ticks.
Source caps/roles/fire chance не доказывают исторические hit volumes/формулы.
Отдельный `test_lab.p06t.plate-penetration-or-exterior-gun.v1` разрешает только
module gunHealth для настоящего source GunVisualMaterial25 с достаточным
nominal power; vehicle HP от этой поверхности не уменьшается. Source chance
0.33 не объявляется восстановленным алгоритмом старого сервера.

Один World damage/death ledger принимает direct/splash/fire и crew death.
При гибели экипажа положительный HP сохраняется; команды закрываются,
retained geometry блокирует следующий снаряд без повторного урона/смерти.
Повреждения двигателя/гусениц идут в реальные shared-scene controls; башни/
экипажа — в Aim; ammo bay/loader — в reload; optics/commander — в view range.
Radio и dispersion пока не имеют полноценной игровой модели и не считаются
реализованными эффектами этих capabilities. Ammo-bay explosion, ремонт,
восстановление экипажа и историческая damage variance пока не реализованы.

Native publication хранит текущие crew/fire/HP при hide/reveal и требует
актуальные epochs всех entity IDs. Модули/места экипажа получает только владелец;
скрытые позиции/HE center не передаются. Actual client execution ещё NOT_RUN.
Source WT1286/1504 scheduler и FV premium HE275 проверяются отдельно; у WT/FV
нет qualified physics/owned admission, UK nationID5 требует versioned catalogue
correction. Полную P06T или доступность этих машин это не закрывает.

## Граница доказательств

- **VERIFIED SOURCE:** типы и порядок аргументов `.def`, значения ресурсов,
  выбранные инструкции оригинального Python 2.7, порядок extras и коды уведомлений.
- **OBSERVED PREVIOUS GATE:** формат размера ARRAY signed32 и уже принятые AP/HP
  пути описаны в [P02](P02_ARENA_ENTRY.md),
  [P06K](P06K_AP_IMPACT_CONTRACT.md) и последующих боевых исследованиях. Новые
  критические уведомления, смена семейства снаряда и пожар здесь не наблюдались.
- **INFERRED:** новые численные ID методов из стабильного порядка по stream size;
  начальная политика серверной реализации. Сам `.def` не задаёт численный wire ID.
- **UNKNOWN:** отсутствующая серверная модель пробития/взрыва/модулей, внутренние
  hit volumes и результат новых пакетов на настоящем клиенте. Клиентский UI
  predictor из P06K не доказывает серверную механику.

Источник: `C:\WoT_0.9.1_RU_0717_original\res\scripts\`, из проверенного #717.
Локальные исходные выписки и disassembly остаются в ignored
`local/evidence/20261016-p06t-01/` (`E` ниже). В git помещены только выводы,
числовые данные и pins, без исходного кода клиента. `.pyc` исследованы как
инертные данные через `tools/py27_static.py`; оригинальные модули не импортированы
и не исполнены. Opcode table CPython 2.7.3 SHA256:
`acfe212847ecb81ca28bdab976a3caacff3568b45a9e8ca78d6957f9f3ef4884`.

## Public fire: массив эффектов, не битовая маска

**VERIFIED SOURCE:** `entity_defs/vehicle.def` задаёт
`publicStateModifiers: ARRAY<EXTRA_ID>`, flags `ALL_CLIENTS`.
`entity_defs/alias.xml` задаёт `EXTRA_ID = UINT8`. Это список индексов extras
descriptor конкретной машины. `damageStickers` — другой список, `ARRAY<UINT64>`.

В уже принятом native create layout Vehicle восемь свойств:

| Индекс свойства | Поле | Сериализуемый тип |
|---|---|---|
| 0 | isStrafing | BOOL |
| 1 | isCrewActive | BOOL |
| 2 | gunAnglesPacked | UINT16 |
| 3 | health | INT16 |
| 4 | engineMode | TUPLE<UINT8, size=2> |
| 5 | publicInfo | исходный составной public-info type |
| 6 | damageStickers | ARRAY<UINT64> |
| 7 | publicStateModifiers | ARRAY<UINT8> |

Порядок подтверждается текущим `arena/vehicle.rs::create_vehicle` и
`shared/wire.rs::create_vehicle`; не следует подставлять порядок объявления
из `.def`. Signed32 count у ARRAY установлен прежним P02 native/static gate.
Исходная PE выписка: `local/evidence/20261005-p02-arena-entry/wire/CONTRACT.md`,
ordinary factory mode3 `dc92c0`, client-property sort `dca5b0`/`dc6e30`,
stable insertion sort `dcb3b0`, variable ARRAY count reader `dedc84`,
`dedc90–dedc97`. Закреплённый оригинальный EXE SHA256
`86f5e351d44c12e0d2b89ed741ee9a4e70d21f234c39aa9cfd709536d49f04ed`.
Поэтому `property 6 + i32(0)` — **пустой damageStickers**, а
`property 7 + i32(0)` — **пустой publicStateModifiers**.
Для целого значения publicStateModifiers `[4]` содержимое типа —
`01 00 00 00 04`, для `[]` — `00 00 00 00`. Четвёрка здесь элемент массива,
не mask `1 << 4` и не произвольный флаг здоровья.

`Vehicle.set_publicStateModifiers:331` при `isStarted` превращает новое
значение в frozenset, запоминает его и передаёт разности added/removed в
`Vehicle.__updateModifiers:765`. Удалённый индекс вызывает `extra.stop(data)`;
добавленный после проверки границ — `typeDescriptor.extras[idx].startFor(self)`
(bytecode offset 201). Из исходного порядка extras **индекс 4 = fire**.
`client/vehicle_extras.pyc::Fire._start:275` запускает flaming effects модели
и вибрации; `_cleanup:301` останавливает их. Удалять надо только fire из
текущего полного набора modifiers, сохраняя остальные активные extras.
После создания уже горящей машины initial modifiers тоже должны содержать 4.

**INFERRED/UNKNOWN wire boundary:** при существующей базе property messages
`0x9e` индекс 7 даёт кандидата `0xa5`, но полный dynamic ARRAY/property-update
envelope и возможный partial-array update требуют отдельного PE/native proof.
Первоначальная граница этого раздела впоследствии уточнена отдельным
[PE proof наружного формата](P06T_FIRE_PROPERTY_ENVELOPE.md): full update0xa5
имеет VAR1 длину. Его native визуальное исполнение всё ещё NOT_RUN.

Отдельно `Avatar.showVehicleDamageInfo` включает собственную damage-panel/fire
индикацию и звуковые уведомления. Он **не меняет** publicStateModifiers и сам
по себе не зажигает видимую другим машину. Обе публикации должны вытекать из
одного авторитетного серверного fire state; внешняя — только законным текущим
наблюдателям машины после её создания, с правилами P07B.

## Native методы и входящие настройки

Типы и порядок ниже **VERIFIED SOURCE** по `.def` и consumers. Численные ID
новых методов — **INFERRED candidates** в `E/method-tables02.json`, не native PASS.
Фиксированные параметры идут в обычном little-endian представлении;
`OBJECT_ID` — 4 байта. Каждый message ID принадлежит таблице своей сущности.

| Сущность/метод | Аргументы в порядке `.def` | Байты аргументов | Кандидат ID |
|---|---|---:|---:|
| Avatar.updateVehicleHealth | INT16 health, BOOL isCrewActive | 3 | 0x3f |
| Avatar.updateVehicleSetting | UINT8 code, INT32 value | 5 | 0x40 |
| Avatar.updateVehicleAmmo | INT32 compactDescr, UINT16 quantity, UINT8 quantityInClip, INT16 timeRemaining | 9 | 0x44 |
| Avatar.showVehicleDamageInfo | OBJECT_ID vehicleID, UINT8 damageIndex, EXTRA_ID extraIndex, OBJECT_ID entityID | 10 | 0x45 |
| Avatar.updateVehicleGunReloadTime | OBJECT_ID vehicleID, FLOAT32 timeLeft, FLOAT32 baseTime | 12 | 0x46 |
| Avatar.updateVehicleMiscStatus | OBJECT_ID vehicleID, UINT8 code, INT32 intArg, FLOAT32 floatArg | 13 | 0x47 |
| Avatar.showOtherVehicleDamagedDevices | OBJECT_ID vehicleID, ARRAY<EXTRA_ID> damaged, ARRAY<EXTRA_ID> destroyed | variable | 0x54 |
| Vehicle.onHealthChanged | INT16 health, OBJECT_ID attackerID, UINT8 attackReason | 7 | 0x3c |
| Vehicle.showAmmoBayExplosion | FLOAT32 fireballVolume, FLOAT32 projectedTurretSpeed | 8 | 0x3d |
| Vehicle.showDamageFromExplosion | OBJECT_ID attackerID, VECTOR3 center, UINT8 effectsIndex | 17 | 0x40 |
| Vehicle.showDamageFromShot | OBJECT_ID attackerID, ARRAY<UINT64> points, UINT8 effectsIndex | variable | 0x42 |

Эти fixed method layouts и существующие target selectors надо использовать
через установленный native transport. Размер наружной записи и VAR-length
существующей entity boundary не входит в колонку «байты аргументов».
Массивам нужны count/size/element bounds; нельзя переносить весь разрешённый
размер transport в неограниченный allocation по count клиента.

`Avatar.showVehicleDamageInfo:1506` сначала индексирует
`constants.DAMAGE_INFO_CODES[damageIndex]`. При `extraIndex != 0` берёт
`self.vehicleTypeDescriptor.extras[extraIndex]`, при 0 — None. Для собственной
или наблюдаемой после смерти машины обновляет damage icon/sound, затем при
разрешённом damageCode вызывает battleMessages. Это **не сообщение HP модуля**:
численного module health в аргументах нет. Его выбирает сервер, а extraIndex
должен соответствовать descriptor получателя/наблюдаемой машины. Нельзя
рассылать чужие module IDs всем клиентам или строить крит из client hit report.

`__showDamageIconAndPlaySound:2852` переводит имена extras с суффиксом `Health`
в device state `critical`, `destroyed` или `normal`, обновляет damage panel и
расходники. `FIRE_STOPPED` снимает локальный fire indicator. Generic state codes
0/1/2/3 и drowning 16/17/21 входят в noNotification set: UI-state восстановление
без нового голосового event — допустимая семантика исходного consumer, а не
доказательство оригинального server replay алгоритма.

`VehicleMarkersManager.ATTACK_REASONS:2497` имеет независимый порядок:
**0 attack, 1 fire, 2 ramming, 3 world_collision, 4 death_zone, 5 drowning**.
Shot visual hit effect — ещё один namespace: 0 ricochet, 1 not pierced,
2 pierced no damage, 3 pierced, 4 critical. Packed hit component 0 chassis,
1 hull, 2 turret, 3 gun тоже не extraIndex.

`Avatar.updateVehicleHealth:1145` нужен для owner HUD/postmortem;
`Vehicle.health` и `onHealthChanged` — для entity presentation.
`Vehicle.isCrewActive` ALL_CLIENTS BOOL и `set_isCrewActive:371` отдельно
от HP допускают смерть с положительным health. Если сервер реализует полную
гибель экипажа, owner BOOL, public property, capability и lifecycle обязаны
согласоваться. Визуально выставить false, сохранив живого стреляющего actor,
нельзя. `VEHICLE_HEALTH.EXPLODED=-1` и `TURRET_DETACHED=-2` имеют особую
семантику; обычный ноль HP не доказывает взрыв БК или отрыв башни.

Входящий Base Avatar `vehicle_changeSetting(UINT8 code, INT32 value)` имеет
кандидат 0x8d и 5 байт аргументов в существующей VAR2 Base boundary.
`VEHICLE_SETTING`: CURRENT_SHELLS=0, NEXT_SHELLS=1, AUTOROTATION=2,
ACTIVATE_EQUIPMENT=16, RELOAD_PARTIAL_CLIP=17. Исходный
`onAmmoButtonPressed:1786` проверяет alive/known ammo/quantity>0, оптимистично
меняет клиентскую настройку, затем вызывает base. Сервер проверяет admission,
свой owned stack и schedule; отказ не должен оставлять ложный выбранный shell.
Точный caller/order для partial-clip reload здесь не установлен — **UNKNOWN**.
Base `vehicle_replenishAmmo()` — другой метод, кандидат 0x89 без аргументов;
не повод бесплатно пополнять боекомплект.

`updateVehicleSetting:1350` обновляет current/next ammo, activeGunShotIndex и aim.
`__processVehicleAmmo:3281` хранит `(compactDescr, quantity, quantityInClip)`;
shell-ветка не использует timeRemaining. Reload timer обновляется отдельным
`updateVehicleGunReloadTime:1195`. Историческая server convention «quantity
включает/не включает clip» и переключение неполного clip пока не измерены.

`VEHICLE_MISC_STATUS.DESTROYED_DEVICE_IS_REPAIRING=7` использует intArg:
`extraIndex = intArg & 255`, `progress = (intArg & 65280) >> 8`, floatArg — время
ремонта. Это UI progress, не HP модулей. `showOtherVehicleDamagedDevices` связан
с исходным monitor/perk path. Cell
`monitorVehicleDamagedDevices(OBJECT_ID)` — shape VERIFIED, численный wire ID
**UNKNOWN**; нужен отдельный transport proof. Не открывать по этому пути всем
скрытое состояние модулей.

## Exact DAMAGE_INFO_CODES: damageIndex

**VERIFIED SOURCE:** литерал `common/constants.pyc`, порядок 0-based.

| Index | Code | Index | Code |
|---:|---|---:|---|
| 0 | DEVICE_CRITICAL | 18 | DEVICE_REPAIRED_TO_CRITICAL |
| 1 | DEVICE_DESTROYED | 19 | DEVICE_REPAIRED |
| 2 | TANKMAN_HIT | 20 | TANKMAN_HIT_AT_WORLD_COLLISION |
| 3 | FIRE | 21 | TANKMAN_HIT_AT_DROWNING |
| 4 | DEVICE_CRITICAL_AT_SHOT | 22 | TANKMAN_RESTORED |
| 5 | DEVICE_DESTROYED_AT_SHOT | 23 | DEATH_FROM_DEVICE_EXPLOSION_AT_FIRE |
| 6 | DEVICE_CRITICAL_AT_RAMMING | 24 | ENGINE_CRITICAL_AT_UNLIMITED_RPM |
| 7 | DEVICE_DESTROYED_AT_RAMMING | 25 | ENGINE_DESTROYED_AT_UNLIMITED_RPM |
| 8 | DEVICE_STARTED_FIRE_AT_SHOT | 26 | DEATH_FROM_SHOT |
| 9 | DEVICE_STARTED_FIRE_AT_RAMMING | 27 | DEATH_FROM_INACTIVE_CREW_AT_SHOT |
| 10 | TANKMAN_HIT_AT_SHOT | 28 | DEATH_FROM_RAMMING |
| 11 | DEATH_FROM_DEVICE_EXPLOSION_AT_SHOT | 29 | DEATH_FROM_FIRE |
| 12 | DEVICE_CRITICAL_AT_FIRE | 30 | DEATH_FROM_INACTIVE_CREW |
| 13 | DEVICE_DESTROYED_AT_FIRE | 31 | DEATH_FROM_DROWNING |
| 14 | DEVICE_CRITICAL_AT_WORLD_COLLISION | 32 | DEATH_FROM_WORLD_COLLISION |
| 15 | DEVICE_DESTROYED_AT_WORLD_COLLISION | 33 | DEATH_FROM_INACTIVE_CREW_AT_WORLD_COLLISION |
| 16 | DEVICE_CRITICAL_AT_DROWNING | 34 | DEATH_FROM_DEATH_ZONE |
| 17 | DEVICE_DESTROYED_AT_DROWNING | 35 | FIRE_STOPPED |

Исходные UI categories: critical={0,18,4,6,12,14,16,24};
destructions={1,5,7,13,15,17,2,10,20,21,25};
healings={19,22,35}; fire={3,8,9,35}. Пересечения intentional: FIRE_STOPPED
одновременно лечит fire state и принадлежит fire category.

## Exact extraIndex: модули и места экипажа

**VERIFIED SOURCE:** `_readExtras:5258` начинает с dummy NoneExtra в индексе 0,
читает исходный XML `/extras` по порядку и создаёт индекс через `len(extras)`.
Guard максимум 200 не делает каждый UINT8 допустимым индексом. Это **не ID
модуля магазина**, не compactDescr и не номер hit component.

| Extra | Name | Extra | Name |
|---:|---|---:|---|
| 0 | dummy NoneExtra | 22 | ration_japan |
| 1 | shoot | 23 | hotCoffee |
| 2 | noAmmo | 24 | removedRpmLimiter |
| 3 | gunReload | 25 | qualityOil |
| 4 | fire | 26 | engineHealth |
| 5 | commanderSixthSense | 27 | ammoBayHealth |
| 6 | stereoscope | 28 | fuelTankHealth |
| 7 | camouflageNet | 29 | radioHealth |
| 8 | handExtinguishers | 30 | leftTrackHealth |
| 9 | autoExtinguishers | 31 | rightTrackHealth |
| 10 | smallMedkit | 32 | gunHealth |
| 11 | largeMedkit | 33 | turretRotatorHealth |
| 12 | smallRepairkit | 34 | surveyingDeviceHealth |
| 13 | largeRepairkit | 35 | commanderHealth |
| 14 | lendLeaseOil | 36 | driverHealth |
| 15 | gasoline100 | 37 | radioman1Health |
| 16 | gasoline105 | 38 | radioman2Health |
| 17 | chocolate | 39 | gunner1Health |
| 18 | cocacola | 40 | gunner2Health |
| 19 | ration | 41 | loader1Health |
| 20 | ration_china | 42 | loader2Health |
| 21 | ration_uk | — | — |

`_selectCrewExtras:6044` использует primary role каждого seat: commander/driver
без порядкового суффикса, остальные роли с ordinal 1/2. Поэтому stock MS-1
имеет **два seat extras [35,36]**, а IS-7 — **[35,39,36,41,42]**. Совмещённые
gunner/radioman/loader роли командира MS-1 не создают дополнительных людей;
loader+radioman IS-7 тоже один seat. Server wounded-seat state должен влиять
на все его обязанности; нельзя потерять второго заряжающего при dedup роли.

## Снаряды и исторические ограничения

Все строки — **VERIFIED SOURCE #717**. Power — исходная пара значений
номинального пробития 100/500 м; это ещё не серверная формула. Damage —
armor/devices. Speed — **сырой** XML, до `_readShot` scaling. ID локален нации;
полный compactDescr формировать существующим исходным item codec.

| Орудие | Shell | ID | Kind | Damage | Power | Speed | HE radius, м |
|---|---|---:|---|---|---|---:|---:|
| MS-1, 37 mm Gochkins id23 | _37mm_UBRT1 | 10 | ARMOR_PIERCING | 30/50 | 34/27 | 442 | — |
| то же | _37mm_BPT1 | 11 | HOLLOW_CHARGE | 30/50 | 44/44 | 354 | — |
| то же | _37mm_UOT1 | 12 | HIGH_EXPLOSIVE | 36/50 | 19/19 | 442 | 0.31 |
| IS-7, 130 mm S-70 id58 | _130mm_UBR-482 | 57 | ARMOR_PIERCING | 490/180 | 250/240 | 900 | — |
| то же | _130mm_UBR-482P | 58 | ARMOR_PIERCING_CR | 490/180 | 303/263 | 1125 | — |
| то же | _130mm_UOF-482 | 59 | HIGH_EXPLOSIVE | 640/180 | 68/68 | 900 | 2.78 |
| WT E100, 128 mm K44/2 L61 id90 | _128mm_PzGr39L | 54 | ARMOR_PIERCING | 560/180 | 276/261 | 1200 | — |
| то же | _128mm_PzGr43 | 55 | ARMOR_PIERCING_CR | 560/180 | 352/295 | 1500 | — |
| то же | _128mm_SprG19 | 56 | HIGH_EXPLOSIVE | 700/180 | 65/65 | 1200 | 2.71 |
| WT E100, 150 mm Rohr L38 id91 | _150mm_PzGr42 | 76 | ARMOR_PIERCING | 750/203 | 235/220 | 757 | — |
| то же | _150mmGr_39H3A_G | 75 | HOLLOW_CHARGE | 750/203 | 334/334 | 606 | — |
| то же | _150mm_SprgG_ausf_45 | 74 | HIGH_EXPLOSIVE | 950/203 | 85/85 | 757 | 3.57 |
| FV215b (183), 183 mm AT Gun id54 | _183mm_AP_Mk1 | 81 | ARMOR_PIERCING | 1150/244 | 310/300 | 830 | — |
| то же | **_183mm_HESH** | **82** | **HIGH_EXPLOSIVE** | **1750/244** | **275/275** | **830** | **5.05** |
| то же | _183mm_HE_Mk1 | 83 | HIGH_EXPLOSIVE | 1750/244 | 92/92 | 830 | 5.05 |

FV premium HESH имеет исходный `price/gold` node. Это именно HE семейство с
275 мм, не HEAT и не современное значение. Отдельной HESH ballistic-kind
константы для него нет. `HOLLOW_CHARGE` здесь означает кумулятив, а
`ARMOR_PIERCING_CR` — подкалибер; не переименовывать строки входного каталога.

Для этих shot rows исходные gravity=9.81, maxDistance=720. Общий
`projectileSpeedFactor=0.8`; `_readShot:4473` умножает speed на factor и gravity
на factor² (offsets 179/182 и 205/208/211/212). Raw speed нельзя бездумно
скопировать как готовую клиентскую скорость; нельзя оставить AP speed для
HEAT/APCR другого shot. Принятая траектория P03H остаётся отдельной проверкой
реального transport/physics соответствия.

**Mounted WT contract:**
`waffentrager_e100.xml:/turrets0/Turret_1_Waffentrager_E100/guns` задаёт:

| Орудие | Clip count | Clip rate | Между выстрелами | Reload | Max ammo |
|---|---:|---:|---:|---:|---:|
| _128mm_K44_2_L61 | **6** | 30/min | **2 s** | 60 s | 60 |
| _150mm_Rohr_L38 | **4** | 20/min | **3 s** | 50 s | 60 |

`_readGunClipBurst:4286` возвращает count и `60.0 / rate` для count>1.
Шесть выстрелов относятся только к 128 мм. Сначала читать mounted overrides,
не только shared component: у stock MS-1 mounted reload=2.5 s против generic
2.2857; у IS-7 mounted=13.7 против generic 15.42857. Crew modifiers и реальное
время неполного reload — отдельная часть runtime policy.

## Module health и отсутствующая серверная механика

Source caps выбранных stock loadouts ниже — **VERIFIED SOURCE**;
`maxHealth/maxRegenHealth` не задают сами по себе critical threshold,
chance-to-hit, burn rate, ремонтную скорость или правило взрыва.

| Модуль | MS-1 max/regen | IS-7 max/regen |
|---|---:|---:|
| ammoBay | 60/40 | 210/140 |
| engine | 25/17 | 360/180 |
| fuelTank | 100/40 | 200/80 |
| radio | 90/75 | 250/75 |
| left/right track | 40/30 | 250/190 |
| gun | 54/27 | 210/105 |
| turretRotator | 50/25 | 170/85 |
| surveyingDevice | 30/15 | 120/60 |

MS-1 engine `MS-1`, Small fuel tank, Alarm_flags radio; IS-7 engine M-50T,
Large fuel tank, 10RK-26 radio. Исходные engine fireStartingChance 0.2/0.15;
common misc minFireStartingDamage=21. Точные условия, величина и порядок RNG
их применения остаются UNKNOWN. Hull/turret health72+18=90 у MS-1 и
1720+430=2150 у IS-7 составляют vehicle HP; не делать из этой суммы
дополнительный независимый «HP башни» с придуманным критом.

`_readDeviceHealthParams:4637` читает maxHealth/maxRegenHealth/repairCost.
Ветки healthRegenPerSec, healthBurnPerSec, chanceToHit, hysteresisHealth
охраняются `!IS_CLIENT || IS_DEVELOPMENT` (offsets159/166/169); часть полей
отсутствует в release resources. Common material descriptors содержат,
например, engine extra/chanceProjectileHit0.45, ammoBay0.27,
commander projectile0.33/explosion0.15, track1.0, gunBreech1.0. Это
содержимое конфигурации, не доказанный server algorithm или RNG порядок.

`_readShell:4405` тоже закрывает normalization/ricochet/часть HEAT
параметров server/development guard. Наличие loader defaults
damageRandomization=0.25 и piercingPowerRandomization=0.25 не устанавливает
распределение, число draws, округление или порядок обработки слоёв.
Нет доказанного оригинального HE splash solver, HEAT loss-through-screen,
HESH solver или internal-module damage solver. Современные Tankopedia,
Blitz/Lesta и чужие серверы в исследовании не использовались.

## Что реально можно реализовать дальше

**INFERRED proposed test_lab v1**, не обещание исторической симуляции:

1. Source-bound shell catalog и bounded авторитетный scheduler для
   admitted owner ammo: выбранное семейство, расход соответствующего stack,
   reload, clip capacity и запрет стрельбы до готовности. Client ammo-setting
   — намерение, не изменение server inventory. P08B writer, который сохраняет
   только AP, сначала обобщить на реальные frozen stacks; не выдавать HE/HEAT
   по факту выбора и не списывать их как AP. Любая тестовая выдача — отдельная
   явная seed policy/fixture без скрытой экономики.
2. Pure bounded module/crew/fire state с типизированными результатами и
   фиксированной policy revision. На вход — **проверенный authoritative hit
   конкретного модуля/seat** с shot ID и simulation revision. Порог крита,
   chances, repair/burn rates, effects и RNG seed/draw order, если исходник
   неполон, объявить лабораторной политикой, сохранить в replay evidence.
3. Native encoder для source-backed enum и state transitions; invalid index,
   чужой actor, лишний count, нечисловое время/HP отклонять до enqueue.
   Криты меняют реальную серверную возможность ехать/вращать/целиться/заряжать,
   fire ticks — vehicle/module HP и lifecycle/results. Одной картинки
   повреждённого двигателя недостаточно для authoritative приёмки.
4. Fire start/end публикует согласованные public modifier4, owner HUD
   damageInfo и health/death события с attackReason1; после outcome HP,
   module ticks и projectile damage должны замереть. Результат/возврат
   проходит существующий atomic writer, не отдельный непроверенный save.

**Обязательный геометрический блокер:** текущий `shared/geometry.rs::Bundle`
хранит ballistic surfaces Hull/Turret/Gun MS-1/IS-7. Он не экспортирует
внутренние объёмы двигателя, БК и мест экипажа. `shared/materials.rs`
сохраняет `extra_is_none`, а не идентичность extra; exterior gun kind25 и
surveying-device kind28 не заменяют внутренний layout. Некоторые исходные
материалы имеют действительное missing effective record, это не armor0.

До реального internal-module damage нужны original collision/hit-volume
исследование и provenance-bound export: component/material→actual extra/seat,
трансформы, модель объёма/сегмента и порядок прохождения. Внешнюю gun surface
можно подключать только после сохранения настоящего extraID. Назначать
случайного заряжающего при hull penetration и называть это установленной
геометрией запрещено. Isolated state tests с честными typed hit facts полезны,
но не закрывают runtime попадание в двигатель или экипаж.

Native приёмка затем проверяет смену каждого разрешённого семейства,
правильный расход/возврат/restart; clip 6/4 и reload; реальные hit locations и
изменение возможностей; start/stop видимого огня обоим законным наблюдателям;
owner sounds/HUD, death/postmortem и results. Автоматический codec round-trip
эту приёмку не заменяет.

## Воспроизведение и receipts

**Реально выполнено:** bounded static source extraction, rehash **25** уникальных
источников и **26** точных source assertions, включая исходные shell facts,
WT mounted clips, FV gold flag, ordered extras и выбранные bytecode offsets.
Результат `E/source-checks01.json`: **PASS_STATIC_SOURCE**, 7825 bytes, SHA256
`deba729e7bdb10305c6a906dd5886070ada1541359f0cf857511cc85d60001e7`.
Финальная read-only сверка 25 pins с оригиналом, всех 36 damage codes и 42
extra names с отчётом также PASS; `E/report-verification01.json`.
Это не Rust/Python damage runtime tests. Gateway/Jolt build, native packet
delivery, звук, fire UI и историческая статистика P06T — **NOT_RUN**.

Extraction commands (каждая создаёт отдельный append-only receipt; повторять
в новом каталоге, не затирая успешные/неуспешные старые прогоны):

```powershell
python -B -X utf8 local/evidence/20261016-p06t-01/read_source.py
python -B -X utf8 local/evidence/20261016-p06t-01/supplement.py
python -B -X utf8 local/evidence/20261016-p06t-01/extras_source.py
python -B -X utf8 local/evidence/20261016-p06t-01/more_source.py
python -B -X utf8 local/evidence/20261016-p06t-01/codes_source.py
python -B -X utf8 local/evidence/20261016-p06t-01/facts.py
python -B -X utf8 local/evidence/20261016-p06t-01/method_tables.py
python -B -X utf8 local/evidence/20261016-p06t-01/verify_source.py
```

Read-only повтор конкретного исходного вывода:

```powershell
python -B -X utf8 local/evidence/20261016-p06t-01/show_source.py client/vehicle 'set_publicStateModifiers|__updateModifiers'
python -B -X utf8 local/evidence/20261016-p06t-01/show_source.py client/avatar 'showVehicleDamageInfo$'
```

| Receipt | Bytes | SHA256 |
|---|---:|---|
| source-contract01.json | 4057813 | f619bcabe897a6bd699a1d5c11047e6a29de76f5390096089e503ac4c3fd37c6 |
| source-supplement01.json | 669188 | 34f007365198e729c6580014fb6f2d8e1c8050811d9a491a7a6fd5dccafafb59 |
| source-extras01.json | 298520 | d5bd2279ffba7ecb55a94cd6869296c1aeb0e7c41e92241303941d685538080a |
| source-more01.json | 327382 | ab98eeb5e881f76aff72c3345b28ba629976ffe86071e6a3ce603d7bd7e9c385 |
| source-codes01.json | 38282 | 7e2d1978c05fb9ec7e5595af5a33bdfdc9ae79cd288b4704759022979e211541 |
| facts01.json | 31216 | 59e3074baaf75fdfec7f6d3a3b999c29a89a59dabd866b9ce780686e5e8ade14 |
| method-tables02.json | 24767 | a0d45533c6c216ed61ffc7ec3f65e9da8a561909b236c36db7e3d1d0c9ac63fb |

`method-tables01.json` — прежний вывод с неустановленными Cell IDs;
используется только исправленный 02, где Cell ID UNKNOWN. `method_tables.py`
создаёт текущий 02; его numeric candidates не становятся VERIFIED от повторного
запуска собственного сортировщика.

Основные pins; полный список 25 путей/размеров/хешей в source-checks01:

| Original path относительно res/scripts | Bytes | SHA256 |
|---|---:|---|
| entity_defs/avatar.def | 7450 | 38cf983d6ea1fcaf1bbca25fd18567fed5abc3b2e07fbe14b168f46fa883f74d |
| entity_defs/vehicle.def | 5588 | 08dc1e6be577f80a04bf813ca046550201a3c4e673dad1540c5f1c6a047d1297 |
| entity_defs/alias.xml | 5987 | 14d5fcce8d979de6c24c50b3ff94d3ddf464f4ad27f2ef68c063407b4bbbc746 |
| common/constants.pyc | 34396 | 1c07c2e6a956dcfef95c4020954b4ca39efd77844d328cded935307a6515eebd |
| common/items/vehicles.pyc | 125668 | 805240e4b59d8a75950dbb97b41c17867606e7e96d7ff0c8d7b05312b83ae8b6 |
| client/avatar.pyc | 83656 | c13cd58a4c5d766dfd3c5f47ae7be50c962aee6c7f8cf25b4341322381f21e0e |
| client/vehicle.pyc | 24119 | b81d08ca14092bb8912adb2eff20325c3dd23424868bc03164cfe6b8da50463c |
| client/vehicle_extras.pyc | 9729 | 57fb84c47f923456b7a71fa9564f799b518da7dc56bc642dfa2a8d909e3ed0e0 |
| item_defs/vehicles/common/vehicle.xml | 13786 | 599ea82e48e98bf9a00c10256030097da31ce5d5889fa03737bc3b79230d256a |
| item_defs/vehicles/ussr/ms-1.xml | 11839 | a494bf04d29da7d066fd6923dbb75a79b947559a52405298c494a943c4b0c535 |
| item_defs/vehicles/ussr/is-7.xml | 5809 | 8d55fa4657a88f1436cd164afe11bade875a906fa7b97256f1fb2f803b09c10d |
| item_defs/vehicles/germany/waffentrager_e100.xml | 7551 | 6d8de10ed31cb908738ca9b32935aacfe01fec78d47239dadbd86713cba052e2 |
| item_defs/vehicles/uk/gb48_fv215b_183.xml | 6264 | ffbe8c9bbffbddf61d9197ce0cd4d4d79b6e0a6bfcbf2846c10fc31dd38f6712 |

Изменён только этот новый отчёт и ignored evidence. Откат — убрать этот файл;
runtime/база/оригинал от него не зависят. Статус: **research complete,
P06T implementation/native acceptance NOT_RUN**. Единственный следующий шаг
по P06T — source-bound bounded shell/module state component с явной lab policy
и закрытой границей неизвестной геометрии, после предшествующих карточек.
