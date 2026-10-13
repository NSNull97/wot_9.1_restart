# P04H — native recruitment for complete MS-1 and IS-7 crews

2026-10-13. **PASS_NATIVE_ROSTER_RECRUITMENT_CURRENT_MAIN** after all declared
native/regression/restoration gates. Branch `codex/p04h-native-crew-recruitment`,
accepted main baseline `626867c758c32b189a77a7a7a2fe9ff29837e11b`.
Commit, ordinary no-ff merge, tested tree and remote SHA are recorded in
`local/evidence/20261013-p04h-native-recruitment-01/acceptance-final/`.

## Goal and changes

Recruit every primary role of the two verified vehicles through the original
0.9.1 #717 interface. Owner explicitly selected new50% crew for free; retain
old100% descriptors and defer paid options. Two loader slots must have distinct
identities. Occupant replacement must preserve the displaced member in barracks.

Owned worktree:
`C:/Users/NSNull/.codex/worktrees/crew-equipment-snapshot/WoT_9.1_Server`.
Evidence root E: `local/evidence/20261013-p04h-native-recruitment-01/`.
Only owned client `local/clients/p04d-b`, profile `local/p04d/profile`, new owned
SQLite copies and loopback23414/23415/3435 were used. Original
`C:/WoT_0.9.1_RU_0717_original` is read-only. Primary P05 work is unchanged.

Changed files, grouped by responsibility:

- `tools/p04h_tankman_descriptor.py`, `p04h_crew_projection.py`,
  `p04h_crew_store.py`: independently authored bounded25-byte descriptor codec,
  original role/passport catalogs, profile8-to9 migration and inherited sole
  transaction writer. Minimal hooks in `tools/p04f_crew_store.py` preserve old
  output/replay. New passports use server IDs4..16 and target-machine training.
- `server/gateway/src/account/{crew_service,crew_transfer,ammo_session,identity,hangar}.rs`
  and `server/gateway/src/session.rs`: explicit roster opt-in, bounded309/105
  layouts, profile9 metadata, existing shared queue/revision/replay transport.
- `web/src/{p04h-crew,p04d-crew,game-adapter}.mjs`: strict roster projection,
  two-loader capacity, policy selection and retained D/F/G command replay.
- `client_patch/{p04h_crew_ui,crew_capabilities,hangar_bootstrap,sr_interactive}.py`
  and `tools/interactive_client.py`: original RecruitWindow/crew callbacks,
  visible50%/quota label, disabled unsupported tariffs, passive native evidence.
- `tools/p04h_crew_source_audit.py`, `p04h_native_crew_verify.py`, seven new
  `tests/test_p04h_*` modules, `tests/test_crew_capabilities.py` and
  `web/tests/p04h-crew.test.mjs`: pinned sources and positive/adversarial tests.
