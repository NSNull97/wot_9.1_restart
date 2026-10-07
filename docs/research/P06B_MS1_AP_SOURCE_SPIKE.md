# P06B — MS-1 AP source-field research spike

Status: **PASS_STATIC_SOURCE_FIELDS / NATIVE_HIT_NOT_RUN**
Base: `4535480098c877540518ab8cf6907ae6bd722b61` (`main`)
Branch: `codex/p06b-ms1-ap-research`
Target: original WoT `v.0.9.1 #717` RU, MS-1 with `T-18_Standart` and
`_37mm_Gochkins`.

This is a read-only source audit for the P06A AP-first boundary. It checked the
locally available original resources and the `vehicles_russian.pkg` entries
used by the MS-1 collision descriptors. It did not start the client, server,
deployed gateway or a physics runtime, and it changed no client/resource/code
file.

## Result at a glance

The exact source fields do exist. They are enough to stop calling the MS-1 AP
profile “fieldless”, but they do not by themselves prove the historical hit
algorithm:

| Question | Result | Boundary |
|---|---|---|
| Which AP shell is mounted? | **VERIFIED_STATIC** — `_37mm_UBRT1`, shell item id `10`, native compact descriptor `2570`, `ARMOR_PIERCING`, caliber `37` | Source identity only |
| What damage fields are present? | **VERIFIED_STATIC** — `damage/armor=30`, `damage/devices=50` | Field names/values are pinned; their runtime roll/units and application order are **UNKNOWN** |
| What penetration field is present? | **VERIFIED_STATIC** — mounted gun shot `piercingPower="34 27"` | Pair semantics, distance interpolation and effective units are **UNKNOWN** |
| What flight fields are present? | **VERIFIED_STATIC** — speed `442`, gravity `9.81`, max distance `720`, common factor `0.8` | Existing P03H effective lab values are presentation inputs; historical hit integration remains **NOT_RUN** |
| Are MS-1 armor descriptors present? | **VERIFIED_STATIC** — hull, turret, chassis-track and gun armor/material mappings | Descriptor numbers do not identify a triangle or prove impact resolution |
| Are collision surfaces available? | **VERIFIED_STATIC** — Hull/Turret_01/Gun_02 model, visual and primitive entries | BSP2 interpretation, transforms, units/axes and runtime hit test are **NOT_RUN** |
| Did an AP round damage a target? | **NOT_RUN** | No native hit, penetration, HP/module/crew or duplicate-shot receipt exists |

## Exact source pins

| Relative source | Bytes | SHA-256 | Relevant evidence |
|---|---:|---|---|
| `res/scripts/item_defs/vehicles/ussr/ms-1.xml` | 11,839 | `a494bf04d29da7d066fd6923dbb75a79b947559a52405298c494a943c4b0c535` | active vehicle/turret/gun overrides and armor labels |
| `res/scripts/item_defs/vehicles/ussr/components/guns.xml` | 58,493 | `889fe1564987566478c474ddfef21cbc7742d23bebd19f6a200c59bfafd7d87b` | `_37mm_Gochkins` shot and `piercingPower` |
| `res/scripts/item_defs/vehicles/ussr/components/shells.xml` | 20,468 | `ed301edbe07a72b04dc6c6d799bc563de55d0d1f26bd35798354a9f6769e7a96` | AP identity and `damage` fields |
| `res/scripts/item_defs/vehicles/common/vehicle.xml` | 13,786 | `599ea82e48e98bf9a00c10256030097da31ce5d5889fa03737bc3b79230d256a` | projectile factor and material rules |
| `res/packages/vehicles_russian.pkg` | 1,182,066,680 | `c2e16aef6fe7a7e44e476e2cb96e009b9f4eb7edab55fda2861601ba783415aa` | MS-1 collision payloads |
| `local/evidence/20261002-p00-p01/static/vehicles_russian-index.json` | 1,357,462 | `f52e74baff7063d5edce4d5d807c8cca80612a2c669a1aae2c848e62fc0e24f3` | package member sizes/CRC; not a substitute for payload SHA |

The compact machine-readable receipt is ignored local evidence:
`local/evidence/20261008-p06b-ms1-ap-research-01/summary.json` (receipt SHA
`e2a493c6dee7280c1643277a83dcbddfc736b17abe039157fc798872136b9e14`).
The extraction used the bounded local readers `tools/packed_xml.py` and
`tools/geometry_spike.py::collision_mesh`; it did not execute client bytecode.

## Pinned AP and flight fields

The source path is the authority for each value; no wiki or modern ruleset was
used.

```text
shell: _37mm_UBRT1
  id=10, kind=ARMOR_PIERCING, caliber=37
  isTracer=True, effects=smallArmorPiercing
  damage/armor=30, damage/devices=50

mounted gun: _37mm_Gochkins → shots/_37mm_UBRT1
  defaultPortion=1.0
  speed=442, gravity=9.81, maxDistance=720
  piercingPower="34 27"

common vehicle
  miscParams/projectileSpeedFactor=0.8
```

`piercingPower` is recorded as the literal two-number source field. The report
does not rename it to “minimum/maximum penetration”, assign units, or apply a
distance formula. Likewise `damage/armor` and `damage/devices` are source fields,
not a claim that an accepted server hit subtracts exactly those numbers from HP
or a device.

## Active MS-1 descriptor fields

The following values come from the active `T-18_Standart` chain in
`ms-1.xml`; alternate `T-18_mod`, `T-18Bis` and other guns are not silently
merged into this profile.

