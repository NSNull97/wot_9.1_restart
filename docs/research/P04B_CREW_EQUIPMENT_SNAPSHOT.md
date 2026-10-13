# P04B — immutable crew / installed-device snapshot

2026-10-13; branch `codex/p04b-crew-equipment-snapshot`, accepted base
`90c7a1d92a67be2acf2d02ab9a5720a377c9f2c8`. Isolated parallel card: no merge,
main checkout changes, live inventory issuance or runtime wiring.

## Existing work and chosen result

P02_MS1_CREW already issued two native MS-1 tankmen and checked cached relogin.
That frozen generator, native descriptors, account state and its 100%/no-perks
test_lab policy remain unchanged. P03I researched vehicle/queue boundaries;
`battle/profile4_adapter.rs` binds MS-1 crew count to the existing loadout gate.
Neither provides a general installed-device modifier snapshot. P04's existing
typed content importer remains the resource boundary, without a parallel import
format or replacement XML/bytecode reader in this card.

New `server/domain/crew_equipment.py` validates a server configuration and
returns canonical immutable bytes plus SHA256. It covers complete healthy
100% correctly trained crews without skills and four source-proven optional
devices, with exact source decimal arithmetic. This is a server domain
component, not a game endpoint or native serializer. The source audit reuses
`packed_xml`, `py27_static` and the bounded `destructible_catalog` helpers.

## VERIFIED source facts

Original root comes only from the explicit existing local configuration:
`C:\WoT_0.9.1_RU_0717_original`, build `v.0.9.1 #717`, RU, recorded client
manifest `74c37c18e9ac7e30196c134076dacf6f2a8bf3897f7def73905d09feb3647797`.
The new audit rehashes the 12 selected resources, not the entire client tree.

| Definition | Source ID / native typeCD | Ordered seats; primary role first |
|---|---|---|
| `vehicle:ms1` | USSR `13` / `3329` | commander+gunner+radioman+loader; driver |
| `vehicle:is7` | USSR `28` / `7169` | commander; gunner; driver; loader; loader+radioman |

Native primary-role indices: commander=1, radioman=2, driver=3, gunner=4,
loader=5 (`tankmen.pyc`, module 177–192 and 366–391). Roles remain domain
strings in the validator. `vehicles._readCrew`, line 4705, preserves XML
seat order, prepends the primary role to additional `asString.split()` roles
(offsets 64–257), then checks role coverage and one commander (308–423).
The second IS-7 loader must not be deduplicated by primary role.

The older native vehicle exports independently contain these same rosters:
`local/server/native-descriptors.json` SHA256
`18e6c2babfc205ce80fa24c2c9f23385a1731233c4d504be369638485652d6f2`, and
`native-is7-descriptors.json` SHA256
`4b24a59c5344808018caf438c044d31d86cf1da20c8b2cbd58f93b8ab2f859b1` in the
primary checkout. This run reads them only. No IS-7 tankman descriptors,
personalities, IDs or grants were generated.

The installed-device category is `ITEM_TYPES.optionalDevice=9`, distinct
from consumable `ITEM_TYPES.equipment=11` (`items/__init__.pyc` offset 91).
`nations.NONE_INDEX=15` (40–43). Compact ID is `(source_id<<8)+(15<<4)+9`.
`vehicles.pyc` module offsets 540–549 defines three optional-device slots
and, separately, three consumable slots. Our input accepts only the former.

| Domain suffix after `optional_device:` | Source ID / compact ID | Admitted vehicle | Static effect | Extra mass |
|---|---|---|---|---|
| `improvedVentilation_class1` | 17 / 4601 | MS-1 | add 5 to `crewLevelIncrease` | 100 kg |
| `improvedVentilation_class3` | 19 / 5113 | IS-7 | add 5 to `crewLevelIncrease` | 200 kg |
| `enhancedAimDrives` | 25 / 6649 | both | multiply `gunAimingTimeFactor` by 0.91 | 100 kg |
| `coatedOptics` | 5 / 1529 | both | multiply `circularVisionRadiusFactor` by 1.1 | 0 kg |

