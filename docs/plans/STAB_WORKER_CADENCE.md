# STAB — bounded worker cadence diagnostics

## Цель

Разобрать два fail-closed события contact130 раздельно: отставание
логического 100-мс scheduler grid и превышение 500-мс ожидания ответа
IPC7 scene worker. Существующие `REPLY_TIMEOUT=500 ms` и `MAX_LAG=500 ms`
остаются без изменений; диагностика не превращает FAIL в PASS и не меняет
физику, скорость мира или порядок команд.

## Изменение

В production `scene_worker::Worker` добавлен opt-in sink, включаемый только
через `WOT091_STAB_DIAGNOSTICS_DIR`. Для каждого поколения создаётся новый
JSONL-файл в заранее существующем каталоге. Записываются bounded-события:

- отправка каждого `advance` и число акторов;
- время ожидания ответа и время его потребления gateway;
- scheduler lag относительно запланированного logical deadline;
- обе ветви deadline с `status=FAIL_CLOSED`;
- bounded stderr: размер, SHA-256 и короткий ASCII prefix;
- wall-time и Windows `GetProcessTimes` CPU sample дочернего worker.

События ограничены 4096 строками/512 KiB, при переполнении сохраняется
структурированная `diagnostic_truncated` запись. Путь проверяется на
абсолютность и отсутствие symlink/reparse ancestors; файлы открываются
`create_new`. Обычный запуск без env не пишет файлов. Ошибка записи sink не
влияет на авторитетный runtime.

## Проверки

Три unit checks sink прошли: bounded output, stderr hash/prefix и сохранение
обоих `FAIL_CLOSED` receipts без статуса PASS. Исполняемый canonical build
прошёл через временный локальный GNU/CRT overlay, потому что pinned driver
сталкивается с двумя разными локальными CRT-наборами; исходники и toolchain
в репозитории не менялись. Полный suite на canonical checkout завершился
`1587 passed / 48 failed / 5 ignored`; 48 FAIL относятся к отсутствующим
старым physics/fixture artifacts (`p06t`/portable source roots), поэтому
карточка остаётся FAIL/непринятой, а не получает PASS по частичному suite.
Точечный direct IPC7 Worker test на p04m06 fixture прошёл 1/0/0 и сохранил
четыре bounded JSONL: 600 `advance_dispatched`, 620 replies и Windows CPU
samples; stderr был пуст, поэтому `worker_stderr` не появился. Receipt лежит
в `local/evidence/20261017-stab-worker-cadence/contact132/`.
Scheduler lag именно `BatchRuntime` и services/native/client checks остаются
`NOT_RUN` до successor/native прогона.

## Ограничения

CPU sample доступен на Windows через `GetProcessTimes`; на других платформах
поле остаётся `null`. Диагностика не доказывает причину physics regression и
не является native/UI приёмкой. Она намеренно не сохраняет IPC payloads,
координаты, клиентские ресурсы, токены или полный stderr.

## Откат

Откатить commit ветки `codex/stab-worker-cadence`; runtime без env полностью
совместим с предыдущим поведением. Не удалять уже собранные historical
evidence или базы стендов.
