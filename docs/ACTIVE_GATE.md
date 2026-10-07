# ACTIVE_GATE — 2026-10-07

## Current phase

Branch policy: one card per `codex/<card-id>-<purpose>` branch; merge an accepted
card into `main` with `--no-ff`, then verify the remote SHA. See
[owner-approved workflow](07_CODEX_WORKFLOW.md).

`P03G_SHARED_GUN_AIM_20261007`: **NATIVE_PATH_PASS_OWNER_PENDING**.
Branch `codex/p03g-shared-gun-aim`, base `8709b07151cdf4c8238ae918044e1b34855bfb6d`.
Native target input, server-owned rate/limit integration, per-entity property
delivery and original client rotator initialization are implemented. Both real
clients received native callbacks; independent native math samples constrain
the approximate test_lab solver. Canonical/legacy tests **363/361 PASS**;
Python **2054, 0 errors/failures, 2 skips**; layout **57/22 PASS**.
Owner continuous rotation/elevation and repeat-shot regression are **NOT_RUN**,
so this card is **NOT_ACCEPTED** and must remain unmerged. See
[current P03G receipt](evidence-index/P03G.md) and
[research/limits](research/P03G_SHARED_GUN_AIM.md).
Full P03 and the separate two-PC requirement remain open. Next: one owner
manual check in the already launched two-client battle.

## Accepted previous card and historical P03F receipt

`P03F_TWO_CLIENT_WORLD_20261007`:
**PASS_OWNER_P03F_SAME_PC_WORLD_SHOT_SOUND_NEUTRAL_POSE**.
Two real native processes share the world; abrupt closure/re-authentication
preserved the other session and returning ammunition. The owner confirmed
synchronized movement and visible remote shooting after build07's shot cue.
The zero packed-angle seed was then corrected on build08; both native clients
received neutral angles and the owner confirmed “Башня и ствол нормально, звук
есть”. The scoped same-PC card is **ACCEPTED**. Source branch:
`codex/p03f-two-client-world`; exact commit/merge/remote state is in its final
local handoff receipt. Evidence: [accepted P03F receipt](evidence-index/P03F_GUN_POSE.md).

This explicit local lab uses two temporary allied MS-1s and bounded flat
kinematics. It does not grant garage inventory or replace the deployed service.
Original/research/deployed EXE guards match their pre-card hashes. Native PNGs
show own/ally vehicles, floating geometry and a colored grid artifact; this is
not physics or final rendering acceptance. Warm Leave-to-hangar is unavailable
in the lab; full process close/re-authentication is the observed exit path.

Previous `ORG-0B_TEST_REPAIR_20261007`: **PASS_TEST_REPAIR**, 2047 Python tests
with 2 documented skips; separate Python 2.7 check PASS. Historical receipt:
[ORG-0B](evidence-index/ORG-0B.md). P03F's latest full Python count is 2053.

The battle phase is **P03 — IN_PROGRESS**. Same-PC P03F acceptance does not close
the separate two-PC repeat or imply full authoritative combat acceptance.

ORG-0A local organizational gate: **PASS**; remote publication:
**PASS_REMOTE_VERIFIED** after the owner ran the four delivery commands.
Independent `ls-remote` verification matched main `0b7b8ac6f9ef4a955840df7e690a6e73640dd16f`,
tag object `0b0fa2f54abd5f14ec39147b034a70757bd5227a` and baseline target
`7d2a600b7e65ecd7568cb5a985af941313dffb60`. Earlier HTTP 408/TLS errors remain history.
The follow-up documentation delivery is recorded separately in the machine receipt. Exact attempts and SHAs:
[ORG-0A receipt](evidence-index/ORG-0A.md).

## Accepted P03 subcards

| Subcard | Status | Verified evidence | Remaining boundary |
|---|---|---|---|
| P03D native ammunition HUD panel | `PASS_OWNER_NATIVE_AMMO_PANEL_HUD` | `local/evidence/20261007-battle-ammo-panel-01/owner-test/owner-panel-acceptance-01.json`; owner screenshot SHA256 `8a0777a437d78d73dd58dec3566f645759b1a68211205ba95448c64225f55c64` | Input profile contains no equipment/consumables; equipment message and zero-count selection are not accepted |
| P03E native fire/reload/consumption | `PASS_OWNER_NATIVE_FIRE_RELOAD_CONSUMPTION` | `local/evidence/20261007-battle-fire-reload-01/owner-test/owner-acceptance-fire-reload-03.json`; 5 owner shots, AP `20 -> 15`, 5 completion callbacks | Projectile, hit, damage, visibility, physics, equipment and persistence remain outside this subcard |
| P03F shared native same-PC laboratory | `PASS_OWNER_P03F_SAME_PC_WORLD_SHOT_SOUND_NEUTRAL_POSE` | `local/evidence/20261007-p03f-two-client-world-01/aim-01/owner-acceptance.json`; native movement/rejoin, remote shots/sound and neutral initial pose | Dynamic aiming, two-PC/LAN and the other explicitly listed lab limitations remain open |

The owner fire/reload gate is therefore **closed**. Earlier build07/build08
`NOT_RUN` or route-ready text is retained as historical evidence; it does not
override the later build09 owner receipt.

