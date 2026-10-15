# P05C — shared Jolt scene component

Ночная работа разрешена владельцем 2026-10-16 без ожидания ручной проверки.
Основа этой ветки — P08B `c7999e6`, worktree `p05c-night-shared-physics`.
Статус: **PASS_COMPONENT / GATEWAY_INTEGRATION_NOT_RUN / NATIVE_NOT_RUN**.
Это компонент карточки, а не закрытая приёмка P05C.

## VERIFIED: что работает

- Новый IPC7 создаёт один PhysicsSystem и один процесс на1..6 машин. В боевой
  конфигурации coordinator должен требовать2..6; singleton нужен для сравнения.
- MS-1 и ИС-7 используют полные прежние профили P05B, `TrackedHandling`, колёса,
  тормоза, коробку, массу и инерцию. Числа не перенастраивались. Legacy IPC1–6
  остаются прежними; в Program.cs добавлен только выбор нового entrypoint.
- Все контроллеры обновляются до единственного Jolt update на подшаг. Выдаётся
  один batch после6×1/60s, sequence1..36000, ready после180 settling ticks.
- Танк–танк — обычный solid contact слоя1↔1. Никаких клиентских координат, HP,
  native method IDs или урона от тарана worker не принимает и не назначает.
- Один каталог8/terrain/static mesh на сцену. Первый фактический подходящий
  callback получает глобальное право на один debit и удаление объекта. Остальные
  manifolds видят sensor этого же подготовленного удаления. Callback order
  записывается в `fracture_claims`; InlineJobSystem закрепляет один поток.
- Старые scalar/angular kernels переиспользуются. У каждого actor сохраняются
  binding, witnesses и receipts; новый advance блокируется до единого scene ACK.

Политика `p05c-shared-scene-v1` — приближение test_lab. Она меняет старое
приближение двух независимых миров, где два actor могли отдельно потратить
энергию на один объект. Историческая семантика оригинального сервера UNKNOWN.
Кроссплатформенная повторяемость NOT_RUN.

## Файлы и границы владения

- `server/physics/BattleSceneInput.cs`: bounded manifest/config/IPC commands,
  source projection, server spawn, общий scene identity.
- `server/physics/BattleTank.cs`: body, controller, handling и state одного actor.
- `server/physics/BattleScene.cs`: единый мир, callback arbitration, общий step,
  prepared/ACK/removal и cleanup.
- `server/gateway/src/drive/scene_worker.rs` и `scene_worker/tests.rs`: checked
  Rust private-pipe transport, pinning runtime tree, полный batch parser.
- `server/gateway/src/shared/scene_runtime.rs`: маленький component coordinator.
- `tools/p05c_scene_checks/`: отдельный Rust harness без зависимости от копии
  wg-toolkit; `tools/p05c_{build,shared_scene_probe,catalog_probe,rust_worker_probe}.py`.

Root продолжает World/native integration после P08C. Эти файлы сами по себе не
подключены к gateway main; ordinary gateway не объявляется проверенным новым
режимом. Source assets читаются из `D:/WoT_9.1_Server/local`, без копирования
ресурсов, junction и symlink. Сборки находятся в local/build этого worktree.

## Контракт IPC7

Запуск:

```text
MapDriveWorker.exe --battle-scene PATH --scene-sha256 SHA --local-root ROOT --generation POSITIVE_U32
```

Manifest имеет ровно `version=1,profile="test_lab",policy="p05c-shared-scene-v1",
map,catalog,actors`. `map` — Karelia или Prohorovka. `catalog` — null либо
`{path,sha256}` существующего catalog8. Actor rows строго slot0..N−1, каждая
ровно `{slot,kind,config:{path,sha256},spawn_origin:[x,y,z],spawn_yaw}`.
Kind — ms1/is7, полный config3 проверяется против закреплённой физической
проекции AngularBodyBinding. Геометрические references/bounds всех actors
должны совпадать; исходно перекрывающиеся горизонтальные OBB запрещены.
Paths абсолютные, внутри явного root, без reparse. Manifest ≤32KiB, config≤16KiB.

