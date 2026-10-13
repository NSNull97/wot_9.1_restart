# P05B — bounded rotating-corner fence response

Date:2026-10-14 local. Card branch:`codex/p05b-tracked-handling`.
Baseline:`d747eec405e7e6c949fa42f5afcbe9e066266606`, runtime candidate14.
E:`local/evidence/20261013-p05b-tracked-handling-01/`.
Status: STAGE_A_PASS / STAGE_B_IMPLEMENTATION_GO, root decision2026-10-13
19:51UTC. The completed scalar review and bounded runtime ownership are
recorded below. This is an existing P05B
side-contact correction, not another roadmap card or historical-server claim.

## Evidence and intended difference

`night-contact-checkpoint01/receipt.json` binds unchanged runtime and completed
measurements. Actual IS-7 first selected contact has17324.64J normal-mode
energy, while the current COM-only ledger has19.52J. Evaluation of the same
world point on the captured pre-step full motion gives17491.64J; MS-1 gives
498.12J. See [diagnostic report](../research/P05B_CONTACT_DIAGNOSTICS.md).
Only an actual hull callback on the existing403 fences may use the proposed
fallback. Keep candidate14 total-linear choice first, and its exact debit.
Keep626 trees/9 ordinary whole fragiles on their current normal-linear rule.
No new coverage, resistance, static-force/dwell law, client/input behavior,
Space mode, source mass/speed tuning or fixed wall-clock compensation.

## Stage A: freeze and check the scalar kernel before runtime wiring

Controller agent owns an isolated angular-worker worktree; metrics agent owns
an isolated angular-gateway worktree. Root retains D: checkout, Python export
and docs. Existing dirty worktrees/P09B are preserved. No root production edits
by agents, no native client/service or automatic input. Source-audit agent
reviews the independent kernels/schema and tests; no worker launch in stage A.

Use actual f32 pre-step COM, v, omega and native inverse world inertia A, with
one shared shadow(v,omega) per substep. Actual callback/query point p and
normal n are evaluated on that frozen motion. This intentionally mixes current
geometry with pre-step motion, preserving the old linear ledger; it is not a
claim to have measured p before the step. No callback refill or independent
budget per mode/object. A native body binding must establish inverse mass and
principal inertia for each supported source profile before runtime wiring.

Keep all9 raw native tensor components as f32 bits. Form the symmetric kernel
matrix A=(raw+transpose(raw))/2 in f64. Stage-A proposal bounds raw asymmetry
by1e-12+8*2^-23*max_abs_matrix_entry and principal/body reconstruction error
by1e-12+16*2^-23*max_abs_matrix_entry per entry, plus finite/SPD checks.
Use exact reconstructed f32 inputs for scalar witnesses; shortest JSON decimal
tokens parsed as f64 are not the exact original f32 values. Preserve earlier
diagnostic analyses and add refinements separately, never rewrite their numbers.

Keep the reported f32 normal and all old linear arithmetic. Inside only the
angular kernel normalize it in f64 once, using
sqrt((nx*nx+ny*ny)+nz*nz) and component division, with no f32 Vector3 intermediate.
For r=p-COM, h=r cross n, u=inverse mass, c=(v+omega cross r) dot n,
d=u+h^T A h, the isolated static-contact normal energy is max(c,0)^2/(2*d).
Raw AND shared shadow states need closing>=0.1m/s, positive rotational closing
and energy>=8000J. Require finite/SPD/frame/source bounds. Angular fallback is
considered only when the retained old COM-selected candidate fails the old
linear predicate. It cannot override an existing successful linear choice.

The stable impulse for requested e is:

    J = 2*e / (c + sqrt(max(0,c*c - 2*d*e)))
    v_after = v - u*J*n
    omega_after = omega - J*A*h

Compute double intermediates over exact f32 inputs and cast each final
component once. For c<=0 or e=0 return unchanged. No per-component clipping,
pose change, pre-step output restoration or repeated rounding search.

Freeze the proposed conservative quantization gate BEFORE component runs:

- Shadow reservation spends8000J only when the rounded full-body energy loss
  lies in[7999.875,8000.125]J, total energy does not increase, resulting point
  closing>=0, total linear speed<=25m/s and every angular component<=20rad/s.
  Otherwise reject this angular candidate; do not lower the threshold, refill
  another budget, broaden tolerance or declare the candidate numerically paid.
