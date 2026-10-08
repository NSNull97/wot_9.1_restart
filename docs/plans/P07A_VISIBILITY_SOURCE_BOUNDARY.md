# P07A — static visibility contract and leak boundary

Status: **PASS_STATIC_VISIBILITY_SOURCE_AUDIT; native capture NOT_RUN**.
Branch: `codex/p07a-static-audit`.
Base: current `main` (2026-10-08).

## Goal

Close one narrow P07 preparation seam without pretending that a marker on a
screen proves a server interest set: inventory the #717 entity-def and client
bytecode declarations that can carry visibility state, and define the handoff
needed for a later two-client capture. The card is read-only. It must keep
server authority explicit and prevent hidden positions, target IDs, or
visibility diagnostics from leaking through a generic broadcast.

This is a source boundary, not a visibility implementation. It does not tune
view ranges, calculate line of sight, add foliage rules, or alter gateway,
server, client patches, fixtures, or the deployed service.

## Existing static evidence

Receipt: `local/evidence/20261008-p07a-visibility-source-boundary-01/summary.json`
(SHA-256 `e8dd6ca61c8946a5e0991f887217fd50f83ae83ab330cb182cfdd22209aaaf3a` —
recompute before acceptance; the authoritative hash is recorded by the run).

The source manifest is the existing P00/P01 receipt
`local/evidence/20261002-p00-p01/summary/sources.json` (SHA-256
`67a4d82108d821a3a39614ba9b3a278cbf8330b4329d6c6e5e9b5cc8ef53eb9a`). The
selected #717 files and hashes are copied into the receipt:

- `entity_defs/avatar.def` and `client/avatar.pyc`;
- `entity_defs/vehicle.def` and `client/vehicle.pyc`;
- `entity_defs/arena.def` and `client/clientarena.pyc`.

The extracted contract inventory is deliberately small and typed:

- `Avatar.freezeVisibilityState()` and `Avatar.receiveVisibilityInfo(array<OBJECT_ID>, array<FLOAT32>, array<FLOAT32>)`;
- `Vehicle.sendVisibilityDevelopmentInfo(OBJECT_ID, VECTOR3)`;
- `Vehicle.invisibility: FLOAT32` and `Vehicle.detectedVehicles: array<OBJECT_ID>`;
- `Arena.receiveVehicleVisibilityInfo(OBJECT_ID, array<OBJECT_ID>, array<FLOAT32>, array<FLOAT32>, FLOAT32, array<OBJECT_ID>)`;
- `Arena.fogOfWar: UINT8` and `Arena.fogOfWarCell: UINT8`.

The receipt records the source flags (`BASE`, `CELL_PRIVATE`, `CELL_PUBLIC`) and
all declared CellMethod wire IDs as `UNKNOWN`. These declarations establish names,
shapes and exposure labels only; they do not establish serializer order,
recipient filtering, ranges, timing, or line-of-sight semantics.

The bounded recheck is now implemented by
`tools/p07a_visibility_static_audit.py`. It re-reads the hash-bound P00/P01
`contracts.json` and `sources.json`, asserts exactly eight declaration shapes,
and re-hashes the six selected files in both permitted #717 copies. Receipt:
`local/evidence/20261008-p07a-static-audit-01/receipt.json`, SHA-256
`8dd8bfab40f7b9a53cb2e28da8b4e8b38a09c1f06a632fc157d7801ba4d25c76`.
The targeted negative/positive suite is 9/9 PASS in
`tests/test_p07a_visibility_static_audit.py`. JSON input is bounded with
duplicate-key, non-finite, depth and item-count rejection; all paths are
contained beneath the repository and client copies are read-only.

## Unknowns and safety boundary

- Wire IDs, framing, serializer order, revision/sequence fields and callback
  order are **UNKNOWN**.
- Meaning and units of the two `FLOAT32` arrays, `invisibility`, and arena
  parameters are **UNKNOWN**; names are not formulas.
- Native LOS, terrain/foliage occlusion, movement/shot state, spotting delay,
  disappearance and reappearance are **NOT_RUN**.
- Per-recipient interest sets and whether `detectedVehicles` is authoritative,
  derived, or a client mirror are **NOT_RUN**.
- The server must retain exact positions privately and send only the minimum
  recipient-authorized state. `sendVisibilityDevelopmentInfo` is a diagnostic
  candidate, not a public API. No implementation may broadcast hidden entity
  IDs or coordinates merely because the client has a field that can display
  them.

## Bounded execution plan

### A. Static recheck (read-only) — PASS

1. Recompute the manifest and contracts receipt hashes. **Done** by the
   bounded verifier; the pinned hashes still match.
2. Assert the eight selected declarations, exact primitive/container types,
   exposure flags, and `UNKNOWN` wire IDs.
3. Reject duplicate names, unexpected visibility fields, non-finite or
   client-authored values if a future receipt adds samples.
4. Preserve the source hashes and receipt under the ignored evidence directory;
   do not infer a wire decoder from entity-def order.

### B. Native handoff (owner-gated, later card)

Use one manifested research-client copy and the existing local test account.
Run a bounded pair of clients with a known target and an occluding map feature:
record process/source manifest, server recipient, target identity, positions
inside the private server log, and exactly the payload delivered to each
recipient. Repeat after moving, firing, hiding, reappearing, and reconnecting.
Correlate native callback/property traces with packet hashes and screenshots.
Do not treat a screenshot, marker, tracer, or sound as proof of filtered wire
state. Do not mutate the deployed service or original client.

A future measured receipt must separate `server_interest_set`,
`native_visibility_event`, `payload_fields`, `occlusion_control`, and
`runtime_eligibility`. A missing callback, missing payload, or ambiguous
recipient is `NOT_RUN`, not a guessed decoder.

### C. Verifier only after capture

After B yields bytes, add a bounded read-only verifier for measured fields:
strict sizes/depth, duplicate-key rejection, finite vectors, known entity IDs,
monotonic sequence/tick, recipient binding, and fail-closed handling of stale
or hidden target data. The verifier may report `PASS_CAPTURE_SHAPE_ONLY`; it
must not claim historical spotting coefficients or solver equivalence.

## Acceptance and rollback

This docs-only preparation accepts only
`PASS_STATIC_VISIBILITY_SOURCE_BOUNDARY`. Native payload, LOS/occlusion,
interest-set filtering, timing, reappearance, and two-client acceptance remain
`NOT_RUN`. No runtime/client/service files are changed. Rollback is a revert of
this docs-only commit and deletion of its ignored receipt directory.

## Single next step

Perform one owner-gated two-client research-copy capture with a fixed occlusion
control, preserving per-recipient payload bytes and the native callback/property
trace before writing any visibility adapter or solver.