Ventilation class1 includes ANY of `lightTank improvedVentilation_class1_user`;
class3 includes ANY of `heavyTank heavyAT-SPG improvedVentilation_class3_user`.
Both exclude `noImprovedVentilation`. Exact #717 MS-1/IS-7 tags are audited;
neither has that exclusion. These two vehicle definitions are the closed
allowlist; class2, rammers, toolboxes, stabilizers and every other item reject
as unsupported even if their source files contain data. Optics/aim drives have
no vehicle filter. This is deliberately narrower than the whole native catalog.

`artefacts._VehicleFilter.checkCompatibility`, line 534, evaluates exclusions
first (0–54), then inclusions (58–122); `_matchSubfilter`, line 639, uses tag
intersection (137–171). `VehicleDescr.mayInstallOptionalDevice` rejects a
duplicate (75–96) and invokes the weight check (204–234).

`VehicleDescr.__updateAttributes`, line 1462, initializes factor attributes
to 1.0 and crewLevelIncrease to zero (519–613), then applies nonempty devices
in **slot order** (619–656). `StaticAdditiveDevice` adds, `StaticFactorDevice`
multiplies; an integer destination is converted with `int(...)` (109–131), a
float destination follows its own path (135–151). For this subset crew addition
is integral and the two factors have distinct attributes, so there is no hidden
cross-factor reorder. The snapshot stores every operation and its before/after
value, as well as reduced numerator/denominator values.

## Arithmetic and mass boundaries

The source literals `0.91` and `1.1` are VERIFIED. `_xml.readPositiveFloat`
delegates to native `section.readFloat`; its C implementation and returned bit
pattern were not measured here. Our `91/100` and `11/10` are an explicit
deterministic **project arithmetic contract**, not a claim of native binary32
identity. No final aim time, reload time, view range or spotting cap is computed.

GUI calculation is separately documented, deliberately not used as a battle
formula. `Vehicle._calcCrewBonuses`, line 217, computes the commander's rounded
role+specialization+optional-device addition (360–380), adds brotherhood and
consumable bonus, then divides by COMMANDER_ADDITION_RATIO=10 and rounds again
(390–434). `Tankman.realRoleLevel`, line 185, clears the commander's own bonus
(43–73), then sums efficiency+commander+brotherhood+equipment+optional-device
bonuses (139–158). Existing standalone CPython 2.7.3 x86 really returned
`round(10.5)=11.0`: GUI levels are 100/110 without ventilation and 105/116 with
it. This is an arithmetic check of inspected GUI logic, not native game execution
or an inferred battle formula. The snapshot emits base levels and the static
`crewLevelIncrease`, without treating GUI percentages as combat coefficients.

Native base mass is the sum of hull, chassis, engine, fuel tank, radio and all
turret/gun pairs (`VehicleDescr.__computeWeight`, line 1432, 13–117). Optional
devices supply fraction/addition/max-load changes, combined as
`base*(1+sum_fraction)+sum_addition`; max load is chassis limit plus changes
(130–240). Selected devices have zero fractional and max-load changes.
The native change predicate allows nonnegative new reserve OR a non-worsening
overweight change (`_isWeightAllowedToChange`, line 6212). Our project policy
is stricter: final total must be at most max load.

This card does **not** independently import and verify masses for every mounted
assembly. A nonempty equipment configuration therefore requires a separate
trusted `MassBudget`, bound to the same component-configuration SHA and the
upstream mass-evidence SHA. Its base mass excludes optional devices and both
values use exact integer grams. Missing/unknown budget rejects, even for optics.
Unit-test mass budgets are explicitly synthetic inputs, not MS-1/IS-7 historical
measurements. An empty-device roster snapshot can be built without that budget;
its `mass_check=null` is not proof of vehicle admissibility.

## Server integration contract

Call `build_snapshot(raw, binding=TrustedBinding(...))` with at most 8192 bytes
of `crew-equipment-input.v1`. The binding comes from the authenticated account /
configuration authority, under the same reservation and revision. It supplies
account ID, vehicle inventory ID, revision, exact input SHA256, mounted-component
configuration SHA256, `POLICY_SHA256` and optional verified `MassBudget`.
**Do not construct this binding from the candidate JSON or a client request.**
Neither SHA nor this validator authenticates a network caller.

