"""P04G one-shot opt-in validation; no native launch, command or client mutation."""
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
import p04g_crew_ui
from tests.test_p04d_crew_control import functions
from tests.test_p04g_crew_ui import snapshot


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path, self.events = Path(self.temp.name) / 'control.json', []
        self.ns = {'os': os, 'json': json, '_control_done': False, '_p04g_scenario': None,
                   'owned': lambda path, root: path,
                   '_settings': {'test_control': str(self.path), 'local_root': self.temp.name,
                                 'endpoint': '127.0.0.1:20014', 'enable_p09d_ammo_service': True,
                                 'enable_crew_recruitment': True, 'enable_crew_transfer': True, 'enable_cross_vehicle_crew': True},
                   'record': lambda event, **fields: self.events.append((event, fields))}
        functions({'consume_control'}, self.ns)
        self.module = SimpleNamespace(checked_expected=Mock(side_effect=p04g_crew_ui.checked_expected),
                                      NativeScenario=Mock())
        self.view = SimpleNamespace(onLogin=Mock())
        self.value = {'username': 'own@example.test', 'password': 'owned-unit-secret-987', 'submit_via': 'python',
                      'verify_cross_vehicle_crew': True, 'cross_vehicle_crew_mode': 'transfer',
                      'cross_vehicle_crew_expected': snapshot(), 'quit_when': 'cross_vehicle_crew_observed'}

    def consume(self, value):
        self.path.write_text(json.dumps(value))
        with patch.dict(sys.modules, {'p04g_crew_ui': self.module}):
            self.ns['consume_control'](self.view)

    def test_explicit_transfer_arms_once_before_original_login_and_redacts(self):
        self.consume(self.value)
        self.assertFalse(self.path.exists())
        self.module.NativeScenario.assert_called_once_with(self.ns['record'], 'transfer',
            expected=self.value['cross_vehicle_crew_expected'], settings=self.ns['_settings'])
        self.view.onLogin.assert_called_once_with(self.value['username'], self.value['password'], '127.0.0.1:20014')
        self.ns['consume_control'](self.view)
        self.assertEqual(self.view.onLogin.call_count, 1)
        public = json.dumps((self.events, self.ns['_control']))
        for forbidden in (self.value['username'], self.value['password'], 'cross_vehicle_crew_expected'):
            self.assertNotIn(forbidden, public)

    def test_fresh_login_accepts_source_validated_vacant_seat_expectation(self):
        expected = p04g_crew_ui.projected_transfer(snapshot(), 1, 0, -1)
        self.consume(dict(self.value, cross_vehicle_crew_mode='relogin', cross_vehicle_crew_expected=expected))
        self.module.NativeScenario.assert_called_once_with(self.ns['record'], 'relogin', expected=expected,
                                                           settings=self.ns['_settings'])

    def test_mixed_modes_unsupported_flags_and_missing_expectations_reject_before_login(self):
        cases = [dict(self.value, **changes) for changes in (
            {'verify_cross_vehicle_crew': 1}, {'verify_crew_recruitment': True}, {'verify_p09d_ammo': True},
            {'cross_vehicle_crew_mode': 'paid'}, {'cross_vehicle_crew_expected': None}, {'quit_when': None},
            {'quit_after_seconds': 10}, {'screenshot_when': 'hangar'}, {'submit_via': 'flash'},
            {'quit_when': 'crew_recruitment_observed'}, {'username': 'invalid'}, {'password': None})]
        for key in ('cross_vehicle_crew_expected', 'cross_vehicle_crew_mode', 'username', 'password'):
            value = dict(self.value)
            del value[key]
            cases.append(value)
        for value in cases:
            with self.subTest(keys=list(value)), self.assertRaises(ValueError):
                self.consume(value)
            self.module.NativeScenario.assert_not_called()
            self.view.onLogin.assert_not_called()

    def test_previous_transfer_diagnostic_cannot_run_with_cross_vehicle_policy_installed(self):
        value = {k: v for k, v in self.value.items() if not k.startswith('cross_vehicle_crew')
                 and k != 'verify_cross_vehicle_crew'}
        value.update(verify_crew_transfer=True, crew_transfer_mode='transfer',
                     crew_transfer_expected=self.value['cross_vehicle_crew_expected'], quit_when='crew_transfer_observed')
        with self.assertRaises(ValueError):
            self.consume(value)
        self.view.onLogin.assert_not_called()

    def test_all_four_explicit_features_are_required_and_plain_login_is_inert(self):
        for key in ('enable_cross_vehicle_crew', 'enable_crew_transfer', 'enable_crew_recruitment', 'enable_p09d_ammo_service'):
            self.ns['_settings'][key] = False
            with self.assertRaises(ValueError):
                self.consume(self.value)
            self.ns['_settings'][key] = True
        self.consume({'username': self.value['username'], 'password': self.value['password']})
        self.module.NativeScenario.assert_not_called()

    def test_mode_or_expectation_without_operation_rejects(self):
        value = dict(self.value)
        del value['verify_cross_vehicle_crew']
        del value['quit_when']
        with self.assertRaises(ValueError):
            self.consume(value)

    def test_trace_budget_failure_quits_instead_of_silently_losing_transfer_evidence(self):
        events, quit_client = [], Mock()
        namespace = {'_fini': False, '_observations': 0,
                     '_stream': SimpleNamespace(tell=lambda: 16 * 1024 * 1024 + 1),
                     'observation_byte_limit': lambda: 16 * 1024 * 1024,
                     'sys': SimpleNamespace(setprofile=Mock()),
                     '_control': {'verify_cross_vehicle_crew': True, 'quit_when': 'cross_vehicle_crew_observed'},
                     'record': lambda event, **fields: events.append((event, fields)),
                     'quit_client': quit_client}
        functions({'observe'}, namespace)
        namespace['observe']()
        quit_client.assert_called_once_with()
        self.assertEqual(events[-1][0], 'diagnostic_condition_failed')


class InstallerTests(unittest.TestCase):
    def test_wrong_feature_copy_or_arena_rejects_before_artifact_creation(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            paths = dict(local_artifacts_root=base, original_client_root=base / 'original', research_client_root=base / 'other')
            for copy, ammo, recruit, shared, arena in ((None, True, True, False, False), ('copy', True, False, False, False),
                ('copy', False, True, False, False), ('copy', True, True, True, False), ('copy', True, True, False, True)):
                args = SimpleNamespace(out=str(base / 'prepare'), research_copy=copy,
                    enable_p09d_ammo_service=ammo, enable_crew_recruitment=recruit, enable_cross_vehicle_crew=True, enable_crew_transfer=True,
                    enable_shared_lab=shared, enable_map_drive=arena)
                with patch.object(installer, 'config', return_value=({}, paths)), \
                        patch('shared_client_copy.checked_copy', return_value=(base / 'own-copy', {'owned': True})):
                    with self.assertRaises(ValueError):
                        installer.prepare(args)
                self.assertFalse((base / 'prepare').exists())
        self.assertEqual(installer.MODULES.count('p04g_crew_ui'), 1)
        self.assertEqual(len(installer.MODULES), len(set(installer.MODULES)))


if __name__ == '__main__':
    unittest.main()
