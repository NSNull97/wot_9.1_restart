# P06O — source-driven fragile object catalog

Goal: replace the individually selected crate with reusable resource import,
independent per-object state and matching movement/projectile/native removal.
Branch `codex/p06o-destructible-import`; accepted base `main5f38525`.
Plan: [P06O_DESTRUCTIBLE_IMPORT](../plans/P06O_DESTRUCTIBLE_IMPORT.md).
Evidence root: `local/evidence/20261012-p06o-destructible-import-01/`.

## Verified scope and source identity

VERIFIED by the original #717 packages, definitions,144 chunk files and both
pinned geometry exports:2918 instances;2564 trees,49 fragile objects across11
chunks,2 structures,303 unclassified. Original definitions have1860 records,
1859 unique resources. Every source transform is matched to both exports.
The generic intact/destroyed BSP material rule selects six whole-instance
fragiles in three chunks: three camouflage boxes, two GerBoxes variants and
one cistern. No per-instance allowlist or triangle range appears in runtime
rules. Mixed/ramp geometry, missing collision and other families have explicit
exclusion reasons. This does not claim full-map destruction or tree support.

Inventory: `resource-contract/inventory02/inventory.json`, SHA256
`5658e7620389e9726b1ff06f1eb80125224a45fe17d8558c2e072b4a7cc6bbf3`.
Generated11-chunk preprocessing spec SHA256
`661705b49305b1fe11b16ec2035d5a0dbf4cb7f2aa4731a1fcfdc60d44de176d`.
Original definitions SHA256
`bd39e3047b435fc8917ca2e7c3dc82de4a5a03cc164054af83395af8b479fdd5`.

VERIFIED native contract: all destruction families share a per-chunk index
namespace. Resource/XML ordinal is not a proven native index. The optional
read-only original-client preprocessing probe reads each explicit index,
filename and full local/chunk matrices twice. It requires all requested chunks
and identical complete passes. It writes a bounded own artifact with hashes;
the offline importer joins that artifact to original sources. Runtime receives
only a pinned immutable catalog; no live client hit/state becomes authoritative.
Contract: `native-contract/contract01.json`, SHA256
`24b50c29ff34309da6d8999ac37dd83f3b5f435617a8cb0663731d77fc08babb`.

## State, geometry and approximation

Catalog admission checks exact fields, hashes, bounded JSON, source IDs/ranges,
native index uniqueness, full projectile geometry spans and matching worker
entries. Limit64 objects,40 removed IDs (current total ammunition),128KiB JSON.
World and impact trace independently bind damage to the computed terrain hit.
Only HP0 removes an instance. Scene version counts removed objects; partial
damage leaves collision intact. All removed IDs are sorted and cumulative.

IPC3 restores the current scene before a new worker creates/settles its tank.
Subsequent mutations contain the full removed set and a catalog-bound SHA256.
The coordinator drains movement replies and stages a World clone; it publishes
only after every participating worker acknowledges the exact target scene.
Unknown/substituted/shrinking sets, stale ACKs and changed membership fail
closed. A partial external mutation is not represented as a successful rollback.
Legacy IPC1/2 and accepted one-crate mode remain available.

Native replication uses original AreaDestructibles type3, one controller per
catalog chunk, full sorted `destroyedFragiles` arrays and short VAR1 lengths.
Creation contains current state; repeated updates do not append duplicates.
All controller creation ACKs gate commands. Native effects and free passage
still require actual native/owner acceptance.

APPROXIMATION `test_lab-fragile-reference-hp-ap30-v1`: original unscaled
reference HP, fixed AP30, projectile ends on the first surface, no resistance,
impulse or continuation rule. Source `ceil(scale²*referenceHP)` is VERIFIED;
meaning of its scale input is UNKNOWN. Source basis lengths are recorded,
not substituted as that argument. Historical/server formulas are not claimed.

## Changes and performed checks

- `tools/destructible_catalog.py`, associated tests: original resource import,
  explicit coverage and strict native identity join.
- `client_patch/destructible_catalog_probe.py`, `sr_interactive.py`,
  `tools/interactive_client.py` and tests: opt-in preprocessing and ledger install.
