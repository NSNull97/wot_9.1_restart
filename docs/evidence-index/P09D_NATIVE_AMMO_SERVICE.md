# P09D — native hangar ammunition service

Owner request: connect MS-1 and IS-7 servicing to the actual #717 hangar and
verify it in the real client. Branch `codex/p09d-native-ammo-service` depends
on P09C `7fb0e479dce684af0940fe37e5798d54d1c1e7fd`. The primary P06R checkout,
its database and the original client are separate and were not deployed over.

## Reproducible local stand

All private paths below are relative to this card's managed worktree:
`C:\Users\NSNull\.codex\worktrees\p09c-ammo-service\WoT_9.1_Server`.

- `local/p09d/runtime/game.sqlite` is an SQLite online backup of the existing
  game database, explicitly migrated in place. It is the sole authoritative
  game database of this stand; there is no ammunition sidecar database.
- `local/p09d/runtime/portal.sqlite` is a separate online backup of the existing
  project identity database. Original project test credentials were used only
  through the original login flow; credentials and service keys remain ignored.
- `local/p09d/source-bundle-05` preserves the verified portable profile4 source.
- `local/clients/p09d-a` is an independent full resource copy with the existing
  documented two-string instance-mutex patch, source receipt `sr_lab_copy.json`.
- Identity listens on `127.0.0.1:20120`; native login/base use 20114/20116.
  This stand does not replace the primary 20014/20016/20020 service.

The opt-in `ammunition_service` gateway flag and versioned bridge configuration
must agree. `--enable-p09d-ammo-service` admits the native maintenance window
for exactly the two P09C source-bound mounts. Purchases, automatic servicing,
repair, equipment changes and battle admission are unsupported. Activation
preserves the initial twenty MS-1 AP rounds and journals one grant of 100
rounds of each of the six supported shell definitions. Re-activation does not
grant again. This is explicit test stock, not a historical starting balance.

## Implementation and verified boundaries

`tools/p09d_ammo_store.py` commits P09C stock/load quantities, layout order and
currency signs, snapshot, existing `game_profiles` projection and both command
ledgers in one transaction. Requests contain only the original bounded CMD108
layout; the gateway supplies authenticated account identity and the admitted
persistent revision. All incoming data remain primitives.

`tools/p09d_ammo_projection.py` first re-encodes the source descriptors to the
exact original fixture bytes. It projects immutable profile5 login fixtures
and a bounded Account.update delta. The source shop revision is **3**, while
connection-local Account revision starts at **1**. Delta construction and its
240-byte bound run before commit. The actual initial service deltas were 142
bytes.

`server/gateway/src/account/ammo_session.rs` schedules the HTTP worker only
after the entire cloned receive frame and piggyback tree have committed. One
worker, bounded pending commands, a random session command prefix and durable
replay prevent duplicate debits. Committed updates precede success responses.
An earlier valid refresh cursor receives the current no-change delta behind
the already queued update, matching original AccountSyncData semantics.
Ambiguous worker outcomes require a fresh login. Battle modes reject this
configuration; the existing profile4 battle loadout is not silently changed.

Original source pins and the exact native callback contract are documented in
[the source report](../research/P09D_NATIVE_AMMO_SOURCE.md). The passive UI
helper preserves original fillVehicle, Inventory and Account handlers.

## Executed checks and retained limitations

- P09D persistence/projection plus P09C/P09B: **101 Python PASS**; actual HTTP
  login, service, replay and restart integration: **1 PASS**. Receipts:
  `local/evidence/20261013-p09d-native-ammo-01/persistence-validation-02/`.
- Codec **10 PASS**, hangar regression **20 PASS**, final scheduler **11 PASS**.
  Receipt/logs: `local/evidence/20261013-p09d-native-ammo-01/codec/`.
