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

The fresh manual stand uses run `fencechain01`, `gateway-p06r-fences-09`,
`physics-p06r-fences-03/pool-near.json`, and `import/fence-response01/manifest.json`.
Exact executed launch arguments, full source HEAD, file hashes and owned process
identities are in `native-chain/launch-{server,a,b}-fencechain01.json` after
launch. Preparation uses `native-chain/prepare_stand.py --slot a|b --run
fencechain01 --mode runtime --map 05_prohorovka`; runtime launches do not enable
the passive catalog export. Native acceptance remains PENDING_OWNER.

After the owner finishes, stop and restore only this stand:

```text
python -B -X utf8 local/evidence/20261013-p06r-compound-01/native-chain/stop_stand.py --receipt-dir local/evidence/20261013-p06r-compound-01/native-chain --run fencechain01 --out-name fencechain01stop --reason "Owner manual run complete"
python -B -X utf8 tools/interactive_client.py rollback --out local/evidence/20261013-p06r-compound-01/native-chain/install-a-fencechain01
python -B -X utf8 tools/interactive_client.py rollback --out local/evidence/20261013-p06r-compound-01/native-chain/install-b-fencechain01
```

Next: the owner's native fence-chain drive, then collect its evidence before
beginning P03M runtime integration.
