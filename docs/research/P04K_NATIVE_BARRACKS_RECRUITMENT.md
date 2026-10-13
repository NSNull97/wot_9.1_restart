# P04K — original Barracks recruitment, #717

The card extends the accepted sparse crew inventory with original CMD303 hires
into Barracks. MS-1 and IS-7 assignments remain unchanged. New50 qualification,
free tariff0 and the lifetime16/quota rule are explicit owner-approved project
policy. They are not claimed as the historical daily recruitment entitlement.
Paid training and berth purchases remain unavailable. No new Flash resource
transformation is introduced by K.

The original client is read only at `C:/WoT_0.9.1_RU_0717_original`.
Research uses bounded Python2.7 marshal/bytecode and SWF/ABC readers, never
execution of original Python or ActionScript. Local evidence root, abbreviated
`E` below, is `local/evidence/20261014-p04k-native-barracks-01/` in the owned
`crew-equipment-snapshot` worktree. Earlier Barracks extraction is preserved
under `local/evidence/20261013-crew-complete-research-01/barracks-source01/`.

## Frozen source and command contract — VERIFIED

`tools/p04k_crew_source_audit.py::audit_sources(Path)` verifies the original
source set, inherited J facts, Python method signatures and offsets, Flash
method byte ranges and public traits. Its canonical path-independent report is
`ef2239aed04ed2dd29608ee305d2028863f162631454e91388358f579fbcd7c1`.
The report does not depend on authored client modules or the current native
runtime. Compatibility findings below are separate acceptance companions;
they do not silently revise that frozen domain audit or policy.

Principal original pins:

| Original source | Bytes | SHA256 |
| --- | ---: | --- |
| `res/scripts/client/account_helpers/shop.pyc` | 25626 | `84aa30eb5b1862ac4fbb08557b67ad36dabc9b90cc1d083a29e0e12040127b6d` |
| `res/scripts/client/gui/scaleform/daapi/view/lobby/barracks/barracks.pyc` | 13142 | `1c18c924c6bfb9e753dae3f637b8b8079807a25b2e08e421b895bbb83bab3f19` |
| `res/scripts/client/gui/scaleform/daapi/view/lobby/recruitwindow/recruitwindow.pyc` | 11904 | `ac81a6a0a009fbc856505395f87f76d2a6df303291a7569eb2054f01f802fc41` |
| `res/scripts/client/gui/shared/utils/requesters/__init__.pyc` | 43604 | `1e2ab64ad9bc08308fec05f295f4a58a087c8ea970672b9ac6ec2da4b1e055a9` |
| `gui.pkg!gui/flash/Application.swf` | 1258376 | `8c53f7cf510a3b328ee114307613c8f1416beb3360b587b6b158bb7d8ac02b62` |
| `gui.pkg!gui/flash/barracks.swf` | 1861196 | `96b699ffdd5be7faeebc3d0ce382dfdcd2060e14286bf8337abad5e9388b4daf` |

Original `Shop.buyTankman`, first line795, calls Account doCmdInt4 with
`[shop cache revision, vehicle type compact descriptor, primary role index,
cost index]`. CMD303 uses the measured0x90 VAR2 envelope with24-byte
`<hhqiii>` payload including request ID and command. Current projected shop
revision3 is distinct from account, configuration and connection wire revisions.
The exact projected shop SHA is
`b55573c5b14fbbc034fbc2091d9e381645926c67e561ab46917ecd3d6965129a`.

The original callback lambda at line800 has code SHA
`295ac0b6f67a10f900820e4d0efee27c4d31937597584e2a632d608660002d3f`,
filename `scripts/client/account_helpers/Shop.py`, and locals
`requestID,resultID,errorStr,ext`. It passes result plus
`ext.get('tmanInvID',None)` and `ext.get('tmanCompDescr',None)` to its callback.
Acceptance therefore requires exact typed extension fields and native cache
update before that original proxy call/return, followed by Account success.
An empty success extension is insufficient for303.

The two planned requests are `[3,7169,4,0]` for IS-7 gunner12 and
`[3,3329,1,0]` for MS-1 commander13. They allocate unassigned members
`vehicle=-1,seat=None`, preserve all existing descriptor bytes and retired
identities, and advance K56→58/config45→47/quota5→3. Only the new descriptor,
its vehicle mapping and free quota appear in each inventory delta. No unchanged
vehicle crew arrays are added to those deltas.

