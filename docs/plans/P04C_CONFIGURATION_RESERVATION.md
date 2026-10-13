# P04C — source-mass-backed crew/equipment and ammunition reservation

2026-10-13. Owner requested the next integration step after P04B. Reuse the
managed crew worktree on `codex/p04c-configuration-reservation`. Parallel main
remains on P06R; native ammo/hangar wiring is actively owned by P09D and runtime
IS-7 integration by P03M. Do not compete for installations or live databases.

## Dependency stack and allowed files

Base main is still `90c7a1d92a67be2acf2d02ab9a5720a377c9f2c8`. Keep P04B
`20b5d523cc3d8dbc99f1accef199fa8f390f785a`, and cherry-pick the frozen P09C
`7fb0e479dce684af0940fe37e5798d54d1c1e7fd` into this isolated integration
branch (local equivalent `85c4710`; only additive STATUS conflict resolved).
Neither dependency runtime source is edited. This explicit dependency stack
avoids changing main while the owner-requested parallel integration continues.

New namespaced `tools/crew_equipment_mass.py`,
`tools/crew_configuration_store.py`, their tests, a local harness, this card's
docs/index/STATUS. Reuse P09B/P09C SQLite connection, aggregate, revision and
ledger, without a second persistence engine or modifying ammo semantics.
All new DB/evidence below this worktree's `local/evidence/`.

## One acceptance slice

1. Verify exact stock mounted assemblies in #717, pin all seven contributing
   component masses and chassis maxLoad, produce a deterministic assembly
   identity and genuine P04B MassBudget. Unsupported assembly/source rejects.
2. Add a same-database configuration extension to the existing P09C store.
   Initialize explicitly isolated test records, preserve ownership and mount
   bindings, reject duplicate assigned crew across vehicles. Fixture creation
   is not a native grant or an equipment-purchase command.
3. One `BEGIN IMMEDIATE` admission transaction checks authenticated subject,
   current aggregate revision, configuration digest, actual mounted assembly,
   source policy, crew/equipment and loaded ammo, then freezes their exact bytes
   with reservation, aggregate revision and shared ledger. No second ammo debit.
   Disable the inherited unauthenticated reservation bypass.
4. Replay returns the original frozen reservation after reopening and later
   changes to a different vehicle. Wrong owner/payload/revision/mount, missing
   config/ammo, overweight setup, corrupt state and injected failures reject
   atomically. Run real separate-connection races against ammo servicing.
5. Preserve evidence and commit the card, with source and dependency SHAs.

## Acceptance and limits

`PASS_SOURCE_BOUND_CONFIGURATION_RESERVATION` requires real source audits,
real isolated SQLite commit/reopen/replay/rollback/race tests, applicable P04B /
P09C / P09B regressions and a clean current-head handoff. Snapshot config revision
and shared aggregate revision are explicitly separate fields. Native/gameplay
admission, live deployment, account grants, inventory purchases, release and
post-battle consumption remain separate integration work; do not label isolated
SQLite success as network-game acceptance. Whole-card native gate is NOT_RUN.

Rollback: revert only the new P04C commit; no deployment/client rollback is
needed. Keep P04B and P09C dependency commits distinct for integration review.