- Native gateway build02 and its scheduler gate PASS, executable SHA256
  `492e5d5ad918025c618cd2aab19eda22817c0b10eaf7c89831532154e56f3113`.
  Build receipt: `local/build/gateway-p09d-native-02/result.json`.
- Identity HTTP/reply boundary **7 PASS** in build01. No dependency versions
  changed; the lockfile's incidental package sorting is not an intended change.
- Current bridge/test-garage/vehicle-status/P09D regression: **21 PASS**, zero
  skips. Historic MS-1 ammunition suite: **3 PASS / 5 FAIL**, zero skips. Its
  old crew/ammo proof paths are absolute paths in the primary checkout and fail
  the managed worktree's strict local-path boundary. Immutable proof files were
  not rewritten to manufacture a passing result. Full diagnostic receipt:
  `local/evidence/20261013-p09d-native-ammo-service/bridge-regression-receipt-01.json`.
  One intermediate bridge run had a transient 503; subsequent isolated and
  combined runs passed, but that transient's cause remains UNKNOWN.
- Broader Rust `ammo` filter retained six failures for absent historical
  fixture/pool paths. The new codec/session/hangar gates above are separate
  targeted results, not a claim that the complete historical suite is green.

## Actual native observations

Native PID43004, trace
`local/evidence/20261013-p09d-native-ammo-service/runtime-02/native-43004-1791892368675.jsonl`,
used the original maintenance callback and native transport:

| Request | Vehicle | Loaded after operation | Depot after operation | Persistent revision |
| --- | --- | --- | --- | --- |
| 226 | IS-7 | AP21, APCR9, HE0 | 79, 91, 100 | 6 |
| 227 | MS-1 | AP42, HEAT36, HE18 | 78, 64, 82 | 7 |

Each operation has original Account.update -> Account._update return661 with
matching raw/GUI quantities -> original onCmdResponseExt(result0), in that
order. Gateway logs are `local/p09d/runtime/gateway-03.stdout.log`; the online
database snapshot is `local/p09d/runtime/after-native-two-service.sqlite`.
The input actor is not inferred from the traces; these are actual observed
native callback actions, not a claim of successful Computer Use pointer input.
Independent RSA/Blowfish decoding of the actual own UDP capture confirms
`0x57` with the exact durable-ledger delta, followed by `0x4d`: sequence52/53
for IS-7 and62/63 for MS-1. The audit also checks native Flash maintenance
payloads and all six conservation totals. Receipt:
`local/evidence/20261013-p09d-native-ammo-01/codec/native-independent-03/receipt.json`.

The client, gateway and identity process were then stopped and restarted.
Native PID40676 loaded persistent revision7 as a new wire revision1. The
client-generated `runtime-02/screenshots/hangar_001.png` visibly shows MS-1
42/36/18. Replaying the exact first native command through the authenticated
loopback boundary after that restart returned its original result and left
all seven state/ledger projections byte-identical; `live-replay-01.json`
records both hashes. No replay response was injected into the native client.

Windows Computer Use could enumerate the correct owned window but its image
capture repeatedly returned `FrameArrived timed out` / `window capture timed
out`, including recovery. The native renderer's own PNG was captured and
inspected instead. The first client run also exposed a partial-import profiler
failure before login; the fix and real Python2.7 compilation are recorded in
`partial-import-fix-01/` and `partial-import-fix-02/`. That failed installation
was restored with its ledger; it is not counted as a passing native run.

### Completed native unload/refill/restoration

Install04 / native PID20020 completed the seven-stage scenario at87.2886s
and exited through the diagnostic's normal original quit path. Its six actual
service requests advanced persistent revision7→13 and wire revision1→7:

| Request | Mount | Loaded | Depot | Persistent revision |
| --- | --- | --- | --- | --- |
| 226 | MS-1 unload | 41/35/17 | 79/65/83 | 8 |
| 227 | MS-1 refill/change | 40/30/26 | 80/70/74 | 9 |
| 228 | IS-7 unload | 20/8/0 | 80/92/100 | 10 |
| 229 | IS-7 refill/change | 18/8/4 | 82/92/96 | 11 |
| 230 | MS-1 restore | 42/36/18 | 78/64/82 | 12 |
| 231 | IS-7 restore | 21/9/0 | 79/91/100 | 13 |

