# P03F — accepted shared shots and neutral initial gun pose

**PASS_OWNER_P03F_SAME_PC_WORLD_SHOT_SOUND_NEUTRAL_POSE.** The owner confirmed
“Башня и ствол нормально, звук есть” on build08 after the prior synchronized
movement and visible remote-shot confirmations. P03F's scoped same-PC card is
accepted. **Full P03 remains IN_PROGRESS**: the separate two-PC repeat is NOT_RUN.
The previous negative observations and pending receipts remain immutable history.

Evidence root: `local/evidence/20261007-p03f-two-client-world-01/`.
Owner receipt: `aim-01/owner-acceptance.json`, with two hashed owner screenshots.
Native receipt: `aim-01/result.json`; final commit/merge/remote/process state:
`aim-01/handoff.json`. This index does not claim publication before that receipt.

## Problem and correction

The original shared server sent ammo/reload updates but no native neighbour shot
event. The [shot correction](P03F_SHOT_CUE.md) publishes accepted shots once per
created recipient using the original `Vehicle.showShooting(1)` and preserves
server ammo/reload authority. Rejected or duplicate inputs cannot manufacture
extra effects, and rejoin does not replay past shots.

The owner's next concrete symptom was a neighbour turret reversed 180 degrees
and a raised gun. VERIFIED: its old `gunAnglesPacked=0` creation seed decodes as
yaw `-180°`, pitch `-25°`. The MS-1 `_37mm_Gochkins` limits and original #717
ten-bit yaw / six-bit pitch format yield neutral **`0x8030` (32816)**. The
original decoder returns **yaw 0°, pitch +0.142857°**, within half a pitch bin of
horizontal. Only shared creation changes; archived one-vehicle probes retain
their original contracts. See `aim-01/static-receipt.json` and original bytecode
and resource hashes. No client code writes turret or gun state.

OBSERVED: both fresh native clients received both vehicles with packed value
32816. Their original `gun_rotation_shared.decodeGunAngles` returned the pinned
angles and actual `[-25°,8°]` limits. A has 145 complete frozen snapshots, B 144;
both contain their own and neighbouring vehicle. Native engine screenshots were
inspected, including a side view of the correctly oriented neighbour. The owner
then confirmed the pose and remote sound.

The fresh audited prefix contains **3669 packets, 3661 channel frames, 2 native
logins, 4 vehicle creations, 1132 pose publications and 6 shot cues**, zero
crypto/transport/callback errors. The later frozen native prefixes each contain
4 original completed shot calls; the first 3 on each match the 6 audited cues.
These cutoffs differ explicitly. Server-assigned world slots follow login order:
this run A owns vehicle `152043525`, B `152043523`. The independent audit derives
ownership from the actual native binding, not the order of process launches.

## Changes and checks

Changed runtime sources: `shared/model.rs` (bounded accepted shot events),
`shared/mod.rs` (recipient cursors), `shared/server.rs` (reliable delivery),
`shared/wire.rs` (original cue and neutral creation seed), and
`client_patch/sr_interactive.py` (passive original call/angle observations).
`tests/test_shared_lab_control.py` and Rust regression tests cover the contracts.
STATUS, ACTIVE_GATE, P03 indexes, plan and research record the actual acceptance.

| Executed check | Result | Evidence |
|---|---|---|
| Canonical isolated build08 | **353 Rust PASS** | `local/build/server/gateway-shared-world-08/result.json` |
| Legacy shared-source build04 | **351 Rust PASS** | `local/build/server/gateway-shared-world-legacy-04/result.json` |
| Final full Python suite | **2053 tests, 0 errors/failures, 2 skips**, 38.673 s | `unittest-05.json`, `.txt` |
| Source layout | PASS, 56 files / 22 relocations | `server/check_layout.py`, handoff receipt |
| Pinned CPython 2.7.3 client compilation/install | PASS, both copies | `install-a-05`, `install-b-05` |
| Native decode/creation/shot proof | PASS within the frozen cutoffs | `aim-01/result.json`, `capture-audit-05.json` |
| Owner initial pose and remote sound | **PASS_OWNER** | `aim-01/owner-acceptance.json` |
| Original/research/deployed EXE guards | PASS, unchanged pinned hashes | `aim-01/result.json` |

Python skips remain the Windows symlink capability and the Python-2.7-only test
under Python 3. Current 2.7.3 client compilation is a separate PASS. Earlier
build06 fixture failures and Python run03 errors remain in the shot receipt.

- Build08 SHA256: `60d1209523d15b5fcb2aa62d4ce518925212c3c92e48951a3e1e66b8bf03dd66`.
- Legacy04 SHA256: `3bb3d4e0f36385386e0c75ced4d90bc7e0ec069b3340c93a97c419e2c2cef7ae`.

## Commands actually run

From `D:\WoT_9.1_Server`; launch IDs and evidence files are single-use.

```powershell
python -B -X utf8 server/build.py gateway --test --out local/build/server/gateway-shared-world-08
python -B -X utf8 server/build.py gateway --legacy --test --out local/build/server/gateway-shared-world-legacy-04
python -B -X utf8 local/evidence/20261007-p03f-two-client-world-01/run_checks.py --run 05
python -B -X utf8 server/check_layout.py
python -B -X utf8 local/evidence/20261007-p03f-two-client-world-01/prepare_stand.py --slot a --run 05
python -B -X utf8 local/evidence/20261007-p03f-two-client-world-01/prepare_stand.py --slot b --run 05
python -B -X utf8 local/evidence/20261007-p03f-two-client-world-01/start_stand.py server --run 05 --build gateway-shared-world-08
python -B -X utf8 local/evidence/20261007-p03f-two-client-world-01/start_stand.py a --run 06
python -B -X utf8 local/evidence/20261007-p03f-two-client-world-01/start_stand.py b --run 05
python -B -X utf8 local/evidence/20261007-p03f-two-client-world-01/audit_capture.py --run 05
python -B -X utf8 local/evidence/20261007-p03f-two-client-world-01/collect_neutral_pose.py
python -B -X utf8 local/evidence/20261007-p03f-two-client-world-01/record_owner_pose.py
```

Server listens on loopback login `20124` and base `20126`; deployed services and
original/research clients are not replaced. The game windows were already closed
when the first stop guard ran; it aborted without killing anything. The matching
build07 gateway was then stopped, documented in `aim-01/stop-build07.json`.
The new server is bounded to one hour from 11:20:30 UTC.

## Limits, rollback and one next step

This fixes the **initial** turret/gun pose. Continuous dynamic aiming replication
is still unsupported; the card does not claim it. Two temporary allied MS-1s,
small flat movement boxes and loopback are the accepted scope. Terrain following,
the colored grid artifact, hit/damage, enemy visibility, equipment, persistence,
warm leave-to-hangar and two-PC/LAN remain outside this acceptance.

Stop only exact current launch-receipt PIDs/images before rollback. Restore each
overlay with `python -B -X utf8 tools/interactive_client.py rollback --out
local/evidence/20261007-p03f-two-client-world-01/install-a-05` and the matching
`install-b-05` command. Preserve all evidence/copies. Source rollback is a reviewed
revert of the accepted card/merge; the prior isolated build07 remains available
with its documented initial-angle defect. No original/deployed restore is needed.

**Single next recommended step:** a separate card for authoritative dynamic
turret/gun aiming and native replication. Do not confuse neutral creation with
aiming synchronization; full P03 still needs its separate two-PC repeat.
