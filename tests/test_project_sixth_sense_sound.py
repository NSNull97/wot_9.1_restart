# -*- coding: utf-8 -*-
"""Project Sixth Sense cue (not original 0.9.1). Runs under CPython 2.7.3 and 3.

Fake engine modules prove ordering and the one-cue-per-lighting rule only; they
do not prove audio in the native client (native audio check is NOT_RUN).
"""
import hashlib
import json
import marshal
import os
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'client_patch'))
import project_sixth_sense_sound as cue_module

PATH = '/GUI/notifications_FX/gun_intuition'


class Harness(object):
    def __init__(self, visible=None):
        self.now = 100.0
        self.played = []
        self.records = []
        self.result = object()
        self.visible = visible

    def clock(self):
        return self.now

    def play(self, path):
        self.played.append(path)
        return self.result

    def audible(self):
        return self.visible

    def record(self, event, **fields):
        self.records.append((event, fields))

    def cue(self, candidate='gun_intuition', duration=2.0):
        return cue_module.Cue(candidate, self.play, self.clock, duration, self.audible, self.record)


class CueTests(unittest.TestCase):
    def test_first_lighting_plays_one_existing_fx_event(self):
        h = Harness()
        cue = h.cue()
        self.assertEqual(cue.after_show(1, True), 'played')
        self.assertEqual(h.played, [PATH])
        event, fields = h.records[-1]
        self.assertEqual(event, 'project_sixth_sense_sound')
        self.assertEqual(fields['policy'], 'project_override_not_original_091')
        self.assertEqual(fields['candidate'], 'gun_intuition')
        self.assertEqual(fields['lit_until'], 102.0)

    def test_repeated_show_while_lit_is_silent_and_extends_the_lamp(self):
        h = Harness()
        cue = h.cue()
        outcomes = []
        for now in (100.0, 101.5, 103.0, 104.9):
            h.now = now
            outcomes.append(cue.after_show(1, True))
        self.assertEqual(outcomes, ['played', 'repeat_while_lit', 'repeat_while_lit', 'repeat_while_lit'])
        self.assertEqual(h.played, [PATH])
        h.now = 106.9
        self.assertEqual(cue.after_show(1, True), 'played')
        self.assertEqual(len(h.played), 2)

    def test_lamp_dark_again_at_exact_duration_boundary(self):
        h = Harness()
        cue = h.cue()
        cue.after_show(1, True)
        h.now = 102.0
        self.assertEqual(cue.after_show(1, True), 'played')

    def test_new_battle_window_or_clock_reset_is_a_new_lighting(self):
        h = Harness()
        cue = h.cue()
        cue.after_show(1, True)
        h.now = 100.5
        self.assertEqual(cue.after_show(2, True), 'played')
        h.now = 50.0
        self.assertEqual(cue.after_show(2, True), 'played')
        self.assertEqual(len(h.played), 3)

    def test_hide_is_ignored_and_keeps_state(self):
        h = Harness()
        cue = h.cue()
        self.assertEqual(cue.after_show(1, False), 'ignored_not_show')
        self.assertEqual(cue.after_show(1, 1), 'ignored_not_show')
        self.assertEqual(h.played, [])
        self.assertIsNone(cue.lit_until)

    def test_hidden_window_is_silent_and_never_plays_late(self):
        h = Harness(visible='window_hidden')
        cue = h.cue()
        self.assertEqual(cue.after_show(1, True), 'window_hidden')
        h.visible = None
        h.now = 101.0
        self.assertEqual(cue.after_show(1, True), 'repeat_while_lit')
        self.assertEqual(h.played, [])

    def test_fmod_failure_is_recorded_not_reported_as_played(self):
        h = Harness()
        h.result = None
        self.assertEqual(h.cue().after_show(1, True), 'fmod_returned_none')
        self.assertEqual(h.records[-1][1]['outcome'], 'fmod_returned_none')

    def test_play_errors_propagate(self):
        h = Harness()

        def broken(path):
            raise RuntimeError('fmod')
        cue = cue_module.Cue('gun_intuition', broken, h.clock, 2.0, h.audible, h.record)
        self.assertRaises(RuntimeError, cue.after_show, 1, True)

    def test_constructor_and_clock_are_bounded(self):
        h = Harness()
        for duration in (0.0, -1.0, 61.0, 2):
            self.assertRaises(ValueError, h.cue, 'gun_intuition', duration)
        self.assertRaises(ValueError, h.cue, 'sixth_sense')
        self.assertRaises(TypeError, cue_module.Cue, 'gun_intuition', None, h.clock, 2.0,
                          h.audible, h.record)
        cue = h.cue()
        h.now = 5
        self.assertRaises(TypeError, cue.after_show, 1, True)