The real original Flash-bound maintenance callback initiates each request;
no inventory/cache state is assigned by the scenario. Original request,
Account.update, Inventory/GUI values, layout processor and response are checked
before advancing. Both restored windows are reopened and rendered. Bounds are
30s per phase,210s total,240 observations,12 unique native PNGs.

Independent RSA/Blowfish decoding of the actual own wire capture confirms all
six CMD108 layouts, exact142-byte durable deltas and update-before-success.
The final mount and depot database rows exactly equal the pre-scenario backup,
including all quantities; resources/crew/dossier identity remains unchanged.
`local/p09d/runtime/after-native-scenario.sqlite` has revision13, eight total
native commands and SQLite integrity `ok`; SHA256
`f29ba3385decd87ac14e6a9d86e2714ab2aa7e85262cae822c6fc752f3ee5348`.

Evidence:

- `local/evidence/20261013-p09d-native-ammo-01/codec/native-scenario-independent-02/receipt.json`;
  an earlier audit-tool missing-field assumption is preserved as attempt01 FAIL,
  not represented as a product failure.
- `runtime-03/native-20020-1791893740924.jsonl`, `wire-05/`, and
  `local/p09d/runtime/gateway-05.stdout.log`.
- `runtime-03/screenshots/`:12 actual1024x768 native PNGs, all visually inspected
  across `native-pixels-root-01.json` and `visual-review-subagent-01/receipt.json`.
  Some filenames name the upcoming action; e.g. `ms1_refill` shows the completed
  unload before refill. The receipts distinguish pre-action and result values.
- `scenario-check-02/receipt.json`:152 regression tests PASS, actual Python2.7
  scenario/wiring compilation PASS. `final-validation-01/receipt.json`:101
  Python and21 Node PASS, source hashes unchanged, zero skips. The separately
  rerun HTTP test is included in21 and is not counted twice.
- `native-source-final-01/receipt.json`: all original static source pins rechecked.

This is **OBSERVED_NATIVE**, programmatically invoking original UI callbacks.
Computer Use could not capture this DirectX window. Human/OS-pointer acceptance
is NOT_RUN. Native pixels were separately reviewed; background rendering
artifacts are visible, so no general graphics-quality claim is made.

Install03 was only prepared and superseded before installation by a diagnostic
callback-recording fix. Install04 is ledger-restored. Normal install05 has
`verify_p09d_ammo=false`, no quit trigger and no scenario events. Its one-shot
login file was consumed and deleted. Fresh native PID48100 after restart of
both services shows IS-7 21/9/0 in
`runtime-04/screenshots/hangar_001.png`; normal GUI service remains available.
Owned running processes at handoff: client48100, gateway27452, bridge21252.
PID files are under `local/p09d/runtime/`; always recheck process identity before
stopping. Gateway invocation is bounded to7200s; there is no installed daemon.

### Acceptance and outstanding gate

Native scoped acceptance: **PASS_NATIVE_AMMO_SERVICE_OWNED_STOCK_TEST_LAB**.
Merge acceptance: **HOLD_IN_BRANCH_REQUIRED_REGRESSION_FAIL**. The five legacy
bridge failures and six missing-fixture Rust failures remain documented, not
silently skipped. P09D is committed on its own branch; main is not merged.
The final local `final-card-01.json` binds the delivered commit, evidence and
source hashes. The only recommended next task is historical proof portability
and the failed-gate rerun before integration.

### Changed files

- Gateway: new `server/gateway/src/account/ammo_service.rs`, `ammo_session.rs`;
  integration in `account/hangar.rs`, `account/identity.rs`, `session.rs`,
  `main.rs` and `shared/server.rs`.
