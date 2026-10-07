# P10A — training-room lifecycle static research

Status: **PASS_STATIC_CONTRACT_BOUNDARY / NATIVE_ROOM_LIFECYCLE_NOT_RUN**.

Branch: `codex/p10a-training-room-static`
Base: `f63f204e39f0cf02de366822e64af709862447eb` (`main`)

This is a read-only audit of the verified P00/P01 entity-definition and
content-manifest receipts. It establishes what can safely be planned for a
training-room slice of P10. It does not claim that the current server accepts
these methods or that the native client sends them in the order below.

## Receipts and provenance

| Static question | Receipt | Classification |
|---|---|---|
| Account/prebattle/unit method names and argument shapes | `local/evidence/20261002-p00-p01/decoded/res__scripts__entity_defs__account.def.json`, `prebattle.def.json`, `unitmgr.def.json` | `VERIFIED_STATIC / NATIVE_TRACE_NOT_RUN` |
| Original file hashes for the client training-room surface | `local/evidence/20261002-p00-p01/baseline/original-content-manifest.json` | `VERIFIED_STATIC / SOURCE_PRESENCE_ONLY` |
| Client-side module names for training/prebattle UI | same baseline manifest | `VERIFIED_STATIC / SEMANTICS_NOT_DECODED_HERE` |
| Lifecycle ordering, race handling and native request IDs | no P00/P01 runtime receipt | `UNKNOWN / NOT_RUN` |

Relevant manifest hashes (the values are inputs, not protocol IDs):

| Path | Bytes | SHA-256 |
|---|---:|---|
| `res/scripts/client/clientprebattle.pyc` | 6155 | `c74fc3070d15fb7099e2fba95f955483b09df174596d9f6d118db0956ab9decb` |
| `res/scripts/client/clientunitmgr.pyc` | 15046 | `c4c50ee6a462f7988ad1f8d5d9ae2a6f9238feb08994b0d0b00119d19cdd7edc` |
| `res/scripts/client/gui/scaleform/daapi/view/lobby/trainings/trainingroom.pyc` | 18298 | `a0647da875489f330281d614d24cddc9d8c08b79245e0064c47fd2b4a57f3970` |
| `res/scripts/client/gui/scaleform/daapi/view/lobby/prb_windows/prebattlewindow.pyc` | 14517 | `9586fa2ff766436b9699f9700ab330b538ae2113a8937a7d5ce3df6625d1bfc1` |
| `res/scripts/client/gui/scaleform/daapi/view/lobby/prb_windows/prbsendinviteswindow.pyc` | 6136 | `8d88a4f44444eac982ca59464dfa61ded1fb36007d7a5e078d0aa4e0fc3407dc` |
| `res/scripts/client/gui/scaleform/daapi/view/meta/receivedinvitewindowmeta.pyc` | 1648 | `371115c2d59d2aaf9c4165599904abd6416e9df6138e6fe93863547391320558` |
| `res/scripts/entity_defs/account.def` | 10588 | `883ec72e77675600f245e0f0aea8837e35c2c4bb9e7a5c5d70f3656d9d076674` |
| `res/scripts/entity_defs/prebattle.def` | 1920 | `115d555f1d13aa720c8ed4ee2240ef704788695614f1bd51671ae11c4e8a9dd8` |
| `res/scripts/entity_defs/unitmgr.def` | 1581 | `cb3b15a69f940981bf8676d914eb34a747ed46322659a0fcb91c219c3979ddc1` |

## Verified static contract

The entity definitions provide the following names and shapes. `wire_id` is
`UNKNOWN` for all rows; names must not be converted to invented numeric IDs.

### Account boundary

| Method/callback | Shape | Classification |
|---|---|---|
| `createTraining` | `INT32`, `INT32`, `BOOL`, `STRING`, `Exposed` | `VERIFIED_STATIC` |
| `createDevPrebattle` | `INT8`, `INT32`, `INT32`, `STRING`, `Exposed` | `VERIFIED_STATIC` |
| `sendPrebattleInvites` | `ARRAY<INT64>`, `STRING`, `Exposed` | `VERIFIED_STATIC` |
| `onPrebattleJoined` (client) | `OBJECT_ID` | `VERIFIED_STATIC` |
| `onPrebattleJoinFailure` (client) | `UINT8` | `VERIFIED_STATIC` |
| `onPrebattleLeft` (client) | no arguments | `VERIFIED_STATIC` |
| `onKickedFromPrebattle` (client) | `UINT8` | `VERIFIED_STATIC` |
| `receivePrebattleRoster` | `OBJECT_ID`, `PYTHON` | `VERIFIED_STATIC`; payload semantics `UNKNOWN` |
| `updatePrebattle` (client) | `UINT8`, `STRING` | `VERIFIED_STATIC`; code/text semantics `UNKNOWN` |
| `onPrebattleResponse` | `OBJECT_ID`, `INT16`, `BOOL`, `STRING`, `INT32` | `VERIFIED_STATIC`; response code meanings `UNKNOWN` |
| `onPrebattleVehicleChanged` | `OBJECT_ID`, `INT32`, `INT32` | `VERIFIED_STATIC`; fields `UNKNOWN` |

### Prebattle room boundary

