# P06M — projectile contact with Karelia terrain and static obstacles

2026-10-10. Branch `codex/p06m-terrain-impact`, accepted base main `55af06f`.
Owner authorized this next card after accepting live and wreck impact effects.

## Native01 defect and correction in progress

Owner reported: some rocks pass shots or have no effect; rock effects appear
after variable delays while ground appears immediate. Immutable snapshot01
retains24 launches,15 terrain contacts and30 paired original ground-effect
callbacks. Delivery audit passed; **spatial/owner acceptance FAILED**. Some
native early-stop points differ from the terrain-only server by up to551.217m.
This cannot be reported as accepted world collision.

Original ProjectileMover.__calcTrajectory uses mask128 and destructible
predicate, while the accepted map-drive obstacle export uses mask18. They
are not equivalent. New `export_projectile_obstacles.py` reuses the verified
original model/BSP/material decoders without modifying old exports or client
resources. It emits179,365 triangles /538,095 vertices,2,918 instance spans,
per-triangle mapped UINT16 flags and hashes under
`projectile-obstacles01/01_karelia/`. All kept flags satisfy `(flags&128)==0`.
Independent verification checks every vertex/index/flag and recomputed AABB.
Manifest SHA256
`ccd28d8e3320d041e569e217a8c20e0285db0459bc2ef447c5bd95dd97d80cea`.

New `shared/obstacles.rs` provides a bounded BVH query over this separate
projectile export; it participates in the same nearest terrain/vehicle
decision. Original material kinds101..113 map through the original effect
table, including107(rock)→ground0 and111(stone)→stone1. Unmapped static kinds
use explicit approximate `test_lab-unmapped-static-ground-v1`; no original
fallback is claimed. Static initial destructible meshes are provisional:
map-object damage/removal/penetration and their native predicate state remain
unsupported. This card does not establish the full destructible simulation.

Passive __calcTrajectory observation records original hit material/point,
stop return offset and owning shot, without invoking or replacing native
collision. A second native run must confirm near/far rock timing, actual
effect positions/materials and retained ground/live/wreck behavior.

## Goal and implementation

The cumulative two-client runtime queries the accepted map-drive terrain,
the separate original mask128 static projectile mesh, and the other tank on
each original flight segment. The nearest selected surface terminates the
projectile; world surfaces cannot produce AP, HP change or death events.
Both peers receive the original Avatar.explodeProjectile callback once. Its
terminal replaces stopTracer: sending stop afterwards can hide the deferred
native explosion. Rejoin skips historical shot effects.

New `shared/terrain.rs` loads only the pinned hole-free Karelia export, checks
hashes before decoding, checks every grid coordinate/checkerboard index and
stores immutable shared heights. A clipped supercover grid walk bounds work
at 1540 crossing parameters and 6160 candidate cells, without scanning all
1,179,648 triangles per shot update. Map and terrain paths remain below local/.

`shared/impact.rs` keeps combined queries and terminal facts atomic. A cached
terrain hit is tied to its shot/update/segment, not supplied by the caller.
Terrain-first blocks AP/wreck outcomes and continued flight. World clones its
actors/projectiles/history before mutation; queue failure cannot duplicate
damage or FX. The bounded trace holds at most36,040 events for40 shots.

Terrain is queried in original world XYZ: no body-centre, spawn or worker
settling offset is added to the map. Terrain-enabled flight splits delayed
updates into chords no longer than100ms; the final range tail is included.
Same-update subsegments must be contiguous and nonzero, retaining all count
and identity guards. Target pose is the current authoritative update pose;
this is not continuous swept moving-target collision.

Vehicle query retains `t:f32`, terrain computes `t:f64`. Selection compares
both in the f32 parameter domain. Ground wins the same rounded bucket, with
no additional epsilon. This deliberate tiny ground bias is documented and
tested with t0.7; claiming an exact mathematical tie would be incorrect.

