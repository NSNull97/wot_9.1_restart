# P05 — воспроизводимое движение, статическая коллизия и reconciliation

Статус: **DRAFT / NOT_STARTED**.

Рабочая ветка черновика: `codex/p05-plan`. Основа — текущий `main` после
принятого P04 content-import contract. Этот документ описывает узкий
проверяемый срез P05. Он не объявляет текущий Jolt worker исторической
физикой World of Tanks и не открывает production/deployed gateway.

## Цель

Зафиксировать серверный контракт, в котором один авторитетный MS-1 получает
разрешённые команды движения, двигается по одной из двух уже экспортированных
карт, упирается в проверенную статическую геометрию и получает monotonic
коррекции состояния после потери/дубликата/опоздания кадров. Клиентские
координаты, часы и локальная конечная поза не являются источником истины.

Первый срез ограничен одним серверным телом и статическими terrain/obstacle
мешами. Это позволяет проверить поверхность, стену, границу и протокол
коррекции без подмены отсутствующей модели танк–танк или destructible objects.

## Предпосылки и источники

`P04` уже принял только typed import contract. Полный #717 dataset, native
геометрическая эквивалентность и историческая физика остаются `NOT_RUN`.
Используются только закреплённые локальные материалы:

- `server/physics/Program.cs` и `server/physics/CheckedInput.cs` — приватный
  .NET worker с фиксированным шагом 1/60 и domain JSONL, без socket/native IDs;
- `server/physics/README.md` — текущий test_lab contract и его ограничения;
- `server/gateway/src/drive/worker.rs`, `drive/world.rs` и map-drive service —
  загрузка hash-pinned worker/pool и публикация серверной позы;
- `tools/map_geometry.py` и его tests — bounds, finite coordinates, indices,
  zero-area triangles, instance spans и точечные ray queries;
- `local/server/map-drive/pool.json` и `local/server/map-drive/worker-v1/` —
  локальные packaged artifacts, если их SHA совпадают с receipt;
- `local/evidence/20261005-p02-map-drive/data/` — terrain/obstacle exports,
  `handoff-01/index.json`, `bind03-ground-review-01`, `ms1-drive03-review` и
  `offline-collision-review-01`;
- `docs/research/P02_MAP_DRIVE.md` и `docs/research/P02_DRIVE_LIMITATIONS.md` —
  наблюдённые границы native drive, включая слабый pivot на месте;
- `docs/02_ARCHITECTURE.md`, `docs/03_ROADMAP.md` и `docs/ACTIVE_GATE.md` —
  авторитетность worker, два типа геометрии и обязательные ограничения.

Evidence из `local/` — ignored, append-only и привязанное к конкретному
источнику. Отсутствующий evidence не заменяется синтетическим PASS.

## Границы карточки

Входит в этот узкий срез:

1. MS-1 из уже принятого test_lab профиля; vehicle profile и crew/ammo
   admission не переделываются этой карточкой.
2. Две карты из существующего проверенного пула: `01_karelia` и
   `05_prohorovka`.
3. Фиксированный physics step 1/60, шесть шагов на domain request и
   ограниченная 10 Hz публикация, как описано в worker contract.
4. Команды `neutral`, `forward`, `reverse`, `brake`, `left`, `right` и
   forward/reverse turn через доменную модель. Native bit flags переводятся
   только в compatibility layer.
5. Авторитетное состояние: `tick`, `sequence`, position, direction, signed
   speed, linear/angular velocity, contact count и шесть wheel contact masks.
6. Surface settle, разгон, торможение, остановка, задний ход, поворот в
   движении, slope/uneven участок, статический stone/wall, map bounds и
   безопасный EOF/worker failure.
7. Reconciliation contract: stale/duplicate state не откатывает tick;
   пропущенное состояние восстанавливается ближайшим полным серверным кадром;
   клиентский pose не записывается обратно в world; rejoin получает новый
   authoritative snapshot перед следующей командой.

Не входит:

