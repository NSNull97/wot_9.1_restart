# P06C server-owned impact trace foundation — 2026-10-08

Карточка `codex/p06c-impact-pipeline` принята как
**PASS_CAPTURE_FOUNDATION / native_impact_status=NOT_RUN**. Shared laboratory
теперь ведёт bounded typed trace только для серверных admission → launch →
flight segment → range terminal. Записи finite, cross-battle-safe,
монотонные; World commit делает атомарно. Pinned профиль — MS-1 AP `2570`,
vehicle `3329`, gun `5892`.
Карточечный commit: `p06c: add bounded server impact trace foundation` на
ветке `codex/p06c-impact-pipeline`.

Gateway Rust suite: **381/381 PASS**. Receipt:
`local/evidence/20261008-p06c-impact-foundation-01/summary.json` (SHA-256
`dbc6c61ddd0ca8adba3d6e7e8f31a4d5524271fcb332750b30f8e2b712d1c0db`).
Source layout: **PASS_SERVER_SOURCE_LAYOUT**, 59 files / 22 relocations.

Intersection, material/normal/thickness, penetration, damage, HP/module/crew
и replay намеренно отсутствуют; синтетические hit/miss/damage rows не
создаются. Действующий P03J service/client runtime не менялся и не
перезапускался. Реальный P06C owner-gated capture остаётся следующим gate.

# Fresh current-head evidence after status-only merge — 2026-10-08

На проверенном head `39b36078a1030387fb95c3578d52cee28b4a6051`, совпавшем с
`origin/main` на момент запуска, сохранены свежие receipts для текущего
checkout. P04 bundle/import/map suite — **42/42 PASS**; `content_bundle.py`
вернул `PASS_CONTENT_BUNDLE`, а `content_import.py` —
`PASS_TYPED_IMPORT_VALIDATOR` с canonical SHA-256
`a1b1191b29bbae5e2aed2f4417a139c7e9a2e6740ec40698347ad6baa8aac2b9`.
Receipt: `local/evidence/20261008-p04-current-main-11/summary.json`,
SHA-256 `e7fd34cd33ee278595944012f601d5d67990344320e004b791877b2f3679cafb`.

P03I/P09A static subset — **17/17 PASS**: request `202`, command `700`,
envelope `INT16, INT16, INT64, INT32, INT32`; TechTree handoff and visibility
matrix remain static-only with 374 trees, 3945 nodes, 2062 edges and
`IS-8 -> IS-7`. Receipt: `local/evidence/20261008-p03i-p09a-current-main-12/summary.json`,
SHA-256 `8202aeb6ff5ec78483f9d06409f288295ee4a2d6f4f1f01d6ee677f6a21cd0ae`.
Native payloads, callbacks, screenshots, queue/server handoff and runtime
eligibility remain `NOT_RUN`.

После этого status-only merge полный UTF-8 regression на проверенном head
`a23e602e74967d520a2e2ef9ee296a6e9da740c2` дал **2187 тестов, 0
failures/errors, 4 known skips**. Receipt:
`local/evidence/20261008-current-main-14/summary.json`, full log SHA-256
`8f9c7648f40a57edc348e02156c94245703c9bbba1c3eeb67a648ead265e454e`.

# Current-head goal recheck — 2026-10-08

На проверенном code head `283bf5f55c05514a2541bd84bca1feabf7aaab20`, который на
момент запуска совпадал с `origin/main`, повторён goal-specific набор:
**59 тестов, 0 failures/errors**.
Полный UTF-8 regression на том же head дал **2187 тестов, 0 failures/errors,
4 known skips**. Portable receipt:
`local/evidence/20261008-p04-p03i-goal-recheck-10/summary.json`.
Лог targeted SHA-256
`8479145bf727b7615e1d4058323e3bc1dd929f2c0b9c29a25dbb142084982eb7`;
полный лог SHA-256
`d65e0e57f9fd357d44a948e26ba0d0f5abdfe17d6c43db083b564c43e3cfd81f`.

В этом recheck P04 typed importer снова вернул
`PASS_TYPED_IMPORT_VALIDATOR` с canonical SHA-256
`a1b1191b29bbae5e2aed2f4417a139c7e9a2e6740ec40698347ad6baa8aac2b9`;
P03I static source predicate — `PASS_P03I_STATIC_SOURCE_RECHECK` с request
202/command 700 и envelope `INT16, INT16, INT64, INT32, INT32`; P09A static
graph — 374 trees, 3945 nodes, 2062 edges, `IS-8 -> IS-7`. Native payload,
callback bytes, queue/server handoff, account/shop payload and UI screenshot
остаются `NOT_RUN` и требуют owner-gated capture.

# P06E bounded client-collision static recheck — 2026-10-08

P06E теперь имеет `tools/p06e_client_collision_static_audit.py`: он hash-bind
ит принятые #717 `bytecode.json` и P06E summary, проверяет bounded JSON
duplicate/non-finite/depth/item/path guards и ровно **8/8** collision/flight
методов. Восьмой замер — `collideDynamicAndStatic`, связующий dynamic/static
segment path. Targeted `tests.test_p06e_client_collision_static_audit` —
**6/6 PASS**; receipt —
`local/evidence/20261008-p06e-static-audit-01/receipt.json` (ignored).
Это только `PASS_STATIC_CLIENT_COLLISION_BOUNDARY_RECHECK`: BSP2/трансформации,
penetration/damage, native server callback и client/server solver equivalence
остаются `UNKNOWN/NOT_RUN`. Клиент, gateway, server и deployed service не
запускались.

## P06B bounded MS-1 source recheck

