# P06I — stock MS-1 surfaces in the accepted integrated world

## Scope and evidence classes

Goal: preserve P03L physics/aim/ammunition/reload and stop a native tracer at
the nearest server-computed surface of the other stock MS-1. This is an
unresolved geometric contact, not penetration, HP damage or an armor verdict.
Branch: `codex/p06i-native-collision-binding`, base `cb8125f`.

VERIFIED: the descriptor and collision members are hash pinned by P06F before
export. Bundle schema `ms1-collision.v1`, 893 vertices/566 triangles in Hull,
Turret_01 and Gun_02; no client resource bytes are committed to Git.

- source revision: `ms1-717:b21e25230f1e5d35d9ae95a713622dfa9606a1b916a22bd0350a73c5f3fcce86`
- local bundle SHA: `e975427c05d40fc2850ad3829165f287cef9655092032c8e515b597a7a262e00`
- descriptor SHA: `a494bf04d29da7d066fd6923dbb75a79b947559a52405298c494a943c4b0c535`
- package SHA: `c2e16aef6fe7a7e44e476e2cb96e009b9f4eb7edab55fda2861601ba783415aa`

The gateway accepts only that exact bundle digest, within the configured local
root and without reparse ancestors. It validates component order, IDs, counts,
offsets, indices, finite coordinates and nondegenerate triangles before binding.
Binding is optional and explicit on the existing integrated route; no reduced
physics profile was substituted. Geometry is immutable and shared through Arc.

## Measured coordinate chain

VERIFIED static source: Vehicle.pyc SHA
`b81d08ca14092bb8912adb2eff20325c3dd23424868bc03164cfe6b8da50463c`,
`getComponents:477`, `collideSegment:521`; ModelHitTester.pyc SHA
`e5d51bdc1a7eadfb55d38b53e93748bee2dd78fd19554e18c519ee7a14d40726`,
`localHitTest:80`/`worldHitTest:85`; VehicleAppearance.pyc SHA
`aa4f0c9ac4e830209c7929bd6c3aad1c19efec316c8cc7711f8b9211c893335a`,
assembly at source line1652; VehicleGunRotator.pyc SHA
`d0105237b62447fee170cbf17984fd48437115087d6af6bf44743cc0cf68576a`,
`__getShotPosition:717`. These are original #717 source identities read as data.

Let h=(-.012,.894681,-.055245), t=(.013778,.421721,.08902),
g=(-.238144,.234668,.410043). In column-vector notation:

```
Hull   = h + v
Turret = h + t + Ry(turretYaw) v
Gun    = h + t + Ry(turretYaw) (g + Rx(gunPitch) v)
World  = chassisPosition + Ry(yaw) Rx(pitch) Rz(roll) Component
```

OBSERVED native Math mixed-angle basis and actual getComponents inverse
matrices support this chain. The nonzero gun-pitch inverse fixture closes the
gunPosition/pitch ordering check. No COM offset is added to the worker's chassis
origin. No guessed correction is applied to turret minimum Y.

OBSERVED local hit oracle: 72 rays (54 unique), 70 equal raw result counts,
104 aligned intersections with maximum distance difference 1.10e-6m. Two
directions through one hull surface produce one duplicate native result each;
all their locations match. Four horizontal rays at turret Y=-.25 miss in both
native and extracted geometry. This supports sampled surface placement; it
does not prove every BSP2 face or native result multiplicity is identical.
The duplicate/BSP2-bound cause remains UNKNOWN. Material names are labels only.

## RMB regression and full-pose aiming

OBSERVED owner report/video: aim held with RMB drifted after camera movement
on a slope. Static #717 free-camera mode stops tracking via Avatar0x8e;
Vehicle0x0f really is trackPointWithGun, not unrelated telemetry. Capture shows
shots36–38 used the same Hold and essentially identical velocity; no intervening
Point overwrote it. The old server interpreted hull-local angles using yaw only.
Both aiming and launch now use the complete authoritative chassis orientation;
gravity remains world-down. Hold remains a rate-limited request, not authority
to teleport the barrel.

OBSERVED independent native tilted getShotAngles: twelve samples from 5–547m.
Far samples differ by at most 7e-6rad. Close samples differ by up to .001262rad
yaw and .000369rad pitch; the cause is UNKNOWN. Tests retain explicit separate
near/far tolerances; they do not call these algorithms bit-identical. Native
event SHA: `4bb48fac175a4f4b8c29e72972ecfee6bbc9d62fb33365763287c65e413c7a83`.
The bounded iterative world-gravity solver holds prior angles on unreachable,
near-vertical or nonconvergent tilted inputs. Native pitch/rate limits remain.

Owner confirmed native01 with “сейчас все нормально” after the requested
Point → RMB Hold → camera movement shots on a slope. That receipt applies to
the full-pose/RMB behavior tested in native01. The later range-tail fix is
covered by the final regression test; native03 confirms startup only, not a
new native shot or range-tail contact.

## Runtime boundary

Each projectile segment queries only the other actor's current server pose.
The same computed candidate list enters the ordered impact trace and selects
the nearest endpoint. Query, stop, contact metadata and actor update commit
together. Terminal is `UnresolvedCollision`; no HP/crew/module state is altered.
The original showTracer/stopTracer methods preserve shot ID and endpoint in
both clients. A slow observer receives start before stop even if the first
observation already contains a stopped projectile. Reconnection does not replay
past effects.

