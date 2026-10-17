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