P06B теперь имеет tracked `tools/p06b_source_audit.py`: он повторно хеширует
шесть #717 источников и пакет, декодирует четыре Packed XML набора, сверяет
девять collision payloads и обязательные границы отчёта. Targeted suite —
**12/12 PASS**; receipt
`local/evidence/20261008-p06b-ms1-ap-research-01/p06b-recheck-v2.json` имеет
SHA-256 `c245fa0e2e48bab904a530a9a6493879e8a7948720e093795b85d34bae3e0c96`.
Это статическая проверка источников: native hit, penetration, damage, callback
и P06C server handoff остаются `UNKNOWN/NOT_RUN`.

## P09B persistence/transaction boundary — isolated harness

P09B теперь имеет bounded stdlib-SQLite harness в
`tools/game_profile_tx.py`: server-owned `reserve_vehicle` делает snapshot,
vehicle-state и command-ledger запись одной `BEGIN IMMEDIATE` транзакцией.
Повтор того же command payload возвращает сохранённый результат; payload
mismatch, stale revision, unknown/already-reserved vehicle, повреждённый
snapshot и pre-commit failpoint закрываются без частичной записи. Это именно
изолированный контракт, без подключения к gateway, deployed service или
клиенту.

Status: **PASS_P09B_SQLITE_TRANSACTION_HARNESS / runtime integration NOT_RUN**.
Migration, battle lease release/consume, economy, concurrency, crash/restart и
native restart остаются **NOT_RUN**. Plan, research and evidence:
[P09B plan](plans/P09B_PERSISTENCE_TRANSACTION_BOUNDARY.md),
[P09B research](research/P09B_PERSISTENCE_TRANSACTION_BOUNDARY.md),
[P09B receipt](evidence-index/P09B.md).

## P10A training-room static boundary

P10A is accepted as `PASS_STATIC_TRAINING_ROOM_CONTRACT /
NATIVE_ROOM_LIFECYCLE_NOT_RUN`. The bounded `tools/training_room_static_audit.py`
rechecks 7 Account base methods, 5 Account client methods, 21 Prebattle base
methods and all nine documented source manifest entries. Its targeted suite is
6/6 PASS; receipt SHA-256 is
`38cba6df11e6e7caac872f69cf038197a7de56b6956ae5182172f41b28549d50`.
P00/P01 definitions establish only the typed vocabulary for
training/prebattle creation, invites, roster/team/player ready, arena-created
and teardown. Wire IDs/order, opaque roster semantics, races, room isolation,
native UI and battle admission remain `UNKNOWN/NOT_RUN`.

The next gate is one owner-captured private room followed by a second
simultaneous room, with raw Account bodies, callbacks, room IDs, roster
revisions and teardown correlation. Do not implement guessed room or
matchmaker routes before that capture.
# ACTIVE_GATE — 2026-10-08

## P08A bounded lifecycle static audit

P08A теперь имеет bounded read-only verifier
`tools/p08a_lifecycle_static_audit.py`: exact hashes/sizes для четырёх P00/P01
JSON, Account/Avatar/Arena/Vehicle typed method/property shapes, path
containment и duplicate/non-finite/depth/item guards. Targeted
`tests.test_p08a_lifecycle_static_audit` — **8/8 PASS**; receipt
`local/evidence/20261008-p08a-static-audit-01/receipt.json` (ignored).
Native lifecycle, wire framing, callback bytes, server handoff and deployed
runtime remain `NOT_RUN`; no client/gateway/service was started.

## P07A bounded visibility static audit

P07A is rechecked as `PASS_STATIC_VISIBILITY_SOURCE_AUDIT`. The bounded
read-only verifier asserts exactly eight declaration shapes against the pinned
P00/P01 `contracts.json`, validates the pinned `sources.json`, and matches all
six selected files in both permitted #717 copies. Targeted tests are **9/9
PASS**; receipt SHA-256 is
`8dd8bfab40f7b9a53cb2e28da8b4e8b38a09c1f06a632fc157d7801ba4d25c76`.
Duplicate/non-finite/depth/item/path and mutation cases are fail-closed. Wire
framing, serializer order, native LOS/occlusion, interest filtering and server
handoff stay **UNKNOWN/NOT_RUN**. No client, gateway or service was started.

## Latest P04/P03I/P06B/P06E/P07A/P08A/P09A/P10A current-main recheck

The latest UTF-8 full regression was run on code head
`d0674b6b38c4611ff962ecb3c17300bf17f7c20b`, matching `origin/main` at test
time: **2187 tests, 0 failures/errors, 4 known skips**. Log:
`local/evidence/20261008-p06b-p06e-current-main-01/full-python-utf8.txt`
(SHA-256
`80441128c571488ee874cbe63d6b2b8975d804a3d9e66d4ce061f51c21220b1f`).
`server/check_layout.py` remains `PASS_SERVER_SOURCE_LAYOUT` with 58 source
files and 22 relocations (receipt SHA
`4973971a5503f3fef21c18ba56c086ede47f8c03f1fbeafb5bbc06c7486857c2`). The
bounded docs-link recheck is `PASS_DOC_LINK_RECHECK` for 449 repository links,
0 missing targets and 105 skipped external/absolute links (receipt SHA
`cbbe9b1f1200039607f71c97ff223435f865a6c1cdc49d88e1c5d3ff791620d4`). The
combined recheck summary is
`local/evidence/20261008-p06b-p06e-current-main-01/summary.json` (SHA-256
`d2a2e3ed047f7666409a74b6f6c049aa3456f06aea56afa204170810850869c4`). The same summary records P04 **42/42 PASS**, P03I static **5/5 PASS**, P06B source **12/12 PASS**, P06E collision boundary **6/6 PASS**, P07A visibility **9/9 PASS**, P08A lifecycle **8/8 PASS**, P09A TechTree static **5/5 PASS**, P09A NationObjDumper/nested static **7/7 PASS**, P10A training-room static **6/6 PASS**, plus a combined targeted run **100/100 PASS**. The docs-link recheck is **449 links, 0 missing** (105 skipped external/absolute).