- Post-solver, recompute r/c/d from actual current POST COM/tensor and ordered
  v/omega chain; request min(8000,normal energy). Nonclosing is an explicit
  unchanged-motion branch. If rounded bounds/nonincrease/nonrebound or
  abs(actual loss-requested loss)<=0.125J fails, use an explicit deterministic
  unchanged-motion quantization branch. Rust recomputes that branch exactly.
  This is a conservative engineering rounding rule, not historical behavior.
  Positive acceptance fixtures must exercise actual applied impulses; an
  all-no-op implementation cannot pass. Underpaid post-solver work is recorded,
  never refunded using pre-solver motion.

Required scalar cases: exact/adjacent8000 boundary, both source tensors,
zero/separating/tangent/unrelated angular axis, quaternion/tensor frames,
NaN/non-SPD/bounds, raw versus depleted shadow, linear/angular/normal mixed
orders, quantized no-op, stopped/separating POST and non-increasing full energy.
Use exact C#/Rust witness components and explicit result branches. Independent
calculation verifies conservation bounds; tests must not just echo the helper.
Preserve failures. If this policy fails practical source fixtures, stop before
runtime and revise a separately recorded contract; never widen a gate silently.

## Stage B review: required before runtime implementation

Private proposals in `night-angular-proposal01/PROPOSAL.md` and
`night-angular-gateway-design01/` define remaining interfaces. Freeze exact
schema, native body binding, output bounds and file ownership after stage A.
Candidate versions: domain7 / worker8 / IPC6,
`test_lab-fence-linear-angular-energy-v1`, fence response
`total_linear_angular_fallback`. Retain all older versions and artifact outputs.

### Body provenance and geometry envelope frozen before stage-B tests

Accept the bounded design in
`night-angular-review01/BODY_BINDING_PROPOSAL.md` (SHA256
`14a73604599fb39967f3d877784cb4c17820048887f0dea2eb4282b77ed2f105`),
supported by the11200-row offline getter audit
`body-binding-analysis01.json` (SHA256
`3f5a530bf54a0cdfe06e35fee2d859d86967765c02d8e7e658e09a1fadd46081`).
This freezes the following design choices; runtime wiring is still NOT_GO
until numerical tests, exact JSON schema and the stage-B decision below.

- Only the two existing config3/profile2 source profiles are eligible. Require
  their complete pinned profile SHA, all14 physical fields and handling object;
  never select inertia by mass alone. Map paths/spawn/yaw may vary only through
  the existing verified config projection and scene context. Other loadouts
  require separate binding evidence and remain unsupported by this policy.
- `body_binding` occurs once in every IPC6 ready/state/prepared motion frame:
  `inverse_mass`, `principal_inverse_diagonal[3]`,
  `inertia_rotation_xyzw[4]`. Reject extras and compare all f32 bits, including
  zero signs, against the immutable native-getter lookup. ACK envelopes keep
  their existing generation/config/catalog/scene binding. Full domain/trace
  proof retains the body binding and its approved profile identity.
- MS1 inverse-mass bits395f8781 and principal390ec909/3919bf9b/3a25f4bb;
  IS7 inverse-mass3776094c and principal363bac7f/365da392/3775d3e2.
  Both native inertia quaternions XYZW are3f3504f3/3f3504f3/00000000/00000000.
  These are observed pinned-platform getter values, not historical formulas.
- Raw tensor order is M11,M12,M13,M21,M22,M23,M31,M32,M33. Reconstruct
  `(R_body*R_inertia*diag(principal))*transpose(R_body*R_inertia)` with the
  scalar association in the proposal; use the frozen asymmetry/frame gates.
  Native constructor and artifact hashes are part of the final build receipt.
- For angular fallback only, bound both selected and legacy candidate PRE
  arms by `dot(p-COM,p-COM)<=4*((hx*hx+hy*hy)+hz*hz)`, promoting the approved
  f32 source half-extents to f64. Check the chosen angular point again against
  actual POST COM. An invalid POST frame/arm faults the entire unpublished
  advance; it cannot become a successful no-op removal. This2*hull-radius
  envelope is a project rejection bound, not surface membership or a claimed
  limit on solver corrections. Actual geometry/query selection remains the
  trusted pinned-worker boundary. Old successful linear paths keep their rule.
