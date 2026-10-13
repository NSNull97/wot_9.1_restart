# P05B — bounded tracked handling for MS-1 and IS-7

Date: 2026-10-13. Branch: `codex/p05b-tracked-handling`.
Accepted base: `0393857e2a67646e87dd03763baf3b98da98b0b9` (P03M).
Status: **PASS_AUTOMATIC_PRIVATE / NATIVE_OWNER_NOT_RUN**.
Evidence root (E below): `local/evidence/20261013-p05b-tracked-handling-01/`.
This report does not close general P05 reconciliation or historical fidelity.

## Owner feedback and candidate08 direction reversal

OBSERVED: owner reports better MS-1 handling on ms1ram02, but strange delays
switching acceleration/reverse and missing houses/logs/barrels/outhouses.
This is partial improvement, not acceptance. Frozen `native-handling-ram08/
ownerfeedback01/` contains10 scene commits, each with both preceding worker
ACKs, and no recorded faults. `owner-feedback-receipt01.json` finds3 direct
opposite worker input changes among23 throttle changes. Native prefixes do
not contain motor/gear/clutch telemetry; attribution of every perceived delay
to the ramp is UNKNOWN.

VERIFIED defect: v3 TrackedHandling slews signed motor input at2/s. Direct
nonzero sign reversal retains old-sign input for about0.5s. A neutral step
already cleared it, explaining why key sequences can feel different. Existing
flat tests exercised reverse from rest, not moving reversal. Candidate08
clears only the old ramp state when the requested motor sign changes, then
retains its0.5s rise from zero. No body pose/velocity, gearbox timing, source
power/brakes or friction changes. Config1/2 do not use this helper.

Canonical isolated build: `local/build/server/physics-p05b-candidate08`, DLL
SHA256 `7c3446217abed21ca1777be1e7f94dcb55341bbc0ce4a246e6ec97f0ef77b7be`.
`reversal-audit01/component01/` links the actual current helper against the
pinned native6-wheel controller:1638 assertions/526 Apply calls PASS, including
correct motor sign from the FIRST1/60s call, preserved30-step ramp, release,
brake,40 toggles, pivot-to-reverse and speed caps. The same test against the
committed old helper fails at the first reverse call, retained under
`component-baseline01/`. Actual native gearbox tests select opposite gear on
step1, positive clutch on32/full on49; the physical ground test is separate.

`reversal-metrics01/direct01` and `direct08` each contain8 real-worker runs:
both tanks, short/long moving reversals, each repeated twice with exact state
and diagnostic replay. At10Hz, first requested motor sample improves0.6→0.1s,
requested gear0.5→0.1s, clutch re-engagement1.1→0.6s. Sampled speed crossings:

| Initial condition | Candidate07 | Candidate08 |
|---|---:|---:|
| MS-1 forward2.934m/s → reverse |2.1s|1.4s|
| MS-1 forward7.647m/s → reverse |2.9s|2.5s|
| IS-7 forward3.178m/s → reverse |2.1s|1.4s|
| IS-7 forward11.856m/s → reverse |3.6s|3.1s|

Separate `controls07`/`controls08` add8 real runs total for neutral/brake,
steering/pivot transitions and rapid toggles. Old-direction driver input is
removed, not physical momentum. Delivered ground torque and exact historical
gearbox timing remain UNKNOWN; sampled zero crossings are not continuous
substep traces. New08 native owner acceptance remains NOT_RUN.

Fresh no-reversal regression:36 flat runs+2 calibrations,114 command/state/
diagnostic byte comparisons against07 PASS. All20 paired ram cases PASS;
76 state/contact/fracture/scene streams match byte-for-byte. Four wall ACK
streams differ only in config hashes caused by fresh wall-fixture paths:
complete configs except that path, manifests and buffer hashes were verified
equal before comparing ACK semantics. Initial unnormalized comparator failed
on this metadata difference; script/failure receipt retained. Corrected
`regression08_summary02.py` produces `regression08-summary.json`. No new
gateway/Rust/parser changes:728 gateway tests are PRIOR evidence, not rerun
with this08 worker. Legacy1/2 matrix was not rerun for this v3-only correction.

Commands executed (from repository root):

```powershell
python -B -X utf8 server/build.py physics --out local/build/server/physics-p05b-candidate08
python -B -X utf8 local/evidence/20261013-p05b-tracked-handling-01/reversal-metrics01/reversal.py --label direct08 --build 08 --kind ms1 is7 --plan direct short --repeats 2
python -B -X utf8 tools/tracked_handling_matrix.py --worker D:/WoT_9.1_Server/local/build/server/physics-p05b-candidate08/bin/MapDriveWorker.exe --local-root D:/WoT_9.1_Server/local --config D:/WoT_9.1_Server/local/evidence/20261013-p05b-tracked-handling-01/candidate-config01/ms1.json --out D:/WoT_9.1_Server/local/evidence/20261013-p05b-tracked-handling-01/controller-audit/final-matrix08-ms1 --diagnostics
python -B -X utf8 local/evidence/20261013-p05b-tracked-handling-01/regression08_summary02.py
```

