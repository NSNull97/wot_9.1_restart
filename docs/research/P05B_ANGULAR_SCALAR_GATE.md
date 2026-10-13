# P05B angular response: completed scalar gate

2026-10-14 local; root branch `codex/p05b-tracked-handling`.
Scope: Stage A of [the angular contact plan](../plans/P05B_ANGULAR_FENCE_CONTACT.md).
Runtime remains candidate14 at this checkpoint. Pure unused helpers were
created in the isolated angular-worker and angular-gateway worktrees; neither
was connected to a worker, domain or running service. Stage B is a separate
implementation decision in the plan, not implied physical/native acceptance.

E = `local/evidence/20261013-p05b-tracked-handling-01/`.

## Goal and result

Check the proposed bounded contact-normal angular impulse before changing
actual destruction. Exact f32 inputs promote to scalar f64 in a fixed order;
outputs round once. The shadow gate requires8000J within0.125J, nonincrease,
nonnegative remaining closing and fixed velocity bounds. POST recomputes from
actual solver motion and may honestly do nothing. No PRE momentum restoration,
new static-pressure law, changed mass, grip, controls or object coverage.

VERIFIED: C# and Rust independently implement the frozen math and match output
bits on the saved cases. Separate Fraction and Decimal90 calculations use
Gauss-Jordan inversion and check energy, eligibility, rounding and nonrebound.
These tests prove the stated finite component cases, not a historical solver.

| Executed check | Result |
|---|---|
| C# scalar/basis component build03 |3548 checks PASS;256 scalar cases and2882 saved native basis rows |
| C# native-source mixed component |266 checks PASS;12 sequences/84 steps |
| Rust scalar module |5 unit tests PASS,0 ignored |
| C#/Rust scalar comparison |256 cases: six f32 output components, branches and eight f64 quantities match exactly |
| Independent Fraction oracle |238 finite scalar cases checked;18 invalid cases rejected |
| Mixed chains across both implementations |18 sequences/126 steps PASS, including12 source-mass sequences/84 steps |
| Independent Decimal90 review |Scalar energy, quantization reasons and source-mass mixed checks PASS |
| Root evidence integrity |127 C# artifacts and102 copied Rust files checked;262 root runtime files unchanged |

The256 scalar cases include20 shadow applications,35 POST applications,
8 shadow quantization rejections,22 POST quantization no-ops,58 nonclosing,
95 ineligible and18 invalid cases. Positive fixtures actually pay energy.
Sixteen high-spin candidates (eight shadow/eight POST) fail only the frozen
accounting band; the gate was not widened after seeing these results.

Mixed source fixtures keep profile masses4691/68190 for the old linear
operators and actual native inverse mass for angular math. They are deliberately
authored motions on source tensors, not new native trajectories. Angular-only
sequences pay twice for MS1 and six times for IS7, then stop paying; no reserve
is recreated. Mixed reducer composition does not itself prove a legitimate
linear-first contact selection. That selection is a required Stage-B test.

OBSERVED: the saved native body/tensor values match the two pinned profiles on
the recorded Windows build. The first IS-7 contact remains a plausible target
for the new fallback. INFERRED: it should remove that rotating-corner blockage;
no actual worker has yet executed this policy. UNKNOWN: native outcome,
simultaneous-wall behavior, historical fidelity and fully stalled pressure.

## Source and evidence binding

Unused C# source `server/physics/AngularContactResponse.cs` in the worker
worktree is SHA256
`00921a2a6a26c6d4bcec9c1d82f8f26db10d4f77766dbd57f4b06e81241075e4`.
Its byte snapshot is `E/night-angular-kernel01/AngularContactResponse.stage-a.cs`.
Unused Rust source `server/gateway/src/shared/ram_response.rs` in the gateway
worktree is SHA256
`e8f6fc7451fa6e43a14fa962b8199330ed65e1d738a22f30c3c47708f8b0ef51`.

