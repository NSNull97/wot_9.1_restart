# P09A static research-tree graph audit receipt

Status: **PASS_STATIC_RESEARCH_TREE_GRAPH**.

| Item | Evidence | Result |
|---|---|---|
| Pinned source catalog | `web/data/catalog.v1.json` | SHA `d66aad60c13d83807f49b1ebfc8cc89f330e658ed3223706169f763052547567` |
| Pinned research graph | `web/data/catalog-research.v1.json` | SHA `fddd218109633aeb009bfca2859e5da1c4416737a48be71aa63b278a848df698` |
| Bounded verifier | `tools/research_tree_audit.py` | duplicate/non-finite/size/depth/edge checks |
| Positive and negative tests | `tests/test_research_tree_audit.py` | 8/8 PASS, including MS-1 level-I root mutation rejection |
| Machine receipt | `local/evidence/20261008-p09a-tree-graph-audit-02-receipt.json` | SHA `454c9b0c9e0666e92856239dd55c486014695317052eff766f50b772239ef8d8` |

The receipt establishes only static reference-data integrity, including
`ussr-ms-1` tier I and its tier-II outgoing vehicle edges. Native account
ownership, shop hidden-item payload, callback bytes/order, screenshot
correlation and battle admission remain **NOT_RUN**.

Single next step: capture one research-copy account/shop response together
with the native USSR tree callback and screenshot, then compare that measured
payload with this static graph.
