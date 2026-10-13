# P04D — native recruitment and assignment of one MS-1 tankman

2026-10-13. Owner authorized the proposed next slice with "погнали":
recruit one MS-1 tankman through the actual #717 client, assign to the
appropriate seat, persist and verify a new login. Skills, general retraining,
dismissal and broad economy remain separate cards.

## Scope, base and ownership

Branch codex/p04d-native-crew-recruitment in the existing managed crew
worktree, from 48ff5fa031ab272748e34b5cda62710e2a45db4f (P04C).
Accepted main remains 90c7a1d92a67be2acf2d02ab9a5720a377c9f2c8.
Keep the P04B/P09C/P04C dependency commits separately reviewable.

New explicit native-recruitment scope permits the necessary crew protocol,
identity-bridge, projection and client capability implementation in this
isolated worktree. It does not permit editing the parallel primary checkout,
P06R physics, P03M runtime or another chat's worktree/stand/database.
P09D is actively implementing native ammo persistence; inspect it read-only
and reuse a frozen checked dependency if appropriate rather than implementing
a competing game store. Record any additional dependency SHA before use.

Frozen handoff acquired during implementation: P09D
`db72382652ec18a475b3cf85a024dc78a7e13fe7`, local cherry-pick `b13ca5c`.
Only the additive STATUS history conflicted; both card sections were retained.
The dependency's native ammunition acceptance passed; its historical proof
portability regressions remain FAIL and hold main integration. This card does
not silently waive those failures or modify the sibling's running stand.

Read-only original is the configured C:\WoT_0.9.1_RU_0717_original.
Existing explicit configuration is D:\WoT_9.1_Server\config\project.local.json.
New outputs, databases, builds and any independently owned client copy stay
under this worktree's ignored local/. No experiment touches another running
client or the primary stand. Native installation must have owned-copy and
rollback receipts; do not overwrite shared preferences or launch ledgers.

## Sequence

1. Re-audit source hashes, native recruit/assignment commands, arguments,
   callbacks and inventory/cache update order. Inspect recruit UI costs and
   descriptor construction. Record VERIFIED/OBSERVED/INFERRED/UNKNOWN.
   Never substitute modern tariffs or treat the existing 100% test grant as
   historical recruitment.
2. Use native combined buy-and-equip CMD309 for a supported MS-1 slot.
   Tier0 is verified free; historical tier-to-level mapping and paid prices
   remain UNKNOWN. First profile is explicit test_lab free100/no-skills,
   consistent with existing project test crews, not historical pricing.
   Paid tiers must be honestly unavailable even though original RecruitWindow
   expects three tariff rows. Research the smallest truthful UI compatibility
   change before exposing the window.
3. Introduce mutable server-owned crew IDs/ownership/assignment using the
   existing game database and shared command ledger. Partial garage crews are
   representable; battle admission remains fail-closed. Reserved vehicles
   cannot change crew. A duplicate request cannot create a second tankman or
   debit twice. Update configuration revision where this path is integrated;
   do not mutate a persisted frozen reservation.
4. Implement only the verified native command, response and state projection.
   Lift only the capability restrictions satisfied by real server operations.
   Keep full PersonalCase and unrelated operations unavailable where required.
5. Test ownership, wrong seat/role, unsupported tariff, quota/funds,
   duplicate/replay, stale state, reservation and rollback using real SQLite.
   Test bounded native codec and shared gateway scheduling with no external
   mutation before full packet validation. Verify existing ammo/crew behavior.
6. Prepare an isolated receipt-owned native stand. Perform
   recruit -> assignment -> state update -> relogin through actual client
   mechanisms, collecting source/wire/callback/DB/visual evidence.
   Never replace real native acceptance with a synthetic round trip.
7. Update STATUS, research report, evidence index and current-head checks.
   Preserve a reviewed commit. A missing required native gate is NOT_RUN and
   leaves this card unmerged; do not claim the feature complete.

## Known implementation seams

P04C remains the strict battle configuration validator, with all seats,
100% healthy no-skills and immutable revision1. Garage inventory needs a
versioned mutable representation; do not weaken frozen battle snapshots.

P09D NativeAmmoStore already projects game_profiles from the shared aggregate,
but its current projection starts from immutable P02 crew. The compatible
crew extension must override/extend this single projection instead of writing
profile_json independently or creating another authoritative database.

The actual bridge is web/src/game-adapter.mjs. The opt-in replacement
server/identity/account_service.mjs is not the live native path.
Mutation dispatch must occur only after successful full Session::receive
validation, and retain ambiguous in-flight jobs across session retirement.

## Acceptance and rollback

One actual native recruitment produces a single server-owned tankman assigned
to the supported MS-1 seat. The same ID, descriptor and assignment survive
client/server restart and cached login. Wrong owner/role/price/state rejects
without mutation. All inventory, quota, profile and ledger changes are atomic.
Native tariffs, policy values and any limitations are explicit.

Rollback only receipt-owned installations/processes and this card's commits;
restore an isolated DB from its consistent pre-migration backup when necessary.
No automatic restore over another chat's or primary database.
