# P06P — Prohorovka cumulative map migration

## Goal and state

Owner requested replacing the test map with Prohorovka while continuing map
object work. This card migrates the accepted P06O cumulative native battle:
movement, grounded suspension, aim/RMB, ammunition/reload, world/live/wreck
contacts and effects, and catalog-based fragile removal. Trees follow as a
separate card after this prerequisite. Base main:878ade656906918f2aa9c095621feb4f504be603.
Branch:codex/p06p-prohorovka-cumulative. Acceptance:PENDING_NATIVE_OWNER. Oracle entry observed; gameplay acceptance pending.

## Evidence and knowledge categories

Evidence root: `local/evidence/20261012-p06p-prohorovka-01/`.

VERIFIED: original #717 arena list assigns asset05_prohorovka arena type4,
not5. Native arena INT32 and space asset are now derived from one MapId.
Arena XML SHA7a3898a15922ff6b350e0ba91fe5ceab53b916ad1bcfdf1a198002f9d33e863d.

VERIFIED: fresh projectile mask128 export (not driving mask18) has3904
instances,285350 triangles; source709793=kept285350+excluded424443,
degenerate0. Manifest SHA3db1ad3859ae2f5fed678ac5f148005cff38a3c915bb33dde3303de22e22bef7.
Physics mesh428597 triangles; terrain769x769,144 chunks without holes.
Exact source/buffer pins are centralized in drive/map_profile.rs; readers
verify size/SHA before decoding and reject mixed maps. Original resources
are read-only; their package/member pins precede inventory XML decoding.

VERIFIED: full inventory finds712 fragiles,2943 trees,71 falling atoms,
58 structures and120 undefined objects. Nine whole fragile colliders meet
the accepted rule: sixenv014_Toilet and one eachmle019_GerBoxes1/2/3.
703 exclusions have explicit reasons. MAX_OBJECTS64/removed40 unchanged.
Native preprocessing must still read all44 fragile-containing chunks before
joining the nine eligible objects; no partial output or ordinal guess.
Importer verification preserves the accepted Karelia inventory byte-for-byte.

OBSERVED: private physics25/25 on original configurations verifies both maps,
two Prohorovka lane poses/contact/travel, emptyIPC3 equality withIPC1,
cumulative removal/retry/restore and malformed map/hash/generation rejection.
This does not prove rendered native passage. The exact root DLL also passed25/25:
`boundary/worker-ipc-root02/receipt.json` (ba724f06...d2ae).

OBSERVED: oracle01 both approved clients loaded Prohorovka with grounded tanks,
original reticle and20ammo. Original screenshot in runtime-b-oracle01/screenshots.
UNKNOWN: owner-visible driving/FX and eligible-object passage remain untested. Historical penetration/damage and full object
coverage are not claimed; existing test_lab approximations remain explicit.
Tree flags from12 pinned BSP resources all have bit128, so the native
projectile mask excludes those faces. Tree fall/collision needs a separate
original contract; do not silently add trees to the static projectile subset.

## Changes and commands

Changed implementation and checks:

- `client_patch/destructible_catalog_probe.py`
- `server/gateway/src/arena/codec.rs`
- `server/gateway/src/drive/map_profile.rs`
- `server/gateway/src/drive/worker.rs`
- `server/gateway/src/drive/worker/catalog.rs`
- `server/gateway/src/main.rs`
- `server/gateway/src/session.rs`
- `server/gateway/src/shared/fragiles.rs`
- `server/gateway/src/shared/fragiles_tests.rs`
- `server/gateway/src/shared/impact.rs`
- `server/gateway/src/shared/mod.rs`
- `server/gateway/src/shared/model.rs`
- `server/gateway/src/shared/obstacles.rs`
- `server/gateway/src/shared/server.rs`
- `server/gateway/src/shared/server_catalog_tests.rs`
- `server/gateway/src/shared/terrain.rs`
- `server/gateway/src/shared/wire.rs`
- `server/physics/CheckedInput.cs`
- `server/physics/Program.cs`
- `server/physics/README.md`
- `tests/test_destructible_catalog.py`
- `tests/test_destructible_catalog_probe.py`
- `tools/destructible_catalog.py`
- `tools/wg_probe/src/main.rs`

Planning/status/report changes are in docs/plans/P06P_PROHOROVKA_CUMULATIVE.md,
docs/STATUS.md,docs/ACTIVE_GATE.md and this report. No vehicle physics
coefficients are changed. Source-derived spawn changes only origin/yaw.

Canonical builds (fresh ignored output):

```powershell
python -B -X utf8 server/build.py physics --out local/build/server/physics-integrated-p06p-01
python -B -X utf8 server/build.py gateway --test --out local/build/server/gateway-integrated-world-p06p-03
python -B -X utf8 tools/destructible_catalog.py --map 05_prohorovka --out local/evidence/20261012-p06p-prohorovka-01/import/catalog-inventory01
```

