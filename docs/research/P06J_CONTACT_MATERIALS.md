# P06J — component material facts before damage

Date: 2026-10-10. Base: accepted P06I `b4ddd02`, storage cleanup `e238ffb`.
Code head: `748bbda`. Scope: one stock MS-1 contact-material binding on the
cumulative integrated route, without a new damage model.

## Result and evidence categories

**VERIFIED:** the pinned #717 descriptor/common material/mapping sources and
the original loader distinguish component materials. `Hull/armor_8=8` and
`Turret_01/armor_8=0` cannot be resolved by label alone. `_readArmor` starts
an empty table and copies common defaults only for explicitly listed local
records; `_readGunLocals` replaces the shared table when local armor exists.

**OBSERVED:** two real clients, two entities each, returned all expected
effective MaterialInfo fields. Independent comparison: 104 records, 1352 fields,
8 explicit checks that surveyingDevice kind28 is absent from Hull/Turret tables.
Each client produced eight bounded material-oracle events including chassis.
Only the three geometry-bound components enter the catalog; chassis is not
silently claimed as implemented collision geometry.

**VERIFIED:** the new bundle contains the original P06I geometry unchanged.
The final Rust suite recomputed all nine accepted native01 segments: same
nearest triangle, material, pose revision, normal, `t` and endpoint, including
exact float32 bits. A separate independent metadata replay retained all 21
original fields and bound the nine rows to the new catalog. These are offline
regressions over the previous accepted capture, not new P06J native shots.

**INFERRED:** this metadata-only addition preserves accepted gameplay because
the query and world endpoint calculations remain unchanged and are exercised
by the retained physics/aim/ammo/reload/native-wire tests. It does not replace
owner visual acceptance if a later change alters those calculations or wire.

**UNKNOWN / outside this card:** historical penetration, normalization,
ricochet, screen traversal, entry/exit orientation, module/crew resolution,
RNG distribution/order and HP damage. Raw descriptor armor is not declared a
complete effective-thickness contract. Winding normals are not certified
outward normals. `vehicleDamageFactor=0` is a source fact, not a full gameplay
verdict. P06D complete classification/outcome/replay acceptance stays NOT_RUN.

## Source chain and catalog

All resources come from configured research copy
`D:\WoT_9.1_Server\WoT_0.9.1_RU_0717_research`. Original client is untouched.
No modern 1.45 mechanics or external service traffic was used.

- `misc.pkg!system/data/material_kinds.xml`: name to native kind.
- `scripts/common/material_kinds.pyc::_init`, source line33: checks mapping.
- `scripts/common/items/vehicles.pyc::_readMaterials`, line5321: common record.
- `_readArmor`, line4534: explicit component records and overrides.
- `_readHull` line3119, `_readTurret` line3746, `_readGunLocals` line4071:
  effective component binding; local gun section replaces shared materials.
- `scripts/client/Vehicle.pyc::getComponents`, line477: descriptors observed.
- `Vehicle.collideSegment`, line521: missing material becomes armor0 in its
  client presentation result. This is explicitly not imported as damage logic.

Seventeen source pins, complete paths/byte lengths/SHA-256 and static loader
provenance are recorded by `tools/ms1_contact_bundle.py` and its local export.
The bytecode is inspected as data, never executed by the importer.

| Component | Present effective records | Explicitly absent mesh material |
|---|---|---|
| Hull | kinds1..12 | surveyingDevice28 |
| Turret_01 | kinds1..10 | surveyingDevice28 |
| Gun_02 | kinds1,2,3,25 | none |

Hull armor values: `18,16,16,16,16,16,16,8,8,0,10,16`; armor11 factor0.
Turret: `18,16,16,16,18,16,8,0,8,16`.
Gun: armor1=18, armor2=16, armor3=8 (all factor0); gun25 armor10/factor0,
damageKind1. Gun armor1 is retained even though this mesh does not use it.
The complete flags/chances are compared, not inferred from those examples.

Hull armor10 and turret armor8 remain real records with armor0/damageKind0.
Absent surveyingDevice is `effective:null`. Common defaults are not substituted.
gun25, surveyingDevice28 and gunBreech31 are distinct identifiers. `extra` is
observed only as `extra_is_none`, without serializing a native object.
Source `0.33` rounds to native `0.33000001311302185`; the audit compares exact
IEEE754 binary32 rounding, with zero post-rounding difference.

## Implementation and boundaries

`ms1-contact.v1` wraps unchanged `ms1-collision.v1` geometry plus immutable
component material records and full source pins. Its source revision is:

`ms1-contact-717:7666849add0757fd91c224dbc6c0a6550d8ae1bca434f175eaa5c66b06e2d9ab`

Bundle: 130856 bytes, SHA-256
`26a6714ea562bbc81b64835a8a9495ab9105ae648894b724ea94467d9d7771c2`.
Original geometry SHA remains
`e975427c05d40fc2850ad3829165f287cef9655092032c8e515b597a7a262e00`.

