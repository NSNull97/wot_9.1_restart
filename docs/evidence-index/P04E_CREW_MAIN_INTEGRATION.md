# P04E — accepted crew integration on current main

2026-10-13. Goal: close the nine historical Rust fixture failures blocking
P04D, verify the combined crew/ammo/accepted-world baseline, then perform the
standing ordinary no-ff main merge and remote SHA check.

**Acceptance: PASS_APPLICABLE_REGRESSION_AND_NATIVE_CREW_RELOGIN.** Final Git
commit/merge/remote identities are recorded in the local final-card receipt.
No primary battle stand is deployed by this integration.

## Baseline and actual change

Owned worktree:
`C:/Users/NSNull/.codex/worktrees/crew-equipment-snapshot/WoT_9.1_Server`.
Branch: `codex/p04e-crew-main-integration`, from current accepted main
`a998ca39f8d63f8a809336cc4a2b536c6ecb9f9b`, verified against origin.
Incoming crew history: P04D `1449e4c1b10247023c7faf43df27dec49d35bcbf`,
including P04B/P04C and the earlier frozen P09C/P09D dependencies.

The exact portable fixture repair had already landed in P09D `8d61c16` and
current main. This card reuses it; no duplicate relocation implementation,
test weakening, historical hash rewriting or production physics change.
The accepted main also contains P06R's cumulative destruction behavior.

Gateway conflicts in `account/{ammo_session,hangar,identity}.rs`, `main.rs`
and `session.rs` were resolved with logical common base `b13ca5c`. An
independent diff check confirms the exact P04D added/removed lines on top of
current main. `shared/server.rs` remains identical to accepted main.
Client conflicts in `client_patch/sr_interactive.py` and
`tools/interactive_client.py` use the same logical base; P06R helper and
profile observer ASTs remain unchanged. `web/src/game-adapter.mjs` likewise
retains the exact P04D route/profile change. STATUS histories were combined;
the newer accepted P09D plan was preserved.

The integration brings the P04B/P04C domain/source/configuration files and
P04D store/projection/gateway/UI/verifier/test files into main. Their complete
lists and contracts are in the [P04B](P04B.md), [P04C](P04C.md) and
[P04D](P04D_NATIVE_CREW_RECRUITMENT.md) indices. New integration documentation
is this index, its plan and the current STATUS entry. Private inputs and
generated artifacts remain ignored.

## Why the nine failures now pass

Accepted `cfg(test)` relocation pins the original packaged/P06N/P06O pools,
configs, runtime artifacts and geometry. It maps only known historical paths
to verified files inside the current worktree's local directory, creates new
derived configs/pool with their own hashes and records provenance. Production
`Pool::load` still checks ownership and every runtime artifact. Archived worker
stdout retains its original stdout/config hash; it is not passed off as new
output. The test-only helper also supports accepted P06R fixtures.

Missing ignored inputs were copied read-only from the accepted P09D worktree
and checked byte-for-byte. Rust receipt covers234 source/target files,86 newly
copied. Domain/web restored874 files including798 catalog-allowlisted PNGs,
plus one separately pinned bridge archive. Client tests restored two exact
crew02 archive files. Archived export closures were imported by the explicit
versioned resolver; new sidecars and fixture manifests are separate artifacts.
Nine `.gitattributes` LF paths were checked; two stale CRLF copies were restored
to exact index bytes, without logical changes.

## Evidence and current-source checks

All paths below are relative to the owned worktree's
`local/evidence/20261013-p04e-crew-main-integration-01/`.

| Gate | Actual result | Evidence |
|---|---|---|
| Full canonical Rust tests/build |691 PASS,0 FAIL/ignored/filtered; build PASS | `rust/receipt.json` |
| Each of the previous nine failures | All actually executed PASS, including real worker IPC and barriers | Same receipt and named test log |
| Domain/source/store/content/profile4 Python |270 PASS,0 skips | `domain/domain-tests-01.json` |
| Historical crew/ammo/relocation Python |67 PASS,0 skips | `domain/historical-tests-01.json` |
| Client/control/UI Python |287 PASS,0 skips | `client-integration/run-02/receipt.json` |
| Real CPython2.7.3 compilation |7 PASS | `client-integration/run-01/receipt.json` |
| Full Node suite |97 PASS,0 skips | `web/full-web-02.json` |
| Actual native recruit + fresh client/server login | PASS | `independent-native/final01/receipt.json` |
| Three actual native PNGs | Scope-limited visual PASS | `native-pixels.json` |
| Source layout | PASS,87 source files/22 relocations | `layout.json` |
| Independent merge/store review | No blocking findings | `gateway-merge01/review.json`, `client-integration/source-review.json`, `domain/source-review-01.json` |

The624 Python tests above are distinct groups. Initial missing-fixture/CRLF
failures and a Node96PASS/1FAIL run remain preserved; their complete successful
reruns are separately recorded. No final required regression is skipped.
Current source/build/install hashes are bound in `acceptance-final/receipt.json`.

