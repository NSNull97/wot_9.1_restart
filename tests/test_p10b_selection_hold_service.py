"""Actual four-owner subprocess/SQLite CLI precursor; no native Training5."""
from copy import deepcopy
from contextlib import closing
from pathlib import Path
from unittest import mock
import atexit
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import p10b_selection_hold_support as s
import p10b_selection_hold_service as service
from p10b_selection_hold import SelectionHoldReader, MAX_REQUEST, MAX_REPLY
from game_profile_tx import TransactionError

CODE_ROOT = Path(__file__).resolve().parents[1]
CLI = CODE_ROOT / 'tools/p10b_selection_hold_service.py'
OUT = Path(tempfile.mkdtemp(prefix='wot091-selection-cli63-'))
assert OUT.drive.lower() == s.ROOT.drive.lower()
CALLS, TRACES = [], []


def save_report():
    value = dict(schema='p10b-selection-hold-cli63-actual.v1', calls=CALLS,
                 traces=TRACES, setup=s.SETUPS, source_observations=s.SOURCE_OBSERVATIONS,
                 new_grants=0, native_training5='FORBIDDEN_UNIMPLEMENTED', output=str(OUT))
    with (OUT / 'result.json').open('xb') as f:
        f.write(s.canonical(value))


atexit.register(save_report)


class SelectionHoldServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        metadata, _ = s.context_seed(1, s.ROOT)
        cls.catalog = s.load_catalog(metadata['original'])
        cls.fixtures = []
        try:
            for index in (0, 1):
                cls.fixtures.append(s.Fixture(index, cls.catalog))
        except BaseException:
            for fx in cls.fixtures:
                fx.close()
            raise

    @classmethod
    def tearDownClass(cls):
        for fx in cls.fixtures:
            fx.close()

    def call(self, fx, request, slot=0, database=None, raw=None, account=None, label=''):
        database = database or fx.database
        command = [sys.executable, '-B', '-X', 'utf8', str(CLI), '--database', str(database),
                   '--bundle', fx.metadata['bundle'], '--original-root', fx.metadata['original'],
                   '--account-id', account or fx.accounts[slot], '--shell-catalog', str(s.SHELLS),
                   '--terminal-policy', str(s.TERMINAL)]
        env = dict(os.environ)
        env.pop('PYTHONPATH', None)  # Actual production bootstrap, unrelated cwd.
        payload = s.canonical(request) if raw is None else raw
        result = subprocess.run(command, input=payload, capture_output=True, cwd=OUT,
                                env=env, timeout=60)
        self.assertLessEqual(len(result.stdout), MAX_REPLY)
        self.assertLessEqual(len(result.stderr), 4096)
        CALLS.append(dict(label=label, account_id=account or fx.accounts[slot],
            database=str(database), request_sha256=s.sha(payload), request_bytes=len(payload),
            response_sha256=s.sha(result.stdout), response_bytes=len(result.stdout),
            stderr_sha256=s.sha(result.stderr), exit_code=result.returncode,
            response=json.loads(result.stdout) if result.stdout else None,
            child_pythonpath_removed=True, unrelated_cwd=str(OUT)))
        return result

    def conserved(self, fx, action):
        before = (s.logical(fx.stores[0].connection), s.files(fx.database))
        result = action()
        self.assertEqual((s.logical(fx.stores[0].connection), s.files(fx.database)), before)
        fx.assert_source()
        return result

    def denial(self, result, code):
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b'')
        self.assertEqual(json.loads(result.stdout), dict(error='selection_not_ready', code=code))

    def unavailable(self, result):
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, b'')
        self.assertEqual(result.stderr.decode('ascii').splitlines(),
                         ['selection_hold_worker_invalid_or_unavailable'])

    def test_actual_four_owner_cli_proofs_equal_real_readonly_selection(self):
        self.assertEqual(Path(service.__file__).resolve(), CLI)
        for fx in self.fixtures:
            for slot in (0, 1):
                request, _ = fx.request(slot)
                expected = fx.select(request, slot)
                result = self.conserved(fx, lambda: self.call(fx, request, slot, label='four-owner-positive'))
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stderr, b'')
                self.assertEqual(result.stdout, s.canonical(expected))
                self.assertEqual(expected['version'], 5)
                self.assertEqual(len(expected['projection_stamp']), 11)

    def test_malformed_duplicate_unknown_path_and_oversize_stdin_never_load_sources(self):
        fx = self.fixtures[1]
        request, _ = fx.request()
        bad = dict(request, database=str(OUT / 'must-not-exist.sqlite'))
        for raw in (b'{}', b'{"version":5,"version":5}', b'\xff', b'[' * 4097,
                    s.canonical(bad), b' ' * (MAX_REQUEST + 1)):
            result = self.conserved(fx, lambda raw=raw: self.call(fx, request, raw=raw, label='invalid-stdin'))
            self.denial(result, 'INVALID_INPUT')
        self.assertFalse((OUT / 'must-not-exist.sqlite').exists())

    def test_stale_cas_and_each_new_hold_stamp_field_are_explicit_readonly_denials(self):
        fx = self.fixtures[1]
        request, _ = fx.request()
        cases = [(dict(request, expected_revision=request['expected_revision'] - 1), 'STALE_REVISION')]
        for key, code in (('hold_policy_sha256', 'OWNER_HOLD_POLICY_REQUIRED'),
                          ('hold_companion_sha256', 'SOURCE_STAMP_MISMATCH')):
            bad = deepcopy(request)
            bad['projection_stamp'][key] = '0' * 64
            cases.append((bad, code))
        for bad, code in cases:
            self.denial(self.conserved(fx, lambda bad=bad: self.call(fx, bad, label='known-denial')), code)

    def test_foreign_authenticated_owner_is_generic_and_emits_no_payload(self):
        fx = self.fixtures[1]
        request, _ = fx.request()
        self.unavailable(self.conserved(fx, lambda: self.call(fx, request, account=fx.accounts[1], label='foreign-owner')))

    def test_actual_active_hold_reservation_blocks_another_selected_vehicle(self):
        fx = s.Fixture(1, self.catalog)
        self.addCleanup(fx.close)
        request, _ = fx.request()
        admit = {k: request[k] for k in ('version', 'contract', 'account_id',
                 'native_database_id', 'run_id', 'expected_revision')}
        admit.update(operation='admit', command_key='selection-cli63:held',
                     battle_id=s.RUN + ':63', native_inventory_id=1)
        receipt = fx.stores[0].battle_hold(admit, authenticated_account_id=fx.accounts[0])
        self.assertEqual(receipt['status'], 'admitted')
        current, _ = fx.request(native=2)
        self.denial(self.conserved(fx, lambda: self.call(fx, current, label='actual-held')), 'VEHICLE_RESERVED')

    def test_existing_schema_preflight_missing_and_corrupt_files_never_initialize(self):
        fx = self.fixtures[1]
        request, _ = fx.request()
        missing = OUT / 'missing-game.sqlite'
        self.unavailable(self.call(fx, request, database=missing, label='missing-db'))
        self.assertFalse(missing.exists())
        empty = OUT / 'non-hold.sqlite'
        with closing(sqlite3.connect(empty)) as c, c:
            c.execute('CREATE TABLE sentinel(value TEXT)')
            c.execute("INSERT INTO sentinel VALUES ('authored non-Hold fixture')")
        before = s.files(empty)
        self.denial(self.call(fx, request, database=empty, label='existing-no-hold'), 'OWNER_HOLD_POLICY_REQUIRED')
        self.assertEqual(s.files(empty), before)
        with closing(sqlite3.connect(empty)) as c:
            self.assertEqual(c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(), [('sentinel',)])
        corrupt = OUT / 'not-sqlite.bin'
        corrupt.write_bytes(b'authored-invalid-sqlite\n')
        before = s.files(corrupt)
        self.unavailable(self.call(fx, request, database=corrupt, label='corrupt-db'))
        self.assertEqual(s.files(corrupt), before)
        poisoned = OUT / 'poisoned-hold-marker.sqlite'
        # Real backup of the already activated test DB, then an explicit
        # corruption fixture. This is not another ownership/admission source.
        with closing(sqlite3.connect(fx.database.as_uri() + '?mode=ro', uri=True)) as src, \
                closing(sqlite3.connect(poisoned)) as dst:
            src.execute('PRAGMA query_only=ON')
            src.backup(dst)
        with closing(sqlite3.connect(poisoned)) as c, c:
            c.execute('UPDATE battle_owner_hold_schema SET policy_sha256=?', ('0' * 64,))
        with closing(sqlite3.connect(poisoned)) as c:
            before = (s.logical(c), s.files(poisoned))
        self.unavailable(self.call(fx, request, database=poisoned, label='poisoned-existing-hold-schema'))
        with closing(sqlite3.connect(poisoned)) as c:
            self.assertEqual((s.logical(c), s.files(poisoned)), before)

    def test_actual_constructor_trace_query_only_write_refusal_and_all_handle_cleanup(self):
        fx = self.fixtures[1]
        request, _ = fx.request()
        connections, statements = [], []
        original = sqlite3.connect

        def observed_connect(*args, **kwargs):
            # Test-only observer: every call still opens the genuine SQLite
            # connection with its original args; no fake store/reply/SQL data.
            c = original(*args, **kwargs)
            c.set_trace_callback(statements.append)
            connections.append(c)
            return c

        before = (s.logical(fx.stores[0].connection), s.files(fx.database))
        with mock.patch.object(sqlite3, 'connect', observed_connect):
            with service.configured_store(fx.database, self.catalog, fx.accounts[0],
                                          s.SHELLS, s.TERMINAL) as store:
                self.assertIs(type(store), s.OwnerHoldStore)
                self.assertEqual(store.connection.total_changes, 0)
                self.assertFalse(store.connection.in_transaction)
                self.assertEqual(store.connection.execute('PRAGMA query_only').fetchone()[0], 1)
                selected = SelectionHoldReader(store, fx.sources[0]).select(request,
                    authenticated_account_id=fx.accounts[0])
                self.assertEqual(selected, fx.select(request))
                self.assertEqual(store.connection.execute('PRAGMA query_only').fetchone()[0], 1)
                with self.assertRaises(sqlite3.OperationalError):
                    store.connection.execute('DELETE FROM p08b_run')
                self.assertEqual(store.connection.total_changes, 0)
        self.assertEqual((s.logical(fx.stores[0].connection), s.files(fx.database)), before)
        self.assertEqual(len(connections), 2)
        for c in connections:
            with self.assertRaises(sqlite3.ProgrammingError):
                c.execute('SELECT 1')
        self.assertFalse(any(x.lstrip().upper().startswith(('CREATE ', 'INSERT ', 'UPDATE ', 'ALTER ', 'DROP ')) for x in statements))
        self.assertIn('DELETE FROM p08b_run', statements)
        TRACES.append(dict(kind='actual-constructor-and-selection-readonly', sql=statements,
                           total_changes=0, actual_connections=len(connections), all_closed=True,
                           trace_observer_only_authored=True))

    def test_failed_genuine_constructor_closes_partial_handle_and_path_guards(self):
        fx = self.fixtures[1]
        invalid = OUT / 'bad-shell-source.json'
        invalid.write_bytes(b'{}\n')
        connections = []
        original = sqlite3.connect

        def observed_connect(*args, **kwargs):
            c = original(*args, **kwargs)
            connections.append(c)
            return c

        before = (s.logical(fx.stores[0].connection), s.files(fx.database))
        with mock.patch.object(sqlite3, 'connect', observed_connect):
            with self.assertRaises(TransactionError) as caught:
                with service.configured_store(fx.database, self.catalog, fx.accounts[0], invalid, s.TERMINAL):
                    self.fail('invalid genuine constructor source accepted')
            self.assertEqual(caught.exception.code, 'P06T_SOURCE_REQUIRED')
        self.assertEqual(len(connections), 2)
        for c in connections:
            with self.assertRaises(sqlite3.ProgrammingError):
                c.execute('SELECT 1')
        self.assertEqual((s.logical(fx.stores[0].connection), s.files(fx.database)), before)
        for path in ('relative.sqlite', ':memory:', fx.database.as_uri() + '?mode=ro'):
            with self.assertRaises(ValueError):
                service.plain_database(path)


if __name__ == '__main__':
    unittest.main()