class PolicyTests(unittest.TestCase):
    def test_candidates_are_the_three_existing_notifications_fx_events(self):
        self.assertEqual(sorted(cue_module.CANDIDATES), ['enemy_sighted_for_team', 'gun_intuition',
                                                       'minimap_attention'])
        for name, path in cue_module.CANDIDATES.items():
            self.assertEqual(path, '/GUI/notifications_FX/' + name)
        for value in (None, '', 'sixth_sense', 'lamp', 'GUN_INTUITION', 1, True, []):
            self.assertRaises(ValueError, cue_module.validate_candidate, value)

    def test_prepare_option_is_off_by_default_and_needs_a_battle_mode(self):
        self.assertIsNone(cue_module.prepare_option(None))
        self.assertIsNone(cue_module.prepare_option(None, True, True))
        self.assertRaises(ValueError, cue_module.prepare_option, 'gun_intuition')
        self.assertRaises(ValueError, cue_module.prepare_option, 'unknown', True)
        option = cue_module.prepare_option('enemy_sighted_for_team', profile13=True)
        self.assertEqual(option['event_path'], '/GUI/notifications_FX/enemy_sighted_for_team')
        self.assertEqual(option['policy'], 'project_override_not_original_091')
        self.assertEqual(option['native_audio_check'], 'NOT_RUN')
        self.assertEqual(cue_module.prepare_option('minimap_attention', map_drive=True)['candidate'],
                         'minimap_attention')

    def test_runtime_settings_validation(self):
        self.assertIsNone(cue_module.validate_settings({}))
        self.assertRaises(ValueError, cue_module.validate_settings, {'sixth_sense_sound': None})
        self.assertRaises(ValueError, cue_module.validate_settings, {'sixth_sense_sound': 'gun_intuition'})
        self.assertRaises(ValueError, cue_module.validate_settings,
                          {'sixth_sense_sound': 'x', 'enable_profile13_battle': True})
        self.assertEqual(cue_module.validate_settings(
            {'sixth_sense_sound': 'gun_intuition', 'enable_profile13_battle': True}), 'gun_intuition')
        self.assertEqual(cue_module.validate_settings(
            {'sixth_sense_sound': 'gun_intuition', 'enable_map_drive': True}), 'gun_intuition')

    def test_duration_is_bounded_integer_milliseconds(self):
        self.assertEqual(cue_module.duration_seconds(2000), 2.0)
        for value in (0, -1, 60001, 2000.0, '2000', True, None):
            self.assertRaises(ValueError, cue_module.duration_seconds, value)

    def test_module_never_touches_notification_queues_or_scout_voice(self):
        names = set()
        consts = set()

        def walk(code):
            names.update(code.co_names)
            for const in code.co_consts:
                if isinstance(const, types.CodeType):
                    walk(const)
                elif isinstance(const, str):
                    consts.add(const)
        with open(cue_module.__file__.replace('.pyc', '.py'), 'rb') as stream:
            walk(compile(stream.read(), 'project_sixth_sense_sound.py', 'exec'))
        for forbidden in ('soundNotifications', 'complexSoundNotifications', 'IngameSoundNotifications',
                          'ComplexSoundNotifications', 'onScoutEvent', 'notifyEnemySpotted',
                          'updateVehicleMiscStatus', 'cancel', 'playSound', 'eval', 'exec'):
            self.assertNotIn(forbidden, names)
        self.assertIn('FMODplaySound', names)


