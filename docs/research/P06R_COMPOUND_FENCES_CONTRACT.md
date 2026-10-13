# P06R — source-bound fences and compound boundary

Work in progress on `codex/p06r-compound-destructibles`, based on accepted
P06Q merge `90c7a1d92a67be2acf2d02ab9a5720a377c9f2c8`.
Evidence root: `local/evidence/20261013-p06r-compound-01/`.
Original `C:\WoT_0.9.1_RU_0717_original` stays read-only.

## Verified source contracts

The imported Prohorovka inventory has 3904 instances: 2943 trees, 712
fragiles, 71 falling columns, 58 structure instances, and 120 undefined.
Source geometry was reconstructed for 77 model resources / 841 instances;
all 1682 physics/projectile byte comparisons match the pinned meshes.
`geometry-contract/summary.json` SHA256:
`404e87b242dbb6a374f84c74167001cf9e8c6bf7ea3dd6df1510cab3de3eaa03`.

403 fence instances across seven resources have one exact descriptor/BSP/
visual material, native kind 73, collision flags 128, a complete movement
span, zero projectile triangles, and no replacement visual. Their reference
health is 2 or 3. The prior importer required a projectile span and excluded
these objects. Eligibility now follows these source properties, without
filename or instance allowlists. Movement geometry totals 17103 triangles.
The accepted 635 P06Q source rows stay unchanged, yielding 1038 total rows.

The old 117-chunk native capture covers only 391/403 new instances. The other
12 need chunks 31105 and 32896. The fresh inventory requires all 119 chunks;
partial imports and invented native indices remain forbidden. Source paths
now point to the verified C drive original, so old D-path export receipts
are not rewritten or silently accepted against a new spec.

`import/fence-inventory01/inventory.json` SHA256:
`e7bb87e6914cb2982de83157107f56da73d5e0f08958d439ef16b37d57c3ef35`.
Probe spec SHA256:
`8b23c71350b260ef1eb0aeffb1a7d5bf36b6fe1304f783fc367c9845db2d6396`.

## Implemented first slice

Domain catalog v3 adds `movement_fragile` and sorted, bounded `area_chunks`.
Worker catalog v4 preserves whole-instance removal and IPC4 ACK semantics;
both caps are 2048 rows. Older versions retain their previous limits.
The native UINT16 cumulative fragile property allows 125 elements in its
254-byte VAR1 payload; tree UINT32 remains limited to 62 per area.

Movement-only objects can be rammed using the existing authoritative mass/
speed test_lab energy policy. Their original empty projectile spans are
validated against the exact source instance/cursor and never become bullet
surfaces. Projectile exclusion replay now ignores removed objects without
projectile geometry, so long tree/fence ramming sequences do not exhaust the
40-shot query budget. Accepted source geometry is not reimported or enlarged;
fence bodies are split from geometry already present in the static map.

## Compound objects remain a separate unaccepted slice

Pinned #717 Python and PE inspection verifies module packing, per-module
health, sorted module material kinds, transitive dependencies and native
render transitions. Native `destroyedModules` is property 0 (UINT16).
There are 320 instance-modules across the 58 structure instances.

`setMaterialKindVisible` changes rendering and does not, on its inspected
path, activate Havok shapes. `havokDestroyMaterial` uses a separate material
message (0x40c); whole-fragile `isDestroyed` also queues a whole-object
message (0x40d). Render material survival is not proof of collision survival.
The exact message-consumer collision semantics and rubble activation remain
UNKNOWN. Mixed BSP materials can have hundreds of disjoint triangle runs;
a single whole-instance range cannot safely represent an arbitrary module.
No mixed/compound collider is admitted by this first slice.

Static PE addendum: `native-contract/pe-bindings01/CONTRACT02.md`, SHA256
`62fc43369a1dcd8f0277b55c8fa7e8d4a934b163534d3c7979933a8da63a225f`;
receipt SHA256 `f734eec79b4144ffe97002bd656ba724435aaed58ff221b75c88d2e0a3d4685b`.
The verified client kinetic-damage calculation is client prediction, not
proof of the historical authoritative server formula. Current damage/ram
constants remain explicitly approximate test_lab.

## Checks at the implementation checkpoint

- `gateway-p06r-fences-01`: FAIL, old test constructor lacked catalog fields.
- `gateway-p06r-fences-02`: 631 PASS / 1 FAIL, old wire test still asserted
  that 65 entries overflowed the former artificial 64-entry limit.
