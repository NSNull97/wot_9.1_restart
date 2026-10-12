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
- **VERIFIED:** the Rust gateway suite passes 614 tests, including catalog
  parser limits, tree/fragile type rules, contact validation, immutable fall
  packing, trace replay, scene exclusion, worker ACK transactions, restore,
  legacy regression coverage, an atomic vehicle-contact batch regression, and
  a mass/closing-speed ramming regression.
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
python -B -X utf8 server/build.py gateway --test --out local/build/server/gateway-p06q-final-10
python -B -X utf8 server/build.py physics --out local/build/server/physics-p06q-final-02
python -B -X utf8 local/evidence/20261012-p06p-prohorovka-01/test_stand_helpers.py
python -B -X utf8 -m py_compile local/evidence/20261012-p06p-prohorovka-01/start_stand.py
python -B -X utf8 local/evidence/20261012-p06p-prohorovka-01/start_stand.py server --run contactprep04 --mode runtime --map 05_prohorovka --build gateway-p06q-final-09 --build-sha256 6ff51d463868022759b38262337b44802cafd04e7b7e3a375961970df0f547ea --build-result-sha256 9977d2a78d379f286a2ee79e82d22ee85876254fb4b87a3482f28c18eed25aad --expected-head 18016c2c2d6d6e0d2620f9ab2526e6735b3f22b4 --pool local/build/server/physics-p06q-final-02/pool-near.json --pool-sha256 59b88e5c2d2b1f9689c3b302275915cf2b9aed65290a8e1827c2d2eb596b5288 --destructible-catalog local/evidence/20261012-p06q-tree-contact-01/import/native-join01/manifest.json 59a51da7613e17ae4150471053b1ad9856a4acbd74d493aee1cc16f04ebcdb7f --dry-run
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
  mass/closing-speed ramming policy. Canonical final-11 receipt:
  `local/build/server/gateway-p06q-final-11/result.json`; receipt SHA256
  `1e0770db77bf4449f305de4c88c8ba766ab2024f80903e6adf51d410ab7bda3e`,
  executable SHA256
  `7d215fff8442bcb2ad655d72f7eb7eaae1382f526544a7e17395c897f5c57d6d`.
  The intermediate atomic-only receipt remains
  `local/build/server/gateway-p06q-contact-atomic-01/result.json`.
- Helper guards: 12 tests, **PASS**. The runtime command accepts the joined
  P06Q v2 manifest envelope (240 KiB) while retaining the 128 KiB ceiling for
  legacy v1 catalogs; an unbound v2 catalog is rejected.
- Runtime preflight `contactprep06`: **PREFLIGHT_ONLY_NOT_STARTED**. The
  joined v2 manifest, Prohorovka pool, final-11 executable and source HEAD all
  passed their pins; no gateway, worker, or client process started. Receipt:
  `local/evidence/20261012-p06q-tree-contact-01/tests/runtime-preflight-contactprep06.json`
  (SHA256 `f532f21b8242c42292a4fec058bdf6f43a32558b3c4c5ca34039949745ed013b`).
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
verified owned P06Q processes, restore the installation ledgers, and relaunch
the retained accepted P06P gateway/physics/pool/catalog artifacts. Removing
the P06Q source files and this evidence directory leaves the P06P mainline
unchanged; no tracked deployment artifact was replaced.

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
