# P05B — tracked handling for MS-1 and IS-7

Date: 2026-10-13. Branch: `codex/p05b-tracked-handling`.
Base: accepted main `0393857e2a67646e87dd03763baf3b98da98b0b9`.
Status: PASS_AUTOMATIC_PRIVATE; native/owner acceptance NOT_RUN.

## Goal and scope

Repair the shared P05 driving debt exposed by the accepted P03M IS-7 run:
sluggish acceleration/braking, ineffective stationary steering, excessive
lateral slide and abrupt moving turns. Both accepted vehicle identities,
geometry, mass and speed limits remain source-bound. This is a versioned
test_lab tracked controller, not a claim to reproduce the closed #717 solver.

One card covers the common handling controller and its MS-1/IS-7 fixtures.
No crew/ammo/economy, combat damage, network transport or client-input rewrite.
Fixed 60 Hz authoritative rigid-body simulation and existing contact/fracture
and both-worker ACK barriers remain. Original client is read-only. Root A/B
are stopped; no sibling service processes, live DBs or installs are touched.
Unrelated dirty P09B research file is explicitly excluded.

## Execution

1. Preserve existing binary/config/input traces and reproduce handling defects.
   Audit source parameters and pinned Jolt drivetrain APIs/defaults.
2. Measure yaw, displacement, forward/lateral velocity, acceleration, stopping
   distance/time, contact masks and available engine/gear/track telemetry.
   Use controlled flat geometry for causal/symmetry checks and real map meshes
   for regression; synthetic terrain never proves native acceptance.
3. Add a bounded versioned control policy and explicit config/profile binding.
   Preserve legacy config semantics for rollback. Fix traction/braking/steering
   through the physics controller, without trusting client pose or teleporting
   bodies to desired trajectories. Record any engineering constants as policy.
4. Run repeatable paired workers for both masses: launch/stop/reverse,
   stationary left/right, forward/reverse turns, steering release, neutral,
   slope/wall, fence chain/tree and both-worker ACK regression. Validate bad
   config/telemetry inputs, source layout and applicable gateway/Python suites.
5. Save before/after metrics and exact commands/source/build hashes. Update
   STATUS, ACTIVE_GATE and research. Prepare reversible manual test artifacts
   after automatic gates; owner checks both tanks before merge.

## Acceptance

Baseline defects must be visible in retained metrics. Candidate must turn
from rest without the old powered forward lunge, remain directionally stable
under sustained and released steering, brake to rest, respect source speed
limits, and have bounded left/right symmetry on flat ground. Numeric thresholds
will be fixed in the harness before tuning, identified as project quality
criteria rather than historical constants. No PASS from finite values alone.
Real map contact/destruction gates and deterministic replay must stay intact.
Full native movement/reconciliation and historical fidelity are not inferred
from offline tests. Required owner gate keeps the card in its branch.

## Files, evidence and rollback

Allowed code: `server/physics/`, narrow config/profile support in
`server/gateway/src/drive/worker*`, new handling tools/tests and required
existing test fixture updates. Documentation: this plan, P05 plan, research,
STATUS and ACTIVE_GATE. No source-wide rewrites.
Evidence: `local/evidence/20261013-p05b-tracked-handling-01/` (append-only).
Build through `python -B -X utf8 server/build.py physics --out <fresh-path>`;
gateway through the corresponding `gateway --test` command. Exact harness
commands/results will be recorded in the research report.
Rollback: stop receipt-owned stand, restore install/namespace ledgers, select
accepted P03M binaries/pools; revert only this card's changes. No global reset.

Implementation and automatic gates complete; see
[P05B research](../research/P05B_TRACKED_HANDLING.md) for the source audit,
retained failures, declared quality bounds, 36 final flat runs,34 paired map
cases,10 legacy cases and9 exact historical trajectory comparisons. Gateway
723/723 PASS; affected Python76 PASS/one symlink NOT_RUN. No historical solver
or native handling acceptance is inferred. Next gate: manual MS-1 then IS-7.
