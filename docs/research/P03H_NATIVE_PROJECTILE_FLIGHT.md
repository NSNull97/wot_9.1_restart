# P03H — native projectile contract, 2026-10-07

Status: **PASS_OWNER_P03H_SAME_PC_SERVER_PROJECTILE_NATIVE_TRACER / ACCEPTED**.
The scoped same-PC card is accepted after the owner confirmed that both real
clients saw the tracer flight. Full P03 remains IN_PROGRESS. Raw pinned
resources/bytecode and local scripts are in
`local/evidence/20261007-p03h-native-projectile-flight-01/` (`E` below).
The original client and deployed server are read-only inputs.

## VERIFIED static contract

`E/sources.json` hashes the original Avatar, ProjectileMover, VehicleGunRotator,
projectile_trajectory and items.vehicles modules; `E/bytecode.json` stores bounded
disassembly without executing client bytecode. Original defs/PE-derived method
table: `local/evidence/20261005-p02-map-drive/wire/static-02/method-tables.json`.

- `Avatar.showTracer=0x4c`: fixed41 args, uint32 shooter, uint32 shot ID,
  uint8 effects index, VECTOR3 reference origin, VECTOR3 velocity, float gravity,
  float max distance. Avatar selection `0x13` precedes the call.
- `Avatar.stopTracer=0x48`: fixed16 args, uint32 shot ID + VECTOR3 endpoint.
  `explodeProjectile=0x57` is a separate variable callback; this card does not
  send it or assert a collision/damage result.
- Original showTracer can use visible gun model node HP_gunFire for the rendered
  start point. It preserves the server reference start point for trajectory
  computation. This is native presentation adjustment, not server pose input.
- Original ProjectileMover.add rejects duplicate shot IDs and starts from
  BigWorld.time() at receipt. There is no launch-time argument in this callback.
  Its local tracer solver reads scene geometry and can hide visual flight before
  a server lifetime callback. This is not proof of a server hit or damage.
- Original VehicleGunRotator.__getShotPosition uses hull position plus turret
  pivot and rotated gun pivot; pitch rotates the launch vector around local X.
  Reference origin is the gun pivot, not an invented barrel-length offset.
- `E/resources.json`: stock AP _37mm_UBRT1 raw speed442, gravity9.81, distance720;
  common miscParams.projectileSpeedFactor is **0.8**. Original reader multiplies
  speed by the factor and gravity by its square: effective **353.6 m/s** and
  **6.2784 m/s²**, maximum distance **720m**. The P03G aiming ratio g/v² is
  unchanged, so that card's aiming solver needs no angular correction.
- Shell effects are `smallArmorPiercing`, index **2** by original ordered
  shot_effects.xml enumeration. Native projectile models/particles/audio stay
  in local client resources; no assets or borrowed code are added to Git.

## Explicit laboratory policies / INFERRED

Zero spread, a flat server hull, immutable server launch parameters and analytic
ballistic integration. The monotonic server clock defines expiry at 720m radial
displacement from the origin; bounded root solving determines its exact time.
No terrain or vehicle collision is simulated or accepted in this card.
No historical crew/RNG or general artillery claims are made.

The original tracer's range/space boundary branches divide by velocity.x with
no zero guard. The zero-spread lab must avoid that singularity. A documented
server-side floor of 0.01m/s for absolute horizontal X velocity, preserving total
speed, is an approximate compatibility policy (maximum yaw change about 0.002
degrees for this gun). This is not a historical dispersion distribution.

Only accepted shots create projectiles. Start is published only for fresh events
and known, ready allied entities. Stops correspond to starts delivered/queued for
that recipient. Rejoin does not replay old effects. Reliable native frames have
bounded queues and immutable retries; the callback has no late-start timestamp,
so local delivery does not establish general network latency compensation.

## VERIFIED / OBSERVED runtime result

The canonical isolated build `gateway-shared-world-flight-05` passed 373 Rust
tests (EXE SHA256
`780dbd6d430e59d346b7ce383da6c91e4cf810d82ff2654fa10abc5dda4bc887`). The
legacy entrypoint passed 371 tests (EXE SHA256
`f4288d65209611293b1c9311bf534370f59261391fd27d6382b15612025ca775`). The
deployed gateway hash stayed
`daef0dde9e012beac4e0f363bf66b672ec4a154473be4b05b00cfe4cc0608c3b`.

In the fresh two-client stand, the independent crypto/channel audit covered
28,410 packet records and 28,402 channel frames for both peer slots with zero
errors. It verified 4 vehicle creations, 8,962 pose publications, 38 native
shooting cues, 38 `Avatar.showTracer` starts and 38 `Avatar.stopTracer` stops.
The server log records each accepted shot as a server-owned projectile with
the pinned effective speed/gravity and a bounded flight of about 2.03 seconds
to the 720m radial limit. Start and stop are queued once per recipient and
are not replayed after rejoin.

The passive native observer on each real client completed
`Avatar.showTracer`, `Avatar.stopTracer`, `ProjectileMover.add` and
`ProjectileMover.hide` for 19 observed shots. Bounded mover samples recorded
the projectile as present and then removed/expired. The owner manually
confirmed: «визуально вроде все окей, оба клиента видят» — the tracer fired
from either window was visible in the other window. The owner receipt is
`E/owner-acceptance.json`; native result is `E/native-02/result.json`, and the
wire audit is `E/capture-audit-06.json`.

The targeted Python control suite passed 4 tests. The established full Python
discovery run passed 2,050 tests with 4 known skips; the exact output is
`E/unittest-discover-01.txt`.

## UNKNOWN / outside this accepted card

Collision/armor/damage and a server-authoritative hit result are not
implemented. The server currently ends a projectile at the analytic 720m
range boundary; terrain and vehicle geometry are not consulted. Dispersion,
crew/equipment modifiers, persistence, garage inventory, IS-7 selection and
the independent full-P03 two-PC/LAN repeat remain NOT_RUN. The accepted test
profile still creates temporary allied MS-1s with zero spread and a flat hull.

The native observer is passive and does not mutate gameplay. A callback receipt
and an owner screenshot prove presentation and delivery for this run; they do
not prove historical bit-for-bit physics, damage, or latency compensation.
