"""One-shot runner guards and process lifetime using isolated unit fixtures.

The dummy bytecode/executable and simulated child handles never run. These
tests prove harness decisions only, not native compilation or compatibility.
"""
import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import diagnostic_client_run as runner
import test_manual_client_run as manual_tests


class DiagnosticClientRunTests(unittest.TestCase):
    put = staticmethod(manual_tests.ManualClientRunTests.put)
    write_plan = manual_tests.ManualClientRunTests.write_plan
    packet = manual_tests.ManualClientRunTests.packet
    append_manifest = manual_tests.ManualClientRunTests.append_manifest

    def setUp(self):
        manual_tests.ManualClientRunTests.setUp(self)
        self.project = self.local / 'project'
        (self.project / 'tools').mkdir(parents=True)
        (self.project / 'client_patch').mkdir()
        self.modules = ('sr_interactive', 'project_auth', 'project_preferences',
                        'hangar_bootstrap', 'hangar_ui_probe', 'hangar_capabilities',
                        'crew_capabilities', 'ms1_crew_probe', 'ms1_crew_scenario')
        (self.project / 'tools/interactive_client.py').write_text(
            'MODULES = ' + repr(self.modules) + '\n', encoding='utf-8')
        (self.out / 'compiled').mkdir()
        self.plan['sources'], self.plan['files'] = [], []
        for module in self.modules:
            source = self.project / 'client_patch' / (module + '.py')
            source.write_text('# isolated unit fixture: ' + module + '\n', encoding='utf-8')
            pyc = self.out / 'compiled' / (module + '.pyc')
            pyc.write_bytes(bytes.fromhex('03f30d0a') + b'unit fixture, never executed')
            self.put(self.out / 'compiled' / (module + '.json'), {
                'compiler': '2.7.3 unit test metadata, not actual compilation',
                'source': module + '.py', 'source_sha256': runner.sha256(source),
                'pyc_sha256': runner.sha256(pyc), 'magic': '03f30d0a', 'source_executed': False})
            target = 'res_mods/0.9.1/scripts/client/' + module + '.pyc'
            bundle = self.out / 'bundle' / target
            bundle.parent.mkdir(parents=True, exist_ok=True)
            bundle.write_bytes(pyc.read_bytes())
            self.plan['sources'].append({'path': 'client_patch/' + module + '.py',
                'compiled': str(Path('compiled') / (module + '.pyc')),
                'metadata': str(Path('compiled') / (module + '.json')),
                'sha256': runner.sha256(source)})
            self.plan['files'].append({'path': target, 'runtime_mutable': False,
                'installed_sha256': runner.sha256(pyc), 'bytes': pyc.stat().st_size})
        self.control = self.local / 'one-shot.json'
        self.control_value = {'export_ms1_crew': True, 'quit_when': 'ms1_crew_exported'}
        self.put(self.control, self.control_value)
        self.settings['test_control'] = str(self.control)
        self.write_plan()

    def prepare(self):
        return runner.prepare(str(self.out), str(self.service), self.paths, self.project)

    def execute(self, context, child=None, install_effect=None, spawn_error=None, mutex=False):
        if child is None:
            child = Mock(pid=123, spec=['pid', 'wait', 'poll'])
            child.wait.return_value = child.poll.return_value = 0
        installer = Mock(side_effect=install_effect) if install_effect else Mock(return_value=0)
        with patch.object(runner.manual, 'installer', installer), \
                patch.object(runner, 'observe', return_value={'exists': mutex}), \
                patch.object(runner.manual, 'spawn', side_effect=spawn_error, return_value=child) as spawn, \
                contextlib.redirect_stdout(io.StringIO()):
            result = runner.run(context)
        return result, child, installer, spawn

    def test_exact_condition_and_provenance_preflight(self):
        context = self.prepare()
        self.assertEqual(context['control']['quit_when'], 'ms1_crew_exported')
        self.assertFalse(context['control']['credentials_present'])
        self.assertEqual(len(context['source_provenance']['modules']), 9)
        self.assertEqual(context['plan_sha256'], runner.sha256(self.out / 'install-plan.json'))

    def test_credentials_preserve_exact_unicode_bytes_but_evidence_is_redacted(self):
        password = '  exact Пробелы Пароль  '
        self.control_value.update(username='test@example.invalid', password=password, submit_via='flash')
        self.put(self.control, self.control_value)
        original = self.control.read_bytes()
        metadata = self.prepare()['control']
        self.assertTrue(metadata['credentials_present'])
        self.assertFalse(metadata['plaintext_recorded'])
        self.assertEqual(self.control.read_bytes(), original)
        self.assertNotIn('sha256', metadata)
        self.assertNotIn(runner.sha256(self.control), json.dumps(metadata))
        for secret in (password, self.control_value['username']):
            self.assertNotIn(secret, json.dumps(metadata, ensure_ascii=False))

    def test_verify_operation_has_exact_separate_completion_condition(self):
        self.put(self.control, {'verify_ms1_crew': True, 'quit_when': 'ms1_crew_observed'})
        control = self.prepare()['control']
        self.assertFalse(control['export_ms1_crew'])
        self.assertTrue(control['verify_ms1_crew'])
        self.assertEqual(control['quit_when'], 'ms1_crew_observed')
        self.put(self.control, {'export_ms1_crew': False, 'verify_ms1_crew': True,
                               'quit_when': 'ms1_crew_observed'})
        self.assertEqual(self.prepare()['control']['quit_when'], control['quit_when'])

    def test_verify_cannot_use_bundle_without_scenario(self):
        self.put(self.control, {'verify_ms1_crew': True, 'quit_when': 'ms1_crew_observed'})
        (self.project / 'tools/interactive_client.py').write_text(
            'MODULES = ' + repr(self.modules[:-1]) + '\n', encoding='utf-8')
        self.plan['sources'].pop()
        self.write_plan()
        with self.assertRaisesRegex(ValueError, 'scenario module'):
            self.prepare()

    def test_operations_are_exclusive_and_condition_cannot_cross_modes(self):
        for value in (
            {'export_ms1_crew': True, 'verify_ms1_crew': True, 'quit_when': 'ms1_crew_observed'},
            {'export_ms1_crew': False, 'verify_ms1_crew': False, 'quit_when': 'ms1_crew_exported'},
            {'verify_ms1_crew': True, 'quit_when': 'ms1_crew_exported'},
            {'verify_ms1_crew': 1, 'quit_when': 'ms1_crew_observed'},
            {'verify_ms1_crew': True, 'export_ms1_crew': None, 'quit_when': 'ms1_crew_observed'},
            {'verify_ms1_crew': True, 'quit_when': 'ms1_crew_observed', 'quit_after_seconds': None},
        ):
            with self.subTest(value=value):
                self.put(self.control, value)
                with self.assertRaises(ValueError):
                    runner.control_contract(self.control)

    def test_timers_commands_and_future_conditions_rejected(self):
        cases = ({'quit_after_seconds': None}, {'quit_after_seconds': 1},
                 {'command': 'anything'}, {'inspect_ms1_crew': True},
                 {'quit_when': 'ms1_crew_observed'}, {'quit_when': None},
                 {'export_ms1_crew': 1}, {'export_ms1_crew': False})
        for changes in cases:
            with self.subTest(changes=changes):
                self.put(self.control, dict(self.control_value, **changes))
                with self.assertRaises(ValueError):
                    runner.control_contract(self.control)

    def test_control_bounded_duplicate_invalid_and_array_rejected(self):
        for payload in (b'x' * (runner.MAX_CONTROL + 1), b'[]', b'null', b'\xff',
                b'{"export_ms1_crew":true,"export_ms1_crew":true,"quit_when":"ms1_crew_exported"}'):
            with self.subTest(length=len(payload)):
                self.control.write_bytes(payload)
                with self.assertRaises(ValueError):
                    runner.control_contract(self.control)

    def test_credential_contract_failures_do_not_disclose_values(self):
        secret = 'private-do-not-record'
        cases = ({'username': secret}, {'password': secret}, {'submit_via': 'flash'},
                 {'username': secret, 'password': secret, 'submit_via': 'python'},
                 {'username': 'a@b.invalid', 'password': secret, 'submit_via': 'arbitrary'},
                 {'username': 'a@b.invalid', 'password': [secret], 'submit_via': 'flash'})
        for changes in cases:
            with self.subTest(keys=list(changes)):
                self.put(self.control, dict(self.control_value, **changes))
                with self.assertRaises(ValueError) as raised:
                    runner.control_contract(self.control)
                self.assertNotIn(secret, str(raised.exception))

    def test_normal_defaults_cannot_hide_autologin_or_autoquit(self):
        for key in ('normal_auto_login', 'normal_auto_quit'):
            self.plan[key] = True
            self.write_plan()
            with self.assertRaisesRegex(ValueError, 'normal defaults'):
                self.prepare()
            self.plan[key] = False

    def test_control_escape_and_reused_output_rejected(self):
        outside = self.original / 'control.json'
        self.put(outside, self.control_value)
        self.settings['test_control'] = str(outside)
        self.write_plan()
        with self.assertRaisesRegex(ValueError, 'escaped'):
            self.prepare()
        self.settings['test_control'] = str(self.control)
        self.write_plan()
        self.put(self.out / 'native-outcome.json', {})
        with self.assertRaisesRegex(ValueError, 'unused'):
            self.prepare()

    def test_client_roots_must_not_overlap(self):
        self.paths['original_client_root'] = self.research
        with self.assertRaisesRegex(ValueError, 'separate'):
            self.prepare()

    def test_current_source_changes_invalidate_compiler_provenance(self):
        path = self.project / 'client_patch/ms1_crew_probe.py'
        path.write_text('# changed\n')
        with self.assertRaisesRegex(ValueError, 'provenance'):
            self.prepare()

    def test_compiled_bundle_hash_and_source_order_are_bound(self):
        path = self.out / 'bundle/res_mods/0.9.1/scripts/client/ms1_crew_probe.pyc'
        original = path.read_bytes()
        path.write_bytes(b'different')
        with self.assertRaisesRegex(ValueError, 'installation payload'):
            self.prepare()
        path.write_bytes(original)
        self.plan['sources'].reverse()
        self.write_plan()
        with self.assertRaisesRegex(ValueError, 'order or path'):
            self.prepare()

    def test_current_installer_module_set_is_required(self):
        (self.project / 'tools/interactive_client.py').write_text("MODULES = ('sr_interactive',)\n")
        with self.assertRaisesRegex(ValueError, 'module set'):
            self.prepare()

    def test_natural_exit_wait_without_timeout_records_diagnostic_mode_and_restores(self):
        context = self.prepare()
        self.packet()
        result, child, installer, _ = self.execute(context)
        child.wait.assert_called_once_with()
        self.assertEqual([call.args[0] for call in installer.call_args_list], ['install', 'rollback'])
        self.assertEqual(result['process_status'], 'PASS')
        self.assertEqual(result['runner_mode'], 'diagnostic_until_client_condition')
        self.assertTrue(result['condition_status'].startswith('NOT_RUN'))
        self.assertFalse(result['timed_out'])
        self.assertEqual(result['wire_packets'], 1)
        for name in ('native-run-started.json', 'native-process.json', 'native-outcome.json'):
            saved = json.loads((self.out / name).read_text())
            self.assertEqual(saved['runner_mode'], 'diagnostic_until_client_condition')
        self.assertFalse(result['control_consumed'])

    def test_crash_exit_is_failure_and_restores(self):
        child = Mock(pid=123, spec=['pid', 'wait', 'poll'])
        child.wait.return_value = child.poll.return_value = 3221225477
        result, _, installer, _ = self.execute(self.prepare(), child)
        self.assertEqual(result['process_status'], 'FAIL')
        self.assertEqual(result['restore'], 'PASS')
        self.assertEqual(installer.call_args.args[0], 'rollback')

    def test_interrupt_keeps_live_process_and_pending_restore(self):
        child = Mock(pid=123, spec=['pid', 'wait', 'poll'])
        child.wait.side_effect = KeyboardInterrupt()
        child.poll.return_value = None
        result, _, installer, _ = self.execute(self.prepare(), child)
        self.assertEqual(installer.call_count, 1)
        self.assertEqual(result['harness_exit_code'], 130)
        self.assertEqual(result['restore'], 'NOT_RUN')
        self.assertTrue(result['restore_pending'])
        self.assertTrue((self.out / 'native-run-interrupted.json').is_file())
        self.assertFalse((self.out / 'native-outcome.json').exists())
        self.assertFalse((self.out / 'wire').exists())

    def test_unknown_process_lifetime_prevents_restore(self):
        child = Mock(pid=123, spec=['pid', 'wait', 'poll'])
        child.wait.side_effect = OSError('wait error')
        child.poll.side_effect = OSError('poll error')
        result, _, installer, _ = self.execute(self.prepare(), child)
        self.assertEqual(installer.call_count, 1)
        self.assertEqual(result['process_status'], 'NOT_RUN')
        self.assertTrue(result['restore_pending'])

    def test_capture_path_escape_fails_but_restore_runs(self):
        context = self.prepare()
        self.append_manifest({'event': 'packet', 'index': 0, 'bytes': 4, 'file': '../escape.bin'})
        result, _, installer, _ = self.execute(context)
        self.assertEqual(result['capture_status'], 'FAIL')
        self.assertEqual(result['process_status'], 'FAIL')
        self.assertEqual(result['restore'], 'PASS')
        self.assertEqual(installer.call_args.args[0], 'rollback')

    def test_capture_exhaustion_does_not_become_native_success(self):
        context = self.prepare()
        self.append_manifest({'event': 'capture_limit'})
        result, child, _, _ = self.execute(context)
        child.wait.assert_called_once_with()
        self.assertEqual(result['capture_status'], 'FAIL')
        self.assertEqual(result['process_status'], 'FAIL')
        self.assertEqual(result['restore'], 'PASS')

    def test_log_span_bound_is_reused(self):
        context = self.prepare()
        with (self.run_dir / 'gateway.stdout.log').open('ab') as stream:
            stream.write(b'x' * (runner.manual.MAX_LOG + 1))
        result, _, _, _ = self.execute(context)
        self.assertEqual(result['capture_status'], 'FAIL')
        self.assertEqual(result['restore'], 'PASS')
        self.assertFalse((self.out / 'gateway-span.log').exists())

    def test_spawn_failure_and_partial_install_ledger_restore(self):
        result, _, installer, spawn = self.execute(self.prepare(), spawn_error=OSError('spawn failed'))
        spawn.assert_called_once()
        self.assertFalse(result['client_started'])
        self.assertEqual(result['restore'], 'PASS')
        self.assertEqual(installer.call_args.args[0], 'rollback')

    def test_partial_install_failure_with_ledger_restores_without_spawn(self):
        def install(operation, out):
            if operation == 'install':
                self.put(out / 'patch-ledger.json', {'unit_fixture': True})
                return 1
            return 0
        result, _, installer, spawn = self.execute(self.prepare(), install_effect=install)
        spawn.assert_not_called()
        self.assertEqual(result['restore'], 'PASS')
        self.assertEqual(result['process_status'], 'FAIL')
        self.assertEqual(installer.call_args.args[0], 'rollback')

    def test_control_changed_during_install_is_not_executed(self):
        def install(operation, out):
            if operation == 'install':
                self.put(self.control, dict(self.control_value, screenshot_when='login'))
            return 0
        result, _, installer, spawn = self.execute(self.prepare(), install_effect=install)
        spawn.assert_not_called()
        self.assertEqual(result['restore'], 'PASS')
        self.assertIn('changed after preflight', result['run_error'])
        self.assertEqual(installer.call_args.args[0], 'rollback')

    def test_same_length_credential_change_is_detected_despite_identical_public_metadata(self):
        self.control_value.update(username='test@example.invalid', password='unit-secret-one-123', submit_via='python')
        self.put(self.control, self.control_value)
        context = self.prepare()
        before_size = self.control.stat().st_size
        changed = dict(self.control_value, password='unit-secret-two-123')
        self.put(self.control, changed)
        self.assertEqual(before_size, self.control.stat().st_size)
        self.assertEqual(context['control'], runner.control_contract(self.control))
        with self.assertRaisesRegex(ValueError, 'one-shot control changed after preflight'):
            runner.unchanged(context)
        result, _, installer, spawn = self.execute(context)
        installer.assert_not_called()
        spawn.assert_not_called()
        self.assertEqual(result['process_status'], 'FAIL')
        for name in ('native-run-started.json', 'native-outcome.json'):
            encoded = (self.out / name).read_text()
            for secret in (context['_control_checksum'], runner.sha256(self.control),
                           self.control_value['password'], changed['password']):
                self.assertNotIn(secret, encoded)

    def test_public_run_artifacts_exclude_transient_control_checksum(self):
        self.control_value.update(username='test@example.invalid', password='unit-secret-one-123', submit_via='python')
        self.put(self.control, self.control_value)
        context = self.prepare()
        result, _, _, _ = self.execute(context)
        self.assertEqual(result['process_status'], 'PASS')
        for name in ('native-run-started.json', 'native-process.json', 'native-outcome.json'):
            encoded = (self.out / name).read_text()
            saved = json.loads(encoded)
            self.assertNotIn('sha256', saved['diagnostic_control'])
            self.assertNotIn('_control_checksum', encoded)
            for secret in (context['_control_checksum'], self.control_value['username'], self.control_value['password']):
                self.assertNotIn(secret, encoded)

    def test_credential_change_during_install_restores_without_spawn(self):
        self.control_value.update(username='test@example.invalid', password='unit-secret-one-123', submit_via='python')
        self.put(self.control, self.control_value)

        def install(operation, out):
            if operation == 'install':
                self.put(self.control, dict(self.control_value, password='unit-secret-two-123'))
            return 0

        result, _, installer, spawn = self.execute(self.prepare(), install_effect=install)
        spawn.assert_not_called()
        self.assertEqual(result['restore'], 'PASS')
        self.assertEqual(result['process_status'], 'FAIL')
        self.assertIn('changed after preflight', result['run_error'])
        self.assertEqual([call.args[0] for call in installer.call_args_list], ['install', 'rollback'])

    def test_plan_changed_after_preflight_rejected_before_install(self):
        context = self.prepare()
        self.plan['normal_auto_quit'] = True
        self.write_plan()
        result, _, installer, spawn = self.execute(context)
        installer.assert_not_called()
        spawn.assert_not_called()
        self.assertEqual(result['process_status'], 'FAIL')

    def test_mutex_immediately_before_spawn_prevents_second_client(self):
        result, _, installer, spawn = self.execute(self.prepare(), mutex=True)
        spawn.assert_not_called()
        self.assertEqual([call.args[0] for call in installer.call_args_list], ['install', 'rollback'])
        self.assertEqual(result['process_status'], 'FAIL')

    def test_cli_has_no_timeout_parameter(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            runner.main(['--install', 'unused', '--service', 'unused', '--timeout', '60'])
        self.assertEqual(error.exception.code, 2)

    def test_limits_control_has_distinct_condition_without_timer(self):
        self.put(self.control, {'verify_hangar_limits': True, 'quit_when': 'hangar_limits_observed'})
        contract = runner.control_contract(self.control)
        self.assertTrue(contract['verify_hangar_limits'])
        self.assertFalse(contract['verify_ms1_crew'])
        self.assertFalse(contract['credentials_present'])
        self.assertEqual(contract['quit_when'], 'hangar_limits_observed')

    def test_limits_cannot_cross_condition_or_combine_operations(self):
        for extra in ({'verify_ms1_crew': True}, {'export_ms1_crew': True},
                      {'quit_when': 'ms1_crew_observed'}, {'verify_hangar_limits': 1},
                      {'quit_after_seconds': 60}):
            value = {'verify_hangar_limits': True, 'quit_when': 'hangar_limits_observed'}
            value.update(extra)
            self.put(self.control, value)
            with self.assertRaises(ValueError):
                runner.control_contract(self.control)

    def test_limits_cannot_use_bundle_missing_its_scenario(self):
        self.put(self.control, {'verify_hangar_limits': True, 'quit_when': 'hangar_limits_observed'})
        with self.assertRaisesRegex(ValueError, 'limits verification requires'):
            self.prepare()

    def test_windows_control_has_distinct_condition_without_timer(self):
        self.put(self.control, {'verify_hangar_windows': True, 'quit_when': 'hangar_windows_observed'})
        contract = runner.control_contract(self.control)
        self.assertTrue(contract['verify_hangar_windows'])
        self.assertFalse(contract['verify_hangar_limits'])
        self.assertFalse(contract['verify_ms1_crew'])
        self.assertFalse(contract['credentials_present'])
        self.assertEqual(contract['quit_when'], 'hangar_windows_observed')

    def test_windows_cannot_cross_condition_or_combine_operations(self):
        for extra in ({'verify_ms1_crew': True}, {'export_ms1_crew': True},
                      {'verify_hangar_limits': True}, {'quit_when': 'hangar_limits_observed'},
                      {'verify_hangar_windows': 1}, {'quit_after_seconds': 60}):
            value = {'verify_hangar_windows': True, 'quit_when': 'hangar_windows_observed'}
            value.update(extra)
            self.put(self.control, value)
            with self.assertRaises(ValueError):
                runner.control_contract(self.control)

    def test_windows_cannot_use_bundle_missing_its_scenario(self):
        self.put(self.control, {'verify_hangar_windows': True, 'quit_when': 'hangar_windows_observed'})
        with self.assertRaisesRegex(ValueError, 'windows verification requires'):
            self.prepare()

    def relogin_control(self):
        return {'verify_inprocess_relogin': True, 'quit_when': 'inprocess_relogin_observed',
                'username': 'own@example.test', 'password': 'unit-secret-only-123', 'submit_via': 'python'}

    def test_relogin_explicit_control_keeps_credentials_out_of_evidence(self):
        value = self.relogin_control()
        self.put(self.control, value)
        contract = runner.control_contract(self.control)
        self.assertTrue(contract['verify_inprocess_relogin'])
        self.assertTrue(contract['credentials_present'])
        self.assertEqual(contract['quit_when'], 'inprocess_relogin_observed')
        self.assertFalse(contract['verify_hangar_windows'])
        self.assertNotIn(value['username'], json.dumps(contract))
        self.assertNotIn(value['password'], json.dumps(contract))

    def test_relogin_requires_own_paired_python_submit_and_own_capture(self):
        original = self.relogin_control()
        cases = [dict(original, submit_via='flash'), dict(original, screenshot_when='hangar')]
        for field in ('username', 'password', 'submit_via'):
            case = dict(original)
            del case[field]
            cases.append(case)
        for case in cases:
            self.put(self.control, case)
            with self.assertRaises(ValueError) as raised:
                runner.control_contract(self.control)
            self.assertNotIn(original['password'], str(raised.exception))

    def test_relogin_cannot_mix_modes_or_condition_or_timer(self):
        cases = [{'verify_ms1_crew': True}, {'export_ms1_crew': True},
                 {'verify_hangar_limits': True}, {'verify_hangar_windows': True},
                 {'verify_inprocess_relogin': 1}, {'quit_when': 'hangar_windows_observed'},
                 {'quit_after_seconds': 60}]
        for extra in cases:
            value = self.relogin_control()
            value.update(extra)
            self.put(self.control, value)
            with self.assertRaises(ValueError):
                runner.control_contract(self.control)

    def test_relogin_cannot_use_bundle_missing_its_scenario(self):
        self.put(self.control, self.relogin_control())
        with self.assertRaisesRegex(ValueError, 'in-process relogin requires its current'):
            self.prepare()


if __name__ == '__main__':
    unittest.main()
