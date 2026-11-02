# -*- coding: utf-8 -*-
"""UI-02 client module: frame parser, policy, indicator subclass and the #717
contracts. Mocks prove the decisions, not what the client draws."""
import hashlib
import os
import struct
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'client_patch'))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import project_hit_indicator as m

ORIGINAL = 'C:/WoT_0.9.1_RU_0717_original/res/scripts/client/'


def hit(shot=7, yaw=1.5, damage=120, blocked=0xffff, verdict=1, flags=0, source=0, criticals=()):
    payload = struct.pack('<IfHHBBIB', shot, yaw, damage, blocked, verdict, flags, source, len(criticals))
    return b''.join((payload,) + tuple(struct.pack('<BB', *row) for row in criticals))


def frame(*records, **extra):
    body = b''.join(struct.pack('<BB', kind, len(data)) + data for kind, data in records)
    return b'BE' + struct.pack('<BHB', extra.get('version', 1), 3, extra.get('count', len(records))) + body


class ParserTests(unittest.TestCase):
    def test_hit_fields_match_the_server_layout(self):
        sequence, events = m.parse_frame(frame((1, hit(source=523, flags=3, criticals=((2, 5), (4, 0))))))
        self.assertEqual(sequence, 3)
        event = events[0]
        self.assertEqual((event['shot'], event['damage'], event['source'], event['verdict']), (7, 120, 523, 'pierced'))
        self.assertIsNone(event['blocked'])
        self.assertTrue(event['friendly'] and event['fatal'])
        self.assertEqual(event['criticals'], [(2, 5), (4, 0)])

    def test_server_fixture_bytes_decode(self):
        # The literal of the gateway test ui02_frame_layout_is_versioned...
        raw = (b'BE\x01\x03\x00\x01\x01\x17' + struct.pack('<I', 7) + struct.pack('<f', 1.5) + struct.pack('<H', 120)
               + b'\xff\xff\x01\x00' + struct.pack('<I', 152043525) + b'\x02\x02\x05\x04\x00')
        event = m.parse_frame(raw)[1][0]
        self.assertEqual(event['source'], 152043525)
        self.assertEqual(event['criticals'], [(2, 5), (4, 0)])

    def test_hello_and_unknown_kinds_of_later_cards(self):
        events = m.parse_frame(frame((0, b'\x01'), (9, b'later'), (1, hit())))[1]
        self.assertEqual([event['kind'] for event in events], ['hello', 'hit_received'])

    def test_damaged_frames_are_refused(self):
        good = frame((1, hit()))
        for bad in (b'', b'XX' + good[2:], good[:-1], good + b'\0', frame((1, hit()), version=2),
                    frame((1, hit()), count=2), frame(*[(1, hit())] * 9), b'BE' + b'\x01' * 300,
                    frame((1, hit(verdict=9))), frame((1, hit(flags=4))), frame((1, hit(yaw=9.0))),
                    frame((1, hit(yaw=float('nan')))), frame((1, hit(damage=0xffff))),
                    frame((1, hit(criticals=((9, 0),)))), frame((1, hit(criticals=((1, 0),) * 5))),
                    frame((1, hit() + b'\0')), frame((1, hit()[:10])), 'text', None):
            with self.assertRaises(ValueError):
                m.parse_frame(bad)


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.now, self.rows = 100.0, []
        self.policy = m.Policy({'view': 'extended'}, lambda name, **fields: self.rows.append(name), lambda: self.now)

    def event(self, **fields):
        event = m.parse_frame(frame((1, hit(**fields))))[1][0]
        self.policy.remember(event)
        return event

    def test_a_hidden_source_shows_no_name_and_no_invented_number(self):
        event = self.event(damage=0, verdict=2)
        args = self.policy.show_args(event, '', '', 1000)
        self.assertEqual(args[:3], [m.GREY, '- -', ''])

    def test_damage_blocked_critical_friendly_colours(self):
        self.assertEqual(self.policy.show_args(self.event(), u'Т-34', '', 1000)[:4], [m.RED, '120', u'Т-34', m.WHITE])
        self.assertEqual(self.policy.show_args(self.event(damage=0, blocked=400, verdict=2), 'M103', '', 1000)[:2],
                         [m.GREY, '400'])
        args = self.policy.show_args(self.event(criticals=((1, 3),)), 'T57', u'Двигатель', 1000)
        self.assertEqual((args[0], args[4]), (m.ORANGE, u'Двигатель'))
        self.assertEqual(self.policy.show_args(self.event(damage=0, verdict=2, flags=1), 'T110E5', '', 1000)[:4],
                         [m.GREY, '- -', 'T110E5', m.GREEN])

    def test_options_reach_the_arguments(self):
        event = self.event(criticals=((1, 3),))
        self.policy.apply_options({'show_critical': False, 'show_vehicle': False, 'show_damage': False,
                                   'dynamic': False, 'animate': False})
        self.assertEqual(self.policy.show_args(event, 'T34', 'note', 1000), [m.RED, '', '', m.WHITE, '', 1.0, False, '', ''])

    def test_dynamic_scale_grows_with_damage_and_is_bounded(self):
        small = self.policy.show_args(self.event(damage=10), '', '', 1000)[5]
        large = self.policy.show_args(self.event(damage=2000), '', '', 1000)[5]
        self.assertTrue(1.0 < small < large)
        self.assertAlmostEqual(large, 1.6)

    def test_facts_expire_and_stay_bounded(self):
        self.event(yaw=1.0)
        self.assertIsNotNone(self.policy.facts_for(1.0))
        self.assertIsNone(self.policy.facts_for(2.0))
        self.now += m.FACTS_LIFETIME
        self.assertIsNone(self.policy.facts_for(1.0))
        for index in range(100):
            self.event(yaw=index / 100.0)
        self.assertLessEqual(len(self.policy.facts), m.MAX_FACTS)

    def test_friendly_fire_is_hidden_only_by_the_option(self):
        self.event(yaw=1.0, flags=1)
        self.event(yaw=2.0)
        self.assertFalse(self.policy.suppressed(1.0))
        self.policy.apply_options({'show_friendly': False})
        self.assertTrue(self.policy.suppressed(1.0))
        self.assertFalse(self.policy.suppressed(2.0))
        self.assertFalse(self.policy.suppressed(3.0))

    def test_splash_alone_asks_for_the_native_indicator(self):
        shown = []
        self.policy.show_splash = shown.append
        self.event(yaw=1.0, verdict=4)
        self.event(yaw=2.0, verdict=1)
        self.assertEqual(shown, [1.0])

    def test_bad_frames_are_counted_not_raised(self):
        self.policy.on_frame(b'garbage')
        self.assertEqual(self.policy.bad_frames, 1)
        self.policy.on_frame(frame((0, b'\x01')))
        self.assertTrue(self.policy.acknowledged)
        self.policy.reset()
        self.assertFalse(self.policy.acknowledged)

    def test_movie_follows_the_view_and_a_failure(self):
        self.assertEqual(self.policy.movie(), m.EXTENDED_MOVIE)
        self.policy.failed = True
        self.assertIsNone(self.policy.movie())
        self.policy.failed = False
        self.policy.apply_options({'view': 'standard'})
        self.assertIsNone(self.policy.movie())