Same flat command ran with is7 in both paths. Ram exact argv is retained in
`ram-regression/candidate08-{canonical01,oblique01,wall01}/receipt.json`;
component build/run and controls commands are in their receipts/reports.

Coverage recheck (`coverage-owner02`):28 Tun barrels and17 Logs piles are
excluded;58 structure instances require per-module handling. Six Toilet
instances are already accepted: the initial claim they were excluded confused
movement-only admission reasons with the separate accepted legacy9 union.
That preliminary error is retained/corrected, not a new coverage fix. Frozen
owner prefix shows8 fences+2 GerBoxes+1 tree removed and no toilet contact;
it cannot identify the exact small building the owner meant. Nearby excluded
sheds exist. A source predicate identifies38 candidate additional-visual
fragiles (28 barrels,8 farming-machine instances,2 piers) for a later P06R
slice; it is a proposal, not implemented or native accepted. Full structure/
mixed-material log collision must preserve surviving parts.

Owner then explicitly finished ms1ram02 and authorized restart. Root preserved
`native-handling-ram08/ownerfinal02/`, receipt-stopped A/B/gateway, and restored
both install/namespace ledgers. New08 manual lifecycle uses fresh
`native-handling-ram09/` helpers/pools/binding after automatic gates. Original
client and unrelated P09B file remain untouched. Rollback: select frozen07
worker/pools or revert only this helper correction after receipt-owned cleanup;
do not reset shared work. Acceptance: automatic correction verified, native
handling/coverage still OPEN. Next: bound08 MS-1 owner comparison.

## Owner correction and whole-object contact response

After checkpoint491bde5, owner explicitly corrected the phrase "accepted ram":
only continuous fence-chain passage was accepted. Not all expected objects
break, and trees/crates can stop even IS-7. Native preparation was held before
any installation/start. The previous tree regression checked contact/removal
and eventual passage, so it could pass despite an immediate near-zero speed.

VERIFIED code/catalog defect:403 fences had pre-solver8000J response while
626 trees and9 whole fragiles had zero projected response and therefore rigid
collision before post-step removal. Candidate04 traces OBSERVE this: at about
3m/s the new focused fixture has MS-1 crate/tree troughs.146/.095m/s and IS-7
.040/.009m/s. This validates the owner concern for the tested source objects.

Worker catalog6/domain5 now explicitly selects
`test_lab-whole-object-energy-v1`, preserving IPC5 prepared receipts and the
both-worker publication barrier. All existing1038 source/native identities
receive the same retained approximate8000J resistance. New mode drops the
independent total-speed1m/s floor; it requires sufficient positive normal
kinetic energy. Normal-energy reduction preserves tangential velocity and
cannot refund a surviving wall's impulse. Old catalogs preserve old behavior.
8000J is not a historical reconstruction or proof of equal real resistance.

VERIFIED source coverage (`E/ram-audit/REPORT.md`, `coverage.json`):3904 imported
instances comprise2943 trees,712 fragiles,71 fallingAtoms,58 structures and120
undefined. Existing1038 supported rows are unchanged.300 excluded fragiles
need replacement/additional visuals;255 also have mixed/unmatched materials
and182 incomplete whole-span movement coverage (reasons overlap). These
include some carts, logs and crate groups. Whole-body deletion would erase
surviving collision, so these remain the open P06R partial-object contract.
All2317 excluded tree rows have zero movement triangles; they are not missing
solid tree colliders. FallingAtoms and structures need separate native/state
and collision lifecycles; undefined rows cannot be presumed destructible.

The original client predicts contact damage using its mass/speed calculation
and scaled reference HP, but its historical authoritative momentum-loss law
is UNKNOWN. No HP-to-resistance formula was invented. Original shot HP/native
indices/spans remain byte-equivalent. `tree-speed0-source.json` verifies that
the newly reachable slow tree-fall bucket0 still starts animation at.45rad/s
(`(discreteInitSpeed+1)*.45`), with the corrected pi/2 pitch constraint intact.

