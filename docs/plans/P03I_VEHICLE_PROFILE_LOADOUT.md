# P03I — native vehicle selection and loadout capture gate

Status: **PASS_DOCS_ONLY_STATIC_BOUNDARY / NATIVE_HANDOFF_NOT_RUN**.

Card: `P03I_VEHICLE_PROFILE_LOADOUT`
Branch: `codex/p03i-status`
Base: `ba0d5ce0f07247319f8cf617fc936facee4d0534` (`main`)

This docs-only card records the safe static part of the P03I investigation:
the #717 research-tree visibility predicate, the native random-queue command
shape and its callback names, and the exact owner capture still required. It
does not add a vehicle profile, alter fire/reload/projectile runtime, wire a
queue command into the gateway, modify a fixture, or patch a client.

The static source-hash recheck is recorded in
`local/evidence/20261008-p03i-static-audit-01/receipt.json` by
`tools/p03i_static_audit.py`. It confirms the Account.def shape and both
permitted #717 copies while recording a one-character stale hash in the old
ignored queue README. Native payload, callback and server admission remain
outside this static card.

## Static boundary

The complete catalogue remains a reference graph. Native tree visibility is a
shop/account policy: `NationTreeData.load` skips `None` and `item.isHidden`,
while `isHidden` is derived through the shop item data's
`notInShopItems` set. An owned item disappearing from the native tree therefore
must not be “fixed” by deleting it from the static graph. The extracted graph
keeps the direction **IS-8 → IS-7**; UI/account payload correlation is still
unmeasured.

The static queue call chain is recorded as:

```text
FightButton.fightClick
  → RandomQueueFunctional.join
  → BigWorld.player().enqueueRandom(g_currentVehicle.invID,
                                    gameplaysMask, arenaTypeID)
  → PlayerAccount.enqueueRandom
  → Account.doCmdInt3
```

Pinned fields are request id `202` (`REQUEST_ID_NO_RESPONSE`), command `700`
(`CMD_ENQUEUE_RANDOM`), one `INT64` vehicle inventory ID and two `INT32`
values (`gameplaysMask`, `arenaTypeID`). `Account.def` gives the full command
shape `INT16, INT16, INT64, INT32, INT32`. Queue failure is a separate
`onEnqueueFailure(UINT8, UINT8, STRING)` callback.

The callbacks are static client semantics only: `onEnqueued(queueType)` marks
the random queue and emits `events.onEnqueuedRandom()`, while
`onEnqueueFailure` routes its error code and text to
`events.onEnqueueRandomFailure(...)`. None of these observations proves that
the server accepts the command or that a selected vehicle reaches battle.

## Exact owner capture

The next manual/native run must be bounded and receipt-matched:

1. Use the ordinary random-battle button once with the existing MS-1. Preserve
   the decrypted Account application body, source client/process manifest,
   native callback/runtime trace and the selected `g_currentVehicle.invID`.
2. Record request ID `202`, command `700`, the two leading `INT16` fields, the
   `INT64` vehicle inventory ID, the `INT32` gameplay mask and `INT32` arena
   type. Record whether the native transition callback or the exact failure
   callback arrived, including callback arguments and event name.
3. Correlate the selected inventory ID with the authenticated server-owned
   vehicle row. A mismatch, missing callback or malformed body is a failed
   capture, not permission to guess a decoder. Preserve raw frames only in
   ignored local evidence.
4. Repeat with IS-7 only after a separately hash-pinned fixture has explicit
   assigned crew and a server-owned shell stack. The current IS-7 fixture is
   `crew_assigned=false`, ammo `0`; it must fail closed without fixture,
   database or inventory mutation.

Acceptance requires measured live framing, selected-vehicle identity,
gameplay/arena values and either the native queue transition or the exact
failure callback. A static disassembly, unit test, screenshot or map-drive
`CMD700/701` experiment cannot satisfy this gate. Until this capture exists,
live CMD700, IS-7 admission, crew/ammunition reservation, equipment and rejoin
persistence remain **NOT_RUN**.

## Boundaries and rollback

Do not reuse the map-drive parser's hard-coded MS-1 route, add a speculative
decoder, or connect CMD700 to the gateway before the native sample. Original and
research clients, deployed services, databases and existing fixtures remain
read-only. This card changes documentation only; rollback is a single commit
revert.

See the [P03I research ledger](../research/P03I_VEHICLE_PROFILE_LOADOUT.md) and
[P03I evidence index](../evidence-index/P03I.md).
