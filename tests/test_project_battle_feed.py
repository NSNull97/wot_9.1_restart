# -*- coding: utf-8 -*-
"""UI-03 client module: channel additions, row rules, widget life cycle and the
#717 contracts. Mocks prove the decisions, not what the client draws."""
import hashlib
import os
import re
import struct
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'client_patch'))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import project_battle_feed as m
import project_hit_indicator as channel

ORIGINAL = 'C:/WoT_0.9.1_RU_0717_original/res/scripts/client/'
NO_VALUE = 0xffff


def feed_record(kind, value=NO_VALUE, vehicle=0):
    return (2, struct.pack('<BHI', kind, value, vehicle))


def hit_record(damage=120, blocked=NO_VALUE, verdict=1, source=0, criticals=()):
    payload = struct.pack('<IfHHBBIB', 7, 1.5, damage, blocked, verdict, 0, source, len(criticals))
    return (1, b''.join((payload,) + tuple(struct.pack('<BB', *row) for row in criticals)))


def frame(sequence, *records):
    body = b''.join(struct.pack('<BB', kind, len(data)) + data for kind, data in records)
    return b'BE' + struct.pack('<BHB', 1, sequence, len(records)) + body


def event(*record):
    return channel.parse_frame(frame(0, feed_record(*record)))[1][0]


def hit(**fields):
    return channel.parse_frame(frame(0, hit_record(**fields)))[1][0]



class WidgetSizeTests(unittest.TestCase):
    def test_flash_size_is_the_tuple_of_floats_gui_flash_takes(self):
        class Holder(object):
            pass
        class Base(object):
            def __init__(self, movie):
                self.component, self.movie = Holder(), Holder()
                self.component.position = Holder()
        size = m.widget_class(Base, 0.5, lambda: (1920, 1080))().flashSize
        self.assertIs(type(size), tuple)
        self.assertEqual([type(value) for value in size], [float, float])
        self.assertEqual(size, (1920.0, 1080.0))

    def test_a_new_resolution_resizes_the_component_like_native_aim(self):
        class Holder(object):
            pass
        class Base(object):
            def __init__(self, movie):
                self.component, self.movie = Holder(), Holder()
                self.component.position = Holder()
        screen = [(1920, 1080)]
        widget = m.widget_class(Base, 0.5, lambda: screen[0])()
        screen[0] = (1280, 720)
        widget.fit()
        self.assertEqual(widget.component.size, (1280.0, 720.0))


