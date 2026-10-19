# -*- coding: utf-8 -*-
"""PROJECT POLICY, not original 0.9.1: opt-in GUI FX cue for the Sixth Sense lamp.

#717 PlayerAvatar.updateVehicleMiscStatus(IS_OBSERVED_BY_ENEMY) only calls
Battle.showSixthSenseIndicator(True) and battle.swf animates the lamp without
audio (docs/research/P07B_AUDIO_BOUNDARY_20261018.md). With the explicit prepare
option this module wraps that one Battle method: the original call runs first and
unchanged, then one existing gui.fev notifications_FX event is played directly
through the original SoundGroups.FMODplaySound when the lamp lights from dark.
A repeated show while the lamp is still lit (GUI_SETTINGS.sixthSenseDuration
after the latest show) is silent. IngameSoundNotifications queues, the Minimap
radar cue and the onScoutEvent voice are not called or changed.

Pure Python 2.7 at import time: prepare (Python 3) and tests load this module;
engine modules are imported only by install() inside the client.
"""
import hashlib
import traceback

try:
    string_types = (basestring,)
except NameError:
    string_types = (str,)

VERSION = 1
SETTING = 'sixth_sense_sound'
POLICY = 'project_override_not_original_091'
# Existing #717 gui.fev group /GUI/notifications_FX (gui/sound_notifications.xml,
# Minimap.__init__); no new resource. Keys are the only accepted option values.
CANDIDATES = {
    'gun_intuition': '/GUI/notifications_FX/gun_intuition',
    'enemy_sighted_for_team': '/GUI/notifications_FX/enemy_sighted_for_team',
    'minimap_attention': '/GUI/notifications_FX/minimap_attention',
}
BATTLE_CONTRACT = ('scripts/client/gui/Scaleform/Battle.py', 'showSixthSenseIndicator', 303,
                   ('self', 'isShow'),
                   '3422e8e98785ca88346035b78dd2c09a7ba7b0e9c637492d15e8da56278434ab')
SOUND_CONTRACT = ('scripts/client/SoundGroups.py', 'FMODplaySound', 659, ('self', 'event'),
                  '3544f2341473c157c71c9d886d064de41ecda942003611392be0854506b74563')
HISTORICAL_DURATION_MS = 2000  # #717 gui_settings.xml sixthSenseDuration (P07B ledger)
MAX_DURATION_MS = 60000
EVENT = 'project_sixth_sense_sound'

_installed = None


def validate_candidate(value):
    if not isinstance(value, string_types) or value not in CANDIDATES:
        raise ValueError('unsupported project Sixth Sense sound candidate')
    return CANDIDATES[value]


def prepare_option(value, profile13=False, map_drive=False):
    """Prepare-time seam; None keeps the original silent lamp."""
    if value is None:
        return None
    validate_candidate(value)
    if profile13 is not True and map_drive is not True:
        raise ValueError('Sixth Sense sound requires an explicit battle mode')
    return {'candidate': value, 'event_path': CANDIDATES[value], 'policy': POLICY,
            'version': VERSION, 'original_behavior': 'silent lamp (P07B VERIFIED)',
            'native_audio_check': 'NOT_RUN'}


def validate_settings(settings):
    value = settings.get(SETTING)
    if value is None:
        if SETTING in settings:
            raise ValueError('Sixth Sense sound setting must be omitted when disabled')
        return None
    validate_candidate(value)
    if (settings.get('enable_profile13_battle') is not True
            and settings.get('enable_map_drive') is not True):
        raise ValueError('Sixth Sense sound requires an explicit battle mode')
    return value


def duration_seconds(value):
    if type(value) is not int or not 1 <= value <= MAX_DURATION_MS:
        raise ValueError('bounded integer sixthSenseDuration required')
    return value / 1000.0