Importer20/20 PASS, including exact old export bytes. New manifest SHA
`944ca90d9b8855fbba2206abc0d32138b9807106afb4c5d60c270d2257bd87c8`;
worker catalog SHA
`6d9a57de3b86f1e3b9a66390ff0968677b9a29e9238ca8559158d99dfb3dce16`.
Candidate05 DLL SHA
`7b61da99e7dc5969de8fbb5b7197d0bde9537cef4e11d7ad82bd8bcab4eee7be`.
36 final flat runs plus two calibrations match candidate04c state/input/
diagnostic bytes exactly (`E/ram-audit/flat05-comparison.json`). Legacy10 paired
cases pass;9 available historical trajectories remain exact. Affected Python
96 PASS/one symlink NOT_RUN of97; worker config/output16 and new catalog12
negative checks PASS. `E/python-final05.log`, `legacy-regression05/`,
`legacy-state-comparison05.json`, `worker-boundaries05/` and
`whole-catalog-negatives05/` retain evidence. Focused contact/runtime gates are
recorded separately below when complete; no native acceptance is implied.

Additional changed files: `server/physics/{CheckedInput,FractureResponse}.cs`,
physics README; gateway worker/catalog/fracture, shared fragiles/server and
their tests; new `server_whole_fracture_real_tests.rs`; compound importer/tests;
P06R scope clarification. Private source-backed fixture failures are retained,
including blocked approaches/spawn settle and initial too-short low-speed
passage duration. They do not justify changing runtime thresholds to pass.

## Final contact candidate07 and retained failures

Candidate05 exposed a second real defect: MS-1 hits fence3167 obliquely with
12.667kJ normal energy but receives no fracture and stops. The first weak
manifold cached rejection for the complete object/substep. Retrying admission
on a later manifold could leave an earlier rigid constraint, so catalog6 now
uses a bounded exact-body-pair prepass before the first callback returns.
The actual Added/Persisted hull callback is mandatory; a query alone never
destroys anything. The read-only NoLock native shape query uses the world's
speculative separation and active-edge setting. It copies one strongest
closing contact with stable tie breaking, then shares the decision across
all manifolds. The receipt may carry that actual query contact rather than
the triggering callback manifold. This is explicit approximate policy.

Limits:4096 hits per source body query,32 distinct decisions per substep,
32 debits per advance. Candidate07 adds an early owner-thread/fault/count
guard before the mutable query; successful trajectories match06 exactly.
83 component checks (including10,000 seeded reducer vectors) verify actual
pinned native query axis/world-space coordinates, collection callback API,
selection order, repetition, separation, thread and capacity failures.
Evidence: `E/controller-audit/whole-prepass-component01/receipt.json`.

Final worker DLL SHA256:
`956cf0a898c84fa9c4e9180dd52f3f9bede21945ee12e01ae498a697796004bb`.
Build: `local/build/server/physics-p05b-candidate07`.
Full worker artifact manifest SHA256:
`8bf6be66b8a7021a8362a71021ce8f5a53bef9a7bd61edfc77da3e51d21856d5`.
Native pools are `E/pools-ms1-07/pool-ms1-handling.json` and
`E/pools-is7-07/pool-is7-handling.json`; exact source geometry/profile pins
remain unchanged. Final private helpers: `E/native-handling-ram07/`.
Earlier helper directories are preserved superseded drafts, not launch pins.

At approximately3m/s incoming speed, the sampled minimum longitudinal
speed in the first0.5s after target contact is:

| Source target | MS-1 before / candidate07, m/s | IS-7 before / candidate07, m/s |
|---|---:|---:|
| Crate3618 | .146 / 2.385 | .040 / 2.949 |
| Tree3680 | .095 / 2.361 | .009 / 2.976 |

All20 final paired real-Jolt cases pass:12 normal/low-speed,4 oblique and4
object-plus-solid-wall controls,40 owned workers exited0. Each energetic
clear case requires exactly one debit, both ACKs before the next advance,
no post-commit target contact and full projected body passage. Comparable
normal input speeds differ by only.005-.015m/s; MS-1 loses about.635-.640m/s
normal speed to the resistance versus IS-7's.0393-.0395m/s. Three low-speed
MS-1 impacts stay solid, while three IS-7 impacts below1m/s break and pass.
For the oblique tree pair, normal speeds1.562/1.587m/s yield5.719/85.882kJ:
MS-1 does not break it; IS-7 breaks it and preserves tangential velocity.
All four surviving-wall controls still stop the tank; no solver-speed refund.
The identical formerly failing fence3167 config now keeps2.283m/s and passes.

