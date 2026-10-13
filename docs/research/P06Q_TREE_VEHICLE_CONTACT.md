# P06Q — original trees, vehicle contact, and cumulative scene state

Card branch: `codex/p06q-tree-vehicle-contact`
Base: accepted P06P `52978a25c63d51a56be90054c449b281cc4d3e3d`
Evidence root: `local/evidence/20261012-p06q-tree-contact-01/`

## Goal and result

The card extends the accepted Prohorovka cumulative runtime with a bounded,
server-authoritative contact path. The source-pinned importer now admits the
original tree collision spans together with the nine previously supported
fragile objects. A contact-capable catalog is versioned separately from the
legacy catalog. The private physics worker reports bounded hull and wheel
contact candidates; the gateway accepts only validated hull candidates for a
test_lab mutation policy. A contact carries the worker's hash-bound mass, and
the authoritative ram gate uses `E = 0.5 × mass × closing_speed²`: a light tap
is recorded as a candidate but does not remove the object. A fragile ram removes
the object with `isShotDamage` false once the explicit energy floor is crossed.
A tree stores the original `fallenTrees` packed `UINT32` value and removes its
collision body only after every participating worker acknowledges the
cumulative scene. The prepared passive native probe now completes on both
owned Prohorovka clients: two stable passes over all 117 chunks per slot,
with identical v2 exports. This proves the native catalog mapping; it does
not perform destruction. Owner-controlled ramming, tree fall, rendered
passage, and acceptance remain open.

## Evidence classification

- **VERIFIED:** the pinned Prohorovka source inventory contains 626 eligible
  SpeedTree instances in 116 tree chunks plus nine legacy fragile instances in
  one additional chunk: 635 catalog rows across 117 target chunks. Every
  admitted tree has projectile span zero, a non-empty physics span, source
  material 71, and a checked `.spt` resource. The saved inventory reproduces
  byte-for-byte on a second import.
- **VERIFIED:** historical isolated build final-12 passed 614 Rust tests, including catalog
  parser limits, tree/fragile type rules, contact validation, immutable fall
  packing, trace replay, scene exclusion, worker ACK transactions, restore,
  legacy regression coverage, an atomic vehicle-contact batch regression, and
  a mass/closing-speed ramming regression. The later gateway-recheck02 has
  610 PASS / 4 FAIL from absent historical worker fixtures (see below).
- **VERIFIED:** the isolated .NET physics worker builds with the contact IPC
  implementation. It bounds raw contacts, distinct object IDs, line size,
  normal/point/velocity values, and rejects unknown body identity or overflow.
- **VERIFIED:** in fresh run `treecontact02`, clients `a` and `b` each emitted
  two stable native observations for all 117 Prohorovka chunks. Both files are
  1,241,592 bytes with SHA256
  `dfff68fbecfb754c4a87a7095198dc6dbabd99308061c34b8d723534bc9f9c48`, and
  each contains 3627 native items. Independent validation against the pinned
  inventory and spec succeeded; the joined catalog contains 635 source
  objects. Stop and rollback receipts are clean.
- **OBSERVED:** the implementation is internally consistent on the pinned
  synthetic worker fixtures and existing private worker IPC tests.
- **OBSERVED:** while the original clients were loading, their native manager
  and player space IDs were temporarily different. The observer waited for a
  stable loaded state; both final exports passed all source, transform, chunk,
  and item checks. This transient loading state is not treated as a mapping
  failure.
- **INFERRED:** the selected `test_lab` thresholds (minimum speed 1 m/s,
  closing speed 0.1 m/s, mass range 1000–100000 kg, and 8 kJ energy floor)
  are explicit project policy, not historical 0.9.1 damage rules.
- **UNKNOWN:** the historical 0.9.1 kinetic damage formula, collision callback
  ordering in the original client, and whether every source tree uses the same
  fall animation constraints.

## Changed files

- `tools/tree_contact_catalog.py` — source-pinned tree/fragile inventory and
  contact-capable catalog output.
- `tests/test_tree_contact_catalog.py` — 117-chunk, source, schema, and
  fail-closed native-export tests.
- `client_patch/destructible_catalog_probe.py` — retained v1 probe and added
  the bounded v2 tree-contact probe specification.
- `server/gateway/src/drive/worker.rs` and
  `server/gateway/src/drive/worker/catalog.rs` — bounded JSON/catalog v3,
  IPC v4, object-contact decoding, hash-bound mass, scene limits, and legacy
  preservation.