## Original window, selectors and list — VERIFIED

The empty Barracks tile emits `CrewEvent(SHOW_RECRUIT_WINDOW,null,true)`.
The original Python opening receives renderer dataNone and menuEnabledTrue;
the unseated window has currentVehicleId-1 and slotNone. Original recruitment
validators still include money, free recruitment and free Barracks capacity.

Native selector data uses an initial `id=None` placeholder. Availability is
the conjunction of original UNLOCKED and not-observer criteria; ownership alone
is not an unlock predicate. The immutable imported unlock list includes3329
and7169. The role selector deduplicates each seat's primary role, so IS-7 has
commander,gunner,driver,loader, without a second loader option or separate
radioman primary role.

The netwg DropdownMenu public selectedIndex setter4389 dispatches its original
index-change event when the index changes. Its clik base implementation differs;
the class-qualified source matters. Diagnostic selection uses this public
setter and waits for the original Python update callback from the same window.
It does not directly call private Flash selection handlers or manufacture their
callbacks. A same-index change or final role choice does not invent a callback.

Original `Barracks.setFilter144` accepts
`(nation,role,tankType,location,nationID)`. The source values are
`[-1,'None','None','None',None]` for all,
`[-1,'None','None','barracks',None]` for Barracks, and
`[-1,'gunner','None','None',None]` for gunners. The string `'None'` is distinct
from PythonNone. Total and unassigned counts are calculated before filtering.

`BarracksForm.as_setTankmen14330`, Application body offset2693869/345bytes,
preserves the ordinary rows, conditionally appends an empty tile when unassigned
count is below capacity, and always appends one berth-purchase tile. Its source
SHA is `f3d8c49ea0f8faff3f27e23a95b150b2163e81f611fd6e54cfb0be41493b8c30`.
The project masks only the unsupported purchase tile via public enabled,
description and price/count visibility surfaces. It preserves original rows
and displays `Покупка мест недоступна`. Raw Boolean widget getters remain
observations; mandatory inspected screenshots bind the visible result.

## Native compatibility findings — VERIFIED source, OBSERVED failures

The older Barracks inventory reader requires a dictionary that the newer item
cache did not require for the earlier scenario. Original
`InventoryParser.parseVehicles178`, code SHA
`fef301f8d8ad2305b73805025396a35abc794c819be44094f4e52fdccfcc2ee1`,
reads `data['lock'].get(id,0)` at offsets285–301 and passes that value to the
vehicle constructor. Missing the dictionary raises KeyError. For the two
authoritatively available, unreserved vehicles, the K full-state projection
adds `inventory[1]['lock']={}`; absent per-vehicle entries use original default0.
This does not guess nonzero lock enums or admit a reserved vehicle. Evidence:
`E/source-audit/legacy-vehicle-parser01.json`.

The original renderer lifecycle also matters across recruitment and filtering:

- `BarracksItemRenderer.onDispose11456` at body2542113/319bytes clears `_data`,
  countField and descrField. Restoring saved display fields must happen before
  original list replacement; an exact fully disposed proxy is no live widget.
- `TileList.getRendererAt3044` bounds the physical renderer pool, not the current
  logical data-provider length. `TileList.populateData3066` calls setData for
  each pool entry, then disables/hides unused entries.
- `BarracksItemRenderer.setData11457` returns at offset7 for a falsy argument,
  before assigning data at offset18. An unused pool object can retain old
  `data.buy`. Counting every pool entry as a current row creates a false duplicate.
- The original `TileList.updateSelectedIndex3052` calls
  `getRendererAt(logicalIndex,scrollPosition)`. The corrected reader uses that
  public pair and requires exact category, identity and public renderer.index
  agreement. The logical bounds come from the exact original `as_setTankmenS`
  arguments and the verified empty/buy append rules. A transition remains
  pending, never accepted; the true duplicate-card check remains active.

The independently re-read method bytes and public traits are in
`E/source-audit/renderer-pool-companion03.json`, SHA
`7d698f6005790189557795da5dba09555fbcbc0386ac296447412f107618ad86`.
No K SWF change is needed for these findings.

The public `ListItemRenderer.getData2481` is a zero-argument method returning
`this.data`. Its original Application body offset2064323/7bytes has SHA
`829aaf4b4473c1b00e22658f3f11b0e532262a794c72779077c401f1ed5d9504`.
Static evidence does not make this a cache-refresh API. Native04 independently
distinguished the functional method result from the public provider getter:
all12 `getData()` row results and renderer indices matched the newly populated
list, including recruited ID12, while `dataProvider` still exposed the previous
11 entries. Engine internals explaining that difference remain UNKNOWN.

