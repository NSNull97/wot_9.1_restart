# ACTIVE_GATE — 2026-10-07

## Current phase

Branch policy: one card per `codex/<card-id>-<purpose>` branch; merge an accepted
card into `main` with `--no-ff`, then verify the remote SHA. See
[owner-approved workflow](07_CODEX_WORKFLOW.md).

`P03F_TWO_CLIENT_WORLD_20261007`:
**PASS_NATIVE_SAME_PC_DATA_PLANE_OWNER_CONTROL_PENDING**. Two real native
processes reached one battle; both received changed server positions. Abrupt
closure/re-authentication preserved the surviving session and the returning
actor's ammunition. Mandatory owner control confirmation remains pending;
the card is **NOT_ACCEPTED**, on `codex/p03f-two-client-world`, unmerged.
Exact scope and evidence: [P03F receipt](evidence-index/P03F.md).

This explicit local lab uses two temporary allied MS-1s and bounded flat
kinematics. It does not grant garage inventory or replace the deployed service.
Original/research/deployed EXE guards match their pre-card hashes. Native PNGs
show own/ally vehicles, floating geometry and a colored grid artifact; this is
not physics or final rendering acceptance. Warm Leave-to-hangar is unavailable
in the lab; full process close/re-authentication is the observed exit path.

Previous `ORG-0B_TEST_REPAIR_20261007`: **PASS_TEST_REPAIR**, 2047 Python tests
with 2 documented skips; separate Python 2.7 check PASS. Historical receipt:
[ORG-0B](evidence-index/ORG-0B.md). P03F's final full Python count is 2052.

The battle phase is **P03 — IN_PROGRESS**. P03 is not a completed two-client
authoritative-world acceptance.

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

Remaining: owner confirmation that movement/turn is visibly correct between
the two windows, and the separate two-PC repeat when a tester is available.
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
- P03F canonical build05:
  `8c6c48e2186fd4ccb7bcbe12a410a423e25ad78e9ba76471b796569b3108111e`.
- P03F legacy build02:
  `66622f901e0a6c657be06e9b948accd6f331bb52482c95d57b2663d700ad4af0`.
- Per-copy EXE/trace/screenshot hashes: [P03F receipt](evidence-index/P03F.md)
  and its local `result.json`.
- ORG-0A historical baseline commit (tag `baseline-2026-10-07`): `7d2a600b7e65ecd7568cb5a985af941313dffb60`.

## Checks for this card

| Check | Result | Evidence |
|---|---|---|
| Canonical/legacy isolated Rust builds | PASS, 346 / 344 tests | `local/build/server/gateway-shared-world-05/` and `gateway-shared-world-legacy-02/` |
| `python -B -X utf8 server/check_layout.py` | PASS, 56 source files, 22 relocations | P03F `layout-01.json`, repeat before handoff |
| Final Python suite | 2052 run, 0 errors/failures, 2 skips | P03F `unittest-02.txt` / `.json` |
| Pinned Python 2.7.3 client compilation | PASS | P03F A/B install02 preparation receipts |
| Actual native capture prefix | PASS, 20,620 packets, 0 crypto/transport/callback errors | P03F `capture-audit-02.json` |
| Same-PC world, changed pose, abrupt rejoin | OBSERVED, owner controls pending | P03F `result.json`, frozen traces and engine PNGs |
| Windows symlink / Python-2.7-only unittest under Python 3 | SKIPPED with explicit reasons | Final Python log; not converted to PASS |
| Two-PC repeat | NOT_RUN | Local-only mode |

## Rollback

Stop only this card's current launch-receipt image paths. Restore A/B overlays
using `tools/interactive_client.py rollback --out <install-a-02 or install-b-02>`
after the corresponding process stops; optional instance-string rollback uses
each stopped isolated copy's hash-verified EXE backup. Full paths and commands:
[P03F receipt](evidence-index/P03F.md). Source rollback uses a reviewed revert
of the unmerged checkpoint. Preserve original/research clients, all local
evidence, prior receipts and deployed services. No reset or force-push.

## Single next step

Owner performs the short P03F visible movement/turn check in the two running
windows: move A briefly, release input, switch to B and confirm A's changed
position/direction. This is the remaining same-PC owner-control gate; no new
roadmap card starts before its result.
