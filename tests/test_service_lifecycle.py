"""Local lifecycle safety only; these tests make no client compatibility claim."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import service_lifecycle as lifecycle


def hidden_process_options():
    return {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}


def pid_result(pid, state='ABSENT', **details):
    return dict(pid=pid, state=state, **details)


class LifecycleFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / 'runtime'
        self.directory.mkdir()
        self.run = self.directory / 'run-owned-test'
        self.run.mkdir()
        self.config = self.directory / 'service.json'
        self.config.write_bytes(b'{"fixture": true}\n')
        self.state_path = self.directory / 'state.json'
        self.lock_path = self.directory / 'supervisor.lock'
        # Recovery creates this permanent guard; exclude that one-time creation
        # from assertions about preservation of prior runtime records.
        with lifecycle.lifecycle_guard(self.directory):
            pass
        self.state = {
            'status': 'RUNNING', 'supervisor_pid': 24001,
            'run_dir': str(self.run), 'config': str(self.config),
            'processes': [{'role': 'identity', 'pid': 24002},
                          {'role': 'gateway', 'pid': 24003, 'exit_code': None}],
            'website': 'http://127.0.0.1:3092', 'website_owned': False,
        }
        self.write_state(self.state)
        self.lock_path.write_bytes(b'24001\r\n')
        (self.run / 'retained.log').write_bytes(b'prior run evidence\r\n')

    def write_state(self, state):
        # Deliberately retain noncanonical formatting for archival byte checks.
        self.state_path.write_bytes((json.dumps(state, indent=3) + '\r\n').encode('utf8'))

    def records(self):
        return {str(path.relative_to(self.directory)): (path.read_bytes(), path.stat().st_mtime_ns)
                for path in self.directory.rglob('*') if path.is_file()}

    def recover(self, preflight=None):
        with lifecycle.lifecycle_guard(self.directory):
            return lifecycle.recover_stale(self.directory, self.config, preflight or (lambda: None))

    def probe_map(self, overrides=None):
        overrides = overrides or {}
        return lambda pid: pid_result(pid, overrides.get(pid, 'ABSENT'))


class ObservedStatusTests(LifecycleFixture):
    def test_stale_running_is_observed_without_modifying_any_record(self):
        before = self.records()
        with patch.object(lifecycle, 'probe_pid', side_effect=self.probe_map()):
            status = lifecycle.observed_status(self.directory)
        self.assertEqual('STALE', status['status'])
        self.assertEqual('RUNNING', status['recorded_status'])
        self.assertTrue(status['supervisor_lock_present'])
        self.assertEqual(['supervisor', 'identity', 'gateway'],
                         [row['role'] for row in status['process_observations']])
        self.assertEqual(before, self.records())

    def test_active_child_of_dead_supervisor_is_orphaned(self):
        with patch.object(lifecycle, 'probe_pid', side_effect=self.probe_map({24002: 'ALIVE'})):
            status = lifecycle.observed_status(self.directory)
        self.assertEqual('ORPHANED', status['status'])

    def test_access_denied_is_unknown_and_preserves_saved_state(self):
        before = self.records()
        with patch.object(lifecycle, 'probe_pid', return_value=pid_result(24001, 'UNKNOWN', winerror=5)):
            status = lifecycle.observed_status(self.directory)
        self.assertEqual('UNKNOWN', status['status'])
        self.assertEqual('RUNNING', status['recorded_status'])
        self.assertEqual(before, self.records())

    def test_alive_supervisor_missing_child_is_degraded(self):
        with patch.object(lifecycle, 'probe_pid', side_effect=self.probe_map({24001: 'ALIVE'})):
            status = lifecycle.observed_status(self.directory)
        self.assertEqual('DEGRADED', status['status'])

    def test_alive_supervisor_without_lock_is_inconsistent(self):
        self.lock_path.unlink()
        with patch.object(lifecycle, 'probe_pid', side_effect=self.probe_map({24001: 'ALIVE', 24002: 'ALIVE', 24003: 'ALIVE'})):
            status = lifecycle.observed_status(self.directory)
        self.assertEqual('INCONSISTENT', status['status'])

    def test_maintenance_lock_with_different_live_owner_is_busy(self):
        self.lock_path.write_bytes(b'24009')
        with patch.object(lifecycle, 'probe_pid', side_effect=self.probe_map({24009: 'ALIVE'})):
            status = lifecycle.observed_status(self.directory)
        self.assertEqual('BUSY', status['status'])
        self.assertIn({'role': 'lock_owner', 'pid': 24009, 'state': 'ALIVE'}, status['process_observations'])

    def test_stopped_record_with_live_unconfirmed_child_is_inconsistent(self):
        self.write_state(dict(self.state, status='STOPPED'))
        self.lock_path.unlink()
        with patch.object(lifecycle, 'probe_pid', side_effect=self.probe_map({24002: 'ALIVE'})):
            status = lifecycle.observed_status(self.directory)
        self.assertEqual('INCONSISTENT', status['status'])

    def test_confirmed_exit_is_not_reinterpreted_using_a_reused_pid(self):
        self.write_state(dict(self.state, status='STOPPED', processes=[
            {'role': 'gateway', 'pid': 24003, 'exit_code': 7}]))
        self.lock_path.unlink()
        with patch.object(lifecycle, 'probe_pid', side_effect=self.probe_map({24003: 'ALIVE'})) as probe:
            status = lifecycle.observed_status(self.directory)
        self.assertEqual('STOPPED', status['status'])
        self.assertEqual([24001], [call.args[0] for call in probe.call_args_list])

    def test_not_started_directory_does_not_create_a_guard_or_state(self):
        empty = Path(self.temp.name) / 'empty-runtime'
        empty.mkdir()
        status = lifecycle.observed_status(empty)
        self.assertEqual('NOT_STARTED', status['status'])
        self.assertEqual([], list(empty.iterdir()))

    def test_malformed_json_or_missing_status_returns_unknown_read_only(self):
        for data in (b'{', b'{}', b'[]', b'null', b'{"status":"RUNNING","processes":{}}'):
            with self.subTest(data=data):
                self.state_path.write_bytes(data)
                before = self.records()
                with patch.object(lifecycle, 'probe_pid', side_effect=self.probe_map()):
                    status = lifecycle.observed_status(self.directory)
                self.assertEqual('UNKNOWN', status['status'])
                self.assertEqual(before, self.records())


class RecoveryTests(LifecycleFixture):
    def test_archive_preserves_exact_bytes_hashes_and_unknown_exit_codes(self):
        self.state['processes'].append({'role': 'finished', 'pid': 24004, 'exit_code': 9})
        self.write_state(self.state)
        state_raw, lock_raw = self.state_path.read_bytes(), self.lock_path.read_bytes()
        prior_log = (self.run / 'retained.log').read_bytes()
        preflight = Mock()
        with patch.object(lifecycle, 'probe_pid', side_effect=self.probe_map()) as probe:
            receipt_path = self.recover(preflight)
        preflight.assert_called_once_with()
        receipt = json.loads(receipt_path.read_bytes())
        archive = receipt_path.parent
        self.assertEqual('RECOVERED_ABSENT_PROCESSES', receipt['status'])
        self.assertEqual(state_raw, (archive / 'state.before.json').read_bytes())
        self.assertEqual(lock_raw, (archive / 'supervisor.lock.before').read_bytes())
        self.assertEqual(lock_raw, (archive / 'supervisor.lock.retired').read_bytes())
        self.assertEqual(hashlib.sha256(state_raw).hexdigest(), receipt['state_sha256'])
        self.assertEqual(hashlib.sha256(lock_raw).hexdigest(), receipt['lock_sha256'])
        self.assertEqual(str(self.run), receipt['prior_run_dir'])
        self.assertFalse(self.lock_path.exists())
        recovered = json.loads(self.state_path.read_bytes())
        self.assertEqual('STOPPED', recovered['status'])
        self.assertEqual(str(receipt_path), recovered['recovery_receipt'])
        self.assertEqual(self.state['processes'], recovered['processes'])
        self.assertNotIn('exit_code', recovered['processes'][0])
        self.assertIsNone(recovered['processes'][1]['exit_code'])
        self.assertEqual(9, recovered['processes'][2]['exit_code'])
        self.assertNotIn(24004, [call.args[0] for call in probe.call_args_list])
        self.assertEqual(prior_log, (self.run / 'retained.log').read_bytes())

    def test_live_or_unconfirmed_supervisor_and_children_block_before_preflight(self):
        for pid, state in ((24001, 'ALIVE'), (24002, 'ALIVE'), (24003, 'UNKNOWN')):
            with self.subTest(pid=pid, state=state):
                before = self.records()
                preflight = Mock()
                with patch.object(lifecycle, 'probe_pid', side_effect=self.probe_map({pid: state})):
                    with self.assertRaisesRegex(RuntimeError, 'live or unconfirmed'):
                        self.recover(preflight)
                preflight.assert_not_called()
                self.assertEqual(before, self.records())

    def test_absent_lock_with_live_child_still_refuses_duplicate_start(self):
        self.lock_path.unlink()
        before = self.records()
        with patch.object(lifecycle, 'probe_pid', side_effect=self.probe_map({24002: 'ALIVE'})):
            with self.assertRaisesRegex(RuntimeError, 'live or unconfirmed'):
                self.recover()
        self.assertEqual(before, self.records())

    def test_absent_lock_stale_state_can_be_archived(self):
        self.lock_path.unlink()
        state_raw = self.state_path.read_bytes()
        with patch.object(lifecycle, 'probe_pid', side_effect=self.probe_map()):
            receipt_path = self.recover()
        receipt = json.loads(receipt_path.read_bytes())
        self.assertIsNone(receipt['lock_sha256'])
        self.assertEqual(state_raw, (receipt_path.parent / 'state.before.json').read_bytes())
        self.assertFalse((receipt_path.parent / 'supervisor.lock.before').exists())

    def test_different_maintenance_pid_is_preserved_even_when_absent(self):
        self.lock_path.write_bytes(b'24009')
        before = self.records()
        with patch.object(lifecycle, 'probe_pid', side_effect=self.probe_map()):
            with self.assertRaisesRegex(RuntimeError, 'does not match'):
                self.recover()
        self.assertEqual(before, self.records())

    def test_malformed_oversized_and_out_of_range_locks_are_preserved(self):
        for value in (b'', b'OTHER_OWNER', b'-1', b'0', b'4294967296', b'1' * 65):
            with self.subTest(value=value):
                self.lock_path.write_bytes(value)
                before = self.records()
                preflight = Mock()
                with patch.object(lifecycle, 'probe_pid', side_effect=self.probe_map()):
                    with self.assertRaises(ValueError):
                        self.recover(preflight)
                preflight.assert_not_called()
                self.assertEqual(before, self.records())

    def test_wrong_config_or_missing_state_does_not_claim_stale_owner(self):
        for change in ('wrong-config', 'missing-state'):
            with self.subTest(change=change):
                if change == 'wrong-config':
                    self.write_state(dict(self.state, config=str(self.directory / 'another.json')))
                else:
                    self.state_path.unlink()
                before = self.records()
                with patch.object(lifecycle, 'probe_pid', side_effect=self.probe_map()):
                    with self.assertRaisesRegex(RuntimeError, 'does not match'):
                        self.recover()
                self.assertEqual(before, self.records())

    def test_outside_or_unexpected_run_directory_refused(self):
        foreign = Path(self.temp.name) / 'run-foreign'
        foreign.mkdir()
        wrong_name = self.directory / 'other-run'
        wrong_name.mkdir()
        for run in (foreign, wrong_name):
            with self.subTest(run=run):
                self.write_state(dict(self.state, run_dir=str(run)))
                before = self.records()
                with patch.object(lifecycle, 'probe_pid', side_effect=self.probe_map()):
                    with self.assertRaisesRegex(ValueError, 'run directory'):
                        self.recover()
                self.assertEqual(before, self.records())

    def test_preflight_failure_preserves_all_records_without_archive(self):
        before = self.records()
        with patch.object(lifecycle, 'probe_pid', side_effect=self.probe_map()):
            with self.assertRaisesRegex(OSError, 'occupied fixture port'):
                self.recover(Mock(side_effect=OSError('occupied fixture port')))
        self.assertEqual(before, self.records())
        self.assertEqual([], list(self.directory.glob('recovery-*')))

    def test_changed_lock_during_preflight_is_preserved(self):
        original_state = self.state_path.read_bytes()
        replacement = b'24009'
        with patch.object(lifecycle, 'probe_pid', side_effect=self.probe_map()):
            with self.assertRaisesRegex(RuntimeError, 'changed during recovery'):
                self.recover(lambda: self.lock_path.write_bytes(replacement))
        self.assertEqual(replacement, self.lock_path.read_bytes())
        self.assertEqual(original_state, self.state_path.read_bytes())
        self.assertEqual([], list(self.directory.glob('recovery-*')))

    def test_changed_state_during_preflight_is_preserved(self):
        replacement = dict(self.state, status='STARTING', new_owner_marker='preserve')
        with patch.object(lifecycle, 'probe_pid', side_effect=self.probe_map()):
            with self.assertRaisesRegex(RuntimeError, 'changed during recovery'):
                self.recover(lambda: self.write_state(replacement))
        self.assertEqual(replacement, json.loads(self.state_path.read_bytes()))
        self.assertEqual(b'24001\r\n', self.lock_path.read_bytes())

    def test_pid_becoming_alive_during_preflight_refuses_recovery(self):
        states = {}
        before = self.records()
        with patch.object(lifecycle, 'probe_pid', side_effect=lambda pid: pid_result(pid, states.get(pid, 'ABSENT'))):
            with self.assertRaisesRegex(RuntimeError, 'changed during recovery'):
                self.recover(lambda: states.update({24001: 'ALIVE'}))
        self.assertEqual(before, self.records())

    def test_existing_stopped_state_needs_no_recovery(self):
        self.write_state(dict(self.state, status='STOPPED'))
        self.lock_path.unlink()
        before = self.records()
        preflight = Mock()
        with patch.object(lifecycle, 'probe_pid', side_effect=self.probe_map()):
            self.assertIsNone(self.recover(preflight))
        preflight.assert_not_called()
        self.assertEqual(before, self.records())


class OwnedLockTests(LifecycleFixture):
    def setUp(self):
        super().setUp()
        self.lock_path.unlink()

    def test_owned_lock_covers_early_setup_failure(self):
        before = self.records()
        with self.assertRaisesRegex(OSError, 'setup fixture failure'):
            with lifecycle.owned_supervisor_lock(self.directory):
                self.assertEqual(str(os.getpid()).encode('ascii'), self.lock_path.read_bytes())
                raise OSError('setup fixture failure')
        self.assertFalse(self.lock_path.exists())
        self.assertEqual(before, self.records())

    def test_owned_lock_creation_write_failure_does_not_leave_an_empty_lock(self):
        original_open = Path.open

        class FailedPidWriter:
            def __init__(self, stream):
                self.stream = stream

            def __enter__(self):
                self.stream.__enter__()
                return self

            def write(self, value):
                raise OSError('PID record write fixture failure')

            def __exit__(self, *details):
                return self.stream.__exit__(*details)

            def __getattr__(self, name):
                return getattr(self.stream, name)

        def opened(path, *args, **kwargs):
            stream = original_open(path, *args, **kwargs)
            if path == self.lock_path and args == ('xb',):
                return FailedPidWriter(stream)
            return stream

        before = self.records()
        with patch.object(Path, 'open', opened):
            with self.assertRaisesRegex(OSError, 'PID record write fixture failure'):
                with lifecycle.owned_supervisor_lock(self.directory):
                    self.fail('The body cannot run with an unwritten PID record')
        self.assertFalse(self.lock_path.exists(), 'Failed PID write leaked its newly created empty lock')
        self.assertEqual(before, self.records())

    def test_pid_write_failure_preserves_an_external_replacement(self):
        original_open = Path.open
        lock = self.lock_path

        class ReplacedPidWriter:
            def __init__(self, stream):
                self.stream = stream

            def __enter__(self):
                self.stream.__enter__()
                return self

            def write(self, value):
                self.stream.close()
                lock.unlink()
                lock.write_bytes(b'24009')
                raise OSError('replacement during PID write fixture failure')

            def __exit__(self, *details):
                return self.stream.__exit__(*details)

            def __getattr__(self, name):
                return getattr(self.stream, name)

        def opened(path, *args, **kwargs):
            stream = original_open(path, *args, **kwargs)
            if path == lock and args == ('xb',):
                return ReplacedPidWriter(stream)
            return stream

        with patch.object(Path, 'open', opened):
            with self.assertRaisesRegex(OSError, 'replacement during PID write fixture failure'):
                with lifecycle.owned_supervisor_lock(self.directory):
                    self.fail('Entered body after failed PID record creation')
        self.assertEqual(b'24009', self.lock_path.read_bytes())

    def test_normal_cleanup_and_competing_owner(self):
        with lifecycle.owned_supervisor_lock(self.directory):
            with self.assertRaises(FileExistsError):
                with lifecycle.owned_supervisor_lock(self.directory):
                    self.fail('Competing owner entered the owned region')
            self.assertEqual(str(os.getpid()).encode('ascii'), self.lock_path.read_bytes())
        self.assertFalse(self.lock_path.exists())

    def test_replacement_lock_is_preserved_on_cleanup(self):
        with self.assertRaisesRegex(RuntimeError, 'changed externally'):
            with lifecycle.owned_supervisor_lock(self.directory):
                self.lock_path.write_bytes(b'24009')
        self.assertEqual(b'24009', self.lock_path.read_bytes())

    def test_missing_or_malformed_lock_never_gets_recreated_during_cleanup(self):
        for replacement in (None, b'OTHER_OWNER', b'x' * 65):
            with self.subTest(replacement=replacement):
                with self.assertRaises((RuntimeError, ValueError)):
                    with lifecycle.owned_supervisor_lock(self.directory):
                        if replacement is None:
                            self.lock_path.unlink()
                        else:
                            self.lock_path.write_bytes(replacement)
                if replacement is None:
                    self.assertFalse(self.lock_path.exists())
                else:
                    self.assertEqual(replacement, self.lock_path.read_bytes())
                    self.lock_path.unlink()


class ProcessAndGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def child(self, source, *arguments):
        process = subprocess.Popen([sys.executable, '-B', '-u', '-c', source,
                                    str(ROOT / 'tools'), *map(str, arguments)],
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, **hidden_process_options())
        self.addCleanup(self.reap, process)
        return process

    def reap(self, process):
        if process.poll() is None:
            process.terminate()
        process.communicate(timeout=10)

    def test_current_process_and_reaped_child_pid_are_observed(self):
        self.assertEqual('ALIVE', lifecycle.probe_pid(os.getpid())['state'])
        process = self.child('import time; time.sleep(60)')
        self.assertEqual('ALIVE', lifecycle.probe_pid(process.pid)['state'])
        process.terminate()
        process.communicate(timeout=10)
        self.assertEqual('ABSENT', lifecycle.probe_pid(process.pid)['state'])

    def test_invalid_pid_has_no_os_probe(self):
        for pid in (None, True, False, 0, -1, 1.0, '123', 0x100000000):
            with self.subTest(pid=pid):
                self.assertEqual({'pid': pid, 'state': 'UNKNOWN', 'reason': 'invalid_pid'},
                                 lifecycle.probe_pid(pid))

    def test_reused_live_pid_is_never_reclaimed_even_for_same_python(self):
        process = self.child('import time; time.sleep(60)')
        run = self.directory / 'run-reused-pid'
        run.mkdir()
        config = self.directory / 'service.json'
        state = dict(status='RUNNING', supervisor_pid=process.pid, config=str(config),
                     run_dir=str(run), processes=[])
        state_raw = json.dumps(state).encode('utf8')
        (self.directory / 'state.json').write_bytes(state_raw)
        (self.directory / 'supervisor.lock').write_text(str(process.pid), encoding='ascii')
        preflight = Mock()
        with lifecycle.lifecycle_guard(self.directory):
            with self.assertRaisesRegex(RuntimeError, 'live or unconfirmed'):
                lifecycle.recover_stale(self.directory, config, preflight)
        preflight.assert_not_called()
        self.assertIsNone(process.poll())
        self.assertEqual(state_raw, (self.directory / 'state.json').read_bytes())
        self.assertEqual(str(process.pid), (self.directory / 'supervisor.lock').read_text())

    def test_byte_lock_contention_from_another_process(self):
        source = """import sys
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from service_lifecycle import lifecycle_guard
try:
    with lifecycle_guard(Path(sys.argv[2])):
        print('ENTERED')