- Existing exact artifact-set/hash verification remains mandatory before
  launch. The binding additionally requires the pinned managed/native members
  specified in the proposal. Loaded-module-path attestation is UNKNOWN; this
  phase retains the local loader trust boundary and adds no new loader logic.

Selection must include successful shadow rounding reservation before ranking
angular candidates, so an unpayable highest-energy point cannot hide a payable
candidate. Selection does not mutate/refill the shared budget; only the final
admission spends it. Generic scalar-only result names cannot silently expand
the three frozen IPC solver branches.

The prepass keeps its old COM-ranked candidate and independently selects an
eligible angular candidate in the same bounded actual-pair query. Rank angular
candidates by min(raw,shadow normal energy), then exact existing bitwise tie
break. One pair decision precedes any solid constraint, no later-manifold retry.
Retain4096-hit/callback and32-receipt limits, one removal per object/advance.

New IPC carries at most six shared pre/post motion witnesses and compact
ordered typed receipts. An angular receipt also retains the old linear-selected
point/normal, so its linear-first rejection can be recomputed. Carry a checked
full immutable frame proof and receipt index through worker parsing, shared
world admission and impact replay; never
substitute point speed for COM velocity or bypass domain validation. Native
identity/scene binding, prepare/both-ACK/rejoin semantics remain unchanged.

The [closed IPC6 field contract](../research/P05B_ANGULAR_FENCE_IPC.md)
freezes the schema, exact float identities, complete proof ownership and the
unchanged pose-mapping trust boundary. Its final source table SHA256 is
`e0d8406c3f660461075e046d417a0e37cf79ef1bf4f115cd6aa153adbaf16345`.
The final spelling produces a structural estimate of48244 JSON payload bytes
(48245 including LF),2258 nodes/depth6. Earlier48237B estimates remain saved
in `night-angular-gateway-design01/budget-final02-receipt.json`; they are not
silently rewritten. The new IPC6 payload cap is65536 bytes excluding LF;
older versions retain32768 excluding LF, including their exact boundary.
Keep4096-node/depth12 limits. No unbounded reader, truncation or extra receipt
capacity. Include accepted/rejected boundary serialization tests.
For IPC6 scene ACKs retain the2048-element removal-array capacity but use the
new frame's4096-node limit explicitly: the older ACK reader reuses the40000-node
extended-catalog parser. Do not inherit that larger node budget into IPC6 or
shrink a valid2048-ID ACK to the ordinary1024-element array limit. Earlier ACK
parsing and catalog-manifest limits remain unchanged.

Post-step impulse nonincrease does not prove every simultaneous solid-wall
constraint stays satisfied. Define no-refund as no restoration of PRE motion
and no increase in actual total kinetic energy; real wall/contact regressions
must additionally check physical outcomes. Do not claim a multibody solver
equivalence from the single-contact formula.

## Integration gates, reporting and rollback

Stage-B decision: GO for implementation within the existing authorized night
task, after [Stage A](../research/P05B_ANGULAR_SCALAR_GATE.md) passed both
independent kernels, oracle review, source-mass mixed chains and the exact
body/schema freeze. This is not native/physical acceptance. Root integrity
receipt `night-angular-stage-a-root01/receipt.json` confirms unchanged262
runtime sources; independent final review is
`night-angular-review01/stage-a-final-review.json`. No numeric gate changes.

Exclusive implementation ownership:

- Controller: isolated angular-worker checkout, physics Program/CheckedInput/
  FractureResponse, new scalar/support code and applicable linked components.
  Preserve TrackedHandling, body constructor and all old modes. Callback
  validation faults must escape only after native Update returns.
- Metrics: isolated angular-gateway checkout, worker/catalog/fracture/profile,
  pure shared response and bounded full-frame proof, shared model/fragiles/
  impact/server validation and relevant tests. No client/cadence/P09 changes.
- Root: Python exporter/tests, exact source/export/build integration, docs and
  bounded regression harnesses. Export option `angular_fence_response` /
  `--angular-fence-response` is exclusive with the three previous options.
- Source audit: independent source/schema/test review; no production mutation
  or shared service/process control. New actual worker matrices need a frozen
  bounded fixture/run contract before launch and retain every failed attempt.