`E/ram-regression/final07-summary02/receipt.json` pins all commands, files,
20 exact06-to07 state/contact/receipt comparisons and10 metric/mutation tests.
Its SHA256 is `d5dc375bfe925e3eba6419f49dd19f8235ff111b104e5a59fe8f2affc18b4ee2`.
These controlled cases retain the source geometry but isolate the target by
initially removing the other catalog objects. They directly replay scene
policy over real worker IPC; the separate Rust runtime gate uses all1038
intact objects and actually checks domain publication and both-worker ACKs.
Observation is10Hz plus exact fracture-substep before/after vectors. Absence
of any zero-speed instant between samples is UNKNOWN. No native visual claim.

Metric clarification: the first classifier incorrectly expected every angled
hit to destroy the object; final expectation uses the fixed8000J normal-energy
threshold. The projected-plane no-passage assertion was also restricted to
low-speed frontal controls: a glancing deflection can legitimately go around
an intact object. Subthreshold angled controls require actual hull contact,
paired replay, no removal/debit and nontrivial tangent. This change did not
rescue a penetration failure: the retained MS-1/tree3680 cases in05/06/07 all
have `full_body_passage=false`, so the earlier assertion also passes on them.
Original and final runner snapshots preserve both rules.

Final07 checks also pass:36 flat runs plus2 calibrations with114 exact
comparisons against04c/05b/06b;10 paired legacy cases;9 available historical
state files byte-identical (IS-7 chain historical file absent, NOT_RUN);
16 real worker config/output and12 malformed catalog rejections. Python97
discovered:96 PASS and one Windows symlink fixture NOT_RUN. Layout97 source
files/22 relocations PASS. Evidence: `E/ram-audit/flat07-comparison.json`,
`legacy-regression07/`, `legacy-state-comparison07.json`, `worker-boundaries07/`,
`whole-catalog-negatives07/`, `python-final06.log`, `layout-final07.json`.

Full canonical gateway03 suite:728/728 PASS, including four final07 real
whole-object source-map cases through receipt parser, actual domain/fallenTrees
state and both-worker publication barrier. Its executable SHA256 is
`dd93bff0107a31b445bb28e238bb56ea4d65af66b6f9d903dc6b2a3f44a3ebf2`.
Build receipt: `local/build/server/gateway-p05b03/result.json`; raw commands
and logs remain beside it. Fresh real-case proofs are in `E/ram-gateway-real/`.
Gateway02 never
ran tests: Rust compilation failed with Windows os112 (disk D full), and
even its result.json could not be written. The tiny attempted
`controller-audit/whole-prepass-receipt.json` is0 bytes and INVALID; use the
completed component receipt above. Automatic approval rejected deleting
intermediate caches, so no deletion occurred. NTFS compression of this card's
five gateway target directories and evidence preserved content and freed
about1.67GB; retained executable and final RAM receipt hashes matched.
`E/ntfs-compression01.json` and per-directory logs record that operation.
Fresh gateway03 uses `CARGO_INCREMENTAL=0`;260 runtime source hashes were
frozen in `E/final-source-before-gateway03.json`. Source/build history remains.

Other retained failures: gateway targeted01 had a crate spawn intersecting a
surviving fence; only the approach fixture was corrected. Candidate05 oblique
failure is retained before the actual repair. Tree3344 approach and IS-7 fence
3307 full passage remain failed because of surrounding static geometry; they
are not counted as accepted routes. First final RAM report consolidation
failed on a str/Path helper after tests; the error remains in
`ram-regression/final07-summary/failure.json`, and fresh summary02 succeeded.

Reproduction commands (fresh output names required; do not overwrite evidence):

```powershell
python -B -X utf8 server/build.py physics --out local/build/server/physics-p05b-candidate07
$env:CARGO_INCREMENTAL = '0'
python -B -X utf8 server/build.py gateway --test --out local/build/server/gateway-p05b03
python -B -X utf8 local/evidence/20261013-p05b-tracked-handling-01/run_map_regression.py --build D:/WoT_9.1_Server/local/build/server/physics-p05b-candidate07 --out legacy-regression07 --legacy
python -B -X utf8 local/evidence/20261013-p05b-tracked-handling-01/ram-regression/ram_matrix.py --out local/evidence/20261013-p05b-tracked-handling-01/ram-regression/candidate07-canonical01 --build local/build/server/physics-p05b-candidate07 --dll 956cf0a898c84fa9c4e9180dd52f3f9bede21945ee12e01ae498a697796004bb --mode normal --mode low
```

All additional oblique/wall/flat/component commands are pinned in their
receipts. Manual setup/stop/restore commands are in the private final helpers'
README. Unsupported compound coverage, historical resistance calibration,
100-battle production capacity and native owner acceptance remain unclosed.
Rollback remains receipt-owned stop, installation/namespace restore, then
the accepted P03M worker/pools/catalog; do not reset unrelated changes.

## Problem, evidence and interpretation

