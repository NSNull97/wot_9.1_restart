# P04F — native crew unloading and reassignment

2026-10-13. The owner explicitly requested unloading and reassignment through
the original interface after accepted P04E. One card on branch
`codex/p04f-native-crew-transfer`, from main
`06582030050c7b6720f4616dffa50b2be61e4abc`.

## Ownership and scope

All writes/builds/database copies/native installations remain in the owned
`C:/Users/NSNull/.codex/worktrees/crew-equipment-snapshot/WoT_9.1_Server`.
Original `C:/WoT_0.9.1_RU_0717_original` is read-only. The existing independent
`local/clients/p04d-b` copy and isolated preferences may be reused only after
checking restoration/ownership. Primary P03M and other chat stands are untouched.

Support existing server-owned MS-1 commander/driver identities, unloading to
barracks, filling vacant seats and replacing an occupied compatible seat.
Retain the recruited driver and the displaced original driver; never create
identities during reassignment. Other vehicles, cross-specialization penalties,
retraining, skills, dismissal, paid tariffs and battle admission are separate.
Whole-crew unloading uses the source-verified same CMD105 with slot=-1 and
tankman=-1 and is included in the atomic/native acceptance sequence.

Owner clarification: assignment/unloading is a common operation for all tanks.
The core planner consumes validated vehicle/seat-role data and owned assignments;
it must not contain a separate MS-1 algorithm. The current native adapter binds
that general operation to its actually imported mutable MS-1 profile. Synthetic
multi-vehicle planner tests establish reuse, not native acceptance of other tanks
or historically accurate cross-specialization effects.

## Execution

1. Pin original #717 bytecode/definitions; establish exact commands, argument
   order/types, callbacks, vacancy/assignment representations and UI entry points.
   Record VERIFIED/OBSERVED/INFERRED/UNKNOWN; execute no imported client bytecode
   outside its real owned client, and use bounded static readers.
2. Add a versioned mutable assignment policy using the existing single SQLite
   writer and command ledger. Migration retains IDs, descriptors, balances,
   ammunition, quota and prior evidence. Old writers reject the new schema.
   Require authenticated ownership, compatible seat, available vehicle, current
   revision, finite barracks capacity, unique assignment and bounded inputs.
3. Extend the native gateway queue and bridge with the verified operation only.
   Publish the real inventory update before success. Failed/stale/ambiguous
   commands cannot claim success; duplicate delivery cannot mutate twice.
4. Enable only the corresponding original UI callbacks. Keep native processors,
   command writers and inventory readers; use a bounded diagnostic scenario to
   invoke those same callbacks and capture their real network/cache/visual result.
5. Test SQLite transactions/rollback/reopen/replay, wrong owner/role/seat,
   reserved vehicle, partial crew, unchanged ammo/recruitment behavior, protocol
   framing and full-packet atomicity. Run canonical Rust, applicable Python,
   complete Node and actual Python2.7 compilation on final sources.
6. On an isolated database copied consistently from our accepted state, use a
   real original client to unload, seat from barracks and replace an occupant.
   Restart bridge/gateway/client; verify identical identities/assignments with
   independent packet, database, callback and screenshot evidence. No synthetic
   command or client-side state mutation substitutes for native acceptance.
7. Restore owned client installations, stop receipt-owned processes, update
   STATUS/research/evidence, commit and perform the authorized ordinary no-ff
   merge/push only after every required gate passes; compare remote SHA.

## Acceptance and rollback

Final status: PASS_NATIVE_CREW_TRANSFER_CURRENT_MAIN. Source/wire/native
behavior is evidenced in the P04F research and evidence index. Native acceptance uses the original callbacks in a real
client plus independent wire/state/visual correlation. Physical mouse/manual
owner acceptance is separately reported if not run. Graphics artifacts and
other vehicle behavior are not accepted by inference.

Every operation preserves identities, descriptors, quota, balances and ammunition;
only assignments and shared/configuration revisions change atomically. Rejected
operations leave all relevant tables unchanged. Vacant seats survive fresh login.
Replacing a seated driver preserves the displaced tankman in barracks.

Rollback: ledger-restore only owned installs; stop only receipt-identified
processes. Preserve new DB/evidence and the unchanged accepted predecessor DB.
Revert this card's main merge with `git revert -m 1`, never rewrite history or
reset another checkout. Missing mandatory native/test evidence is NOT_RUN/HOLD.

Completed: original callbacks/packets/durable updates and fresh relogin twice;
final pair05/06 uses the combined accepted P03M main baseline and final build04.
726 Rust,770 applicable Python,98 Node tests and9 CPython2.7 compile checks pass.
P03M test-only fixture relocation preserves exact scalar bytes after a retained
initial precision-audit failure; production pool ownership checks are unchanged.
All own native installs restored, processes stopped, scenario consumed.
Physical owner input and native cross-vehicle assignment remain NOT_RUN.
Final commit/ordinary merge/push/remote SHA are bound in the local final receipt.
