# P09A — static research-tree graph audit

Date: 2026-10-08, Asia/Yekaterinburg.

The bounded reader `tools/research_tree_audit.py` verifies the tracked
reference graph without opening either client. It binds
`catalog-research.v1.factsSha256` to the exact `static-catalog.v1` bytes,
checks bounded JSON and IDs, validates every node/edge target, and rejects
duplicate/non-finite input. The audit also checks the graph facts relevant to
the observed UI issue: USSR has tiers I–X, the graph contains one IS-8 → IS-7
vehicle edge, and IS-7 has no outgoing vehicle edge.

The real receipt is
`local/evidence/20261008-p09a-tree-graph-audit-01/receipt.json`, SHA-256
`39733821cf916a069152a0d67909fca54b816ebab13ad3a33dc0edb94abb0f44`.
It reports:

- `PASS_STATIC_RESEARCH_TREE_GRAPH`;
- 374 trees, 3945 nodes and 2062 edges;
- 85 USSR vehicles with tiers `[1,2,3,4,5,6,7,8,9,10]`;
- catalog SHA `d66aad60c13d83807f49b1ebfc8cc89f330e658ed3223706169f763052547567`;
- research graph SHA
  `fddd218109633aeb009bfca2859e5da1c4416737a48be71aa63b278a848df698`.

Targeted tests: `python -B -X utf8 -m unittest tests.test_research_tree_audit`
ran 7 tests with zero failures/errors. This proves only the integrity of the
reference graph. Native `notInShopItems`, account/shop payload, research-tree
callback, visual window state and selection-to-battle handoff remain
`NOT_RUN`; an owned garage vehicle can still be hidden by native policy.
