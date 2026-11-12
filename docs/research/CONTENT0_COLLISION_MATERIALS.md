# CONTENT-0 2.5b: источники коллизии 13 отказанных машин

Карточка CONTENT-0, подшаг 2.5b (2026-11-12). Вопрос: почему генератор боевых профилей
(`tools/battle_any_profiles.py`) отказывает 13 машинам #717 по источникам коллизии, что об этих
данных известно из клиента 0.9.1 и что можно принять без выдумки. Клиент только читался:
`C:/WoT_0.9.1_RU_0717_original` (стенд `full-test-20261112-19`, `bridge.json`), packed XML через
`tools/packed_xml.py`, байткод не исполнялся. Закреплённые источники те же, что у MS-1/P04M:
`common/vehicle.xml` sha256 `599ea82e…d256a`, `misc.pkg!system/data/material_kinds.xml`
`59a2b751…c6fb9`, `vehicles.pyc` `805240e4…ae8b6`.

## Итог

| Группа | Машины | Причина отказа | Решение (только test_lab) |
|---|---|---|---|
| A. Группы-устройства в collision visual | Bat_Chatillon155_55, E50_Ausf_M, M41, A44 | `unmapped material kind` | приняты как `device_visual_material` |
| B. Роли экипажа в `<armor>` компонента | DickerMax, T40, Object263, M10_Wolverine | `active armor kind bound` | приняты как записи устройств |
| C. `nodefullVisual` вместо `nodelessVisual` | VK4502P, GB22_Comet | `collision model/visual binding` | приняты при проверке рамки |
| D. Дубликат постороннего XML-потомка | IS | `duplicate/invalid XML child` | дубликат не мешает, нужная секция уникальна |
| E. Дефект данных клиента | Ch01_Type59_Gold, T_50_2 | `COLLISION_SOURCE_UNRESOLVED` | остаются отказанными |

В test_lab 11 машин A–D становятся `generated` (в scratch-сборке 343 вместо 332 из 375). Таблица main
при этом не меняется ни на байт: все новые правила стоят за `WOT091_TEST_LAB=1`.

## Таблица видов материалов

**VERIFIED** (`material_kinds.xml`): броня 1–16; engine 21, ammoBay 22, leftTrack 23, rightTrack 24,
gun 25, turretRotator 26, surveyingDevice 28, fuelTank 29, radio 30, gunBreech 31; commander 41,
driver 42, radioman_1 43, radioman_2 44, gunner_1 45, gunner_2 46, loader_1 47, loader_2 48.
До 2.5b генератор и шлюз знали только броню, 25, 28 и 31 (`EXPECTED_KINDS`).

**VERIFIED** (`common/vehicle.xml`, `<materials>`): у каждого устройства и роли экипажа есть общая
запись `extra` + `damageKind device`, `collideOnceOnly true`, `useHitAngle/mayRicochet/
useArmorHomogenization false`:

| Вид | extra | vehicleDamageFactor | chanceToHit снаряд/взрыв | continueTraceIfNoHit |
|---|---|---|---|---|
| engine, fuelTank, radio, turretRotator | `<имя>Health` | 1.0 | 0.45 / 0.45 | false |
| ammoBay | ammoBayHealth | 1.0 | 0.27 / 0.27 | false |
| commander, driver, radioman_1/2, gunner_1/2, loader_1/2 | `commanderHealth`, `radioman1Health`… | 0.0 | 0.33 / 0.15 | true |

Гусеницы (`damageKind auto`) принадлежат шасси и в 2.5b не входят. Таблица имён в генераторе
(`ms1_contact_bundle.DEVICE_KINDS`/`DEVICE_EXTRAS`) и в шлюзе (`materials::device_kind_name`)
одна и та же; тест сверяет обе.

## A. Группы-устройства в collision visual

**VERIFIED** (primitiveGroup `identifier` и `materialKind`, `collisionFlags 0`):

| Машина | Компонент | Группы-устройства |
|---|---|---|
| F67 Bat.-Châtillon 155 55 | Turret_01 | radio 30, ammoBay 22, loader_2 48, loader_1 47, commander 41, gunner_1 45 |
| G73 E-50 Ausf. M | Hull | ammoBay, turretRotator, engine, fuelTank (имя в base64), radioman_1, driver, radio |
| G73 E-50 Ausf. M | Turret_01 | commander, gunner_1, loader_1, ammoBay |
| A18 M41 | Hull | radioman_1, driver, gunner_1, loader_1, commander, engine, radio, fuelTank, ammoBay |
| R59 A-44 | Hull | turretRotator |

