# P02 project_submit source-location pin

## Goal and boundary

The own hangar-relogin diagnostic's strict input wrapper audit rejected current own project_auth.submit because its stored source location was113 while the actual CPython2.7.3 code object starts at115. This card changes only that own AUDIT tuple's line number. It preserves project_auth.py, all test assertions, bytecode digest/signature/closure/flags and every original WG client AUDIT entry.

Base200dcd221fb48c019b0939046ac38c18a85061dd; isolated C:/wot091-py27-pin90/w, branch codex/p02-project-submit-pin. Plan c478338; tested runtime a6224a9940ef7a9b7b1aec3db2f06dbe5e906678. Primary morning source200/raw925, D working tree/data and existing research clients remain unchanged. No merge or install is performed by this card.

## VERIFIED measurements

Pinned interpreter: D:/WoT_9.1_Server/local/toolchains/cpython-2.7.3-x86/python.exe, SHA702e31ed1537c279459a255460f12f0f2863f973e121cd9194957f4f3e7b0994, actual2.7.3 MSC1500 x86. Own source is compiled only; no execution of project_auth compiled code or original client bytecode.

Exact submit tuple before fix: ('project_auth.py',115,4,('view','user','password','host'),('endpoint','original','record'),19,'66212cbb7a3b1224dfda6b7d606530074681af64da5f108fee4dbe6e0074b2ba'). Stored tuple differed only at113. Raw project_auth.py remains b95dd65f437770a53ad024430228b471ab953a060e1ff1a43025784422e511fe.

Actual unchanged test InputAndContractTests.test_project_input_boundary_compile_only_matches_pin under CPython2.7.3: RED1failure/0errors/0skip on base, then GREEN1/0/0 on runtime a6224a9. REDresult db6d69791808bf3c4e7df8c7dfa7a8f2bccafd9004bdf41ca38fcc31d03d3a88; GREEN4ad2b31ffd17899fb67f2604e7f0a95f5d75aecf5d799bf18a24b42f4a16beef.

Ordinary Python3 complete test_hangar_relogin_scenario module:57run,54passed,0fail,0error,3skip, result634e0fd89427a1fe949844e213926d315957f2f606e07cb8ddb257f45307ea22. Exact reasons: local original client path not configured in the isolated source-only worktree; project bytecode must use Python2.7 (covered separately by real2.7.3 target); historical native corpus not installed. No fake-original metadata or copied private/native corpus supplied.

Every actual child is assigned to pinned OwnJob43 before GO. All completed with Job active0, no inherited PYTHONPATH/PYTHONHOME, -B, C-only own temporary/output directories. RED exit1 is expected test failure; GREEN/Python3 exit0. Primary raw925 and card runtime before/after maps exact. Other924 runtime files are raw-identical to base, including production project_auth and unchanged test module. Whole changed file exactly equals base bytes with this single113→115 replacement; originalWG AUDIT bytes therefore unchanged. New worktree was raw925/filteredGitblob/parenttree parity checked (320 checkout EOL spellings restored from tested primary bytes), with primary index/config unchanged.

First red01 instrumentation metadata inherited this helper's print_function future flag; its unchanged unittest still failed on the line only. That own observer guard failed closed, logs retained. Independent metadata compile now explicitly dont_inherit=True; fresh red02 gives flags19 and the exact line-only drift. No project edits were made before the accepted red02 measurement.

## Commands and evidence

Own bounded driver A/p02-project-submit-pin90/observe.py invokes the unchanged test through the tests directory (tests has no package __init__). Actual commands:
python -B A/p02-project-submit-pin90/observe.py --label red02
python -B A/p02-project-submit-pin90/observe.py --label green01
python -B A/p02-project-submit-pin90/observe.py --label python3-module01

A = C:/Users/NSNull/AppData/Local/Temp/wot091-night-workspace-kcadgetk. Driver requests preserve exact actual argv/environment/interpreter/program pins. Source maps, logs, expected/actual tuple, counts and OwnJob receipts are retained.

Durable own metadata proof: C:/wot091-py27-pin90/w/local/evidence/20261017-p02-project-submit-pin90/proof-manifest.json, SHA783f8d46a9f7036270aafe07d3c2fb89582f9b91b745a6882dcc4d52e382ba42,30files/976507bytes; all exclusive copies source/target rehashed. No proprietary resources, binaries, keys, credentials, DB or native wire copied into it.

## Limits, acceptance and rollback

VERIFIED: this strict own compile-time boundary accepts current project source after the one-line-location correction; ordinary synthetic unit module is green with three stated skips. OBSERVED: tests on the pinned Windows/x86 CPython2.7.3 and hostPython3 environment. INFERRED: a future freshly compiled project wrapper at the same source revision will satisfy this code-object audit. UNKNOWN/NOT_RUN: actual native logoff/relogin/UI, client installation and original-static/corpus checks inside this new source-only worktree. No whole Rust/Python rerun or gateway build was needed for this constant-only own diagnostic change.

Component acceptance PASS, native acceptance NOT_RUN. Branch review-ready, not merged into main or prepared primary morning source. Rollback is a revert of runtime a6224a9 in an isolated branch; no deployed client/DB rollback required. Next: Root reviews exact six-path diff and metadata, retaining the source200/raw925 morning binding unchanged.
