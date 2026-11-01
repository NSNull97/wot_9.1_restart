# -*- coding: utf-8 -*-
"""UI-04 history logic. Runs on Python 3 and on CPython 2.7.3 like the client."""
import hashlib
import os
import re
import struct
import subprocess
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'client_patch'))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import project_battle_feed as feed_module
import project_battle_history as m
import project_hit_indicator as channel

ORIGINAL = 'C:/WoT_0.9.1_RU_0717_original/res/scripts/client/'
NO_VALUE = 0xffff


def feed(kind, value=None, vehicle=0):
    return {'kind': 'feed', 'feed': kind, 'value': value, 'vehicle': vehicle}


def hit(damage=0, blocked=None, verdict='pierced', source=0, criticals=()):
    return {'kind': 'hit_received', 'damage': damage, 'blocked': blocked, 'verdict': verdict, 'source': source,
            'criticals': list(criticals)}


def totals(**fields):
    row = dict(kind='totals', dealt=0, blocked=0, assist_spot=0, assist_track=0, burned=0)
    row.update(fields)
    return row


def history(**options):
    return m.History(options, lambda vehicle: 'tank%d' % vehicle)


def filled(rows):
    return [row for row in rows if row[2] != m.KIND_EMPTY]


def details(rows):
    return [(row[4], row[5], row[6]) for row in filled(rows) if row[2] == m.KIND_DETAIL]


def sums(h):
    return [row[4] for row in filled(h.view()['bottom']) if row[2] == m.KIND_TOTAL]


class WireTests(unittest.TestCase):
    def test_totals_record_matches_the_server_layout(self):
        raw = struct.pack('<IIIII', 1240, 700, 200, 1000, 103)
        frame = b'BE' + struct.pack('<BHB', channel.VERSION, 1, 1) + struct.pack('<BB', 3, 20) + raw
        self.assertEqual(channel.parse_frame(frame)[1], [totals(dealt=1240, blocked=700, assist_spot=200,
                                                                assist_track=1000, burned=103)])

    def test_a_broken_totals_record_is_refused_by_length(self):
        frame = b'BE' + struct.pack('<BHB', channel.VERSION, 1, 1) + struct.pack('<BB', 3, 19) + b'\0' * 19
        with self.assertRaises(ValueError):
            channel.parse_frame(frame)