Это ровно пять visual из переписи SHELL-02 (`tools/collision_device_census.py`, 2522 collision
visual): ни у одной другой машины #717 таких групп нет. У M41 и E-50M имя `fuelTank` в packed XML
записано как base64-строка — генератор теперь раскрывает её так же, как имена видов.

**VERIFIED**: `<armor>` этих компонентов в описании машины перечисляет только `armor_N` (и `gun` у
орудия); записей для устройств нет. **VERIFIED** (MS-1, `_readArmor` @4534): таблица материалов
компонента начинается пустой и содержит только перечисленных потомков `<armor>`. **INFERRED**: у
компонента для этих видов нет MaterialInfo — тот же случай, что `surveyingDevice` 28 без записи;
генератор пишет `effective: null`, общий шаблон не подставляется.

Как это трактовал 0.9.1:
- **VERIFIED** (P06J): `Vehicle.collideSegment` клиента превращает отсутствующий материал в броню 0
  для своего показа; механики урона клиент не содержит.
- **UNKNOWN**: что делал сервер при попадании в такую группу (урон модулю, шанс, продолжение
  трассы). Внутренние объёмы для остальных машин в клиенте отсутствуют (SHELL-02), так что эти пять
  visual — **INFERRED** остатки разработки, а не рабочая модель 0.9.1.

Поведение проекта (без нового закона): класс источника `device_visual_material`. Это не обычная
плита: AP возвращает `Unsupported(MaterialClass)`, прямой выстрел, ближайший контакт которого —
такой треугольник, останавливается без урона HP (как сейчас у `surveyingDevice` без записи);
луч HE-взрыва проходит его насквозь, как любой неброневой материал. Модули по-прежнему получают
урон через LAB-коробки/объёмы из скинов. Внутренние группы закрыты бронёй и ближайшими не бывают;
на практике это касается открытых групп (рубка Bat.-Chât. 155 55, открытый отсек M41).

## B. Роли экипажа в `<armor>` компонента

**VERIFIED**: корпус DickerMax — `commander, gunner_1, driver, radioman_1, loader_1`; корпус T40 —
`commander, driver, gunner_1, loader_1, loader_2`; корпус Object263 — те же пять ролей; башня
M10 Wolverine (`Turret_1_M10_Wolverine`) — `commander, gunner_1, loader_1`. Каждая запись:
броня `0` и локальный `vehicleDamageFactor 1.0` (в общем шаблоне экипажа 0.0). **VERIFIED**
(перепись): в их collision visual групп экипажа нет, поэтому записи есть, а треугольников нет.

Генератор (test_lab) строит для них записи из общего шаблона плюс локальные переопределения, ровно
как `_readArmor`; `vehicleDamageFactor` разрешён к переопределению и раньше. Записи попадают в
`material_kinds` компонента и в каталог шлюза; попасть в них нельзя (нет геометрии). Тестовая
броня TESTVEH проставляет им толщину, как и орудию 25, — на попадание это не влияет.

## C. `nodefullVisual`

**VERIFIED**: все 22 collision `.model` #717 с `nodefullVisual` (остальные 2500 — `nodelessVisual`)
принадлежат VK4502P и GB22_Comet (по 11). Ссылка равна стему. В visual узлы `Scene Root` (единичный)
→ `collision` (единичный) → `hull`/`turret_01`/`gun_01` со смещением (например, hull VK4502P
`(0, −0.9, 0)`), а `renderSet` привязан к одному `Scene Root`; `treatAsWorldSpaceObject false`.
**VERIFIED**: `boundingBox` visual совпадает с `visibilityBox` модели и содержит вершины mesh.

**INFERRED**: вершины лежат в рамке `Scene Root`, как у nodeless visual; смещения дочерних узлов к
этой рамке не применяются (иначе mesh вышел бы из собственного bbox). **UNKNOWN**: применяет ли
нативный BSP клиента/сервера узлы. Правило test_lab: `nodefullVisual` принимается, только если
render set привязан к одному `Scene Root`, других корневых узлов и render set нет, а mesh лежит в
bbox visual с допуском 1 мм.

