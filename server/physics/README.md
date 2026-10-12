# Authoritative map drive worker — test_lab

This small worker receives domain controls on its private stdin pipe and returns
server-generated state on stdout. It has no listening socket and does not receive
native method IDs, client coordinates, client clocks or a target pose.

The caller pins a local configuration by SHA256, which pins the original-derived
terrain and static obstacle manifests and buffers. Binary assets remain in ignored
`local/`. The current imported maps are `01_karelia` and `05_prohorovka`; these are
compatibility asset identifiers, not approved public display names.

The worker uses the existing locked JoltPhysicsSharp 2.22.0 dependency on .NET 9.
It settles for 180 fixed 1/60-second ticks before emitting `ready`. Every `advance`
request performs exactly six ticks; the parent is responsible for 10 Hz real-time
pacing, one outstanding request, and failing closed on timeout/overload. A missing
input line never causes unbounded simulation catch-up. EOF disposes the world.

Input (one ASCII JSON line, at most 1024 bytes; unique exact keys):

```json
{"version":1,"op":"advance","seq":1,"ticks":6,"input":{"throttle":1,"steer":0,"brake":false}}
```

Throttle and steering are integers −1/0/1. Steering is left/neutral/right.
An explicit stop is throttle=0, steer=0, brake=true. A brake with nonzero control
is rejected. Native cruise bits must be translated explicitly by the compatibility
layer; they are not a brake flag. Sequences are monotonic, starting at 1.

Both output events have the same fields:
`version,event,seq,tick,settle_ticks,map,config_sha256,state`.
`event` is `ready` (seq=0,tick=180) or `state` (matching seq,tick+=6).
State fields: `position` (original vehicle origin in world metres),
`direction` (yaw,pitch,roll radians), `speed` (signed forward m/s),
`rspeed` (world-Y rad/s), `contacts` (0..6), `linear_velocity` (XYZ m/s),
`angular_velocity` (XYZ rad/s), `wheel_contact_masks` (six integers0..63, one for
each last60Hz tick; bits0..2 left supports,3..5 right supports). No success state is written after an error;
the worker reports `worker_error` on stderr and exits nonzero.

The collision hull, six support rays, spring/friction/drivetrain coefficients and
controller are an explicitly approximate **test_lab** model. Original descriptor
mass/dimensions/speed limits should be sourced from the measured native export.
The speed thresholds cut motor torque; gravity can exceed them on a slope.
This is not a claim of historical 2014 physics. Initial static obstacles do not
simulate destruction unless the explicit one-object profile below is selected.
Four explicit server walls enforce map bounds. Shooting,
damage, water, other vehicles and battle results are outside this worker's scope.

Source ownership: this worker is maintained in `server/physics`. The old
`tools/map_drive_worker/MapDriveWorker.csproj` references these same files.
The canonical six-argument launch keeps the configured `spawn_origin`:

```text
MapDriveWorker.exe --local-root <local> --config <map.json> --config-sha256 <sha256>
```

The integrated two-client harness may append `--spawn-xz <x> <z>`. This is a
server-owned lane override: X/Z must stay within 12 metres of the configured
spawn and Y is always retained from the map configuration. The worker then
settles and reports the complete terrain pose at that lane; the gateway does
not translate the pose after physics.

P06N adds an optional, separate test_lab scene mutation profile. Append
`--remove-one <descriptor.json> --remove-one-sha256 <sha256> --generation <positive-u32>`
after the ordinary arguments (and after `--spawn-xz`, when present). With no
descriptor the original version-1 IPC and mesh construction are unchanged.

The bounded, hash-pinned descriptor has exactly these fields:

```json
{"version":1,"profile":"test_lab","map":"01_karelia","object_id":1,"instance_id":1513,"physics_manifest_sha256":"ea6ef22aed0fdd4e4826500c280a616737f8990ce7ab7cd808b9382227ec5ffd","projectile_manifest_sha256":"ccd28d8e3320d041e569e217a8c20e0285db0459bc2ef447c5bd95dd97d80cea","first_triangle":171814,"triangle_count":42,"object_revision":"karelia-instance1513-v1"}
```

Only that identity is accepted. The loader also checks the pinned physics
manifest's instance count and the selected chunk `[-5,-5]`, `/model[2]`, and
`content/MilitaryEnvironment/mle009_BoxCamouflage/normal/lod0/mle009_BoxCamouflage.model`.
The same 42 source triangles become a separate static body at startup. Every
other source triangle and coordinate is preserved in the base mesh. The worker
does not consume projectile geometry: its manifest hash binds the shared
descriptor, while the server separately verifies/imports that source.

This profile uses IPC version 2. Every `advance` additionally includes
`scene_version` (initially 0), which must equal the current worker scene. The
`ready`/`state` responses additionally bind `generation,descriptor_sha256,object_id,
object_revision,scene_version`. Pose fields and fixed driving cadence are unchanged.
The separate mutation request has exactly:

```text
version=2, op="remove_one", mutation_seq=1, expected_scene_version=0,
scene_version=1, generation, object_id=1, object_revision,
descriptor_sha256, config_sha256, advance_seq=<last completed driving sequence>
```

The `removed` ACK has exactly `version=2,event="removed",mutation_seq=1,
advance_seq,tick,generation,config_sha256,descriptor_sha256,object_id,
object_revision,scene_version=1`. It removes/destroys only that static body;
it does not advance physics, the driving sequence, or the tick. Repeating the
same mutation is idempotent, including after subsequent advances (with the
current `advance_seq`). Any mismatched identity/version fails explicitly.

The Rust bridge allows one pending operation, validates all ACK pins, exposes
`take_removal_ack`, and blocks advances until that ACK is consumed. The battle
coordinator must stop both lanes, obtain both acknowledgments, then commit the
projectile/world revision and native event. Partial worker failure cannot be
rolled back by this API: stop the battle and both workers explicitly. This
worker does not decide damage, destruction eligibility, native IDs, client
effects, or authoritative battle state. No generic map destruction is implied.

Build via `python -B -X utf8 server/build.py physics --out local/build/server/physics-check-03`
from the project root, using a fresh output directory. No bin/obj in sources.

The earlier source-layout card had two isolated builds and two successful
private-pipe worker smoke runs on this Windows host. Native drive evidence
and its partial manual acceptance remain in `docs/research/P02_MAP_DRIVE.md`
and `docs/research/P02_DRIVE_LIMITATIONS.md`. The later P06N single-object
removal/ACK contract above is covered in `docs/research/P06N_DESTRUCTIBLE_STATE.md`.
Linux ABI and cross-platform repeatability are NOT_RUN.