- DB/projection/bridge: new `tools/p09d_ammo_store.py`,
  `tools/p09d_ammo_projection.py`, `web/src/p09d-ammo.mjs`; minimal hook in
  `web/src/game-adapter.mjs`.
- Native/helper/diagnostic: `client_patch/p09d_ammo_ui.py`,
  `p09d_ammo_scenario.py`, `hangar_capabilities.py`, `sr_interactive.py`;
  `tools/interactive_client.py`, `p09d_native_ammo_audit.py`, `p09d_ammo_control.py`.
- Tests: five new `tests/test_p09d_ammo_*.py`, `web/tests/p09d-ammo.test.mjs`,
  and narrow existing fixture/wiring updates in
  `test_interactive_relogin_control.py`, `test_interactive_window_trace.py`,
  `test_ms1_ammo_profile.py`.
- Docs: this index, P09D plan/source report and `docs/STATUS.md`.

No dependency version changes. Cargo.lock was restored to exact HEAD bytes;
four frozen historical files retain exact HEAD/LF content with no semantic diff.

## Commands and rollback

Build: `python -B -X utf8 server/build.py gateway --test --test-filter ammo_session --out local/build/gateway-p09d-native-02`.
Bridge: `node server/identity/service.mjs --config local/p09d/runtime/bridge.json`.
Gateway: built `sr-gateway.exe legacy091-interactive` with this stand's private
key, client digest, gateway configuration and an **absolute fresh** capture
directory. The initial relative capture path failed before listener startup;
its log is retained as gateway01, not counted as native success.

Prepare/install/rollback use `tools/interactive_client.py` and a fresh
`local/evidence/20261013-p09d-native-ammo-service/install-NN` receipt directory.
Launch the copied EXE with its own client directory as working directory.
Only the recorded owned process IDs may be stopped. Diagnostic installs must
be restored by their exact ledger, never by overwriting unknown client edits.

Rollback this isolated service by stopping its recorded processes, restoring
its client install ledger, and retaining/archiving its database and fixtures
as evidence. The primary service database was not migrated, so no shared DB
rollback is needed. Source rollback is a revert of the P09D commit, retaining
the independently accepted P09C dependency. Do not merge while a required
regression remains FAIL/NOT_RUN; the historical proof relocation remains
explicit work rather than an exception invented for this card.


Normal service use on the isolated client: select MS-1 or IS-7, open
**Обслуживание**, change the three shell counts within owned depot stock and
capacity, then **Принять**. Unloading returns rounds to the same depot. Stock
limits and unsupported purchase attempts are validated by the server.

Final test commands (execute from this worktree):

```powershell
python -B -X utf8 -m unittest tests.test_p09d_ammo_projection tests.test_p09d_ammo_store tests.test_p09c_ammo_catalog tests.test_p09c_ammo_service tests.test_game_profile_tx -v
node --test --test-concurrency=1 web/tests/game-adapter.test.mjs web/tests/test-garage.test.mjs web/tests/vehicle-status.test.mjs web/tests/p09d-ammo.test.mjs
python -B -X utf8 server/check_layout.py
```

The exact152-test client command and Python2.7 compile arguments are in
`scenario-check-02/receipt.json`. The native gateway invocation is:

```powershell
local/build/gateway-p09d-native-02/target/debug/sr-gateway.exe legacy091-interactive local/p09d/runtime/native-private.pem local/p09d/runtime/client-digest.bin local/p09d/runtime/gateway.json <absolute-fresh-capture-directory>
```

After stopping only verified owned processes, restore the active normal client
installation with:

```powershell
python -B -X utf8 tools/interactive_client.py rollback --out local/evidence/20261013-p09d-native-ammo-service/install-05
```

Private ignored evidence includes local account identifiers and protocol traces;
no credentials, keys, client resources, databases or native dumps are staged.
