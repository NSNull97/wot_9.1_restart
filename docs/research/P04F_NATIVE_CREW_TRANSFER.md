# P04F — native crew unloading and reassignment

2026-10-13. Branch `codex/p04f-native-crew-transfer`, based on accepted P04E
main `06582030050c7b6720f4616dffa50b2be61e4abc`. The owner requested crew
unloading and reassignment through the original interface. The execution plan
is [P04F_NATIVE_CREW_TRANSFER.md](../plans/P04F_NATIVE_CREW_TRANSFER.md).

**Initial native gate: PASS_NATIVE_CREW_TRANSFER_WIRE_RELOGIN**, run02 plus
fresh relogin04, with separate scoped native pixel acceptance. This result is
bound to `E/independent-native/final01/receipt.json`; it does not depend on the
successful operation trace alone. All four initial installations have
`restore.json` status `PASS`. Physical mouse input remains NOT_RUN.

Accepted P03M main `0393857` was subsequently integrated at
`a233166fdbf24cc6dc9b9370511c9e3dde41addc`. **Final main-integration acceptance
is PENDING:** full current-source Rust checks and the repeat native05/06 pair
must close before merge/push. The completed initial native gate remains valid
for its recorded sources; it is not silently relabelled as the post-integration
run.

Evidence prefix `E` below means the worktree-local ignored directory
`local/evidence/20261013-p04f-native-crew-transfer-01/`. Raw client resources,
compiled modules, credentials, keys, captures and databases remain local.

## Source facts and the boundary of the native profile

**VERIFIED_STATIC:** the original RU 0.9.1 #717 source manifest is
`74c37c18e9ac7e30196c134076dacf6f2a8bf3897f7def73905d09feb3647797`.
`tools/p04f_crew_source_audit.py` pins 25 resources and checks 31 new bytecode
records, with the retained P04D baseline checks. It uses bounded static
readers; it does not execute imported client code. The canonical source audit
SHA256 is
`b4a7dd9dd4bdb5f106460a9f5b681b0b1944fd83bf05662e2bba4e9f1f0164d3`.
The immutable source receipt is `E/source-audit/pinned-audit02/receipt.json`.
Its original NOT_RUN entries describe the static audit's own scope and are
not retroactively rewritten after a native run.

**VERIFIED_STATIC:** `Inventory.equipTankman` uses CMD105,
`CMD_EQUIP_TMAN`, through `doCmdInt3`. After request ID and command, arguments
are vehicle inventory ID, seat, tankman inventory ID. The declared types are
`INT16, INT16, INT64, INT32, INT32`, the payload is 20 bytes, and its struct is
`<hhqii>`. Unloading one seat sends tankman `-1`; unloading the entire crew
sends seat `-1` and tankman `-1`. CMD157 restores a previous crew and CMD306
dismisses a tankman; neither operation is implemented by treating it as CMD105.
The static method-table candidate was wire `0x8e`, VAR2 length20.
**OBSERVED_NATIVE_717:** independent decoding of run02 now confirms that exact
method and framing for all seven requests. The static source receipt retains
its original **INFERRED** classification; the native receipt supplies the
additional evidence.

**VERIFIED_STATIC:** original entry points include `Crew.equipTankman`,
`Crew.unloadTankman`, `Crew.unloadAllTankman`, `Crew.unloadCrew` and
`Barracks.unloadTankman`. The source admits replacement of an occupied seat.
Unload validates available barracks capacity and counts only present members
for a whole-crew unload. The equip processor does not provide the same
barracks validator; these client checks cannot replace authoritative ownership,
role, reservation and capacity validation on the server.

**VERIFIED_STATIC:** vehicle inventory category1 contains `crew`, a complete
seat list. Its empty seat is `None`; category8 `vehicle` uses `-1` for a
tankman in barracks. Assignment does not require a changed `compDescr` or
embedded dossier. Dictionary synchronization recursively merges maps but
replaces lists as complete values. Therefore `crew: {vehicle_id: [1, None]}`
preserves an empty seat, while `crew: {vehicle_id: None}` would delete a map
entry. Category8 changes trigger original crew/barracks refresh paths.

