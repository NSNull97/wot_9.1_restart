# P10A — training-room lifecycle static boundary

Status: **PASS_DOCS_ONLY_STATIC_BOUNDARY / NATIVE_ROOM_LIFECYCLE_NOT_RUN**.

Card: `P10A_TRAINING_ROOM_STATIC`
Branch: `codex/p10a-training-room-static`
Base: `f63f204e39f0cf02de366822e64af709862447eb` (`main`)

This card records the narrow, read-only P10 starting point visible in the
P00/P01 manifests and entity definitions: a training/prebattle room can be
represented as a server-owned object with a roster, per-player readiness,
team readiness, invitations and an arena-start callback. It deliberately does
not invent wire IDs, client command order, a matchmaking policy or an arena
admission implementation.

## Scope

The first P10 slice is a training-room lifecycle only:

```text
create room → invite/accept (when used) → roster/team assignment
→ select vehicle → player ready/not-ready → team ready/not-ready
→ start/arena-created → cancel/leave/destroy
```

The arrows are a **research plan**, not a verified native order. The native
client may use a different ordering or omit steps for a creator. Queueing,
random matchmaking, platoons, worker placement and battle results stay outside
this card.

## Static material available

The P00/P01 corpus is sufficient for a docs-only boundary:

- `account.def` exposes `createTraining`, `createDevPrebattle`,
  `sendPrebattleInvites`, `receivePrebattleRoster`, `updatePrebattle`, and
  prebattle join/leave/failure callbacks. The argument shapes are recorded in
  the research ledger; every numeric method ID remains `UNKNOWN`.
- `prebattle.def` exposes server-side lifecycle vocabulary: `addPlayer`,
  `removePlayer`, `setPlayerNotReady`, `setPlayerReady`, `setPlayerOnline`,
  `updatePlayerInfo`, `kickPlayer`, `changePlayerRoster`, `swapTeams`,
  `changeArenaType`, `changeRoundLength`, `changeOpenStatus`,
  `changeComment`, `changeArenaVoip`, `changeGameplaysMask`,
  `setTeamReady`, `setTeamNotReady`, `onArenaCreated`, `onArenaFinished` and
  `smartDestroy`.
- The baseline manifest contains client modules for this surface, including
  `clientprebattle.pyc`, `clientunitmgr.pyc`, `gui/prb_control/context/pre_queue_ctx.pyc`,
  `gui/prb_control/factories/prebattlefactory.pyc`,
  `gui/scaleform/daapi/view/lobby/trainings/trainingroom.pyc`,
  `prebattlewindow.pyc`, `prbsendinviteswindow.pyc`, and
  `receivedinvitewindowmeta.pyc`. Their presence proves source availability,
  not a captured lifecycle trace.

## Acceptance boundary

A future owner-gated/native capture must preserve the raw Account request and
callback sequence for one private training room and a second independent room.
It must correlate room identity, creator, invite target, roster changes,
selected vehicle inventory IDs, readiness transitions, start/cancel outcome and
teardown to the authenticated server state. Missing bytes, unknown command
IDs, or a callback without server correlation is `NOT_RUN`, not permission to
guess a serializer.

No gateway route, fixture, database schema, client overlay, service restart or
matchmaker is changed by this card.
