# P04G — native cross-vehicle crew reassignment

2026-10-13. Owner asks for the second tank and crew reassignment between the
two through the original interface. One card, branch
`codex/p04g-native-cross-vehicle-crew`, accepted main
`83fecd563a9edc7dd13cdab56f3846e59673140b`.

## Ownership and scope

Reuse owned worktree
`C:/Users/NSNull/.codex/worktrees/crew-equipment-snapshot/WoT_9.1_Server`.
Original `C:/WoT_0.9.1_RU_0717_original` remains read-only. Only the independently
owned `local/clients/p04d-b`, isolated preferences, fresh owned DB copies and
receipt-owned processes may be used. No deployment/change to primary P05 or
sibling stands. Evidence: `local/evidence/20261013-p04g-cross-vehicle-crew-01`.

Use the already imported MS-1 and IS-7 vehicles, native IDs1/2. Source-verify
IS-7 seat roles, original cross-vehicle validators, specialization handling and
inventory update semantics before enabling the profile. Preserve the existing
three MS-1-trained crew identities/descriptors, ammunition, balances and quota.
No fictional IS-7 passports or silently retrained tankmen. Runtime battle
admission, skills, retraining, paid tariffs and handling remain separate.

## Steps

1. Pin #717 original rosters and original UI/processor cross-vehicle paths.
   Record VERIFIED/OBSERVED/INFERRED/UNKNOWN. Resolve native warnings/selection
   requirements through original behavior, never by bypassing validators.
2. Add a versioned profile7-to8 migration and general two-vehicle assignment
   projection over the existing sole authoritative writer/domain planner.
   Validate owned source and target availability, compatible main role, unique
   seat, capacity, revision and replay. Atomically update both vehicle crew
   lists and tankman-to-vehicle bindings without changing training descriptors.
3. Extend bounded gateway/bridge policy with explicit opt-in; keep default and
   earlier profiles unchanged. Original CMD105 remains the researched command.
4. Add finite native scenario through original Crew/TankCarousel callbacks and
   passive Account/cache observers. Cover source-unload then barracks-to-target
   movement in both directions (the original dropdown excludes seated crew),
   occupied-seat replacement, whole-crew unloading and persistence of partial
   crews. Freeze the exact sequence with the independent verifier before run.
5. Run applicable domain/store/projection/client/source/web tests, full Rust,
   actual CPython2.7 compilation and layout checks on final sources. Negative
   cases include wrong role/nation/vehicle/owner, reserved source/target, stale
   commands, ambiguous replay, rollback and simultaneous assignment conflicts.
6. Use a fresh copy of the accepted P04F DB and actual original #717 client.
   Independently correlate raw commands, both-vehicle deltas, ledger/state,
   original callbacks and actual PNGs. Restart client/bridge/gateway and verify
   exact identities/descriptors/assignments and unchanged non-login tables.
7. Restore own installations, stop owned processes, update STATUS/research/
   evidence. Commit, ordinary no-ff merge/push and remote-SHA verification only
   after all declared applicable gates pass.

## Acceptance and rollback

PASS_NATIVE_CROSS_VEHICLE_CREW_CURRENT_MAIN. Native01/02 pass14 original
operations plus fresh login; final MS-1 `[None,2]`, IS-7 `[1,None,None,None,None]`.
Independent wire/durable audit, four inspected PNGs, current-source gates and
restoration all pass. [Final evidence](../evidence-index/P04G_NATIVE_CROSS_VEHICLE_CREW.md).
Existing synthetic generic-planner tests are not native evidence.
This card's gate uses actual original callbacks, network/state/pixels and fresh
process login; physical mouse/manual owner input is separately NOT_RUN unless
performed. Cross-specialization combat formulas are UNKNOWN until researched
and are not accepted merely because native UI renders a modifier.

Every accepted movement leaves the source seat empty, preserves any displaced
tankman in barracks and retains all IDs/descriptors. Rejected operations cannot
change either vehicle or authoritative revision/ledger. Final partial crews
must survive fresh login. Earlier profile behavior must remain passing.

Rollback: restore only owned installs via their ledgers, stop only receipt-
verified processes, preserve new and predecessor DBs. Older writers must reject
the new schema. Code rollback uses `git revert -m 1 <P04G-main-merge>` with a
matching predecessor DB/profile on our own stand. Required FAIL/NOT_RUN means
HOLD on this branch. Next crew step: native recruitment for every required
primary role of the two verified rosters, enabling a complete IS-7 crew.

## Owner note for the later perk card

2026-10-13 VERIFIED owner decision: Sixth Sense (the lamp) is a base perk,
always active without learning, including a crew at 50% training. Its activation
must not depend on perk XP or crew training percentage. This explicit project
rule overrides historical learning prerequisites for that future feature.
Timing/reset/display details are not changed or inferred by this decision.
Implement in the later perk card, not in P04G.
