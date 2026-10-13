# P05B — bounded tracked handling for MS-1 and IS-7

Date: 2026-10-13. Branch: `codex/p05b-tracked-handling`.
Accepted base: `0393857e2a67646e87dd03763baf3b98da98b0b9` (P03M).
Status: **PASS_AUTOMATIC_PRIVATE / NATIVE_OWNER_NOT_RUN**.
Evidence root (E below): `local/evidence/20261013-p05b-tracked-handling-01/`.
This report does not close general P05 reconciliation or historical fidelity.

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

Single next step: owner's native handling comparison of MS-1, then IS-7.
