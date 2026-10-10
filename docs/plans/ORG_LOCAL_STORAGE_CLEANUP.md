# Local storage cleanup — 2026-10-10

Owner request: clean the oversized `D:/WoT_9.1_Server/local` directory.
Preserve the just-accepted P06I merge `b4ddd02` and reproducible test evidence.

## Plan and boundaries

1. Read-only inventory: build caches, evidence/test-runs, approved client copies,
   pinned toolchains/vendor, staging and downloads. Do not traverse reparse paths.
2. Create an exact deletion manifest for disposable Rust intermediate caches
   beneath isolated `local/build` target output directories. Preserve executable
   deliverables, DLLs needed at runtime, worker pools, build/test receipts and logs.
3. Before deletion, verify every resolved absolute target is inside the named
   workspace subtree; reject reparse entries, overlaps, unexpected directory names
   and active-process targets. Record hashes of retained runtime artifacts.
4. Delete only manifest entries with native PowerShell `Remove-Item -LiteralPath`;
   retain per-path outcome and measure actual free-space change. Do not invoke a
   second shell or silently widen the scope on failure.
5. Verify retained hashes, pool references, evidence receipts and current source
   layout. Record the result, limitations and rebuild command; merge this
   documentation card only after its own checks pass.

Protected: original/research clients, approved copies and install rollback
ledgers, account/database/key material, canonical running services, accepted
physics worker binaries, pinned tools/vendor sources, raw accepted native
captures and their receipts. No arbitrary age-based evidence removal.

Audited additional exception: remove the accidentally installed, unreferenced
`local/toolchains/rustup/toolchains/1.58.1-x86_64-pc-windows-gnu` with the local
rustup toolchain manager and explicitly local CARGO_HOME/RUSTUP_HOME. The P06I
report records the accidental installation; accepted builds and local default
use 1.90.0. Verify the pinned 1.90.0 compiler hash/version after removal.

## Acceptance and recovery

PASS requires exact manifest containment, successful outcomes for all attempted
paths, retained runtime hashes unchanged and a measured disk-space gain.
Deleted intermediate caches are recoverable by rebuilding from the corresponding
source with `python -B server/build.py gateway --test --out local/build/server/<fresh>`.
Deletion is not reversible from the Git documentation revert; retained launchable
artifacts and historical receipts are the rollback anchors. No runtime feature
change or automatic test-client launch is part of this cleanup.

Evidence: `local/evidence/20261010-local-storage-cleanup-01/`.

## Result

**PASS_BUILD_CACHE_CLEANUP / PASS_POST_CLEANUP_VERIFICATION**.
Applied the 448 eligible paths from the immutable manifest SHA
`bcbfd2dc80c6843c6f1e1208f34457f8f7a28a70f2b707cfd4555c753bb05963`.
All resolved below local/build, had the expected target/debug/cache layout,
had no reparse ancestor/descendant and contained no running executable.
Removed all 448, zero errors and zero retained-file mismatches.

- Build-cache removal increased free space by 52,193,226,752 bytes.
- Local rustup successfully uninstalled accidental Rust 1.58.1.
- Final observed free-space gain: **53,280,419,840 bytes (49.62 GiB)**.
- Free space: 402,952,192 → **53,683,372,032 bytes (50.00 GiB)**.
- **1,347 retained file SHA-256 values unchanged**, including all audited build
  deliverables/receipts, both worker runtime directories and accepted evidence.
- gateway19 and final P06I gateway03 both executed and returned the expected
  no-argument CLI usage error (exit1); this verifies loader/CLI entry only.
- Pinned Rust 1.90.0 hash still matches build03; `rustc -V` succeeds.
- Source layout PASS:62 files/22 relocations. P06I native prefix auditor rerun
  PASS:9 contacts/18 exact endpoints; retained late StorageFull failures remain
  visible as documented, without contaminating the completed accepted prefix.

No new native match or full test rebuild was needed for cache removal; these
were NOT_RUN and the previous runtime acceptance remains separate. Filesystem
free-space delta may include concurrent normal application activity.
Eleven cache directories in three nonstandard target layouts were excluded;
the old client copy and historical evidence were retained because they may be
rollback/provenance inputs. Approved a/b clients, configured services, keys,
account storage, pinned toolchain and offline package sources remain available.

Reproduce verification:

```
python -B -X utf8 local/evidence/20261010-local-storage-cleanup-01/verify_cleanup.py
python -B -X utf8 local/evidence/20261010-p06i-native-collision-01/ownauditor.py --verify
python -B server/check_layout.py --out local/evidence/<fresh>/layout.json
```

Exact applied commands and every path/outcome are recorded in
`clean_build_caches.ps1`, `preflight-applied.json`, `deletion-actions.jsonl`,
`cleanup-result.json`, `rustup-uninstall.log` and
`post-cleanup-verification.json`. The deletion script refuses a second apply
when its action receipt exists. Ready-to-run artifacts were retained; rebuilding
the removed intermediate cache requires the normal fresh-output build command.

The sole next step returns to P06I's accepted development gate: measured
material/contact classification before damage, on the cumulative integrated
runtime. P06I code/owner acceptance is already merged/pushed as `b4ddd02`.
