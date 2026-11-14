"""Play the local stereoscope cue on the pinned native HUD callback."""

import traceback

SETTING = 'stereoscope_sound'
EVENT = 'project_stereoscope_sound'
EVENT_PATH = '/SCP/notifications_FX/scope_enabled'
DEVICE_ID = 4
FADE_SECONDS = 0.5
AVATAR_CONTRACT = (
    'scripts/client/Avatar.py', 'updateVehicleOptionalDeviceStatus', 1260,
    ('self', 'deviceID', 'isOn'),
    '601bb3cc8f7f95b8acab71d36bd2b20c343f6b9e59f12d0d2047c35d1a6d9320',
)
_installed = None


def validate_settings(settings):
    enabled = settings.get(SETTING, False)
    if type(enabled) is not bool or (enabled and settings.get('enable_p06t_mixed_ammo') is not True):
        raise ValueError('stereoscope sound requires the native mixed-ammo battle mode')
    return enabled


class Cue(object):
    def __init__(self, play, fade):
        self.play = play
        self.fade = fade
        self.arena = None
        self.active = False
        self.sound = None

    def stop(self):
        if self.sound is not None:
            sound, self.sound = self.sound, None
            sound.stop()

    def update(self, arena, active, muted):
        if arena != self.arena:
            self.stop()
            self.arena, self.active = arena, False
        if active == self.active:
            return 'unchanged'
        self.active = active
        if not active:
            if self.sound is not None:
                sound, self.sound = self.sound, None
                self.fade(sound)
            return 'deactivated'
        if muted:
            return 'muted'
        self.sound = self.play(EVENT_PATH)
        return 'played' if self.sound is not None else 'fmod_returned_none'


def install(record):
    global _installed
    if _installed is not None:
        raise RuntimeError('stereoscope sound already installed')
    import BigWorld
    import BattleReplay
    import SoundGroups
    from Avatar import PlayerAvatar
    from native_contract import check
    from project_sixth_sense_sound import SOUND_CONTRACT
    original = PlayerAvatar.__dict__['updateVehicleOptionalDeviceStatus']
    check(original, *(AVATAR_CONTRACT + ('optional device callback',)))
    check(SoundGroups.SoundGroups.__dict__['FMODplaySound'], *(SOUND_CONTRACT + ('sound callback',)))

    def play(path):
        return SoundGroups.g_instance.FMODplaySound(path)

    def fade(sound):
        started, volume = BigWorld.time(), sound.volume

        def step():
            try:
                elapsed = BigWorld.time() - started
                if 0 <= elapsed < FADE_SECONDS:
                    sound.volume = volume * (1 - elapsed / FADE_SECONDS)
                    BigWorld.callback(0.05, step)
                else:
                    sound.stop()
            except Exception:
                record(EVENT + '_error', traceback=traceback.format_exc()[-4000:])

        BigWorld.callback(0.05, step)

    cue = Cue(play, fade)

    def updateVehicleOptionalDeviceStatus(self, deviceID, isOn):
        result = original(self, deviceID, isOn)
        if deviceID == DEVICE_ID:
            try:
                replay = BattleReplay.g_replayCtrl
                muted = (not BigWorld.isWindowVisible()
                         or (replay is not None and replay.isPlaying and replay.isTimeWarpInProgress))
                outcome = cue.update(self.arenaUniqueID, bool(isOn), muted)
                record(EVENT, arena_unique_id=self.arenaUniqueID, active=bool(isOn), outcome=outcome)
            except Exception:
                record(EVENT + '_error', traceback=traceback.format_exc()[-4000:])
        return result

    PlayerAvatar.updateVehicleOptionalDeviceStatus = updateVehicleOptionalDeviceStatus
    _installed = (PlayerAvatar, original, updateVehicleOptionalDeviceStatus, cue)
    record(EVENT + '_installed', event_path=EVENT_PATH, original_call_first=True)


def restore(record):
    global _installed
    if _installed is None:
        return
    avatar, original, wrapper, cue = _installed
    if avatar.__dict__['updateVehicleOptionalDeviceStatus'] is not wrapper:
        raise RuntimeError('stereoscope callback was replaced')
    avatar.updateVehicleOptionalDeviceStatus = original
    _installed = None
    cue.stop()
    record(EVENT + '_restored')
