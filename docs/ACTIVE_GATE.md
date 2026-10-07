# ACTIVE_GATE — 2026-10-07

## Current phase

Branch policy: one card per `codex/<card-id>-<purpose>` branch; merge an accepted
card into `main` with `--no-ff`, then verify the remote SHA. See
[owner-approved workflow](07_CODEX_WORKFLOW.md).

`ORG-0A_PROJECT_HYGIENE_20261007` is the active organizational card. Its
scope is the repository boundary, baseline commit/tag, canonical status and
evidence index. It does not change gateway protocol, battle/fire/reload,
physics, deployed service or client files. Baseline identifiers and the delivery record are in the
[ORG-0A receipt](evidence-index/ORG-0A.md).

The battle phase is **P03 — IN_PROGRESS**. P03 is not a completed two-client
authoritative-world acceptance.

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

No second client or projectile/hit/damage run is performed by ORG-0A.

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
| `python -B -X utf8 server/check_layout.py` | `PASS_SERVER_SOURCE_LAYOUT` (52 source files, 22 relocations) | `local/evidence/20261007-org-0a-project-hygiene-01/layout-check.txt` |
| `python -B -X utf8 -m unittest discover -s tests -q` | `FAIL` — 2028 run, 10 errors, 4 skips | `local/evidence/20261007-org-0a-project-hygiene-01/unittest-discover-q.txt`; triage is ORG-0B |
| stale path/link inventory | `RECORDED` | `docs/research/ORG-0A_STALE_PATHS_20261007.md` |
| explicit Git allowlist | `PASS_EXPLICIT_SOURCE_ALLOWLIST` | ORG-0A baseline receipt |

## Rollback

The baseline is a new local history point; no reset or destructive tree
operation is used. Undo later organizational commits with a reviewed revert
commit if the owner asks; preserve history.
Do not remove the original/research clients, `local/` evidence, deployed EXE,
supervisor, identity service or existing P03 receipts. Remote force-push is
forbidden.

## Single next step

After ORG-0A, run `ORG-0B` to classify the 10 unittest errors and 4 skips and
prepare the smallest repair plan without changing P03 battle code.