class Native(object):
    """The shape of #717 _DamageIndicator as the subclass uses it."""
    _DamageIndicator__SWF_FILE_NAME = 'DamageIndicator.swf'
    refuse = None

    def __init__(self):
        self.calls, self.movie = [], self._DamageIndicator__SWF_FILE_NAME
        if self.movie == Native.refuse:
            raise RuntimeError('movie not loaded')

    def setup(self, gYaw, offset):
        self.calls.append(('setup', gYaw, offset))

    def call(self, methodName, args=None):
        self.calls.append((methodName, args))


class IndicatorTests(unittest.TestCase):
    def setUp(self):
        Native.refuse = None
        self.rows = []
        self.policy = m.Policy({'view': 'extended'}, lambda name, **fields: self.rows.append(name), lambda: 1.0)
        self.cls = m.indicator_class(Native, self.policy, lambda event: ['facts'], self.policy.record)

    def native_flow(self, yaw=1.5):
        indicator = self.cls()
        indicator.setup(yaw, (1, 2))
        indicator.call(m.NATIVE_CALLBACK, [True, 0])
        return indicator

    def test_extended_with_facts_calls_the_project_callback_after_the_native_one(self):
        self.policy.on_frame(frame((1, hit())))
        indicator = self.native_flow()
        self.assertEqual(indicator.movie, m.EXTENDED_MOVIE)
        self.assertEqual(indicator.calls[-2:], [(m.NATIVE_CALLBACK, [True, 0]), (m.CALLBACK, ['facts'])])

    def test_without_facts_or_in_standard_the_calls_are_native(self):
        indicator = self.native_flow()
        self.assertEqual(indicator.calls, [('setup', 1.5, (1, 2)), (m.NATIVE_CALLBACK, [True, 0])])
        self.policy.on_frame(frame((1, hit())))
        self.policy.apply_options({'view': 'standard'})
        indicator = self.native_flow()
        self.assertEqual(indicator.movie, 'DamageIndicator.swf')
        self.assertEqual(indicator.calls, [('setup', 1.5, (1, 2)), (m.NATIVE_CALLBACK, [True, 0])])

    def test_a_movie_that_does_not_load_leaves_the_native_arc(self):
        Native.refuse = m.EXTENDED_MOVIE
        self.policy.on_frame(frame((1, hit())))
        indicator = self.native_flow()
        self.assertEqual(indicator.movie, 'DamageIndicator.swf')
        self.assertEqual(indicator.calls[-1], (m.NATIVE_CALLBACK, [True, 0]))
        self.assertTrue(self.policy.failed)
        self.assertIn(m.EVENT + '_movie_failed', self.rows)

    def test_a_failing_facts_lookup_keeps_the_native_call(self):
        def broken(event):
            raise KeyError('roster')
        cls = m.indicator_class(Native, self.policy, broken, self.policy.record)
        self.policy.on_frame(frame((1, hit())))
        indicator = cls()
        indicator.setup(1.5, (1, 2))
        indicator.call(m.NATIVE_CALLBACK, [True, 0])
        self.assertEqual(indicator.calls[-1], (m.NATIVE_CALLBACK, [True, 0]))
        self.assertTrue(self.policy.failed)


