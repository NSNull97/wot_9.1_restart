# P06E — #717 client collision and projectile callback source audit

Status: **PASS_STATIC_CLIENT_COLLISION_BOUNDARY / NATIVE_SERVER_HIT_NOT_RUN**.

Card: `P06E_CLIENT_COLLISION_SOURCE_RESEARCH`
Base: `2391370` (`Merge P06D status`)
Source: existing #717 bytecode receipt from the accepted P03H research copy.

This is a read-only audit of client-side source structure. It does not execute
client bytecode, start a client/server, alter the deployed gateway, or claim
that the client collision path is the authoritative server solver.

## Source pin and extracted methods

The inspected file is
`local/evidence/20261007-p03h-native-projectile-flight-01/bytecode.json`, SHA-256
`502581a94b4be46d4db885e5922038287b38ff155138cc37ebc24e2216ce7625`. The
bounded extraction receipt is
`local/evidence/20261008-p06e-client-collision-research-01/summary.json`, SHA-256
`61ddf923d1b276176fe8b346590228cd00ab51acefc5f1bce94eb968ec364839`.

The method entries were hashed after canonical JSON serialization:

| Method | #717 source | Static observation |
|---|---|---|
| `_readShell` | `scripts/common/items/vehicles.py:4405` | reads `damage/armor` and `damage/devices`; initializes `damageRandomization=0.25` and `piercingPowerRandomization=0.25`; branches through AP `normalizationAngle`/`ricochetAngle` fields |
| `_readShot` | `scripts/common/items/vehicles.py:4473` | reads `piercingPower` as a `Vector2`, speed/gravity/max distance with bounded XML readers, and multiplies speed by `projectileSpeedFactor` |
| `VehicleDescr.getHitTesters` | `scripts/common/items/vehicles.py:1138` | collects chassis, hull, each turret and each gun `hitTester` |
| `collideEntities` | `scripts/client/ProjectileMover.py:576` | calls each entity `collideSegment(start,end,skipGun)`, keeps the nearest distance, and wraps `entity`, `hitAngleCos`, `armor` in `EntityCollisionData` |
| `collideVehiclesAndStaticScene` | `scripts/client/ProjectileMover.py:603` | calls `BigWorld.wg_collideSegment` for static space, compares nearest dynamic/static result, and returns the nearer candidate |
| `getCollidableEntities` | `scripts/client/ProjectileMover.py:645` | iterates started arena vehicles, applies `segmentMayHitVehicle`, excludes IDs, and adds detached turrets |
| `ProjectileMover.__notifyProjectileHit` | `scripts/client/ProjectileMover.py:200` | calls `BigWorld.player().inputHandler.onProjectileHit(hitPosition, caliber, isOwnShot)` |

The bounded recheck also measures the wrapper that completes this call chain:

| `collideDynamicAndStatic` | `scripts/client/ProjectileMover.py:686` | supplies `getCollidableEntities` to `collideVehiclesAndStaticScene`, joining the dynamic and static segment paths |

The accepted summary predates this recheck and therefore contains seven
method pins. The new receipt derives and hash-checks the eighth wrapper against
the same bytecode source, so the measured set is exactly eight entries while
the original summary remains hash-bound and immutable.

These are source observations, not a reconstructed penetration or damage
algorithm. In particular, the client callback carries a hit position, caliber
and own-shot flag; it does not carry a server-owned target entity, armor layer,
penetration result, HP delta, module event or shot ledger token in this
extracted call.

## What this closes and what it does not

**VERIFIED_STATIC_CLIENT:** the native client has a separate dynamic/static
segment collision path; vehicle descriptors expose hit testers; shell loading
has explicit damage/randomization fields and AP angle-field branches; the
client-side projectile hit notification is an input-handler presentation path.
The `0.25` values are loader defaults observed in this bytecode, not a claim
that the server has adopted them or that they are the complete historical RNG
rule.

**UNKNOWN / NOT_RUN:** server use of these helpers, BSP2 traversal and model
transforms, exact semantics/units of `piercingPower="34 27"`, distance loss,
normalization/ricochet/overmatch, damage roll/application, module/crew rules,
native server hit/damage callback, and equivalence between client and server
solvers. A client hit notification or tracer stop cannot close P06.

The P06C/P06D receipt gate remains the required next step: a real server-owned
intersection with material/normal/thickness, terminal result and replay
idempotency. Until that owner-gated capture exists, hit/damage code stays
unavailable.

## Checks, rollback, next step

The bounded verifier is
`tools/p06e_client_collision_static_audit.py`; its targeted suite is **6/6
PASS**. Receipt:
`local/evidence/20261008-p06e-static-audit-01/receipt.json` (ignored), with
source SHA `502581a94b4be46d4db885e5922038287b38ff155138cc37ebc24e2216ce7625`
and accepted summary SHA
`61ddf923d1b276176fe8b346590228cd00ab51acefc5f1bce94eb968ec364839`.
Duplicate/non-finite/depth/item/path controls and mutation negatives pass. No
arbitrary code or client bytecode was executed. `git diff --check` and
`git show --check` remain required for this card. Rollback is a single commit
revert plus removal of the ignored receipt directory; no runtime state changes.

Single next step: correlate one owner-gated native two-MS-1 impact with this
client boundary and feed only the server-owned rows into the P06D auditor.
