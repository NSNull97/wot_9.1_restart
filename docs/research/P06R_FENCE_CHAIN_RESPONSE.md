# P06R fence-chain response

Goal: remove the measured full stop on successive light fence sections while
retaining mass-dependent energy loss, ordinary rigid collision, and both-worker
scene acceptance. Owner requested automatic checks before a native drive, then
the queued P03M IS-7 runtime card. This is an explicit test_lab policy.

## Evidence and decision

- VERIFIED: the source-bound close-joint fixture uses object3307/instance3306
  and object3308/instance3307. The first original worker hit had 37,171.685 J;
  the second had 3,823.791 J after the static solver consumed almost all motion.
  Both ACKs consumed no simulation ticks. This identifies a response-order
  problem, distinct from the already repaired asynchronous contact retention.
- OBSERVED: paired baseline workers reproduce the stall with masses2345.5,
  4691 and9382 kg, retaining MS1 geometry and scaling torque for the experiment.
  This is not an IS-7 model. Baseline results and source snapshots are in
  `local/evidence/20261013-p06r-compound-01/chain-regression02/baseline02/`.
  Two repeated sets of seven cases returned equal state traces. The earlier
  baseline01 also retains an overstrict free-passage assertion failure; its
  corrected classification does not claim full native passage.
- VERIFIED on the pinned library: native snapshot/restore exports are absent.
  `numThreads=0` did not give serial callbacks (32 observed threads), and1 still
  used two threads. A callback job system with inline execution and declared
  concurrency1 gave one caller thread, equal order/state hashes in two runs,
  4480 contact callbacks and1530 jobs per run. Native Jolt was not upgraded.
  Private source/API/receipt evidence: `snapshot-feasibility02/` under the same
  evidence root. This proves the bounded probe, not all platforms or gameplay.
- INFERRED and implemented as a testable design: reserve contact energy before
  the solver, suppress only admitted fence constraints, then remove energy
  from post-solver velocity without refunding any rigid-wall impulse.
- UNKNOWN: original server fracture resistance, historical collision/engine
  model, mixed-material compound replacement geometry, and production capacity.

## Versioned contract

Domain v4 and worker catalog v5 select `test_lab-fence-energy-v1`. The same
1038 object/native identities are retained; only403 movement-only whole
fragiles receive an8000 J response. Accepted trees and other whole fragiles
retain their previous behavior. The source/native join is regenerated from
pinned source files and the119-chunk/two-pass capture; it does not require a
new probe or invent native indices.

Worker IPC5 reports exact bounded fracture receipts. Each step starts a
shadow vector budget at actual pre-step velocity; admission requires enough
positive normal energy in both actual and remaining budget velocity. A
repeated manifold cannot reserve the same object again. The first decision
within a step is retained. After the solver, the normal-energy reducer acts
on current velocity, can only decrease its magnitude, and never restores a
component lost to a wall. Details and packet fields are in
`server/physics/README.md`.

Nonempty receipts produce `prepared`, with original scene identity. The
worker cannot advance until the cumulative commit includes every prepared
removal. The gateway validates receipts, stages the pose and domain outcome,
and requires both workers' exact ACK before publication. Bad receipts,
omitted IDs, stale sessions or worker failures stop the battle. A partly
advanced physical world has no claimed rollback. A simultaneous same-object
hit may dissipate energy from both actors in this discrete model; shared
destruction/native publication occurs once.

The synthetic rigid-wall control adds a separately hash-bound private terrain
fixture and preserves the original obstacle buffers. It tests the physical
response safety property; it is not original client or native visual evidence.

## Current validation

Importer scope:16/16 tests PASS, command
`python -B -X utf8 -m unittest -v tests.test_compound_destructible_catalog`.
Tool-output provenance and exact source hashes:
`local/evidence/20261013-p06r-compound-01/chain-fix01/importer-tests01.json`.

Fresh source/native join command:

```text
python -B -X utf8 tools/compound_destructible_catalog.py --out local/evidence/20261013-p06r-compound-01/import/fence-response01 --fence-response --native-export local/evidence/20261013-p06r-compound-01/native-probe/runtime-a-fenceids01/destructible-catalog-46736.json --native-sha256 ca420c2ca560457f87acc10b1449f262d0f8a1ec3c4eb163e9bde2ed1f6cc5ab
```

