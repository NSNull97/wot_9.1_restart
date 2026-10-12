# P06Q — vehicle contact and falling trees

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

Rollback: stop only verified owned P06Q processes, restore installation ledgers,
relaunch retained accepted P06P gateway03 / physics01 / pool-near / catalog.
Until acceptance P06Q remains in its branch; main P06P stays available.
