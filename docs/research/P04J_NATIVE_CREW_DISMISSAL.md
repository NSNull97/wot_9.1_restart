# P04J — native dismissal, sparse crew and bounded display compatibility

This card researches only the verified RU0.9.1 #717 client. Original resources
remain read-only. It continues accepted P04I; the server is authoritative and
uses native CMD306. It does not establish historical reset prices, dismissal
refunds, crew recovery rules or battle effects.

## Evidence and classification

**VERIFIED_STATIC:** `tools/p04j_crew_source_audit.py` retains every P04I source
pin and audits46 original Python/.def/XML resources plus the original
`res/packages/gui.pkg!gui/flash/Application.swf`. It validates26 additional
Python code records with complete code SHA, signatures and semantic offsets,
and23 Flash method bodies. It never executes original Python/ActionScript.

The API is `audit_sources(original_root: Path) -> dict`, returning
`PASS_P04J_STATIC_SOURCE_AUDIT`. Canonical UTF-8 JSON with sorted keys and
separators `(',', ':')`, `ensure_ascii=False` has SHA256:

`4b615aac0f62d4a6369066285e343e81df08829ccbb31c89cc8ef0dd6a5ca456`.

This receipt contains source facts, no authored client/store file pins and no
absolute installation paths. Resource pins are independent of the client
manifest's target identity. The package container is bounded before ZIP
metadata allocation; its selected member is cryptographically pinned. The
whole629MB archive is not claimed to be independently hashed by this auditor.

Ignored evidence root:
`local/evidence/20261013-p04j-native-dismissal-01/source-audit/`.
`prepared.json` records static extraction; `run01/receipt.json` is the source
audit; `unit01/receipt.json` and logs bind the actual35 J/I tests.
`events02.json` adds original constructor signatures and access namespaces.
The initial19-test run had one type-equality failure (pin list versus inherited
tuple); exact pin values were unchanged. The corrected35-test run is recorded.

## Native command and confirmation

`common/accountcommands.pyc` module offsets298/301 bind306 to
`CMD_DISMISS_TMAN`. `Inventory.dismissTankman` source line162, bytecode offsets
86/92/95/98/101/107, sends `_doCmdInt3(CMD_DISMISS_TMAN, tmanInvID, 0, 0, proxy)`.
The Int3 request arguments after requestID and command are `[tankmanID,0,0]`.
The method0x8e/VAR2/20 framing is now **OBSERVED in native19 CMD306**
requests226/227, with exact ID3/ID5 layouts, independent decryption and
source-pinned original button callbacks before both commands.

Original entry points are `PersonalCase.dismissTankman(tmanInvID)` line146
and `Barracks.dismissTankman(invID)` line304. Both get the actual cached member
and invoke `TankmanDismiss`; Barracks explicitly rejects a missing member.
`TankmanDismiss.__init__` line15 creates
`DismissTankmanConfirmator('protectedDismissTankman', tankman)` and enables
`VehicleValidator` only when the member has `vehicleInvID > 0`.
`DialogAbstractConfirmator._confirm` line451 yields the original dialog and
returns `makeError` after cancellation before a server request.

The Python dialog `__prepareTankmanData` line32 always builds the model payload
from the real member. No skills and primary qualification below100 selects
ordinary confirmation. No skills at100 uses `str(roleLevel)` as the protected
control number. An existing skill uses `str(lastSkill.level)` even at zero:
ID3 with Repair0 therefore requires **"0"**, not"100". The controls are installed
by `__updateInputChecker` line84. `InputChecker.sendUserInput` line42 requires
both equality to the original control string and valid syntax. Its method
`as_invalidUserTextS(True)` means the input is valid despite the method name.

Directly calling Python `SimpleDialog.onButtonClick('submit')` cannot prove
this protection: `__callHandler` line22 only compares the supplied button ID
with SUBMIT. Actual acceptance must observe the original Flash enabled-button
path and resulting request, including wrong-input rejection and cancellation.

