# P07B — original #717 AoI and recipient interest source contract

2026-10-16. Night preparation authorized by the owner; native/manual gates are
deferred until morning. This document records static research, not a completed
P07B implementation or native visibility acceptance. No runtime source, client,
service or original file was changed or executed by this audit.

## Evidence and classification

`local/evidence/20261016-p07b-01/source-contract01.json` is
**PASS_STATIC_SOURCE_CONTRACT**, SHA-256
`d5e28d2a427454e075de34f81b3f25ef2649fe8777581fb9e253a94181d83dfb`.
It binds original executable SHA-256
`86f5e351d44c12e0d2b89ed741ee9a4e70d21f234c39aa9cfd709536d49f04ed`,
exact original PE instruction windows, original bytecode and the previously
pinned #717 ClientInterface registration table. Extracted native bytes and
bytecode stay in ignored local evidence. The original root was read from
`config/project.local.json`; no nearby executable or modern protocol was used.

The current audit reads bytecode as bounded data with `tools/py27_static.py`.
No client module import, `eval`, `exec`, process attachment, client input or
foreign server connection occurs. The initial historical P00 baseline manifest
path is absent after cleanup; the successful audit instead rechecks the retained
P02 roster source receipt and its original file hashes. A failed first lookup
does not constitute a source verification.

## VERIFIED_STATIC: native enter and leave wire

The original CRT registration names `leaveAoI` at initializer `0x16847d0`:
ID **0x0c**, kind **1**, length parameter **2**. This is a two-byte little-endian
variable payload length, not a fixed two-byte body. Its handler registration at
`0x1684475` assigns original handler **0xd6dd50** to `0x1f84d08`.

The exact body is:

```text
0c | payload_byte_length:u16le | entityID:u32le | eventNumber:u32le ...
```

The minimum payload is four bytes. There is **no flag byte, count field, alias
or reason code**. Handler `0xd6dd7d` reads four bytes for the entity ID;
`0xd6ddf6` divides the stream's remaining byte count by four; the loop at
`0xd6de26` reads that many four-byte event numbers. The sender should require
`payload_length = 4 + 4*N`, with bounded N. The receiver's division does not
justify sending malformed non-multiple-of-four tails. Signed interpretation
of event numbers is not needed for a zero-event vector.

Example for existing vehicle entity `0x09100005`, empty event vector:

```text
0c 04 00 05 00 10 09
```

Original `enterAoI` remains **0x0a / FIXED5**, `entityID:u32le, alias:u8`;
handler `0xd6dcc0` reads the ID at offset0 and alias at offset4, then calls
`0xd71270`. No visibility booleans are added. The separate
`enterAoIOnVehicle` message is **0x0b / FIXED9** and is not needed for a tank
which is itself an entity rather than a passenger on another entity.

Earlier P02 native evidence already establishes the mandatory server-entity
entry order: **enter AoI → actual requestEntityUpdate0x08/VAR2/entityID →
createEntityDetailed0x09/VAR2 → ACK/ready**. A cached server entity cannot be
assumed to skip this order. See [P02 arena entry](P02_ARENA_ENTRY.md).

## VERIFIED_STATIC: EntityManager behavior and client consumers

The original handler vtable starts at `0x17ca924`:

| Offset | Function | Observed static role |
|---|---|---|
| +0x0c | `0x5c8250` | enter AoI, including existing/pending entity branches |
| +0x14 | `0x5c84e0` | leave AoI, active/prerequisite/pending branches |

Connection handler `0xd6de47` calls the +0x14 slot with entityID and the event
vector. In the ordinary active branch, `0x5c8538` decrements entity enter-count
at +0xa8. Only when it reaches zero does the manager call `0x5c1c50(false)`
at `0x5c8590`, remove the active map entry, then call `0x5c1f30` at `0x5c85a4`.
`0x5c1c50` resolves and calls original Python `onLeaveWorld`. `0x5c1f30` clears
the entity's `__dict__` and sets its destroyed byte +0x45. Remaining reference
counts may delay memory release; this is not proof that a model or Python
object survives usable in a cache. Prerequisite and pending-entity branches
have distinct cancellation/count paths. Do not force all of them into the
active-entity assumption.