Domain SHA256 `39bb68815dd2d7ca54789a1cc71be619cc4f2f5cf351bf52f22de92f2afca11d`;
worker SHA256 `0a7c8fd70f00c8c49c3282ac1fe574281f384d042b1adb7da549d1680c192ef9`.
The full inventory SHA remains
`e7bb87e6914cb2982de83157107f56da73d5e0f08958d439ef16b37d57c3ef35`.
Both original client captures were verified byte-identical in the retained
native-join01 receipt; the command uses their deduplicated content hash.

Final automatic results on the pinned Windows host:

| Scope | Executed result | Evidence relative to the evidence root |
| --- | --- | --- |
| Canonical gateway09 |649/649 PASS, including actual paired IPC5 runtime/domain/ACK gate | `../../build/server/gateway-p06r-fences-09/result.json` and test logs |
| Paired physics03 behavior |7 PASS: close chain, three masses, low speed, free control and solid-wall controls | `chain-regression02/final03-behavior/receipt.json` |
| IPC5 protocol |4 PASS: premature advance/omitted commit rejected, exact retry, restored scene | `chain-regression02/final03-negatives/receipt.json` |
| Matched incoming speed |3 PASS at2345.5/4691/9382kg | `chain-regression02/final03-matched/receipt.json` |
| Old modes and tree3344 |9 PASS: IPC1/2/3, retry/restore, real tree hull contact on catalogs3/4/5 | `legacy-compat01/summary.json` |
| Component arithmetic |64 PASS including10000 seeded vectors, adjacent-f32 energy boundaries and speed limits | `snapshot-feasibility02/fracture-math/checks-threshold.json` |
| Importer |16/16 PASS | `chain-fix01/importer-tests01.json` |
| Source layout |PASS,83 files/22 relocations | `chain-fix01/layout-final.json` |

The close chain now removes3307 at advance19 and3308 at20, with maximum
Z466.41174 versus the previous stall at462.01862. Matched incoming normal
speeds2.94726/2.96498/3.01229m/s lose1.58170/0.64543/0.29779m/s respectively.
Each mass case charges approximately8000J. These use MS1 geometry and scaled
torque, not an IS-7. Ten final movement traces equal their physics02 counterparts
on this pinned host. The real Rust test intentionally consumes only worker A's
ACK and verifies unchanged published world until B's ACK, two unique shared
object events, cleared preparation and resumed movement beyond Z464.

The final private aggregate is `chain-regression02/final03-receipt.json`, SHA256
`4a3315b46785c3794cbf0e28323f6a4cd14317997c73249a0475398ba3d62408`.
It contains exact commands, script/source pins and process receipts. Final
physics DLL SHA256 `1d75294e1179667b8de643deffffc589e7eedfcaa0e77e8d0a59b1d476679074`;
near pool SHA256 `769580fc5c9612dde51e9c328edeaaf6359046d75267703579d22083c00d74e0`.
Gateway09 executable SHA256
`fbf2c4e5cfc6962dee8ecbc7b34e661c178411ac0df8f98ebf4e1ade0080b082`;
build result SHA256 `9a12f2949aa60c139d68400b1c8d8feafe10f70097eade8c95db8ec214d44828`.
Canonical commands actually executed:

```text
python -B -X utf8 server/build.py physics --out local/build/server/physics-p06r-fences-03
python -B -X utf8 server/build.py physics --legacy --out local/build/server/physics-p06r-fences-03-legacy
python -B -X utf8 server/build.py gateway --test --out local/build/server/gateway-p06r-fences-09
python -B -X utf8 server/check_layout.py --out local/evidence/20261013-p06r-compound-01/chain-fix01/layout-final.json
```

