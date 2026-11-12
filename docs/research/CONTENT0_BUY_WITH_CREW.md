# CONTENT-0 — покупка машины с экипажем и базовым боекомплектом (окно «Покупка …»)

Дата: 2026-11-12. Карточка CONTENT-0, шаг 6 (экипаж), заказ владельца со стенда -21: найм по одному через казарму
слишком долгий — купленная машина должна приходить с полным экипажем. Клиент читался только как данные
(`tools/py27_static.py`, ограниченный разбор marshal/байткода; `packed_xml` для `guns.xml`), без исполнения и без
изменений: `C:/WoT_0.9.1_RU_0717_original`. Нативная проверка в окне клиента: **NOT_RUN** (ждёт владельца).

## VERIFIED: что шлёт окно

| Источник (`res/scripts/…`) | Функция, строка | Факт |
| --- | --- | --- |
| `client/gui/scaleform/daapi/view/lobby/vehiclebuywindow.pyc` | `VehicleBuyWindow.submit`, 149 | при `buySlot` сначала `VehicleSlotBuyer`, затем `VehicleBuyer(vehicle, data.buySlot, data.buyAmmo, data.crewType).request()` |
| `client/gui/shared/gui_items/processors/vehicle.pyc` | `VehicleBuyer.__init__`, 19 | `buyCrew = crewType != -1`; валидаторы: VehicleValidator, MoneyValidator(цена), VehicleSlotsConfirmator, VehicleFreeLimitConfirmator |
| там же | `VehicleBuyer._request`, 55 | `shop.buyVehicle(nationID, innationID, buyShell, buyCrew, crewType, cb)` |
| `client/account_helpers/shop.pyc` | `Shop.buyVehicle`, 766 | `flags = NONE; if buyShells: flags \|= SHELLS; if recruitCrew: flags \|= CREW`; `_doCmdInt4(CMD_BUY_VEHICLE, shopRev, typeCD, flags, tmanCostTypeIdx)` |
| `common/accountcommands.pyc` | `BUY_VEHICLE_FLAG` | NONE 0, CREW 1, SHELLS 16 |
| `processors/vehicle.pyc` | `VehicleBuyer.__sumBuyPrice`, 71 | цена = машина + `tankmanCost[crewType]` × `len(vehicle.crew)` (если crewType ≠ −1) + Σ `shell.buyPrice × shell.defaultCount` по `gun.defaultAmmo` (если buyShells) |
| `vehiclebuywindow.pyc` | `_initData`, 34 | число танкистов = `len(vehicle.crew)`; строка 1 тарифа — кредиты, строка 2 — золото; цена БК из `gun.defaultAmmo` |

Итого на проводе (команда 301, Int4): `[shopRev, typeCD, flags, tariff]`, где flags ∈ {0, 1, 16, 17}; tariff = −1
при «Купить машину без экипажа», иначе индекс строки `shop.tankmanCost` 0/1/2. Соответствие индексов подписям
(курсы 0, школа 1, академия 2) — VERIFIED ранее по Flash `RecruitWindow.swf` (P04H, раздел «Tariffs»).

## VERIFIED: базовый боекомплект (флаг 16)

`gui_items/vehicle_modules.pyc` `VehicleGun._getDefaultAmmo` → `items.vehicles.getDefaultAmmoForGun(descriptor)` →
`_getAmmoForGun(gun, None)` (`common/items/vehicles.pyc`, строка 2908):

```
for shot in gun['shots']:                    # порядок components/guns.xml
    count = int(shot['defaultPortion'] * maxAmmo / clip + 0.5) * clip
    if current + count > maxAmmo: count = maxAmmo - current
    current += count
```

`_readShot` (строка 4473) читает `defaultPortion`, отсутствие = 0.0. В каталоге проекта долей нет, поэтому
`tools/content0_default_ammo.py` читает закреплённые `item_defs/vehicles/<нация>/components/guns.xml` (7 файлов,
размеры и SHA-256 в таблице) и пишет каноническую `config/catalog/default_ammo.v1.json` для всех 361 машин test_lab
(основной каталог — подмножество). maxAmmo и обойма — смонтированные значения из `config/test_lab/battle_profiles.v1.json`
(сверка maxAmmo с каталогом). Для всех 361 сумма равна maxAmmo. Примеры: МС-1 96 ББ; ИС-7 18 ББ / 0 БП / 12 ОФ;
КВ-3 73 / 0 / 18. Проверка совпадения с клиентом: `python -X utf8 -B tools/content0_default_ammo.py --original <клиент> --check`.