Owner accepted the IS-7 identity/profile while reporting a shared driving
failure: ineffective stationary steering, car-like turns, lateral drift and
sluggish acceleration/braking. The old pivot defect predates IS-7.

VERIFIED local #717 source audit (`E/source-audit/receipt.json`, `REPORT.md`,
`vehicle-movement-values.json`) pins eight freshly read original resources.
MS-1 mounted profile is 4691 kg, 43 hp / 31626.5 W, 34 deg/s source rotation;
IS-7 is 68190 kg, 1050 hp / 772275 W, 28 deg/s. Original resources under
`C:/WoT_0.9.1_RU_0717_original` were read only. No modern vehicle data imported.
`rotationIsAroundCenter=false` alone does not specify the original solver or
justify forced forward propulsion when only a steering key is held.

OBSERVED retained flat baseline `baseline-matrix03-{ms1,is7}/result.json`:
MS-1 pivot is about .0012 deg/4 s and reverse-turn slip reaches 21.2 deg;
IS-7 stationary steering moves its centre 10–13 m, and released steering has
4.45 m/s lateral RMS / 87.2 deg slip. Replays agree exactly on this platform.
Straight acceleration and braking already pass the declared flat criteria:
MS-1 reaches 5 m/s in 2.3 s, IS-7 in 1.3 s. This does not disprove the owner's
native experience; it does rule out blindly increasing engine torque based
only on that observation.

VERIFIED pinned Jolt binary defaults include fixed track inertia 10 kg m².
OBSERVED candidate03 on IS-7 still gives roughly 9.94/83.68 deg left/right
moving turns. Changing only track inertia for candidate04 gives 75.17/78.10.
INFERRED: underscaled track inertia materially contributed to poor heavy-tank
constraint convergence. This experiment is not proof of the original WoT law.
The full native BigWorld handling algorithm and delivered track torque remain
UNKNOWN. A different local wrapper checkout was not treated as the exact
package source; actual APIs were checked against the pinned DLL and execution.

## Implemented contract

- Pool/config v3 and exact SHA-bound handling profiles select the new policy.
  Legacy pool1/config1 MS-1 and pool2/config2 IS-7 remain available unchanged.
- `TrackedHandling.cs` controls the existing Jolt drivetrain and six supports
  at 60 Hz. It never assigns the desired pose or velocity to the body.
- Opposite tracks allow stationary steering. Moving ratios depend on measured
  speed, track width and bounded yaw feedback. Reverse keeps the existing
  domain steering convention. Source yaw rates bound the requested target;
  measured yaw is not represented as a hard mathematical cap.
- Project policy: 3 m/s² lateral acceleration budget; yaw-target ramp three
  source yaw rates per second; motor-input ramp 2/s; immediate zero drive
  request on release/brake. Existing source-derived torque/gears/brakes remain.
- During steering, fore/aft support lateral friction is .001 of the baseline;
  middle supports retain lateral grip. Friction returns at 5 baseline units/s
  on release/brake. Baseline lateral1.0/longitudinal1.2 are explicit engineering
  parameters, not imported historical coefficients.
- Per-track inertia is `max(10, .02 * mass_kg * wheel_radius²)`: MS-1 remains10,
  IS-7 becomes about204.85 kg m². The 2% equivalent rotating-mass model is an
  approximation. The accepted v1/v2 modes retain the native default10.
- Optional `--handling-diagnostics <fresh-owned-path>` writes a separate
  bounded JSONL, at most12000 rows/16 KiB each, with quaternion, local/world
  velocities, RPM, gear/clutch, inputs, both tracks and six support impulses.
  IPC is unchanged; diagnostics are off in normal gateway launches. Impulses
  cover the last1/60 s step, not a whole10 Hz interval. Offered engine torque
  does not claim to measure delivered ground torque.

Changed files: `server/physics/{Program,TrackedHandling,HandlingDiagnostics}.cs`,
`server/gateway/src/drive/worker.rs`, `worker/profile.rs`, the two
`worker/*-handling-profile.json` files; `tools/tracked_handling_{profile,matrix}.py`,
matching Python tests, `tools/map_drive_worker/MapDriveWorker.csproj`, two LF
rules in `.gitattributes`, this report, P05/P05B plans, STATUS and ACTIVE_GATE.
The unrelated dirty P09B research file is excluded.

## Automatic results and exact scope

