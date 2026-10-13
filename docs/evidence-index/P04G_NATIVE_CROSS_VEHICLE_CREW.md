# P04G — native MS-1 / IS-7 crew transfers

2026-10-13. Owner request: add a second tank to the verified crew flow and
transfer crew between the two through the original interface. Branch
`codex/p04g-native-cross-vehicle-crew`, accepted main baseline
`83fecd563a9edc7dd13cdab56f3846e59673140b`.

**Acceptance: PASS_NATIVE_CROSS_VEHICLE_CREW_CURRENT_MAIN.** All declared native,
regression, source binding and restoration gates passed before integration.

## Scope, ownership and implementation

Owned worktree:
`C:/Users/NSNull/.codex/worktrees/crew-equipment-snapshot/WoT_9.1_Server`.
Evidence root E: `local/evidence/20261013-p04g-cross-vehicle-crew-01/`.
Read-only original: `C:/WoT_0.9.1_RU_0717_original`.
Only owned independent client `local/clients/p04d-b`, profile `local/p04d/profile`
and loopback ports23314/23315/3425 are used. The primary P05 checkout and other
stands are outside this card.

The generic assignment planner introduced by P04F is reused. The source-bound
adapter now supplies verified rosters for MS-1 (commander/driver) and IS-7
(commander/gunner/driver/loader/loader). Three existing identities remain;
there is no new recruitment grant. Original training descriptors remain MS-1,
100% base qualification. Gunner/loader recruitment is outside this card.

Changed files by responsibility:

- `tools/p04g_crew_store.py`, `tools/p04g_crew_projection.py`: profile7-to8
  migration, two vehicle assignments, source binding and inherited transaction
  writer. Small contract hooks in `tools/p04f_crew_store.py` and
  `tools/p04f_crew_projection.py` preserve the prior default behavior.
- `server/gateway/src/account/{crew_transfer,ammo_session,hangar,identity}.rs`
  and `server/gateway/src/session.rs`: explicit cross-vehicle opt-in, bounded
  CMD105 arguments, strict profile8 metadata and the existing shared queue.
- `web/src/{p04g-crew,p04d-crew,game-adapter}.mjs`: strict profile8 public
  projection, configuration dependencies and authoritative worker selection.
  Historical D/F receipts retain their exact response and do not mutate state.
- `client_patch/p04g_crew_ui.py`, `crew_capabilities.py`, `hangar_bootstrap.py`,
  `sr_interactive.py`, `tools/interactive_client.py`: explicit feature guard,
  original carousel/crew callbacks and passive bounded diagnostic observations.
- `tools/p04g_crew_source_audit.py`, `tools/p04g_native_crew_verify.py`,
  `tests/test_p04g_*`, `tests/test_crew_capabilities.py`,
  `web/tests/p04g-crew.test.mjs`: source pins and positive/adversarial evidence.
- [Plan](../plans/P04G_NATIVE_CROSS_VEHICLE_CREW.md),
  [research](../research/P04G_NATIVE_CROSS_VEHICLE_CREW.md), this index, STATUS,
  and the future Sixth Sense decision in `docs/08_RESEARCH_BACKLOG.md`.

Schema `p04g-native-cross-vehicle-crew.v1`; policy SHA256
`20f7d65c6d360a17f164cb6e4eaa73056a58a793727d4bfbecc1358e1f21969f`.
Original source audit SHA256
`e0693e0e36d2b5ca0c72e584684439b3b1c6eecfa9709b06820cbbc8832c7cb9`.

## Declared native scenario

The original dropdown excludes tankmen seated in another vehicle. Therefore
the native scenario unloads into barracks before choosing the other vehicle
and equipping its seat. Direct cross-vehicle server transition tests are
synthetic domain evidence only.

