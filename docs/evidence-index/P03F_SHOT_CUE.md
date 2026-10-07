# P03F follow-up — neighbour receives the original gun effect

**PASS_NATIVE_AND_OWNER_VISIBLE_REMOTE_SHOT.** This shot-specific receipt records
build07. Subsequent build08 pose/sound owner acceptance and current rollback are
in the [final P03F receipt](P03F_GUN_POSE.md). Owner synchronized
movement is now PASS. The owner confirmed a specific defect on build05: the
shooter sees/hears its own shot, while the neighbouring client gets no sound or
effect. The correction was developed in `codex/p03f-two-client-world`.
The fresh build07 run now has owner confirmation that remote shooting is visible.
Audio was not explicitly confirmed. The owner next identified the neighbour's
180-degree turret / fully elevated gun; its initial packed-angle fix is tracked
in [P03F follow-up](../plans/P03F_SHARED_AIM.md).

Plan and scope: [P03F](../plans/P03F_TWO_CLIENT_WORLD.md). This is the same card's
shared-event correction, not projectile/hit/damage implementation.
Evidence root: `local/evidence/20261007-p03f-two-client-world-01/`.

## Cause and change

VERIFIED_STATIC: original #717 `Avatar.__showTimedOutShooting` eventually invokes
its own `Vehicle.showShooting(burstCount, True)` if no network shot effect arrived.
Thus the shooter's local effect is not evidence of a server event broadcast.
Build05 emitted ammo/reload callbacks only; neighbours had no shooting event.
This agrees with the owner's observed missing neighbour sound/effect.

The server now records each **accepted** shot with a bounded domain sequence,
actor slot and server tick. Each connected ready recipient gets the original
`Vehicle.showShooting(1)` on the shooter's entity. Pinned transport/def sequence:
`selectEntity=0x12` + `UINT32 entity`, `showShooting=0x3b` + `UINT8 burstCount`,
then `selectPlayerEntity=0x13` to restore Avatar selection.

Only entities already acknowledged as created receive the event. The reliable
channel preserves the message on retry; per-session cursors prevent requeueing.
Rejected reload/no-ammo inputs create no event. Rejoin starts after the previous
events. Ammo, event and cursor/queue changes commit together in the existing
cloned transaction. The total history is bounded by this lab's 40 AP rounds.
Original native prediction handles the shooter's own duplicate suppression.

A shared-only passive profiler records original `Vehicle.showShooting` call and
return, entity ID, started/player flags, burst and prediction flag. It never
invokes the handler, writes entity state or manufactures an effect.

Static proofs and exact owner messages:
`fire-cue-01/static-receipt.json`, `fire-cue-01/original-shot-handlers.json`,
`fire-cue-01/owner-observation.json`. These bind original EXE/packed defs/bytecode
and measured method/PE registration tables by SHA256; client bytes stay ignored.

## Executed checks

| Check | Actual result | Evidence |
|---|---|---|
| Canonical isolated build07 | PASS, 352 Rust tests | `local/build/server/gateway-shared-world-07/result.json`, logs |
| Legacy shared-source build03 | PASS, 350 Rust tests | `local/build/server/gateway-shared-world-legacy-03/result.json`, logs |
| Final Python suite | 2053 tests, 0 errors/failures, 2 skips, 37.372 s | `unittest-04.json`, `unittest-04.txt` |
| Layout | PASS, 56 files / 22 relocations | `server/check_layout.py`; follow-up handoff receipt |
| Pinned Python 2.7.3 client compilation/install | PASS, both copies | `install-a-04/`, `install-b-04/` |
| Previous owner run's complete packet prefix | PASS, 47,787 packets / 47,775 frames, zero crypto/transport errors | `capture-audit-02final.json` |
| Owner synchronized movement | PASS on build05 | Exact owner messages in `fire-cue-01/owner-observation.json` |
| Neighbour shot sound/effect on build05 | FAIL_OWNER_REMOTE_SHOT_CUE | Same owner receipt; not relabeled PASS |
| Native shot delivery after correction | PASS: 14 accepted shots, 28 cues, 14 original handler completions on each client; A observed 8 remote shots, B 6 | `fire-cue-01/result.json`, frozen native prefixes |
| Current native packet prefix | PASS: 5743 packets, 5731 frames, 3 logins, 1733 poses, 28 cues, zero errors | `capture-audit-04.json`; cutoff 2026-10-07T11:10:01Z |
| Owner visible remote shooting | PASS; audio not explicitly confirmed | `fire-cue-01/owner-observation-02.json`, two hashed owner PNGs |