## INFERRED

* Уровни тарифов 50/75/100 % — подписи окна (скриншот владельца) и исторические правила 0.9.1; источник уровня на
  стороне оригинального сервера недоступен. Строки `tankmanCost` в бандле проекта пусты (сервер их формирует нулевыми).
* Оригинальный сервер при флаге 16 **покупал** весь базовый БК (клиент берёт цену за все `defaultCount`, не учитывая
  склад) и загружал его в машину. Решение CONTENT-0: снаряды покупаются бесплатно и сразу загружаются; общий склад
  (одна запись на compact ID) не уменьшается и не увеличивается. Нехватки на складе поэтому не бывает.
* Танкисты: по одному на каждое место машины (`crew_roles` каталога), роль — первая роль места, нация и тип обучения —
  купленной машины, порядок мест — порядок каталога; паспорта (имя/фамилия/иконка) — те же модульные наборы нации, что
  и при найме (V2). Клиент ждёт их как обычные записи инвентаря 8 (`compDescr`, `vehicle`) плюс список `crew` машины.

## UNKNOWN

* Исторические цены тарифов и как оригинальный сервер расходовал `freeTMenLeft` при покупке с курсами.
* Отдаёт ли оригинальный сервер всё одной большой diff-посылкой (длинный VAR1 Mercury на #717 не проверен).

## Реализация (проектные решения)

* `p09e_native_commands`: допускаются только комбинации окна; всё прочее — явный отказ `AUTOBUY_CREW_SHELLS_UNSUPPORTED`
  (ответ «недоступно», без записи). flags 0 — прежняя операция `buy_vehicle`; иначе `buy_vehicle_equipped`
  `{vehicle_id, crew_role_level 0/50/75/100, load_shells}`.
* `ResearchStore.execute`: покупка, экипаж и загрузка — одна транзакция (`_equip_purchase` после записи состояния
  исследования); любая ошибка — откат всего. Журнал хранит итог (`details.equipment`); повтор команды воспроизводит
  ответ и пересчитывает экипаж/БК из исходного состояния. Хранилища без пула (P09E без P04M) отвечают отказом.
* `PoolStore`: экипаж из того же пожизненного распределителя (`CrewContract.plan_purchase`), запись через
  `_persist_crew_members` и `p04d_crew_meta`; БК — `p09c_ammo_mount` и `p09d_native_layout`.
* Контракт экипажа V2 (192) принимает паспорта 50/75/100; хеш политики V2 не менялся (миграция стенда не нужна).
  V1 (16) — только 50: школа/академия на V1 получают отказ `RECRUIT_SELECTION_UNSUPPORTED`.
* Нехватка свободных идентичностей (лимит 192 на аккаунт, без возврата при увольнении) — отказ
  `FREE_RECRUITMENT_EXHAUSTED` для всей покупки, машина не покупается.
* Посылка клиенту: один `Account.update` ограничен 240 байтами (VAR1, `ammo_service.rs`), 6 танкистов по 25 байт
  не помещаются. Ответ — цепочка diff'ов prevRev w+i → w+i+1 (как принятая цепочка int-settings): запись машины,
  затем по одному танкисту (инв. 8 + список `crew` машины + `freeTMenLeft`), затем `shells`/`shellsLayout`, жадно
  упакованные (`chained_updates`, до 12 diff'ов). Шлюз (`identity.rs research_reply`) принимает необязательный
  `extra_update_hex` только для успешного research-ответа, каждый diff проверяет тем же валидатором, сдвигает курсор
  на число diff'ов и отправляет их по порядку перед единственным callback успеха (`ammo_session.rs`, fresh-путь).
  Бюджет ответа research — 16 КиБ (прочие сервисы — прежние 4 КиБ).

## Проверки, откат

Тесты: `tests/test_content0_buy_with_crew.py` (флаги, алгоритм и таблица БК, упаковка цепочки; на стор-цепочке P04M в
каталожном режиме, контракт V2 — каждый тариф, БК с экипажем и без, отказы, исчерпание V1, failpoint'ы, повтор);
Rust: `research_service` (опции 301), `identity` (`content0_research_reply_…`), `ammo_session` (цепочка до success),
`ammo_session_fresh` (курсоры). Нативная проверка в клиенте — NOT_RUN.

Откат: revert коммитов ветки; данные стенда, созданные покупкой с экипажем (танкисты 75/100), читаются только новым
кодом — перед откатом на стенде такие покупки нужно не делать или пересоздать стенд.
