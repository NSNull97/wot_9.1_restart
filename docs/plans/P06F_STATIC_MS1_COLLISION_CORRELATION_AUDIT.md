# P06F — bounded MS-1 static collision correlation audit

Status: **PASS_STATIC_MS1_COLLISION_CORRELATION / STATIC_ONLY**.

## Goal

Read the configured #717 research client copy and correlate the active MS-1
descriptor with the real packaged `Hull`, `Turret_01`, and `Gun_02` collision
members. The audit must pin package/member bytes and hashes, decode only the
observed Packed XML shape, and report primitive material/group ranges and
finite mesh bounds. It must fail closed on path escapes, links, malformed
containers, non-finite values, invalid group ranges, unknown materials, and
descriptor/package mismatches.

## Explicit boundary

This card does not execute client bytecode, start a client or service, compose
runtime transforms, choose axes or units, decode BSP2, trace a segment, select
a hit, classify penetration, mutate HP, or emit a gameplay impact. The report
keeps `runtime_axes_status=UNKNOWN`, `bsp2_status=UNKNOWN`, and
`native_server_hit_status=NOT_RUN`.

## Implementation

- add `tools/p06f_ms1_collision_static_audit.py`, using bounded package reads,
  `packed_xml`, and the existing primitive parser;
- verify only the active `ms-1.xml` collision paths and the nine corresponding
  package members (`.model`, `.visual`, `.primitives`);
- cross-check `nodelessVisual`, `Scene Root`, identity transform and
  `treatAsWorldSpaceObject=false`; measure visual/model/primitive bounds with
  a documented tolerance and preserve any real mismatch as an explicit
  observation (no guessed transform or axis correction);
- map every primitive group to the visual material identifier and descriptor
  armor field/material kind, preserving exact measured ranges without applying
  a solver;
- emit a bounded receipt with source hashes, mesh summaries, and explicit
  unknown/not-run statuses;
- test positive real resources and mutation controls for paths, links,
  malformed bytes, non-finite vertices, invalid ranges, unknown groups and
  mismatched bounds/materials.

## Checks and rollback

Run the targeted P06F unit suite, the existing P06B/P06E static suites, Python
compilation, and the repository UTF-8 test command. The receipt is ignored
local evidence and must record the exact command, hashes and status. Rollback
is one commit revert; no client, gateway, service or original copy is changed.

## Acceptance

`PASS_STATIC_MS1_COLLISION_CORRELATION` only proves measured static source and
mesh/material correlation. It does not advance P06C native impact acceptance;
the next step remains an owner-gated runtime capture after a separately
measured collision boundary.