Fourteen commands transfer the commander MS-1 to IS-7, move driver3 through
MS-1 into IS-7, replace him with driver2, return commander1 and driver2 to
MS-1, seat driver3 in IS-7, unload the whole IS-7 crew, and finally move
commander1 back to IS-7. Expected final assignments:
MS-1 `[None,2]`, IS-7 `[1,None,None,None,None]`, driver3 in barracks.
All identities, descriptors, money, ammunition and quota must remain exact.
Revision16/configuration9 become revision30/configuration23. A fresh
bridge/gateway/client login must preserve both incomplete crews.

Original `Tankman.efficiencyRoleLevel` is read separately:100 in barracks/MS-1,
50 on IS-7 for these unchanged MS-1-trained passports. This property is not a
server training edit or acceptance of all historical combat formulas.

## Checks and commands

Run from the owned worktree. Receipts contain complete arguments, fixture
environment and tested source hashes. No original resources, secrets, raw
captures or databases are committed.

```powershell
python -B -X utf8 server/build.py gateway --test --out local/build/server/gateway-p04g01
python -B -X utf8 local/p04g/run-web02.py
python -B -X utf8 -m unittest -v tests.test_p04g_crew_source_audit tests.test_p04g_native_crew_verify
python -B -X utf8 server/check_layout.py --out <fresh-E-receipt>
```

The first full Node run passed99/99, then independent review reproduced a
historical replay bug at the HTTP boundary: profile8's minimum revision
blocked a preserved F7/D6 receipt. The G-only fix permits those old cursors
only for successful immutable replay; missing/altered receipts cannot change
state. The official real bridge test now covers both predecessor paths.
Reproducers are retained under `E/client/review-replay*`.

Store regression:394 PASS; historical fixture regression:67 PASS. Client/control:
336 PASS plus42 P03M PASS; ten real CPython2.7.3 compile checks PASS. Full canonical
Rust:729 PASS and build PASS. Store CLI evidence uses22 real separate processes,
including all14 layouts; accepted F fixture files remain byte-identical after
the contract refactor. Final full Node:100/100 PASS, no skips; independent G
verifier adds24 distinct tests, giving863 distinct applicable Python tests.
The combined source/verifier group is73 tests; its49 overlapping tests are
already counted in store394. All final runtime hashes match their test runs.

| Final gate | Result | Evidence under E |
|---|---|---|
| Full Rust/build |729 PASS/build PASS | `rust/source-current01.json`, `local/build/server/gateway-p04g01/result.json` in worktree |
| Store and migration |394 PASS | `store/regression-01.json`, `store/final-receipt.json` |
| Historical fixtures |67 PASS | `store/historical-01.json` |
| Client/control and P03M |336+42 PASS | `client/run-01/receipt.json` |
| CPython2.7.3 compile |10 PASS | same client receipt; native plans bind33 installed modules each |
| Source/verifier group |73 PASS,24 G verifier tests distinct | `independent-native/unit03/receipt.json` |
| Full Node |100 PASS | `web/full-web02.json` |
| Independent gateway/web review |PASS after resolved replay finding | `client/gateway-web-review.json` |
| Independent verifier review |PASS after resolved binding findings | `store/verifier-review-02.json` |
| Actual migration |PASS | `store/native-migration-comparison.json` |
| Native wire/state/relogin |PASS | `independent-native/final01/receipt.json` |
| Four inspected native PNGs |PASS scoped crew UI | `native-pixels01.json` |
| Restoration/process cleanup |PASS | `native-cleanup-final.json` |
| Source layout |94 files/22 relocations PASS | `layout-final.json` |

## Actual native outcome

Run01: client50404, original requests226 through239,14 CMD105 frames,
method0x8e/VAR2 length20. Every assignment-only delta (101–107 bytes) precedes
its successful callback; full lists for both vehicles and all three tankman
assignments match durable state. Final crews are exactly MS-1 `[None,2]`,
IS-7 `[1,None,None,None,None]`, driver3 in barracks. Revision16→30 and
configuration9→23. IDs, descriptors, ammunition, balances and quota are exact.

