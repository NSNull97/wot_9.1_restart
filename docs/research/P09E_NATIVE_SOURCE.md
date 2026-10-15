# P09E — original #717 research and acquisition boundary

Date: 2026-10-13. Accepted base: `626867c758c32b189a77a7a7a2fe9ff29837e11b`.
Branch: `codex/p09e-tank-module-research`. Native acceptance: **NOT_RUN**.

## Scope and provenance

This report covers the source contract, independently authored descriptor
encoder, reversible XP display policy, and opt-in gateway adapter. Domain
catalog/import, ownership, compatibility, transaction and projection work is
implemented separately in `tools/p09e_research_*.py`. Reading a source or passing
an encoder test does not prove an original client callback, Flash screen or
network exchange works.

The only original is `C:\WoT_0.9.1_RU_0717_original`; it was read without imports,
execution or modification. Source bytecode was decoded as bounded static data
by the existing `py27_static` parser. Packed `Account.def` was decoded by the
bounded packed-XML reader. Original bytecode/resources are not exported into
the repository. All writes, dependency copies and builds used the managed
C: worktree. No root D: checkout file, client installation, live database or
running server process was changed by this subtask.

`tools/p09e_native_research_audit.py` pins size and SHA-256 for 16 original files;
`local/evidence/20261013-p09e-research-01/native-source/source-audit03.json`
records the pins, function source-line metadata and checked bytecode offsets.
Earlier audit01/02 receipts retain their smaller 14-file scope. Those earlier
receipts do not establish the later elite checks.

## VERIFIED: request contract

Source paths below are relative to original `res/scripts/`. Source line numbers
are the code object's historical `co_firstlineno`; byte offsets are in the
code object's instruction stream, not offsets in the `.pyc` container.

| Command | Native helper and source line | Ordered arguments after command |
| --- | --- | --- |
| 101 equip | `client/account_helpers/inventory.pyc`, `Inventory.equip`, 181 | vehicle **inventory** ID, component CD, 0 |
| 101 turret | same, `Inventory.equipTurret`, 204 | vehicle inventory ID, turret CD, gun CD |
| 201 research | `client/account_helpers/stats.pyc`, `Stats.unlock`, 165 | parent vehicle **type** CD, native unlock **index**, 0 |
| 301 buy vehicle | `client/account_helpers/shop.pyc`, `Shop.buyVehicle`, 766 | shop revision, vehicle type CD, flags, crew tariff index |
| 302 buy module | same, `Shop.buy`, 688 | shop revision, item CD, count, gold-for-credits option |
| 308 buy and equip | same, `Shop.buyAndEquipItem`, 718 | array: shop revision, item CD, inventory vehicle ID, slot index, paid removal, gun CD |

`common/accountcommands.pyc` supplies these command IDs. `BUY_VEHICLE_FLAG`
defines none=0, crew=1 and shells=16. P09E supports the explicit unpaid subset:
buy-vehicle flags/tariff 0, buy-item gold option 0, and buy-and-equip slot/paid
removal 0. Other choices return unavailable before reaching the writer. Gold
prices and gold balances are not changed by the free XP/credit policy.

`entity_defs/account.def` and `PlayerAccount._doCmdInt3`/`_doCmdInt4`/
`_doCmdIntArr` establish field order and widths. The gateway uses the existing
family mapping: Int3 method `0x8e`, Int4 `0x90`, IntArr `0x97`. Payloads include
signed INT16 request/command IDs; Int3 then INT64/INT32/INT32 (20 bytes),
Int4 adds INT32 (24 bytes), and this IntArr carries the six-element INT32
array after its count (32 bytes). This P09E command family's actual wire
capture is **NOT_RUN**; previous accepted family traffic does not replace it.

**VERIFIED source distinction:** `ModuleBuyer._request` line173 in
`client/gui/shared/gui_items/processors/module.pyc` calls `Shop.buy` (302).
`TurretInstaller._request` line569 calls `Inventory.equipTurret` (101), and
`OtherModuleInstaller._request` line616 calls `Inventory.equip` (101).
A static name scan of all 992 client `.pyc` files found no GUI callsite for
`Shop.buyAndEquipItem`. Its slot argument is mandatory; there is no wrapper
default proving 0 or -1. **INFERRED:** ordinary GUI purchase/install can use
302 followed by101. **UNKNOWN:** whether a native UI path emits308 on this
build. The implemented308 subset must not be reported as observed UI behavior.

## VERIFIED: graph indices, descriptors and cached state

`VehicleType.__init__` and its component readers in
`common/items/vehicles.pyc` append unlock records in original resource order:
vehicle-level entries, chassis, engines, fuel tanks, radios, then turret
positions. Gun entries are read before each turret's own unlock entries.
`_readGun` passes the gun CD to `_readUnlocks`; `_readGunLocals` also passes
the turret CD. Sorting or deduplicating unlock rows would change the meaning
of CMD201. `VehicleType.__convertAndValidateUnlocksDescrs` line1961 retains
the rows and resolves per-target requirement unions and transitive parents.
Rows have `(XP, target CD, prerequisite CD...)`; the request carries the row's
index within that parent vehicle, not its target CD.

