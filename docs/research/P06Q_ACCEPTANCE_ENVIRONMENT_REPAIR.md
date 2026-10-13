# P06Q final acceptance and source relocation — 2026-10-13

## Native result and cleanup

Owner statements "о, теперь падают" and, after the second-view/passage prompt,
"все корректно" accept the corrected native tree gate. Final private evidence:
`local/evidence/20261012-p06p-prohorovka-01/tests/treeobserve10-owner-accepted.json`
(SHA256 `d3071855e73915933dcbe1ed009fe706bc7e34cf0ed4ac51633fbff3b24ec6a2`).
The callback audit is separately retained as `treeobserve10-corrected-audit.json`
(SHA256 `8c702abfe042371407f2212e86f6d850ff4fb5bf0133c0d1f60f8a26ef305c8f`).
Three vehicle contacts, four committed scenes and eight worker ACKs are
recorded; two tree drops reach both original animators with pi/2. No server
reject/failure/closure before the controlled receipt stop. The stop and both
restore receipts are pinned by the owner receipt. Processes are no longer live.

Native runtime tested source d316828, build35. Subsequent Rust changes only
replace test fixtures; they do not change runtime behavior. Tree final angles
on slopes/obstacles, exact historical ram rules, all-object coverage and
network endurance remain unaccepted. This is cumulative test_lab acceptance.

The third contact in the full server log must not be counted as a third
matched native fall: both native traces contain two drop call/return pairs.
Client A ends with an `observation_limit` record at elapsed 1032.747 seconds
(16 MiB passive diagnostic bound). This bounds the evidence, not gameplay;
the two earlier matched events and explicit owner gate are the acceptance.

## Original source relocation

Owner moved the original to `C:\WoT_0.9.1_RU_0717_original`; no agent deleted
or changed original resources. Read-only `client_audit.manifest` verified all
3469 files / 14,680,626,869 bytes. Canonical content manifest SHA256 is still
`74c37c18e9ac7e30196c134076dacf6f2a8bf3897f7def73905d09feb3647797`, matching
the initial client audit. Evidence and backups:
`local/evidence/20261013-original-relocation-01/`.

`config/project.local.json` and the `original_root` field in
`local/clients/p03f/{a,b}/sr_lab_copy.json` now refer to C. Config and both
copy identities/hashes passed after the change. `*.before.json` backups and
`path-update.json` preserve the exact prior bytes and before/after hashes.
Historical install/run receipts retain their original paths. Old receipts
do not authorize a fresh install or rollback under different roots.

## Automated recheck and fixture repair

Fresh `gateway-p06q-acceptance-01` stopped during compilation with ENOSPC;
`test.command.json`, stderr and `failure.json` are retained. No test PASS was
inferred. Automatic approval review rejected removal of that incomplete
target directory with the generic reason `blocked by policy`; nothing was
deleted by that command. The owner's source move subsequently freed space.

Running the already verified build35 test executable against unchanged source
reported 619 PASS / 4 FAIL from missing P06N/P06O pool files, before behavioral
assertions. The exact command and log are in
`local/evidence/20261012-p06p-prohorovka-01/tests/treeobserve10-closeout/rust-full.*`.
Old root fixture directories exist but are empty. Original root DLL pins were
not recovered and must not be attributed to private binaries.

Retained historical private builds were copied to fresh
`physics-p06n-private-fixture-01` and `physics-p06o-private-fixture-01` outputs.
All runtime dependencies are verified; original config/descriptor/catalog
hashes remain unchanged. New pool pins are
`80f14d87bb01c9c28f5376265dce80989eeb715fdfe3f15018b6d29c54db9251` and
`a96e7b8c1b410446e3e7c0f6e7e7453b633c3fbb19ce94a62686fbb319031d21`.
Migration receipt:
`local/evidence/20261013-p06q-fixture-migration-01/migration.json`, SHA256
`8fab39ffb23f9c0bd9affcf9452de8422d5830a9b445dc1963a1ffedbab6cb27`.
Private-vs-root provenance and P06N's freshly pinned PDB are explicit there.
The initial too-strict empty-directory preflight failure is retained. The
strict cfg(test) helper verifies new pool/manifest pins without fallback;
all four original real-worker assertions remain in place.

