# P09D acceptance repair — historical evidence and real client recheck

## Goal and scope

**Acceptance: PASS_APPLICABLE_AUTOMATIC_AND_NATIVE.** Final merge and remote
identity are recorded in the local `final-card.json` after push.

Owner requested repair of historical evidence paths and missing fixtures,
rerun of failed checks, then ordinary no-ff merge into main after green.
This is the completion of P09D, not a new gameplay card. Work is confined to
`C:/Users/NSNull/.codex/worktrees/p09c-ammo-service/WoT_9.1_Server`.
The accepted P06R main `eb054618bd0eae1ae23bba42a0f875969ac2d24e` was integrated
into P09D before validation (merge `58fe72c`). The primary checkout remains
on its independent P03M branch; neither its client nor services are deployed
by this card. The original #717 client remains read-only.

## Repair design and changed files

- `tools/native_evidence_relocation.py`, `web/src/native-evidence.mjs`:
  explicit version1 sidecar for the two exact accepted crew/ammo export01
  checkpoints. Export, install plan, outcome, trace, compiled probe and
  metadata retain their historical bytes/hashes. Six exact mapped files,
  canonical schema, path containment, size limits and no-link checks are
  mandatory. No automatic primary-checkout fallback is used. Python retains
  complete producer/native-event/clean-outcome/resource validation; Node
  rechecks the original proof closure on use.
- `tools/ms1_crew_state.py`, `tools/ms1_ammo_state.py`,
  `web/src/ms1-crew.mjs`, `web/src/ms1-ammo.mjs`: use the explicit resolver.
  Historical manifests retain their true old producer hash. New manifests
  record the actual current producer and relocation dependency hashes.
- `.gitattributes`: nine files whose raw source bytes participate in provenance
  use LF across Windows checkouts. This changes no historical evidence.
- `server/gateway/src/shared/server_worker_fixtures.rs`,
  `server_catalog_tests.rs`, `server_fracture_real_tests.rs`,
  `server/gateway/src/{main.rs,shared/server.rs,drive/worker.rs,drive/world.rs}`:
  cfg(test)-only fixture relocation. Pinned source pool/configs remain
  immutable; explicit derived paths/config hashes are used for new worker
  executions. Archived stdout is parsed against its original config/hash.
  Production worker, Pool loader and response parser are unchanged.
- `tests/test_shared_lab_control.py`, `tests/test_hangar_windows_scenario.py`:
  include the accepted P06R helper in the AST test extraction; resolve the
  exact pinned historical crew02 trace within this checkout without editing
  its plan. `tests/native_fixture_migration.py`, `tests/test_ms1_crew_state.py`,
  `tests/test_ms1_ammo_state.py`: explicit test fixture migration produces new
  manifests and requires six native payloads plus four domain input files
  to be byte-identical to their pinned archives.
- `tests/test_native_evidence_relocation.py`,
  `web/tests/native-evidence.test.mjs`, `web/tests/ms1-ammo.test.mjs`:
  positive and hostile relocation/provenance coverage.
- `web/tests/email-nickname.test.mjs`: the missing old encoder is not
  reconstructed or impersonated. Test its real nine-file archived output,
  plus current real encoder catalog1 output with varied account/resources.
  Both retain identity, tamper, no-overwrite, ledger and migration checks.
- `web/tests/helpers.mjs`: select test ports by checking TCP and UDP together,
  with bounded retries and cleanup; the production lease still owns the final
  bind. A TCP-only check had selected a number already occupied by UDP.
- `web/src/catalog.mjs`: send only the allowlisted basename relative to its
  exact directory root. Express otherwise rejected the `.codex` ancestor as
  a dotfile and returned HTTP500 for valid PNGs. The allowlist and dotfiles deny
  policy are unchanged; independent review is in `client/catalog-dotpath-review.json`.
- This report, `docs/STATUS.md` and `docs/plans/P09D_NATIVE_AMMO_SERVICE.md`.

Missing local assets are copied exactly with SHA receipts, not committed:
worker artifacts, original portable profile bundles, archived native proofs,
nine-file old r1 profile, and 798 tracked-catalog-allowlisted PNGs. No client
binary/resource, database, password, token, capture or private fixture enters Git.