| Gate | Result | Evidence |
|---|---|---|
| Canonical gateway build/full suite | 723/723 PASS | `local/build/server/gateway-p05b01/result.json` |
| Canonical physics candidate04 build | PASS | `local/build/server/physics-p05b-candidate04/result.json` |
| Final flat handling matrix | 9 scenarios x2 repetitions x2 vehicles, PASS | `E/controller-audit/final-matrix04c-{ms1,is7}/result.json` |
| Exact flat state + diagnostics replay | PASS, 1826 MS-1 /1806 IS-7 frames | `E/controller-audit/candidate04c-final-receipt.json` |
| Real-map paired regressions | 17 cases per vehicle,34 PASS | `E/map-regression04/receipt.json` |
| Legacy v1/v2 paired regressions | 5 per vehicle,10 PASS | `E/legacy-regression04/receipt.json` |
| Old/new legacy trajectory bytes | 9/9 available comparisons exact | `E/legacy-state-comparison04.json` |
| Legacy IS-7 chain historical comparison | NOT_RUN, no historical file; fresh case PASS | same receipt |
| Worker invalid config/output guards | 16 rejections PASS | `E/worker-boundaries04/receipt.json` |
| Affected Python suite | 76 PASS /1 SKIP of77 discovered | `E/python-final02.log` |
| Windows symlink fixture | NOT_RUN, creation unavailable | same Python log |
| Both projected native pools | PASS export/identity/hash checks, not native runtime | `E/pools-{ms1,is7}/receipt.json` |
| Native handling and reconciliation | NOT_RUN | owner gate below |

The flat quality criteria were fixed before tuning: stationary yaw >=30 deg/4 s
with centre excursion <=2 m; moving signed yaw >=15 deg with speed >=1 m/s;
lateral RMS <=1 m/s and slip <=20 deg; left/right yaw asymmetry <=15%; reach
5 m/s within8 s; brake from5–6 m/s within3 s/10 m to stable full XYZ rest;
neutral centre excursion <=.2 m and released yaw <=5 deg/s. These are project
quality criteria. Each braking run uses a separate retained calibration to
find the first5 m/s crossing, then repeats the exact launch and braking input.

| Final flat measurement | MS-1 | IS-7 |
|---|---:|---:|
| Stationary yaw over4 s | about118 deg | about95 deg |
| Maximum centre excursion | about.79 m | about.08 m |
| Maximum moving-turn slip | <1.48 deg | <.18 deg |
| Time to5 m/s | 2.4 s | 1.4 s |
| Stable stop from about5 m/s | 1.4 s /1.42 m | 1.0 s /2.29 m |

Real-map runs use retained Prohorovka meshes and two actual workers per case,
120 advances each; every state agrees exactly. Cases include straight/reverse,
left/right standing/moving turns, slope/rest, wall, fence chain, tree removal,
contact commits and both-worker ACK. A private wall append and private scene
policy replay are labelled fixtures. They do not prove native falling visuals
or a fresh gateway destruction transaction. Those remain owner checks.

Failed candidate01–03, the initial wrong-input harness attempt, relative-path
setup failures and the earlier mismatched fixed-duration brake criterion are
retained in E. `controller-audit/ITERATIONS.md` explains the candidate sequence.
Harness/setup failures are not relabelled as physics failures or erased.

## Reproduction commands

Run from `D:/WoT_9.1_Server`; all output paths must be fresh. The executed build
paths below identify retained runs and must not be overwritten.

```powershell
python -B -X utf8 server/build.py physics --out local/build/server/physics-p05b-candidate04
python -B -X utf8 server/build.py gateway --test --out local/build/server/gateway-p05b01
python -B -X utf8 -m unittest tests.test_tracked_handling_matrix tests.test_pivot_diagnostics tests.test_tracked_handling_profile tests.test_vehicle_physics_profile tests.test_server_layout -v
python -B -X utf8 tools/tracked_handling_matrix.py --worker D:/WoT_9.1_Server/local/build/server/physics-p05b-candidate04/bin/MapDriveWorker.exe --local-root D:/WoT_9.1_Server/local --config D:/WoT_9.1_Server/local/evidence/20261013-p05b-tracked-handling-01/candidate-config01/ms1.json --out D:/WoT_9.1_Server/local/evidence/20261013-p05b-tracked-handling-01/controller-audit/final-matrix04c-ms1 --diagnostics
python -B -X utf8 local/evidence/20261013-p05b-tracked-handling-01/run_map_regression.py --build D:/WoT_9.1_Server/local/build/server/physics-p05b-candidate04 --out map-regression04
python -B -X utf8 local/evidence/20261013-p05b-tracked-handling-01/run_map_regression.py --build D:/WoT_9.1_Server/local/build/server/physics-p05b-candidate04 --out legacy-regression04 --legacy
python -B -X utf8 local/evidence/20261013-p05b-tracked-handling-01/check_worker_boundaries.py --build D:/WoT_9.1_Server/local/build/server/physics-p05b-candidate04 --out worker-boundaries04
```

