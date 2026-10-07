"""Diagnostic scheduling/bounds only; fake callbacks do not establish native GUI compatibility."""
import ast
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'client_patch/sr_interactive.py'


def load_scheduler(**settings):
    nodes = [node for node in ast.parse(SOURCE.read_bytes()).body
             if isinstance(node, ast.FunctionDef) and node.name == 'schedule_tooltip_screenshot']
    assert len(nodes) == 1
    callbacks = []
    # No navigation, login, input or quit methods are supplied.
    namespace = dict(_settings=settings, _control=None, _fini=False, _capture_done=True,
                     _tooltip_capture_count=0, _tooltip_callbacks={},
                     _passive_capture_counts={'tooltip': 0, 'awards': 0},
                     BigWorld=SimpleNamespace(callback=lambda delay, fn: callbacks.append((delay, fn))))
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), 'exec'), namespace)
    return namespace, callbacks


class PassiveCaptureTests(unittest.TestCase):
    def test_default_normal_session_does_not_capture_ui(self):
        n, pending = load_scheduler()
        n['schedule_tooltip_screenshot'](1, 'onCreateComplexTooltip_shown')
        self.assertEqual([], pending)

    def test_explicit_passive_normal_capture_needs_no_control_or_input(self):
        n, pending = load_scheduler(capture_ui_passive=True)
        n['schedule_tooltip_screenshot'](1, 'onCreateComplexTooltip_shown')
        self.assertEqual(1, len(pending))
        self.assertEqual(1.0, pending[0][0])
        self.assertIsNone(n['_control'])

    def test_eight_hovers_cannot_starve_awards_and_total_is_bounded(self):
        n, pending = load_scheduler(capture_ui_passive=True)
        for i in range(100):
            n['schedule_tooltip_screenshot'](i + 1, 'onCreateComplexTooltip_shown')
        for i in range(100):
            n['schedule_tooltip_screenshot'](i + 101, 'profile_awards_rendered')
        self.assertEqual(10, len(pending))
        self.assertEqual({'tooltip': 8, 'awards': 2}, n['_passive_capture_counts'])

    def test_not_ready_or_shutdown_does_not_schedule(self):
        for field, value in [('_capture_done', False), ('_fini', True)]:
            n, pending = load_scheduler(capture_ui_passive=True)
            n[field] = value
            n['schedule_tooltip_screenshot'](1, 'profile_awards_rendered')
            self.assertEqual([], pending)

    def test_missing_call_identity_does_not_schedule(self):
        n, pending = load_scheduler(capture_ui_passive=True)
        n['schedule_tooltip_screenshot'](None, 'profile_awards_rendered')
        self.assertEqual([], pending)

    def test_scheduled_callback_after_shutdown_is_inert(self):
        n, pending = load_scheduler(capture_ui_passive=True)
        n['schedule_tooltip_screenshot'](1, 'profile_awards_rendered')
        n['_fini'] = True
        pending[0][1]()
        self.assertEqual({}, n['_tooltip_callbacks'])

    def test_historical_control_budget_is_preserved(self):
        for scenario, maximum in [('profile', 8), ('tooltip', 12)]:
            n, pending = load_scheduler()
            n['_control'] = {'ui_scenario': scenario}
            for i in range(20):
                n['schedule_tooltip_screenshot'](i + 1, 'onCreateComplexTooltip_shown')
            self.assertEqual(maximum, len(pending))


class VehicleCaptureTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='passive-unit-', dir=SOURCE.parents[1] / 'local')
        self.addCleanup(self.folder.cleanup)
        directory = os.path.normcase(os.path.realpath(self.folder.name))
        self.clock = [0.0]
        self.shots, self.events = [], []
        nodes = [node for node in ast.parse(SOURCE.read_bytes()).body
                 if isinstance(node, ast.FunctionDef) and node.name == 'capture_observed_vehicle']
        self.n = dict(_settings={'capture_ui_passive': True, 'screenshot_dir': directory, 'local_root': directory},
                      _capture_done=True, _fini=False, _vehicle_capture_ready=None, _vehicle_capture_ids=set(),
                      _observations=7, long=int, os=os, time=SimpleNamespace(clock=lambda: self.clock[0]),
                      owned=lambda path, root: path, primitive=lambda value: value,
                      record=lambda event, **fields: self.events.append((event, fields)),
                      BigWorld=SimpleNamespace(screenShot=lambda ext, name: self.shots.append((ext, name))))
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), 'exec'), self.n)
        settings = SimpleNamespace(g_instance=SimpleNamespace(engineConfig=SimpleNamespace(readString=lambda key: directory)))
        self.modules = patch.dict('sys.modules', Settings=settings)
        self.modules.start()
        self.addCleanup(self.modules.stop)

    def observe(self, identity, stamp, ready=True):
        self.clock[0] = stamp
        self.n['capture_observed_vehicle']({'vehicle': {'inventory_id': identity},
                                           'selected_inventory_id': identity, 'vehicle_model_loaded': ready}, ready)

    def test_requires_same_ready_selection_for_two_seconds(self):
        self.observe(1, 0)
        self.observe(1, 1.9)
        self.assertEqual([], self.shots)
        self.observe(1, 2)
        self.assertEqual([('png', 'vehicle_1')], self.shots)
        self.assertEqual(7, self.events[0][1]['observation_index'])
        self.assertIs(self.events[0][1]['selection_changed_by_observer'], False)

    def test_loading_or_selection_change_resets_interval(self):
        self.observe(1, 0)
        self.observe(1, 1, False)
        self.observe(1, 2)
        self.observe(2, 3)
        self.observe(2, 4.9)
        self.assertEqual([], self.shots)
        self.observe(2, 5)
        self.assertEqual([('png', 'vehicle_2')], self.shots)

    def test_repeated_and_third_vehicle_cannot_exceed_two_capture_bound(self):
        for identity, stamp in [(1, 0), (1, 2), (2, 3), (2, 5), (1, 6), (1, 9), (3, 10), (3, 13)]:
            self.observe(identity, stamp)
        self.assertEqual([('png', 'vehicle_1'), ('png', 'vehicle_2')], self.shots)

    def test_existing_target_cannot_be_overwritten(self):
        Path(self.folder.name, 'vehicle_1_001.png').write_bytes(b'unit-marker')
        self.observe(1, 0)
        with self.assertRaisesRegex(ValueError, 'occupied'):
            self.observe(1, 2)
        self.assertEqual([], self.shots)

    def test_shutdown_cannot_capture(self):
        self.observe(1, 0)
        self.n['_fini'] = True
        self.observe(1, 2)
        self.assertEqual([], self.shots)


if __name__ == '__main__':
    unittest.main()
