# P06H — offline geometric query and trace boundary

## Result and provenance

This card implements a server-side geometric primitive and diagnostic trace
API. It does not connect collision geometry to a running battle. The accepted
integrated world, physics workers, native gateway protocol and client copies
are unchanged.

The implementation is project-authored Rust: bounded, two-sided
segment/triangle intersection with f64 intermediate arithmetic over f32 input
facts. It embeds no client resources, armor tables or borrowed implementation.
The source card is `c4f3b5b12ec4b5b6babe36d040b0d18de8f30622`.

## Evidence categories

| Category | Finding and practical limit |
| --- | --- |
| VERIFIED (source) | `Mesh::new` validates finite/bounded vertices, indices, unique source IDs and metadata. Private storage prevents later index mutation. Revision strings are caller labels, not proof of historical correctness. |
| VERIFIED (source) | `Trace::collision_query` reads the latest segment for the specified shot, requires its exact end tick and performs the query itself. Query and intersection rows commit atomically. |
| VERIFIED (source) | Empty results permit more segments. Nonempty results require `UnresolvedCollision`; they cannot be silently replaced by range expiry or continued flight through the surface. This changes the diagnostic trace only. |
| VERIFIED (source) | `World::advance` and native publication do not call the new API. No HP, ammunition, projectile or client state is changed by this card's query. |
| INFERRED / design choice | 4096 vertices, 8192 triangles and 128 candidates bound one supplied mesh/query. These are laboratory limits, not native WoT protocol limits or proof of suitability for every vehicle. |
| INFERRED / design choice | Relative angular tolerance and dimensionless parameter tolerance are both `1e-12`; they describe this implementation's numerical contract, not the original server's behavior. |
| UNKNOWN | Actual world transforms for Hull/Turret/Gun, outward winding, moving target pose at collision time, BSP2 equivalence, armor surface deduplication and native impact presentation. |
| NOT_RUN | Native collision capture, historical penetration, HP/module/crew damage, Linux/cross-platform bitwise reproducibility. |

The P06F static MS-1 correlation remains useful source evidence, but its turret
Y-min mismatch has not been corrected by assumption. A measured runtime
transform must precede connecting those source triangles to a battle.

## Geometry and trace limits

- Caller vertices must already be in world space. Local-to-world transformation
  and target entity ownership are not provided here.
- Normals follow source triangle winding; no outward-facing guarantee is made.
- Shared edges may yield two distinct triangle candidates. Duplicate source
  IDs are rejected; overlapping geometry with different IDs is not collapsed.
- Coplanar/near-parallel segments have no point candidate under the documented
  tolerance. Finite shell radius, moving-target sweep and curved-subsegment
  error bounds are not modeled.
- A query reserves capacity for one immediate terminal. A future runtime
  adapter still needs a World-level query/terminal transaction before other
  shots consume the remaining event budget.
- The old segment row retains its flight-only revision; the associated query
  row carries the actual supplied geometry/transform labels. Both rows are
  linked by exact event order. These are internal typed events, not a new wire
  protocol or a serialized impact-capture.v1 receipt.

## P06D incompatibility

`tools/impact_capture_audit.py` requires one intersection, classification
(including thickness and penetration), and replay evidence. A zero-candidate
or multi-candidate geometric query has different semantics. P06D acceptance
is therefore **NOT_RUN** for this boundary; no dummy classification/replay rows
were added and the auditor was not weakened. Its existing synthetic tests
cannot establish native hit behavior.

## Verification and follow-up

The final pinned gateway suite/build and layout receipts are recorded in
`local/evidence/20261010-p06h-collision-boundary-01/summary.json` and
`local/build/server/gateway-p06h-collision-05/result.json`.
The unit fixtures are explicitly synthetic: planes, shared edges, reversed
winding, scales, malformed geometry and interleaved shot traces. They are not
screenshots or native MS-1 collision evidence.

Next: bind hash-pinned MS-1 geometry and measured component transforms to the
accepted integrated world, then correlate a fixed-pose native shot. Penetration
and damage remain unavailable until that separate integration gate is passed.
