"""P04D opt-in/control checks; no original client or service is launched."""
import ast
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'client_patch'))
sys.path.insert(0, str(ROOT / 'tools'))
import interactive_client as installer
import p04d_crew_ui
from tests.test_p04d_crew_ui import transition


def functions(names, namespace):
    path = ROOT / 'client_patch/sr_interactive.py'
    nodes = [v for v in ast.parse(path.read_bytes()).body if isinstance(v, ast.FunctionDef) and v.name in names]
    assert len(nodes) == len(names)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), namespace)


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'control.json'
        self.events = []
        self.ns = {'os': os, 'json': json, '_control_done': False, 'owned': lambda path, root: path,
                   '_p04d_scenario': None,
                   '_settings': {'test_control': str(self.path), 'local_root': self.temp.name,
                                 'endpoint': '127.0.0.1:20014', 'enable_p09d_ammo_service': True,
                                 'enable_crew_recruitment': True},
                   'record': lambda e, **f: self.events.append((e, f))}
        functions({'consume_control'}, self.ns)
        self.scenario = SimpleNamespace(checked_expected=Mock(side_effect=p04d_crew_ui.checked_expected),
                                        NativeScenario=Mock())
        self.view = SimpleNamespace(onLogin=Mock())
        self.value = {'username': 'own@example.test', 'password': 'owned-unit-secret-987', 'submit_via': 'python',
                      'verify_crew_recruitment': True, 'crew_recruitment_mode': 'recruit',
                      'quit_when': 'crew_recruitment_observed'}

    def consume(self, value):
        self.path.write_text(json.dumps(value))
        with patch.dict(sys.modules, {'p04d_crew_ui': self.scenario}):
            self.ns['consume_control'](self.view)

    def test_explicit_recruit_arms_once_before_original_login_and_redacts(self):
        self.consume(self.value)
        self.assertFalse(self.path.exists())
        self.scenario.NativeScenario.assert_called_once_with(self.ns['record'], 'recruit', expected=None,
                                                            settings=self.ns['_settings'])
        self.view.onLogin.assert_called_once_with(self.value['username'], self.value['password'], '127.0.0.1:20014')
        self.ns['consume_control'](self.view)
        self.assertEqual(self.view.onLogin.call_count, 1)
        public = json.dumps((self.events, self.ns['_control']))
        for forbidden in (self.value['password'], self.value['username'], 'crew_recruitment_expected'):
            self.assertNotIn(forbidden, public)

    def test_relogin_binds_exact_prior_snapshot_and_keeps_it_out_of_control_metadata(self):
        expected = transition()[1]
        value = dict(self.value, crew_recruitment_mode='relogin', crew_recruitment_expected=expected)
        self.consume(value)
        self.scenario.checked_expected.assert_called_once_with(expected)
        self.scenario.NativeScenario.assert_called_once_with(self.ns['record'], 'relogin', expected=expected,
                                                            settings=self.ns['_settings'])
        self.assertNotIn('crew_recruitment_expected', self.ns['_control'])

    def test_modes_missing_mixed_or_unsupported_inputs_reject_before_arm_and_login(self):
        cases = [dict(self.value, **changes) for changes in (
            {'verify_crew_recruitment': 1}, {'verify_ms1_crew': True}, {'verify_p09d_ammo': True},
            {'crew_recruitment_mode': 'paid'}, {'crew_recruitment_mode': 'relogin'},
            {'crew_recruitment_expected': transition()[1]}, {'quit_when': None},
            {'quit_after_seconds': 10}, {'screenshot_when': 'hangar'}, {'submit_via': 'flash'},
            {'quit_when': 'ms1_crew_observed'}, {'extra': True}, {'username': 'invalid'}, {'password': None})]
        for key in ('crew_recruitment_mode', 'username', 'password'):
            row = dict(self.value)
            del row[key]
            cases.append(row)
        for value in cases:
            with self.subTest(keys=list(value)):
                with self.assertRaises(ValueError):
                    self.consume(value)
                self.scenario.NativeScenario.assert_not_called()
                self.view.onLogin.assert_not_called()

    def test_feature_pair_required_and_ordinary_control_stays_inert(self):
        for feature in ('enable_crew_recruitment', 'enable_p09d_ammo_service'):
            self.ns['_settings'][feature] = False
            with self.assertRaises(ValueError):
                self.consume(self.value)
            self.ns['_settings'][feature] = True
        self.consume({'username': self.value['username'], 'password': self.value['password']})
        self.scenario.NativeScenario.assert_not_called()
        self.scenario.checked_expected.assert_not_called()

    def test_mode_without_operation_is_rejected(self):
        value = dict(self.value)
        del value['verify_crew_recruitment']
        del value['quit_when']
        with self.assertRaises(ValueError):
            self.consume(value)


