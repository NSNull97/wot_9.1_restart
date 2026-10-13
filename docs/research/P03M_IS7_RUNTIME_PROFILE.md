# P03M — source-bound IS-7 runtime

Status: PASS_AUTOMATIC_PRIVATE; native owner gate NOT_RUN.
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
Source visual bounds are VERIFIED. The first native run also sampled all three
hitTester boxes in both clients: all six boxes match the source bundle exactly
after float32 conversion (`native-is7/is7run01-bbox-observation.json`), repeated
with corrected labels in `native-is7/is7run03-bbox-observation.json`. This
does not establish full BSP collision or movement-box equivalence.

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

Changed implementation files (relative to the accepted P06R merge):
`.gitattributes`; `server/gateway/src/battle/fire.rs`, `drive/worker.rs`,
`drive/worker/{profile.rs,is7-physics-profile.json}`, `main.rs`, `session.rs`;
`server/gateway/src/shared/{aim,ap,destructible,fragiles,fragiles_tests,geometry,
impact,impact_wire,materials,mod,model,projectile,server,server_is7_real_tests,
terrain_wire,vehicle_profile,vehicle_profile_tests,wire}.rs`;
`server/physics/Program.cs`; `tools/{is7_collision_bundle,is7_contact_bundle,
vehicle_physics_profile,client_marker_oracle}.py`; `client_patch/collision_oracle.py`;
`tests/test_{is7_contact_bundle,vehicle_physics_profile,client_marker_oracle,
collision_oracle}.py`. This report, its plan, STATUS and ACTIVE_GATE record the
acceptance boundary. Unrelated P09B research is excluded from this card.

## Actual checks and retained failures

- Root canonical `gateway-p03m-is7-01` failed compilation on an old test's
  exhaustive Gun02-only match after introducing Gun01. Fixed both gun cases.
- `gateway-p03m-is7-02`:667 PASS/5 FAIL. All five were geometry fixtures indexing
  an empty newly-created World. Fixtures now attach real actors through the
  ordinary API; geometry assertions are unchanged.
- `gateway-p03m-is7-03`:673 PASS/1 FAIL. All five geometry cases pass, including
  articulated surface segments. A new real screen-shot fixture expected
  armor_14 but hit armor_6. Correcting the ballistic origin to the interior of
  source Hull triangle8 fixed that fixture. Actual side-plate fire verifies
  five490-damage hits, death and subsequent wreck blocking.
- `gateway-p03m-is7-04`:674/674 PASS. Final `gateway-p03m-is7-05`:676/676 PASS,
  including revised14-field physics/config binding and actual IS-7 workers
  through the runtime/domain/both-ACK transaction. Fresh reference receipts
  match domain contacts exactly for3307/3308 at advances16/17. World stays
  unchanged after only A's ACK; scenes1/2 commit only after both. Actual
  energy debits are within0.24J of8000J at68190kg. This contact fixture does
  not assert full hull passage. `gateway-real01/result-50672-1791897540526302600.json`.
  All owned test workers exited. Exact230 tracked runtime source hashes before
  and after the full gate match: `integration/canonical-final01/receipt.json`;
  tested source `0f6a3cd0970fbaf0d2c9b70fe90856cce0f1a7c2`.
- Root geometry/layout Python run:37 executed PASS, one symlink fixture
  NOT_RUN because this Windows account cannot create symlinks. Log:
  `integration/python-geometry-layout01.log`. It covers10 new IS-7 tests,
  20 existing MS-1 collision/contact tests and7 executed layout tests.
- Initial source-profile Python tests:8 PASS in
  `integration/physics-import-tests-root01.json`; final revised-control root
  run is8/8 PASS in `integration/python-physics-v2-01.log`.
- Private paired workers exposed near-absent turning at inherited lateral
  friction1.2 on an unobstructed lane. Candidate0.8 did not fix it;0.6 restored
  turning on the move and retained tested straight/brake/slope stability.
  Stationary counter-rotation failed for both vehicles. These are real failed
  control gates, retained under `physics-source01/`, not native acceptance.
  Source `rotationIsAroundCenter=false` is freshly verified. Final config2 uses
  longitudinal/lateral friction1.2/.4 and powered finite-radius steer ratio.2,
  respecting the forward traction cutoff. V1 defaults remain unchanged.
  This is approximate policy; original28deg/s handling is not verified.
- Final canonical physics02:16 IS-7 and8 MS-1 paired real-worker scenarios PASS,
  120 six-substep advances each. Both directions of moving/rest/reverse
  steering, acceleration/braking, straight/slope stability, solid wall, fence,
  adjacent fences and tree are covered. Ten actual C# config rejections,
  two diagnostic traction-cutoff cases and two ordinary EMPTY-scene spawn
  lanes PASS. Five old/new MS-1 trajectories match all120 full states exactly.
  Evidence `physics-source01/REPORT.md`, `FINAL_AUDIT.json`,
  `canonical-is7-02/`, `canonical-ms1-02/`, `canonical-negatives02/`.