## Evidence and actual checks

All paths below are relative to this worktree's
`local/evidence/20261013-p09d-acceptance-repair-01/`.

| Gate | Actual result | Evidence |
| --- | --- | --- |
| Full canonical gateway build/tests | 674 PASS, 0 FAIL, 0 ignored/filter | `rust/receipt.json` |
| Domain/store + content/profile4 validation | 114 PASS, 0 FAIL/SKIP | `domain-02/receipt.json`, `tests.log` |
| Client/control regression | 240 PASS, 0 FAIL/SKIP | `client/run-03/receipt.json` |
| Real CPython 2.7.3 compile | 4 PASS | `client/run-03/receipt.json` |
| Crew/ammo/relocation Python | 53 PASS, 0 FAIL/SKIP | `python-relocation-04.log` |
| Full web suite | 96 PASS, 0 FAIL/SKIP | `final-web-03/receipt.json` |
| Independent source review | PASS, no blocker found | `client/source-review-01.json` |
| Source layout | PASS | `layout.json` |
| Fresh real native six-service scenario | PASS | `independent-native/run-01/receipt.json` |
| All 12 original scenario PNGs visually inspected | PASS | `native-pixels-review.json` |
| Normal DB preserved through full service/client restart | PASS, seven durable tables equal, revision13 | `normal-durable-after-restart.json` |
| Final Git/source/evidence binding and remote SHA | See actual final receipt | `final-card.json` |

Intermediate failures remain recorded: Rust 664/10, then673/1; client test
238/1error/1skip before its two fixture repairs; old Python fixture-path
failures; expanded domain107/2errors/1skip before portable bundle restoration;
full web90/6 before missing media and test-port repair, then92/4 before
fixing the verified Express dot-directory issue. The first new native
startup also correctly rejected a malformed local service token (64 hex plus
CRLF rather than43 base64url bytes). Only local configuration was corrected;
`native-startup-correction.json` records it. No failed trace is relabelled PASS.

## Fresh native execution

Actual client PID46432 ran the frozen merged source and gateway SHA256
`b6c701c700e1ed4c450b68eeb842d8f98e2decdb8dfc6a43da4b1fcb342b49a6`.
The scenario uses a fresh isolated database copied from the actual revision7
backup SHA256 `224d92e2c617230e3357d067f8c2135e75869497c5fc38ec456a1553b6235b9c`.
It never resets or replaces the normal live database. Loopback ports20134,
20136 and20140 belong only to this recheck.

Native original maintenance callbacks sent requests226–231. Independent
read-only decryption verifies six real CMD108 commands, six142-byte original
Account.update deltas, each before its success callback. Persistent revision
advanced7→13. MS-1 unload/refill/restore and IS-7 unload/refill/restore conserve
all six shell totals and credits/gold/freeXP. Final loads are MS-1 42/36/18,
IS-7 21/9/0; final depot and mount rows exactly equal the starting rows.
The client completed all seven stages and exited naturally. The final
immutable backup SHA is
`25c7ede66c95a61b306c189e9c8e5fbcee4d1e35eeb30ca480b635beda4c5e48`.

Root viewed all twelve actual native PNGs and read the visible loaded/depot
values. Pre-action service screenshots are distinguished from subsequent
results. Colored rendering artifacts visible in the background are not
claimed fixed. Scenario input invokes source-pinned original Flash callbacks;
OS pointer automation and human/manual owner acceptance are NOT_RUN.

Recheck services are stopped and `native-install-01/restore.json` verifies
ledger rollback. The ordinary own stand was restarted on the tested gateway
and current bridge using its preserved revision13 database. Its new versioned
installation is `normal-install-01`, with no armed servicing scenario; only a
consumed one-shot test login and passive hangar capture. Final process identities
and capture are recorded in `normal-handoff.json` and `final-card.json`. This does not deploy P03M's
primary battle stand.

## Reproduction commands

Execute in the managed worktree. Historical import is explicit and append-only:

