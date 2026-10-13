# P09C — isolated ammunition service

Date: 2026-10-13. Base: accepted main
`90c7a1d92a67be2acf2d02ab9a5720a377c9f2c8`.
Branch: `codex/p09c-ammo-service`. Parallel handoff only; no merge or main change.

## Goal and existing boundary

P02 already granted and verified 20 MS-1 AP shells in an immutable profile4;
P03I and the battle adapter define static/native and admission boundaries.
P09B already owns an isolated SQLite reservation/revision/command ledger.
The missing slice is a source-bound MS-1/IS-7 ammunition selection and atomic,
idempotent service command transferring owned shells between depot and tank.
This card extends the existing harness, without a second persistence system.

## Permitted paths and scope

New namespaced `tools/p09c_*`, `tests/test_p09c_*`, this plan, one research
contract, one evidence index, and a prepend to this worktree's STATUS only.
All new DB/evidence under this worktree's ignored `local/evidence/`.
Read-only original client resolved through existing main checkout configuration;
read-only historical evidence under `D:\WoT_9.1_Server\local` is allowed.
Do not change primary checkout, its dirty P09B research, live DB/services,
client installations, shared loadout, gateway, physics, transport, combat,
crew/equipment, or UI. No copied client resources committed.

## Execution

1. Verify original #717 resource hashes and mounted gun-specific capacity and
   shell IDs, reusing bounded packed XML tooling. Separate VERIFIED source
   facts from UNKNOWN native IS-7 export and service wire semantics.
2. Implement a versioned catalogue and narrow domain service on the existing
   P09B connection, revision, reservation and ledger interfaces. Absolute desired
   quantities consume only already-owned test depot shells and return unloaded
   shells. Purchasing remains explicitly unsupported; no invented prices.
3. Test actual isolated SQLite commit/reopen/replay, stale/foreign/incompatible/
   overflow/insufficient/reserved rejection, duplicate mismatch, rollback at
   pre-commit boundaries, and interaction with P09B reservation.
4. Reverify source pins, save bounded local evidence, update research/STATUS,
   review allowlist and commit the tested branch for integration.

## Acceptance and integration boundary

`PASS_P09C_ISOLATED_AMMO_SERVICE` requires source audit and applicable automatic
tests on the current code. Runtime wiring, actual native service/IS-7 loadout,
prices, repair, consumables, battle consumption and financial ledger are
NOT_RUN/UNKNOWN and outside this acceptance. Isolated tests never imply a
working network game. Repair and consumables get dependency coverage only.

## Rollback and risks

Revert this card commit; retain/delete only its own isolated DB/evidence as
needed. No deployed migration or client rollback is involved. Source mismatch
must reject catalogue activation. An extension of the P09B test schema is not
a deployed migration. Authenticated subject is a trusted caller input, not an
authentication implementation. Native compact IDs belong only to the catalogue
adapter, not command policy, physics or economy.
