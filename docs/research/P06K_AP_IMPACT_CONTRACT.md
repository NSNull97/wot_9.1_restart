# P06K — AP source contract and original marker oracle

## Goal and outcome boundary

Investigate the next dependency between a measured P06J vehicle contact and
an authoritative AP outcome, using the verified WoT 0.9.1 #717 sources.
The source-backed calculation found in this client is a **UI marker predictor**.
It is implemented as a pure, bounded diagnostic. It is not used to decide
penetration, ricochet, damage, effects or any world-state transition.

Plan: [P06K](../plans/P06K_AP_IMPACT_CONTRACT.md). Base accepted merge:
`92ed46e30d4cdca824437a282a0916b9c987ad5b` (P06J). Evidence directory:
`local/evidence/20261010-p06k-ap-impact-contract-01/`.

## VERIFIED source contract

Bounded static inspection covered 1081 original client/common `.pyc` files,
9,083,662 bytes, with 93 selected records from 45 modules. Fourteen specific
methods and their input resources were pinned. This does not establish that
no implementation exists in native code or unavailable server code.

`original-client-ap-contract.json` is 19,274 bytes, SHA-256
`62418541798cd06b12087c63618e9ca035735faf7714bd105521f6a65a340acb`.
It retains original paths, source hashes, bytecode offsets and classification
of unknowns; original bytecode/resource dumps stay in ignored local evidence.

The marker chain is:

1. `ModelHitTester.localHitTest` delegates the geometric query to native BSP.
2. `Vehicle.collideSegment` returns distance, hitAngleCos and raw material
   armor. A missing material becomes zero only in this client-side result.
3. `ProjectileMover.collideEntities` carries these values to the gun marker.
4. `_FlashGunMarker.update` selects `normal` for no target, allies or dead
   vehicles. For a live enemy it passes only hit point and raw armor to
   `_changeColor`; the contact angle is not used.
5. `_changeColor` reads the selected shot and own vehicle position, computes
   nominal power/score, and calls the marker color callback.

`res/scripts/client/AvatarInputHandler/control_modes.pyc` SHA-256:
`d13714e51ecf56586565b382caa1ca9702911125644269bb3c6096c5ac75e6c5`.
The original method begins at source line 2772. Its raw `co_code` SHA is
`928595f683fa01b6f07fd27bf209187f3132ca51c0c427f3464e59d8830d14a3`;
the canonical static record SHA is
`f1d404c952ae6baa7f5dc2356b326f5ea1f438028205c43e92ba94d5226758c7`.
These hash different representations and must not be interchanged.

For stock MS-1 gun5892/AP2570, the nominal pair is 34/27 and maximum distance
is 720 m. The marker uses the native vector length from own vehicle position
to the supplied point, not muzzle distance or integrated projectile travel.
Binary64 operation order is preserved:

```text
d <= 100:       P = 34
100 < d < 720:  P = max(0, 34 + (27 - 34) * (d - 100) / 400)
d >= 720:      P = 0
score = 100 + (armor - P) / P * 100, if P > 0; otherwise 1000
score >= 150: not_pierced
90 < score < 150: little_pierced
otherwise: great_pierced
```

There is **no clamp at 500 m**. P(500)=27; P(600)=25.25; just below 720 the
limit is 23.15; at 720 it is zero. Algebraically rewriting the score changes
floating-point boundary behavior. UI names are preserved for correlation and
are explicitly not server outcomes or probabilities.

The source also confirms caliber37, armor damage30, device damage50 and
two loader randomization defaults0.25. The latter do not establish a RNG
distribution, draw order or server rounding. AP normalizationAngle and
ricochetAngle are absent from the release resource; the loader reads these
only under `!IS_CLIENT || IS_DEVELOPMENT`. Hull/turret armorHomogenization is
also absent from the stock resource and read by a server-only branch.

## Implementation and actual native observations

- `server/gateway/src/shared/client_marker.rs`: typed stock-only diagnostic,
  finite/range validation, exact arithmetic and UI-label enum. No angle/normal
  input, no generic unsupported shell constructor. Absent armor is rejected;
  present armor0 remains distinct. P06J MaterialFacts are untouched.
- `server/gateway/src/shared/mod.rs`: module declaration only.
- `client_patch/collision_oracle.py`: bounded passive original-method probe.
  It checks method identity, calls original `im_func` with a local callback
  receiver, and records 60 cases. No constructor, GUI update, global patch,
  player/descriptor mutation, shot command or state write is introduced.
- `tools/client_marker_oracle.py`, its negative tests and native-derived Rust
  fixture validate provenance, unchanged inputs and observed labels.

The probe was run in both approved native copies on the accepted P06J gateway
and accepted physics pool, with the unchanged P06J contact bundle. Both
clients produced `PASS_NATIVE_CALLS`, 60 cases each. Distances include
0/100/100.01/300/500/600/719.99/720/720.01 with actual native measured values;
separate samples straddle both score thresholds. Own position and selected
shot were unchanged across the synchronous calls. Only labels are observed
from the original method; intermediate numeric power is not a native output.
These are original-method measurements, not a visual UI color acceptance.