Original bytecode hashes rechecked against retained P02 source evidence:

| Original path | SHA-256 |
|---|---|
| `res/scripts/client/Vehicle.pyc` | `b81d08ca14092bb8912adb2eff20325c3dd23424868bc03164cfe6b8da50463c` |
| `res/scripts/client/Avatar.pyc` | `c13cd58a4c5d766dfd3c5f47ae7be50c962aee6c7f8cf25b4341322381f21e0e` |
| `res/scripts/client/ClientArena.pyc` | `30b21bb0e386b909d162f127b79b86e5da1aeecb65e9c6700b2b50f435dbd455` |
| `res/scripts/client/vehicleappearance.pyc` | `aa4f0c9ac4e830209c7929bd6c3aad1c19efec316c8cc7711f8b9211c893335a` |

The original Vehicle/Avatar consumer chain is explicit:

- `Vehicle.onLeaveWorld` line155 stops extras, calls
  `BigWorld.player().vehicle_onLeaveWorld(self)`, then asserts not isStarted.
- `PlayerAvatar.vehicle_onLeaveWorld` line1032 returns early for an unstarted
  vehicle; otherwise calls `onVehicleLeaveWorld`, `vehicle.stopVisual()`, saves
  model, clears `vehicle.model`, and passes vehicle/model to stipple `showFor`.
- `Vehicle.stopVisual` line614 destroys the native marker, destroys appearance,
  removes edge detection where relevant, calls minimap `notifyVehicleStop(id)`
  and stops local presentation physics. These calls are original behavior;
  no client-side visibility fabrication is required.
- `PlayerAvatar.vehicle_onEnterWorld` line995 first calls stipple
  `hideIfExistFor(vehicle)`. With Avatar init complete and a fresh unstarted
  vehicle it calls `startVisual()` then `onVehicleEnterWorld`.
- `Vehicle.startVisual` line562 recreates marker and presentation, applies
  current HP/death state and calls minimap `notifyVehicleStart(id)`.

These facts support a normal native lifecycle rather than sending exact hidden
positions and merely suppressing a marker. Duration/behavior of the stippled
last model, actual repeated reentry and minimap last-known-position behavior
remain **UNKNOWN / NATIVE_NOT_RUN**. Never hide the owner's own tank or Avatar
as part of an enemy interest calculation; this is an implementation policy
required to preserve input/camera ownership, not a recovered historical rule.

## Required sender boundary (INFERRED design, not implemented here)

Current `shared/mod.rs::visible()` means creation ACK received. It must remain
distinct from a server-computed recipient interest set. A visibility revision
must govern **all** routes before queueing:

1. Initial enter announcements and incoming entity requests: hidden enemy
   entities are not announced or described; arbitrary/stale requests cannot
   obtain a hidden entity snapshot.
2. Pose/rotation/gun angles, current HP and all entity properties.
3. Shooting/sound/tracer starts and ends, impacts and source/target references.
   A hidden shooter ID or muzzle position cannot leak through an effect.
4. Catch-up/reconnect and retransmission: no replay of historical fire when an
   entity becomes visible; recreate current state only.

Suggested bounded state per recipient/target: `Hidden → EnterPending →
CreatePending → Visible → LeavePending → Hidden`. Reliable enter, create and
leave receipts/epochs must prevent duplicate native enter-count increments.
Visibility lost while enter/create is pending must finish or cancel the
measured lifecycle in a coherent order; do not send an unpaired second enter.
Reliable bytes already emitted cannot be retracted. Do not queue new precise
state after the hide decision; retain prior reliable history exactly and put
leave after it. Delay reentry until the leave barrier is resolved, then use a
new interest epoch and the actual native request/create path.

P07 source does not establish a need to call `receiveVisibilityInfo`, set
`invisibility` or patch native marker logic for ordinary entity disappearance.
Those declarations alone do not authorize guessed method IDs or payloads.

Server terrain/static LOS can reuse the existing bounded
`shared/terrain.rs::nearest_excluding_many` query. Exact sight points, ranges,
camouflage, bushes, delay and spotting retention need separate versioned rules
and source classification. Existing projectile geometry is evidence of mesh
queries, not historical spotting semantics.