| Method | Shape | Classification |
|---|---|---|
| `addPlayer` | `MAILBOX`, `STRING`, `DB_ID`, `UINT8`, `STRING`, `DB_ID`, `STRING`, `UINT32` | `VERIFIED_STATIC`; field semantics `UNKNOWN` |
| `removePlayer` | `INT32`, `OBJECT_ID` | `VERIFIED_STATIC` |
| `setPlayerNotReady` | `INT32`, `OBJECT_ID`, `UINT16`, `BOOL` | `VERIFIED_STATIC` |
| `setPlayerReady` | `INT32`, `OBJECT_ID`, `INT32`, `STRING`, `ARRAY<INT32>`, `ARRAY<INT32>` | `VERIFIED_STATIC`; vehicle/ammo/equipment meaning `UNKNOWN` |
| `setPlayerOnline` | `OBJECT_ID`, `BOOL` | `VERIFIED_STATIC` |
| `updatePlayerInfo` | `OBJECT_ID`, `UINT8`, `DB_ID`, `STRING` | `VERIFIED_STATIC` |
| `kickPlayer` | `MAILBOX`, `INT32`, `OBJECT_ID` | `VERIFIED_STATIC` |
| `changePlayerRoster` | `MAILBOX`, `INT32`, `OBJECT_ID`, `UINT8` | `VERIFIED_STATIC`; team/slot mapping `UNKNOWN` |
| `swapTeams` | `MAILBOX`, `INT32` | `VERIFIED_STATIC` |
| `changeArenaType` | `MAILBOX`, `INT32`, `INT32` | `VERIFIED_STATIC`; values `UNKNOWN` |
| `changeRoundLength` | `MAILBOX`, `INT32`, `INT32` | `VERIFIED_STATIC`; units `UNKNOWN` |
| `changeOpenStatus` | `MAILBOX`, `INT32`, `BOOL` | `VERIFIED_STATIC` |
| `changeComment` | `MAILBOX`, `INT32`, `STRING` | `VERIFIED_STATIC` |
| `changeArenaVoip` | `MAILBOX`, `INT32`, `BOOL` | `VERIFIED_STATIC` |
| `changeCompanyDivision` | `MAILBOX`, `INT32`, `INT32` | `VERIFIED_STATIC`; division semantics `UNKNOWN` |
| `changeGameplaysMask` | `MAILBOX`, `INT32`, `INT32` | `VERIFIED_STATIC`; mask values `UNKNOWN` |
| `setTeamReady` | `MAILBOX`, `INT32`, `UINT8`, `BOOL` | `VERIFIED_STATIC`; team semantics `UNKNOWN` |
| `setTeamNotReady` | `MAILBOX`, `INT32`, `UINT8` | `VERIFIED_STATIC`; team semantics `UNKNOWN` |
| `onArenaCreated` | `MAILBOX`, `UINT64`, `OBJECT_ID`, `UINT8`, `INT32`, `UINT8` | `VERIFIED_STATIC`; arena/team/type meanings `UNKNOWN` |
| `onArenaFinished` | 3 arguments, exact aliases in `prebattle.def` | `VERIFIED_STATIC`; result meaning `UNKNOWN` |
| `smartDestroy` | `UINT8` | `VERIFIED_STATIC`; reason values `UNKNOWN` |

The shape `PYTHON` on roster or player-info paths is opaque and must not be
fed to an unsafe generic deserializer. It remains a bounded, separately
researched payload in any future capture.

## Candidate lifecycle model (research labels)

The following model is intentionally a **domain planning boundary**, not a
native sequence:

```text
EMPTY
  └─ createTraining/createDevPrebattle → OPEN
OPEN
  ├─ invite/addPlayer/accept → ROSTERED
  ├─ changePlayerRoster/swapTeams → ROSTERED
  ├─ setPlayerReady or setTeamReady → READY_PENDING_START
  ├─ leave/kick/remove → OPEN or DESTROYED (policy UNKNOWN)
  └─ cancel/smartDestroy → DESTROYED
READY_PENDING_START
  ├─ all required participants ready → START_REQUESTED (predicate UNKNOWN)
  ├─ setPlayerNotReady/setTeamNotReady → ROSTERED
  └─ cancel/disconnect → DESTROYED or ROSTERED (race UNKNOWN)
START_REQUESTED
  ├─ onArenaCreated → IN_ARENA
  └─ failure/timeout → ROSTERED or DESTROYED (UNKNOWN)
IN_ARENA
  └─ onArenaFinished/smartDestroy → FINISHED → DESTROYED
```

No implementation should copy this diagram until a native trace fixes command
order, participant predicates, idempotency, stale revision behavior, and the
cancel-vs-start race.

## What remains NOT_RUN

- Native training-room creation, room ID and owner correlation.
- Invite delivery, accept/decline and private/open password behavior.
- Roster/team ordering, selected vehicle IDs and loadout admission.
- Player/team ready callbacks and start authorization.
- Cancel, leave, disconnect and `smartDestroy` race behavior.
- `onArenaCreated`/`onArenaFinished` payload semantics and battle handoff.
- Two simultaneous rooms with independent state.
- Queue, random matchmaking, platoons, worker assignment and battle results.

The safe next step is one owner-gated native capture of a private room, then a
second room in parallel. Do not add a guessed server route before those
receipts exist.

