# -*- coding: utf-8 -*-
"""UI-05 settings logic. Runs on Python 3 and on CPython 2.7.3 like the client.
Mocks prove the decisions, not what the native window shows."""
import hashlib
import os
import subprocess
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'client_patch'))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import project_battle_feed as feed_module
import project_battle_history as history_module
import project_battle_settings as m
import project_hit_indicator as hit_module

ORIGINAL = 'C:/WoT_0.9.1_RU_0717_original/res/scripts/client/'
MODULES = {'hit_indicator': hit_module, 'battle_feed': feed_module, 'battle_history': history_module}


def options(**overrides):
    result = dict((name, module.default_options()) for name, module in MODULES.items())
    for widget, values in overrides.items():
        result[widget].update(values)
    return result


class Section(object):
    """The DataSection calls the module makes; the shape of ResMgr's section."""

    def __init__(self, text=''):
        self.children, self.asString = {}, text

    def has_key(self, name):
        return name in self.children

    def __getitem__(self, name):
        return self.children[name]

    def items(self):
        return sorted(self.children.items())

    def deleteSection(self, name):
        del self.children[name]

    def createSection(self, name):
        self.children[name] = Section()
        return self.children[name]

    def writeString(self, name, value):
        self.children[name] = Section(value)


class Harness(object):
    def __init__(self, rows=None, save=None):
        self.root, self.saved, self.events, self.pushed = Section(), [], [], []
        self.fail_save = False
        if rows is not None:
            section = self.root.createSection(m.SECTION)
            for name, value in rows.items():
                section.writeString(name, value)
        targets = dict((widget, self.target(widget)) for widget in m.WIDGETS)
        self.controller = m.Controller(options(), m.Preferences(self.root, save or self.save), targets, self.record)

    def target(self, widget):
        return lambda value: self.pushed.append((widget, value))

    def save(self):
        if self.fail_save:
            raise IOError('disk full')
        self.saved.append(1)

    def record(self, name, **fields):
        self.events.append((name, fields))

    def names(self):
        return [name for name, _ in self.events]


class ImportTests(unittest.TestCase):
    def test_a_class_bound_over_its_submodule_does_not_hide_the_module(self):
        # Native gui...settings/__init__ binds the class over the submodule.
        names = ('ui05pkg', 'ui05pkg.SettingsWindow')
        package, module = types.ModuleType(names[0]), types.ModuleType(names[1])
        package.__path__ = []
        class SettingsWindow(object):
            pass
        package.SettingsWindow, module.SettingsWindow = SettingsWindow, SettingsWindow
        sys.modules[names[0]], sys.modules[names[1]] = package, module
        try:
            self.assertIs(m._import(names[1]), module)
            self.assertIs(getattr(m._import(names[1]), 'SettingsWindow'), SettingsWindow)
        finally:
            for name in names:
                del sys.modules[name]


