# P04I — original PersonalCase and first skill selection

Status: **PASS_NATIVE_PERSONALCASE_FIRST_SKILL_CURRENT_SOURCE**.
Branch `codex/p04i-native-crew-progression`; accepted baseline main
`1e45eae4e454f196a1842472061d70aeb416651b`. Commit, no-ff merge and remote SHA
are bound in ignored evidence `acceptance-final/`; the owner's complete-crew
request remains open. Physical owner input is NOT_RUN until after09:00 on
2026-10-14 Asia/Yekaterinburg.

## Result and changed files

Original #717 PersonalCase selects a skill through CMD151 and the existing
authoritative transaction writer. Primary qualification100 is mandatory;
the owner reiterated it on2026-10-13. Native UI and server both reject50%.
Current assigned seat determines combined-role eligibility; barracks provides
only the primary role. Sixth Sense is an owner-defined base capability,
excluded from learnable descriptors. No combat signal is claimed here.

- `tools/p04i_tankman_descriptor.py`, `p04i_crew_projection.py`,
  `p04i_crew_store.py`: bounded source XP/descriptor arithmetic, profile10
  migration and one learned skill at0%, retaining the sole SQLite writer.
  Narrow `p04f_crew_store.py` hooks preserve old F/G/H/D receipt replay.
- `server/gateway/src/account/crew_progression.rs`, `crew_transfer.rs`,
  `ammo_session.rs`, `identity.rs`, `hangar.rs`, `session.rs`, `main.rs`:
  explicit opt-in, exact20-byte CMD151 framing, shared bounded FIFO and
  revision handling, inventory update before success.
- `web/src/p04i-crew.mjs`, `p04d-crew.mjs`, `game-adapter.mjs`:
  fixed authenticated internal route and profile10 overview projection.
- `client_patch/p04i_crew_ui.py`, `crew_capabilities.py`,
  `hangar_bootstrap.py`, `sr_interactive.py`, `tools/interactive_client.py`:
  original PersonalCase data/commands, opt-in installation and passive evidence.
  Unsupported price-dependent tabs stay disabled; no invented shop data.
- `tools/p04i_crew_source_audit.py`, `p04i_native_crew_verify.py`, associated
  `tests/test_p04i_*.py`, `tests/test_crew_capabilities.py` and
  `web/tests/p04i-crew.test.mjs`: source pins, boundary/replay/rollback tests,
  real HTTP/SQLite tests and independent native verification.
- STATUS, plan, expanded crew plan and research/evidence documentation.

## Executed gates

All paths below are relative to the crew worktree's
`local/evidence/20261013-p04i-native-progression-01/`.

| Check | Actual result | Evidence |
|---|---|---|
| Rust full suite / isolated build |738 PASS; no deployment to primary stand|`rust/receipt01.json`, `local/build/server/gateway-p04i01/result.json`|
| Python applicable distinct tests |1049 PASS, no final required skips|`python-test-union02.json`|
| Store/regression and historical |529 +67 PASS; immutable source hashes|`store/regression-03.json`, `historical-01.json`|
| Client +P03M |392 +42 PASS|`client/run-05/receipt.json`|
| Static source / independent verifier |65 +82 PASS;11 additional peer mutants rejected|`source-audit/tests01/`, `independent-native/unit03/`, `store/verifier-review01.json`|
| Full Node suite |104 PASS, all executed source hashes stable|`web/full-web03.json`|
| Real CPython2.7.3 |12 targeted compile checks and Unicode execution PASS; all35 installed source modules bound in both native plans|`client/run-05/`, `native-install05/06`, independent receipt|
| Native05 / fresh06 |6 original mutations, persistent relogin, both clients exit0|`independent-native/final02/receipt.json`|
| Native pixels |9 exact PNGs inspected|`native-pixels02.json`|
| Cleanup |6 restores PASS,18 owned PIDs absent, ports23416/23417/3436 free, no armed control|`native-cleanup-final02.json`|
| Source layout |95 source files /22 relocations PASS|`layout-final01.json`|
| Physical mouse / owner tests |NOT_RUN|Deferred by owner until after09:00|

The Python union avoids double counting overlapping suites. Source bindings
are in `source-binding-final02.json`; one broad historical enumeration included the
new I descriptor test, which that suite does not execute. Current store
regression03 covers that file after its EOF cleanup. No executed-source mismatch is excused.