class NoteTests(unittest.TestCase):
    class Extra(object):
        def __init__(self, name):
            self.name = name

    class Descriptor(object):
        pass

    def note(self, *critical):
        descriptor = self.Descriptor()
        descriptor.extras = [self.Extra('engineHealth'), self.Extra('leftTrackHealth'), self.Extra('driverHealth')]
        return m._note({'criticals': [critical]}, descriptor, lambda key: key + '. Tail.')

    def test_native_keys(self):
        self.assertEqual(self.note(1, 0), '#ingame_gui:damage_panel/devices/engine/critical')
        self.assertEqual(self.note(2, 1), '#ingame_gui:damage_panel/devices/track/destroyed')
        self.assertTrue(self.note(3, 2).startswith('#ingame_gui:damage_panel/crew/driver/destroyed'))
        self.assertTrue(self.note(4, 0).startswith('#ingame_gui:player_messages/tank_in_fire'))


class ArtStageTests(unittest.TestCase):
    class Native(object):
        def __init__(self):
            self.sizes = getattr(self, '_DamageIndicator__FLASH_SIZE', (680, 680))

        def setup(self, gYaw, offset):
            pass

        def call(self, methodName, args=None):
            pass

    def indicator(self, art=False):
        rules = m.Policy(dict(m.default_options(), view='extended'), lambda *a, **k: None, lambda: 0.0, art)
        return m.indicator_class(self.Native, rules, lambda event: [], lambda *a, **k: None)()

    def test_only_a_movie_with_art_gets_the_large_component(self):
        self.assertEqual(self.indicator().sizes, (680, 680))
        self.assertEqual(self.indicator(art=True).sizes, m.ART_FLASH_SIZE)

    def test_art_setting_is_a_true_beside_the_indicator(self):
        good = {'hit_indicator': m.prepare_settings('extended'), 'enable_profile13_battle': True}
        self.assertTrue(m.validate_settings(dict(good, hit_indicator_art=True)))
        for bad in (dict(good, hit_indicator_art=False), {'hit_indicator_art': True}):
            self.assertRaises(ValueError, m.validate_settings, bad)


