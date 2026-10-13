# P04H — native recruitment for the verified MS-1 and IS-7 rosters

Research date: 2026-10-13. Target: the local, verified RU #717 client only.
Original files remain read-only. Original Python bytecode was treated as bounded
data; it was neither imported nor executed during this static investigation.

## Scope and evidence classification

**VERIFIED_STATIC:** the original combined recruitment command, role and seat
selection, client validators, compact descriptor format, USSR passport catalog,
rank mapping, empty tankman dossier, and the original crew-completeness getter.
The same source-bound roster algorithm covers both current vehicle profiles;
this does not assert that every vehicle in the client is integrated.

**Project decision, explicitly authorized by the owner:** new hires start at
50% with no skills, cost no currency, and consume one project recruitment token.
The migration grants 13 tokens once and caps the owned roster at 16 identities.
Existing IDs 1–3 retain their original 100% descriptors. These are project rules,
not a reconstruction of historical free allowances or prices. Paid recruitment
is deferred and remains unavailable in this card.

**UNKNOWN:** the historical numeric credit/gold prices; the original server's
mapping from tariff index to training percentage; its token grant/reset policy;
and whether a complete crew meets every battle admission rule. Bounds of 50–100
in the descriptor generator do not establish the historical tariff mapping.

**OBSERVED_NATIVE_717:** final runs 02/03 pass the independent native gate:
seven original recruitment callbacks, three original loader transfer callbacks,
exact wire/durable-state correlation, and a fresh process relogin. This observed
compatibility covers the explicit project policy above, not historical prices.

## Source identity and repeatable audit

The reusable auditor is [tools/p04h_crew_source_audit.py](../../tools/p04h_crew_source_audit.py).
Its `audit_sources(original_root: Path) -> dict` result has no absolute host paths,
timestamps, policy grants or runtime side effects. It inherits all G/F selected
source pins and adds eight resources: 35 source pins in total, 29 H bytecode
anchors, and the inherited G/F semantic checks. The target manifest identifies
the build; each selected source is independently checked by size and SHA-256.

Canonical audit SHA-256, using sorted keys, compact separators and ASCII JSON:
`db7179a139d7caabd92aa1026f20e163c5a8583267bb0a1aa95541d248abf585`.

Local receipt:
`local/evidence/20261013-p04h-native-recruitment-01/source-audit/static02/receipt.json`
with file SHA-256
`83bf3d038e2981cdd7de0fc7ee6e6c9c8a9dc9c854dabdbb60d6194b3b6d04c2`.
The pretty receipt file hash differs intentionally from the canonical audit hash.

Key source pins, relative to original `res/scripts/`:

| Resource | Bytes | SHA-256 |
|---|---:|---|
| `client/gui/scaleform/daapi/view/lobby/recruitwindow/recruitwindow.pyc` | 11904 | `ac81a6a0a009fbc856505395f87f76d2a6df303291a7569eb2054f01f802fc41` |
| `client/gui/shared/gui_items/processors/tankman.pyc` | 25844 | `ef86bdc26577dc1d34dcc0c2f97ce230c185e5ae5b5ec41aaef5766224274d21` |
| `client/account_helpers/shop.pyc` | 25626 | `84aa30eb5b1862ac4fbb08557b67ad36dabc9b90cc1d083a29e0e12040127b6d` |
| `client/gui/shared/utils/requesters/shoprequester.pyc` | 27997 | `8680e4bb6255b7e58abaa323b9fca7b4244f5749b9e40d97e3205a0a0b948375` |
| `client/gui/shared/utils/requesters/statsrequesterr.pyc` | 9934 | `85c35d9320332c4ccc282ac17b0786fd08bcd4a9d59275fce0e61d4758a51b34` |
| `common/items/tankmen.pyc` | 24558 | `74f914b1e5e7e574086dd865d87e4cfbf8cace6e60b5e506757eba28ca8bc530` |
| `item_defs/tankmen/ussr.xml` | 45148 | `7277417f9ffac7f742cd6b1bfce02cc7a182558fbdf7db137604323403552cee` |
| `common/dossiers2/custom/layouts.pyc` | 12686 | `233499cb9e4f34f039c46d449a68c117f266f4b6578b4742e3ebba7b646e6471` |
| `common/dossiers2/custom/updaters.pyc` | 33911 | `ea546eaa1e01b57afb431ed6a578a79318643029ba067e45ffb10e1e0a3acf62` |

