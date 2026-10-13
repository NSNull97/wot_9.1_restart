# P04G — native cross-vehicle crew assignment

2026-10-13. Branch `codex/p04g-native-cross-vehicle-crew`, accepted base
`83fecd563a9edc7dd13cdab56f3846e59673140b`. The owner requested a second
verified vehicle and crew transfers through the original interface.
The [execution plan](../plans/P04G_NATIVE_CROSS_VEHICLE_CREW.md) defines the
runtime, regression, restoration and acceptance gates.

**Static research: VERIFIED_STATIC. Native P04G wire/state/relogin gate:
PASS_NATIVE_CROSS_VEHICLE_CREW_WIRE_RELOGIN.** The actual G run01 and fresh
relogin02 were independently verified with unchanged verifier code. No result
from the earlier P04F run or generated unit inputs is relabelled as this
cross-vehicle observation. Pixel inspection and physical mouse input are
separate from this gate.

Evidence prefix `E` means the owned ignored directory
`local/evidence/20261013-p04g-cross-vehicle-crew-01/`. Original resources are
read only at `C:/WoT_0.9.1_RU_0717_original`. Captures, databases, keys, client
resources and compiled artifacts remain local. Static inspection uses the
bounded Python 2.7 reader and packed XML reader; original bytecode is not
executed or imported into the research process.

## Source identity and reproducible audit

The original target is RU `v.0.9.1 #717`, client manifest SHA256
`74c37c18e9ac7e30196c134076dacf6f2a8bf3897f7def73905d09feb3647797`.
`tools/p04g_crew_source_audit.py` checks 27 pinned resources, retains the 31
P04F bytecode records and adds 14 G records. It verifies specific constants,
operands, jumps and property calls rather than trusting names alone.

The path-independent canonical audit digest is
`e0693e0e36d2b5ca0c72e584684439b3b1c6eecfa9709b06820cbbc8832c7cb9`.
The full record, including file sizes, SHA256 values, marshal offsets, code
hashes, argument names and instruction offsets, is
`E/source-audit/pinned-audit01/receipt.json`. That pretty-printed file has SHA256
`c0c5004a335ea15801117496d607ba901aa49347bc944e69abb8bce556f12906`;
its file digest is intentionally distinct from the canonical object digest.
The static receipt's original NOT_RUN entries remain intact: the later native
receipt establishes additional observations without rewriting the source audit.

Selected original source pins:

| Source under the original client | Bytes | SHA256 |
| --- | ---: | --- |
| `res/scripts/item_defs/vehicles/ussr/ms-1.xml` | 11839 | `a494bf04d29da7d066fd6923dbb75a79b947559a52405298c494a943c4b0c535` |
| `res/scripts/item_defs/vehicles/ussr/is-7.xml` | 5809 | `8d55fa4657a88f1436cd164afe11bade875a906fa7b97256f1fb2f803b09c10d` |
| `res/scripts/client/gui/scaleform/daapi/view/lobby/hangar/crew.pyc` | 7329 | `8defb03050f4d903d40e466e11fed0b04c368f8fc0450263316e0b768edba136` |
| `res/scripts/client/gui/scaleform/daapi/view/lobby/hangar/tankcarousel.pyc` | 12529 | `84e023be8befc58478600084811bc753ec670dee0fdf0f1982fa1bd66e596e8a` |
| `res/scripts/client/gui/shared/gui_items/processors/tankman.pyc` | 25844 | `ef86bdc26577dc1d34dcc0c2f97ce230c185e5ae5b5ec41aaef5766224274d21` |
| `res/scripts/client/gui/shared/gui_items/tankman.pyc` | 15745 | `07645906b7cac95bc482c0e9548b37c598d3ec440752f7f19058688f981fa364` |
| `res/scripts/client/gui/shared/gui_items/vehicle.pyc` | 25863 | `ec78e36ab100e2c2274dd69476da99a26791037c6d79d707921168b1e95ae1e8` |
| `res/scripts/common/items/tankmen.pyc` | 24558 | `74f914b1e5e7e574086dd865d87e4cfbf8cace6e60b5e506757eba28ca8bc530` |