class HistoryTests(unittest.TestCase):
    def test_dealt_row_and_sum(self):
        h = history()
        self.assertTrue(h.add(feed(1, 320, 7)))
        self.assertEqual(details(h.view()['bottom']), [('320', m.CROSS, 'tank7')])
        self.assertEqual(sums(h), ['320', '0', '0', '0'])

    def test_rows_of_one_vehicle_merge_and_move_up(self):
        h = history()
        for row in (feed(1, 100, 7), feed(1, 50, 8), feed(1, 20, 7)):
            h.add(row)
        self.assertEqual(details(h.view()['bottom']), [('120', m.CROSS, 'tank7'), ('50', m.CROSS, 'tank8')])

    def test_a_withheld_amount_is_absent_and_the_sum_says_so(self):
        h = history()
        h.add(feed(1, None, 0))
        self.assertEqual(details(h.view()['bottom']), [('- -', m.CROSS, '')])
        self.assertEqual(sums(h)[0], '0+')
        h.add(feed(1, None, 0))
        self.assertEqual(details(h.view()['bottom'])[0][0], 'x2')
        h.add(feed(1, 300, 9))
        self.assertEqual(sums(h)[0], '300+')

    def test_a_row_with_a_known_and_a_withheld_amount_keeps_the_known_part(self):
        h = history()
        h.add(hit(blocked=400, verdict='ricochet', source=5))
        h.add(hit(blocked=None, verdict='not_pierced', source=5))
        self.assertEqual(details(h.view()['bottom']), [('400+', m.SHIELD, 'tank5')])
        self.assertEqual(sums(h)[1], '400+')

    def test_assist_of_both_kinds_has_its_own_row_and_one_sum(self):
        h = history()
        h.add(feed(14, 151, 3))
        h.add(feed(15, 867, 3))
        self.assertEqual(details(h.view()['bottom']), [('867', m.TRACK, 'tank3'), ('151', m.EYE, 'tank3')])
        self.assertEqual(sums(h)[2], '1018')

    def test_burned_hp_has_a_row_and_counts_as_dealt_too(self):
        h = history()
        h.add(feed(7, None, 4))
        self.assertEqual(h.rows, [], 'ignition itself has no amount')
        h.add(feed(8, 30, 4))
        h.add(feed(8, 12, 4))
        self.assertEqual(details(h.view()['bottom']), [('42', m.FLAME, 'tank4')])
        self.assertEqual(sums(h), ['42', '0', '0', '42'])

    def test_received_rows_of_a_shell_ram_and_fire(self):
        h = history()
        h.add(hit(damage=490, source=2, criticals=[(1, 26)]))
        h.add(feed(11, 20, 6))
        h.add(feed(12, 15, 0))
        self.assertEqual(details(h.view()['bottom']), [('15', m.CROSS, ''), ('20', m.CROSS, 'tank6'),
                                                       ('- -', m.GEAR, 'tank2'), ('490', m.CROSS, 'tank2')])
        self.assertEqual(sums(h)[0], '0', 'received damage is not dealt')

    def test_feed_rows_outside_the_history_change_nothing(self):
        h = history()
        for kind in (3, 4, 5, 6, 7, 9, 10, 13):
            self.assertFalse(h.add(feed(kind, 1, 1)))
        self.assertFalse(h.add(hit(verdict='unknown')))
        self.assertFalse(h.add({'kind': 'other'}))

    def test_totals_replace_the_partial_sums(self):
        h = history()
        h.add(feed(1, None, 0))
        h.add(feed(8, 30, 4))
        h.add(totals(dealt=500, blocked=70, assist_spot=20, assist_track=30, burned=90))
        self.assertEqual(sums(h), ['500', '70', '50', '90'])

    def test_a_reset_forgets_the_battle(self):
        h = history()
        h.add(feed(1, None, 0))
        h.reset()
        self.assertEqual(h.rows, [])
        self.assertEqual(sums(h), ['0', '0', '0', '0'])

    def test_overflow_keeps_the_newest_rows_on_screen(self):
        h = history()
        for vehicle in range(1, m.KEPT_ROWS + 5):
            h.add(feed(1, vehicle, vehicle))
        self.assertEqual(len(h.rows), m.KEPT_ROWS)
        rows = details(h.view()['bottom'])
        self.assertEqual(len(rows), m.BOTTOM_ROWS)
        self.assertEqual(rows[0][2], 'tank%d' % (m.KEPT_ROWS + 4))


class LayoutTests(unittest.TestCase):
    def fill(self, **options):
        h = history(**options)
        h.add(feed(1, 320, 7))
        h.add(hit(damage=490, source=2))
        return h

    def test_all_at_the_bottom(self):
        view = self.fill().view()
        self.assertEqual(filled(view['top']), [])
        self.assertEqual(details(view['bottom']), [('490', m.CROSS, 'tank2'), ('320', m.CROSS, 'tank7')])

    def test_received_at_the_top(self):
        view = self.fill(layout='top').view()
        self.assertEqual(details(view['top']), [('490', m.CROSS, 'tank2')])
        self.assertEqual(details(view['bottom']), [('320', m.CROSS, 'tank7')])

    def test_the_event_filter(self):
        self.assertEqual(details(self.fill(events='efficiency').view()['bottom']), [('320', m.CROSS, 'tank7')])
        self.assertEqual(details(self.fill(events='received').view()['bottom']), [('490', m.CROSS, 'tank2')])

    def test_details_hidden_keep_the_sums(self):
        view = self.fill(detail='hidden').view()
        self.assertEqual(details(view['bottom']), [])
        self.assertEqual(len(filled(view['bottom'])), m.TOTALS_ROWS)

    def test_alt_shows_details_while_held(self):
        h = self.fill(detail='alt')
        self.assertEqual(details(h.view()['bottom']), [])
        h.alt = True
        self.assertEqual(len(details(h.view()['bottom'])), 2)

    def test_each_sum_has_its_switch(self):
        h = self.fill(total_blocked=False, total_burned=False)
        self.assertEqual(sums(h), ['320', '0'])

    def test_the_vehicle_name_has_a_switch(self):
        self.assertEqual(details(self.fill(show_vehicle=False).view()['bottom'])[0][2], '')

    def test_disabled_shows_nothing(self):
        view = self.fill(enabled=False).view()
        self.assertEqual(filled(view['bottom']) + filled(view['top']), [])

    def test_ids_are_stable_and_inside_the_movie(self):
        view = self.fill(layout='top').view()
        self.assertEqual([row[0] for row in view['bottom']], list(range(m.TOTALS_ROWS + m.BOTTOM_ROWS)))
        self.assertEqual([row[0] for row in view['top']], list(range(m.TOP_ROWS)))
        for rows in view.values():
            self.assertTrue(all(0 <= row[1] <= m.MOVIE_SIZE[1] - m.ROW_HEIGHT for row in rows))

    def test_clip_position_follows_the_screen_height(self):
        self.assertEqual(m.clip_position('bottom', (1920, 1080))[0], 0.0)
        top, bottom = m.clip_position('top', (1920, 1080))[1], m.clip_position('bottom', (1920, 1080))[1]
        self.assertAlmostEqual(top, 1 - 2 * (24 + 340) / 1080.0)
        self.assertAlmostEqual(bottom, 1 - 2 * (1080 - 118 - 340) / 1080.0)
        self.assertGreater(top, bottom)


