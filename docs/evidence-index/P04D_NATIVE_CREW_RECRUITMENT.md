# P04D — actual native recruitment and persistent assignment

2026-10-13. Goal: recruit one tankman through the original RU0.9.1#717
RecruitWindow/CMD309, assign him to MS-1 and retain the same server-owned
identity after a real client/server restart.

**PASS_NATIVE_CREW_WIRE_RELOGIN** for this explicit native callback scenario.
Main integration is **HOLD**, pending the full regression findings below.
Physical mouse interaction/owner manual acceptance is **NOT_RUN** and is not
implied by the automated original-callback diagnostic.

## Scope, checkout and inputs

- Worktree: `C:\Users\NSNull\.codex\worktrees\crew-equipment-snapshot\WoT_9.1_Server`.
- Branch: `codex/p04d-native-crew-recruitment`.
- Accepted main base: `90c7a1d92a67be2acf2d02ab9a5720a377c9f2c8`.
- Stacked P04B `20b5d52`, P09C `85c4710`, P04C `48ff5fa`.
- Frozen P09D upstream `db72382652ec18a475b3cf85a024dc78a7e13fe7`, local
  cherry-pick `b13ca5cf1b33ff27b2a4e11cb29adeb8e785e862`.
- Original read-only client: `C:\WoT_0.9.1_RU_0717_original`, manifest
  `74c37c18e9ac7e30196c134076dacf6f2a8bf3897f7def73905d09feb3647797`.
- Owned independent native copy: `local/clients/p04d-b`. The only executable
  adaptation is the documented slot-B mutex replacement; EXE SHA256
  `510174793cbd1fbf43e2abfc73b6a9b5ab4273f44d2f9c9be01208922bf60fe1`.
- Verified portable source bundle: `local/p04d/source-bundle-05`, manifest SHA
  `d99f2ba765e39d096cf2d0858c9864ed897a36eb9c4ea6972a15385e2355b2db`.
- New local credentials, keys, identity/game databases and fixture publication
  remain ignored. No credentials, raw client resources or captures are committed.
  Primary/P09D worktrees, their processes and databases were not modified.

In the rest of this index `E` means
`local/evidence/20261013-p04d-native-crew-recruitment-01`, and `N` means
`local/evidence/p04d-native01`, relative to the worktree above.

## Changed files and behavior

| Area | Files | Result |
|---|---|---|
| Authoritative state | `tools/p04d_crew_store.py`, `tools/p04d_crew_projection.py` | Versioned source-gated migration, one shared ammo/crew SQLite writer, atomic recruitment/quota/assignment/profile/ledger, replay and rollback |
| Source facts | `tools/p04d_crew_source_audit.py` |18 pinned original sources; inert bytecode/definition inspection |
| Native gateway | `server/gateway/src/account/{crew_service,ammo_session,hangar,identity}.rs`, `server/gateway/src/{main,session}.rs` | Explicit opt-in CMD309, bounded decoding, full packet validation before shared worker, update before success |
| Identity bridge | `web/src/{p04d-crew,game-adapter}.mjs` | Authenticated loopback route and strict profile6 overview through the same store |
| Original UI compatibility | `client_patch/{p04d_crew_ui,crew_capabilities,hangar_bootstrap,sr_interactive}.py`, `tools/interactive_client.py` | Truthful free-test label, unavailable paid choices, original recruitment callbacks and bounded optional diagnostic |
| Independent evidence | `tools/p04d_native_crew_verify.py` | Bounded raw-wire decryption/literal parsing, DB/ledger and separate-process native readback comparison |
| Tests | `tests/test_p04d_*.py`, `tests/test_crew_capabilities.py`, `web/tests/p04d-crew.test.mjs`, inline Rust tests | Ownership, malformed input, replay/quota/reservation, transaction failures, shared ammo preservation, controls and evidence rejection |
| Documentation | Plan, research report, this index, `docs/STATUS.md` | Scope, facts, actual results, limitations and rollback |

No dependency or lockfile changes are part of this card. Restoring
`tools/hangar_state.py` to the exact LF bytes in HEAD repairs a frozen hash
check and has no logical Git diff.

## Actual native proof

Run03 client PID8780 used the original decorated recruit callback. The wire
request is27 bytes: `90 18 00` +24-byte `<hhqiii>` payload
`(226,309,3,1,1,0)`. Independently verified sequence:

1. `N/wire01/packet-000156-base_client_to_server.bin`, session3/sequence6:
   actual CMD309 request226.
