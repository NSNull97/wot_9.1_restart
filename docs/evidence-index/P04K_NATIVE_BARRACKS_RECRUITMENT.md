# P04K — original Barracks recruitment

Status: **PASS_NATIVE_BARRACKS_RECRUITMENT_CURRENT_SOURCE**. Branch
`codex/p04k-native-barracks-recruitment`, base main
`32aa2fc2e77e652bc6eccbce5ef404a06711943c`.
Source/no-ff merge/remote SHA are recorded in `acceptance-final/`.
Complete-crew acceptance remains open; physical owner input is NOT_RUN.

## Goal and implemented contract

Hire free50 tankmen directly into the original Barracks through CMD303, retain
original lists/counts/filters and prove persistence through fresh native login.
The same authoritative writer preserves all previous crew operations and
immutable historical receipts. Ordinary learning requires100% primary
qualification; the owner's unlearned base Sixth Sense exception is retained.

Schema `p04k-native-barracks-recruitment.v1`, profile12. Canonical policy:
`e9a12e9000cc255679d5dad6d744943f325ae1982c5a21060a5996f62c433fd7`.
Original source audit:
`ef2239aed04ed2dd29608ee305d2028863f162631454e91388358f579fbcd7c1`.
Shop revision3 and exact fixture SHA are separate from account/configuration/
wire revisions. New response fields carry only the validated allocated ID and
25-byte passport; gateway independently binds request/descriptor/delta/quota,
then queues inventory update before the original two-field response extension.

Frozen native expectation, independently accepted in native05/06: J55→migration56→58,
config45→47, quota5→3,next12→14; hires IS7gunner12 and MS1commander13 remain
in barracks. MS1[4,11]/IS7[6,7,8,10,9], retired3/5 and all previous members,
skills, money and ammunition remain unchanged. Final11 active/4 barracks.

## Changed files and current gates

Components: K projection/store and minimal J retirement-contract hook; K
request/typed response gateway and existing identity/session/hangar admission;
web route/strict response/sparse overview; client Barracks UI/control/install
and original callback observers; independent source/native audit and tests.
Primary P05, original client and other stands are unchanged. The J evidence
index also corrects one command transcription: positive dismiss19 did not
activate the schema again. Accepted J evidence itself remains unchanged.

Ignored evidence root `local/evidence/20261014-p04k-native-barracks-01/`.

| Gate | Actual current result | Evidence |
|---|---|---|
| Original source audit |Canonical digest verified against actual #717|`source-audit/`, source agent receipts|
| Store/domain/regression |648 distinct PASS:554 unchanged broad+67 historical+27 current K|`store/final-store02.json`|
| Separate-process persistence |13 actual CLI invocations PASS; maximum mutation/replay1.079s|`store/cli01/receipt.json`|
| Rust gateway/build |750 PASS, exact executable frozen|`rust/receipt02.json`, `local/build/server/gateway-p04k01/result.json`|
| Real HTTP/SQLite bridge |2 targeted tests PASS, stable sources|`web/targeted-web01.json`|
| Independent gateway/web review |PASS, no findings|`store/integration-review01.json`|
| Full web suite |108 PASS, no failures/skips; current runtime closure bound, unrelated verifier drift identified|`web/full-web02.json`, `store/full-web02-binding.json`|
| Native UI/control/CPython2.7.3 |471 client+42 P03M PASS,14 real CPython2.7.3 compiles and Unicode execution PASS; both native installs bind37 compiled modules|`client/run-05/receipt.json`, `client/freeze04.json`, final native receipt|
| Native303/callback/wire/DB/relogin/pixels |PASS: two hires, fresh login preserves29 non-rate-limit tables,14 required PNGs inspected, no new runtime errors|`independent-native/final01/receipt.json`, `native-run05/root-pixels.json`, `native-run06/root-pixels.json`|
| Source/verifier regression and cross-review |65 distinct PASS; actual UI-observer model accepted and all negative mutants rejected|`independent-native/unit03/receipt.json`, `store/functional-renderer-cross-review01.json`|
| Actual Python union |1233 distinct PASS; one existing platform NOT_RUN kept separate|`checks-final02/receipt.json`|
| Owned cleanup |6 installs restored,18 process instances ended,12 service stops, ports free/control unarmed|`native-cleanup-final01.json`|
| Layout |97 source files/22 relocations PASS;7 unit cases PASS, one existing symlink-permission NOT_RUN|`layout01.json`, `layout-tests01.log`|
| Physical owner input |NOT_RUN; deferred until after09:00 on2026-10-14 Asia/Yekaterinburg|Owner instruction|

## Preserved development failures

Native01 exits0 but fails the scenario: original303 request226 commits
IS7gunner12 (K56→57, nextID13), and original Shop callback sees the matching
new descriptor. Recycled renderer restoration then raises None.text; the
original old inventory parser also reports missing `lock`. This is **FAIL**,
not a successful native scenario. Partial pixels show correct original
selectors/free50 quota and visible unavailable berth purchase, without proving
the completed workflow. `native-run01/root-partial-pixels.json`,
`client/native01-diagnosis.json`, `native-persistence/after-recruit01.sqlite`
and all logs are retained. The initial progress statement of no mutation was
corrected after full trace/DB review. `reset-after01.json` records restoration
of the isolated runtime to immutable K56 for a new attempt.

