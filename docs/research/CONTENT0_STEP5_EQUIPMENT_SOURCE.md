# CONTENT-0 step 5 equipment source receipt

The original RU 0.9.1 #717 client was read as data from the configured original
root. The runtime never loads client bytecode on the server. The generated
catalogue records all 43 optional devices and 18 consumables, including ordered
source include/exclude clauses, effect properties and historical prices. Its
sources are identified by size and SHA-256 in the catalogue.

```powershell
python -B -X utf8 tools/content0_equipment_catalog.py check --client C:/WoT_0.9.1_RU_0717_original
```

Verified catalogue SHA-256
`2c38786202ef015ae0e3a645719b869fe1e01421b7ec9521e2af93332f4b76af`.

## VERIFIED source facts

| Source | Function and bytecode offsets | Argument and data layout |
| --- | --- | --- |
| `common/accountcommands.pyc`, `ba439d8…` | Module stores at 121, 133, 157, 277 and 313 | Commands 102, 104, 108, 302 and 308 |
| `client/account_helpers/inventory.pyc`, `3d17842…` | `Inventory.__equipOptionDevice_onShopSynced`, 80–119 | 102 int-array `[shopRev, vehInvID, deviceCDOrZero, slot, int(isPaidRemoval)]` |
| Same | `Inventory.equipEquipments`, 127–133 | 104 int-array `[vehInvID, cdOrZero, cdOrZero, cdOrZero]` |
| Same | `Inventory.__setAndFillLayouts_onShopSynced`, 86–224 | 108 int-array `[shopRev, vehInvID, shellIntCount, shellData…, equipmentIntCount, equipmentData…]` |
| `client/account_helpers/shop.pyc`, `84aa30e…` | `Shop.buy`, 151–175 and `Shop.buyAndEquipItem`, 89–128 | 302 int4 `[shopRev, cd, count, goldForCredits]`. 308 int-array `[shopRev, cd, vehInvID, slot, isPaidRemoval, gunCD]` |
| `client/gui/scaleform/daapi/view/lobby/hangar/technicalmaintenance.pyc`, `1193382…` | `TechnicalMaintenance.fillVehicle`, 126–280 | Consumable part contains three `(cd, 1)` or `(0, 0)` pairs. Negative CD indicates buying a gold item with credits |
| `client/gui/shared/gui_items/vehicle.pyc`, `ec78e36…` | `Vehicle.__init__` and `Vehicle._parseEqs`, 34–99 | `inventory[1].eqs` and `eqsLayout` are raw compact ID slot lists read separately |
| `common/items/vehicles.pyc`, `805240e…` | `VehicleDescr.makeCompactDescr`, 175–294 and `_combineVehicleCompactDescr`, 146–164 | Shift mask left per slot. Write each occupied raw `device.id[1]` as LE uint16 in slot order. Slots 0, 1 and 2 set mask bits 2, 1 and 0 |
| Same | `VehicleDescr.__initFromCompactDescr`, 450–543 | Reverse loop starts at slot 2, reads low flag bit and reads device words from the end |
| `client/gui/shared/gui_items/processors/module.pyc`, `9ed4b67…` | `OptDeviceInstaller.__init__`, 243–342 and `_request`, 0–81 | Distinct preservation and destruction dialogs for a non-removable device, transmitted via the paid-removal flag |
| `client/gui/scaleform/daapi/view/lobby/hangar/ammunitionpanel.pyc`, `54d139d…` | `AmmunitionPanel.setVehicleModule`, 317, 347, 505 | Purchase from the original UI uses the Shop buyer before the native installer when the item is absent from stock |

Examples of equipped descriptor suffixes replacing the plain descriptor's
final `00`. Coated optics raw item ID is 5 and compact ID is 1529.

| Slot | Suffix |
| --- | --- |
| 0 | `04 05 00` |
| 1 | `02 05 00` |
| 2 | `01 05 00` |

## Project policy and coverage

- The first stand offered coated optics, two repair kits, two first-aid kits
  and two extinguishers. The weighted candidate adds the six rows below. The
  native callback uses projected zero-priced rows and retains original
  confirmation behavior.
- The catalogue records source vehicle filters. Source duplicate restrictions
  are enforced at the store.