## Overnight verification

The latest UTF-8 full regression was run on code head
`4d9c5fb2e95c337d3972f02745f22641df8fd586` immediately before the following
status-only documentation merge; that head matched `origin/main` at test time.
It is **2125 tests, 0 failures/errors, 4 known skips**. Log:
`local/evidence/20261008-overnight-final-09/full-python-utf8.txt` (SHA-256
`c4f326c7a1f82b10cfd4770643d6bc47b5284d424387a80c20f2220844a1f87d`). Layout
is `PASS_SERVER_SOURCE_LAYOUT` with 58 source files and 22 relocations;
receipt `local/evidence/20261008-overnight-final-09/layout.json` (SHA-256
`4973971a5503f3fef21c18ba56c086ede47f8c03f1fbeafb5bbc06c7486857c2`). The
current diff from baseline contains documentation/evidence, bounded movement
matrix auditor/tests, static research-tree auditor/tests, and the isolated
SQLite transaction harness/tests. The latest documentation link recheck is
`PASS_DOC_LINK_RECHECK` for 434 repository links with no missing targets (105
external/absolute links skipped); receipt
`local/evidence/20261008-overnight-final-09/doc-links.json` has SHA-256
`2572ee6be18bbaae31abc194e9acf594b49dcd8a0927dd9f98fcd390679e6bfba`.

## P07A/P08A static source boundaries

P07A is accepted as `PASS_STATIC_VISIBILITY_SOURCE_BOUNDARY`: eight typed
`Avatar`/`Vehicle`/`Arena` declarations are hash-bound to the inspected P00/P01
contracts. Wire IDs, serialization order, LOS/interest filtering, concealment
timers and native replication remain `UNKNOWN/NOT_RUN`.

P08A is accepted as `PASS_STATIC_SOURCE_BOUNDARY_ONLY`: typed
`PlayerAccount`/`PlayerAvatar`/`ClientArena`/`Vehicle` lifecycle declarations
are recorded with their source flags. Wire envelope/order, native state machine,
HUD/audio/timer and ten-battle owner acceptance remain `UNKNOWN/NOT_RUN`.

These are source boundaries only. No runtime/client/service was changed. The
next gates are owner-driven fixed-occlusion visibility capture and bounded
native lifecycle capture; no guessed adapter or solver is permitted before
those receipts.

## P05 offline deterministic matrix

The pinned test-lab worker now has a two-map deterministic receipt:
`PASS_OFFLINE_DETERMINISTIC_MATRIX`, 160 commands and 161 events per map,
sequence `0 → 160`, tick `180 → 1140`, finite state and return code 0. See
[P05 research](research/P05_OFFLINE_DETERMINISTIC_MATRIX.md) and
[P05 evidence](evidence-index/P05.md).

This does not close native movement, historical physics, tank–tank or static
obstacle causality, prediction/correction, rejoin reconciliation or owner
acceptance. Worker engine/track/gear telemetry remains unknown. The next gate
is one bounded native movement/reconciliation capture using this offline
baseline; no controller tuning is justified by this receipt.

## P05 bounded movement-matrix receipt audit

`tools/movement_matrix_audit.py` accepts the existing aggregate/map receipts as
`PASS_OFFLINE_MATRIX_SHAPE_ONLY`, while reporting
`pose_validation=NOT_PRESENT_IN_AGGREGATE` and
`native_status=NOT_VERIFIED_BY_AUDITOR`. Its targeted suite is 14/14 PASS;
optional event traces receive strict finite-pose, sequence/tick and map-bound
validation. It does not establish native movement, server reconciliation,
collision causality or historical physics. See
[P05 matrix audit](research/P05_MATRIX_RECEIPT_AUDIT.md) and
[P05 audit evidence](evidence-index/P05_MATRIX_AUDIT.md).

## P09A preparation — native research-tree visibility

Docs-only branch `codex/p09a-research-tree-visibility` records
**PASS_P09A_PLAN_STATIC_PREDICATE_AND_HANDOFF_GATE**. The static/reference
catalogue remains complete (374 trees, 3945 nodes, 2062 edges; USSR I–X), and
the verified direction is **IS-8 → IS-7**, with IS-7 terminal. Pinned #717
bytecode establishes the native filter `NationTreeData.load` → `item.isHidden`
→ `shop.items.notInShopItems`; this explains why an owned reference can vanish
from the native tree without deleting it from the static graph.

This is a preparation gate only. Native account/shop payload, the
`requestNationTreeData`/`getNationTreeData` callback, screenshot correlation,
and a measured unowned control remain **NOT_RUN**. Selection-to-CMD700 and IS-7
battle admission stay outside P09A; the current IS-7 fixture is still
fail-closed because crew/ammunition are incomplete. Plan, research ledger and
receipt: [P09A plan](plans/P09A_RESEARCH_TREE_VISIBILITY.md),
[P09A research](research/P09A_RESEARCH_TREE_VISIBILITY.md),
[P09A receipt](evidence-index/P09A.md).

### P09A Phase A static fixture visibility matrix