Bounds: 40 shots, 256 segments per shot, 128 candidates per query and 25,720
trace events. Full 100ms cadence tests consume all ammunition for hits and
misses. A final fractional range tail is queried before RangeExpired; an expiry
between ticks waits for the next segment, at most one normal tick. Contact
duration is clamped to the exact range endpoint. Launch pose revision is
`wot-0.9.1-#717-ms1-ap-full-pose-v2`.

INFERRED approximation limits: target pose is sampled once per tick, not a
continuous swept moving body; flight uses segment chords, with normal 100ms
curvature error about7.8mm and larger error for delayed ticks. No projectile
terrain, rock, building or chassis-track query is included. Contact has no
native impact spark/sound, hit marker, ricochet, penetration or damage yet.
Shell dispersion is not claimed historically correct. This remains the explicit
stock MS-1/stock gun/AP laboratory binding; other vehicles require their own
verified descriptors/bundles. P06D classification/replay acceptance remains
NOT_RUN and was not faked by adding invented outcome rows.

## Executed verification and operational recovery

- Final gateway03: **429/429 PASS**, isolated pinned Windows GNU build.
  EXE SHA `741629de4597bb062b44a4cc849293847f7af351072ecc84a15f6eaddf7767de`.
- Focused Python checks: 34 collected,33 PASS,1 existing symlink-permission
  NOT_RUN (`test_server_layout` Windows account cannot create symlinks).
- Layout inventory:62 files,22 relocations, PASS. Pinned Python2.7.3 observer
  compilation and both client prepare/install/rollback ledgers succeeded.
- Native01:9 accepted shots,9 geometric contacts, both shooter slots,18 matching
  native stop endpoints (both clients). Full correlation receipt is below.
- Native03 final-build startup: one world, two ready workers/clients, 532
  snapshots per client in the audited prefix, both vehicles present and local
  prediction started. No errors in those prefixes; stderr empty. Repeat GUI
  shot NOT_RUN: Windows capture returned `window capture timed out` after
  binding refresh; no shot input was sent. This optional repeat does not replace
  native01 owner acceptance. The diagnostic clients/server were then stopped
  by verified PID/path to prevent continued capture growth on the near-full disk.
- Late native01 logging hit StorageFull after the completed nine-shot sequence.
  That tail is not accepted as an error-free run. A subsequent native02 restart
  also failed for storage; neither failure is hidden or called PASS.
- Recursive removal of our temporary build target was rejected by execution
  policy. Recovery used lossless NTFS compression of our build01/build02 target
  directories; the artifacts and receipts were retained. The failed rollback
  was retried successfully, and fresh native03 ledgers/runtime were created.
- The subagent's first noncanonical cargo invocation accidentally hit rustup's
  shim and installed1.58.1 before failing. All accepted builds used the pinned
  repository driver/Rust1.90.0. No toolchain change is required by this card.

Evidence root: `local/evidence/20261010-p06i-native-collision-01/`:
`ms1-collision.json`, `local-oracle-comparison.json`, `rmb-aim-static-audit.json`,
`native-contact-audit01.json`, `summary.json`, `source-layout-01.json`,
`capture-native01`, `capture-native03`, client runtime directories and install
ledgers. Build receipts: `local/build/server/gateway-integrated-world-p06i-03/`;
independent tilt comparison: `local/build/server/p06i-aim-native-target-01/`.
See summary.json for final native03 result and source/artifact identities.
`native-contact-audit01.json` pins completed prefixes (gateway 1,515,254 bytes,
A 2,488,821 bytes, B 2,510,278 bytes), not the failing late tail. Receipt SHA
`e47e03f0ff92e4b0d4c64da0957d7f8a4a6dd4dd74c7480a4502f8ff232afa85`.
`native03-smoke-audit01.json` SHA
`6a21ce44edfbde6a1f1bb4aa3c403134cee83baca15f8c74a972689f989bed85`.

## Reproduction and rollback

```
python -B -X utf8 tools/ms1_collision_bundle.py --out local/evidence/<fresh>/ms1-collision.json
python -B server/build.py gateway --test --out local/build/server/<fresh>
python -B server/check_layout.py --out local/evidence/<fresh>/layout.json
sr-gateway.exe legacy091-integrated-lab KEY DIGEST GATEWAY POOL CAPTURE ABSOLUTE_LOCAL_BUNDLE
```

The fresh bundle bytes must match the pinned SHA. The current native fixture
test expects the evidence-root bundle above (or project root via WOT091_ROOT);
missing fixture fails explicitly. Linux/cross-platform physics NOT_RUN.
Owned start_stand.py/prepare_stand.py in the evidence root contain the exact
local commands and record executable hashes without credentials in arguments.

Changed sources: shared/{geometry,pose,aim,projectile,impact,model,wire,server,mod}.rs,
main.rs; tools/ms1_collision_bundle.py and its tests; the passive diagnostic
client_patch/collision_oracle.py, sr_interactive.py and interactive_client.py;
STATUS, plan and this report. No original client bytes/canonical service were
deployed over. Roll back client ledgers on closed isolated copies, then start
accepted gateway-integrated-world-19 with physics-integrated-lane-01. Revert the
card merge for source rollback. The sole next recommended card is measured
material/contact classification before implementing damage.
