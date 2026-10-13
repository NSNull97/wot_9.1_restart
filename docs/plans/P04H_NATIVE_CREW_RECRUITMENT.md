# P04H — native recruitment for the MS-1 and IS-7 rosters

2026-10-13. Owner approved the preceding next step: native recruitment for all
required primary roles of the two verified vehicles, so both can have complete
crews. One card, branch `codex/p04h-native-crew-recruitment`, accepted main
`626867c758c32b189a77a7a7a2fe9ff29837e11b`.

## Owned paths and scope

Reuse attached worktree
`C:/Users/NSNull/.codex/worktrees/crew-equipment-snapshot/WoT_9.1_Server`.
Original `C:/WoT_0.9.1_RU_0717_original` is read-only. Native execution may use
only owned independent `local/clients/p04d-b`, `local/p04d/profile`, own test
account/keys and fresh owned DB copies. Primary P05 and sibling stands are
outside this card. Evidence root:
`local/evidence/20261013-p04h-native-recruitment-01/`.

Required roles: MS-1 commander/driver; IS-7 commander/gunner/driver/loader/loader.
Two loader seats must produce distinct identities. Replacing an occupied seat
must preserve the displaced tankman in barracks. Retain P04G transfers and
existing identities, source-bound descriptors, ammunition and monetary state
except a source-verified and explicitly selected recruitment tariff.

Research must first establish descriptor fields, role/trained-vehicle bounds,
tariff/training behavior and original dialog callbacks. Earlier D's one free
100% MS-1 driver was an explicit test policy, not historical recruitment.
Do not silently extend it or invent paid prices. Freeze the new policy after
source inspection and any necessary owner choice. No perk/retraining/dismissal,
new vehicle profiles or battle admission in this card. The owner's always-on
base Sixth Sense rule remains recorded for the later perk card.

## Execution

1. Pin original #717 descriptor, recruitment UI and CMD309 facts. Separate
   VERIFIED, OBSERVED, INFERRED and UNKNOWN. Do not execute arbitrary original
   bytecode in the research interpreter or copy borrowed code into the server.
2. Implement a bounded authored descriptor codec/catalog from verified fields;
   generated passports must be decoded/rendered by the actual client. Stable
   server allocation must never derive identity from client data.
3. Freeze profile8-to9 migration and explicit recruitment policy. Extend the
   existing sole SQLite writer and shared gateway queue; avoid copying a new
   transaction implementation. Validate source/target ownership, role/seat,
   tariff/quota/funds if applicable, capacity, revision, replay and reservation.
   Reject unsupported inputs without mutations. Old writers fail closed.
4. Expose original RecruitWindow flow only for enabled operations. Preserve
   actual original processors/network/cache, capture passive evidence and
   correlate native commands with durable outcomes. Keep other menus truthful.
5. Run current-source store/domain/codec/source/client/web regressions, full
   canonical gateway suite/build and actual CPython2.7.3 compilation. Cover
   repeated/malformed/stale commands, concurrency/failpoint rollback and old
   immutable ledger replay across migration. Preserve earlier profile behavior.
6. On a fresh copy of accepted G state, recruit each required role via original
   UI callbacks, including both loader seats and occupied-seat replacement;
   verify a complete IS-7 and MS-1 crew. Fresh client/bridge/gateway login must
   reproduce exact descriptors, IDs, assignments, balances and ammunition.
   Native scenario/oracle is frozen before execution. Inspect actual PNGs.
7. Independently verify raw CMD309 and inventory deltas, update-before-success,
   source/build/install binding and frozen database equality after relogin.
   Restore own installations, stop receipt-bound own services and unarm control.
8. Update research/STATUS/evidence. Only after required gates pass on the exact
   final source: commit, ordinary no-ff merge to main, push and verify remote SHA.

## Acceptance and rollback

PASS_NATIVE_ROSTER_RECRUITMENT_CURRENT_MAIN. Native02/03 closes the declared
wire/cache/persistence gates: seven original hires plus three loader moves,
fresh login, final MS-1 `[4,5]` and IS-7 `[6,7,8,10,9]`, quota6, both crews full.
All owned installations restored and services stopped. See the
[evidence index](../evidence-index/P04H_NATIVE_CREW_RECRUITMENT.md).

Owner explicitly selected new50% free recruitment; old100% crew are retained.
Paid choices remain outside this card. The16-member/13-new-hire bound is an
explicit test policy, not the source's historical daily free-recruitment limit.
733 Rust,958 distinct Python,102 Node and11 actual CPython2.7.3 compile checks
pass on applicable final sources. Six final native PNGs inspected. The initial
clipped-label attempt and resolved metadata/provenance mutants are retained.

Native compatibility requires actual original #717 execution;
unit-generated wire/UI fixtures cannot close this gate. Physical pointer/manual
owner input is separately NOT_RUN unless performed. No combat readiness,
historical unverified prices or graphics quality claim follows from full crews.

Retain accepted G DBs and immutable H backups. Restore only owned client files
through installation ledgers and stop only verified own processes. Pair any
code rollback with the matching predecessor DB/profile. After merge use
`git revert -m 1 <P04H-main-merge>`; no history rewrite. A required final
FAIL/NOT_RUN leaves the card in its branch. Choose one next crew step from the
actual outcome. Subsequent cards are now authorized by the owner's expanded
[overnight crew request](P04_CREW_FUNCTIONALITY_091.md), preserving separate
branches and gates.
