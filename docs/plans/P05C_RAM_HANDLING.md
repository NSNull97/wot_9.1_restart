# P05C software-only handling and tank-ram plan

## Goal

Repair the bounded shared-scene handling path on the P04M/P05C/P07B-compatible
base: preserve powered turns on uphill terrain, avoid braking a moving turn into
a dead stop, keep a forward-commanding IS-7 from snapping backwards while it is
physically pushing another actor, and carry an authoritative tank-to-tank ram
damage event into the domain with one hit per continuous contact pair.

## Scope

- `server/physics`: versioned handling/traction policy and bounded contact hold.
- `server/gateway/src/drive/scene_worker.rs`: typed IPC7 tank-contact rows.
- `server/gateway/src/shared/server_scene_runtime.rs` and `model.rs`: validated
  contact transfer and server-owned ram damage.
- automatic Rust/Python tests for the mixed five-profile roster/filter matrix
  and ram policy; existing native/UI/manual gates remain NOT_RUN.
- evidence under a fresh `local/evidence/20261018-p05c-ram-handling-01/` path.

## Policy boundaries

The ram damage equation is an explicit `test_lab` engineering policy. It uses
the source-bound masses and worker relative velocity after IPC validation; it is
not presented as a historical 0.9.1 damage formula. Contact damage is emitted
once when a sorted actor pair enters contact and is re-armed only after that pair
is absent from a later authoritative frame. Malformed or duplicated rows fail
the whole frame before mutation.

## Validation

Run targeted Rust tests and the pinned physics/gateway build drivers into fresh
output directories. Native two-client, UI, manual owner, and historical
equivalence checks are explicitly NOT_RUN in this card.

## Rollback

Revert the card commits on this branch. Do not alter client copies, retained
historical evidence, or `main`.
