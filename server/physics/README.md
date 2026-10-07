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
simulate destruction. Four explicit server walls enforce map bounds. Shooting,
damage, water, other vehicles and battle results are outside this worker's scope.

Source ownership: this worker is maintained in `server/physics`. The old
`tools/map_drive_worker/MapDriveWorker.csproj` references these same files.
Build via `python -B -X utf8 server/build.py physics --out local/build/server/physics-check-03`
from the project root, using a fresh output directory. No bin/obj in sources.

The current source-layout card has two isolated builds and two successful
private-pipe worker smoke runs on this Windows host. Native drive evidence
and its partial manual acceptance remain in `docs/research/P02_MAP_DRIVE.md`
and `docs/research/P02_DRIVE_LIMITATIONS.md`; the layout card does not fix
pivot/destruction. Linux ABI and cross-platform repeatability are NOT_RUN.
