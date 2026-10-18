# P09E purchased full-stand preparation (2026-10-18)

## Результат

`tools/p09e_full_stand.py` добавляет source-bound планировщик для уже купленной
записи P09E. Он использует существующие `assembly()` и `garage_record()` и
собирает детерминированный JSON-отчёт с исходным descriptor, ремонтом, массой,
пределом нагрузки и установленными компонентами. SQLite не открывается и не
изменяется.

Для новой записи с `native_id >= 3` отчёт имеет статус
`PREPARED_GARAGE_ONLY_NOT_NATIVE`. В нём явно остаются:

- экипаж — `NOT_RUN`: подтверждённый P04K writer принимает только native IDs 1/2;
- боекомплект — `NOT_RUN`: P09D mount/layout привязан к двум принятым stock
  записям, нового inventory ID в контракте нет;
- оборудование — `NOT_RUN`: optional-device purchase/service contract не
  закреплён исходниками;
- бой — `BLOCKED_UNVERIFIED_PROFILE` и `battle_admission=false`.

Это подготовка гаражной проекции, а не способ выдать экипаж, снаряды или допуск
через SQL. Непустые запросы crew/ammo/equipment и попытка поднять admission
отклоняются типизированным `TransactionError` до любого изменения состояния.
Descriptor в отчёте представлен canonical hex, поэтому доказательство можно
хешировать без небезопасной сериализации байтов.

## Проверка

Focused suite `tests.test_p09e_full_stand`: **4 PASS / 0 FAIL**. Проверены
source assembly/loadout, неизменность входной купленной записи, повторяемый
digest, три fail-closed guards для crew/ammo/equipment, отказ battle promotion
и отказ базового/уже runtime-qualified/несовместимого ряда.

Native/UI, реальный клиент, экипировка через Flash, боекомплект в бою и
`battle_admission` остаются **NOT_RUN**. Для полного полигона нужен отдельный
source contract для crew descriptors/seat assignment, ammo mount/capacity,
optional devices и runtime profile конкретной новой машины; только после него
можно писать следующий writer и отдельный canonical gate.

Откат — не вливать ветку `codex/p09e-full-stand`; production `main`, базы и
ресурсы клиента этим изменением не затронуты.