## D. IS: дубликат в секции орудия

**VERIFIED**: в `/turrets0/IS-85/guns/_85mm_D-5T` два потомка `animateEmblemSlots` (`True` и `False`).
Это не броня и не коллизия; `<armor>` и `hitTester` уникальны. **INFERRED**: DataSection BigWorld
берёт первого потомка с именем, загрузчик 0.9.1 машину читает. Правило test_lab: при поиске нужной
секции посторонние дубликаты не мешают, сама нужная секция (`armor`, звенья пути) должна быть
единственной.

## E. Дефекты данных клиента

**Ch01_Type59_Gold.** **VERIFIED**: в `list.xml` — `notInShop`, тег `secret`, уровень 8; все модели
описания (`normal/lod0`, `collision`) указывают на `vehicles/chinese/Ch01_Type59_Gold/…`, а в
`vehicles_chinese.pkg` и других пакетах такой папки нет вовсе (есть только `Ch01_Type59`).
**INFERRED**: дефект клиентских данных — клиент #717 не может загрузить ни вид, ни коллизию этой
машины. Подставлять модели обычного Type 59 — выдумка; машина остаётся отказанной.

**T_50_2.** **VERIFIED**: в `list.xml` — `notInShop`, `secret`, уровень 5. Стоковая башня
`Turret_1_T_50_2` указывает и видом, и `hitTester` на
`misc.pkg!content/MilitaryEnvironment/mle060_HimmelBall/…/mle060_HimmelBall_04.model` (объект карты),
а орудие — на `HimmelBall/normal/lod0/Gun_01.model`. Коллизионный файл в `misc.pkg` существует,
поэтому **INFERRED** 0.9.1 загрузил бы как башню объект карты — это заглушка/дефект данных, а не
модель танка. У второй башни `Turret_2_T_50_2` есть нормальные `R70_T_50_2/collision/Turret_02` и
`Gun_05`. Машина остаётся отказанной; брать вторую башню как сток — решение владельца.

## Изменения

- `tools/ms1_contact_bundle.py`: `DEVICE_KINDS`, `DEVICE_EXTRAS`, `ALL_KINDS`; `_common_materials(...,
  kinds)` (по умолчанию прежний набор MS-1, экспорт MS-1 не меняется).
- `tools/p04m_battle_profiles.py`: `_effective(..., kinds)` (по умолчанию прежний набор).
- `tools/battle_any_profiles.py`: `KINDS` (test_lab — `ALL_KINDS`), `child_section`/`active_armor`,
  `visual_binding`/`inside_box`, раскрытие base64-имени группы.
- `server/gateway/src/shared/materials.rs`: `SourceClass::DeviceVisualMaterial` (тег провода 4),
  `device_kind_name`, `Catalog::from_generated` принимает виды 21–48.

## Проверка

- `python -B -X utf8 -m unittest tests.test_content0_collision_materials` — 8 OK (main и
  `WOT091_TEST_LAB=1`).
- Rust, `--features test_lab materials` — 11 OK, в том числе
  `content0_device_kinds_are_named_and_never_ordinary_plates`.
- Scratch-сборка обеих таблиц (`build()` в файл scratch, без `--update`): main байт-в-байт равна
  сборке базовой ветки; test_lab — 11 новых `generated`, остальные строки без изменений.
- Наборы `test_battle_any`, `test_p04m_battle_profiles`, `test_cat_nations`, `test_test_lab_flag`,
  `test_ms1_contact_bundle`, `test_shell_rules`: те же FAIL/ERROR, что на базе (нет `local/evidence`
  в worktree, таблицы базы не пересобраны).

NOT_RUN: пересборка закоммиченных таблиц/привязок/пинов и qualification физики (основная сессия),
бой с этими машинами, native-сверка попаданий в группы-устройства.

## Вопросы владельцу

1. Открытые группы-устройства (рубка Bat.-Chât. 155 55, отсек M41): сейчас снаряд, первым задевший
   такую группу, останавливается без урона HP. Оставить так, пропускать группу насквозь
   (`continueTraceIfNoHit` у экипажа true, у модулей false) или бить по модулю по этой геометрии
   вместо LAB-коробки?
2. T-50-2: взять `Turret_2_T_50_2` как сток test_lab или оставить машину отказанной?
3. Type 59 Gold: оставить отказанной (моделей в клиенте нет) — подтвердить.
