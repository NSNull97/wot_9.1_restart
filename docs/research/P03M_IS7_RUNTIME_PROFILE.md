# P03M — source-bound IS-7 runtime

Status: IN_PROGRESS; automatic steering gate open, native owner gate NOT_RUN.
Branch: `codex/p03m-is7-runtime-profile`. Accepted baseline is P06R merge
`eb054618bd0eae1ae23bba42a0f875969ac2d24e`, pushed and remote-verified.
Owner accepted the fence-chain passage before requesting this next vehicle.

## Purpose and selected contract

Make the exact #717 IS-7 drive and fight in the authoritative shared Prohorovka
laboratory, with its own mass, collider, HP, mounted gun, projectile, aim joints
and native descriptor. The explicit trailing CLI selection is
`--map 05_prohorovka --vehicle-test-lab is7`; both actors use the selected kind.
The default remains MS-1. A pool, collision bundle or actor of a different kind
is rejected before publication. The older own-primary map-drive route is
MS-1-only and now rejects IS-7 pools before opening capture/sockets.

This slice uses temporary server-owned AP ammunition. It does not grant owned
items or change accounts, service/chat work, normal hangar-selected queue
admission, mixed-vehicle battle composition or production capacity.

## Verified source inputs

Original `C:\WoT_0.9.1_RU_0717_original` was read only. Source audits live in
`local/evidence/20261013-p03m-is7-01/`:

- `gateway-audit/`: nine historical native-catalog source hashes and twelve
  IS-7 collision resources; native descriptor
  `011c3a002400cd000b002f003a0000`, type7169, mounted gun14852, AP14602.
- `physics-source01/`: assembled mass68190kg, source movement dimensions and
  numerical conversion provenance. The chassis uses a documented six-support
  Jolt primitive-box approximation; original native dynamics are UNKNOWN.
- `geometry-surface01/is7-contact.json`: SHA256
  `a65013d10b8a8b05bd076a783e6da24749bcf8b823bfc2e0b9919d745694acbe`.
  Hull/Turret_01/Gun_01 contain1105 vertices and723 nonzero-area triangles;
  34 material entries have32 effective and2 absent rows. Original exact
  zero-area Hull IDs107/157 are explicitly excluded while source IDs are
  retained. The earlier725-triangle `geometry/` export is kept as invalid for
  runtime; the mesh validator was not weakened. Both full source packages
  and resource hashes were verified by the exporter.

Selected source values:2150HP,30 mounted rounds,13.7s mounted reload,3.4s aim
time,130mm AP490 damage,250/240mm nominal penetration. Shared S-70 defaults
15.43s/28 rounds do not override the mounted vehicle definition. Native source
speed900 and client factor0.8 yield720m/s. APCR/HE rows are explicitly empty.
Turret/gun pivots and angular/rear-sector limits come from the selected source.
Source visual bounds are VERIFIED; native hitTester bounds are NOT_RUN.

## Implementation and boundaries

`shared/vehicle_profile.rs` carries the immutable closed kind and mounted
configuration. Battle fire, shared model, aim/projectile, native wire, HP/damage,
terrain effects and trace admission use that kind. Shot storage permits60,
while MS-1 admission remains40 and IS-7 admission60. Trace initial ammunition,
event bound, materials, AP and wreck revisions are bound to the selected kind.
The fragile projectile path uses the selected shell's damage, rather than the
old fixed30. Geometry/material bundles admit only exact pinned source exports.

`tools/vehicle_physics_profile.py` and the Rust worker profile loader require
the complete admitted numerical physics projection; a changed mass alone or
an MS-1 collider cannot satisfy IS-7 admission. Physics policy parameters are
labelled approximate; they are not claimed to be reconstructed WoT formulas.
Single-plate AP, fixed damage/no RNG, unsupported screens/devices, retained
wreck geometry and primitive movement collision remain laboratory limits.
Chassis layers, track/module damage and detached/damaged models are not covered.

## Actual checks and retained failures

- Root canonical `gateway-p03m-is7-01` failed compilation on an old test's
  exhaustive Gun02-only match after introducing Gun01. Fixed both gun cases.
- `gateway-p03m-is7-02`:667 PASS/5 FAIL. All five were geometry fixtures indexing
  an empty newly-created World. Fixtures now attach real actors through the
  ordinary API; geometry assertions are unchanged.
- `gateway-p03m-is7-03`:673 PASS/1 FAIL. All five geometry cases pass, including
  articulated surface segments. A new real screen-shot fixture expected
  armor_14 but hit armor_6; fix/recheck is pending. Actual side-plate fire
  already verifies five490-damage hits, death and subsequent wreck blocking.
- Root geometry/layout Python run:37 executed PASS, one symlink fixture
  NOT_RUN because this Windows account cannot create symlinks. Log:
  `integration/python-geometry-layout01.log`. It covers10 new IS-7 tests,
  20 existing MS-1 collision/contact tests and7 executed layout tests.
- Initial source-profile Python tests:8 PASS in
  `integration/physics-import-tests-root01.json`; final revised-control profile
  requires a fresh run.
- Private paired workers exposed near-absent turning at inherited lateral
  friction1.2 on an unobstructed lane. Candidate0.8 did not fix it;0.6 restored
  turning on the move and retained tested straight/brake/slope stability.
  Stationary counter-rotation failed for both vehicles. These are real failed
  control gates, retained under `physics-source01/`, not native acceptance.
  IS-7 source `rotationIsAroundCenter=false` calls for a bounded controllable
  turn from rest with radius; the revised policy is still under test.

Build/test command used for each fresh numbered directory:
`python -B -X utf8 server/build.py gateway --test --out local/build/server/gateway-p03m-is7-NN`.
Python command: `python -B -X utf8 -m unittest tests.test_is7_contact_bundle
tests.test_ms1_collision_bundle tests.test_ms1_contact_bundle tests.test_server_layout -v`.
Set `WOT091_ROOT=D:\WoT_9.1_Server` for the pinned actual-source fixtures.
Build stdout/stderr, command receipts and failure files are retained unchanged.

## Native setup, rollback and next gate

Private launch/stop helpers are prepared in `native-is7/`, with exact source,
build, pool and geometry checks, separate ports20124/20126 and temporary
copy namespace `p03m`. They have not installed or launched this stand yet.
Original and parallel service-client copies remain untouched. The prior
P06R root stand is stopped and both installation/namespace ledgers restored;
its full owner evidence is in `20261013-p06r-compound-01/native-chain/fencechain03-final/`.

Do not merge P03M with required FAIL/NOT_RUN gates. Roll back this card by
returning to the accepted P06R runtime/pool/geometry after stopping only
receipt-owned processes and restoring this stand's installation and namespace
ledgers. Revert only P03M commits if a code rollback is needed; no global reset,
original-client edits or changes to the unrelated P09B file are required.

Next: finish the measured steering correction and automatic matrix, then launch
the reviewed IS-7 stand for the owner's movement/fire/destruction comparison.