- `gateway-p06r-fences-03`: 632/632 PASS, canonical isolated build PASS.
  Executable SHA256:
  `569952ce04aa3fe483973c3bf3b6b93619877e646eb4035ec74b4404ebd2b00b`.
- `physics-p06r-fences-01`: canonical build PASS; DLL SHA256
  `19a9734bf8c79c207d5e3c24de235ef50789e496d0bf0addb023765910a73434`.
  Build alone is not a physics simulation test.
- New importer suite: 15/15 PASS, including actual original source inventory,
  retained baseline rows, exact masks, complete native join requirements,
  relocation mismatch, and cumulative packet bounds.
- `layout01.json`: PASS, 78 source files / 22 single-source relocations.

Independent review found a remaining trace-capacity mismatch: the event
journal still reserved 1024 contacts for a 2048-object catalog. It now reserves
2048, with a combined maximum-shot/maximum-segment plus 2048-ram regression.
Explicit null/numeric `kind` values now fail closed. Scene membership uses
binary search in the already validated sorted catalog, avoiding the prior
quadratic removed-ID admission scan. Repeated snapshot hashing and physics
reverse body lookup remain future measured optimization work.

Subsequent build checkpoints are retained, not overwritten:
`gateway-p06r-fences-04` had two test-fixture failures (old literal event budget
and missing synthetic obstacle-world binding); `-05` stopped at compilation
because that fixture needed `Arc<Obstacles>`. These were test setup repairs,
not accepted runtime or native runs. Final validation follows below.

Combined Python scope in `python-scope01.log`: 62 collected, **61 executed
PASS, 1 NOT_RUN** (Windows account cannot create the symlink layout fixture).

Commands:

```powershell
python -B -X utf8 -m unittest discover -s tests -p test_compound_destructible_catalog.py -v
python -B -X utf8 server/build.py gateway --test --out local/build/server/gateway-p06r-fences-03
python -B -X utf8 server/build.py physics --out local/build/server/physics-p06r-fences-01
python -B -X utf8 server/check_layout.py --out local/evidence/20261013-p06r-compound-01/layout01.json
```

## Scaling boundary raised by the owner

Current integrated runtime is a two-slot test laboratory, with one physics
process and full map load per actor. It has no shared native mesh cache
across processes and is NOT accepted for 100 simultaneous battles. Catalog
entries become static collision bodies, not independent simulated vehicles
or scripted thinkers. Shared immutable geometry and separate per-battle
damage state are the intended production boundary. A battle must eventually
have one authoritative physics scene containing its actors, with measured
memory/tick budgets and map-resource reuse where supported. This card does
not silently replace that architecture or claim a load test from unit tests.

Read-only source audit: `scaling-audit01/report.md`, SHA256
`6fe580dd12ab00f6098126d6a277157b6f1c2bc163dc096365a5a42958236a39`.
The complete raw terrain/obstacle buffers total 41,824,764 bytes; the new
fences account for 820,944 bytes already present in those buffers. These are
input-file sizes, not process-memory measurements. A separate real-worker
snapshot (`worker-smoke/capacity01/two-workers-memory.json`) observes roughly
222 MiB private memory per ready worker and roughly 1.7 s startup in this
specific two-worker run. This is not an extrapolated 100-battle capacity result.

Private source-bound worker checks in `worker-smoke/capacity01/receipt.json`
(SHA256 `6bdd117472fcac42a019796e9cbbb0cf7d99ebc1b345b8e22ec60c859b408d83`)
passed: both real workers ready, matching scene-1 ACKs, idempotent retry,
cumulative 1038-object ACK/advance, restore before ready, and rejection of
legacy-version overcapacity, 2049 rows, and stale scene hashes. All owned child
processes exited. This worker projection needs no native IDs. Positive 2048
real-source execution is NOT_RUN_SOURCE_CARDINALITY: Prohorovka contains only
1436 distinct nonempty source instances within the per-instance triangle cap.
The 2048 parser/state boundary is unit-tested; geometry was not fabricated.

