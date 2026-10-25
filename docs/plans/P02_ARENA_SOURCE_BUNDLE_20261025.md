# P02 source-bundle arena vehicle bridge

## Цель

Дать только opt-in `legacy091-arena-ready-bundle-probe` возможность загрузить
профиль4 Vehicle/снаряжение из проверенного portable `server-content.v1` bundle,
когда exact legacy `manifest.json` исключён из bundle из-за абсолютных путей.
Account/Avatar остаются авторизованными через обычный profile13 fixture; profile4
vehicle state используется отдельным явно связанным контекстом.

## Границы

- strict legacy `arena_vehicle091::load` и `prepare_primary_ms1` не ослабляются;
- bundle path задаётся CLI, не trigger-файлом, и должен находиться под
  `gateway.local_root`;
- принимаются только закреплённые bundle manifest/profile-chain hashes и
  конкретные profile4 blobs с ограничениями размера/SHA;
- pickle/object payloads не интерпретируются произвольным loader’ом;
- canonical gateway и обычный `legacy091-arena-ready-probe` не меняют поведение;
- движение, стрельба, полноценный бой и внешний сниффер не входят в карточку.

## План

1. Добавить bounded verifier portable bundle и отдельные source-bundle loaders
   Vehicle и battle preparation.
2. Передать immutable source-bundle context только в opt-in probe Session;
   не подменять authenticated hangar/profile13 state.
3. Добавить отрицательные Rust tests для изменённого bundle manifest/chain/blob,
   чужой identity, state mismatch, symlink/escape и отсутствующего файла.
4. Собрать legacy probe, запустить targeted tests и один новый native bounded run.
5. Обновить evidence/STATUS; при отсутствии всех native callbacks оставить
   `NOT_RUN`, а не объявлять совместимость.

## Приёмка

PASS только при свежем native `LOGGED_ON → Avatar → Space → Vehicle → Ready` с
сохранённым loopback capture metadata, clean rollback и независимой проверкой
bundle provenance. Bridge-only/fixture tests не заменяют native acceptance.

## Откат

Удалить только новый ignored build/evidence/stand каталог, затем выполнить
`tools/interactive_client.py rollback --out <run-evidence>`. Исходный клиент и
основные SQLite не изменяются.

## Результат bounded run — 2026-10-25

Targeted Rust tests прошли: portable source bundle 2/2 и capture CLI 3/3.
Отдельный native запуск в
`local/evidence/native-arena-source-bundle-20261025-01/` подтвердил
`LOGGED_ON → Account → Avatar → Space → Vehicle`: есть
`PlayerAvatar.onSpaceLoaded`, `Vehicle.onEnterWorld`, `ARENA_VEHICLE_ANNOUNCED`
и `ARENA_VEHICLE_QUEUED`. Ready callback клиента не пришёл: native view остался
`BattleLoading`, `ready=false`, gateway остался в `ARENA_READY_WAITING` до
bounded timeout. `ARENA_READY_ACCEPTED`/Prebattle отсутствуют.

Evidence: `local/evidence/native-arena-source-bundle-20261025-01/arena-source-bundle-evidence.json`.
Статус: **NOT_ACCEPTED_HASH_ANCHORED_PORTABLE**. Это не PASS legacy
совместимости: закреплённый exact legacy `manifest.json` отсутствует, поэтому
режим является отдельным локальным hash-anchored экспериментом. Client capture
и trace сохранены с размерами/SHA-256 без вывода payload или credential данных;
rollback install2 — PASS.