2. Packet158, server sequence17: Account.update0x57, exact158-byte delta.
3. Packet159, server sequence18: success0x4d/result0/empty dictionary.
4. `N/runtime03/native-8780-1791895702349.jsonl`: before line244, submit263,
   original update return330, matching callback return336, inventory readback350.
5. DB aggregate6→7, exactly one recruitment ledger entry, crew `[1,2]→[1,3]`,
   ID2 retained in barracks, quota1→0,100000credits/0gold unchanged.

The bridge45852 and gateway38028 were stopped after validating their owned
process receipts and executable/command lines. New bridge52088/gateway49940
were started over the same DB. Run04 client33176 reused the local preferences:

- `N/runtime04/native-33176-1791896127221.jsonl`, line254: exact read-only
  comparison of all tankmen identities, descriptor hashes, seats and balances.
- `N/wire02`: fresh connection with no recruitment command.
- `N/persistence/after-recruit.sqlite` SHA
  `df1c3f3e3e35b390e4517a6fbbfeb941b5acda7e02677572ccc1280a667ecee6`.
- `N/persistence/after-relogin.sqlite` SHA
  `a77988fc3f8f2e69d0948a87d48c83db95c83333162cd71d8817f9c5c020c403`.
- Both are consistent SQLite backups, independent of live WAL files.
  `E/persistence-research/native-wire-final-01/semantic-restart.json` confirms
  equality of all11 game/crew/ammo/profile/ledger tables across restart.

Final independent verdict:
`E/persistence-research/native-wire-final-01/receipt.json`.
Its `review-receipt.json` binds verifier/readers,12 adversarial tests and the
two service stop/start/cleanup chains. The raw verifier does not claim pixels.

Root inspected actual native PNGs, with separate receipts:
`N/persistence/visual-recruit.json`, `N/persistence/visual-relogin.json`.
Images: `N/runtime03/screenshots/p04d_recruit_window_001.png`,
`p04d_recruit_after_002.png`, and
`N/runtime04/screenshots/p04d_recruit_relogin_001.png`.

Both successful installations `N/install04` and `N/install05` have PASS
install and RESTORED ledgers. Both original clients exited0 naturally without
timeouts. The fresh owned gateway/bridge were also stopped after acceptance.

## Tests, reviews and retained failures

| Gate | Actual result | Evidence |
|---|---|---|
| Native recruitment + fresh server/client relogin | PASS | `E/persistence-research/native-wire-final-01/` |
| Store/projection, source audit, P09D persistence, P04C reservation, layout tests |115 PASS /1 symlink NOT_RUN,116 discovered | `E/final-checks02/python-receipt.json`, `python.log` |
| UI, all control tests, crew capability guard |158 PASS (24+119+15) | `E/tariff-source/ui-native-success-final-receipt.json` |
| Independent evidence verifier |12 PASS,0 skips | `E/persistence-research/native-wire-final-01/review-receipt.json` |
| Node identity/garage/status/P09D/P04D regression |22 PASS,0 skips | `E/bridge-portable04/receipt.json` |
| Targeted Rust account/crew/ammo/scheduler/identity |65 PASS | `E/native-source/gateway-receipt01.json` |
| Full Rust after restoring exact ignored inputs |654 PASS /9 FAIL /0 skipped;663 total | Final full-suite receipt, indexed by `E/acceptance-final/receipt.json` |
| Native gateway build | PASS; EXE SHA `8dae46a3c44288c688617221e6338833a8321132e839aa4ef200b51b926d3fce` | Same gateway receipt |
| Python2.7.3 native module compilation | PASS | UI final receipt and install metadata |
| Source layout | PASS,82 files/22 relocations | `E/final-checks02/layout.json` |
| Independent bridge/gateway review | No blocking findings | `E/persistence-research/bridge-review.json`, `E/tariff-source/gateway-independent-review.json` |

Full Rust regression initially produced495 PASS/168 FAIL. Restoring139 exact
ignored files (69,707,503 bytes) through verified read-only copying leaves
654 PASS/9 FAIL/0 skipped. The9 remaining failures comprise5 legacy pool
worker/orientation tests,2 P06N tests and2 P06O tests. Their historical
pool files embed absolute `D:\WoT_9.1_Server\local` paths, incompatible with
the new worktree's required local root; changing those paths also changes
their frozen whole-file hashes. Those checks must not be waived. The final
full-suite recheck and exact remaining failures are bound by the final receipt.
**Main merge/push is held until the required failures are resolved.**

