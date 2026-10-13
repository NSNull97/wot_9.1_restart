# P03M — second source-bound vehicle for movement and battle checks

Status: QUEUED_OWNER_PRIORITY; implementation/native admission NOT_RUN.
Owner requested playable IS-7 on 2026-10-13 to compare mass, speed and collision
behavior while prioritizing a reliable single-tank scenario on Prohorovka.
This is a new runtime card, not a repeat of accepted P02_test_is7 (hangar)
or P03I_VEHICLE_PROFILE_LOADOUT (static native queue boundary).

## Goal and dependencies

Use one authoritative movement/battle path for MS-1 and the exact #717 IS-7
configuration. A heavy visual model over the MS-1 mass, collider, HP or gun
does not satisfy the goal. First finish/review the current P06R contact loss
repair and chain-collision evidence; isolate the next runtime implementation
in its own codex/p03m-is7-runtime-profile branch from the accepted baseline.
If P06R remains pending, research and source contract work may proceed in an
isolated checkout without treating the pending runtime as accepted main.

## Sequence

1. Freshly pin original IS-7 descriptors/modules, assembled mass and dimensions,
   movement parameters, hull/turret/gun collision and native compact descriptor.
   Reuse existing imports; explicitly mark missing historical receipts.
2. Identify hard-coded MS-1 runtime values and introduce the smallest typed,
   immutable server-owned vehicle profile shared by spawn, physics, HP and gun.
   Keep source IDs separate from network indices and damage rules.
3. Use the parallel crew/equipment and ammo/service source contracts where
   verified. Select a bounded test_lab configuration with explicit provenance;
   no live inventory grants or production admission shortcuts are implied.
   Ordinary queue wiring still requires the real P03I framing gate.
4. Run the same deterministic movement cases for both vehicles: launch/stop,
   turn, slope, solid wall, one fragile, consecutive fragile sections and tree.
   Record acceleration, stopping distance, contact speed, source mass, pre/post
   impact speed, affected objects and both-worker scene ACKs. Establish explicit
   tolerances and classify approximate rules; no invented historical fidelity.
5. Validate malformed/mismatched profiles, unsupported modules, stale hashes,
   incompatible shells, independent loadouts, restore and existing MS-1 tests.
6. Prepare a source-pinned native owner run with rollback and confirm correct
   vehicle model, movement, fire, damage, visible destruction and replication.
   Native acceptance remains NOT_RUN until the actual owner's result.

## Parallel work boundaries

Crew/equipment chat: 01a134ec-781f-70a1-8970-4a978d2fff51.
Ammo/service chat: 01a134ec-7eca-7791-8d29-56bea40989c2.
Both start with existing-card audits and isolated domain components/worktrees.
They do not edit gateway/physics/shared loadout or live profiles while this
chat owns runtime integration. Each returns a tested commit, source pins,
explicit interface and remaining UNKNOWNs. Native installation is coordinated
only here. Do not duplicate P09B persistence or accepted MS-1 crew/ammunition.

## Paths, acceptance and rollback

Original C:\WoT_0.9.1_RU_0717_original is read-only. All private outputs under
the configured project local directory; no unrelated repositories/accounts.
One card/branch; applicable automatic tests plus native gate before merge.
Pin the accepted runtime first, use fresh versioned artifacts and receipt-owned
processes, restore client ledgers, revert only card commits when required.
