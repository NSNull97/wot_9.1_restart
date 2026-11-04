# SHELL-MECH — механика снарядов #717, этап 1

Дата: 2026-10-27. База `2da4baab9085b06a8d1e8156e2e1cc16e097d4b1`,
ветка `codex/shell-mech-research`. Цель — исследование и план; реализация,
merge в main и push **не входят** в этот этап. Глобальный GW-01 не заменён.
Предложенная очередь: [SHELL_MECH plan](../plans/SHELL_MECH.md).

**Результат:** наружная collision-геометрия, материалы, shell fields и клиентский
контракт декалей доступны. Полная внутренняя геометрия и серверные законы
пробития/HE/RNG этим клиентом не доказаны. Нынешние LAB-политики нельзя просто
переименовать в исторические. Приёмка исследования — **PASS_STATIC_RESEARCH**;
одобрение плана владельцем — **APPROVED** по дополнению ниже, native/UI/audio — **NOT_RUN**.

Дополнение владельца прочитано целиком:
`D:/WoT_9.1_Server/local/codex-tasks/APPROVAL-20261027.md`, SHA256
`5a48d89e828cd19941a4d67d777cd9b4a98264ea44c9706d0ab7503f8cdc6ae1`.
Оно разрешает переход к отдельным карточкам после принятия/слияния ARENA-01
и BATTLE-ANY, поднимает независимую часть SHELL-05 раньше и требует выбора
владельцем UNKNOWN-политик. Merge/push будущих карточек — только после native
PASS владельца и обязательных проверок. Исходное исследование сохранено в
`4cb7f77`; его результаты не заменяют проверки новой базы. Заявления документа
о копировании evidence/резерве независимо не проверялись, cleanup не разрешён.

## Сверка с main 04.11 (SHELLS-R)

Проверено чтением кода main `5816c24` и новым чтением оригинала. План карточки — в git на `a23e8eb:docs/plans/SHELLS_R.md`.
Номера строк шлюза в разделах ниже относятся к базе `2da4baa` (27.10); актуальные — в этой таблице.

| Утверждение 27.10 | На main 04.11 | Категория |
|---|---|---|
| Закон урона — одна пластина LAB: AP 5°/70°, APCR 2°/70°, HEAT 0°/85°, 2×/3×, придуманный HE, без RNG | Без изменений: `shared/p06t_damage.rs` `resolve_direct`, `attenuated_he`; пробитие линейно 100→500 м (`penetration`) | VERIFIED source |
| Ходовая сервером не покрыта | Без изменений: `geometry.rs` `impact_segment` (686) отвергает mesh `Chassis` (тест 1473) | VERIFIED source |
| HEAT lossFactor 0.05 загружается | Загружается в данные (`p06t_damage_tests.rs:33`), в законе не используется — второго слоя нет | VERIFIED source |
| `damageStickers` всегда пуст | AV-01 (`329643e`): `av01_feedback.rs` — stickerID из `targetStickers`, точка из `showDamageFromShot`, `MAX_STICKERS=30`; `server.rs:2739–2790` — последние 30 разных кодов цели, только видящим | VERIFIED source; политика проектная |
| Восстановление декалей при hide/reveal | Выход из AoI сбрасывает `stickers_sent` (`mod.rs:325,339`), при возвращении шлётся текущее состояние | INFERRED из кода; native NOT_RUN |
| WT 128: барабан 6, 2 с, 60 с; 150: 4, 3 с, 50 с | `p06t_shell_data.rs:65,70`; генерируемый реестр — тест `agents_invariants_wt_drum_six_and_fv_hesh_275`, `generated_wt_fv_match_closed_kinds`; `armament.rs:36` отвергает clip > 6 | VERIFIED source + тест |
| FV215b (183) HESH 275/275, HIGH_EXPLOSIVE, id 82, gold | `p06t_shell_data.rs:77` (compact 21082, 1750/244, R 5.05) | VERIFIED source + тест |
| Калибр HESH 182.9 (строка, `readInt`) | Сервер хранит `caliber_mm: 182.9`; результат движка NOT_RUN | UNKNOWN |

Новое чтение оригинала 04.11 (`local/evidence/shell-mech-shells-r-20261104/`, тот же инструмент, PowerShell — в Git Bash
аргумент `/clip` превращается в путь Windows и выбирается 0 полей): `waffentrager_e100.xml` SHA `6d8de10e…`
128 мм reloadTime 60 [6327,6328), clip/count 6 [6383,6384), rate 30 [6384,6385); 150 мм 50 / 4 / 20 [7005…7061).
`uk/components/guns.xml` SHA `4214df56…` `_183mm_HESH/piercingPower` 275 275 [29741,29748); AP 310 300, HE 92 92.
`uk/components/shells.xml` SHA `3dee7c09…` `_183mm_HESH` id 82, kind HIGH_EXPLOSIVE, caliber `182.9`, radius 5.05,
damage 1750/244, gold-узел есть. Всё совпадает с отчётом 27.10 и данными сервера.

### Shell Mechanics 2.0 — принятая конфигурация владельца (04.11, заменяет политику v1)

Владелец 04.11 передал [SHELL_MECHANICS_2_0](../decisions/SHELL_MECHANICS_2_0.md) («файл с принятыми конфигурациями»,
SHA256 `ebc38044512a5972071be97f49650028bbaa96df7463dc6a9a1f89b2e6c661bb`). Это проектный профиль **Classic+** поверх
базы 0.9.1, а не восстановленный закон оригинального сервера; числа, помеченные в нём экспериментальными, не считаются
балансом. Политика v1 (ответ «Yes, recommended» на решения 1–8, в git на `0273dc9`) заменена там, где они расходятся:

| v1 | Shell Mechanics 2.0 | Что это значит для работ |
|---|---|---|
| 1 рикошет/нормализация по заметкам 8.6/8.9 | Исторические правила 2, 3 и **10** калибров, сверка именно с 0.9.1, локальная нормаль и остаток на каждом слое | Правило 10 калибров (внутренняя трассировка) — новое; точные углы/порядок #717 по-прежнему UNKNOWN, нынешние значения — `requires_verification` |
| 2 разброс ±25 %, равномерный | ±25 % для пробития и HP, один бросок пробития на выстрел | Распределение в 2.0 не названо: равномерное остаётся `requires_verification` |
| 3 линейно 100→500 м | Падение пробития по параметрам конкретного снаряда; HEAT/HE/HESH не теряют | Совпадает по смыслу; закон между двумя значениями снаряда — `requires_verification` |
| 4 HEAT −5 %/10 см | «Собственная модель разнесённой брони» HEAT | Совместимо; сохраняется как `requires_verification` |
| 5 HESH = HIGH_EXPLOSIVE | **HESH — отдельный тип в данных сервера**, свои параметры, штраф на экранах, слабее сплэш | В клиенте #717 kind остаётся HIGH_EXPLOSIVE (VERIFIED), клиент показывает его как HE; тип HESH — только серверный, номинал 275 сохраняется |
| 6 LAB-объёмы модулей | Классика 0.9.1: свои HP модулей, пороги, ремонт, независимость от урона корпусу, шансы из данных 0.9.1 | HP/шансы/maxRegen берутся из клиента (VERIFIED данные); сами внутренние объёмы в клиенте отсутствуют — остаются LAB |
| 7 калибр 182.9 | — | Проверка в SHELL-01 без изменений |
| 8 декали AV-01 | — | Без изменений |
| — | **Dual Dispersion 2.0** (75 % в внутренней зоне, k(A) — эксперимент) | Проектная механика, не историческое распределение (AGENTS: разброс до 9.6 — отдельное исследование) |
| — | Экраны для HE/HESH с остаточным пробитием, Limited Splash, однослойные разрушаемые препятствия, тестовый профиль САУ (1 на команду, ×1.25, ×1.10) | Новые карточки; формулы в 2.0 — кандидаты |
| — | Слои конфигурации, неизменяемый снимок боя (`configVersion`, `rulesHash`), трасса каждого выстрела, детерминированный повтор | Отдельная карточка до SHELL-02 |

Сайт-симулятор из 2.0 не публикуется без разрешения владельца.

### Очередь карточек (по Shell Mechanics 2.0, 04.11)

| Карточка | Результат |
|---|---|
| SHELL-01 — броня целиком | Ходовая (гусеница — отдельный модуль с коллизией), все слои Hull/Turret/Gun/Chassis по порядку вдоль луча, локальные нормали, материалы «нет записи / armor 0 / factor 0», проверка калибра 182.9 |
| SHELL-CFG — профиль правил | Слои конфигурации 2.0, валидация, `configVersion`/`rulesHash`, неизменяемый снимок на бой, трасса выстрела и повтор |
| SHELL-02 — пробитие по слоям | Нормализация, 2/3/10 калибров, рикошет, остаток по слоям, один бросок ±25 %, падение по снаряду |
| SHELL-03 — HE и HESH | HESH отдельным серверным типом, экраны с остаточным пробитием, Limited Splash, без суммирования по поверхностям |
| SHELL-04 — модули и экипаж | HP/пороги/шансы из данных 0.9.1, независимо от HP корпуса; объёмы LAB |
| DISP-01 — Dual Dispersion 2.0 | Внешний круг классики, внутренняя зона 75 %, статистические прогоны ≥ 100 000 |
| ENV/SPG | Однослойные препятствия; тестовый профиль САУ |

### Варианты, предложенные владельцу

В клиенте #717 закона сервера нет. Ниже — что известно и варианты; любой выбор — версионируемая проектная политика,
а не «исторически точно».

1. **Рикошет, нормализация, перекрытие калибром.** Сейчас (LAB): AP 5°/70°, APCR 2°/70°, HEAT 0°/85°, нормализация ×1,4·калибр/броня
   при калибре ≥ 2× брони, рикошет невозможен при калибре ≥ 3× брони. Согласуется с официальными заметками 8.6 (APCR 5→2) и 8.9
   (HEAT 80→85, исключение 3× для HEAT убрано). (а) оставить как политику v1 «по заметкам 8.6/8.9»; (б) другое.
2. **Разброс урона и пробития.** VERIFIED только ±25 % (загрузчик и окно параметров). Распределение UNKNOWN. (а) равномерное в
   ±25 %, отдельные броски для урона и пробития, один бросок пробития на выстрел; (б) нормальное с обрезкой на ±25 %; (в) без разброса.
3. **Потеря пробития с дистанцией.** У снаряда две цифры пробития; сейчас — линейно от 100 до 500 м (LAB). Для HEAT/HE потери нет.
   (а) оставить; (б) другое.
4. **HEAT после экрана.** Заметки 8.6: −5 % за каждые 10 см после пробития экрана, гусеницы — экран. Линейно или от остатка — UNKNOWN.
   (а) линейно от начального пробития; (б) от остатка.
5. **Фугасы и HESH.** Сейчас придуманная формула `floor(max(0, 0.5·урон·(1−d/R) − 1.1·броня))`. HESH в #717 — обычный
   HIGH_EXPLOSIVE (275 мм — номинал, не гарантия). Нужны: урон непробившего фугаса, сплэш по расстоянию, преграды, экраны.
   Варианты сформулирую в SHELL-03 с таблицей; сейчас — только подтвердить, что HESH остаётся HE без отдельной механики.
6. **Модули и экипаж.** Внутренних объёмов двигателя, БК, баков и мест экипажа в клиенте нет (поиск по 374 описаниям и
   именам collision). (а) проектные объёмы, помеченные как LAB, как сейчас; (б) отложить историческую приёмку модулей.
7. **Калибр 182,9.** В XML строка `182.9`, загрузчик читает её `readInt`; что вернёт движок (182 или 183) — NOT_RUN.
   От этого зависят границы 2×/3×. Предлагаю проверить на копии клиента в SHELL-01, решения не нужно.
8. **Декали (AV-01, принято 29.10).** Политика «последние 30 разных кодов на цель, только видящим цель» выбрана в AV-01,
   не историческая. (а) оставить; (б) другая.

## Источники, категории и адреса

Оригинал только читался: `C:/WoT_0.9.1_RU_0717_original`.
`version.xml` содержит `v.0.9.1 #717`, RU. Новый полный manifest всего клиента
не снимался; заново проверены перечисленные файлы/пакеты, а не весь каталог.
Полный старый manifest из project.local.json не выдаётся за новый результат.