class IconTests(unittest.TestCase):
    def setUp(self):
        self.policy = m.Policy(dict(m.default_options(), view='extended'), lambda *a, **k: None, lambda: 0.0)

    def icon(self, name, kind=2):
        descriptor = NoteTests.Descriptor()
        descriptor.extras = [NoteTests.Extra(name)]
        return m._module_icon({'criticals': [(kind, 0)]}, descriptor)

    def test_modules_and_crew_name_their_sprite(self):
        for name, sprite in (('engineHealth', 'engineCircle'), ('leftTrackHealth', 'tracksCircle'),
                             ('rightTrackHealth', 'tracksCircle'), ('surveyingDeviceHealth', 'triplexCircle'),
                             ('turretRotatorHealth', 'turretCircle'), ('gunner1Health', 'gunnerCircle'),
                             ('loader2Health', 'reloaderCircle'), ('radioman1Health', 'radiomanCircle')):
            self.assertEqual(self.icon(name), sprite)

    def test_fire_and_unknown_extra_have_no_sprite(self):
        self.assertEqual(self.icon('engineHealth', 4), '')
        self.assertEqual(self.icon('fire'), '')

    def test_vehicle_class_and_ally_variant(self):
        self.assertEqual(m._vehicle_icon(frozenset(('heavyTank', 'premium')), False), 'heavyTank')
        self.assertEqual(m._vehicle_icon(frozenset(('AT-SPG',)), True), 'ally_AT-SPG')
        self.assertEqual(m._vehicle_icon(frozenset(('premium',)), True), '')

    def test_icon_stands_in_only_without_damage(self):
        event = {'shot': 1, 'yaw': 0.5, 'damage': 0, 'blocked': None, 'verdict': 'not_pierced', 'friendly': False,
                 'fatal': False, 'source': 7, 'criticals': [(1, 0)]}
        self.assertEqual(self.policy.show_args(event, 'T34', 'n', 1000, 'engineCircle', 'heavyTank')[7:],
                         ['engineCircle', 'heavyTank'])
        event['damage'] = 100
        self.assertEqual(self.policy.show_args(event, 'T34', 'n', 1000, 'engineCircle', 'heavyTank')[7], '')
        self.policy.apply_options({'show_critical': False})
        event['damage'] = 0
        self.assertEqual(self.policy.show_args(event, 'T34', 'n', 1000, 'engineCircle', 'heavyTank')[7], '')

    def test_class_icon_follows_the_name(self):
        event = {'shot': 1, 'yaw': 0.5, 'damage': 10, 'blocked': None, 'verdict': 'pierced', 'friendly': False,
                 'fatal': False, 'source': 0, 'criticals': []}
        self.assertEqual(self.policy.show_args(event, '', '', 1000, '', 'heavyTank')[8], '')
        self.policy.apply_options({'show_vehicle': False})
        self.assertEqual(self.policy.show_args(event, 'T34', '', 1000, '', 'heavyTank')[8], '')