- `server/gateway/src/shared/fragiles.rs` and `fragiles_tests.rs` — typed
  tree/fragile catalog, u32 contact health, hull/wheel policy, fall packing,
  and replayable state transitions.
- `server/gateway/src/shared/impact.rs` — separate `VehicleContact` trace
  event/stage, replay, ordering, scene and exclusion accounting, and contact
  event budget.
- `server/gateway/src/shared/fragiles.rs` — candidate-world contact policy,
  mass/closing-speed energy floor, and contact event mass binding.
- `server/gateway/src/shared/model.rs` — candidate-world contact application
  and atomic server state integration. Contact batches stage both fragile state
  and impact trace state, so a malformed later row cannot leave an earlier row
  committed; the regression test covers that rollback boundary.
- `server/gateway/src/shared/server.rs` — worker contact collection, catalog
  kind/profile binding, server-pinned mass propagation,
  ACK-gated scene commit, and cumulative publication.
- `server/gateway/src/shared/mod.rs` and
  `server/gateway/src/shared/destructible_wire.rs` — per-area fallen-tree
  state and the original `ARRAY<UINT32>` property wire.
- `server/gateway/src/shared/server_catalog_tests.rs` — contact-capable
  catalog fixture updates.
- `server/physics/CheckedInput.cs`, `Program.cs`, and `README.md` — checked
  contact catalog loading, Jolt hull/wheel capture, IPC v4, and documented
  bounds.
- `client_patch/sr_interactive.py` — passive observer keeps the native catalog
  alive when this 0.9.1 client lacks `gunRotator`; no synthetic pose is used.
- `docs/plans/P06Q_TREE_VEHICLE_CONTACT.md` — card plan.

## Commands and real checks

```text
python -B -X utf8 -m unittest tests.test_destructible_catalog tests.test_destructible_catalog_probe tests.test_tree_contact_catalog -v
python -B -X utf8 server/build.py gateway --test --out local/build/server/gateway-p06q-final-12
python -B -X utf8 server/build.py physics --out local/build/server/physics-p06q-final-02
python -B -X utf8 local/evidence/20261012-p06p-prohorovka-01/test_stand_helpers.py
python -B -X utf8 -m py_compile local/evidence/20261012-p06p-prohorovka-01/start_stand.py
python -B -X utf8 local/evidence/20261012-p06p-prohorovka-01/start_stand.py server --run contactprep09 --mode runtime --map 05_prohorovka --build gateway-p06q-final-12 --build-sha256 418818d1012e0a25c4d8594d5bdb86f05beb8ed351b6300c492c8a70017fac22 --build-result-sha256 b886ddb62cc39a72229f33f8ba2f6b980d231dc6b7fbe523727fb3a739eb7189 --expected-head 1772d767ebd61af2c1da3e20e1ff5dc89c0aa650 --pool local/build/server/physics-p06q-final-02/pool-near.json --pool-sha256 59b88e5c2d2b1f9689c3b302275915cf2b9aed65290a8e1827c2d2eb596b5288 --destructible-catalog local/evidence/20261012-p06q-tree-contact-01/import/native-join01/manifest.json 59a51da7613e17ae4150471053b1ad9856a4acbd74d493aee1cc16f04ebcdb7f --dry-run
git diff --check
Get-Process -Name WorldOfTanks,sr-gateway,MapDriveWorker,PhysicsSpike
python -B -X utf8 local/evidence/20261012-p06p-prohorovka-01/prepare_stand.py --slot a --run treecontact02 --mode oracle --map 05_prohorovka --catalog-spec local/evidence/20261012-p06q-tree-contact-01/import/inventory01/probe-spec.json --catalog-spec-sha256 5a1940b7e975445422e7b10898757ba88877f7a2c92e120760fceccb6f78eacd
python -B -X utf8 local/evidence/20261012-p06p-prohorovka-01/prepare_stand.py --slot b --run treecontact02 --mode oracle --map 05_prohorovka --catalog-spec local/evidence/20261012-p06q-tree-contact-01/import/inventory01/probe-spec.json --catalog-spec-sha256 5a1940b7e975445422e7b10898757ba88877f7a2c92e120760fceccb6f78eacd
python -B -X utf8 local/evidence/20261012-p06p-prohorovka-01/start_stand.py server --run treecontact02 --mode oracle --map 05_prohorovka --build gateway-p06q-final-05 --build-sha256 1615648a13bb4ab745b992ec0ba576ea2e507657f485c0c14420e46f4313aeba --build-result-sha256 2b00050d3f35d9ceb6c26e8b14a28cb3512cf64c79174578ec9f3cade2c766e0 --expected-head 4ee631ff02d640c45191604a80bd7fedc5df7cf5 --pool local/build/server/physics-p06q-final-02/pool-near.json --pool-sha256 59b88e5c2d2b1f9689c3b302275915cf2b9aed65290a8e1827c2d2eb596b5288
python -B -X utf8 local/evidence/20261012-p06p-prohorovka-01/stop_stand.py --receipt-dir local/evidence/20261012-p06p-prohorovka-01 --run treecontact02 --out-name treecontact02stop --reason "P06Q passive native probe complete: both clients stable 117-chunk two-pass exports"
python -B -X utf8 tools/interactive_client.py rollback --out local/evidence/20261012-p06p-prohorovka-01/install-a-treecontact02
python -B -X utf8 tools/interactive_client.py rollback --out local/evidence/20261012-p06p-prohorovka-01/install-b-treecontact02
python -B -X utf8 -c "validate both raw exports with tools.tree_contact_catalog.validate_native and join one canonical byte-identical export with tools.tree_contact_catalog.join_exports"
```