- **VERIFIED** — конкретные исходные байты/поля/инструкции и проверенные pins;
  это не означает подтверждения поведения недоступного оригинального сервера.
- **OBSERVED** — выполненный статический parser-аудит в Windows/Python3.14.3.
  Новых наблюдений работающего клиента или сервера нет.
- **INFERRED** — явно обозначенный вывод из данных, который ещё можно опровергнуть.
- **UNKNOWN** — отсутствует достаточное доказательство; также явно указан scope поиска.

XML offsets — десятичные raw file bytes, нумерация с нуля, полуинтервалы `[a,b)`.
Bytecode `+N` — offset внутри `co_code` названного метода; начало marshal-record
указывается отдельно и включает 8-байтовый PYC header. ZIP local-header offset
не равен offset внутри распакованного member. SHA всегда подписан по представлению.
Пустой диапазон значения Packed XML может означать присутствующий false/zero/empty.

Все новые evidence находятся в **этом worktree**:
`C:/Users/NSNull/.codex/worktrees/shell-mech-research/WoT_9.1_Server/local/evidence/`.
Ниже E-A = `shell-mech-armor-20261027-01`, E-R = `shell-mech-rules-20261027-01`,
E-D = `shell-mech-decals-20261027-01`, E-S = `shell-mech-source-20261027-01`,
E-V = `shell-mech-validation-20261027-01`. Это не общий `D:/.../local`.
Raw disassembly/декодированные ресурсы остаются ignored и не публикуются в Git.

Основные source pins (пути относительно оригинала):

| Код | Файл | SHA256 |
|---|---|---|
| V | res/scripts/common/items/vehicles.pyc | `805240e4b59d8a75950dbb97b41c17867606e7e96d7ff0c8d7b05312b83ae8b6` |
| M | res/scripts/common/modelhittester.pyc | `e5d51bdc1a7eadfb55d38b53e93748bee2dd78fd19554e18c519ee7a14d40726` |
| C | res/scripts/item_defs/vehicles/common/vehicle.xml | `599ea82e48e98bf9a00c10256030097da31ce5d5889fa03737bc3b79230d256a` |
| W | res/scripts/item_defs/vehicles/germany/waffentrager_e100.xml | `6d8de10ed31cb908738ca9b32935aacfe01fec78d47239dadbd86713cba052e2` |
| F | res/scripts/item_defs/vehicles/uk/gb48_fv215b_183.xml | `ffbe8c9bbffbddf61d9197ce0cd4d4d79b6e0a6bfcbf2846c10fc31dd38f6712` |
| G | res/scripts/item_defs/vehicles/uk/components/guns.xml | `4214df566a69b23e92f339f0a157bb89145a41a90ea7ce1db7762496342028cd` |
| S | res/scripts/item_defs/vehicles/uk/components/shells.xml | `3dee7c0961b050bf78d3954f85813ad62beb57d1d3e33b4d0738ab3dbf62cbac` |
| CV | res/scripts/client/vehicle.pyc | `b81d08ca14092bb8912adb2eff20325c3dd23424868bc03164cfe6b8da50463c` |
| VE | res/scripts/client/vehicleeffects.pyc | `61b91aed672d8dfe7e4329b000e04c4be396b68e8cfe9a02c6c3ab57c9281756` |
| VS | res/scripts/client/vehiclestickers.pyc | `b0fa1e983227b56e26b963215051ae0b0b7f3fbe9f4f367d1ddbf916399843f6` |
| DS | res/scripts/item_defs/vehicles/common/damage_stickers.xml | `d620d6741760e2a885085949b3370a9cda9b6ef47facbd31bfbf72e46b0c47ee` |
| FX | res/scripts/item_defs/vehicles/common/shot_effects.xml | `738cab95f623d7cabd8aaf811c6395ebf731a6b632e259c01dad31a2172525d3` |
| DEF | res/scripts/entity_defs/vehicle.def | `08dc1e6be577f80a04bf813ca046550201a3c4e673dad1540c5f1c6a047d1297` |

Bytecode прочитан как данные существующим `py27_static`; magic `03f30d0a`.
Opcode declarations прочитаны из разрешённого
`D:/WoT_9.1_Server/local/toolchains-py27-20261019/cpython-2.7.3-x86/Lib/opcode.py`,
raw SHA `620c2ea086354a4e3b445578d6fa005e944bfdddaf0791b19e1e9856ab41b7cf`.
LF-normalized SHA `acfe212847ecb81ca28bdab976a3caacff3568b45a9e8ca78d6957f9f3ef4884`
совпадает со старым vendor pin; raw pin не подменялся normalized-хешем.
Код клиента не импортировался/исполнялся; unsafe object deserialization не использовалась.

## Поправка к предпосылкам ТЗ и текущий runtime

**VERIFIED source:** броня уже не целиком AABB. `shared/geometry.rs:415`
(`Bundle::proxy_ray`, проверки427–435) использует первый настоящий source triangle,
material, pose/revision; AABB даёт дальнейший выход из компонента.
`shared/p06t_lab_proxy.rs:1,25,39` содержит придуманные **внутренние** объёмы
модулей/мест экипажа и nearest-two, а не замену наружной armor mesh.
SHA geometry `6dc8643de99abd680c55a792883a63c86e1583527be5c50db14186b57e15e246`,
proxy `348feb16516dc191693d4eee4a9c0c30b6d7a4cd48e78fb1ea056b2c9671dc47`.

`shared/p06t_damage.rs:44–86` действительно содержит single-plate AP5/70,
APCR2/70, HEAT0/85, LAB2×/3× и фиксированный nominal damage. HE attenuation
строки48–55 — явная придуманная формула с коэффициентами0.5/1.1 и floor;
исторический damage/penetration RNG в этом resolver отсутствует. Это текущие
исходники, не доказательство исторического закона; поздние fire RNG не равны P/D RNG.

`shared/wire.rs:188` и `arena/vehicle.rs:208` пишут property6 `damageStickers`
как пустой i32 count. В исследованных publishers постоянное состояние декалей
не найдено. `shared/server.rs:2136–2172` публикует non-HE shot impact и HE splash;
это доказывает код публикации, но свежая native-визуальная проверка **NOT_RUN**.
Source SHA этих файлов сохранены в E-D/receipt.json. Все runtime-файлы неизменны.