Run02: new client35096 and fresh bridge/gateway, original views of both tanks.
All20 non-rate-limit tables remain equal after relogin; `game_limits` is
explicitly excluded. Both clients exit0 normally. All33 installed source and
compiled modules per plan are bound to current source. Gateway executable
SHA256 `e95f3949ffa5fe121532c0ca09008bcb880bb46ac515e9f66752636915d225ac`.

Independent gate: `PASS_NATIVE_CROSS_VEHICLE_CREW_WIRE_RELOGIN`.
Traces: `native-runtime01/native-50404-1791905211885.jsonl` and
`native-runtime02/native-35096-1791905406323.jsonl`; captures `native-wire01/02`.
Frozen DBs: `native-persistence/{before-transfer,after-transfer,after-relogin}.sqlite`.
The exact verifier command is in the linked research report's native section.
Four actual screenshots were inspected with `view_image`;17 were generated.
Displayed100/50 efficiency is observed independently of unchanged base100
qualification. Full relogin sync is not claimed as a bytewise packet comparison;
fresh native cache views, authenticated capture and unchanged DBs establish it.

All own client installs restored, six own process IDs absent, loopback listeners
absent and one-shot control consumed. Initial cleanup helper invoked Windows
PowerShell5 whose execution policy refused the script; no processes were stopped
by that failed invocation. Repeating through the already-used PowerShell7 host
completed exact-identity cleanup, without changing execution policy. Logs remain.
Generated Python caches initially failed layout; owned caches were archived
under E and final layout passes. Unit fixture/review failures are retained;
no required final FAIL/NOT_RUN remains. See `failed-attempts.json`.

Native preparation flags:
`--enable-p09d-ammo-service --enable-crew-recruitment --enable-crew-transfer
--enable-cross-vehicle-crew`. Each `native-installNN/install-plan.json` binds
the own copy, compiler, trace, flags, source and compiled bytes.

```powershell
python -B -X utf8 local/p04g/prepare-native.py --run 01 --mode transfer --activate
./local/p04g/services.ps1 -Action start -Run 01
python -B -X utf8 local/p04d/run-native.py --install <E>/native-install01 --out <E>/native-run01
python -B -X utf8 local/p04g/freeze-native.py --run 01 --mode transfer
python -B -X utf8 local/p04g/prepare-native.py --run 02 --mode relogin
./local/p04g/services.ps1 -Action start -Run 02
python -B -X utf8 local/p04d/run-native.py --install <E>/native-install02 --out <E>/native-run02
python -B -X utf8 local/p04g/freeze-native.py --run 02 --mode relogin
```

The independent verifier takes two `--wire`, two `--trace`, two `--install-plan`,
`--private-key`, `--before-database`, `--database`, `--relogin-database`,
`--original-root` and fresh `--out`. Its exact invocation is saved with its
receipt. Native callbacks and pixels are required; synthetic tests do not close
this gate. Physical mouse/manual owner input is separately NOT_RUN.

## Limits and rollback

VERIFIED: original source anchors, descriptor identity, transaction and replay
checks. OBSERVED: actual14 native operations, displayed crew slots/qualification,
fresh login and persistence on this Windows #717 client. INFERRED: the shared planner
can serve additional source-verified rosters. UNKNOWN: other vehicle adapters,
combat penalties, retraining, skills, paid tariffs, other hosts and full UI
rendering quality. Battle admission remains false; P05 handling debt is open.

Owner decision for the later perk card: Sixth Sense is always active without
learning, including50% crew. This is an explicit project rule overriding the
historical learning requirement; timing and reset behavior are unspecified.
No perk implementation is included in P04G.

Rollback own client installs by their ledgers; stop only receipt-bound own
processes. Keep predecessor and current DBs. New schema rejects old writers,
so pair a code rollback with the matching predecessor DB/profile. After merge:
`git revert -m 1 <P04G-main-merge>`; never reset another checkout or force-push.
Final source/commit/merge/remote bindings belong in `E/acceptance-final/`.

**One next crew step:** native recruitment for every required primary role of
these two verified rosters, so IS-7 can receive a complete crew. Perks remain a
later card with the recorded base Sixth Sense rule.
