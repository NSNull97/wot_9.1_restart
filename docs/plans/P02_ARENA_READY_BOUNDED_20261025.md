# P02 bounded Avatar/Arena-ready slice

## Цель

Проверить свежим native-запуском границу `Account → Avatar → Space → Vehicle → setClientReady/PREBATTLE` на собственном loopback gateway. Не включать движение, стрельбу, полноценный бой, внешний capture или исходный клиент.

## Предусловия

- gateway executable должен содержать CLI `legacy091-arena-ready-probe`;
- локальный Rust toolchain должен быть доступен без junction escape;
- новый one-shot control, profile/trace/evidence directories и typed trigger;
- rollback клиента и остановка собственных процессов после запуска.

## Приёмка

`LOGGED_ON`, оригинальные Avatar/Space/Vehicle callbacks, native `setClientReady`, server PREBATTLE/countdown, raw capture metadata, clean teardown и независимая сверка trace/capture. При отсутствующем entrypoint или toolchain ставить `NOT_RUN`, не имитировать arena.

## Текущий результат

Preflight 2026-10-25 остановлен до клиента: установленный gateway отверг `legacy091-arena-ready-probe`, а `cargo`/`rustc` отсутствуют. Evidence: `local/evidence/native-arena-ready-20261025-01/arena-ready-preflight-evidence.json`.

## Откат

`python -B -X utf8 tools/interactive_client.py rollback --out local/evidence/native-arena-ready-20261025-01`; bridge/gateway stop; оригинал клиента не менять.
