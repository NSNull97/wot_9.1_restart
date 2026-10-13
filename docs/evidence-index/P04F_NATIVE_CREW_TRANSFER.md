# P04F — native crew unloading and reassignment

2026-10-13. Owner request: unload and reassign crew through the original
interface. The operation is general; MS-1 is the first mutable native profile
with verified source data, not a different assignment algorithm for every tank.

Branch `codex/p04f-native-crew-transfer`, original accepted baseline
`06582030050c7b6720f4616dffa50b2be61e4abc`. Implementation checkpoint72352b5;
accepted concurrent P03M main0393857 was merged as a233166 before final checks.
**Acceptance: PASS_NATIVE_CREW_TRANSFER_CURRENT_MAIN.** Final Git/source/build/
native/remote bindings are recorded in the local `acceptance-final` receipt.

## Ownership and implementation

Owned worktree: `C:/Users/NSNull/.codex/worktrees/crew-equipment-snapshot/WoT_9.1_Server`.
Evidence root, abbreviated E below:
`local/evidence/20261013-p04f-native-crew-transfer-01/`.
Read-only original: `C:/WoT_0.9.1_RU_0717_original`.
Only independent client `local/clients/p04d-b` and our isolated profile are
installed. Loopback23214/23215/3415, own keys and own test credentials.
Primary P03M/P05 and sibling stands are not deployed or modified.

Changed files by responsibility:

- `server/domain/crew_transfer.py`, `tools/p04f_crew_store.py` and
  `tools/p04f_crew_projection.py`: generic role/seat assignment transition,
  versioned profile6-to7 migration, one authoritative SQLite writer, replay,
  ownership/reservation/capacity validation and native vacancies.
- `server/gateway/src/account/{crew_transfer,crew_service,ammo_session,hangar,identity}.rs`,
  `main.rs`, `session.rs`: bounded CMD105 decoder, opt-in policy, shared queue,
  authenticated bridge and update-before-success.
- `web/src/{p04f-crew,p04d-crew,game-adapter}.mjs`: profile7 validation and
  server-owned transfer route on the existing worker.
- `client_patch/{p04f_crew_ui,crew_capabilities,hangar_bootstrap,sr_interactive}.py`,
  `tools/interactive_client.py`: exact original callback whitelist, explicit
  opt-in, passive observers and bounded native diagnostic scenario.
- `tools/p04f_crew_source_audit.py`, `tools/p04f_native_crew_verify.py`,
  corresponding `tests/test_p04f_*`, `tests/test_crew_transfer.py`,
  `tests/test_crew_capabilities.py`, `web/tests/p04f-crew.test.mjs`: source pins,
  independent evidence checks and positive/adversarial regression cases.
- `server/gateway/src/shared/{server_worker_fixtures,server_is7_real_tests}.rs`:
  test-only relocation of the accepted P03M pool into this checkout, preserving
  original pool/config/profile hashes and production ownership validation.
- This index, the [research report](../research/P04F_NATIVE_CREW_TRANSFER.md),
  [plan](../plans/P04F_NATIVE_CREW_TRANSFER.md) and STATUS.

Schema `p04f-native-crew-transfer.v1`; policy SHA256
`35a58c8e13d9b815f8552371bbd6556ba10c091753861e697e522d6a5c877cb2`.
No broad menu enablement, invented wire API, new tankman identity, client-side
inventory mutation or second database writer closes this gate.

## Source and native result

Source audit pins25 originals and31 anchors. Actual #717 packets independently
confirm CMD105/method0x8e, VAR2 payload20 with `<hhqii>` arguments.
Seven original callbacks unload the driver, seat driver2, replace with driver3,
unload/reseat commander1, unload the whole crew, then seat commander1 again.
Final crew `[1, None]`; both drivers remain in barracks. Each inventory delta
precedes the successful original callback; credits, gold, quota, ammunition,
all three identities and descriptors remain unchanged.

