# ORG-0A project hygiene receipt — 2026-10-07

## Scope and result

Organizational card only: explicit source allowlist, Git baseline/tag, current
gate and P03 indexes. Gateway protocol, battle/fire/reload, physics and deployed
service were not edited; no owner client was launched. Source/client/deployed
hash checks are in `local/evidence/20261007-org-0a-project-hygiene-01/pins.json`.

## Git receipt

- Local organizational acceptance: `PASS_ORG_0A_HEAD`; remote publication:
  **`PASS_REMOTE_VERIFIED`** after owner delivery and independent remote SHA
  verification. The local history is retained; this is not a
  stable/green release.
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
  failures retain the exact command output. The verified owner delivery is
  documented below; any later follow-up push has its own exact-head receipt.
- Explicit included-file list: [ORG-0A_BASELINE_ALLOWLIST.txt](ORG-0A_BASELINE_ALLOWLIST.txt).
- The baseline contains 474 files. Current source/docs candidate list including
  ORG-0A is [ORG-0A_SOURCE_ALLOWLIST.txt](ORG-0A_SOURCE_ALLOWLIST.txt).
- ORG-0A branch: `codex/org-0a-project-hygiene`; base is the historical baseline.
  Accepted organizational head will be merged with `--no-ff`; main will retain
  the recorded ORG-0B test debt. [Branch policy](../07_CODEX_WORKFLOW.md).

### Historical failed delivery attempts

Accepted initial organizational head: `8eba3b78945b7a1a136784f68d0749bcf53019cd`.
First accepted `--no-ff` merge / attempted remote head:
`ebd6f782016c275c3e548491c310a1dd2f3a7646`.
The delivery-failure receipt is a subsequent documentation-only continuation
of the same ORG-0A branch; final local SHA is in the machine receipt.

1. `git -c credential.interactive=never push -u origin main` — exit 1:
   `error: RPC failed; HTTP 408 curl 22 The requested URL returned error: 408`,
   `send-pack: unexpected disconnect while reading sideband packet`,
   `fatal: the remote end hung up unexpectedly`.
   The trailing `Everything up-to-date` is not success: exit code is 1 and
   `git ls-remote --heads origin` afterwards returned no heads (exit 0).
2. One ordinary retry of the same history with `--progress` and command-local
   low-speed timeout — exit 128:
   `fatal: unable to access 'https://github.com/NSNull97/wot_9.1_restart.git/': schannel: failed to receive handshake, SSL/TLS connection failed`.
3. `git push origin baseline-2026-10-07` — NOT_RUN because main delivery is
   blocked by the network. The annotated tag remains local.

Exact output: `local/evidence/20261007-org-0a-project-hygiene-01/push-main.txt`,
`push-main-attempt02.txt`, `remote-heads-after-push01.txt` under that directory.
TLS verification was not disabled; credentials and remote history were not
altered. These failed attempts are not reclassified as successful.

### Owner delivery independently verified (2026-10-07)

The owner reported running the four commands from the handoff. Their terminal
exit codes were not captured here; the resulting remote refs were independently
read with `git ls-remote --heads origin` and
`git ls-remote --tags origin 'baseline-2026-10-07*'` (both exit 0):

| Remote ref | Verified SHA |
|---|---|
| `refs/heads/main` | `0b7b8ac6f9ef4a955840df7e690a6e73640dd16f` |
| `refs/tags/baseline-2026-10-07` (annotated object) | `0b0fa2f54abd5f14ec39147b034a70757bd5227a` |
| `refs/tags/baseline-2026-10-07^{}` (target commit) | `7d2a600b7e65ecd7568cb5a985af941313dffb60` |

All three matched the local refs. Status: **PASS_REMOTE_VERIFIED**.
Evidence: `local/evidence/20261007-org-0a-project-hygiene-01/owner-delivery-01/`.
The previous blocked machine receipt and audit outputs are preserved there in
`before/`. This follow-up only updates documentation in the existing ORG-0A
branch; the subsequent docs merge/push and final remote SHA are in `result.json`.

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

Single next step: ORG-0B, classify the 10 unittest errors and 4 skips and
prepare the minimal repair plan. It remains a separate unstarted card and is
not executed by this ORG-0A follow-up.