class SchemaTests(unittest.TestCase):
    def test_every_option_of_every_widget_has_exactly_one_control(self):
        for widget, module in MODULES.items():
            table = dict((key, allowed) for key, allowed, _ in module.OPTION_SCHEMA)
            rows = [row for row in m.CONTROLS if row[1] == widget]
            self.assertEqual(sorted(row[2] for row in rows), sorted(table))
            for row in rows:
                if row[4] is None:
                    self.assertEqual(set(table[row[2]]), {True, False}, row[0])
                else:
                    self.assertEqual(set(value for value, _ in row[4]), set(table[row[2]]), row[0])

    def test_control_names_are_unique_and_fit_the_preferences_tags(self):
        names = [row[0] for row in m.CONTROLS]
        self.assertEqual(len(names), len(set(names)))
        for name in names:
            self.assertTrue(name.startswith('sr') and name.isalnum(), name)

    def test_no_disorientation_control(self):
        self.assertFalse([row for row in m.CONTROLS if 'ориент' in row[3]])

    def test_panels_hold_every_control_once_and_fit_the_native_page(self):
        placed = [row[0] for panel in m.PANELS for row in panel[6]]
        self.assertEqual(sorted(placed), sorted(row[0] for row in m.CONTROLS))
        for _, _, x, y, width, height, rows in m.PANELS:
            self.assertLessEqual(x + width, 790)
            self.assertLessEqual(y + height, 530)
            self.assertGreaterEqual(height, m.HEADER + m.ROW_STEP * len(rows))

    def test_panels_do_not_overlap(self):
        boxes = [panel[2:6] for panel in m.PANELS]
        for index, (x, y, width, height) in enumerate(boxes):
            for other_x, other_y, other_width, other_height in boxes[index + 1:]:
                self.assertTrue(x + width <= other_x or other_x + other_width <= x
                                or y + height <= other_y or other_y + other_height <= y)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.base = m.base_values(options())

    def test_nothing_stored_keeps_the_prepare_values(self):
        base = m.base_values(options(hit_indicator={'view': 'extended'}, battle_history={'layout': 'top'}))
        self.assertEqual(m.decode(None, base), (base, []))
        self.assertEqual(base['srHitView'], 'extended')
        self.assertEqual(base['srHistLayout'], 'top')

    def test_stored_values_survive_a_round_trip(self):
        values = dict(self.base, srHitView='extended', srFeedLabel=False, srHistDetail='alt', srHistEvents='received')
        self.assertEqual(m.decode(m.encode(values), self.base), (values, []))

    def test_settings_read_by_the_python_2_json_are_accepted(self):
        import json
        settings = json.loads(json.dumps({'enable_profile13_battle': True, 'hit_indicator': {'view': 'extended'},
                                          'battle_feed': {}, 'battle_history': {'layout': 'top'},
                                          'battle_settings': {'version': 1}}))
        self.assertTrue(hit_module.validate_settings(settings))
        self.assertTrue(m.validate_settings(settings))
        base = m.base_values(options(hit_indicator=settings['hit_indicator'], battle_history=settings['battle_history']))
        self.assertEqual(m.window_value('srHitView', base['srHitView']), 1)
        self.assertTrue(all(isinstance(value, str) for value in m.encode(base).values()))

    def test_rows_are_strings_with_the_schema_version(self):
        rows = m.encode(self.base)
        self.assertEqual(rows[m.VERSION_KEY], str(m.VERSION))
        self.assertEqual(rows['srHitDamage'], 'true')
        self.assertEqual(rows['srHistLayout'], 'bottom')
        self.assertTrue(all(isinstance(value, str) for value in rows.values()))

    def test_an_unknown_value_falls_back_alone(self):
        rows = m.encode(dict(self.base, srFeedShot=False))
        rows['srHitView'], rows['srHitDamage'] = 'sideways', '1'
        values, problems = m.decode(rows, self.base)
        self.assertEqual(sorted(problems), ['srHitDamage', 'srHitView'])
        self.assertEqual(values['srHitView'], self.base['srHitView'])
        self.assertTrue(values['srHitDamage'])
        self.assertFalse(values['srFeedShot'])

    def test_an_unknown_key_is_reported_and_ignored(self):
        rows = m.encode(self.base)
        rows['srFromTheFuture'] = 'true'
        values, problems = m.decode(rows, self.base)
        self.assertEqual(problems, ['srFromTheFuture'])
        self.assertEqual(values, self.base)

    def test_a_newer_or_damaged_version_keeps_the_base(self):
        for version in (str(m.VERSION + 1), 'x', ''):
            rows = dict(m.encode(dict(self.base, srFeedShot=False)), version=version)
            self.assertEqual(m.decode(rows, self.base), (self.base, [m.VERSION_KEY]))

    def test_a_section_without_version_keeps_the_base(self):
        rows = m.encode(dict(self.base, srFeedShot=False))
        del rows[m.VERSION_KEY]
        self.assertEqual(m.decode(rows, self.base), (self.base, [m.VERSION_KEY]))

    def test_migration_steps_run_in_order(self):
        def step(rows):
            rows = dict(rows)
            rows['srFeedShot'] = rows.pop('srOldShot')
            return rows

        values, problems = m.decode({m.VERSION_KEY: '0', 'srOldShot': 'false'}, self.base, {0: step})
        self.assertEqual(problems, [])
        self.assertFalse(values['srFeedShot'])

    def test_an_older_version_without_a_step_keeps_the_base(self):
        self.assertEqual(m.decode({m.VERSION_KEY: '0'}, self.base, {}), (self.base, [m.VERSION_KEY]))

    def test_control_values_are_closed(self):
        self.assertIs(m.control_value('srHitDamage', False), False)
        self.assertEqual(m.control_value('srHistEvents', 1), 'efficiency')
        self.assertEqual(m.control_value('srHistEvents', 2.0), 'received')
        for name, value in (('srHitDamage', 1), ('srHitDamage', 'true'), ('srHistEvents', 3), ('srHistEvents', -1),
                            ('srHistEvents', 1.5), ('srHistEvents', True), ('srHistEvents', None), ('srNothing', 1)):
            with self.assertRaises(ValueError):
                m.control_value(name, value)

    def test_window_values_invert_control_values(self):
        for row in m.CONTROLS:
            values = (True, False) if row[4] is None else [choice for choice, _ in row[4]]
            for value in values:
                self.assertEqual(m.control_value(row[0], m.window_value(row[0], value)), value)

    def test_section_replaces_itself_in_the_data_section(self):
        h = Harness()
        preferences = h.controller.preferences
        self.assertIsNone(preferences.read())
        preferences.write({m.VERSION_KEY: '1', 'srHitView': 'extended', 'srFeedShot': 'false'})
        preferences.write({m.VERSION_KEY: '1', 'srHitView': 'standard'})
        self.assertEqual(preferences.read(), {m.VERSION_KEY: '1', 'srHitView': 'standard'})
        self.assertEqual(len(h.saved), 2)

    def test_the_section_passes_the_owned_preferences_writer(self):
        import project_preferences
        h = Harness()
        h.controller.preferences.write(m.encode(h.controller.base))
        data = project_preferences.serialize(h.root)
        self.assertIn(b'<projectBattleUi>', data)
        self.assertIn(b'<srHitView>standard</srHitView>', data)


