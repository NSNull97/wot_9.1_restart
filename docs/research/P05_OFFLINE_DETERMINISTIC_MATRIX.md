# P05 — offline deterministic movement matrix

Status: **PASS_OFFLINE_DETERMINISTIC_MATRIX / NATIVE_RECONCILIATION_NOT_RUN**.

This is a bounded test-lab worker receipt for the next P05 slice. It exercises
the existing documented domain JSONL contract on two hash-pinned map fragments;
it does not claim historical World of Tanks physics or native-client
compatibility.

## What was run

The pinned `MapDriveWorker.exe` was launched directly for the existing worker
contract. Each map received the same 160-command sequence:

`neutral → forward → brake → reverse → forward_left → forward_right → stop →
steering_left → neutral_2 → steering_right`.

The worker settled for 180 ticks, then produced one ready event and one state
event per command. Both runs returned code 0, had finite state, monotonic
sequence/tick prefixes, and no stderr errors.

| Map | Config SHA-256 | Commands | Events | Tick range | Contacts | Result SHA-256 |
|---|---|---:|---:|---|---|---|
| `01_karelia` | `841ca209675dac6b8135d109b93526d5aa57650bed7e27443d4724de9dbe33a7` | 160 | 161 | 180 → 1140 | 2 → 6 | `a59aa3ce9fa713c3551a0ef0ed170baaf04f4f1707306ab55e863b54fa8f6677` |
| `05_prohorovka` | `7242ba3e804f191f44e2a09c716f1f2b495a0fe6295190f0e84ce694468e1f17` | 160 | 161 | 180 → 1140 | 3 → 6 | `9f9e4e3f21c6f00ea053d64cb53af421df20ecef36d1f6f6715a896eb83daa7d` |

The summary receipt is
`local/evidence/20261009-p05-deterministic-matrix-01/summary.json`, SHA-256
`ebaa38d47673d331464f9628a7ecf9ae3e9729479826c82d2ccd28ec494677aa`.
The worker manifest is hash-bound at
`local/server/map-drive/worker-v1-manifest.json`, SHA-256
`2ceb5811c0e7d199b43bf27606ce6411cf7f56a061dc763170d32dcdce7277e9`.

The earlier bounded pivot receipts are retained alongside this matrix:
`local/evidence/20261009-p05-offline-matrix-probe-01/result.json` and
`local/evidence/20261009-p05-offline-matrix-prohorovka-01/result.json`.
They report `PASS_OFFLINE_PIVOT_DIAGNOSTICS`, six or five-to-six contacts and
reverse-speed ranges, while leaving engine RPM, track speeds, gear/clutch and
delivered torque explicitly unknown.

## Interpretation and boundary

`PASS_OFFLINE_DETERMINISTIC_MATRIX` proves only that the pinned worker accepts
the bounded command sequence and emits finite, ordered state on these two test
lab fragments. It does not prove collision causality, map destruction, tank–tank
interaction, client prediction/correction, rejoin reconciliation, historical
track/engine physics, native movement, or owner acceptance. The worker's
diagnostics still lack engine RPM, per-track speed, gear/clutch and delivered
torque, so those fields remain `UNKNOWN_NOT_IN_WORKER_STATE`.

No client, deployed service, database, gateway or original/research copy was
started or modified. The next gate remains an owner-gated native movement and
reconciliation capture after the offline inputs are reviewed; do not tune the
controller from these receipts alone.

