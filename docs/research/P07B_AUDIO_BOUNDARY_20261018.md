# P07B audio boundary — Sixth Sense lamp (2026-10-18)

The owner completed the P07B native geometry run and reported a visual lamp
without a lamp sound. This was checked against the permitted #717 client and
the actual test-copy audio package before changing server code.

## Verified original path

`PlayerAvatar.updateVehicleMiscStatus` receives
`VEHICLE_MISC_STATUS.IS_OBSERVED_BY_ENEMY = 1` and calls only
`Battle.showSixthSenseIndicator(True)`. The decompiled #717
`gui/scaleform/battle.swf` handler `onShowSixthSense` performs the indicator
timeline transition (`active`, timer and `fade`) and does not call a sound
manager or an audio callback.

The source-bound callback is therefore a visual status callback. Its server
candidate remains the existing `0x47` wire contract in
`shared/sixth_sense_wire.rs`.

## Audio resources and the separate scout path

The retained #717 GUI sound notification table and FMOD GUI bank contain
`enemy_sighted_for_team`, `enemy_sighted` and `enemies_sighted`, but no
`sixth_sense`, `sixth-sense` or `lamp` event. The original `Avatar.onScoutEvent`
callback is a different enemy-spotted voice/FX path:

- `SPOTTED = 0`, `HIT_ASSIST = 1`, `KILL_ASSIST = 2`;
- `PlayerAvatar.onScoutEvent` calls `ComplexSoundNotifications`;
- the helper selects `enemy_sighted` or `enemies_sighted` and cancels the team
  notification before playing it.

This callback does not prove a Sixth Sense lamp sound. Guessing its method ID
or publishing it as a substitute would change enemy-spotted semantics and may
leak a notification to the wrong recipient.

## Decision

No server audio callback was added. The owner's result is recorded as:

- P07B geometry/LOS/rollover/visual lamp: owner PASS;
- original Sixth Sense lamp sound: **VERIFIED absent from this client path**;
- project-owned audio override: NOT_IMPLEMENTED / NOT_RUN.

Adding a chime is a separate client/audio card. It must choose an explicit
project policy (a new resource or the existing `enemy_sighted_for_team` FX),
modify only the prepared test-copy overlay, and run a native audio check. It
must not be described as original 0.9.1 behavior.

The combined owner scenario remains useful: record the visual lamp and the
absence/presence of any chosen project override together with P06T ammo-bay
loss and turret detachment. The turret/damage result is independent of this
audio boundary.

Evidence from the owner run is retained in
`local/evidence/20261018-p07b-native/owner-feedback-audio-missing.json`.
