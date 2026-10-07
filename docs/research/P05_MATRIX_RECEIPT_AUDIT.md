# P05 movement-matrix receipt audit

Status: **PASS_OFFLINE_MATRIX_SHAPE_ONLY / NATIVE_RECONCILIATION_NOT_RUN**.

`tools/movement_matrix_audit.py` is a bounded, read-only verifier for the
existing `p05-deterministic-matrix.v1` test-lab receipts.  It accepts both the
two-map aggregate summary and an individual map row.  It pins the two accepted
map IDs and config SHA-256 values, requires `event_count == command_count + 1`,
checks the sequence/tick prefixes, phase ordering, finite aggregate ranges,
worker return code and duplicate/non-finite JSON rejection.  It also rejects
fields that would blur client coordinates or clocks into server authority.

An optional `events` trace can be attached to a map row for a future bounded
capture.  When present, every event must have the documented worker event
shape; sequence must advance by one, ticks must increase, map/config identity
must match, and position/direction/velocity vectors must be finite and within
the supplied `bounds_xz`.  The current accepted receipts contain aggregate
phase data only, so their result is explicitly
`pose_validation=NOT_PRESENT_IN_AGGREGATE`; this is not a pose or native
movement claim.

## Checks

Targeted tests: `tests.test_movement_matrix_audit` — 14 tests, 0 failures.

The auditor was run against:

* `local/evidence/20261009-p05-deterministic-matrix-01/summary.json`;
* `local/evidence/20261009-p05-deterministic-matrix-01/01_karelia.json`.

Both returned `PASS_OFFLINE_MATRIX_SHAPE_ONLY`.  Native client movement,
server reconciliation, historical physics, tank/static collision causality and
owner acceptance remain `NOT_RUN`.

No worker, client, deployed service, gateway, database or fixture was started
or changed by this audit.
