"""Runner lifecycle tests use owned temporary files and simulated child handles.

They do not install or launch a client and do not prove native compatibility.
"""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import manual_client_run as runner


class ManualClientRunTests(unittest.TestCase):
    def setUp(self):
        temp_root = ROOT / 'local/test-runs'
        temp_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='manual-run-', dir=temp_root)
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name).resolve()
        self.local = base / 'artifacts'
        self.original, self.research = base / 'original', base / 'research'
        self.out = self.local / 'install'
        self.trace, self.profile = self.local / 'trace', self.local / 'profile'
        self.run_dir = self.local / 'server/run-001'
        self.wire = self.run_dir / 'wire'
        for directory in (self.original, self.research, self.out / 'bundle',
                          self.trace / 'screenshots', self.profile, self.wire):
            directory.mkdir(parents=True)
        (self.research / 'WorldOfTanks.exe').write_bytes(b'non-executable test fixture')
        self.service = self.run_dir.parent / 'service.json'
        self.service.write_text('{}', encoding='utf-8')
        self.state = {'run_dir': str(self.run_dir), 'status': 'RUNNING', 'native_wire_capture': True}
        self.put(self.run_dir.parent / 'state.json', self.state)
        (self.run_dir / 'gateway.stdout.log').write_bytes(b'before\n')
        (self.wire / 'packets.jsonl').write_bytes(b'{"event":"capture_started"}\n')
        self.settings = {'schema_version': 1, 'endpoint': '127.0.0.1:20014',
            'profile_dir': str(self.profile), 'trace_dir': str(self.trace),
            'screenshot_dir': str(self.trace / 'screenshots'), 'local_root': str(self.local),
            'preferences_resource': 'sr_preferences.xml', 'test_control': None,
            'capture_hangar': False, 'capture_ui_passive': True}
        self.plan = {'schema_version': 1, 'mode': 'interactive',
            'research_root': str(self.research), 'original_root': str(self.original),
            'settings': self.settings, 'normal_auto_login': False, 'normal_auto_quit': False}
        self.paths = {'original_client_root': self.original, 'research_client_root': self.research,
                      'local_artifacts_root': self.local}
        self.write_plan()

    @staticmethod
    def put(path, value):
        path.write_text(json.dumps(value), encoding='utf-8')

    def write_plan(self):
        self.put(self.out / 'install-plan.json', self.plan)
        self.put(self.out / 'bundle/sr_interactive_settings.json', self.settings)

    def prepare(self):
        return runner.prepare(str(self.out), str(self.service), self.paths)

    def packet(self, name='packet-000000-client_to_server.bin', data=b'abcd', index=0):
        (self.wire / name).write_bytes(data)
        row = {'event': 'packet', 'index': index, 'bytes': len(data), 'file': name,
               'channel': 'login', 'direction': 'client_to_server', 'elapsed_seconds': 1.0}
        self.append_manifest(row)

    def append_manifest(self, row):
        with (self.wire / 'packets.jsonl').open('ab') as stream:
            stream.write(json.dumps(row).encode() + b'\n')

    def execute(self, context, child=None, install_effect=None, spawn_error=None):
        if child is None:
            child = Mock(pid=123, spec=['pid', 'wait', 'poll'])
            child.wait.return_value = 0
            child.poll.return_value = 0
        installer = Mock(side_effect=install_effect) if install_effect else Mock(return_value=0)
        with patch.object(runner, 'installer', installer), \
                patch.object(runner, 'observe', return_value={'exists': False}), \
                patch.object(runner, 'spawn', side_effect=spawn_error, return_value=child) as spawn, \
                contextlib.redirect_stdout(io.StringIO()):
            result = runner.run(context)
        return result, child, installer, spawn

    def test_user_exit_wait_has_no_timeout_and_restores(self):
        context = self.prepare()
        self.packet()
        result, child, installer, _ = self.execute(context)
        child.wait.assert_called_once_with()
        self.assertEqual([c.args[0] for c in installer.call_args_list], ['install', 'rollback'])
        self.assertEqual(result['process_status'], 'PASS')
        self.assertEqual(result['exit_code'], 0)
        self.assertFalse(result['timed_out'])
        self.assertEqual(result['wire_packets'], 1)
        self.assertTrue((self.out / 'native-process.json').is_file())
        self.assertTrue((self.out / 'native-outcome.json').is_file())
        capture = json.loads((self.out / 'wire/capture.json').read_text())
        self.assertEqual(capture['packets'][0]['sha256'], runner.sha256(self.wire / 'packet-000000-client_to_server.bin'))

    def test_crash_exit_is_fail_and_still_restores(self):
        child = Mock(pid=123, spec=['pid', 'wait', 'poll'])
        child.wait.return_value = child.poll.return_value = 3221225477
        result, _, installer, _ = self.execute(self.prepare(), child)
        self.assertEqual(result['process_status'], 'FAIL')
        self.assertEqual(result['restore'], 'PASS')
        self.assertEqual(installer.call_args.args[0], 'rollback')

    def test_keyboard_interrupt_preserves_live_client_and_install(self):
        child = Mock(pid=123, spec=['pid', 'wait', 'poll'])
        child.wait.side_effect = KeyboardInterrupt()
        child.poll.return_value = None
        result, _, installer, _ = self.execute(self.prepare(), child)
        self.assertEqual(installer.call_count, 1)
        self.assertEqual(result['harness_exit_code'], 130)
        self.assertTrue(result['restore_pending'])
        self.assertEqual(result['restore'], 'NOT_RUN')
        self.assertTrue((self.out / 'native-run-interrupted.json').is_file())
        self.assertFalse((self.out / 'native-outcome.json').exists())
        self.assertFalse((self.out / 'wire').exists())

    def test_wait_error_preserves_live_client_without_rollback(self):
        child = Mock(pid=123, spec=['pid', 'wait', 'poll'])
        child.wait.side_effect = OSError('wait failed')
        child.poll.return_value = None
        result, _, installer, _ = self.execute(self.prepare(), child)
        self.assertEqual(installer.call_count, 1)
        self.assertEqual(result['process_status'], 'NOT_RUN')
        self.assertEqual(result['harness_exit_code'], 1)

    def test_capture_error_does_not_hide_failure_or_prevent_restore(self):
        context = self.prepare()
        self.append_manifest({'event': 'packet', 'index': 0, 'bytes': 4, 'file': '../escape.bin'})
        result, _, installer, _ = self.execute(context)
        self.assertEqual(result['process_status'], 'FAIL')
        self.assertEqual(result['capture_status'], 'FAIL')
        self.assertEqual(result['restore'], 'PASS')
        self.assertIn('unsafe', result['capture_error'])
        self.assertEqual(installer.call_args.args[0], 'rollback')

    def test_spawn_failure_after_install_restores(self):
        result, _, installer, _ = self.execute(self.prepare(), spawn_error=OSError('spawn failed'))
        self.assertFalse(result['client_started'])
        self.assertEqual(result['process_status'], 'FAIL')
        self.assertEqual(result['restore'], 'PASS')
        self.assertEqual([c.args[0] for c in installer.call_args_list], ['install', 'rollback'])

    def test_partial_failed_install_with_ledger_restores(self):
        def install(operation, out):
            if operation == 'install':
                self.put(out / 'patch-ledger.json', {'test_only': True})
                return 1
            return 0
        result, _, installer, spawn = self.execute(self.prepare(), install_effect=install)
        spawn.assert_not_called()
        self.assertEqual(result['restore'], 'PASS')
        self.assertEqual(result['process_status'], 'FAIL')
        self.assertEqual(installer.call_args.args[0], 'rollback')

    def test_mutex_checked_after_install_immediately_before_spawn(self):
        context = self.prepare()
        events = []
        def install(operation, out):
            events.append(operation)
            return 0
        def mutex():
            events.append('observe')
            return {'exists': True}
        with patch.object(runner, 'installer', side_effect=install), \
                patch.object(runner, 'observe', side_effect=mutex), \
                patch.object(runner, 'spawn') as spawn:
            result = runner.run(context)
        spawn.assert_not_called()
        self.assertEqual(events, ['install', 'observe', 'rollback'])
        self.assertEqual(result['process_status'], 'FAIL')

    def test_capture_limit_is_fail_even_after_clean_exit(self):
        context = self.prepare()
        self.append_manifest({'event': 'capture_limit'})
        result, _, _, _ = self.execute(context)
        self.assertEqual(result['process_status'], 'FAIL')
        self.assertEqual(result['restore'], 'PASS')
        self.assertTrue(json.loads((self.out / 'wire/capture.json').read_text())['limit_reached'])

    def test_gateway_span_budget_is_bounded_and_restore_runs(self):
        context = self.prepare()
        with (self.run_dir / 'gateway.stdout.log').open('ab') as stream:
            stream.write(b'x' * (runner.MAX_LOG + 1))
        result, _, _, _ = self.execute(context)
        self.assertEqual(result['process_status'], 'FAIL')
        self.assertEqual(result['restore'], 'PASS')
        self.assertIn('bounded capture', result['capture_error'])
        self.assertFalse((self.out / 'gateway-span.log').exists())

    def test_control_autologin_autoquit_are_rejected_before_install(self):
        for key in ('normal_auto_login', 'normal_auto_quit'):
            with self.subTest(key=key):
                self.plan[key] = True
                self.write_plan()
                with self.assertRaisesRegex(ValueError, 'forbids'):
                    self.prepare()
                self.plan[key] = False
        self.settings['test_control'] = str(self.local / 'control.json')
        self.write_plan()
        with self.assertRaisesRegex(ValueError, 'forbids'):
            self.prepare()

    def test_reused_evidence_and_root_escape_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'escaped'):
            runner.within(self.original, self.local)
        self.put(self.out / 'native-outcome.json', {})
        with self.assertRaisesRegex(ValueError, 'unused'):
            self.prepare()

    def test_manifest_bounds_count_and_bytes(self):
        path = self.wire / 'packets.jsonl'
        with patch.object(runner, 'MAX_MANIFEST', 2):
            with self.assertRaisesRegex(ValueError, 'large'):
                runner.manifest(path)
        self.packet()
        with patch.object(runner, 'MAX_PACKETS', 0):
            with self.assertRaisesRegex(ValueError, 'budget'):
                runner.manifest(path)
        with patch.object(runner, 'MAX_PACKET_BYTES', 3):
            with self.assertRaisesRegex(ValueError, 'budget'):
                runner.manifest(path)

    def test_cli_does_not_accept_timeout(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            runner.main(['--install', 'unused', '--service', 'unused', '--timeout', '90'])
        self.assertEqual(error.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
