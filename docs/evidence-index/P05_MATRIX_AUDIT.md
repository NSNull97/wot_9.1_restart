# P05 movement-matrix receipt audit evidence index

Status: **PASS_OFFLINE_MATRIX_SHAPE_ONLY / NATIVE_RECONCILIATION_NOT_RUN**.

| Artifact | Result |
|---|---|
| `tools/movement_matrix_audit.py` | bounded summary/map auditor |
| `tests/test_movement_matrix_audit.py` | 14 targeted tests PASS |
| `local/evidence/20261009-p05-deterministic-matrix-01/summary.json` | audited, two pinned maps |
| `local/evidence/20261009-p05-deterministic-matrix-01/01_karelia.json` | audited, config SHA pinned |

The auditor enforces duplicate-key and non-finite JSON rejection, bounded
depth/size, map/config identity, command/event count, sequence/tick prefix and
phase order.  If a receipt includes an event trace, it additionally verifies
finite bounded pose vectors and rejects reordered/gapped sequence or ticks.
The existing aggregate receipt has no event-level poses; therefore the audit
reports `NOT_PRESENT_IN_AGGREGATE` rather than inventing pose evidence.

The result proves only receipt shape and test-lab summary integrity.  It does
not prove native movement, server authority over a client pose, historical
physics, collision causality, prediction/correction or rejoin behavior.

Rollback is a reviewed revert of the docs/tool/test commit.  No runtime or
client restoration is required.