Earlier failures remain preserved: Node missing dependencies/data and CRLF
frozen-encoder mismatch; P04C34 missing mounted-descriptor errors fixed by
copying the exact two already-pinned inputs into the owned local/server;
two native UI attempts failing before CMD309; an independent verifier bug
that applied the target callback length to an unrelated bundled login reply.
The corresponding fixes were followed by successful reruns. Source/hash
assertions and native acceptance were not weakened.

## Commands actually used

All commands run from the worktree above, with its local config and owned
source bundle. Python3.14.3, Node24.21.0, Windows10 build19045; native runtime
and module compiler are32-bit CPython2.7.3.

```powershell
$env:WOT091_CONFIG = "$PWD/config/project.local.json"
$env:P04D_TEST_BUNDLE = "$PWD/local/p04d/source-bundle-05"
$env:P09D_TEST_BUNDLE = $env:P04D_TEST_BUNDLE
$env:P04D_TEST_ORIGINAL = 'C:/WoT_0.9.1_RU_0717_original'
$env:P09D_TEST_ORIGINAL = $env:P04D_TEST_ORIGINAL
python -B -X utf8 -m unittest tests.test_p04d_crew_projection tests.test_p04d_crew_store tests.test_p04d_crew_source_audit tests.test_p09d_ammo_projection tests.test_p09d_ammo_store tests.test_crew_configuration_store tests.test_server_layout -v
python -B -X utf8 -m unittest discover -s tests -p test_p04d_crew_ui.py -v
python -B -X utf8 -m unittest discover -s tests -p '*control.py' -v
python -B -X utf8 -m unittest discover -s tests -p test_crew_capabilities.py -v
python -B -X utf8 -m unittest tests.test_p04d_native_crew_verify -v
node --test --test-concurrency=1 web/tests/game-adapter.test.mjs web/tests/test-garage.test.mjs web/tests/vehicle-status.test.mjs web/tests/p09d-ammo.test.mjs web/tests/p04d-crew.test.mjs
python -B -X utf8 server/check_layout.py
```

Native install preparation used `tools/interactive_client.py prepare`,
explicit `--research-copy local/clients/p04d-b`, owned `--public-key`,
`--endpoint 127.0.0.1:23014`, profile `local/p04d/profile`,
`--enable-p09d-ammo-service --enable-crew-recruitment`, own Python2.7 compiler
and fresh evidence output directories. Exact settings/sources/compiled hashes
are retained in `N/install04/install-plan.json` and `N/install05/install-plan.json`.
The receipt-owned launcher performed:

```powershell
python -B -X utf8 local/p04d/run-native.py --install local/evidence/p04d-native01/install04 --out local/evidence/p04d-native01/run03
python -B -X utf8 local/p04d/run-native.py --install local/evidence/p04d-native01/install05 --out local/evidence/p04d-native01/run04
python -B -X utf8 tools/interactive_client.py rollback --out local/evidence/p04d-native01/install04
python -B -X utf8 tools/interactive_client.py rollback --out local/evidence/p04d-native01/install05
```

Independent verifier invocation uses repeatable `--wire` for `N/wire01` and
`N/wire02`, repeatable `--trace` for the two successful native traces above,
`--private-key local/p04d/runtime/private.pem`,
`--database N/persistence/after-relogin.sqlite`,
`--install-plan N/install04/install-plan.json`, and a fresh owned `--out`.
`N` must be expanded to its literal relative directory; keys/captures stay local.

## Limitations, rollback and next step

**PROJECT_POLICY:** one free100% MS-1 driver, fixed verified passport, no skills,
no battle admission. Paid tariffs, historical tariff-to-level mapping, other
roles/vehicles, retraining, dismissal, skill XP and equipment mutations remain
unsupported/UNKNOWN as described in the research report. Native visual110%
is a commander bonus, not a persisted110% recruitment level. General graphics
quality and physical mouse interaction are not accepted by this card.

Runtime rollback is already complete for all installed own test overlays.
For a later reactivation, use that new installation's ledger and stop only its
receipt-owned processes. To undo schema activation on the isolated stand,
stop its writers and restore a consistent pre-activation DB backup
`local/p04d/runtime/game-before-activation.sqlite`; this intentionally loses
the later test recruitment/ammo state. Do not copy it over another database.
Source rollback is a normal revert of this P04D commit, keeping the frozen
dependency commits separately reviewable. Never reset the primary checkout.

**One next recommended step:** repair the historical regression fixtures'
portable path/hash binding, rerun the required integration checks, then merge
the accepted crew/ammo dependency stack through the standing workflow.
