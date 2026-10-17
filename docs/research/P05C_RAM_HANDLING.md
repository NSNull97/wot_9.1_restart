# P05C software-only handling and tank ram checkpoint

## Result

Branch `codex/p05c-ram-handling` is based on `f704927`, the P05C/P07B-compatible
P04M follow-up matrix checkpoint.  The software change adds the bounded handling
repair and the authoritative tank-contact path; it does not grant owner/native
admission to T-26, T-34, or T-34-85.

The physics policy now keeps a powered turn moving on a grade by reducing outer
scrub and retaining a minimum inner-track ratio.  A released moving turn enters
the stronger clutch/brake hand-off only near the pivot window.  During a hull
contact, a forward-commanding pusher has only its negative forward velocity
component removed after the Jolt step; lateral and vertical solver velocity is
preserved.

IPC7 tank contacts are materialized as typed rows with sorted unique pair
validation.  `World::apply_tank_contacts` resolves the explicit
`test_lab-tank-ram-energy-v1` energy policy from source-bound masses and worker
relative velocity, records both health transitions, and arms a pair again only
after a frame without that pair.  Separating, tangent, resting, malformed, and
duplicate contacts fail closed or produce no damage.

## Matrix and evidence

The five source profiles are guarded by `tools/p05c_followup_matrix.py`.  The
matrix now has single, ordered pair, mixed 3, mixed 4, all-5, and max-6 filters;
all cases keep `native=NOT_RUN` and `worker_result=NOT_RUN` until an actual IPC7
receipt is attached.  Evidence outputs are under
`local/evidence/20261018-p05c-ram-handling-01/`.

## Validation

- `python -B -X utf8 -m unittest discover -s tests -p 'test_p05c_followup_matrix.py' -v` — **PASS**, 13 tests.
- `python -B -X utf8 tools/p05c_followup_matrix.py --out local/evidence/20261018-p05c-ram-handling-01/matrix-all.json --filter all` — **PASS_MATRIX_PROFILE_GUARDS**, 270 cases.
- The same tool with `--filter single --scenario flat_straight` — **PASS_MATRIX_PROFILE_GUARDS**, 5 cases.
- The same tool with `--filter mixed-3 --scenario contact_head_on` — **PASS_MATRIX_PROFILE_GUARDS**, 5 cases.
- `python -B -X utf8 server/build.py physics --out local/build/server/p05c-ram-handling-physics03` — **PASS_ISOLATED_BUILD**; DLL SHA256 `2facab87e1c27a4068a6f7633f87b31f45fd7e31118ca7b07412f22ea1734d47`.
- Pinned Rust gateway test/build — **NOT_RUN**: the required local Rust 1.90.0 Windows GNU toolchain is absent on this host.

Native client, UI, manual owner, two-PC, real worker mixed-contact, and
historical-equivalence checks remain **NOT_RUN**.  The static Python matrix is
not a physics simulation and the physics build is a compile gate only.

## Rollback and acceptance

Revert the P05C card commits on `codex/p05c-ram-handling`; no client resources,
secrets, or retained historical evidence were changed.  Status is
`PASS_AUTOMATIC_SOFTWARE / GATEWAY_NOT_RUN / NATIVE_OWNER_NOT_RUN /
HISTORICAL_EQUIVALENCE_UNKNOWN`.  The single next step is to run the pinned
gateway suite and a real IPC7 mixed-contact receipt on a host with the verified
Rust toolchain, then review the receipt before any native owner test.
