# P03F — native two-client laboratory research

Card: [plan](../plans/P03F_TWO_CLIENT_WORLD.md). Branch:
`codex/p03f-two-client-world`; base `3e59991f41d4459bbe571afcec04207ce2c20e12`.
Evidence root: `local/evidence/20261007-p03f-two-client-world-01/`.
Same-PC native/owner acceptance is now PASS, scoped by the
[final receipt](../evidence-index/P03F_GUN_POSE.md). This document distinguishes each run.

## Verified inputs and implementation boundaries

| Category | Finding | Concrete input/evidence |
|---|---|---|
| VERIFIED | Previous dispatcher has one live session and rejects a second login; own drive fixes vehicle `0x09100003` and the primary profile | Base commit `server/gateway/src/session.rs`, `drive/world.rs`, `arena/vehicle.rs` |
| VERIFIED | Original #717 EXE has two startup mutex names at exact offsets | EXE SHA256 `86f5e351d44c12e0d2b89ed741ee9a4e70d21f234c39aa9cfd709536d49f04ed`; `local/evidence/20261002-p01-bootstrap/pe-mutex-final/pe-startup.json`, UTF-16 strings at `20731348` and `20731996` |
| VERIFIED | Existing secondary account has a real MS-1 garage fixture with no crew/ammo | `local/server/fixtures/271022a3-41e0-406e-b6fa-59930c320442/r1-catalog2/fixture.json`; this card does not modify it |
| VERIFIED | Own native callbacks, cell/space layout, detailed entity creation, roster and player binding already have pinned #717 contracts | Accepted P03D/P03E receipts and `arena/codec.rs`, `arena/vehicle.rs`, `drive/world.rs` |
| INFERRED before native run | Those layouts can carry two distinct allied vehicle IDs and separate player IDs | New bounded codecs in `shared/wire.rs`; encoder tests alone do not establish this |
| OBSERVED in native run01 | Both actual processes authenticated, became distinct native Avatars and requested both native vehicle creations | `gateway-01.stdout.log`, `runtime-a/`, `runtime-b/`, `capture-audit-01.json` |

The new CLI is explicitly `legacy091-shared-lab KEY DIGEST GATEWAY CAPTURE`.
It waits for two authenticated, synchronized hangars, then assigns two temporary
allied MS-1 actors. Each slot has a distinct vehicle (`152043523`, `152043525`)
and Avatar (`152043522`, `152043524`), one shared server battle ID/clock, private
native channel, independent ammo/reload and a bounded movement intent queue.
The shared laboratory uses a 4-by-4-metre flat kinematic box per vehicle at two
nearby spawn points. This is not terrain/contact simulation or historical physics.
Both actors are allied; no enemy visibility or hidden-position claim is made.

Old account/drive routes keep their primary-profile validation and ordinary CLI.
New dispatcher admission checks real credentials for every new attempt, distinct
accounts and cipher keys/peers, unique handoff/token capabilities, two active
sessions and retirement capacity including all live reservations. Base handshakes
route by handoff; encrypted traffic routes by its exclusive bound endpoint. A
failed whole envelope/piggyback tree cannot publish partial domain commands.

Disconnect parks only the relevant controller. Reauthentication attaches the
same account to its original world slot; ammo and cooldown are not granted again.
The world has two account slots for its entire bounded process lifetime. A third
account and LAN connections are unavailable in this local card.

## Independent client copies

`tools/shared_client_copy.py` copied all resources into
`local/clients/p03f/a/` and `local/clients/p03f/b/`, with no hard links or junctions.
Only the two fixed-width UTF-16 instance names in each EXE change. The backup,
offsets, strings and hashes are recorded in each `sr_lab_copy.json`.

- A EXE: `b627530f709b10b38c2da3b0ee57524e79b861e6911dbfc98824cffcec77da08`.
- B EXE: `510174793cbd1fbf43e2abfc73b6a9b5ab4273f44d2f9c9be01208922bf60fe1`.
- Original/research configured roots are not modified by this card.
- Copy validation initially rejected its own padded mutex name; the check was
  corrected to include the fixed-width underscore padding. The already copied
  bytes were preserved and validated; no second 30-GB copy was made.
- Each installed copy has its own profile, runtime and screenshot directory.
  Install/rollback hold that copy's actual instance mutex and verify file hashes.

Explicit shared installs initialize the same original arena services that the
ordinary Fight button initializes, before server-driven entry. This compatibility
change does not create/move entities, alter HP/ammo/clock or replace the protocol.
An explicit one-shot private control invokes the original local login method for
the two pre-existing owned test accounts. Credentials are not printed or passed
in process arguments; the client consumes/removes its control file.

## Native run01 and correction

Run01: gateway build03, EXE
`4362a5f9377fd9a397d0a61985475788007f540921fc2b146d241b8de315dc88`.
Both processes ran simultaneously, reached `SHARED_READY` under battle
`16952150665331696954` and had distinct own vehicle IDs. However, movement binding
failed at the next incoming envelope. This run is **FAIL_NATIVE_INITIAL_BINDING**,
not successful two-client gameplay.

