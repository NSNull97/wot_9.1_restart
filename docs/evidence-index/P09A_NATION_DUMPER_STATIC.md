# P09A — NationObjDumper static evidence index

Status: **PASS_STATIC_NATION_DUMPER_OUTPUT / nested format shape measured / native payload NOT_RUN**.

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

The follow-up bounded receipt
`local/evidence/20261008-p09a-nested-shapes-01/receipt.json` extends the same
hash-bound parser with the `NationXMLDumper` nested shape. It records
`unlockProps` indexes `0..3`, the iteration of `unlockProps[-1]` and
preservation of `unlockProps[:-1]`, plus `displayInfo.lines`, `inPins`,
`viaPins`, `outLiteral` and `outPin` access paths and seven exact format
constants. Status remains static-only; Python value types, wire serializer,
callback bytes and account ownership remain unknown/NOT_RUN. Receipt SHA-256:
`6a96bf9dc6d926906ae6758ce5db6d261cf387006f93d6ca3b336bcd62cc3e48`.

## Commands actually run

- `python -B -X utf8 tools/nation_dumper_static_audit.py --root D:\\WoT_9.1_Server --out ...\\receipt.json` — PASS.
- `python -B -X utf8 -m unittest tests.test_nation_dumper_static_audit` — **7/7 PASS**.
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