- Four unsupported fuel items, `lendLeaseOil`, `gasoline100`, `gasoline105` and
  `qualityOil`, have the separate nested `incompatibleTags/installed=fuel` rule in
  the pinned source. The current catalogue receipt omits this nested equipment
  conflict. It requires a versioned receipt extension if those items are enabled.
- Separate current and preferred consumable slots let settlement clear only
  units used while retaining the maintenance selection. Unloading returns unused
  consumables to shared stock. Destroying a non-removable device clears it,
  while demounting it preserves it at the stand's configured zero cost.
- The original client and full wire transport must still be exercised for
  native acceptance. Bytecode inspection and repository tests cover source
  contracts and server transactions.

## Hangar parameter display in #717

VERIFIED in `gui/shared/utils/parameterscache.pyc` (SHA-256
`e5aa176b58c059d17287b7cde2f41786bd3bc87d57d4431a5c3b275bf84925a4`).
`getVehicleParameters` takes the shot rate from the gun at offsets 324–338.
`_getShotsPerMinute` uses the raw reload time and clip/burst properties. View
range reads the turret's `circularVisionRadius` at offsets 676–689, and aiming
time reads the gun at offsets 725–747. These paths do not evaluate the assigned
crew or specify a fixed crew level. Whether the source values were calibrated
to any specific crew level is UNKNOWN. Other rows can read computed descriptor
properties, for example mass from `vd.physics`.

## Weighted equipment

VERIFIED against the same `optional_devices.xml` source and existing manifest.

| Item subtype | Compact ID | Added mass | Source effect |
| --- | ---: | ---: | --- |
| Toolbox | 249 | 100 kg | `repairSpeedFactor` × 1.25 |
| Medium caliber tank rammer | 5625 | 200 kg | `gunReloadTimeFactor` × 0.90 |
| Large caliber tank rammer | 5881 | 400 kg | `gunReloadTimeFactor` × 0.90 |
| Medium caliber howitzer rammer | 6137 | 300 kg | `gunReloadTimeFactor` × 0.90 |
| Large caliber howitzer rammer | 6393 | 500 kg | `gunReloadTimeFactor` × 0.90 |
| Enhanced gun laying drive | 6649 | 100 kg | `gunAimingTimeFactor` × 0.91 |

`artefacts._VehicleFilter.checkCompatibility` checks exclusions first at
bytecode offsets 0–54, then includes at 58–122. `_matchSubfilter` checks the
nation at 41–80, any matching vehicle tag at 122–168, then minimum and maximum
tiers at 174–267. Separate `<include>` entries are alternatives. The four
rammers have no individual component filters, so every mounted build inherits
its vehicle type's eligibility. Medium and large tank rammers require their
respective `*TankRammer_user` tags. Medium and large SPG rammers require their
respective `*HowitzerRammer_user` tags or an American SPG of tier ≤6 or 8–10,
respectively. A scan of all 374 original vehicle types found 157, 74, 37 and 13
matches in that order and zero overlaps.

`VehicleDescr.mayInstallComponent` recalculates optional-device compatibility
and weight at offsets 684–736 before approving a module replacement. The server
retains compatible equipment and refuses a replacement that would exceed the
new chassis's weight allowance. Every stored configuration must already fit, so
the client's alternative non-worsening overload condition cannot occur in this
slice. The mass check uses integer grams and the existing module catalogue.
For example, the stock MS-1 has 199 kg reserve, allowing either a toolbox or
laying drive. The two together require an upgraded suspension. The IS-7 takes
the large tank rammer and enhanced laying drive on its stock suspension.

## Ventilation and rations

VERIFIED against the pinned `optional_devices.xml` and `equipments.xml`.
Ventilation uses `StaticAdditiveDevice` on `miscAttrs/crewLevelIncrease`.
The three filters below had 87, 120 and 95 matches respectively across the 374
entries in the seven native vehicle lists, with no overlapping classes.

| Source subtype | Compact ID | Qualification | Added mass | Included tags (any) | Excluded tags (any) |
| --- | ---: | ---: | ---: | --- | --- |
| `improvedVentilation_class1` | 4601 | +5 | 100 kg | `lightTank improvedVentilation_class1_user` | `noImprovedVentilation` |
| `improvedVentilation_class2` | 4857 | +5 | 150 kg | `mediumTank mediumAT-SPG improvedVentilation_class2_user` | `noImprovedVentilation lightTankArtefacts_User` |
| `improvedVentilation_class3` | 5113 | +5 | 200 kg | `heavyTank heavyAT-SPG improvedVentilation_class3_user` | `noImprovedVentilation` |