Results:

- Python: 39 tests, **PASS**. The final log is
  `local/evidence/20261012-p06q-tree-contact-01/tests/importer-tests-final.log`.
- Gateway: 614 tests, **PASS_ISOLATED_BUILD** on the atomic contact and
  mass/closing-speed ramming policy. Canonical final-12 receipt:
  `local/build/server/gateway-p06q-final-12/result.json`; receipt SHA256
  `b886ddb62cc39a72229f33f8ba2f6b980d231dc6b7fbe523727fb3a739eb7189`,
  executable SHA256
  `418818d1012e0a25c4d8594d5bdb86f05beb8ed351b6300c492c8a70017fac22`.
  The intermediate atomic-only receipt remains
  `local/build/server/gateway-p06q-contact-atomic-01/result.json`.
- Helper guards: 12 tests, **PASS**. The runtime command accepts the joined
  P06Q v2 manifest envelope (240 KiB) while retaining the 128 KiB ceiling for
  legacy v1 catalogs; an unbound v2 catalog is rejected.
- Runtime preflight `contactprep09`: **PREFLIGHT_ONLY_NOT_STARTED**. The
  joined v2 manifest, Prohorovka pool, final-12 executable and source HEAD all
  passed their pins; no gateway, worker, or client process started. Receipt:
  `local/evidence/20261012-p06q-tree-contact-01/tests/runtime-preflight-contactprep09.json`
  (SHA256 `4f90edd84d92d136d452cc085f52f31c3e8d587abd5d178f144697f2e7af9028`).
- Physics: **PASS_ISOLATED_BUILD**. Receipt:
  `local/build/server/physics-p06q-final-02/result.json`; DLL SHA256
  `74513499fcb0b88b78abc53be88d1111e9fa4a83d120f2f0249e1d9fdad692de`.
- `git diff --check`: **PASS**.
- The process snapshot was empty after the checks. No original client or
  server process was left running.
- The private worker contact smoke was attempted against the pinned near-spawn
  tree but is **NOT_RUN/PENDING** as an acceptance result: the test-lab vehicle
  settles against the imported static mesh before a catalog body callback is
  emitted. This does not establish native contact or tree destruction and is
  retained as a diagnostic only.
- A bounded spawn sweep repeated that diagnostic at six X/Z starts around the
  measured `BirchFall_1` target. Starts at Z=`459..461` all settled near
  Z=`461.1` with no catalog contact; starts at Z=`462..463.5` ended before a
  ready row because they entered the collision envelope. Receipt:
  `local/evidence/20261012-p06q-tree-contact-01/tests/contact-spawn-sweep01.json`
  (SHA256 `5040394aeb7912c03ed9eaccabae167c0033c7dae2ec99b7fd6eafc7e9da14e3`;
  diagnostic only). This narrows the private smoke failure to the imported
  static-mesh/starting-envelope interaction; it does not change the native
  owner gate or claim a destruction result.