`VehicleDescr.makeCompactDescr` line930 writes chassis, engine, fuel tank and
radio in that order as four little-endian unsigned16 component IDs, then
turret/gun unsigned16 pairs for every position. `_combineVehicleCompactDescr`
line6163 places the vehicle header before those components and flags after
them. Integer CDs use `(itemID << 8) | (nationID << 4) | itemType`.
The project encoder handles plain vehicles with no optional devices or
customization: byte `1 | nationID << 4`, byte vehicle ID, component pairs,
zero flags byte. A one-position descriptor is15 bytes. The module API is
`plain_vehicle_descriptor(vehicle_cd, chassis_cd, engine_cd, fuel_tank_cd,
radio_cd, turret_gun_pairs)`; it validates representation, type and nation.
The authoritative catalogue must separately validate the actual mounts,
position count, compatibility, weight and ownership.

Codec tests match both previously measured mounts:
MS-1 `010d1a000e00c90000001700170000` and
IS-7 `011c3a002400cd000b002f003a0000`. A synthetic multi-position encoding
test checks representation only, not native support for another vehicle.

Inventory uses item-type buckets. Vehicle bucket1 contains `compDescr`,
`repair`, `crew`, `settings`, `shells`, `shellsLayout`, `eqs` and `eqsLayout`
maps keyed by inventory ID; component buckets2–7 hold depot counts keyed by
full integer CD. The complete vehicle record must arrive in one update.
New tanks may have empty crew slots; catalogue availability is not battle
admission. Existing verified battle assemblies remain separately guarded.

`Stats.synchronize` line70, offsets215–305, applies `_GROWING_SET_STATS`
through `setdefault(..., set()).update(...)`. The same function handles
economics `unlocks` and `eliteVehicles` at offsets432–482 as growing sets.
Thus command deltas should contain **new** unlock/elite IDs, while login
state contains their complete authoritative sets. `AccountSyncData`
`.__onSyncResponse` line163 checks `prevRev`, reads `rev` and calls `_update`.
The existing shared writer sends the account update before command success.

`Vehicle.__init__` line97 in `client/gui/shared/gui_items/vehicle.pyc`,
offsets365–410, sets elite when the native unlock list is empty or the type
CD is present in `proxy.stats.eliteVehicles`. `StatsRequesterr.eliteVehicles`
line120 simply returns the cache field. The client does not recompute elite
eligibility for a nonempty tree. **INFERRED server rule:** declare a vehicle
elite after all its graph target CDs belong to authoritative unlocks, and
project newly elite IDs. No original server code was available to prove that
eligibility algorithm; only the consuming client contract is verified.

## VERIFIED: minimal free-cost UI policy

`_TechTreeDataProvider.__readNation` line433 enumerates `unlocksDescrs`
(offset654), reads tuple index0 (685) and populates unlock prices (692).
Changing server debits alone leaves historical XP requirements in the UI.
`Shop.__getPriceFromCache` line1049 reads `items.itemPrices[CD]`, so credit
prices can be projected by the server without another client price patch.

`client_patch/p09e_research_policy.py` is a source-pinned, explicit opt-in
overlay for `test_lab.research.free-credit-xp.v1`. Call
`init(record, policy=POLICY)` before original GUI personality initialization.
It wraps the historical converter, calls its original validation first, and
replaces only each row's XP field with0. List order, target CD, prerequisite
tail and original row objects for rollback are preserved. Existing cached
VehicleType instances are checked before any mutation; construction after
early resource initialization is also covered. An already loaded native
tech-tree provider is rejected because cached prices would otherwise remain
stale. Startup installation and the module guard are integrated separately
by the card's bootstrap change; this subtask never installed the patch.

The runtime pin checks converter code hash, filename, first line, argcount,
names and constants against the independently audited source. The source
file SHA is `805240e4b59d8a75950dbb97b41c17867606e7e96d7ff0c8d7b05312b83ae8b6`;
converter code SHA is
`89fb933bfc007c68d34a0871c88f85fbeabffba5f7f439641f1da48063207915`.
`restore()` verifies current bindings and descriptor objects before restoring
the original class method and exact list objects; a foreign mutation causes
an explicit failure instead of overwriting another patch. Both before-cache
and after-cache lifecycle tests pass. Actual client initialization and UI
appearance remain **NOT_RUN**.

## Gateway integration and bounded projection

The account writer API is authenticated `POST /internal/native/research` with
exact fields `account_id`, `native_database_id`, `command_key`,
`expected_revision`, `wire_revision`, integer `command`, integer `arguments`.
Identity comes from the accepted session. The response binds those identities
and key to revision/wire revision, `update_hex`, `replayed`, `result_code` and
status `researched` or `rejected`. The Python store remains responsible for
catalogue identity, costs, unlocked parents, inventory, capacity, compatible
mounts, reservation, atomic persistence and replay.