The second matrix run substitutes `is7` for both occurrences of `ms1`.
Pool export uses `tools/tracked_handling_profile.py --base-pool` with the
accepted P03M `physics-source01/native-lanes02/pool-native-is7.json`, `--vehicle
ms1|is7`, candidate04 `--worker-executable` and `--worker-manifest`, and fresh
`--out E/pools-ms1` / `E/pools-is7`; receipts contain all absolute inputs.
Source pool version selects source validation; target kind selects the new
profile. Both exports preserve geometry/spawn and replace the full physics
profile, not merely the mass.

Gateway executable SHA256:
`85f8d2e6a57a8ba391cb206c3b29dfa7b9c41a1a33f5226f584c935b0c98d5b7`.
Physics DLL SHA256:
`ef511dbd52c724a9d1bcf9c6b2568ad28da5b45e999e86b68be9419678586e78`.
Final matrix-tool SHA256:
`e3db2f25129b8f18f3c4bd6376c9b2f4234c53e64de784b288cbba3b56f012e7`.

## Limits, rollback and owner gate

OBSERVED MS-1 hard launch briefly leaves only two supports; hard braking gives
a transient reverse recoil of about.479 m/s before stable rest. These are not
silently removed from evidence. Suspension response and native appearance need
the owner. General tank–tank physics, original ground-resistance law, precise
historic transmission, cross-platform identity, performance at100 arenas and
full native reconciliation are UNKNOWN/NOT_RUN as applicable.

Manual sequence: two homogeneous MS-1 clients on Prohorovka, then a fresh
homogeneous IS-7 stand. Mixed vehicle selection is not introduced here. Check
stationary A/D, straight launch/stop, W+A/W+D, reverse turns, steering release,
slopes and consecutive fence/tree passage in both views. Capture full server
and client logs, no computer-input automation. Session readiness alone cannot
accept handling. Keep P05B on its branch until both owner results are recorded.

Private reversible stand commands and exact current source/build bindings
belong under `E/native-handling/`. Stop only receipt-owned root A/B, gateway and
workers; restore installation and namespace ledgers and verify hashes. Reuse
accepted P03M binaries/legacy pools to roll back behavior; revert only P05B
commits if source rollback is needed. Original client and sibling service stand
remain untouched. No main merge or production deployment is part of this gate.

Single next step at that checkpoint: owner's native handling comparison of MS-1, then IS-7.
# Native stand readiness recovery, 2026-10-13

After final automatic gate, `native-handling-ram07/ms1ram01` passed8 real
binding preflights and installed both owned copies, but A credential preflight
returned503 before either native client/control file existed. Exact gateway
PID18860 was stopped and both install/namespace ledgers restored. The README's
`interactive_client.py restore` was an incorrect command; argparse rejected
without mutation, then the actual `rollback` subcommand passed for both slots.
Failed logs are preserved alongside `partial-stop-ms1ram01.json` and restore
receipts. No native readiness or owner acceptance is claimed from this attempt.

Read-only `auth-audit/` proves current validator accepts existing A r4 while
historical validator rejects its retained r3 producer: `Crew generator source
changed`. B's simpler fixture remained available. Old root identity PID32780
predated the accepted P09D historical-evidence fix. In-memory code identity is
INFERRED from age/history and exact reproduction, not memory instrumentation.
Both SQLite quick_checks passed; no password/profile rewrite was attempted.

The P06N `identity-launch-native01.json` matched exact PID32780, executable
SHA, command/config and process creation (receipt written62ms after creation).
Its sole listener was127.0.0.1:20020 with no established requests. Root ran:

```powershell
python -B -X utf8 local/evidence/20261013-p05b-tracked-handling-01/auth-audit/restart_owned.py
```

Only that receipt-owned process was replaced with the current committed source
and unchanged config. New identity PID43384 has exact creation/hash receipt
`auth-audit/bridge-current-launch.json`; source inventory including web modules
is in `restart-before.json`. Both A/B auth200, identity match and overview200
ready; both DB quick_check OK and all stored game profiles unchanged. Normal
service rate-limit writes occur on auth requests. `restart-result.json` records
PASS_CURRENT_BRIDGE_BOTH_LOGINS. Runtime source was not changed by the repair.
If this process must be stopped, verify its exact new receipt; do not use old
PID32780 or global Node/process-name stop. Prior config remains the rollback
reference; no DB/fixture/credential migration needs undoing.

Fresh lifecycle `native-handling-ram08/` copies only the frozen six07 helpers
plus passive tests, supplies a current-head binding, corrects README rollback
commands and creates fresh ledgers. Prior files remain evidence. Final automatic
physics results remain applicable by exact260-file source/hash comparison.
Manual steering/ram feel and native acceptance are still NOT_RUN until owner
feedback. Universal object coverage remains open P06R, including300 excluded
fragiles; the wording "accepted ram" has been withdrawn beyond fence passage.

