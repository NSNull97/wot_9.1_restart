# P09A — bounded static research-tree graph audit

## Goal

Add a read-only guard for the already generated `static-catalog.v1` and
`catalog-research.v1` files. The guard pins the #717 build and catalogue hash,
rejects malformed or cross-tree edges, and makes the observed USSR tier and
IS-8/IS-7 facts reproducible without treating the web graph as native UI data.

## Scope

- `tools/research_tree_audit.py` reads only the two tracked JSON catalogues.
- `tests/test_research_tree_audit.py` covers the real graph and bounded negative
  controls for hashes, IDs, duplicate keys, non-finite values and edge direction.
- The receipt is local ignored evidence; no client, gateway, service, fixture or
  database is started or modified.

## Acceptance

`PASS_STATIC_RESEARCH_TREE_GRAPH` requires 374 catalogued trees, 3945 nodes,
2062 edges, USSR tier coverage I–X, an MS-1 tier-I root with tier-II outgoing
vehicle edges, exactly one `ussr-is8 → vehicle-ussr-is-7` vehicle edge and zero
outgoing vehicle edges from IS-7. Native shop payload,
tree callback, hidden-item policy at runtime and screenshot correlation remain
`NOT_RUN`.

## Rollback

Revert the docs/tool/test commit and delete the ignored receipt directory. The
tracked catalogue and all client/runtime state remain unchanged.
