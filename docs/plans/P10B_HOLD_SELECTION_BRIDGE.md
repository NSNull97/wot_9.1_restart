# Proposed P10B private Hold5 selection bridge

Root-approved bounded private bridge implementation card, before code. CLI63 is already
preserved at ed53addea71a5b3623d0a6602caf9dd7c43b23b0 / tree
15eedecca01295e1c1ba718c02a0172034a60861. Primary200/raw925 stays untouched.
This proposal is one functional private bridge step, not native Training5.

## Concrete integration choice

Use the existing private createIdentityBridge listener and its fixed POST
/internal/native/room-selection-hold. Add one new adapter module
web/src/p10b-selection-hold.mjs and narrow game-adapter.mjs hooks. This avoids an
unused service and a second listener/auth implementation. A route needs one
explicit new bridge option, so this scope requires Root approval; no option or
route is changed by this plan. Gateway Config, Rust flags and the existing
training+Hold5 rejection remain completely unchanged.

Proposed exact optional config:

    room_selection_hold_service = {
      version: 5, schema: 'p10b-owned-selection-hold.v1',
      contract: 'p08b-owner-battle-hold.v1',
      policy_sha256: '98cdc5d657e4cdf30225c26913f2c70a89865de9ae2bb97704fa4b623efd806e',
      accounts: [one to six unique configured owner UUIDs]
    }

The subset must belong to BOTH existing owner_hold_service and ammo_loss_service
owners and be disjoint from configured old2/4 selection owners. Existing
holdReaderFence / lateReaderFence and the real all-method OwnerHold factory stay
in force. No deriving new capabilities from a table marker, fallback to4 or
implicit activation. Absent new option returns404. Other config schemas and
old2/4 routes keep their current behavior and Hold-owner denials.

The handler lives after current private bearer/Host/Origin/method checks. It
requires a registered selected owner and actual identity/game native DB ID,
then invokes only the bound per-owner reader service. A successful 'ready'
response means selected-loadout proof, never native402/411/WriterReadyRef.
No new economic or client-facing API is introduced.

## Worker and DTO contract

The adapter uses the intrinsic normal project ROOT and fixed
tools/p10b_selection_hold_service.py. No caller worker path or env ROOT.
Arguments are actual configured database/bundle/original/source files and
bound owner; incoming raw bytes are only the existing Request9/Stamp11.
Preserve original bytes through Python's duplicate-key parser. Request4096B,
reply12288B, stderr4096B; fixed per-owner one-active read, worker7s / request9s
matching the existing loss selection contract. Real tests must prove success
within this bound; a timing failure is retained, not silently widened.

Validate exact Reply15 with actual owner/native/run/inventory/current revision
and exact Stamp11. Validate explicit FrozenHold3, nested actual Loss wrapper
and base9 stock MS1/IS7 constraints, all three hashes and selection fingerprint.
Do not construct a fake Selection4 envelope or cast a Hold payload to old4.
Reuse only policy constants/canonical digest helpers, not old Ready authority.
Known CLI denials map409; malformed request400/oversize413; foreign owner403;
unexpected worker/schema/exit/timeout503 with generic details. Child timeout or
stdio failure kills the SAME child and waits close before releasing active
capacity. Reads may coexist with ordinary SQLite WAL writes; do not claim this
is another mutation lane or reserve/ledger writer.

## Minimal proposed file allowlist

Production: new web/src/p10b-selection-hold.mjs; narrow existing
web/src/game-adapter.mjs. Preserve CLI63/reader56 and every Python writer.

Tests: new web/tests/p10b-selection-hold.test.mjs;
web/tests/p10b-selection-hold-http.test.mjs;
tests/helpers/p10b_selection_hold_http_seed.py.

Administrative: .gitattributes, docs/ACTIVE_GATE.md, docs/STATUS.md and a new
docs/plans/P10B_HOLD_SELECTION_BRIDGE.md on its own future card branch. No other
runtime source, schema, original client, resource or operational helper edit.

## Actual proof plan after approval

1. Golden unit validation uses the actual source-owned four-vector fixture
   already committed by reader56. Reject all new stamp/wrapper/hash/identity/
   version/field poisons and owner subset errors without fabricating SQL proof.
2. An explicit fixture-only Python seed helper reuses genuine attested C/D
   resource/source context and actual setup writers, preserving all old input
   main/WAL/SHM hashes and no grants. A/B raw-anchor positive is already proven
   by CLI63; this first HTTP composition uses two actual owners, not four rooms.
   Any setup backup/publication is distinct from the selection baseline.
3. Coherent ordinary module imports require this branch's real CLI63, never an
   ignored loader/worker substitution for a positive. New test DBs/identity/
   fixture dirs live only beneath this own worktree's local test namespace so
   production Web localPath stays unchanged. WOT091_ROOT is a test-only attested
   resource pointer; no production path scope is widened. Retain new outputs.
4. Start only the test's own loopback ephemeral HTTP listener. Existing exact
   createIdentityBridge auth/factory publishes real current Hold5 Fresh during
   allowed setup/profile refresh. Capture complete logical/raw DB baseline
   AFTER setup and BEFORE selection. Actual HTTP -> new Node adapter -> CLI63
   -> existing SQLite -> strict Hold5 response must leave every table/CAS/
   command ledger/reserve/resource/crew/ammo/depot unchanged.
5. Wrong bearer/Origin/Host/owner/native, duplicate/malformed/oversize/path input,
   missing mode404, missing owner activation and wrong5 stamps must fail. An
   actual fixture Admit5 must block selection without another reserve. An
   ordinary existing garage mutation and genuine Fresh must make oldCAS/stamp
   fail while the new actual projection succeeds. New selection never performs
   RunOpen, activation, garage mutation, fixture publish or Finish itself.
6. If time allows, a separately labeled trusted test stall proves bounded own
   child termination/close and no SQL changes; no fabricated positive worker.
   Every listener/worker stops in finally, errors retain evidence, no old
   cleanup/firewall/real stand action. No external network or native UI test.
7. Normal Node tests and existing relevant bridge tests on one committed source;
   exact own/primary before/after raw/head/index proofs, finite durable evidence
   copy and Root review before push. Full new source/native remain NOT_RUN.

UNKNOWN until actual gates: new HTTP end-to-end latency under concurrent full
Python load; current fixture factory compatibility from the independent
worktree's local output root. If a required source/output seam fails, preserve
the failure; do not alias roots, weaken source hashes, grant resources or open
Training5. Root decides any wider follow-up separately.

Rollback: revert only the new optional private bridge module/hook/test/docs
card; preserve old records and runtime fences, no database restore or migration.
Next step: Root reviews this exact bounded endpoint/config/allowlist proposal
and approves implementation, or keeps this artifact source-only.
