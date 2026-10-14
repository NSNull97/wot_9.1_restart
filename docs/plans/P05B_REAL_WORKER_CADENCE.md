# P05B real-worker cadence: bounded automatic evidence

Authorized phase of the existing overnight P05B card, starting at `1ceb392`
(candidate14, full gateway755/755). Native owner acceptance remains OPEN.
Goal: exercise the existing100ms publication fix with actual candidate14
workers, real monotonic time and requested11ms polling for MS-1 and IS-7.
No production scheduler, controller, physics, client or service edits.

## Frozen design and ownership

Detailed design: `local/evidence/20261013-p05b-tracked-handling-01/night-cadence-real-plan01/PLAN.md`,
SHA256 `a110cd3ed230c2af672b54df90392666ac851accc70719abae150355319c2937`.
Root owns this plan, STATUS, reporting and final checkpoint. Agent
`p05b_source_audit` initially owned
`server/gateway/src/shared/server_cadence_tests.rs` and new private cadence
fixtures/evidence. No other tracked source changes are authorized by this phase.
After that agent's capacity failure, root took over the bounded test and its
repairs; `p05b_metrics` performs independent offline review. The later explicit
build-driver amendment below is also root-owned. No production change is needed.

## Execution and gates

1. Verify candidate14's complete artifact manifest/source binding. Prepare
   fresh MS-1/IS-7 pools using the existing source-profile turn configurations,
   full original terrain/obstacles and full alive domain6/worker7 catalogs.
   Preserve both pool map entries and all source profiles. Check containment
   and reject reparse-point ancestors. Preserve prior evidence and failures.
2. Before each integrated run, run both exact production offset lanes through
   121 real six-substep advances, one worker at a time. Require sequential
   validated states, scene0, no catalog contacts/fractures and a moving interval.
   A failed route preflight stops the run; no silent route or geometry changes.
3. Run both real workers through IntegratedRuntime for120 publications, real
   Instant/11ms requested polling,15s active bound and separately bounded
   warmup. Verify each source sequence and full mapped pose exactly against
   the reference, one fresh paired source per publication, exact100ms logical
   deadline increments, no pending-pose replacement and no aim-only advancement.
   Record every poll, source age, publication interval, scene and timing lag.
   Ordinary no-load consecutive-world-bucket failures remain recorded failures;
   OS stalls do not justify threshold relaxation or automatic bug attribution.
4. Drop and reap only captured owned worker PIDs, including on assertion failure.
   Run one canonical focused test after source freeze, requiring nonzero test
   selection. Independent review checks timing, oracle and evidence limits.
   No repeated full755 gate is required for a test-only addition absent a new
   production change or unresolved concern.

Command (fresh output; `CARGO_INCREMENTAL=0`):

`python -B -X utf8 server/build.py gateway --test --test-filter gateway091::shared::server::cadence_tests::real_worker_11ms_cadence --out local/build/server/gateway-p05b-cadence-real01`

## Limits and rollback

All new runtime checks are NOT_RUN at plan publication. Actual-worker cadence
does not prove native UDP/filter/aim rendering, owner jerk resolution or
historical driving fidelity. Static pressure and object coverage stay OPEN.
Rollback is a reviewed revert of this test-only phase after owned children exit;
keep candidate14/runtime and all evidence. No native input, install, merge or push.

Next: prepare pinned fixtures and implement the bounded test under the frozen
design, then run the route preflight and two-profile cadence gate.

## Retained preflight failures and explicit route revision

Focused01 compiled but failed in the test harness: asynchronous Worker launch
does not expose a PID immediately. Test-only bounded PID capture now precedes
reference execution and integrated startup. Unverified launch or cleanup
failure stops further profiles. Production Worker and scheduling are unchanged.

Focused02 correctly rejected the proposed route before any integrated run:
MS-1 lane0 hits catalog object2865 at seq67, IS-7 lane0 at seq54. Both captured
workers exited0 and were reaped. The previously measured turning route was not
proof of a clear twelve-second straight route; preserve both failure directories.

Authorize one explicitly designed route revision after a read-only audit of
the complete source obstacle triangles and terrain. Fresh private configs may
change only spawn origin/yaw; both vehicle profiles, source geometry, all alive
catalog objects and input sequence remain unchanged. The corridor must cover
both production lane offsets and the larger hull over a bounded straight run.
Record the geometric selection and remaining settling risk before execution.
Then rerun the same121-step reference validation and120-publication assertions
with fresh pools/hashes/output. Do not remove geometry, change timing thresholds,
accept contacts as clean or silently shorten the test. A further fixture failure
remains an explicit failed attempt requiring assessment before another revision.

Frozen revision: spawn `[-180,2.5,-350]`, yaw0; lanes x=-184/-176. Audit
`night-cadence-route02/receipt.json`, SHA256
`4c3defb6c1ab87094ef72b747747bbf3212335b2646a37557ece36e5c42d051c`,
finds zero overlap with3904 instance bounds and428597 obstacle triangle bounds
in XZ `[-192,-355,-168,-125]`. Terrain4768 intersecting facets have maximum
planar slope8.1843degrees. SpawnY is derived from the initial hull footprint;
settling remains a runtime gate. Fresh `night-cadence-real02/fixtures` preserves
every non-spawn config value and all objects. This is a private diagnostic
origin, not a changed native/manual spawn or a harder speed cap.

## Isolate the timing gate from parallel regression work

Focused03 passed both120-publication cases on the revised full scene. Independent
review identifies a test-infrastructure risk: an unignored strict wall-clock
smoke would run alongside other actual-worker tests in default cargo parallelism.
Its declared no-load condition would then be false. Do not weaken timing checks.

Root additionally owns a narrow `server/build.py` change: explicit
`--run-ignored` is valid only with gateway `--test --test-filter`; it invokes
the exact selected ignored test with one test thread and requires exactly one
passing test. Mark this timing test ignored for ordinary parallel suites, with
a clear reason. Ordinary driver commands retain their behavior; record ignored
counts and explicit execution mode in results. No game/runtime code changes.

Verify invalid option combinations fail before creating output; execute the
exact ignored gate through the pinned canonical driver in a fresh output and
check the compiled test is skipped without explicit opt-in. Retain focused03
as actual timing proof predating this infrastructure adjustment. New final
command adds `--run-ignored`; no full756 PASS claim is permitted.

## Completed scope

Focused04 PASS: both actual profiles publish120 fresh paired poses with exact
reference equality and unchanged actors/aim on no-publication polls. Eight
owned workers exit, cleanup errors0. Four invalid actual CLI combinations,
one actual default skip and three mocked driver selection guards PASS. Review,
failed01/02, successful03/04, commands and limits are in
[the research report](../research/P05B_REAL_WORKER_CADENCE.md). No production
scheduler/controller edit and no native acceptance. Proceed to the existing
[morning handoff](P05B_MORNING_HANDOFF.md); pressure/coverage remain OPEN.
