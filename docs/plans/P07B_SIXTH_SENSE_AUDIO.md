# P07B follow-up — Sixth Sense audio callback

## Trigger

The owner accepted the P07B geometry, cover/LOS, rollover and persistent visual
lamp checks, but reported that the lamp sound was missing. The current server
publishes `Avatar.updateVehicleMiscStatus` only; that callback drives the
Scaleform indicator and does not invoke the original sound notification path.

## Source-bound contract

The permitted #717 client exposes a separate `Avatar.onScoutEvent` callback:

- client arguments: `UINT8 eventType, OBJECT_ID reportedID`;
- cell arguments: `UINT8 eventType, ARRAY<OBJECT_ID> reportedIDs`;
- `SCOUT_EVENT_TYPE.SPOTTED = 0`, `HIT_ASSIST = 1`, `KILL_ASSIST = 2`;
- `PlayerAvatar.onScoutEvent` forwards `SPOTTED` to
  `ComplexSoundNotifications.notifyEnemySpotted`;
- the sound helper cancels `enemy_sighted_for_team`, then plays
  `enemies_sighted` for the plural branch or `enemy_sighted` for the single
  branch. This is the enemy-spotted voice/FX path, not proof of the Sixth
  Sense lamp sound.

The original Sixth Sense path was also checked directly: the #717
`updateVehicleMiscStatus` handler calls only
`Battle.showSixthSenseIndicator(True)`, and the original `battle.swf`
`onShowSixthSense` handler only changes the indicator timeline and fade timer.
The retained `gui/sound_notifications.xml` has no `sixth_sense` or `lamp`
event. Therefore the owner's missing lamp sound is **VERIFIED original-path
behavior**, not a broken `0x47` payload. A sound attached specifically to the
lamp would be a deliberate project-owned client/audio override.

The callback method ID and native serializer order remain `UNKNOWN`. They must
be derived from the bounded protocol map or a controlled native capture; the
existing Sixth Sense candidate ID `0x47` must not be reused by guesswork.

## Server boundary

No server-side audio callback is added in this branch. Publishing
`onScoutEvent` merely to force a sound would change the original enemy-spotted
semantics and would guess an unverified native method ID. The source ledger and
wire map must remain explicit until a controlled capture proves the callback
and serializer. If the owner chooses the project override, it becomes a
separate client/audio card with its own resource and UI compatibility gate.

## Combined owner gate

The follow-up native test is deliberately coupled to P06T:

1. Put MS-1 and IS-7 in one battle and create one fresh visibility transition.
2. Confirm the visual lamp and hear the `enemy_sighted` cue in the observing
   client. Repeat after hiding and reappearing if the event is once-per-epoch.
3. Destroy the target's ammo bay and confirm every remaining loaded shell is
   lost while depot stock remains unchanged.
4. Apply the qualifying lethal turret event and confirm the turret detaches,
   the tank is terminal, no further damage is accepted, and both clients get
   consistent results.
5. Return both clients to the hangar and record audio, damage, turret and
   session-return outcomes separately.

Visual-only Sixth Sense PASS is retained as prior evidence. The combined run
must record the absence of the original lamp sound explicitly, then separately
check any future project-owned audio override. P06T/turret-detach remains a
separate damage acceptance gate.
