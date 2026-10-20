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

P06O adds a separate catalog mode without changing the IPC1/IPC2 entrypoints:
`--destructible-catalog <catalog.json> --catalog-sha256 <sha256> --generation <positive-u32>`.
The version-2 catalog (at most128KiB) has exact keys `version,profile,map,
physics_manifest_sha256,projectile_manifest_sha256,objects`; profile is `test_lab`,
map is one of the source-pinned rows below. P06P adds Prohorovka through the
existing version-2 descriptor and IPC3; legacy IPC2 remains Karelia-only.

| Map | Instances | Physics triangles | Physics manifest SHA256 | Projectile manifest SHA256 |
| --- | ---: | ---: | --- | --- |
| `01_karelia` | 2918 | 335551 | `ea6ef22aed0fdd4e4826500c280a616737f8990ce7ab7cd808b9382227ec5ffd` | `ccd28d8e3320d041e569e217a8c20e0285db0459bc2ef447c5bd95dd97d80cea` |
| `05_prohorovka` | 3904 | 428597 | `9d358a48da303abaf15572f478dddc16971864960d9341943cc6d207b32b3265` | `3db1ad3859ae2f5fed678ac5f148005cff38a3c915bb33dde3303de22e22bef7` |

The descriptor, selected map, config and actual source manifest must agree.
The Rust `CatalogSpec::map_id()` retains that binding and rejects a different
map/arena identity in launch, scene requests, ACKs and ready/state decoding.
Whole-map tree geometry remains static: this mode does not implement falling
trees, collision transforms/replacement, or admit speedtree as a fragile model.
`objects` contains1..64 rows, ordered by strictly increasing positive `object_id`.
Each row has exactly `object_id,instance_id,first_triangle,triangle_count,
object_revision`. The revision is lowercase SHA256, each source instance is
unique, and its positive full triangle span (at most4096 triangles) must match
the pinned original physics manifest's model instance and nonempty resource.
Spans must not overlap. The loader preserves all original triangles/coordinates,
splitting admitted spans into independent static bodies. Body capacity is
max(32,catalog size+8); the other accepted physics parameters are unchanged.
The worker checks geometry identity; the importer/domain still decides which
objects are eligible, their HP/policy, and whether their destroyed state has no
collision. A catalog is not proof of native visual IDs or historical rules.

IPC3 uses the same1024-byte ASCII line bound. The first input must be
`restore_scene`, BEFORE any tank creation or180-tick settling. Its exact keys:
`version=3,op="restore_scene",generation,config_sha256,catalog_sha256,
advance_seq=0,scene_version,removed_object_ids,scene_sha256`.
The full list contains0..40 known object IDs in strictly increasing order;
`scene_version` equals its length. These bodies are omitted before settling.
`ready` confirms the restored revision/hash, so reconnect cannot briefly settle
on a collider that the authoritative battle already removed.

The canonical digest is SHA256 of ASCII `wot091-fragile-scene-v3` followed by
one NUL byte, the raw32 catalog hash bytes, then the ID count as uint32LE and
each sorted ID as uint32LE. For catalog hash `b` repeated64 times and an empty
list it is `3b4d76b3e9b6266fea62459b5d9d2567819a9851fc9abdc2c59640f8e089f81f`.
The bound40 describes the current ammunition-limited card, not the map's total
destructible count. No timer, tick, native ID, or JSON spelling enters this hash.

`sync_removed` has the same keys as `restore_scene`, with `advance_seq` equal to
the last completed driving sequence. The snapshot must contain every previously
removed ID. The complete delta is validated before removing any body; exact
retries do nothing. Shrinking/replacing the set fails explicitly. The ACK has
exact keys `version=3,event="scene_synced",generation,config_sha256,
catalog_sha256,advance_seq,tick,scene_version,removed_object_ids,scene_sha256`.
It consumes no simulation ticks or driving sequence. IPC3 `advance` additionally
requires `scene_version,scene_sha256`; `ready`/`state` additionally return
`generation,catalog_sha256,scene_version,scene_sha256`. All accepted pose and
six-substep driving semantics remain the same.

Rust exposes `CatalogSpec::load`, immutable entries, `Scene::new`,
`Worker::launch_with_catalog(...,initial_scene)`, `sync_removed`,
`take_catalog_ack`, and `catalog_scene` (available only after verified ready).
It checks all ACK fields against the exact pending snapshot before publishing
the scene and blocks advances until the caller consumes that ACK. The battle
coordinator must still freeze all lanes and publish domain/native changes only
after every worker acknowledges. Partial native removal failure is fail-closed:
terminate the battle/workers, not a claim of reversible physics rollback.

P06Q contact mode is a separate bounded profile. A worker catalog at
`version=3` has the same map and manifest pins as IPC3, plus `contacts=true`.
Each row has exactly `object_id,instance_id,kind,first_triangle,triangle_count,
object_revision`; `kind` is `tree` or `fragile`. A tree row must bind to a
`speedtree` source instance (the source resource remains the checked `.spt`
asset); a fragile row binds to a `model` instance. The catalog file is capped
at one MiB, rows at 1024, and a restored scene at 1024 removed IDs. IPC3 and
catalog version 2 retain their 64-object/40-removed limits and exact fields.

