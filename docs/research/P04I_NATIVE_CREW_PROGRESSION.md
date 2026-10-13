# P04I — original PersonalCase, first skill and dossier evidence

Target: verified RU World of Tanks 0.9.1 #717. Baseline is accepted P04H,
main `1e45eae4e454f196a1842472061d70aeb416651b`. This research supports
PersonalCase and CMD151; it does not accept battle XP awards or skill effects.
The original client tree remains read-only. No original Python code is executed
by the source audit: the bounded Python 2.7 marshal reader returns data records,
and instruction operands are inspected using the pinned CPython 2.7.3 opcode map.

## Classification and reproducible source binding

`tools/p04i_crew_source_audit.py` inherits every H source pin and checks a closed
set of 40 resources. It verifies 42 additional function signatures, complete
code-byte hashes and selected instruction offsets. The report includes original
source filenames, first lines, marshal offsets, argument names and code hashes.
The report contains no local absolute paths, so an exact owned source copy
produces the same canonical digest.

- Static report: `local/evidence/20261013-p04i-native-progression-01/source-audit/static01/receipt.json`.
- Report file SHA256: `102211f86dd5f902f6616cbdf2cb75e8cc18b1f0718593a3aaefa54d4249453f`.
- Canonical report SHA256: `dda516c73da6cda8d838e3366888d4fca58f06bc798fa5de4f8425ec2020fa48`.
- Source status: **VERIFIED_STATIC**. Native CMD151, original dossier object
  readback and fresh-login acceptance are **OBSERVED_NATIVE_717** in the
  measured final 05/06 runs below.

Important original resource pins:

| Resource under `res/scripts/` | Bytes | SHA256 |
| --- | ---: | --- |
| `common/items/tankmen.pyc` | 24558 | `74f914b1e5e7e574086dd865d87e4cfbf8cace6e60b5e506757eba28ca8bc530` |
| `client/gui/shared/gui_items/tankman.pyc` | 15745 | `07645906b7cac95bc482c0e9548b37c598d3ec440752f7f19058688f981fa364` |
| `common/dossiers2/common/dossierdescr.pyc` | 3886 | `7396051744955d9911490d1b73a7fa7cd286915764c07a52e9743ab65a712179` |
| `common/dossiers2/custom/layouts.pyc` | 12686 | `233499cb9e4f34f039c46d449a68c117f266f4b6578b4742e3ebba7b646e6471` |

The machine report is the authoritative complete list, including the original
PersonalCase, inventory, processor, dossier builder and statistics modules.

## First skill without an XP grant

**VERIFIED_STATIC:** a tankman with primary qualification 100, no selected
skills and zero free XP can select a first skill. `TankmanDescr.addSkill`,
original line 594, rejects duplicates, inactive skill names, qualification below
100 and an unfinished previous skill. It appends the selected name at offsets
120–132, sets its level to zero at 136–142, then calls `__levelUpLastSkill`.

`__levelUpLastSkill`, line 906, compares the cost of the next level with existing
free XP and stops when that amount is insufficient. First-skill 0→1 costs
100 XP. Therefore this selection creates one skill at **0%**, leaves free XP
at **0**, and grants nothing. Original `Tankman.hasNewSkill`, line 314, and
`newSkillCount`, line 321, agree: before selection the result is `(1, 0)`;
after selection it is `(0, 0)`. A second skill cannot be selected yet.

The descriptor helper itself does not validate the tankman's role. The native
PersonalCase menu supplies compatible candidates; the authoritative server
must independently enforce the same role rule and all eligibility conditions.

## Skill IDs, current seat and owner exception

The source constructs `SKILL_NAMES` at module offsets 177–363 and enumerates
that tuple into `SKILL_INDICES`. `ACTIVE_SKILLS` is the union of five role sets.

| Category | Names and native indices |
| --- | --- |
| Common | repair 6; fireFighting 7; camouflage 8; brotherhood 9 |
| Commander | tutor 16; eagleEye 17; sixthSense 18; expert 19; universalist 20 |
| Driver | virtuoso 28; smoothDriving 29; badRoadsKing 30; rammingMaster 31; tidyPerson 32 |
| Gunner | gunsmith 37; sniper 38; smoothTurret 39; rancorous 40 |
| Loader | pedant 46; desperado 47; intuition 48 |
| Radio operator | inventor 53; finder 54; retransmitter 55; lastEffort 56 |