`python -B -X utf8 server/build.py gateway --test --out
local/build/server/gateway-p06q-acceptance-02` passes **623/623 Rust tests** and
the canonical build. Executable SHA256:
`da6fe2882adc34e0c23602092540cd5dde6bce66db0cb7c6db8d73af377f88f7`.
This includes actual worker startup, ACK barriers, generation restore,
membership rejection, map admission and all P06Q transport/contact regressions.

The scoped Python command in `treeobserve10-closeout/python-scoped.command.json`
runs importer, native catalog probe, tree importer, shared observer, interactive
primitive and owned-copy tests: **59/59 PASS**. Source layout initially found
stray generated `server/__pycache__` and `server/gateway/target`. Their contents
were preserved under that closeout evidence directory, then the layout check
passed. Its receipt is `treeobserve10-closeout/layout.json`.

## Final source-path checks and acceptance

Live static-audit defaults now use configured original/research roots, with
exact-match overrides and rejection of traversal, symlink and Windows reparse
paths. Read-only source roots may be explicitly configured outside the repo;
evidence inputs/output remain repo-bound. This is the relocation amendment to
the historical P07A plan's repository-only source-path statement.

Final combined check, after all source-path changes:

```powershell
python -B -X utf8 -m unittest -v tests.test_client_source_paths tests.test_p03i_static_audit tests.test_p07a_visibility_static_audit tests.test_ms1_ammo_probe tests.test_ms1_ammo_profile tests.test_destructible_catalog tests.test_destructible_catalog_probe tests.test_tree_contact_catalog tests.test_shared_lab_control tests.test_interactive_primitive tests.test_shared_client_copy
python -B -X utf8 tools/p03i_static_audit.py
python -B -X utf8 tools/p07a_visibility_static_audit.py
python -B -X utf8 server/check_layout.py --out local/evidence/20261012-p06p-prohorovka-01/tests/treeobserve10-closeout/layout-final.json
```

**120 executed Python tests PASS**, plus one skipped P07A class. That class
and direct P07A CLI remain **NOT_RUN / prerequisite exit 1** because historical
`local/evidence/20261002-p00-p01/summary/{contracts,sources}.json` are absent.
Their schema acceptance was not weakened or recreated. P03I CLI passes; both
MS1 original-source hash tests run on C. A separate read-only check verifies
all **12/12** pinned P07A source files in original/research copies. New path
boundary tests validate the changed slice without claiming full P07A PASS.
Full historical P07A reacceptance is outside P06Q's required gates.

Evidence under `local/evidence/20261012-p06p-prohorovka-01/tests/`:

- `treeobserve10-closeout/python-final/receipt.json`, SHA256
  `0e9545de751384a6861a336dfe404f6a84d8f2c657d9e91df64f60890a578220`;
- `client-path-relocation01/receipt.json`, exact CLI commands and exit codes;
- `client-path-relocation01/p07a-resource-hashes-only.json`, SHA256
  `3c58dc7474855e13e710c081447b7b7fa54270263303758baf1c4308e3c41def`;
- `treeobserve10-closeout/layout-final.json`: 78 source files / 22 relocations,
  SHA256 `e51623465f15243b2ac55a5157695869a334a82e7d7cbd85a128e7a89b3b44b2`.

Gateway acceptance02 result SHA256:
`a377f830844e714ddaf0a2981c4b32c423a70cff5356956bf83a66528e5fb709`.
This final gate supersedes the owner receipt's pending automated-repair field,
without modifying the historical receipt. Native gameplay remains the tested
d316828/build35 behavior; subsequent Rust changes are cfg(test) only.
The unrelated P09B working edit is excluded. The full Python repository suite,
Linux and deliberate server-loss/reconnect are not newly accepted here.

Required P06Q gates are satisfied for normal no-ff merge/push. The final private
`treeobserve10-closeout/final-acceptance.json` and `merge.json` record source,
artifact and remote pins. Next recommended work is a separately scoped card
for remaining compound destructibles/fences, preserving accepted behavior.

## Rollback

For local paths, restore saved config/marker bytes only after the original
exists at the former D path again; keep the verified C source intact meanwhile.
For fixture changes, revert the test helper/acquisition changes and retain
both new fixtures and failure receipts. For the feature after merge, use a
reviewed revert of the P06Q merge; never reset unrelated work. A historical
P06P runtime relaunch still requires its missing original physics artifacts.
No original-client modifications or native ownership checks were bypassed.
