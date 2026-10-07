# P07A — static visibility source research ledger

Date: 2026-10-08, Asia/Yekaterinburg
Branch: `codex/p07a-visibility-boundary`.
Scope: read-only #717 source inventory for the P07 visibility handoff. No
client, gateway, deployed service, runtime, fixture or database was started or
modified.

## Evidence ledger

| Claim | Status | Evidence | Limit |
|---|---|---|---|
| Selected #717 entity-def/client bytecode sources are hash-bound | `VERIFIED_STATIC_SOURCE` | `local/evidence/20261008-p07a-visibility-source-boundary-01/summary.json`; P00/P01 `sources.json` | Hash binding identifies files, not runtime behavior |
| Avatar exposes `freezeVisibilityState` and typed `receiveVisibilityInfo` | `VERIFIED_STATIC_DECLARATION` | `contracts.json` SHA `c9bd0893dfdb1ec6c09de9af200b04eb19b6dd08f71b97f40b32bb831a70a6e5` | Method wire IDs/order and callback semantics unknown |
| Vehicle declares `invisibility: FLOAT32`, `detectedVehicles: array<OBJECT_ID>` and a development-info method | `VERIFIED_STATIC_DECLARATION` | Same receipt; `vehicle.def` SHA in receipt | Public/private flags do not prove server authority |
| Arena declares typed visibility callback and `fogOfWar`/`fogOfWarCell` | `VERIFIED_STATIC_DECLARATION` | Same receipt; `arena.def` SHA in receipt | Cell/base flags do not prove recipient filtering |
| Native LOS, occlusion, foliage, delay and reappearance are implemented | `NOT_RUN` | No controlled native capture in this card | Must not infer from names or screenshots |
| Server interest set filters hidden state per recipient | `NOT_RUN` | No server/runtime change | Required P07 implementation gate |

## Static contract inventory

The bounded receipt contains exactly eight selected declarations:

- Avatar: `freezeVisibilityState()` and
  `receiveVisibilityInfo(array<OBJECT_ID>, array<FLOAT32>, array<FLOAT32>)`;
- Vehicle: `sendVisibilityDevelopmentInfo(OBJECT_ID, VECTOR3)`,
  `invisibility: FLOAT32`, `detectedVehicles: array<OBJECT_ID>`;
- Arena: `receiveVehicleVisibilityInfo(OBJECT_ID, array<OBJECT_ID>,
  array<FLOAT32>, array<FLOAT32>, FLOAT32, array<OBJECT_ID>)`,
  `fogOfWar: UINT8`, `fogOfWarCell: UINT8`.

`CellMethod` wire IDs remain `UNKNOWN` in the source receipt. `CELL_PUBLIC`,
`CELL_PRIVATE` and `BASE` are recorded as declaration flags, not as an
authorization policy. The `sendVisibilityDevelopmentInfo` name is treated as a
possible diagnostic path and is excluded from any proposed public replication
contract until a native trace proves its recipient and purpose.

## What this card does not establish

No value here is a view distance, camouflage coefficient, spotting delay,
position, target truth, or penetration/impact result. No client-side marker,
tracer, sound, screenshot, or self-reported visibility state is authoritative.
The server must retain private world state and derive a recipient-specific
interest set before emitting a measured event. Hidden target IDs and exact
coordinates must not enter a shared debug/API envelope.

## Owner-gated capture recipe for the next card

Use one manifested research-client copy and two local clients on a fixed map.
Keep one target in an unobstructed lane, then repeat behind a fixed wall or
terrain edge. For every recipient, preserve process/source manifest, server
recipient and target IDs, private server positions, exact payload bytes,
callback/property traces, packet hashes, sequence/tick and screenshots. Add
movement, fire, disappearance, reappearance and reconnect controls only after
the static pair is captured. Correlate payload differences with native events;
absence of a callback or ambiguous recipient is `NOT_RUN`, never a guessed
wire decoder.

## Commands and reproducibility

The static receipt was generated with a bounded Python reader over the existing
P00/P01 JSON receipts (UTF-8, no client/runtime launch):

```powershell
@'
# read-only receipt extraction: load contracts.json/sources.json,
# assert exactly 8 declarations, record source hashes, write summary.json
'@ | python -X utf8 -
```

For acceptance, rerun the reader, recompute the receipt SHA, and verify the
source hashes before merging. No test suite or gateway build is claimed by this
card.

## Acceptance and rollback

Accepted label: `PASS_STATIC_VISIBILITY_SOURCE_BOUNDARY`.
Native payload, wire framing, recipient filtering, LOS/occlusion, timing,
reappearance, two-client screenshots and server implementation remain
`NOT_RUN`. Rollback is a revert of this docs-only card and removal of the
ignored receipt directory.

Single next step: owner-gated two-client capture with a fixed occlusion control
and per-recipient payload/callback correlation.