Native05 requests226–231 are three transfers and three skill selections.
IDs1/2/3 learn Mentor/Smooth Ride/Repair at0%; no XP is granted. Revision42→48,
configuration33→39, quota6, money and ammunition unchanged. Final MS-1 `[4,5]`,
IS-7 `[6,7,8,10,9]`, old1/2/3 in barracks. Skills survive transfer/relogin.
The original zero dossier readers materialize10 bytes while the stored6-byte
dossier remains unchanged. This is actual source behavior, not invented stats.

Gateway executable SHA256:
`be4cddfec45cadb32076bae14e71a1269dd8d3c300c39fc951a35dfd6726ffa8`.
Final frozen database `native-persistence/after-relogin06.sqlite` SHA256:
`e2414174e13dc8f99a1d60c3c586de729c2b3c8de6b098a2ba120ba48ca7ebf1`.
Canonical source audit:
`dda516c73da6cda8d838e3366888d4fca58f06bc798fa5de4f8425ec2020fa48`.

## Commands and failures

Commands run in the owned crew worktree; paths/configuration remain local.

```powershell
python -B -X utf8 server/build.py gateway --test --out local/build/server/gateway-p04i01
python -B -X utf8 local/evidence/20261013-p04i-native-progression-01/store/run_tests03.py
python -B -X utf8 local/evidence/20261013-p04i-native-progression-01/client/run_checks.py run-05
python -B -X utf8 local/p04i/run-web.py --run 03 --full
python -B -X utf8 local/p04i/prepare-native.py --run 05 --mode learn
pwsh -NoProfile -File local/p04i/services.ps1 -Action start -Run 05
python -B -X utf8 local/p04d/run-native.py --install local/evidence/20261013-p04i-native-progression-01/native-install05 --out local/evidence/20261013-p04i-native-progression-01/native-run05
python -B -X utf8 local/p04i/freeze-native.py --run 05 --mode learn
python -B -X utf8 local/p04i/prepare-native.py --run 06 --mode relogin
pwsh -NoProfile -File local/p04i/services.ps1 -Action start -Run 06
python -B -X utf8 local/p04d/run-native.py --install local/evidence/20261013-p04i-native-progression-01/native-install06 --out local/evidence/20261013-p04i-native-progression-01/native-run06
python -B -X utf8 local/p04i/freeze-native.py --run 06 --mode relogin
python -B -X utf8 server/check_layout.py --out local/evidence/20261013-p04i-native-progression-01/layout-final01.json
```

Exact test argv/environment and full independent verifier CLI are in receipts
and [research](../research/P04I_NATIVE_CREW_PROGRESSION.md). These write-once
evidence commands require fresh output names when reproduced. Activation
occurred once from accepted H41 to I42 before native01; failed runs restarted
from the immutable I42 backup, preserving their own failed databases.

Preserved failures: native01 exposed a real PyGFx Python-list data provider
where the adapter expected `.length`; native02 exposed popup lookup requiring
an explicit PersonalCase alias. Both were corrected with regressions and a
complete fresh03/04 run. Root stopped only the identified failed client PIDs;
the separate failed-reset receipts correct the runner's generic stop label.
Initial test-fixture assertion/setup mistakes are retained in store/web logs.
Final staged whitespace check found extra EOF blank lines in three new files;
only those bytes were removed, affected tests rerun, and complete native05/06
binds final raw sources. Successful03/04 evidence remains archived. A Windows
rename WinError5 interrupted one fixture in store regression02; isolated
recheck and full regression03 passed unchanged sources. Root cause is UNKNOWN.

## Limits, rollback and next card

This is first-skill selection and persistence, not completed historical crew.
Current I storage admits one0% skill/freeXP0; the general pure codec is tested
but battle XP, level progression and combat effects are not connected.
Training/retraining/reset, paid hiring, dismissal, personalization and bulk
operations remain unavailable. Historical daily quota is UNKNOWN; cap16 is
explicit test_lab policy. P05 handling and colored rendering debt remain open.

Rollback: restore the owned installation and pre-I SQLite snapshot together
with matching H sources/config, or `git revert -m 1 <P04I-main-merge>` followed
by matching DB restore. Never downgrade a progressed database in place or
rewrite accepted history. No original client or primary P05 files were changed.

One next card: source-bound CMD306 dismissal through native confirmation,
with sparse active IDs, retained tombstones, monotonic IDs and unchanged quota
on deletion. Continue the owner's complete-crew objective afterwards.