## Независимость SHELL-05 и порядок после одобрения

Новый анализ зависимостей использует сохранённое исследование, без реализации.
Evidence: собственный `local/evidence/shell-mech-independence-20261027-01/`.
`dependencies.json` закрепляет решение, refs, команды, head-документы веток
и SHA прочитанных runtime-файлов; `decals-independence.md`/`decals-receipt.json`
содержат независимый read-only обзор. Время снимка записано в UTC.

**VERIFIED Git:** локальный/удалённый main
`2da4baab9085b06a8d1e8156e2e1cc16e097d4b1` совпадают;
ARENA-01 `356bea85106e583347094dc12579d4e7cb0a5f20` и BATTLE-ANY
`387a3b1b180161ce550f3b217dbeb239f8f11948` не являются его предками.
Обе проверки `git merge-base --is-ancestor <head> <main>` дали exit1,
ahead5/1. **Ни одна требуемая карточка не слита**; имя ветки/общая старая
база готовностью не считаются. Main пока прежний, обновления своей базы на
непринятые ветки-кандидаты нет.

**VERIFIED содержание документа, не повторная приёмка:** BATTLE-ANY на этом
head описывает stage1 — генератор, отсутствие runtime consumers,
`battle_admission=false` и native NOT_RUN. Перед стартом проверить финальное
принятое состояние карточки, а не только возможный merge stage1.
Native-приёмка этих веток самостоятельно не подтверждена.

| Часть | Независимость от SHELL-01..04 | Source anchor и ограничение |
|---|---|---|
| StickerId/ShotOutcome, packed segment, full ARRAY framing | **INFERRED: да**, зависит от #717 schema/decoder | DEF/VE; `impact_wire.rs:85–167` отделяет codec от damage. Original inverse rounding UNKNOWN; для первого codec вход уже квантован |
| Current state, add/remove, create/reveal | **INFERRED: да**, не вычисляет попадание/урон | CV set_damageStickers/startVisual; `wire.rs:179–191` пока пустая property6. Нужны actor+arena identity/config и snapshot revision |
| Hide/reveal/rejoin | **INFERRED: да** относительно damage laws; **зависит от ARENA/BATTLE integration** | `shared/mod.rs:215–335` проверяет creation ACK/epochs, сбрасывает sent caches, повторяет privacy-check перед enqueue; тот же `shared/mod.rs:365–380,719–731` начинает с актуальных event cursors |
| Доставка существующих transient effects | **INFERRED: да**, outcome уже определён сервером | `server.rs:2077–2201`, show_damage_shell/explosion; сохранять current observer/tracer/epoch gates и не воспроизводить прошлые эффекты |
| Автоматический gameplay producer/накопление | Новых damage laws не требует в узком прежнем LAB, но **нужен выбор явной presentation policy** | Клиентские mappings не устанавливают original producer/rounding/cap/eviction; не копировать hitEffectCode как stickerID |
| Новые layered/chassis/HE/internal module/crew outcomes | **Нет**, нужны соответствующие SHELL-01..04 | Presentation не создаёт отсутствующее доказательство попадания/пробития/critical |

**Решение порядка по поручению владельца:** первой после внешних merge идёт
SHELL-05A — typed native protocol, current snapshot и доставка уже существующих
эффектов. Затем SHELL-01→02→03→04 и зависимые адаптеры SHELL-05B; узкий producer
прежнего LAB можно рассмотреть отдельной карточкой после05A/выбора политики,
не ожидая новых damage laws. Архитектурная независимость не является native PASS.

Первая05A принимает явный server-owned snapshot с уже квантованными сегментами
на новом разрешённом стенде. Реальный клиент должен подтвердить add/remove,
положение на component, hide/reveal/rejoin и отсутствие replay transient events.
Это **protocol fixture**, не приёмка автоматической игровой декали/исторического
урона. Mocks/самостоятельный codec round-trip без native карточку не закрывают.
Не меняются HP/ammo/RNG/HE/overmatch и admission машин.

**VERIFIED source lifecycle:** `shared/model.rs::attach_loadout_fire` сохраняет
того же actor с проверкой identity/loadout; rejoin относится к живому World.
`tools/p08b_owner_hold_store.py:25` задаёт per_shot_wal=False/aborted_restart;
после process restart живые actor/marks не обещаются. Current marks очищаются
при teardown/new World, не немедленно на Finished, пока показывается wreck.
`fresh_battle` pristine guard должен охватывать новое state. Перенос на
detached turret — отдельное native-доказательство, не следствие обычной смерти.
Полные file SHA/line anchors — decals-receipt.json и записка независимого обзора.

Перед автоматическим producer остаётся выбор владельцем версии политики:
LAB-only либо новые resolver outcomes; first-N/FIFO/source-priority retention;
derived quantizer либо дополнительное измерение; recipient filtering либо
отдельно одобренное раскрытие local marks; обычный Vehicle либо detached lifecycle.
Ни один вариант/лимит сейчас не назначен. Декаль может раскрыть направление
скрытого выстрела: прежние ограничения видимости нельзя незаметно расширить.

**Дополнение: PASS_DEPENDENCY_ANALYSIS; реализация WAIT_DEPENDENCY_MERGES.**
Runtime не менялся. Unit/gateway/native этой будущей карточки **NOT_RUN**;
23 прежних parser tests относятся к исследованию `4cb7f77`, не к новому gameplay.

## Броня, collision и материалы

**VERIFIED:** descriptor `hitTester/collisionModel` → `.model/nodelessVisual`
→ `.visual` primitive groups/material IDs → `.primitives` sections
`vertices`, `indices`, `bsp2`, `bsp2_materials`. `.model`/`.visual` — Packed XML,
а выбранные `bsp2_materials` — обычный XML с упорядоченными `<id>`.
Толщина берётся из component-local `armor/<name>`, flags/defaults — C.
Одинаковое `armor_1` разных компонентов не означает один материал.

В девяти исследованных WT/FV mesh: position FLOAT3 от `vertices.offset+68`,
stride32; indices от `indices.offset+72`, UINT16 `list`, затем 16-byte groups.
WT имеет `xyznuvtb`, FV `xyznuv`; оставшиеся байты xyznuvtb не объявлены FLOAT5.
Неизменённый `p06t_combat_geometry.load_source(original)` перепроверил свои pins,
18 members шести Hull/Turret/Gun mesh и source dependencies; затем отдельно разобран chassis.

