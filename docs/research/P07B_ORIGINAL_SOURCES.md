# P07B — original #717 spotting source ledger (0.9.1)

This ledger is the source boundary for the no camouflage/no bushes phase of
P07B. The reader uses only the read-only client at
`C:/WoT_0.9.1_RU_0717_original` and retained evidence. It does not import
client modules, execute Python 2 bytecode, start a client/server, copy client
resources, or claim native wire compatibility.

The bounded receipt has **exactly six static source rows** and **exactly seven
dynamic observations**. The counts are intentional: changing either count is
a source-ledger review event, not a harmless formatting change.

## Evidence table

| Area | Status | What is actually bound | Limit |
|---|---|---|---|
| Six source files | `VERIFIED_STATIC` | Three entity definitions and three #717 client bytecode files, hash and byte count pinned below | Hash identity does not establish runtime timing or server authority |
| Seven mounted base ranges | `VERIFIED_STATIC` | `circularVisionRadius` and turret identity for MS-1, IS-7, T-26, T-34, T-34-85, Waffenträger E 100 and FV215b (183) | Base radius only; no crew/equipment/camo/effective range |
| Observer declarations | `VERIFIED_STATIC_DECLARATION` | `onObservedByEnemy`, `notifyVehicleOnObservationByEnemy`, `receiveVisibilityInfo` | Declaration is not proof of invocation, recipient filtering or wire ID |
| Sixth Sense event | `VERIFIED_STATIC_BYTECODE` | `VEHICLE_MISC_STATUS.IS_OBSERVED_BY_ENEMY = 1`; `updateVehicleMiscStatus` carries 13 fixed bytes; client calls the lamp UI | Owner's 3 s delay is a project rule, not recovered from this source |
| Sixth Sense UI duration | `VERIFIED_STATIC_EVIDENCE` | Retained `gui_settings.xml` has `sixthSenseDuration = 2000 ms` | Native lamp/audio/control run is still NOT_RUN |
| Point observers/transforms | `VERIFIED_STATIC_POINT_FORMULAS` / `UNKNOWN` | Six source `visibilityCheckPoints` and two observer positions are bound below | Yaw/pitch/roll transform and native target set are UNKNOWN |

### The six pinned static source rows

| Relative path under `res/scripts` | Bytes | SHA-256 |
|---|---:|---|
| `entity_defs/avatar.def` | 7,450 | `38cf983d6ea1fcaf1bbca25fd18567fed5abc3b2e07fbe14b168f46fa883f74d` |
| `entity_defs/vehicle.def` | 5,588 | `08dc1e6be577f80a04bf813ca046550201a3c4e673dad1540c5f1c6a047d1297` |
| `entity_defs/arena.def` | 3,036 | `e50906f11e0fcbf1f5b41e105353689ca4b9e3cdb1768b7ac41edab7f3c2f4fc` |
| `client/avatar.pyc` | 83,656 | `c13cd58a4c5d766dfd3c5f47ae7be50c962aee6c7f8cf25b4341322381f21e0e` |
| `client/vehicle.pyc` | 24,119 | `b81d08ca14092bb8912adb2eff20325c3dd23424868bc03164cfe6b8da50463c` |
| `client/clientarena.pyc` | 12,823 | `30b21bb0e386b909d162f127b79b86e5da1aeecb65e9c6700b2b50f435dbd455` |

The bytecode reader accepts Python 2.7 marshal as bounded data. It returns code
records, names and constants; it never imports a client package and never calls
`eval`/`exec`.

### The seven dynamic observations

These are source observations used by the server contract. They are not a
native capture and do not turn an inferred server policy into a historical
claim.

1. `avatar.def` `ClientMethods.updateVehicleMiscStatus` has
   `(OBJECT_ID, UINT8, INT32, FLOAT32)`, exactly 13 fixed payload bytes.
2. `avatar.def` `BaseMethods.updateVehicleMiscStatus` has the same four
   arguments and 13 fixed bytes.
3. `common/constants.pyc` defines
   `VEHICLE_MISC_STATUS.IS_OBSERVED_BY_ENEMY` as event code **1**.