Все команды содержат `version=7,generation,manifest_sha256,catalog_sha256`.
При отсутствии каталога его SHA —64 нуля. Bootstrap `restore_scene` и дальнейший
`sync_removed` дополнительно имеют `op,advance_seq,scene_version,
removed_object_ids,scene_sha256`. Список cumulative и строго возрастает; нельзя
забыть старое или prepared удаление. Для catalog8 hash прежний
`wot091-fragile-scene-v3\0` + raw32 catalog SHA + count/u32LE IDs.
Без каталога hash = SHA256 ASCII `wot091-empty-battle-scene-v1` + NUL.

`advance` дополнительно имеет `op,seq,ticks=6,scene_version,scene_sha256,inputs`.
Inputs ровно N строк slot0..N−1; каждая `{slot,throttle,steer,brake,speed_percent}`.
Throttle/steer−1..1; brake разрешён только при нулях; cruise100 либо50 при
ненулевом throttle без brake, либо25 только вперёд без brake. Весь batch
проверяется до первого update. Никакого implicit missing-input/default actor.

Ready/state/prepared имеют ровно `version,event,generation,manifest_sha256,
catalog_sha256,seq,tick,settle_ticks=180,map,scene_version,scene_sha256,actors,
tank_contacts,fracture_claims`. Tick =180+6seq. Actor row имеет
`slot,kind,config_sha256,profile_sha256,state`; state повторяет IPC6 angular
схему. Object contacts отсортированы по object ID; receipts сохраняют свой order.
Tank contacts ≤15 pair rows: `{slot_a,slot_b,substep,point,normal,
relative_velocity}`, slot_a<slot_b, normal направлен от a к b. Это диагностика,
не основание для HP. Global claim row — `{object_id,slot,substep,order}`; каждый
object встречается один раз и совпадает со своим actor receipt.

ACK `scene_synced`: `version,event,generation,manifest_sha256,catalog_sha256,
advance_seq,tick,scene_version,removed_object_ids,scene_sha256`; ни tick, ни seq
не продвигаются, точный повтор idempotent. Input ASCII≤32KiB, output JSON+LF
≤512KiB, глубина≤12, Rust nodes≤40000, максимум32 receipts на actor /192 global,
2048 catalog IDs. Один outstanding request. Startup120s, ответ/ACK500ms.
Ошибка — worker_error stderr/nonzero exit, никогда успешный частичный state.

## Rust API для интеграции

Подключить в main `#[path="drive/scene_worker.rs"] mod scene_worker;`, затем
shared модуль `scene_runtime` (он использует `crate::scene_worker`).

1. `Artifacts::load(artifact_manifest_path)`: точный полный runtime tree из
   `p05c_build.py physics`, включая DLL/native dependencies. Повторная проверка
   перед launch. Неперечисленный DLL, смена hash/size, reparse — reject.
2. `SceneSpec::load(asset_root,manifest_path,sha)` → immutable source set.
   `Scene::new(&spec,&removed_ids)` строит cumulative hash.
3. `Runtime::launch(artifacts,Arc<SceneSpec>,generation,scene,now)`; launch
   синхронно проверяет небольшие manifests/runtime pins и запускает child.
   В gateway выполнять подготовку в background startup job, чтобы не держать
   transport loop на hash I/O. `poll(now)` возвращает полный `Frame` или None.
4. Seq0 → импорт всех settled poses до native announcements. Обычный
   `advance(&[Input],now)` принимает ровно весь roster. `Frame.actors` содержит
   slot/kind/Pose и точные `proof` state Values; `Frame.raw` сохраняет весь batch.
