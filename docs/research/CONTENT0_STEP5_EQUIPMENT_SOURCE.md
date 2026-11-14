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

- The initial runtime subset is coated optics, the two repair kits, the two
  first-aid kits and the two extinguishers. Only those rows are offered in the
  original Shop. The native callback selects writable item kinds using the
  projected zero-priced rows and retains original confirmation behavior.
- The catalogue records source filters for all items. The runtime subset has no
  vehicle filter or equipment weight. Source duplicate restrictions are enforced
  at the store, and broader runtime effects will require their own implementation
  before any additional catalogue rows become purchasable.
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