class ControllerTests(unittest.TestCase):
    def test_load_pushes_stored_values_to_every_widget(self):
        h = Harness({m.VERSION_KEY: '1', 'srHitView': 'extended', 'srHistLayout': 'top', 'srFeedKill': 'false'})
        h.controller.load()
        pushed = dict(h.pushed)
        self.assertEqual(pushed['hit_indicator']['view'], 'extended')
        self.assertEqual(pushed['battle_history']['layout'], 'top')
        self.assertIs(pushed['battle_feed']['kill'], False)
        self.assertEqual(sorted(pushed['battle_feed']), sorted(feed_module.default_options()))

    def test_a_broken_section_does_not_stop_the_client(self):
        h = Harness({m.VERSION_KEY: 'x'})
        h.controller.load()
        self.assertEqual(h.events[-1][1]['problems'], [m.VERSION_KEY])
        self.assertEqual(len(h.pushed), 3)

    def test_a_failing_read_is_reported_and_the_base_stays(self):
        h = Harness()

        def broken():
            raise IOError('damaged')

        h.controller.preferences.read = broken
        h.controller.load()
        self.assertIn(m.EVENT + '_read_failed', h.names())
        self.assertEqual(len(h.pushed), 3)

    def test_commit_applies_at_once_and_stores(self):
        h = Harness()
        h.controller.load()
        del h.pushed[:]
        self.assertTrue(h.controller.commit({'srHistDetail': 1, 'srFeedLabel': False}))
        self.assertEqual(dict(h.pushed)['battle_history']['detail'], 'alt')
        self.assertIs(dict(h.pushed)['battle_feed']['show_label'], False)
        self.assertEqual(h.saved, [1])
        stored = h.controller.preferences.read()
        self.assertEqual((stored['srHistDetail'], stored['srFeedLabel']), ('alt', 'false'))
        self.assertEqual(h.controller.window()['srHistDetail'], 1)

    def test_the_same_values_change_nothing(self):
        h = Harness()
        h.controller.load()
        del h.pushed[:]
        self.assertFalse(h.controller.commit({'srHitDamage': True, 'srHitView': 0}))
        self.assertEqual((h.pushed, h.saved), ([], []))

    def test_a_refused_value_is_reported_and_the_rest_goes_on(self):
        h = Harness()
        h.controller.load()
        self.assertTrue(h.controller.commit({'srHitDamage': 'yes', 'srHitAnimate': False, 'srNothing': True}))
        refused = sorted(fields['control'] for name, fields in h.events if name == m.EVENT + '_refused')
        self.assertEqual(refused, ['srHitDamage', 'srNothing'])
        self.assertIs(h.controller.values['srHitAnimate'], False)

    def test_a_failed_save_is_reported_and_the_session_keeps_the_values(self):
        h = Harness()
        h.controller.load()
        h.fail_save = True
        self.assertTrue(h.controller.commit({'srHitAnimate': False}))
        self.assertIn(m.EVENT + '_save_failed', h.names())
        self.assertNotIn(m.EVENT + '_saved', h.names())
        self.assertIs(h.controller.values['srHitAnimate'], False)

    def test_the_callback_list_follows_the_table(self):
        h = Harness()
        h.controller.commit({'srHistEvents': 2})
        current = h.controller.window_list()
        self.assertEqual(len(current), len(m.CONTROLS))
        self.assertEqual(current[[row[0] for row in m.CONTROLS].index('srHistEvents')], 2)

    def test_the_running_widgets_accept_what_the_controller_sends(self):
        clock = [10.0]
        policy = hit_module.Policy(hit_module.default_options(), lambda *a, **k: None, lambda: clock[0])
        feed = feed_module.Feed(feed_module.default_options(), lambda: clock[0], lambda vehicle: 'tank', lambda vehicle: '')
        history = history_module.History(history_module.default_options(), lambda vehicle: 'tank', lambda vehicle: '')
        record = lambda *a, **k: None
        targets = {'hit_indicator': policy.apply_options, 'battle_feed': feed.apply_options,
                   'battle_history': history.apply_options}
        root = Section()
        controller = m.Controller(options(), m.Preferences(root, lambda: None), targets, record)
        controller.load()
        controller.commit({'srHitView': 1, 'srFeedEnabled': False, 'srHistLayout': 1, 'srHistEvents': 2})
        self.assertEqual(policy.movie(), hit_module.EXTENDED_MOVIE)
        self.assertIs(feed.options['enabled'], False)
        self.assertEqual((history.options['layout'], history.options['events']), ('top', 'received'))


