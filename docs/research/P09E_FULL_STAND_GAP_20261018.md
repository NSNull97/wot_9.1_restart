# P09E full-stand readiness gap (2026-10-18)

## Цель

Зафиксировать, почему текущий P09E research/purchase writer нельзя честно подмешать
в полный боевой стенд одной настройкой. Этот документ описывает VERIFIED контракт
исходников текущего head и границу отдельной следующей карточки. Native/UI не
подменяются автоматическими проверками.

## Что уже есть

- `ResearchStore` выполняет source-bound research, покупку танка, покупку модуля и
  установку совместимой конфигурации в общей SQLite-транзакции с replay ledger.
- После миграции профиль хранит исходные MS-1 и ИС-7, их экипаж/боекомплект и
  резервные ревизии. Новая покупка получает отдельный `vehicle_inventory_id`,
  source stock modules, HP и запись в `game_vehicle`.
- Автоматические store/projection/native-codec проверки покрывают prerequisites,
  цены/нулевой test-lab cost, duplicate/replay, restart, depot conservation,
  turret+gun compatibility, chassis mass и bounded native deltas.

## Текущие жёсткие ограничения

| Область | VERIFIED поведение | Следствие для полного полигона |
|---|---|---|
| Боевой допуск | P09E policy содержит `battle_admission=false`; projection ставит этот флаг каждой новой записи | Купленный танк нельзя законно передать в P08B/P05C runtime |
| Runtime-профиль | новая запись получает `runtime_supported=false`; боевые профили P04M/P06T живут в отдельном source registry | Нельзя выбрать купленную машину в бою только по `vehicle_definition_id` |
| Экипаж | `garage_record` создаёт `[None] * crew_seats`; native crew writers принимают только подтверждённые native inventory 1/2 | После покупки UI видит пустые места, а admission обязан отказать |
| Боекомплект | `garage_record` создаёт пустые `shells`; P09D/P09E ammo layout вычисляется только для `ms1-stock` и `is7-stock` | Новая машина не получает выдуманные снаряды и не может стрелять через старый mount |
| Оборудование | P09E module writer принимает chassis/engine/radio/turret/gun; optional-device/equipment writer остаётся fixture-only, native capability guard их отклоняет | «Полностью снарядить» купленную машину нельзя доказанным путём |
| Слоты | миграция сохраняет source `stats.slots=3`; `free_vehicle_purchases` даёт только остаток до этого числа; нет операции slot expansion | Запрос «100 слотов аккаунту» пока не имеет авторитетной команды/исторического контракта |
| Продажа | `ResearchStore` не имеет `sell_vehicle` операции | Покупка/продажа не замыкает полный garage lifecycle |
| Экономика | test-lab обнуляет XP/кредиты только для research/module/tank subset; gold, crew tariffs и shells flags отклоняются | Нельзя объявлять исторический магазин готовым по одному zero-cost тесту |

## Почему это не чинится флажком

Для допуска купленной машины требуется новый source-bound runtime profile и
authoritative loadout contract: crew seats/assignment, ammo mount/capacity,
module/equipment modifiers, damage-module mapping, visibility points и native
projection. Для каждой машины это должно быть подтверждено отдельной карточкой и
каноническим gate. Обход `battle_admission`, выдача пустого экипажа или прямой SQL
grant нарушит сохранённые инварианты P08B/P06T и не будет честным тестовым полигоном.

Запрос на 100 гаражных слотов также требует отдельной versioned policy: источники
#717 и текущий P09E доказывают только `stats.slots=3`. Автоматическое увеличение
до 100 было бы новой игровой политикой, а не исправлением бага.

## Следующая карточка

`P09E-FULL-STAND` (после согласования владельцем):

1. принять ограниченный список боевых машин (сначала IS-7/МС-1, затем профильный
   пул P04M/P06T) и source-bound loadout schema;
2. подключить crew assignment/recruitment для новых inventory IDs;
3. добавить ammo mounts/capacity и equipment service через один writer;
4. только после этого включить battle admission и подготовить свежий native stand;
5. отдельно решить policy для slot expansion/sell и записать её как explicit
   test-lab setting, не как исторический факт.

До этой карточки полная приёмка остаётся `NOT_RUN/UNSUPPORTED` для купленных машин;
текущие MS-1/ИС-7 native battles не закрывают эту границу.

## Откат и доказательства

Изменения этой диагностической ветки — только документ и тест. Откат: удалить
коммит ветки или не вливать ветку; production/main и клиентские ресурсы не
затрагиваются. Команда и результат теста указаны в отчёте родительского агента.
