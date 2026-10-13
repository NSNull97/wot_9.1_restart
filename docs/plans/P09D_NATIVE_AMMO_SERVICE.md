# P09D — native hangar ammunition service

Date: 2026-10-13. Owner directly requested real MS-1/IS-7 ammunition changes
and replenishment in the live native hangar, with real-client verification.
Branch `codex/p09d-native-ammo-service` depends on isolated P09C commit
`7fb0e479dce684af0940fe37e5798d54d1c1e7fd` (accepted main ancestor
`90c7a1d92a67be2acf2d02ab9a5720a377c9f2c8`). This deliberately stacked
integration branch preserves the independent P09C handoff; no main switch or
parallel primary checkout mutation. P06R and queued P03M remain separate work.

## Scope and permissions

Reuse the managed P09C worktree, all new evidence/DB/build output inside its
ignored local directory. Original root from existing config is
`C:\WoT_0.9.1_RU_0717_original`, read-only. Existing configured owned copies and
launch/rollback ledgers must be inspected before any approved copy mutation.
The new explicit owner request authorizes the required native service/client
integration and real client test; it does not authorize changes to the original
client, unrelated running games, physics, ballistics, damage, crew or equipment.
Do not touch the primary checkout's dirty P09B research.

## Sequence

1. Source-audit original CMD108 request, TechnicalMaintenance UI, response,
   AccountSyncData refresh, shells/layout/depot projection and native callbacks.
   Preserve VERIFIED/OBSERVED/INFERRED/UNKNOWN classifications and exact pins.
2. Add a narrow opt-in service to the existing authoritative game DB and
   authenticated identity bridge, reusing P09C transaction policy and shared
   ledger. No independent authoritative sidecar store; migration, projection,
   commit, replay and rollback must be versioned and tested together.
3. Decode only supported native layout shapes. Identity comes from the admitted
   session. Validate the entire envelope and use durable idempotency before
   exposing success. Return genuine state updates through native mechanisms.
4. Expose the native maintenance window for supported mounts. Keep repair,
   equipment changes and unverified purchases explicitly unsupported. An
   explicit journaled test_lab depot grant may provision isolated test stock;
   it is never a historical initial loadout or a free purchase implementation.
5. Run targeted negative, persistence/restart and protocol checks. Build the
   isolated gateway and prepare a receipt-owned local native stand. Exercise
   both vehicles in the original UI, preserve callback/wire/DB/screenshot proof,
   repeat login, and verify rollback/rejection. Restore diagnostic installs.

## Acceptance

Actual native service actions for both mounts change server-owned shell loads,
return unloaded rounds to owned depot, and persist across a new login. Replays
must not double debit; foreign/stale/overflow/incompatible/insufficient inputs
must preserve prior state. Native/UI claims need actual evidence, not mock or
codec round-trip. If a necessary native gate cannot run, report NOT_RUN and
retain the branch rather than claiming live completion.

## Risks and rollback

The current deployed profile4 is immutable and P09C test schema is not its
migration. A new projection must not silently invalidate existing profiles or
pretend the accepted MS-1 battle adapter supports it. Native request semantics,
full sync/update ordering and migration compatibility are research gates.
Use consistent DB backups and immutable fixture versions; rollback the exact
owned stand/install receipts and revert this card's commits. No automatic
rollback over a shared database. Financial rates and battle-consumption wiring
remain outside this service card unless independently established and required.