The receipt records the remaining pins, original line numbers, code SHA-256,
marshal offsets, argument names and instruction offsets. Saved disassembly is
local evidence; it is not published as reconstructed proprietary source.

## Native request and window lifecycle

`RecruitWindow.buyTankman`, original line 294, selects the combined branch when
`slot` is neither `None` nor `-1`. At bytecode offsets 45–72 it calls the original
`__buyAndEquipTankman(vehicle, int(slot), int(studyType))`. The role, nation and
vehicle type dropdown values are not independent command arguments in that
branch. The selected inventory vehicle and seat determine the new role and
training specialization on the authoritative server. The generator calls
`onWindowClose` after the yielded operation, at offsets 121–127.

`Shop.buyAndEquipTankman`, line 741, calls `_doCmdInt4` at offsets 92–122 with:

| Value | Native type |
|---|---|
| request ID | `INT16` |
| command 309 | `INT16` |
| shop cache revision | `INT64` |
| target vehicle inventory ID | `INT32` |
| target seat | `INT32` |
| cost index | `INT32` |

The fixed argument body is 24 bytes. The prior D transport experiment observed
the `0x90` envelope with a two-byte variable length. That prior observation is
not itself the H wire gate. There is no count argument: each request recruits
one identity. The standalone command 303 instead supplies a vehicle compact
type and role index and requires different response extension keys; H does not
claim standalone barracks recruitment.

The combined callback takes `(result_id, error_string, extension)`; the inspected
callbacks do not require keys in the extension. Inventory must be authoritative
before success is delivered. H's independent native verifier must establish the
actual delta-before-callback sequence for every command.

`TankmanRecruitAndEquip.__init__`, line 190, keeps the original target vehicle,
money and free-token validators. It checks whether the target seat is occupied
at offsets 46–76 and enables `BarracksSlotsValidator` for replacements at
155–170. Replacing an occupied seat is a native admitted UI path. The client
does not relocate the old identity by itself: the server must move that identity
to barracks, preserve its descriptor and commit both assignments atomically.

## Tariffs and free-token semantics

`TankmanRecruitAndEquip.__getRecruitPrice`, line 236, reads the selected row, then
returns row 1's credits for index 1, row 2's gold for index 2, and zero currencies
for index 0. `RecruitWindow.__getInitialData`, line 70, reads current and default
school prices from row 1 at offsets 54–88, and academy prices from row 2 at
187–221. It rounds the displayed prices and builds discount information.
Opening the original window therefore requires the tariff row structure even
when the requested operation is free. It does not read a training percentage
from these rows.

The original `Shop` cache supplies `tankmanCost`; `DefaultShopRequester` overlays
defaults on copies of those rows. No historical numeric tariff table was found
in the inspected local sources. Other GUI consumers also inspect `isPremium`;
an incomplete artificial row is not a general historical shop implementation.

The previous source-bound Flash inspection was rechecked against original
`gui/flash/Application.swf` (1258376 bytes, SHA-256
`8c53f7cf510a3b328ee114307613c8f1416beb3360b587b6b158bb7d8ac02b62`)
and `gui/flash/RecruitWindow.swf` (137765 bytes, SHA-256
`9ebbb3ce3e8f2b71f756a01c557bb0721653486de9edc0f617eeaae618d8369f`).
The inspected `onButtonStudyTypeClick` body maps academy to 2, school to 1 and
courses to 0. This establishes the choice labels; it does not establish the
original server's training outcome. The selected bodies and bounded string
search did not prove a 50/75/100 tariff mapping. That negative search result is
limited to the inspected sources, not proof that no such evidence exists.

