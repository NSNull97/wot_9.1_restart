# P09A — native research-tree visibility and ownership predicate

Status: **PASS_STATIC_GRAPH_BOUNDARY; native payload/handoff NOT_RUN**.
Branch: `codex/p09a-research-tree-visibility`.
Base: main `d3110c3` (2026-10-08).

## Goal

Close one narrow P09 seam: make the account-owned visibility of the native
research tree explainable and testable without deleting nodes from the complete
#717 catalogue and without treating a garage selection as a battle admission.
The card must establish which catalogue is static, which visibility comes from
the authoritative shop/account payload, and which native callback supplies the
research-tree screen. It does not implement purchases, research spending,
progression, queue admission, crew/equipment, or battle.

The direct user-visible defect is the observed case where an owned MS-1 is not
shown in the USSR research tree while the static/reference tree still contains
level-I roots. The graph direction must also be made explicit: the measured
reference graph has **IS-8 → IS-7**; IS-7 is terminal. “Нет продолжения ИС-8”
when looking after IS-7 is a direction mistake, not a missing IS-8 node.

## Existing evidence

### VERIFIED static/reference catalogue

- `web/data/catalog.v1.json` SHA256
  `d66aad60c13d83807f49b1ebfc8cc89f330e658ed3223706169f763052547567`.
- `web/data/catalog-research.v1.json` SHA256
  `fddd218109633aeb009bfca2859e5da1c4416737a48be71aa63b278a848df698`.
- The reference graph contains 374 trees, 3945 nodes and 2062 edges; USSR has
  85 entries spanning levels I–X. `ussr-ms-1` has level-I root modules and
  outgoing level-II vehicle links. `ussr-is8` contains
  `gun-2 → vehicle-ussr-is-7` at 189200 XP; `ussr-is-7` is terminal.
- The extraction reads hash-pinned #717 XML and does not execute client code.
  This is a complete reference catalogue for the inspected source set, not a
  proof that a native account has received the same payload.

The bounded static graph guard is implemented in
`tools/research_tree_audit.py` with eight positive/negative tests. Its receipt
`local/evidence/20261008-p09a-tree-graph-audit-02-receipt.json` is
`PASS_STATIC_RESEARCH_TREE_GRAPH` (374 trees, 3945 nodes, 2062 edges); this is
the accepted static part of P09A and does not change the native handoff gate.

### VERIFIED static native visibility predicate

Receipt: `local/evidence/20261007-native-tree-filter-01/predicate-01.json`.
Pinned #717 bytecode establishes the chain:

1. `NationTreeData.load` enumerates `vehicles.g_list.getList(nation)`.
2. It obtains display data and skips a missing item.
3. It obtains `item` and skips `item.isHidden` before `_addNode`.
4. `Vehicle`/`FittingItem` derive `isHidden` through
   `proxy.shop.getItem(intCompactDescr)`.
5. `ShopCommonStats.getHiddens` derives the hidden set from
   `shop.getItemsData().get('notInShopItems', [])`.

This proves the native filter path, not the full account wire serializer. The
correct server-side direction is to preserve every static node and provide a
consistent authoritative shop payload (`itemPrices` plus `notInShopItems`) for
owned/unavailable references. An owned vehicle disappearing from the native
list must not cause the static graph to be pruned.

### OBSERVED native selection boundary

`local/evidence/20261007-p03i-vehicle-profile-loadout-01/native-selection-07/selection-07.json`
records a real local selection transition inventory `1 → 2` to `ussr:IS-7`
(type compact descriptor 7169, 2150 HP, five crew slots, four visible models).
The fixture was unchanged. Current IS-7 state is
`crew_assigned=false`, ammunition count `0`, so battle admission remains
`FAIL_CLOSED`; selection is not queue/battle proof.

### Existing authoritative fixture shape

The r4 manifest is `ea967805376908e939fa691bb3bbc51e72253162aff98732bd753762eec35718`.
The current fixture records the shop payload in `shop.bin` (SHA256
`b8bd4a9c23a5b58c28d0838a5eab5c3f99c707ce2d496dd3747f9fb8e344c467`) and keeps
profile, inventory, dossier and compatibility files hash-bound. Existing
fixture generators already treat `itemPrices` and `notInShopItems` as a typed
catalogue/ownership boundary; their output is test-lab data, not native wire
compatibility evidence.

## Unknowns that block implementation

- Exact native account payload and callback that feed `TechTree.py`/
  `NationTreeData.load` are not captured.