## Roster, identity and specialization are separate

**VERIFIED_STATIC:** both vehicles belong to nation0. MS-1 is non-premium
`lightTank`, trained type13, compact type3329. IS-7 is non-premium `heavyTank`,
type28, compact type7169. Their original seat order is:

| Vehicle | Native inventory ID in this profile | Zero-based seat | Primary role | Additional duties |
| --- | ---: | ---: | --- | --- |
| MS-1 | 1 | 0 | commander | gunner, radioman, loader |
| MS-1 | 1 | 1 | driver | none |
| IS-7 | 2 | 0 | commander | none |
| IS-7 | 2 | 1 | gunner | none |
| IS-7 | 2 | 2 | driver | none |
| IS-7 | 2 | 3 | loader | none |
| IS-7 | 2 | 4 | loader | radioman |

Native primary-role IDs are commander1, radioman2, driver3, gunner4, loader5.
These role IDs must not be confused with the project tankman inventory IDs
1, 2 and 3. G retains commander1 and drivers2/3, all with existing MS-1-trained
type13 descriptors. No IS-7 passport, additional crew member or retraining is
created by assignment.

`Crew.updateTankmen`, source line42, reads the seat's primary role through
`crewRoles[slot][0]` at bytecode offsets200, 203, 207 and210. Its combined-role
field uses the complete seat role tuple, with anchors382 and392.
`Tankman.__init__`, line116, initially derives the unassigned role tuple from
the descriptor at99/108, then obtains assigned seat roles at273/322/329.
An MS-1 commander's additional duties do not make that descriptor a driver or
authorize seating it in the IS-7 gunner/loader positions.

## Original UI selection and validators

**VERIFIED_STATIC:** `Crew.updateTankmen`, line42, excludes members already
seated in another vehicle from its candidate data. The relevant branch is
anchored at432, 441, 447, 450 and456. Consequently, direct cross-vehicle
invocation with an otherwise unselectable seated member is not the native
dropdown scenario accepted by this card. The source-backed path is:

1. Unload the member from its source vehicle into barracks.
2. Select the target through `TankCarousel.vehicleChange(vehInvID)`.
3. Equip that member from the target's original candidate list.

`TankCarousel.vehicleChange`, line114, calls `g_currentVehicle.selectVehicle`
with an integer vehicle inventory ID; anchors0/3/6/9/15. The diagnostic invokes
this original callback and waits for the selected inventory identity and
unchanged native inventory before acting.

`TankmanEquip.__init__`, line126, installs a target `VehicleValidator`,
`ModuleValidator` and `ModuleTypeValidator(TANKMAN)`; anchors142/148/160/
170/182/191/200/203. This checks the target and tankman item through original
plugins. It does not establish historical server ownership, nation, primary
role, source reservation or specialization rules. No cross-specialization
confirmation plugin appears in this processor's pinned constructor.
That narrow observation is not proof that every surrounding original UI path
has no warning or confirmation.

Original callbacks retained from the F audit are `Crew.equipTankman(self,
tmanInvID, slot)`, `Crew.unloadTankman(self, tmanInvID)`,
`Crew.unloadAllTankman(self)`, static `Crew.unloadCrew()` and
`Barracks.unloadTankman(self, invID)`. The unload processor checks barracks
capacity. Occupied-seat replacement and unload have different client checks;
server authorization and resulting capacity remain authoritative.

## Source GUI efficiency is not a combat characteristic

**VERIFIED_STATIC:** `TankmanDescr.efficiencyOnVehicle`, line478, first checks
nation compatibility, retains factor1 for its trained type, and otherwise
distinguishes target class and premium status. For a different type:

| Target relative to trained type | Non-premium | Premium |
| --- | ---: | ---: |
| Same class | 0.75 | 1 |
| Different class | 0.5 | 0.75 |

