# P09E — historical tank/module research and acquisition, free test lab

Date: 2026-10-13, Asia/Yekaterinburg. Branch: `codex/p09e-tank-module-research`.
Accepted base: `626867c758c32b189a77a7a7a2fe9ff29837e11b` (P04G merge).

## Goal and scope

Implement the original #717 research dependencies, tank/module ownership,
purchase and compatible installation through the existing authoritative account
architecture. Only XP/credit costs are overridden by explicit versioned
`test_lab` policy; retain historical source prices and XP. No unlock-all shortcut.
Catalogue availability does not establish battle runtime support.

Writes are limited to this managed C: worktree and its ignored local evidence.
The root D: checkout, dirty P09B document, live DBs, processes, installations,
and original client are untouched. Original client is read-only at
`C:\WoT_0.9.1_RU_0717_original`. Do not copy resources. No computer input,
client/server launches or native acceptance before owner testing after
2026-10-14 09:00 Asia/Yekaterinburg.

## Execution

1. Audit existing P04/P09 catalogues, transaction and native paths; bind original
   resource/bytecode hashes and record VERIFIED/OBSERVED/INFERRED/UNKNOWN.
2. Build a bounded source catalogue adapter preserving graph, defaults, module
   compatibility and historical costs. Identify unsupported assemblies explicitly.
3. Extend existing persistence/command conventions with atomic, idempotent
   research, purchase and installation, authenticated identity, revision,
   reservation, ownership and capacity checks. Keep native IDs out of rules.
4. Implement source-established native request/state adapters, leaving genuinely
   unknown wire behavior fail-closed. Do not replace native acceptance with mocks.
5. Test valid chains, prerequisites, incompatibility/overload, duplicate commands,
   persistence/restart, concurrency/rollback, malformed input and zero costs.
   Check MS-1/IS-7 supported runtime boundary and new-assembly rejection.
6. Record commands, evidence, limitations and owner native checklist; commit.
   Required native NOT_RUN holds the branch: no merge/push to main.

## Acceptance and rollback

Automatic gates are necessary but insufficient: original UI must expose the
historical tree and complete research/purchase/install with durable state after
restart. Owner native gate is mandatory. Unsupported battle configurations must
remain ineligible, including variants of supported vehicles with unverified
mounts. Source numeric parameters alone do not certify physics or battle support.

Rollback: revert this card's commits, retain evidence; isolated DBs are never
copied over shared stores. No shared process/installation rollback is required.
