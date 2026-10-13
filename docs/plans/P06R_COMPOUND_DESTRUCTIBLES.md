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