## Checks, limits and next step

Executed: original PE SHA/instruction assertions, registration table SHA and
ordinal assertions, vtable entry assertions, four original bytecode SHA checks
and bounded disassembly (22 selected records). Source receipt PASS. No gateway
build/tests were needed because no runtime file changed. No client/native
visibility test ran; disappearance/reappearance and on-wire absence are
**NOT_RUN**. No service endpoints were opened.

Reproduction uses `pe_interest_audit.py`, `pyc_interest_audit.py` and
`close_source_receipt.py` under the ignored evidence directory. Outputs are
append-only; use a fresh named receipt path for reruns. Example commands:

```powershell
python -B -X utf8 local/evidence/20261016-p07b-01/pe_interest_audit.py --out local/evidence/20261016-p07b-01/pe-leave02.json --va 0xd6dd50 --va 0x16847d0 --va 0x1684470 --bytes 352
python -B -X utf8 local/evidence/20261016-p07b-01/pyc_interest_audit.py --out local/evidence/20261016-p07b-01/pyc-interest02.json --module client/Vehicle --module client/Avatar --module client/ClientArena --module client/vehicleappearance
```

Rollback: remove/revert this research document; ignored receipts are inert and
need no runtime rollback. Next step: implement the recipient lifecycle with
the exact leave codec and packet-absence/retry tests, then owner native
occlusion/disappearance/reappearance control in the morning.

## Independent pure components — 2026-10-16

Owner authorized overnight dependent work without stopping for native checks.
While root owns P05C, these new files were prepared without modifying existing
runtime modules, module declarations, Session, native codec or server loops:
`shared/visibility.rs`, `shared/interest_wire.rs` and [P07B plan](../plans/P07B.md).
They remain uncommitted for integration in the later dependent P07B branch.
No behavior of the running gateway changes merely by adding these files.

### Stock mounted ranges: VERIFIED_STATIC

Fresh bounded original packed-XML and inert marshal reads:
`local/evidence/20261016-p07b-01/viewrange-binding02.json`,54388bytes,
SHA256 `98c47f50151d21b61d51cd8cf93ee4cd49bab4ec6c0d9aea175720ec0f793a22`.
The script checks fixed size/hash pins before inspecting values, verifies the
constructor/maker descriptor formats and decodes only the two literal mounted
descriptors. It never executes/imports a client module.

| Original source under res/scripts | Bytes | SHA256 |
|---|---:|---|
| `item_defs/vehicles/ussr/ms-1.xml` | 11839 | `a494bf04d29da7d066fd6923dbb75a79b947559a52405298c494a943c4b0c535` |
| `item_defs/vehicles/ussr/is-7.xml` | 5809 | `8d55fa4657a88f1436cd164afe11bade875a906fa7b97256f1fb2f803b09c10d` |
| `item_defs/vehicles/ussr/components/turrets.xml` | 2501 | `2a5927fc6bd030056c25fdca4cf70543b001560d03274b0661389ed2e80c5537` |
| `common/items/vehicles.pyc` | 125668 | `805240e4b59d8a75950dbb97b41c17867606e7e96d7ff0c8d7b05312b83ae8b6` |

| Mounted profile | Original field | Turret ID | Raw radius, metres |
|---|---|---:|---:|
| stock MS-1 | `/turrets0[1]/T-18_Standart[1]/circularVisionRadius[1]` | 23 | 240 |
| IS-7 | `/turrets0[1]/IS-7[1]/circularVisionRadius[1]` | 47 | 400 |

The same original MS-1 file gives280 for the alternate T-18_mod turret;240
must not be reused if a future admitted mounted profile changes turret.
`VehicleDescr.__init__:368` uses `<2B6HB` for the one-turret stock descriptor.
`makeCompactDescr:930` first packs chassis/engine/fuel/radio with `<4H`, then
turret/gun with `<2H`. The turret is the little-endian u16 at byte offset10:
MS-1 `010d1a000e00c90000001700170000`→23;
IS-7 `011c3a002400cd000b002f003a0000`→47. The original components table maps
those IDs to the exact turret names above.