- Fresh gateway recheck `gateway-recheck02` used the pinned local Rust
  toolchain and produced 610/614 passing tests. Four historical real-worker
  tests fail before startup because the P06O/P06N pool fixtures are absent
  (`local/build/server/physics-integrated-p06o-01/pool-near.json` and
  `local/build/server/physics-integrated-p06n-01/pool-near.json`). Receipt:
  `local/evidence/20261012-p06q-tree-contact-01/tests/gateway-recheck02-strict.json`
  (SHA256 `c5e7dcd1e407758e8381b7fd0d338ad10238db73bc76ad862dfbe7a16a8ea923`).
  This is an environment fixture gap, not a P06Q source-regression claim.
- Native run: both slots passed two observations × 117 chunks × 3627 items;
  raw files are under the P06P helper evidence root, and the validated join is
  `local/evidence/20261012-p06q-tree-contact-01/import/native-join01/`.
- Stop receipt: `local/evidence/20261012-p06p-prohorovka-01/stop-treecontact02stop.json`;
  rollback receipts: `install-a-treecontact02/restore.json` and
  `install-b-treecontact02/restore.json`.
- Runtime preflight receipts are retained under
  `local/evidence/20261012-p06q-tree-contact-01/tests/`.

## Evidence paths

- Imported inventory:
  `local/evidence/20261012-p06q-tree-contact-01/import/inventory01/inventory.json`
  SHA256 `d3aae3255e51a583c94e2cdc910f9d70bb36f0f06d66e61928b9d5a513e8884d`.
- Contact probe specification:
  `local/evidence/20261012-p06q-tree-contact-01/import/inventory01/probe-spec.json`
  SHA256 `5a1940b7e975445422e7b10898757ba88877f7a2c92e120760fceccb6f78eacd`.
- Source/import receipt:
  `local/evidence/20261012-p06q-tree-contact-01/import/inventory01/receipt.json`.
- Native launch procedure and pinned run inputs:
  `local/evidence/20261012-p06q-tree-contact-01/native-probe-plan01.md`.
- Native raw exports (two observations per slot):
  `local/evidence/20261012-p06p-prohorovka-01/runtime-a-treecontact02/destructible-catalog-47288.json`
  and
  `local/evidence/20261012-p06p-prohorovka-01/runtime-b-treecontact02/destructible-catalog-16568.json`.
  Both SHA256 `dfff68fbecfb754c4a87a7095198dc6dbabd99308061c34b8d723534bc9f9c48`.
- Validated native join:
  `local/evidence/20261012-p06q-tree-contact-01/import/native-join01/receipt.json`,
  manifest SHA256 `59a51da7613e17ae4150471053b1ad9856a4acbd74d493aee1cc16f04ebcdb7f`,
  worker SHA256 `bb0cd813993f98c2d0d3d1832784651366aedcd6b200e43e4fcc933187c8185d`.
- Stop and rollback receipts:
  `local/evidence/20261012-p06p-prohorovka-01/stop-treecontact02stop.json`,
  `install-a-treecontact02/restore.json`, and
  `install-b-treecontact02/restore.json`.
- Earlier focused importer receipt/logs remain under
  `local/evidence/20261012-p06q-tree-contact-01/tests/`.

## Unconfirmed points and limitations

The native object-index mapping is now verified for the pinned passive catalog,
but native contact callback semantics, rendered fallen-tree state, and
owner-confirmed driving through a removed object are **NOT_RUN**. The passive
observer intentionally reads getters and does not destroy objects, so this run
cannot prove that a tree falls or that a tank can pass through it. The private
physics worker still does not establish historical client damage rules.
Compound buildings, fences, water, historical damage, and arbitrary all-map
object eligibility remain outside this card. Linux/cross-architecture
determinism is also **NOT_RUN**.

## Rollback

Keep the card on this branch until the native gate. To roll back, stop only
verified owned P06Q processes and restore the installation ledgers. The
accepted P06P gateway output is still present and hash-matched, but the
historical `local/build/server/physics-integrated-p06p-01/` directory is
empty in this checkout, so a physical P06P rollback relaunch is **NOT_RUN**
and cannot be claimed. Do not substitute the current P06Q physics worker.
The availability check is recorded in
`local/evidence/20261012-p06q-tree-contact-01/tests/rollback-artifact-availability01.json`
(SHA256 `2574507a601ccef3a2c8bac1f2642881256329521b6f26f4cc4abe70e15fc561`).
Preserve the P06Q branch and all evidence. A source rollback means returning to
the accepted P06P commit in a separate checkout, or a reviewed revert of P06Q
changes; do not delete shared source files or evidence. No tracked deployment
artifact was replaced. Source rollback alone does not restore missing runtime
binaries or pool manifests.