`research_service.rs` parses the source-defined envelopes without side
effects. `hangar.rs` validates the entire bundle before dispatch. The new
requests enter the existing ammunition/crew queue and shared writer only
after the cloned frame commits. Request IDs share the same namespace, queues
remain bounded, duplicate transport frames do not add writes, and one update
is emitted before success. No parallel research writer was introduced.

`research_service: true` is an explicit configuration gate and requires the
accepted cross-vehicle crew chain. Profile9 is mandatory. Its metadata binds
account, native database ID, shared revision, wire revision1, state/shop
hashes, command list, battle=false and exact policy/catalogue digests:

- policy: `46875923affb6bd307ad4d35397880fae1dd16fb1992ae2bfbfed607d132361c`;
- catalogue: `b6baecd204444d1e894253fa6c19c61478993b8ae87c71373633989d3a8ee460`.

Research state and shop streams each permit32KiB and32768 primitive parser
nodes; depth remains bounded. Legacy fixtures retain16KiB/4096-node limits.
The explicit research metadata paths also extend the ammunition and
cross-vehicle crew state hash readers, avoiding an accidental16KiB bottleneck
after a large depot is acquired. Stream output remains the existing bounded
resource mechanism; one stored DEFLATE block and400-byte chunks fit the32KiB
maximum in82 fragments. These limits do not grant larger incoming bundles.

`Account.update` consumes a pickle string directly; no verified generic
large account-delta stream was found. The existing240-byte update limit
therefore remains. Growing-set deltas and bounded three-slot garage records
avoid resending the complete graph. The writer must encode and check the
delta **before** committing. Native validation of these particular updates
remains **NOT_RUN**.

## Changes, checks, limits and rollback

Own sources: `tools/p09e_native_research_audit.py`,
`tests/test_p09e_native_research_audit.py`,
`client_patch/p09e_research_policy.py`, `tests/test_p09e_research_policy.py`,
this report, and gateway `account/research_service.rs`, `account/hangar.rs`,
`account/ammo_service.rs`, `account/crew_transfer.rs`, `account/ammo_session.rs`,
`account/identity.rs`, `session.rs`, `main.rs`.

Run from the managed worktree:

```powershell
python -X utf8 -B tools/p09e_native_research_audit.py --original C:\WoT_0.9.1_RU_0717_original --out local/evidence/20261013-p09e-research-01/native-source/source-audit03.json
python -X utf8 -B -m unittest tests.test_p09e_native_research_audit tests.test_p09e_research_policy -v
python -X utf8 -B server/build.py gateway --test --out local/build/p09e-gateway-full02
python -X utf8 -B server/check_layout.py --out local/evidence/20261013-p09e-research-01/native-source/server-layout03.json
```

Evidence outputs are fresh-only; use a new numeric suffix when rerunning.
Before the full build, `WOT_P09E_READONLY_FIXTURE` was set to the absolute
`automatic-flow01/fixtures/<account>/p09d-r15` directory under this card's
evidence. The loader test always tests a complete synthetic27KiB state and
24KiB shop fixture; the supplied environment additionally verifies the real
Python-generated profile read-only. Neither constitutes a client launch.

Executed checks:16-file exact source audit **PASS_SOURCE_ONLY**;12 Python
codec/policy tests **PASS** (`python-tests02.log`); own patch compiles with
actual pinned CPython2.7.3 **PASS** (`python27-syntax01.log`). The initial
targeted Rust build passed9 research tests and built the gateway at
`local/build/p09e-gateway-research01`. The final targeted source run at `local/build/p09e-gateway-research02`
passed11 tests and built gateway SHA
`22e59163036e9b39b6dca67283035f1c24a53ea1e0fb66bb9500fdaea3d400c3`.
The broader modified/default account boundaries passed95 tests with0 ignored
in `native-source/gateway-boundary-tests01/`; its receipt pins the test binary
and actual Python fixture files, and stdout records their sizes1683/22992/92.
The complete740-test run in `local/build/p09e-gateway-full02` is **FAIL**:
568 passed,172 failed,0 ignored. Failures are missing historical prerequisites:
158 absent paths,5 absent portable fixture roots,9 missing pinned worker
fixtures. `full-rust-failure-classification01.json` records every failing test.
No skipping, fallback fixtures or changed historical assertions were used.
`full01` retains a corrected test-only private constant compile failure.
Final layout check passed95 source files/22 relocations in
`native-source/server-layout03.json`; two generated `.pyc` caches were removed
only from verified owned C: paths, with cleanup inventories retained. Dependency setup logs are in `native-source/`;
only toolchain, registry and pinned source dependencies were copied/cloned
into the owned worktree. No original client resources were copied.

Native callback/wire/UI, native restart login and owner mouse acceptance are
**NOT_RUN**. No claim of native P09E acceptance or battle readiness is made.
The required native gate holds this card in its branch. Rollback is to revert
this card's source changes and disable its explicit profile/patch; preserve
evidence and isolated databases. There is no shared installation or live
database mutation to reverse from this subtask. The one next step is the
owner's scheduled original-client research/purchase/install acceptance on
the isolated test profile after the permitted time.