## Changed files

- `server/gateway/src/shared/terrain.rs`: pinned loader, grid query and tests.
- `server/gateway/src/shared/obstacles.rs`: pinned projectile mesh, immutable
  bounded BVH, material/instance identity and native01 shot3 regression.
- `server/gateway/src/shared/terrain_wire.rs`: verified material-aware FX codec.
- `server/gateway/src/shared/impact.rs`: atomic combined query, typed terrain
  terminal, arbitration guards, contiguous subsegments and budget tests.
- `server/gateway/src/shared/model.rs`: prestart binding, nearest-world
  selection, bounded flight chords, terrain outcomes and transaction tests.
- `server/gateway/src/shared/server.rs`: explicit pool binding, reliable
  publication, source/contact logs and per-peer/rejoin/rollback tests.
- `server/gateway/src/shared/mod.rs`, `server/gateway/src/main.rs`: explicit
  module/CLI binding under `--ap-test-lab --terrain-test-lab`.
- `client_patch/sr_interactive.py`: passive original callback/effect observer,
  immediate native caller shot ID, no new collision or gameplay decisions.
- Plan, STATUS, ACTIVE_GATE and this report.

## Sources and evidence classifications

**VERIFIED:** accepted config `local/server/map-drive/01_karelia-v1.json`,
SHA256 `cf93c617d328865faaf93b7081eb838eb13262b12fe27b4a603e1f2a7023f4c2`;
terrain manifest SHA256
`5e23f58d4e9d78398bd9cd861f6bc09a038cce7e8f7b311731e50c30bcc958f9`.
Original package, all144 cdata digests, no hole members,591,361 vertices,
checkerboard parity and original heightAt byte window were independently
checked. The exported static mesh is the accepted physics geometry.

**VERIFIED:** #717 Avatar.explodeProjectile exposed28/message0x57 uses VAR1.
Arguments: SHOT_ID INT32, effectsIndex U8, materialIndex U8, endpoint and
direction as VECTOR3, ARRAY<UINT32> destructibles. Empty array uses an i32
zero count:34 payload bytes,37 including selector and method header. Stock
smallArmorPiercing2/ground0 selects original ground particles/sound/decal.
Original callback normal RETURN offset72; original effect helper normal
RETURN offset398. Codec rejects malformed IDs, nonfinite coordinates and
nonunit directions. These contracts alone do not prove rendered pixels.

Evidence root: `local/evidence/20261010-p06m-terrain-impact-01/`.

- `geometry-contract01.json` / `geometry_contract_audit.py`: original source
  audit, with initial mixed-precision finding retained unchanged.
- `geometry-arbitration-review02.json`: finding resolved in both selectors;
  SHA256 `4fb609f013e4230e7284b5cb372486d4ccf51b6215cccf7b9fc2b1d21b5c25e1`.
- `native-terrain-effect-contract01.json` and reproduction script: original
  method/source pins; SHA256
  `dadede07ac9ec0dfca9b67bcf479ff644a51d6bac814f95f60f8b1bc80ed1722`.
- `audit_native_ground_run.py`: bounded per-shot two-peer audit of original
  callback returns, endpoint/direction, helper calls and absence of stop/AP.
  Its13 synthetic checks passed; synthetic success is not native evidence.

**INFERRED/explicit policy:** ground0 is a basic ground presentation, without
classifying snow/sand or claiming historical server material rules. The
surface query is two-sided and does not invent a t0 contact for a segment
already entirely underground. Coplanar segments yield no contact.100ms chords
have at most about7.85mm gravitational sagitta with current stock parameters.

**UNKNOWN:** equality with original server projectile collision, historical
server armor/RNG rules, water, dynamic destructible state and full native
predicate equivalence. Client endpoint substitution is observed; rendered
agreement still requires the new native run, not just callback delivery.

## Commands and current verification