Independent Python crypto/transport inspection: **261 packets**, **253 channel
frames**, **2 verified native logins**, two peer slots, zero crypto/transport parse
errors. Both actual clients sent application bytes `8a01000006`: neutral
`vehicle_moveWith(0)`, followed by correction acknowledgement `6`. The new route
incorrectly required correction before the neutral command. Later sequences were
therefore rejected because the receive sequence had not advanced.

The fix admits this harmless neutral command before correction, retaining the
binding ACK requirement and refusing nonzero movement before correction. A test
using the actual bytes reproduced the failure on build04 (345 passed, 1 failed)
and passed on build05. The failed build/run evidence remains intact. Both run01
processes and its gateway were stopped by exact PID/path checks before replacement.

## Initial build05 checks and unresolved native gate (historical)

- Canonical build05: **346 Rust tests PASS**, EXE SHA256
  `8c6c48e2186fd4ccb7bcbe12a410a423e25ad78e9ba76471b796569b3108111e`.
- Legacy build02: **344 Rust tests PASS**, EXE SHA256
  `66622f901e0a6c657be06e9b948accd6f331bb52482c95d57b2663d700ad4af0`.
- Python full run before the final native stop correction/passive observer:
  **2052 tests, zero errors/failures, two skips** (`unittest-01.json`). The known
  symlink and Python-version conditions remain explicit skips.
- Final current-source Python run: **2052 tests, zero errors/failures, two skips**
  in 40.218 seconds (`unittest-02.json` and `.txt`). Both skips are still explicit;
  this card does not substitute ORG-0B's separate Python 2.7 test as a new run.
- Later affected interactive/shared checks: **28 PASS**; preparation compiled
  the current client sources with the existing Python 2.7.3 toolchain.
- Source layout: **56 source files / 22 single-source relocations PASS**.
- `computer-use` window capture failed twice (`FrameArrived timed out` and
  `window capture timed out`); no visual acceptance was inferred from those calls.
  The shared-only observer records actual native entity positions and requests
  at most four screenshots through the original `BigWorld.screenShot` writer.

## Native run02: observed same-PC data plane

Build05 entered both independently authenticated processes into battle
`2448793866150762938`. Initial sessions `1` and `2` control vehicles `152043523`
and `152043525`. Both native engine PNGs show two roster rows, the player's own
tank, the allied tank with the other account's name and the ammunition HUD.
Both read-only native traces contain the same arena ID and inverted own/other
flags. This replaces the initial inference about parameterized layouts with an
OBSERVED result on this Windows/#717 pair.

The actual second client sent nonzero movement/turn intents. Four distinct
changed X/Z positions are present in both native traces and the independently
decoded server packets (comparison rounded to four decimals). Example final X/Z:
`[-55.4386, -445.7800]` instead of spawn `[-54.4999, -445.8130]`. Native rendered Y
is about `33.69943`, whereas server Y is `33.770267`; exact rendered position
identity and terrain collision are not claimed. Native PNGs visibly show floating
tanks and a colored grid artifact. Fixed plane motion explains the absence of
terrain following; the separate grid's cause is **UNKNOWN**. These screenshots
prove entity visibility, not acceptable final rendering or physics.

Native input and server callbacks show separate AP consumption: session `1`
`20 -> 19 -> 18`; session `2` `20 -> 19 -> 18 -> 17`. The independent wire audit
checks five owned reload-start callbacks and five completion callbacks. It also
checks the rejoin binding's remaining AP count. Input quality and the owner's
visual control assessment are still pending; observed traffic is not a fabricated
owner acceptance statement.

At `2026-10-07T10:47:51.6724991Z`, only A PID `21500` was terminated after its
full image path was checked. Gateway retired session `1` at tick `3464`, reason
`retry_exhausted`, survivors `1`. B PID `20620` kept session `2`, battle ID, pose
and ongoing ticks (frozen prefix reaches `5577`). A PID `31968` then authenticated
as new session `3`, slot `0`, same Avatar/vehicle; binding at tick `3909` delivered
**18 AP**, also visible in its native screenshot. This is an observed **abrupt
process-close/re-authentication** check, not a graceful Leave-to-hangar test.

The audit covers a frozen complete-line prefix of the still-running capture:
**20,620 packets**, **20,608 channel frames**, **3 authenticated native logins**,
**6,548 pose publications**, zero crypto/transport/targeted callback errors.
It retains the prefix hash and every packet hash. Later live packets are outside
that receipt. No `SHARED_REJECT`/`SHARED_FAILED` or native observer error events
occur in the separately frozen runtime/log prefixes. Earlier run01 failure remains
preserved and is not relabeled PASS.

Evidence: [P03F index](../evidence-index/P03F.md), local `result.json`,
`capture-audit-02.json`, `capture-manifest-02-prefix.jsonl`, `native-prefix-01/`,
and the three process launch receipts. Original/research EXE and deployed gateway
hash guards match the pre-card pins. Card status is
`PASS_NATIVE_SAME_PC_DATA_PLANE_OWNER_CONTROL_PENDING`; **P03 IN_PROGRESS**.

