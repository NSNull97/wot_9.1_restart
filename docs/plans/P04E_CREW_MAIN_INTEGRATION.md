# P04E — close crew acceptance on the current main baseline

2026-10-13. Owner authorized the next step with "давай": repair the nine
historical fixture failures, rerun required gates and merge the accepted
crew/ammunition stack. One integration card; no new crew gameplay or physics.

## Checked baseline and ownership

The preceding P04D commit1449e4c passed actual native recruitment/relogin but
held main integration on9 Rust fixture failures. Read-only inspection found
the exact repair already accepted in P09D commit8d61c16, merged as current
local/remote main a998ca39f8d63f8a809336cc4a2b536c6ecb9f9b. It also includes
accepted P06R. Reuse that implementation and verify our combined sources.

New branch `codex/p04e-crew-main-integration` starts from that current main
in the existing owned crew worktree. Merge P04D1449e4c with both histories
preserved. The primary checkout remains owned by the active P03M task;
the other P09D stand/worktree is read-only evidence. All writes, generated
fixtures, databases, builds and own native installs stay in our worktree.
Original read-only client remains C:\WoT_0.9.1_RU_0717_original.

## Execution and acceptance

1. Merge the reviewed P04B/P04C/P04D history onto current main; resolve only
   actual overlaps, preserving accepted P06R and P09D behavior/history.
2. Retain exact archived pool/config/runtime hashes. Use existing cfg(test)
   relocation to derive owned-path configurations. Copy missing ignored inputs
   read-only with SHA/provenance; never rewrite archived evidence or bypass
   production ownership/size/hash checks. Independently review the integration.
3. Run full canonical gateway tests/build, applicable source/domain/crew/ammo
   Python tests and full Node suite. Any mandatory FAIL/NOT_RUN keeps the
   integration branch unmerged. Explicit historical environment-only skips
   remain separately described, not silently accepted as native coverage.
4. Recheck actual #717 recruitment and fresh client/server login on the merged
   source/build with an isolated new game DB and the existing own client copy.
   Validate raw packet/update/callback/SQLite/native-cache and actual PNGs;
   restore every installation and stop only receipt-owned test processes.
5. Update STATUS/evidence; commit with source bindings. If all applicable gates
   pass, normal no-ff merge into main from our owned checkout, push and compare
   remote SHA. Never switch another task's checkout or include its changes.

## Facts and limits

VERIFIED: old9 failure receipts and exact path/pin conflict; accepted repair
source retains historical hashes and production loader boundaries. OBSERVED:
previous P04D native result in one Windows environment. Combined native result
is NOT_RUN until this card executes it. No claim for new crew skills, prices,
other vehicles, universal physics equivalence or primary stand deployment.

Rollback: ledger-restore own native installation; stop owned process identities;
keep new DB and immutable evidence. Source rollback is a normal revert of the
integration merge, preserving its dependency history and later work.
