# P09A — bounded NationObjDumper output audit

Status: **IN_PROGRESS / static only**.
Branch: `codex/p09a-dumper-static`.
Base: main `20563af` (2026-10-08).

## Goal and concrete gap

The existing TechTree audit proves the `NationTreeData.load/dump` handoff, but
does not freeze the object returned by `NationObjDumper`. The inspected #717
disassembly contains three envelope keys and thirteen vehicle-node keys. Add a
read-only guard for these static facts so a later native capture can compare
its UI object against measured fields without inventing an account serializer.

## Permitted scope and contract

- Add `tools/nation_dumper_static_audit.py` and negative/positive tests.
- Read only the existing dumpers disassembly JSON and the two permitted #717
  `dumpers.pyc` copies. Pin their SHA-256 values in the tool and receipt.
- Validate bounded UTF-8 JSON, duplicate keys, non-finite values, total/depth
  limits, repository path containment and the exact selected method signatures.
- Parse only `BUILD_MAP`/`STORE_MAP` instruction segments in the inspected
  methods; report their key names and statically visible value sources.
- Keep client/runtime, gateway, fixture, database and deployed service untouched.
  Do not execute/import bytecode, decode a packet or create a tree payload.

## Execution

1. Freeze the source/disassembly hashes and inspect constructor, `dump`, its
   lambda and `_getVehicleData`.
2. Add a bounded static parser that rejects mutated keys/value sources,
   duplicate records, malformed instructions, hash mismatch and path escape.
3. Write an ignored receipt, run targeted tests and `git diff --check`.
4. Record VERIFIED_STATIC and UNKNOWN/NOT_RUN limits in research/evidence docs.
   Hand the accepted commit to the integrator for current-main checks/merge.

## Acceptance and rollback

Accept only `PASS_STATIC_NATION_DUMPER_OUTPUT`: envelope `nodes`,
`displaySettings`, `scrollIndex`; thirteen expected node fields; pinned source
and disassembly hashes; bounded negative controls. This does not close native
account/shop payload, callback bytes, rendered visibility or battle admission.
Those gates remain `NOT_RUN`. Revert this tool/test/docs commit and remove its
ignored evidence directory; no runtime restoration is required.

## Single next step

Capture one bounded research-copy USSR tree run and correlate the account/shop
payload, TechTree callback and rendered screen before writing a native adapter.