- стрельба, projectile, hit/damage, броня, visibility и результаты боя;
- IS-7 native handoff, экипаж, оборудование, экономика и reservation;
- танк–танк collision в первом single-body worker slice;
- деревья/destructibles и изменение collision mesh во время боя;
- partial cruise flags 16/32/17/18/21/33 как принятые режимы;
- historical fidelity, cross-platform identity, Linux или two-PC/LAN;
- production deployment, public endpoint, matchmaking и нагрузка.

Танк–танк и destructibles остаются отдельными follow-up gates. Их нельзя
закрыть тем, что один корпус остановился у static mesh.

## Контракт состояния и ошибок

Сервер принимает только bounded domain commands с monotonic sequence и
фиксированным числом ticks. Неполное, повторное, слишком позднее или
неподдержанное действие отклоняется атомарно, без частичного изменения pose.
Worker error, timeout, malformed state, неверный map/config SHA или нарушение
contact mask переводят арену в явный failed/return path; сервер не публикует
фальшивый `state` после ошибки.

Каждый опубликованный кадр содержит:

```text
version, event, seq, tick, settle_ticks, map, config_sha256, state
```

`state` содержит только серверную позу и измеренные worker diagnostics.
Native entity/method IDs остаются в compatibility layer и не попадают в
physics parser. Отдельная native correction envelope должна иметь monotonic
wire sequence и ссылку на server tick; точный native payload фиксируется
только после нового corpus, а не угадывается из `.def`.

## Порядок выполнения

### 1. Baseline и входы

- Сохранить source/layout/client/deployed SHA и проверить, что relevant
  processes не работают.
- Прочитать pool, worker artifact manifest, terrain/obstacle manifests и
  receipts. Отдельно зафиксировать map ID, spawn, bounds, config SHA и
  coordinate convention.
- Прогнать `tools/map_geometry.py` readers на обеих картах и отвергнуть
  missing/linked/changed/degenerate inputs.

### 2. Offline deterministic worker matrix

На каждой карте записать одну и ту же command sequence и seed/order:

```text
settle → neutral → forward → brake → reverse → stop
settle → forward+left → forward+right → stop
settle → steering-only left → neutral → steering-only right
hold against known stone/wall → release → map-boundary approach
```

Сверять tick/seq, signed displacement, speed sign, contact masks, finite
coordinates, surface clearance и отсутствие выхода за bounds. Для collision
сохранить causal pair: полный mesh останавливает корпус; удаление только
закреплённых obstacle triangles меняет результат; изменение bounds меняет
только boundary result. Это не разрешает удалять triangles в обычном пуле.

### 3. Reconciliation / fault matrix

Изолированный harness подаёт серверные кадры с контролируемыми потерями,
дубликатами, перестановкой и задержкой. Проверки:

- stale frame не уменьшает `tick` и не возвращает старую position;
- duplicate frame не удваивает displacement/command application;
- пропущенный промежуточный кадр не превращает клиентскую позу в authority;
- correction ACK привязан к настоящему server sequence и принят ровно один раз;
- malformed/foreign entity state, wrong config SHA и out-of-bounds pose
  отклоняются без частичного world mutation;
- после закрытия/rejoin следующий baseline совпадает с последним принятным
  серверным state и не создаёт дополнительное движение.

### 4. Native compatibility slice

Только после зелёной offline/fault матрицы подготовить отдельную reversible
research-копию #717 и loopback gateway. Пассивно собрать native callbacks,
wire frames, server log и periodic state samples. Владелец вручную выполняет
короткую последовательность: вперёд, остановка, задний ход, левый/правый
поворот, подход к видимой стене, штатный выход и повторный вход.

Native PASS требует настоящего callback/wire evidence и визуальной проверки
владельца. Логи worker или одинаковые synthetic snapshots не доказывают, что
родная камера/матрица следует серверу. Если native queue/leave/re-entry
контракт не измерен, карточка остаётся `NOT_RUN` по этой части.

## Файлы и изменения

Этот черновик не меняет runtime. В implementation-карточке разрешённый
минимальный allowlist должен быть отдельным и явным:

