# ORG-0B — triage and minimal unittest repairs (2026-10-07)

## Goal and boundary

The owner assigned the next card after ORG-0A. Reproduce the recorded 10 errors
and 4 skips, identify their causes, apply minimal repairs to the affected test
and offline verification code, and report remaining environment requirements.
Branch: `codex/org-0b-test-repair`, from main
`1aa052db33643fab510f2b9185716a8e60d8804a`.

Allowed writes: affected files under `tests/` and `tools/`, this plan, current
status/evidence documents, and new evidence under
`local/evidence/20261007-org-0b-test-repair-01/`.
Read canonical source locations from `server/layout.json`. Do not modify
gateway Rust, physics, network protocol, client patches/copies, deployed services,
accepted native evidence or historical baseline/tag. No game launch or deployment
is required for this test-tooling card.

## Execution

1. Save a fresh full-suite verbose result, environment and base SHA. Keep the
   ORG-0A failing receipts intact.
2. Classify each error and skip as VERIFIED, OBSERVED, INFERRED or UNKNOWN using
   tracebacks, imports and canonical source mappings. Distinguish broken test
   infrastructure from actual validation failures; preserve rejection checks.
3. Fix confirmed causes narrowly. Do not catch arbitrary exceptions, loosen
   source hashes, turn failures into skips, or substitute synthetic evidence for
   native acceptance. Add regressions only where needed to protect the repaired
   behavior.
4. Run affected tests, then the full suite and source-layout check. For skips,
   use existing verified local prerequisites when possible and isolated new
   scratch paths. Record unavailable prerequisites as NOT_RUN; do not bypass
   checks or change system permissions just to remove a skip.
5. Review the final diff, verify runtime/client pins unchanged, update current
   status and evidence, and commit the exact approved file list. Merge with
   `--no-ff` and push only after this card's required checks pass; verify remote SHA.

## Acceptance

All ten baseline errors have a documented cause and minimal verified repair;
the full Python 3 suite has no failures/errors; all remaining skips are named
with actual reasons and any separate prerequisite-specific run. Source layout
passes; gateway/client/deployed pins stay unchanged; no native/P03 gate is
claimed by unit tests. Required unexpected FAIL/NOT_RUN keeps the card unmerged.

## Evidence and rollback

Raw commands, outputs, classifications, changed files and hashes belong in
`local/evidence/20261007-org-0b-test-repair-01/`, with a public summary in
`docs/evidence-index/ORG-0B.md`. Historical receipts remain untouched.
Rollback is a reviewed revert of this card's merge on a new branch, preserving
baseline/tag and all evidence; no reset or force-push.

## Initial hypotheses (not yet verified)

ORG-0A observed three missing old gateway paths, two undefined `_control`
references and five unhandled `BundleError` exceptions. Causes and repairs are
INFERRED until reproduced and inspected here. The four recorded skips depend on
Python 2.7, a closed native export, a local scratch directory and Windows symlink
capability, respectively. Their availability in this run is UNKNOWN.

## Verified repair decisions

Fresh baseline: 2028 tests, 10 errors, 4 skips (37.251 seconds).
The relocated canonical gateway/capture sources no longer have the historical
hashes. Repointing old validators at current files or replacing their pins would
invalidate historical provenance. The affected historical tests will explicitly
read the archived files with the original exact hashes through a test-only reader
fixture. Frozen validators remain byte-for-byte unchanged; direct legacy live
runner compatibility is still NOT_RUN and is outside this card. Add corrupted
source checks so this fixture cannot turn a hash failure into success.

The isolated window-profiler fixture must initialize `_control=None`, matching
the original module. Profile4 verifiers must choose relative imports when loaded
as a package, avoiding duplicate `BundleError` classes after another test adds
`tools/` to `sys.path`; preserve direct-script execution.
