# P09A — NationObjDumper static evidence index

Status: **PASS_STATIC_NATION_DUMPER_OUTPUT / native payload NOT_RUN**.

## Changed files

- `tools/nation_dumper_static_audit.py`
- `tests/test_nation_dumper_static_audit.py`
- `docs/plans/P09A_NATION_DUMPER_STATIC.md`
- `docs/research/P09A_NATION_DUMPER_STATIC.md`
- this evidence index

No original/research client, gateway, service, fixture or database was changed.

## Pinned inputs

- Disassembly: `local/evidence/20261007-native-tree-filter-01/bytecode/client__gui__scaleform__daapi__view__lobby__techtree__dumpers.json`.
- Disassembly SHA-256: `313253c1004396567c2c79cf3cfd8fe5e431683b881a31fa694d3b8c59782a7d`.
- Both permitted #717 `dumpers.pyc` copies SHA-256:
  `09d86ed36847190f41719e95651b43852bdeba10ffeb1430917669ac3e20c8fc`.

## Receipt

`local/evidence/20261008-p09a-nation-dumper-static-01/receipt.json` reports
`PASS_STATIC_NATION_DUMPER_OUTPUT` and records envelope fields
`nodes/displaySettings/scrollIndex` plus node fields
`id/state/type/nameString/primaryClass/level/longName/iconPath/smallIconPath/`
`earnedXP/shopPrice/displayInfo/unlockProps`. Receipt SHA-256:
`6bb18e6f7662f822913d6c5f03def51be9b15d42f7660c2c75e28a53e4afe261`.

## Commands actually run

- `python -B -X utf8 tools/nation_dumper_static_audit.py --root D:\\WoT_9.1_Server --out ...\\receipt.json` — PASS.
- `python -B -X utf8 -m unittest tests.test_nation_dumper_static_audit` — **5/5 PASS**.
- `python -B -X utf8 -m py_compile tools/nation_dumper_static_audit.py tests/test_nation_dumper_static_audit.py` — PASS.
- `git diff --check` — PASS.

## Gate interpretation

The parser is a bounded static disassembly guard. It rejects duplicate and
non-finite JSON, excessive depth/records/instructions, malformed instruction
pool references, path escape and mutations to the measured method shape. It
does not assign nested object types, decode wire bytes, prove native UI output,
or accept account-owned visibility. Account/shop payload, callback bytes,
rendered screenshot, server handoff and battle admission remain
`UNKNOWN`/`NOT_RUN`.

Rollback is a reviewed revert of the card commit and removal of the ignored
receipt directory. The single next step is one owner-gated research-copy USSR
tree capture correlating account/shop bytes, TechTree callback and screen.