The owner clarified that assignment and unloading are common operations for
all tanks. The shared planner reflects that requirement: it consumes owned
assignment records and a validated destination seat-to-role map, with no MS-1
ID, role names or protocol command embedded in its algorithm. This does not
make all native vehicle profiles available. The current native adapter has
verified mutable data only for MS-1 inventory1, commander seat0 and driver
seat1. The source MS-1 compact type is3329, nation0/type13; its commander also
performs gunner/radioman/loader duties. Those secondary roles do not authorize
arbitrary substitutions into the persisted primary-role policy.

**PROJECT_POLICY:** `p04f-native-crew-transfer.v1`, profile7, policy SHA256
`35a58c8e13d9b815f8552371bbd6556ba10c091753861e697e522d6a5c877cb2`.
The adapter supports only existing server-owned identities1..3, compatible
MS-1 seats, 16 crew/barracks bounds, unchanged 100% no-skill passports and
retained one-free-driver recruitment policy. Battle admission is disabled.
These are explicit test-policy limits, not a claim about historical starting
economy or historical cross-specialization penalties.

## Generic transition and one authoritative writer

`server/domain/crew_transfer.py` defines immutable `Assignment` records and
`transfer_assignments`. The caller supplies validated ownership and vehicle
specialization policy. The planner checks unique identities and assignments,
compatible destination roles, bounded inputs and resulting barracks capacity.
It handles empty seats, occupied replacement, single/whole unload and a move
from another vehicle without duplicating a tankman. Synthetic tests use
vehicles101/222, additional seats and role names independent of MS-1. They
establish algorithm reuse; they do not establish native support for those
synthetic vehicles or historical retraining effects.

`NativeCrewTransferStore` extends the existing `NativeCrewStore` and sole
ammunition writer. Transfer, recruitment and ammunition continue through one
SQLite database and the shared command ledger. There is no independently
writable crew JSON or second inventory database. `CrewTransferProjectionSource`
derives public/native output from the current consistent crew/ammo state.

The explicit profile6-to7 migration retains IDs, descriptor bytes, assignments,
quota, balances, ammunition and prior command rows. It advances the aggregate
revision once, retains configuration revision, adds `p04f_schema` and
`p04f_crew_meta`, and changes the old crew schema marker so old writers fail
closed. Migration metadata binds the accepted prior profile digest, revision,
source bundle and actual F source audit. Activation does not silently create
a crew profile from an unrelated profile4 database.

**VERIFIED_LOCAL_SQLITE:** read-only comparison of accepted P04E
`native-persistence/after-relogin.sqlite` with F
`E/native-persistence/before-transfer.sqlite` found 13 identical old tables,
exactly four expected changed old tables and the two new F tables. The shared
revision moved7→8; configuration revision stayed2 and free quota stayed0.
All three identities/descriptors/assignments and the earlier command ledger
row were retained. Existing table schemas were unchanged. Both backups passed
integrity checks and retained their file hashes during immutable read-only
inspection. Detailed deltas: `E/store/migration-comparison-final.json`.

Transfer requests use the existing exact six-field request envelope:
`account_id`, `native_database_id`, `command_key`, `expected_revision`,
`wire_revision`, `layout`. Layout is `[vehicle_id, seat, tankman_id]`.
Authenticated ownership, native identity, shared revision, vehicle reservation,
role compatibility and capacity are checked within the writer transaction.
Whole unload `[1,-1,-1]` is one mutation, not two independently committed seat
operations. An occupied replacement moves the displaced owner to barracks;
it never deletes or creates an identity.

A successful mutation returns `status=transferred`, `result_code=0`, and
increments aggregate, wire and configuration revisions exactly once. Requests
with no assignment change reject as `NO_ASSIGNMENT_CHANGE`, with no revision
or ledger mutation; the CLI maps the rejection to native result-10. This is
an explicit project response policy. Seven rollback injection points cover
assignment, metadata, snapshot/profile projection, ledger and commit boundaries.
Durable before/after state and response hashes validate replay after reopening
or later operations. Existing recruitment still works with a vacant driver;
it consumes only the retained quota and shares the same transaction/ledger.
Old accepted D recruitment replay remains validated at the store interface;
this is not a claim that a pre-F HTTP revision is accepted by the profile7 gate.