4. `client/avatar.pyc` `PlayerAvatar.updateVehicleMiscStatus` (source line
   1266) branches on that code and calls `showSixthSenseIndicator(True)`.
5. `client/gui/scaleform/battle.pyc` `Battle.showSixthSenseIndicator` invokes
   the Scaleform method `sixthSenseIndicator.show`.
6. `Battle.afterCreate` binds the `sixthSenseDuration` setting through
   `sixthSenseIndicator.setDuration`.
7. Retained evidence `20261005-p02-map-drive/bind01-prepare/bundle/res_mods/0.9.1/gui/gui_settings.xml`
   contains `sixthSenseDuration = 2000` milliseconds.

The project-owned change is deliberate: Sixth Sense is always available as a
base commander capability and is not learned or gated by crew qualification.
The requested **3 s / 3000 ms** delay is recorded as
`OWNER_OVERRIDE_NOT_SOURCE_VERIFIED`; the original bytecode above only proves
the status event and UI path.

### Observer declarations

The original entity definitions expose these relevant observation boundaries:

| Source | Method | Arguments | Status |
|---|---|---|---|
| `entity_defs/vehicle.def` | `CellMethods.onObservedByEnemy` | `OBJECT_ID, BOOL` | `VERIFIED_STATIC_DECLARATION` |
| `entity_defs/arena.def` | `CellMethods.notifyVehicleOnObservationByEnemy` | `OBJECT_ID, BOOL` | `VERIFIED_STATIC_DECLARATION` |
| `entity_defs/avatar.def` | `CellMethods.receiveVisibilityInfo` | `ARRAY<OBJECT_ID>, ARRAY<FLOAT32>, ARRAY<FLOAT32>` | `VERIFIED_STATIC_DECLARATION` |

The implementation must treat callback names as source evidence only. Native
method IDs, serializer order, cadence, sender and recipient are still
`UNKNOWN` until a controlled native capture.

## Mounted base ranges

The bounded reader hash-binds each mounted XML row, then checks its turret
identity against the original components table before accepting a radius. The resulting sequence is exactly
`240 / 400 / 280 / 240 / 350 / 420 / 400` metres:

| Profile | Original vehicle source | Mounted turret | Turret ID | Base radius (m) |
|---|---|---|---:|---:|
| MS-1 | `item_defs/vehicles/ussr/ms-1.xml` | `T-18_Standart` | 23 | 240 |
| IS-7 | `item_defs/vehicles/ussr/is-7.xml` | `IS-7` | 47 | 400 |
| T-26 | `item_defs/vehicles/ussr/t-26.xml` | `T-26_cylindrical` | 30 | 280 |
| T-34 | `item_defs/vehicles/ussr/t-34.xml` | `T-34_mod_1940` | 0 | 240 |
| T-34-85 | `item_defs/vehicles/ussr/t-34-85.xml` | `T-34-85` | 17 | 350 |
| Waffenträger E 100 (128 mm) | `item_defs/vehicles/germany/waffentrager_e100.xml` | `Turret_1_Waffentrager_E100` | 134 | 420 |
| FV215b (183) | `item_defs/vehicles/uk/gb48_fv215b_183.xml` | `Turret_1_GB48_FV215b_183` | 69 | 400 |

These are source base values. They must not be silently changed into a
universal 445 m radius or combined with modern camouflage/equipment rules.
The alternate MS-1 `T-18_mod` is a different turret (280 m) and is not a
substitute for the mounted stock `T-18_Standart` row.

## Sight points and transforms

The original `common/items/vehicles.pyc` `VehicleDescr.__updateAttributes`
(line 1462) constructs **exactly six** `visibilityCheckPoints` on the cell
side, plus two named observer positions. The bounded reader verifies the
method record, its geometry inputs (`hullPosition`, `turretPositions`,
`gunPosition`, hit-tester `bbox`) and the six-point contract:

1. `Vector3(0, hullPos.y + turretLocalTopY, 0)`;
2. `hullPos + gunPosOnHull`;
3. `hullPos + Vector3(0, hullLocalCenterY, hullBboxMax.z)`;
4. `hullPos + Vector3(0, hullLocalCenterY, hullBboxMin.z)`;
5. `hullPos + Vector3(hullBboxMax.x, gunPosOnHull.y, hullLocalCenterZ)`;
6. `hullPos + Vector3(hullBboxMin.x, gunPosOnHull.y, hullLocalCenterZ)`.

The same method stores `observerPosOnChassis = Vector3(0, hullPos.y +
turretLocalTopY, 0)` and `observerPosOnTurret = turret.gunPosition`. These are
source-defined local points, not client coordinates supplied by a player. The
receipt records point counts explicitly as `visibility_check_points = 6` and
`observer_positions = 2`.

| Claim | Classification |
|---|---|
| Six source visibility check points and their arithmetic | `VERIFIED_STATIC_POINT_FORMULAS` |
| Two named observer positions | `VERIFIED_STATIC_POINT_FORMULAS` |
| Full hull yaw/pitch/roll transform for all six points | `UNKNOWN` |
| Turret yaw relative to hull and gun pitch ordering | `UNKNOWN` |
| Behavior after a complete rollover and world-up correction | `UNKNOWN` for original spotting; P05C physics has a separate measured rule |
| Exact target-point set used by the native LOS evaluator | `UNKNOWN` |

No hidden client coordinate, clock, HP or self-reported visibility state may be
used as authority. Missing geometry or an unresolved transform must fail
closed in the server path.

## Explicit unknowns and out-of-scope rules

The following remain `UNKNOWN` for the verified 0.9.1 implementation and must
not be filled from memory or a current WoT/Lesta/Blitz ruleset:

- maximum detection cap beyond the mounted base radius;
- any unconditional near/proximity detection shortcut;
- scan cadence and scheduling jitter;
- disappearance hold, reappearance hysteresis and stale target lifetime;
- radio/team transfer semantics and its range;
- exact sight/target point transforms under yaw, pitch, roll and inversion;
- native callback wire IDs, serializer order and client-side ACK behavior;
- native Sixth Sense lamp/audio timing and sound event.

Camouflage, bushes as coefficients, equipment, a new skill system and economy
are outside this card. Geometric obstacle opacity is a separate LOS research
boundary. The current server may use an explicit, versioned lab policy only
when the ledger labels it as project policy rather than historical fact.

## Bounded reader and evidence

The reader is [tools/p07b_original_sources.py](../../tools/p07b_original_sources.py).
It creates one small JSON receipt and refuses to overwrite an existing file or
write outside C:. Example (PowerShell):

```powershell
New-Item -ItemType Directory -Force C:\wot091-p07b-20261017-02\evidence\source-ledger05 | Out-Null
python -B -X utf8 C:\wot091-p07b-20261017-02\w\tools\p07b_original_sources.py `
  --original-root C:\WoT_0.9.1_RU_0717_original `
  --evidence-root D:\WoT_9.1_Server\local\evidence `
  --out C:\wot091-p07b-20261017-02\evidence\source-ledger05\original-sources.json
```

The retained receipt from this run is SHA-256
`c3b1e3cff7c3935c59853b745df3d4f135884ac304036cb1fc3aaa2d06c222b9`.

The command is static-only. Do not run Cargo, the gateway, a client, a live
stand or a native UI/audio check as part of this source receipt. Native/UI/
audio/control acceptance remains `NOT_RUN`.

## Acceptance boundary

Current label: `PASS_STATIC_P07B_ORIGINAL_SOURCE_LEDGER` after the bounded
reader succeeds. This proves only the pinned source facts and receipt
integrity. It does not prove native spotting behavior, timing, radio sharing,
or true client-compatible appearance/disappearance. Rollback is deleting the
new C: receipt and reverting this documentation/tool pair; the original client
and all D: evidence remain untouched.

The source-bound values are integrated into the P07B ruleset and World publication path. Current focused Rust checks pass; native two-client/UI/audio testing remains the owner gate.