```powershell
python -B -X utf8 server/build.py gateway --test --out local/build/server/gateway-integrated-world-p06m-05
python -B -X utf8 -m unittest tests.test_interactive_window_trace tests.test_interactive_primitive tests.test_interactive_relogin_control tests.test_server_layout
python -B -X utf8 server/check_layout.py
python -B -X utf8 local/evidence/20261010-p06m-terrain-impact-01/prepare_stand.py --slot a --run native02
python -B -X utf8 local/evidence/20261010-p06m-terrain-impact-01/prepare_stand.py --slot b --run native02
python -B -X utf8 local/evidence/20261010-p06m-terrain-impact-01/start_stand.py server --run native02 --build gateway-integrated-world-p06m-05 --profile integrated-lab --pool local/build/server/physics-integrated-lane-01/pool.json --geometry local/evidence/20261010-p06j-contact-materials-01/ms1-contact.json --ap-test-lab --terrain-test-lab
python -B -X utf8 local/evidence/20261010-p06m-terrain-impact-01/start_stand.py a --run native02
# Wait for the first actual session before starting B; never race logins.
python -B -X utf8 local/evidence/20261010-p06m-terrain-impact-01/start_stand.py b --run native02
```

Build01 failed compilation on an inferred closure index type; explicit usize
fix retained. Build02 compiled,520 passed/2 new tests failed: an exact0.7 f64
assertion and an overbroad whole-outbox repeat assertion. Corrected assertions
still check the actual rounding bucket and once-only effect/absence of stop.
Build03 passed522/522 Rust tests and isolated build; executable SHA256
`8b398ca994b0af4ae9fd7dedc9b309499d85e19e16adf81b4d218bc3cbe32562`.
Failed receipts are preserved, not relabelled PASS. Build04 passed533 tests
with static obstacles. Final build05 passed534/534, including the actual
native01 shot3 regression and forged static/ground-only revision rejection;
EXE SHA256 `e84eaf3ec132da945ba5b5bc4d4d9cf7c0c410afac237a0d4b041351b4a76818`.
Python26 PASS/1 existing Windows symlink privilege skip (python-observer02.log).
Layout69 files/22 single-source relocations PASS. New native acceptance pending.

Independent replay `projectile-obstacles-replay02/receipt.json` (SHA256
`51db4f906faa1bf69991af2e217bc3f59d253862d34310d5dc3957c5a75bd1a3`)
finds stone kind111, triangle173697/instance2666 at 0.13307s. The100ms chord
endpoint differs9.97mm from the recorded native point;20ms/1ms variants
differ14.41/14.66mm. Original tick phase is unknown. This corroborates the
geometry fix, not a fresh rendered effect. Final read-only review found no
remaining material runtime blocker; original native01 failure remains FAIL.

## Acceptance, limitations and rollback

Status: native01 owner acceptance **FAIL**; corrected static-world candidate
passes automated checks, new native02/owner acceptance **NOT_RUN**. No merge
until both applicable gates pass. Server query/tests do not prove rendered FX.

Scope remains a two-client MS-1 AP test_lab on Karelia with accepted movement,
aim, ammo, reload, live/wreck damage/effects. Static original map geometry is
included; dynamic map destruction and historical_091 are not accepted.
A below-ground muzzle is not
automatically clamped to the surface. Client native presentation can select
its own collision endpoint/material; compare measured callbacks explicitly.

Source rollback: return to accepted main55af06f before merge, or revert this
card's eventual merge. Runtime rollback: stop only verified owned test PIDs,
restore their install ledgers via tools/interactive_client.py rollback, then
launch `gateway-integrated-world-p06l-05` with the same
`physics-integrated-lane-01/pool.json` and P06J contact bundle. Original client,
canonical service, account inventory and physics worker remain unchanged.

**One next gate:** two-client ground, near/far rock, occluded-tank and live/wreck
regression, with actual native effect positions, materials and timing.