class ChannelTests(unittest.TestCase):
    def setUp(self):
        self.rows, self.seen = [], []
        self.policy = channel.Policy({'view': 'standard'}, lambda name, **fields: self.rows.append(name), lambda: 1.0)
        self.policy.subscribe(self.seen.append)

    def test_feed_record_matches_the_server_layout(self):
        # The literal of the gateway test ui03_feed_record_is_seven_bytes...
        raw = b'BE\x01\x01\x00\x02\x02\x07\x01' + struct.pack('<HI', 320, 152043525) + b'\x02\x07\x04\xff\xff\0\0\0\0'
        rows = channel.parse_frame(raw)[1]
        self.assertEqual(rows[0], {'kind': 'feed', 'feed': 1, 'value': 320, 'vehicle': 152043525})
        self.assertEqual(rows[1], {'kind': 'feed', 'feed': 4, 'value': None, 'vehicle': 0})

    def test_a_feed_kind_of_a_later_server_is_skipped_a_broken_record_refused(self):
        self.assertEqual(channel.parse_frame(frame(0, feed_record(channel.MAX_FEED_KIND + 1), feed_record(1)))[1],
                         [{'kind': 'feed', 'feed': 1, 'value': None, 'vehicle': 0}])
        with self.assertRaises(ValueError):
            channel.parse_frame(frame(0, (2, b'\x01\x00')))

    def test_a_repeated_or_older_frame_is_counted_and_not_shown(self):
        self.policy.on_frame(frame(5, feed_record(1, 10)))
        self.policy.on_frame(frame(5, feed_record(1, 10)))
        self.policy.on_frame(frame(4, feed_record(1, 10)))
        self.policy.on_frame(frame(6, feed_record(1, 11)))
        self.assertEqual([row['value'] for row in self.seen], [10, 11])
        self.assertEqual(self.policy.repeated_frames, 2)

    def test_the_sequence_wraps(self):
        self.policy.on_frame(frame(0xffff, feed_record(1, 1)))
        self.policy.on_frame(frame(0, feed_record(1, 2)))
        self.assertEqual(len(self.seen), 2)

    def test_a_hello_reply_starts_the_numbering_of_a_new_channel(self):
        self.policy.on_frame(frame(90, feed_record(1, 1)))
        self.policy.on_frame(frame(0, (0, b'\x01')))
        self.policy.on_frame(frame(1, feed_record(1, 2)))
        self.assertEqual(len(self.seen), 2)
        self.assertEqual(self.policy.repeated_frames, 0)

    def test_a_battle_reset_starts_the_numbering_too(self):
        self.policy.on_frame(frame(90, feed_record(1, 1)))
        self.policy.reset()
        self.policy.on_frame(frame(0, feed_record(1, 2)))
        self.assertEqual(len(self.seen), 2)

    def test_a_failing_widget_never_reaches_the_native_callback_and_leaves(self):
        calls = []

        def broken(row):
            calls.append(row)
            raise RuntimeError('widget')

        self.policy.subscribe(broken)
        self.policy.on_frame(frame(1, feed_record(1, 1)))
        self.policy.on_frame(frame(2, feed_record(1, 2)))
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(self.seen), 2)
        self.assertIn(channel.EVENT + '_listener_failed', self.rows)

    def test_hits_still_reach_the_indicator_and_the_listeners(self):
        self.policy.on_frame(frame(1, hit_record()))
        self.assertEqual(self.seen[0]['kind'], 'hit_received')
        self.assertIsNotNone(self.policy.facts_for(1.5))


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class FeedTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.feed = m.Feed({}, self.clock, {523: 'T-34'}.get, {523: 'whiteIconMediumTank16x16'}.get)

    def row(self, index=0):
        return self.feed.render_args()[index * 8:index * 8 + 8]

    def test_every_wire_kind_has_a_row_and_a_label(self):
        for kind, key in m.FEED_ROWS.items():
            self.assertIn(key, m.ROWS_TABLE, kind)
        self.assertEqual(sorted(m.FEED_ROWS), list(range(1, channel.MAX_FEED_KIND + 1)))

    def test_dealt_damage_with_name(self):
        self.assertTrue(self.feed.add(event(1, 320, 523)))
        self.assertEqual(self.row(), [m.GREEN, '320', m.CROSS, 'Урон выстрелом', 'T-34', 5000,
                                      'ribbonsDamage', 'whiteIconMediumTank16x16'])

    def test_a_withheld_amount_stays_visibly_absent(self):
        self.feed.add(event(1))
        self.assertEqual(self.row()[:5], [m.GREEN, '- -', m.CROSS, 'Урон выстрелом', ''])

    def test_received_blocked_and_critical_rows_of_a_hit(self):
        self.feed.add(hit(damage=90, source=523, criticals=((1, 3), (4, 0))))
        self.assertEqual(self.row(0)[:5], [m.ORANGE, 'x2', m.GEAR, 'Критическое повреждение', 'T-34'])
        self.assertEqual(self.row(1)[:5], [m.RED, '90', m.CROSS, 'Получен урон', 'T-34'])

    def test_blocked_shows_the_nominal_or_a_dash_for_a_hidden_shooter(self):
        self.feed.add(hit(damage=0, blocked=400, verdict=2, source=523))
        self.assertEqual(self.row()[:2], [m.GREY, '400'])
        self.feed.add(hit(damage=0, verdict=3))
        self.assertEqual(self.row()[:5], [m.GREY, '- -', m.SHIELD, 'Удар сдержан', ''])

    def test_an_unknown_verdict_without_damage_is_no_row(self):
        self.assertFalse(self.feed.add(hit(damage=0, verdict=0)))

    def test_a_repeat_merges_and_moves_up_only_when_the_vehicle_is_the_same(self):
        self.feed.add(event(1, 100, 523))
        self.feed.add(event(1, 50, 600))
        self.feed.add(event(1, 20, 523))
        self.assertEqual(self.row(0)[1], '120')
        self.assertEqual(self.row(1)[1], '50')
        self.feed.add(event(4))
        self.feed.add(event(4))
        self.assertEqual(self.row(0)[:3], [m.GREEN, 'x2', m.EYE])

    def test_points_add_up_and_a_fire_row_joins_ignition_and_damage(self):
        self.feed.add(event(5, 1))
        self.feed.add(event(5, 2))
        self.assertEqual(self.row()[1], '3')
        self.feed.add(event(7, NO_VALUE, 523))
        self.assertEqual(self.row()[:4], [m.GREEN, '', m.FLAME, 'Поджог'])
        self.feed.add(event(8, 30, 523))
        self.assertEqual(self.row()[1], 'x2')

    def test_only_three_rows_stay_and_the_newest_is_on_top(self):
        for vehicle in (1, 2, 3, 4):
            self.feed.add(event(1, vehicle, vehicle))
        self.assertEqual([row['value'] for row in self.feed.rows], [4, 3, 2])

    def test_rows_expire_and_the_rest_stay(self):
        self.feed.add(event(1, 1, 1))
        self.clock.now += 4.0
        self.feed.add(event(1, 2, 2))
        self.assertEqual(self.row(1)[5], 1000)
        self.clock.now += 1.0
        self.assertTrue(self.feed.expire())
        self.assertEqual(len(self.feed.rows), 1)
        self.assertFalse(self.feed.expire())
        self.assertEqual(self.feed.render_args()[8:], list(m.EMPTY_ROW) * 2)

    def test_a_merge_refreshes_the_life_of_the_row(self):
        self.feed.add(event(1, 1, 1))
        self.clock.now += 4.0
        self.feed.add(event(1, 1, 1))
        self.clock.now += 4.0
        self.assertFalse(self.feed.expire())

    def test_options_for_ui05(self):
        self.feed.apply_options({'show_label': False, 'show_vehicle': False})
        self.feed.add(event(1, 1, 523))
        self.assertEqual(self.row()[3:5], ['', ''])
        self.assertEqual(self.row()[7], '', 'the class icon goes with the name')
        self.feed.apply_options({'shot': False})
        self.assertFalse(self.feed.add(event(1, 1, 523)))
        self.feed.apply_options({'shot': True, 'enabled': False})
        self.assertFalse(self.feed.add(event(1, 1, 523)))
        with self.assertRaises(ValueError):
            self.feed.apply_options({'unknown': True})

    def test_class_icon_by_the_native_tags(self):
        self.assertEqual(m.class_icon(frozenset(['ussr', 'AT-SPG'])), 'whiteIconAt-SPG16x16')
        self.assertEqual(m.class_icon(frozenset(['mediumTank'])), 'whiteIconMediumTank16x16')
        self.assertEqual(m.class_icon(frozenset(['observer'])), '')

    def test_origin_keeps_the_rows_under_the_centre_and_above_the_history(self):
        self.assertEqual(m.origin((1920, 1080)), (960, 710))
        self.assertEqual(m.origin((1024, 768)), (512, 427))

    def test_arguments_always_cover_three_rows(self):
        self.assertEqual(self.feed.render_args(), list(m.EMPTY_ROW) * 3)