class RunningFeedTests(unittest.TestCase):
    """An open window in battle changes the feed on screen at once."""

    class Widget(object):
        def __init__(self):
            self.calls = []

        def call(self, name, args):
            self.calls.append(args)

        def active(self, state):
            pass

    def running(self):
        self.widget = self.Widget()
        self.widget.component = types.SimpleNamespace(visible=True) if hasattr(types, 'SimpleNamespace') else self.widget
        self.feed = feed_module.Feed(feed_module.default_options(), lambda: 10.0, lambda vehicle: 'tank', lambda vehicle: '')
        runtime = feed_module.Runtime(self.feed, lambda: self.widget, lambda: (1920, 1080), lambda delay, fn: 1,
                                      lambda timer: None, lambda *a, **k: None)
        runtime.on_event({'kind': 'feed', 'feed': 1, 'value': 320, 'vehicle': 7})
        runtime.on_event({'kind': 'feed', 'feed': 3, 'value': None, 'vehicle': 7})
        return runtime

    def test_a_switched_off_row_leaves_the_screen(self):
        runtime = self.running()
        runtime.apply_options({'shot': False})
        self.assertEqual([row['key'] for row in self.feed.rows], ['kill'])
        self.assertEqual(self.widget.calls[-1][2], feed_module.ROWS_TABLE['kill'][1])
        self.assertEqual(self.widget.calls[-1][len(feed_module.EMPTY_ROW)], -1)

    def test_switching_the_feed_off_empties_it(self):
        runtime = self.running()
        runtime.apply_options({'enabled': False})
        self.assertEqual(self.feed.rows, [])
        self.assertEqual(self.widget.calls[-1][0], -1)

    def test_a_label_change_redraws(self):
        runtime = self.running()
        runtime.apply_options({'show_label': False})
        self.assertEqual(self.widget.calls[-1][3], '')

    def test_without_a_widget_only_the_options_change(self):
        feed = feed_module.Feed(feed_module.default_options(), lambda: 10.0, lambda vehicle: 'tank', lambda vehicle: '')
        runtime = feed_module.Runtime(feed, lambda: 1 / 0, None, None, None, lambda *a, **k: None)
        runtime.apply_options({'kill': False})
        self.assertIs(feed.options['kill'], False)

    def test_a_widget_failure_switches_the_feed_off(self):
        runtime = self.running()
        self.widget.call = lambda name, args: 1 / 0
        self.widget.close = lambda: None
        runtime.apply_options({'kill': False})
        self.assertTrue(runtime.failed)