The native assignment delta publishes category1 `crew` with the entire seat
list and category8 `vehicle` for all owned members. Descriptors/dossiers and
quota are omitted from transfer deltas because they did not change. The
profile7 fixture carries exactly 12 primitive fields in `crew-transfer.json`,
including source policy/state digests, shared/configuration revisions and
`battle=false`. It retains current ammunition metadata. Gateway/bridge
opt-in validates profile7 and the F metadata, and shares the existing native
queue, account revision and request identity space with ammunition/recruitment.
Update publication must precede the matching successful callback.

## Run02: seven original native operations observed

**OBSERVED_NATIVE_717:** client process7696 ran the actual original 32-bit
Python2.7.3 runtime. Evidence is
`E/native-runtime02/native-7696-1791901697651.jsonl` (995 records), SHA256
`648882678545d8edc555d7bff0ab3c59d62e9fb6eb583932c0b2d04632954b7f`.
`E/native-run02/outcome.json` records normal native exit0, no timeout and no
physical pointer input. Its launcher-level `native_acceptance=NOT_RUN` is
correctly separate from the subsequent independent evidence audit.

The opt-in diagnostic invoked original Crew callbacks. Passive observation
recorded original `Account.__doCmd` requests and original `_update` and
`onCmdResponseExt` returns. Inventory snapshots were read from the original
synchronized cache; expected transition values were not written into it.
Initial snapshot line287 has crew `[1,3]`, driver2 in barracks, free quota0,
100000credits and0gold. All seven steps use vehicle inventory1:

| Step | Original callback | Request | CMD105 layout | Native crew after | Wire revision | Update / success / readback lines |
| --- | --- | --- | --- | --- | --- | --- |
| Unload driver3 | `Crew.unloadTankman(3)` | 226 | `[1,1,-1]` | `[1,None]` | 1→2 | 371 / 376 / 382 |
| Seat original driver2 | `Crew.equipTankman(2,1)` | 227 | `[1,1,2]` | `[1,2]` | 2→3 | 464 / 469 / 477 |
| Replace with driver3 | `Crew.equipTankman(3,1)` | 228 | `[1,1,3]` | `[1,3]` | 3→4 | 559 / 564 / 570 |
| Unload commander1 | `Crew.unloadTankman(1)` | 229 | `[1,0,-1]` | `[None,3]` | 4→5 | 654 / 659 / 665 |
| Seat commander1 | `Crew.equipTankman(1,0)` | 230 | `[1,0,1]` | `[1,3]` | 5→6 | 749 / 754 / 760 |
| Unload whole crew | `Crew.unloadAllTankman()` | 231 | `[1,-1,-1]` | `[None,None]` | 6→7 | 845 / 850 / 856 |
| Reseat commander1 | `Crew.equipTankman(1,0)` | 232 | `[1,0,1]` | `[1,None]` | 7→8 | 940 / 945 / 951 |

Every matching original callback returned result0 after its inventory update;
the request/update/success owner was the same native Account instance. Final
line963 reports seven completed operations. IDs2 and3 both remain in barracks,
with vehicle/slot-1 in the native readback; ID1 remains commander in slot0.
Descriptor hashes, 100% base role levels, no-skill/free-XP state, quota and
balances remain unchanged throughout the recorded snapshots. Native ammunition
caches are also equal at every step: MS-1 loaded20/0/0, IS-7 loaded0/0/0, and
each of the six recorded depot shell types remains100. The combined independent
raw-wire and durable-DB audit now confirms the corresponding preserved state.

## Initial independent native and fresh-login gate

`E/independent-native/final01/receipt.json` has status
`PASS_NATIVE_CREW_TRANSFER_WIRE_RELOGIN`, SHA256
`b69d43b6ab3d4464926d6aade11456298b8f0cd3f02a50335ee0cba7fc489d21`.
It independently decodes 171 packets in `native-wire02` and 54 in
`native-wire04`. Each of the seven actual CMD105 requests matches its durable
request/policy digest and exact assignment-only update before success. Delta
sizes in scenario order are95,93,93,95,93,97,95 bytes. The shared aggregate
revision advances8→15 and configuration revision2→9; the native wire revision
advances1→8 within the operation session.