class Component:
    class Position:
        z = 0

    def __init__(self):
        self.position, self.visible = self.Position(), None


class Widget:
    def __init__(self):
        self.component, self.calls, self.states, self.closed = Component(), [], [], 0

    def active(self, state):
        self.states.append(state)

    def call(self, name, args):
        self.calls.append((name, args))

    def fit(self):
        self.fits = getattr(self, 'fits', 0) + 1

    def close(self):
        self.closed += 1


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.clock, self.made, self.records, self.timers, self.cancelled = Clock(), [], [], [], []
        self.screen = (1920, 1080)
        self.runtime = m.Runtime(m.Feed({}, self.clock, lambda vehicle: '', lambda vehicle: ''), self.make,
                                 lambda: self.screen, self.schedule, self.cancelled.append,
                                 lambda name, **fields: self.records.append(name))

    def make(self):
        self.made.append(Widget())
        return self.made[-1]

    def schedule(self, delay, callback):
        self.timers.append(callback)
        return len(self.timers)

    def test_the_widget_appears_on_the_first_row_only(self):
        self.runtime.ready()
        self.assertEqual(self.made, [])
        self.runtime.on_event(event(1, 1, 1))
        self.assertEqual(self.made[0].states, [True])
        self.assertEqual(self.made[0].calls[0], (m.PLACE_CALLBACK, [960, 710]))
        self.assertEqual(self.made[0].calls[1][0], m.CALLBACK)
        self.assertEqual(len(self.made[0].calls[1][1]), 24)

    def test_a_new_resolution_moves_a_live_widget(self):
        self.runtime.resize()
        self.runtime.on_event(event(1, 1, 1))
        self.screen = (1280, 720)
        self.runtime.resize()
        self.assertEqual(self.made[0].fits, 1)
        self.assertEqual(self.made[0].calls[-1], (m.PLACE_CALLBACK, [640, 379]))

    def test_a_failing_resize_switches_the_feed_off(self):
        self.runtime.on_event(event(1, 1, 1))
        self.made[0].fit = None
        self.runtime.resize()
        self.assertTrue(self.runtime.failed)
        self.assertEqual(self.made[0].closed, 1)

    def test_an_invisible_row_does_not_create_the_widget(self):
        self.runtime.feed.apply_options({'enabled': False})
        self.runtime.on_event(event(1, 1, 1))
        self.assertEqual(self.made, [])

    def test_expiry_redraws_and_the_timer_stops_with_the_last_row(self):
        self.runtime.on_event(event(1, 1, 1))
        self.clock.now += m.LIFETIME
        self.timers.pop()()
        self.assertEqual(self.made[0].calls[-1][1], list(m.EMPTY_ROW) * 3)
        self.assertEqual(self.timers, [])
        self.assertIsNone(self.runtime.timer)

    def test_a_new_battle_closes_the_old_widget_and_clears_the_rows(self):
        self.runtime.on_event(event(1, 1, 1))
        self.runtime.ready()
        self.assertEqual(self.made[0].closed, 1)
        self.assertEqual(self.runtime.feed.rows, [])
        self.assertEqual(self.cancelled, [1])

    def test_show_all_hides_a_live_and_a_later_widget(self):
        self.runtime.show_all(False)
        self.runtime.on_event(event(1, 1, 1))
        self.assertIs(self.made[0].component.visible, False)
        self.runtime.show_all(True)
        self.assertIs(self.made[0].component.visible, True)

    def test_a_movie_that_does_not_load_switches_the_feed_off_quietly(self):
        def failing():
            raise RuntimeError('no movie')
        self.runtime.make_widget = failing
        self.runtime.on_event(event(1, 1, 1))
        self.runtime.on_event(event(1, 1, 1))
        self.assertEqual(self.records.count(m.EVENT + '_failed'), 1)

    def test_a_failing_call_closes_the_widget(self):
        self.runtime.on_event(event(1, 1, 1))

        def failing(name, args):
            raise RuntimeError('movie gone')
        self.made[0].call = failing
        self.runtime.on_event(event(1, 2, 2))
        self.assertEqual(self.made[0].closed, 1)
        self.assertIsNone(self.runtime.widget)


