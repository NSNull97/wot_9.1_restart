# P06H — server-owned collision boundary

## Goal

Add the first server-owned geometric boundary after the accepted P06C flight
trace: a bounded segment query over an explicitly supplied triangle mesh that
returns ordered candidates with triangle/group/material, parametric `t` and a
finite winding-derived world normal. The result is a geometric observation only; penetration,
damage, HP, modules, crew and client callbacks remain unavailable.

## Scope

- add a reusable Rust segment/triangle query with finite and capacity guards;
- query the exact latest recorded flight segment inside the trace API;
- atomically record `collision_query` (including zero candidates), its ordered
  `intersection` rows, and explicit source segment/query orders;
- permit flight after an empty query; require `UnresolvedCollision` after a
  nonempty query, without claiming physical blockage or penetration;
- require an explicit geometry revision and transform revision on every query;
- preserve the existing flight-only integrated profile until a real geometry
  manifest and runtime transform are supplied;
- add fail-closed tests for degenerate triangles, non-finite input, ordered
  candidates and duplicate terminal rows;
- define the geometry/transform prerequisites for the subsequent native owner
  capture correlating an MS-1 tracer/shot ID with a server receipt.

No armor formula, penetration randomization, HP/module/crew mutation, BSP2
decoder, turret-axis correction or synthetic native hit is part of this card.

## Acceptance

- gateway Rust suite and isolated build pass;
- synthetic unit meshes prove the query's bounded intersection contract;
- no collision event is emitted without an explicit geometry/transform
  revision;
- a collision-only terminal cannot mutate ammo, projectile or damage state;
- partial rows, duplicate queries, wrong battle/shot/tick and capacity overflow
  are rejected without trace mutations;
- this card is accepted only as an offline query/trace foundation. Native
  impact remains `NOT_RUN`; P06D shape acceptance is also `NOT_RUN` because its
  v1 receipt requires classification and replay, which this boundary does not
  produce. Do not fabricate thickness, penetration or replay rows to pass it.

## Contract and known limits

`Mesh::new` checks immutable vertex/index/metadata bounds and unique triangle
IDs; sparse source IDs are preserved. The caller supplies already-world-space
vertices. Revision strings label provenance but do not verify #717 geometry or
component transforms. Query uses f64 arithmetic over f32 facts and returns both
triangle faces, closed segment endpoints, and winding-derived unit normals.
Shared-edge candidates remain distinct triangles; no armor surface deduplication
or outward-normal claim is made. Coplanar and near-parallel cases have no point
candidate under the documented tolerance; shell radius is not modelled.

The existing integrated runtime remains flight-only. The new API is exercised
with synthetic meshes in Rust tests and is not wired to `World::advance`.
Native resources are not embedded, emitted or published by this card.

## Execution

1. Implement bounded immutable geometry and ordered segment query.
2. Bind typed trace batches to saved segment coordinates and tick; reject
   invalid transitions centrally, including the generic terminal API.
3. Run the pinned isolated gateway suite/build and source-layout check.
4. Record the tested source hashes, limitations and next integration gate.

Read-only agent review exposed arbitrary-candidate insertion, terminal bypass
and whole-flight miss claims in the first draft. They are replaced by the
internally computed atomic query API; the P06D criterion above was corrected
before acceptance, rather than weakening the auditor.

## Evidence and rollback

Store the isolated build, targeted tests and source-layout receipt below
`local/evidence/20261010-p06h-collision-boundary-01/`. Revert the single P06H
commit and remove the ignored receipt directory; the canonical service and
original client copies remain untouched.

## Single next step

Bind a hash-pinned MS-1 mesh and measured component transforms to the accepted
integrated world, then correlate a fixed-pose native shot with the server query
in that follow-up card. Keep penetration and damage unavailable until the
geometry/transform correlation is established.