5. Для prepared **обязательно** вызвать старый domain scalar proof verifier
   на каждом actor, связав profile/config/slot/session/battle/generation/scene.
   Структурная проверка IPC не заменяет FrameProof.validate. После staged World
   candidate вызвать `sync_removed(scene,now)`, дождаться `take_scene_ack()`;
   только затем публиковать World/native. Advance до consumption ACK запрещён.
6. `process_id/ready/pending/prepared_ids/scene`; `shutdown(self)` проверяет EOF,
   exit0 и reaping. Drop при ошибке убивает и reaps только собственный child.

Пока **NOT_RUN**: изменённый World, mixed AP/material semantics, six native
roster/ACK, P08C lifecycle integration. Нельзя выдавать компонент за эти gates.

## Реально выполненные проверки

Evidence root: `D:/WoT_9.1_Server/local/evidence/20261016-p05c-night-01/`.
Последний физический binary — `local/build/server/physics-p05c03/` этого
worktree, DLL SHA `d090ecb4e3e1c63d424d29db818896aa115e6bd0cac9728361b3f13ab97854aa`.
Последний Rust unit/build — `rust-p05c08` (7 PASS); actual Rust/Jolt receipt
`rust-worker04` использует checker `rust-p05c07`. Производственные Rust modules
между ними одинаковы; изменена только проверка hash JSONL fixture без newline
и source inventory в build helper. Новый запуск Jolt не выполнялся во время
полного gateway gate root, чтобы не создать искусственные deadline stalls.

| Gate | Факт |
|---|---|
| physics-probe02 |17 PASS: head-on, oblique, heavy-push,30s rest, same-build repeat371 frames; шесть mixed bodies / один PID;6 legacy comparisons;5 rejected input batches |
| P05B singleton comparisons | MS-1/ИС-7: launch→reverse, powered turn→release, cruise25/50;110/130/110 frames; максимальная разница pose/velocity **0** |
| Independent OBB SAT | max penetration head-on0.02317m, oblique0.02153m, push0.00308m; explicit5cm solver tolerance PASS |
| Stable rest | последние3s после30s торможения: drift≤0.000166m, max angular≤0.000049rad/s |
| catalog-probe02 |4 PASS: full unchanged catalog1038 objects, mixed2/6,5 prepared frames/7 claimed objects each, точные повторные ACK; advance-before-ACK/omitted claim rejected |
| Rust unit gate |7 PASS: complete6/source profiles, poisoned last actor/identity, bounded unique JSON, controls, scene digest, actual prepared fixture/global claim replay, runtime artifact tree |
| rust-worker04 |6 PASS: actual Rust↔Jolt,720 total batches, mixed2/6 + singleton MS-1/ИС-7 + catalog2/6;120 batches/run, один PID, EOF exit0/reaped |

Catalog probes явно разрешают физический ACK без World: они проверяют IPC/scene
механику и **не** обозначают domain scalar gate PASS. Никакого native клиента,
оригинальных файлов, базы профиля13 или запущенного стенда не трогали.

Prepared fixture `tools/p05c_scene_checks/fixtures/ipc7-prepared.json` — наш
фактический IPC7 frame seq7 из catalog-probe02, не клиентский ресурс. SHA
payload без JSONL newline `017ea3289d9d4e4a1a81777aeda78a64e1f6efcc79edeb6b1d644105d0d95c1e`;
producer output log SHA `c169bc38d2f17754a54c04fc96fff58db2c2ea0d21a4e4a6a128d24b06cd89ee`.