- Actual legacy CLI rejects the final valid IS-7 pool before capture/key
  setup: `integration/legacy-rejection02/receipt.json` PASS. The reviewed
  legacy guard prevents an MS-1 wire model with IS-7 physics.
- First native setup exposed an MS-1-only passive marker guard. Observer fix
  `a5f8d1e08da71c64454a729e3767705187370898` binds exact mounted vehicle/gun/AP,
  preserves MS-1/schema1, adds explicit IS-7/schema2, correct Gun_01/BSP paths
  and16m rays. Root observer tests23/23 and actual CPython2.7.3 compilation PASS:
  `native-is7/oracle-fix01/{root-tests.log,root-cp27.log,receipt.json}`.
  These synthetic tests do not establish native compatibility.
- `native-is7/oracle-fix01/root-binding.json` compares230 runtime source files
  with the676-test gate: only the two expected observer/tool files changed,
  all server/physics files and gateway05 binary remain exact. The gateway test
  result is reused on that evidence, not represented as a rerun after the
  observer fix. Its first comparison rejected a CRLF test checkout; the test's
  exact normalized bytes were then verified, with both raw hashes retained.
- Native run02 reached the new geometry/profile guards in both clients but
  failed before marker cases: `piercingPower` is a direct native `readVector2`
  return, not necessarily a Python list/tuple. Source `_readShot:4473` and
  `_xml.readVector2:106` establish indexed access, not a concrete native class.
  The incorrect new guard is fixed in `c4f3b8a92afaf9afe4d7146503ce2d647726444f`:
  read exactly indices0/1, preserve numerical/pinned-value checks. Root24/24
  observer tests and CPython2.7.3 compile PASS; source contract, actual failures
  and logs are under `native-is7/oracle-fix02/`. Its root binding again confirms
  gateway05/server sources unchanged; the inherited CRLF note refers to the
  initial oracle-fix01 comparison, not a new failure of this check.

Final gateway EXE SHA256:
`4bcf989e20480be05e64d4f03814afeb19939380b5eacce22ebc7202c357e085`.
Final physics DLL SHA256:
`40f154828707b99e8301d9c72daf520322cfff56ca37a5f417a7309eed0cfdf2`.
Final admitted physics profile SHA256:
`2fefea06de45fd172894ea7330f59d8efa9f9914a4f88192bb7b5f6ce8d47a90`.
Compiler warnings remain; the successful build is not a warning-free claim.

Build/test command used for each fresh numbered directory:
`python -B -X utf8 server/build.py gateway --test --out local/build/server/gateway-p03m-is7-NN`.
Python command: `python -B -X utf8 -m unittest tests.test_is7_contact_bundle
tests.test_ms1_collision_bundle tests.test_ms1_contact_bundle tests.test_server_layout -v`.
Set `WOT091_ROOT=D:\WoT_9.1_Server` for the pinned actual-source fixtures.
Build stdout/stderr, command receipts and failure files are retained unchanged.
Final full gate wrapper:
`python -B -X utf8 local/evidence/20261013-p03m-is7-01/integration/run_gateway_gate.py --build gateway-p03m-is7-05 --out local/evidence/20261013-p03m-is7-01/integration/canonical-final01`.
Physics build:
`python -B -X utf8 server/build.py physics --out local/build/server/physics-p03m-is7-02`.
Actual physics matrix:
`python -B local/evidence/20261013-p03m-is7-01/physics-source01/run_final02.py`.

## Native setup, rollback and next gate

Private launch/stop helpers are in `native-is7/`, with exact source, build,
pool and geometry checks, separate ports20124/20126 and temporary namespace
`p03m`. Current run `is7run03` uses ledger-backed installation and launch source
`c4f3b8a92afaf9afe4d7146503ce2d647726444f`. Root native clients A18056/B51972
and gateway43724 have exact executable/creation-time receipts. The launch
at13:48UTC reuses canonical gateway05 after verifying the observer-only source
rollforward receipt and every recorded runtime hash. Subsequent documentation
commits do not change the launched code. No computer input was automated.
The ordinary native pool SHA is
`d3a64359b96ee254bdc3097761e7f957eb6fea5c5a9a4bde16e6973bafda81e3`;
both actors start with no prior removals. Authentication is staggered A then B
to preserve the known single-pending-login limitation.