## Effective movie, native rendering and bounded compatibility

The registered resource and the executing duplicate class are separate facts.
Original view registration selects `dismissTankmanDialog.swf`, but original
LoaderManager.as_loadView553 constructs `LoaderContext(false,
ApplicationDomain.currentDomain)`. Both Application and the child contain the
same public class. Registration and a ResMgr hash alone cannot establish which
method executes. The canonical domain source audit deliberately makes no such
runtime claim.

**VERIFIED_STATIC:** registration source `settings/__init__.pyc` is15074 bytes,
SHA256 `eb47b23db5f7a3b56928a21c324266e32a1e588c3e15b04b69cac2281e509c1f`;
module offsets2910..2943 bind the alias, Python dialog, child filename and
TOP_WINDOW. Original DismissTankmanDialogMeta accepts `(self,value)` and
conditionally calls `flashObject.as_tankMan(value)`. The original child is
132797 bytes, SHA256
`33a92ccdcf2ef278e41e5ca1dd349e2eff3f323486e9a1c3065d0809336fffe5`.
It remains **untouched in the accepted constructor implementation**.

**OBSERVED_NATIVE:** diagnostic08 changed only the child's as_tankMan to a
fixed-length returnvoid/NOP body and still encountered the invocation error.
Diagnostic09 changed only Application's method to returnvoid/NOP, with the
child restored, and the original Meta call returned. Diagnostic10 wrote
`String(argument1)` into the existing question field: both native readback and
the captured window showed `[object Object]`. This differential located the
effective Application method for this window and proved a non-null argument;
it did not itself prove working confirmation or authorize a fake success.
All probes are retained as diagnostic evidence and rejected by acceptance.

The current compatibility transform therefore affects only Application's
as_tankMan13017. The original Application is1258376 bytes, SHA256
`8c53f7cf510a3b328ee114307613c8f1416beb3360b587b6b158bb7d8ac02b62`.
Original method bytes begin at decompressed-body2631489, length145,
SHA256 `9f35526bcb6052e7bdcbd7386051d9009e5eb46fcecb6a691a6dab99a6009fb5`.
The replacement constructs native SkillDropModel within Flash and copies only
twelve actual member display primitives into existing public fields. It
supplies no tariff rows or invented prices. The original constructor supplies
its own disposable cost objects; the display adapter does not assign prices.

The independent complete-body oracle permits a111-byte prefix in place of the
original9 bytes, method length247, maxstack4 and the corresponding+102-byte
DoABC/SWF length changes. Everything else in the decompressed body is exact,
including original branch operands, confirmation, layout, validation and
disposal. The accepted constructor artifact is1267372 bytes, SHA256
`592c5c8c6ef71f49b49003c64833d3338dd1323e6fd7f3f477466d2acc5c8fa9`.
`source-audit/transform07-independent.json` independently binds it. The
installer includes only Application and independently observes the unchanged
child; bundles, compiled sources, postrun files and complete restoration are
bound by the ordinary install ledger.

**OBSERVED_NATIVE11/12:** the original public widgets render the correct
member name, portrait, role icon, qualification text/bar and learned Repair0
while `flash.model` reads as None through PyGFx. This null getter is an
observation limit, not evidence that the native model failed to construct.
The verifier records `typed_model_readback=UNAVAILABLE_OBSERVED` and
`actual_model_readback=False`; it never relabels this as a successful typed
model readback. Original draw13018 requires a truthy model before setData13023;
that unchanged path feeds the observed public controls.

The gate checks nameField.text, tankmanPic.source, roleIcon.source,
roleLevelField.text, specLevelBar.frontPosition, nation and all four skill
visibility flags. A single learned skill uses native `current_skill`, the
actual icon, level0 and the original widget count default0. The simple50
branch hides all four skill widgets. No root visibility proxy is treated as
proof of rendered content. The independent expected labels come from the
pinned passport, USSR XML, RU MO localization and native icon prefixes;
ID3 is Алексей Петров with ussr-2.png/driver/repair, ID5 is Аркадий Егоров with
ussr-5.png/driver and no skill. No runtime trace provides those expected names.