| Component | Static fields |
|---|---|
| Hull | collision model `vehicles/russian/R11_MS-1/collision/Hull.model`; armor `armor_1=18, armor_2..7=16, armor_8..9=8, armor_10=0, armor_11=10 (vehicleDamageFactor=0.0), armor_12=16`; `primaryArmor="armor_1 armor_3 armor_4"`; hull max health `72`; ammo-bay max health `60` |
| Chassis `T-18` | collision model `.../collision/Chassis.model`; `leftTrack=5`, `rightTrack=5`; chassis max health `40` |
| Turret `T-18_Standart` | collision model `.../collision/Turret_01.model`; armor `armor_1=18, armor_2=16, armor_3=16, armor_4=16, armor_5=18, armor_6=16, armor_7=8, armor_8=0, armor_9=8, armor_10=16`; `primaryArmor="armor_1 armor_3 armor_4"`; turret max health `18`; turret-rotator max health `50` |
| Mounted gun `_37mm_Gochkins` | max ammo `96`; collision model `.../collision/Gun_02.model`; gun armor `armor_1=18, armor_2=16, armor_3=8` with `vehicleDamageFactor=0.0`; gun material label `gun=10` |

These values establish descriptor mappings. They do not establish which
surface is first along a trajectory, the local transform/pivot at impact, or
whether a device hit continues through another layer.

## Collision payload audit

The package payloads were read by name, hashed and checked with the bounded
`xyznuv` primitive parser. The material IDs below come from each corresponding
`.visual` payload and are correlated to descriptor armor labels; no gameplay
trace was run.

| Part | Payload SHA-256 (model / visual / primitives) | Mesh metrics | Visual material groups |
|---|---|---|---|
| Hull | `2407ddc3c3f24f6e58ce77a960ef5cee4af1255d327ae410c4f53e375a4a096d` / `247d9128d0246ccaf888184a56878f0f52770af92ec6afb9d51894be0a2977ed` / `a2ca7e055e2e2b5ab544ef374a17ce0cf16ae0bbe4666d0a8790c16c41646f95` | 436 vertices, 774 indices, 258 triangles, 13 groups; finite normals ~1.0 | `armor_4, armor_7, armor_1, armor_2, armor_5, armor_3, armor_12, armor_6, armor_8, armor_10, armor_11, armor_9, surveyingDevice` |
| Turret_01 | `5abd915c76098d5e124412549a8088a9268981656885990997b94fd3bbaf6103` / `6a7ee9e7d5c4d92791066bf952d8f848b20fc8edb97c6866b5c32d6920ef4a49` / `58e6d50c0643ebdeb10331002066d6d6e3992d4e3ba143f60086b8f216b71952` | 311 vertices, 654 indices, 218 triangles, 11 groups; finite normals ~1.0 | `surveyingDevice, armor_7, armor_1, armor_3, armor_4, armor_5, armor_6, armor_2, armor_8, armor_10, armor_9` |
| Gun_02 | `a20b9abb67ce0471db8e3a8b1f7833c173d674b0ff6ecd9eb854b4f08c07b913` / `6e21999574feec23e641afb1e9c218560a9d7a68eb85e1c472cb6a47c7046014` / `c24bf873af91c8f339f862d5f49f5f240b4850dbbbeef30b5d04e12edd26cdbc` | 146 vertices, 270 indices, 90 triangles, 3 groups; finite normals ~1.0 | `gun, armor_3, armor_2` |

The full hashes, bounds, group ranges and material-kind integers are in the
ignored receipt. `bsp2_decoded=false` and `units_axes_runtime_validated=false`
are deliberate: the payload is present and structurally bounded, but this
spike did not claim a solver or client-equivalent coordinate convention.

## Classification and remaining unknowns

**VERIFIED_STATIC:** exact source hashes; AP shell identity; literal AP damage
and piercing fields; speed/gravity/range fields; active MS-1 armor labels and
thickness-like values; collision payload presence, hashes, finite mesh metrics
and material labels.

**INFERRED:** the active `T-18_Standart`/`_37mm_Gochkins` chain is the correct
static source profile for native compact shell `2570`, because it matches the
already accepted MS-1 loadout pins. This is a source correlation, not a native
impact proof.

**UNKNOWN / NOT_RUN:** meaning and units of `piercingPower="34 27"`, damage
randomization and modifiers, normalization/ricochet/overmatch, screens and
interior ordering, BSP2 traversal, transforms and axes at runtime, projectile
collision against moving entities/terrain, module/crew chance application,
server hit result, HP mutation, native damage callback and duplicate-shot
idempotency.

Do not turn `30`, `50` or `34 27` into a modern formula or a guaranteed result.
Do not use the collision mesh as a damage surface until its material mapping and
runtime hit-test are correlated by an actual local capture.

## Exact next capture

The next narrow experiment should use the existing isolated two-MS-1 test stand
and one static target pose, without changing the original client:

1. Pin the selected target entity, `T-18_Standart`/`_37mm_Gochkins`, shell `2570`,
   ruleset revision and server launch pose. Save before/after server HP and
   module state.
2. Fire one controlled AP round at a known `armor_1` and one at a known
   `armor_8` material group. Capture the server segment/intersection record with
   shot identity, triangle/group, material label, normal, thickness input and
   terminal reason. A client tracer or screenshot alone is insufficient.
3. Repeat the same shot identity at the transport boundary. Verify one ammo
   decrement and at most one terminal damage token; a conflicting replay must
   be rejected. Preserve raw native frames only in ignored local evidence.
4. If the capture cannot provide a server-owned intersection and HP/module
   event, leave the result `NOT_RUN` and keep the solver unavailable. No guessed
   damage is acceptable.

This report is a candidate source closure, not P06 acceptance and not a merge
request. The single next recommended step is the controlled local intersection
capture above.
