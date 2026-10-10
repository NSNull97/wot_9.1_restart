# P06I — measured MS-1 geometry in the integrated world

## Goal

Bind hash-pinned #717 MS-1 collision geometry to server-owned chassis, turret
and gun poses in the accepted P03L integrated world. Observe and stop a native
tracer at the nearest measured geometric contact, with ammunition/reload/aim
and worker physics preserved. No penetration, HP, crew or module damage.

## Preconditions and scope

- Base: accepted `cb8125f` (P06H offline query/trace) and P03L run27 owner receipt.
- Read only the configured research client and approved isolated local copies;
  original client, canonical service and unrelated projects stay untouched.
- Use existing P06F pinned descriptor/package/member checks. Extracted vertex
  data and native oracle output remain under ignored `local/`.
- Establish component transforms from #717 source and independent native Math
  and hit-tester observations before enabling the new geometry path.
- Keep current integrated physics/startup/session/authentication behavior;
  expose geometry binding explicitly as an optional verified input to that path.
- Query the other actor only. Publish ordered, versioned geometry/pose/segment
  evidence and correlate the same shot ID/endpoint in both native clients.
- Stop at an unresolved geometric contact; do not infer armor outcome from
  a material name. Document approximation limits (static pose per tick,
  piecewise flight, absent terrain/obstacle projectile resolver).

## Execution

1. Audit chassis/component coordinate chain and native hit geometry behavior;
   capture independent transform samples with a bounded passive observer.
2. Add a local reproducible geometry bundle and bounded validated loader;
   bind its exact hash and schema to the experimental integrated startup.
3. Compose actor/component transforms, calculate other-actor intersections and
   atomically commit trace/contact/stop. Correct only measured launch-transform
   inconsistencies needed for correlation; preserve original wire ordering.
4. Check real 100ms full-ammo trace budget and late-peer tracer start/stop order.
5. Build/test, run both real clients on the cumulative integrated setup, and
   leave a concrete manual check ready for the owner.

## Acceptance

- pinned gateway build/suite, focused importer/observer checks and source layout;
- no unmeasured transform offsets, no client-authored pose/hit authority;
- malformed or mismatched geometry fails before battle; originals untouched;
- native oracle comparison for component positions/rotations and geometry;
- nearest other-actor contact, miss, self exclusion, atomic rollback, both
  shooter slots, full-ammo cadence and reliable start-before-stop verified;
- native shot ID/endpoint correlated with both real clients; owner visual
  regression of movement/aim/shooting is required before merging runtime changes.

If native geometry differs from primitive triangles, record it explicitly and
resolve or narrow the supported geometry using evidence; do not relabel that
gap as a native hit PASS. Required NOT_RUN leaves this card in its branch.

## Evidence and rollback

Use fresh runs under `local/evidence/20261010-p06i-native-collision-01/` and
isolated `local/build/server/` outputs. Version client diagnostic changes with
the existing prepare/install/rollback ledger on closed isolated copies.
Rollback the client ledger and restart the accepted P03L build/pool. Source
rollback is the card's revert; no canonical deployment is part of this card.

## Completed 2026-10-10

Acceptance: PASS_NATIVE_GEOMETRIC_CONTACT_AND_OWNER_RMB. Native01 provides
9 contacts / 18 exact client endpoints, both shooters and owner confirmation
“сейчас все нормально”. Final gateway03 passes 429 tests including the last
fractional range segment; native03 startup has two ready workers/clients and
532 snapshots per client without errors in the pinned prefix. Optional repeated
GUI shot NOT_RUN after screenshot timeout. Independent final review found no
additional owner test required for that bounded tail correction.

Native01 late StorageFull and failed native02 restart are retained as failures;
lossless compression allowed fresh native03 setup. Diagnostic runtime stopped
after audit to bound capture growth. See research/P06I_NATIVE_COLLISION_BINDING.md
and local/evidence/20261010-p06i-native-collision-01/summary.json for exact scope,
hashes, source identities and commands. Next card: measured material/contact
classification before damage, on this cumulative integrated runtime.
