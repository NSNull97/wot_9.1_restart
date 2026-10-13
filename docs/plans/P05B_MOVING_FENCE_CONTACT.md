# P05B moving fence contact: bounded implementation B

Status: AUTHORIZED IMPLEMENTATION within the existing overnight P05B scope. Starting checkpoint9f384fa (candidate13); fresh gateway736/736 and night13-checkpoint.json preserved. Root selected B as a bounded addition to the existing explicit test_lab energy policy. No historical or native acceptance is implied. Parent P05B remains the card; this is its bounded implementation phase.

## Goal and exact scope

Repair moving grazing contact for the403 already source/native-joined Prohorovka fence sections. Retain normal-energy response for626 trees and9 ordinary whole fragiles. Preserve all1038 object identities, full geometry spans,119 chunks/native joins, source HP, projectile behavior and native destruction encoding. Do not add any eligible objects or change steering/cadence. Static pressure, stationary pivot against a fence, query-only removal and universal destructible coverage remain OPEN/out of scope.

Version occupancy checked in current importer and both catalog readers at HEAD1a3788f plus current working tree: domain reader max5; worker reader max6. Domain6 and worker7 are unoccupied; the worker7 occurrence is an unsupported-version negative, not an implementation. Proposed versions are therefore domain6 / worker7, policy `test_lab-fence-total-energy-v1`, profile `test_lab`. Keep all previous version/policy parsing and exported bytes unchanged. Recheck occupancy at GO if another writer has intervened.

## Frozen contract for implementation review

- New catalogs retain8000J for every existing eligible object. Add required per-object `ram_response` in these versions only, exact values `total_linear` / `normal_linear` in BOTH domain and worker entries. Old versions reject this field. `total_linear` is allowed only for the existing joined movement_fragile fence class; ordinary fragile/tree use `normal_linear`. Worker `kind=fragile` alone is insufficient because it currently merges the two domain classes. Exact domain-to-worker projection must compare the discriminator, energy and every existing identity/geometry field. Root exports only the existing403 fence IDs; the seven accepted gaf010/011/012 resources are recorded in fence-source-summary.json, not inferred from arbitrary names. Pinned catalog hashes and importer provenance remain the source boundary.
- Admission requires an actual Added/Persisted hull callback and existing bounded exact-body prepass; no query-only break or wheel-only break. Keep owner-thread/fault checks, native callback exception containment and4096 pair-hit/32 receipt bounds. Reuse the actual-callback-triggered prepass for worker7 as for worker6.
- For a `total_linear` fence, both actual pre-substep velocity and shared remaining budget must be finite, bounded, have total speed<=25m/s and incoming normal dot>=0.1m/s; require total linear kinetic energy>=8000J. Products/comparisons use double over exact f32 components in C# and Rust, as existing admission does. No separate1m/s floor. Pure tangent, separating and zero COM speed remain ineligible. These are project guards, not the historical client predicate.
- Fence debit R(v)=zero when E(v)<=8000, otherwise v*sqrt(1-8000/E(v)), E=0.5*mass*sum(v_i*v_i). Evaluate E/factor in double; cast each final component to f32 once. Fix shared tolerances and boundary vectors before using them in gates. This changes tangential/vertical linear velocity but leaves angular velocity untouched. No component reversal/energy increase. Non-fence normal debit/admission remains byte-for-byte the previous implementation unless a strictly necessary type dispatch is added around it.
- One shadow velocity per substep, shared across every object/policy. Record order is deterministic and bounded. Check eligibility before debit; each unique object costs once per advance; no per-object/per-policy budget reset. Mixed fence->tree and tree->fence must compose their respective operators in receipt order. Next substep starts from its actual body velocity, never cached pre-contact energy.
- Post-solver start from actual solver output and apply the same operators/order. Never restore pre-solver or shadow velocity. Zero stays zero; an independent wall slowdown is never refunded. If the solver leaves less energy than the reservation, consume only the remainder and clamp;8000J in the receipt denotes the reservation, not a false extra loss claim.
- Retain IPC5 envelope/receipt field shapes. Exact catalog hash plus version/policy/entry discriminator binds the semantics; unknown catalog versions/policies remain rejected. Preserve contact/receipt identity, scene/config/generation hashes, substeps1..6, unique IDs, ordered budget/solver chains and responsive-contact filtering. Domain admission must use the same mode so validated prepared changes cannot bypass or disagree with it. Both ACKs, scene publication and rejoin stay unchanged.

## Exclusive ownership after GO

