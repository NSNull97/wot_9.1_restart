# Tactical hangar UI audit — 2026-10-08

## P03J native map-drive aim/tracer — 2026-10-08

Карточка закрыла runtime-разрыв после наблюдения «выброс после выстрела, без
трассера и КД». Причина была в двух местах: native fire приходил в составном
Avatar envelope вместе с aim/movement body, а server callback-и выстрела,
трассера и БК/КД нельзя было склеивать в один body. Теперь bounded parser
выделяет только contiguous fire-prefix и валидирует хвост штатным map-drive
parser; server queues accepted ammo/reload, `Avatar.showShooting` и
`Avatar.showTracer` отдельными reliable body. `stopTracer` и reload completion
публикуются только по server monotonic deadline.

Изолированный pinned gateway build07: **372/372 Rust tests PASS**, EXE SHA-256
`1fa92e383d80f1118b4ac95dc7b3d08b5ebbfcf69446f851bfb59832cdcb5b45`;
deployed service сейчас работает на этом SHA. Runtime receipt
`local/evidence/20261008-p03j-native-aim-tracer-06/`: visible client exit 0,
8 accepted shots (`20 -> 12`), 8 reload completions (`0.0/2.5`), 8 tracer
stops, zero `INTERACTIVE_REJECT`; owner сообщил, что последний видимый прогон
теперь выглядит нормально. Hit/damage, полноценная видимость второго клиента
и equipment остаются **NOT_RUN**.

На ветке `codex/p02-hangar-tactical-ui-audit` выполнен только статический
аудит requested Tactical Steel UI. Приклеенный запрос обрывается на
`EquipmentPresentationAdapter`, поэтому критерии приёмки после этой строки не
выдумывались. Подтверждены реальные точки входа старого клиента: compiled
Python 2.7.3 `Hangar.pyc`, `TankCarousel.pyc`, `params.pyc`, `crew.pyc`,
`LobbyView.pyc`, их `HangarMeta`/`TankCarouselMeta` contracts и package-index
entries `hangar.swf`, `TankCarousel.swf`, `carousels.swf`, `crew.swf`,
`AmmunitionPanel.swf`, `vehicleInfo.swf`, `lobby.swf`, `LobbyMenu.swf` и
`inventory.swf`. Отчёт: [P02 Tactical UI audit](research/P02_TACTICAL_HANGAR_UI_AUDIT.md),
план: [P02 audit plan](plans/P02_TACTICAL_HANGAR_UI_AUDIT.md), receipt:
`local/evidence/20261008-p02-tactical-ui-audit-01/summary.json`.

Статус: **PASS_STATIC_PIPELINE_AUDIT / REPLACEMENT_NOT_RUN**. Новый Flash/SWF
artifact, ActionScript/FLA source, совместимый compiler/repacker и native
screenshot/click acceptance отсутствуют. Original и research client не
менялись; сервер, протокол и игровые данные не трогались. В соответствии с
`prompts/FIRST_PROMPT.md` реализация UI отложена до отдельной owner-gated P02
карточки. Единственный следующий шаг — один replacement spike существующего
`params` или carousel компонента с hash-pinned Flash artifact; без artifact
результат остаётся `NOT_RUN`.

# Fresh current-head evidence after status-only merge — 2026-10-08

На проверенном head `39b36078a1030387fb95c3578d52cee28b4a6051`, совпавшем с
`origin/main` на момент запуска, сохранены receipts текущего checkout. P04
bundle/import/map suite — **42/42 PASS**; standalone bundle CLI —
`PASS_CONTENT_BUNDLE`, typed importer — `PASS_TYPED_IMPORT_VALIDATOR`,
canonical SHA-256
`a1b1191b29bbae5e2aed2f4417a139c7e9a2e6740ec40698347ad6baa8aac2b9`.
Receipt `local/evidence/20261008-p04-current-main-11/summary.json`, SHA-256
`e7fd34cd33ee278595944012f601d5d67990344320e004b791877b2f3679cafb`.

P03I/P09A static subset — **17/17 PASS**: request 202 / command 700,
`INT16, INT16, INT64, INT32, INT32`; TechTree handoff and visibility matrix
сохраняют static-only статус, 374 trees / 3945 nodes / 2062 edges,
`IS-8 -> IS-7`. Receipt
`local/evidence/20261008-p03i-p09a-current-main-12/summary.json`, SHA-256
`8202aeb6ff5ec78483f9d06409f288295ee4a2d6f4f1f01d6ee677f6a21cd0ae`.
Native payload/callback/screenshot, queue/server handoff и runtime eligibility
остаются `NOT_RUN`.

После этого status-only merge полный UTF-8 regression на проверенном head
`a23e602e74967d520a2e2ef9ee296a6e9da740c2` дал **2187 тестов, 0
failures/errors, 4 known skips**. Receipt
`local/evidence/20261008-current-main-14/summary.json`, full log SHA-256
`8f9c7648f40a57edc348e02156c94245703c9bbba1c3eeb67a648ead265e454e`.

# Current-head goal recheck — 2026-10-08

Проверенный code head `283bf5f55c05514a2541bd84bca1feabf7aaab20` на момент
запуска совпадал с `origin/main`; после него был только status-only merge.
Goal-specific набор прошёл **59/59**, полный
UTF-8 regression — **2187 тестов, 0 failures/errors, 4 known skips**. Receipt:
`local/evidence/20261008-p04-p03i-goal-recheck-10/summary.json`; targeted log
SHA-256 `8479145bf727b7615e1d4058323e3bc1dd929f2c0b9c29a25dbb142084982eb7`,
full log SHA-256
`d65e0e57f9fd357d44a948e26ba0d0f5abdfe17d6c43db083b564c43e3cfd81f`.

P04 typed import — `PASS_TYPED_IMPORT_VALIDATOR`, canonical SHA-256
`a1b1191b29bbae5e2aed2f4417a139c7e9a2e6740ec40698347ad6baa8aac2b9`; P03I
static — `PASS_P03I_STATIC_SOURCE_RECHECK`, request 202 / command 700,
`INT16, INT16, INT64, INT32, INT32`; P09A static graph — 374 trees, 3945
nodes, 2062 edges, `IS-8 -> IS-7`. Native payload/callback, queue/server
handoff, account/shop payload and UI screenshot остаются `NOT_RUN` до
owner-gated capture.

# P06E bounded client-collision static recheck — 2026-10-08

Добавлен bounded read-only `tools/p06e_client_collision_static_audit.py`.
Он проверяет SHA-256 принятого #717 bytecode receipt и P06E summary, не
исполняя client bytecode, и измеряет ровно восемь методов collision/flight,
включая пропущенный ранее wrapper `collideDynamicAndStatic`. Targeted suite
`tests.test_p06e_client_collision_static_audit` — **6/6 PASS**; receipt
`local/evidence/20261008-p06e-static-audit-01/receipt.json` имеет статус
`PASS_STATIC_CLIENT_COLLISION_BOUNDARY_RECHECK`. Duplicate/non-finite/depth/item,
path и mutation controls закрыты. Native server hit, penetration/damage,
callback bytes и solver equivalence остаются `UNKNOWN/NOT_RUN`; клиент,
gateway и deployed service не запускались.

# Overnight verification after P09B harness — 2026-10-08

## P08A bounded lifecycle static recheck — 2026-10-08

`tools/p08a_lifecycle_static_audit.py` повторно закрепил hash-bound P00/P01
`lifecycle-static.json`, `contracts.json`, `resource-facts.json` и
`sources.json`. Проверены группы Account/Avatar/Arena/Vehicle, измеренные
typed method/property shapes, containment путей и bounded JSON guards
(duplicate/non-finite/depth/item). Targeted suite
`tests.test_p08a_lifecycle_static_audit` — **8/8 PASS**. Receipt и hashes
записаны в ignored каталоге `local/evidence/20261008-p08a-static-audit-01/`.

Это всё ещё `PASS_STATIC_SOURCE_BOUNDARY_ONLY`: native Account → Avatar → Arena
→ Vehicle, wire IDs/order, callback bytes, server handoff, UI/audio/timer и
client/gateway/service остаются `UNKNOWN/NOT_RUN`.

## P07A bounded visibility static audit

`tools/p07a_visibility_static_audit.py` now rechecks the hash-bound P00/P01
contracts and source manifest for exactly eight typed `Avatar`/`Vehicle`/`Arena`
visibility declarations, then re-hashes all six selected files in both
permitted #717 copies. Its receipt is
`local/evidence/20261008-p07a-static-audit-01/receipt.json`, SHA-256
`8dd8bfab40f7b9a53cb2e28da8b4e8b38a09c1f06a632fc157d7801ba4d25c76`;
`tests.test_p07a_visibility_static_audit` is **9/9 PASS**. Duplicate keys,
non-finite JSON, excessive depth/items, path escapes, duplicate manifest rows
and mutated declarations are rejected. Wire IDs, serializer order, native
LOS/occlusion, recipient filtering and server handoff remain
**UNKNOWN/NOT_RUN**; no runtime/client/service was started.

## Latest P04/P03I/P06B/P06E/P07A/P08A/P09A/P10A current-main recheck

На code head `d0674b6b38c4611ff962ecb3c17300bf17f7c20b`, который совпадал с
`origin/main` на момент запуска, повторён UTF-8 full regression: **2187 тестов,
0 failures/errors, 4 known skips**. Лог
`local/evidence/20261008-p06b-p06e-current-main-01/full-python-utf8.txt`,
SHA-256 `80441128c571488ee874cbe63d6b2b8975d804a3d9e66d4ce061f51c21220b1f`.
P04 bundle/import/map targeted suite — **42/42 PASS**, P03I static audit —
**5/5 PASS**, P06B source — **12/12 PASS**, P06E collision boundary — **6/6
PASS**, P07A visibility — **9/9 PASS**, P08A lifecycle — **8/8 PASS**, P09A
TechTree static audit — **5/5 PASS**, P09A NationObjDumper/static-nested audit —
**7/7 PASS**, P10A training-room static audit — **6/6 PASS**. Combined targeted
run — **100/100 PASS**. Layout — 58 source files / 22 relocations, docs-link
recheck — 449 внутренних ссылок, 0 missing targets.
Combined summary:
`local/evidence/20261008-p06b-p06e-current-main-01/summary.json`, SHA-256
`d2a2e3ed047f7666409a74b6f6c049aa3456f06aea56afa204170810850869c4`.

# P03I static source-hash recheck — 2026-10-08

The bounded read-only `tools/p03i_static_audit.py` audit reports
`PASS_P03I_STATIC_SOURCE_RECHECK`; targeted tests are **5/5 PASS**. Receipt:
`local/evidence/20261008-p03i-static-audit-01/receipt.json`, SHA-256
`381c6451c964d6f6add2e28e12abf581ece0af8751825e4106e5958efa55302c`.
Both permitted #717 client copies match the tree-predicate and queue source
hashes; `Account.def` confirms request 202, command 700, envelope
`INT16, INT16, INT64, INT32, INT32` and
`onEnqueueFailure(UINT8, UINT8, STRING)`. The audit records one stale hash in
the ignored queue README for `functions.pyc` (`dc7e27aacd46e0f2a...` instead of
the verified `dc7e27aacd46f0e2a...`). Native CMD700 framing, callback bytes and
server handoff remain `NOT_RUN`; no runtime, client or fixture was touched.

## Current-main final-09 recheck

На code head `4d9c5fb2e95c337d3972f02745f22641df8fd586`, который совпадал с
`origin/main` на момент запуска, повторён UTF-8 full regression: **2125 тестов,
0 failures/errors, 4 known skips**. Затем внесён только status-only docs merge;
runtime/source не менялись. Лог
`local/evidence/20261008-overnight-final-09/full-python-utf8.txt`, SHA-256
`c4f326c7a1f82b10cfd4770643d6bc47b5284d424387a80c20f2220844a1f87d`.
`server/check_layout.py` вернул `PASS_SERVER_SOURCE_LAYOUT` для 58 source files
и 22 relocations, receipt SHA
`4973971a5503f3fef21c18ba56c086ede47f8c03f1fbeafb5bbc06c7486857c2`.
Свежий bounded docs-link recheck дал `PASS_DOC_LINK_RECHECK`: 434 внутренних
ссылки, 0 missing targets; 105 внешних/абсолютных ссылок пропущены как
исторические или внешние. Receipt SHA
`2572ee6be18bbaae31abc194e9acf594b49dcd8a0927dd9f98fcd390679e6bfba`.

# P09A Phase A static fixture visibility matrix — 2026-10-08

The bounded read-only `tools/research_tree_visibility_matrix.py` verifier and
`tests/test_research_tree_visibility_matrix.py` freeze the server-owned
`r3-catalog3` fixture against the hash-bound #717 static graph. Targeted
verification is **7/7 PASS** and the receipt
`local/evidence/20261008-p09a-visibility-matrix-01/receipt.json` is
`PASS_STATIC_FIXTURE_VISIBILITY_MATRIX` (SHA-256
`b291bccd2a32c682cb4b09aae6763c27d5f9c907d323b8d072748676c4687a46`).

The matrix rows are MS-1 compact descriptor **3329** and IS-7 compact
descriptor **7169**. Both are present in `state.bin` vehicle
`inventory[1].compDescr`, present in `shop.items.itemPrices` and members of
`shop.items.notInShopItems`. `expected_native_visibility=UNKNOWN` and
`runtime_eligibility=NOT_RUN` remain explicit. The fixture has no separate
unowned reference descriptor, recorded as
`unowned_reference.status=NOT_AVAILABLE_IN_FIXTURE`.

The verifier rejects unknown compact IDs, duplicate `notInShopItems`, graph or
catalog hash mismatch, malformed literal bytes and paths outside the
repository. It uses the bounded literal decoder from the existing verifiers;
no pickle/unpickle, client import, service, gateway or original/research
client was started. After the merge, the authoritative UTF-8 full regression
ran **2125 tests in 37.699s, OK (skipped=4)**; log
`local/evidence/20261008-overnight-final-08/full-python-utf8.txt` has SHA-256
`f34ce9589fca54e549b1cf7ae0a2016d800bf8a1186adb98b7a32e5279a97ff7`.
Layout remains `PASS_SERVER_SOURCE_LAYOUT` (58 source files / 22 relocations)
in `local/evidence/20261008-overnight-final-08/layout.json` with SHA-256
`4973971a5503f3fef21c18ba56c086ede47f8c03f1fbeafb5bbc06c7486857c2`.

# P09B isolated SQLite transaction harness — 2026-10-08

The narrow server-owned `reserve_vehicle` boundary is now implemented only in
`tools/game_profile_tx.py`. It uses a stdlib SQLite game snapshot, vehicle
state rows and command ledger under one `BEGIN IMMEDIATE` transaction. Exact
duplicate replay returns the committed result; payload mismatch, stale
revision, unknown vehicle and already reserved vehicle fail closed. An injected
pre-commit failure is rolled back and the database is reopened to verify there
is no partial snapshot or ledger row.

Targeted `tests.test_game_profile_tx` is **13/13 PASS**. The ignored CLI receipt
`local/evidence/20261008-p09b-transaction-harness-01/receipt.json` is
`PASS_P09B_SQLITE_TRANSACTION_HARNESS`, SHA-256
`cedec631a51a5bf802381f04ad6690582518f3b341e0ce1f78e4bd775a614150`.
This is a bounded harness only: migration, deployed service wiring, battle
lease lifecycle, economy, concurrency/load and native restart remain
**NOT_RUN**. No client, gateway or deployed service was changed.

После P09A MS-1 root guard повторён authoritative UTF-8 regression:
**2118 tests, 0 failures/errors, 4 known skips**. Полный лог:
`local/evidence/20261008-overnight-final-06-full-python-utf8.txt`, SHA-256
`11da64256a7822a19d9df07455c608d1a20cf8ded49be2cf5aab8fb478a7ad2e`.
`server/check_layout.py` снова вернул `PASS_SERVER_SOURCE_LAYOUT` (58 source
files, 22 single-source relocations); layout SHA остался
`4973971a5503f3fef21c18ba56c086ede47f8c03f1fbeafb5bbc06c7486857c2`.
Runtime, gateway, client и deployed service не менялись и не запускались этой
карточкой.

# P09B persistence/transaction boundary — 2026-10-08

Исходная docs-only карточка `codex/p09b-persistence-boundary` зафиксировала
границу, после чего отдельная harness-карточка добавила
`PASS_P09B_SQLITE_TRANSACTION_HARNESS`. Зафиксирована граница:
`game.account.v1` проверяет принадлежность и SHA/ревизию server-owned профиля,
profile4 chain хранит offline provenance, а battle-loadout adapter делает только
revision/loadout binding. Ни один из этих слоёв не является transaction ID,
reservation, consumption или exactly-once result ledger.

Проверено read-only по `server/identity/schema.mjs`, `account_service.mjs`,
`ownership.mjs`, profile4 chain/semantic diff и
`server/gateway/src/battle/profile4_adapter.rs`. Предложенная P09B
transaction boundary (server-owned command key, expected revision, atomic game
ledger + snapshot, duplicate replay and stale fail-closed) теперь доказана в
изолированном harness; integration, migration, reservation lease, economy,
crash/restart recovery и native acceptance остаются **NOT_RUN**.

План: [P09B plan](plans/P09B_PERSISTENCE_TRANSACTION_BOUNDARY.md); исследование:
[P09B research](research/P09B_PERSISTENCE_TRANSACTION_BOUNDARY.md); evidence:
[P09B index](evidence-index/P09B.md).

# P10A training-room static boundary — 2026-10-08

P10A закрыла bounded static contract audit по P00/P01 `account.def`,
`prebattle.def`, `unitmgr.def` и hash-bound client manifest. Аудитор проверяет
7 Account base methods, 5 Account client methods, 21 Prebattle base methods и
9 source entries по exact byte count/SHA-256; targeted suite — **6/6 PASS**.
Доступны только имена/формы `createTraining`, `createDevPrebattle`, invites,
roster/team/player ready, `onArenaCreated` и `onArenaFinished`; opaque `PYTHON`
roster payload остаётся bounded/UNKNOWN. Receipt:
`local/evidence/20261008-p10a-static-audit-01/receipt.json`, SHA-256
`38cba6df11e6e7caac872f69cf038197a7de56b6956ae5182172f41b28549d50`.
Кандидатная state machine — **INFERRED / PLAN_ONLY**, не native порядок.

Wire IDs/order, invite accept/password, room owner/revisions, cancel-vs-start
race, two-room isolation, battle admission, queue/matchmaker/platoons и native
UI остаются **UNKNOWN/NOT_RUN**. Следующий шаг — owner-gated capture одной
private training room и второй независимой комнаты. См. [P10A plan](plans/P10A_TRAINING_ROOM_STATIC.md),
[research](research/P10A_TRAINING_ROOM_STATIC.md) и [evidence](evidence-index/P10A.md).

# P05 bounded movement-matrix receipt audit — 2026-10-08

Добавлен bounded read-only `tools/movement_matrix_audit.py` и 14 targeted
negative/positive tests. Он проверяет `p05-deterministic-matrix.v1` без запуска
worker: bounded UTF-8 JSON, duplicate/non-finite rejection, pinned map/config
SHA, counts, sequence/tick prefixes, phase order, optional finite event poses и
запрет client-authority полей. Реальные aggregate receipts проходят как
`PASS_OFFLINE_MATRIX_SHAPE_ONLY`; `pose_validation=NOT_PRESENT_IN_AGGREGATE`,
`native_status=NOT_VERIFIED_BY_AUDITOR`.

Targeted suite: **14/14 PASS**; полный UTF-8 regression после карточки:
**2097 tests, 0 failures/errors, 4 known skips**. Full log:
`local/evidence/20261008-overnight-final-03/full-python-utf8.txt`, SHA-256
`c4b096bca87f0e14684991a653f1bd2b16c692506e4294e18723a0ae21a82f75`.
Layout снова `PASS_SERVER_SOURCE_LAYOUT` (58/22), receipt
`local/evidence/20261008-overnight-final-03/layout.json`, SHA-256
`4973971a5503f3fef21c18ba56c086ede47f8c03f1fbeafb5bbc06c7486857c2`.
Тесты auditor не требуют ignored receipt: при его отсутствии shape/negative
контур использует встроенную bounded fallback fixture, а при наличии проверяет
реальный receipt. Native movement, reconciliation, collision causality и
историческая физика остаются `NOT_RUN`. Подробности: [P05 matrix audit](research/P05_MATRIX_RECEIPT_AUDIT.md)
и [evidence index](evidence-index/P05_MATRIX_AUDIT.md).
# P05 offline deterministic matrix — 2026-10-08

На двух hash-pinned test-lab фрагментах (`01_karelia` и `05_prohorovka`)
прогнан одинаковый deterministic matrix из 160 команд на карту. Worker вернул
`PASS_OFFLINE_DETERMINISTIC_MATRIX`: по 161 событию, tick `180 → 1140`,
sequence `0 → 160`, finite state и return code 0, без stderr ошибок. Receipts:
`local/evidence/20261009-p05-deterministic-matrix-01/summary.json` и два
map-result JSON с SHA в [P05 evidence index](evidence-index/P05.md).

