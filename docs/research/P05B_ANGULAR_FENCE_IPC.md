# IPC6 exact field table — agreed Stage B design, no runtime authorization

2026-10-14. This supersedes only alternate names in the earlier proposal;
those original artifacts remain unchanged. Root plan fixes domain7/catalog8,
policy `test_lab-fence-linear-angular-energy-v1`, fence catalog response
`total_linear_angular_fallback`. Existing versions and their exact field sets
remain unchanged. All tables below are closed field sets: missing/extra/null
fields, duplicate JSON keys, wrong types or lengths fail the whole frame.

## Envelopes and source authority

IPC6 ready/state/prepared envelope retains the existing catalog envelope:
`version,event,seq,tick,settle_ticks,map,config_sha256,generation,catalog_sha256,
scene_version,scene_sha256,contacts,state`. Version is integer6, contacts is
boolean true, settle_ticks is integer180. Existing identity/seq/tick/scene
checks remain. `event` is ready/state/prepared with the existing transition
rules; ready seq0 carries no receipts or witnesses. A prepared frame requires
nonempty receipts and remains unpublished until its scene commit succeeds.

`scene_synced` retains exactly its existing IPC5 fields with version6:
`version,event,advance_seq,tick,generation,config_sha256,catalog_sha256,
scene_version,removed_object_ids,scene_sha256,contacts`. No redundant body
metadata on ACK. It remains bound to the already validated generation/config.
Requests retain existing advance/sync_removed field sets with version6.

Select 65536-byte JSON payload maximum (excluding LF) from the verified
catalog8 before reading; earlier catalogs keep32768 excluding LF. Exactly
65536 payload bytes plus LF passes the reader size gate;65537 fails. Old
32768/32769 boundaries remain. Existing4096 JSON nodes/depth12 remain. Do not choose the
buffer cap from the untrusted version member. Numeric lexemes are still
subject to the absolute byte cap; no truncation or receipt dropping.

## State and fixed body metadata

State keys are exactly the legacy base eight keys
`position,direction,speed,rspeed,contacts,linear_velocity,angular_velocity,
wheel_contact_masks`, plus `object_contacts,fractures,body_binding,
motion_witnesses`. Base fields and object contact row field sets retain their
current types. A contact velocity always means original PRE COM velocity.
For each fracture its contact is kind hull and exactly matches its object,
substep, point, normal and referenced PRE linear velocity; never substitute
point velocity or a wheel/query-only event.

| Object | Exact keys | Type/bounds |
|---|---|---|
| body_binding | inverse_mass, principal_inverse_diagonal, inertia_rotation_xyzw | f32, f32[3], f32[4]; exact expected native getter bits for the verified source profile |
| motion_witnesses element | substep, pre, post_solver | integer1..6, two full motion objects |
| pre / post_solver | com, rotation_xyzw, linear_velocity, angular_velocity, inverse_inertia_row_major | f32[3], f32[4], f32[3], f32[3], f32[9] |
| budget_after / solver_after | linear_velocity, angular_velocity | f32[3], f32[3] |
| legacy_linear_candidate | point, normal | f32[3], f32[3] |

Body binding is present at ready and every state/prepared frame, including
frames without fractures. It must equal the immutable approved lookup and
ready binding bit for bit, including zero signs. Lookup is chosen only after
the exact source profile/config3 projection, approved body constructor and
pinned native/managed artifact set are validated. Mass alone cannot select it.
Root's BODY_BINDING_PROPOSAL14a736... fixes the exact two-profile native values,
all14 source physical fields, handling object, tensor reconstruction and
source lever envelope. No new module-loader attestation is proposed.

Each witness is immutable native readback: pre before handling/Update, and
post_solver after Update before any debit. Witnesses are strictly increasing,
unique, at most6, and present for exactly the substeps named by receipts.
No receipts => empty witnesses. PRE tick and POST tick are derived from the
validated envelope sequence/substep and fixed6-step advance; no extra wire
timestamp may replenish a budget.

Raw9 values are native f32 row-major M11..M33, not a mirrored six-component
matrix. Exact body quaternion/principal metadata reconstructs the tensor with
the separately frozen scalar basis formula and tolerances. COM/point abs<=2000,
linear norm<=25, angular component abs<=20; finite and all kernel bounds apply.
The angular and legacy-selected points must pass the source2*radius PRE bound;
the angular point must independently pass POST. Invalid POST faults the whole
uncommitted advance, never a no-op removal.

