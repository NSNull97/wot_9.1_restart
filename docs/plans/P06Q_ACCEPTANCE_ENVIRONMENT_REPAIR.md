# P06Q acceptance environment repair — 2026-10-13

The owner accepts the corrected tree fall, both-client agreement and passage.
Final cleanup is complete. The full current-source gateway binary reports
619 PASS / 4 missing historical pool fixture failures. A fresh compilation
was interrupted by disk exhaustion; its error log is preserved. The owner
moved the read-only original client to `C:\WoT_0.9.1_RU_0717_original` to
free space. These maintenance steps preserve the existing acceptance checks.

1. Verify the moved client's complete content manifest against the original
   pinned manifest. Update only configured source paths and owned-copy marker
   references with backups; keep client source bytes unchanged. Update live
   static-audit defaults/tests to read configuration, retaining strict path
   validation and historical evidence paths.
2. Restore missing P06N/P06O test prerequisites under fresh fixture names from
   retained, independently pinned historical private worker builds. Preserve
   original config/descriptor/catalog hashes. Record old root artifacts as
   absent; do not claim private DLLs have the missing root DLL hashes.
3. Give tests an explicit strict helper for the migrated fixture pins. Keep
   every existing real-worker assertion; no mocks, skips or silent fallback.
4. Run applicable Python/source-path checks and the full canonical Rust suite.
   Save source/command/artifact provenance, owner receipt and final cleanup.
5. Only with applicable gates satisfied, no-ff merge/push under standing
   authorization. Leave unrelated P09B edits untouched.

Rollback: source changes are reversible commits; configuration and the two
owned-copy markers have byte-for-byte backups. Restore old path references
only after the original client exists there again. Preserve all failure logs
and the old historical fixture-gap evidence. Never delete client resources
or rewrite historical evidence to conceal the move or changed fixture pins.

Completion: moved-source content and owned-copy identities verified; strict
test-fixture migration passes 623/623 canonical Rust checks. Final applicable
Python scope passes 120 executed tests; historical P07A whole-audit prerequisite
is missing and remains NOT_RUN, separately from its 12/12 source hashes and
new path boundary checks. Owner native gate and receipt-based cleanup are
complete. See the [final report](../research/P06Q_ACCEPTANCE_ENVIRONMENT_REPAIR.md)
for commands, evidence, exact acceptance scope and remaining limitations.
