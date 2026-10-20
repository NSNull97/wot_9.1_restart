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

## Project override (2026-10-19, branch `codex/p07b-sixth-sense-sound`)

The owner asked for an audible lamp. This is **project policy, not original
0.9.1 behaviour**. It is off by default and lives only in the client patch.

### #717 GUI audio API (VERIFIED, marshal+dis under pinned CPython 2.7.3)

- `SoundGroups.FMODplaySound(self, event)` (`SoundGroups.pyc` e7cd3739…, line
  659) returns `FMOD.playSound(checkAndReplace(event))`: a 2D FMOD event by
  path, `None` on failure. `/GUI/notifications_FX` is in the SoundGroups
  `arena` group list, so the group is loaded in battle.
- `IngameSoundNotifications` reads `gui/sound_notifications.xml` (`gui.pkg`,
  e57321e6…, 67 events): per event `fx`/`voice` with `sound`, `playRules`
  (0 = immediate `FMODplaySound` inside a bare `try/except`, 1 = clear queue and
  append, 2 = insert first, 3 = append), `timeout` 3.0, `minTimeBetweenEvents`,
  `shouldBindToPlayer`. `play()` is silent while a replay time-warps or the
  game window is hidden.
- The same `updateVehicleMiscStatus` already plays a crew-skill FX through it:
  `LOADER_INTUITION_WAS_USED` → `self.soundNotifications.play('gun_intuition')`.
- `gui.fev` (967c4826…, identical in test copies a/b) group
  `notifications_FX`: `base_capture_1/2`, `enemy_sighted_for_team`,
  `gun_intuition`, `gun_reloaded`, `minimap_attention`, `sight_convergence`,
  `task_*`, `timer`, `cybersport_*`. No Sixth Sense or lamp event.
- Other #717 users of the candidates: `gun_intuition` — only
  `LOADER_INTUITION_WAS_USED` (our server never sends it); `enemy_sighted_for_team`
  — `Minimap.__addEntry` for a new enemy marker, cancelled by
  `ComplexSoundNotifications.notifyEnemySpotted`; `minimap_attention` —
  `Minimap.__init__` and the `chat_shortcut_common_fx` chat-command cue.

### Candidates (owner's choice; no new resource)

| `--sixth-sense-sound` | Bank in `res/audio` | Meaning in #717 | Risk |
|---|---|---|---|
| `gun_intuition` (recommended) | `gui_notifications_fx_intuition.fsb`, 22 KB | loader "Intuition" skill fired | none known: unused by our server today; also a crew-skill cue |
| `enemy_sighted_for_team` | `gui_enemy_sighted_for_team.fsb`, 90 KB | minimap radar ping for a new enemy | same sound would mean "we spotted" and "I am spotted"; FMOD instance sharing with the minimap ping UNKNOWN |
| `minimap_attention` | `gui_notifications_fx_minimap_attention.fsb`, 2.3 KB | minimap click / ally chat command | very short, confusable with ally pings |

Event→wave mapping (`intuition_03.wav`, `radar_sound_01.wav`,
`minimap_attention_03_stereo.wav`) is INFERRED from FEV strings, not decoded.

### Implementation

- `client_patch/project_sixth_sense_sound.py`; `prepare --sixth-sense-sound
  <candidate>` writes setting `sixth_sense_sound` and plan evidence
  `resources.project_sixth_sense_sound`. It requires `--enable-profile13-battle`
  or `--enable-map-drive`; the client re-validates the setting.