class Component:
    def __init__(self):
        self.visible = None


class Widget:
    def __init__(self, x, y):
        self.at, self.calls, self.closed, self.active_state = (x, y), [], False, None
        self.component = Component()

    def active(self, state):
        self.active_state = state

    def call(self, name, args):
        self.calls.append((name, args))

    def place(self, x, y):
        self.at = (x, y)

    def close(self):
        self.closed = True


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.widgets, self.records, self.timers, self.alt = [], [], [], False
        self.history = history()
        self.make()

    def make(self):
        self.runtime = m.Runtime(self.history, self.widget, lambda: (1920, 1080), lambda: self.alt, self.schedule,
                                 self.timers.remove, lambda *a, **k: self.records.append((a, k)))

    def widget(self, x, y):
        if getattr(self, 'broken', False):
            raise IOError('movie')
        row = Widget(x, y)
        self.widgets.append(row)
        return row

    def schedule(self, period, callback):
        self.timers.append(callback)
        return callback

    def names(self):
        return [row[0][0] for row in self.records]

    def test_nothing_loads_before_the_first_fact(self):
        self.runtime.on_event(feed(3, None, 1))
        self.assertEqual(self.widgets, [])

    def test_the_first_fact_opens_one_widget_at_the_bottom(self):
        self.runtime.on_event(feed(1, 320, 7))
        self.assertEqual(len(self.widgets), 1)
        self.assertIs(self.widgets[0].active_state, True)
        self.assertEqual(self.widgets[0].at, m.clip_position('bottom', (1920, 1080)))

    def test_only_changed_rows_are_sent(self):
        self.runtime.on_event(feed(1, 320, 7))
        first = len(self.widgets[0].calls)
        self.assertEqual(first, m.TOTALS_ROWS + m.BOTTOM_ROWS)
        self.runtime.on_event(feed(1, 10, 7))
        self.assertEqual(len(self.widgets[0].calls), first + 2, 'the sum and the row')

    def test_the_top_layout_opens_a_second_widget_only_with_a_received_row(self):
        self.history.apply_options({'layout': 'top'})
        self.runtime.on_event(feed(1, 320, 7))
        self.assertEqual(len(self.widgets), 1)
        self.runtime.on_event(hit(damage=90, source=2))
        self.assertEqual(len(self.widgets), 2)
        self.assertEqual(self.widgets[1].at, m.clip_position('top', (1920, 1080)))

    def test_options_apply_at_once(self):
        self.runtime.on_event(hit(damage=90, source=2))
        self.runtime.apply_options({'layout': 'top'})
        self.assertEqual(len(self.widgets), 2)
        self.assertEqual(self.widgets[0].calls[-1][1][2], m.KIND_EMPTY)

    def test_options_before_a_fact_load_nothing(self):
        self.runtime.apply_options({'layout': 'top'})
        self.assertEqual(self.widgets, [])

    def test_a_refused_option_leaves_the_screen(self):
        self.runtime.on_event(feed(1, 320, 7))
        with self.assertRaises(ValueError):
            self.runtime.apply_options({'layout': 'side'})
        self.assertEqual(self.history.options['layout'], 'bottom')

    def test_alt_is_polled_only_in_its_mode_and_stops_with_the_widget(self):
        self.runtime.on_event(feed(1, 320, 7))
        self.assertEqual(self.timers, [])
        self.history.apply_options({'detail': 'alt'})
        self.runtime.push()
        self.assertEqual(len(self.timers), 1)
        count = len(self.widgets[0].calls)
        self.alt = True
        self.timers.pop()()
        self.assertGreater(len(self.widgets[0].calls), count)
        self.assertEqual(len(self.timers), 1)
        self.runtime.ready()
        self.assertEqual(self.timers, [])

    def test_resize_moves_the_live_widgets(self):
        self.runtime.on_event(feed(1, 320, 7))
        self.runtime.screen = lambda: (1280, 720)
        self.runtime.resize()
        self.assertEqual(self.widgets[0].at, m.clip_position('bottom', (1280, 720)))

    def test_show_all_hides_a_live_and_a_later_widget(self):
        self.runtime.on_event(feed(1, 320, 7))
        self.runtime.show_all(False)
        self.assertIs(self.widgets[0].component.visible, False)
        self.history.apply_options({'layout': 'top'})
        self.runtime.on_event(hit(damage=90, source=2))
        self.assertIs(self.widgets[1].component.visible, False)

    def test_a_new_battle_closes_the_widgets_and_clears_the_history(self):
        self.runtime.on_event(feed(1, 320, 7))
        self.runtime.ready()
        self.assertTrue(self.widgets[0].closed)
        self.assertEqual(self.history.rows, [])
        self.runtime.on_event(feed(1, 5, 7))
        self.assertEqual(len(self.widgets), 2)

    def test_a_movie_that_does_not_load_switches_the_history_off_quietly(self):
        self.broken = True
        self.runtime.on_event(feed(1, 320, 7))
        self.assertTrue(self.runtime.failed)
        self.assertIn('project_battle_history_failed', self.names())
        self.broken = False
        self.runtime.on_event(feed(1, 320, 7))
        self.assertEqual(self.widgets, [])

    def test_a_failing_call_closes_the_widget(self):
        self.runtime.on_event(feed(1, 320, 7))
        self.widgets[0].call = None
        self.runtime.on_event(feed(1, 5, 7))
        self.assertTrue(self.runtime.failed)
        self.assertTrue(self.widgets[0].closed)