First successful sequence: native PID7696, request226–232, E/native-wire02 and
`native-runtime02/native-7696-1791901697651.jsonl`. Fresh relogin PID35208 uses
E/native-wire04 and `native-runtime04/native-35208-1791902154809.jsonl`.
Shared revision8→15, configuration revision2→9; all18 non-rate-limit database
tables are identical after relogin. Gate:
`independent-native/final01/receipt.json`,
`PASS_NATIVE_CREW_TRANSFER_WIRE_RELOGIN`.

Relogin is established by the fresh process, original cache trace, authenticated
capture and unchanged durable backups. Only operation deltas are independently
matched byte-for-byte to the transfer wire; a complete bytewise relogin sync
comparison is not claimed. Four native PNGs were inspected by root with
`view_image`; scope and hashes are in `native-pixels01.json`.

The initial DB is a consistent copy of accepted P04E; no old evidence/database
is reset. Migration retains IDs/descriptors/quota0/configuration2, balances,
ammo and old ledger; shared revision7→8. Thirteen previous tables remain
identical, four change by the migration contract, two new tables are added.
`store/migration-comparison-final.json` records the comparison.

## Completed checks before concurrent main integration

| Gate | Result | Evidence under E |
|---|---|---|
| Canonical Rust full suite/build |698 PASS, build PASS | build `local/build/server/gateway-p04f02/result.json`, `rust/source-current02.json` |
| Store/domain/source regression |315 PASS,0 skips | `store/final-receipt.json` |
| Historical fixture tests |67 PASS,0 skips | `store/historical-01.json` |
| Client/control |312 distinct PASS,0 skips | `client/run-01/receipt.json`, `client/run-02-selection-guard/receipt.json` |
| Actual CPython2.7.3 compilation |8 PASS | `client/run-01/receipt.json` |
| Source/verifier tests |34 PASS,0 skips | `source-audit/combined-tests03.log` |
| Full Node |98 PASS,0 skips | `web/full-web03.json` |
| Native seven operations/relogin |PASS | `independent-native/final01/receipt.json` |
| Independent verifier review |PASS after two fixes | `store/native-verifier-review-final.json` |

The Python groups above contain728 distinct tests. Final combined-main tests,
new executable and repeated native proof are recorded separately, not silently
substituted for earlier results. Node's broad hash collector observed a change
to the independent native verifier during its run; that file is not an input to
the Node suite. Actual web/runtime input hashes are separately bound at final.

Preserved failed attempts: initial Rust serde-derive compile error (corrected
without a new dependency); initial Node run with7 missing-environment skips,
then a transient listener check failure, followed by98/98 PASS. Native01
aborted before any transfer after selected vehicle1 changed to2; cause UNKNOWN,
existing guard retained and two regression tests added. Native03 started before
services because the helper mistook TCP TIME_WAIT for a listener; it timed out
at login. Helper now checks State Listen and service-start exit before launch.
Native02+04 passed independently. `failed-attempts02.json` retains these facts.

## Final combined-main acceptance

Canonical `gateway-p04f04`: **726 PASS,0 FAIL/ignored**, build PASS, executable
SHA256 `45f6ba2b1b7d712d0a74d954cb69065e5c8fe9ccafe35234821be58e8e218018`.
`rust/source-current04.json` binds all gateway sources to the full run.
Final combined client312/P03M42 tests and9 actual CPython2.7.3 compile checks
pass in `client/run-03-main-integration/receipt.json`. Together with the
unchanged store315/historical67/source-and-verifier34 groups, this is
**770 distinct applicable Python tests**, no skips. Full Node remains98/98;
its executed sources are unchanged. `source-binding-final-explanations.json`
documents the broad-collector files covered by other final test groups.

P03M input copying preserved23 files exactly;14 dependencies already matched.
The initial test-only JSON round-trip changed one decimal by one ULP. That
strict audit FAIL is retained. Final P03M relocation replaces only exactly-once
quoted path tokens in pinned raw bytes. All numbers/other bytes remain exact;
`client/p03m-portability-audit02/receipt.json` and
`store/p03m-helper-review-01.json` independently verify this and the real two-
worker ACK proof. Earlier725-pass build03 is superseded by726-pass build04.