## Original input and event route

The original Python dialog __updateInputChecker84 explicitly converts its
control number to `str` before calling setControlNumbers. InputChecker._populate15
only calls its base and as_invalidUserTextS(False); it contains no truthy-zero
replay branch. The proposed numeric-zero explanation was therefore rejected.
Both original Meta setters forward only while DAAPI is initialized.

Flash isValidControlInput13444 is a public Boolean getter. It requires an
existing creditsParseResult and compares entered text with the original or
formatted control string. It is **not a generic numeric-syntax predicate**:
wrong100 for control0 must returnFalse; correct0 must returnTrue. The public
isInvalidUserText getter13443 exposes the original Python validation response.
Locale.parseFormattedInteger1044 returns a constructed FormattedInteger,
including for zero. Private runtimeValidate13448 only changes the error state;
it is not a public callback route and is not invoked by the diagnostic.

The original userInputHandler13452 handles native KEY_UP, computes getUserText
and isValidControlInput internally, then calls sendUserInputS. The current
measurement sets real input text, dispatches a genuine KEY_LEFTARROW down/up through
GUI.handleKeyEvent and observes the unchanged Python sendUserInput42 callback
passively. It does not supply a Boolean or call that callback itself. Original
Meta setter arguments, DAAPI readiness, original/formatted controls and focus
are recorded separately. No validator or price state is rewritten.

Native13 observed both original setters called with string0 and DAAPI ready.
Their immediate public formatted-control read was empty, then became0 on a
later observation. It also found focus on the second button, not the input,
and refused to inject events. This preserves a remaining uncertainty about
same-tick PyGFx reads. The verified public UIComponent.focused(Number) setter620
is available to request normal input focus, followed by a later readback;
this changes focus only. A successful native validation callback is still
required before acceptance.

For the later positive button gate, original Button.handleInput2445 routes
ENTER down/up through enabled handlePress2461/handleRelease2462 and dispatches
the native click. SimpleDialog.as_setButtonFocus3308 is public. The companion
pins original BigWorld.KeyEvent constructor usage from WebBrowser and original
GUI.handleKeyEvent dispatch from game.pyc. Calling protected handlers or Python
onButtonClick directly is not admissible evidence. KEY_RETURN-to-CMD306 is **OBSERVED in native19**: wrong input produced
no original button callback or command; each positive input produced exactly
one original onButtonClick followed by its correlated CMD306. Automated engine events and physical keyboard or
mouse input are distinct; physical input is **NOT_RUN**.

## Native cache removal and sparse IDs

`Inventory.synchronize` line68 applies `synchronizeDicts` from the original
`account_helpers/diff_utils.pyc`. For ordinary dictionary keys, a None diff
value executes `cache.pop(key,None)` at offsets312..336. The special tuple
suffix `_d` is set difference, not dictionary-entry deletion. Ordinary list
values are replaced intact at offset499, preserving real None vacant seats.

The supported dismissal delta therefore removes inventory8 `compDescr[id]`
and `vehicle[id]` with None and updates inventory1 crew arrays when a seat
changes. `ItemsRequester.invalidateCache` line283 gathers changed tankman IDs;
`_invalidateItems` line573 invalidates inventory items and removes cached GUI
objects. `InventoryRequester.__makeTankman` line182 returns None when the
compact descriptor is absent (offsets81/93/102/105). The upper requester returns
None for missing tankman data as well. IDs are dictionary keys; contiguous
array indexing is not a native requirement. The dossier remains embedded in
the descriptor; no separate dossier deletion stream is established or needed
for this representation. Actual native19 sparse-cache readback and fresh-process native20 relogin
are **OBSERVED/PASS**; missing IDs3/5 return None and no ID is reused.