Это только test-lab контракт. Native movement, историческая физика,
tank–tank/static obstacle causality, prediction/correction, rejoin и ручная
приёмка владельцем остаются `NOT_RUN`; engine RPM, скорости левой/правой
гусеницы, gear/clutch и delivered torque остаются `UNKNOWN_NOT_IN_WORKER_STATE`.
План/исследование: [P05 plan](plans/P05_MOVEMENT_COLLISION_RECONCILIATION.md) и
[P05 offline research](research/P05_OFFLINE_DETERMINISTIC_MATRIX.md).

# Overnight verification — 2026-10-08

После docs-only merges P03I review, P05 offline matrix/auditor, P07A, P08A,
P09B, P10A и self-contained test fallback повторён authoritative UTF-8
regression: **2097 tests, 0 failures/errors, 4 known skips**. Полный лог:
`local/evidence/20261008-overnight-final-03/full-python-utf8.txt`, SHA-256
`c4b096bca87f0e14684991a653f1bd2b16c692506e4294e18723a0ae21a82f75`.
`server/check_layout.py` вернул `PASS_SERVER_SOURCE_LAYOUT` (58 source files,
22 single-source relocations); layout receipt
`local/evidence/20261008-overnight-final-03/layout.json`, SHA-256
`4973971a5503f3fef21c18ba56c086ede47f8c03f1fbeafb5bbc06c7486857c2`.
Между baseline `6ed8424` и текущим head добавлены только docs/evidence и
bounded auditor/test files;
runtime, gateway, client и deployed service не менялись.

# P07A/P08A static source boundaries — 2026-10-08

Два docs-only среза расширили исследование без выдуманного native runtime:

- P07A получил **PASS_STATIC_VISIBILITY_SOURCE_BOUNDARY** по восьми
  hash-bound декларациям `Avatar`/`Vehicle`/`Arena` из P00/P01. Wire IDs,
  порядок, LOS, interest filtering, кусты, задержки засвета и native
  replication остаются `UNKNOWN/NOT_RUN`. Receipt и границы: [P07A
  evidence](evidence-index/P07A.md).
- P08A получил **PASS_STATIC_SOURCE_BOUNDARY_ONLY** по typed
  lifecycle declarations `PlayerAccount`/`PlayerAvatar`/`ClientArena`/`Vehicle`.
  Wire envelope/order, native state machine, HUD, звук, timer и 10-бойная
  ручная приёмка остаются `UNKNOWN/NOT_RUN`. Receipt и границы: [P08A
  evidence](evidence-index/P08A.md).

Оба среза не меняют runtime, gateway, базу, fixture или original/research
client. Следующие gates владельца: P07A — двухклиентский fixed-occlusion
capture payload/callback; P08A — bounded native lifecycle capture с UI/audio и
результатами боя. Нельзя превращать имена статических методов в guessed
serializer или battle solver.

# P09A preparation — native research-tree visibility — 2026-10-08

Подготовлена docs-only карточка `codex/p09a-research-tree-visibility`:
**PASS_P09A_PLAN_STATIC_PREDICATE_AND_HANDOFF_GATE**. Она фиксирует узкий
контур P09: полный справочный граф #717 остаётся неизменным, а видимость узлов
в нативном окне определяется authoritative shop payload и predicate
`item.isHidden ← shop.items.notInShopItems`. В графе подтверждены уровни I–X
СССР и направленная связь **ИС-8 → ИС-7**; ИС-7 терминальный.

Статический predicate подтверждён receipt
`local/evidence/20261007-native-tree-filter-01/predicate-01.json`. Нативный
account/shop payload, callback `requestNationTreeData/getNationTreeData`,
визуальная сверка окна и ownership matrix пока **NOT_RUN**. Выбор ИС-7 в
ангаре не закрывает очередь/бой: текущие `crew_assigned=false` и ammo `0`
оставляют admission `FAIL_CLOSED`.

План: [P09A plan](plans/P09A_RESEARCH_TREE_VISIBILITY.md); исследование:
[P09A research](research/P09A_RESEARCH_TREE_VISIBILITY.md); receipt:
[P09A evidence](evidence-index/P09A.md).

# P05 read-only geometry/movement audit — 2026-10-08

На основе принятого P04-контракта выполнен read-only аудит следующего узкого
среза P05. `tests.test_map_geometry` дали **26/26 PASS**, существующие
`test_map_drive_*` — **354/354 PASS**, `test_arena_movement_*` — **75/75 PASS**.
Свежая квитанция и stdout сохранены в
`local/evidence/20261008-p05-geometry-audit-01/` и
`local/evidence/20261008-p05-movement-matrix-01/`.

Проверены только bounded static reader, fault controls и test_lab worker:
две hash-pinned карты, geometry smoke, четыре offline collision pairs и
negative controls. Отдельный Jolt sphere spike дал один контакт за 300 шагов;
изолированная canonical PhysicsWorker build PASS (DLL SHA
`b81c00db040ae3db53880c7abd1ac35d6270757f77107c953e0edf63f8a267eb`).
Это не закрывает native collision, историческую физику, tank–tank,
prediction/correction или ручную приёмку.

В `main` добавлен план [P05 movement/reconciliation](plans/P05_MOVEMENT_COLLISION_RECONCILIATION.md)
(merge `dccfdabe`). Runtime, deployed gateway, база и оригинальная/research
копии клиента не менялись. Следующая узкая карточка — `P05A-pivot-diagnostics`:
свободный MS-1, 60 Hz neutral/left/right trace, диагностика гусениц и bounded
replay; параметры контроллера не менять до измерения причины слабого pivot.

Карточка P05A уже добавила bounded offline harness в merge `b8b1806`:
`tools/pivot_diagnostics.py` запускает четыре свежих worker-сценария только по
зафиксированному JSONL-контракту, а `tests/test_pivot_diagnostics.py` проверяют
план, monotonic `seq/tick`, finite pose, bounds, contacts и отрицательные
случаи. Свежий recheck на hash-pinned ignored worker/config дал
**PASS_OFFLINE_PIVOT_DIAGNOSTICS** для Karelia и Prokhorovka, по четыре
сценария на карту: receipts `local/evidence/20261008-p05a-pivot-diagnostics-06/`
и `local/evidence/20261008-p05a-pivot-diagnostics-07-prohorovka/`.
Engine RPM, скорости гусениц, gear/clutch и delivered torque остаются
`UNKNOWN`; native movement, reconciliation и owner pivot acceptance остаются
`NOT_RUN`.

# P06A docs-only ballistics boundary — 2026-10-08

Карточка `P06A_BALLISTICS_CONTRACT` слита в `main` merge `4535480` и фиксирует
только контракт для первого MS-1 AP shell `2570`. Порядок доменных стадий
разделён явно: admission → server launch → trajectory → surface intersection
→ material/normal → terminal result → damage. Shot identity должен быть
server-owned и идемпотентным: повтор не списывает второй AP и не создаёт второй
снаряд/урон.

Статически закреплены только уже принятые значения #717/P03H (raw speed 442,
effective 353.6 м/с, gravity 6.2784 м/с², range 720 м). Пробитие, броневые
поверхности, урон, модули/экипаж, RNG и native hit/damage остаются
`UNKNOWN/NOT_RUN`; P03H tracer не считается попаданием. План и evidence index:
`docs/plans/P06A_BALLISTICS_CONTRACT.md` и `docs/evidence-index/P06A.md`.

# P06B read-only MS-1 AP source research — 2026-10-08

Карточка `P06B_MS1_AP_SOURCE_SPIKE` выполнена в ветке
`codex/p06b-ms1-ap-research` (исследовательский commit `8bd8dab`) и слита в
`main` обычным merge `4143803`. Это docs/evidence-only исследование локальных
оригинальных ресурсов WoT `v.0.9.1 #717` RU; клиент, сервер, deployed gateway,
runtime и resource files не запускались и не изменялись.

Статические поля MS-1 AP закрыты как **PASS_STATIC_SOURCE_FIELDS**: shell
`_37mm_UBRT1`/compact `2570`, `damage/armor=30`, `damage/devices=50`, literal
`piercingPower="34 27"`, speed `442`, gravity `9.81`, range `720`, common
projectile factor `0.8`, активные armor descriptors и Hull/Turret_01/Gun_02
collision payload hashes/material groups. Машиночитаемая квитанция
`local/evidence/20261008-p06b-ms1-ap-research-01/summary.json` повторно
проверена как **PASS_STATIC_RECEIPT_RECHECK**; полный отчёт —
`docs/research/P06B_MS1_AP_SOURCE_SPIKE.md`.

Смысл пары `34 27`, единицы и формула пробития, BSP2/transform runtime,
server-owned intersection, penetration, HP/module/crew damage, native callback
и duplicate-shot idempotency остаются **UNKNOWN / NOT_RUN**. Трассер и наличие
collision payload не считаются попаданием. Единственный следующий gate —
контролируемый локальный capture двух MS-1 на фиксированной позе: один выстрел
по известной `armor_1` и один по `armor_8`, с server segment/intersection,
triangle/material/normal/thickness/terminal reason, HP/module state и проверкой
повторной доставки shot identity. Если server-owned hit/HP event не получен,
оставить solver недоступным и статус **NOT_RUN**.

# P06D bounded impact-receipt audit — 2026-10-08

Карточка `P06D_IMPACT_RECEIPT_AUDIT` выполнена в ветке
`codex/p06d-impact-receipt-audit`, commit `2d1465c`, от базы `83bba99`. В
`main` её код уже вошёл merge `10ab3ae`; эта status/docs-карточка оставляет
отдельную проверяемую запись. Добавлены только bounded
`tools/impact_capture_audit.py` и его unit tests: валидатор проверяет
server-owned admission → launch → segment → intersection → classification →
terminal → optional damage → replay, ограничения JSON, finite vectors,
monotonic sequence/ticks и fail-closed negative controls.

Targeted `tests.test_impact_capture_audit`: **11 tests, 0 failures**. Полный
main regression через UTF-8 launcher: **2083 tests, 0 failures/errors, 4
skips**, лог SHA-256
`86cdbbff98bc655b4478f1666125963ed8430f8942d549183664db178eb3a471`.
Преднамеренно неполный CLI receipt честно вернул
**NOT_RUN_INCOMPLETE_CAPTURE** (`missing required stage: launch`); это не
ошибка и не доказательство native capture.

Полный receipt, прошедший форму, получает только
**PASS_CAPTURE_SHAPE_ONLY**: fixture синтетический, результат не доказывает
native hit, penetration, историческую формулу урона или callback клиента.
`native_impact_status` остаётся `NOT_VERIFIED_BY_AUDITOR`, а native
intersection, armor/penetration, HP/module/crew damage и solver —
**NOT_RUN / UNKNOWN**. Evidence: `docs/research/P06D_IMPACT_RECEIPT_AUDIT.md`,
`docs/evidence-index/P06D.md` и ignored
`local/evidence/20261008-p06d-impact-receipt-audit-01/`.

Единственный следующий шаг — owner-gated P06C: прогнать два локальных MS-1,
передать в аудитор реальный server-owned receipt с intersection/material/
normal/thickness/terminal, HP/module state и replay identity, затем отдельно
сверить native evidence. До этого P06 hit/damage остаётся недоступен.

# P06E #717 client collision source boundary — 2026-10-08

Карточка `P06E_CLIENT_COLLISION_SOURCE_RESEARCH` выполнена в ветке
`codex/p06e-client-collision-research`, commit `ed193d8`, и вошла в `main`
merge `37c2a0e`. Это read-only аудит локального #717 bytecode: клиент,
сервер, gateway и physics runtime не запускались, а authoritative hit/damage
solver не реализовывался.

Статическая граница закрыта как **PASS_STATIC_CLIENT_COLLISION_BOUNDARY**.
Bytecode receipt имеет SHA-256
`502581a94b4be46d4db885e5922038287b38ff155138cc37ebc24e2216ce7625`, а новый
summary receipt —
`61ddf923d1b276176fe8b346590228cd00ab51acefc5f1bce94eb968ec364839`.
Summary path: `local/evidence/20261008-p06e-client-collision-research-01/summary.json`.
`_readShell` читает `damage/armor` и `damage/devices` и наблюдает loader
defaults `damageRandomization=.25` и `piercingPowerRandomization=.25`; эти
defaults не являются доказательством server RNG.

`_readShot` читает `piercingPower` через `Vector2`, speed/gravity/max distance
через bounded readers и умножает speed на `projectileSpeedFactor`.
`VehicleDescr.getHitTesters` собирает chassis/hull/turret/gun hit testers;
dynamic `collideSegment(start,end,skipGun)` и static
`BigWorld.wg_collideSegment(...)` сравнивают nearest candidate. Клиентская
уведомлялка вызывает только
`onProjectileHit(hitPosition, caliber, isOwnShot)` — без server-owned target,
armor layer, penetration, HP/module delta или shot ledger token.

Authoritative server hit, penetration/damage, BSP2/transform equivalence,
module/crew effects и native server callback остаются **NOT_RUN / UNKNOWN**.
Клиентский nearest collision и callback, как и tracer stop, не закрывают P06D
receipt или игровой impact gate. Отчёт и evidence index:
`docs/research/P06E_CLIENT_COLLISION_SOURCE_RESEARCH.md` и
`docs/evidence-index/P06E.md`.

Единственный следующий шаг — owner-gated P06C: провести controlled capture двух
MS-1, получить server-owned intersection/material/normal/thickness/terminal,
HP/module state и replay identity, затем сопоставить native evidence. До этой
корреляции P06 hit/damage остаётся недоступен.

# P03I docs-only native vehicle/loadout boundary — 2026-10-08

Документы P03I из commit `81dfb93` слиты в `main` merge `2f43054`; статусная
запись подготовлена отдельно в ветке `codex/p03i-status-docs`. Карточка имеет
статус **PASS_DOCS_ONLY_STATIC_BOUNDARY / NATIVE_HANDOFF_NOT_RUN**. Она не
добавляет runtime профиля, не меняет `server/gateway`, `client_patch`, fixture,
оригинальный/research client или deployed service.

Зафиксирован статический tree predicate: `NationTreeData.load` пропускает
`None` и `item.isHidden`, а hidden set приходит из
`shop.items.notInShopItems`; полный reference graph не урезается. Направление
графа — **ИС-8 → ИС-7**. Native account/shop payload, callbacks окна
исследования и owner screenshot correlation остаются **NOT_RUN**.

Зафиксирован статический random-queue контракт: request `202`, command `700`,
выбранный `g_currentVehicle.invID` как `INT64`, затем `gameplaysMask` и
`arenaTypeID` как два `INT32`; envelope `INT16, INT16, INT64, INT32, INT32`.
Callbacks: `onEnqueued(queueType)` → `events.onEnqueuedRandom()` и
`onEnqueueFailure(UINT8, UINT8, STRING)` →
`events.onEnqueueRandomFailure(...)`. Это source semantics, не live framing.

Следующий owner gate — один обычный random-battle click на MS-1 с сохранением
decrypted Account body, manifest, `202/700`, обоих `INT16`, `INT64` vehicle ID,
обоих `INT32` mask/arena, callback arguments/order, queue event и server
identity correlation. IS-7 можно проверять только после отдельного
hash-pinned crew и server-owned shell grant; текущие `crew_assigned=false`,
ammo `0` должны fail-closed без mutation. Missing framing/callback оставляет
результат **NOT_RUN**; CMD700 нельзя угадывать по map-drive parser.

План, research ledger и evidence index: `docs/plans/P03I_VEHICLE_PROFILE_LOADOUT.md`,
`docs/research/P03I_VEHICLE_PROFILE_LOADOUT.md`,
`docs/evidence-index/P03I.md`.

## P03I bounded native MS-1 queue smoke — 2026-10-08

После ручного запуска настоящего research-клиента выполнен один клик обычной
кнопки «В бой!» на MS-1, затем клиент закрыт владельцем. Свежая overlay-копия
восстановлена **PASS**, native EXE завершился с code `0`, CAPTCHA guard не
заблокировал вызовы, capture сохранил 386 пакетов. Receipt:
`local/evidence/20261008-p03i-native-ms1-queue-01/native-gate-audit.json`.

Это **PASS_NATIVE_MAP_DRIVE_QUEUE_SMOKE / PASS_SERVER_SIDE_BATTLE_ENTRY**:
gateway span фиксирует request `202`, command `700`, выбранный native
inventory `1`, `accepted=true`; далее видны `01_karelia`, worker ready,
avatar/vehicle creation, bind и первый input. Runtime trace видит
`selected_inventory_id=1`, `BattleQueue`, `PlayerAvatar.onEnterWorld`,
`onSpaceLoaded` и `userSeesWorld`.

Строгая native-приёмка P03I остаётся **NOT_RUN**: этот прогон идёт через
совместимый map-drive маршрут и не даёт независимого декодирования live
Account body (оба `INT16`, `INT64` машины, оба `INT32` gameplay/arena) и
аргументов native `onEnqueued(queueType)`. Нельзя выдавать hard-coded
`map_request=0` из map-drive лога за доказательство всех полей исходного
CMD700. IS-7, экипаж, снаряды, оборудование и owner screenshot остаются
**NOT_RUN**.

План этой follow-up карточки: [P03I native MS-1 queue](plans/P03I_NATIVE_MS1_QUEUE.md).

# Параллельная карточка — P04, 2026-10-07: typed content import

В отдельной рабочей копии `codex/p04-content-import` реализован bounded
валидатор `content-import.v1`. Он связывает typed records техники, модулей,
снарядов, карт, материалов и брони с hash-verified `server-content.v1`,
проверяет cross-kind references, bounds/transforms/spawns, armor triangles и
явный `missing` report. Повторная нормализация выдаёт canonical SHA256.

Targeted Python: **33 tests, 0 failures/errors, 1 known skip** (10 importer
hardening tests плюс существующие bundle/map checks). Evidence:
`local/evidence/20261007-p04-content-import-02/result.json` и
`local/evidence/20261007-p04-content-import-02/unittest-targeted.txt`. Отчёт
импортера явно разделяет `data_complete` и runtime eligibility:
`runtime_ready=false`, `runtime_eligibility=NOT_RUN`; пустой `missing` больше не
выдаётся за готовность серверной физики. Полный suite в этой рабочей копии
намеренно не засчитывается: ignored `config/project.local`
и native evidence остаются только в основном checkout, поэтому его результат
`NOT_RUN_FOR_P04_WORKTREE` (28 missing-evidence errors и 1 frozen-source
failure) не относится к importer. Реальный полный #717 content dataset,
native geometry checkpoints, native compatibility/physics и selection-to-battle
handoff остаются `NOT_RUN`.
Карточка принята и слита в `main` обычным `--no-ff` commit
`6d4d32e`; remote `main` подтверждён тем же SHA. Она не меняет
оригинальный/research client.
После merge основной checkout прогнал полный Python suite: **2060 tests,
0 failures/errors, 4 known skips**; это регрессия репозитория, а не доказательство
native content compatibility или готовности physics.
Изолированный gateway build после merge: **373 Rust tests PASS**, executable
SHA `f9beb996733f9dcdd8be70f214bfe2abe1cad242000ab0b3a542c3fd59b729ad`,
deployed SHA не изменился; source layout **58 files / 22 relocations PASS**,
receipt `local/evidence/20261007-p04-postmerge-layout-01.json`.
Legacy gateway build также PASS: **371 Rust tests**, executable SHA
`5325153dfedaededf35fcdbce4cfc55945ab8b267fb6c1e6dfbbf13a193dd50c`; оба
билда изолированы и не заменяют deployed gateway.

08.10 выполнен отдельный recheck self-contained P04 receipt в текущем checkout:
CLI `tools/content_import.py` вернул `PASS_TYPED_IMPORT_VALIDATOR` с тем же
canonical SHA `a1b1191b29bbae5e2aed2f4417a139c7e9a2e6740ec40698347ad6baa8aac2b9`,
а bundle/import/map targeted suite дала **38 tests, 0 failures/errors, 0
skips**. Receipt `result.json` закреплён локальным SHA
`80a34c538ee66c6a60f03b27d5b823dc85ddb7338ab630b897e28af7c159042f`.
Это локальная ignored evidence, восстановленная для воспроизводимой проверки;
`runtime_ready=false`, `runtime_eligibility=NOT_RUN` и native compatibility
остаются **NOT_RUN**.

После этого recheck усилен нижний `server-content.v1` boundary: bundle manifest
и JSON content reader теперь fail-closed на duplicate keys, `NaN/Infinity`,
overflow depth/items, boolean-as-integer и malformed SHA-256. Новые negative
tests входят в `tests.test_content_bundle`; свежий bundle/import/map targeted
suite дала **42 tests, 0 failures/errors, 0 skips**. Receipt
`local/evidence/20261008-p04-bundle-hardening-01/recheck.json`, SHA-256
`8d07c77de1a01c39c92e9153f4c3e7f4c08fabf6c4c632a1cbdc20db571e9685`; canonical
import SHA остался `a1b1191b29bbae5e2aed2f4417a139c7e9a2e6740ec40698347ad6baa8aac2b9`.
Это всё ещё typed resource contract: `runtime_ready=false`,
`runtime_eligibility=NOT_RUN`, native compatibility и physics **NOT_RUN**.

