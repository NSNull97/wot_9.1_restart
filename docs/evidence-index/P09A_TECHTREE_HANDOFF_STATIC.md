# P09A — static TechTree handoff evidence

## Receipt

- Tool: `tools/techtree_handoff_audit.py`.
- Receipt: `local/evidence/20261008-p09a-techtree-static-01/receipt.json`.
- Status: `PASS_STATIC_TECHTREE_HANDOFF_SOURCE`.
- Source SHA-256: `d3fca045cb1fd478a6eb306adfda08ce019795e926574ed943b31946f0dcfb42`.
- Receipt SHA-256: `8e8e5cc9a91885f827979bc3cd59b1940d0f1c10717dfb06565f5f0b81d1e1cf`.
- Disassembly receipt SHA-256: `9a22b51f45c3a24d39407f3727f8f3e5e52f5d50aef28f55c8d8f7b755f209d9`.
- Both permitted #717 copies match the pinned `TechTree.pyc` SHA.

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

### Current-checkout recheck

The handoff audit was rerun on the current checkout together with the bounded
fixture visibility matrix. Fresh outputs are in
`local/evidence/20261008-p03i-p09a-tree-main-02/techtree.json` and
`local/evidence/20261008-p03i-p09a-tree-main-02/visibility-matrix.json`.
The receipt hashes remain
`8e8e5cc9a91885f827979bc3cd59b1940d0f1c10717dfb06565f5f0b81d1e1cf` and
`b291bccd2a32c682cb4b09aae6763c27d5f9c907d323b8d072748676c4687a46`.
The combined TechTree/matrix targeted run is **12/12 PASS** (targeted log
SHA-256 `e2c036271c519c2d3652a8ecdb1a25fdc71110f67942aa722f68407c3862b5f2`).
This remains a static source/fixture check; native account/shop payload,
callback bytes, screenshot and server handoff are `NOT_RUN`.

## Limits

No native client, gateway or deployed service was started. Account/shop wire
payload, callback bytes, screenshot, unowned control and server handoff remain
`NOT_RUN`. Do not reuse this static method shape as a guessed serializer.