## Fresh original-client evidence

Original: read-only `C:/WoT_0.9.1_RU_0717_original`, manifest
`74c37c18e9ac7e30196c134076dacf6f2a8bf3897f7def73905d09feb3647797`.
Own independent slot-B copy: `local/clients/p04d-b`.
Fresh own game/identity DBs live in `local/p04e/runtime`, copied consistently
from our prior owned seed/identity DBs. The previous accepted recruitment DB
was not reset. No other task's database, client or live processes were changed.

Canonical executable:
`local/build/server/gateway-p04e01/target/debug/sr-gateway.exe`, SHA256
`5d6852500eb6667794153fe21ca9b558bc20610f76cb98eb0acd18e24fb862e5`.
Loopback ports23114/23115/3405 belong only to this card.

Client38900 recruited once through the original RecruitWindow/callback.
Independent decryption verifies CMD309/request226/method0x90, the exact158-byte
inventory delta and update-before-success. DB revision6→7, new ID3 seated in
MS-1, ID2 retained in barracks, quota1→0,100000credits/0gold unchanged.
The native cache agrees with the authoritative descriptor/seat/identity state.

Bridge42876/gateway47164 were stopped after receipt/executable verification.
Fresh bridge26056/gateway43708 then loaded the same database; new client34800
reused the local preferences and observed exactly the same crew state.
The second trace is a read-only relogin, with no second recruitment command.
The separate consistent DB backups are `native-persistence/after-recruit.sqlite`
and `after-relogin.sqlite`; all16 non-rate-limit tables compare equal. The
seventeenth table contains authentication rate-limit counters, whose same-key
increments/window rollover match the new login. An initial overly broad
17-table comparison failed and is retained with its correction explanation.
`independent-native/restart-chain02.json` binds this comparison, all61
gateway source files and both31-module native compile/install/restore chains.

Raw captures are `native-wire01/02`; traces are
`native-runtime01/native-38900-1791897820908.jsonl` and
`native-runtime02/native-34800-1791897969252.jsonl`. Both clients exited0
without timeout. Both `native-install01/02` ledgers are RESTORED and both
fresh services were stopped; no one-shot scenario remains armed.

## Commands actually executed

Run from the owned worktree; exact environment and full argv are in receipts:

```powershell
python -B -X utf8 server/build.py gateway --test --out local/build/server/gateway-p04e01
npm --prefix web test
python -B -X utf8 server/check_layout.py
```

The three Python unittest module lists, bundle/config paths and all test
names are saved in the domain/historical/client receipts above. Native setup
used explicit `--research-copy local/clients/p04d-b`, endpoint23114, own key,
the real Python2.7 compiler and both `--enable-p09d-ammo-service` and
`--enable-crew-recruitment`. Exact prepare/install source bindings are in
`native-install01/02/install-plan.json`. Native launch and restoration:

```powershell
python -B -X utf8 local/p04d/run-native.py --install local/evidence/20261013-p04e-crew-main-integration-01/native-install01 --out local/evidence/20261013-p04e-crew-main-integration-01/native-run01
python -B -X utf8 local/p04d/run-native.py --install local/evidence/20261013-p04e-crew-main-integration-01/native-install02 --out local/evidence/20261013-p04e-crew-main-integration-01/native-run02
python -B -X utf8 tools/interactive_client.py rollback --out local/evidence/20261013-p04e-crew-main-integration-01/native-install01
python -B -X utf8 tools/interactive_client.py rollback --out local/evidence/20261013-p04e-crew-main-integration-01/native-install02
```

Independent verification uses `tools/p04d_native_crew_verify.py` with both
wire captures, both successful traces, the immutable post-relogin backup and
the actual install plan. Raw keys, credentials, SQLite and client resources
are retained locally and excluded from Git.

## Claims, rollback and next step

VERIFIED: source/pin/build/archived-evidence identities and actual test results.
OBSERVED: original #717 callbacks, network command, server mutation, subsequent
native UI/cache and fresh-login persistence on this Windows environment.
INFERRED: applicability to equivalent owned checkouts with the same inputs.
UNKNOWN/unsupported: other recruitment roles/vehicles, skills, retraining,
dismissal, historical paid tariffs, general graphics quality and Linux behavior.

This remains one free100% MS-1 driver with a fixed test passport. P04C's
configuration reservation remains its isolated source-bound contract; native
profile6 battle admission is false. Existing P03M work is not deployed or
replaced. Physical mouse input/manual owner acceptance is NOT_RUN; the declared
gate uses actual original callbacks. Colored background artifacts remain.

Runtime rollback is already complete via owned installation ledgers/processes;
both the new DB and earlier accepted P04D DB remain available. Source rollback
is `git revert -m 1 <P04E-main-merge-SHA-from-final-card.json>`, coordinating any
later cards. Never reset another checkout or replace its database.

**One next crew step:** native crew reassignment/removal through the original
interface, with server ownership and persistence, as a separate card.