The Rust loader checks exact bundle SHA before JSON parsing; size, local path,
reparse, schema and complete triangle/material coverage are bounded. Catalog
fields are private; callers receive immutable source facts. New gateway expects
the new contact bundle; the retained P06I executable expects the original one.

`collision_query_classified` queries exactly once, looks up the same nearest
candidate and appends query/intersections/one `MaterialContact` atomically.
The new event references exact shot/query/segment/nearest intersection order.
There is no public API for submitting a made-up material or contact candidate.
Empty queries add no material event. Classification failure publishes no
partial world or tracer stop. Terminal remains `UnresolvedCollision`.
The 40-shot/256-segment/128-candidate bound now allows 25760 events.

`SHARED_GEOMETRIC_CONTACT` gains diagnostic `material_facts`; existing endpoint,
wire, actor pose, ammo/reload and HP behavior remain unchanged. No client HP
setter, hit result or authoritative material input was added.

## Commands, checks and local evidence

Evidence root: `local/evidence/20261010-p06j-contact-materials-01/`.

```powershell
python -B -X utf8 tools/ms1_contact_bundle.py --out local/evidence/20261010-p06j-contact-materials-01/ms1-contact.json
python -B -X utf8 -m unittest tests.test_ms1_contact_bundle tests.test_ms1_collision_bundle tests.test_server_layout -v
python -B -X utf8 server/build.py gateway --test --out local/build/server/gateway-integrated-world-p06j-01
python -B -X utf8 server/check_layout.py --out local/evidence/20261010-p06j-contact-materials-01/source-layout.json
python -B -X utf8 local/evidence/20261010-p06j-contact-materials-01/independent_material_audit.py
python -B -X utf8 local/evidence/20261010-p06j-contact-materials-01/accepted_prefix_material_replay.py
```

Append-only export/build/receipts require fresh output paths for another run.
The actual export was made from the isolated agent worktree with the same
absolute output path and verified source pins, then cherry-picked.

- Gateway full suite: **440/440 PASS**, pinned Windows GNU Rust1.90.0.
- Python focused: **27 PASS / 1 existing NOT_RUN** (Windows symlink-creation
  privilege in layout test); exporter reparse rejection itself is exercised.
- Source layout: **PASS**, 63 source files / 22 single-source relocations.
- Native material oracle: **PASS**, independent report and exact closed-file
  hashes in `independent-material-native-audit.json`.
- Accepted-prefix metadata replay: **PASS**, `accepted-prefix-material-replay.json`;
  P06I accepted prefix is 1515254 bytes, SHA
  `1436384426c2bcc4e8142764bfe7ba83849d3800039a4c452d28b58059d3a0dd`.
  The known later StorageFull tail is excluded, not relabeled clean.
- Final EXE SHA:
  `6a474a99c6e577ef310f90de8bce97f4453dbd7c19135b94f9520ec38afa750a`.
- Final native smoke01: **PASS_NATIVE_STARTUP / PASS_NATIVE_ALIGNMENT**.
  Both workers/clients ready, 370 snapshots and eight material-oracle rows per
  client; no server/observer errors in the closed run. Nine accepted shots,
  18 native launches, three geometric contacts (shots1/3/8), six exact native
  contact stop endpoints. All nine final endpoints agree between both clients.
  Materials (Turret armor6, Hull armor5, Turret armor3) match the bundle and
  effective native records; descriptor armor16/factor1, damage remains false.
  `independent-startup-smoke01-audit.json` and
  `diagnostic-native-contact-audit.json` contain exact closed-file hashes.
  Server ammunition decrements are recorded separately; the passive native
  hooks did not observe battle ammo, so fresh native ammo is NOT_OBSERVED.
- Fresh owner shooting / HP / P06D damage capture: **NOT_RUN**, not a gate of
  this material-metadata card. Previous P06I owner acceptance remains distinct.

Launchers `prepare_stand.py` / `start_stand.py` in this evidence root preserve
the cumulative integrated profile and accepted `physics-integrated-lane-01/pool.json`.
Run `oracle01` used accepted P06I03 plus original geometry to obtain an independent
client table oracle. Client changes are passive scalar observation only and have
separate reversible install ledgers. Final-build startup evidence is recorded
separately in this root; neither run is a new owner shooting acceptance.
The smoke01 diagnostic run also observed actual shots, independently audited
above; this does not imply that every shot contacted the other tank.

## Rollback and next gate

Revert this card's merge. With own clients closed, restore the applicable
`tools/interactive_client.py rollback --out <install-ledger-directory>` ledger.
Use retained `gateway-integrated-world-p06i-03`, original `ms1-collision.json`
and accepted `physics-integrated-lane-01/pool.json`. Canonical service, account
state, original client and physics worker were not replaced by this card.

The next single gate is an explicit source-backed penetration/ricochet contract
for the measured MS-1/AP contact, before connecting any HP reduction.