Final source build at this checkpoint: `gateway-p06r-fences-06`, **632/632
PASS**, executable SHA256
`e74937a494ae13a959e2fc483b4b3b0f19b4ee22bb4d9496ac64e765861646b1`.
The fresh physical pool is `local/build/server/physics-p06r-fences-01/pool-near.json`,
SHA256 `32f1dce529b7abd01996a515724be5e3c9d5142017975f5a103086335486effe`.
Private paired trajectories verify full-hull passage beyond source fence
3322 after removal, an intact control blocked by that fence, and preserved
hull contact with fence 3307 after adjacent fence 3308 alone is removed.
Receipt `worker-smoke/neighbor04/receipt.json`, SHA256
`a106b10607faf0368a07e40efcfe752cf85e77e635d113584fc2ddde7e2a68dd`.
Earlier blocked/settle-invalid approaches remain in the evidence as failures;
they were not relabelled as passage. Summary SHA256:
`327fb3dd071f6eeb91664f6e3a8c535e0306f3adf234c7b37cd2571abd962a9a`.

## Fresh native join and diagnostic transport failure

`fenceids01` ran both owned clients with the exact fresh spec and no diagnostic
gameplay input. Each exported 119 chunks / two stable passes; both complete
outputs are byte-identical (1,254,549 bytes), SHA256
`ca420c2ca560457f87acc10b1449f262d0f8a1ec3c4eb163e9bde2ed1f6cc5ab`.
Both were independently validated; only the identical digest is deduplicated
in the manifest. The exact join covers all 1038 objects:

- `import/native-join01/manifest.json` SHA256
  `ed2024e6d477e88e37d4a66f35e1531399a5e988105e0f738affab88fad62efd`;
- `import/native-join01/physics-removals.json` SHA256
  `4f5f2208660ce49033e07fc8fe51eae0d17263a5e41f294d5810aa6867da7ac9`.

The joined worker JSON is semantically identical to the independently tested
source-only private projection; byte hashes differ due to serialization.
The native export itself is preprocessing evidence, not visual acceptance.

The run also exposed **FAIL: both sessions retry_exhausted** before the
controlled stop. Capture audit finds 5.84/5.74-second gaps in inbound ACKs;
native traces show 5.70/5.67-second gaps immediately before export completion.
After the gap the clients send cumulative ACKs, but the server has already
retired the sessions. The old P06Q `treecontact02` passive export shows the
same pattern with roughly 6.6-second pauses and both session closures. Accepted
owner `treeobserve10` did not run the catalog exporter and had no closures.
This distinguishes an existing diagnostic-path problem from a proven P06R
gameplay regression. Exact callback CPU/I/O contribution remains INFERRED
until measured; transport limits must not be weakened to conceal it.

Audit: `diagnostic-drop01/transport-timeline.json`, SHA256
`f49d6ca004cf8c73d214a1901e36eb2fce70d8efdef070c4bf182fbb7e5a4a85`.
Both clients and server were stopped through verified process receipts at
10:43:37 UTC; both installation ledgers were restored. A fresh bounded
`fenceidle01` runtime comparison uses the real joined catalog with the passive
exporter disabled. Its result will be recorded separately.

Further bounded PE research finds the actual `WoT HKWorld` message consumer.
0x40c selects an exact material-kind entry; 0x40d visits its entire native body
map. That map has resource-dependent HKT/grouped/common fallback branches.
Secondary-object collision and actual per-model map membership remain UNKNOWN.
For Logs, `n_wood_0` and `s_wall` both use numerical kind73; `s_ramp` uses108
and is excluded by both original collision masks. Name prefixes cannot define
the part-removal boundary. No d_* collision activation has been demonstrated.
Addendum: `native-contract/pe-bindings03/CONTRACT03.md`, SHA256
`7154a8e0764dbb99b8a0889965a055fe63270eee9f0a0c58624971e960a3ecca`;
receipt SHA256 `8f6aa4307e6b8d244549da03c47627a67518dfcad3040b87c0a8b5a9d0922262`.

## Owner chain observation and priority change

The owner drove `fenceidle01`: fences break, other object classes remain intact,
and driving through consecutive sections can stop the tank. This is
**OBSERVED / PARTIAL_FAIL_OWNER_CHAIN_STALL**. It does not accept universal
destruction or both-client passage. The completed runtime log has five accepted
contacts (object IDs3307,3308,3615,3614,3618), ten worker ACKs, five commits,
and five native setter call/return pairs on each client. No server reject,
failure, stderr or session closure occurred before controlled cleanup.