class FakeEngine(object):
    MODULES = ('BigWorld', 'BattleReplay', 'SoundGroups', 'gui', 'gui.Scaleform', 'gui.Scaleform.Battle')

    def __init__(self):
        self.saved = dict((name, sys.modules.get(name)) for name in self.MODULES)
        self.calls = []
        calls = self.calls

        class Battle(object):
            def showSixthSenseIndicator(self, isShow):
                calls.append(('flash', isShow))
                return 'flash-result'

        class SoundGroupsClass(object):
            def FMODplaySound(self, event):
                calls.append(('fmod', event))
                return object()

        big = types.ModuleType('BigWorld')
        big.time = lambda: 10.0
        big.isWindowVisible = lambda: True
        replay = types.ModuleType('BattleReplay')
        replay.g_replayCtrl = types.ModuleType('ctrl')
        replay.g_replayCtrl.isPlaying = False
        replay.g_replayCtrl.isTimeWarpInProgress = False
        sound = types.ModuleType('SoundGroups')
        sound.SoundGroups = SoundGroupsClass
        sound.g_instance = SoundGroupsClass()
        gui = types.ModuleType('gui')
        gui.GUI_SETTINGS = types.ModuleType('settings')
        gui.GUI_SETTINGS.sixthSenseDuration = 2000
        scaleform = types.ModuleType('gui.Scaleform')
        battle_module = types.ModuleType('gui.Scaleform.Battle')
        battle_module.Battle = Battle
        gui.Scaleform = scaleform
        scaleform.Battle = battle_module
        for name, module in zip(self.MODULES, (big, replay, sound, gui, scaleform, battle_module)):
            sys.modules[name] = module
        self.Battle, self.big = Battle, big
        self.original = Battle.__dict__['showSixthSenseIndicator']

    def close(self):
        for name, module in self.saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.engine = FakeEngine()
        self.records = []
        self.contracts = []
        self.real_contract = cue_module._contract
        cue_module._installed = None

    def tearDown(self):
        cue_module._contract = self.real_contract
        cue_module._installed = None
        self.engine.close()

    def record(self, event, **fields):
        self.records.append((event, fields))

    def test_fake_methods_fail_the_pinned_717_contract_without_patching(self):
        self.assertRaises(RuntimeError, cue_module.install, self.record, 'gun_intuition')
        self.assertIs(self.engine.Battle.__dict__['showSixthSenseIndicator'], self.engine.original)
        self.assertIsNone(cue_module._installed)
        self.assertEqual(self.records, [])

    def test_original_runs_first_then_one_cue_and_restore_returns_original(self):
        cue_module._contract = lambda function, expected: self.contracts.append((function, expected[1]))
        cue_module.install(self.record, 'gun_intuition')
        self.assertEqual([name for _, name in self.contracts], ['showSixthSenseIndicator', 'FMODplaySound'])
        self.assertIs(self.contracts[0][0], self.engine.original)
        battle = self.engine.Battle()
        self.assertEqual(battle.showSixthSenseIndicator(True), 'flash-result')
        self.assertEqual(battle.showSixthSenseIndicator(True), 'flash-result')
        self.assertEqual(self.engine.calls, [('flash', True), ('fmod', PATH), ('flash', True)])
        installed = [f for e, f in self.records if e == 'project_sixth_sense_sound_installed'][0]
        self.assertTrue(installed['duration_is_historical'])
        self.assertFalse(installed['notification_queues_touched'])
        self.assertEqual([f['outcome'] for e, f in self.records if e == 'project_sixth_sense_sound'],
                         ['played', 'repeat_while_lit'])
        self.assertRaises(RuntimeError, cue_module.install, self.record, 'gun_intuition')
        self.assertTrue(cue_module.restore(self.record))
        self.assertIs(self.engine.Battle.__dict__['showSixthSenseIndicator'], self.engine.original)
        self.assertFalse(cue_module.restore(self.record))

    def test_hidden_window_and_errors_are_recorded(self):
        cue_module._contract = lambda function, expected: None
        self.engine.big.isWindowVisible = lambda: False
        cue_module.install(self.record, 'minimap_attention')
        battle = self.engine.Battle()
        battle.showSixthSenseIndicator(True)
        self.assertEqual(self.engine.calls, [('flash', True)])
        self.assertEqual(self.records[-1][1]['outcome'], 'window_hidden')
        sys.modules['SoundGroups'].g_instance = None
        self.engine.big.isWindowVisible = lambda: True
        self.engine.big.time = lambda: 50.0
        self.assertRaises(RuntimeError, battle.showSixthSenseIndicator, True)
        self.assertEqual(self.records[-1][0], 'project_sixth_sense_sound_error')

    def test_replaced_wrapper_is_not_silently_overwritten(self):
        cue_module._contract = lambda function, expected: None
        cue_module.install(self.record, 'gun_intuition')
        self.engine.Battle.showSixthSenseIndicator = lambda self, isShow: None
        self.assertRaises(RuntimeError, cue_module.restore, self.record)

    def test_unhistorical_duration_is_refused(self):
        cue_module._contract = lambda function, expected: None
        sys.modules['gui'].GUI_SETTINGS.sixthSenseDuration = 0
        self.assertRaises(ValueError, cue_module.install, self.record, 'gun_intuition')
        self.assertIs(self.engine.Battle.__dict__['showSixthSenseIndicator'], self.engine.original)


