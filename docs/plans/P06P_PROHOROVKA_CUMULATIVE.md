# P06P — Prohorovka on the accepted cumulative server

Base: accepted main `878ade656906918f2aa9c095621feb4f504be603` (P06O).
Branch: `codex/p06p-prohorovka-cumulative`.
Evidence: `local/evidence/20261012-p06p-prohorovka-01/`.

## Goal and dependency order

Owner requested continuing destruction/tree work and changing the laboratory
map to Prohorovka for more varied objects. This card makes Prohorovka a real
cumulative test map: accepted movement/aim/ammo/reload/projectiles, terrain and
obstacles, vehicle/wreck damage/effects, and source-driven fragile objects.
The original map-drive imports already exist, but shared battle/wire/projectile
and removal admission still bind Karelia. Resolve that prerequisite first.
Tree fall/state/collision semantics are researched in parallel, then implemented
as the next separately accepted card. Do not label static trees destructible.

## Work and gates

1. Pin original #717 Prohorovka package/arena identity, terrain surface/topology,
   physics mesh and immutable movement configuration. Read originals only.
2. Export projectile geometry using its original mask 128 and materials;
   never substitute the driving mask 18. Inventory destruction families and
   derive eligible whole-fragile objects by the existing geometry rule.
3. Bind one explicit map identity across native arena, World, physics pool,
   terrain/projectile sources, catalog, trace and restored scene. Reject mixed
   maps/hashes before entering a battle. Preserve the accepted Karelia path.
4. Generalize bounded catalog/worker/wire admission as supported by measured
   Prohorovka coverage. Report exclusions; never truncate to fit a limit or
   hand-pick individual instances. Verify native indices by original sources
   and a read-only preprocessing oracle as needed.
5. Exercise source and negative tests, both-map compatibility, actual private
   worker settling/movement/removal and both-worker commit barrier. Use only
   `server/build.py` with fresh pinned outputs. Keep existing movement tuning.
6. Launch approved native copies a/b sequentially on the cumulative candidate.
   Owner verifies grounded driving/tilt, aim/ammo/reload and both-client effects,
   ground/static cover, live/wreck and separate eligible fragile removals/passages.
   All results retain VERIFIED/OBSERVED/INFERRED/UNKNOWN distinctions.

## Ownership and restrictions

Root owns map selection/domain integration, launch, documentation and acceptance.
Separate worktrees own import/export, native wire/oracle research and physics
admission. Agree schema before overlapping changes; no shared branch switching.
Read configured original/research clients and existing source-pinned evidence.
Write only repository-owned source, ignored artifacts and approved laboratory
copies through versioned installers/ledgers. No original or neighboring edits.
Client observations never become authoritative hit/pose/destruction decisions.

## Acceptance, unknowns and rollback

PASS requires native Prohorovka and server physics/projectile/catalog to agree,
the accepted cumulative behavior to remain functional, and actual owner/native
evidence. Unit/build success alone is insufficient. Unsupported tree/compound
semantics and approximate test_lab damage/physics must remain explicit.
Mandatory FAIL/NOT_RUN keeps the card in its branch. After PASS, standing
authorization permits ordinary no-ff merge, push and remote SHA verification.

Rollback: retain accepted P06O gateway05, physics01/pool-near, source catalog,
launch receipts and installed diagnostic ledgers. Stop only identity-verified
own processes; restore lab ledgers and launch the accepted Karelia configuration.
Do not overwrite old evidence or binaries. One next gate: pinned Prohorovka
projectile export and a single consistent map binding contract.