| Owner | Files and duties |
|---|---|
| Agent p05b_controller_review | `server/physics/CheckedInput.cs`, `server/physics/FractureResponse.cs`, minimal `server/physics/Program.cs` wiring; private component tests/build evidence. Do not edit TrackedHandling.cs in this phase. |
| Agent p05b_source_audit | `server/gateway/src/drive/worker/catalog.rs`, `server/gateway/src/drive/worker/fracture.rs`, their inline unit tests; strict metadata, receipt arithmetic and old-version negatives. Read-only review of C# after implementation. |
| Agent p05b_metrics | `server/gateway/src/shared/fragiles.rs`, `server/gateway/src/shared/fragiles_tests.rs`, `server/gateway/src/shared/server.rs` ONLY new catalog projection and new test-module declaration, new `server/gateway/src/shared/server_fence_total_real_tests.rs`; private fresh moving-side/mixed-object fixtures and evidence. Cadence/publication algorithms untouched. |
| Root | `tools/compound_destructible_catalog.py`, `tests/test_compound_destructible_catalog.py`, all tracked docs/STATUS/plan/acceptance records; fresh import/export, source/build bindings, coordinated full gateway gate and final checkpoint. Root owns any necessary final pin update of existing `server_whole_fracture_real_tests.rs`; coordinate it after other writes freeze. |

No two agents write the same file. If an additional tracked file proves necessary, report the concrete dependency to root and transfer ownership before editing. No client/service/DB/install work. Original remains read-only. Reuse existing evidence inputs; write only fresh evidence paths and do not overwrite candidate08/09/13 or prior catalogs. Check free disk space before builds, retain failures, no evidence deletion.

## Sequence and gates

1. Root completes gateway13/checkpoint, records the starting SHA and source hashes, saves this plan, confirms discriminator/arithmetical details and dispatches GO. Root exports a fresh domain6/worker7 fixture after importer tests; each agent implements its owned boundary against the same fixture/schema. Stop immediately on schema disagreement rather than inventing parallel variants.
2. Run focused importer/parser/domain/component checks: old exports unchanged; incompatible version/policy/missing/extra response fields fail; wrong kind/discriminator and foreign source identity fail; finite/boundary8000J, incoming0.1, speed25, radial energy/direction, mixed budgets, repeat object, missing actual contact, malformed receipt/scene/generation and no wall refund. Old normal-policy tests remain unchanged. No-pass-empty-fixture checks stay enabled.
3. Fresh exact-worker replay: both MS-1/IS-7, moving-side~3 and~6m/s against actual fence3167; both workers must emit valid receipts and ACK the same removal. Preserve candidate08 counterexamples. Run both masses' parallel-no-contact and moving-away controls, explicit tangent/rest-pivot/solid-wall/wheel-only controls, front/chain passage and mixed fence/tree/fragile sequences in both orders with exhaustion. Record observed contact speed, budgets, solver pairs, removals, passage and hashes; no claim from offline counterfactual alone.
4. Regression: unchanged626-tree/9-fragile response, low-heavy tree, projectile multi-hit, old catalog/IPC rollback, exact paired determinism on pinned platform, current handling/coast/grip suites. Use new-policy radial assertions only for new fence cases; retain old normal-only tangent assertions in old-policy tests. Run full gateway suite against the final exact worker/build after source freeze. No extra full rebuilds absent new changes/failures.
5. Root documents actual PASS/FAIL/NOT_RUN, source/build/config/catalog/evidence hashes and rollback. Automatic PASS only when all required gates pass; owner/native gate stays OPEN, no merge. Morning native handoff is a separate explicitly authorized step.

## Rollback and limits

Execution checkpoint14: fresh full gateway755/755, Python119, C#162, paired
moving-side8, new ram22, old ram20 and handling38 runs pass. Source-profile
actual gateway checks include both-ACK commit and rejoin restoration. Clear
chain passes both masses. Actual wheel-only source fixture remains NOT_RUN
after12 bounded attempts, including4 settle failures; static pressure still
FAIL/OPEN. Therefore this is a scoped checkpoint with open acceptance, not
completion of every gate. Full report:../research/P05B_MOVING_FENCE_CONTACT.md.

Restore the preserved accepted checkpoint/build and old domain5/worker6 catalogs if the new phase fails; preserve failure evidence and do not alter unrelated P09B work or newer independent owner work. No live processes are started by this plan. Static pressure, historical material strength/server solver equivalence and missing compound-object coverage are not repaired. Client predictor A remains research evidence and is not smuggled into B's thresholds.

Plan review: version occupancy rechecked at checkpoint9f384fa; no intervening catalog edits. New-phase runtime tests/builds remain NOT_RUN until implemented. Prior13 gates are retained evidence, not proof of this contract. Next action: parallel implementation in the exclusive file scopes above and fresh exporter fixtures.