## 2026-10-13 evening — owner candidate08 feedback and overnight reproduction

OBSERVED owner: reversal delay appears gone. Remaining defects are side-fence
snag, drift during ordinary turns, and approximately once-per-second speed
loss30-to20km/h together with an aim-convergence jerk. Owner clarifies Space
means a small inertial slide of a light tank while braking/turning, not boost
or an artificial drift switch. Full P05B acceptance remains OPEN.

The ram09/ms1ram03 final prefix is ownerfinal03/result.json: both ready workers,
238 areas, four scene commits each preceded by both ACKs, zero server faults
and stderr. A's Barracks KeyError 'lock' keeps readiness FAIL_OR_NOT_READY.
The original inventory reader requires a top-level lock dictionary; accepted
fixture producers omit it (VERIFIED), exact live response was not dumped
(causal attribution INFERRED). Evidence: lobby-lock-audit01/receipt.json and
REPORT.md. This separate inventory defect is not suppressed as physics noise.

Root stopped only receipt-identified A47808/B20600/gateway15056, restored both
install and namespace ledgers, and verified former workers18564/34700 no longer
identify those executables. PID34700 was later reused by a Codex node process:
the first closure collector failed its too-strict PID-only absence assertion,
then the corrected collector recorded executable identity/PID reuse without
stopping that unrelated process. Both the failure and correction are preserved
in ram09/closure-attempt01.json and closed-run-receipt.json. Bridge43384 remains.

Executed lifecycle commands (E is the evidence root defined above):

```powershell
python -B -X utf8 E/native-handling-ram09/ready_snapshot.py --run ms1ram03 --vehicle ms1 --out-name ownerfinal03
python -B -X utf8 E/native-handling-ram09/stop_stand.py --receipt-dir E/native-handling-ram09 --run ms1ram03 --out-name ownerdone03 --reason '<owner completed run; overnight automatic work>'
python -B -X utf8 tools/interactive_client.py rollback --out E/native-handling-ram09/install-a-ms1ram03
python -B -X utf8 tools/interactive_client.py rollback --out E/native-handling-ram09/install-b-ms1ram03
python -B -X utf8 E/native-handling-ram09/namespace_copies.py a --restore
python -B -X utf8 E/native-handling-ram09/namespace_copies.py b --restore
python -B -X utf8 E/native-handling-ram09/collect_stop03.py
```

VERIFIED cadence defect: retained server log has5825 shared snapshots but5159
advances per worker. While holding throttle1/steer0, ticks1543/1553/1563/1573
repeat the previous XYZ and then resume roughly8.75-8.87m/s movement. The
dispatcher schedules from actual-send+100ms, while World advances by wall
clock and reuses cached poses. Exact HUD30-to20 and aim correlation remain
INFERRED; client interpolation behavior was not measured at that precision.
night-jitter01/scan01.json pins the retained log and all cited source rows.

Fresh controlled-IPC regression reproduces this on unchanged6ad93ae runtime:
11ms polling repeats a moving pose at tick1011. Canonical command:

```powershell
python -B -X utf8 server/build.py gateway --test --test-filter nondividing_poll_interval_does_not_repeat_a_moving_pose_every_second --out local/build/server/gateway-p05b-night-cadence-before01
```

Result EXPECTED_FAIL:0 passed/1 failed/728 filtered; failing test, build logs,
original source and hashes remain. This is coordinator proof, not native proof.
The planned repair uses logical100ms deadlines, fresh paired poses, bounded
late-worker handling and unchanged scene ACK barriers; tests must verify it.

Fresh real-worker side fixture uses original fence3167 and source map geometry,
both profiles, two workers per case,100 advances each. Both pivot and powered
side steering produce94 hull-contact frames, no fracture and near-zero final
motion. Exact paired-state repeatability passes; requested side behavior FAILS.
COM-normal energy admission omits angular contact velocity and sustained load.
Existing8kJ is project policy. Wheel impulse times distance is not energy,
and track slip work is not proven deformation work delivered to the fence.
Do not hide that gap behind invented historical constants. Evidence:
night-side-contact01/run01/receipt.json. Space/key-order and actual terrain
slip diagnostics live in night-slip01; native owner tests remain pending.

Next: finish/review bounded cadence correction and its automatic regression,
then continue unresolved side-contact and turning work under the overnight
plan until2026-10-14 09:00 Asia/Yekaterinburg. Frozen6ad93ae/candidate08/gateway03
remain rollback references. No merge, auto-driving or historical-ideal claim.