`StatsRequesterr.freeTankmenLeft`, line 248, reads wire field `freeTMenLeft` with
default zero. Its original docstring describes the number of free tankman
recruitment operations of the current day. This is a daily-operation allowance,
not a lifetime roster cap or barracks vacancy. Its initial amount, reset clock
and timezone remain UNKNOWN. `FreeTankmanValidator._validate`, line 397, requires a truthy
counter and otherwise returns `free_tankmen_limit` (offsets 9–25). The validator
is enabled for cost index 0. It establishes a client-side gate, not how the
original server issued, reset or decremented the counter. H preserves that gate
and supplies its separately documented project quota.

## Roles, descriptors, passports and ranks

The source roster is unchanged from G:

| Vehicle | Native type | Primary roles by seat | Additional roles |
|---|---:|---|---|
| USSR MS-1 | 13 | 0 commander; 1 driver | commander also gunner/radioman/loader |
| USSR IS-7 | 28 | 0 commander; 1 gunner; 2 driver; 3 loader; 4 loader | seat 4 also radioman |

The original role IDs are commander 1, radioman 2, driver 3, gunner 4, loader 5.
`RecruitWindow.updateRoleDropdown`, line 216, deduplicates primary roles in its
dropdown. The combined recruitment route retains the concrete seat index, so
IS-7 seats 3 and 4 still select different positions. A separate radioman hire is
not required for either current roster.

`generateCompactDescr`, line 308, checks creation level 50–100, then writes:

1. `4B`: header `8 + (nation_id << 4)`, trained vehicle type ID, primary role ID,
   and base role level (offsets 67–106).
2. Skill count and skill IDs; a no-skill identity has count 0 and last level 0.
3. `<B4Hi`: flags, first-name ID, surname ID, icon ID, packed rank, free XP
   (offsets 308–337). Female is flag bit 0; premium is bit 1.
4. The embedded dossier bytes (offset 347).

The initial rank index is `(role_level - 50) // 50`; levels remaining are
`50 - ((role_level - 50) % 50)`. The stored word is
`rank_index | (levels_remaining << 5)`. A 50% recruit has index 0, 50 remaining
and word 1600; a 100% recruit has index 1, 50 remaining and word 1601.
The rank ID shown by the client is role-specific: the parser indexes
`roleRanks[role][rank_index]`, rather than treating the packed index as a global
rank ID. At 50%, the USSR rank IDs are commander 2, gunner/driver 1 and
loader/radioman 0. The source readers `_readRanks` and `_readRoleRanks` establish
the XML order and name-to-ID conversion.

The checked USSR normal group is male `normalGroups/men1`, with exact contiguous
ID sets: first names 1–112, surnames 1–1036, icons 1–30. Original passport
generation uses random choices. H's deterministic first/name/icon selection by
new inventory ID is an explicit project allocation rule, not a claim about the
original random generator.

The empty tankman dossier is `<3H>(66, 0, 0)`, hex `420000000000`: version 66 and
two zero block sizes. `DossierBuilder` constructs the header; the tankman
initializer adds no fields. A no-skill descriptor with this dossier has 25
bytes. The source parser and repacker are pinned independently. Final runs 02/03
also observe the original descriptor parser and whole-descriptor repacker agree
on every retained and newly created identity. A separate dossier-object
parse/repack was not invoked and remains NOT_RUN.

`Vehicle.isCrewFull`, line 584, maps members from `vehicle.crew`, tests that no
member is `None`, then returns the crew count. The full return is 2 for MS-1 and
5 for IS-7, not strictly the boolean `True`. Consumers may use its truth value.
This getter confirms seat occupancy; it does not grant battle admission.

## Executed bounded native acceptance

Start from accepted G: MS-1 `[None, 2]`, IS-7 `[1, None, None, None, None]`,
ID 3 in barracks. Recruit through fresh original windows for MS-1 seats 0, 1,
then IS-7 seats 0, 1, 2, 3, 4. Each request uses cost index 0. Expected project
IDs are 4–10, with old IDs 1–3 retained in barracks.