Отдельный аудит существующего web research-графа записан в
[P04 research](research/P04_CONTENT_IMPORT.md): в нём уже есть уровни I–X СССР
и переход ИС-8 → ИС-7. Это не означает, что нативное окно клиента умеет этот
граф получать; native/UI handoff остаётся отдельной задачей.

Дополнительно добавлен bounded static graph audit P09A:
`tools/research_tree_audit.py` и `tests/test_research_tree_audit.py` дают
**8/8 PASS**, receipt `local/evidence/20261008-p09a-tree-graph-audit-02-receipt.json`
с SHA `454c9b0c9e0666e92856239dd55c486014695317052eff766f50b772239ef8d8`.
Он подтверждает только hash-bound reference graph (374 деревьев, 3945 узлов,
2062 ребра, USSR I–X, MS-1 level-I → tier-II, ИС-8 → ИС-7, ИС-7 terminal); native account/shop/tree
payload, callback и визуальная сверка остаются **NOT_RUN**.

Для P09A predicate receipt повторно проверены четыре hash-bound исходника
research-копии: все SHA совпали; receipt SHA
`65704882b8361534f68e0965b3e8e4188fb60f87f3f9b48f40a2d403e42956a0`.
Это static provenance recheck, не native callback или account/shop capture.

Для P03I повторно проверен ignored capture-tool audit: `audit.json` SHA
`9e945a9ca0750a83e6b26dfa83dfd6ee726f5c24063637b6166e3206e0d89b27`, семь
зафиксированных исходных SHA совпали, существующие capture/decrypt/channel
helpers прошли `py_compile`. Решение остаётся
`PASS_READ_ONLY_CAPTURE_FORMAT_AUDIT`; live CMD700/callback и IS-7 admission
по-прежнему **NOT_RUN**, поэтому спекулятивный decoder/gateway adapter не
добавлялся.

План: [P04 plan](plans/P04_CONTENT_IMPORT.md); исследование:
[P04 research](research/P04_CONTENT_IMPORT.md); evidence:
[P04 index](evidence-index/P04.md).

# Актуальный указатель — P03H, 2026-10-07: серверный полёт снаряда

Канонический gate: [ACTIVE_GATE](ACTIVE_GATE.md). **P03 IN_PROGRESS**.
Карточка `codex/p03h-native-projectile-flight`:
**PASS_OWNER_P03H_SAME_PC_SERVER_PROJECTILE_NATIVE_TRACER / ACCEPTED**.
Владелец подтвердил: «визуально вроде все окей, оба клиента видят».

Принятый scope — bounded same-PC MS-1 test_lab: сервер создаёт снаряд,
вычисляет старт/скорость и завершение по 720 м, а оба настоящих клиента
получают родные `Avatar.showTracer`/`Avatar.stopTracer` и запускают свой
`ProjectileMover`. Независимый аудит зафиксировал 28 410 пакетов / 28 402
channel frames, 38 start и 38 stop на двух peer-слотах, ноль ошибок. Пассивный
native-аудитор увидел по 19 start/stop/add/hide lifecycle на каждом клиенте.

Финальные проверки: canonical **373 Rust PASS**, legacy **371 Rust PASS**;
Python **2055 tests, 0 failures/errors, 2 известных skip**, targeted observer **4 PASS**.
Evidence receipt: `local/evidence/20261007-p03h-native-projectile-flight-01/owner-acceptance.json`;
подробности: [P03H receipt](evidence-index/P03H.md) и
[P03H research](research/P03H_NATIVE_PROJECTILE_FLIGHT.md).

Ограничения этой карточки: активен только профиль МС-1; IS-7, экипаж,
оборудование, гаражный loadout, экономика, броня, попадания, урон, terrain
collision, dispersion RNG и two-PC/LAN остаются NOT_RUN. Единственный следующий
шаг — отдельная карточка `VehicleProfile/Loadout`, чтобы выбирать IS-7 и его
исторические характеристики поверх уже принятого общего транспорта/полёта.

## Предыдущий указатель — P03G, 2026-10-07: серверное наведение

Канонический gate: [ACTIVE_GATE](ACTIVE_GATE.md). **P03 IN_PROGRESS**.
Карточка `codex/p03g-shared-gun-aim`:
**PASS_OWNER_P03G_SAME_PC_DYNAMIC_AIM_AND_SHOT_REGRESSION / ACCEPTED**.
Владелец после инструкции подтвердил: «вроде все по этим тестам корректно».
Код проверенной сборки: `bbf4eac375676ffd8cf2dc60ebdf804653fd2b20`.
Финальный commit/merge/push и remote SHA записываются после операций в
`local/evidence/20261007-p03g-shared-gun-aim-01/accepted-handoff.json`.

Сервер принимает родные цели наведения, сам ограничивает скорость башни/ствола,
передаёт текущие углы обоим клиентам и сохраняет их при rejoin. Добавлен штатный
`Avatar.updateTargetingInfo`, без которого клиентский gun rotator не стартовал.
Оригинальные native обработчики на обеих копиях реально получили обновления.
Номинальные ограничения stock МС-1 взяты из #717; восемь контрольных направлений
и 15 rear-limit samples сверены с родной математикой клиента. Историческая
точность всей модели остаётся approximate/test_lab, попадания не реализованы.

Финальные сборки: canonical aim-02 **363 Rust PASS**, legacy aim-01 **361 PASS**.
Python **2054 tests, 0 errors/failures, 2 skips**; layout **57/22 PASS**;
клиентские overlays скомпилированы закреплённым Python 2.7.3. Первый Python
прогон выявил 13 ошибок из-за порядка проверки нового диагностического guard;
он исправлен, исходный отрицательный лог сохранён.

Owner-прогон: **28 492 packets / 28 484 frames, 9137 pose+angle publications,
12 shot cues, 0 ошибок**. По 457 native snapshots; 9126/9118 завершённых родных
обработчиков углов точно совпали с префиксом wire-публикаций. A сделал пять
выстрелов (AP20→15), B один (AP20→19); все шесть видны обоим native обработчикам.
Повторная стрельба проверена на A; по два выстрела с каждого клиента не записаны.
Owner receipt: `local/evidence/20261007-p03g-shared-gun-aim-01/owner-acceptance.json`.

Файлы, команды, native evidence и откат: [P03G receipt](evidence-index/P03G.md).
Оригинальная/research-копии и deployed gateway неизменны. Единственный следующий
шаг — отдельная карточка серверного полёта снаряда и native-трассера в обоих окнах.
Two-PC/LAN и полная физика остаются NOT_RUN.

## Предыдущий указатель — принятая P03F

Канонический gate: [ACTIVE_GATE](ACTIVE_GATE.md). **P03 IN_PROGRESS**;
Карточка `codex/p03f-two-client-world` **PASS_OWNER_P03F_SAME_PC_WORLD_SHOT_SOUND_NEUTRAL_POSE**.
Commit/merge/публикация фиксируются после операций в `aim-01/handoff.json`.
Владелец подтвердил синхронное движение и видимый чужой выстрел на build07.
Свежий бой `12600843064120895129`: 14 принятых выстрелов, 28 native callbacks,
по 14 завершений родного `Vehicle.showShooting` на каждом клиенте; порядок
entity ID совпал с независимым wire-аудитом. Позже на build08 владелец также
подтвердил: «Башня и ствол нормально, звук есть».
Префикс capture: 5743 packets / 5731 frames, 28 cues, ноль ошибок.

Финальные проверки: canonical build08 **353 Rust PASS**, legacy04 **351 PASS**,
Python **2053 tests, 0 errors/failures, 2 skips**, layout **56/22**.
Файлы, команды, доказательства и откат: [P03F receipt](evidence-index/P03F_GUN_POSE.md),
`local/evidence/20261007-p03f-two-client-world-01/aim-01/owner-acceptance.json`.

Исправлена причина башни на 180° и поднятого ствола: `gunAnglesPacked=0`
декодировался как `(-pi, minimum pitch)`. Нейтральный seed `0x8030` реально
получен обоими native клиентами; родной decoder даёт `0° / +0,142857°`.
Свежий префикс: 3669 packets / 3661 frames, 4 создания машин, 6 shot cues,
ноль ошибок. Native proof и owner-скрины подтверждают исправление.
Динамическая синхронизация наведения остаётся неподдержанной; это не приёмка
попаданий, урона или физики. Исходная/research-копии и deployed gateway неизменны.

Единственный следующий рекомендуемый шаг — отдельная карточка серверного
наведения башни/орудия с передачей текущих углов. Two-PC/LAN остаётся NOT_RUN.

## Предыдущий указатель — первоначальный handoff build05 (история)

Канонический gate: [ACTIVE_GATE](ACTIVE_GATE.md). **Полный P03 IN_PROGRESS**.
Текущая карточка: **PASS_NATIVE_SAME_PC_DATA_PLANE_OWNER_CONTROL_PENDING**;
ветка `codex/p03f-two-client-world`, **NOT_ACCEPTED**, без merge/push в `main`.
Обязательная оценка управления владельцем ещё нужна.

Две независимые копии #717 на этом ПК реально вошли в один серверный бой
`2448793866150762938`. Native traces и PNG показывают обе машины, разные
own/ally ID и четыре общие изменившиеся X/Z-позиции второго танка. У каждого
свой БК: A `20→18`, B `20→17`, пять завершений перезарядки подтверждены wire.
После принудительного закрытия только A второй клиент продолжил бой; A
переподключился новым session ID к прежней машине с **18 AP**.

Canonical build05: **346 Rust PASS**; legacy build02: **344 PASS**;
финальный Python: **2052 tests, 0 errors/failures, 2 skips**; layout **56/22 PASS**.
Независимый разбор сохранённого префикса native capture: **20 620 packets,
20 608 frames, 3 logins, 6548 pose publications, 0 errors**. Ошибка первого
прогона stop-before-ACK сохранена и исправлена regression-тестом. Исходный
клиент, прежняя research-копия и deployed gateway сохранили закреплённые SHA.

Границы: loopback, два временных союзных МС-1, плоская зона 4×4 м на машину;
танки не следуют рельефу, на PNG также видна цветная сетка неизвестного
происхождения. Физика/рендер не приняты. Warm Leave-to-hangar недоступен;
проверено полное закрытие процесса и повторная авторизация. Two-PC, projectile,
hit/damage, turret aim, visibility, equipment и persistence не приняты.

Файлы, команды, доказательства, ограничения и откат:
[P03F receipt](evidence-index/P03F.md), [research](research/P03F_TWO_CLIENT_WORLD.md),
`local/evidence/20261007-p03f-two-client-world-01/result.json`.
Единственный следующий шаг — короткая owner-проверка: перемещение/поворот A
видны из окна B. Два клиента и изолированный gateway оставлены запущенными
на момент handoff; актуальные PID/пути — в local `handoff.json`.

## Предыдущий указатель — ORG-0B (история до P03F)

Канонический gate: [ACTIVE_GATE](ACTIVE_GATE.md). **Полный P03 IN_PROGRESS**.
P03D `PASS_OWNER_NATIVE_AMMO_PANEL_HUD` и P03E
`PASS_OWNER_NATIVE_FIRE_RELOAD_CONSUMPTION` подтверждены owner receipts.
Повтор ручного P03E в ORG-0B не требуется. Два клиента в общей арене,
projectile/hit/damage и полная боевая приёмка остаются NOT_RUN.

**ORG-0B: PASS_TEST_REPAIR.** Свежий baseline повторил 2028 tests, 10 errors,
4 skips. После минимальных исправлений — **2047 tests, 0 errors/failures,
2 skips**; отдельный Python 2.7 bytecode check — **1 PASS**. Единственная
проверка из исходных четырёх, не выполненная ни в одном режиме, — Windows
symlink refusal: текущая учётная запись не может создать symlink. Layout PASS
(52 source files / 22 relocations), четыре запуска profile4 CLI/module PASS.
Причины, границы и команды: [ORG-0B receipt](evidence-index/ORG-0B.md).

Исправлены test fixtures и режим импорта offline profile4 verifiers. Протокол,
боёвка, frozen verifiers, клиент и deployed gateway неизменны. Historical tests
проверяют архивные source bytes с прежними строгими SHA; новая live/native
совместимость этих legacy CLI не запускалась и не заявляется.

ORG-0A опубликована: [baseline/remote receipt](evidence-index/ORG-0A.md).
ORG-0B base — `1aa052db33643fab510f2b9185716a8e60d8804a`; точные принятый
head, merge/push и remote SHA записываются после операций в local machine receipt,
указанном в индексе. Следующий один шаг — отдельная P03-карточка двух native
клиентов в общем авторитетном мире. Общая стабильность/release не заявляется.

## История карточек (старые NOT_RUN и рекомендации сохранены)

Все результаты ниже относятся к своему запуску и дате. Старое P03 NOT_STARTED
в архивной таблице не заменяет актуальный IN_PROGRESS выше.

**2026-10-07: P03E owner acceptance — PASS_OWNER_NATIVE_FIRE_RELOAD_CONSUMPTION.**

На build09 владелец сделал пять выстрелов на одном MS-1 entry; все прошли
нормально. Gateway записал server-owned AP `20 → 19 → 18 → 17 → 16 → 15`
и пять `BATTLE_RELOAD_COMPLETE` callbacks с
`updateVehicleGunReloadTime(0x46, timeLeft=0.0, baseTime=2.5)`. Второй и
последующие выстрелы реально дошли до `vehicle_shoot=0x88`, значит клиентская
reload latch после initial `0,00` и после каждого shot отпускается.

Свежий capture: `671` packet files, `667` bounded channel frames, crypto и
transport parse PASS, ошибок нет; initial map binding — `176` байт с panel,
`CURRENT_SHELLS` и initial reload callback, пять shot callbacks — по `25`
байт. Gateway и клиент остановлены после owner run; deployed gateway SHA256
`daef0dde9e012beac4e0f363bf66b672ec4a154473be4b05b00cfe4cc0608c3b`,
supervisor/identity/live gateway не заменялись.

Canonical build09: **330 Rust tests PASS**, EXE SHA256
`460d5d68dd47b6599085d2775c316d4e1192a2d53c45f87aaabf86d9341e7970`;
shared legacy build04: **329 PASS**, SHA256
`558a6b72a65e980395e146a48570e1ef1cec2b7accfcbe2c1cdb2a8e832e114a`;
source layout после completion callback: **PASS** (`52` файлов, `22`
relocations). Receipt owner-приёмки:
`local/evidence/20261007-battle-fire-reload-01/owner-test/owner-acceptance-fire-reload-03.json`.

P03E закрыта для fire/reload/consumption. Projectile, hit, damage, visibility,
physics, equipment и persistence остаются **NOT_RUN**; единственный следующий
шаг — отдельная карточка projectile/hit/damage, без расширения этой фазы.

**2026-10-07: P03E reload-latch correction — PASS_ISOLATED_NATIVE_FIRE_ROUTE_READY_RELOAD_RESET.**

Первый owner-прогон на build07 дал полезный отрицательный результат: HUD уже
показывал панель, но при огне клиент писал «орудие перезаряжается», таймер
оставался `0,00`, AP не менялся, а capture не содержал ни клиентского `0x88`
`vehicle_shoot`, ни `BATTLE_SHOT_ACCEPTED`. Bounded transport/crypto аудит
этого прогона PASS; тело initial binding было `162` байта и заканчивалось
только panel rows + `CURRENT_SHELLS`. Причина подтверждена static Avatar
кодом: `PlayerAvatar.updateVehicleGunReloadTime` не был вызван, поэтому
`aim.isGunReload()` оставался поднят и `PlayerAvatar.shoot` не доходил до
native вызова.

Исправление добавляет перед ручным огнём штатный
`updateVehicleGunReloadTime` (`0x46`) с vehicle entity `152043523`,
`timeLeft=0.0`, `baseTime=2.5`. PREBATTLE body теперь `105` байт, map-drive
binding — `176` байт; callback идёт после трёх ammo rows и
`CURRENT_SHELLS=0/2570`. Это не объявляет fire acceptance: новый owner шаг
ещё нужен.

Canonical isolated gateway build08: **329 Rust tests PASS**, EXE SHA256
`b70c73af9cc0060343e51202bf959326d0a584ce37b20a29ad3b4fe253085727`;
shared legacy build03: **328 PASS**, SHA256
`034277a63a55340f21e6604081dfef51d35258e1431307648b992663f5b4fafd`;
source layout after correction: **PASS** (`52` files, `22` relocations).
Deployed `p01-wg-probe.exe` остался на SHA256
`daef0dde9e012beac4e0f363bf66b672ec4a154473be4b05b00cfe4cc0608c3b`;
supervisor, identity и live gateway не перезапускались.

Первый ручной прогон сохранён как
`local/evidence/20261007-battle-fire-reload-01/owner-test/owner-attempt-01-observation.json`;
свежий handoff build08 будет отдельным capture и не перезапишет этот
отрицательный результат. Приёмка P03E всё ещё **NOT_RUN** для фактического
выстрела; единственный следующий шаг — один MS-1 выстрел на build08,
проверить AP `20 → 19` и пройти reload.

Полный receipt: `local/evidence/20261007-battle-fire-reload-01/result.json`;
static-method receipt: `local/evidence/20261007-battle-fire-reload-01/static-method-receipt.json`.

**2026-10-07: P03E isolated native fire/reload route — PASS_ISOLATED_NATIVE_FIRE_ROUTE_READY.**

Добавлен bounded server-owned маршрут MS-1 для `Avatar.BaseMethods.vehicle_shoot`
(`0x88`) и явный диагностический `vehicle_replenishAmmo` (`0x89`). Сервер
держит AP `20`, принимает только авторизованный zero-arg shot, списывает один
AP и ставит монотонную перезарядку `2.5 s`; callback-ы —
`updateVehicleAmmo` (`0x44`, remaining `19`) и
`updateVehicleGunReloadTime` (`0x46`, `2.5/2.5`). `0x89` пока
`domain_applied=false`: бесплатный боекомплект/экономика не добавлены.

Статически подтверждена причина клиентского silent-stop:
`PlayerAvatar.shoot` требует `__currShellsIdx`; поэтому перед тремя ammo rows
добавлен штатный `updateVehicleSetting(CURRENT_SHELLS=0, 2570)` (`0x40`).
PREBATTLE body теперь `91` байт, map-drive binding `162` байта. Ветвление
применено и к живому `drive.is_some()` маршруту, и к legacy arena route.

Canonical isolated gateway: **328 Rust tests PASS**, EXE SHA256
`72dfc02beef4b3af645a98914634463d84a21abb6274a897eac6ba5d47e32ff`; shared
legacy entrypoint: **327 PASS**, SHA256
`e1c05aed270e79d4a8ff25510619e0abd288f5e1718bf4fda68da189cbe9d127`; source
layout: **PASS** (`52` files, `22` relocations). Deployed
`p01-wg-probe.exe` остался на SHA256
`daef0dde9e012beac4e0f363bf66b672ec4a154473be4b05b00cfe4cc0608c3b`;
supervisor, identity и live gateway не перезапускались.

Owner manual fire/reload пока **NOT_RUN**. Свежий handoff подготовлен в
`local/evidence/20261007-battle-fire-reload-01/owner-test/`; capture пустой
до ручного выстрела. Приёмка этой фазы требует одного MS-1 выстрела, ожидания
примерно `4 s` и проверки HUD/capture на AP `20 → 19` и reload.
Полный receipt: `local/evidence/20261007-battle-fire-reload-01/result.json`;
static-method receipt: `local/evidence/20261007-battle-fire-reload-01/static-method-receipt.json`.

# Статус проекта

**2026-10-07: P03D owner acceptance — PASS_OWNER_NATIVE_AMMO_PANEL_HUD.**
Fresh research-client MS-1 entry on the isolated panel gateway visibly showed
three battle ammo slots: AP `2570:20`, HOLLOW_CHARGE `2826:0`,
HIGH_EXPLOSIVE `3082:0`. This is an owner screenshot observation, not a
synthetic HUD claim. The copied screenshot is hashed in
`local/evidence/20261007-battle-ammo-panel-01/owner-test/owner-panel-acceptance-01.json`.

The frozen owner capture has 621 packet files, packet integrity PASS and no
bounded transport parse errors. Packet 73 is a server→client body of 155 bytes;
its suffix at offset 122 is exactly the three 11-byte methods, with
`0x13 0x44` prefixes at offsets `122/133/144`. Equipment/consumables remain
absent (`null`) in the verified MS-1 input, so no equipment item is claimed.
The isolated panel gateway PID 83200 was stopped after the run; deployed
`p01-wg-probe.exe`, supervisor and identity were not replaced.