| Полный пакет | Размер | SHA256 |
|---|---:|---|
| res/packages/vehicles_german.pkg | 1311954316 | `e8dc6afeab9a825a2b9a947f538df6eb4dba80a4c65ed76d1b3eac8cf690580d` |
| res/packages/vehicles_british.pkg | 792056018 | `300f9961160e5b55207f3d47ae1fd7a4082f44fb7dab1febd1fa1dc4d29211d3` |

| Машина / компонент | Вершин / треугольников | Проверенное различие |
|---|---:|---|
| WT Chassis | 374 / 296 | rightTrack24/leftTrack23, броня40/40 |
| WT Hull | 239 / 122 | component armor groups |
| WT Turret_01 | 280 / 189 | восемь local armor records |
| WT Gun_01 (128) | 631 / 238 | gun25:96 triangles; gunBreech31:142 |
| WT Gun_02 (150) | 648 / 240 | отдельная модель орудия |
| FV Chassis | 92 / 80 | rightTrack24/leftTrack23, броня25/25 |
| FV Hull | 257 / 150 | optics28 mesh есть, local record отсутствует |
| FV Turret_01 | 667 / 382 | то же различие missing/zero для optics |
| FV Gun_01 | 160 / 82 | gun25 и armor_1 |

Chassis в native component list есть, прежний серверный Bundle покрывает только
Hull/Turret/Gun. Это конкретный пробел будущего SHELL-01.
WT member `vehicles/german/G98_Waffentrager_E100/collision/Chassis.primitives`,
SHA `3002ff10b4e42e63f8e65315f16b3851ee215cb3615609e9ed68d34856b76c3a`:
vertices `[4,12040)`, indices `[12040,13920)`, bsp2 `[13920,29428)`,
materials `[29428,29524)`.
FV member `vehicles/british/GB48_FV215b_183/collision/Chassis.primitives`,
SHA `12c201779d19050160d530c6d44fff14cfcc79ef958a541a3a1132b830e0dd3f`:
vertices `[4,3016)`, indices `[3016,3600)`, bsp2 `[3600,7460)`, materials `[7460,7556)`.
Все ZIP offsets, individual member SHA и groups — E-A/run03/package-census.json.

**VERIFIED поля:** W track armor40 находится `[4607,4608)`/`[4608,4609)`;
F track armor25 `[4105,4106)`/`[4106,4107)`.
F `/hull/armor/armor_14`: armor6 `[2687,2688)`, vehicleDamageFactor0 `[2688,2691)`;
F `/turrets0/Turret_1_GB48_FV215b_183/armor/armor_10`: armor50.8 `[4818,4822)`,
factor0 `[4822,4825)`. Exact indexed paths — E-A/selected-xml-offsets.json.
**INFERRED:** это кандидаты экранов/масок, требующие следующего контакта луча.
Один factor0 не доказывает всю семантику spaced armor.

V `_readArmor` (record87331, +0,+217..253,+668..681) начинает пустую таблицу,
копирует common record только для явно перечисленных local материалов и применяет
overrides. `_readGunLocals` (78355, +1618..1633,+1833..1842) заменяет local armor.
Поэтому missing material, armor0 и armor>0/factor0 различны; FV optics28 нельзя
незаметно превратить в броню0. WT gunBreech31 имеет source geometry и
armor0/factor1/useHitAngle=true, gun25 — другой материал с armor20/factor0.

V `getHitTesters` record20469/+0..89 перечисляет chassis,hull,turret,gun.
`_readHitTester` record90398/+40..64 создаёт ModelHitTester и вызывает
loadBspModel при IS_CELLAPP. M loadBspModel record1386/+19..43,+77..89 использует
native WGBspCollisionModel и bbox; localHitTest record2118/+0..18 делегирует
native collideSegment. В CV getComponents record12995 и collideSegment13883
видны component transforms/material lookup. Реальное соответствие нашего
triangle query нативному BSP для новых chassis **UNKNOWN/NOT_RUN**.

## Модули и экипаж

**VERIFIED:** C хранит MaterialInfo для engine/ammoBay/fuelTank/radio/tracks/gun/
gunBreech/optics/crew roles, extras, damageKind, flags и chances. Примеры:
engine projectile chance0.45 `[12017,12021)`, ammoBay0.27 `[12120,12124)`,
commander0.33 `[13049,13053)`, explosion0.15 `[13053,13057)`;
leftTrack factor0 `[12420,12423)`, useHitAngle=false `[12423,12423)`,
collideOnceOnly=true `[12423,12424)`; gunBreech extra gunHealth `[12703,12712)`.
Это данные, не доказательство механики save throws, критического порога или RNG.

Bounded census: **374 descriptors + 7 list.xml**, 2826 hitTester/collisionModel
ссылок; семь plain customization.xml исключены явно. Crew поля задают роли,
повторные loader seats, не координаты. По шаблонам
`enginePosition|ammoBayPosition|fuelTankPosition|hitbox|hitBox|internal`
совпадений нет. Среди имён1893 German и969 British collision members нет
самостоятельных engine/ammoBay/crew моделей. В девяти WT/FV mesh нет их
material IDs, но tracks/gun/gunBreech/optics присутствуют.

**UNKNOWN:** исторические внутренние объёмы двигателя/БК/баков/радио и мест
экипажа. Остальные meshes, native BSP внутренности и иной способ сериализации
полностью не исследованы. **INFERRED:** полные объёмы могли быть server-only;
это не установленный факт. Внешняя геометрия части устройств и именованные
MaterialInfo не доказывают наличие всей внутренней модели в клиенте.