## Full P03 gate

`IN_PROGRESS`. P03F's same-PC evidence now includes:

- two independently authenticated native processes in battle `2448793866150762938`;
- different Avatar/vehicle IDs and own/ally visual distinction in native PNGs;
- changed server X/Z positions received in both native entity traces;
- independent AP counts and five owned reload completion callbacks;
- abrupt A closure, continuous B session, A rejoin with the same vehicle/AP18.

Owner confirmed movement. Build07 adds 14 accepted shots / 28 native original
handler completions and owner-visible remote shooting. Build08's neutral initial
turret/gun pose and remote sound are now owner-confirmed. The separate two-PC
repeat remains NOT_RUN; dynamic aiming is unsupported.
Same-PC observations do not claim LAN/public deployment compatibility.

Projectile/hit/damage, visibility, equipment and the full battle lifecycle are
separate later roadmap gates (P06/P07/P08); their NOT_RUN status is not
silently turned into the P03 two-client acceptance criterion.

P03F runs two native clients; projectile/hit/damage remains outside this card.

## Dependencies and pinned inputs

- Client: two independent manifested copies `local/clients/p03f/a` and `b` from
  pinned original #717. Only fixed instance-name strings change in each EXE;
  separate profiles and owned compatibility overlays. Original and prior
  `WoT_0.9.1_RU_0717_research` stay outside Git and untouched by this card.
- Client EXE SHA256 (both copies checked read-only by ORG-0A):
  `86f5e351d44c12e0d2b89ed741ee9a4e70d21f234c39aa9cfd709536d49f04ed`.
- Static method table SHA256:
  `f63fab8f43d204d4a6fc9d819b21321ca46558e23108370d1c2b878fb4072429`.
- Client Avatar static input SHA256:
  `7531aa5ad00add000ae8b5465de88907a27285628347234d5c53d230bde7a13b`.
- Content catalog `web/data/catalog.v1.json` SHA256:
  `d66aad60c13d83807f49b1ebfc8cc89f330e658ed3223706169f763052547567`.
- Canonical P03E isolated EXE SHA256:
  `460d5d68dd47b6599085d2775c316d4e1192a2d53c45f87aaabf86d9341e7970`.
- Legacy P03E isolated EXE SHA256:
  `558a6b72a65e980395e146a48570e1ef1cec2b7accfcbe2c1cdb2a8e832e114a`.
- Deployed gateway guard SHA256 (unchanged):
  `daef0dde9e012beac4e0f363bf66b672ec4a154473be4b05b00cfe4cc0608c3b`.
- P03F canonical build08:
  `60d1209523d15b5fcb2aa62d4ce518925212c3c92e48951a3e1e66b8bf03dd66`.
- P03F legacy build04:
  `3bb3d4e0f36385386e0c75ced4d90bc7e0ec069b3340c93a97c419e2c2cef7ae`.
- Per-copy EXE/trace/screenshot hashes: [P03F receipt](evidence-index/P03F.md)
  and its local `result.json`.
- ORG-0A historical baseline commit (tag `baseline-2026-10-07`): `7d2a600b7e65ecd7568cb5a985af941313dffb60`.

## Checks for previous accepted P03F card

| Check | Result | Evidence |
|---|---|---|
| Canonical/legacy final builds | PASS, 353 / 351 tests | `local/build/server/gateway-shared-world-08/` and `gateway-shared-world-legacy-04/` |
| `python -B -X utf8 server/check_layout.py` | PASS, 56 source files, 22 relocations | P03F `layout-01.json`, repeat before handoff |
| Latest Python suite | 2053 run, 0 errors/failures, 2 skips | P03F `unittest-05.txt` / `.json` |
| Pinned Python 2.7.3 client compilation | PASS | P03F A/B install05 preparation receipts |
| Current native packet prefix | PASS, 3669 packets, 0 crypto/transport/callback errors | P03F `capture-audit-05.json` |
| Shared movement and remote shooting/sound | PASS_OWNER | `aim-01/owner-acceptance.json`, earlier owner receipts |
| Initial neutral turret/gun fix | PASS_NATIVE_AND_OWNER | `aim-01/result.json`, owner receipt and PNGs |
| Windows symlink / Python-2.7-only unittest under Python 3 | SKIPPED with explicit reasons | Final Python log; not converted to PASS |
| Two-PC repeat | NOT_RUN | Local-only mode |

## Rollback for previous accepted P03F card

Stop only this card's current launch-receipt image paths. Restore A/B overlays
using `tools/interactive_client.py rollback --out <install-a-05 or install-b-05>`
after the corresponding process stops; optional instance-string rollback uses
each stopped isolated copy's hash-verified EXE backup. Full paths and commands:
[P03F receipt](evidence-index/P03F_GUN_POSE.md). Source rollback uses a reviewed revert
of the accepted card/merge. Preserve original/research clients, all local
evidence, prior receipts and deployed services. No reset or force-push.

## Single next step

Owner checks continuous turret/gun tracking in both windows and two shots on
the current P03G stand. The initial P03F pose remains accepted; the new P03G
continuous-aim card stays pending until its own evidence is confirmed.