The same seven native operations were repeated on final build04 using fresh
DB copies, preserving earlier runtime/evidence. Bridge9272/gateway46276/
client48556 performed run05; bridge52824/gateway50560/client46936 performed
read-only relogin06. Final independent gate:
`independent-native/final02/receipt.json` — **PASS_NATIVE_CREW_TRANSFER_WIRE_RELOGIN**.
Captures are `native-wire05/06`; traces are
`native-runtime05/native-48556-1791902836612.jsonl` and
`native-runtime06/native-46936-1791902951759.jsonl`.
Initial backup remains `native-persistence/before-transfer.sqlite`;
final backups are `integration-after-transfer.sqlite` and
`integration-after-relogin.sqlite` in the same directory. All18 non-rate-limit
tables remain equal; request226–232 and all seven exact deltas are independently
verified again. New and previous DBs remain local and unchanged by the audit.

Four final-build native PNGs were actually inspected (`native-pixels02.json`).
Both clients exited0 normally; all six installation restores report PASS.
The final restore was rechecked as ALREADY_RESTORED. Own processes/listeners
are absent and one-shot control consumed (`native-cleanup-final.json`).
Generated Python caches were archived under E rather than retained in source;
final source layout is PASS94 files/22 relocations (`layout-final.json`).
Initial layout failure remains recorded. No required final gate is skipped.

## Commands and reproducibility

Run from the owned worktree with exact receipt-recorded environment/inputs:

```powershell
python -B -X utf8 server/build.py gateway --test --out local/build/server/gateway-p04f04
npm --prefix web test
python -B -X utf8 -m unittest -v tests.test_p04f_crew_source_audit tests.test_p04f_native_crew_verify
python -B -X utf8 server/check_layout.py
```

Store/historical/client receipts include their complete unittest module lists
and fixture environment. Native prepare uses the explicit owned copy, real
Python2.7.3 compiler, `--enable-p09d-ammo-service --enable-crew-recruitment
--enable-crew-transfer`, own one-shot control and isolated preferences.
`native-installNN/install-plan.json` records all arguments and compiled sources.

```powershell
python -B -X utf8 local/p04d/run-native.py --install <E>/native-installNN --out <E>/native-runNN
python -B -X utf8 tools/interactive_client.py rollback --out <E>/native-installNN
python -B -X utf8 tools/p04f_native_crew_verify.py --wire <transfer-wire> --wire <relogin-wire> --trace <transfer-trace> --trace <relogin-trace> --private-key local/p04d/runtime/private.pem --before-database <before.sqlite> --database <after.sqlite> --relogin-database <relogin.sqlite> --original-root C:/WoT_0.9.1_RU_0717_original --install-plan <transfer-plan> --install-plan <relogin-plan> --out <fresh-E-path>
```

Keys, credentials, databases, client resources and raw captures stay ignored
locally. Only authored source/tests/documentation are eligible for Git.

## Limits, rollback and next step

VERIFIED: source pins, build/test identities, exact packet/delta/ledger checks.
OBSERVED: original callbacks, actual cache/UI, fresh-process persistence on
this Windows client. INFERRED: generic planner reuse with other verified seat
maps; synthetic two-vehicle tests support the transition only.
UNKNOWN: native cross-tank integration, historical specialization effects,
skills/retraining/paid tariffs, cause of native01 selection change, other hosts.

Native adapter remains MS-1 with existing100% commander/driver passports.
Battle admission is false. Native green readiness text is not a battle gate.
Physical mouse/manual owner acceptance is NOT_RUN; this card declares original
callback/native-wire/state/pixel acceptance. Colored hangar rendering artifacts
remain; graphics quality is not accepted here. P05 handling debt stays open.

Runtime rollback uses installation restore receipts and exact owned process
identities. Preserve both new and predecessor DBs; the new schema rejects an
old writer, so code rollback must use a matching predecessor DB/profile on our
own stand. Source rollback: `git revert -m 1 <P04F-main-merge>` from the final
receipt, coordinating later cards. No force push/reset of another checkout.

**One next crew step:** import a second verified vehicle crew profile and run
native cross-vehicle reassignment through this same generic operation.