- `server/gateway/src/shared/fragiles.rs`, model/impact/terrain/obstacles,
  native area/session/server modules and tests: cumulative authoritative state.
- `server/gateway/src/drive/worker.rs`, `worker/catalog.rs`,
  `server/physics/{Program.cs,CheckedInput.cs,README.md}`: bounded IPC3.
- `server/gateway/src/main.rs`: explicit `--destructible-catalog PATH SHA256`
  after existing geometry/AP/terrain arguments, mutually exclusive with legacy.

Runtime source commit `294fe42`. Gateway05: **590 Rust PASS**, pinned driver,
SHA256 `c23035f0288de15637000b7e2c339e942281a14ff76d2eb9ce81e170b838f60b`.
Includes real two-worker ACK/restore, half-ACK gate, cold reconnect, membership
failure, independent removals, partial HP, forged trace, cumulative arrays,
fresh connection state and transactional session failures. These tests do not
prove native visual behavior. Python suite03 after probe readiness correction: **56 PASS**.

Private physics: **20 PASS**, receipt
`boundary/worker-ipc01/receipt.json`, SHA256
`1ca49c8535514a4bc122ac626f1c1fcbf37b7968dbda7978265d91af934d80aa`.
Root physics build `physics-integrated-p06o-01`: DLL SHA256
`dc37069b1652c2ed140d1246663a07d242d6e7764d05778b9154bd754f1f5c06`.
Pool `pool-near.json` SHA256
`c2dd3da12e275b94172107e3e358dfb8452dc3dc7895fd3e295a0ac38c0db22b`.
Movement settings/geometry are unchanged. The new test pool shifts only
spawn_origin X by -4m: [-398.25,58,-414] to [-402.25,58,-414], placing the pair
beside the additional stack. Fresh artifacts only; accepted pool is unchanged.

Earlier failures retained: gateway01 compile module-path/slice-coercion errors;
gateway02 old exact trace-capacity assertion; gateway03 new golden packet test
used count offset as payload offset. Fixed; gateway05 complete suite PASS.
Python suite01 included a nonexistent test module; suite02 corrected module
selection and PASS; suite03 adds the three startup regression checks. Worktree linker failures preceded project compilation;
root canonical driver is the actual integration evidence.

Oracle01 OBSERVED: both original clients entered the accepted P06N battle.
Preprocessing failed on first manager/player space check during entry; no
catalog produced. This failure is retained, not counted as native acceptance.
Oracle02 VERIFIED: initial manager1073741824/Avatar1, then manager switches to1
after loading. Both clients export identical complete tables of11 chunks and
329 native entries, two stable passes, maximum102 entries per chunk. Export
SHA256 `d9917eb5daf8c40aab13f2ce26c32f1dfcbcf6062b39cf12bbae142de6cc82e6`.
Paths: `runtime-a-oracle02/destructible-catalog-25340.json` and
`runtime-b-oracle02/destructible-catalog-13936.json`. The importer rejects two
identical input pins; final join uses one unique byte sequence and preserves
independent A/B provenance in `identity-join-runtime-receipt01.json`.

Final join `resource-contract/native-join02/manifest.json` SHA256
`d5063d067763589647198acf79f65ef747fb5293f4d7b38d619f301217ac73a3`;
worker `physics-removals.json` SHA256
`d0335f44e98e16192cb84a927fd23d2d580866e6fea47264ceddf0a7e13a2dd4`.
Native (instance/chunk/index):1230/33667/9,1231/33667/10,1237/33667/16,
1512/31354/0,1513/31354/1,1528/31355/3. These are generated evidence, not
handwritten runtime selection. Full matrices match original source float32 bits.

Native01 entry VERIFIED in retained `native-entry01/receipt.json` and source
prefixes: both clients in battle832598004322204188, all three AreaDestructibles
created in each, two workers at tick180 with6 contacts each, both vehicles and
prediction started, same replicated positions, no error/failed observer events.
This proves startup only; the subsequent object acceptance is recorded below.

## Owner object acceptance and remaining cumulative gate