- `server/physics/Program.cs`, `CheckedInput.cs`, `README.md` — только если
  trace докажет конкретную причину, с unit/IPC regression;
- `server/gateway/src/drive/worker.rs`, `world.rs`, map-drive compatibility
  files — только для server-owned state/correction wiring;
- `tools/map_geometry.py` — менять только при подтверждённой ошибке reader;
  existing frozen exports/tests сохранять;
- `tests/test_map_geometry.py`, `tests/test_map_drive_*`,
  `tests/test_arena_movement_*` и новая узкая reconciliation test module;
- ignored evidence: `local/evidence/20261008-p05-movement-collision-01/`.

Не трогать original/research client, deployed EXE, SQLite/identity fixtures,
accepted P03 code и P04 validator ради удобства теста.

## Проверки и команды

Команды ниже являются планом; `NOT_RUN` до фактического запуска:

```powershell
python -B -X utf8 server/check_layout.py --out local/evidence/20261008-p05-movement-collision-01/layout.json
python -B -X utf8 server/build.py physics --out local/build/server/physics-p05-movement-01
python -B -X utf8 -m unittest discover -s tests -p 'test_map_geometry.py' -v
python -B -X utf8 -m unittest discover -s tests -p 'test_map_drive_*.py' -v
python -B -X utf8 -m unittest discover -s tests -p 'test_arena_movement_*.py' -v
```

Если меняется Rust gateway, добавить изолированный canonical/legacy build с
`--test`; если меняется только worker, gateway test count не объявлять
доказательством physics. Полный Python suite запускать из основного checkout
с его `config/project.local.json`, а не превращать missing ignored evidence
из worktree в PASS.

Каждая команда должна сохранить stdout/stderr, exit code, source/artifact
hashes и append-only JSON receipt. Native run дополнительно сохраняет packet
capture, callback counts, server tick prefix, PNG SHA и rollback receipt.

## Приёмка

Минимальный offline PASS:

- обе карты загружены по pinned SHA и re-import дают одинаковый canonical
  result;
- settle имеет не менее трёх контактов и валидные wheel masks;
- forward/reverse/brake/turn имеют правильный знак скорости и finite bounded
  state;
- полный static obstacle и boundary causal tests PASS;
- worker timeout/error/EOF и malformed responses fail closed;
- reconciliation matrix PASS без client-coordinate authority;
- rollback/evidence audit PASS.

Native same-PC owner acceptance — отдельный gate поверх этого offline PASS:
родная модель/камера визуально следует движению и коррекции, препятствие не
проходится, reverse/turn не дают постоянного drift, штатный exit/re-entry
восстанавливает server state. Без ручной проверки статус остаётся
`PASS_OFFLINE_ONLY`, а не `PASS_OWNER_NATIVE_MOVEMENT`.

## Ожидаемые статусы до новой карточки

Пока план не исполнен:

| Область | Статус |
|---|---|
| Imported terrain/obstacle source contract | `PASS_P04_CONTRACT` |
| Existing worker smoke/mesh parser | `VERIFIED prior evidence` |
| New deterministic P05 matrix | `NOT_RUN` |
| Reconciliation fault matrix | `NOT_RUN` |
| Native manual movement/obstacle/re-entry | `NOT_RUN` |
| Tank–tank, destructibles, partial cruise | `NOT_RUN` |
| Historical physics / Linux / two-PC | `NOT_RUN` |

## Откат и единственный следующий шаг

Для реализации оставить эту ветку планом до отдельного owner-approved
implementation branch. Откат runtime не нужен: текущая карточка меняет только
этот документ. Для будущего запуска останавливать только receipt-matched
worker/gateway/client, выполнять соответствующий `interactive_client.py
rollback`, сохранять evidence и не делать `reset --hard` или force-push.

Единственный следующий рекомендуемый шаг: запустить offline deterministic
matrix из раздела 2 на обеих закреплённых картах и сохранить первый P05
receipt; native запуск не начинать до разбора этого результата.