except RuntimeError:
    print('BUSY')
"""
        with lifecycle.lifecycle_guard(self.directory):
            process = self.child(source, self.directory)
            stdout, stderr = process.communicate(timeout=10)
            self.assertEqual(0, process.returncode, stderr.decode('utf8', errors='replace'))
            self.assertEqual(b'BUSY', stdout.strip())
        with lifecycle.lifecycle_guard(self.directory):
            pass

    def test_competing_real_processes_get_only_one_supervisor_owner(self):
        gate = self.directory / 'start-gate'
        source = """import sys, time
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from service_lifecycle import owned_supervisor_lock
directory, gate, marker = map(Path, sys.argv[2:5])
marker.with_suffix('.ready').write_bytes(b'ready')
while not gate.exists():
    time.sleep(0.01)
try:
    with owned_supervisor_lock(directory):
        marker.write_bytes(b'owned')
        time.sleep(0.3)
    print('OWNED')
except (FileExistsError, RuntimeError):
    print('BUSY')
"""
        markers = [self.directory / 'owner-one', self.directory / 'owner-two']
        children = [self.child(source, self.directory, gate, marker) for marker in markers]
        deadline = time.monotonic() + 10
        while (not all(marker.with_suffix('.ready').exists() for marker in markers)
               and all(child.poll() is None for child in children) and time.monotonic() < deadline):
            time.sleep(0.02)
        self.assertTrue(all(marker.with_suffix('.ready').exists() for marker in markers),
                        'Competing temporary processes did not reach their start gate')
        gate.write_bytes(b'go')
        outputs = []
        for child in children:
            stdout, stderr = child.communicate(timeout=10)
            self.assertEqual(0, child.returncode, stderr.decode('utf8', errors='replace'))
            outputs.append(stdout.strip())
        self.assertEqual([b'BUSY', b'OWNED'], sorted(outputs))
        self.assertEqual(1, sum(marker.exists() for marker in markers))
        self.assertFalse((self.directory / 'supervisor.lock').exists())

    def test_guard_is_released_on_actual_owner_process_death(self):
        marker = self.directory / 'guard-acquired'
        source = """import sys, time
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from service_lifecycle import lifecycle_guard
with lifecycle_guard(Path(sys.argv[2])):
    Path(sys.argv[3]).write_bytes(b'owned')
    time.sleep(60)