Role-specific native names have the corresponding prefix, such as
`commander_tutor` or `driver_smoothDriving`. Common names have no prefix.
`gunner_woodHunter` index 41 exists in the name/perk catalog but is absent from
the original active role sets. Catalog existence does not make it learnable.

`Tankman.__init__`, line 116, starts `combinedRoles` with the descriptor's primary
role. For a seated member it replaces that tuple with the **current assigned
vehicle's** `crewRoles[vehicleSlotIdx]` at offsets 264–329. The trained vehicle
does not determine secondary roles. In the barracks only the primary role
remains. The verified MS-1 commander seat has commander, gunner, radioman and
loader roles; the IS-7 second loader seat has loader and radioman roles.
`PersonalCaseDataProvider.getSkillsData`, line 438, filters groups by this
tuple and excludes already acquired skills.

The original active set has 25 skills. **Project owner exception:** Sixth Sense
index 18 is a free base capability, excluded from learning, regardless of
qualification. The project therefore exposes 24 learnable indices. It must not
encode a fabricated learned 100% skill or consume a skill slot/XP for this
exception. Its actual combat signal remains outside this card's acceptance.

Original GUI activity distinguishes ordinary skills, perks and brotherhood:
ordinary skills report active; non-brotherhood perks require their own level
100; brotherhood reads the vehicle's brotherhood bonus. These GUI properties
do not prove server combat calculations. A historical tooltip mentioning
qualification below 100 is not sufficient evidence for a universal battle rule.

## Native command and descriptor representation

`PersonalCase.addTankmanSkill(invengoryID, skillName)`, original line 208
(including the original argument spelling), creates `TankmanAddSkill` and
yields its request. `TankmanAddSkill`, lines 539/559, adds no extra validator or
confirmation plugin. `Inventory.addTankmanSkill`, line 375, maps the name through
`SKILL_INDICES` then calls `_doCmdInt3` at offsets 99–120:

`[requestID, CMD151, tankmanInventoryID, skillIndex, 0]`.

The network adapter must preserve the established Int3 framing and use the
shared crew/ammunition writer and revision sequence. Native receipt and update
ordering require actual capture; static call shape alone is not wire acceptance.

The compact descriptor retains its four-byte header. Byte 4 is the skill count;
ordered skill indices start at byte 5; the last skill level follows those IDs.
The existing `<B4Hi` suffix starts at `6 + skillCount`; the embedded dossier
starts at `19 + skillCount`. With the preserved six-byte empty dossier the
descriptor length is `25 + skillCount`. Earlier selected skills implicitly
have level 100; only the last level is encoded. Passports, trained type, rank,
free XP and dossier bytes must be checked independently of selected skills.

## Source XP arithmetic

`_makeLevelXpCosts`, line 1228, constructs 101 cumulative values:

`C[0] = 0; C[L] = C[L-1] + int(round(50.0 * pow(100.0, float(L-1)/100)))`.

This is original Python 2 rounding and floating-point arithmetic. The cost
from level `L` to `L+1` is `2**sequence * (C[L+1] - C[L])`: sequence zero is
primary qualification and sequence one is the first additional skill.
`addXP`, line 567, caps stored free XP at 2,000,000,000, fills qualification
first and then the final selected skill. Rank changes follow earned levels.

The implementation's separately recorded evaluation on owned CPython 2.7.3 may
freeze an integer table for the domain; the static audit does not execute the
original helper. Arithmetic tests do not accept battle rewards, and bitwise
floating-point identity across other platforms remains **UNKNOWN**.

## Empty dossier is a real native format

H retained the source-derived six-byte dossier `420000000000`, little-endian
`<3H>(66, 0, 0)`: version 66, two zero-length blocks. The total block contains
only `battlesCount`; the achievements block contains 30 counters.
`StaticSizeBlockBuilder.__init__`, line 30, gives every record an initial zero
at offsets 243–252. Reading an absent block lazily constructs these records.

`ItemsRequester.getTankmanDossier`, line 479, uses the embedded
`tankman.descriptor.dossierCompactDescr`; no separate tankman dossier stream
is required. It also obtains a vehicle dossier for a seated member or the
account dossier for a barracks member. `TankmanDossier.__init__`, line 128,
requires that external object and reads its total and 7×7 statistics.
With zero history: battles count is zero, average XP is zero and estimated
battles to the next level is `None`, displayed as unknown.

`getStats`, line 184, produces two groups: `common` contains `battlesCount`;
`studying` contains `nextSkillXPLeft`, `avgExperience`, `nextSkillBattlesLeft`.
Each packed statistic has `name`, `value`, `extra`, `imageType`, `image`.
Formatted text should be bounded separately from numeric getters.

