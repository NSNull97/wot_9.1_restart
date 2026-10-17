# STAB worker cadence — implementation record

Статус: **PREPARED / native NOT_RUN**.

Contact130 классифицировал два события как разные fail-closed пути: сначала
logical scheduler lag gateway, затем ожидание ответа shared scene worker.
Раньше в receipts не было wall-time каждого `advance`, child CPU/scheduling
sample или bounded stderr. Эта ветка добавляет только наблюдение.

## Receipt contract

`WOT091_STAB_DIAGNOSTICS_DIR` — явно заданный существующий каталог на C. На
каждый запущенный IPC7 worker создаётся свежий файл
`scene-worker-g<generation>-p<pid>-n<nonce>.jsonl`. Формат имеет
`schema=1`, `scope=p05c-stab-worker-cadence-v1` и event-specific fields.

Набор событий: `diagnostic_open`, `worker_spawned`, `advance_dispatched`,
`worker_reply`, `scheduler_lag`, `scheduler_sample`, `worker_deadline`,
`worker_deadline_sample`, `worker_stderr`, `reply_sample` и
`worker_event_failed`. `scheduler_lag` получает `DUE`/`EARLY`, а при lag
строго больше 500 ms — `FAIL_CLOSED`. `worker_deadline` получает только
`FAIL_CLOSED` при истечении `REPLY_TIMEOUT`/`START_TIMEOUT`.

Bounded policy: до 4096 событий/512 KiB на файл; stderr receipt ограничен
4096 байтами metadata и 512 ASCII prefix, плюс digest. При лимите появляется
`diagnostic_truncated`; запись не содержит `PASS` и не маскирует ошибку.

## Categorisation

- **VERIFIED (source):** guard constants и timeout branches не изменены;
  scheduler receipt записывается до вызова прежнего `drive_deadline`.
- **VERIFIED (source):** diagnostics module проходит standalone Rust metadata
  compile на pinned compiler.
- **NOT_RUN:** runtime unit execution и canonical Windows gateway build после
  завершения этого отчёта (локальный checkout не имеет полного
  linker/runtime toolchain); native successor-stand, two-client and UI checks.
- **UNKNOWN:** CPU scheduling/OS contention и точная причина contact130 до
  первого запуска с env-bound receipts.