Then exercise the two actual loader identities: unload seat 4, replace seat 3
with ID 10, and place ID 9 in seat 4. The three CMD105 layouts are
`[2, 4, -1]`, `[2, 3, 10]`, `[2, 4, 9]`. Final expected crews are MS-1 `[4, 5]`
and IS-7 `[6, 7, 8, 10, 9]`, with quota 6. Wire frames, exact inventory deltas,
ledger transitions, identity descriptors, original callbacks and both vehicle
views after a fresh relogin agree. Mouse-driven selection is a separate
claim from invoking the original UI callbacks.

The frozen independent verifier returned
`PASS_NATIVE_ROSTER_RECRUITMENT_WIRE_RELOGIN` on final captures 02/03, clients
51048 and 18396. Requests 226–232 are CMD309 (`0x90 VAR2 length24`); requests
233–235 are CMD105 (`0x8e VAR2 length20`). Every exact ledger delta appears on
the wire before its successful callback with an empty extension. Shared revision
advances 31 to 41, crew configuration revision 23 to 33, and quota 13 to 6.
All seven new identities have the independently checked target specialization,
primary role and 50% no-skill descriptor. Old IDs 1–3, balances and ammunition
remain unchanged. Both original `isCrewFull` getters are true after normalization
of their native values 2 and 5. Fresh login observes both vehicle views and all
22 non-rate-limit database tables equal the post-operation snapshot.

Each of the two install plans binds all 34 source files through compiler
metadata, compiled bytes, immutable plan entries and bundle bytes; its patch
ledger binds the raw plan digest. Separate root receipts establish service
processes, executable identity, cleanup and PNG inspection. The independent
verifier does not claim physical pointer input, battle readiness, a full combat
formula, or separate dossier-object parse/repack. The earlier run 01 with a
clipped quota label is retained; final runs use `50%, бесплатно: N`.

Final receipt:
`local/evidence/20261013-p04h-native-recruitment-01/independent-native/final02/receipt.json`
(36612 bytes, SHA-256
`979c15852e84f9b6eb48128a6a916070ebd56208ae0d02c5aebfcd8155ffc172`).
It pins captures, traces, all three immutable database backups, install plans,
the static audit and current implementation sources. Verifier source SHA-256:
`0410159533473ae26d35fee1ae0fece1b975261f129f91778f0f9f72f865076b`.

## Executed checks and rollback

Executed in the owned worktree:

```powershell
python tools/p04h_crew_source_audit.py --config config/project.local.json --out local/evidence/20261013-p04h-native-recruitment-01/source-audit/static02
python -m unittest tests.test_p04h_crew_source_audit tests.test_p04g_crew_source_audit tests.test_p04f_crew_source_audit -v
```

Result: **49 PASS** (17 H, 15 G, 17 F), no skips. The earlier unit01 test-name
error is preserved; unit02 contains the corrected run. Coverage includes each
source's size/hash mutation, opcode semantic mutations, malformed config,
path-independent copied inputs and refusal to overwrite prior receipts.

Independent verifier/source regression: **112 PASS**, no skips, in
`independent-native/unit01/receipt.json`; after the visible-label-only correction,
**22 H verifier tests PASS** in `independent-native/unit02/receipt.json`.
The final whitespace-only cleanup removed four spaces from one empty line;
**22 H verifier tests PASS** again in `independent-native/unit03/receipt.json`,
and `final02` verifies the same immutable native inputs under that exact source.
The final native command used `python -B -X utf8 tools/p04h_native_crew_verify.py`
with `--wire` for `native-wire02` and `native-wire03`, `--trace` for
`native-runtime02/native-51048-1791909191172.jsonl` and
`native-runtime03/native-18396-1791909327868.jsonl`, `--install-plan` for
`native-install02/install-plan.json` and `native-install03/install-plan.json`,
`--before-database native-persistence/before-recruit.sqlite`,
`--database native-persistence/after-recruit02.sqlite`,
`--relogin-database native-persistence/after-relogin03.sqlite`, the owned private
key, the read-only original root, and fresh `--out independent-native/final02`.
All evidence paths in this command are relative to the H evidence directory.

This research changes no original client file, service state or database.
Rollback of the research addition is removal of its new auditor/test/document
and verifier/test in the feature branch; retain local receipts for provenance.
The next research step is the separate historical crew economy/capability audit;
UNKNOWN historical economy is not upgraded by this H acceptance.