def _original_root():
    path = os.path.join(ROOT, 'config', 'project.local.json')
    if not os.path.isfile(path):
        return None
    with open(path, 'rb') as stream:
        data = json.loads(stream.read().decode('utf-8-sig'))
    root = data['paths']['original_client_root']
    return root if os.path.isdir(root) else None


class OriginalBytecodeTests(unittest.TestCase):
    """VERIFIED pins: read-only marshal of #717 .pyc; no client code is executed."""

    def _code(self, relative, qualified):
        if sys.version_info[:2] != (2, 7):
            self.skipTest('requires CPython 2.7 marshal for #717 bytecode')
        root = _original_root()
        if root is None:
            self.skipTest('original #717 client not configured (NOT_RUN)')
        with open(os.path.join(root, *relative.split('/')), 'rb') as stream:
            raw = stream.read(4 * 1024 * 1024)
        code = marshal.loads(raw[8:])
        for part in qualified.split('.'):
            code = [c for c in code.co_consts if isinstance(c, types.CodeType) and c.co_name == part][0]
        return hashlib.sha256(raw).hexdigest(), code

    def _check(self, relative, qualified, file_sha, contract):
        digest, code = self._code(relative, qualified)
        self.assertEqual(digest, file_sha)
        holder = types.FunctionType(code, {})
        cue_module._contract(holder, contract)

    def test_battle_show_sixth_sense_contract_matches_717(self):
        self._check('res/scripts/client/gui/Scaleform/Battle.pyc', 'Battle.showSixthSenseIndicator',
                    'aa43bc6b7e1f7ae9e2bba03fa527a9e6ce95a5d41ef23f26785b1490cd6f38de',
                    cue_module.BATTLE_CONTRACT)

    def test_sound_groups_fmod_contract_matches_717(self):
        self._check('res/scripts/client/SoundGroups.pyc', 'SoundGroups.FMODplaySound',
                    'e7cd3739489f6a44f77fb6b42f945e9625a18db04cb0b201f4a295de9366a09b',
                    cue_module.SOUND_CONTRACT)

    def test_contract_rejects_another_717_method(self):
        _, code = self._code('res/scripts/client/gui/Scaleform/Battle.pyc', 'Battle.afterCreate')
        self.assertRaises(RuntimeError, cue_module._contract, types.FunctionType(code, {}),
                          cue_module.BATTLE_CONTRACT)


if __name__ == '__main__':
    unittest.main()