OBSERVED: owner answered «Всё работает» to the requested two-object,
untouched-neighbor, free-passage, repeat-shot and cumulative gameplay check.
Frozen complete-line prefixes are retained in `native-acceptance01/`, with
SHA256/byte/line counts in `snapshot.json`. Independent `native-audit.json`
and `server-audit.json` distinguish recorded events from owner observations.

VERIFIED: three independent fragile instances 1512, 1528 and 1513 were
destroyed on shots 1, 2 and 4, in two chunks. Removed object IDs progress
`[1513]` -> `[1513,1529]` -> `[1513,1514,1529]`. Both workers ACK each exact
scene before commit; six native publications follow three commits. Other
catalog objects remain intact. Each client records three successful original
setter, destroy and effect callback pairs. Seven shots consume ammo 20 -> 13;
three contact fragiles and four contact ground. Each client records seven
original shot/ground-effect pairs and 369 snapshots. Server sample path is
69.28 m for the moving tank; 3461 contiguous movement advances per worker.
No worker/channel/native errors or diagnostic trace caps occur in the prefix.
Six unsupported camera requests are explicitly reported without domain change.

Diagnostic limitation: the existing passive array recorder accepts length <=1.
The third cumulative native array is therefore `unrecognized`, not a recorded
`[1,257]`. Server publication and original destroy/effect returns are verified;
the complete two-element native array itself is **NOT_RECORDED**. Visual
effects and passage remain owner OBSERVED. The two private install ledgers
match all 37 immutable files and 28 source files per client; runtime logs are
excluded from immutable checks (`installed-audit.json`).
Rendered client reconnect after destruction is NOT_RUN; scene restoration is
covered by real owned-worker and wire/session tests, not a rendered rejoin claim.

Required remaining gate: the frozen prefix contains no AP/health/death/wreck
event; both tanks have 90 HP throughout. Thus live kill, wreck hit and survivor
control after death are **NOT_RUN_IN_THIS_CAPTURE**, despite the general owner
answer. One narrow follow-up has been requested in the same running battle.
This is missing acceptance evidence, not a reported gameplay failure; do not
repeat the accepted crate/ground test or infer missing health callbacks.

Follow-up `native-acceptance02/` extends those prefixes without changing their
bytes. Owner explicitly answered «Уже проверил — всё работает» for live kill,
wreck and survivor control. VERIFIED in both clients: HP 90 -> 60 -> 30 -> 0,
one death, three armorHit and five armorRicochet callback pairs. Of nine AP
outcomes, one is explicitly `Unsupported(VehicleDamageFactor)` with no damage
or native effect; this existing test_lab limitation is not counted as success.
Five active survivor controls after death, about 0.225 m displacement and
changing yaw prove continued control. Native callback traces have no errors
or caps; raw packet capture reached its 48000-packet cap before shots 17–20,
while stdout/native JSONL continued. Late raw wire coverage is NOT_RECORDED.

The killing shot is shot 20 and exhausts ammunition. There are no post-death
shots or wreck contacts in this second prefix. **Only the wreck-hit gate is
still NOT_RUN in that prefix.** The general owner response does not substitute a missing shot.
Native01 was stopped using PID/executable/creation-time receipts after evidence
was frozen. Fresh native02 uses the identical gateway05, physics pool and
catalog with full ammunition; the accepted crate test need not be repeated.
Preparation initially rejected the still-installed previous configuration
before mutation, then succeeded after ledger rollback of both approved copies.
An invalid stop receipt label was also rejected at argument parsing, before
any process action; the corrected `stop-ammo01.json` records the actual stop.
Fresh native02 entry (`native02-ready01.json`) confirms battle
17544553518420522740, both tanks at 90 HP, native prediction started and zero
accepted shots. The later owner answer «я снаряды потратил)) думаю работает»
is uncertain and does not close the wreck gate. The exhausted ammunition
belongs to native01; native02 initially opened with a full loadout.