Remaining limits: two-PC/LAN repeat NOT_RUN; owner visual movement confirmation
pending; warm native Leave-to-hangar is unavailable in this mode (the current
Leave branch retires the session); at most two retained account slots and one
hour of process lifetime. Full physics, turret aiming, projectiles, hits, damage,
enemy visibility, equipment and persistent inventory are not accepted here.

## Owner follow-up: remote shot cue

The owner confirmed synchronized movement in both windows and clarified that
shooting sound/effect was present only on the firing client. Movement is therefore
`PASS_OWNER_SYNCHRONIZED_MOVEMENT`; remote shooting on build05 is
`FAIL_OWNER_REMOTE_SHOT_CUE`. These are separate observations, preserved verbatim
in `fire-cue-01/owner-observation.json`.

VERIFIED_STATIC original bytecode explains the asymmetry:
`Avatar.__showTimedOutShooting` calls its own vehicle's `showShooting(..., True)`
after the waiting timer. The normal network `Vehicle.showShooting(UINT8)` invokes
the original shoot extra and suppresses already-predicted own shots. Build05 had
no broadcast of this Vehicle callback. Its ammo/reload receipts alone never
proved a visible shot on neighbours.

The correction publishes a bounded, server-owned accepted-shot event to each
ready recipient that already knows the shooting vehicle. Native selection is
`0x12 + entity UINT32`, callback `0x3b + burstCount UINT8`, followed by `0x13`
to restore the player's entity. Per-peer event cursors and existing reliable
sequence handling prevent duplicate enqueue; reconnect/late creation do not
replay historical effects. There are at most 40 events under the finite lab ammo
budget. No synthetic tracer or damage outcome was added.

Canonical build07 **352 PASS**; legacy build03 **350 PASS**; full Python run04
**2053 tests, zero errors/failures, two skips**. Initial fixture/selector failures
remain preserved. The final previous-run audit covers **47,787 packets**, **47,775
frames** with zero errors, including the owner's two additional B shots
`17 -> 16 -> 15`. Fresh build07 battle `12600843064120895129` produced 14 accepted
shots, 28 native cue frames and 14 original `showShooting` final returns on each
client. A received 8 remote shots, B 6. All were non-predicted; per-recipient IDs
match the independent wire audit. Owner confirms remote shooting is visible.
Audio is not explicitly confirmed. Proof: `fire-cue-01/result.json` and
`owner-observation-02.json`; packet prefix 5743 / 5731 frames, zero errors.

Owner then clarified the remaining visual defect: the neighbour's turret is
rotated 180 degrees and its gun appears fully elevated. VERIFIED: shared
creation still emits `gunAnglesPacked=0`; original `decodeGunAngles` maps this
to yaw `-pi` and the minimum pitch bound. It does not mean neutral angles.
The screenshot timers differ by 25 seconds; no simultaneous dynamic-aim claim
is drawn from them. Correcting the initial neutral pose is the narrowed follow-up.
The existing unsupported dynamic aiming remains an explicit separate limitation.

## Neutral initial gun pose and final same-PC acceptance

VERIFIED: the equipped `_37mm_Gochkins` has absolute pitch limits `[-25°,8°]`.
The original packed format encodes neutral as `0x8030`, not zero; decoded pitch
is +1/7 degree due to six-bit quantization. Shared creation now sends this value
without changing archived probes. Current passive observations read the actual
native property and call the original pure angle decoder; they never move a gun.

OBSERVED on build08: both actual clients received both neutral properties and
decoded `0° / +0.142857°`. Frozen runtime A/B have 145/144 complete snapshots,
and inspected native PNGs show the corrected neighbour pose. An independent
3669-packet prefix validates 4 native creations and 6 cues with zero errors.
Authentication order assigned A vehicle525, B vehicle523; audit ownership is
derived from native binding, not hard-coded from process labels.

The owner's two new screenshots and exact answer “Башня и ствол нормально, звук
есть” close the scoped pose/sound gate. P03F is
`PASS_OWNER_P03F_SAME_PC_WORLD_SHOT_SOUND_NEUTRAL_POSE`; full P03 is IN_PROGRESS.
Final canonical/legacy checks: 353 / 351 Rust PASS; Python 2053 tests, no failures
or errors, two documented skips. Evidence: `aim-01/result.json`,
`aim-01/owner-acceptance.json`; commands and limits in the final receipt.

Full proof, commands, failures, limits and current rollback:
[P03F shot cue receipt](../evidence-index/P03F_SHOT_CUE.md).

## Rollback

Stop only PIDs whose image path equals this card's launch receipt. Roll back the
latest A/B install (`install-a-05`, `install-b-05` after the neutral-angle follow-up)
with `tools/interactive_client.py rollback --out <install-dir>`
after the associated game is stopped; all before hashes/backups are preserved.
For the optional EXE-name rollback, verify the current patched SHA and restore
`WorldOfTanks.exe.p03f-backup` to `WorldOfTanks.exe` in that same stopped isolated
copy. Do not delete copies/evidence or touch the original client. The accepted
ordinary gateway was never replaced. Scoped same-PC native/owner checks are now
accepted; Git delivery status is recorded separately after the actual operations.
