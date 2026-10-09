# P06G — server-owned impact trace invariant hardening

## Goal

Close the narrow invariant gaps found during the P06C read-only review before
any native collision capture: a launch must belong to the admission slot and
the same server tick, same-tick and delayed two-actor launches must retain a
deterministic ordered trace, and rejected `World::apply`/`advance` operations
must publish no partial projectile or trace state.

## Scope

- `server/gateway/src/shared/impact.rs` and `model.rs` only, plus focused tests
  and evidence/docs;
- no geometry, BSP2, transforms, penetration, damage, HP, module/crew logic,
  client resources, deployed service or native runtime capture;
- preserve the existing flight-only boundary and explicit
  `native_impact_status=NOT_RUN`.

## Acceptance

- `Trace::launch` binds projectile slot and launch tick to its admission;
- same-tick and staggered two-actor launches produce complete ordered traces;
- invalid apply/advance and direct rejected trace calls are byte-for-byte
  equivalent by `PartialEq` to their pre-call state;
- deterministic 40-shot flight cadence stays within `MAX_EVENTS`, with every
  order present exactly once;
- targeted Rust tests, full gateway Rust tests and source-layout gate pass.

## Rollback

Revert the single merge commit. No client, package, service or runtime state
is changed by this card.