Canonical gateway03:603 Rust PASS, executable SHA
03b4f4a31d44a1d7c1122ad317f849a6a7a648e6969a644f87b1cbe5a54921da.
Tested source c03b3b571186971f7a5cd96717cd6a31bc857e03. Build01 failed on
one missing test-fixture map field; build02 had602PASS/1FAIL because the new
negative test expected InvalidInput instead of established InvalidData.
Both failures retained; corrected full build03 passed. Legacy entrypoint also
builds from the same sources: gateway-legacy-p06p-01, compile PASS (no extra tests).
Root Python:47PASS/1existing Windows symlink-privilege SKIP, including importer,
probe, shared controls and layout. Layout77files/22relocations PASS. Receipts
and source snapshot:verification01/. No runtime source changed after this build.

Root physics DLL SHA d28063bb88f0214919518c43891303dcc4bbcf1a252fbd37319bec7ca6a9a586.
Pool physics-integrated-p06p-01/pool-near.json SHA
c80199db93cbcf27eac6192e4d929fb97da915f141e29773ab2564a504b989c2.
Only Prohorovka spawn_origin changes to[-205,6.046776865530075,458],yaw0.
Other movement coefficients match the accepted Prohorovka configuration exactly;
Karelia pool entry stays unchanged. Both near lanes settle with6contacts,
clearance3.4–8.1cm, drive and brake without an airborne frame.

The additional IPC1-versus-IPC3 bitwise trajectory comparison FAILS for laneB
from frame14 near a fence: maximum difference1.65cm/0.0169rad. LaneA and both
initial settled states match exactly. This comparison is not the native
cumulative acceptance criterion; it is retained as a limitation, not PASS.
Source coverage is exact428328base+269selected=428597, no omissions/duplicates.
Contact ordering after splitting Jolt shapes is INFERRED; exact cause UNKNOWN.
Evidence:boundary/near01/receipt03.json,difference-review04.json and preserved
failure receipts. This does not promise bit identity across different scene
representations. B meets the intact fence after~2.9m; use its actual passage.

Native launches use ledger-backed helpers in the evidence root. Stop receipts,
plan/patch ledgers, explicit build/pool hashes and exact process identities are
retained. Original client unchanged. Oracle uses the same cumulative AP/terrain/
physics stack while reading original object identities; final runtime adds the
native-joined catalog and disables the preprocessing probe.

## Rollback and next gate

P06O gateway05/physics01/pool-near/catalog remain intact. Stop only receipt-
verified own processes, restore installed diagnostic ledgers, and restart the
accepted P06O Karelia configuration. Revert the P06P branch changes if needed.
No merge/push while any required native gate is FAIL/NOT_RUN.

## Native setup and pending owner gate

Oracle01 completed in both clients:44chunks/2156entries/two stable passes,
exports byte-identical SHA062c3fce8c2d7dd0ece94bfe6322a2a3b80f2a2d22be7de1906a8eb854f37e60.
Audit native-contract/oracle01-audit.json pins immutable log prefixes with no
faults. Owner confirmed closing both intermediate windows himself. Supplying
the identical export twice was explicitly rejected as duplicate; native join
uses the single distinct digest and retains both-copy equivalence evidence.
Final import/native-join01/manifest.json SHA
2a3cd7cb62e9dd6638aef843776584b179d13e8da83b00cf3c19168588c47e57,
worker SHA6f385e1fc79397c0019778ffcb077274e0eac11c0710148ebe56f5497495ced3.

Final native01 server PID38128, clientA36752/clientB26228, battle
13347218205700078493. Both worker READY on05_prohorovka with6contacts;9objects
in6area controllers bound to the exact imported catalog. All gateway, pool,
source and installation identities are retained in launch/prepare receipts.
The authoritative runtime does not accept oracle hits as gameplay inputs.
Exact repeatable launch arguments:launch-native01-command.json; source
helpers prepare_stand.py/start_stand.py/stop_stand.py in the evidence root.
Native scripts use the original #717 callbacks and owned diagnostic copies.

Manual steps: drive and turn/aim briefly; go around the intact fence into the
courtyard, destroy two separate crate groups and traverse the cleared spots;
shoot ground/static cover, then the other vehicle until destruction and once
at its wreck, verify both-client effects and continued survivor control.
Ammo/reload and RMB aim lock must remain correct. Test_lab supports the9whole
fragiles; trees, fences and compound buildings are not generalized yet.

One next gate: owner acceptance of this fresh cumulative Prohorovka battle.
No merge before that result; existing P06O remains the accepted fallback.