`is7run03ready01/result.json`: PASS_READY_PREFIX_NOT_OWNER_ACCEPTANCE, two READY
sessions/workers,238 areas, zero server faults/stderr and no client diagnostic
errors at the frozen log prefix. `is7run03-marker02/audit.json` records120/120
original marker callbacks aligned with the pinned formula. Six native hitTester
boxes exactly match source float32 bounds;144 native rays are recorded with
correct Hull/Turret_01/Gun_01 names, without claiming mesh intersection parity.
The first offline marker audit rejected generic snapshot filenames because
they omitted PID. Identical payloads were frozen under their original observed
native filenames and bound to launch receipts; provenance and the failure are
retained in `is7run03-native-prefixes/receipt.json`. No callback was rewritten.
These checks do not prove rendered marker color or owner movement/fire/tree
and fence acceptance; that gate remains NOT_RUN.

Initial run01 reached two READY sessions/workers and238 areas without network
faults, but both passive marker collectors failed on the old MS-1-only AP2570
guard. The collector also labelled the IS-7 Gun_01 row as legacy Gun_02. The
failure is preserved in `is7run01ready01/` and `is7run01-failure-summary.json`.
Run02 also reached READY but failed the new list/tuple-only check on the direct
native vector returned by `readVector2`. Both failures are retained in their
`is7runNN-failure-summary.json` files. Runs01/02 are stopped, installations
restored and workers verified absent before the fresh run03. The owned p03m
namespace was retained across these installs and remains active for run03.
The first run02 launch preflight also caught an incorrect local-only source
path guard in the private launcher; corrected repository-contained hash checks
passed before server launch. Both preflight logs are kept.
Original and parallel service-client copies remain untouched. The prior
P06R root stand is stopped and both installation/namespace ledgers restored;
its full owner evidence is in `20261013-p06r-compound-01/native-chain/fencechain03-final/`.

Do not merge P03M with required FAIL/NOT_RUN gates. Roll back this card by
returning to the accepted P06R runtime/pool/geometry after stopping only
receipt-owned processes and restoring this stand's installation and namespace
ledgers. Revert only P03M commits if a code rollback is needed; no global reset,
original-client edits or changes to the unrelated P09B file are required.

Exact server executable arguments are retained in `native-is7/preflight-is7run03.log`
and `launch-server-is7run03.json`; A/B launch receipts exclude credential values.
Actual commands below use PowerShell from `D:\WoT_9.1_Server`. Preparation and
start already ran; do not repeat existing run names. The stop/restore commands
are the prepared rollback after owner testing, NOT_RUN for the current live03.

```powershell
$p03mNative='local/evidence/20261013-p03m-is7-01/native-is7'
python -B -X utf8 "$p03mNative/prepare_stand.py" --slot a --run is7run03 --mode runtime --map 05_prohorovka
# The same prepare command ran for b. Exact server start arguments are in its launch receipt.
python -B -X utf8 "$p03mNative/start_stand.py" a --run is7run03 --mode runtime --map 05_prohorovka
# B started only after A's SESSION_ACTIVE, using the same command with b.
python -B -X utf8 "$p03mNative/ready_snapshot.py" --run is7run03 --out-name is7run03ready01
python -B -X utf8 tools/client_marker_oracle.py --vehicle-kind is7 --trace-a "$p03mNative/is7run03-native-prefixes/native-18056-1791899311912.jsonl" --trace-b "$p03mNative/is7run03-native-prefixes/native-51972-1791899337359.jsonl" --out "$p03mNative/is7run03-marker02"
python -B -X utf8 -m unittest tests.test_collision_oracle tests.test_client_marker_oracle -v

# AFTER the owner's run, stop only the exact receipt-owned processes:
python -B -X utf8 "$p03mNative/stop_stand.py" --receipt-dir "D:/WoT_9.1_Server/$p03mNative" --run is7run03 --out-name is7run03ownerstop --reason 'Owner run finished'
python -B -X utf8 tools/interactive_client.py rollback --out "$p03mNative/install-a-is7run03"
python -B -X utf8 tools/interactive_client.py rollback --out "$p03mNative/install-b-is7run03"
python -B -X utf8 "$p03mNative/namespace_copies.py" a --restore
python -B -X utf8 "$p03mNative/namespace_copies.py" b --restore
```

Verify both receipt-owned workers are gone before final acceptance, then freeze
the complete logs and correlate actual owner input, contact, removal, both ACKs,
native callbacks and passage. Preserve original and unrelated service processes.

Additional UNKNOWNs: source-slope left/right steering is measurably asymmetric;
native stance/BSP equivalence, source28deg/s turn fidelity and wider terrain
sensitivity are unverified. IS-7 Karelia runtime is NOT_RUN. Single-plate AP
screens/device outcomes remain explicit unsupported zero damage. Production
100-battle scaling and universal destruction are not claimed.

Next: owner checks IS-7 movement in both directions, braking, consecutive
fences, tree fall/passage, turret/gun and one AP shot in both clients; collect
the native evidence before deciding P03M acceptance/merge.
