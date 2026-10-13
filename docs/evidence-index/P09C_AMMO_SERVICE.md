# P09C isolated ammunition service evidence

Date: 2026-10-13. Status: **PASS_P09C_ISOLATED_AMMO_SERVICE**.
Runtime/native integration: **NOT_RUN**. Branch: `codex/p09c-ammo-service`.
Base: `90c7a1d92a67be2acf2d02ab9a5720a377c9f2c8`.
No merge/push in this parallel handoff.

Worktree:
`C:\Users\NSNull\.codex\worktrees\p09c-ammo-service\WoT_9.1_Server`.
All paths below are relative to it; `E` means
`local/evidence/20261013-p09c-ammo-service-01/`.

| Check actually run | Result | Evidence |
|---|---|---|
| Nine original #717 resources, mounted capacities, ordered compatibility, compact encoder | PASS | `E/source-audit-03/receipt.json`, also `E/harness-02/source-audit.json` |
| Source-bound catalogue tests | 11/11 PASS | `E/validation-02/tests.stderr.txt` |
| Real isolated SQLite service tests | 50/50 PASS | same combined log |
| Existing P09B regression | 13/13 PASS | same combined log |
| Complete applicable Python scope | **74/74 PASS, no skips** | `E/validation-02/receipt.json` |
| Fresh scenario, persistent isolated DB, reopen and original replay | **16/16 checks PASS** | `E/harness-02/receipt.json`, `observations.json`, `isolated-ammo.sqlite3` |
| Repository source layout | PASS | `E/validation-02/layout.txt` |
| Whitespace/error diff check | PASS | `E/validation-02/receipt.json` |
| Native servicing, live IS-7 ammo grant, deployed integration | NOT_RUN | Explicit scope boundary |
| Prices, purchases, repair and consumables | UNKNOWN / UNSUPPORTED | No financial write path |

The tests include all six shells, full and over-capacity loads, stock
conservation, unload/refill deltas, stale/foreign/incompatible/insufficient/
reserved refusals, payload mismatch, replay after later changes and reopen,
four precommit rollback points, once-only bootstrap, legacy schema refusal,
snapshot/ledger corruption and three real two-connection thread races.
Each rejection compares full logical SQL state. The inherited reservation
uses the same revision and command ledger and preserves ammunition.

Source catalogue fingerprint:
`9c50c64b85c6301e64145f9fbb90450417dc9063bcd8c136ac6de0c9cbabca62`.
Source-audit-03 receipt SHA256:
`959aee0adde7fb1c6914111c5ce616f3062b6a6ed958622b3e10eef74c2a64c4`.
Harness isolated DB SHA256:
`731aa2a886b3f252b9b9d7cb952411e84758672e1b4826b680d1f46a529a6a67`.
Validation and harness receipts pin all applicable source hashes and logs.
Environment: Windows 10 build 19045, Python 3.14.3, SQLite 3.50.4.

## Reproduction commands

From the worktree, with a fresh output name for each run:

```powershell
$env:TEMP = Join-Path (Get-Location) 'local/evidence/20261013-p09c-ammo-service-01/tmp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
python -B -X utf8 -m unittest tests.test_p09c_ammo_catalog tests.test_p09c_ammo_service tests.test_game_profile_tx -v
python -B -X utf8 tools/p09c_ammo_catalog.py --original-root C:\WoT_0.9.1_RU_0717_original --out local/evidence/20261013-p09c-ammo-service-01/source-audit-repeat
python -B -X utf8 tools/p09c_ammo_harness.py --original-root C:\WoT_0.9.1_RU_0717_original --out local/evidence/20261013-p09c-ammo-service-01/harness-repeat
python -B -X utf8 server/check_layout.py
git diff --check
```

The original root above was verified from the existing primary local config;
if relocated again, resolve the new explicit configured path before running.
The harness never discovers or opens any shared/live database.

The local `E/validate_card.py validation-02` runner captured the combined
commands, source hashes and exit codes. `validation-01` is retained as
**FAIL_VALIDATION_RUNNER / product tests NOT_RUN**: an off-by-one parent path
ran commands above the worktree. Correcting only that ignored runner produced
validation-02; no failed run was relabelled PASS.

Two review findings (unbound saved ammo result and inherited reservation replay
skipping aggregate validation) were fixed before final tests. Dedicated
corruption tests now cover both; independent post-fix in-memory review passed.

Final branch commit, clean worktree verification and a validation on that exact
commit are recorded in ignored `E/handoff.json` and `E/validation-head/`.
Those local handoff receipts do not change tracked source or imply runtime
acceptance. No gateway build is required for this Python-only extension;
combat/runtime files and shared P09B implementation are unchanged.

## Changed files and rollback

New: `tools/p09c_ammo_catalog.py`, `tools/p09c_ammo_service.py`,
`tools/p09c_ammo_harness.py`, both `tests/test_p09c_ammo_*.py`,
`docs/plans/P09C_AMMO_SERVICE.md`,
`docs/research/P09C_AMMO_SERVICE_CONTRACT.md`, this index.
Updated: this worktree's `docs/STATUS.md` only.

Revert the P09C commit to undo source changes. Isolated DB/evidence is disposable
and never replaces live data; no deployed migration or client rollback applies.
The accepted old profile4 grant remains separate and untouched.

One next step: a separately reviewed account/loadout integration gate using
this contract, coordinated with crew/equipment, followed by native acceptance.