The client's daily free-hire allowance is distinct from member count or
barracks capacity. Historical refunds, daily grant/reset parameters, ID reuse,
recovery and retired-member persistence are **UNKNOWN** from this code.
J's lifetime allocator, immutable terminal records, no refund and no quota
refill are explicit authoritative project rules, not historical claims.

## Measured native acceptance and limits

Initial acceptedI has revision48/config39/quota6 and active IDs1..10;
MS1 `[4,5]`, IS7 `[6,7,8,10,9]`. J migration gives revision49. Planned checks:
protected ID3 wrong"100" versus correct"0", cancel with no request or mutation;
then dismiss3, dismiss seated50% ID5, hire next unused driver11, seat2, unload2,
restore11. Six commands should give revision55/config45/quota5/next12,
retired3/5, nine live members, MS1 `[4,11]`, unchanged IS7. These values were independently fixed
before execution and are now matched by native19/20, not derived from their
outcome.

**PASS_NATIVE_DISMISSAL_SPARSE_CREW_WIRE_RELOGIN**, native19/20, final
independent verifier3759ad0721164b70883f83236f9b18abfb9558ce031facaed17d7bbdac0de4f0.
Native18 also passes the current verifier
(`independent-native/preflight18-final03/receipt.json`, SHA
`cad21b220192900c93c85564046af2df037237de4afdedd4e648dcc028b3073d`).
Normal process exit, exact artifact bytes and successful rollback are not UI
acceptance. Earlier evidence remains available:

- Factory/9-byte Application attempts01..03 observed a null typed getter but
  did not establish the actual rendering or a PyGFx conversion defect.
- Application constructor05 had the same getter limitation, without the
  public surface proof later obtained in11. Its bytes match the current
  constructor; the earlier failure interpretation was incomplete.
- Child constructor06 and coerce-only07 failed at Meta invocation. The latter
  falsified the proposed coerce repair. Their exact static diffs remain
  `transform05-independent.json` and `transform06-independent.json`.
- Child probe08, Application probe09 and argument marker10 established the
  effective method/argument boundary. Their artifacts are diagnostic only.
- Attempt11 exposed the typed-getter limitation while the original window
  rendered correctly. Attempt12 passed the renderer gate but correct0 still
  appeared invalid through the then-used direct getter/callback sequence.
- Attempt13 observed real initialization and delayed primitive readback,
  then stopped because the original text input had no focus. It sent no
  validation keys or crew requests; all27 durable tables stayed unchanged.
- Attempt14 established positive input focus on a later native tick, then
  rejected the diagnostic's unsupported Keys.KEY_LEFT symbol before key
  dispatch. Original WebBrowser.__init__55 pins KEY_LEFTARROW instead.
  The diagnostic name is corrected from source; no native result is inferred.
- Attempt15 used the actual engine constants LEFTARROW203/RETURN28. GUI
  handled the events, and the original passive Python callback observed
  wrong100=False and correct0=True. A later assertion about the button and
  public validation-result getter failed; those fields were not separately
  emitted at failure. This proves the input callback, not enabled confirmation.
- Attempt16 observed the original callback followed by original Meta68(True).
  Four later reflected Boolean reads remained false, while inspected PNGs
  showed the correct0 dismissal button white with gold focus and wrong100 grey.
  That attempted acceptance still failed and remains immutable. The cause is
  UNKNOWN: a PyGFx cache defect is only a hypothesis. A bounded search of the
  original Flash/Application/DAAPIModule wrappers found no refresh API;
  `store/pygfx-refresh-source-review01.json` pins three files and13 anchors.