The final reader therefore uses the original method result for every accepted
visible row and purchase tile. Raw provider/property observations remain
unchanged and explicitly `OBSERVATION_ONLY`; their disagreement is never
rewritten into equality. Every observed method row must match its current
source-derived logical index, with no duplicate index or purchase tile.
Bindings are `E/source-audit/functional-renderer-companion04.json`, SHA
`d63b74b7b2d951df08a6a4bc7ee20e7d733f91096f5f3fee08bf93225aea6a73`, and
`E/source-audit/native04-getdata-readback.json`, SHA
`adad0f18b32f73444ff354668cfd52d387e8303493cabc91709fd78796cd9914`.

## Native evidence and remaining gate

Native01 is retained as a failed partial attempt: one real303 succeeded and
created ID12 before the renderer cleanup failure. The database reached K57,
not an unchanged baseline. The missing-lock traceback and disposed description
field error are preserved. Root restored the owned client, stopped services and
reset the isolated runtime from the immutable K56 backup; reset evidence is
`E/native-persistence/reset-after01.json`.

Native02 completed both real303 mutations and reached K58, then failed while
filtering the shorter Barracks list because stale pool entries looked like a
second buy tile. The independent partial receipt is
`E/independent-native/partial02-final/receipt.json`. It verifies both encrypted
wire requests, exact deltas and typed success extensions against immutable
ledger/database transitions. It also reassembles the actual initial CMD100
resource stream, verifies compressed size/CRC and bounded decompression, and
confirms the explicit empty lock dictionary and source-bound crew inventory.
This is **partial observed mutation evidence**, not UI or fresh-login acceptance.
The after database was reused only for the mutation oracle's comparison input;
no real relogin is claimed. Root preserved and reset that failed attempt too.

Native03 failed before recruitment because the provider getter still exposed
the saved Barracks filter after the original all-filter callback. Native04 was
a retained diagnostic failure after one successful303; it established the
functional row/provider divergence above. Neither run supplies final UI or
fresh-login acceptance. No post-failure native04 screenshot is claimed as proof
of the refreshed list; the bounded original method readbacks are the evidence
for that finding.

The independent final verifier requires two current-source processes, complete
native lists/selectors, two original303 proxies, unchanged fresh-login tables,
exact source→CPython2.7.3→installed bundle→restore bindings and separately
inspected native PNGs. It independently reassembles both initial state streams
and rejects missing locks, retired descriptors, wrong assignments or quota.
The native Python log must have no new traceback/error; only the two exact
known Vivox-unavailable messages are outside the crew acceptance scope.

Final corrected native05 plus fresh login06: **PASS**, independently verified
in `E/independent-native/final01/receipt.json`. Two exact303 hires, original
callbacks, full-state sync, unchanged29 fresh-login tables and14 required
visually inspected PNGs pass. Both native processes exit0 with no new errors;
37 current installed modules per run bind through actual CPython2.7.3.
Physical owner input, paid prices, berth expansion, daily quota/reset
rules and combat/battle admission remain unverified or outside this card.
Public script wrappers do not establish reliable primitive Boolean reflection
for every engine-backed Flash property. Pixel inspection and original callbacks
provide separate, explicitly bound observations.

Source unit evidence is `E/source-audit/unit01.json`; independent current-source
unit results and exact distinct test IDs are under
`E/independent-native/unit03/`:65 distinct tests passed, comprising15 K source,
22 K verifier and28 retained J verifier tests. This includes accepted stale raw
provider observations and rejected altered functional rows, indices, summaries,
missing retired-cache readbacks and mismatched Barracks owners.
The entry points are `tools/p04k_crew_source_audit.py --config ... --out ...`
and `tools/p04k_native_crew_verify.py --wire ... --trace ... --install-plan ...
--pixel-review ... --private-key ... --before-database ... --database ...
--relogin-database ... --original-root ... --out ...`, with each paired input
specified twice for recruitment and relogin. Run Python with `-B -X utf8`.

Rollback uses the owned installer ledger and an immutable database backup;
original #717 files are never modified. All six owned installations were
restored and18 owned process instances ended. The next crew card is original
free first-skill reset/reselection; no failed or incomplete K attempt was used
to close the final native gate.
