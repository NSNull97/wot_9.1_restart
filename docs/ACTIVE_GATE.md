# ACTIVE_GATE — 2026-10-07

## Current phase

Branch policy: one card per `codex/<card-id>-<purpose>` branch; merge an accepted
card into `main` with `--no-ff`, then verify the remote SHA. See
[owner-approved workflow](07_CODEX_WORKFLOW.md).

`ORG-0B_TEST_REPAIR_20261007`: **PASS_TEST_REPAIR**. All ten reproduced unittest
errors are repaired. Full Python 3 run: **2047 tests, 0 errors/failures, 2 skips**;
the Python 2.7 bytecode check passed separately. Windows symlink refusal remains
NOT_RUN because this account cannot create a symlink. Exact scope and evidence:
[ORG-0B receipt](evidence-index/ORG-0B.md).

ORG-0B changes test fixtures and offline profile4 import selection. Gateway
protocol, battle/fire/reload, physics, frozen legacy verifiers, deployed service
and client files remain unchanged. Historical source checks use real archived
bytes with the original pins; they do not certify the current live gateway.

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

`IN_PROGRESS`: the following are still required before P03 acceptance:

- two independent native clients in one server-authoritative battle;
- one battle ID and two independent sessions in server logs;
- own/other vehicle distinction and server-state changes visible at both clients;
- exit/re-entry isolation: one client closing does not stop the other;
- a repeat from two PCs when a second tester is available.

Projectile/hit/damage, visibility, equipment and the full battle lifecycle are
separate later roadmap gates (P06/P07/P08); their NOT_RUN status is not
silently turned into the P03 two-client acceptance criterion.

No second client or projectile/hit/damage run is performed by ORG-0B.

## Dependencies and pinned inputs

- Client: verified research copy `WoT_0.9.1_RU_0717_research`; original copy is
  outside Git and untouched.
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
- ORG-0A historical baseline commit (tag `baseline-2026-10-07`): `7d2a600b7e65ecd7568cb5a985af941313dffb60`.

## Checks for this card

| Check | Result | Evidence |
|---|---|---|
| `python -B -X utf8 server/check_layout.py` | `PASS_SERVER_SOURCE_LAYOUT` (52 source files, 22 relocations) | `local/evidence/20261007-org-0b-test-repair-01/layout.txt` |
| Python 3 full suite with existing export and fresh scratch directory | `PASS_WITH_DOCUMENTED_SKIPS` — 2047 run, 0 errors/failures, 2 skips | `local/evidence/20261007-org-0b-test-repair-01/unittest-after.txt` |
| Python 2.7 pinned bytecode check | `PASS` — 1 test | `local/evidence/20261007-org-0b-test-repair-01/python273-bytecode-attempt02.txt` |
| profile4 CLI and package modes | `PASS` — 4 commands, identical results | `local/evidence/20261007-org-0b-test-repair-01/profile4-cli-modes.json` |
| Windows symlink refusal | `NOT_RUN` — insufficient account capability | Full suite skip reason; no system permission changes |

## Rollback

Undo ORG-0B with a reviewed revert of its merge on a separate branch; retain
the original baseline/tag and prior organizational history. Exact merge SHA
is in the ORG-0B machine receipt. No reset or destructive tree operation is used.
Do not remove the original/research clients, `local/` evidence, deployed EXE,
supervisor, identity service or existing P03 receipts. Remote force-push is
forbidden.

## Single next step

The next recommended card is P03 two-client shared-world preparation and
acceptance: establish two independent native sessions in one battle and verify
shared state plus exit/re-entry isolation. It is not started by ORG-0B.
