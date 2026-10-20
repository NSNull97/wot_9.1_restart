# P06T — детонация БК и потеря заряженных снарядов

Задача владельца 2026-10-16 после принятого узкого P08C checkpoint1e87e1b:
«снесли БК — значит потерял все снаряды». Ветка
`codex/p06t-ammo-rack-detonation` от этого checkpoint. Main и ночные ветки
сохраняются. Это явное правило проекта, не утверждение об оригинальном сервере.

## Объём

- Переход AmmoBay HP>0→0 при непустом loaded БК даёт детонацию и гибель машины.
  Повреждение жёлтого модуля само по себе не детонация. Пустой БК не взрывается:
  нечему детонировать; это закреплённая политика проекта для граничного случая.
- Уничтожаются все оставшиеся loaded stack, включая снаряды в барабане. Склад
  не меняется. Выстрелы учитываются отдельно от снарядов, потерянных при взрыве.
- Один авторитетный causal event связывает shot/attacker/target/tick,
  переход модуля, оставшиеся HP, гибель и потерянные количества. Не подменять
  исходный plate Trace дополнительным уроном и не начислять два фрага.
- Native: корректный exploded/detached health presentation, FX взрыва БК и
  отдельная DetachedTurret с серверной позой/движением, request/create/ACK/leave.
  Родительская машина и башня подчиняются видимости; скрытые координаты не текут.

## Последовательность

1. Сохранить прежнюю приёмку P08C и actual evidence. Закрепить original#717
   health/FX/DetachedTurret entity type/property/method layouts по исходникам/PE.
2. Согласовать отдельный versioned ammo-loss contract и frozen policy до admit.
   Старые v2 резерв/terminal/results7/8/читатель и записи сохраняются. Новый
   контракт не конфликтует с future OwnedV3. frozen=fired+lost+remaining;
   native shots=sum(fired), при детонации remaining0. Никакой пересчёт истории.
3. Реализовать домен/журнал/armament и World glue, SQLite writer+Rust codec,
   затем native публикацию/authoritative detached visual timeline.
4. Проверить реальные World/Trace/geometry и actual SQLite/HTTP: одного unit
   codec roundtrip недостаточно. Replay/поздняя ошибка/одна смерть/непустой и
   пустой БК/смена current/clip/fire/crew/death/6slots/visibility/return gates.
5. Committed current-head canonical full, raw source before/after, новая
   source-bound binding и fresh native стенд с существующим БК. Owner проверяет
   детонацию/башню, ангары с нулевым loaded БК и сохранность склада.

## Долговечность и границы

Потеря фиксируется атомарным finish через один SQLite writer с расходом,
терминалом и результатом. Commit/replay/relogin/restart не восстанавливают
потерянное. Авария всего процесса до terminal commit сохраняет прежнюю явную
aborted_restart/refund policy; per-shot/per-hit WAL эта карточка не обещает.
Новая policy применяется только новым явно подготовленным резервам. Нельзя
включить новые потери для старой активной v2 машины или переписать её terminal.

Native/UI/полёт/звук NOT_RUN до actual проверки. Не публиковать клиентские
ресурсы/дампы. Изменяются только server/tools/tests/web/client_patch/docs,
оригинальный клиент не менять. Текущий source-bound coreV7 run оставлен
в ангарах, его остановка/замена только по собственным receipts после сохранения.

Откат: остановить новый run по receipts, вернуть checkpoint1e87e1b и его matching
binding06/runtime46d5c20, сохранив БД и совершённые потери. Старый writer должен
явно отказать работе с новым activated contract, а не вернуть фиктивный успех.
До проверки миграции/старого reader откат данных не объявлять совместимым.

Приёмка пока NOT_RUN. Следующий шаг — согласованный closed versioned contract
и source/native evidence, затем конкретная реализация в этой ветке.