Contact mode uses IPC `version=4` for `restore_scene`, `sync_removed`,
`advance`, ACKs, and `ready/state`; every packet carries `contacts=true`.
Response lines are ASCII and capped at 32 KiB. The state adds
`object_contacts`, at most 32 rows with strictly increasing known object IDs:

```text
{object_id:u32, kind:"hull"|"wheel", substep:1..6,
 point:[x,y,z], normal:[x,y,z], velocity:[x,y,z]}
```

The C# worker captures hull contacts from Jolt body-pair callbacks and wheel
support contacts after each 1/60 s substep. The normal is kept in Jolt's body
order and oriented from the tank body to the catalog body; it is never flipped
to agree with velocity, so a separating contact cannot become a fake impact.
Velocity is the tank velocity captured before the solver step. Contacts are
bounded to 4096 raw events per six-substep advance; overflow, unknown body
identity, non-finite values, non-unit normals, or more than 32 distinct object
IDs fail the worker instead of silently dropping data. The server may use hull
rows for impact policy; wheel rows are observational and do not authorize
destruction by themselves.

P06R catalog v4 extends contact capacity to 2048 source-bound objects and
removed IDs, keeping IPC4 and its previous semantics. Catalog v5 selects the
separate `ram_policy="test_lab-fence-energy-v1"` response and IPC5. Every v5
object additionally has `ram_energy_j`: 8000 for admitted movement-only
fences, zero for legacy whole fragiles and trees. The domain v4 manifest
cross-checks this projection; the policy is approximate, not a reconstruction
of the original server's impact formula.

IPC5 uses the same scene/sequence/config/generation pins and bounded private
pipe. Its state additionally contains `fractures`, at most 32 receipts, ordered
by `order=1..N`. A receipt has exactly `object_id,substep,order,point,normal,
velocity,budget_before,budget_after,solver_before,solver_after,energy_j`.
The vector `velocity` is actual pre-substep velocity; the shadow budget is
reset to it each substep. Both actual and remaining budget must qualify for
the existing normal kinetic-energy threshold. Reserving a hit reduces the
positive normal component by `w - sqrt(max(0,w*w - 2*8000/mass))`.
Repeated manifolds of that object cannot reserve another hit. The first
decision for an object within a substep is retained for all its manifolds.

Only a reserved contact is a sensor. Once the ordinary solver finishes, the
same reducer is applied to its current velocity and recorded in the receipt.
It can only remove positive normal speed, never refund the velocity lost to
a surviving wall or terrain. The object body is provisionally detached after
that substep. The pinned native callback job system runs inline at concurrency
one; callback order is recorded, and only this Windows build is qualified by
repeat tests. This does not promise cross-platform determinism.

A nonempty receipt list returns event `prepared`, not `state`. The worker
refuses another advance until `sync_removed` includes every local prepared
ID. Commit destroys detached bodies once and removes any peer's additional
bodies. Retries neither advance ticks nor apply another velocity reduction.
The gateway validates receipts before staging domain state and poses; native
publication still waits for both workers' exact cumulative scene ACKs.
Malformed receipts, omitted commits or worker loss fail closed by stopping the
battle. There is no claimed rollback of a partly advanced physics world.
Two actors contacting the same object in the same discrete frame can each
spend their own impact energy; the domain transition and native publication
are deduplicated. This is a documented test_lab approximation.

P05B catalog v6/domain v5 explicitly selects
`ram_policy="test_lab-whole-object-energy-v1"`, retaining IPC5 and its bounded
receipt/prepared/commit contract. All existing source/native-joined whole
fragiles and trees carry `ram_energy_j=8000`; v5's fence-only projection is
unchanged. The new mode uses positive normal energy without the independent
1m/s total-speed floor. With the fixed approximate8000J threshold, normal
speed needed is about1.847m/s for4691kg and.484m/s for68190kg. Tangential speed
does not authorize a fracture or get debited by the normal-energy reducer.
Low-energy contacts and objects outside the catalog retain ordinary collision.
This repairs the pre-removal rigid stop of trees/crates; it neither admits
unmapped compound parts nor claims that8000J is historically correct for every
object. Mass and velocity come from the server body/profile. No client impact
claim or velocity restoration is introduced. Existing same-frame/multiple
actor and native-acceptance limits above still apply.

Catalog6 additionally evaluates the complete contacting body pair before its
first manifold returns solver settings. Candidate05 exposed an oblique fence
case where a weak first manifold cached rejection despite a later affordable
normal. Retrying later would leave an already emitted rigid constraint.
The first actual Added/Persisted hull callback now triggers a read-only
`NarrowPhaseQueryNoLock.CollideShape` for the exact hull/static-body pair.
It uses the pinned native defaults, world speculative separation and active
edge setting. A bounded collector copies only finite point/normal values,
selecting the strongest positive closing normal with a deterministic tie
break; all manifolds of that object share one admission and energy budget.
At most4096 query hits and32 distinct object decisions are permitted. Thread,
value and capacity violations fail the worker after the native update; a
faulted or wrong-thread callback cannot enter the mutable prepass.