Factor constants and branches are anchored at39, 51, 54, 63, 84, 90, 96,
102, 111, 117, 123 and126. `TankmanDescr.__paramsOnVehicle`, line882,
anchors0/6/9/18/27/31/34, derives premium status and class intersection from
the original tags. The efficiency method also returns the target's separate
crew-level addition at138/145/148/151.

The public original GUI property `Tankman.efficiencyRoleLevel`, line351,
starts with factor1 and only calls the assigned-vehicle efficiency method if
the tankman is in a tank. Its anchors0/15/27/33/51/57/60/63/64 establish
`round(roleLevel * factor)` using Python2 semantics. Therefore the retained
100% MS-1-trained members have base GUI efficiency100 in barracks or MS-1 and
50 when assigned to IS-7. `Tankman.roleLevel` still reads the descriptor's
base100; `Tankman.descriptor.vehicleTypeID` remains13.

`Tankman.realRoleLevel` and `Vehicle._calcCrewBonuses` include additional
commander, skill, equipment and device effects. This card observes the narrower
base efficiency property separately from persistent state. A displayed base
50 or commander addition does not establish an authoritative cross-training
battle formula, gun handling, reload, visibility or mobility characteristic.
Those characteristics remain **UNKNOWN / NOT_ACCEPTED** here.

## Shared operation and current native boundary

**VERIFIED_STATIC:** assignment still uses CMD105 through `doCmdInt3`.
The declaration is request ID `INT16`, command `INT16`, vehicle inventory ID
`INT64`, seat `INT32`, tankman inventory ID `INT32`: payload20, struct
`<hhqii>`. Unload one uses tankman `-1`; unload all uses seat and tankman `-1`.
Wire method `0x8e`, VAR2 length20 was **OBSERVED** in the earlier P04F native
capture. G run01 independently confirms it for all14 commands below.
CMD157 return-previous-crew, dismissal, retraining and recruitment are not
substituted for this operation.

Vacant native seats use `None`. A member in barracks has category8 `vehicle=-1`.
G projects both complete arrays under category1 `crew`, lengths2 and5, plus
all three category8 vehicle assignments. It sends no replacement descriptor
or dossier for transfers. The independent verifier requires that exact delta,
an empty successful extension, and inventory update before the correlated
success callback for each request.

The generic assignment algorithm consumes validated owned member records and
a source-verified seat-to-primary-role map. Its logic applies to any roster
that the caller has independently verified and authorized; vehicle IDs, MS-1
specific roles and network command IDs do not belong in that algorithm.
This card enables exactly two source-bound native profiles, MS-1 and IS-7.
Synthetic arbitrary-roster tests do not enable other native vehicle profiles.

**PROJECT_POLICY:** profile8, schema `p04g-native-cross-vehicle-crew.v1`, policy
SHA256 `20f7d65c6d360a17f164cb6e4eaa73056a58a793727d4bfbecc1358e1f21969f`.
The server retains the three existing identities, exhausted free quota0,
100% no-skill descriptors and 16-member/barracks bounds. It validates compatible
primary roles and owned available source/target vehicles using the existing
sole writer and shared revision. This is explicit project test policy, not
historical starting economy or a claim about the original server's internals.
Battle admission remains disabled.

## Frozen native acceptance sequence

The accepted predecessor has MS-1 `[1, None]`, empty IS-7 and drivers2/3 in
barracks. Migration is expected to move shared revision15→16 while preserving
crew configuration9. Fourteen accepted commands must produce revision30 and
configuration23 without changing money, ammunition, quota or descriptors.