class ShowAllTests(unittest.TestCase):
    def test_one_wrapper_serves_both_widgets_and_the_last_one_restores_the_native(self):
        seen = []

        class Battle(object):
            def showAll(self, isShow):
                seen.append(('native', isShow))

        native = Battle.__dict__['showAll']
        modules = {'gui': types.ModuleType('gui'), 'gui.Scaleform': types.ModuleType('gui.Scaleform'),
                   'gui.Scaleform.Battle': types.ModuleType('gui.Scaleform.Battle')}
        modules['gui'].Scaleform = modules['gui.Scaleform']
        modules['gui.Scaleform'].Battle = modules['gui.Scaleform.Battle']
        modules['gui.Scaleform.Battle'].Battle = Battle
        saved = dict((name, sys.modules.get(name)) for name in modules)
        checked = feed_module._check
        sys.modules.update(modules)
        feed_module._check = lambda function, *contract: seen.append('checked')
        try:
            hook = feed_module.ShowAll()
            first, second = (lambda state: seen.append(('feed', state))), (lambda state: seen.append(('history', state)))
            hook.add(first)
            hook.add(second)
            hook.bind()
            hook.bind()
            Battle().showAll(False)
            self.assertEqual(seen, ['checked', ('native', False), ('feed', False), ('history', False)])
            hook.remove(first)
            self.assertIsNot(Battle.__dict__['showAll'], native)
            hook.remove(second)
            self.assertIs(Battle.__dict__['showAll'], native)
        finally:
            feed_module._check = checked
            for name, module in saved.items():
                if module is None:
                    del sys.modules[name]
                else:
                    sys.modules[name] = module

    def test_a_replaced_wrapper_is_reported_not_overwritten(self):
        hook = feed_module.ShowAll()
        listener = lambda state: None
        hook.add(listener)

        class Battle(object):
            def showAll(self, isShow):
                pass

        hook.bound = (Battle, None, object())
        with self.assertRaises(RuntimeError):
            hook.remove(listener)