class InstallerTests(unittest.TestCase):
    def test_actual_prepare_rejects_wrong_copy_service_or_arena_before_artifact_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            paths = dict(local_artifacts_root=base, original_client_root=base / 'original',
                         research_client_root=base / 'shared-research')
            for copy, ammo, shared, arena in ((None, True, False, False), ('copy', False, False, False),
                                               ('copy', True, True, False), ('copy', True, False, True)):
                args = SimpleNamespace(out=str(base / 'prepare'), research_copy=copy,
                                       enable_p09d_ammo_service=ammo, enable_shared_lab=shared,
                                       enable_map_drive=arena, enable_crew_recruitment=True)
                with patch.object(installer, 'config', return_value=({}, paths)), \
                        patch('shared_client_copy.checked_copy', return_value=(base / 'own-copy', {'owned': True})):
                    with self.assertRaisesRegex(ValueError, 'native hangar|isolated copy'):
                        installer.prepare(args)
                self.assertFalse((base / 'prepare').exists())

    def test_correct_owned_hangar_options_reach_existing_endpoint_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            paths = dict(local_artifacts_root=base, original_client_root=base / 'original',
                         research_client_root=base / 'shared-research')
            args = SimpleNamespace(out=str(base / 'prepare'), research_copy='copy', endpoint='not-loopback', registration_url=None,
                                   enable_p09d_ammo_service=True, enable_shared_lab=False,
                                   enable_map_drive=False, enable_crew_recruitment=True)
            with patch.object(installer, 'config', return_value=({}, paths)), \
                    patch('shared_client_copy.checked_copy', return_value=(base / 'own-copy', {'owned': True})):
                with self.assertRaisesRegex(ValueError, 'numeric IPv4 loopback'):
                    installer.prepare(args)
            self.assertFalse((base / 'prepare').exists())
        self.assertEqual(installer.MODULES.count('p04d_crew_ui'), 1)
        self.assertEqual(len(installer.MODULES), len(set(installer.MODULES)))


class FailureBoundaryTests(unittest.TestCase):
    def test_trace_limit_fails_and_quits_p04d_instead_of_stopping_observation_silently(self):
        events, quit_client = [], Mock()
        namespace = {'_fini': False, '_observations': 0,
                     '_stream': SimpleNamespace(tell=lambda: 16 * 1024 * 1024 + 1),
                     'observation_byte_limit': lambda: 16 * 1024 * 1024,
                     'sys': SimpleNamespace(setprofile=Mock()),
                     '_control': {'verify_crew_recruitment': True, 'quit_when': 'crew_recruitment_observed'},
                     'record': lambda event, **fields: events.append((event, fields)),
                     'quit_client': quit_client}
        functions({'observe'}, namespace)
        namespace['observe']()
        quit_client.assert_called_once_with()
        self.assertEqual(events[-1], ('diagnostic_condition_failed', {'condition': 'crew_recruitment_observed'}))


if __name__ == '__main__':
    unittest.main()