| Step | Original action | CMD105 layout `[vehicle, seat, tankman]` |
| ---: | --- | --- |
| 1 | Unload MS-1 commander | `[1, 0, -1]` |
| 2 | Seat commander in IS-7 | `[2, 0, 1]` |
| 3 | Seat driver3 in MS-1 | `[1, 1, 3]` |
| 4 | Unload driver3 from MS-1 | `[1, 1, -1]` |
| 5 | Seat driver3 in IS-7 | `[2, 2, 3]` |
| 6 | Replace IS-7 driver3 with driver2 | `[2, 2, 2]` |
| 7 | Unload IS-7 commander | `[2, 0, -1]` |
| 8 | Return commander to MS-1 | `[1, 0, 1]` |
| 9 | Unload IS-7 driver2 | `[2, 2, -1]` |
| 10 | Return driver2 to MS-1 | `[1, 1, 2]` |
| 11 | Seat barracks driver3 in IS-7 | `[2, 2, 3]` |
| 12 | Unload the IS-7 crew | `[2, -1, -1]` |
| 13 | Unload MS-1 commander | `[1, 0, -1]` |
| 14 | Seat commander in IS-7 | `[2, 0, 1]` |

The measured final arrays are MS-1 `[None, 2]` and IS-7
`[1, None, None, None, None]`; driver3 remains in barracks. Fresh login must
read both native vehicle views and the same final member descriptors, balances
and ammunition; run02 satisfies that check.

## Actual native run01 and fresh relogin02

**OBSERVED_NATIVE_717:** the independent verifier ran once after both inputs
were frozen and returned `PASS_NATIVE_CROSS_VEHICLE_CREW_WIRE_RELOGIN`, exit0.
Receipt: `E/independent-native/final01/receipt.json`, SHA256
`f2698b5699e583d7b5bdaee29be912b24904fda1ad834f6efd3f573d2110d00c`.
Verifier source SHA256:
`be1d696c08212114b78e02b377adb2767d741661cfdf375168f9ceb6bc48565c`.
The verifier was not changed to accommodate the live result.

The raw capture contains exactly the14 expected CMD105 operations with request
IDs226 through239 in one gateway session. Each command has exactly its durable
assignment delta, then a successful response with empty extension. Deltas are
101–107 bytes, below the240-byte bound. Shared revision moves16→30 and crew
configuration9→23. Quota0, all three identities, MS-1-trained descriptors,
ammunition and balances remain unchanged.

The original Account request, inventory update and success return are
correlated by request ID, owner identity, revision and ordering with the
immutable ledger and decrypted raw frames. Original Crew callbacks and original
TankCarousel selection occur in the frozen sequence. Every corresponding native
readback reports the correct selected tank and complete crew lists, with
base `efficiencyRoleLevel`100 in barracks/MS-1 and50 in IS-7.

The transfer trace belongs to client PID50404,
`native-runtime01/native-50404-1791905211885.jsonl`; fresh login belongs to
PID35096, `native-runtime02/native-35096-1791905406323.jsonl`. The fresh process
observes vehicle1 and vehicle2 before its final read-only match. All20
non-rate-limit database tables are identical after transfer and after login;
only `game_limits` is excluded from that equality check. File hashes remain
unchanged during immutable read-only inspection:

| Backup | SHA256 |
| --- | --- |
| `native-persistence/before-transfer.sqlite` | `c5a815d6789414f226f39c22cae9d007be4685e6994ae1df4fc554b43899c0c4` |
| `native-persistence/after-transfer.sqlite` | `f3bf244a6a9a1dd602330c8f512fec36ec56532e60f5bd911e56fd3e4612a6e7` |
| `native-persistence/after-relogin.sqlite` | `34318ca1737ac6c86630b92dc1adcefc4140fddbca8bbed99925c81d3d4bd0dc` |

Each install plan binds all33 source modules to current source bytes, actual
CPython2.7.3 compilation metadata, compiled bytes, immutable plan entries and
bundle bytes. Patch ledgers bind the raw plan digest and its settings/files.
The separate `native-persistence/frozen01.json` and `frozen02.json` record
normal native exit0; both `native-install01/restore.json` and
`native-install02/restore.json` report PASS. Service process ownership and
cleanup receipts remain a separate final integration gate rather than a claim
made by the wire verifier.