## Overnight handoff integrity correction — 2026-10-13

**VERIFIED:** the ORG-0B summary now has SHA256
`3b90fcd5e34f4acda38d7b54c9de4a2c6d1b7968bf83817369f86255552d2256`.
The earlier STATUS hash preceded correction of elapsed time from `50.310s`
to the retained log's `47.892s`. The log still records 2222 tests, one missing
historical Email22-fixture error and 17 skips. No tests were rerun for this
metadata correction. The full log's hash is unchanged.

`docs/ACTIVE_GATE.md` now points to P06Q instead of the historical P06P gate;
this plan and the research rollback instructions now agree on the missing
P06P physics artifacts and require evidence preservation. The historical
614-test build is distinguished from the later 610 PASS / 4 FAIL recheck.

**OBSERVED:** the prior P09A/P09B targeted counts (22/13) came from console
output; their fresh directories retain auditor/self-check receipts, not unit
test logs. This integrity check confirms the receipt hashes and statuses, not
an independent replay of those unit-test counts.

The P08A receipt's `audit_error` is a paraphrase of the missing-input cause.
The recorded CLI actually reported `path escapes bound` for the missing
`lifecycle-static.json`: `_bounded` labels both path-resolution errors and
containment errors that way. The original receipt is preserved; no path escape
is inferred from that wording, and source audit acceptance remains **NOT_RUN**.

Metadata-only checks and pre-change document snapshots are retained under
`local/evidence/20261012-p06q-tree-contact-01/handoff-integrity01/`.
Use the four `before/docs/` snapshots to undo only this handoff correction while
preserving earlier overnight documentation and evidence. No source, runtime,
client or deployed artifact changed; native owner acceptance remains **NOT_RUN**.

## Acceptance

**PASS_NATIVE_CATALOG_PROBE_PENDING_OWNER_CONTACT.** Source import, bounded
contact runtime, worker IPC, isolated tests, atomic batch rollback, native
object-index mapping, and two-client passive catalog agreement pass.
Mass/speed-sensitive ramming policy is implemented and covered by isolated
tests. Owner-rendered tree-fall, scene replication after a real contact, and
passage through a removed object remain open until the owner-controlled gate.

**One next recommended step:** perform the owner-controlled tank-to-tree
ramming/tree-fall and passage gate using the joined 635-object catalog. The
passive native probe is complete and deliberately does not destroy anything.

## Transport boundary fix — 2026-10-13

The first 117-chunk owner-run (`manualtree01`) failed before
`SHARED_ANNOUNCED`: `shared_payload` built one body larger than the transport
body cap, then reconnect noise appeared as `channel_state`/`channel_framing`.
The retained log is
`local/evidence/20261012-p06p-prohorovka-01/gateway-manualtree01.stdout.log`.

The P06Q transport card now bounds each announcement body to 512 bytes and
stages vehicle and area creation records behind the reliable window of eight
pending bodies. A 117-chunk synthetic contact catalog exercises announcement
splitting, request staging, cumulative ACK release, duplicate rejection, and
the all-area readiness gate. The targeted gateway catalog-wire suite is 8/8
PASS in
`local/build/server/gateway-p06q-final-17/result.json`; the receipt explicitly
marks this as `PASS_ISOLATED_BUILD_TARGETED` with scope `catalog_wire_tests`.

Bounded private smoke `p06qsmoke01` used that pinned build with both approved
client copies. It recorded two entries, two ready transitions, 117 unique
catalog-area creations per session, 632 ready snapshots, and no failed session
or channel-state/channel-framing reject. Stop and rollback receipts are
captured by
`local/evidence/20261012-p06q-tree-contact-01/tests/gateway-p06q-transport-smoke01.json`.

The fresh post-fix full-suite run is 611 PASS / 4 FAIL (615 total); the one
additional pass is the new 117-chunk regression. The same four real-worker
tests need missing P06O/P06N pool fixtures. This is an environment gap and
remains separate from the P06Q transport result. The owner-controlled native contact,
tree fall, `fallenTrees`, both-worker ACK, and passage checks remain
**NOT_RUN** until a clean bounded smoke and the morning manual gate.