"""
        process = self.child(source, self.directory, marker)
        deadline = time.monotonic() + 10
        while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertTrue(marker.exists(), 'Child did not acquire its temporary lifecycle guard')
        with self.assertRaisesRegex(RuntimeError, 'in progress'):
            with lifecycle.lifecycle_guard(self.directory):
                self.fail('Entered guard held by another live process')
        process.terminate()
        process.communicate(timeout=10)
        with lifecycle.lifecycle_guard(self.directory):
            pass

    def test_supervisor_cleanup_waits_for_brief_competing_guard_owner(self):
        marker = self.directory / 'cleanup-contender-acquired'
        source = """import sys, time
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from service_lifecycle import lifecycle_guard
with lifecycle_guard(Path(sys.argv[2])):
    Path(sys.argv[3]).write_bytes(b'owned')
    time.sleep(0.4)
print('RELEASED')
"""
        with lifecycle.owned_supervisor_lock(self.directory):
            process = self.child(source, self.directory, marker)
            deadline = time.monotonic() + 10
            while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(marker.exists(), 'Temporary cleanup contender did not acquire guard')
            self.assertEqual(str(os.getpid()).encode('ascii'),
                             (self.directory / 'supervisor.lock').read_bytes())
        stdout, stderr = process.communicate(timeout=10)
        self.assertEqual(0, process.returncode, stderr.decode('utf8', errors='replace'))
        self.assertEqual(b'RELEASED', stdout.strip())
        self.assertFalse((self.directory / 'supervisor.lock').exists())


if __name__ == '__main__':
    unittest.main()
