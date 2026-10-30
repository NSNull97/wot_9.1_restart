# LATE stored profile decoder — bounded CAT depot

The retained synthetic hybrid-07 release-stamp failure was reproduced on an
in-memory backup of its own DB. The exact `game_profiles.profile_json` contains
36 ammunition depot entries; the generic incoming-message decoder permits at
most 32 object keys and rejects it as `INVALID_INPUT`. Evidence: diagnostic
`E:/WoT091_Hybrid_Validation_20261030/WoT_9.1_Server/local/evidence/hybrid-late-owner-diagnostic-01/result.json`,
SHA `59e0f77d432b996115366f95118445b424d04235ef419ed87c65a24d0b56eb84`.
The actual late append and native client remain NOT_RUN.

Only the DB-owned profile uses the selected store's existing `_stored_json`
reader (ASCII, duplicate/non-finite and depth guards) and enforces the actual
selected crew profile's 16 KiB v1 or 64 KiB v2 bound. A separate iterative
profile walk retains depth 12, a node budget bounded by that profile's byte
cap, normal object limit 32,
and expands only the root ammunition depot up to the configured shell count.
Arrays have a conservative 3 × 256 owned-vehicle ceiling, derived from three
ammo rows per vehicle and `MAX_OWNED`; the exact shell set and bounded integer
quantities remain mandatory. The catalog-wide shell count is not tied to one
owner's garage; it is bounded independently by the selected profile byte cap.
This describes parser capacity only, not proof
that an arbitrary large authored profile satisfies the complete game schema.
The incoming request/seal decoder and its 32-key/64-element caps are unchanged.

Tests to run in an isolated window: unit profile decoding legacy 15, 32 and
CAT 36, wrong count/quantity, profile/network caps, malformed input and own
SQLite owner binding; existing late/guard regressions; actual preserved-DB
stamp diagnostics and full real HTTP/SQLite + BW/Jolt synthetic hybrid on the
exact commit. Until run they are NOT_RUN. No migration, history rewrite, merge
or push. Roll back by reverting this isolated code commit; no persisted data is
changed by the patch itself.
