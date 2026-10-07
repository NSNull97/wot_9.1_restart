# P09A — research-tree visibility evidence ledger

Date: 2026-10-08, Asia/Yekaterinburg
Branch: `codex/p09a-visibility-matrix`.
Scope: read-only static graph verification, a bounded server-owned fixture
matrix, and preparation for native account-owned research-tree visibility.
No client, gateway, deployed service, fixture or database was started or modified.

## Evidence ledger

| Claim | Status | Evidence | Limit |
|---|---|---|---|
| Static #717 catalogue is complete for the inspected source set | `VERIFIED` | `web/RESEARCH_TREE_REPORT.md`; `catalog.v1.json` SHA `d66aad60...`; `catalog-research.v1.json` SHA `fddd2181...` | Reference data is not native account payload |
| Bounded graph shape, targets and USSR tier/direction predicates | `PASS_STATIC_RESEARCH_TREE_GRAPH` | `local/evidence/20261008-p09a-tree-graph-audit-01/receipt.json`, SHA `39733821cf916a069152a0d67909fca54b816ebab13ad3a33dc0edb94abb0f44` | Static graph only; shop/account visibility remains separate |
| USSR graph has levels I–X, MS-1 roots and IS-8 → IS-7 | `VERIFIED` | `web/data/catalog-research.v1.json`; P04 research | Direction is `IS-8 → IS-7`; IS-7 terminal |
| Native tree filters `item.isHidden` before adding a node | `VERIFIED_STATIC_NATIVE_FILTER` | `local/evidence/20261007-native-tree-filter-01/predicate-01.json` (SHA `65704882b8361534f68e0965b3e8e4188fb60f87f3f9b48f40a2d403e42956a0`) | Bytecode path only; full wire callback not captured |
| Hidden set derives from `shop.items.notInShopItems` | `VERIFIED_STATIC_NATIVE_FILTER` | Same predicate receipt; `ShopCommonStats.getHiddens/getItem` disassembly | Account serializer/order still unknown |
| Owned/granted fixture descriptors are placed in `notInShopItems` | `OBSERVED` | r4 fixture manifest/generator and predicate receipt | Project fixture policy, not proof of server/client compatibility |
| Native selection 1 → 2 loads IS-7 model | `OBSERVED` | `native-selection-07/selection-07.json` | Passive observer; no tree payload or battle handoff |
| IS-7 is battle-ready | `FAIL_CLOSED` | selection receipt: `crew_assigned=false`, ammo `0` | Must not be promoted to queue admission |
| Native research-tree account callback and payload | `NOT_RUN` | No live capture yet | Required next experiment |

## Phase A static fixture matrix

Receipt: `local/evidence/20261008-p09a-visibility-matrix-01/receipt.json`,
status `PASS_STATIC_FIXTURE_VISIBILITY_MATRIX`.

The bounded reader uses the literal decoder from `tools/verify_hangar.py` and
only accepts fixture/catalog paths under the repository root. It checks the
manifest file hashes, parses `state.bin` and `shop.bin`, validates the
compatibility mapping and hash-bound MS-1/IS-7 descriptor JSON, then
cross-checks the static graph with `tools/research_tree_audit.py`.

| Vehicle | Compact descriptor | `state.inventory[1].compDescr` | `itemPrices` | `notInShopItems` | Expected native visibility | Runtime eligibility |
|---|---:|---|---|---|---|---|
| MS-1 | 3329 | present (slot 1) | present | member | `UNKNOWN` | `NOT_RUN` |
| IS-7 | 7169 | present (slot 2) | present | member | `UNKNOWN` | `NOT_RUN` |

The state mapping is the source for the inventory column; the profile JSON is
not used to manufacture presence. The fixture has no separate unowned
reference compact descriptor, so the receipt records
`unowned_reference.status=NOT_AVAILABLE_IN_FIXTURE`. The static graph remains
complete and is never pruned by this matrix. Native payload ordering, callback
correlation, rendered visibility and battle readiness remain outside this
receipt.

Targeted tests are in `tests/test_research_tree_visibility_matrix.py` and
cover the real r3/r2 fixture shapes plus negative unknown-ID, duplicate-hidden,
graph-hash, malformed-literal and path-boundary controls.

## Static hashes

- `web/data/catalog.v1.json`: `d66aad60c13d83807f49b1ebfc8cc89f330e658ed3223706169f763052547567`.
- `web/data/catalog-research.v1.json`: `fddd218109633aeb009bfca2859e5da1c4416737a48be71aa63b278a848df698`.
- Original `ussr/list.xml`: `167a637d725a233d42e52bd7d5bac00b9af45c0ef225163ab578e202454f5138`.
- Original `ussr/is8.xml`: `73ea8ffa6b7f0522962d7ab5631eaaeeaa05d74f5b20b6c153c8f9feca3cb4be`.
- Original `ussr/is-7.xml`: `8d55fa4657a88f1436cd164afe11bade875a906fa7b97256f1fb2f803b09c10d`.
- r4 fixture manifest: `ea967805376908e939fa691bb3bbc51e72253162aff98732bd753762eec35718`.
- r4 `shop.bin`: `b8bd4a9c23a5b58c28d0838a5eab5c3f99c707ce2d496dd3747f9fb8e344c467`.

## Interpretation

The static graph and the native account visibility policy are separate layers.
The graph must remain complete even when the client hides an owned reference.
The current evidence supports an authoritative shop payload containing
`itemPrices` and `notInShopItems`, but does not establish the exact native
serializer or callback. The correct next action is a bounded research-copy
capture of account/shop data plus the native tree callback and screenshot.

The predicate receipt's four hash-bound research-client sources were rechecked
on 2026-10-08: all four matched their recorded SHA-256 values. This is a
source-provenance recheck only; no native process or account/shop payload was
started or captured.

Do not use the current map-drive CMD700 parser for this card. Do not use native
selection alone to claim queue/battle readiness. Do not add an IS-8-after-IS-7
edge: the verified direction is IS-8 to IS-7.

## Acceptance gate

`PASS_STATIC_RESEARCH_TREE_GRAPH / PASS_P09A_PLAN_STATIC_PREDICATE_AND_HANDOFF_GATE`
applies to the static guard and docs-only preparation. The additional Phase A
receipt is `PASS_STATIC_FIXTURE_VISIBILITY_MATRIX`; native payload, visual
handoff and battle admission remain `NOT_RUN`. A later implementation can pass only with a receipt binding account
identity, source/fixture hashes, shop payload, native callback and screenshot;
all malformed/stale/partial payloads must fail closed.

## Commands and rollback

Read-only inspection used `Get-Content`, `rg`, `Get-FileHash` and fixture
manifest reads from the permitted local repository/evidence paths. No runtime
command was launched. Rollback is a reviewed revert of this docs-only branch;
ignored local evidence is untouched.

Single next step: capture the native USSR research-tree payload/callback on the
research client and correlate it with the static graph and the hash-bound
`notInShopItems` state recorded by Phase A.