class Cue(object):
    """One cue per dark-to-lit lamp transition; never repeats while lit."""

    def __init__(self, candidate, play, clock, duration, audible, record):
        self.candidate = candidate
        self.event_path = validate_candidate(candidate)
        if not (callable(play) and callable(clock) and callable(audible) and callable(record)):
            raise TypeError('Sixth Sense cue requires callable engine seams')
        if type(duration) is not float or not 0.0 < duration <= MAX_DURATION_MS / 1000.0:
            raise ValueError('bounded lamp duration required')
        self.play, self.clock, self.duration = play, clock, duration
        self.audible, self.record = audible, record
        self.battle_id = self.shown_at = self.lit_until = None

    def after_show(self, battle_id, is_show):
        now = self.clock()
        if type(now) is not float:
            raise TypeError('native clock must be float')
        if is_show is not True:
            return self._note('ignored_not_show', now)
        if battle_id != self.battle_id:
            self.battle_id, self.shown_at, self.lit_until = battle_id, None, None
        # A clock that went backwards is not "still lit": treat it as a new lighting.
        repeat = self.shown_at is not None and self.shown_at <= now < self.lit_until
        self.shown_at = now
        self.lit_until = max(self.lit_until, now + self.duration) if repeat else now + self.duration
        if repeat:
            return self._note('repeat_while_lit', now)
        reason = self.audible()
        if reason is not None:
            return self._note(reason, now)
        if self.play(self.event_path) is None:
            return self._note('fmod_returned_none', now)
        return self._note('played', now)

    def _note(self, outcome, now):
        self.record(EVENT, version=VERSION, policy=POLICY, candidate=self.candidate,
                    event_path=self.event_path, outcome=outcome, native_time=now,
                    lit_until=self.lit_until)
        return outcome


def _contract(function, expected):
    filename, name, line, args, digest = expected
    code = getattr(function, 'func_code', getattr(function, '__code__', None))
    if (code is None or code.co_filename.replace('\\', '/') != filename or code.co_name != name
            or code.co_firstlineno != line or code.co_argcount != len(args)
            or tuple(code.co_varnames[:len(args)]) != args or code.co_flags & 12
            or hashlib.sha256(code.co_code).hexdigest() != digest):
        raise RuntimeError('original #717 callback differs: ' + name)


def install(record, candidate):
    """Client-only. Wrap the exact #717 Battle method; fail closed on any mismatch."""
    global _installed
    if _installed is not None:
        raise RuntimeError('Sixth Sense sound already installed')
    if not callable(record):
        raise TypeError('Sixth Sense sound recorder required')
    validate_candidate(candidate)
    import BigWorld
    import BattleReplay
    import SoundGroups
    from gui import GUI_SETTINGS
    from gui.Scaleform.Battle import Battle
    original = Battle.__dict__.get('showSixthSenseIndicator')
    _contract(original, BATTLE_CONTRACT)
    _contract(SoundGroups.SoundGroups.__dict__.get('FMODplaySound'), SOUND_CONTRACT)
    duration_ms = GUI_SETTINGS.sixthSenseDuration

    def play(path):
        groups = SoundGroups.g_instance
        if type(groups) is not SoundGroups.SoundGroups:
            raise RuntimeError('original SoundGroups instance required')
        return groups.FMODplaySound(path)

    def audible():
        # Same suppression as original IngameSoundNotifications.play for FX cues.
        replay = BattleReplay.g_replayCtrl
        if replay is not None and replay.isPlaying and replay.isTimeWarpInProgress:
            return 'replay_time_warp'
        if BigWorld.isWindowVisible() == False:
            return 'window_hidden'
        return None

    def clock():
        return float(BigWorld.time())

    cue = Cue(candidate, play, clock, duration_seconds(duration_ms), audible, record)

    def showSixthSenseIndicator(self, isShow):
        result = original(self, isShow)
        try:
            cue.after_show(id(self), isShow)
        except Exception:
            record(EVENT + '_error', version=VERSION, traceback=traceback.format_exc()[-4000:])
            raise
        return result

    Battle.showSixthSenseIndicator = showSixthSenseIndicator
    _installed = (Battle, original, showSixthSenseIndicator)
    record(EVENT + '_installed', version=VERSION, policy=POLICY, candidate=candidate,
           event_path=cue.event_path, duration_ms=duration_ms,
           duration_is_historical=duration_ms == HISTORICAL_DURATION_MS,
           original_call_first=True, notification_queues_touched=False,
           native_audio_check='NOT_RUN')
    return cue


def restore(record):
    global _installed
    if _installed is None:
        return False
    battle, original, wrapper = _installed
    if battle.__dict__.get('showSixthSenseIndicator') is not wrapper:
        raise RuntimeError('Sixth Sense wrapper was replaced; original not restored')
    battle.showSixthSenseIndicator = original
    _installed = None
    record(EVENT + '_restored', version=VERSION)
    return True
