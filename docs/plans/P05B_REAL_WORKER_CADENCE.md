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
`p05b_source_audit` exclusively owns
`server/gateway/src/shared/server_cadence_tests.rs` and new private cadence
fixtures/evidence. No other tracked source changes are authorized by this phase.
If production changes are required, report the dependency before editing.

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
