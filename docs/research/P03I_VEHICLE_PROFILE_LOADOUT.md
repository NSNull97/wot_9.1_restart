# P03I — static vehicle/loadout handoff research

Status: **PASS_STATIC_NATIVE_TREE_AND_QUEUE_CONTRACT / NATIVE_CAPTURE_NOT_RUN**.

Branch: `codex/p03i-status`
Base: `ba0d5ce0f07247319f8cf617fc936facee4d0534` (`main`)

This ledger preserves only read-only #717 source observations. It does not
claim that the current server accepts native queue traffic, does not add a
profile/loadout runtime, and does not alter the original or research client.

## Source receipts

| Static question | Local receipt | Classification |
|---|---|---|
| Why an owned node can be hidden in the native tree | `local/evidence/20261007-native-tree-filter-01/predicate-01.json` | `VERIFIED_STATIC / NATIVE_PAYLOAD_NOT_RUN` |
| Native random-queue call chain and command fields | `local/evidence/20261007-p03i-queue-research-08/README.md` | `VERIFIED_STATIC / LIVE_QUEUE_NOT_RUN` |
| Whether existing capture helpers are ready for a live sample | `local/evidence/20261007-p03i-queue-capture-audit-01/README.md` | `OBSERVED_TOOLING_ONLY / LIVE_CAPTURE_NOT_RUN` |

The capture-tool audit receipt is pinned locally by
`audit.json` SHA-256
`9e945a9ca0750a83e6b26dfa83dfd6ee726f5c24063637b6166e3206e0d89b27`.
The read-only recheck matched its seven source hashes and passed bounded
`py_compile` for `verify_unified_entry.py`, `verify_hangar.py`,
`verify_account_ready.py` and `verify_channel_capture.py`. This confirms tool
readiness only; it does not provide the missing live CMD700 bytes or callback.

The receipts are ignored local evidence and are not copied into Git. Their
presence does not turn a static extraction into a native acceptance result.

## Provenance and exclusion

The safe static material is synthesized from commits `af7c724` (research-tree
predicate), `99f6856` (queue contract), `dc0de03` (manual queue-capture gate),
`2f5ec67` (callback semantics) and `e0065af` (capture-audit boundary). The
mixed runtime/client commits `4b66ce3` and `cae2c3b` are deliberately excluded;
this card carries no `server/gateway`, `client_patch`, fixture or native-overlay
change.

## Research-tree visibility predicate

The pinned client disassembly shows `NationTreeData.load` enumerating the
nation's static list, skipping `None`, then skipping `item.isHidden` before
calling `_addNode`. `Vehicle.__init__` and `FittingItem.__init__` derive
`isHidden` through `proxy.shop.getItem(intCompactDescr)`, while
`ShopCommonStats.getItem/getHiddens` derive the hidden set from
`shop.getItemsData().get('notInShopItems', [])`.

This is a static UI/account predicate. The reference catalogue must remain
complete; authoritative shop data controls visibility. The extracted graph
records **IS-8 → IS-7** as the input direction. Native account/shop payload,
the `requestNationTreeData`/`getNationTreeData` callback, an unowned control and
the owner screenshot correlation are **NOT_RUN**.

## Random-queue command contract

The static #717 call chain is:

```text
FightButton.fightClick
  → RandomQueueFunctional.join
  → BigWorld.player().enqueueRandom(g_currentVehicle.invID,
                                    gameplaysMask, arenaTypeID)
  → PlayerAccount.enqueueRandom
  → Account.doCmdInt3
```

The command pins the following fields:

| Field | Static value/shape | Status boundary |
|---|---|---|
| Request ID | `REQUEST_ID_NO_RESPONSE = 202` | static only |
| Command | `CMD_ENQUEUE_RANDOM = 700` | static only |
| Vehicle | selected `g_currentVehicle.invID`, `INT64` | live value **NOT_RUN** |
| Gameplay | `gameplaysMask`, `INT32` | live value **NOT_RUN** |
| Arena | `arenaTypeID`, `INT32` | live value **NOT_RUN** |
| Envelope | `INT16, INT16, INT64, INT32, INT32` from `Account.def` | static only |

The static disassembly names `onEnqueueFailure(UINT8, UINT8, STRING)` as the
failure method. `onEnqueued(queueType)` sets the random queue state and emits
`events.onEnqueuedRandom()`. Failure routes `errorCode` and `errorStr` to
`events.onEnqueueRandomFailure(...)`. These callback observations are client
semantics; they do not supply a server-owned target, reservation, battle ID or
profile admission result.

## Manual capture fields and stopping rule

The owner-gated capture must preserve, for one ordinary MS-1 queue click:

- receipt-matched client/process manifest and selected inventory identity;
- decrypted Account application body with request `202`, command `700`, both
  `INT16` fields, `INT64` vehicle ID and both `INT32` mask/arena fields;
- callback method and arguments: either `onEnqueued(queueType)` plus the
  resulting random-queue event, or `onEnqueueFailure(errorCode, errorType,
  errorStr)` plus the failure event;
- authenticated server correlation for the selected inventory ID and the
  exact failure/transition outcome;
- no fixture/database/inventory mutation, duplicate command side effect or
  client-authored profile acceptance.

If any body field or callback framing is missing, mark the run **NOT_RUN** and
retain the raw material in ignored evidence. Do not derive a decoder from the
map-drive experiment. Repeat for IS-7 only after explicit assigned crew and
server-owned ammunition are measured; current `crew_assigned=false`, ammo `0`
must remain fail-closed.

## Explicit unknowns

The following remain **UNKNOWN / NOT_RUN**:

- live CMD700 framing, gameplay mask and arena values;
- live `onEnqueued`/`onEnqueueFailure` callback bytes and ordering;
- selected-vehicle garage-to-battle handoff, reservation and rejoin;
- assigned IS-7 crew/tankman data, shell grant and equipment modifiers;
- server queue ownership, battle admission, hit, armor, damage and physics;
- two-PC/LAN behavior.

The static tree predicate and queue contract are evidence boundaries only. They
must not be reported as runtime compatibility or native owner acceptance.