The correction restores display values before original row disposal, releases
only source-proven disposed proxies and waits for incomplete renderers.
K full-state projection adds original `inventory[1].lock={}` for two available
owned vehicles; reserved full-state publication fails closed. Existing303
mutation/replay and historical D–J projection bytes remain unchanged.
`fixture02.json` confirms fresh fixtures without changing any of30 DB tables.
Focused store02 initially failed its new test because the old hangar-only
bounded decoder rejects valid shell-layout tuple keys; the test now uses the
existing bounded ammunition decoder. The production parser was not weakened.

Native02 proves both original303 mutations (K56→58/config45→47), typed
extensions, cache callbacks and initial CMD100 full state with `lock={}`.
It still fails after selecting the Barracks-only filter: original TileList
retains unused pooled renderers, and BarracksItemRenderer.setData(undefined)
leaves their prior data intact. A pool-wide scan therefore finds a stale buy
card. The fix binds traversal to the current logical provider and renderer
index while retaining duplicate rejection. `after-recruit02.sqlite`,
`reset-after02.json` and `independent-native/partial02-final/receipt.json`
retain this result as partial observations, never as full UI/relogin acceptance.
The isolated DB was explicitly restored to the same K56 baseline for retry.

Native03 fails before commands because provider reflection keeps the previous
saved filter. Native04 passes the initial surface and commits the first303;
its additional diagnostics establish all12 current functional getData rows
and indices, including newID12, while the provider property still returns11
old rows. This is an OBSERVED readback divergence, not proof of the underlying
engine cache cause. The final seam must use original getData/current logical
inputs and retain raw property observations; it may not manufacture provider
equality. `source-audit/native04-getdata-readback.json` and all failed native
receipts are retained. Native04 has no postfailure screenshot, only earlier
stages; final complete pixels remain mandatory on the corrected source.

Review of the actual layout output found that both J and K collect8 cases but
skip the pre-existing symlink-creation case on this Windows account. K reports
7 PASS/1 NOT_RUN and corrects J's earlier aggregate to1175 PASS/1 NOT_RUN;
J's immutable original receipts are retained with a separate correction receipt.
The layout checker itself passes; this unavailable auxiliary platform case is
not used to claim native or filesystem-link behavior.

`gateway-p04k-check01` failed compilation on a missing new optional field in a
test initializer and missing continue in the new dispatch match arm. Both were
fixed before the current full run. `gateway-p04k-check02` passed two codec
tests but its third assertion mistook the selectPlayerEntity prefix for the
method ID. Test offsets were corrected; the encoder was unchanged. Current
full750 includes the repaired tests and the additional response/metadata/
scheduler adverse cases. Earlier logs remain immutable.

## Commands, limits and rollback

Executed commands include:

```text
python -B -X utf8 server/build.py gateway --test --out local/build/server/gateway-p04k01
python -B -X utf8 local/p04k/run-web.py --run 01
python -B -X utf8 local/p04k/run-web.py --run 02 --full
python -B -X utf8 local/p04k/prepare-runtime.py
python -B -X utf8 server/check_layout.py --out local/evidence/20261014-p04k-native-barracks-01/layout01.json
```

Actual final native commands (run05 mode recruit, then06 mode relogin):

```text
python -B -X utf8 local/p04k/prepare-native.py --run 05 --mode recruit
powershell -NoProfile -File local/p04k/services.ps1 -Action start -Run 05
python -B -X utf8 local/p04d/run-native.py --install local/evidence/20261014-p04k-native-barracks-01/native-install05 --out local/evidence/20261014-p04k-native-barracks-01/native-run05
python -B -X utf8 local/p04k/freeze-native.py --run 05 --mode recruit
python -B -X utf8 local/p04k/prepare-native.py --run 06 --mode relogin
powershell -NoProfile -File local/p04k/services.ps1 -Action start -Run 06
python -B -X utf8 local/p04d/run-native.py --install local/evidence/20261014-p04k-native-barracks-01/native-install06 --out local/evidence/20261014-p04k-native-barracks-01/native-run06
python -B -X utf8 local/p04k/freeze-native.py --run 06 --mode relogin
python -B -X utf8 local/p04k/verify-native.py --scenario 05 --relogin 06 --out final01
powershell -NoProfile -File local/p04k/check-cleanup.ps1 -Runs 6
python -B -X utf8 local/p04k/final-checks.py --client client/run-05 --source independent-native/unit03 --run 02
```

Runtime preparation is isolated. Reproduction uses fresh evidence names and
the frozen baseline; never rerun positive hires against the progressed DB.
Final root pixel-review receipts were written only after visual inspection.
Finalization initially undercounted two passing tests whose expected CLI
rejection diagnostics split the unittest status over multiple lines; the
strict collector now associates the later `ok` with the pending test ID.
`checks-final01/` remains preserved; no production or test expectation changed.

Current raw source hashes are rechecked against each applicable suite and
both native installation manifests before Git staging. Final receipts bind
the staged Git blobs, source commit, ordinary merge and verified remote SHA.

Paid choices, berth purchases, historical daily reset and exact tariff tables
remain unavailable/UNKNOWN. Lifetime16 is explicit test_lab policy. Broader
nations/vehicles, earned XP progression, retraining/reset/personalization/bulk
operations and combat perk effects are outside this card's acceptance.
The complete-crew objective remains open.

Rollback restores the owned installation ledger and immutable accepted J55 DB
with matching J source/config. Never downgrade just the schema markers or
reuse retired IDs. After acceptance, revert K with
`git revert -m 1 <K-main-merge>` and the matching DB restoration.

One next step: separate original free first-skill reset/reselection card for
the currently represented primary100/skill0/freeXP0 state, with immutable
historical replay and a complete original-dialog/native-wire acceptance gate.
