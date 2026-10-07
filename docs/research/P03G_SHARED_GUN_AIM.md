# P03G — native shared aiming, 2026-10-07

Card: `codex/p03g-shared-gun-aim`; original client #717. All raw data and
read-only inspection helpers are ignored under
`local/evidence/20261007-p03g-shared-gun-aim-01/` (called `E` below).
No borrowed implementation or client assets are added to Git.

## VERIFIED: pinned original protocol and data

- `E/sources.json`, `bytecode.json`: original Avatar, Vehicle,
  VehicleGunRotator, gun_rotation_shared, projectile_trajectory and vehicle
  resource readers, with file hashes. The rotator cannot start while its
  maximum turret speed is None. Original `PlayerAvatar.updateTargetingInfo`
  supplies both rates/initial angles and starts it. The previous shared binding
  did not send this callback.
- Original `Avatar.ClientMethods.updateTargetingInfo`: method `0x4b`, nine
  FLOAT32 arguments: yaw, pitch, turret rate, gun rate, dispersion multiplier,
  turret dispersion factor, movement factor, hull rotation factor, aiming time.
  Native method table: P02 map-drive `wire/static-02/method-tables.json`, SHA256
  `f63fab8f43d204d4a6fc9d819b21321ca46558e23108370d1c2b878fb4072429`.
- Original input: Avatar base `vehicle_trackPointWithGun=0x8f` (VECTOR3),
  `vehicle_stopTrackingWithGun=0x8e` (two FLOAT32); Vehicle cell
  `trackPointWithGun=0x0f` (addressed entity + VECTOR3). Each has VAR2 length.
  `VehicleGunRotator.__updateShotPointOnServer` selects cell versus base route
  using the currently bound own Vehicle. These are intents, not trusted poses.
- Original `Vehicle.gunAnglesPacked`: indexed UINT16 property 2, ALL_CLIENTS,
  unreliable/latest-only declaration. Pinned PE registers dynamic property
  range at `0x9e`, yielding `0xa0` for this simple property. The selected entity
  is set with `0x12 + uint32`, restored to Avatar with `0x13`.
  Native reception below independently checks this inferred wire use.
- Original angle serializer uses ten yaw bits biased by pi and six pitch bits
  across the actual absolute limits. Native neutral seed stays `0x8030`.
- `E/resources.json`: stock T-18 / T-18_Standart / _37mm_Gochkins, nominal
  turret/gun rates 39 / 52.5 degrees/s; pitch -25..+8 degrees; rear sector 35
  degrees, rear maximum pitch +1 degree. Constants.pyc supplies transition
  0.4 radians. Positive pitch points down. AP speed/gravity 442 / 9.81.
  Turret pivot sums to (0.001778, 1.316402, 0.033775); gun pivot is
  (-0.238144, 0.234668, 0.410043). Turret-local overrides give aiming time 2.5s.
- Dispersion inputs use original reader conversions: 0.16 per degree becomes
  `0.16/radians(1)`; 0.42 per km/h becomes `0.42*3.6`; 0.42 per degree becomes
  `0.42/radians(1)`. Multiplier 1 is explicitly nominal laboratory policy,
  not proof of historical crew/equipment coefficients or shot RNG.

## OBSERVED: two real clients, first native run

Gateway build aim-01, battle `13043401772469146894`, both real isolated native
processes: the original initializer completed, rotators report started=True,
original cell aim commands reached the server, and original
`Vehicle.set_gunAnglesPacked` completed on both entities on both clients.
Initial native targets moved the serialized seed from 32816 to 32895.
No helper assigned a target, turret matrix, entity property or filter state.

The first independent capture audit (`E/capture-audit-01.json`) inspected
2585 packets / 2577 frames, four creations and 791 pose+angle publications,
with zero errors. Account-to-world slot order is established from native
binding, not assumed from process launch order.

Each client also called the original **pure math functions**, with an identity
matrix and eight fixed points, without issuing game commands. Samples include
front/right/rear, elevated/depressed, distances 5, 100, 720 and 10000m.
Against these samples the independent server solver's maximum differences
were about 0.06921 degrees yaw and 0.01414 degrees pitch, below the respective
wire bins (0.3515625 and 0.5238095 degrees). The rear limit transition matched
15 native samples (120..145 degree transition, then 1 degree rear stop).
These measurements are preserved in native traces and exercised as regression
vectors; they do not establish every input or the historical server algorithm.

## INFERRED and explicit laboratory policy

The independent flat-hull solver transforms a world target through the
server-owned hull yaw/pivots, solves lateral gun offset, then the low ballistic
arc. Its normal tested directions agree closely with the native solver.
Historical fidelity remains **approximate**: native iteration/degenerate
targets, all hull orientations and historical crew multipliers are not proven.
Unreachable ballistic targets use geometric direction; extremely close points
hold the current angles. There is no projectile or hit implementation here.

The server retains one validated intent per actor; it controls current angles
with its monotonic step and pinned nominal angular speeds. Stop-tracking angles
are rate-limited desired angles, never an immediate pose assignment. Disconnect
parks current angles; rejoin initializes from current state. Unknown/wrong-owner,
nonfinite, malformed and late-poison records fail before command/ACK commit.
Startup intents can wait for native correction acknowledgement; no pre-ACK aim
motion is applied. The two temporary allied actors are already mutually visible.

This lab sends current angle properties alongside 10Hz shared pose snapshots
through the existing bounded reliable channel. This deliberately differs from
the original unreliable/latest-only property hint: up to four pending frames,
exact reliable retransmissions, and no accumulating list of unsent old angles.
Only acknowledged created entities receive these updates. This is sufficient
for local laboratory delivery, not a latency/loss or production claim.

## OBSERVED: owner run on the final build

Owner message: “вроде все по этим тестам корректно”. The original plan's
same-PC continuous aiming/shot regression criterion is accepted. Audit of the
complete saved run: 28492 packets, 28484 frames, 9137 pose+angle publications,
12 shot cues, zero errors. Frozen native traces contain 457 snapshots each and
9126/9118 completed angle callbacks matching the exact captured wire prefix.
Six remaining sent properties per peer (three frames) have no completion after
the clients disconnect; delivery is not claimed for those trailing frames.

Observed yaw ranges include approximately -32.7..89.3 degrees for one vehicle
and -61.9..99.5 degrees for the other; pitch changes are recorded on both, with
one reaching the full -25..+8 degree range. A literal 360-degree sweep was not
observed. Each native process completed the original shooting callback six
times. A fired five own shots (AP20→15), B one (AP20→19); the requested two
own shots on each client were not recorded. Repeated-fire regression is
therefore observed on A, with both peers rendering all six shot events.

These facts and the exact owner wording are preserved in `E/owner-acceptance.json`.
The current closure changes documentation/evidence only; tested runtime hashes
still match `bbf4eac375676ffd8cf2dc60ebdf804653fd2b20`.

## UNKNOWN / outside this acceptance

Two-PC/LAN, terrain
physics, the previous colored-grid artifact, projectiles/hits/damage, visibility,
equipment, persistence and warm leave-to-hangar remain separate boundaries.
The original client, prior research client and deployed gateway are untouched.