- The live payload ordering, serializer envelope, revision/cursor fields and
  relation between inventory ownership, `itemPrices` and `notInShopItems` have
  not been measured from the #717 client.
- A screenshot of a tree is insufficient to identify which field hid a node;
  the account/shop payload, native callback and screen must be correlated.
- The selected IS-7 has no server-owned crew/ammunition readiness, so any queue
  or battle test must remain a later gate.
- Exact native account callback names/indices for tree refresh and stale shop
  data are UNKNOWN. Do not reuse CMD700 or map-drive parser assumptions.

## Execution phases

### A. Freeze static inputs and ownership matrix (read-only)

1. Record the current hashes above plus the original #717 `ussr/list.xml`,
   `ussr/is8.xml` and `ussr/is-7.xml` hashes from the static receipt.
2. Build a matrix from server-owned fixture data only: owned MS-1, explicit IS-7
   grant, and one unowned reference vehicle if the account fixture contains it.
   For every compact descriptor record inventory presence, `itemPrices` presence,
   `notInShopItems` membership and expected native visibility as
   `UNKNOWN` until the live payload is captured.
3. Keep the complete static graph immutable. Any difference must be represented
   as an account/shop delta with a version and source hash.

### B. Capture the native tree handoff (research copy only)

1. Use one manifested research-client copy and the existing local authenticated
   account. Do not touch original client or deployed service.
2. Capture a normal hangar/account sync, open USSR research, and collect the
   native callback/trace around `requestNationTreeData` and
   `getNationTreeData`. Capture the exact shop/account payload bytes before and
   after selecting MS-1/IS-7; preserve packet hashes, runtime trace, source
   hashes, rollback ledger and screenshots.
3. Use separate runs for any changed fixture/grant. Never infer a wire field from
   a screenshot or from the map-drive CMD700 helper.
4. Stop at the first measured callback and keep the capture bounded; no purchase,
   research spend, battle queue, or inventory mutation is part of P09A.

### C. Define the bounded payload contract

After the capture, write a versioned read-only schema that validates only measured
fields. It must:

- bind to the authenticated account/profile and exact source/fixture hashes;
- preserve the full static tree hash and graph counts;
- parse `itemPrices`, `notInShopItems`, ownership references and revision/cursor
  fields with strict integer/list/depth/size bounds;
- reject duplicate IDs, unknown compact descriptors, stale revisions, path
  escapes, non-finite values and payloads that silently delete static nodes;
- report `catalog_complete`, `account_visibility`, `native_callback` and
  `runtime_eligibility` separately; an empty missing list is not runtime-ready;
- treat `IS-8 → IS-7` as a directed edge and preserve terminal IS-7; never add a
  reverse edge just to make the screen look fuller.

The first implementation should be a read-only verifier plus negative tests. It
must not make gateway queue changes or accept client-authored ownership.

### D. Native visual/handoff gate

Pass only when one receipt ties together the hash-pinned static graph, the
server-owned shop payload, the native research callback and the rendered tree.
The acceptance run must show:

- USSR level-I roots and the IS-8 → IS-7 edge in the reference graph;
- owned MS-1/IS-7 visibility behavior matching the measured `notInShopItems`
  policy without deleting their static nodes;
- an unowned reference case, if available, with the opposite measured policy;
- native tree callback and screenshot from the same account/revision;
- no fixture/database mutation, no stale-payload acceptance and successful
  rollback/relogin where the run changes only an isolated research copy.

Selection-to-CMD700 and selected-vehicle battle admission remain a separate
P03I/native queue card. P09A must not mark them PASS.

## Acceptance, status and rollback

Acceptance label for this planning/native-handoff card:
`PASS_STATIC_RESEARCH_TREE_GRAPH / PASS_P09A_PLAN_STATIC_PREDICATE_AND_HANDOFF_GATE`.
It is **not** native implementation acceptance. Until phase B runs,
`native_payload=NOT_RUN`, `visual_handoff=NOT_RUN` and
`battle_admission=NOT_RUN` remain explicit.

No tracked code, client, service, fixture or database is changed by this plan.
A future implementation must use a dedicated `codex/p09a-*` branch and a fresh
receipt. Rollback is deletion/revert of the docs-only card plus removal of its
ignored evidence directory; no runtime restoration is needed.

## Single next step

Run one bounded read-only native research-tree capture on the research copy,
correlating the shop/account payload, `requestNationTreeData` callback and USSR
screen before writing any server adapter or visibility decoder.