Сохранённые неуспехи: rust-p05c01 — syntax/module path compile errors;
rust-worker01 — Windows canonical `\\?\` spelling passed to C# root, исправлено
de-prefix только drive-qualified аргументов; catalog-probe01 —6 slots на одной
широкой линии не settled на исходной геометрии. Во втором harness used две
проверенные колонки по три ряда; geometry/collider/settling gate не ослаблялись.
rust-p05c06 — отрицательный тест присваивал уже имевшийся slot1, исправлен тест
на другую сторону фактического owner. Исходные FAIL receipts не перезаписаны.

## Команды и откат

Из этого worktree, всегда новые output directories:

```powershell
python -B -X utf8 tools/p05c_build.py physics --asset-root D:/WoT_9.1_Server/local --out local/build/server/physics-p05c03
python -B -X utf8 tools/p05c_shared_scene_probe.py --asset-root D:/WoT_9.1_Server/local --worker local/build/server/physics-p05c03/bin/MapDriveWorker.exe --out D:/WoT_9.1_Server/local/evidence/20261016-p05c-night-01/physics-probe02
python -B -X utf8 tools/p05c_catalog_probe.py --asset-root D:/WoT_9.1_Server/local --worker local/build/server/physics-p05c03/bin/MapDriveWorker.exe --out D:/WoT_9.1_Server/local/evidence/20261016-p05c-night-01/catalog-probe02
python -B -X utf8 tools/p05c_build.py rust --asset-root D:/WoT_9.1_Server/local --out local/build/server/rust-p05c08
python -B -X utf8 tools/p05c_rust_worker_probe.py --asset-root D:/WoT_9.1_Server/local --checker local/build/server/rust-p05c07/target/debug/p05c-scene-checks.exe --artifacts local/build/server/physics-p05c03/artifacts.json --physics-evidence D:/WoT_9.1_Server/local/evidence/20261016-p05c-night-01/physics-probe02 --catalog-evidence D:/WoT_9.1_Server/local/evidence/20261016-p05c-night-01/catalog-probe02 --out D:/WoT_9.1_Server/local/evidence/20261016-p05c-night-01/rust-worker04
```

Откат компонента — revert его commit в этой отдельной ветке; deployed binaries
не заменялись, client patch не ставился. Не удалять/архивировать worktree до
сохранения нужных собственных build receipts; junction/symlink в нём нет.

Единственный следующий шаг — связать checked batch с World/native в root после
P08C, сохранив scalar proof admission и STAB-01 fail-closed boundary; затем
отдельно выполнить утреннюю native-приёмку.

## Интеграция P05C после P08C — VERIFIED на 2026-10-16

Core snapshot `6967f6a` уже включает P08C `2ef781f` и native capacity snapshot.
Новый маршрут включается только явным manifest **version2**: прежние поля
`map/catalog/profiles` сохраняются, добавляется `shared_physics:{path,sha256}`
с полным authored artifact manifest. Config `battle_players` — optional integer
2..6 (default2), больше2 разрешено только в profile13 + version2. Version1 и
legacy IPC1–6 продолжают использовать прежние два отдельных worker.

VERIFIED: `World::new_for_roster(id,now,map,count)`, `expected_actors()`,
`mixed_profiles()` и `shot_limit()` дают отдельную bounded модель. CAPACITY2
сохранена для legacy; MAX_ACTORS6/MAX_BATTLE_SHOTS576 — абсолютные потолки.
MS-1 сохраняет96 ББ, ИС-7 —30; смешанные3+3 имеют378 выстрелов, не576 подаренных.
Каждый actor сохраняет frozen kind/HP/ammo/reload/geometry/material identity.
Снаряд проверяет все остальные реальные meshes, выбирает ближайшую цель по
параметру пересечения (точный tie — меньший slot), затем исходный Trace повторно
считает выбранный collision batch и terrain precedence. AP использует shell
стреляющей машины и material/HP цели. Предварительные query других машин не
сохраняются как отдельные Trace events; World + complete actor snapshot нужны
для воспроизведения выбора между целями. Это ограничение диагностики, не
доказательство исторической баллистики.

VERIFIED: `server_scene_runtime.rs` подключён через существующий runtime wrapper.
Один background startup job создаёт маленький manifest, проверяет source/artifact
pins и запускает один child. Transport loop не выполняет hash/read/sync больших
ресурсов. Frame содержит всех акторов; перед candidate World каждый actor проходит
**тот же** `drive/worker/angular.rs::parse` и `ram_proof::FrameProof::validate`,
включая source body binding, witnesses, receipts, chain arithmetic и final motion.
`shared_angular_proof` — только thin wrapper, нового scalar verifier нет.
Новая сцена/подготовленный fracture становится доступна native только после
единого точного ACK. Быстрый reply текущего100ms bucket хранится целиком до
следующего domain tick; второго advance в этот момент нет.

VERIFIED: physical epoch/session хранится отдельно от текущего transport session.
Выход, disconnect и смерть дают STOP controls, но тело остаётся в PhysicsSystem,
его подтверждённый pose импортируется и может измениться от контакта/инерции.
Scene не перезапускается на выходе одного игрока. Frozen outcome останавливает
physics dispatch/domain damage; прямой batch step остаётся успешным и неизменным
на протяжении восьми секунд AFTERBATTLE. Drop убивает/reaps только owned child.

Реальные интеграционные evidence:
`D:/WoT_9.1_Server/local/evidence/20261016-p05c-night-01/domain-integration01/`.
Сборка gateway в нашем worktree — `local/build/p05c-gateway-compile08.log` PASS;
авторитетный full gateway gate после итогового commit выполняет root.

- `p05c-actual-domain03.log`: **1 PASS**, два последовательных case2/6,
  по120 complete batches / один неизменный PID на case. По7 реальных объектов
  прошли producer→исходный scalar verifier→World+Trace→пять scene ACK commit.
  После60 batches последний actor detached, в6-body case ещё один actor убит;
  оставшиеся двигаются, HP/ammo не восстанавливаются, process ID сохраняется.
  После этого80 шагов AFTERBATTLE не меняют actors/HP/ammo/Trace/scene/tick.
- `p05c-scalar-bridge01.log`: **1 PASS**, сохранённый настоящий IPC7 frame
  пропущен через исходный IPC6 parser; изменённый body binding отклонён.
- `p05c-mixed-model01.log`: **3 PASS**, реальные per-kind бюджеты378,
  ближайшая mixed цель slot3 с ИС-7 geometry/material, pushed parked/dead poses.
- `p05c-ap01.log`: **11 PASS**, прежний AP gate; `p05c-impact01.log`:
  **53 PASS**, прежний полный Trace gate. Ранее core model39 и native wire six2
  также PASS; отдельные namespace/native six gates выполняет root.

Сохранён FAIL `p05c-actual-domain01.log`: background job создавал свой более
новый Instant, чем текущий dispatcher turn. Producer polling получал clock
regression. Исправлено единым dispatcher start epoch; startup120s включает IO.
`domain02` подтвердил2/6, `domain03` дополнительно восемь секунд freeze.

UNKNOWN / NOT_RUN: настоящий mixed native таран/дребезг/звуки/UI, шесть живых
клиентов, итоговый native экран и сетевой первый тест. Доменные owners в тестах
изолированные authored fixtures, не шесть созданных настоящих аккаунтов.
Урон тарана не реализован; контакт танк–танк — Jolt solid без HP policy.
Новые исторические параметры/машины и видимость относятся к следующим карточкам.

Команды для канонического checkout (fresh output):

```powershell
python -B -X utf8 server/build.py gateway --test --test-filter p05c_ --out local/build/server/gateway-p05c-focused-NN
python -B -X utf8 server/build.py gateway --test --out local/build/server/gateway-p05c-full-NN
```

В изолированном worktree — `tools/p05c_gateway_checks/README.md`; toolchain,
resources и зависимости читаются по разрешённым абсолютным путям. Откат runtime:
revert P05C commits на отдельной зависимой ветке и вернуть version1 manifest;
main/клиентские файлы/БД этим integration gate не менялись. Статус приёмки —
**автоматический focused gate PASS, полный gate ожидается; native NOT_RUN**.
Следующий рекомендуемый шаг — полный gateway gate root и утренняя native matrix.