Preserved failures/limitations: baseline01's distant free-passage assertion
crossed an unrelated static well; candidate01's mass-speed spread0.269m/s
failed comparability, so the final receipt marks that group NOT_COMPARABLE
and requires the separate matched-speed experiment (spread0.06503m/s).
The first tree route hit fence3309 before reaching3344; a north approach with
unchanged geometry supplies the passing contact. Its first aborted private
worker was reaped but its PID/trace were not captured; the compatibility
summary discloses this. An initial C# compile error was fixed with the explicit
zero legacy energy parameter. The integration patch's missing new-file mode
caused `git apply --check` to fail without edits; adding that header produced
`fracture-gateway-real01/integration-followup-git.patch`, SHA256
`e2f5e16058d01ec0fd31655f1c10e286968775dc51b08c1c5ef4da824255c439`.
Original failed receipts/patches remain available.44 existing Rust warnings
remain. No native PASS, branch merge or IS-7 gameplay claim follows from these
automatic checks.

Changed files: physics `Program.cs`, `CheckedInput.cs`, new
`FractureResponse.cs`/`InlineJobSystem.cs`, physics README and legacy csproj;
gateway worker/catalog/new fracture validator, shared fragiles/server and
their tests/new real-worker integration test; compound catalog importer/test;
P06R plan, this report, STATUS and ACTIVE_GATE. The unrelated P09B edit is
excluded from this change.

## Rollback and next step

Only owned processes are stopped by pinned launch receipts and client install
ledgers are restored. Previous code/builds and all failure evidence are kept;
reviewed reverts restore the old behavior without resetting the unrelated
P09B edit. Runtime launch helpers in the fresh `native-chain/` evidence folder
preserve original/process/source guards and require the new policy explicitly.

The fresh manual stand uses run `fencechain03`, `gateway-p06r-fences-09`,
`physics-p06r-fences-03/pool-near.json`, and `import/fence-response01/manifest.json`.
Exact executed launch arguments, full source HEAD, file hashes and owned process
identities are in `native-chain/launch-{server,a,b}-fencechain03.json` after
launch. Preparation uses `native-chain/prepare_stand.py --slot a|b --run
fencechain03 --mode runtime --map 05_prohorovka`; runtime launches do not enable
the passive catalog export. Native acceptance remains PENDING_OWNER.

The first A preparation (`fencechain01`) stopped before client writes: another
user-owned service chat's isolated client retained the same v1 instance mutex
`sr_p03f_a_mutex_`. Its process was left alone. The launch prerequisite now
supports an optional four-character namespace in v2 copy markers, changing only
the same two already-researched UTF16 EXE strings. Old v1 copies stay compatible;
the checker reconstructs expected names/patches/EXE hash from the pinned original
backup. Root stopped copies use namespace `p06r`, with exact-path process checks,
new-mutex lock, full EXE/marker backups and before/after ledger. Evidence and
failure: `native-chain/prepare-fencechain01-failure.json`, `namespace-a/` and
`namespace-b/`. This identity change does not change physics or gameplay code.
The copy tool and its tests are the only additional tracked runtime-tool files.
Fresh root copy/interactive suite:35/35 PASS (`namespace-tests01/root-suite.log`),
including nine pinned-EXE/schema checks. Command:

```text
python -B -X utf8 -m unittest -v tests.test_shared_client_copy tests.test_interactive_primitive tests.test_interactive_relogin_control tests.test_interactive_license_policy tests.test_interactive_window_trace
```

The subsequent `fencechain02` launched both processes within0.82s. A logged
on; B's native callback recorded `LOGIN_REJECTED_SERVER_NOT_READY`. No battle
started. OBSERVED result is kept in `native-chain/fencechain02rejected/`.
INFERRED cause is the existing single pending auth/250ms admission guard
(`shared/server.rs` login branch); this path does not emit a reason log, so
exact overlap is not proven. This is not a fence-physics failure. Both owned
clients/server were stopped by verified receipts and both ledgers restored;
`stop-fencechain02retry.json` records cleanup. Fresh `fencechain03` launches B
only after A's `SESSION_ACTIVE`. Concurrent-login admission remains a known
limitation; sequential startup is a launcher workaround, not a protocol fix.
Launch helpers log in to the hangar only. The owner presses the native Battle
button on each client to enter the configured Prohorovka arena; no agent
steering, firing or automated owner acceptance is performed.