These are source **base** radius values, not a verified final effective view
calculation. Crew proficiency, optics/binoculars, commander effects, camouflage,
bushes, historical spotting latency/retention and radio sharing are not derived
or modeled by this component. Using240/400 directly is explicit test_lab v1
policy, not a claim to reproduce the complete 0.9.1 spotting algorithm.

### Domain desired set API and LOS integration

`visibility::Actor` contains only domain slot, team, authoritative position,
authoritative sight point and mounted profile range. No native entity/method ID,
sequence, client coordinates or native-reported visibility enters this API.
`desired_sets(&[Actor],Allies,FnMut(SightLine)->io::Result<bool>)` returns a
bounded `InterestMatrix`; `desired_set` handles one recipient with the same
validation. Output contains only slot bitsets, not hidden coordinates.

Every invocation validates the whole snapshot before LOS:1..6 actors, unique
slots0..5, teams1/2, finite coordinates within±10000m, finite range(0,1000].
The1000m ceiling is a safety bound, not a historical maximum spotting radius.
Slot ordering is canonical, so permuting snapshot entries does not change query
order or results. There are at most30 LOS calls, independent of packet traffic.

`Allies::Always` is the accepted initial test_lab policy: own and allied tanks
remain interested. `Allies::RequireRangeAndLos` offers an explicit stricter
variant; own always remains interested. Enemies require inclusive Euclidean
3D centre distance within the **recipient's** range and a successful clear LOS.
Therefore an IS-7 can see an unobstructed MS-1 at300m while that MS-1 cannot see
the IS-7. Single-ray sight from supplied server points is a v1 approximation;
this audit does not establish original historical sight checkpoints.

The actual integration callback must use the current authoritative geometry:
`Terrain::nearest_excluding_many(start,end,&excluded)`, returning clear only
when the result is `Ok(None)`. This combines ground triangles with the retained
static-obstacle BVH. `obstacles::query_excluding_many` already enforces finite
query coordinates, sorted unique exclusions, node/stack traversal bounds and
stable source triangle identity. Never substitute `Ok(true)` when terrain or
static geometry is absent. Ground-only mode without the required static bundle
does not establish a clear line through buildings.

Build sight points from the transformed server profile joint plus a versioned,
documented lab offset. Apply the same coherent destroyed-object scene revision
as the authoritative publication; derive/canonicalize exclusions from applicable
removed projectile-mesh instances (`fragiles::State::projectile_excluded` and
any single destructible instance). Do not exclude intact walls or reuse stale
exclusions. The source query's two-sided closed-segment intersections, coplanar
miss policy and exported-map boundary are geometry facts, not historical spotting
rules. Root must handle endpoint/self-contact policy explicitly and fail closed
on missing geometry, invalid/zero-length segments or any query error.

Any invalid input or LOS error returns `Err` without a partial matrix. The
algorithm is stateless and retains no former permissive result. Root must stop
that publication on error and must not publish through the previous matrix.
Evaluate from one server snapshot at **every publication tick**, without a hidden
position keepalive or unproven hysteresis.

### Pure native lifecycle bookkeeping

`interest_wire::Book` is bounded to6 entries and stores only slots, booleans,
desired revision and reliable sequence numbers. `Book::new(own)` fixes the owner;
`set_desired(active,desired)` requires own active/interested and forbids interested
inactive slots. Invalid updates leave the book unchanged. There is no native
packet encoder or entity ID mapping in this file.

`transitions()` proposes at most6 actions. `mark_queued(action,sequence)` applies
them only after root successfully enqueues the native bytes in the **same Session
clone transaction**. An action carries the desired revision, so an old proposal
cannot be applied after a hide/show flap. Exact repeated marks for the same
sequence are idempotent; another enter for an already Announced/Leaving entity
is rejected. Multiple distinct actions in one reliable compound can share a
sequence. Native transport retries reuse the original bytes and sequence;
they do not generate fresh enter messages.

States are Hidden, Announced{enter_seq}, Leaving{leave_seq}. Announced stops
allowing requests/publication immediately when desired becomesfalse, before
leave can fit the output queue. Leaving never proposes enter, even if LOS
returns. Only a validated cumulative ACK **greater than** leave_seq, or selective
membership of exactly leave_seq, returns that slot to Hidden. A following enter
must use a sequence after the leave; stale action/sequence attempts fail without
mutation. Reliable sequence0 and selective ACK0 are valid initial native values;
optional sequence floors distinguish "none yet" from0. Selective ACK vectors
are bounded256. The root transport remains responsible for rejecting
future/invalid ACKs.