The bounded fixture receipt
`local/evidence/20261008-p09a-visibility-matrix-01/receipt.json` is
`PASS_STATIC_FIXTURE_VISIBILITY_MATRIX`. It binds the complete static #717
graph to `r3-catalog3` and records MS-1 CD3329 plus IS-7 CD7169 from the
server-owned `state.bin` vehicle `inventory[1].compDescr`; both are present in
`itemPrices` and in `notInShopItems`. The fixture has no unowned reference
descriptor, recorded as `NOT_AVAILABLE_IN_FIXTURE`.

This remains a static fixture boundary. `expected_native_visibility` is
`UNKNOWN`, native payload/callback/screenshot are `NOT_RUN`, and runtime
eligibility remains `NOT_RUN`. The targeted verifier suite is 7/7 PASS with
negative controls for unknown IDs, duplicate hidden IDs, graph/catalog hash
mismatch, malformed literals and path escapes. The post-merge full regression
is 2125 tests with the same four known skips; evidence is the overnight-08 log
above. Do not infer native screen visibility or battle readiness from this
matrix.

### P09A static graph guard

`tools/research_tree_audit.py` now returns
`PASS_STATIC_RESEARCH_TREE_GRAPH` for the pinned #717 reference data: 374
trees, 3945 nodes, 2062 edges, USSR tiers I–X, an MS-1 tier-I root with five
tier-II outgoing vehicle edges, one IS-8 → IS-7 edge and no outgoing vehicle
edge from IS-7. This verifies the reference graph only; native
shop/tree payload, callback and visual handoff remain `NOT_RUN`. See the
[audit research](research/P09A_TREE_GRAPH_AUDIT.md) and
[audit receipt](evidence-index/P09A_TREE_GRAPH_AUDIT.md).

## Accepted P04 resource contract

Branch `codex/p04-content-import` delivered the typed `content-import.v1`
validator and bounded negative tests. The card is accepted as a resource-import
contract in merge `6d4d32e`; it does not change the accepted P03 runtime. The
historical isolated receipt has 33 tests with one known skip; the current
checkout recheck has 38 tests with zero failures/errors/skips. A follow-up
strict bundle-boundary recheck now has **42 tests, 0 failures/errors, 0 skips**
and rejects duplicate/non-finite JSON, boolean-as-integer fields and malformed
digest shapes; its receipt is
`local/evidence/20261008-p04-bundle-hardening-01/recheck.json`.
Full native/evidence suite, real #717 dataset, native compatibility and physics
remain `NOT_RUN`.
Evidence and receipt: [P04 index](evidence-index/P04.md).

## P05 preparation — offline only

The read-only geometry/movement audit on 2026-10-08 is recorded in
`local/evidence/20261008-p05-geometry-audit-01/`; the fresh bounded source/fault
matrix is in `local/evidence/20261008-p05-movement-matrix-01/`. Geometry,
map-drive and arena-movement source controls pass (26, 354 and 75 tests), and
the isolated test_lab PhysicsWorker build passes. Native collision equivalence,
historical physics, tank–tank, prediction/correction and owner movement
acceptance remain `NOT_RUN`.

The merged draft plan is
[P05 movement/reconciliation](plans/P05_MOVEMENT_COLLISION_RECONCILIATION.md)
(`dccfdabe`). The next narrow card is `P05A-pivot-diagnostics`; do not tune the
controller before a fixed MS-1 neutral/left/right trace identifies the failing
layer.

P05A's bounded offline harness is in merge `b8b1806`. Its targeted P05A/geometry
run is **33 tests OK with one known skip**. A fresh receipt-matched worker
recheck now passes all four scenarios on both imported maps:
`local/evidence/20261008-p05a-pivot-diagnostics-06/result.json` (Karelia,
SHA-256 `9915b226305eee1ef6f1f87c2838b91c5a4751ac1a4e58850c7106da4ada8d93`)
and `local/evidence/20261008-p05a-pivot-diagnostics-07-prohorovka/result.json`
(Prokhorovka, SHA-256
`c692507dacaf2cc5469f8e9c93fe2619ccce14f684fb2e39ce0582bf2d020e2c`). The
harness still exposes no engine/track telemetry. This is an offline worker
PASS only; native movement, reconciliation, historical physics and owner pivot
acceptance remain `NOT_RUN`.

## P06A preparation — ballistics boundary only

The docs-only MS-1 AP boundary is merged in `4535480` with plan and evidence
index `docs/plans/P06A_BALLISTICS_CONTRACT.md` and `docs/evidence-index/P06A.md`.
It pins shell `2570` and the already accepted P03H flight inputs, then keeps
surface intersection, penetration, armor, damage, modules/crew, RNG and native
hit/damage explicitly `UNKNOWN/NOT_RUN`. No solver, callback or runtime path
was added. The read-only #717 source check is now closed by P06B; the current
P06 gate is the owner-gated P06C two-MS-1 capture, followed by the P06D receipt
auditor.

## P06B source-field research — static closure, native hit still open

The read-only card `P06B_MS1_AP_SOURCE_SPIKE` was researched on branch
`codex/p06b-ms1-ap-research` at commit `8bd8dab` and merged into `main` as
`4143803`. The report pins exact SHA-256 values for the original #717 MS-1
descriptor, gun/shell/common vehicle definitions, the Russian vehicle package,
and the selected Hull/Turret_01/Gun_02 collision payloads. The static result is
**PASS_STATIC_SOURCE_FIELDS**: AP shell `_37mm_UBRT1`/compact `2570`, armor and
device damage fields `30`/`50`, literal `piercingPower="34 27"`, flight fields
`442`/`9.81`/`720`, common factor `0.8`, active MS-1 armor descriptors and
bounded mesh/material evidence are recorded in
[`P06B research`](research/P06B_MS1_AP_SOURCE_SPIKE.md).