class SettingsTests(unittest.TestCase):
    def test_explicit_and_only_with_the_channel(self):
        self.assertFalse(m.validate_settings({}, 'hit_indicator'))
        good = {'battle_feed': m.prepare_settings('labels'), 'hit_indicator': {'view': 'standard'}}
        self.assertTrue(m.validate_settings(good, 'hit_indicator'))
        for bad in ({'battle_feed': None}, {'battle_feed': good['battle_feed']},
                    {'battle_feed': {'nope': True}, 'hit_indicator': {}},
                    {'battle_feed': {'shot': 1}, 'hit_indicator': {}},
                    {'battle_feed': True, 'hit_indicator': {}}):
            with self.assertRaises(ValueError):
                m.validate_settings(bad, 'hit_indicator')

    def test_views_of_the_flag(self):
        self.assertIs(m.prepare_settings('labels')['show_label'], True)
        self.assertIs(m.prepare_settings('icons')['show_label'], False)
        with self.assertRaises(ValueError):
            m.prepare_settings('modern')

    def test_no_running_feed_before_install(self):
        self.assertIsNone(m.policy())

    def test_install_needs_the_channel(self):
        with self.assertRaises(RuntimeError):
            m.install(lambda name, **fields: None, {}, None)

    def test_every_option_has_a_default_inside_its_values(self):
        for key, allowed, default in m.OPTION_SCHEMA:
            self.assertIn(default, allowed)
        self.assertEqual(set(m.ROWS_TABLE) - set(row[0] for row in m.OPTION_SCHEMA), set())

    @unittest.skipUnless(sys.version_info[0] == 3, 'prepare is a Python 3 tool')
    def test_prepare_lists_the_flag_and_needs_the_channel(self):
        env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, 'tools'))
        result = subprocess.run([sys.executable, '-B', os.path.join(ROOT, 'tools/interactive_client.py'),
                                 'prepare', '--help'], env=env, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertIn(b'--battle-feed', result.stdout)


@unittest.skipUnless(sys.version_info[0] == 3, 'static checks run on Python 3')
class ContractTests(unittest.TestCase):
    @unittest.skipUnless(os.path.isfile(ORIGINAL + 'gui/scaleform/flash.pyc'), 'original client absent')
    def test_pinned_records_equal_the_original_bytecode(self):
        import py27_static as static
        rows = {}
        for name in ('gui/scaleform/flash.pyc', 'gui/scaleform/battle.pyc'):
            with open(ORIGINAL + name, 'rb') as source:
                for key, code in static.records(static.parse_pyc(source.read())):
                    rows[key] = code
        for name, line, args, digest in m.FLASH_CONTRACTS:
            code = rows['<module>.Flash.' + name]
            self.assertEqual(static.text(code['filename']), m.FLASH_FILE)
            self.assertEqual(code['firstlineno'], line)
            self.assertEqual(hashlib.sha256(code['code']).hexdigest(), digest)
        code = rows['<module>.Battle.showAll']
        self.assertEqual(static.text(code['filename']), m.SHOW_ALL_CONTRACT[0])
        self.assertEqual(code['firstlineno'], m.SHOW_ALL_CONTRACT[2])
        self.assertEqual(hashlib.sha256(code['code']).hexdigest(), m.SHOW_ALL_CONTRACT[4])

    def test_server_constants_match(self):
        path = os.path.join(ROOT, 'server/gateway/src/shared/battle_events.rs')
        with open(path, encoding='utf-8') as source:
            text = source.read()
        self.assertIn('b"%s"' % m.FEATURE, text)
        kinds = dict((int(number), name) for name, number in re.findall(r'(\w+)=(\d+)', text[text.index('pub enum FeedKind'):
                                                                                             text.index('pub struct FeedEvent')]))
        self.assertEqual(sorted(kinds), sorted(m.FEED_ROWS))
        self.assertEqual(max(kinds), channel.MAX_FEED_KIND)


if __name__ == '__main__':
    unittest.main()
