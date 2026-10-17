# P10B Hold5 selection CLI precursor

Base0472ddbc0aa49445ee0315b30e2676dc184c4397 on a separate branch
codex/p10b-hold-selection-cli in C:/wot091-selection56/w. Primary short-C
HEAD200/index/config/raw925 and the saved reader branch remain unchanged.
This card adds only a Python CLI worker and actual subprocess/SQLite tests;
no Web/Rust/Config/native Training5 route, activation, reserve or publication.

1. Preserve all four frozen reader56/test/vector files and the other929 runtime
   source bytes. Add this plan before implementation, LF attrs for only the new
   service/test, and concise ACTIVE_GATE/STATUS updates for this branch.
2. Add tools/p10b_selection_hold_service.py. The script-rooted project layout
   owns imports; caller cwd/PYTHONPATH/WOT091_ROOT never choose production code.
   Trusted argv alone supplies database,bundle,original-root,account-id,
   shell-catalog,terminal-policy. Stdin is only the strict version5 Request9,
   bound4096, Reply15/stamp11 bound12288, no input paths or raw Ready/receipt.
3. Validate a preexisting absolute local plain DB and required existing Hold5
   namespace on a mode=ro/query_only preflight connection before constructing
   an exact genuine OwnerHoldStore. No missing DB creation or activation.
   Root-approved constructor boundary: current inherited constructors perform
   existing-file checks, connect/PRAGMAs and source/catalog field setup, without
   initialize/DDL. The genuine constructor briefly opens an RW-capable handle;
   immediately set/assert query_only=ON before source/reader methods. Do not
   claim RO from the first open, mutate private fields, substitute a subclass,
   monkeypatch SQLite, or copy constructor fields. Close every handle on error.
4. The unchanged reader owns its one query_only BEGIN snapshot and validates
   current schemas/catalog/policies/late-reader/source raw bytes/run/CAS, all
   owner reservations, selected crew/ammo/mount and actual companion stamps.
   Its inherited required-existing-schema initialize path only validates; no
   reachable schema creation/migration is authorized. Selection returns no
   reservation and invokes no RunOpen/admit/fixture publication.
5. Known bounded domain denials emit canonical {error:selection_not_ready,code}
   with exit0. Malformed stdin maps to INVALID_INPUT. Auth/foreign ownership,
   corruption, filesystem/SQLite/source errors and unknown codes emit only a
   generic stderr marker and exit1, no stdout/trace/path/token dump. Argparse
   failures keep ordinary exit2. No fake empty/Ready success.
6. Add normal tests/test_p10b_selection_hold_service.py using existing exact
   source-owned support: genuine AnchorA/OwnerB/C/D from attested source seeds,
   fixture-only explicit setup separate from reader, no grants/assets copying.
   Actual subprocess uses clean child PYTHONPATH and unrelated cwd. Verify four
   positive proofs, malformed/duplicate/oversize input, CAS/stamp/held denials,
   foreign/unsupported/corrupt/missing DB failures, query_only write refusal,
   actual SQL trace and complete raw/logical DB equality. Constructor/preflight
   tests exercise actual existing namespace and missing/foreign/link paths.
7. Commit the bounded allowlist, run ordinary new CLI tests plus existing10
   reader tests from the committed source, capture own runtime/head/index and
   exact primary925 before/after. Retain failures; copy finite evidence to the
   new worktree local/evidence without DB/assets/private configuration contents.
   No Cargo/services/network/native/merge/push before Root review.

Source evidence: reader56 strict DTOs and actual4 owner vectors are retained in
the parent. Old loss selection service is only a process/error-shape pattern;
its exact-type reader/factory is untouched. No old925/929 full is relabeled as
this new Python source closure. Positive IS-7/native training remain NOT_RUN.

Rollback: revert this additive branch's service/test/docs/attrs changes; no DB
migration or restore is required. Retain all new temporary test DBs/receipts.
Next step after actual scoped tests and Root review: a separate private Web/
Rust codec card; keep native Training+Hold5 Config refusal closed throughout.

## Actual committed-source gate

Source02c25d37f5ae784d57cfa014b57d0e275526a005, runtime931:

    $env:WOT091_ROOT='C:/wot091-night-20261017-01/w'
    python -B -X utf8 -m unittest discover -s tests -p 'test_p10b_selection_hold*.py' -v

18PASS/0FAIL/0errors/0skips,200.682 seconds. These are the existing10 actual
reader tests and8 new CLI tests. Both explicit own committed HEAD/raw931/index/
config and primary200/raw925/index/config remain exact before/after. The four
parent reader/support/test/vector bytes remain exact; full931 was not run.
No old full is treated as this new CLI source closure's acceptance.

The new tests perform19 real Python subprocess calls with PYTHONPATH removed
and unrelated cwd: four genuine source-owned positive selections (A/B in one
attested source context,C/D in another, NOT a four-player room), malformed/
duplicate/oversize/unknown-path input, CAS/new Hold stamp denials, foreign-owner
generic failure, actual held5 reserve exclusion, missing/non-Hold/corrupt file
and actual copied Hold-policy-marker corruption rejection. Setup operations
are separate fixture-only actual writers with no grants. All13 source-DB
main/WAL/SHM observations in the combined report remain exact.

A test-only connect observer always delegates the real original sqlite3.connect
and only installs trace callbacks. It captures343 actual SQL statements across
RO preflight, genuine constructor and selection. No DDL/insert/update occurs;
the actual attempted DELETE fails readonly, total_changes stays0, and both
actual connections are closed. A failing genuine constructor with an invalid
configured shell source also closes its partially opened handle. No runtime
monkeypatch/subclass/private field construction is used. The brief RW-capable
constructor connection remains an explicit reviewed limitation, not an OS-RO
guarantee. Query_only is set before any source/reader/store method.

First scoped run on6c13eef had8PASS/0FAIL/0skip in73.587s, with two ResourceWarning
messages from new test fixtures using SQLite's transaction context without
closing. That result/stderr is retained unchanged. Commit02c25d3 fixes only the
new test handles with closing() and adds genuine copied-schema corruption
coverage; service bytes are unchanged. Final18PASS stderr has no warnings.

Evidence: local/evidence/20261017-p10b-hold-selection-cli-01. The original
operator/test records are retained under C temp/training-hold-selection-cli63;
finite SHA-verified copies contain reports/logs/source maps, not DBs, assets,
toolchains, private configs or client resources. Actual source-generated SQL
report a790b8695dd165689cd1de6829d5cb3f8cc62cb58259097131647f1a3cae90df
is retained independently with its exact source/argv/status proof.

Software precursor scope passes. CLI response 'ready' means only the existing
selected-loadout proof; it is no native Ready, reserve or allowed Training5
mode. No Web/Rust/config route, services, network, client/native test, push or
merge was executed. Root reviews the exact branch tree/receipts before push.
