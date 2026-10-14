# P05B actual-worker cadence and morning preparation

Scope: test infrastructure and evidence for the existing candidate09 logical100ms scheduling
correction, using candidate14 Jolt workers and both source-bound vehicle
profiles. Production runtime remains checkpoint `1ceb392`; no native client,
input, installation, service or live database operation is part of this phase.
Plan: [real-worker cadence](../plans/P05B_REAL_WORKER_CADENCE.md).

`E` below means `local/evidence/20261013-p05b-tracked-handling-01`.
The earlier full755 gateway gate and all candidate14 movement/fracture evidence
remain in [moving-fence report](P05B_MOVING_FENCE_CONTACT.md). This test-only
phase does not rebrand that historical gate as a fresh756-test full run.

## Preserved attempts

| Attempt | Result and actual scope |
|---|---|
| gateway-p05b-cadence-real01 | Test compiled; FAIL in harness before ready/advance. PID was requested immediately after asynchronous launch. |
| gateway-p05b-cadence-real02 | Bounded PID capture fixed; route preflight FAIL. MS-1 lane0 hits object2865 at seq67/tick582, IS-7 at seq54/tick504. Both actual workers exited0/reaped. Integrated cadence NOT_RUN in this attempt. |
| gateway-p05b-cadence-real03 | Revised full-scene corridor; actual two-profile cadence PASS, one selected Rust test. |
| gateway-p05b-cadence-real04 | Final source: explicit isolated ignored gate PASS, one selected test/zero ignored; production build PASS. |

Actual failing runs are `E/night-cadence-real01/run-6400-1791915223173723800`
and `run-14792-1791915363493109600`. The second failure has actual hull contact
and prepared fracture in the retained frame; it is not a cadence regression.
The original clean-turn observation did not establish a clear straight route.
The full scene was preserved. `post-failed02-process-observation.json` records
no remaining candidate14 executable after the failed run.

The harness now waits a bounded time for the child PID and retains known child
identities before waiting for later children. Unverified launch/cleanup stops
the next profile; exactly two complete cases are required for a PASS. These are
test changes, not Worker implementation changes. Independent review initially
missed the immediate-PID race and records that explicitly in
`E/night-cadence-review01/ASYNC_LAUNCH_ADDENDUM.md`.

The route amendment permits only independently justified spawn origin/yaw
changes in fresh private configs, keeping all geometry, source vehicle fields,
alive catalog objects, input sequence and timing assertions unchanged.

## Final actual result and evidence boundary

VERIFIED on this pinned Windows/Jolt build: focused04 saves the complete run in
`E/night-cadence-real02/run-42876-1791916216965184400`. Earlier successful03 is
`run-49752-1791915974568094900` in the same directory. Each run contains four
independent lane reference traces (488 states total), two paired traces and
eight captured owned child exit waits. Each actual sequence/pose matches its
reference exactly; no source was reused, mixed, skipped or overwritten before
publication. Both scenes remain0 with all1038 catalog objects alive.

| Final04 measurement | MS-1 | IS-7 |
|---|---:|---:|
| Publications / independent advances per lane | 120 / 121 | 120 / 121 |
| Active polls / active duration | 1002 / 11.831628s | 1013 / 11.848078s |
| Maximum observed poll gap | 12.815ms | 12.886ms |
| Unchanged actor/aim polls without publication | 882 | 893 |
| Aim changes across both actors | 24 | 38 |
| Observed publication interval range | 23.819–108.746ms | 35.507–108.534ms |

The short first interval is startup alignment with the independent100ms grid;
it is retained, not rounded into a claim of perfect wall-clock100ms spacing.
Logical deadlines advance exactly100ms; after the initial publication, world
buckets advance consecutively. Both runs have zero cleanup errors; independent
exit waits confirm owned processes have exited. Successful cargo output does
not retain the workers' exit-code/graceful-stop lines, so no exit0 claim is
made for03/04. Reference geometry audit covers the entire hull corridor;
MS-1 support masks range2..6, so this is not an all-wheels-grounded assertion.
In these no-load runs all replies were consumed and published in the same poll;
held/mixed pending observations are0. Delayed/early reply handling remains the
separate controlled-IPC evidence, not a scenario exercised by this smoke.

The revised origin `[-180,2.5,-350]`, yaw0, is private diagnostic configuration.
`E/night-cadence-route02/receipt.json` audits3904 instance bounds and428597
obstacle triangle AABBs: none intersects the full audited corridor. The
independent runtime reference still gates settling and catalog contacts.
`E/night-cadence-real02/fixtures/receipt.json` verifies that only spawn origin
changed; source vehicle fields, both map entries, geometry and catalogs remain.
Native/manual pools retain their original spawn.

This no-load wall-clock gate is explicitly ignored in the ordinary parallel
suite. `server/build.py --run-ignored` requires gateway `--test --test-filter`,
runs an exact test on one thread and rejects any result other than one pass
and zero ignored. The new option does not alter game/runtime scheduling.
`E/night-cadence-driver01/receipt.json` records four actual invalid CLI cases
rejected before output creation, an actual compiled default run with0passes/
1ignored, and three mocked cargo-result guards rejecting empty/multiple/still-
ignored selection before a build. The latter are driver checks, not workers.
Focused04 proves the real positive execution path. Default skip is intentional
and must never be counted as cadence acceptance by a future ordinary full run.