Receipts: `local/evidence/20261007-battle-ammo-panel-01/result.json`,
`local/evidence/20261007-battle-ammo-panel-01/owner-test/owner-panel-acceptance-01.json`,
`local/evidence/20261007-battle-ammo-panel-01/owner-test/owner-capture-audit-panel-01-frozen.json`.
Ammo-panel HUD acceptance is complete. Zero-count shell selection and
fire/reload/consumption remain **NOT_RUN**; equipment needs a later verified
item-bearing profile/message. The single next step is a separate firing/reload
card, without widening this panel card into guessed combat semantics.

**2026-10-07: P03D battle ammo panel route — PASS_OFFLINE_BATTLE_AMMO_PANEL_ROUTE.**
После owner-проверки build07 клиент показывал только выбранный AP `2570:20`.
Причина подтверждена текущим payload: сервер отправлял один `Avatar.updateVehicleAmmo`.
Новый изолированный route сохраняет binding prefix и добавляет три bounded
entity-method строки в доказанном native order: `2570:20`, `2826:0`, `3082:0`.
Размер suffix —33 байта; ordinary map-drive binding теперь155 байт вместо133,
PREBATTLE preparation —84 вместо62. `equipment` и `consumables` в закреплённом
MS-1 input отсутствуют (`null`), поэтому фальшивые предметы не отправляются.

Canonical gateway: **319 Rust tests PASS**, SHA256
`4247C1E9A575570E6252E3CCBFD503FA0B50D8D926F04AC8F3ACAEDF2630A0A`; legacy
shared entrypoint: **318 PASS**, SHA256
`4E222DDEE890938E2AF2FC47ADE4FAB976F6247EBC5F42100BA99713FB4D4C03`.
Source layout PASS; isolated bind-smoke на `20134/20136` PASS; deployed
`p01-wg-probe.exe`, live supervisor, сайт, БД и оба клиента не заменялись.
Receipts: `local/evidence/20261007-battle-ammo-panel-01/result.json` и
`local/build/server/gateway-battle-ammo-panel-01/result.json`.

На момент этой offline-записи native HUD ещё был **NOT_RUN**; owner-приёмка
закрыта следующей записью выше. Эта запись сохраняет исходные offline
размеры/хэши и не объявляет оборудование, zero-count selection или fire/reload.

**2026-10-06: P03 owner wire review + build07 route correction — PASS_OFFLINE_OWNER_ROUTE_FIX.**
Первый owner-прогон на build06 теперь зафиксирован как
**VERIFIED_OWNER_CAPTURE_ROUTE_MISS**: capture содержит валидный
`READY_COMPOUND` (packet 74), а следующий server→client binding имеет ровно
122 байта (packet 76). Bounded-аудит 658 packet files / 654 encrypted channel
frames проходит без ошибок, но `0x13 0x44` и exact candidate отсутствуют.
Клиентский trace подтверждает MS-1, `BattleLoading`/`onSpaceLoaded` и чистый
выход; ammo callbacks в trace — только hangar-side до battle, а владелец увидел
«БК нет». Это не доказательство native HUD rejection: старый live route просто
не отправлял кандидат. Receipts:
`owner-test/owner-capture-audit-060.json`,
`owner-test/owner-wire-frame-summary-060.json`,
`owner-test/owner-trace-audit-060.json`.

Причина найдена в dispatch order: live map-drive с `self.drive.is_some()` идёт
через `drive_avatar`, раньше поздней `queue_map_binding` ветки; build06 оставлял
там старый 122-byte binding. Build07 добавляет типизированный 11-byte
`13440a0a00001400000000` в фактический `drive_avatar` route после той же
server-owned BattlePreparation и до reliable enqueue. Новый build07: **318 Rust
tests PASS**, executable SHA256
`39BE8CA6B782ED5C902C0AA93D9DFF4CF31A50910D959947687DB338E719BEC8`, source
layout PASS, isolated bind-smoke PASS на `20124/20126`; deployed gateway SHA
`DAEF0DDE9E012BEAC4E0F363BF66B672EC4A154473BE4B05B00CFE4CC0608C3B` и live
service не менялись. План исправления:
`docs/plans/P03C_OWNER_WIRE_AMMO_ROUTE_FIX.md`.

Следующий ручной шаг подготовлен в
`local/evidence/20261006-battle-shooting-native-loadout-01/owner-test-build07.md`:
остановить только старый owner gateway, запустить build07 с fresh
`owner-capture-070`, один раз войти на MS-1, проверить battle HUD и нормально
выйти; fire/move/sniper/второй клиент запрещены. Native receipt/order/HUD после
build07 пока **NOT_RUN**.

**2026-10-06: P03 battle preparation loadout route — PASS_DOMAIN_BATTLE_PREPARATION_LOADOUT.**
Перед PREBATTLE и ordinary `drive_join` canonical gateway теперь повторно
проверяет authenticated `VehicleSeed`, читает exact profile/compatibility/
manifest/native-ammo inputs по pinned SHA, строит typed
`BattlePreparation` через общий fail-closed `battle::loadout::validate` и
привязывает результат к generation арены. Count берётся из server-owned
profile, mapping — из compatibility, mounted turret5891/gun5892, shell2570 и
capacity96 — из native export; client input и HUD не используются. Cancel/return
очищают доменное состояние. Canonical isolated build: 312 Rust tests PASS;
legacy shared entrypoint: 311 PASS; `server/check_layout.py` PASS; deployed
gateway SHA `DAEF0DDE9E012BEAC4E0F363BF66B672EC4A154473BE4B05B00CFE4CC0608C3B`
не изменился. Финальный output:
`local/build/server/gateway-battle-shooting-after-05`; Evidence:
`local/evidence/20261006-battle-shooting-loadout-route/result.json`; plan/report:
`docs/plans/P03_BATTLE_SHOOTING.md`, `docs/research/P03_BATTLE_SHOOTING.md`.
Native Avatar `AMMO/LOADOUT` event, wire decode, fire/reload, расход БК,
hit/damage, physics и live restart — NOT_RUN. Read-only maintenance audit в
`local/evidence/20261006-battle-shooting-maintenance-preflight-01/` дал
`NOT_READY_NATIVE_LOADOUT`: deployed service всё ещё закреплён на старом EXE,
изолированная сборка не развёрнута, а 345-пакетный capture уже сохранил «БК
нет». Research-копия восстановлена до prior SHA после ошибочного rollback
active install016; original/backend не трогались. Повторный клиентский run сейчас
не просить. Единственный следующий шаг — offline определить native
Avatar ammo method/serializer/order; только потом планировать owner-driven окно
с capture и MS-1 → «В бой!». До реального числового БК fire/reload handler не
добавлять.

**2026-10-06: profile4 battle-loadout revision adapter — PASS_BOUND_PROFILE4_LOADOUT_ADAPTER.**
Добавлен отдельный `server/gateway/src/battle/profile4_adapter.rs` поверх
прежнего domain-only `loadout.rs`. Adapter принимает bounded trusted
`game.account.v1` assertion, exact r4 profile/compatibility/native-ammo SHA,
сверяет account/native DB/nickname/creation, revisions 4/4, MS-1 inventory,
commander+driver crew, 20 AP, mounted turret5891/gun5892, shell2570 и
vehicle-specific maxAmmo96, затем вызывает прежний typed loadout validator.
Canonical isolated gateway test/build: 307 Rust tests PASS; deployed gateway
не заменён, `main.rs` только включает compile-only module без session/transport
wiring. Native Avatar ammo event, battle admission/reservation, consumption,
reload/fire/damage/physics и live backend — NOT_RUN. Existing loadout.rs и
arena/gateway runtime behavior не переписаны. План/отчёт:
`docs/plans/BATTLE_LOADOUT_REVISION_GATE.md`,
`docs/research/BATTLE_LOADOUT_REVISION_GATE.md`; evidence:
`local/evidence/20261006-battle-loadout-revision-gate/`. Следующий один шаг:
после отдельного native capture решить, как adapter связывается с настоящим
Avatar loadout event, не добавляя fire handler по догадке.

**2026-10-06: profile4 r3→r4 semantic diff — PASS_PORTABLE_PROFILE4_SEMANTIC_DIFF.**
Добавлен bundle-rooted offline verifier `tools/profile4_semantic_diff.py`.
Принятый `portable-bundle-05` сначала проходит immutable chain, затем строго
проверяется exact delta: crew/identity/resources/IS-7/vehicle+crew mapping
сохранены, MS-1 ammunition `0→20` добавлен с shell2570/turret5891/gun5892,
`shop.bin` и `dossier.bin` byte-identical, state меняется только shells и
shellsLayout. Пять unit checks PASS, включая отрицательные identity/IS-7/state и
ammo-mapping мутации. Native compatibility, native proof, battle gate и live
backend не запускались; absolute r3/r4 preservation остаётся NOT_BUNDLED.
План и отчёт: `docs/plans/PROFILE4_SEMANTIC_DIFF.md`,
`docs/research/PROFILE4_SEMANTIC_DIFF.md`; evidence:
`local/evidence/20261006-profile4-semantic-diff/semantic-diff.json`.
Следующий один шаг: подключить этот revision/loadout assertion к отдельному
battle-loadout gate без изменения native transport и physics.

**2026-10-06: game account ownership assertion — PASS_GAME_ACCOUNT_OWNERSHIP.**
Добавлен отдельный `game.account.v1` contract и pure builder/validator
`server/identity/ownership.mjs`. Он связывает принятый
`identity.account.v1` game assertion с server-owned profile по `account_id`,
никнейму и creation timestamp, добавляет bounded native database ID,
profile/snapshot revisions и SHA256 профиля. DTO не содержит email, password,
browser session token, fixture path или loadout. Четыре новые isolated Node
проверки и прежние пять identity/account тестов PASS. Arena/gateway/physics,
battle worker, live identity DB и native client не менялись и не запускались.
Это ownership boundary для будущего loadout gate, не боевое разрешение и не
native compatibility. План и отчёт: `docs/plans/GAME_ACCOUNT_OWNERSHIP.md`,
`docs/research/GAME_ACCOUNT_OWNERSHIP.md`; receipt:
`local/evidence/20261006-game-account-ownership/result-final.json`. Следующий
один шаг: отдельный semantic diff r3→r4 crew/ammo delta, который может принять
этот assertion, без изменения battle/native source.

**2026-10-06: bundle-rooted profile4 chain — PASS_PORTABLE_PROFILE4_CHAIN.**
Добавлен отдельный provenance/data-only verifier
`tools/profile4_chain.py`. На свежем bundle проверены immutable
`profile4-r4 → r3 → r2 → r1-catalog2`, profile/base SHA256, версии 4/3/2/1,
account/native DB continuity, monotonic grant IDs/timestamps, payload hashes,
сохранение `shop.bin`/`dossier.bin`, r2 preservation receipt, vehicle/crew
mapping и точная ammo mapping (shell2570/turret5891/gun5892/inventory1).
Native crew/ammo blobs совпали с grant hashes; старый bundle с неверным порядком
цепочки отвергнут negative control. Старые validators/fixtures/live runtime не
менялись, SQLite/client не открывались. Profile4 новый encoder не создан,
r3/r4 absolute preservation и native proof не повторялись: `NOT_RUN`.
План и отчёт: `docs/plans/PROFILE4_PORTABLE_CHAIN.md`,
`docs/research/PROFILE4_PORTABLE_CHAIN.md`; receipt:
`local/evidence/20261006-profile4-chain/result-final.json`. Следующий один шаг:
сделать отдельный semantic diff r3→r4 для crew/ammo delta без native запуска.

**2026-10-06: portable server-content/encoder export — PASS_CONTENT_EXPORT.**
Создан отдельный `server-content.v1` bundle для проверенной MS-1 `test_lab`
closure: 56 измеренных blobs, относительные content IDs, digest каждого файла,
digest полного client manifest и frozen encoder dependency revision.
`tools/content_bundle.py` валидирует bundle без project config, SQLite или
установленного клиента; `tools/portable_hangar_state.py` прочитал descriptor,
profile и packed XML из bundle и повторил profile1-catalog2 byte-for-byte:
`state.bin` 1106 B, `shop.bin` 419 B, `dossier.bin` 8 B. В bundle нет паролей,
email, session, live DB/WAL или абсолютных client paths; старые fixtures,
validators и absolute provenance сохранены без изменений. Profile4 immutable
r4→r3→r2→r1 chain экспортирован как hash-anchored closure, но отдельный новый
profile4 encoder ещё не объявлен. Ресурсы остаются `UNKNOWN; local-only
non-redistribution` до проверки лицензии. Native compatibility, свежий обмен с
клиентом, live cutover и 15×15 — `NOT_RUN`; это переносимость локального
генератора, не native acceptance. Тесты: 2 content-bundle unittest PASS,
bundle verification PASS 56/56, portable profile1 generation PASS. План:
`docs/plans/CONTENT_ENCODER_EXPORT.md`; отчёт:
`docs/research/CONTENT_ENCODER_EXPORT.md`; evidence:
`local/evidence/20261006-content-export/result-final-2.json` и bundle-папка. Следующий один шаг: отдельная
проверка portable profile4 chain на чистом bundle-rooted API без изменения
старых validators и live runtime.

**2026-10-06: opt-in identity/account boundary — PASS_IDENTITY_BOUNDARY.**
Создан отдельный loopback-only `identity.account.v1` сервис в
`server/identity/account_service.mjs` с версионированной SQLite migration,
единым `account_id`, email-only login, русским/латинским ником, scrypt hashes,
browser sessions и profile owner. Новый портал `web/src/account_portal.mjs`
проверен через регистрацию, явный повторный вход, смену профиля и чтение того же
UUID. `game` service-role проверяет те же email/credentials и получает только
`account_id`/ник/created_at; пароль, email, session и fixture path наружу не
выходят. Отказы contract mismatch, неверных credentials/role, неподдерживаемой
DB schema и недоступности сервиса проверены без ложного guest/fallback.
Пять isolated Node tests PASS; все SQLite/токены были в
`local/staging/identity-boundary`, live backend/site/client не переключались и
не перезапускались. Legacy `web/src/server.mjs`, `server/identity/service.mjs`,
старый native gateway и frozen encoders сохранены. Это HTTP/account boundary,
не доказательство native compatibility, настоящего боя или 15×15.
План и фактические границы: `docs/plans/INFRASTRUCTURE_BOUNDARIES.md`;
подробный отчёт и receipt: `docs/research/IDENTITY_BOUNDARY.md` и
`local/evidence/20261006-infrastructure-boundaries/`.
Следующий один шаг: отдельная карточка versioned server content/encoder export,
чтобы game profile generation перестала читать установленный клиент и evidence
paths, сохранив старые validators/provenance до независимой проверки.

**2026-10-06: организация серверных исходников — PASS_SERVER_SOURCE_LAYOUT.**
Завершена отдельная карточка структуры, без развёртывания и изменения физики.
Canonical `server/`: control, identity entrypoint, gateway с protocol/account/
arena/drive, physics. 20 Rust + 2 C# core files перенесены byte-identical,
старые точки запуска/сборки используют тот же source. Имена файлов без `091`
и `P01`; protocol IDs/ресурсные пути/исторические manifests сохранены.
291 canonical + 290 legacy Rust tests/build PASS; 50 Python PASS;
layout 7 PASS/1 SKIP (Windows symlink permission); identity 4 PASS.
Оба C# build PASS; два новых worker реально загрузили geometry, ответили
ready+3 состояния и завершились EOF/exit0. Их состояния на одном Windows
хосте совпали; общая/cross-platform детерминированность этим не доказана.
Ранние C# offline restore FAIL и identity harness FAIL сохранены отдельно.
Ordinary deployed EXE/config/PIDs не переключались: supervisor96576,
identity81748/gateway5192, site43164; capture=False. Source/library/client
hash preservation закрывается `local/evidence/20261006-server-layout/final-audit-02/result.json`.
Новая сборка gateway называется sr-gateway, но текущая служба всё ещё закреплена
за прежним p01-wg-probe.exe. Fresh init также сохраняет прежнее binding правило.
Новый native вход/поездка и Linux/remote build/ABI — NOT_RUN в этой карточке.
Shared identity/encoders остаются frozen; свежий профиль ещё зависит от client
resources и provenance paths. Это source layout, не самостоятельный deploy.
Документация: `server/README.md`, `docs/SOURCE_LAYOUT.md`.
Следующий один шаг: versioned server content/encoder inputs без зависимости
генерации аккаунта от установленного клиента и исследовательских каталогов.
Прежние ограничения pivot/круиза/разрушений ниже сохраняются.

**2026-10-06,11:15 UTC+5: ordinary backend восстановлен без capture;
итог ручного protocol повтора PARTIAL.** Два настоящих Flash-входа,14 camera
changes, первый штатный return/warm/reentry подтверждены, неожиданных
disconnect/reject/Python exceptions0.542 publications совпали с worker,
538 ACKed;4 последних retired при штатном quit из второй арены. Второй warm
return NOT_RUN; nonzeroMove→первый6 после fix2 NOT_OBSERVED (captured regression
PASS). Strict reader FAIL сохранён, supplementary scope PARTIAL.290Rust
tests/build PASS, source review0 blockers. Обычная служба supervisor96576,
identity81748/gateway5192, run061506-d7a679; capture=False, тот же pool,
exe daef0dde…0608c3b; клиент016 прежний. Не объявляется полный P02 PASS.
Владелец сообщил отсутствие pivot и разрушения деревьев. A/D доходят до
TrackedVehicleController, near-rest yaw почти не меняется: причина UNKNOWN.
Мир пока static MeshShape, разрушений нет. Частичные cruise25/50% дают safety
stop;100% идут ordinary flags1/2, действие владельца по ступеням NOT_RUN.
Остановки на подъёме OBSERVED, конкретная причина UNKNOWN. Подробности:
`docs/research/P02_SNIPER_CAMERA_PROTOCOL.md`, `P02_DRIVE_LIMITATIONS.md`;
evidence `local/evidence/20261006-sniper-camera/`. Следующая отдельная карточка —
диагностика pivot, без одновременной реализации разрушений/стрельбы.
Закрывающая read-only сверка ordinary runtime:88 build sources,34 immutable
client files,43 worker/map hash bindings PASS; оба native UDP и identity
слушают127.0.0.1. Сайт3091 сохраняет прежний внешний процесс и адрес0.0.0.0.
`local/evidence/20261006-sniper-camera/final-state-02/result.json`, SHA256
`59f1d6c872f5904ac11357770428e3058e8bf1f0cb5c43d566e968eba0e5d3dc`.
Reader01 harness FAIL (лишнее требование loopback к внешнему сайту) сохранён,
runtime не менялся. Полный inventory клиента/БД сегодня не повторялся.

**2026-10-06, после ручного повтора: fix1 camera PASS_SCOPED, второй вход FAIL;
fix2 собран, native повтор ожидается.** Первые8 переключений камеры прошли,
1719/1719 publications совпали с worker и ACKed; штатный возврат/warm sync.
Второй вход отверг exact app `8a01000106` (Move1→correction6), хотя footer
ACK1863 правильно подтверждал binding1862. Движение проверялось раньше6 в
том же compound; ошибка откатывала валидный ACK и RX. Это возникло до camera
RPC; время нажатия владельца не объявляется причиной. Fix2 учитывает exact6
в том же полностью parsed envelope, сохраняя настоящие forceACK/clone guards
и отсутствие worker effects до commit. 290Rust tests/build PASS, independent
review0 blockers; EXE SHA256
`daef0dde9e012beac4e0f363bf66b672ec4a154473be4b05b00cfe4cc0608c3b`.
Closed fixed-review-01 сохраняет FAIL_REPRO_SECOND_ENTRY; повтор fix2 NOT_RUN
до закрытого native результата. `local/client-install-016` прежний.

**2026-10-06,10:37 UTC+5: ручная Flash-кнопка PASS_2_NATIVE_FLASH_CLICKS;
переключение снайперского прицела — исправление на native повторе.**
Ordinary пакет016 нормализует измеренный callback float0.0→int0. Два реальных
клика открыли Avatar/карту;72 команды движения приняты сервером. Владелец
подтвердил движение/повороты/задний ход, круиз OBSERVED_OWNER_FEEDBACK;
точный контракт круиза UNKNOWN. На подъёме остановка/возобновление движения
OBSERVED_DEFECT, физика test_lab. Полный ручной цикл пока FAIL_TWO_DISCONNECTS:
оба разрыва при снайперском режиме и один последующий Minimap traceback сохранены.
Closed capture1704packets доказал первое неподдерживаемое приложение
`8d05000200000000`: original Avatar Base vehicle_changeSetting(setting2,INT32zero),
настройка автоповорота камеры.5B heartbeat отказы были следствием RX gap.
Сервер теперь валидирует только setting2/INT32 0|1; whole-envelope/ACK guards
сохранены, применение к физике отсутствует и явно логируется.
288Rust tests PASS,offline locked build PASS; новый executable
SHA256 `71b5e9de0af56aab433199ace0e508f69bfa9f8a6d0d738ece620bc776d63e61`.
Native повтор после исправления ожидается, **NOT_RUN до закрытого результата**.
Сайт не перезапускался, клиент016 не менялся; diagnostic capture включён только
для этого повтора. Отчёты: `docs/research/P02_MANUAL_BATTLE_BUTTON.md`,
`docs/research/P02_SNIPER_CAMERA_PROTOCOL.md`; evidence:
`local/evidence/20261006-manual-battle-button/manual-result-01/`,
`local/evidence/20261006-sniper-camera/`. Стрельба/урон/двое не подключены.

