# P06R — compound objects and fences

Owner authorized this card on 2026-10-13 after accepting P06Q tree fall and
passage. Base: main `90c7a1d92a67be2acf2d02ab9a5720a377c9f2c8`.
Branch: `codex/p06r-compound-destructibles`.

## Goal

Extend the accepted cumulative Prohorovka destruction path to original
compound objects/fences with source-bound part identities. Each eligible part
must retain server-owned health and contact policy, matching projectile and
movement geometry, ACK-gated collision transitions and native state in both
clients. Preserve trees, whole fragiles, transport, driving and combat.

## Sequence

1. Inventory excluded original map objects by destructible family and reason;
   inspect pinned #717 descriptors, BSP materials, part IDs, native registration
   and state packing. Record VERIFIED/OBSERVED/INFERRED/UNKNOWN separately.
2. Define the smallest complete source-backed part/state contract. Document
   remaining unsupported object classes; never remove an entire compound
   collider when only one original part should be removed.
3. Implement a bounded versioned importer/catalog and part-aware runtime and
   physics transition as the evidence requires. Preserve previous schemas and
   pin each new artifact. Reuse accepted ACK/restore/rejoin boundaries.
4. Check source joins, repeated/partial damage, adjacent surviving parts,
   mass/speed contact thresholds, projectile behavior, two-worker atomicity,
   malformed catalogs, stale identities and cumulative native packing.
5. Run applicable automatic tests and bounded private physics diagnostics.
   Prepare a reviewable native owner scenario with exact target identities,
   supported coverage, launch/cleanup commands and pinned rollback artifacts.
6. Actual native visuals and passage require owner acceptance. Until then
   retain the card branch; no full native PASS or merge. After acceptance and
   required checks use standing no-ff merge/push and verify remote SHA.

## Paths and ownership

Original `C:\WoT_0.9.1_RU_0717_original` is read-only; configured research and
owned A/B copies remain under `D:\WoT_9.1_Server`. Local outputs:
`local/evidence/20261013-p06r-compound-01/` and fresh `local/build/server/`.
Code scope: resource import/probe tools and tests, existing gateway
destructible/state/wire/worker boundary, physics component. No unrelated
projects, accounts, or external game servers. Preserve unrelated dirty P09B.
Parallel initial tasks are read-only analysis with separate private evidence;
agree schemas before disjoint implementation work.

## First source-backed slice and capacity boundary

Inventory established 403 complete movement-only fence instances. Implement
these first, preserving the accepted 635 P06Q rows (1038 total). Source-based
admission excludes replacement visuals and mixed BSP materials. A fresh native
probe needs 119 chunks and two stable passes on both copies; old 117-chunk
exports cannot close this join. Compound modules remain in this card's research
scope until native collision semantics support a safe part transition.

Owner raised 100-battle scaling during implementation. Record the current
per-actor physics-process duplication and a bounded two-worker measurement.
Do not claim production capacity or silently replace the physical-world
ownership model inside P06R. Static fences have no independent simulation
loop; per-battle damage state must remain isolated. A future one-world-per-battle
and immutable map-resource reuse change requires its own measured card.

## Owner priority update — 2026-10-13

Owner observed fences breaking but the tank stopping when driving along a
chain of sections; other object classes remained intact. This is a partial
native failure, not full P06R acceptance. Prioritize one tank's measurable
movement/contact behavior before widening destruction coverage: retain impacts
across asynchronous worker replies; test chain contacts, speed loss and
remaining collision; preserve mass/speed dependence and both-worker ACKs.
Use the second native client to check replication, not to multiply the primary
physics scenarios. Do not claim "ideal" handling without defined tolerances.

Owner also requested IS-7 as the contrasting vehicle and two parallel service
sessions. The queued [IS-7 runtime card](P03M_IS7_RUNTIME_PROFILE.md) builds on
the accepted hangar inventory and P03I static boundary, without reimplementing
either. Separate crew/equipment and ammo/service chats own isolated worktrees
and domain components; P06R owns movement, gateway and physics integration.
Their tests do not by themselves authorize native acceptance or runtime wiring.

## Fence-chain response implementation — 2026-10-13

The close-joint private reproduction binds objects 3307/3308: the first hit
has 37.17 kJ, but the static solver removes almost all speed before the
gateway can remove the fence. The next hit has only 3.82 kJ. Fix this at
contact resolution, with an explicitly approximate, versioned test_lab
policy; do not refund pre-impact velocity after the solver has hit a wall.

Worker catalog v5 / IPC5 will reserve 8000 J per admitted movement-only
fence in the actual hull-contact order. Each substep owns a shadow velocity
budget; repeated manifolds cannot debit the same object twice. Only reserved
contacts become sensors. After the solver, the reducer can only decrease the
positive velocity component along each admitted contact normal. Rigid walls,
terrain and unadmitted contacts retain their ordinary collision response.
An inline single-concurrency callback job system must be proved against the
pinned native library before it is used; numThreads=0 is not assumed serial.

The worker returns an explicit prepared result with bounded fracture receipts
and the original scene identity. It cannot advance again until a cumulative
scene commit includes every prepared removal. The gateway validates receipts,
stages poses and domain changes, then publishes only after both workers ACK.
Any inconsistent receipt, omitted removal, worker loss or stale identity stops
the battle; no incomplete physical rollback is claimed. Concurrent actors
may each spend their own contact energy in this discrete test_lab model;
the shared object transition/native publication still occurs only once.

Checks precede the owner drive: real Jolt close-joint and straight chains,
mass/speed threshold and loss, repeated-contact energy accounting, rigid wall
immediately behind a fence, repeatability on this pinned Windows build,
receipt corruption, stale/omitted commits and both-worker publication barriers.
The old catalog/IPC modes and accepted tree path remain separately testable.
Only after automatic checks pass is the native owner stand prepared. IS-7
runtime work follows that fence check in the owner's requested order.

Native preparation exposed a second owned chat using the same v1 A mutex.
Keep that chat running. Add a backwards-compatible, four-character namespace
to the existing two-string instance patch, prove exact EXE-byte scope and
strict marker validation, and migrate only stopped root A/B copies with
before/after hashes and restore receipts. Do not release another process's
mutex or bypass launch guards. Retry on fresh run fencechain02.

## Limits and rollback

Original descriptors alone do not prove historical damage/ram formulas.
Unknown formulas retain explicit approximate test_lab policy. Unmapped or
ambiguous parts fail admission with coverage reasons rather than fabricated
indices or broad collision deletion. Do not infer native acceptance from
unit tests or mutate the client to force an effect.

Stop only receipt-identified owned processes and restore install ledgers.
P06Q source and retained build35/physics-p06q-final-02 are the rollback basis;
verify their pins before a relaunch. Source rollback is a reviewed revert,
never reset unrelated work. Evidence and prior failure receipts are retained.