class SettingsTests(unittest.TestCase):
    def test_explicit_and_profile13_only(self):
        self.assertFalse(m.validate_settings({}))
        good = {'hit_indicator': m.prepare_settings('extended'), 'enable_profile13_battle': True}
        self.assertTrue(m.validate_settings(good))
        for bad in ({'hit_indicator': None}, {'hit_indicator': good['hit_indicator']},
                    {'hit_indicator': {'view': 'modern'}, 'enable_profile13_battle': True},
                    {'hit_indicator': {'nope': True}, 'enable_profile13_battle': True},
                    {'hit_indicator': {'animate': 1}, 'enable_profile13_battle': True},
                    {'hit_indicator': True, 'enable_profile13_battle': True}):
            with self.assertRaises(ValueError):
                m.validate_settings(bad)

    @unittest.skipUnless(sys.version_info[0] == 3, 'prepare is a Python 3 tool')
    def test_prepare_lists_the_flag(self):
        env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, 'tools'))
        result = subprocess.run([sys.executable, '-B', os.path.join(ROOT, 'tools/interactive_client.py'),
                                 'prepare', '--help'], env=env, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertIn(b'--hit-indicator', result.stdout)

    def test_no_running_policy_before_install(self):
        self.assertIsNone(m.policy())

    def test_every_option_has_a_default_inside_its_values(self):
        for key, allowed, default in m.OPTION_SCHEMA:
            self.assertIn(default, allowed)


@unittest.skipUnless(os.path.isfile(ORIGINAL + 'clientarena.pyc') and sys.version_info[0] == 3, 'original client absent')
class ContractTests(unittest.TestCase):
    def test_pinned_records_equal_the_original_bytecode(self):
        import py27_static as static
        rows = {}
        for name in ('clientarena.pyc', 'avatarinputhandler/aims.pyc'):
            with open(ORIGINAL + name, 'rb') as source:
                for key, code in static.records(static.parse_pyc(source.read())):
                    rows[key] = code
        for key, contract in (('<module>.ClientArena.update', m.ARENA_CONTRACT), ('<module>.Aim.showHit', m.SHOW_HIT_CONTRACT),
                              ('<module>._DamageIndicatorCtrl.add', m.ADD_CONTRACT),
                              ('<module>._DamageIndicator.__init__', m.INIT_CONTRACT),
                              ('<module>._DamageIndicator.setup', m.SETUP_CONTRACT)):
            code = rows[key]
            self.assertEqual(static.text(code['filename']), contract[0])
            self.assertEqual(code['firstlineno'], contract[2])
            self.assertEqual(hashlib.sha256(code['code']).hexdigest(), contract[4])

    def test_server_constants_match(self):
        path = os.path.join(ROOT, 'server/gateway/src/shared/battle_events.rs')
        with open(path, encoding='utf-8') as source:
            text = source.read()
        for fragment in ('ARENA_UPDATE_TYPE:u8=%d;' % m.ARENA_UPDATE_TYPE, 'VERSION:u8=%d;' % m.VERSION,
                         'b"%s"' % m.FEATURE, 'MAX_FRAME_BYTES:usize=%d;' % m.MAX_FRAME_BYTES,
                         'MAX_EVENTS_PER_FRAME:usize=%d;' % m.MAX_EVENTS, 'MAX_CRITICALS:usize=%d;' % m.MAX_CRITICALS):
            self.assertIn(fragment, text)



class ShellRecordTests(unittest.TestCase):
    """UI-03b: the server's battle_events::KIND_SHELL record after a hit."""

    @staticmethod
    def frame(*records):
        body = b''.join(struct.pack('<BB', kind, len(data)) + data for kind, data in records)
        return b'BE' + struct.pack('<BHB', m.VERSION, 1, len(records)) + body

    def test_the_shell_of_a_hit_with_its_family_and_gold_flag(self):
        events = m.parse_frame(self.frame((m.KIND_SHELL, struct.pack('<IB', 7, 0x13)),
                                          (m.KIND_SHELL, struct.pack('<IB', 8, 4))))[1]
        self.assertEqual(events, [{'kind': 'shell', 'shot': 7, 'family': 'hollow_charge', 'premium': True},
                                  {'kind': 'shell', 'shot': 8, 'family': 'high_explosive', 'premium': False}])

    def test_a_family_of_a_later_server_is_skipped_a_broken_record_refused(self):
        self.assertEqual(m.parse_frame(self.frame((m.KIND_SHELL, struct.pack('<IB', 7, 9))))[1], [])
        self.assertEqual(m.parse_frame(self.frame((m.KIND_SHELL, struct.pack('<IB', 7, 0x41))))[1], [])
        with self.assertRaises(ValueError):
            m.parse_frame(self.frame((m.KIND_SHELL, b'\x01\x00\x00\x00')))

    @unittest.skipUnless(sys.version_info[0] == 3, 'static checks run on Python 3')
    def test_server_constants_match(self):
        path = os.path.join(ROOT, 'server/gateway/src/shared/battle_events.rs')
        with open(path, encoding='utf-8') as source:
            text = source.read()
        self.assertIn('const KIND_SHELL:u8=%d;' % m.KIND_SHELL, text)
        self.assertIn('const SHELL_PREMIUM:u8=0x%x;' % m.SHELL_PREMIUM, text)
        self.assertIn('ArmorPiercing=1,ArmorPiercingCr=2,HollowCharge=3,HighExplosive=4', text)


if __name__ == '__main__':
    unittest.main()