The actual invocation used these arguments from the owned worktree; choose a
fresh output directory when reproducing because prior receipts cannot be
overwritten:

```powershell
$crewEvidenceRoot = 'local/evidence/20261013-p04g-cross-vehicle-crew-01'
python tools/p04g_native_crew_verify.py `
  --wire "$crewEvidenceRoot/native-wire01" --wire "$crewEvidenceRoot/native-wire02" `
  --trace "$crewEvidenceRoot/native-runtime01/native-50404-1791905211885.jsonl" `
  --trace "$crewEvidenceRoot/native-runtime02/native-35096-1791905406323.jsonl" `
  --install-plan "$crewEvidenceRoot/native-install01/install-plan.json" `
  --install-plan "$crewEvidenceRoot/native-install02/install-plan.json" `
  --private-key local/p04d/runtime/private.pem `
  --before-database "$crewEvidenceRoot/native-persistence/before-transfer.sqlite" `
  --database "$crewEvidenceRoot/native-persistence/after-transfer.sqlite" `
  --relogin-database "$crewEvidenceRoot/native-persistence/after-relogin.sqlite" `
  --original-root C:/WoT_0.9.1_RU_0717_original `
  --out "$crewEvidenceRoot/independent-native/final01"
```

## Verification, remaining limits and rollback

The source API is `audit_sources(original_root: Path) -> dict`. Reproduction:

```powershell
python tools/p04g_crew_source_audit.py --config config/project.local.json --out local/evidence/20261013-p04g-cross-vehicle-crew-01/source-audit/fresh-audit
python -m unittest tests.test_p04g_crew_source_audit tests.test_p04f_crew_source_audit -v
python -m unittest tests.test_p04g_native_crew_verify tests.test_p04f_native_crew_verify -v
```

Source tests actually passed32/32, including source tamper rejection, bounded
input failures and offset semantics. The final combined source and F/G verifier
run passed73/73 with no skips: `E/independent-native/unit03/receipt.json`.
Independent review confirmed rejection of altered migration bundle, predecessor
profile hash and gateway session nonce after strengthening these bindings:
`E/store/verifier-review-02.json`. The independent wire/DB/trace verifier is
`tools/p04g_native_crew_verify.py`. It accepts two wire captures, two native
traces, before/after/relogin immutable SQLite backups, two install plans, the
owned capture key and the pinned original root. It never imports production
transfer/store/projection logic to decide the expected transitions.

The generated verifier fixtures exercise the real D→F→G SQLite migration and
14 transactions, plus adversarial altered evidence. Synthetic packet and
trace producers are labelled unit-only. Current detailed verifier runs and
source hashes live under `E/independent-native/unit*/`; failed earlier fixture
runs remain present. No native acceptance follows from those unit receipts.

**UNKNOWN:** historical original-server validation beyond client bytecode;
direct seated-to-other-vehicle acceptance by that server; cross-specialization
combat characteristics; unobserved surrounding UI warnings. Scoped pixels and
service process cleanup are separate final integration gates. Physical mouse
input and pixel inspection are NOT_RUN within this independent verifier;
separate visual acceptance must identify the PNGs actually inspected.
Skills, paid tariffs, retraining,
dismissal, complete IS-7 staffing and battle admission are outside this card.

The research adds only the G source auditor/tests, independent verifier/tests
and this document. Rollback of these additions is their normal commit revert;
the read-only auditor does not change the original client. Runtime rollback
must follow the plan: restore owned installations using their ledgers, stop
only receipt-owned processes and retain both database generations. An older
writer must not operate on the new schema.

Research acceptance is PASS for the bounded static facts and actual native
wire/state/fresh-client-login result. Root completed the separate pixel and
cleanup gates; the [final card index](../evidence-index/P04G_NATIVE_CROSS_VEHICLE_CREW.md)
binds them to current-build regressions. Next crew card: native recruitment
for every required primary role of the two verified rosters.