**2026-10-06, утро: запуск после устаревшего supervisor.lock восстановлен —
PASS_LOCAL_SERVICE_RECOVERY.** `status` теперь проверяет процессы, прежний
сохранённый RUNNING с отсутствующими PID сообщает как STALE. Автовосстановление
архивирует точные state/lock и требует подтверждённого отсутствия всех старых
процессов, совпадения владельца и свободных игровых портов. Живые/непроверенные
PID и maintenance lock сохраняются. Ранние ошибки serve также освобождают
собственную блокировку; lifecycle guard автоматически освобождается ОС.
36 lifecycle tests и65 применимых regression tests PASS. Обычный backend
поднят: supervisor78824/identity47384/gateway91148, оба native UDP endpoints
и identity health проверены. Внешний сайт43164 поднят с прежней network.json,
ownership/capture/map pool не менялись. Повторный start при живой службе
получил ожидаемый отказ без изменения state/lock. Игровая БД семантически
неизменна; полный дамп БД сайта изменился, точный состав утренней разницы
UNKNOWN (предполагается штатная очистка истёкших sessions). Пользователи
совпадают с сохранённым эталоном предыдущей карточки. PARTIAL этой проверки
сохранён отдельно; не объявляется полная неизменность обеих БД.
Ручной вход владельца сегодня OBSERVED; «В бой!» дал старый hangar-only отказ,
ручная поездка остаётся NOT_RUN. Отдельная карточка
`docs/plans/P02_manual_battle_button.md`: установлен ordinary policy, но первый
фильтр mapID/actionName не пропускает настоящий Flash callback; точные аргументы
пока UNKNOWN. Отчёт восстановления службы:
`docs/research/P02_SERVICE_RECOVERY.md`; evidence:
`local/evidence/20261006-service-recovery/`.

**2026-10-06,02:24 UTC+5: карточка локальной поездки PASS;
финальный аудит сохранности PASS; ручной ввод владельца NOT_RUN.**
Ride21:5 поездок одним EXE (Карелия×4, Прохоровка×1),5946packets,
1760/1760 публикаций подтверждены ACK,12/12 строгих остановок PASS.
Минимальный dense low-speed suffix2.7403s; worker после отхода от камня2.8s.
3129samples: own/bodyΔ0, targetdrop0;10560 масок опор, airborne0.
Ride22: native-путь до границы Прохоровки, stall под газом5.0258s
(worker5.8s), reverse6.4045m, остановки и возврат.881/881 публикация ACKed.
На ударе14/5286ticks потеряли левую опору, правая осталась; airborne0.
Измерено краткое перекрытие грубого корпуса со стеной8.585cm; не скрывается.
GUI/wire/data проверены независимо. Root просмотрела4PNG21 и3PNG22.
Исторические PARTIAL16/19 и FAIL17/18/20 сохранены.

Установлен `local/client-install-014`:25 модулей,34 immutable files и3
сохранённых owner logs. Sources/actual273 bytecode совпадают с21/22.
Автологин/автозакрытие/capture отключены, enable_map_drive=True.
Серверный режим `legacy091-map-drive`, тот же build10/pool, сайт не
перезапускался; игра закрыта. Полные manifests3469 original/3499 research
сняты и сверены с историческим baseline: неожиданных отличий0. Два semantic
DB snapshots, профили4/1, fixtures и4 конфигурации сохранены. Final audit
перепроверил25 текущих diagnostic restores/25replays,32619packets и27
исторических restore records. В обычном режиме native0/worker0, mutex свободен.
Итог `local/evidence/20261005-p02-map-drive/final-audit-02/final-state-audit.json`,
SHA256 `c07de7886178861d5c254eb0df1e0711446f01ec018b45547c8fb3482bc973c7`,
status `PASS_AUTHORIZED_LOCAL_DRIVE_SCOPE`. Предыдущий FAIL итогового reader01
сохранён: старый startup Bind03 имел другую документированную схему времени;
исправлена только её точная проверка, не runtime. После этого PASS менялся
только итоговый текст четырёх документов; отдельная inventory02 фиксирует
неизменность всех остальных исходников без повторения native опытов.
Доказательства: `local/evidence/20261005-p02-map-drive/` →
`data/ride21-physics-review-01`, `data/ride22-physics-review-01`,
`wire/ride21-review-01`, `wire/ride22-review-01`,
`gui/ride21-native-review-01`, `gui/ride22-native-review-01`,
`gui/normal014-package-review-01`, `root-visual-review-06`,
`root-visual-review-07`, `server-ordinary-12/after.json`.
Единственный следующий шаг владельца — ручной круг МС-1: «В бой!», движение
и задний ход, препятствие, возврат в ангар и повторный вход. Без таймера
закрытия игры и без управления компьютером со стороны агента.
Утреннее сообщение назначено около09:30 UTC+5. Полный P02/стрельба/бой вдвоём
не приняты; историческая физика UNKNOWN, текущий контроллер test_lab.

Ниже — история промежуточных прогонов; поздние результаты не переписывают FAIL.

**2026-10-06, ночь: поездка по карте — IN_PROGRESS.**
Последнее уточнение, около 01:40 UTC+5: Ride19 на build10 прошёл Карелию и
Прохоровку одним EXE, два возврата; 955/955 публикаций совпали с worker и ACK.
GUI/wire PASS_SCOPED, общий результат PARTIAL: после отскока на остановке
worker дал 1.8s покоя; между 1Hz замерами native filter кратко снова ускорился,
поэтому dense suffix у второго маркера 1.747s. Минимум приёмки 2s не меняется;
следующий диагностический вариант увеличивает ожидание до 3s. Камера19:
1070 samples, own/body Δ0, targetdrop0; reverse относительный maxstep 6.14mm
на Карелии / 3.13mm на Прохоровке. Это OBSERVED в данном прогоне.
Ride20 boundary_only сохранил FAIL до движения: validator скриншотов ещё
не принимал новую группу имён map_boundary_rNN_*. Клиент закрыт, installer
и replay откатились. Граница по-прежнему NOT_RUN. Результаты:
`local/evidence/20261005-p02-map-drive/data/ride19-physics-review-01`,
`local/evidence/20261005-p02-map-drive/data/ride19-hold-explanation-01`,
`local/evidence/20261005-p02-map-drive/wire/ride19-review-01`,
`local/evidence/20261005-p02-map-drive/gui/ride19-native-review-01`,
`local/evidence/20261005-p02-map-drive/root-visual-review-05`.
Сервер перезапущен с тем же build10 только для свежего ограниченного capture:
`local/evidence/20261005-p02-map-drive/server-drive-restart-11/after.json`.
Обычная установка normal014 ещё NOT_RUN.

R=`local/evidence/20261005-p02-map-drive/`. Ride16 одним EXE прошёл пять
случайных арен (Карелия четыре раза, Прохоровка один), пять возвратов в готовый
ангар; 25 снимков Account/ammo/repository совпали. Все1360 серверных публикаций
совпали с worker и подтверждены ACK; 4694 пакета,2399 native samples.
Wire/lifecycle PASS в этом объёме. Строгая остановка PARTIAL: в9/10 интервалов
фактический низкоскоростной suffix короче2s; исправлен только диагностический
отсчёт с первого допустимого замера. Ride17 сохранил FAIL во второй арене:
серверный poll_drive отказал при публикации worker247, затем оборвалась сессия.
Текст generic invalid() не доказывает неизвестный входящий RPC. Wire выясняет
конкретный guard. Первая Прохоровка17 уже подтвердила настоящий dense stopped
suffix2.667/2.854s после original stop; весь17 не принят. Ввод не автоматизируется.
Причинный replay исходных команд Ride16: полная карта побитно повторила716
состояний и4296 масок; без только696 треугольников целевого камня машина
продолжает путь. Под непрерывным газом2.9s: с камнем0.35mm, без17.14m.
Это OBSERVED_CAUSAL_IMPACT_AND_BLOCKING; sampled overlap2.65cm и прежний
NOT_CONFIRMED строгого5s критерия сохранены, нулевая пенетрация не заявлена.
Доказательства: `R/data/ride16-physics-review-06`,
`R/data/ride16-rock-causal-review-01`, `R/wire/ride16-review-03`,
`R/gui/ride16-native-review-03`, `R/root-visual-review-04`.
Общий source с режимами phase2_drive/boundary_only закреплён в
`R/gui/boundary-promotion-01` и`R/root-mode-integration-01`;186 focused tests
Python3 PASS,181 actualPython2.7.3 PASS+5 прежних host-only SKIP;
102 control/runner regression PASS. Реальная native граница ещё NOT_RUN.
Обычная установка normal014 и итоговый аудит ещё NOT_RUN; клиент во время
исследования запускается только через откатываемый диагностический installer.
Сайт не перезапускался, источник аккаунта и конфиги не менялись.
Игра17 закрыта, install/replay rollback PASS. Утренний heartbeat уже назначен
на6октября около09:30 поЕкатеринбургу.
Build10 применён после сохранённого старого regressionFAIL и284/284RustPASS:
новый запрос worker ждёт следующего непубликовавшегося native tick; ошибки
публикации именованы; аварийный Account reset отправляется сразу. До actual09
старые проверенные Avatar envelopes ограниченно разбираются без применения к
миру. Native прохождение аварийного recovery отдельно NOT_RUN.
Ride18 наbuild10 закрылся со сценариемFAIL: камень удержал машину; после
backoff5.45m basicforward3.82m снова привёл turn в препятствие, поэтому
порог угла не достигнут за30s. Меняется только диагностический отход12m,
граница/обычная физика не смягчаются. Клиент18 закрыт, rollback PASS.
Ниже сохранена история предшествующих результатов этой карточки.

**2026-10-05: управляемая поездка через «В бой!» — IN_PROGRESS.**
План `plans/P02_map_drive.md`, R=`local/evidence/20261005-p02-map-drive/`.
Владелец расширил задание до поездки, случайной проверенной карты, штатного
возврата в ангар и повторного входа. Промежуточные опыты это не закрывают.
Baseline380 authored files/17 local files/2SQLite backups сохранён до изменений.
VERIFIED readonly: native forcedPosition и updateOwnVehiclePosition нужны для
привязки Avatar.vehicle/ownVehicleMProv; прежнее движение тела этого не доказывало.
OBSERVED: отдельный synthetic Jolt tracked API test прошёл forward/turn/brake/reverse,
но не проверяет карту или клиент. Terrain/BSP двух original maps импортируются.
Кнопка и серверный random уже наблюдались на обеих картах; полная поездка,
статический obstacle и возврат/re-entry пока не приняты.
Предыдущие PASS ниже относятся только к явно указанным узким checkpoint.
Bind03 теперь PASS binding only: actual own/body ΔZ2m, original callbacks,
53.100s/426packets/exit0/restorePASS; Bind01 wireFAIL иBind02 observerFAIL сохранены.
Семь native Karelia rays совпали с mesh до0.00002885m. Новый .NET/Jolt worker
собран; обе mapmesh offline пройдены с measured MS-1 и test_lab подвеской;
840ticks/map, все тики имеют опоры слева/справа, forward/turn/reverse/stop PASS.
Worker-v1/pool опубликованы только в ignored local/. Полноценная
native поездка/button/random/return ещё НЕ ПРИНЯТА; работа продолжается.
Ride01/02 FAIL сохранены. Ordinary service policy counter1 + guard до внешнего
urlopen проверены настоящим клиентом: original CaptchaFalse,blocked0.
Исправлен diagnostic None→INT32zero для случайной карты. Ride03 уже даёт
CMD700→server random→workerREADY→Avatar/Vehicle. CMD502 исправлен и проверен.
Ride05 выявил native heading=worker roll: VERIFIED PE #717 требует RPY для
0x06/0x15, тогда как0x09/0x4a используютYPR. Только эти два codec исправлены,
253Rust tests PASS, build04 SHA59de4e8e…810f7. Ride06 выбрал Prohorovka;
начальный native yaw совпал с worker yaw. Запуск FAIL до движения: observer
потребовал roster ready раньше получения отправленного native ready122B.
Ожидание исправлено. Ride07/09 native forward/turn/reverse/stop наблюдались,
176 публикаций Ride07 побайтно связаны с worker и original callbacks/ACK.
Возврат выявил штатный warm enable09 и новую нумерацию ClientChat; исправлены.
Ride09 уже прошёл warm100/300/600, original showGUI/stream completion; текущий
observer FAIL — неверная классификация загрузки spaces/hangar_v2 после leave.
Исправляется только этот observer. Retry чтения native targetNone теперь0.1s,
прежняя readiness gap3s не увеличена. Полная приёмка по-прежнему IN_PROGRESS.
Все исходные FAIL/trace/replay сохранены, install rollback PASS. Серверные
273 теста PASS; отдельный opt-in capture profile48k/32MiB подготовлен для
same-EXE обеих случайных карт. Обычные лимиты и отсутствие autquit сохранены.
Ride10 обнаружил отсутствующий LOBBY_SUB во время перехода; добавлен exactNone
wait, без catch-all. Ride11 прерван отдельной nativeforward командой вне сценария
(её происхождение ещё проверяется). Владелец наблюдал рывки камеры приreverse;
это новый обязательный дефект к устранению до приёмки, не визуальный PASS.
Проверяется periodic0x4a correction против native interpolation и worker motion.
Владелец явно подтвердил: в Ride11 клавиши движения не нажимал. Происхождение
дополнительной команды UNKNOWN; не классифицировать её как ручной ввод.
Закрытые трассы подтверждают скачок own provider Ride09: за0.109072s он
сместился вперёд0.489508m, тогда как body/model/server двигались назад.
Это ещё не доказательство движения самой камеры: actual camera transform
тогда не записывался. R/data/ride11-jitter-review-01/result.json сохраняет
числа и ограничения; R/gui/sampler-checks-02 — новый ограниченный пассивный
измеритель actualcamera/own/body. Следующий опыт A сохраняет65B; кандидатB
проверяет initial4a + periodic15-only без изменений физики и клиентских позиций.
2026-10-05 вечером владелец поручил автономно продолжать эту карточку ночью;
утренний отчёт с ручными проверками назначен на6октября09:30–10:00 UTC+5.
Ride13A/Прохоровка: полный original Fight→drive→leave→готовый Hangar,
54.400965s/643packets/620samples/3PNG/exit0/restorePASS. Все7 movement callers
объяснены; команда Ride11 не повторилась, её происхождение остаётсяUNKNOWN.
Измеритель исправлен по signed32 native callback handle; отрицательный token
реально записан. Ride14B/Карелия и Ride15B/Прохоровка с тем же client source
прошли полный цикл. Build08(8a3d3dcc…41d43d) сохраняет initial122B/4a, дальше
публикует31B tickSync+15. Same-map A13/B15: reversecamera/body maxstep
0.477005→0.003705m, own/body совпали во всех674B samples, target switches300→0.
Это scoped camera/drive/return результат. Полная карточка ещё IN_PROGRESS:
same-EXE повторные карты, native obstacle/bound и обычная установка не закрыты.
Точные доказательства: R/gui/ride13a-native-review-01;
R/wire/ride14b-camera-review-01 иride15b-camera-review-01;
R/data/ride13-frame-review-03 иride15-frame-review-01 (итоговыйA/B отдельный).
Root просмотрела actual PNG A13/B15: карта/МС-1/90HP и возвращённый ангар
подтверждены, цветная сетка в original screenshot остаётсяUNKNOWN.
Развёрнутый текущий отчёт: `research/P02_MAP_DRIVE.md`.

**2026-10-05: native команда движения → серверная позиция — PASS узкой карточки.**
Q=`local/evidence/20261005-p02-arena-movement/`.
Move02/PID114140:63.536s,437packets/14794B, originalforward1→serverpath2m→
originalstop0, nativeVehicle/entitymatrix/modelmatrixΔZ=2m,hold≥3.015s.
Окончательный независимый отчёт19/19 PASS:
`Q/data/verify-move02-final-01/arena-movement-native-verification.json`, SHA256
`dc09da9016bb6fe6f2e8c4391dd7de7a3f4203271eb014aab759db53bd20548f`.
Nativeperiod3 только внутриlab,10Hz/1m/s/2m — собственная политика опыта.
97publications; четыреterminalstopped updates136–139 безACK перечислены
отдельно (доставкаNOT_RUN), принятие движения/hold на них не опирается.
Два originalPNG просмотрены,90/90HP; exit0/cleanup/restorePASS.
Move01 — сохранённыйFAIL наблюдателя доforward: originalauto0earlyRETURN12
ошибочно запрещался. Исправлен только exactautomatic branch;explicitstill345.

181Rust/40control/40runner/18profile/39verifier PASS;scenario36Python3,
35Python2.7.3+1host-onlySKIP иcompilePASS. Исходный Rust180/1FAIL negativefixture,
ранние readerFAIL иcorpora сохранены. Точные команды/хеши/откат —
`research/P02_ARENA_MOVEMENT.md`; план `plans/P02_arena_movement_probe.md`.
Normal01322modules/31immutable+3ownerlogs установлен; ordinarygateway
run121443-951a48 безcapture/trigger, сайт не перезапускался, клиент закрыт.
Обаgeneratedreplay сохранены/hash/timebound иоткачены;manifestoriginal3469/
research3496. Итоговая сверка — `Q/final-audit-01/final-state-audit.json`.
Baseline373sources/17localfiles/2SQLitebackups; игровые данные не менялись.

OBSERVED: getOwnVehicleMatrix осталась уseed,contacts0/0, nativeYoffset−0.07084m,
gunrotatorне запущен. Это ещё не управление своей машиной и не groundphysics.
ПолныйP02PARTIAL;NOT_RUN: гусеничныйконтроллер,ammoAvatar,выстрел/урон,
второйигрок/итоги/нагрузка. ЦветнаясеткаUNKNOWN; свежегоPythontracebackнет.
Один следующий шаг: originalcontrolEntity/сервернаякоррекция и связь с
getOwnVehicleMatrix в отдельном ограниченном опыте. Он здесь не начат.
Предыдущие ordinaryпакеты/рекомендации ниже — история.

**2026-10-05: native setClientReady → серверный PREBATTLE — PASS узкой карточки.**
O=`local/evidence/20261005-p02-arena-ready/`. Ready01/PID27912:90.528s,
247 пакетов/8202B, actual33B→51B preparation, семь разных значений таймера
на интервале6.036s. Два действительно просмотренных native PNG:27→21.
Exit0 и четыре стадии cleanup PASS; независимый отчёт18/18:
`O/data/verify-ready01-final-02/arena-ready-native-verification.json`, SHA256
`094edf304e3b39f6871440f2793df22a5a73ee9f16c1ee0dcc7bf051e7e272f8`.
Сервер применяет только готовность после ACK create97; три других метода
явно неподдерживаемые. Монотонный дедлайн30s не перезапускается и не начинает
BATTLE. Native expiry30s NOT_RUN: клиент завершился по выполненному условию.
Частота10 — параметр собственного опыта, не историческая tickrate.

162 Rust +31 control +40 runner +18 profile +33 verifier PASS; сценарий:
47 Python3 /46 Python2.7.3 PASS +1 host-only SKIP, отдельно PASS на Python3.
Независимый GUI/lifecycle review15/15 PASS: `O/gui/native-ready01-review-02/`.
Первый review-helper FAIL на неверном лимите8KiB для старого ammo-события
сохранён; исправлен только reader, исходные данные/клиент не менялись.
Original LightManager штатно инициализирован(enabled=false) и уничтожен.
Свежего Python traceback нет; графические DEVICE_LOST/RESET/shader warnings
и цветная сетка PNG остаются OBSERVED/UNKNOWN. Вводом компьютера не управляли.

Normal012 установлен:21 modules/30 immutable+3 owner logs; ordinary gateway
run105936-a33e1a без capture/trigger. Сайт не перезапускался, клиент закрыт.
Replay2096B сохранён по exact hash; дата/mtime связаны с запуском, прежнее
отсутствие восстановлено: `O/ready01-replay/restore.json`. Baseline365 sources/
17 local files/2 SQLite сохранён. Final manifest: original3469/research3495.
Отдельный результат итоговой сверки: `O/final-audit-01/final-state-audit.json`.
Полный отчёт, команды и откат: `research/P02_ARENA_READY.md`.

Физика: `research/PHYSICS_AUTHORITY.md`, original5 files/10 methods/17 anchors
PASS_READONLY_RESEARCH. WGVehiclePhysics/filter есть в клиенте; точное
предсказание/коррекция UNKNOWN. Jolt — кандидат библиотеки внутри battle worker;
прежний sphere/floor spike не доказывает гусеничное движение.
Полный P02 PARTIAL: BATTLE, Avatar ammo, ground contact, движение, стрельба,
второй игрок NOT_RUN. Один следующий шаг — ограниченный native эксперимент
команды движения своего МС-1 и серверного обновления положения. Он не начат.
Более ранние обычные установки и рекомендации ниже — история.

