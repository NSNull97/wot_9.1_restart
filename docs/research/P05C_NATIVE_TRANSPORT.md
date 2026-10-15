# P05C — bounded transport для смешанных2..6 машин

2026-10-16, ночная реализация. Это проверка server Session/codec, а не
подтверждение шести настоящих клиентов. Физический компонент и его реальные
Jolt probes — [P05C_SHARED_PHYSICS](P05C_SHARED_PHYSICS.md).

## Контракт

Старые laboratory modes сохраняют CAPACITY2. Явный profile13 shared-scene путь
задаёт expected actors2..6, каждый Actor хранит свой frozen source profile.
Нативные descriptor/aim/ammo/HP должны происходить от конкретного Actor;
shell effects от стрелявшего, health bounds от пострадавшего.
Общий bounded журнал —6*96 выстрелов, без выдачи лишних боеприпасов машине.

ClientArena #717 принимает initial VEHICLE_LIST1 и отдельные VEHICLE_ADDED2,
VEHICLE_UPDATED11. ДляN>2 initial list содержит одну машину, затем идут
отдельные tuples остальных. Native UINT8 длина каждого update остаётся≤252;
полные сообщения группируются по≤500 байт, транспортное окно остаётся8.
Bounded pending queues, а не увеличение окна, обслуживают creates всех машин
и контроллеров объектов. P07B позднее ограничивает AoI по засвету.

Creations/READY/HP/ACK state содержит6 slots, публикация проходит только по
существующим World actors. Requests имеют уникальные IDs; допустимый wire ID
не разрешает создать отсутствующую в этом бою машину. READY/aim остаются
привязаны к собственной машине. Проверка malformed compound атомарна.

## ID и алиасы

ПервыйN6 Session gate обнаружил настоящий конфликт: прежняя формула давала
третьей машине ID0x09100007 и alias2, уже занятые AreaDestructibles.
Исправление fe8a3c7 сохраняет прежнюю принятую пару и выделяет новый диапазон:

| Объект | Entity ID | Native alias |
|---|---|---|
| Машины0/1 |0x09100003/0x09100005|0/1|
| Машины2..5 |0x09110003+2*(slot-2)|240..243|
| Avatar каждой машины |vehicleID-1|не используется этой таблицей|
|144 AreaDestructibles |0x09100007..0x09100096|2..145|

Это выбранные сервером opaque IDs, не восстановленные исторические ID боёв.
Они укладываются в исходные OBJECT_ID/u8 поля. Проверяется уникальность всех
156 entity IDs и150 aliases, включая полный каталог областей.

## Выполненные проверки

`gateway-p05c-six01`:5PASS/1FAIL. FAIL сохранил исходный namespace conflict;
тест не ослаблялся. После исправления:

```powershell
python -B -X utf8 server/build.py gateway --test --test-filter six_ --out local/build/server/gateway-p05c-six02
```

7PASS/0ignored: полный six-actor IPC frame, исходные scalar substeps,
mixed roster с48-byte UTF8 names, все6 entity requests/последний shot ID,
весь area namespace и реальный Session scheduling. Session test проверяет
duplicate seventh request без частичного эффекта, selective ACK slots3/5,
отказ чужого READY, собственный slot5 READY и отказ slot5 в двухместном World.
Сборочный результат — `local/build/server/gateway-p05c-six02/result.json`.

Root physics build отдельно PASS: `physics-p05c-night01`, DLL SHA256
9201b8f93b815c43189a957560eceb7a18a46e12c4b2eaae41aeeb6ab2395e53.
Сборка не подменяет actual physics probes из компонентного отчёта.
Полный integrated gateway gate и actual World↔batch runtime ещё впереди.

## Утро и откат

NOT_RUN: настоящее создание/READY третьего–шестого клиента, смешанный бой,
контакт танков/управление/звуки/возврат. В native проверке нужны минимум
смешанная пара и затем реальные дополнительные клиенты; synthetic Session
не доказывает их UI. Ранее принятые два legacy клиента проверяются full suite
и отдельно владельцем на общем стенде.

Откат — commits ветки P05C; вернуть v1 resource manifest и прежний gateway,
client install ledger. Main не изменяется до обязательной native приёмки.