| Receipt relative to E | SHA256 |
|---|---|
| night-angular-kernel01/receipt.json |2a540499baa1d7d109f6144a6a1a2b28193404bb9b8b3eb94d41967d0da57e3b |
| night-angular-components-rust01/final-receipt.json |d6f8ca8450cc1b6e229d029f3195447af57e6c05016277cacffe54e261286c0f |
| night-angular-components-rust01/copy-receipt.json |709bc9fce4f6051bd5707694b911715c0b2a618520d0da9295be398d7cbdcb24 |
| night-angular-review01/stage-a-final-review.json |0b51116e8bbc2f608469afe3170a93af052065435776f949f2d65b243d113cb6 |
| night-angular-stage-a-root01/receipt.json |feb225f55e37a735421c8e96ef17ad5191eeabdcbb7b88dfabc616cdba9c8a96 |

The C# inventory binds127 files/8626563 bytes. The Rust original inventory
binds100 files/19113664 bytes; root copied them and the two final inventory/
receipt files byte-for-byte into E. Original command paths remain the isolated
C: checkout; the copy is not presented as another execution. The root receipt
also verifies the preserved P09B hash and all262 baseline runtime source pins.

Actual successful command entrypoints (full argv/tool hashes/stdout/stderr are
inside each attempt's command receipts):

    python -B -X utf8 E/night-angular-kernel01/build_run.py build03 inputs02.json
    python -B -X utf8 E/night-angular-kernel01/build_mixed.py

From the angular-gateway checkout:

    python local/evidence/angular-stage-a01/run.py run02 inputs02
    python local/evidence/angular-stage-a01/oracle.py run02 run02-oracle.json inputs02
    python local/evidence/angular-stage-a01/run_mixed.py mixed02 <pinned C# result> <mixed_inputs.json>
    python local/evidence/angular-stage-a01/oracle_mixed.py mixed02
    python local/evidence/angular-stage-a01/compare_mixed.py mixed02 <pinned C# mixed result> compare-mixed02.json

Root executed the saved copy and integrity scripts:

    python -B -X utf8 E/night-angular-stage-a-copy01/copy.py
    python -B -X utf8 E/night-angular-stage-a-root01/verify.py

Here E is the explicitly defined path abbreviation, not a literal executable
argument. Scripts and full receipts retain actual absolute referenced paths.
No physical workers, clients or services were launched in this phase.

## Failures, bounds and next phase

C# build01 failed compilation from ambiguous target-typed constructors;
build02 failed aggregate coverage because no shadow-quantized case existed.
Both remain preserved. Supplemental inputs, not looser thresholds, close that
coverage. Python/shell preparation failures and the first oracle's incomplete
cardinality/analytic-case assertions remain alongside corrected later runs.
No failed attempt is relabelled PASS.

[The exact IPC6 table](P05B_ANGULAR_FENCE_IPC.md), body-binding proposal and ACK
addendum are frozen before runtime work. Structural size is48244 payload bytes
excluding LF/2258 nodes/depth6; actual serialization/parser tests are still
required. IPC6 cap65536 and older32768 exclude LF. IPC6 ACK permits2048 IDs
with4096 nodes; older ACK/catalog parsing retains its previous limits.
Disk artifact verification is retained; loaded-module-path attestation and
legacy origin/Euler/signed-speed mapping remain explicit trust boundaries.

Acceptance: PASS_STAGE_A_SCALAR_ONLY. Actual contact selection, private physics,
domain/event replay, both-ACK commit, rejoin and passage are NOT_RUN for this
new policy. Native owner acceptance remains NOT_RUN until after09:00; no merge.
Static pressure, compound coverage and energetic wheel-only isolation remain
OPEN/NOT_RUN. Candidate14 is the working rollback; no live installation changed.

Single next step: implement the separately authorized Stage B in the isolated
worktrees, integrate a new candidate and execute its bounded automatic gates.