**Repack distinction:** after lazy reads, `makeCompDescr` materializes loaded
zero records through `StaticDossierBlockDescr.updateDossierCompDescr`, line 194.
Equivalent zero statistics can consequently repack to different bytes. The
native observer must preserve the inventory descriptor's original embedded
bytes while independently checking the parsed/repacked dossier's meaning.
Demanding that the expanded object equal the original six bytes would be an
incorrect acceptance condition. Actual dossier, achievements and statistics
readback passed the native 05/06 gate below: the object repacked to ten bytes,
while the six-byte embedded inventory dossier remained unchanged.

## Remaining boundaries and acceptance

Historical paid prices, retraining/reset parameters and daily free-hire reset
policy remain **UNKNOWN**. Original `StatsRequesterr.freeTankmenLeft` documents
free recruitment operations of the current day; H's finite test allowance is
an explicit project rule. PersonalCase's retraining reader expects real tariff
fields such as `isPremium`; `[{}]` is not adequate for that reader. Unsupported
tariff operations must stay visibly unavailable without inventing prices.

Run the bounded audit and its tests from the owned worktree:

```powershell
python -B -X utf8 tools/p04i_crew_source_audit.py --config config/project.local.json --out local/evidence/20261013-p04i-native-progression-01/source-audit/static01
python -B -X utf8 -m unittest tests.test_p04i_crew_source_audit -v
```

The audit refuses to overwrite an existing receipt; use a fresh output directory
for a later run. Initial focused result: **16 tests PASS**, including all source
mutants, opcode/signature/hash/offset mutants, exact-copy path independence,
configuration bounds and write-once receipt behavior.

The combined F/G/H/I source audit suite passed **65 tests** in
`source-audit/tests01/receipt.json`. The independent wire/state verifier and
its historical F/G/H predecessors passed **82 tests** (19 new I tests) in
`independent-native/unit03/receipt.json`. These fixtures use generated traces
and owned SQLite databases; they establish rejection and invariant checks,
not native acceptance. A separate reviewer ran a valid generated baseline and
11 additional corruptions; all were rejected as expected, recorded in
`store/verifier-review01.json`. Read-only gateway/bridge review found no
actionable issue in `independent-native/boundary-review01.json`; executable
build and service-process evidence are separate gates.

Changed files owned by this source slice are the new auditor and its tests,
the independent native verifier and its tests, and this research document.
Runtime, original and accepted H sources are unchanged by this slice. Rollback
removes/reverts these new tracked files and preserves ignored evidence.
Static acceptance and the bounded native callback/relogin gate are **PASS**.
Physical owner input, battle XP awards and skill combat effects remain outside
this acceptance. Next step for this card: finish the separately owned process,
build, screenshot and cleanup review before integration.

## Native observations

**OBSERVED_NATIVE_717 / PASS**, independent receipt
`local/evidence/20261013-p04i-native-progression-01/independent-native/final02/receipt.json`,
39,094 bytes, SHA256
`ed3265e6a328b136e75b5e994ed332752f8844bdd4bdf9eacec3ff26192a0aef`.
The final verifier source SHA256 is
`f46e2e66cd85860c962f417084950e09138566b4c7631fe64e32980e5a2d3eec`.

Only completed run05 and fresh-login run06 enter this current-source acceptance.
Their client PIDs were 46904 and 27332, with 851 and 459 trace records respectively. The
verifier checked all 35 source/actual CPython 2.7.3 compiled-file/bundle records
in each install plan, raw plan-to-install ledger binding, the current source
audit, captured encrypted traffic and immutable SQLite backups. Gateway
executable/process receipts and screenshot inspection remain separate evidence.

| Request ID | CMD | Original request layout | Observed delta bytes |
| --- | --- | --- | --- |
| 226 | 105 | `[1, 0, 1]` | 104 |
| 227 | 151 | `[1, 16, 0]` | 87 |
| 228 | 105 | `[1, 0, -1]` | 99 |
| 229 | 105 | `[1, 0, 4]` | 97 |
| 230 | 151 | `[2, 29, 0]` | 87 |
| 231 | 151 | `[3, 6, 0]` | 87 |

Both commands used method `0x8e`, a two-byte variable-length envelope with a
20-byte Int3 payload. Every observed inventory update preceded its correlated
successful empty-extension response, in one gateway session and one immutable
ledger chain. Each CMD151 delta contained only the changed member descriptor;
the native client parsed and repacked the resulting 26-byte descriptors.