Regression coverage includes one cue per recipient on duplicate reliable input,
independent private ammo, no cue on rejected shots, uncreated-entity gating, no
stale replay after creation/rejoin, and rollback of ammo/event/cursor if output
publication fails. These are unit/contract checks, not a substitute for sound QA.

OBSERVED: all 28 receiving native calls had `isPredictedShot=false`, started
entities and the original final return offset 183 after the shoot extra. Their
per-recipient entity order matches all 28 independently decoded cue frames.
The prefixes contain no shared rejection/failure or native observer error event.

Earlier failed attempts are retained: build06 had three new test-fixture failures
(extra readiness notifications and an output fault inserted before the wrong
transaction boundary); final tests represent the correct ready/session boundary.
Python run03 exposed 13 isolated-profiler fixture errors: the new selector read
shared settings before checking the relevant source/method. The selector now
short-circuits on the original Vehicle handler first; full run04 is green.
Two final Python skips remain Windows symlink capability and a Python-2.7-only
test under Python 3. Client compilation under 2.7.3 is a separate check.

## Launch and evidence

Current stand uses gateway build07 with login `127.0.0.1:20124`, base
`127.0.0.1:20126` and the existing owned identity bridge. Native client EXEs retain
their previous isolated mutex patch. Only their reversible diagnostic overlay
was updated; original/research/deployed EXE guards remain unchanged.

Commands run from `D:\WoT_9.1_Server`:

```powershell
python -B -X utf8 server/build.py gateway --test --out local/build/server/gateway-shared-world-07
python -B -X utf8 server/build.py gateway --legacy --test --out local/build/server/gateway-shared-world-legacy-03
python -B -X utf8 local/evidence/20261007-p03f-two-client-world-01/run_checks.py --run 04
python -B -X utf8 server/check_layout.py
python -B -X utf8 local/evidence/20261007-p03f-two-client-world-01/prepare_stand.py --slot a --run 04
python -B -X utf8 local/evidence/20261007-p03f-two-client-world-01/prepare_stand.py --slot b --run 04
python -B -X utf8 local/evidence/20261007-p03f-two-client-world-01/start_stand.py server --run 04 --build gateway-shared-world-07
python -B -X utf8 local/evidence/20261007-p03f-two-client-world-01/start_stand.py a --run 05
python -B -X utf8 local/evidence/20261007-p03f-two-client-world-01/start_stand.py b --run 04
python -B -X utf8 local/evidence/20261007-p03f-two-client-world-01/collect_shot_cue.py
```

Paths/launch receipts are single-use; a later restart requires fresh launch IDs.
An initial A-only hangar launch was stopped for current profiler installation;
it is preserved as `launch-a-04.json`, `runtime-a-03/` and
`fire-cue-01/stop-a04-hangar.json`. It never started a two-client battle.

- Build07 EXE SHA256: `87498f8606bef4b376c49df6f81c0159f944865b215c7d428b4d1fb607070226`.
- Legacy build03 SHA256: `dfc5527b5ff5f9d988ce299affd5349c1885ec32ef8b3c504214dedc4f0360d1`.
- Exact checkpoint, live PIDs, source/receipt hashes and native entry status:
  final `aim-01/handoff.json`; build07's frozen proof is `fire-cue-01/result.json`.

Changed source files: `server/gateway/src/shared/{model,mod,wire,server}.rs`,
`client_patch/sr_interactive.py`, `tests/test_shared_lab_control.py`. Plan,
research, STATUS and P03 indexes record the revised acceptance boundary.

## Limits, rollback and next step

Remote muzzle effect and gun sound are the only new native behaviour. There is
no tracer trajectory, hit, damage, terrain physics, enemy visibility or inventory
grant. The same two-account/loopback/one-hour/capture bounds apply. Native audio
is not explicitly owner-confirmed; visible remote shooting is confirmed. Unit
tests do not certify audio. Owner screenshots are 25 seconds apart and are not
simultaneous measurements of turret angles.

Rollback: stop only the current launch-receipt image paths. Restore the client
overlays with `tools/interactive_client.py rollback --out
local/evidence/20261007-p03f-two-client-world-01/install-a-04` and the matching
`install-b-04` command. Preserve all copies/evidence. Source rollback is a reviewed
revert of this follow-up checkpoint; build05 is the preserved prior server build.
No deployed service or original client needs restoration.

The initial-angle follow-up and explicit sound check are now accepted on build08.
**Single next step:** the separate dynamic aiming card specified in the final receipt.