Independent reviews and raw-trace audits are retained in
`E/night-cadence-review01/` and final `E/night-cadence-review04/`. The final source/evidence inventory is
`E/night-cadence-checkpoint.json`, produced after the source commit and passive
stand binding. These automatic checks do not close native owner acceptance.

## Assertions and interpretation

The test first retains seq0..121 from each exact production lane using actual
validated worker states. Startup/settling is separately bounded. Reference
replays must have no catalog contact/fracture and a moving interval. The paired
IntegratedRuntime then receives real monotonic time with requested11ms polling
for120 publications per vehicle, bounded to15s active time.

It checks independent seq0 X/Z anchoring, consecutive source sequences, exact
reference poses and speeds, one fresh source per lane/publication, no pending
pose overwrite, independent100ms grid/world bucket arithmetic, no aim/actor
advancement without a publication, and bounded shutdown. It records actual
poll gaps, dispatch/consumption/publication times and complete poses. Source
age means observed consumption/dispatch age, not an unavailable producer clock.
Actual timer/OS stalls remain failures of the ordinary timing smoke, not
permission to relax the criterion or automatically attribute a production bug.

No assertion proves native network delivery, interpolation, convergence rendering,
owner-visible jerk resolution or historical solver equivalence. Uncatalogued
static collision callbacks are not exposed by this IPC; exact reference replay
does not turn their absence into a directly observed fact.

## Pressure feasibility and morning artifacts

`E/night-pressure-plan01/NOTE.md` and its pinned receipt audit the remaining
static side-pressure gap. Both profiles retain114 actual hull-contact frames
without fracture; near-zero speed is below the current energy/closing guards.
The original #717 client predictor uses mass and speed squared, not an exposed
force/dwell/deformation law. A stalled-push model and historical parameters
remain UNKNOWN; static pressure remains FAIL/OPEN. No threshold was quietly
lowered, no contact timer damage or unpaid angular energy was introduced.

The fresh passive stand is `E/native-handling-night14`, with exact exported
`pools-ms1-night14` and `pools-is7-night14`. It binds the full755 gateway14,
complete16-file worker14 and full domain6/worker7 catalog. Twelve existing
passive helper checks PASS; they mock only the final committed-source binding.
Independent review pins all helpers, catalogs, profiles, geometry and build
receipts in `E/night-pressure-plan01/manual-preparation-review.json`.

Actual final-source dry-run results belong in
`E/native-handling-night14/actual-preflight-receipt.json`, after reviewed source
commit and creation of its complete `binding.json`. The local README gives exact
commands for preflight, owner-authorized launch, collection, receipt-owned stop
and installation/namespace rollback. Preparation is not native acceptance.

## Commands, files, rollback and pending gate

Executed canonical attempts used:

```powershell
$env:CARGO_INCREMENTAL='0'
python -B -X utf8 server/build.py gateway --test --test-filter gateway091::shared::server::cadence_tests::real_worker_11ms_cadence --out local/build/server/gateway-p05b-cadence-real01
python -B -X utf8 server/build.py gateway --test --test-filter gateway091::shared::server::cadence_tests::real_worker_11ms_cadence --out local/build/server/gateway-p05b-cadence-real02
python -B -X utf8 server/build.py gateway --test --test-filter gateway091::shared::server::cadence_tests::real_worker_11ms_cadence --out local/build/server/gateway-p05b-cadence-real03
python -B -X utf8 server/build.py gateway --test --test-filter gateway091::shared::server::cadence_tests::real_worker_11ms_cadence --run-ignored --out local/build/server/gateway-p05b-cadence-real04
python -B -X utf8 local/evidence/20261013-p05b-tracked-handling-01/night-cadence-driver01/check.py
python -B -X utf8 local/evidence/20261013-p05b-tracked-handling-01/night-handoff-prep01/prepare.py
python -B -X utf8 local/evidence/20261013-p05b-tracked-handling-01/native-handling-night14/test_helpers.py -v
```

Tracked source changes are the existing cfg(test)
`server/gateway/src/shared/server_cadence_tests.rs` and the narrow explicit
ignored-test option/count reporting in `server/build.py`; the remaining changes are
plans/research/status and fresh local evidence/helpers. Unrelated P09B is
preserved. Revert this test-only phase after owned workers exit to return to
candidate14's preceding source. No installed runtime change requires rollback.
Preserve failed outputs and the previous candidate13/owner-run08 bundles.

Current acceptance: paired actual-worker cadence PASS on the pinned platform;
native owner NOT_RUN, static pressure FAIL/OPEN, compound coverage/historical
solver fidelity OPEN. Next: bind the committed morning bundle and run its six
actual passive preflights, then retain the explicit owner handoff. The binding
script is `E/night-handoff-prep01/bind_and_preflight.py`; its actual receipt is
authoritative for the later preflight result. No native launch or merge.