After the owned service restart, fresh native client35208 completed relogin04
and exited0 normally. Its original cache read at line260 of
`E/native-runtime04/native-35208-1791902154809.jsonl` matches final crew
`[1,None]`, with both drivers in barracks and the same IDs/descriptors/quota,
balances and ammunition. Consistent after-transfer and after-relogin backups
have all **18 non-rate-limit tables identical**. `game_limits` is separately
excluded because authentication rate-limit bookkeeping changes on login.
The verifier binds both native traces to their actual installed Python2.7
compiled observers and installation plans. It does not claim that the second
capture's entire full-sync state was independently reconstructed byte for byte.

**OBSERVED_NATIVE_PIXELS:** the root coordinator actually inspected four
engine PNGs, recorded in `E/native-pixels01.json`, status
`PASS_SCOPED_NATIVE_PIXELS`. The views show an empty driver seat and red
incomplete-crew status after driver unload; both portraits and green native
ready status after replacement; an empty crew panel after whole unload; and
the commander with an empty driver seat after fresh login. The green label
is a native UI observation, not runtime battle admission. Colored rendering
artifacts remain outside this scoped acceptance. Physical pointer input and
owner manual acceptance remain NOT_RUN. The verifier's own `pixels=NOT_RUN`
field correctly describes that tool's scope; the separate visual receipt is
the evidence for inspection.

`E/native-install01/restore.json` through `native-install04/restore.json`
all record status `PASS` for restoring their owned installation files while
preserving local preferences. Restoration is established by these receipts;
`patch-ledger.json` has no restoration-status field and is not described as
having a `RESTORED` status. The initial successful clients exited normally;
receipt-owned service stop evidence is preserved under `E/native-persistence/`.

## Failed attempts and unresolved causality

**OBSERVED:** attempt01 process4160 selected MS-1 and recorded a correct
initial inventory1 snapshot at line251. Lines261–264 record a carousel tooltip
for inventory2, and line303 records the selected IS-7/inventory2. Line304 then
fails with `native vehicle changed during transfer scenario`. There are zero
`p04f_native_transfer_request` records in that attempt. The evidence remains
in `E/native-runtime01/native-4160-1791901312515.jsonl` and `E/native-run01/`.

**UNKNOWN:** the cause of the inventory1→2 selection change in attempt01.
The nearby tooltip is an observation, not proof of causality or physical input.
The successful second attempt does not establish a historical client bug or
prove that a particular timing hypothesis caused the first failure. No crew
ownership, operation-success or selected-vehicle guard was waived to accept it.

Relogin03 process46408 did not complete: the run outcome records diagnostic
timeout, exit1, and retained logs under `E/native-run03/`. The coordinator
identified infrastructure launch ordering as the failed attempt's operational
context. It provides no fresh-login acceptance. Successful relogin04 and the
combined independent receipt close that initial persistence gate; the failed
attempt remains preserved.

## Checks, evidence interpretation and remaining gate

**VERIFIED_LOCAL_TESTS:** store/projection/core45/45; combined applicable
Python315/315 (including those45); separate historical compatibility67/67;
all without skips. Eighteen real separate CLI processes cover migration,
recruitment, the seven transfers, ammunition after transfers, replay, reopen,
explicit rejection and fixture publication. These CLI cases are not substitutes
for native execution. Their manifests, exact commands, environment and source
hashes are `E/store/tests-02.json`, `regression-01.json`, `historical-01.json`,
`cli02/receipt.json` and `final-receipt.json`. The failed cli01 harness encoding
alias is preserved separately; it failed before database creation.

The historical command, with its previous P04E migrated fixture/export
environment preserved in the receipt, was:

```text
python -B -X utf8 -m unittest -v tests.test_native_evidence_relocation tests.test_ms1_crew_state tests.test_ms1_ammo_state tests.test_test_garage_state
```

`tools/p04f_native_crew_verify.py` is independent of the transfer store/planner.
It reads bounded checkpointed SQLite backups immutably, validates exact
seven-step ledger/request/delta chains, decodes authenticated captured packets,
and correlates original Account calls with actual native cache snapshots.
Fresh-process relogin requires matching final crew and equal non-rate-limit
tables. Native transfer capture bytes are compared with durable deltas; the
additional login capture establishes authenticated server data, not an asserted
independent full-sync byte reconstruction. Service restart/process correlation
and pixels remain separate gates.

