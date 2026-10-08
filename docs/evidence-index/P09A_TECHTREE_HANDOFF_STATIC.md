# P09A — static TechTree handoff evidence

## Receipt

- Tool: `tools/techtree_handoff_audit.py`.
- Receipt: `local/evidence/20261008-p09a-techtree-static-01/receipt.json`.
- Status: `PASS_STATIC_TECHTREE_HANDOFF_SOURCE`.
- Source SHA-256: `d3fca045cb1fd478a6eb306adfda08ce019795e926574ed943b31946f0dcfb42`.
- Disassembly receipt SHA-256: `9a22b51f45c3a24d39407f3727f8f3e5e52f5d50aef28f55c8d8f7b755f209d9`.

## What is proven

The static method shape is hash-bound to the permitted #717 research copy:

- `requestNationTreeData` sets available nations and the selected nation, then
  returns `True`.
- `getNationTreeData` rejects an unknown nation, selects its index, loads
  `NationTreeData` and returns its dump.

## Commands and tests

- `python -B -X utf8 tools/techtree_handoff_audit.py ...` — PASS receipt.
- `python -B -X utf8 -m unittest tests.test_techtree_handoff_audit` — 4/4 PASS
  when the ignored client/evidence copies are available.
- `git diff --check` — PASS.

## Limits

No native client, gateway or deployed service was started. Account/shop wire
payload, callback bytes, screenshot, unowned control and server handoff remain
`NOT_RUN`. Do not reuse this static method shape as a guessed serializer.