class WindowHost(object):
    """The shape of the native SettingsWindow."""

    def __init__(self):
        self.calls = []

    def _SettingsWindow__getSettings(self):
        return {'GameSettings': {}}

    def _applySettings(self, settings, isCloseWnd):
        self.calls.append(('apply', dict(settings), isCloseWnd))

    def _SettingsWindow__commitSettings(self, settings=None, restartApproved=False, isCloseWnd=False):
        self.calls.append(('commit', settings, restartApproved, isCloseWnd))

    def onSettingsChange(self, settingName, settingValue):
        self.calls.append(('preview', settingName, settingValue))


class DialogHost(object):
    """The shape of the native SettingsInterface."""

    def __init__(self):
        self.calls = []

    def onPopulateUI(self, *args):
        self.calls.append(('populate', args))

    def onCommitSettings(self, *args):
        self.calls.append(('commit', args))

    def call(self, name, args):
        self.calls.append((name, args))


class HostTests(unittest.TestCase):
    def setUp(self):
        self.h = Harness()
        self.h.controller.load()
        self.window = m.wrap_window(WindowHost, self.h.controller, self.h.record)
        self.dialog = m.wrap_interface(DialogHost, self.h.controller, self.h.record)
        self.addCleanup(m.unwrap, self.window)
        self.addCleanup(m.unwrap, self.dialog)

    def test_the_window_gets_its_group(self):
        data = WindowHost()._SettingsWindow__getSettings()
        self.assertEqual(data[m.VIEW]['srHitDamage'], True)
        self.assertEqual(data[m.VIEW]['srHitView'], 0)
        self.assertIn('GameSettings', data)

    def test_native_code_never_sees_a_project_key(self):
        host = WindowHost()
        host._applySettings({'srHitDamage': False, 'fov': 90}, True)
        self.assertEqual(host.calls, [('apply', {'fov': 90}, True)])
        self.assertTrue(self.h.controller.values['srHitDamage'])

    def test_values_apply_only_when_the_native_part_commits(self):
        host = WindowHost()
        host._applySettings({'srHitDamage': False}, False)
        host._SettingsWindow__commitSettings({}, True, False)
        self.assertIs(self.h.controller.values['srHitDamage'], False)
        self.assertEqual(host.calls[-1], ('commit', {}, True, False))

    def test_a_refused_restart_drops_the_project_part_with_the_native_part(self):
        host = WindowHost()
        host._applySettings({'srHitDamage': False}, False)
        host._applySettings({}, False)
        host._SettingsWindow__commitSettings({}, False, False)
        self.assertTrue(self.h.controller.values['srHitDamage'])

    def test_project_controls_have_no_native_preview(self):
        host = WindowHost()
        host.onSettingsChange('srHitDamage', False)
        host.onSettingsChange('fov', 90)
        self.assertEqual(host.calls, [('preview', 'fov', 90)])

    def test_the_dialog_gets_the_values_after_its_native_data(self):
        host = DialogHost()
        host.onPopulateUI('name')
        self.assertEqual(host.calls[0], ('populate', ('name',)))
        self.assertEqual(host.calls[1], (m.VALUES_CALLBACK, self.h.controller.window_list()))

    def test_the_dialog_commits_inside_a_battle_at_once(self):
        host = DialogHost()
        settings = {'srFeedEnabled': False, 'fullScreen': True}
        host.onCommitSettings(5, settings)
        self.assertIs(self.h.controller.values['srFeedEnabled'], False)
        self.assertEqual(host.calls, [('commit', (5, {'fullScreen': True}))])
        self.assertIs(self.h.pushed[-2][1]['enabled'], False)

    def test_a_commit_without_settings_is_native(self):
        host = DialogHost()
        host.onCommitSettings()
        self.assertEqual(host.calls, [('commit', ())])

    def test_a_replaced_wrapper_is_not_restored_over(self):
        current = WindowHost.__dict__['onSettingsChange']
        WindowHost.onSettingsChange = lambda self, name, value: None
        try:
            with self.assertRaises(RuntimeError):
                m.unwrap(self.window)
        finally:
            WindowHost.onSettingsChange = current