No actual contact callback means no query or destruction. Other body pairs
remain ordinary solid contacts. A receipt can therefore describe a stronger
real shape-query contact than the triggering callback manifold; the published
hull contact is that exact admission contact. This is an explicit approximate
policy, not a claim that the closed historical solver selected the same
manifold. Catalog5 retains the original first-manifold decision and trajectories.

P05C adds a separate IPC7 entrypoint, preserving all arguments and schemas above:

```text
MapDriveWorker.exe --battle-scene <manifest.json> --scene-sha256 <sha256> --local-root <local> --generation <positive-u32>
```

One source-pinned manifest selects1..6 existing MS-1/IS-7 config3 projections,
server-owned spawns, one map and an optional existing catalog8. A one-actor scene
is for handling comparisons; battle admission still belongs to the coordinator.
One PhysicsSystem owns every tank, static mesh and catalog body. All controls are
applied before one60Hz update; all poses return in one batch after six updates.
Tank contacts remain solid Jolt contacts, with no added ram-damage policy.

IPC7 requires `restore_scene` before ready and `sync_removed` after prepared
fractures. A source-bound per-actor angular proof is retained. The first
qualifying actual catalog callback claims one object globally; other manifolds
see the same pending removal. One scene ACK commits all global removals before
the next advance. This is an explicit pinned-platform test_lab policy.

The complete schema, Rust integration API, actual-worker evidence and remaining
gateway/native gates are in [P05C_SHARED_PHYSICS](../../docs/research/P05C_SHARED_PHYSICS.md).

P04M physics preparation adds an opt-in IPC7 manifest version2. It retains the
same root fields, policy, pipe frames, scene ACK and192 fracture-claim ceiling.
Every actor additionally has `source_profile`: null for the existing MS-1/IS-7
projections, or a pinned `{path,sha256}` reference for precisely stock `t26`,
`t34`, `t3485`. Version1 remains unchanged. No legacy IPC1–6 profile is added.
Kind is explicit and checked against the complete binding; mass is not identity.

`Profiles/stock-definitions.json` is a small embedded derived source definition.
Its exact vehicle/component XML pins, selected Hull primitive member pins,
assembly weights and source wheel metadata accompany the complete physics and
handling projection. The source bounds/center, summed mass, support positions,
speed, torque and brake projection are recomputed before loading a profile.
All six supports deliberately use the equal main W_L/W_R group radius. T-26's
other three source radii remain metadata. This is an explicit laboratory
approximation, not a claim of native historical wheel/drivetrain fidelity.

Scenes containing a new stock kind use four native collision steps within each
outer1/60s update; the outer control/reducer tick and six-tick IPC batch stay the
same. The exact `collision_steps_per_60hz=4` and `motion_quality="Discrete"`
policy are pinned in every new definition. Old-only scenes keep one native
collision step, including manifest v2 with null old-profile references. No CCD
settings or quality overrides are applied. In qualification, the original
one-step T-26 head-on test exceeded the fixed5cm overlap limit (7.6316cm); the
four-step policy reduced that case to1.29mm without widening the gate. Actual
catalog8 witness/prepare/ACK checks are still required with this stepping policy.

The qualification authoring command requires an unbound, pinned source draft:

```text
MapDriveWorker.exe --qualify-stock-profile <draft.json> --profile-sha256 <sha256> --local-root <local> --source-root <verified-original-root>
```

It validates closed source/profile fields, bounded owned paths without reparse
points, exact source file hashes and exact bounded Hull package member hash.
The prior full-package hash remains labelled prior provenance: this command
does not rehash1.18GB to qualify one small member. It then constructs real Jolt
BoxShape bodies through the same settings factory used by IPC7, reads actual
inverse-mass, principal inverse-inertia and inertia-quaternion getter bits at
three body yaws, checks the scalar world-tensor basis and an independent box
inertia formula. The sole bounded JSON output contains `qualified_profile`,
three `basis_frames` and exact managed/native/worker build SHA provenance.

The profile remains `battle_admission=false`, with owner acceptance `NOT_RUN`.
Loading it on IPC7 v2 authenticates its complete definition and config projection;
actual body creation must still match every getter bit. This physics-only route
does not implement the P04M Rust scalar registry, ammunition160, owned inventory,
crew/layout, native rendering or admission. Those require separate integration
and actual checks. Existing Jolt2.22.0 and Windows x64 dependency pins are fixed.
`qualified_worker_sha256` records the authoring build's provenance; it is not an
equality requirement on later worker assemblies. The exact native getter checks
and fixed managed/native dependency pins remain mandatory at runtime.
