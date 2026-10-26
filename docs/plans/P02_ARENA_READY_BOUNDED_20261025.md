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

Toolchain восстановлен в изолированном каталоге: `rustc 1.90.0`, `cargo 1.90.0`,
проверенный LLVM-MinGW архив. Pinned installer из bootstrap не принят молча:
его ожидаемый SHA отличается от текущего официального файла, поэтому сохранён
отдельный hash-drift факт. Legacy gateway собран свежим бинарником
`p01-wg-probe.exe` с CLI `legacy091-arena-ready-probe`; targeted
`arena_ready091::tests::` — 7/7 PASS, отдельный session regression filter
`arena_transition_requires_all` — 1/1 PASS. Полный набор Cargo в этом checkout дал
1217 PASS, 494 FAIL, 6 ignored: все FAIL — fixture-зависимые `ENOENT`, это не
linker/toolchain regression.

Один bounded native run `native-arena-ready-20261025-12` действительно дошёл до
`LOGGED_ON`, `SESSION_ACTIVE`, трёх Account sync и `ACCOUNT_SHOW_GUI_QUEUED`.
Typed trigger `avatar_ready` был съеден ровно один раз, но переход к Vehicle
закрыт fail-closed: gateway записал
`ARENA_BASE_TRIGGER_REJECT reason=queue_failed`. Причина установлена по
проверенным входам: клиент получил чистый research profile13 fixture `p09d-r21`,
а `arena_vehicle091::load` принимает только pinned profile4 с точным manifest
15490 bytes/SHA `ea9678…`. Поэтому Avatar/Space/Vehicle/Ready callbacks не
объявляются достигнутыми. Client/gateway/bridge остановлены, rollback PASS.

Evidence: `local/evidence/native-arena-ready-20261025-12/arena-ready-evidence.json`.
Кандидат восстановления profile4 из portable source-bundle сохранён отдельно:
`local/stands/profile4-arena-ready-source-bundle-20261025-01/candidate-receipt.json`;
в bundle есть blobs и chain, но отсутствует exact legacy `manifest.json` и
path-bound preservation, поэтому candidate имеет статус `NOT_RUN_STRICT_LOADER`.

## Откат

`python -B -X utf8 tools/interactive_client.py rollback --out local/evidence/native-arena-ready-20261025-12`; bridge/gateway stop; оригинал клиента не менять.