Physics provenance (`boundary/physics-provenance01.json`) verifies matching
Program.cs/CheckedInput.cs SHA256 in both private/root Portable PDBs, identical
locked dependencies and SDK 9.0.315. Different DLL hashes reflect different
generated informational commit versions and build paths; binary identity is
not claimed. Private physics 20 PASS and root real two-worker gateway tests
remain separately identified evidence. Current source hashes match all 88
recorded files; repeated layout check PASS: 76 files, 22 relocations.
`native-acceptance01/source-audit-resolved.json` records 22 successful checks;
the earlier overly broad FAIL from comparing different build hashes is retained
and corrected by this source/provenance audit, not erased.

## Final native02 owner gate

Owner then explicitly confirmed «да, проверил - работает» and «в новых окнах».
Frozen `native-acceptance03/` is the separate fresh native02 battle
17544553518420522740; it does not overwrite or relabel the earlier prefixes.
Server events now verify four shots: three AP hits reduce HP 90 -> 60 -> 30
-> 0, and shot 4 hits the wreck with damage 0 and HP 0 -> 0. Ammunition goes
20 -> 16. This closes the missing actual wreck-shot event, while the earlier
native01 evidence retains accepted multiple-object destruction, passage,
ground, aim/reload and survivor control on the identical runtime and catalog.
VERIFIED in each client: three original armorHit callback pairs and one
armorResisted pair for shot 4 (effect code 1, hasPiercedHit false, target HP 0,
original return offset 397). Exactly one death per client, no duplicate health
or death from the wreck hit, one survivor post-death shooting return and 39
post-death snapshots each. No native/server faults or capture caps in this
fresh prefix; stderr is empty. The owner confirms the rendered effect in both
new windows. `native-audit.json` and `server-audit.json` preserve exact fields,
lines and hashes. The required combined native gate has no remaining blocker.

## Reproduction and rollback

```powershell
python -B -X utf8 server/build.py gateway --test --out local/build/server/gateway-integrated-world-p06o-05
python -B -X utf8 server/build.py physics --out local/build/server/physics-integrated-p06o-01
python -B -X utf8 tools/destructible_catalog.py --out <fresh-local-output> --native-export <owned-export> --native-sha256 <sha256>
python -B -X utf8 local/evidence/20261012-p06o-destructible-import-01/start_stand.py server --run native01 --mode runtime --build gateway-integrated-world-p06o-05 --pool local/build/server/physics-integrated-p06o-01/pool-near.json --destructible-catalog local/evidence/20261012-p06o-destructible-import-01/resource-contract/native-join02/manifest.json d5063d067763589647198acf79f65ef747fb5293f4d7b38d619f301217ac73a3
python -B -X utf8 local/evidence/20261012-p06o-destructible-import-01/start_stand.py a --run native01 --mode runtime
# Wait for SESSION_ACTIVE before launching b with the same run/mode.
```

The current fresh follow-up uses those same start commands with `--run native02`.
Both slots were prepared with `prepare_stand.py --slot a|b --run native02
--mode runtime`, after rollback of the native01 install ledgers. Exact launch
arguments and process identities are in `launch-{server,a,b}-native02.json`.

Build/output directories must be fresh; existing paths above identify performed
runs and must not be overwritten. Native preparation/start/stop commands and
process identity guards are in evidence `oracle01-commands.txt` and own helpers.
Credentials remain in private files, never command arguments or report output.

Rollback: stop only receipt-verified own processes; restore installed diagnostic
ledgers with `tools/interactive_client.py rollback --out <install-directory>`.
Launch accepted P06N gateway04 with physicsP06N01/pool-near, geometry/AP/terrain
and `--destructible-test-lab`. Original client/resources and accepted binaries
were not modified. Revert the P06O merge with `git revert -m 1 <P06O-merge>`
if a source rollback is needed; keep accepted binaries and evidence intact.

Acceptance: **PASS_OWNER_AND_SERVER_CUMULATIVE_TEST_LAB**. Native identity,
multiple-object destruction/passage, ground, live HP/death, survivor control
and the fresh wreck-hit gate pass within the stated limits. Owner-authorized
ordinary no-ff merge/push applies. Exact final branch/merge/remote SHAs are
recorded in the private evidence `merge-receipt.json` after publication.
One next recommended card: original-resource-driven tree fall/state replication
with matching movement/projectile collision on this accepted cumulative runtime.
