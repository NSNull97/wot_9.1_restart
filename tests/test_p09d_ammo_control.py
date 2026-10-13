"""Explicit control dispatch and redaction, with no real client launch."""
import ast
import io
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
from tests.test_p09d_ammo_scenario import expected


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
        self.ns = {'os':os, 'json':json, '_control_done':False, 'owned':lambda path, root:path,
            '_settings':{'test_control':str(self.path), 'local_root':self.temp.name,
                         'endpoint':'127.0.0.1:20014', 'enable_p09d_ammo_service':True},
            'record':lambda e, **f:self.events.append((e,f))}
        functions({'consume_control'}, self.ns)
        self.scenario = SimpleNamespace(checked_expected=Mock(side_effect=lambda v:v), arm=Mock())
        self.view = SimpleNamespace(onLogin=Mock())
        self.value = {'username':'own@example.test', 'password':'owned-unit-secret-987', 'submit_via':'python',
                      'verify_p09d_ammo':True, 'p09d_ammo_expected':expected(), 'quit_when':'p09d_ammo_observed'}

    def consume(self, value):
        self.path.write_text(json.dumps(value))
        with patch.dict(sys.modules, {'p09d_ammo_scenario':self.scenario}):
            self.ns['consume_control'](self.view)

    def test_explicit_native_login_arms_once_removes_input_and_logs_no_secrets(self):
        self.consume(self.value)
        self.assertFalse(self.path.exists())
        self.scenario.arm.assert_called_once_with(self.value['p09d_ammo_expected'])
        self.view.onLogin.assert_called_once_with(self.value['username'], self.value['password'], '127.0.0.1:20014')
        self.ns['consume_control'](self.view)
        self.assertEqual(self.view.onLogin.call_count, 1)
        public = json.dumps((self.events, self.ns['_control']))
        self.assertNotIn(self.value['password'], public)
        self.assertNotIn(self.value['username'], public)
        self.assertNotIn('p09d_ammo_expected', self.ns['_control'])

    def test_bad_modes_missing_or_extra_fields_fail_before_arm_or_login(self):
        cases = [dict(self.value, **changes) for changes in (
            {'verify_p09d_ammo':1}, {'verify_ms1_ammo':True}, {'quit_when':None},
            {'quit_after_seconds':10}, {'screenshot_when':'hangar'}, {'submit_via':'flash'},
            {'quit_when':'ms1_ammo_observed'}, {'extra':True})]
        for key in ('p09d_ammo_expected','username','password'):
            row = dict(self.value); del row[key]; cases.append(row)
        for value in cases:
            with self.subTest(keys=list(value)):
                with self.assertRaises(ValueError): self.consume(value)
                self.scenario.arm.assert_not_called(); self.view.onLogin.assert_not_called()

    def test_feature_required_and_normal_control_stays_inert(self):
        self.ns['_settings']['enable_p09d_ammo_service'] = False
        with self.assertRaises(ValueError): self.consume(self.value)
        self.scenario.arm.assert_not_called()
        self.consume({'username':self.value['username'], 'password':self.value['password']})
        self.scenario.arm.assert_not_called()

    def test_expectation_requires_diagnostic_flag(self):
        value = dict(self.value); del value['verify_p09d_ammo']; del value['quit_when']
        with self.assertRaises(ValueError): self.consume(value)


class PassiveDispatchTests(unittest.TestCase):
    def test_log_first_then_native_only_dispatch_handles_partial_module(self):
        stream = io.StringIO()
        modules = {}
        namespace = {'json':json, 'time':SimpleNamespace(clock=lambda:1), '_clock':0, '_stream':stream,
                     'sys':SimpleNamespace(modules=modules)}
        functions({'record'}, namespace)
        namespace['record']('unrelated', secret='test-only-not-a-credential')
        modules['p09d_ammo_scenario'] = SimpleNamespace()
        namespace['record']('p09d_native_ammo_call', method='update')
        seen = []
        modules['p09d_ammo_scenario'].native_event = lambda f:seen.append((dict(f), stream.getvalue()))
        namespace['record']('p09d_native_ammo_call', method='_update')
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0][0]['method'], '_update')
        self.assertIn('"method": "_update"', seen[0][1])


if __name__ == '__main__': unittest.main()
