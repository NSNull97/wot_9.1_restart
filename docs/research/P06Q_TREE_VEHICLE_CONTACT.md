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
test_lab mutation policy. A fragile ram removes the object with `isShotDamage`
false. A tree stores the original `fallenTrees` packed `UINT32` value and
removes its collision body only after every participating worker acknowledges
the cumulative scene. Native client rendering and owner acceptance were not
run in this card.

## Evidence classification

- **VERIFIED:** the pinned Prohorovka source inventory contains 626 eligible
  SpeedTree instances in 116 tree chunks plus nine legacy fragile instances in
  one additional chunk: 635 catalog rows across 117 target chunks. Every
  admitted tree has projectile span zero, a non-empty physics span, source
  material 71, and a checked `.spt` resource. The saved inventory reproduces
  byte-for-byte on a second import.
- **VERIFIED:** the Rust gateway suite passes 612 tests, including catalog
  parser limits, tree/fragile type rules, contact validation, immutable fall
  packing, trace replay, scene exclusion, worker ACK transactions, restore,
  and legacy regression coverage.
- **VERIFIED:** the isolated .NET physics worker builds with the contact IPC
  implementation. It bounds raw contacts, distinct object IDs, line size,
  normal/point/velocity values, and rejects unknown body identity or overflow.
- **OBSERVED:** the implementation is internally consistent on the pinned
  synthetic worker fixtures and existing private worker IPC tests.
- **INFERRED:** the selected `test_lab` thresholds (minimum speed 1 m/s,
  closing speed 0.1 m/s, and tree speed code bands) are an explicit project
  policy, not historical 0.9.1 damage rules.
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
  IPC v4, object-contact decoding, scene limits, and legacy preservation.
- `server/gateway/src/shared/fragiles.rs` and `fragiles_tests.rs` — typed
  tree/fragile catalog, u32 contact health, hull/wheel policy, fall packing,
  and replayable state transitions.
- `server/gateway/src/shared/impact.rs` — separate `VehicleContact` trace
  event/stage, replay, ordering, scene and exclusion accounting, and contact
  event budget.
- `server/gateway/src/shared/model.rs` — candidate-world contact application
  and atomic server state integration.
- `server/gateway/src/shared/server.rs` — worker contact collection, catalog
  kind/profile binding, ACK-gated scene commit, and cumulative publication.
- `server/gateway/src/shared/mod.rs` and
  `server/gateway/src/shared/destructible_wire.rs` — per-area fallen-tree
  state and the original `ARRAY<UINT32>` property wire.
- `server/gateway/src/shared/server_catalog_tests.rs` — contact-capable
  catalog fixture updates.
- `server/physics/CheckedInput.cs`, `Program.cs`, and `README.md` — checked
  contact catalog loading, Jolt hull/wheel capture, IPC v4, and documented
  bounds.
- `docs/plans/P06Q_TREE_VEHICLE_CONTACT.md` — card plan.

## Commands and real checks

```text
python -B -X utf8 -m unittest tests.test_destructible_catalog tests.test_destructible_catalog_probe tests.test_tree_contact_catalog -v
python -B -X utf8 server/build.py gateway --test --out local/build/server/gateway-p06q-final-04
python -B -X utf8 server/build.py physics --out local/build/server/physics-p06q-final-02
git diff --check
Get-Process -Name WorldOfTanks,sr-gateway,MapDriveWorker,PhysicsSpike
```

Results:

- Python: 39 tests, **PASS**. The final log is
  `local/evidence/20261012-p06q-tree-contact-01/tests/importer-tests-final.log`.
- Gateway: 612 tests, **PASS_ISOLATED_BUILD**. Receipt:
  `local/build/server/gateway-p06q-final-04/result.json`; executable SHA256
  `fd060bed9f0901ed1b25ee314a15ee08a4b442c3cc67d5da89eb758d8a6dbbee`.
- Physics: **PASS_ISOLATED_BUILD**. Receipt:
  `local/build/server/physics-p06q-final-02/result.json`; DLL SHA256
  `74513499fcb0b88b78abc53be88d1111e9fa4a83d120f2f0249e1d9fdad692de`.
- `git diff --check`: **PASS**.
- The process snapshot was empty after the checks. No original client or
  server process was left running.

## Evidence paths

- Imported inventory:
  `local/evidence/20261012-p06q-tree-contact-01/import/inventory01/inventory.json`
  SHA256 `d3aae3255e51a583c94e2cdc910f9d70bb36f0f06d66e61928b9d5a513e8884d`.
- Contact probe specification:
  `local/evidence/20261012-p06q-tree-contact-01/import/inventory01/probe-spec.json`
  SHA256 `5a1940b7e975445422e7b10898757ba88877f7a2c92e120760fceccb6f78eacd`.
- Source/import receipt:
  `local/evidence/20261012-p06q-tree-contact-01/import/inventory01/receipt.json`.
- Native launch procedure (not a native result):
  `local/evidence/20261012-p06q-tree-contact-01/native-probe-plan01.md`.
- Earlier focused importer receipt/logs remain under
  `local/evidence/20261012-p06q-tree-contact-01/tests/`.

## Unconfirmed points and limitations

The full native export for both owned clients (`a` and `b`) was **NOT_RUN**.
Therefore native object-index mapping, native contact callback semantics,
rendered fallen-tree state, and owner-confirmed driving through a removed
object are **NOT_RUN**. The synthetic exporter and private physics worker do
not establish compatibility with the original client. Compound buildings,
fences, water, historical damage, and arbitrary all-map object eligibility
remain outside this card. Linux/cross-architecture determinism is also
**NOT_RUN**.

## Rollback

Keep the card on this branch until the native gate. To roll back, stop only
verified owned P06Q processes, restore the installation ledgers, and relaunch
the retained accepted P06P gateway/physics/pool/catalog artifacts. Removing
the P06Q source files and this evidence directory leaves the P06P mainline
unchanged; no tracked deployment artifact was replaced.

## Acceptance

**PENDING_NATIVE_OWNER.** Source import, bounded contact runtime, worker IPC,
and isolated tests pass. Native mapping, two-client scene replication, and
owner-rendered ramming/tree-fall acceptance remain open.

**One next recommended step:** run the prepared passive native probe for both
owned Prohorovka clients, capturing two stable 117-chunk passes per client,
then perform the owner-controlled ramming/tree-fall and passage gate.