Fresh run03 subsequently reached actual battle readiness: two SHARED_READY,
two real worker READY,238 area creates (119 per client), zero fault/closure
lines and zero stderr in the complete-line frozen prefix. Evidence:
`native-chain/fencechain03ready01/result.json`; raw saved server/client prefixes
are beside it. Server PID44816, A50076, B15740; verify creation time and hashes
from receipts before cleanup. Launch code is `e155c4e`, fence physics change
`0d94ee6`; later documentation checkpoints do not alter the running code.
Both clients/server remain running for the owner. Native fence-chain visuals,
speed feel and passage acceptance are PENDING_OWNER, not inferred from READY.

After the owner finishes, stop and restore only this stand:

```text
python -B -X utf8 local/evidence/20261013-p06r-compound-01/native-chain/stop_stand.py --receipt-dir local/evidence/20261013-p06r-compound-01/native-chain --run fencechain03 --out-name fencechain03stop --reason "Owner manual run complete"
python -B -X utf8 tools/interactive_client.py rollback --out local/evidence/20261013-p06r-compound-01/native-chain/install-a-fencechain03
python -B -X utf8 tools/interactive_client.py rollback --out local/evidence/20261013-p06r-compound-01/native-chain/install-b-fencechain03
python -B -X utf8 local/evidence/20261013-p06r-compound-01/native-chain/namespace_copies.py a --restore
python -B -X utf8 local/evidence/20261013-p06r-compound-01/native-chain/namespace_copies.py b --restore
```

The above launch checkpoint is historical; final acceptance follows.

## Final owner acceptance and cleanup — 2026-10-13

**PASS_OWNER_FENCE_CHAIN_TEST_LAB.** Owner: «Проверил, теперь цепочку заборов
проходит нормально, без стопа после первой секции. Останавливай оба клиента и
сервер, собирай evidence и переходи к ИС-7.» Scope is the source-complete fence
slice and chain response. Mixed compounds/all-object coverage are deferred,
not silently accepted. The exact quote is pinned in
`native-chain/fencechain03-owner.json`.

Read-only audit of full logs: ten fence receipts, eleven ram contacts/commits,
22 worker ACKs, both-client publications/setter and original destruction
call/returns for all ten fences. Each fence spends7999.986–8000.010J.
Tree3365 additionally publishes `fallenTrees=421445632`; projectile object3620
makes final scene12. Gateway stderr0, no session failure/reject/closure, complete
native JSONL/no cap, capture27978 packets/1234012 bytes below configured limits.
Nine of ten projected-center clearances pass within50 ticks; object3625 does not
meet that separate metric. This inference is not an exact swept-hull check;
the owner's actual chain observation closes passage. Native callbacks do not
prove separately inspected rendering on each screen.

Full per-object/source-position correlation and raw-file hashes:
`native-chain/fencechain03-final/REPORT.md` SHA256
`10ff240ad922349bae36f4498c7894a9de867ea83fb93b30914e2e0654b8ec8b`,
`audit.json` SHA256
`2eae41a6ba160c04274c19573da6890fd5d83122930ec230d877ae5b5f576b67`.
Command actually run:
`python -B -X utf8 local/evidence/20261013-p06r-compound-01/native-chain/fencechain03-final/audit.py`.

Cleanup commands above executed with stop output `fencechain03ownerstop` and
reason `Owner confirmed chain passage without first-section stop; proceed to IS-7`.
Stop receipt PASS; root clients50076/15740, server44816, workers44840/35368 are
absent. Both install `restore.json` and namespace restore receipts PASS; current
restored hashes/absences/EXE/marker match preinstall pins. No unrelated process
was stopped. Original remains read-only. No rollback is pending.

No new game test is claimed by this post-run audit; previously passed canonical
checks apply to unchanged source pins. Remaining limitations: historical ram
formula, mixed compounds/replacement collision, production100-battle capacity,
simultaneous login admission and IS-7 runtime. Source rollback remains a reviewed
revert, preserving evidence and unrelated P09B edits. Next: accepted P06R no-ff
merge/push, then P03M source-bound IS-7 runtime implementation.
