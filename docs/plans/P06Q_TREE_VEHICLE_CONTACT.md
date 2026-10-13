# P06Q — vehicle contact and falling trees

Current completion (2026-10-13): owner accepted corrected native tree fall in
both clients and passage in `treeobserve10`. Applicable automated checks and
environment repair pass; clients/server stopped and ledgers restored. Final
branch is `codex/p06q-tree-visual-sync`. See [closeout evidence and remaining
limits](../research/P06Q_ACCEPTANCE_ENVIRONMENT_REPAIR.md). Pending/FAIL wording
below describes earlier checkpoints rather than the current gate.

Base: accepted main52978a25c63d51a56be90054c449b281cc4d3e3d (P06P).
Branch: codex/p06q-tree-vehicle-contact. Owner authorized the next tree card
and reported that driving into obstacles never destroys them.

## Goal

On the cumulative Prohorovka runtime, authoritative vehicle contact destroys
eligible whole fragiles and fells original trees. Both original clients show
the same event and the physical passage agrees with the committed scene.
Retain accepted driving/aim/RMB/ammo/reload/world/live/wreck behavior.

## Work

1. Pin original tree descriptors, native IDs, fallenTrees encoding and runtime
   callback semantics. Record unknown historical contact/damage rules.
2. Extend the resource-driven importer and bounded versioned catalog to trees;
   preserve source instance/matrix/native-index binding and collision masks.
3. Report real vehicle/object contacts from private physics through bounded,
   versioned IPC. Server selects an explicit approximate test_lab policy.
4. Stage immutable destruction/fall records; both workers acknowledge matching
   collision removal before world commit and native cumulative publication.
5. Run relevant unit/negative/import/private physics and canonical build checks.
6. Prepare and launch both approved clients on the accumulated Prohorovka stack;
   owner checks ramming, tree fall, both-client agreement and prior gameplay.
7. Only after required evidence and owner acceptance: ordinary no-ff merge,
   push and remote SHA verification under standing authorization.

## Boundaries and parallel ownership

Root owns World/catalog state, transactions, gateway integration and reports.
Physics worktree owns C# and Rust worker IPC; importer worktree owns Python
import/probe; native worktree owns original tree wire/callback research.
Agree shared schemas before parallel implementation. Original client resources
are read-only; installations use existing owned local/clients/p03f/a,b ledgers.
Evidence: local/evidence/20261012-p06q-tree-contact-01/.

No historical kinetic damage formula is inferred from descriptor health alone.
Native tree mask128 excludes tree faces: do not silently change projectile
behavior to make ramming work. Compound buildings/fences need separate coverage.
Explicit bounds must reject overflow, never silently drop catalog or state.

## Verification and rollback

Test contact identity, scene/map/generation mismatch, repeated contacts,
stationary ground contact, simultaneous contacts, ACK failure, restore and
native cumulative state without replay. Real physics must block before contact
and permit passage after the committed transition. Native/owner gates remain
NOT_RUN until observed, regardless of unit results.

Rollback: stop only verified owned P06Q processes and restore installation
ledgers. The accepted P06P commit remains the source rollback point; retain the
P06Q branch and all evidence. A physical P06P relaunch is **NOT_RUN**: the
gateway03 executable is present and hash-matched, but physics01/pool-near are
absent from the empty `local/build/server/physics-integrated-p06p-01/` directory.
Restore and verify the historical pinned artifacts before relaunch; do not
substitute current P06Q physics bytes. See the [rollback availability check
and pins](../research/P06Q_TREE_VEHICLE_CONTACT.md#rollback).
Until owner acceptance P06Q remains in its branch; no merge is implied.

## Measured zero-pitch correction — 2026-10-13

`treeobserve07` reaches the original animator with `pitchConstr=0`, so its
maximum rotation remains upright. The pinned original animator uses pi/2 as
the no-ground fallback; terrain-derived constraints can differ from pi/2.
Use a named pi/2 **test_lab flat-ground fallback** in authoritative ram events
until server-side tree root/height and terrain sampling are available. This
does not claim original slope or obstacle fidelity. Preserve mass/closing
speed, direction/speed packing, immutable publication and worker ACK ordering.

Add a domain regression that decodes the emitted native pitch independently
and checks native index, direction, speed and repeated contacts. Run the
fragile/contact and catalog/transaction tests, save build receipts and the
original animator provenance in research. Tree pixels and passage remain an
owner gate. The owner's latest run09 observation is visual FAIL despite
apparently stable sessions; do not mark this new correction native-accepted.