Each ration is a zero-mass consumable tagged `stimulator`, filtered to its
source nation. `Stimulator._readConfig` reads `crewLevelIncrease` at offsets
0–24 in `common/items/artefacts.pyc` (SHA-256 `aedbfc161d7f0b2b78f376540811a0b4113736757982d03bceb4e6f4cccac49c`).

| Source subtype | Compact ID | Nation | Qualification |
| --- | ---: | --- | ---: |
| `chocolate` | 2555 | Germany | +10 |
| `ration` | 3067 | USSR | +10 |
| `hotCoffee` | 3579 | France | +10 |
| `ration_china` | 4091 | China | +10 |
| `ration_uk` | 4603 | UK | +10 |
| `ration_japan` | 4859 | Japan | +10 |
| `cocacola` | 25851 | USA | +10 |

All seven `*/always` strings in pinned `res/text/lc_messages/artefacts.mo`
(SHA-256 `87e24105b2794fa64363ee72ff0554e38173c94c4df1be485c83a2a94f690c8a`)
describe a +10 bonus and one-battle use. Each `*/onUse` text is empty.
`PlayerAvatar.onEquipmentButtonPressed` exits at offsets 126–158 for a
`stimulator` or `fuel` tag, before sending `ACTIVATE_EQUIPMENT`, in
`client/avatar.pyc` (SHA-256 `c13cd58a4c5d766dfd3c5f47ae7be50c962aee6c7f8cf25b4341322381f21e0e`).
The official 9.0 manual shows Extra Combat Rations active for the course of
the battle (p. 26). It also says automatic and battle-long consumables are
displayed without an item count (p. 30). [Wargaming 9.0 manual](https://worldoftanks.eu/dcont/fb/document/world_of_tanks_oyun_klavuzu_tr_web_9_0.pdf#page=30)

The exact original server tick and HUD packet values are UNKNOWN. The project
projects the bonus during setup and applies it automatically in combat. It
records one spent slot when combat begins and clears that slot at settlement.
A reservation canceled before combat does not consume a ration. The battle
HUD keeps the loaded ration icon while the effect lasts. A quantity of zero
would show its spent state:
`BattleConsumablesPanel.swf` (SHA-256 `a425cf4f53f867f1f86cb2b3f2de1741a541dee05916d2b567d11d578a641fb7`)
sets renderer `quantity` at expanded body offsets 16839–16882. In
`BattleArtefactButtons.swf` (SHA-256 `a42fc15f29f1b0db8efbf6e7344ab3103bc0ad9715d102166e894ae406c1ccaf`),
zero quantity calls `setEmpty(true)` at offsets 165747–165789 or 166614–166655
on initialization. The icon remains visible at 166756–166805 and receives a
color transform at 184591–184813. The automatic slot class has an empty
`handleClick` at 187466. The icon presentation and settlement state are tracked
independently by the project.

### Crew qualification and combat calibration

VERIFIED in the original garage bytecode. `Vehicle._calcCrewBonuses` in
`client/gui/shared/gui_items/vehicle.pyc` (`ec78e36…`) sums ration effects at
offsets 19–72 and reads ventilation at 73–92. It rounds the commander's
trained qualification including ventilation at 336–380, then adds food and any
fully trained crew-wide Brotherhood bonus before dividing by 10 and rounding
at 390–434. `Tankman.realRoleLevel` in `client/gui/shared/gui_items/tankman.pyc`
(`07645906…`) suppresses the commander's self-bonus at offsets 43–73 and sums
qualification and bonuses at 139–158. `TankmanDescr.efficiencyOnVehicle` in
`common/items/tankmen.pyc` (`74f914b1…`) supplies the training factor and
ventilation addition at offsets 39–151. For a fully trained separate-seat crew
with no perks, both items give commander 115 and other crew 127; the original
GUI rounds 11.5 to 12. See [the P04B crew audit](P04B_CREW_EQUIPMENT_SNAPSHOT.md).

INFERRED combat calibration. The static scan of 1,081 `common` and `client`
`.pyc` files parsed all files and found no implementation tying the effective
qualification to gun timing or spotting distance. The scan checked relevant
attribute names and the candidate curve constants. It cannot rule out an
equivalent expression or implementation in the unavailable original server.
The period Wargaming manual links the gunner to aiming speed, the loader to
reload and the commander to sight. A 2012 player report compared the public
curve against in-game reload timer results across training levels and bonuses.
Neither establishes the original server formula for all three characteristics
on this specific build. [Wargaming 9.0 manual, p. 58](https://worldoftanks.eu/dcont/fb/document/world_of_tanks_oyun_klavuzu_tr_web_9_0.pdf#page=58) ·
[2012 primary measurement report](https://whrl.pl/RdcrrN)

The stand uses `Q(level) = 0.5 + 0.00375 × level`, normalized to the fully
trained healthy reference for the mounted seats (100 for the commander, 110
for a separate crew member receiving the commander's bonus). The gunner and
loader time factors are `Q(reference) / Q(effective)`, and the commander's range
factor is `Q(effective) / Q(reference)`. This calibration preserves the previous
stand's effective timings at the project reference; the source XML values alone
cannot establish the historical reference. Rammer, gun laying drive and coated
optics compose with their respective factors. Existing wounded-crew and
damaged-module penalties still apply through the established damage paths.
These checks concern mounted qualification and rations/ventilation; the wider
combat effect of perks and other role-dependent parameters has separate scope.

### KV-1S test configuration

The pinned `res/scripts/item_defs/vehicles/ussr/kv-1s.xml` (SHA-256
`16cd67ba2f6297c74ee101d4edb819badbf9b76177f00cb9340ae4b315221994`) gives
the KV1S_mod_43 turret 330 m view range (320 m for KV1S_mod_42) and a separate
seat for each role. The 122 mm D-25T on that turret has 16.0 s reload and
3.4 s nominal aiming time. The `ussr-KV-1s--84818961` assembly weighs 43,970 kg;
its KV-1s_bis chassis limit is 48,200 kg. Rammer, gun laying drive and class 3
ventilation bring mass to 44,670 kg with 3,530 kg reserve.

Calculated stand expectations for a healthy, correctly trained 100% crew with
rammer and gun laying drive retained, no perk bonus and no optics. These values
are test expectations and do not represent measurements from a native battle.

| Additional equipment and consumable | Commander / gunner / loader | Full reload | Nominal aim time | View range |
| --- | ---: | ---: | ---: | ---: |
| None | 100 / 110 / 110 | 14.40 s | 3.094 s | 330.0 m |
| Class 3 ventilation | 105 / 116 / 116 | 14.05 s | 3.020 s | 337.1 m |
| Soviet ration | 110 / 121 / 121 | 13.78 s | 2.960 s | 344.1 m |
| Class 3 ventilation and Soviet ration | 115 / 127 / 127 | 13.46 s | 2.892 s | 351.2 m |

## Stabilizers, stereoscope and module protection

The pinned `optional_devices.xml` defines these effects and installation filters.

| Item | Compact ID | Mass added | Source effect and filter |
| --- | ---: | ---: | --- |
| Vertical stabilizer Mk1 | 7929 | 100 kg | `additiveShotDispersionFactor` × 0.8, `aimingStabilizer_Mk1_user` |
| Vertical stabilizer Mk2 | 8185 | 200 kg | `additiveShotDispersionFactor` × 0.8, `aimingStabilizer_Mk2_user` |
| Stereoscope | 1273 | 50 kg | 3 s stationary, `circularVisionRadiusFactor` × 1.25 |
| Wet ammo rack, classes 1 and 2 | 6905 / 7161 | 1% of base assembled mass | `ammoBayHealthFactor` × 1.5, corresponding `wetCombatPack_class*_user` |
| Cyclone filter | 7673 | 10 kg | `engineHealthFactor` × 1.5, USSR except `lendLeaseVehicle` |
| CO₂ fuel tanks | 7417 | 50 kg | `fuelTankHealthFactor` × 1.5, tier VI and above |

VERIFIED in `Avatar.getOwnVehicleShotDispersionAngle`: the stabilizer multiplies
the sum of the squared motion, rotation and post-shot penalties by `0.8²` before
the square root. The fixed stationary term stays one. The native descriptor
already carries the device. `updateTargetingInfo` therefore sends unscaled
movement coefficients so the client does not apply the effect twice. A scan of
374 vehicle types found 52 Mk1 and 37 Mk2 matches with no overlap. The IS-7 can
take Mk2. The KV-1S has neither of the stabilizer tags.

The stereoscope drive condition uses the committed pose of the hull. Rotation
of the turret alone is excluded. The [8.5 release notes](https://worldoftanks.com/en/news/general-news/85-update-notes/)
explicitly document retaining stereoscope and camouflage net effects when a
damaged track prevents movement. The [2014 official manual](https://worldoftanks.eu/dcont/fb/document/world_of_tanks_game_manual_fr_web_8_11_3.pdf)
shows ×1.25 while stationary, with a 500 m equipment ceiling. The existing
server spotting cap is measured separately. Exact historical movement
tolerances and telescope/optics interaction are not exposed by #717. The stand
uses a 5 cm translation limit from the stationary anchor, a 0.01 rad hull
orientation limit and a 0.1 m/s speed limit to reject solver drift. It uses the
stronger active range when both devices are fitted. The existing direct spotting
limit is 445 m. The owner's equipment HUD is notified with the original
`Avatar.updateVehicleOptionalDeviceStatus` raw ID 4 and a boolean. Avatar slot
`0x3d` follows the inherited method table of the pinned client.

The camouflage net sources establish an activation delay of 3 s, 100 kg and a
stationary effect. The [8.6 release notes](https://worldoftanks.com/en/content/docs/release_notes/86-update-notes-archive/)
confirm a fixed class-dependent bonus. The #717 `camouflageNetBonus` reader
has no corresponding value in the pinned vehicle XML. The existing spotting
law has no camouflage rating for the target. Net activation can follow the
same stationary state after a target camouflage model and its data are bound.

Module HP multipliers are source values. Whole HP rounds half up in the
stand and `maxRegenHealth` remains source-pinned. Original server rounding and
regeneration treatment are unknown. The frozen equipment sets maxima in the
live damage state and in the result validators, including cancellation. The
wet rack uses original `VehicleDescr.__computeWeight` order: 1% of the assembled
mass before adding the fixed weights of other equipment.

## Spall liners and passive first-aid protection

VERIFIED against `optional_devices.xml` and `AntifragmentationLining.updateVehicleDescrAttrs`
in `common/items/artefacts.pyc` (SHA-256
`aedbfc161d7f0b2b78f376540811a0b4113736757982d03bceb4e6f4cccac49c`). At offsets
9–27 the descriptor multiplies `antifragmentationLiningFactor` by the XML
factor. At offsets 28–50 it multiplies `crewChanceToHitFactor` by one minus
`increaseCrewChanceToEvadeHit`.

| Spall liner | Compact ID | Added mass | Absorption factor | Crew hit chance factor |
| --- | ---: | ---: | ---: | ---: |
| Light | 505 | 250 kg | 1.20 | 0.80 |
| Medium | 761 | 500 kg | 1.25 | 0.75 |
| Heavy | 1017 | 1,000 kg | 1.30 | 0.70 |
| Superheavy | 11001 | 1,500 kg | 1.50 | 0.50 |

The #717 descriptions identify absorption for explosions and ramming. The
[official 8.8 release notes](https://worldoftanks.eu/en/content/docs/release_notes/release-notes-88/)
independently confirm the four reductions in crew wound chance. The original
server's application of the absorption multiplier to a ramming collision is
UNKNOWN. The project currently uses a contact-energy law in `tank_ram.rs`.
The explosion penalty can use the material's `useAntifragmentationLining` bit
for the applicable armor term in direct non-penetration and splash. Splash
simulation and its independent trace validator must agree on that input.

The #717 Russian tooltip `largeMedkit/always` and the
[official 8.8 manual, p. 52](https://worldoftanks.eu/dcont/fb/updated_manuals/world_of_tanks_game_manual_en_eu_web_8_8.pdf#page=52)
both specify +15% crew wound protection. `Repairkit._readConfig` offsets 21–42
read the XML `bonusValue` of 0.30 as a fraction. No battle consumer of that
property exists in the scanned original `common` or `client` bytecode. The
exact original server conversion, combination with spall lining and duration
after use are UNKNOWN. The stand implements the documented relative crew
chance factor 0.85 on penetrating projectile and HE/HESH seat rolls. It uses
the frozen loadout so the effect lasts throughout the battle, including after
active healing. That lifetime is a project decision. Spall liner integration
remains pending.
