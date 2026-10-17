# P10B private Hold5 selection bridge

One bounded component card, branch codex/p10b-hold-selection-bridge from
reviewed/pushed CLI63 ed53adde. Implementation tested at5b8c2b4/raw935.
Primary200/raw925, prior CLI/reader branches, all Python writers and the native
training+Hold5 prohibition remain unchanged. This is private selection proof,
not a native Ready/claim/reserve/admit or full P10B acceptance.

## Functional contract and scope

Add web/src/p10b-selection-hold.mjs and narrow game-adapter.mjs hooks. The fixed
POST /internal/native/room-selection-hold uses existing private bearer, exact
Host/Origin and actual registered owner/native database identity checks.
Absent option returns404. New exact optional room_selection_hold_service has:
version5, schema p10b-owned-selection-hold.v1, contract
p08b-owner-battle-hold.v1, policy_sha256
98cdc5d657e4cdf30225c26913f2c70a89865de9ae2bb97704fa4b623efd806e,
and1..6 unique accounts. They must belong to both configured Hold and Loss
owners, and be disjoint from existing Selection2/4 owner sets. There is no
fallback to4, implicit activation or default enabling. Existing Hold/late
startup and all-method writer/factory fences remain in force.

The fixed intrinsic tools/p10b_selection_hold_service.py receives only trusted
configured argv paths/bound owner and original incoming Request9 bytes. Its
unique-key parser remains authoritative for duplicates. Request4096B,
reply12288B, stderr4096B; worker7s, outer request9s, one active read per owner.
Timeout and all three stdio error paths kill the same child and wait close
before releasing capacity. Read snapshots may coexist with SQLite WAL writes;
this does not claim a mutation-worker lane. Only known typed denials become409;
malformed400, oversize413, foreign403, unexpected generic503.

Reply15/Stamp11 and FrozenHold3 are validated directly: explicit Hold policy,
nested Loss3 policy/hash and base9 stock MS1/IS7 fields, every nested hash,
request identity/revision/stamp and selection fingerprint. No fake Selection4
envelope/cast. 'ready' is only readonly selected-loadout proof. Gateway Config,
Rust/native flags, callbacks402/411 and server admission remain untouched.
The CLI63 genuine constructor briefly owns a RW-capable handle before verified
query_only; its existing-schema preflight/trace/cleanup proof is retained.
There is no claim of OS-readonly from the first actual constructor handle.

## Actual verification and evidence

Ordinary committed-source Node15 PASS/0FAIL/0skip; exact four-file invocation
96.289s test/97.362s wrapper. New unit6 include four actual source-owned golden
vectors, recomputed-hash semantic poisons, closed config/body and authored
failure-only stdout/stderr errors proving same-child kill and close-before-slot
release. Actual HTTP2 exercise the real bridge -> fixed CLI63 -> genuine C/D
SQLite setup, actual Fresh, ordinary ammo layout mutation, stale CAS/stamp
refusal, current success, real Admit5/held denial, auth/Host/Origin/foreign/body/
duplicate rejection, concurrent owner200/503 and disabled mode404.
Selection main/WAL/logical tables/CAS are unchanged; normal layout mutation
conserves actual loaded+depot totals, resources and crew. Original source DB
main/WAL/SHM and finite project-generated descriptor bytes stay exact. Setup
activation/RunOpen/copy/publication are explicit fixture-only writers with no
grants, separate from the reader baseline. All fresh test outputs are retained.

Unchanged reader10+CLI8 ordinary Python PASS18/0FAIL/0errors/0skip in203.605s:
four genuine source owners, raw AnchorA, readonly constructor/attempted DELETE,
all handle cleanup, current run/CAS/source stamps and actual WAL race.

Existing Hold HTTP driver also PASS3 (one complete factory scenario plus two
Selection2/4 fence subtests),86.298s test/87.327s wrapper. This is explicitly a
DERIVED_TEST_DRIVER: only ROOT D->exact W and suppression of its fresh directory
removal. Every assertion/bridge close/DB close is preserved. Its final World
facts remain AUTHORED; it proves SQL/HTTP/cache behavior, not combat/native UI.

Durable evidence: local/evidence/20261017-p10b-hold-selection-bridge-01.
Primary200/925 and own5b8c2b4/935 raw source, HEAD/index/config before/after are
exact for all normal and derived gates. Parent931 changes only the reviewed
adapter plus four new runtime paths; total card allowlist9 includes docs/attrs.
Scoped peer source review found one readable-pipe error gap; it was fixed and
covered before final gates. No further concrete blocker in that reviewed scope.

Preserved harness history: normal01 failed before any tests due scratch config
proof filename; normal02 used the actual unchanged config/project.local.json.
Its extra unmatched old test argument was noticed; exact four-file Node03 rerun
removed ambiguity. Derived initial verifier expected one test instead of the
three containing/subtests: actual Node exit0/pass3 logs were retained, and
verified-result02 corrects only the external count contract, not assertions.

## Commands, limits and rollback

From C:/wot091-selection56/w, WOT091_ROOT points only test resource provenance
to C:/wot091-night-20261017-01/w; production paths remain intrinsic worktree:

    node --test --test-concurrency=1 web/tests/p10b-selection-hold.test.mjs web/tests/p10b-selection-hold-http.test.mjs web/tests/p10b-selection-loss.test.mjs web/tests/p08b-owner-hold.test.mjs
    python -B -X utf8 -m unittest discover -s tests -p "test_p10b_selection_hold*.py" -v

Full935, Rust consumption, native Training5, native UI/physics and broken-pipe
OS reproduction are NOT_RUN. The pipe regression authors only the failing
stream seam and no successful SQL/DTO. Two HTTP owners are source-owned setup;
this is not a four-player room or native match. Historical925 full receipts
are never relabeled as935. No main merge; Root reviews exact tree before push.

Rollback only this additive bridge card/option, preserve existing Hold reader
fences and all durable records; never restore a DB/refund inventory. The next
step is Root review of exact nine-path tree and receipts, then branch push.
