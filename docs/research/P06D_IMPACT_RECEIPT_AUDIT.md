# P06D — bounded impact receipt audit

Status: **PASS_SHAPE_AUDITOR / NATIVE_HIT_NOT_RUN**.

Card: `P06D_IMPACT_RECEIPT_AUDIT`
Branch: `codex/p06d-impact-receipt-audit`
Base: `83bba99` (`Merge P06C controlled capture plan`)

This card adds a bounded JSON receipt auditor for the P06C controlled MS-1 AP
capture. It validates the server-owned admission → launch → segment →
intersection → classification → terminal → optional damage → replay chain and
rejects client authority fields, non-finite values, duplicate JSON keys, stage
omissions, sequence rollback, identity conflicts that mutate state, and
out-of-bound lists/coordinates. It does not run a client or server and does not
implement a hit solver or historical penetration formula.

## Result and boundary

`tools/impact_capture_audit.py` returns:

- `PASS_CAPTURE_SHAPE_ONLY` for a complete receipt whose shape and authority
  boundaries satisfy P06C;
- `NOT_RUN_INCOMPLETE_CAPTURE` when bounded JSON is readable but a required
  impact stage is missing;
- `FAIL_INVALID_RECEIPT` (CLI exit 2) for malformed, unsafe or contradictory
  input.

Even the pass result carries `native_impact_status=NOT_VERIFIED_BY_AUDITOR`.
The auditor cannot turn a synthetic fixture, screenshot or tracer into proof of
native impact. A future native receipt must still be correlated with its local
process manifest and server evidence.

The verifier pins the active scope to shell `2570` / profile `ms1_ap_2570`,
requires one server `shot_id` and battle/ruleset identity, checks monotonic
server sequence/ticks and finite vectors, and requires all five P06C negative
controls. The replay row must report one total ammo/projectile side effect,
zero replay duplication, and a `SHOT_ID_REUSE_CONFLICT` for a conflicting
identity. A damage row is optional for a clean miss/non-penetration but, when
present, has exactly one damage token and non-increasing target HP.

## Checks and evidence

Targeted unit run: `tests.test_impact_capture_audit` — 11 tests, 0 failures.
Full main regression with the repository's explicit UTF-8 launcher: `python -B -X utf8 -m unittest discover -s tests -p 'test*.py'` — 2083 tests, 0 failures/errors, 4 skips (log SHA-256 `86cdbbff98bc655b4478f1666125963ed8430f8942d549183664db178eb3a471`).
`py_compile` passed for the tool and its tests; `git diff --check` and
`git show --check` passed. A deliberately incomplete local receipt returned
`NOT_RUN_INCOMPLETE_CAPTURE` with `missing required stage: launch`:

- `local/evidence/20261008-p06d-impact-receipt-audit-01/incomplete.json`
  SHA-256 `bc3f08a64aee84748f24a8bad11b73f1d44d652812cf4b885aa589bd8a55a131`;
- `local/evidence/20261008-p06d-impact-receipt-audit-01/result.json`
  SHA-256 `4af5fb999f7e004d5061baf7100212992338cc8fd1ad1f6af05664d96e2a16fa`.

The unit fixture that reaches `PASS_CAPTURE_SHAPE_ONLY` is synthetic and is
not a native acceptance artifact. The full Python regression and any native
capture remain separate checks.

## Unknowns, rollback, next step

The tool does not determine `piercingPower="34 27"` semantics, armor units,
BSP2 traversal, runtime transforms, trajectory correctness, damage/randomization,
module/crew rules, or client callback compatibility. These remain
`UNKNOWN / NOT_RUN` exactly as in P06B/P06C.

Rollback is a single commit revert; no client, ignored evidence, database,
service process or deployed artifact is changed.

Single next step: run the owner-gated two-MS-1 capture from P06C and feed its
server receipt to this auditor. Keep P06 hit/damage unavailable until the shape
pass is correlated with a real server-owned intersection and native evidence.