Detailed final validation, exact artifact hashes and commit identities are
recorded in `summary.json` and `merge-proof.json` in the evidence directory.
Diagnostic clients and server were stopped after collection. The passive
patch is restored by each install ledger before another prepare operation.

## Native impact delivery contract (static, not sent)

`native-impact-effect-contract.json` SHA-256:
`ac61aa82f73a2f9747d4a1d6cfad528b697d42cfcf284bb0d4bdcf28923b6175`.
Ten source/table pins were independently rechecked.

`Vehicle.showDamageFromShot` exposed index7/message0x42 takes attackerID,
ARRAY<UINT64> points and UINT8 effectsIndex. Each packed point contains an
outcome byte, component byte and six bytes for a local segment in the
component bounding box. The decoder expands the segment and performs its own
native hit test. Outcomes0..4 mean ricochet, resisted armor, pierced without
damage, pierced, critical hit. **There is no neutral contact code.**

Sending pierced-without-damage still asserts penetration. Substituting a
metal `explodeProjectile` is also not neutral: it takes the world/terrain
effect path, can substitute water/position and signal PLAYER_SHOT_MISSED.
Encoder rounding, actual callback delivery and rendered effects are NOT_RUN.
The accepted `stopTracer` contact path is unchanged by P06K.

## Historical primary-source boundaries

The official 9.3 announcement describes continued flight after ricochet as a
new behavior; the previous shell disappeared. Importing modern continuing
ricochet behavior into 0.9.1 would therefore require contrary version-specific
evidence. [Official 9.3 announcement](https://worldoftanks.eu/en/news/general-news/version-93-announcement/).

Official 8.6 notes change APCR normalization from5 to2 degrees. This does not
establish the AP value. HEAT80 in those notes was superseded by85 in final
8.9 notes, which also remove the HEAT three-caliber ricochet exception.
These HEAT/APCR rules must not be applied to the stock AP shot.
[8.6 notes](https://worldoftanks.eu/it/content/docs/release_notes/release-notes-86/),
[8.9 final notes](https://worldoftanks.com/en/content/docs/release_notes/89-update-notes/).

A dated 2013 official article explains armor angles and effective thickness,
but not the complete server execution order or RNG.
[Chieftain: Armor Angles](https://worldoftanks.com/en/news/history/The_Chieftains_Guide_Armor_Angles/).

Web evidence is explicitly limited: the search index exposed these official
historical texts; several direct opens returned bot challenges. No original
historical HTML hash or assurance against later edits is claimed. Receipt:
`historical-ap-primary-sources.json`, SHA-256
`03f84554ea8c77c9b8c18e068a76c04e327efe7d68927cc009db8da0b181c34c`.

## Commands, limits and rollback

Source inspection commands and receipts live alongside `research_ap_contract.py`
and `compile_contract_receipt.py` in the evidence directory. Native preparation:

```powershell
python -B -X utf8 local/evidence/20261010-p06k-ap-impact-contract-01/prepare_stand.py --slot a --run oracle01
python -B -X utf8 local/evidence/20261010-p06k-ap-impact-contract-01/prepare_stand.py --slot b --run oracle01
python -B -X utf8 local/evidence/20261010-p06k-ap-impact-contract-01/start_stand.py server --run oracle01 --profile integrated-lab --build gateway-integrated-world-p06j-01 --pool D:\WoT_9.1_Server\local\build\server\physics-integrated-lane-01\pool.json --geometry D:\WoT_9.1_Server\local\evidence\20261010-p06j-contact-materials-01\ms1-contact.json
python -B -X utf8 local/evidence/20261010-p06k-ap-impact-contract-01/start_stand.py a --run oracle01
python -B -X utf8 local/evidence/20261010-p06k-ap-impact-contract-01/start_stand.py b --run oracle01
```

Run IDs and output directories must be fresh; restore prior ledgers first
while the owned clients are closed. Exact invocations for audit/build/tests
are retained in the summary and command receipts.

**UNKNOWN/NOT_RUN for the subsequent authoritative resolver:** AP numeric
angles and 2×/3× boundaries/order, homogenization, server range semantics,
RNG distribution/order, layer traversal and damage rounding. No penetration,
HP/module/crew damage, projectile terrain/obstacle collision, native impact
effects or new owner gameplay acceptance is claimed. Material contact and
tracer stop remain the accepted P06J behavior; this diagnostic cannot close
P06D damage acceptance.

Rollback: revert the P06K merge; restore `install-a-oracle01` and
`install-b-oracle01` through `tools/interactive_client.py rollback --out ...`
while clients are closed. Continue with accepted `gateway-integrated-world-p06j-01`,
`ms1-contact.json` and `physics-integrated-lane-01/pool.json`. Original client,
canonical service and persistent account state were not mutation targets.

**One next step:** close the explicit historical AP resolver rule table
(including unknowns above) before emitting a real outcome and choosing its
native impact effect. Further marker-color work does not close that gate.