The ignored receipt
`local/evidence/20261008-p06b-ms1-ap-research-01/summary.json` is
**PASS_STATIC_RECEIPT_RECHECK**. It verifies six source hashes, four Packed XML
re-decodes and nine collision-payload hashes without launching the client or a
physics/runtime process. The meaning/units of `34 27`, historical penetration
and damage semantics, BSP2 traversal, runtime transforms, server-owned hit,
HP/module/crew mutation, native callback and shot idempotency remain
**UNKNOWN / NOT_RUN**. Static descriptors and tracer presentation do not close
the hit gate.

The exact next gate is one controlled local two-MS-1 capture at a fixed pose:
fire shell `2570` at known `armor_1` and `armor_8` groups, then preserve the
server segment/intersection record (shot identity, triangle/group, material,
normal, thickness and terminal reason), before/after HP/module state, and a
same-identity replay check proving one ammo decrement and at most one terminal
damage token. Until a server-owned intersection and damage event are captured,
the solver remains unavailable and the result is **NOT_RUN**. Rollback is a
revert of merge `4143803`; no client/resource/runtime rollback is required.

## P06D bounded impact-receipt audit — shape only

The bounded auditor card `P06D_IMPACT_RECEIPT_AUDIT` is commit `2d1465c` on
branch `codex/p06d-impact-receipt-audit`, based on `83bba99`; its implementation
is present in main merge `10ab3ae`. `tools/impact_capture_audit.py` validates a
server-owned MS-1 AP receipt through admission, launch, segment, intersection,
classification, terminal, optional damage and replay. It rejects client
authority fields, non-finite values, duplicate keys, stage omissions, sequence
rollback and side-effecting identity conflicts within bounded JSON limits.

The targeted suite is **11 tests, 0 failures**. The explicit UTF-8 full main
regression is **2083 tests, 0 failures/errors, 4 skips**; log SHA-256 is
`86cdbbff98bc655b4478f1666125963ed8430f8942d549183664db178eb3a471`.
A deliberate incomplete receipt returned
**NOT_RUN_INCOMPLETE_CAPTURE** with `missing required stage: launch`.

`PASS_CAPTURE_SHAPE_ONLY` means only that a synthetic complete fixture satisfies
the receipt shape and authority boundary. It does not prove a native hit,
penetration, damage formula, HP/module/crew mutation or client callback;
`native_impact_status=NOT_VERIFIED_BY_AUDITOR` remains explicit. Native
intersection and solver status stay **UNKNOWN / NOT_RUN**. See [P06D research](research/P06D_IMPACT_RECEIPT_AUDIT.md)
and [P06D evidence](evidence-index/P06D.md).

The exact next gate is owner-gated P06C: run the controlled two-MS-1 local
capture and feed a real server-owned receipt to this auditor, then correlate
intersection/material/normal/thickness/terminal, HP/module state, replay
identity and native evidence. Keep P06 hit/damage unavailable until that
correlation succeeds. Rollback for the implementation is a revert of `2d1465c`;
the status-only update is independently reversible.

## P06E client collision source boundary — static only

The read-only `P06E_CLIENT_COLLISION_SOURCE_RESEARCH` card is commit `ed193d8`
on branch `codex/p06e-client-collision-research`, merged into `main` as
`37c2a0e`. Its static result is
**PASS_STATIC_CLIENT_COLLISION_BOUNDARY**. The pinned #717 bytecode receipt SHA
is `502581a94b4be46d4db885e5922038287b38ff155138cc37ebc24e2216ce7625`; the
bounded extracted summary SHA is
`61ddf923d1b276176fe8b346590228cd00ab51acefc5f1bce94eb968ec364839`.
Summary path: `local/evidence/20261008-p06e-client-collision-research-01/summary.json`.

The client `_readShell` loader reads `damage/armor` and `damage/devices` and
observes defaults `damageRandomization=.25` and
`piercingPowerRandomization=.25`. `_readShot` reads `piercingPower` as a
`Vector2`, reads speed/gravity/max distance, and applies
`projectileSpeedFactor`. Vehicle descriptors expose chassis/hull/turret/gun hit
testers. Dynamic `collideSegment(start,end,skipGun)` and static
`BigWorld.wg_collideSegment(...)` select the nearest client candidate. The
projectile callback only calls
`onProjectileHit(hitPosition, caliber, isOwnShot)`.

These observations are client-side source boundaries. They do not establish
server ownership, BSP2/runtime transforms, penetration or damage semantics,
HP/module/crew mutation, native server callback or solver equivalence;
authoritative server hit/damage remains **NOT_RUN / UNKNOWN**. The callback has
no server target, armor layer, HP delta or shot-ledger token. See [P06E research](research/P06E_CLIENT_COLLISION_SOURCE_RESEARCH.md)
and [P06E evidence](evidence-index/P06E.md).

The exact next gate remains owner-gated P06C: run the controlled two-MS-1
capture, feed the real server-owned rows to the P06D auditor, and correlate
intersection/material/normal/thickness/terminal, HP/module state, replay
identity and native evidence. Keep P06 hit/damage unavailable until that
correlation succeeds.

## P03I docs-only native vehicle/loadout boundary

Docs commit `81dfb93` is merged into `main` as `2f43054`; the status-only
follow-up is on branch `codex/p03i-status-docs`. The card is
**PASS_DOCS_ONLY_STATIC_BOUNDARY / NATIVE_HANDOFF_NOT_RUN**. It changes no
runtime, `server/gateway`, `client_patch`, fixture, original/research client or
deployed service.

The static tree predicate is `NationTreeData.load` → skip `None` and
`item.isHidden`, with hidden items derived from
`shop.items.notInShopItems`; the reference graph remains complete and records
**IS-8 → IS-7**. Native shop/account payload, research-window callbacks and
owner visual correlation remain **NOT_RUN**.