**SHELL-02, полная перепись collision-visual (04.11, `tools/collision_device_census.py`,
`local/evidence/shell-02-census-20261104-01.json`).** VERIFIED: все **2522** `*/collision/*.visual` семи
пакетов машин, `materialKind` каждой primitiveGroup через закреплённый `material_kinds.xml`. Группы
материалов-устройств (engine 21, ammoBay 22, turretRotator 26, fuelTank 29, radio 30, экипаж 41–48) есть
только в **5** visual четырёх машин: `A18_M41` Hull (полный набор), `F67_Bat_Chatillon155_55` Turret,
`G73_E50_Ausf_M` Hull+Turret, `R59_A44` Hull (только turretRotator). Все четыре отказаны в боевом реестре
(M41 и Bat.-Chât. 155 55 — SPG, E-50M — SUPPORT_SOURCE_UNRESOLVED, A-44 — материал turretRotator).
**Ни у одной из 232 боевых машин внутренних объёмов в клиенте нет.** INFERRED: эти пять — остатки
разработки, а не рабочая модель 0.9.1; формат допускает объёмы в collision-модели, но для боевых машин
они UNKNOWN (возможно, только на сервере). Следствие: внутренние модули остаются LAB-коробками; частое
уничтожение БК — артефакт LAB-коробки (большая центральная коробка `[0.25..0.75]×[0.25..0.75]×[0.4..0.65]`,
две ближайшие, урон модулю без шанса), а не исторический факт. VERIFIED данные `chanceToHitByProjectile`
(ammoBay 0.27, engine 0.45 и др.) LAB-путь не применяет: их смысл в серверной механике UNKNOWN — решение
владельца (SHELL-04).

**SHELL-02, гусеницы в живом попадании.** VERIFIED: в клиентском байткоде `collideOnceOnly`,
`continueTraceIfNoHit`, `vehicleDamageFactor` встречаются только в загрузчике `vehicles.pyc`
(`_readMaterials`); ASCII-поиск в `WorldOfTanks.exe` их не находит. Клиент не решает, что происходит со снарядом
после гусеницы. Данные гусениц VERIFIED (общий `vehicle.xml` + локальная броня): `vehicleDamageFactor` 0,
`useHitAngle` false, `mayRicochet` false, `collideOnceOnly` true, `chanceToHitByProjectile` 1.0, броня
5–40 мм. Правило LAB `test_lab.shell02.track-spaced-nominal-armour.v1` (INFERRED из этих флагов и заметок
8.6 «гусеницы — экран»): модульное попадание по гусенице уроном `device_damage` без урона HP; одна запись
на гусеницу за выстрел (`collideOnceOnly`); номинальная броня гусеницы снимается с пробития без угла и
рикошета; остаток ≤ 0 — снаряд остановлен; HE взрывается на гусенице; остаток идёт в корпус обычным
законом. Потеря HEAT за экраном (8.6) не применяется — вопрос 4 владельцу.

## Снаряды, углы, HEAT, HE/HESH и разброс

V `_readShell` record84021, co_code SHA
`463526a3bb33827beefb5d95356567a7d9c602471370f38d7ab4cf5b0076a759`:

| Bytecode offsets | VERIFIED действие loader | Чего это не доказывает |
|---|---|---|
| +142..155 | defaults damageRandomization/piercingPowerRandomization =0.25 | распределение RNG и серверное округление |
| +403..413 | guard `!IS_CLIENT || IS_DEVELOPMENT` | наличие этих значений в release client |
| +416..498 | AP-prefixed kind: radians(normalizationAngle), cos(radians(ricochetAngle)) | конкретные AP/APCR углы и порядок overmatch |
| +502..579 | HEAT lossFactor×10.0, cosine ricochetAngle | точка начала distance loss, linear/compound, layered order |
| +586..658 | HE explosionRadius; fallback caliber²/5555 для неположительного radius | HE HP/осколочная формула |

`_readShot` record85706, +139..160 читает penetration pair; +161..216
масштабирует speed и gravity через factor/factor²; +217..238 читает maxDistance.
Это descriptor loader, не penetration resolver. V module +1380..1398 допускает
пять kinds, включая `ARMOR_PIERCING_HE`; **569 release shell rows семи наций**
содержат четыре (AP/APCR/HEAT/HE), APHE среди них нет, HESH отдельного kind нет.
Все49 HEAT rows имеют distance-loss field `0.05`; во всех семи shells.xml нет
normalizationAngle/ricochetAngle/randomization overrides. Scope — эти семь
файлов, не весь native binary и не оригинальные server resources.

**VERIFIED UI:** `parameterscache.pyc`, SHA
`e5aa176b58c059d17287b7cde2f41786bd3bc87d57d4431a5c3b275bf84925a4`,
`_ParametersCache.__calcShellParams` record10947, +51..136/+139..240 считает
`round(P0±P0*rP)` и `round(D±D*rD)`. Поэтому отображаемые границы ±25%
подтверждены. Client random.choice для decal texture к этому RNG отношения не имеет.
Ограниченный поиск перечисленных имён по **1081 pyc / 9 083 662 bytes** дал
loader/UI и два ложных THESHOLD-совпадения; sampler P/D не установлен.
**UNKNOWN:** uniform/Gaussian/truncated, включение концов, per-shot/per-layer draws,
P/D correlation, seed/order, серверное округление. Разброс точки попадания до9.6 —
отдельная задача, его распределение здесь не устанавливалось.

Исторические официальные release notes перепроверены 2026-10-27 поисковой
выдачей; прямые открытия показали anti-bot page. Исторический HTML snapshot/hash
не получен. **VERIFIED как содержание доступной индексной выдержки**, перенос
в полный solver #717 остаётся **INFERRED**, точные операции/границы — UNKNOWN:

- 8.6: APCR normalization5→2; HEAT loss5% за10см после пробития, tracks как
  spaced armor. Из этих слов нельзя выбрать linear/compound и весь порядок
  операций. [Официальные notes8.6](https://worldoftanks.eu/fr/content/docs/release_notes/release-notes-86/).
- 8.9: HEAT ricochet80→85, исключение3× удалено. Устаревшее80 из8.6 не переносить.
  [Официальные notes8.9, 31.10.2013](https://worldoftanks.com/en/content/docs/release_notes/89-update-notes/).
- 9.3: продолжение движения после рикошета объявлено новым поведением вместо
  исчезновения. Это ограничение против переноса более поздней механики;
  внутренние повторные контакты #717 полностью не описаны.
  [Официальное объявление9.3, сентябрь2014](https://worldoftanks.eu/en/news/general-news/version-93-announcement/).

## Обязательные инварианты конкретных модулей

Все строки ниже **VERIFIED SOURCE**, а не измерение таймеров/исходов попадания.
W prefix `/turrets0[1]/Turret_1_Waffentrager_E100[1]/guns[1]/`:

| Mount | Поле | Значение | Raw offsets в W |
|---|---|---:|---|
| _128mm_K44_2_L61 | clip/count | **6** | [6383,6384) |
| тот же | clip/rate; reloadTime | 30;60 | [6384,6385);[6327,6328) |
| _150mm_Rohr_L38 | clip/count | **4** | [7059,7060) |
| тот же | clip/rate; reloadTime | 20;50 | [7060,7061);[7005,7006) |

V `_readGunClipBurst` record81550/+28..54 вычисляет60/rate: source-derived
межвыстрельные2с/3с. Mounted overrides имеют приоритет над shared gun reload;
значение6 не распространяется на150мм. German gun IDs90/91; nation1 → compact
23060/23316. IDs подтверждены GERMANY guns SHA
`4b2c18c233fcdbb1102792d5962b9a35a1dc237b7f49e0dbe5bed498747851c8`, offsets4067/4068.

F mount `/turrets0/Turret_1_GB48_FV215b_183/guns/_183mm_AT_Gun` ссылается на shared.
G `/shared[1]/_183mm_AT_Gun[1]/shots[1]/_183mm_HESH[1]/piercingPower[1]` =
**`275 275`**, `[29741,29748)`. В том же орудии AP310/300 и обычный HE92/92.
S `/_183mm_HESH[1]`: id82 `[13344,13345)`, price20 `[13383,13384)`,
**присутствующий gold-node** descriptor13379, kindHIGH_EXPLOSIVE `[13384,13398)`,
radius5.05 `[13403,13407)`, damage1750/244 `[13443,13445)`/`[13445,13447)`.
Raw caliber — строка182.9 `[13398,13403)`, но loader вызывает `_xml.readInt`;
конверсия native ResMgr здесь **NOT_RUN**, загруженный integer-калибр не угадан.
UK gun54/nation5 → gun13908, shell82 → compact21082. Compact formula V
makeIntCompactDescrByID record53456/+0..32: `(id<<8)+(nation<<4)+itemType`.
275 — номинал конкретного premium HESH, не гарантированное пробитие275мм.

## DamageStickers и эффекты

DEF `/Properties[1]/damageStickers[1]`: ARRAY of UINT64, ALL_CLIENTS.
VE `DamageFromShotDecoder.decodeSegment` record18440, co_code SHA
`c474cdb0d5dd292c83967876fb090010460e047a73d3cecf14879ee27934b056`:

| Bits UINT64 | Значение |
|---|---|
| 0..7 | **stickerID** для property; **hitEffectCode** для showDamageFromShot |
| 8..15 | component index: chassis0,hull1,turret2,gun3 |
| 16..23 /24..31 /32..39 | XYZ начала bbox-local segment |
| 40..47 /48..55 /56..63 | XYZ конца segment |

Extraction +0..11, shifts +244/+288; genexpr record18868/+15..33 декодирует
`bbox.min + extent*byte/255`. +305..336 расширяет оба конца на1% длины.
**UNKNOWN:** original server inverse rounding и выбор этого сегмента.
Копировать shot-event UINT64 в property нельзя: hitEffectCode3 означает
penetration, а stickerID3 — medium_ricochet.

CV `set_damageStickers` record8752/+18..145 сравнивает frozenset текущего и
предыдущего массивов, удаляет исчезнувшие и добавляет новые. `startVisual`
record/метод source line562, +237 применяет начальное состояние. Дубликаты
одного UINT64 схлопываются. CV `showDamageFromShot` record5056/+29..183
создаёт transient bound effects/impulses/markers, постоянное property не пишет.

DS порядок даёт IDs0..7: small_hole, small_ricochet, medium_hole,
medium_ricochet, main_hole, main_ricochet, large_hole, large_ricochet.
V `_readDamageStickers` record99146/+183..192,+398..407 задаёт IDs по len/append.
FX содержит targetStickers armorResisted/armorPierced; hugeHighExplosive →
main_ricochet/main_hole, hugeArmorPiercing → large_ricochet/large_hole.
V `_readShotEffects` record97108/+16..215 разрешает имена в IDs.
Серверные условия выбора/лимит/вытеснение/очистка остаются **UNKNOWN**.

VS `addDamageSticker` record12399/+35..74 выбирает descriptor/случайный вариант,
+107..188 расширяет начало на0.25 и выбирает случайное вращение,
+330..399 вызывает native model.addDamageSticker и сохраняет handle.
Это cosmetic RNG. Hit-effect codes0..4 — ricochet, armor-not-pierced,
pierced-no-damage, pierced, critical (constants.pyc SHA
`1c07c2e6a956dcfef95c4020954b4ca39efd77844d328cded935307a6515eebd`,
VEHICLE_HIT_EFFECT record18557/+6..39). Нейтрального «contact» кода среди них нет.

HE `Vehicle.showDamageFromExplosion` record6653/+56..78 даёт impulse/4,
vibration/SPLASH shake и marker. World blast идёт отдельно через
Avatar.explodeProjectile → ProjectileMover.explode → __addExplosionEffect:
materialHit может быть заменён waterHit/позицией воды; возможен missed trigger.
Нельзя считать этот вызов нейтральной заменой target-hit event.

В `res/packages/misc.pkg`, SHA
`4d4d26d27ebb2f4614dc6e36d6fe629d8e5a717cb96bb70e799d1ada5e5411ff`,
проверены HE effects members (префикс `particles/Shells_Eff/`):

| Member | ZIP local-header offset | SHA256 |
|---|---:|---|
| armorHit_HE_3.xml | 418507061 | `7abe15b9c1d2b2a5ae7c02b00c4d3feda7d2810aaad0a3a1f694420554b9adfa` |
| shellFall_HE_3.xml | 418819903 | `176122c82d3a8bccb38e4730cc0b8ad2c22ee2d5fca3bd678d1a956f12968ba5` |
| groundHit_HE_4.xml | 418622518 | `0fc4f9190a26b044069a54d609458de9c7c9fb8b3d5c74fbc21d09b2b5351718` |

armorHit_HE_3 `/influx/Renderer/MeshParticleRenderer/visualName_` →
metallparts_02.visual, sparkles используют TrailParticleRenderer/spark_trail.dds.
Это **VERIFIED визуальные частицы**, не доказательство damaging fragments.
Старый неизменённый PE-аудитор повторно подтвердил ARRAY framing: signed32 count,
VAR1 envelope, 54 instructions/10 pointers на EXE SHA
`86f5e351d44c12e0d2b89ed741ee9a4e70d21f234c39aa9cfd709536d49f04ed`.
Property candidate0xa4 (`0x9e+6`) — **INFERRED STATIC**, свежего capture нет;
partial ARRAY updates не квалифицированы.

## Матрица неизвестных и следующего решения

| Область | VERIFIED/OBSERVED | UNKNOWN / необходимое решение |
|---|---|---|
| Наружная броня | source meshes/materials/позиционные поля; static read PASS | native parity новых chassis, winding/entry-exit/layer order |
| Внутренние устройства | некоторые external devices + MaterialInfo/crew roles | полные internal volumes; недоказанные AABB остаются LAB |
| AP/APCR/HEAT | loader keys, 49 lossFactor, historical notes с provenance | AP5/70 и полная2×/3× граница/order именно #717, full layered solver |
| HE/HESH | HIGH_EXPLOSIVE fields, nominal275, radius и effects | original HP/LOS/spall/fragment formula; fallback radius не damage |
| Damage/penetration RNG | defaults0.25, UI endpoints±25% | распределение, sampling order/correlation, rounding; явная policy |
| Декали | decode/lifecycle/texture mapping | original producer/encoder rounding, cap/eviction, native appearance |

Неизвестное нельзя закрыть round-trip своего encoder/decoder, синтетическим
RNG-тестом или эффектом на экране. Будущая project policy должна иметь явную
версию и одобрение владельца; отсутствие historical evidence остаётся видимым.

## Проверки, воспроизведение, ограничения и откат

Основной новый инструмент — `tools/shell_mech_source_audit.py`: чтение
Packed XML через неизменённый `packed_xml.decode`, raw field offsets/SHA,
никакой записи клиенту. Ограничения16MiB/file,64MiB/набор,32 files,
decoder64 depth/100000 nodes, path4096/суммарные paths2MiB на один XML,
JSON32MiB; выход только
в **новый** JSON своего `local/evidence/shell-mech-*`; links/junction/escape
отвергаются. Неоднозначные логические XML-пути отвергаются до сведения в dict.
Это source inventory, не аттестация целого билда или server-law oracle.

| Реально выполненная проверка | Статус / evidence |
|---|---|
| Новый reader: 8 tests; существующие parser boundary:15 | PASS, E-V/tests.log и validation.json |
| Новый CLI: 10 original XML/DEF, точные spans/SHA | PASS_STATIC_READ, E-V/fields.json |
| Исторические6/4/275, gold/id/kind и source byte recheck | PASS, E-V/validation.json; E-R/invariant-field-offsets.json |
| Existing geometry reader:6 meshes; дополнение chassis,9 total | PASS_STATIC, E-A/run03/run-receipt.json; supplement-receipt.json |
| 24 source pins,19 XML,1081 pyc;569 shell rows/49HEAT | PASS_STATIC_READ, E-R/collection-summary.json |
| Декали21 instruction assertions/11 file rechecks;PE54+10 | PASS_STATIC_SOURCE_ONLY, E-D/receipt.json |
| git diff --check и unchanged runtime/allowlist | PASS, E-V/validation.json |
| Полный gateway gate, старый geometry unit suite | NOT_RUN; gateway неизменён, legacy fixtures не копировались |
| Native/owner/UI/audio, фактическая механика сервера | NOT_RUN; статический аудит это не заменяет |

Ранние geometry exploratory попытки получили явные ошибки plain
customization.xml/BSP material XML; частичные файлы сохранены, не объявлены
PASS. Final run03/supplement учитывают форматы. Независимый review обнаружил
коллизию logical XML path, исправлена с adversarial test; расширение path
ограничено до накопления. План исправлен: reentry восстанавливает **декали**,
не повторяет старые transient вспышки/звуки. История замечаний — E-R/REVIEW.md.

Команды из корня собственного worktree:

```powershell
python -B -X utf8 -m unittest tests.test_shell_mech_source_audit tests.test_research.ParserBoundaryTests -v
python -B -X utf8 tools/shell_mech_source_audit.py --client-root C:/WoT_0.9.1_RU_0717_original --resource res/scripts/item_defs/vehicles/germany/waffentrager_e100.xml --select /clip --out local/evidence/shell-mech-repeat-NEW/fields.json
python -B -X utf8 local/evidence/shell-mech-rules-20261027-01/collect_rules.py
python -B -X utf8 local/evidence/shell-mech-armor-20261027-01/inspect_geometry.py
python -B -X utf8 local/evidence/shell-mech-armor-20261027-01/inspect_supplement.py
python -B -X utf8 local/evidence/shell-mech-decals-20261027-01/inspect_decals.py
python -B -X utf8 local/evidence/shell-mech-decals-20261027-01/verify_decals.py
git diff --check
```

Существующие evidence не перезаписывать: local harvesters закрепляют свои
output paths; повтор исследования требует новой папки/нового run. Полный
реально выполненный argv нового CLI, версии, source/evidence SHA и логи — E-V.

Изменения: этот отчёт, план, один новый read-only tool и его тесты, короткие
добавления в STATUS/INDEX. Эти два общих документа потенциально пересекаются
со второй параллельной карточкой; при будущем merge сохранять обе записи.
ACTIVE_GATE/IMPLEMENTATION_ORDER, runtime, tools/p04m_*, tools/p06t_*,
каталоги/профили машин и ENGINE_SOUND неизменны. Общий local, оригинал,
стенды, пароли и процессы владельца не были целями записи/управления.

Откат — `git revert <коммит SHELL-MECH>` в этой ветке; стендового отката нет,
evidence сохраняется. План одобрен, **merge/push не выполнены**.
Единственный следующий рекомендуемый шаг: **после фактического принятия и
слияния ARENA-01/BATTLE-ANY проверить новый main и начать отдельную
SHELL-05A** по обновлённому плану. UNKNOWN-политики требуют выбора владельца;
одобрение очереди не превращает их в исторически подтверждённые законы.