**2026-10-05: native арена с собственным МС-1 — PASS узкого checkpoint.**
N=`local/evidence/20261005-p02-arena-entry/`. Vehicle03 настоящий#717/PID73668:
Account→Avatar→Карелия→МС-1, native Battle/HUD,90HP и исходные модели;
172packets/6730B,4готовых наблюдения3.012s,65.475srun,exit0/cleanup/restore.
Независимый17/17 PASS `N/data/verify-vehicle03-final-01/arena-vehicle-native-verification.json`
SHA256 `42a55da5b88e3f2a2105c013e260fc6a70559007f5b136abc6520d6822fa19f2`.
GUI lifecycle/cleanup review14/14 PASS; свежего traceback/__manualSound нет.
Original Vivox unsupported и штатный AccountRepositoryNone warning сохранены.
Нативный снимок действительно просмотрен: ожидание игроков00:00, лабораторная
точка, контакт с грунтом не доказан. Цветная сетка PNG остаётся UNKNOWN.

Исправлен реальный wire порядок:221Bобъявление→actual08+ACKannouncement40→97B
Vehicle. Четыре original init-step return101/101/101/640; prerequisites,
onEnterWorld/startVisual и normal teardown подтверждены. Actual33B содержит
bindToVehicle/changeSetting/setClientReady/autoAim; пока только transport ACK,
без применения доменных команд. Серверные фазы/отсчёт/Avatarammo/движение/
стрельба/второй игрок NOT_RUN. Полный P02 PARTIAL, P03 не начат.

141Rusttests,24Vehicle-verifier,22rootguards+40runner+18profile PASS;
entry26/bootstrap28/space27/Vehicle41 — на Python3 и2.7.3 PASS,capacity19 PASS.
Ранние base01/space01/space02/vehicle02 ипервыйverifier03 FAIL сохранены;
неустановленный vehicle01 NOT_RUN.7настоящих диагностических запусков этой
карточки откатились; дополнительно сохранён generated replay1784B и восстановлено
его отсутствие по exact hash, `N/native-generated-replay-01/result.json`.

**Normal011 установлен:**20modules/29immutable+3ownerlogs, безtestcontrol/
autologin/autoquit/capture/управлениявводом. Gateway ordinary, сайт не
перезапускался этой карточкой, клиент закрыт. Профилиprimary4/secondary1 прежние.
Итоговая независимая сверка original/research,32 ledger entries,4configs,
профилей/fixtures и runtime: `N/final-audit-02/final-state-audit.json`.
Параллельная web demo работа из следующей записи сохранена отдельно и не
включается в функциональную приёмку арены. Полный отчёт/команды/откат:
`research/P02_ARENA_ENTRY.md`. Оценка1000CCU: `research/CAPACITY_1000_CCU.md`,
ориентиры3/5/7 физических узлов — ESTIMATE_ONLY, настоящая нагрузка NOT_RUN.
Единственный следующий шаг — серверная обработка настоящего setClientReady
и фаза подготовки одной арены с родным отсчётом. Эта карточка не начата.

**2026-10-05: публичная демоверсия сайта — PASS.**
По отдельному уточнению владельца опубликован самостоятельный каталог на
`https://tanks.nsnull.su`: главная, техника/модули, карты/миникарты, без аккаунтов
и игровой интеграции. VPS использует отдельные service/user/vhost и HTTPS;
существующий `duo.nsnull.su` сохранил конфигурацию и ответ авторизации.
5 Node-тестов и453 HTTPS-проверки (431изображение) PASS; браузер1280/390px PASS.
Локальные сайт и игровой bridge не перезапускались. Отчёт
`../web/REMOTE_DEMO_REPORT.md`, evidence `local/web/remote-deploy/20261005-01/`.
Это приёмка демонстрации каталога, не изменение статуса native P02 ниже.

**2026-10-05,14:05: native Avatar BASE принят; геометрия Карелии загружена,
чистое завершение частичного Avatar пока FAIL. Карточка арены IN_PROGRESS.**
N=`local/evidence/20261005-p02-arena-entry/`. Base02 independent14/14 PASS
(`data/verify-base02-final-02/`). Space02 independent14/15: точные cell/space
по родному09, original onEnterWorld/onSpaceLoaded, inWorld/space1/load1 PASS;
Vehicle отсутствует, initcounter1, userSeesWorld/worldDrawFalse. Fresh caught
original teardown AttributeError звука башни делает clean runtime FAIL:
`data/verify-space02-final-01/arena-space-native-verification.json`, SHA690b5ff9…9bec.
Оригинальный init_sound выполняется только после последнего шага с Vehicle;
заглушки полей и пропуск destroy не применяются. В этой же карточке готовится
настоящий собственный МС-1 + roster для завершения native lifecycle. Стрельба,
движение и бой NOT_RUN. Старая запись normal010 ниже историческая: сейчас она
штатно откачена; клиент закрыт, gateway в явном исследовательском space-режиме.
Расчёт1000CCU `research/CAPACITY_1000_CCU.md` готов (ESTIMATE_ONLY),19testsPASS.


**2026-10-05,12:51: начата карточка native Account → Avatar / локальная арена.**
План `plans/P02_arena_entry.md`; N=`local/evidence/20261005-p02-arena-entry/`.
Baseline сохранён:336 authored-файлов,17 local-файлов,2 SQLite backups.
Normal010 штатно откачен,3 свежих owner logs сохранены. Реальный resource export01
PASS: original Account/native PID9316,46 packets, родная Карелия type1/ctf,
`spaces/01_karelia/space.settings` доступен;11 исходных hash pins совпали.
Завершение exit0,12 cleanup, rollback PASS. Export не создавал Avatar/space;
загрузка арены и бой пока NOT_RUN. Evidence `N/native-arena-entry-export01.json`
SHA256 `11163b6e86951434d16221fd6fc6d7996a46628b71e75819185f6c28d9f17c2b`.
Подготовлен отдельный opt-in checkpoint смены native player; текущий рабочий
gateway ещё не заменён. Полный P02 PARTIAL, карточка арены IN_PROGRESS.
Параллельный расчёт1000CCU готов: `research/CAPACITY_1000_CCU.md`,
19 arithmetic tests PASS. Ориентиры3/5/7 физических узлов — ESTIMATE_ONLY;
нагрузка настоящего боя и1000 игровых сессий NOT_RUN.
Следующие записи — история предыдущих завершённых карточек.

**2026-10-05,11:54: минимальный серверный боекомплект МС-1 — PASS.**
В принятом test_lab primary profile4:20 обычных ББ,0 HEAT,0 ОФ. Сайт/API
показывают20; оба настоящих входа с прежним profile002 показали20/0/0 через
родной `AmmunitionPanel.__updateAmmo → as_setAmmoS`. В каждом94packets,
3actual snapshots/2PNG, ready17.1284/17.0981s,exit0/12cleanup/restorePASS.
Никаких закупок/пополнения/стрельбы;96 — вместимость,20 — тестовая выдача.
Отчёт `research/P02_MS1_AMMO.md`, M=`local/evidence/20261005-p02-ms1-ammo/`.
Paired report `M/wire/verify-ammo02-pair-02/ms1-ammo-verification.json` SHA256
`b218c032e9fddbee62f5284e98db9cb7019ddead25994d847af8119272ca035c` PASS;
41verifier tests и60 независимых отрицательных controls PASS. 84Rusttests,
85webtests (82full+3targeted),75root regression PASS. Новые data19Python+8Node,
GUI27+32+18 на Python3 и2.7.3 PASS; native не заменён этими unit tests.
**Normal010 установлен**,16modules/25immutable+3ownerlogs, безautologin/autoquit/
capture/управлениявводом. Native закрыт; сервер/сайт работают.
Fullaudit `M/final-audit-02/final-state-audit.json` SHA256
`cc69a32abcdd6b8ced4f82dd8884ecca8f3e330fa695b1baebb7f5471bba8a49` PASS:
original3469/research3490,0unexpected,17completed diagnostic restores,
4configs и secondary сохранны,21negativecontrols PASS_REJECTED.
Независимый review полного аудита также PASS:14дополнительных RAM controls,
`M/gui/final-audit-review-01/result.json` SHA256
`1ea80bb84c67456f76c459e5c8da5776978f34c5fb807d20896e9d66e19fbbe5`.
Выдача обратима4→3 с journal SHA555015e2…87819; exactcommands в отчёте.
Production rollback и ручная проверка владельцем новой выдачи NOT_RUN.
Полный P02 PARTIAL; арена/бой NOT_STARTED. Единственный следующий шаг:
минимальный native Account→Avatar и загрузка одной своей локальной арены.
Карточка завершена; дальнейшие фазы этим запуском не выполняются.
Более ранние IN_PROGRESS/NOT_RUN ниже — история, не текущая приёмка.

**2026-10-05,11:24: P02 боекомплект МС-1 — IN_PROGRESS.**
После разрешения владельца начата одна карточка `plans/P02_ms1_ammo.md`.
Владелец закрыл клиент; before/backups и свежие owner logs сохранены, normal009
штатно откачен. Настоящий export01 прочитал родные данные #717: вместимость96,
снаряды2570/2826/3082, выбор танка не изменён. Native process/capture/restore PASS;
envelope `local/evidence/20261005-p02-ms1-ammo/native-ms1-ammo-export01.json`,
SHA256 `683daac81143a9d7edfbe671870ba163db088c54f5101fa52e077f596ebbfc74`.
Политика test_lab:20 обычных ББ,0 HEAT,0 ОФ, без склада и автопополнения.
Это ещё не выдача: профиль primary пока3; native приёмка боекомплекта NOT_RUN.
Подготовлена добавочная схема4 с неизменным catalog3/wire1; арена/бой вне среза.
Записи ниже описывают историческое состояние на указанный момент.

**2026-10-05,10:41: естественное истечение сессии и повторный вход — PASS_MANUAL_AND_BACKEND.**
Владелец: «истечение сработало, выбросило на вход, вход прошел нормально».
Сохранённый gateway подтверждает SESSION_CLOSED id11 reason=session_deadline
настроке5790, затем session12 ACTIVE5835 для того же UUID/nativeID, sync100/300/600
и showGUI. Между сессиями38no_session rejects, в session12 до конца snapshot
отказов нет. GUI подтверждён владельцем (OBSERVED); точная задержка перехода
UNKNOWN, автоматический native trace сценария NOT_RUN. Новых запусков нет.
Отчёт `research/P02_MANUAL_EXPIRY_20261005.md`; evidence
`local/evidence/20261005-p02-manual-expiry/review01/result.json`, SHA256
`7fb14ef7c550a3f6a6821a6f198fcdbc5a0a7a09cb1f8301e5509914ec2b58a1`.
Normal009 и сервер оставлены работающими, конфигурация/код/профили не менялись.
Полный P02 PARTIAL. Следующий рекомендуемый срез: исследовать родной контракт
боекомплекта МС-1 и проверить минимальный серверный боекомплект после relogin.
Эта новая карточка не начата. Более ранние NOT_RUN ниже — история до подтверждения.

**2026-10-05, после утреннего запуска владельца: ручная проверка PASS (OBSERVED).**
Владелец явно подтвердил «Всё нормально» для входа, экипажа МС-1 и переключения
МС-1 ↔ ИС-7. Отчёт `research/P02_MANUAL_ACCEPTANCE_20261005.md`.
Evidence `local/evidence/20261005-p02-manual-acceptance/review01/result.json`,
SHA256 `9903b5ed5dc0c63702bec6d01fb826f9378bdd1294f05dd633f79d191934e50b`.
Все23 immutable файла обычной009 совпадают с принятой установкой. Свежий
сохранённый python.log:0EXCEPTION/0Traceback,2известныхERROR неподдерживаемого
Vivox. Завершённая server session10 успешна; точная временная связь с клиентским
блоком INFERRED. Более поздняя session11 наблюдается отдельно, mutex занят;
её результат не приписывается предыдущему проходу. Новых запусков/тестов нет.
Ручной PASS относится только к явно перечисленным трём пунктам. Expiry1800s
и прочие окна NOT_RUN; полный P02 PARTIAL. Следующий шаг прежний: настоящий
session_deadline1800→disconnected→LoginView. Исторические ночные записи ниже
сохраняют состояние на момент их написания.

**2026-10-05,07:46: ночной срез завершён — native, полный audit и independent review PASS.**
План `plans/P02_long_hangar.md`, отчёт `research/P02_LONG_HANGAR.md`,
L=`local/evidence/20261005-p02-long-hangar/`. Независимый final audit review завершён:
11 actual bindings и38 negative controls PASS, `L/wire/audit-review-01/result.json`,
SHA256 `c82997905b315e35636034b75acd87a5081a7203d1463233016fd69d3adc617b`.
Один EXE PID49420:938.3719s,2580packets/53082B,exit0/12cleanup/restorePASS.
Native ready913.2943s/909samples/maxgap1.0699222s.182реальныхCMD501/CCU1/1/
normalreturns;181послеready/span907.7934s.3совпавших полных snapshots,2PNG
просмотрены,0fresherrors/retransmissions. Это CCU, не изменение статистики игрока.
Final20gate report `L/wire/verify-long01-03/long-hangar-verification.json`
SHA256 `c74df14374e053bab68c13a5c1b366814834b50ba8a084123340b32062b95d25`.
40verifier tests/55independent controls PASS. Первый verifier FAIL(generator
resume counted as new entry) сохранён; native повтор не понадобился.
**Normal009 установлен**,14modules/23immutable+3ownerlogs, безcontrol/autologin/
autoquit/capture/управлениявводом. Native закрыт, server/site работают.
Fullaudit `L/final-audit-02/final-state-audit.json` SHA256
`1932650550743d296355af81edd48c8e176820853a9e52ba916c6c0e82a2cf1e` PASS:
original3469/research3488,0unexpected,14completedrestores,54negativecontrols;
29backend/4configs/70runtime/обаprofiles/fixtures сохранны в границах L.
Откат ordinary009 после закрытия клиента и сверки ledger:
`python -B -X utf8 tools/interactive_client.py rollback --out local/client-install-009`.
Утренний отчёт `research/OVERNIGHT_20261005.md`, индекс файлов
`research/OVERNIGHT_20261005_FILES.md`. Heartbeat automation-2 PAUSED после
завершения ночного среза; новые карточки не запускаются. Единственный следующий шаг:
реальный session_deadline1800→disconnected→LoginView. Сейчас UNKNOWN/NOT_RUN:
gateway закрывает session безnativekick; немедленный возврат GUI не обещается.
Ручная приёмка ночных изменений NOT_RUN. Полный P02 PARTIAL,арена/бойNOT_STARTED.

**2026-10-05,06:42: поздние datagrams закрытого BaseApp peer — PASS.**
План `plans/P02_retired_base_replay.md`, отчёт `research/P02_RETIRED_BASE_REPLAY.md`,
T=`local/evidence/20261005-p02-retired-base-replay/`.
Один настоящий replay01 PID96040:280 packets, из них277native+3 точных повтора
из действительно освобождённого старого peer. Все3 отвергнуты; B остался готов,
A вернулся со своими данными. Exit0/12cleanup/restorePASS,3PNG просмотрены.
Final verifier `T/wire/verify-replay01-02/retired-base-replay-verification.json`
SHA256 `8a7274f8f6742af1dd2a3d343d8a52817ac2c5f7c0bb85d019a86a44ae0f72f5`.
59verifier tests,58independent controls,14gates offline repeat PASS.
Final audit `T/final-audit-02/final-state-audit.json` SHA256
`05a209133d77e92aa51864083ff59dcdf86c846cf55829234567be4b2af9a066` PASS:
original3469/research3487,0unexpected,13restores,оба profiles/fixtures прежние.
Независимый audit review: actual binding и17negative controls PASS.
**Normal008 установлен**,13modules/22immutable+3ownerlogs, без control/auto-login/
auto-quit/capture;normal007 проверенно откатан. Клиент и probe закрыты.
Сервер run20261004T234409-c866fd и сайт работают. Откат после закрытия игры:
`python -B -X utf8 tools/interactive_client.py rollback --out local/client-install-008`.
Следующий шаг исследуется отдельно: длительный готовый ангар с реальными
periodic server updates. Пока NOT_RUN. Ручная приёмка NOT_RUN; полный P02 PARTIAL.
Никаких новых выдач, экономики или арены.

**2026-10-05,05:49: переключение primary → secondary → primary — PASS.**
План `plans/P02_account_switch.md`, отчёт `research/P02_ACCOUNT_SWITCH.md`,
evidence `local/evidence/20261005-p02-account-switch/` (S).
Один EXE PID7600,3 настоящих auth/Account/repository,279 packets=93+92+94,
16.073/16.076/16.070s готового ангара,3 просмотренных native PNG.
NativeIDs1→2→1; машины2→1→2,танкисты2→0→2, собственные dossier/streams каждого
аккаунта, точное восстановление primary cache. Данные профилей не менялись.
Exit0/12cleanup/restorePASS,0trace/0свежихPythonerrors. Ручная приёмка NOT_RUN.
Verifier60ffcbbe…29d4,46 tests PASS, независимые31 review controls PASS.
Final report `S/wire/verify-switch02-02/account-switch-verification.json`
SHA256 `530dd12717cef8967d23fded670b49fa3d0c3855c56a2ee88537403d17612dd6`.
Root repeat `S/root-verification-02` PASS. Старый verifier пропускал лишние
public metadata fields; exact schema исправлена, промежуточный PASS сохранён.
Runner больше не сохраняет SHA control с credentials, только проверяет в RAM.
На момент закрытия S **Normal007 установлен** (позднее проверенно откатан
карточкой T),13modules/22immutable+3ownerlogs, без control/auto-login/
auto-quit/capture. Full original3469/research3487,0unexpected,12restores,
20negative audit controls;29backend/4config/2profiles/fixtures unchanged.
Final audit `S/final-audit-02/final-state-audit.json` SHA256
`5f3f202c65acf530c1d594e652d9330a65fb205f3cb9f7007379c74b55102c42` PASS.
Игровой клиент закрыт; server run20261004T234409-c866fd и сайт работают.
Откат после закрытия игры и проверки ledger:
`python -B -X utf8 tools/interactive_client.py rollback --out local/client-install-007`.
Следующий отдельный шаг начат карточкой T выше. Арена/экономика/новые выдачи
не начинались.

**2026-10-05,05:06: повторный вход внутри одного EXE — PASS.**
План `plans/P02_inprocess_relogin.md`, evidence `local/evidence/20261005-p02-inprocess-relogin/`.
До изменений сохранены288 sources/14 local files/2 DB. Первый настоящий запуск
R01 завершён FAIL: после корректного logoff сервер отверг второй login кодом73.
Клиент сохраняет транспортный ключ внутри EXE, но меняет encrypted nonce и
LoginApp endpoint; прежний запрет любого retired key слишком широк. Отрицательный
report `local/evidence/20261005-p02-inprocess-relogin/wire/verify-relogin01-negative-01/inprocess-relogin-verification.json`
SHA256 `8b3dea4c27a28b51861672b5cb54601e8a32ee19af76a0b1ee85deb39d808dfe`.
95 пакетов, один ангар/PNG, exit0/12 cleanup/restore PASS. Normal005 откатан;
клиент закрыт. Узкая политика nonce и retired endpoints внедрена,83 Rust checks
PASS; новый gateway EXE `8aea2e503c3b20e13b5eb9a9be7d66d2912a5027d8404a268bf65dfc778c41e1`.
R02 завершил оба входа и два16s интервала готового ангара в одном PID90800:
188 packets,2 PNG просмотрены,exit0/12cleanup/restore,0 свежих ошибок.
Строгий verifier83 tests PASS, итоговый native report
`local/evidence/20261005-p02-inprocess-relogin/wire/verify-relogin02-03/inprocess-relogin-verification.json`
SHA256 `9f42acfd7928d824ad4e52a22c9c0470784a76252e1aff8a82577a047c40b071`.
Root повтор отдельно PASS (`root-verification-01`). Доказаны два свежих auth
worker, retirement1 до allocation2, две доставки всех точных payload/cache.
На момент закрытия R **Ordinary006 был установлен** (затем проверенно откатан
карточкой S),12 compiled modules/21 immutable files+3logs,
без control/autologin/autoquit/capture. Full original3469/research3486 audit
PASS,0 неожиданных отличий,11 диагностических restores; оба profile/fixture
прежние. Итоговый audit SHA256
`0ff1f08a1c7d56a3ac1c1e378aa4848d74511ead31bad52745df6916ffc6ff35`.
Сервер/сайт работают, клиент закрыт. Ручная приёмка ordinary006 NOT_RUN.
Генераторы, fixtures и игровые профили заморожены; мышь/клавиатура
не используются. Предыдущие обычные установки ниже — исторические checkpoints.
[Отчёт, проверки, ограничения и откат](research/P02_INPROCESS_RELOGIN.md).
Откат normal006: `python -B -X utf8 tools/interactive_client.py rollback --out local/client-install-006`.
Следующая отдельная проверка: primary → secondary → primary в одном EXE,
изоляция существующих аккаунтов и кэшей. Пока NOT_RUN; бой NOT_STARTED.

