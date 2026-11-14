"""Bounded passive #717 markers; no native client or UI is simulated here."""
import ast
import hashlib
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'client_patch/hangar_latency_trace.py'


def load_observer():
    spec = importlib.util.spec_from_file_location('hangar_latency_trace_test', SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Poison:
    def __repr__(self):
        raise AssertionError('unneeded data must not be inspected')


class HangarLatencyTrace(unittest.TestCase):
    def setUp(self):
        self.module = load_observer()
        self.body = b'test code bytes'
        self.digest = hashlib.sha256(self.body).hexdigest()
        self.module._PINS = {name: (line, self.digest) for name, (line, _) in self.module._PINS.items()}
        self.records = []

    def record(self, event, **fields):
        self.records.append((event, fields))

    def frame(self, method, **values):
        line = self.module._PINS[method][0]
        code = SimpleNamespace(co_filename='scripts/client/Account.py', co_name=method,
                               co_firstlineno=line, co_code=self.body)
        return SimpleNamespace(f_code=code, f_locals=values)

    def test_commands_return_only_and_never_expose_arguments(self):
        for i, command in enumerate((105, 201, 301, 302, 303, 308), 1):
            frame = self.frame('__doCmd', cmd=command, requestID=i,
                               args=Poison(), password=Poison())
            frame.f_locals['self'] = Poison()
            self.module.observe(frame, 'call', self.record)
            self.module.observe(frame, 'return', self.record)
        self.assertEqual(len(self.records), 6)
        for i, (event, fields) in enumerate(self.records, 1):
            self.assertEqual(event, 'hangar_latency_native')
            self.assertEqual(fields, {'method': '__doCmd', 'phase': 'return',
                                      'command': (105, 201, 301, 302, 303, 308)[i-1], 'request_id': i})

    def test_update_and_callback_only_copy_bounded_primitives(self):
        update = self.frame('_update', diff={'rev': 13, 'prevRev': 12, 'inventory': Poison()})
        self.module.observe(update, 'return', self.record)
        callback = self.frame('onCmdResponseExt', requestID=11, resultID=0, ext=Poison())
        self.module.observe(callback, 'call', self.record)
        self.module.observe(callback, 'return', self.record)
        self.assertEqual(self.records[0][1], {'method': '_update', 'phase': 'return',
                                             'revision': 13, 'previous_revision': 12})
        self.assertEqual(self.records[-1][1], {'method': 'onCmdResponseExt', 'phase': 'return',
                                              'request_id': 11, 'result_id': 0})

    def test_plain_callback_is_source_pinned_and_excludes_error_and_payload(self):
        frame = self.frame('onCmdResponse', requestID=226, resultID=0,
                           errorStr=Poison(), ext=Poison(), args=Poison())
        self.module.observe(frame, 'call', self.record)
        self.module.observe(frame, 'return', self.record)
        self.assertEqual(self.records, [
            ('hangar_latency_native', {'method': 'onCmdResponse', 'phase': 'call',
                                       'request_id': 226, 'result_id': 0}),
            ('hangar_latency_native', {'method': 'onCmdResponse', 'phase': 'return',
                                       'request_id': 226, 'result_id': 0}),
        ])

    def test_plain_callback_pin_mismatch_disables_only_diagnostic(self):
        frame = self.frame('onCmdResponse', requestID=226, resultID=0)
        frame.f_code.co_code = b'wrong'
        self.module.observe(frame, 'return', self.record)
        self.assertEqual(self.records[0][0], 'hangar_latency_trace_source_mismatch')
        self.assertEqual(self.records[0][1]['method'], 'onCmdResponse')
        self.assertTrue(self.records[0][1]['observer_disabled'])

    def test_unknown_request_id_and_invalid_values_never_invent_success(self):
        self.module.observe(self.frame('__doCmd', cmd=201, requestID=Poison()), 'return', self.record)
        self.module.observe(self.frame('onCmdResponseExt', requestID=True, resultID=Poison()), 'return', self.record)
        self.assertIsNone(self.records[0][1]['request_id'])
        self.assertIsNone(self.records[1][1]['request_id'])
        self.assertIsNone(self.records[1][1]['result_id'])

    def test_wrong_source_pin_is_reported_without_raising_and_disables_observer(self):
        frame = self.frame('__doCmd', cmd=201, requestID=1)
        frame.f_code.co_filename = 'other/Account.py'
        self.module.observe(frame, 'return', self.record)
        self.assertEqual(self.records, [])
        frame.f_code.co_filename = 'scripts/client/Account.py'
        frame.f_code.co_code = b'wrong'
        self.module.observe(frame, 'return', self.record)
        self.assertEqual(self.records[0][0], 'hangar_latency_trace_source_mismatch')
        self.assertTrue(self.records[0][1]['observer_disabled'])
        frame.f_code.co_code = self.body
        self.module.observe(frame, 'return', self.record)
        self.assertEqual(len(self.records), 1)

    def test_limit_reports_truncation_once(self):
        self.module._MAX_EVENTS = 1
        frame = self.frame('__doCmd', cmd=201, requestID=1)
        for _ in range(3):
            self.module.observe(frame, 'return', self.record)
        self.assertEqual([event for event, _ in self.records],
                         ['hangar_latency_native', 'hangar_latency_trace_truncated'])

    def test_profiler_hook_is_explicitly_opt_in(self):
        source = (ROOT / 'client_patch/native_call_trace.py').read_text(encoding='utf-8')
        self.assertIn("_host._settings.get('trace_native_calls') is True", source)
        self.assertIn('hangar_latency_trace.observe(frame, phase, _host.record)', source)

    def profiler(self, enabled):
        source = (ROOT / 'client_patch/native_call_trace.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                  and node.name == 'profile_calls')
        host = SimpleNamespace(_settings={'trace_native_calls': enabled}, _control=None,
                               record=self.record)
        namespace = {'_host': host, '_profile_call_id': 0, '_profile_frames': {}}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), '<profile_calls>', 'exec'), namespace)
        return namespace['profile_calls']

    def test_pin_mismatch_does_not_interrupt_existing_account_profiler(self):
        profile = self.profiler(True)
        frame = self.frame('_update', diff={})
        frame.f_code.co_code = b'wrong'
        frame.f_lasti = 0
        frame.f_back = None
        with patch.dict(sys.modules, {'hangar_latency_trace': self.module}):
            profile(frame, 'call', None)
            profile(frame, 'return', None)
        self.assertEqual([event for event, _ in self.records],
                         ['hangar_latency_trace_source_mismatch',
                          'native_account_call', 'native_account_call'])

    def test_ordinary_profile_does_not_activate_the_observer(self):
        profile = self.profiler(False)
        frame = self.frame('_update', diff={})
        frame.f_lasti = 0
        frame.f_back = None
        def forbidden(*args):
            raise AssertionError('observer must stay disabled')
        with patch.dict(sys.modules, {'hangar_latency_trace': SimpleNamespace(observe=forbidden)}):
            profile(frame, 'call', None)
            profile(frame, 'return', None)
        self.assertEqual([event for event, _ in self.records], ['native_account_call'] * 2)

    def test_plain_callback_is_forwarded_by_opt_in_profiler(self):
        profile = self.profiler(True)
        frame = self.frame('onCmdResponse', requestID=226, resultID=0, errorStr=Poison())
        frame.f_lasti = 0
        frame.f_back = None
        with patch.dict(sys.modules, {'hangar_latency_trace': self.module}):
            profile(frame, 'call', None)
            profile(frame, 'return', None)
        rows = [row for name, row in self.records if name == 'hangar_latency_native']
        self.assertEqual([row['phase'] for row in rows], ['call', 'return'])
        self.assertEqual([row['request_id'] for row in rows], [226, 226])
        self.assertTrue(all('errorStr' not in row for row in rows))


if __name__ == '__main__':
    unittest.main()
