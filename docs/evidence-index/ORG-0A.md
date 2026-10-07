# ORG-0A project hygiene receipt — 2026-10-07

## Scope and result

Organizational card only: explicit source allowlist, Git baseline/tag, current
gate and P03 indexes. Gateway protocol, battle/fire/reload, physics and deployed
service were not edited; no owner client was launched. Source/client/deployed
hash checks are in `local/evidence/20261007-org-0a-project-hygiene-01/pins.json`.

## Git receipt

- Baseline commit: `7d2a600b7e65ecd7568cb5a985af941313dffb60`.
- Annotated tag: `baseline-2026-10-07`; tag object: `0b0fa2f54abd5f14ec39147b034a70757bd5227a`.
- Branch: `main`.
- Remote: `https://github.com/NSNull97/wot_9.1_restart.git`.
- Remote was absent locally; `origin` was added only after checking.
- `git ls-remote --heads origin` before commit: exit 0, no heads.
- Author name/email were supplied directly by the owner and configured locally;
  no global Git setting was changed.
- Delivery status is recorded separately after the actual merge/push, to avoid
  claiming a future network action in its own commit. Machine receipt:
  `local/evidence/20261007-org-0a-project-hygiene-01/result.json`.
  It records exact base/branch/merge SHAs, remote URL, branch and push status;
  failures retain the exact command output. No successful push is implied by
  this source snapshot.
- Explicit included-file list: [ORG-0A_BASELINE_ALLOWLIST.txt](ORG-0A_BASELINE_ALLOWLIST.txt).
- The baseline contains 474 files. Current source/docs candidate list including
  ORG-0A is [ORG-0A_SOURCE_ALLOWLIST.txt](ORG-0A_SOURCE_ALLOWLIST.txt).
- ORG-0A branch: `codex/org-0a-project-hygiene`; base is the historical baseline.
  Accepted organizational head will be merged with `--no-ff`; main will retain
  the recorded ORG-0B test debt. [Branch policy](../07_CODEX_WORKFLOW.md).

## Boundary

`local/`, both client copies, caches, dependencies, targets, dumps, captures,
private keys/config, databases and built executables are excluded. `web/data/`
is also excluded: generated client catalog datasets remain local pending
redistribution review. A clean clone therefore needs local content/dependencies
from the documented research setup; this is a source baseline, not a portable
release or deployment bundle.

Four original image_gen PNGs are included by exact path, with provenance in
`web/ASSETS.md`. Imported client images, client code and third-party repository
archives are not included. External repositories remain reference-only under
the existing pinned report `docs/research/EXTERNAL_REPOSITORIES_20261007.md`.

The high-confidence secret-pattern scan found one reviewed negative-test URL
fixture in `web/tests/network.test.mjs` (host.test), not a real credential.
This bounded scan is not a full security audit.

## Checks

| Command/check | Actual result | Evidence relative to project root |
|---|---|---|
| `python -B -X utf8 server/check_layout.py` | PASS: 52 source files, 22 relocations | `local/evidence/20261007-org-0a-project-hygiene-01/layout-check.txt` |
| `python -B -X utf8 -m unittest discover -s tests -q` | FAIL: 2028 tests, 10 errors, 4 skips | `local/evidence/20261007-org-0a-project-hygiene-01/unittest-discover-q.txt` |
| Verbose suite, solely to identify skip names/reasons | FAIL: same 2028 tests, 10 errors, 4 skips; exact skips listed in ORG-0B | `local/evidence/20261007-org-0a-project-hygiene-01/unittest-discover-v.txt` |
| Explicit allowlist/type/secret-pattern scan | PASS explicit paths/types; staged/head checks in machine receipt | `local/evidence/20261007-org-0a-project-hygiene-01/git-allowlist-review.json` |
| Markdown local links | PASS current navigation; three historical missing source links preserved and classified | `local/evidence/20261007-org-0a-project-hygiene-01/local-links.json` |
| Old path inventory | Recorded, with relocation/deployed/historical classifications | [full occurrence list](ORG-0A_STALE_PATHS.tsv), [interpretation](../research/ORG-0A_STALE_PATHS_20261007.md) |
| New native run / two-client battle / Linux | NOT_RUN in this card | Out of scope |

The three broken historical links point to old `gateway091.rs`/`hangar091.rs`
in `docs/research/OVERNIGHT_20261005_FILES.md`; their canonical targets are
`server/gateway/src/session.rs` and `server/gateway/src/account/hangar.rs`, as
recorded in `server/layout.json`. Historical records were not rewritten.
Old-source live reads in historical readers remain explicit ORG-0B defects;
their fresh native rerun is NOT_RUN, and the unit failures remain FAIL.

## Card acceptance boundary

Organizational acceptance requires a documentation-only delta from the
baseline, unchanged runtime source and deployed/client pins, valid current
links/canonical paths, exact allowlist membership, and the separately recorded
unit-test debt. The current-head checks are executed after committing this
branch and before merge; exact head/result is recorded in the machine receipt.
The historical baseline contains 474 files; the ORG-0A tree adds only documents.
Existing owner P03D/P03E receipts are not re-run or expanded by this card.

## Rollback and remaining work

Use a reviewed revert commit for organizational changes, preserving the baseline
and history. Do not use reset --hard, force-push or deletion of ignored local
inputs/evidence. P03D and P03E owner receipts remain accepted; full P03 remains
IN_PROGRESS.

Single next step: [ORG-0B](../plans/ORG-0B_TEST_TRIAGE_BACKLOG.md), classify
the 10 unittest errors and 4 skips and prepare the minimal repair plan.