Independent review found and closed two verifier gaps: public crew-service
configuration revision is now checked exactly against authoritative state;
source/compiled hashes are now bound to immutable bundle entries and the
installation ledger's plan digest. Four pinned observers include
`p09d_ammo_ui.py`. Source-audit/verifier34 tests passed, including adverse
mutations of revision/policy, bundle bytes and ledger hash. Review evidence:
`E/store/native-verifier-review-01.json` and
`E/store/native-verifier-review-final.json`; test log:
`E/source-audit/combined-tests03.log`. No unresolved blocker was found within
that reviewed implementation scope. A passing code review is not native
acceptance, nor a claim of exhaustive safety proof.

After main integration at `a233166`, the accepted P03M private fixture still
contains its original primary-checkout paths. The existing test-only worker
relocation helper now preserves the exact P03M pool/config/v2-profile pins and
maps their locations into this worktree. Only paths and derived config/pool
digests change; profile bytes and the production `Pool::load` checks remain
unchanged. The real IS-7 test records source and derived hashes separately,
rather than presenting relocated bytes as the historical original. This
portability check does not imply native acceptance of IS-7 crew assignment.

An initial relocation serialized parsed JSON and changed
`body_center_offset[1]` from `1.0385702341794967` to
`1.038570234179497` in both map configurations. That output is not accepted
as a path-only transformation. The corrected P03M-only helper substitutes
exactly one complete JSON-encoded token per terrain/obstacles path in the
bounded original UTF-8 bytes, retaining every other byte. Tests preserve
decimal/scientific notation, negative zero and whitespace, and reject missing,
duplicate, differently escaped or oversized substitutions. No production
loader or physics dependency was changed. The earlier Rust run on the
reserializing helper is superseded by the final current-helper run.
`E/client/p03m-portability-audit02/receipt.json` verifies both fresh derived
configurations byte-for-byte after inverse path substitution, exact parsed
numbers, unchanged profile bytes and a matching real both-worker-ACK result.
The earlier precision failure remains in
`E/client/p03m-portability-audit01/failure.json`.

Current-source client312/P03M42 Python checks and nine actual Python2.7
compilation results pass in `E/client/run-03-main-integration/receipt.json`.
Final canonical gateway-p04f04 passes726 tests and build; source hashes are
`E/rust/source-current04.json`. Final executable SHA256 is
`45f6ba2b1b7d712d0a74d954cb69065e5c8fe9ccafe35234821be58e8e218018`.
The second native05/06 pair is **PASS_NATIVE_CREW_TRANSFER_WIRE_RELOGIN** in
`E/independent-native/final02/receipt.json`. Clients48556 and46936 both exited0;
fresh bridge/gateway processes loaded the same DB. All seven requests/deltas
and18 unchanged non-rate-limit tables are verified again. Root inspected four
final PNGs (`E/native-pixels02.json`). Both final installs were restored,
own services stopped and control consumed (`E/native-cleanup-final.json`).
Previous failed/passing receipts remain under their actual source hashes.

**UNKNOWN / NOT_RUN:** the cause of attempt01's selection change and physical
owner input. Skills, retraining, dismissal, paid recruitment, CMD157, other
native vehicle profiles, historical cross-specialization effects and runtime
battle admission remain unsupported. General rendering quality is not accepted.

All writes are confined to the managed crew worktree and its independent
`local/clients/p04d-b` copy. `C:/WoT_0.9.1_RU_0717_original` is read-only;
primary P03M and sibling stands are outside this card. Rollback uses only owned
installation ledgers and receipt-identified processes, preserving the unchanged
accepted predecessor DB and the new evidence. A later integrated card can be
reverted with `git revert -m 1 <merge>`; no history reset or other checkout
restoration is implied.

**Acceptance: PASS_NATIVE_CREW_TRANSFER_CURRENT_MAIN.** Final commit/ordinary
merge/push/remote SHA are bound in E/acceptance-final. The single next crew
step is importing a second verified vehicle crew profile and testing actual
native cross-vehicle reassignment through the same generic operation.