`request_allowed(slot)` requires desired+active+Announced, so enter has already
been queued before create. It does not impose an extra enter-ACK wait: root's
current native request handler permits a request after queued announcement and
the original request can arrive before a separate ACK datagram. Recheck the
live current-world desired set both at request acceptance and delayed create.
`announcement_sequence(slot)` exposes
the binding for external create state. `publish_allowed(slot,creation_acked)`
also requires desired+active+Announced and root's current creation ACK. **Root must
clear the previous creation/publication state on leave/new enter and bind new
ACKs to this announcement**; passing an old cycle's true boolean would defeat
that external barrier. The book does not pretend a native create succeeded.

The earlier per-recipient sender requirements remain mandatory for pose, aim,
health, shooting/tracer/sound/impact references, arbitrary entity requests,
catch-up and retry. These pure components alone do not inspect outgoing packets,
encode leaveAoI, validate original client callbacks or implement that filtering.

### Actual component checks and limits

First standalone visibility gate: `local/build/server/p07b-visibility-component01/`,
6PASS/0ignored. Combined std-only harness:
`local/build/server/p07b-components04/receipt.json`, **12PASS/0failed/0ignored**,
Windows GNU Rust1.90.0; compile/test exit0. Its commands/source/toolchain hashes
and full stdout/stderr are retained there. Test scope includes:

- exact range boundary, vertical distance, asymmetric240/400 mixed profiles;
- occlusion/clear/occlusion recalculation and authoritative sight endpoints;
- explicit own/allies policy, no LOS call for out-of-range enemies;
- six recipients/six targets, canonical query order and bounded queries;
- invalid point, duplicate/out-of-bounds slot, team, range and recipient errors;
- LOS failure after the first allow: no partial matrix or snapshot mutation;
- balanced AoI cycles, cumulative equality vs selective ACK and leave barrier;
- rapid LOS flaps, stale actions/retries, no hidden requests or early reentry;
- invalid owner/mask/ACK inputs and six independent bounded books.
- actual initial reliable sequence0, ACK0, leave1 and reenter2 barrier.

Frozen component source SHA256:
`visibility.rs`=`a52641ae407b0208c1ea27aced817b4442e9dc7309194dd67f5cfe4c2ca1c56c`;
`interest_wire.rs`=`f89fbae37627f260169bee0255e9c0aa2a321c928031192398111ea823dffe41`.
Combined02 was the earlier passing component snapshot with an unnecessarily
strict external announcement-ACK parameter on request_allowed. Root's current
native receive path does not require that wait;03 removes it and adds an
explicit check that queued enter allows the request while publication still
waits for creation ACK. No native behavior was claimed by either component run.
Component04 corrects the older zero-sequence rejection to the actual Window
contract: initial queue sequence0 and selective ACK0 are legal. Optional floors
keep that initial state distinct from a completed leave, and the added regression
exercises the real first sequence before the leave/reentry cycle.
Commands (fresh output paths are required for another run):

```powershell
python -B -X utf8 local/evidence/20261016-p07b-01/viewrange_binding.py
python -B -X utf8 local/evidence/20261016-p07b-01/test_visibility.py
python -B -X utf8 local/evidence/20261016-p07b-01/test_components.py
```

No Cargo/gateway/Jolt build or server/client launch was performed for this
preparation. Existing geometry/BVH tests were not rerun; the new pure tests use
a deterministic authored LOS callback and do not prove the actual map's LOS.
Integrated packet absence, effect filtering, retries/ACKs, native disappearance,
reappearance and mixed-client behavior remain **NOT_RUN**. P07B is unaccepted.
Rollback before integration: remove the two new modules, plan and this addendum;
existing runtime behavior remains unchanged. Single next step: root integrates
these components and the measured AoI codecs in the separate P07B branch after
P05C automatic gates, then performs wire/packet-absence/geometry checks.