class SettingsTests(unittest.TestCase):
    def test_explicit_and_only_with_the_channel(self):
        self.assertFalse(m.validate_settings({}, 'hit_indicator'))
        good = {'battle_history': m.prepare_settings('top'), 'hit_indicator': {'view': 'standard'}}
        self.assertTrue(m.validate_settings(good, 'hit_indicator'))
        for bad in ({'battle_history': None}, {'battle_history': good['battle_history']},
                    {'battle_history': {'nope': True}, 'hit_indicator': {}},
                    {'battle_history': {'layout': 'side'}, 'hit_indicator': {}},
                    {'battle_history': {'enabled': 1}, 'hit_indicator': {}},
                    {'battle_history': True, 'hit_indicator': {}}):
            with self.assertRaises(ValueError):
                m.validate_settings(bad, 'hit_indicator')

    def test_views_of_the_flag(self):
        self.assertEqual(m.prepare_settings('bottom')['layout'], 'bottom')
        self.assertEqual(m.prepare_settings('top')['layout'], 'top')
        with self.assertRaises(ValueError):
            m.prepare_settings('left')

    def test_every_option_has_a_default_inside_its_values(self):
        for key, allowed, default in m.OPTION_SCHEMA:
            self.assertIn(default, allowed, key)
        self.assertEqual(m.checked_options({}), m.default_options())

    def test_no_running_history_before_install(self):
        self.assertIsNone(m.policy())
        self.assertFalse(m.restore(lambda *a, **k: None))

    def test_install_needs_the_channel(self):
        with self.assertRaises(RuntimeError):
            m.install(lambda *a, **k: None, m.default_options(), None)


@unittest.skipUnless(sys.version_info[0] == 3, 'static checks run on Python 3')
class ContractTests(unittest.TestCase):
    def test_prepare_lists_the_flag(self):
        env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, 'tools'))
        result = subprocess.run([sys.executable, '-B', os.path.join(ROOT, 'tools/interactive_client.py'),
                                 'prepare', '--help'], env=env, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertIn(b'--battle-history', result.stdout)

    def test_server_constants_match(self):
        path = os.path.join(ROOT, 'server/gateway/src/shared/battle_events.rs')
        with open(path, encoding='utf-8') as source:
            text = source.read()
        self.assertIn('b"%s"' % m.FEATURE, text)
        kinds = dict((name, int(number)) for name, number in re.findall(r'(\w+)=(\d+)', text[text.index('pub enum FeedKind'):
                                                                                             text.index('pub struct FeedEvent')]))
        for number, name in (('ShotDamage', 'shot'), ('RamDamage', 'ram'), ('FireDamage', 'burned'),
                             ('RamReceived', 'received'), ('FireReceived', 'received'),
                             ('AssistSpot', 'assist_spot'), ('AssistTrack', 'assist_track')):
            self.assertEqual(m.FEED_ROWS[kinds[number]], name)
        self.assertIn('const KIND_TOTALS:u8=%d;' % channel.KIND_TOTALS, text)

    @unittest.skipUnless(os.path.isfile(ORIGINAL + 'avatarinputhandler/aims.pyc'), 'original client absent')
    def test_the_engine_names_the_widget_uses_exist_in_717(self):
        import py27_static as static
        names = set()
        for rel in ('avatarinputhandler/aims.pyc', 'avatarinputhandler/control_modes.pyc', 'avatarinputhandler/__init__.pyc',
                    'avatarinputhandler/videocamera.pyc', 'gui/shared/utils/key_mapping.pyc'):
            with open(ORIGINAL + rel, 'rb') as source:
                for _, code in static.records(static.parse_pyc(source.read())):
                    names.update(static.text(code['names']))
        for name in ('screenResolution', 'g_guiResetters', 'DEPTH_OF_Aim', 'isKeyDown', 'KEY_LALT', 'KEY_RALT', 'position'):
            self.assertIn(name, names)


if __name__ == '__main__':
    unittest.main()
