# ORG-0B — verified unittest repairs (2026-10-07)

## Result and scope

**PASS_TEST_REPAIR**, with documented environment skips. Base:
`1aa052db33643fab510f2b9185716a8e60d8804a`; branch:
`codex/org-0b-test-repair`. [Execution plan](../plans/ORG-0B_TEST_REPAIR_20261007.md).

The fresh baseline reproduced 2028 tests, 10 errors and 4 skips. Minimal repairs
yielded **2047 tests, zero errors/failures, two skips**. The Python 2.7 bytecode
check passed separately. Windows symlink refusal is the only original skipped
check not executed in any mode; current account capability is insufficient.

This accepts test/offline-tool repairs only. It does not close P03 or certify a
stable release, a new native run, live legacy-tool compatibility, or deployment.
Gateway Rust, physics, client patches/copies, deployed gateway and frozen native
verifiers are unchanged. P03D/P03E owner acceptance remains intact.

## Ten errors: confirmed causes and repairs

All causes below are **VERIFIED** by the fresh tracebacks, inspected source and
successful affected/full-suite runs.

| Baseline errors | Cause | Minimal repair |
|---|---|---|
| `CapturedSwitchControls.setUpClass`, `InprocessWireParserControls.test_frozen_protocol_sources`, `ActualSourceRecheckUnitTests.test_live_server_rejects_changed_run_pid_configuration_and_exited_process` | Frozen 2026-10-05 checks read removed `tools/wg_probe/src/gateway091.rs`; canonical sources have evolved and cannot satisfy the old hashes | Tests explicitly supply actual archived gateway/capture bytes through `tests/frozen_relogin_sources.py`; original validators and their hashes stay unchanged. Added corrupted-source rejection checks |
| `WindowTraceTests.test_owned_wrappers_are_not_reported_as_original_entries`, `test_unrelated_native_methods_and_similar_paths_are_not_reported` | The extracted profiler function expects global `_control`, omitted by its isolated test namespace | Initialize `_control=None`, matching the original module; no client patch edit |
| `Profile4ChainTests.test_old_profile_chain_layout_is_rejected`; `Profile4SemanticDiffTests.test_identity_mutation_is_rejected`, `test_is7_mutation_is_rejected`, `test_unexpected_ammo_mapping_mutation_is_rejected`, `test_unexpected_state_shell_delta_is_rejected` | Discovery adds `tools/` to `sys.path`; absolute-first imports create both `content_bundle.BundleError` and `tools.content_bundle.BundleError`, so a valid rejection escapes the caller's expected exception class | Package imports use relative dependencies; direct scripts use local absolute imports. No rejection rule or exception expectation was relaxed |

The test count grew by 19: 13 account-switch tests previously blocked by
`setUpClass`, five actual-export tests enabled by an existing closed export,
and one new archived-source mutation regression. The existing retired-source
test also now checks source mutation separately from service configuration.

### Historical source boundary

The map in `server/layout.json` points old gateway/capture paths to
`server/gateway/src/session.rs` and `server/gateway/src/protocol/capture.rs`.
Those are current sources, not the frozen build accepted in October 5 evidence.
The test fixture reads these existing archives, without writing or executing them:

- Gateway: `local/evidence/20261005-p02-inprocess-relogin/gui/gateway-review-01/frozen-01/sources/tools__wg_probe__src__gateway091.rs`;
  SHA256 `2edd6e6c0c36fb2544bc66fd6d7252b6a4e0d59b1e24cba7f1fb2c2800738ade`.
- Capture: `local/evidence/20261005-p02-ms1-crew/wire/contract-01/sources/tools/wg_probe/src/capture091.rs`;
  SHA256 `8e03a19b0e686a71c71cf0d0d2c56659461b7f1d3a35a8d0b3124e7cbd6d5e97`.

The reader fixture is installed only inside explicit test patches. Missing or
changed archives still fail; there is no source-pin substitution or live fallback.
Direct historical verifier/probe CLI compatibility with the current layout is
**NOT_RUN**, remains a separate adaptation task, and is not required to close
these historical regression tests.

## Four original skips