The static queue contract pins request `202`, command `700`, selected
`g_currentVehicle.invID` as `INT64`, and two `INT32` values for
`gameplaysMask` and `arenaTypeID`; `Account.def` gives
`INT16, INT16, INT64, INT32, INT32`. Static callback semantics are
`onEnqueued(queueType)` → `events.onEnqueuedRandom()` and
`onEnqueueFailure(UINT8, UINT8, STRING)` →
`events.onEnqueueRandomFailure(...)`. Live bytes, ordering and server handoff
are **NOT_RUN**.

The exact next owner gate is one ordinary MS-1 random-battle click preserving
the process manifest, decrypted Account body, `202/700`, both `INT16`, selected
`INT64` vehicle ID, both `INT32` mask/arena values, callback arguments/order,
queue event and server identity correlation. IS-7 remains fail-closed until a
hash-pinned assigned crew and server-owned shell stack exist; current
`crew_assigned=false`, ammo `0` must not mutate fixtures. Missing framing or a
callback is **NOT_RUN**, never a guessed decoder. See [P03I plan](plans/P03I_VEHICLE_PROFILE_LOADOUT.md),
[research](research/P03I_VEHICLE_PROFILE_LOADOUT.md) and
[evidence index](evidence-index/P03I.md).

### P03I static source-hash recheck

The bounded read-only `tools/p03i_static_audit.py` receipt
`local/evidence/20261008-p03i-static-audit-01/receipt.json` is
`PASS_P03I_STATIC_SOURCE_RECHECK` (5/5 targeted tests). It confirms both
permitted #717 copies, the tree predicate, Account.def request 202/command
700 shape and the capture-audit source hashes. It records one stale hash row
in the ignored queue README for `functions.pyc` (`…d46e0f2…` versus verified
`…d46f0e2…`). Native CMD700 bytes, callback ordering and server handoff remain
`NOT_RUN`; this recheck changes no runtime or evidence source.

### P03I bounded native MS-1 queue smoke

The 2026-10-08 owner run is recorded as
**PASS_NATIVE_MAP_DRIVE_QUEUE_SMOKE / PASS_SERVER_SIDE_BATTLE_ENTRY** in
`local/evidence/20261008-p03i-native-ms1-queue-01/native-gate-audit.json`.
The gateway accepted request `202` / command `700`, created the map-drive
avatar and vehicle, bound the client and delivered input; the runtime trace
correlates selected native inventory `1` with `BattleQueue` and avatar/world
entry. The client exited cleanly and the isolated overlay restored.

This is a bounded compatibility smoke, not the strict P03I native handoff:
live Account framing, gameplay/arena values and native queue callback
arguments remain **NOT_RUN** because the route logs a compatibility
`map_request=0` rather than independently decoding the original body. The
next gate is a raw-frame/callback capture; IS-7 admission still waits for
server-owned crew and shell data.

## Latest accepted card

`P03H_NATIVE_PROJECTILE_FLIGHT_20261007`:
**PASS_OWNER_P03H_SAME_PC_SERVER_PROJECTILE_NATIVE_TRACER / ACCEPTED**.
Branch `codex/p03h-native-projectile-flight`. The server now owns each accepted
MS-1 projectile's launch geometry and bounded 720m flight lifetime, and both
real same-PC clients receive the original native tracer start/stop callbacks.
The owner confirmed that both windows saw the tracer. Canonical/legacy Rust
tests **373/371 PASS**; Python **2055 tests, 0 failures/errors, 2 known skips**; native lifecycle and
transport audit are clean. Evidence: [P03H receipt](evidence-index/P03H.md),
`local/evidence/20261007-p03h-native-projectile-flight-01/owner-acceptance.json`.

This card remains a bounded MS-1 test_lab result. IS-7/loadout, crew,
equipment, collision, hit, damage, historical dispersion/physics and the
independent two-PC/LAN repeat are still open. Next: a versioned
`VehicleProfile/Loadout` card for real vehicle and shell selection.

## Current phase

Branch policy: one card per `codex/<card-id>-<purpose>` branch; merge an accepted
card into `main` with `--no-ff`, then verify the remote SHA. See
[owner-approved workflow](07_CODEX_WORKFLOW.md).

`P03G_SHARED_GUN_AIM_20261007`:
**PASS_OWNER_P03G_SAME_PC_DYNAMIC_AIM_AND_SHOT_REGRESSION / ACCEPTED**.
Branch `codex/p03g-shared-gun-aim`, base `8709b07151cdf4c8238ae918044e1b34855bfb6d`.
Native target input, server-owned rate/limit integration, per-entity property
delivery and original client rotator initialization are implemented. Both real
clients received native callbacks; independent native math samples constrain
the approximate test_lab solver. Canonical/legacy tests **363/361 PASS**;
Python **2054, 0 errors/failures, 2 skips**; layout **57/22 PASS**.
Owner reported “вроде все по этим тестам корректно” after the instructed check.
Both native traces contain changing yaw/pitch; 9126/9118 original property
completions match the wire prefix exactly. Six shots (five A, one B), six native
shot handler completions on each peer; 28492 packets audited with zero errors.
Repeat firing is recorded on A; two own shots from each peer were not recorded.
The same-PC card is **ACCEPTED**. Owner receipt and final merge/remote SHAs:
`local/evidence/20261007-p03g-shared-gun-aim-01/owner-acceptance.json` and
`accepted-handoff.json`. See
[current P03G receipt](evidence-index/P03G.md) and
[research/limits](research/P03G_SHARED_GUN_AIM.md).
Full P03 and the separate two-PC requirement remain open. Next: a separate
server-owned projectile-flight/native-tracer card.