Root integrates reviewed patches sequentially. Worktree builds/components may
proceed independently with fresh output/source pins and disk checks. Actual
physics runs and gateway acceptance follow the new catalog/build binding;
they are not implied by the successful scalar phase.

Only after stage-B GO: implement separate reviewed patches in the isolated
worktrees and root importer/tests, integrate sequentially, build candidate15
with disk-space check and new source/artifact/catalog manifests. Allowed areas
are physics response/input/program, gateway worker catalog/parser/profile and
pure response math, shared contact/model/trace validators plus their tests,
compound catalog exporter/tests, versioned docs/build inputs as necessary.
Do not change cadence, control/grip/coasting, networking, P09E or live accounts.

Require repeated actual IS-7 angular fracture and MS-1 below-threshold control,
static/tangent/wheel negatives, ordered finite mixed budgets, no free repeat,
actual both-worker ACK and fresh rejoin, source profiles and separate all-alive
map coverage. Retained14 moving-side/clear-chain/normal/wall and handling must
match where the new fallback is not exercised; document genuine changed cases.
Passage is separate from a receipt. Run applicable Python/C#/Rust checks and
fresh full gateway gate before preparing any morning stand. Native owner tests
stay NOT_RUN until after09:00; no merge while those remain open.

### Source catalog gate — 2026-10-13 19:57UTC

Root added the mutually exclusive `--angular-fence-response` export option.
The actual pinned native join passes25 Python tests and the CLI export:
1038 objects/119 chunks, exactly403 existing movement fences on the new mode
and635 unchanged normal-linear objects, all at the retained8000J project cost.
IDs, masks, geometry, health, source inventory and old catalog bytes stay exact.
The existing moving export still hashes to9f54f371.../9c40f5bd....
Evidence:`night-angular-export01/receipt.json`, SHA256
`ec7160af566ca581058bb0f9caa8116607a07db1fe775e0db9d9a7445dd26c39`.
New domain7 `catalog/manifest.json`:
`1dca4febb0bc4921263682f82b927e26c33248c5b837a885f075245adf948f99`.
New worker8 `catalog/physics-removals.json`:
`41c0d9ccfd5b608a07e80a4eb68a3b6ed70bacffdd1444bb58c3f2ebb179bea9`.
Exact commands, source hashes and logs are in that directory. No physics worker
or client ran in this gate. Runtime implementations remain in isolated review.

The canonical build driver currently accepts Cargo's successful zero-test
selection as a passing targeted gate (its isolated ignored gate already rejects
it). Before using the new saved-frame filter, reject a total passing count of
zero for every requested test run. This changes acceptance reporting only,
not Rust execution or game code. Check positive/empty/failing transcripts and
the retained actual full/targeted logs; retain that validation separately.
Implemented and checked:5 Python accounting tests PASS in
`night-angular-build-accounting01/receipt.json`. Existing755/1 Rust result logs
were read and retain their counts; Rust and workers were NOT_RUN in this check.

The first-eight actual-worker design is frozen in
`night-angular-stageb-review01/ACTUAL_WORKER_MATRIX.md`, SHA256
`980b0845112f21477a8a7bd3826de9bd75e8723ea351a96af74b3dc73a3ea955`:
two exact repeats of source IS7 pivot, MS1 low-energy pivot, MS1 clear chain
and IS7 clear chain, each180 settle ticks and120 fixed advances. All source
physical fields/handling stay exact. Four older capped fixtures are excluded
from worker8 binding and remain old-catalog regression inputs only. The runner,
reviewed candidate15 and saved-frame full Rust proof decoder must be pinned
before this design becomes an actual run. A raw transport capture by itself
cannot pass the new proof/domain gate. All eight new runs remain NOT_RUN.

On failed prototype keep candidate14 unchanged. On failed integrated experiment
revert only its own unaccepted patch to the pinned baseline; retain all evidence,
owned-child exit receipts and isolated worktrees. Stop/reap exact children only.
Before a future native launch make a fresh source binding/passive preflight;
the old2d66203 morning bundle is preserved, not rewritten or treated current.
Next automatic action: review and integrate Stage-B worker/gateway patches,
then bind the fresh candidate15 build and first-eight actual-worker runner.