| Check | This card's result | Evidence / limitation |
|---|---|---|
| Python 2.7 project input bytecode | **PASS**, 1 test under existing CPython 2.7.3 x86 | Remains an expected skip in the Python 3 suite |
| Actual MS-1 export tests | **PASS**, all 5 tests | Explicit `MS1_AMMO_TEST_EXPORT` selects the existing `native-ms1-ammo-export01.json`; this rechecks saved evidence, not a new game run |
| Guarded preferences write | **PASS** | `SR_TEST_TEMP` points at this card's fresh scratch directory; real preferences are untouched |
| Reject real filesystem symlink | **NOT_RUN** | Windows account cannot create symlinks; no skip was added and no permissions were changed |

The actual-export tests now use a class-owned temporary directory with cleanup,
instead of leaving test scratch under an old acceptance-evidence directory.

## Commands and actual checks

Run from the repository root. The optional inputs below exist in this verified
local environment; a clean clone does not contain private/native evidence.

```powershell
python -B -X utf8 -m unittest discover -s tests -v

$env:SR_TEST_TEMP = (Resolve-Path local/evidence/20261007-org-0b-test-repair-01/scratch).Path
$env:MS1_AMMO_TEST_EXPORT = 'local/evidence/20261005-p02-ms1-ammo/native-ms1-ammo-export01.json'
python -B -X utf8 -m unittest discover -s tests -v

& local/toolchains/cpython-2.7.3-x86/python.exe -B tests/test_hangar_relogin_scenario.py -v InputAndContractTests.test_project_input_boundary_compile_only_matches_pin
python -B -X utf8 server/check_layout.py
python -B -X utf8 tools/profile4_chain.py --bundle local/evidence/20261006-profile4-chain/portable-bundle-05
python -B -X utf8 -m tools.profile4_chain --bundle local/evidence/20261006-profile4-chain/portable-bundle-05
python -B -X utf8 tools/profile4_semantic_diff.py --bundle local/evidence/20261006-profile4-chain/portable-bundle-05
python -B -X utf8 -m tools.profile4_semantic_diff --bundle local/evidence/20261006-profile4-chain/portable-bundle-05
```

| Check | Actual result | Evidence under this card's directory |
|---|---|---|
| Baseline full suite | **FAIL**, 2028 tests, 10 errors, 4 skips, 37.251 s | `unittest-before.txt` |
| Six affected test modules | **PASS**, 168 tests, 2.314 s | `targeted-after.txt` |
| Full suite with explicit local prerequisites | **PASS_WITH_DOCUMENTED_SKIPS**, 2047 tests, 2 skips, 36.243 s | `unittest-after.txt`, `unittest-after-status.json` |
| CPython 2.7.3 bytecode check | **PASS**, 1 test, 0.002 s | `python273-bytecode-attempt02.txt` |
| Profile4 script/package modes | **PASS**, 4 commands, identical JSON results per verifier | `profile4-cli-modes.json` |
| Source layout | **PASS**, 52 source files / 22 relocations | `layout.txt` |
| Original/research EXEs, deployed EXE, catalog and four battle source pins | **PASS**, all 8 unchanged | `pins-before.json`, `pins-after.json` |

The first Python 2 invocation put `-v` after the test name; that old unittest
parser treated it as a test attribute and failed before running a test. Its log
is retained as `python273-bytecode.txt`; the corrected command above passed.
That invocation error is not counted as a successful test run.

Full machine evidence directory:
`local/evidence/20261007-org-0b-test-repair-01/`. `result.json` records exact
changed files, command results, classification, limitations, accepted head,
merge/push output and independently verified remote SHA after those operations.
`tested-python-sources.json` binds the successful full run to the unchanged
Python files checked at the committed head. Historical ORG-0A receipts remain
untouched; this card has its own allowlist/link audit and head receipts.

## Rollback and next step

Rollback: reviewed `git revert -m 1 <ORG-0B-merge>` on a new card branch,
preserving baseline/tag, source archives and owner evidence. It was not run.

One next recommended card: P03 two-client shared-world preparation and
acceptance, including shared server state and exit/re-entry isolation. It is
not started by ORG-0B.