```powershell
python -B -X utf8 tools/native_evidence_relocation.py --source D:/WoT_9.1_Server/local/evidence/20261005-p02-ms1-crew/native-ms1-crew-export01.json --source-root D:/WoT_9.1_Server/local --out local/evidence/20261005-p02-ms1-crew/native-ms1-crew-export01.json
python -B -X utf8 tools/native_evidence_relocation.py --source D:/WoT_9.1_Server/local/evidence/20261005-p02-ms1-ammo/native-ms1-ammo-export01.json --source-root D:/WoT_9.1_Server/local --out local/evidence/20261005-p02-ms1-ammo/native-ms1-ammo-export01.json
python -B -X utf8 tests/native_fixture_migration.py --out local/evidence/<fresh-run>/migrated-fixtures
$env:MS1_TEST_FIXTURE_ROOT='local/evidence/20261013-p09d-acceptance-repair-01/migrated-fixtures-01'
$env:MS1_CREW_TEST_EXPORT='local/evidence/20261005-p02-ms1-crew/native-ms1-crew-export01.json'
$env:MS1_AMMO_TEST_EXPORT='local/evidence/20261005-p02-ms1-ammo/native-ms1-ammo-export01.json'
python -B -X utf8 -m unittest -v tests.test_native_evidence_relocation tests.test_ms1_crew_state tests.test_ms1_ammo_state
python -B -X utf8 -m unittest -v tests.test_p09d_ammo_projection tests.test_p09d_ammo_store tests.test_p09c_ammo_catalog tests.test_p09c_ammo_service tests.test_game_profile_tx tests.test_content_bundle tests.test_profile4_chain tests.test_profile4_semantic_diff
python -B -X utf8 server/build.py gateway --test --out local/build/server/gateway-p09d-acceptance-repair-03
npm --prefix web test
python -B -X utf8 server/check_layout.py --out local/evidence/<fresh-run>/layout.json
```

Exact client240 command and real compiler argv are preserved in
`client/run-03/receipt.json`. Rust fixture copying is described and hash-bound
in `rust/fixture-copy*.json` and `rust/receipt.json`; portable profile restoration
in `rust/profile4-fixture-repair/receipt.json`. Private files intentionally do
not travel with the public Git source. Missing input remains a hard failure,
not a successful skipped compatibility test.

Native recheck preparation and original command flags are in
`client/native-recheck-plan.json`, `native-install-01/install-plan.json`,
`native-runtime-preparation.json`. The canonical server entrypoints were:

```powershell
node server/identity/service.mjs --config local/p09d/acceptance-runtime-01/bridge.json
local/build/server/gateway-p09d-acceptance-repair-03/target/debug/sr-gateway.exe legacy091-interactive local/p09d/acceptance-runtime-01/native-private.pem local/p09d/acceptance-runtime-01/client-digest.bin local/p09d/acceptance-runtime-01/gateway.json <absolute-repair-root>/native-wire-02
```

Use fresh output directories for another run; do not overwrite the acceptance
records or reset the normal database. Secrets are local and omitted from logs.

## Claim limits, rollback and next step

VERIFIED: pinned historical/native source bytes, unchanged archived outputs,
canonical test logs and current source bindings. OBSERVED: one tested Windows
#717 environment, actual native callbacks/UDP, persisted ammo and visible UI.
INFERRED: equivalent servicing under the same exact mount/source constraints.
UNKNOWN: unrestricted other tanks/mounts, historical prices/purchases,
automatic refill, repair/equipment and battle-consumption integration; no claim
is made for them. The exact missing old encoder source is UNKNOWN/unrecovered;
its execution is NOT_RUN, while its authentic saved output is verified.

Rollback source with `git revert -m 1 <merge-SHA-from-final-card.json>` after
coordinating any later cards. To remove this client installation, first verify
and stop only its receipt-owned WorldOfTanks process, then run:

```powershell
python -B -X utf8 tools/interactive_client.py rollback --out local/evidence/20261013-p09d-acceptance-repair-01/normal-install-01
```

Stop only the receipt-owned gateway/bridge; preserve the live game DB and all
immutable evidence. Historical archives require no rollback because they were
not edited. Local derived imports can be retained for reproducibility.

One next recommended step: complete the already-active P03M source-bound IS-7
battle/runtime gate, using the accepted authoritative loadout as its input.
No next card is started or altered by this acceptance repair.