**2026-10-05,03:47: два неподключённых окна ангара — узкая карточка PASS.**
«Внешний вид» и «Обслуживание» из панели теперь показывают отдельные родные
предупреждения. Оба исходных entrypoint/fireEvent и неподключённые окна не
вызываются; информационные callbacks модулей сохранены. Ремонт, пополнение,
кастомизация и бой этим не реализуются.

Windows01→02: по78packets/3 native PNG/3 неизменных crew snapshots,
0 новых ошибок,exit0/12cleanup/restore PASS. Тот же profile002 и ненулевые
cache hints. Парный report `local/evidence/20261005-p02-hangar-windows/wire/verify-windows02-paired-01/hangar-windows-verification.json`,
SHA256 `62a206bf7c208a313900b12e5cfdcf30b4a7690d01676ae8e7ea81a4d78903ec`;
root повтор побайтово тот же. Policy110/scenario31/runner33/verifier53 checks PASS.

**Checkpoint обычной установки normal005**,11 проверенных compiled modules,
без control/autologin/autoquit/capture. Игра закрыта, сервер и сайт работают;
primary profile3 с экипажем МС-1, второе игровое состояние побайтово прежнее.
Full manifest/ledger audit PASS:original3469/research3485,0 неожиданных отличий,
9 ночных restores. Report `local/evidence/20261005-p02-hangar-windows/final-audit-02/final-state-audit.json`,
SHA256 `ddbfa7525ce105e44518f1ae4bb797e31db588af46718fb898503627788eda32`.

Откат: `python -B -X utf8 tools/interactive_client.py rollback --out local/client-install-005`.
Физические клики, ручная приёмка и отдельный запуск normal005 NOT_RUN.
Цветная зернистость native PNG UNKNOWN. Полный P02 PARTIAL; арена/бой NOT_STARTED.
[Отчёт, ограничения, команды](research/P02_HANGAR_WINDOWS.md).
Следующий отдельный проверяемый шаг: original logoff→LoginView→повторный вход
одним аккаунтом внутри одного EXE, без перезапуска. Пока NOT_RUN.

## Checkpoint границ боя и приветствия

**2026-10-05,03:12: границы боя и приветствие — PASS.** Полные native
limits02→limits03 прошли: оба танка, профиль и возврат, реальный disabled
Flash-button, complex tooltip, явный отказ callback, ноль команд мутации.
По6 просмотренных PNG,3 неизменных crew snapshots,0 новых ошибок в каждом
успешном проходе;exit0/12cleanup/restore PASS. Тот же profile002 и ненулевые
реальные cache hints подтверждены отдельной строгой проверкой.

Парный report `local/evidence/20261005-p02-hangar-limits/wire/verify-limits03-strict-01/hangar-limits-verification.json`,
SHA256 `f296eaedd7e9c40aad4a7da9d58d24070cfbbf25819da2775d3a4abf74162587`.
63 проверки verifier PASS. Limits01 сохранён FAIL собственной диагностики;
его штатный выход не выдаётся за успешный сценарий. [Отчёт, команды и откат](research/P02_HANGAR_SERVICE_LIMITS.md).

**Сейчас normal004 установлен**, те же10 compiled modules и два MO, которые
проверены limits03. No control/autologin/autoquit/capture; игра закрыта,
сервер/сайт работают. Откат: `python tools/interactive_client.py rollback --out local/client-install-004`.
Ручной запуск именно этого normal-конфига NOT_RUN. Физический hover NOT_RUN;
проверен original complex API и текст на PNG. Original/research full manifests
сняты:3469/3484 файлов; финальная сверка ledger PASS, неожиданных отличий0.
`local/evidence/20261005-p02-hangar-limits/final-audit-02/final-state-audit.json`
SHA256 `506c0792bf55f1bac0fda5c21ca3d00f364fd1e01a4c993be3ad93395755dddb`.
Семь диагностических откатов и22 before-checks пакета004 PASS. Второй аккаунт
реально проверен через сайт, его игровая запись побайтово прежняя.

Дальше в разрешённой ночной доводке — отдельная карточка входов
«Внешний вид»/«Обслуживание». Оригинальная причина первого падения исследована;
ремонт, пополнение, кастомизация и бой этим не реализуются. Полный P02 PARTIAL,
P03/арена/бой NOT_STARTED. Человеческая приёмка ночью NOT_RUN.

## Checkpoint минимального экипажа

**2026-10-05, ночной checkpoint: минимальный серверный экипаж МС-1 — PASS.**
Собственный primary получил двух танкистов, профиль3. Реальная доставка,
родное отображение, явный отказ изменения экипажа и cached relogin crew02→03
проверены. Деньги/XP/статистика, ИС-7 и второй аккаунт сохранены. Сайт/API
показывают назначение экипажа. Ручная приёмка владельцем NOT_RUN.

Доказательства: `local/evidence/20261005-p02-ms1-crew/` (`C`). Парный отчёт
`C/wire/verify-crew03-final-01/ms1-crew-native-verification.json`, SHA256
`ec625af4067714e80c56a7bb260007483f1ef8736da2ea5c7d452683c7961dd6`.
Полная Node suite73, Rust62, независимый verifier34 PASS. Crew01 FAIL
наблюдателя сохранён; crew02/03 — по62 пакета, три crew snapshots и два PNG,
штатный exit0,12 cleanup и rollback PASS. [Отчёт/команды/откат](research/P02_MS1_CREW.md).

На момент checkpoint экипажа игра закрыта, диагностические overlays сняты. Normal003 уже откатан;
последние пользовательские логи сохранены. Normal004 ещё НЕ установлен.
Сервер/сайт работают с profile3, конфигурации endpoint не менялись.
Полный P02 PARTIAL; P03, арена и бой NOT_STARTED. Долгий проход с новым
экипажем NOT_RUN, найм/обучение/перемещение/личное дело недоступны.

Владелец поручил автономную работу до утра: [ночной план](plans/OVERNIGHT_20261005.md).
Следующая отдельная узкая карточка — честная недоступность кнопки боя и
исправление одного старого приветствия; исследование `C/data/next-hangar-gates.md`.
Она не реализует очередь, экономику или бой.

## Предыдущий checkpoint UI13

**2026-10-04: контрольный UI13 и пара UI08 → UI13 — PASS.** Закрыта
узкая карточка двух машин, подсказок/Awards и повторного входа с кэшем.
Полный P02 остаётся PARTIAL; P03/арена/бой не начинались.

`E` = `local/evidence/20261004-p02-hangar-ui/`.

| Проверка UI13 | Результат |
|---|---|
| Ручной запуск без таймера стенда | PASS; новый manual_client_run,14/14 unit tests; никаких автокликов |
| Повторный native вход с прежним profile002/cache | PASS; initial100/300/600 + revision1 refresh; кэш не очищался |
| Устойчивый ангар до вкладок | PASS;125.7657979s,126 последовательных samples |
| МС-1 ↔ ИС-7, native модели/имена/90 и2150HP | PASS; фактический цикл и native PNG |
| Original complex ToolTip и Awards | PASS; callbacks, просмотренные native PNG;0 свежих ошибок UI13 |
| Подсказка недоступности оборудования | OBSERVED/PASS на фото владельца; хранится отдельно от native markers |
| Сеть/сервер | PASS;586 packets,198.9757065s канала, точные3 streams |
| Ручное завершение | PASS;247.3996002s процесса,exit0,no timeout,11 cleanup,rollback PASS |
| Общий verifier/session/cards/relogin | PASS; `E/is7-verifier/ui13-reviewed-01/` |
| Аккаунты после UI13 и последующего normal003 | PASS; оба точных профиля/ресурсы/статистика сохранены |

Отчёт UI13 SHA256 `2b6620e1b91725bfe941a59dbffbc968748630381fb9fc090a24e53213cee3cc`.
Независимый wire proof: `E/wire-analysis/ui13-manual-proof-01/`,16/16 PASS.
Фото оборудования: `E/owner-screenshots-ui13/`; свежие профили:
`E/accounts-after-normal003-01.json`. Исторические UI09–UI12 FAIL сохранены.

**Отдельная проверка владельца normal003: обнаружены ошибки найма экипажа
и внешнего вида.** Владелец подтвердил собственный повторный запуск22:32–22:33
и открытие этих окон. Trace62556 подтверждает вход и ангар; python.log содержит
IndexError в RecruitWindow.__getInitialData и
VehicleCustomization → ShopRequester.getInscriptionsGroupHiddens. Эти окна
ещё не готовы. Свой outcome/exit code и отдельная полная приёмка normal003
отсутствуют (UNKNOWN/NOT_RUN), ошибки OBSERVED_FAIL. Это не тот же run, что UI13.
Логи не откатывались: `E/normal003-extra-launch-01/`. Аудит04 FAIL по снимку
менявшегося во время ручного запуска лога сохранён. Финальный `E/final-audit-05/`
PASS: original3469 файлов неизменны; research3480, неожиданных отличий0;
12/12 диагностических восстановлений,17/17 backups пакета003 и отдельная
проверка отката002 PASS. Допускаются только два точных сохранённых user-log
хеша;4 отрицательных проверки отвергают любые другие изменения.