- Attempt17 completed protected/wrong/correct/simple observations and both
  original cancellations with zero mutations. Its PNGs were inspected and its
  trace passes the new callback/Meta oracle in isolation. It used an earlier
  sr_interactive source missing the full-mode button observer route; the whole
  current-source acceptance is deliberately repeated in18 instead of relaxing
  source pins. Neither17 nor generated full-mode fixtures establish CMD306.
- Attempt18 passed the strict independent CLI after exit0, rollback and service
  stop. `independent-native/preflight18/receipt.json` SHA
  `10adf05e762b59445cb14828b5c9f984ee8ba50b09f29bed9f66edbce7ebaf02`
  binds36 current source/compiled/bundle/postrun/restore chains, the exact
  Application transform and unchanged child, six native confirmation
  observations, both cancellations and actual callback/Meta values. Decrypted
  traffic contains zero crew requests; all27 durable tables are unchanged at
  revision49/config39/quota6. Eight actual PNG containers are pinned; five
  stages are linked to root's separate visual inspection. No typed or Boolean
  getter success is invented.

Native19/20 full receipt: `independent-native/final01/receipt.json`, SHA
`5702396068316b88461b7d16e0595f4ab8eb68890a0004ccb12a47ab3ed640c1`.
Process9180 executes request IDs226..231; fresh process31988 only reads both
vehicles. The six original commands are306/306/309/105/105/105 with exact
layouts `[3,0,0]`, `[5,0,0]`, `[3,1,1,0]`, `[1,1,2]`, `[1,1,-1]`,
`[1,1,11]`. Exact independent delta lengths are113/112/166/104/99/97 bytes;
each update precedes its correlated native success with an empty extension.
The final database is revision55/config45/quota5/next12, retired IDs3/5,
MS1 `[4,11]` and IS7 `[6,7,8,10,9]`. All surviving passports, skills,
embedded dossiers, ammunition and balances are unchanged. The next ID was
allocated once, without reuse or quota refund. Both original retirement
immutability triggers are checked independently. All27 durable tables match
between final and fresh-login backups; only the operational rate-limit table
is excluded. Each install binds all36 current sources through the actual
CPython2.7 compilation, immutable bundle, postrun capture and restored state.
Eighteen scenario PNGs and two relogin PNGs are byte-bound; mandatory named
stages link to root's actual visual inspection. Full crew observations do not
claim battle readiness; the native ammunition warning is legitimate.

**NOT_RUN/UNKNOWN limits:** physical owner mouse/keyboard input, historical
reset/retraining prices, historical dismissal refunds/recovery, server daily
hire reset policy and combat behavior. The authoritative allocator and terminal
journal are explicit project policy. Reflected Boolean/typed object getters
remain unavailable as effective-state evidence; their raw values are preserved.

Unit03 preserves73 passing tests of the then-current child candidate. Unit04
preserves77 tests with one obsolete transform-API test failure, fixed rather
than waived. Unit05 passes78 tests of diagnostic15. Unit06 passes81 tests but
independent review identified three accepted full-trace mutants: a foreign
checker in dispatch summaries and mismatched numeric Enter keys. These are
closed in unit07:82 tests PASS in24.067 seconds, plus independent18-check
`store/full-verifier-review07.json` (SHA
`e3116cecafa4fa055d2ba7f5154768ae31e2bb2f66a5b07cdac8ce539dd84e6a`).
The exact distinct test IDs are `independent-native/unit07/test-ids.json`.
Unit07 binds final UI1149cc61 and sr47d32561. A repeat preflight verifier run
while native19 had the owned copy installed correctly failed its final rollback
hash gate (`preflight18-final02`); after both restores the current repeat
`preflight18-final03` passes. That environment failure is retained.