Shared revision advanced **42→48**, configuration revision **33→39**. IDs 1–3
retained qualification100 and gained respectively `commander_tutor` (16),
`driver_smoothDriving` (29), `repair` (6), each at **0%** with **zero free XP**.
No identity, passport, rank, quota, balance or ammunition was granted or changed.
All ten IDs remained present; quota stayed six. Final MS-1 crew was `[4, 5]`,
IS-7 crew `[6, 7, 8, 10, 9]`, with IDs 1–3 in barracks.

Four original PersonalCase windows were observed in each process. ID1 seated
in MS-1 exposed all four current combined roles before learning; its barracks
window after fresh login exposed only commander skills. IDs2/3 exposed driver
skills. The retained 50% recruit ID4 could not learn. Sixth Sense was excluded
from the learned catalog and shown by the explicit base-capability notice;
the combat signal remains **NOT_IMPLEMENTED**.

All observed dossier objects reported zero battles and average XP. The next
skill XP values were zero before first selection, 100 after selecting a 0%
skill, and 500 for the 50% recruit's next qualification point. Original dossier
statistics and achievements readers ran. The lazy zero dossier repacked to ten
bytes, SHA256 `fc3f4cb958282bbc52f221510efd9171d4b0bee1f385ded864563b90c4547caa`;
the persisted six bytes remained unchanged. No fabricated battle history was
required. Fresh login preserved every checked table except the explicitly
excluded request rate-limit table `game_limits`.

The immutable DB pins are:

- Before learning: `6442553ad7a73e61f19c61604b3c01575b461cec4283e7e7c7108bc31561cbbb`.
- After run05: `211e0ad1d1c5c63f8ddf543a7b68a65f303b535100465ef382531a37e9cb3f0c`.
- After fresh login06: `e2414174e13dc8f99a1d60c3c586de729c2b3c8de6b098a2ba120ba48ca7ebf1`.

Attempts01 and02 remain failed diagnostic evidence. Attempt01 encountered the
original Python list returned by Flash's data-provider bridge, where the first
adapter expected a `.length` property. Attempt02 used a popup lookup without
the required alias criteria, so the observer could not find the existing
PersonalCase window. The client owner made bounded compatibility fixes and
reran regressions before03/04. Failed traces, outcomes and intermediate database
backups were preserved; neither attempt is counted as successful acceptance.

Runs03/04 had already passed the same native checks under the preceding exact
source bytes. Their `independent-native/final01/receipt.json` remains preserved
with SHA256 `2a38eb0f66a8cf04bde23d11507f1b3dbec644ea0aa2999cef5ec217bff431a4`.
The final cleanup removed only one excess EOF LF from the verifier and two
excess EOF CRLFs from the client module; behavior and event schemas did not
change. Unit03 and complete new native runs05/06 were nevertheless performed
to bind the final source bytes to actual compiled files and execution.

Reproduce the independent final gate from the owned worktree (use a fresh
`--out` directory when rerunning):

```powershell
python -B -X utf8 tools/p04i_native_crew_verify.py `
  --wire local/evidence/20261013-p04i-native-progression-01/native-wire05 `
  --wire local/evidence/20261013-p04i-native-progression-01/native-wire06 `
  --trace local/evidence/20261013-p04i-native-progression-01/native-runtime05/native-46904-1791913042632.jsonl `
  --trace local/evidence/20261013-p04i-native-progression-01/native-runtime06/native-27332-1791913153120.jsonl `
  --install-plan local/evidence/20261013-p04i-native-progression-01/native-install05/install-plan.json `
  --install-plan local/evidence/20261013-p04i-native-progression-01/native-install06/install-plan.json `
  --private-key local/p04d/runtime/private.pem `
  --before-database local/evidence/20261013-p04i-native-progression-01/native-persistence/before-learn.sqlite `
  --database local/evidence/20261013-p04i-native-progression-01/native-persistence/after-learn05.sqlite `
  --relogin-database local/evidence/20261013-p04i-native-progression-01/native-persistence/after-relogin06.sqlite `
  --original-root C:/WoT_0.9.1_RU_0717_original `
  --out local/evidence/20261013-p04i-native-progression-01/independent-native/final02
```

This proves the six recorded original callbacks and native persistence on the
owned #717 stand. It does not prove physical owner clicks, all 24 learnable
skills, nonzero-XP progression in a native session, combat effects, historical
paid tariffs, retraining or resets. The complete-crew request remains open.