## Accepted previous card and historical P03F receipt

`P03F_TWO_CLIENT_WORLD_20261007`:
**PASS_OWNER_P03F_SAME_PC_WORLD_SHOT_SOUND_NEUTRAL_POSE**.
Two real native processes share the world; abrupt closure/re-authentication
preserved the other session and returning ammunition. The owner confirmed
synchronized movement and visible remote shooting after build07's shot cue.
The zero packed-angle seed was then corrected on build08; both native clients
received neutral angles and the owner confirmed “Башня и ствол нормально, звук
есть”. The scoped same-PC card is **ACCEPTED**. Source branch:
`codex/p03f-two-client-world`; exact commit/merge/remote state is in its final
local handoff receipt. Evidence: [accepted P03F receipt](evidence-index/P03F_GUN_POSE.md).

This explicit local lab uses two temporary allied MS-1s and bounded flat
kinematics. It does not grant garage inventory or replace the deployed service.
Original/research/deployed EXE guards match their pre-card hashes. Native PNGs
show own/ally vehicles, floating geometry and a colored grid artifact; this is
not physics or final rendering acceptance. Warm Leave-to-hangar is unavailable
in the lab; full process close/re-authentication is the observed exit path.

Previous `ORG-0B_TEST_REPAIR_20261007`: **PASS_TEST_REPAIR**, 2047 Python tests
with 2 documented skips; separate Python 2.7 check PASS. Historical receipt:
[ORG-0B](evidence-index/ORG-0B.md). P03F's latest full Python count is 2053.

The battle phase is **P03 — IN_PROGRESS**. Same-PC P03F acceptance does not close
the separate two-PC repeat or imply full authoritative combat acceptance.

ORG-0A local organizational gate: **PASS**; remote publication:
**PASS_REMOTE_VERIFIED** after the owner ran the four delivery commands.
Independent `ls-remote` verification matched main `0b7b8ac6f9ef4a955840df7e690a6e73640dd16f`,
tag object `0b0fa2f54abd5f14ec39147b034a70757bd5227a` and baseline target
`7d2a600b7e65ecd7568cb5a985af941313dffb60`. Earlier HTTP 408/TLS errors remain history.
The follow-up documentation delivery is recorded separately in the machine receipt. Exact attempts and SHAs:
[ORG-0A receipt](evidence-index/ORG-0A.md).

## Accepted P03 subcards

| Subcard | Status | Verified evidence | Remaining boundary |
|---|---|---|---|
| P03D native ammunition HUD panel | `PASS_OWNER_NATIVE_AMMO_PANEL_HUD` | `local/evidence/20261007-battle-ammo-panel-01/owner-test/owner-panel-acceptance-01.json`; owner screenshot SHA256 `8a0777a437d78d73dd58dec3566f645759b1a68211205ba95448c64225f55c64` | Input profile contains no equipment/consumables; equipment message and zero-count selection are not accepted |
| P03E native fire/reload/consumption | `PASS_OWNER_NATIVE_FIRE_RELOAD_CONSUMPTION` | `local/evidence/20261007-battle-fire-reload-01/owner-test/owner-acceptance-fire-reload-03.json`; 5 owner shots, AP `20 -> 15`, 5 completion callbacks | Projectile, hit, damage, visibility, physics, equipment and persistence remain outside this subcard |
| P03F shared native same-PC laboratory | `PASS_OWNER_P03F_SAME_PC_WORLD_SHOT_SOUND_NEUTRAL_POSE` | `local/evidence/20261007-p03f-two-client-world-01/aim-01/owner-acceptance.json`; native movement/rejoin, remote shots/sound and neutral initial pose | Dynamic aiming, two-PC/LAN and the other explicitly listed lab limitations remain open |
| P03G continuous turret/gun aim | `PASS_OWNER_P03G_SAME_PC_DYNAMIC_AIM_AND_SHOT_REGRESSION` | `local/evidence/20261007-p03g-shared-gun-aim-01/owner-acceptance.json`; 457 snapshots per native process, changing angles and six shared shots | Same-PC test_lab only; repeat own shots recorded on A, one own shot on B; two-PC/LAN, historical fidelity and projectile/hit/damage remain open |
| P03H server-owned projectile flight/native tracer | `PASS_OWNER_P03H_SAME_PC_SERVER_PROJECTILE_NATIVE_TRACER` | `local/evidence/20261007-p03h-native-projectile-flight-01/owner-acceptance.json`; 28,410 audited packets, 38 starts/stops, native mover lifecycle on both clients, owner confirmed both windows see tracer | MS-1 test_lab only; IS-7/loadout, crew/equipment, collision, hit/damage, historical physics and two-PC/LAN remain open |

The owner fire/reload gate is therefore **closed**. Earlier build07/build08
`NOT_RUN` or route-ready text is retained as historical evidence; it does not
override the later build09 owner receipt.

## Full P03 gate

`IN_PROGRESS`. P03F's same-PC evidence now includes:

- two independently authenticated native processes in battle `2448793866150762938`;
- different Avatar/vehicle IDs and own/ally visual distinction in native PNGs;
- changed server X/Z positions received in both native entity traces;
- independent AP counts and five owned reload completion callbacks;
- abrupt A closure, continuous B session, A rejoin with the same vehicle/AP18.

Owner confirmed movement. Build07 adds 14 accepted shots / 28 native original
handler completions and owner-visible remote shooting. Build08's neutral initial
turret/gun pose and remote sound are now owner-confirmed. The separate two-PC
repeat remains NOT_RUN. Dynamic aiming was subsequently accepted by P03G above.
Same-PC observations do not claim LAN/public deployment compatibility.