## Ordered compact receipts

All receipts have exactly these common fields:
`object_id,substep,order,point,normal,mode,budget_after,solver_after,energy_j`.
IDs are known live catalog objects, unique within the advance; substep1..6,
order consecutive1..N with nondecreasing substep; N<=32; energy_j integer8000.

| mode | Additional required fields | Additional fields forbidden |
|---|---|---|
| normal_linear | none | legacy_linear_candidate, solver_branch |
| total_linear | none | legacy_linear_candidate, solver_branch |
| angular_corner | legacy_linear_candidate, solver_branch | all others |

The626 trees/9 ordinary whole fragiles allow only normal_linear. The403 fences
allow total_linear first and angular_corner only if the retained legacy
candidate does not satisfy BOTH old raw and shared COM admission predicates
(one failure suffices; do not require each to fail). For angular
mode Rust recomputes that failure at legacy_linear_candidate, then raw AND
remaining angular eligibility at the selected angular point. The parser does
not claim to prove query maximization; actual hull callback and bounded native
pair-query selection remain pinned worker/source responsibilities.

First budget state per substep is witness.pre v/w. First solver state is
witness.post_solver v/w. Every subsequent before state is inferred from the
previous receipt's serialized after state in that same substep. All modes
share these exact chains; none may reset to PRE/callback because its mode or
object changed. Linear modes leave omega bit-identical. Receipts carry no
redundant raw/before vectors that could disagree with the chain.

Wire solver_branch is exactly applied / noop_nonclosing / noop_quantized for
angular receipts only, recomputed by Rust. Pure helper noop_zero is defensive
and is NOT a new wire state: an unexpected such result fails IPC6 serialization
and validation until a separate reachable-case contract is reviewed. Incoming
invalid geometry/matrix/frame is an error. Unexpected arithmetic invariant
failure is also an error; only a finite candidate failing the frozen rounded
energy/rebound/output cap gates becomes the specified unchanged branch.
The8000J angular normal-mode predicate, positive rotational closing and
0.125J rounded accounting gate apply only to angular_corner. Existing
normal_linear/total_linear admission and debit arithmetic remain unchanged;
normal_linear arithmetic tolerance cannot relax any metadata/chain identity.

## Float equality and immutable proof ownership

All JSON numeric payloads are decoded to bounded finite f32 exactly once.
Do not perform f64 arithmetic on shortest JSON decimals before that conversion.
Preserve signed zero. Body binding, contact identities, chain values, omega
preservation and total/angular output equality compare `to_bits` values.
The ONLY retained legacy arithmetic tolerance is normal_linear's computed
v_after check, using its existing published tolerance/operator. It never
applies to metadata, witness equality, before-chain identity or zero signs.
The chain continues from the actual serialized v_after, exactly as validated.

Pure FrameProof contains physical profile identity, supplied body binding,
full witness list and complete ordered receipt list, with no network/session/
generation/map/native method IDs. A separate contextual wrapper binds source
slot/session/generation/seq/tick/config/catalog/scene and owns Arc<FrameProof>.
Each contact/event stores that full immutable reference and receipt index.
Domain and impact replay revalidate the full chain and their catalog/profile
authority. Parser approval booleans or isolated row hashes are insufficient.
Within a frame, all contacts must use the same context and same full proof;
unique receipt indices/object IDs prevent duplicate charging, and required
prepared IDs still equal the accepted atomic scene delta. A subset/reordered
proof cannot become a new seed or omit earlier energy debits.

## Final-state binding and unchanged pose trust boundary

If a receipt-bearing witness has substep6, final state linear/angular velocities
must equal the last ordered solver_after bits for that substep. The direct
rspeed field also equals final angular Y. The existing Program.State mapping
from COM/body quaternion to origin/MathF Euler/signed speed remains trusted
pinned worker code; this scope adds no new pose tolerance or reconstruction.
Earlier last receipt permits later native substeps, so those final values are
not falsely equated to an earlier snapshot. Test both cases and final-state
substitution of final v/w. Tensor reconstruction validates the supplied
PRE/POST orientation, but is not a proof that the unchanged legacy pose
mapping serialized that same quaternion. State bounds remain mandatory.

Controller and source reviewer agree with root on this table. Final structural
size is48244 payload bytes excluding LF (48245 including LF),2258 nodes and depth6. Root StageB GO remains required. This is not
implementation, worker acceptance, or native historical behavior.