The authoritative input has exactly `format`, `policy`, `account_id`,
`vehicle_inventory_id`, `vehicle_definition_id`, `configuration_revision`,
`component_configuration_sha256`, `crew`, `optional_devices`. Every crew row
has exactly `crew_id`, `seat`, `role`, `role_level`,
`trained_vehicle_definition_id`, `vehicle_inventory_id`, `healthy`, `skills`.
The account authority must have verified ownership/existence of these IDs;
this component enforces digest, binding, slot, role, training and policy rules.
Equipment is a three-item slot array of null or allowlisted domain ID strings.
It cannot supply a coefficient, native wire index, skill implementation or price.

Output `crew-equipment-snapshot.v1` has immutable canonical bytes and SHA256,
the exact input/revision/component/policy bindings, ordered crew roles, installed
devices, slot-ordered operations, rational modifiers, mass-check provenance and
source pins. `as_dict()` returns an independent decoded copy. Identical input
bytes/binding produce identical output. Reordering source JSON changes the
input digest intentionally even if normalized crew rows match.

To consume it later, battle preparation must verify the authenticated owner,
reserved vehicle, current revision, mounted-component SHA, policy SHA and
snapshot digest in the same atomic reservation as ammo/service. A stale or
foreign snapshot must fail admission. Implemented output always has
`runtime_ready=false`, `runtime_acceptance=NOT_RUN`. It contains no session
secrets, client positions or hostile-visible state. IS-7 issuance and any
native serialization remain separate work. Shared `loadout.rs`, ammo/service,
gateway, transport and physics are unchanged.

## Classification and limitations

- VERIFIED: selected original source hashes, rosters/IDs/filters/slots/static
  coefficient order, domain validation and deterministic snapshot properties.
- OBSERVED: the separately recorded standalone Python 2.7.3 arithmetic output;
  prior native roster exports agree, but no new native client was run.
- INFERRED: this frozen snapshot is a suitable future integration boundary;
  suitability for the live battle path is not acceptance.
- UNKNOWN / NOT_RUN: native float bit patterns, crew-to-combat formula, final
  characteristic composition/caps, native installed-device readback, real
  component-mass integration, live IS-7 crew grant and battle/UI integration.

Training, injury, perks, consumables, economy and all unlisted devices reject
explicitly. No client resources, bytecode, compiled binary or copied source are
tracked. Only original implementations, small factual constants and source pins
are committed. Whole-client licensing/redistribution remains outside this card.

## Commands, evidence and rollback

Run from this managed worktree. All writes stay under its own ignored `local/`.

```powershell
$env:WOT091_CONFIG = 'D:\WoT_9.1_Server\config\project.local.json'
python -B -X utf8 -m unittest tests.test_crew_equipment tests.test_crew_equipment_source_audit tests.test_content_bundle tests.test_content_import tests.test_server_layout -v
python -B -X utf8 tools/crew_equipment_source_audit.py --config D:\WoT_9.1_Server\config\project.local.json --out local/evidence/20261013-p04b-crew-equipment-01/source-final
python -B -X utf8 server/check_layout.py --out local/evidence/20261013-p04b-crew-equipment-01/layout-final.json
```

Fresh outputs are append-only; choose a new output path for reruns. Exact
execution counts, hashes and final commit are in [the evidence index](../evidence-index/P04B.md)
and the local final receipt. Earlier extraction/rounding evidence remains in
`local/evidence/20261013-p04b-crew-equipment-01/crew-source/` and
`equipment-source/`. Source assertions and extracted factual rosters are saved,
while original files remain read-only.

Rollback: revert the P04B commit in the integrating branch, or leave this branch
unmerged. There are no grants, DB migrations, native installs or deployed
process changes to undo. Preserve ignored evidence until integration review.

Single next step: integrate this snapshot at the shared configuration-reservation
gate with independently verified mounted-component mass evidence and then run
the separate native acceptance card alongside ammo/service integration.