- [Card plan](../plans/P04H_NATIVE_CREW_RECRUITMENT.md),
  [research](../research/P04H_NATIVE_CREW_RECRUITMENT.md), STATUS and
  [owner's expanded crew plan](../plans/P04_CREW_FUNCTIONALITY_091.md).

Schema `p04h-native-crew-recruitment.v1`; policy SHA256
`3e86a495c028570d96a479f409dc578875652e01f60f6ac8c42c5c1bae51737c`.
Original audit SHA256
`db7179a139d7caabd92aa1026f20e163c5a8583267bb0a1aa95541d248abf585`.
The16-member limit and once-only13 free operations are explicit test policy.
Original `freeTMenLeft` is documented as a daily allowance; its historical
initial value/reset schedule remains UNKNOWN and is not implemented by H.

## Actual native outcome

Accepted G revision30/configuration23 is copied and migrated to H31/23.
Seven original RecruitWindow submissions create IDs4..10: MS-1 commander and
driver, then IS-7 commander, gunner, driver and two loaders. Original CMD105
unloads loader10, replaces loader9 with10, then seats9 in the other loader slot.
Final MS-1 `[4,5]`, IS-7 `[6,7,8,10,9]`; old IDs1/2/3 remain in barracks.
Revision41/configuration33; free quota13→6. Both native crews are complete.
Money, ammunition and original descriptors remain exact.

Native02 PID51048 sends requests226–232 as309/method0x90 VAR2 length24 and
233–235 as105/method0x8e VAR2 length20. Each exact inventory delta precedes
success. Native03 PID18396 starts with fresh gateway/bridge and observes both
machines; all22 non-rate-limit tables match. Both clients exit0 normally.
Original descriptors parse and repack to identical25-byte values. Independent
verifier compares generated passport bytes from its own source-derived oracle.
Separate dossier-object parsing remains NOT_RUN; whole descriptor repack passes.

Six final PNGs were inspected: MS-1 commander recruitment, IS-7 gunner and
second-loader recruitment, final IS-7 and both fresh-login vehicle views.
50% base training is shown as50 for the commander and55 for other crew in the
native hangar. This observes the original commander bonus; it does not accept
the server combat effect. Original ready/incomplete-ammunition text does not
enable server battle admission, which remains false.

Native01 PID43636 also finished all ten operations, but its long label clipped
the remaining quota in actual pixels. That attempt is retained; a short label
was compiled/tested and the whole scenario repeated from the immutable H31 DB.
Accepted02/03 use the final source. Three owned installs restored, all nine
owned process IDs absent, ports free and one-shot control unarmed.

## Executed checks and evidence

| Gate | Result | Evidence under E |
|---|---|---|
| Canonical gateway |733 PASS/build PASS | `rust/receipt02.json`, `rust/source-current02.json`; worktree `local/build/server/gateway-p04h02/result.json` |
| Store/domain/source regression |464 PASS | `store/regression-01.json` |
| Historical fixture tests |67 PASS | `store/historical-01.json` |
| Client/control + P03M |363+42 PASS | `client/run-02/receipt.json` |
| Actual CPython2.7.3 |11 compile checks + Unicode/control execution PASS | same client receipt |
| Independent H verifier |22 PASS | `independent-native/unit03/receipt.json` |
| Source/verifier combined regression |112 PASS, overlapping tests counted once | `independent-native/unit01/receipt.json` |
| Full Node |102 PASS, zero skips | `web/full-web03.json` |
| Actual CLI/preservation |18 processes PASS;8 old F files byte-identical | `store/cli01/receipt.json`, `store/final-receipt.json` |
| Independent reviews |PASS after resolved metadata/provenance findings | `store/integration-review.json`, `store/verifier-review-03.json`, `source-audit/boundary-review.json` |
| Actual native wire/cache/relogin |PASS_NATIVE_ROSTER_RECRUITMENT_WIRE_RELOGIN | `independent-native/final02/receipt.json` |
| Six native PNGs |PASS scoped UI | `native-pixels01.json` |
| Owned cleanup |PASS | `native-cleanup-final.json` |
| Source layout |94 files/22 relocations PASS | `layout-final02.json` |
| Final source bindings |PASS | `source-binding-final.json` |

There are958 distinct applicable Python tests:464+67+363+42+22. The other90
combined verifier/source tests already appear in464. No required final skips.
The broad Node source enumeration included an independent verifier that changed
during the run; Node never executes it. The final verifier is separately tested
and used on native data. Store receipts likewise included an unrelated client
test subsequently changed/tested in client363. These exact scope exclusions,
without changed executed dependencies, are recorded in the binding receipt.

Run from the owned worktree; each receipt contains full commands/environment:

```powershell
python -B -X utf8 server/build.py gateway --test --out local/build/server/gateway-p04h02
python -B -X utf8 local/p04h/run-web.py --run 03 --full
python -B -X utf8 -m unittest -v tests.test_p04h_native_crew_verify
python -B -X utf8 local/p04h/prepare-native.py --run 02 --mode recruit
pwsh -NoProfile -File local/p04h/services.ps1 -Action start -Run 02
python -B -X utf8 local/p04d/run-native.py --install local/evidence/20261013-p04h-native-recruitment-01/native-install02 --out local/evidence/20261013-p04h-native-recruitment-01/native-run02
python -B -X utf8 local/p04h/freeze-native.py --run 02 --mode recruit
```

Run03 repeats preparation/start/run/freeze with `--mode relogin`. Install flags
include ammo, recruitment, transfer, cross-vehicle and roster-recruitment opt-ins.
Exact independent verifier arguments are in the research report and final receipt.
Gateway SHA256: `4d776083841b84eb110ac94a7e247dcdbf63953a49943c962b8523b814648788`.
Source/install bindings cover34 modules per accepted installation.

## Limits, rollback and continuation

VERIFIED: pinned source descriptors/roles/callback widths. OBSERVED: actual
native02/03 wire, cache, UI and durable outcomes. UNKNOWN: exact historical
paid tariff table, daily free allowance/reset and full authoritative combat
crew formulas. Physical pointer/manual owner acceptance is NOT_RUN, scheduled
by the owner for after09:00 on2026-10-14. Existing colored render artifacts and
P05 handling debt remain open. Skills, retraining, dismissal and other operations
are subsequent cards in the newly expanded request, not accepted by H.

Rollback after merge: `git revert -m 1 <P04H-main-merge>` and restore the matching
predecessor G DB on the owned stand. Keep H backups for recovery; never give an
H database to the old writer. No original assets/secrets/binaries are committed.

**Next crew card:** PersonalCase and individual training/progression, preparing
the historical skill system and the owner's always-active base Sixth Sense.