- `install` pins file/name/line/args/`co_code` SHA-256 of
  `Battle.showSixthSenseIndicator` (line 303, 3422e8e9…) and
  `SoundGroups.FMODplaySound` (3544f234…) and reads
  `GUI_SETTINGS.sixthSenseDuration` (bounded int, 2000 ms in #717). Any
  mismatch is a bootstrap error; nothing is patched.
- The wrapper calls the original first. From a dark lamp, `show(True)` plays the
  chosen event directly through `SoundGroups.FMODplaySound`, not through
  `IngameSoundNotifications`: no queue, no `cancel`, so the minimap radar and
  the `onScoutEvent` voice are unchanged. The lamp counts as lit until the
  latest show + `sixthSenseDuration`; a show while lit is silent and extends it.
  A new `Battle` window or a clock reset starts dark. Hidden window / replay
  time warp are silent (same rule as original FX cues) and still light the lamp,
  so no late cue follows. `FMODplaySound` returning `None` is recorded.
- Trace: `project_sixth_sense_sound` with `outcome` = `played`,
  `repeat_while_lit`, `window_hidden`, `replay_time_warp`, `fmod_returned_none`
  or `ignored_not_show`; plus `_installed`, `_error`, `_restored`.
- Server unchanged: `sixth_sense_wire.rs` already sends `0x47` once per
  spotting generation; the client rule only guards against duplicates.

### Checks (2026-10-19)

- `python -B -X utf8 -m unittest tests.test_project_sixth_sense_sound
  tests.test_sixth_sense_prepare`: 27 run, PASS, 3 skipped (2.7-only).
- `local/toolchains-py27-20261019/cpython-2.7.3-x86/python.exe -B -E -s
  tests/test_project_sixth_sense_sound.py`: 22 PASS, including both contracts
  against the original #717 bytecode.
- Tests that load `sr_interactive`/`interactive_client`: the same 5 errors as on
  the base `codex/full-test-20261019` (bundle NOT_RUN, stale prepare slices).
- Actual `prepare --enable-map-drive --sixth-sense-sound gun_intuition` on the
  default research copy: PREPARED, `client_write_performed=false`, evidence
  `local/p07b-sixth-sense-sound-20261019/prepare-mapdrive-gun-intuition-01/`
  (module pyc 4438bede…). Without a battle mode or with an unknown value
  prepare refuses before writing.
- Native audio check in the client: **NOT_RUN**.

### Installing on test copies a/b (NOT_RUN; only on the owner's command)

Clients a/b serve the running FULL-TEST stand; do not touch them during it.
Their patch is the 2026-10-17 install
`C:\wot091-night-20261017-01\w\local\stands\night-battle-20261017-03\unified-01\client-v8-morning61-final\install-{a,b}-01`,
prepared by the temporary tool copy
`C:\Users\NSNull\AppData\Local\Temp\wot091-night-workspace-kcadgetk\morning61\client-tools`.
Later, `paths.xml`, `res/engine_config.xml`,
`res_mods/0.9.1/scripts_config.xml` and `sr_interactive_settings.json` were
edited in place to point at port 20340. Their `*.global-heavy-prev*` copies
equal that ledger's installed hashes (checked 2026-10-19), so the ledger
rollback refuses until those four files are put back.

1. Close both clients. For a and b, save the four current files (for example
   as `*.full-test-20340*`), copy the `*.global-heavy-prev*` versions back and
   check their hashes against the ledger.
2. Roll back with the tool copy that installed the ledger:
   `python <client-tools>\interactive_client.py rollback --out <install-X-01>`.
3. Copy the current profile
   `D:\wot091-successor-worktree-20261018-01\local\stands\full-polygon-native-20261019-ramfix-01\client-profile-X`
   to `local/stands/full-test-20261019-01/client-sound-01/profile-X`.
4. From this branch's checkout, prepare and install (X = a, b):

```powershell
python tools/interactive_client.py prepare --out local/stands/full-test-20261019-01/client-sound-01/install-X --research-copy local/clients/p03f/X --public-key local/server/native-public.pem --endpoint 127.0.0.1:20340 --profile-dir local/stands/full-test-20261019-01/client-sound-01/profile-X --trace-dir local/stands/full-test-20261019-01/client-sound-01/runtime-X --compiler local/toolchains-py27-20261019/cpython-2.7.3-x86/python.exe --enable-profile13-battle --enable-p09d-ammo-service --enable-crew-recruitment --enable-crew-transfer --enable-cross-vehicle-crew --enable-roster-recruitment --enable-crew-progression --enable-crew-dismissal --enable-barracks-recruitment --enable-research-service --capture-hangar --disable-legacy-license-dialog --enable-p06t-mixed-ammo --enable-training-rooms --sixth-sense-sound gun_intuition
python tools/interactive_client.py install --out local/stands/full-test-20261019-01/client-sound-01/install-X
```

   This also replaces the 17.10 night-clone modules with this branch's
   `client_patch` (same checkout as the stand, as the one-checkout rule asks).
5. Native check: one fresh spotting of each client. The lamp lights with one
   cue; a repeated `0x47` while lit is silent; enemy-spotted voice and minimap
   radar sound as before. Read the outcomes in `runtime-X/native-*.jsonl`.

Rollback: `python tools/interactive_client.py rollback --out
local/stands/full-test-20261019-01/client-sound-01/install-X`. Without the
flag the patch keeps the original silent lamp.