Сейчас установлен обычный `local/client-install-003`: те же6 compiled modules,
profile002, endpoint127.0.0.1:20014, без control/autologin/autoquit/автоскриншотов.
Игра закрыта, сервер/сайт работают. Нового таймера закрытия EXE нет; собственный
лимит серверной сессии1800s пока остаётся. Откат после закрытия клиента:
`python tools/interactive_client.py rollback --out local/client-install-003`.
Выдача ИС-7 и данные аккаунтов сохраняются. Команды/доказательства/границы:
[GUI](research/P02_HANGAR_UI.md#ui13-ручное-завершение-вместо-таймера),
[ИС-7](research/P02_TEST_IS7.md).

Следующий рекомендуемый отдельный шаг: минимальный серверный экипаж МС-1
с проверкой отображения и сохранения при повторном входе. В этой задаче
экипаж, кастомизация, боеприпасы и бой не реализовывались.

## Предыдущий checkpoint и история

Текущая карточка, 2026-10-04: **тестовый ИС-7 выдан, каталог модулей
исправлен, повторный native-вход с сохранённым кэшем работает. Полная
приёмка карточки PARTIAL; полный P02 PARTIAL, P03 NOT_STARTED.**
[Каталог/GUI](research/P02_HANGAR_UI.md), [ИС-7 и cached sync](research/P02_TEST_IS7.md).

`E` = `local/evidence/20261004-p02-hangar-ui/`. Основной аккаунт получил второй
серверный экземпляр ИС-7,2150HP; МС-1, UUID/nativeID,100000/0/0 ресурсов и
нулевая статистика сохранены. Сайт/API показывают обе машины; второй аккаунт
сохранил свой МС-1. Повтор выдачи ALREADY_GRANTED. Финальный read-only контроль:
`E/accounts-final-01.json` PASS, сайт3091 работает.

| Проверка | Фактический результат |
|---|---|
| UI08: первый вход с двумя машинами | session/garage PASS,357 packets,74.336 s ready, Awards pixels PASS,exit0/rollback PASS |
| UI09: первый cached relogin | FAIL: не распознаны persistent hints CMD100/300; исторический corpus сохранён |
| UI10: следующий cached run | FAIL: initial streams приняты, но CMD100 revision1 с тем же persistent hash ещё отвергался |
| UI11: после обоих исправлений | wire/backend/garage/GUI PASS,289 packets,0 свежих ошибок,exit0/11cleanup/rollback PASS; strict session FAIL только41.173 s непрерывного ready вместо60 |
| UI12: контроль устойчивости | OBSERVED657.113 s непрерывного готового ангара; полный run FAIL по720s harness timeout/exit1, штатный cleanup NOT_RUN; filesystem rollback PASS |
| Код | 236 Python checks закрыты:235 PASS+1skip в общей suite, пропущенный файловый тест отдельно PASS; Node65/65, Rust61/61 PASS |

UI11 final report: `E/is7-verifier/ui11-reviewed-final-01/test-garage-verification.json`.
Он не маскирует непрошедший duration gate успехом GUI. UI12 не склеивается с
UI11 в выдуманную успешную сессию. Пиксели текста недоступности оборудования
остаются NOT_RUN; оригинальные complex callbacks с этим текстом наблюдались.
Технические исправления проверены настоящим клиентом, полная парная приёмка
с60 s ready, нужными пикселями и штатным выходом в одной сессии ещё не закрыта.

Постоянный research-пакет: `local/client-install-002`, свой endpoint20014,
профиль `local/client-profile-002`, без control/autologin/autoquit/автоскриншотов.
Игра закрыта; сервер и сайт оставлены работающими. Отдельный запуск именно
этого финального конфига после установки NOT_RUN; те же compiled modules
проверены в UI11/UI12. Старый пакет001 восстановлен и повторно не используется.
Финальные manifests: `E/final-manifest-02/`; аудит установки и исходников:
`E/final-audit-03/`. Original3469 файлов неизменны. Research3480 файлов
соответствуют исходному состоянию, двум точно сохранённым входным логам и
финальному ledger: неожиданных отличий0,17/17 before/backup checks,
11/11 диагностических восстановлений PASS. Два лога изменились между
UI04 и UI05; инициатор UNKNOWN. Они сохранены, первоначальное строгое
сравнение остаётся FAIL (`final-audit-02`). Пустой temp replay после timeout
сохранён с хешем/backup и обратимо перенесён в `E/ui12-timeout-replay-01/`.

Откат клиентских overrides — своим ledger; откат выдачи — точная запись
профиля по журналу плюс отдельный обратимый шаг для owned dossier cache.
Реальный откат выдачи на primary NOT_RUN; временные SQLite rollback tests PASS.
Клиентское управление остаётся у владельца. Арена/бой/экипаж/боекомплект и
экономика не реализовывались этой карточкой. Следующий шаг один: завершить
контрольный cached relogin на той же копии с измеренными60 s до переходов,
подсказкой оборудования, Awards и ручным чистым выходом. Ниже история.

Дата исходного плана: 2026-10-02.

Обновлено: 2026-10-04 (Asia/Yekaterinburg). Runs: `20261002-p00-p01`,
`20261002-p01-bootstrap`, `20261002-p02-login-redirect`, `20261004-p02-baseapp-reply`,
`20261004-p02-channel-ack`, `20261004-p02-server-reliable`,
`20261004-p02-session-gateway`, `20261004-p02-account`,
`20261004-p02-account-ready`, `20261004-p02-hangar`,
`20261004-p02-unified-account` (финальная установка/audit завершены).

**Текущий узкий результат: единая email-учётка сайта и native-вход в ангар
с серверными данными — PASS. Полный P02 PARTIAL, P03 NOT_STARTED.**
Одна таблица users и один password verifier; account_id равен users.id.
Вход только по почте, отдельный уникальный ник поддерживает русские буквы,
латиницу, цифры и `_` с сохранением регистра. Email не входит в игровой
payload; resources/inventory остаются test_lab, статистика нового игрока нулевая.
План: [P02_unified_account_entry](plans/P02_unified_account_entry.md);
отчёт и точные команды: [P02_UNIFIED_ACCOUNT](research/P02_UNIFIED_ACCOUNT.md).

В этом текущем блоке `E` = `local/evidence/20261004-p02-unified-account/`.

| Проверенный срез | Результат и evidence |
|---|---|
| Основной сайт → прежний аккаунт → native | PASS Email17: UUID `c5326cc1…`, nativeID1,91.360 s готового ангара; `E/wire-agent/verify-email17-primary-01/unified-entry-verification.json` |
| Второй основной аккаунт с русским ником | PASS Email18: UUID `271022a3…`, nativeID2,176.846 s готового ангара,180.263 s соединения, server/client sequence134/40; `E/wire-agent/verify-email18-primary-cyrillic-01/unified-entry-verification.json` |
| Сохранение профиля через настоящий restart и relogin | PASS Email19: прежний UUID/nativeID1,76.359 s ready,254packet hashes; `E/wire-agent/verify-email19-primary-relogin-01/unified-entry-verification.json` |
| Два primary профиля и изоляция /api/game | PASS: `E/primary-state-before-restart-01/`, `primary-state-after-restart-01/`, `primary-state-after-native-01/`; UUID, данные и fixture hashes сохранены, чужой query не меняет subject |
| Единственный владелец основного сайта | PASS: `E/primary-external-restart-01/restart.json`; game supervisor остановлен/запущен, website PID9452 продолжил работу; external mode не владеет сайтом |
| Обычная форма входа без control/autologin/autoquit | PASS Normal21: процесс жив95.003 s, original LoginView ready76.435 s,0пакетов своего gateway; `E/gui-agent/normal21-prepare/normal-idle/normal-idle-report.json` |
| Ручной вход владельца в Normal20 | PASS только AUTH_AND_SERVER_ACCOUNT_DATA_ONLY: владелец подтвердил «Да, сам ввел, вошел, потыкал разное», trace связывает login с UUID `c5326cc1…`/nativeID1; `E/wire-agent/manual-auth20/manual-auth-analysis-02.json` |

**Полный GUI Normal20 — FAIL, не замаскирован успешным входом.** Сохранены семь
ошибок original ToolTip `len(None)` и одна ошибка primitive-сериализации
собственного observer. Observer исправлен:9 unit +5CPython2.7.3 checks
PASS. Email22 с новым source подтвердил wire/identity/ангар и exit0, но получил
ещё1originalToolTip error после fini_enter: **overall FAIL сохранён**.
Повтор самого ProfileAwards после фикса NOT_RUN. Producer пустого tooltipId
и точная кнопка/действие пока UNKNOWN. Historical idle gate Normal20
остаётся FAIL: человек выполнил вход во время измерения ожидания. Отдельный
Normal21 проверил нетронутую форму. Оба idle harness завершены собственным
принудительным stop, поэтому clean native exit для них NOT_RUN.

Финальная research-копия установлена: `local/client-install-001`,
без control/autologin/autoquit, свой endpoint20014/сайт3091. Клиент закрыт.
Полный audit **PASS**: original unchanged; research = baseline +12установленных
файлов, неожиданных изменений0; 21/21 диагностических откатов и15backup/before
checks PASS. Evidence: `E/final-state-audit-02.json`; состав source/hashes:
`E/project-after.json`, `project-changes.json`, `source-handoff-audit.json`.
Основные Email17/18/19/22 native PNG просмотрены root. Недостающих входных данных
для авторизации нет; двух независимых клиентов/ПК для будущей арены ещё нет.

## История предыдущих карточек

Ниже прежние NOT_RUN, таймеры и числа восстановлений относятся к указанным
карточкам. Текущие результаты и ограничения приведены выше.

**Предыдущий результат: штатный ангар и собственная сводка статистики с серверными
данными — PASS.** Итоговая серия normal/loss/rejection/relogin:4/4 на одном
живом gateway. Настоящий клиент показывает MS-1, ник,100000/0/0 тестовых ресурсов,
90/90HP и нулевую статистику нового игрока; original callbacks и Flash данные
коррелируют с серверными streams. Шесть native скриншотов просмотрены.
План: `docs/plans/P02_hangar.md`; [итоговый отчёт](research/P02_HANGAR.md).
Evidence: `local/evidence/20261004-p02-hangar/verify-final-03/hangar-verification.json`.
Работа была разделена на GUI, данные и wire; реальные запуски выполняла одна сессия.
Оригинальный клиент неизменен, все22 диагностических отката к своему before PASS.
Строгое сравнение research с началом карточки — FAIL по3логам отдельного старта;
они сохранены. Владелец сообщил, что, вероятно, пытался запустить клиент сам.
Полный audit: `local/evidence/20261004-p02-hangar/final-state-audit.json`.
В том лабораторном профиле сохранялись32 reliable sequence/таймер30s.
На этой точке остановились: арена, бои и экономические действия не начаты.
После завершения этого рубежа владелец разрешил следующий срез: **единая учётка
сайта/игры и ручной запуск исследовательского EXE на свой endpoint**.
На момент завершения ангара новая работа была IN_PROGRESS, её приёмка NOT_RUN.
Теперь узкая единая авторизация подтверждена текущим блоком и новым отчётом;
исторический ангарный PASS сам по себе её не заменял.
Единый аккаунт сайта/игры остаётся обязательным требованием; лабораторное
состояние игрока не является отдельным продуктовым реестром авторизации.

**P00 выполнен в текущей среде. P01 PASS по исследовательским критериям
docs/03_ROADMAP.md:** есть реальные client runtime traces, native login request
и принятый клиентом отрицательный ответ своего endpoint. Причина, достаточная
для раннего exit, воспроизведена через instance mutex. Карта оставшихся
неизвестных зафиксирована. По последующему разрешению владельца выполнена
узкая карточка P02: LoginSuccess → первый настоящий BaseApp request, два
клиентских запуска PASS. Следующая разрешённая карточка подтвердила BaseApp
reply, первый encrypted frame и настоящий callback LOGGED_ON в двух запусках.
Следующая карточка подтвердила ACK первого reliable frame и ограниченный
keepalive: 16.5853 и 21.6106 секунд после LOGGED_ON до диагностического quit.
Далее первый reliable packet сервера и его дубликат получили настоящий
client cumulative ACK=1/1 в трёх завершённых runs.
По новому разрешению идти последовательно до крупного шага выполнен
**локальный transport/session gateway рубеж**: 10 native входов/выходов подряд
на одном живом gateway; gap/selective ACK/retry, неверный пароль/digest,
дубликат, обрыв и recovery проверены. Итоговая серия 14/14 PASS.
Следующее разрешённое продолжение подтвердило первое native создание
`Account.PlayerAccount`: message ID5, entity type0, ID и 3 поля из server packet.
Пять реальных creation runs PASS по wire criterion, no-creation control PASS.
В следующей разрешённой карточке устранены исследованные bootstrap blockers:
**минимальный оригинальный Account lifecycle и начальная синхронизация PASS**.
Подтверждены три native RPC, original callbacks и один dossier stream с CRC.
Итоговая серия 8/8: семь успешных Account сессий на одном gateway, включая
loss/duplicate controls, и отказ неверного пароля. Последующий вход успешен.
Следующая карточка довела этот путь до штатного ангара и собственной сводки
профиля:4/4 native cases PASS. Настоящие state/shop/dossier streams, showGUI,
revision refresh и display-only данные проверены; state доставлен в3fragments.
На конец ангарной карточки обычный bootstrap/native preferences, persistence
и web→game login ещё были NOT_RUN; позднее они получили отдельные проверки.
Полный Account/P02 остаётся PARTIAL: общий канал/fragments/wraparound,
полный GUI и арена не приняты. Следующие фазы не начаты.

| Этап | Статус | Доказательства |
|---|---|---|
| P00 | PASS (локальная среда; вторая чистая машина NOT_RUN) | Полные manifests, Git exclusions, проверенный rollback |
| P01 | PASS — исследование, не приёмка игрового сервера | Runtime + native request/rejection PASS; stock toolkit native/vertices FAIL, отличия измерены |
| P02 | Единая email-учётка/native ангар PASS; полный gate PARTIAL | Primary17/18/19, два профиля/restart, normal idle21 PASS; ручной auth20 PASS, full GUI20 FAIL; final installation/audit PASS; Email22 overallFAIL(ToolTip при fini), general transport/арена NOT_RUN |
| P03 | IN_PROGRESS — same-PC native fire/reload, shared world/aim and projectile subcards accepted; full two-client/LAN battle gate open | `docs/ACTIVE_GATE.md`, accepted P03D–P03H receipts |
| P04 | PASS_TYPED_IMPORT_VALIDATOR (resource contract; native/physics NOT_RUN) | `local/evidence/20261007-p04-content-import-02/` |
| P05 | OFFLINE_BASELINE / native movement and reconciliation NOT_RUN | `docs/evidence-index/P05.md`, `docs/evidence-index/P05_MATRIX_AUDIT.md` |
| P06 | STATIC_BOUNDARY_ONLY / native impact, penetration and damage NOT_RUN | `docs/evidence-index/P06A.md`, `docs/research/P06B_MS1_AP_SOURCE_SPIKE.md`, `docs/evidence-index/P06D.md` |
| P07A | PASS_STATIC_VISIBILITY_SOURCE_BOUNDARY / native visibility NOT_RUN | `docs/evidence-index/P07A.md` |
| P08A | PASS_STATIC_BATTLE_LIFECYCLE_SOURCE_BOUNDARY / native lifecycle NOT_RUN | `docs/evidence-index/P08A.md` |
| P09A | PASS_STATIC_RESEARCH_TREE_GRAPH / native shop payload and visual handoff NOT_RUN | `docs/evidence-index/P09A_TREE_GRAPH_AUDIT.md`, `docs/evidence-index/P09A.md` |
| P09B | PASS_P09B_SQLITE_TRANSACTION_HARNESS / deployed runtime and native restart NOT_RUN | `docs/evidence-index/P09B.md` |
| P10A | PASS_DOCS_ONLY_STATIC_BOUNDARY / native room lifecycle NOT_RUN | `docs/evidence-index/P10A.md` |
| P11–P12 | NOT_STARTED | Нет |

Точный локальный билд: `v.0.9.1 #717`, RU; metadata client 435206,
overrides 435633, localization 428638 RU. Издательская аутентичность UNKNOWN.
Строка entity compatibility: `ru_0.9.1_2`.

Пути заданы в исключённом `config/project.local.json`; original только читается.
Исторический baseline до hangar: в обеих копиях3469 файлов /
14 680 626 869 байт. Content manifest SHA-256:
`74c37c18e9ac7e30196c134076dacf6f2a8bf3897f7def73905d09feb3647797`.
После запусков account-ready все файлы обеих копий совпали с baseline:
`20261004-p02-account-ready/integrity-comparison.json`.
Все19 client runs той карточки восстановлены; её `client-restores.json` сверяет
hashes с before. Позднейшие три log-различия research сохранены в hangar audit;
новая unified-card использует собственный baseline; final audit PASS с
явным сохранением финальной установки.

Путь старого офлайн-проекта: не требуется; не изменять.
Выбранный транспорт: NATIVE_PRIMARY; узкий login/rejection обмен проверен,
также проверены LoginSuccess, BaseApp reply и первый encrypted client frame;
ACK первого packet и bounded transport проверены; interactive native Account
session и >32sequence подтверждены текущей карточкой. Общий надёжный канал,
wraparound и арена ещё не проверены.
Первые последовательности, selective ACK, ограниченный retry/window и
минимальная лабораторная сессия подтверждены. Полный игровой lifecycle UNKNOWN.
Выбранный стек: предварительный; [ADR](decisions/ADR_TRANSPORT_AND_STACK.md).
Историческая формула разброса: UNKNOWN.
Доказанный онлайн: не измерен.

## Фактические результаты

Это хронология отдельных этапов. Прежний NOT_RUN означает состояние на момент
названного этапа; актуальная общая учётка и её ограничения перечислены в начале.

- PASS: 20 Python tests, из них 5 читают настоящий клиент; 70 файлов decoded,
  44 entity names, 23 aliases, 62 ZIP package indexes, 2255 pyc семейства 2.7.
  Активный runtime подтверждён: Python 2.7.3, MSC v.1700, 32-bit, Jun 17 2014.
- PASS: 128-мм WT E 100 clip=6; 150-мм clip=4; premium HESH FV183 цепочка
  конкретного орудия/снаряда даёт 275/275.
- PASS: collision hull Т-34-85 — 301 vertices, 198 triangles, 16 groups;
  прочитаны chunk/cdata Прохоровки. Полная физическая карта ещё не импортирована.
- PASS: wg-toolkit на commit `5b879f0...` собран и читает настоящий XML.
  FAIL: штатный vertex decoder оставляет 2408 из 9700 байт legacy section.
- PASS: JoltPhysicsSharp 2.22.0 / Native 1.1.0, headless Windows-x64/net9.0,
  300 steps и contact. .NET 10, tracked vehicle simulation, Linux — NOT_RUN.
- PASS: ранний exit воспроизведён занятым `wot_client_mutex`; теперь preflight
  отказывает до изменений, не закрывая игру владельца.
- PASS: собственный `.pyc` в res_mods загружается, marker/runtime получены.
  Python source-only на этом пути дал ImportError; исправлено компиляцией 2.7.3.
- PASS: два запуска без debugger — 273-byte native login → RSA OAEP/SHA1
  decode → 45-byte reply → `LOGIN_REJECTED_SERVER_NOT_READY` → штатный exit 0.
  Исторический код 73 подтверждён; современный toolkit code 74 означал updater.
- PASS: 4 Rust boundary tests и 4 проверки настоящего corpus/его повреждений.
  Stock toolkit читает этот packet неправильно; профиль legacy091 собственный,
  vendor не изменён. Полный login/arena — NOT_RUN.
- PASS: отдельная карточка P02 — ответ 28 B, Blowfish с ключом из native
  LoginRequest, redirect на второй loopback endpoint, шесть реальных BaseApp
  requests по 21 B в каждом из двух запусков. Токен ответа совпал с каждым.
- PASS: 51 проверка текущего corpus/backend (34 offline повреждения BaseApp,
  17 UDP controls/отрицательных случаев), повторные 20 Python / 4 Rust tests,
  прежний native P01 rejection и полный откат. `onChangeEnvironments` hook
  исправлен после ошибки первого run, свежие логи повторного запуска чистые.
- PASS (2026-10-04): BaseApp reply 24 B → первый encrypted client packet 24 B
  с новым token; callback `[1, 'LOGGED_ON', '']`, два настоящих запуска.
  После первого frame другие payloads не dispatch-ятся; наблюдался callback
  `[6, 'NOT_SET', '']`. Причина завершения пока INFERRED, стабильного канала нет.
- PASS: 75 новых corpus/backend checks (50 offline + 25 UDP), 8 Rust / 20
  Python tests, real redirect regression и полный client rollback. Новых
  dependencies нет; прежние profiles сохранены.
- PASS (2026-10-04, channel-ack): clear ACK `08 04 01 00 00 00`, encrypted
  16 B, прекращает повтор первого sequence=0. Два завершённых positive runs
  удержались 16.5853/21.6106 s; ACK=0 удержал связь с 9 вхождениями seq0;
  без ACK разрыв через 5.2258 s до planned quit.
- FAIL сохранён: `native-ack-01`, Windows UDP 10054 в capture при shutdown,
  итоговый exit отсутствовал. Runner исправлен с явной записью bounded reset
  events; повторные runs PASS, включая реальный 10054 в run 03.
- PASS: 34 новых parser/UDP/Windows checks, 75 прежних BaseApp regression
  cases, 11 Rust / 20 Python tests. Все пять client runs откатились, свежие
  Python logs чистые, полные manifests обеих копий совпали. Зависимости прежние.
- PASS (server-reliable): server seq0 и один identical duplicate → native
  transport-only ACK flags0x0448, sequence1/2, cumulative1/1. Три corrected
  runs, удержание16.58–21.62 s; keepalive-only control не вызывает этих ACKs.
- FAIL сохранён: native-01 нового run — bytes получены, но observer ошибочно
  требовал application token. Измеренный transport-only формат добавлен только
  в новый профиль за peer/key/handshake checks; native-02/03/04 PASS.
- PASS: 35 новых controls, 34 ACK regression cases, 13 Rust / 20 Python tests.
  Все пять запусков откатились, manifests совпали, процессы завершены.
  Исходник diagnostic personality в этой карточке не изменялся.
- PASS (session-gateway): server sequence1 при пропуске0 → selective ACK=[1],
  cumulative0; поздний0 → cumulative2; duplicate1 сохраняет2. В gateway
  контролируемая потеря первого0 устранена автоматическим retry по таймеру.
- PASS: один persistent gateway PID87048, 10 успешных native входов/выходов
  подряд; затем отказ пароля, blackhole и успешный recovery. Всего 14 сценариев
  итоговой серии; session IDs1–12, active state в конце отсутствует.
- PASS: native INVALID_PASSWORD=67 и BAD_DIGEST=69, без allocation; digest
  mismatch создан в server expectation, другой клиентский билд NOT_RUN.
- PASS: 33 новых own-UDP controls, 35 regression, 19 Rust / 20 Python tests.
  FAIL controls-01 был ошибкой bytes/bytearray в тестовом harness, сохранён;
  после исправления controls-02 PASS. Код gateway для этого не менялся.
- PASS: все 22 client runs восстановлены, полные manifests совпали. Personality
  получила только явный отрицательный парольный control; native callbacks
  не подменяются. Один disposable lab account; web/ не подключён.
- PASS (native Account wire): серверный `createBasePlayer` ID5/VAR2,
  type0, entity ID152043521 и три поля коррелируют с настоящим
  `Account.PlayerAccount` из `BigWorld.player()` в пяти запусках.
  Контроль без create packet: 22 пустых samples. Потеря packet с Account
  исправлена автоматическим retry; duplicate first client frame не создаёт
  вторую server session. Account/Entity callbacks не подменялись.
- FAIL предыдущей карточки (Account Python lifecycle): `Settings.g_instance.userPrefs` при
  `ContactInfo.py:43`, далее `syncData` отсутствует при become/non-player.
  Этот bootstrap blocker устранён в следующей карточке; старые ошибки сохранены.
- PASS: 20 Rust / 20 Python tests, 33 own-UDP controls, native no-creation
  regression; все 6 client runs восстановлены. Полные manifests после
  последнего запуска сверены с baseline. Файлы web не изменялись.
- PASS (account-ready): оригинальные Settings и Account ctor/onBecomePlayer/
  onBecomeNonPlayer завершаются; native data revision1/synchronized=True,
  pending commands/streams0; lifecycle доказан normal return offsets, не только
  отсутствием traceback. Original Account classes/callbacks не заменены.
- PASS: doCmdInt3 ID0x8e VAR2, commands100/300/600; onCmdResponseExt ID0x4d VAR1;
  native ranges прочитаны из88 bytes своего child. Остальные candidate IDs UNKNOWN.
- PASS: один dossier stream18 B, resource IDs52/53; original game CRC/length
  check и original Account.onStreamComplete подтверждены. General fragments NOT_RUN.
- PASS: 8/8 native series на одном gateway PID22872 — sessions1..7 и password
  rejection67 без allocation; потери create/sync reply и дубликаты first/RPC frames
  обработаны, commands по1 разу. Готовое состояние удерживается9.06–10.09 s.
  Отдельный повтор с исправленным runner и no-creation control также PASS.
- PASS: 26 Rust /20 Python tests, 311 actual-corpus mutation checks и33 прежних
  own-UDP gateway controls. Все19 client runs откатились, полные manifests обеих
  копий совпали,31 записанный собственный PID завершён/отсутствует, порты свободны.
- FAIL эксперименты сохранены: invalid preferences guard, file_server KeyError,
  unicode path TypeError, cache-thread timeout, wrong RPC route0x4c. Старый generic
  outcome ошибочно искал legacy log marker; исправление проверено отдельным run.
  Исследовательский getter shim изолирует Python caches; native preferences NOT_RUN.
- NOT_RUN на конец account-ready: полноценный ангар/магазин, разные пользовательские аккаунты, persistence,
  общая web→game авторизация, OS egress capture, арена. Пустое состояние своего
  diagnostic account не является проверкой экономики или готовности сервиса.

Git инициализирован, remote/commits нет; user.name/email не настроены.
Code version фиксируется evidence code-manifest. Клиенты, дампы, ключи,
локальная конфигурация, vendor и извлечённый контент исключены из Git.
Собственные отображаемые названия зафиксированы в [NAMING](NAMING.md):
владелец утвердил GAYmDev Stutio и рабочее «Стальной рубеж». README обновлён,
сессия сайта уведомлена. Технические имена/provenance сохранены, EXE и исходные
ресурсы массово не переименовывались. Названия карт пока не утверждены.

## Отчёты и приёмка

[CLIENT_AUDIT](research/CLIENT_AUDIT.md), [PROTOCOL_MAP](research/PROTOCOL_MAP.md),
[RESOURCE_MAP](research/RESOURCE_MAP.md), [INTEGRATION_SPIKES](research/INTEGRATION_SPIKES.md),
[KNOWN_UNKNOWNS](research/KNOWN_UNKNOWNS.md), [ADR](decisions/ADR_TRANSPORT_AND_STACK.md),
[MISSING_INPUTS](../MISSING_INPUTS.md), [команды/откат](research/REPRODUCE.md),
[evidence index](evidence-index/P00_P01.md).
Текущее продолжение: [BOOTSTRAP_AND_NATIVE_LOGIN](research/P01_BOOTSTRAP_AND_NATIVE_LOGIN.md).
Предыдущая карточка: [P02_LOGIN_REDIRECT](research/P02_LOGIN_REDIRECT.md).
Далее: [P02_BASEAPP_REPLY](research/P02_BASEAPP_REPLY.md).
Далее: [P02_CHANNEL_ACK](research/P02_CHANNEL_ACK.md).
Далее: [P02_SERVER_RELIABLE](research/P02_SERVER_RELIABLE.md),
[её evidence index](evidence-index/P02_SERVER_RELIABLE.md).
Далее: [P02_LAB_GATEWAY](research/P02_LAB_GATEWAY.md),
[её evidence index](evidence-index/P02_LAB_GATEWAY.md).
Далее: [P02_NATIVE_ACCOUNT](research/P02_NATIVE_ACCOUNT.md),
[её evidence index](evidence-index/P02_NATIVE_ACCOUNT.md).
Далее: [P02_ACCOUNT_READY](research/P02_ACCOUNT_READY.md),
[её evidence index](evidence-index/P02_ACCOUNT_READY.md).
Предыдущая: [P02_HANGAR](research/P02_HANGAR.md), включая точные команды,
снимки,4/4 native acceptance,38Rust/20Python/21encoder/52verifier checks и откат.
Текущая: [P02_UNIFIED_ACCOUNT](research/P02_UNIFIED_ACCOUNT.md): email-only,
русский ник, stable UUID/native ID, primary/restart evidence, normal/manual
срезы и сохранённый full-GUI FAIL. Source suites58Node/55Rust и независимые
native verifiers не объявляют готовность арены или всей продукции.
Ранние разделы выше — история отдельных карточек; их прежний NOT_RUN не заменяет
более позднее подтверждение штатного ангара и сводки статистики.

R02 runtime и диагностический путь R03 закрыты. R05–R07 имеют первый реальный
request/reply corpus. В отдельной карточке P02 подтверждён первый BaseApp
request/reply, первый encrypted frame/ACK и первый server reliable packet/ACK;
ограниченный канал и transport/session lifecycle проверены. Wire creation
Account/type0, original lifecycle/initial sync, showGUI и штатный ангар подтверждены;
неизмеренные entity/RPC IDs UNKNOWN. V02 PASS в лабораторном native-сценарии;
V01/V04 имеют подтверждённые поднаборы, полный P02 остаётся PARTIAL.

**Единственный следующий рекомендуемый шаг:** локализовать producer пустого
tooltipId на конкретной кнопке/действии, получить воспроизводимую original
trace и проверить исправление без подавления ошибки. Арена — отдельная
последующая карточка с явным разрешением; автоматического перехода нет.
P03 не начат.

Отдельно 2026-10-04 владелец запросил параллельную сессию сайта с регистрацией
и личным кабинетом. Чат `01a10526-7835-77f0-bccf-48f0baa5dee0` работает только
в `web/` и `local/web/`; имеет собственные проверки. Веб-авторизация не является
доказательством native Account/session или приёмки P02.
История уведомлений до unified-card: по прямому поручению владельца сайту отправлен статус:
его собственные регистрация/вход проверены, общей авторизации с игрой пока нет.
Сессии также отправлены подтверждённый minimal Account результат и новые
публичные названия. Web→game login не объявлен готовым.
После завершения ангара отправлено новое информационное уведомление:4/4 native
cases PASS, собственная сводка профиля работает, fixture остаётся test_lab,
единая авторизация ещё NOT_RUN; новой работы/фазы уведомление не поручает.
Владелец отдельно подтвердил единую учётку для сайта/игры: одна регистрация,
общие credentials/account_id/профиль. Тогда раздельность была временной,
требование добавлено в SCOPE/ARCHITECTURE и передано сайту. Его прежний
NOT_RUN закрыт current primary17/18/19 и state/restart evidence; история
уведомлений не является текущим статусом авторизации.

## P09A static TechTree handoff — 2026-10-08

Добавлен bounded read-only аудит `tools/techtree_handoff_audit.py`. По
hash-bound #717 `TechTree.pyc` подтверждены формы
`requestNationTreeData` (available/selected nation fields, `True`) и
`getNationTreeData` (unknown-nation guard, index selection,
`NationTreeData.load` → `dump`). Receipt:
`local/evidence/20261008-p09a-techtree-static-01/receipt.json`,
`PASS_STATIC_TECHTREE_HANDOFF_SOURCE`.

Это статическая граница. Account/shop payload, callback bytes, screenshot и
server handoff остаются `NOT_RUN`; запуск клиента, gateway и deployed service
не выполнялся. См. [P09A static handoff plan](plans/P09A_TECHTREE_HANDOFF_STATIC.md),
[research](research/P09A_TECHTREE_HANDOFF_STATIC.md) и
[evidence](evidence-index/P09A_TECHTREE_HANDOFF_STATIC.md).

Добавлен bounded static audit `NationObjDumper`: envelope `nodes/displaySettings/scrollIndex` и 13 node fields подтверждены receipt `local/evidence/20261008-p09a-nation-dumper-static-01/receipt.json`, `PASS_STATIC_NATION_DUMPER_OUTPUT`. Follow-up receipt `local/evidence/20261008-p09a-nested-shapes-01/receipt.json` и 7/7 targeted tests фиксируют только измеренные вложенные пути `unlockProps`/`displayInfo` и XML format conversions; payload-типы, native callback и serializer остаются `UNKNOWN/NOT_RUN`.
