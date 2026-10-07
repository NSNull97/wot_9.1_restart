# P09A static research-tree graph audit receipt

Status: **PASS_STATIC_RESEARCH_TREE_GRAPH**.

| Item | Evidence | Result |
|---|---|---|
| Pinned source catalog | `web/data/catalog.v1.json` | SHA `d66aad60c13d83807f49b1ebfc8cc89f330e658ed3223706169f763052547567` |
| Pinned research graph | `web/data/catalog-research.v1.json` | SHA `fddd218109633aeb009bfca2859e5da1c4416737a48be71aa63b278a848df698` |
| Bounded verifier | `tools/research_tree_audit.py` | duplicate/non-finite/size/depth/edge checks |
| Positive and negative tests | `tests/test_research_tree_audit.py` | 7/7 PASS |
| Machine receipt | `local/evidence/20261008-p09a-tree-graph-audit-01/receipt.json` | SHA `39733821cf916a069152a0d67909fca54b816ebab13ad3a33dc0edb94abb0f44` |

The receipt establishes only static reference-data integrity. Native account
ownership, shop hidden-item payload, callback bytes/order, screenshot
correlation and battle admission remain **NOT_RUN**.

Single next step: capture one research-copy account/shop response together
with the native USSR tree callback and screenshot, then compare that measured
payload with this static graph.
