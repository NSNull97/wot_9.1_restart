# P09A — TechTree handoff static research ledger

Date: 2026-10-08, Asia/Yekaterinburg

| Claim | Status | Evidence | Limit |
|---|---|---|---|
| `requestNationTreeData` publishes available and selected nation fields and returns success | `VERIFIED_STATIC` | `local/evidence/20261008-p09a-techtree-static-01/receipt.json` | UI method calls only; no account wire payload |
| `getNationTreeData` guards unknown names, selects an index, loads and dumps `NationTreeData` | `VERIFIED_STATIC` | Same receipt; #717 `TechTree.pyc` SHA `d3fca045...` | Instruction shape is not a serializer or callback trace |
| Account/shop payload and native tree rendering are measured | `NOT_RUN` | No native run in this card | Requires owner-gated research-copy capture |

The audit is deliberately narrower than a decoder. It gives the native capture
an exact correlation point: the nation name passed to `getNationTreeData` and
the selected index passed into `NationTreeData.load`. It does not claim that the
static web catalogue or server fixture is the payload returned by `dump()`.

## Source and receipt

- Permitted #717 client sources: `WoT_0.9.1_RU_0717_original/res/scripts/client/gui/scaleform/daapi/view/lobby/techtree/TechTree.pyc` and the matching research-copy path; both have the pinned SHA.
- Source SHA-256: `d3fca045cb1fd478a6eb306adfda08ce019795e926574ed943b31946f0dcfb42`.
- Disassembly evidence: `local/evidence/20261007-native-tree-filter-01/bytecode/client__gui__scaleform__daapi__view__lobby__techtree__techtree.json`.
- Receipt status: `PASS_STATIC_TECHTREE_HANDOFF_SOURCE`.

## Single next step

Capture one bounded native USSR research-tree run on the research copy and
correlate account/shop bytes plus the two TechTree methods with the rendered
screen before writing any adapter.