The 300-second readiness watcher is retained unchanged. Its area counter used
the wrong event string (`SHARED_AREA_CREATED`); a separate raw audit corrects
that diagnostic field to **238 creates /119 unique chunks per session** using
`SHARED_CATALOG_AREA_CREATED`. Native cumulative arrays beyond one value were
also marked unrecognized by the old passive observer; callback delivery alone
does not reconstruct those missing values. The observer now records bounded
UINT16 arrays of up to125 entries, with explicit invalid/overflow markers.

Evidence: `runtime-smoke01/raw-audit-owner01.json`, SHA256
`d79479a7614bd64a0873afca8589fbf8452300b37b6321ea5f4e2dd6e1724b5c`.
Both approved clients and the gateway were receipt-stopped at10:52:36 UTC;
both patch ledgers were restored. No diagnostic injected gameplay input.

Source review verifies a separate sequencing bug: `Worker::poll` consumes a
reply, but IntegratedRuntime originally kept its contacts in a local vector.
If the peer was still pending, the early return discarded the first impact.
Later persisted contacts can already have much lower velocity. This is a
verified code defect, but its contribution to this particular owner stall is
not established by the old logs, which record accepted contacts only.

Private real-worker chain02 independently reproduces the physical cause at
mass4691kg: first fence closing3.980965m/s,37171.685J; after removal the next
section is reached0.2 simulated seconds later at1.276819m/s,3823.791J, below
the approximate8kJ threshold. One hundred later contacts leave it intact and
the tank nearly stationary despite throttle. A control with the first section
already absent clears the second. The accepted worker completes all six
substeps against a rigid collider before removal, losing momentum; fixing the
gateway batch loss alone cannot claim to repair that physical behavior.

Owner priorities are recorded in the plan: first make one tank's behavior
measurable and correct, then contrast MS-1 with source-bound IS-7. A new queued
P03M runtime card reuses existing hangar/P03I work. Two user-requested chats
have begun isolated crew/equipment and ammo/service components; neither owns
gateway/physics/shared loadout, live databases or native installations.

## Passive exporter repair checkpoint

JSON serialization, bounded write/hash verification and atomic publication
now run on one daemon writer after immutable per-chunk snapshots. Native
getters remain on the client main thread; its polls never join the writer.
The deadline is cooperative: an OS-blocked write cannot safely be killed;
timeout is an explicit failure with pending evidence, never fake completion.

Root automatic scope: **34/34 Python tests PASS**, including observer bounds.
Root CPython2.7.3 x86 compilation of both changed client files and standalone
writer execution reproduce the observed119-chunk3662-item export byte-for-byte:
1,254,549bytes, SHA256`ca420c2ca560457f87acc10b1449f262d0f8a1ec3c4eb163e9bde2ed1f6cc5ab`.
Observed writer time0.342s; max main poll0.000074s. This toolchain build is
MSC1500, not the embedded MSC1700 client; native post-fix rerun is **NOT_RUN**.
Evidence: `writer-fix01/root-tests01.log`, `writer-fix01/root-py27/py27-receipt.json`.

Commands:
```powershell
python -B -X utf8 -m unittest -v tests.test_destructible_catalog_probe tests.test_destructible_catalog_writer tests.test_interactive_primitive
local/toolchains/cpython-2.7.3-x86/python.exe -B local/evidence/20261013-p06r-compound-01/writer-fix01/root-py27/verify.py
python -B -X utf8 local/evidence/20261013-p06r-compound-01/audit_fenceidle01.py
```
The audit uses exclusive output creation; retain the existing receipt rather
than overwrite it when rerunning an analysis.

## Acceptance and rollback

P06R remains IN_PROGRESS. The full native identity join and private physics
checks pass; the owner observed breaking fences and a chain-motion failure.
Full visual/contact/pass-through acceptance is pending. Compound collision
remains UNKNOWN; the diagnostic export repair still needs native verification.
No merge to main is authorized by these partial results alone.
Retained P06Q build35 and `physics-p06q-final-02/pool-near.json` are pinned in
`baseline.json`. Stop only receipt-owned processes and restore their client
install ledgers. Source rollback is a reviewed revert on this card branch;
unrelated P09B documentation remains untouched. Native client tests must use
fresh helper/run paths; copied helper provenance is retained under
`native-probe/helper-provenance.json`.