class BinderTests(unittest.TestCase):
    def binder(self, modules, importer):
        self.h = Harness()
        return m.Binder(self.h.controller, modules, importer, self.h.record)

    def test_nothing_is_imported_before_the_lobby(self):
        calls = []
        binder = self.binder({}, lambda name: calls.append(name))
        binder.bind(True)
        self.assertEqual(calls, [])

    def test_a_different_client_leaves_the_window_native_and_says_so(self):
        host = types.ModuleType('host')

        class SettingsWindow(object):
            def _SettingsWindow__getSettings(self):
                return {}

        class SettingsInterface(object):
            pass

        host.SettingsWindow, host.SettingsInterface = SettingsWindow, SettingsInterface
        original = SettingsWindow.__dict__['_SettingsWindow__getSettings']
        binder = self.binder({}, lambda name: host)
        binder.bind(False)
        self.assertEqual(self.h.names().count(m.EVENT + '_bind_failed'), 2)
        self.assertIs(SettingsWindow.__dict__['_SettingsWindow__getSettings'], original)
        calls = len(self.h.events)
        binder.bind(False)
        self.assertEqual(len(self.h.events), calls)

    def test_validate_needs_every_widget(self):
        full = dict((widget, {}) for widget in m.WIDGETS)
        self.assertFalse(m.validate_settings({}))
        self.assertTrue(m.validate_settings(dict(full, battle_settings=m.prepare_settings())))
        with self.assertRaises(ValueError):
            m.validate_settings({'battle_settings': None})
        with self.assertRaises(ValueError):
            m.validate_settings(dict(full, battle_settings={'version': 2}))
        del full['battle_feed']
        with self.assertRaises(ValueError):
            m.validate_settings(dict(full, battle_settings=m.prepare_settings()))


@unittest.skipUnless(os.path.isfile(ORIGINAL + 'gui/scaleform/settingsinterface.pyc') and sys.version_info[0] == 3,
                     'original client absent')
class ContractTests(unittest.TestCase):
    def test_pinned_records_equal_the_original_bytecode(self):
        import py27_static as static
        rows = {}
        for name in ('gui/scaleform/settingsinterface.pyc', 'gui/scaleform/daapi/view/lobby/settings/settingswindow.pyc'):
            with open(ORIGINAL + name, 'rb') as source:
                for key, code in static.records(static.parse_pyc(source.read())):
                    rows[key] = code
        for owner, contracts in (('SettingsWindow', m.WINDOW_CONTRACTS), ('SettingsInterface', m.INTERFACE_CONTRACTS)):
            for _, filename, name, line, args, digest in contracts:
                code = rows['<module>.%s.%s' % (owner, name)]
                self.assertEqual(static.text(code['filename']), filename)
                self.assertEqual(code['firstlineno'], line)
                self.assertEqual(code['argcount'], len(args))
                self.assertEqual(hashlib.sha256(code['code']).hexdigest(), digest)


@unittest.skipUnless(sys.version_info[0] == 3, 'driver of the 2.7.3 run')
class Python27Tests(unittest.TestCase):
    def test_this_file_passes_on_the_client_python(self):
        python = os.path.join('D:/WoT_9.1_Server', 'local/toolchains-py27-20261019/cpython-2.7.3-x86/python.exe')
        if not os.path.isfile(python):
            self.skipTest('CPython 2.7.3 absent')
        done = subprocess.run([python, '-B', os.path.abspath(__file__)], capture_output=True, cwd=ROOT, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr.decode('utf-8', 'replace')[-2000:])


if __name__ == '__main__':
    unittest.main()