Reflected Boolean fields are retained verbatim under
`raw_boolean_observations`, with `boolean_readback=UNAVAILABLE_OBSERVED`.
They are never changed to true or interpreted as effective enabled state.
Preflight requires source-pinned actual callback42 and Meta68 call/return pairs,
exact scalar rendering, protected/wrong/correct/simple PNGs and both original
cancellations. An independently attributed root pixel-review receipt is bound
by trace SHA and each exact screenshot SHA; file hashing alone is not visual
inspection. Full mode additionally requires wrong native Enter with no original
button callback/request for the bounded observation interval, then correct or
simple native Enter followed by exactly one pinned original onButtonClick and
its correlated CMD306 within five seconds. A callback may arrive asynchronously
after GUI.handleKeyEvent returns. No direct Python submit or enabled/validation
assignment can satisfy these gates.

Commands actually run:

```text
python -B -X utf8 tools/p04j_crew_source_audit.py --config config/project.local.json --out local/evidence/20261013-p04j-native-dismissal-01/source-audit/run01
python -B -X utf8 -m unittest tests.test_p04j_crew_source_audit tests.test_p04i_crew_source_audit
python -B -X utf8 -m unittest tests.test_p04j_native_crew_verify tests.test_p04j_crew_source_audit tests.test_p04i_native_crew_verify tests.test_p04i_crew_source_audit
python -B -X utf8 tools/p04j_native_crew_verify.py --mode preflight --wire local/evidence/20261013-p04j-native-dismissal-01/native-wire18 --trace local/evidence/20261013-p04j-native-dismissal-01/native-runtime18/native-27396-1791921752121.jsonl --install-plan local/evidence/20261013-p04j-native-dismissal-01/native-install18/install-plan.json --pixel-review local/evidence/20261013-p04j-native-dismissal-01/native-preflight18/root-pixels.json --private-key local/p04d/runtime/private.pem --before-database local/evidence/20261013-p04j-native-dismissal-01/native-persistence/before-dismiss.sqlite --database local/evidence/20261013-p04j-native-dismissal-01/native-persistence/after-preflight18.sqlite --original-root C:/WoT_0.9.1_RU_0717_original --out local/evidence/20261013-p04j-native-dismissal-01/independent-native/preflight18
# Same preflight18 inputs repeated after the final restore with --out .../independent-native/preflight18-final03.
python -B -X utf8 tools/p04j_native_crew_verify.py --mode full --wire local/evidence/20261013-p04j-native-dismissal-01/native-wire19 --wire local/evidence/20261013-p04j-native-dismissal-01/native-wire20 --trace local/evidence/20261013-p04j-native-dismissal-01/native-runtime19/native-9180-1791921927516.jsonl --trace local/evidence/20261013-p04j-native-dismissal-01/native-runtime20/native-31988-1791922089433.jsonl --install-plan local/evidence/20261013-p04j-native-dismissal-01/native-install19/install-plan.json --install-plan local/evidence/20261013-p04j-native-dismissal-01/native-install20/install-plan.json --pixel-review local/evidence/20261013-p04j-native-dismissal-01/native-run19/root-pixels.json --pixel-review local/evidence/20261013-p04j-native-dismissal-01/native-run20/root-pixels-corrected.json --private-key local/p04d/runtime/private.pem --before-database local/evidence/20261013-p04j-native-dismissal-01/native-persistence/before-dismiss.sqlite --database local/evidence/20261013-p04j-native-dismissal-01/native-persistence/after-dismiss19.sqlite --relogin-database local/evidence/20261013-p04j-native-dismissal-01/native-persistence/after-relogin20.sqlite --original-root C:/WoT_0.9.1_RU_0717_original --out local/evidence/20261013-p04j-native-dismissal-01/independent-native/final01
```

Changed research files: this document, the new J source auditor, independent
verifier and their tests.
Rollback this research by reverting those files; installed compatibility must
use the ordinary owned-client install/restore ledger. A progressed J database
must be replaced only with its immutable pre-J backup and matching I sources,
never downgraded in place. **Next step:** integrate the accepted J card
under the repository branch/merge workflow. Native barracks recruitment CMD303
is a separate researched card, not part of this acceptance.
