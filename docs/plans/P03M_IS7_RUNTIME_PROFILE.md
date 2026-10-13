# P03M — second source-bound vehicle for movement and battle checks

Status: PASS_OWNER_IS7_PROFILE_SHARED_HANDLING_DEBT_OPEN.
Accepted base: P06R merge `eb054618bd0eae1ae23bba42a0f875969ac2d24e`, pushed
and remote SHA verified. Branch `codex/p03m-is7-runtime-profile`.
Owner requested playable IS-7 on 2026-10-13 to compare mass, speed and collision
behavior while prioritizing a reliable single-tank scenario on Prohorovka.
This is a new runtime card, not a repeat of accepted P02_test_is7 (hangar)
or P03I_VEHICLE_PROFILE_LOADOUT (static native queue boundary).

## Owner scope clarification — 2026-10-13

Owner explicitly accepts IS-7 and classifies the poor driving as the previously
deferred shared physics failure. Close this card for the source-bound playable
IS-7 profile, preserving the test_lab limits. General driving quality is not an
acceptance claim of this closure. The original sequence below is retained as
history; its broad handling gate is assigned to the existing
[P05 plan](P05_MOVEMENT_COLLISION_RECONCILIATION.md) by this clarification.
Weak pivot/car-like steering predates P03M; v2 forward-arc steering and reduced
lateral friction still need scrutiny and are not certified as correct.
Both clients/server/workers are stopped and client/namespace rollback passed.
Evidence: `local/evidence/20261013-p03m-is7-01/native-is7/is7run03-owner-final/receipt.json`.

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

### Bounded implementation contract — 2026-10-13

First playable slice is an explicitly selected homogeneous `test_lab` vehicle
kind for both actors: default MS-1 or IS-7. The exact original descriptor,
2150HP, assembled68190kg mass, source geometry and mounted S70/AP configuration
travel together in immutable typed profiles. IS-7 uses a temporary server-owned
30-round AP14602 loadout and mounted reload13.7s; APCR/HE remain unavailable.
This does not grant items, modify live accounts or claim ordinary selected-hangar
queue admission. Mixed-vehicle pools are rejected. Separate MS-1/IS-7 runs are
sufficient for the first comparison; mixed actors need their own bounded work.

Pool v2 binds a pinned physics profile and the full numerical config projection;
old pool v1 stays MS-1 only. Existing config hashes still bind worker startup.
Geometry/material bundle identity must match the selected kind. Native method
indices remain in adapters, never in physics. Preserve default MS-1 wrappers
and behavior. Existing Jolt control and AP single-plate approximation stay
explicit test_lab rules; no historical drivetrain/dispersion formula is claimed.

Disjoint worktrees at the accepted merge: gameplay/profile/model/aim/shot/wire;
physics importer/pool binding and private real-worker cases; collision/material
importer and bundle checks. Root owns server/CLI/impact/session integration,
acceptance docs and review. Source audits are under
`local/evidence/20261013-p03m-is7-01/`; original remains read-only.

Actual-worker testing exposed near-absent IS-7 turning on a clear source lane
with inherited lateral friction1.2. Preserved bounded comparisons led to
config2 with longitudinal/lateral friction1.2/.4 and powered finite-radius
steering ratio.2, motivated by verified source rotationIsAroundCenter=false.
V1 defaults remain unchanged; five old/new MS-1 trajectories match exactly.
All16 final IS-7 paired scenarios and8 MS-1 scenarios pass, plus actual config
rejections/traction cutoff/spawn checks. Steering asymmetry on the source slope
and fidelity to nominal28deg/s remain UNKNOWN. This is explicit approximate
test_lab control, never relabelled as original server physics.

Final canonical gateway05:676/676 PASS, including actual IS-7 runtime/domain/
both-worker ACK gating and source-geometry AP damage. Source/current-build
hashes, commands, failures, native run `is7run03` and rollback are retained in
[the P03M report](../research/P03M_IS7_RUNTIME_PROFILE.md). Native rendered
movement, gun/UI, destruction and owner handling acceptance remain NOT_RUN.
Fresh run03 passes two-client READY,120 original marker calls and six native
bbox comparisons. Two failed passive-observer setups were stopped/restored;
source-grounded indexed-vector correction passes24 tests and Python2.7.3.
These observations prepare the native owner gate; they do not close it.

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