Projectile/hit/damage, visibility, equipment and the full battle lifecycle are
separate later roadmap gates (P06/P07/P08); their NOT_RUN status is not
silently turned into the P03 two-client acceptance criterion.

P03F runs two native clients; projectile/hit/damage remains outside this card.

## Dependencies and pinned inputs

- Client: two independent manifested copies `local/clients/p03f/a` and `b` from
  pinned original #717. Only fixed instance-name strings change in each EXE;
  separate profiles and owned compatibility overlays. Original and prior
  `WoT_0.9.1_RU_0717_research` stay outside Git and untouched by this card.
- Client EXE SHA256 (both copies checked read-only by ORG-0A):
  `86f5e351d44c12e0d2b89ed741ee9a4e70d21f234c39aa9cfd709536d49f04ed`.
- Static method table SHA256:
  `f63fab8f43d204d4a6fc9d819b21321ca46558e23108370d1c2b878fb4072429`.
- Client Avatar static input SHA256:
  `7531aa5ad00add000ae8b5465de88907a27285628347234d5c53d230bde7a13b`.
- Content catalog `web/data/catalog.v1.json` SHA256:
  `d66aad60c13d83807f49b1ebfc8cc89f330e658ed3223706169f763052547567`.
- Canonical P03E isolated EXE SHA256:
  `460d5d68dd47b6599085d2775c316d4e1192a2d53c45f87aaabf86d9341e7970`.
- Legacy P03E isolated EXE SHA256:
  `558a6b72a65e980395e146a48570e1ef1cec2b7accfcbe2c1cdb2a8e832e114a`.
- Deployed gateway guard SHA256 (unchanged):
  `daef0dde9e012beac4e0f363bf66b672ec4a154473be4b05b00cfe4cc0608c3b`.
- P03F canonical build08:
  `60d1209523d15b5fcb2aa62d4ce518925212c3c92e48951a3e1e66b8bf03dd66`.
- P03F legacy build04:
  `3bb3d4e0f36385386e0c75ced4d90bc7e0ec069b3340c93a97c419e2c2cef7ae`.
- Per-copy EXE/trace/screenshot hashes: [P03F receipt](evidence-index/P03F.md)
  and its local `result.json`.
- ORG-0A historical baseline commit (tag `baseline-2026-10-07`): `7d2a600b7e65ecd7568cb5a985af941313dffb60`.

## Checks for previous accepted P03F card

| Check | Result | Evidence |
|---|---|---|
| Canonical/legacy final builds | PASS, 353 / 351 tests | `local/build/server/gateway-shared-world-08/` and `gateway-shared-world-legacy-04/` |
| `python -B -X utf8 server/check_layout.py` | PASS, 56 source files, 22 relocations | P03F `layout-01.json`, repeat before handoff |
| Latest Python suite | 2053 run, 0 errors/failures, 2 skips | P03F `unittest-05.txt` / `.json` |
| Pinned Python 2.7.3 client compilation | PASS | P03F A/B install05 preparation receipts |
| Current native packet prefix | PASS, 3669 packets, 0 crypto/transport/callback errors | P03F `capture-audit-05.json` |
| Shared movement and remote shooting/sound | PASS_OWNER | `aim-01/owner-acceptance.json`, earlier owner receipts |
| Initial neutral turret/gun fix | PASS_NATIVE_AND_OWNER | `aim-01/result.json`, owner receipt and PNGs |
| Windows symlink / Python-2.7-only unittest under Python 3 | SKIPPED with explicit reasons | Final Python log; not converted to PASS |
| Two-PC repeat | NOT_RUN | Local-only mode |

## Rollback for previous accepted P03F card

Stop only this card's current launch-receipt image paths. Restore A/B overlays
using `tools/interactive_client.py rollback --out <install-a-05 or install-b-05>`
after the corresponding process stops; optional instance-string rollback uses
each stopped isolated copy's hash-verified EXE backup. Full paths and commands:
[P03F receipt](evidence-index/P03F_GUN_POSE.md). Source rollback uses a reviewed revert
of the accepted card/merge. Preserve original/research clients, all local
evidence, prior receipts and deployed services. No reset or force-push.

## Single next step

A separate card for server-owned projectile flight and native tracer display
on both clients. P03G aiming is accepted; the two-PC requirement remains open.

## P09A static TechTree handoff

`tools/techtree_handoff_audit.py` подтверждает hash-bound static method shape
`requestNationTreeData` и `getNationTreeData` из #717 TechTree.pyc:
available/selected nation fields, unknown-nation guard, index selection,
`NationTreeData.load` и `dump`. Receipt:
`local/evidence/20261008-p09a-techtree-static-01/receipt.json`,
`PASS_STATIC_TECHTREE_HANDOFF_SOURCE`.

Это только source boundary: account/shop payload, callback bytes, screenshot и
server handoff остаются `NOT_RUN`; native client/service не запускались. См.
[P09A static handoff evidence](evidence-index/P09A_TECHTREE_HANDOFF_STATIC.md).

`tools/nation_dumper_static_audit.py` дополнительно фиксирует envelope `nodes`, `displaySettings`, `scrollIndex` и 13 полей node output; receipt `local/evidence/20261008-p09a-nation-dumper-static-01/receipt.json` имеет статус `PASS_STATIC_NATION_DUMPER_OUTPUT`. Follow-up receipt `local/evidence/20261008-p09a-nested-shapes-01/receipt.json` фиксирует measured XML access/format shape для `displayInfo`/`unlockProps`; конкретные Python value types, native callback и serializer остаются `UNKNOWN/NOT_RUN`.
