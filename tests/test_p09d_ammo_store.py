"""Real isolated game.sqlite migration/CAS/replay/rollback integration tests."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from game_profile_tx import TransactionError
from p09d_ammo_projection import ProjectionSource, canonical
from p09d_ammo_store import NativeAmmoStore
from p09c_ammo_catalog import SHELLS
from p09c_ammo_service import AmmoServiceStore

BUNDLE = Path(os.environ.get('P09D_TEST_BUNDLE', ROOT / 'local/p09d/source-bundle-05'))
ORIGINAL = Path(os.environ.get('P09D_TEST_ORIGINAL', r'C:\WoT_0.9.1_RU_0717_original'))
TEMP = ROOT / 'local/evidence/20261013-p09d-native-ammo-01/store-tests'
GRANT = {'grant_id': 'p09d-test-depot-v1', 'quantity_each': 100}


@unittest.skipUnless(BUNDLE.is_dir() and ORIGINAL.is_dir(), 'NOT_RUN: original #717 and portable profile4 sources required')
class NativeStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ProjectionSource(BUNDLE)
        cls.account = cls.source.profile['account_id']
        cls.native_id = cls.source.profile['native_database_id']

    def setUp(self):
        TEMP.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=TEMP)
        self.database = Path(self.temp.name) / 'game.sqlite'
        with sqlite3.connect(self.database) as c:
            c.executescript('''PRAGMA user_version=1;
              CREATE TABLE game_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
              CREATE TABLE game_profiles(native_id INTEGER PRIMARY KEY AUTOINCREMENT,account_id TEXT NOT NULL UNIQUE,profile_json TEXT NOT NULL);
              CREATE TABLE game_limits(key_hash TEXT PRIMARY KEY,hits INTEGER NOT NULL,resets_at INTEGER NOT NULL);''')
            c.execute('INSERT INTO game_profiles VALUES (?,?,?)', (self.native_id, self.account, canonical(self.source.profile).decode('ascii')))
            c.execute('INSERT INTO game_profiles VALUES (999,?,?)', ('untouched-account', '{"unrelated":true}'))
            c.execute('INSERT INTO game_meta VALUES (?,?)', ('unrelated', 'preserve-me'))
        c.close()
        self.store = NativeAmmoStore(self.database)

    def tearDown(self):
        self.store.close(); self.temp.cleanup()

    def migrate(self):
        return self.store.migrate(self.source, account_id=self.account, original_root=ORIGINAL, grant=GRANT)

    def command(self, native=1, counts=(30, 10, 5), key='native-session-1:cmd:225', revision=5, wire=1):
        cds = (2570, 2826, 3082) if native == 1 else (14602, 14858, 15114)
        return dict(account_id=self.account, native_database_id=self.native_id, command_key=key,
                    expected_revision=revision, wire_revision=wire,
                    layout=[3, native, 6, *[v for cd, n in zip(cds, counts) for v in (cd, n)], 6, 0, 0, 0, 0, 0, 0])

    def service(self, request=None):
        return self.store.service(request or self.command(), authenticated_account_id=self.account)

    def snapshot(self):
        return list(self.store.connection.iterdump())

    def rejected_unchanged(self, command, code):
        before = self.snapshot()
        with self.assertRaises(TransactionError) as error: self.service(command)
        self.assertEqual(error.exception.code, code)
        self.assertEqual(self.snapshot(), before)

    def test_explicit_migration_preserves_original_profile_fields_and_other_account(self):
        result = self.migrate()
        self.assertEqual(result['revision'], 5)
        state = self.store.read_profile(self.account)
        self.assertEqual(state['depot'], dict.fromkeys(SHELLS, 100))
        profile = json.loads(self.store.connection.execute('SELECT profile_json FROM game_profiles WHERE account_id=?', (self.account,)).fetchone()[0])
        for key in ('crew', 'crew_grant', 'test_grant', 'ammo_grant', 'resources', 'statistics', 'username'):
            self.assertEqual(profile[key], self.source.profile[key])
        self.assertEqual(profile['inventory'][0]['ammunition_count'], 20)
        self.assertEqual(profile['inventory'][1]['ammunition_count'], 0)
        self.assertEqual(self.store.connection.execute('SELECT profile_json FROM game_profiles WHERE native_id=999').fetchone()[0], '{"unrelated":true}')
        self.assertEqual(self.store.connection.execute('PRAGMA user_version').fetchone()[0], 1)

    def test_repeated_migration_never_regrants_stock(self):
        self.migrate(); self.service(); before = self.snapshot()
        self.assertEqual(self.migrate()['status'], 'already_migrated')
        self.assertEqual(self.snapshot(), before)

    def test_migration_failpoint_rolls_back_schema_and_profile(self):
        before = self.snapshot(); self.store.failpoint = 'before_migration_commit'
        with self.assertRaises(TransactionError): self.migrate()
        self.assertEqual(self.snapshot(), before)

    def test_migration_refuses_changed_base_before_ddl(self):
        changed = deepcopy(self.source.profile); changed['resources']['credits'] += 1
        self.store.connection.execute('UPDATE game_profiles SET profile_json=? WHERE account_id=?', (json.dumps(changed), self.account)); self.store.connection.commit()
        before = self.snapshot()
        with self.assertRaises(TransactionError) as error: self.migrate()
        self.assertEqual(error.exception.code, 'BASE_PROFILE_MISMATCH'); self.assertEqual(before, self.snapshot())

    def test_both_vehicles_commit_to_same_game_profile_and_depot(self):
        self.migrate(); first = self.service()
        second = self.service(self.command(native=2, counts=(15, 10, 5), key='second', revision=6, wire=2))
        self.assertEqual((first['revision'], second['revision']), (6, 7))
        profile = json.loads(self.store.connection.execute('SELECT profile_json FROM game_profiles WHERE account_id=?', (self.account,)).fetchone()[0])
        self.assertEqual(profile['snapshot_revision'], 7)
        self.assertEqual([i['ammunition_count'] for i in profile['inventory']], [45, 30])
        self.assertEqual(profile['ammunition_depot']['shell:ms1-stock-ap'], 90)
        self.assertEqual(profile['ammunition_depot']['shell:is7-stock-ap'], 85)
        self.assertEqual(len(bytes.fromhex(second['update_hex'])) < 241, True)

    def test_unload_returns_owned_ammo_and_preserves_balances(self):
        self.migrate(); self.service(self.command(counts=(0, 0, 0)))
        self.assertEqual(self.store.read_profile(self.account)['depot']['shell:ms1-stock-ap'], 120)

    def test_native_signed_order_is_persisted_and_bound_to_replay(self):
        self.migrate(); command = self.command(); command['layout'][3:9] = [-3082, 5, -2570, 30, 2826, 10]
        self.service(command)
        self.assertEqual(self.store.layouts(self.account)[1], command['layout'][3:9])
        replay = self.service(command); self.assertTrue(replay['replayed'])
        command['layout'][3] *= -1
        self.rejected_unchanged(command, 'DUPLICATE_PAYLOAD_MISMATCH')

    def test_original_replay_after_later_change_and_reopen(self):
        self.migrate(); command = self.command(); original = self.service(command)
        self.service(self.command(counts=(0, 0, 0), key='later', revision=6, wire=2))
        self.store.close(); self.store = NativeAmmoStore(self.database); self.store.initialize()
        before = self.snapshot(); replay = self.service(command)
        self.assertEqual(replay, {**original, 'replayed': True}); self.assertEqual(before, self.snapshot())

    def test_stale_revision_and_mismatched_wire_replay_reject(self):
        self.migrate(); command = self.command(); self.service(command)
        self.rejected_unchanged(self.command(key='stale'), 'STALE_REVISION')
        command['wire_revision'] = 2
        self.rejected_unchanged(command, 'DUPLICATE_PAYLOAD_MISMATCH')

    def test_foreign_native_identity_and_account_reject(self):
        self.migrate()
        command = self.command(); command['account_id'] = 'other'
        self.rejected_unchanged(command, 'FOREIGN_ACCOUNT')
        command = self.command(); command['native_database_id'] += 1
        self.rejected_unchanged(command, 'FOREIGN_ACCOUNT')

    def test_invalid_layouts_preserve_all_state(self):
        self.migrate()
        cases = [(1, 3, 'UNKNOWN_VEHICLE'), (0, 2, 'SHOP_REVISION_MISMATCH'), (3, 14602, 'INCOMPATIBLE_SHELL'),
                 (10, 1, 'EQUIPMENT_UNSUPPORTED'), (4, -1, 'INVALID_QUANTITY'), (4, True, 'INVALID_INPUT')]
        for index, value, code in cases:
            with self.subTest(code=code):
                request = self.command(); request['layout'][index] = value; self.rejected_unchanged(request, code)
        self.rejected_unchanged(self.command(counts=(96, 1, 0)), 'CAPACITY_EXCEEDED')

    def test_insufficient_stock_preserves_old_load(self):
        self.migrate()
        # Test fixture represents a future depleted owned depot. Rebuild both
        # projections transactionally; this is not an exposed runtime writer.
        self.store.connection.execute('BEGIN IMMEDIATE')
        self.store.connection.execute("UPDATE p09c_ammo_depot SET quantity=0 WHERE account_id=? AND shell_id='shell:ms1-stock-he'", (self.account,))
        AmmoServiceStore._save_snapshot(self.store, self.account, 5)
        aggregate = json.loads(self.store.connection.execute('SELECT snapshot_json FROM game_snapshot WHERE account_id=?', (self.account,)).fetchone()[0])
        value = self.store._project_profile(self.account, aggregate)
        self.store.connection.execute('UPDATE game_profiles SET profile_json=? WHERE account_id=?', (canonical(value).decode('ascii'), self.account))
        self.store.connection.commit()
        self.rejected_unchanged(self.command(), 'INSUFFICIENT_STOCK')

    def test_five_failure_points_roll_back_profile_layout_depot_and_ledgers(self):
        self.migrate()
        for point in ('after_depot_update', 'after_ammo_update', 'after_profile_projection', 'after_snapshot_update', 'before_commit'):
            with self.subTest(point=point):
                self.store.failpoint = point; self.rejected_unchanged(self.command(), 'INJECTED_FAILURE')
        self.store.failpoint = None

    def test_direct_game_profile_edit_detected_before_commit(self):
        self.migrate()
        raw = self.store.connection.execute('SELECT profile_json FROM game_profiles WHERE account_id=?', (self.account,)).fetchone()[0]
        changed = json.loads(raw); changed['resources']['credits'] += 1
        self.store.connection.execute('UPDATE game_profiles SET profile_json=? WHERE account_id=?', (json.dumps(changed), self.account)); self.store.connection.commit()
        self.rejected_unchanged(self.command(), 'CORRUPT_STORE')

    def test_immutable_fixture_refresh_and_relogin_preserve_dossier(self):
        self.migrate(); destination = Path(self.temp.name) / 'fixtures'
        first = self.store.publish(self.source, self.account, destination)
        raw = (Path(first['fixture_dir']) / 'state.bin').read_bytes()
        self.service(); second = self.store.publish(self.source, self.account, destination)
        self.assertNotEqual(first['fixture_dir'], second['fixture_dir'])
        self.assertEqual((Path(first['fixture_dir']) / 'state.bin').read_bytes(), raw)
        self.assertEqual((Path(second['fixture_dir']) / 'dossier.bin').read_bytes(), self.source.raw['dossier.bin'])
        self.assertEqual(self.store.publish(self.source, self.account, destination)['fixture_dir'], second['fixture_dir'])
        metadata = json.loads((Path(second['fixture_dir']) / 'ammo-service.json').read_text())
        self.assertEqual((metadata['revision'], metadata['wire_revision']), (6, 1))

    def test_concurrent_duplicate_connections_commit_once(self):
        self.migrate(); command = self.command(); barrier = threading.Barrier(2)
        def apply():
            with NativeAmmoStore(self.database) as store:
                store.initialize(); barrier.wait()
                return store.service(command, authenticated_account_id=self.account)
        with ThreadPoolExecutor(max_workers=2) as pool: values = list(pool.map(lambda _: apply(), range(2)))
        self.assertEqual(sorted(v['replayed'] for v in values), [False, True])
        self.assertEqual(self.store.read_profile(self.account)['revision'], 6)
        self.assertEqual(self.store.ledger_count(self.account), 1)

    def test_battle_writer_is_explicitly_unavailable(self):
        self.migrate(); before = self.snapshot()
        with self.assertRaises(TransactionError) as error: self.store.reserve_vehicle()
        self.assertEqual(error.exception.code, 'BATTLE_UNSUPPORTED'); self.assertEqual(before, self.snapshot())

    def test_existing_reserved_vehicle_refuses_service(self):
        self.migrate()
        self.store.connection.execute('BEGIN IMMEDIATE')
        self.store.connection.execute("UPDATE game_vehicle SET state='reserved',battle_id='test-battle' WHERE account_id=? AND vehicle_id=?",
                                      (self.account, self.account + ':starter-vehicle-v1'))
        AmmoServiceStore._save_snapshot(self.store, self.account, 5)
        self.store.connection.commit()
        self.rejected_unchanged(self.command(), 'VEHICLE_RESERVED')

    def test_corrupt_native_response_never_returns_success_on_replay(self):
        self.migrate(); command = self.command(); self.service(command)
        self.store.connection.execute("UPDATE p09d_native_command SET response_sha256=? WHERE account_id=?", ('0' * 64, self.account))
        self.store.connection.commit()
        self.rejected_unchanged(command, 'CORRUPT_STORE')

    def test_concurrent_different_commands_share_one_revision(self):
        self.migrate(); barrier = threading.Barrier(2)
        def apply(index):
            with NativeAmmoStore(self.database) as store:
                store.initialize(); barrier.wait()
                try:
                    store.service(self.command(key='racing-' + str(index), counts=(20 + index, 0, 0)), authenticated_account_id=self.account)
                    return 'COMMITTED'
                except TransactionError as error: return error.code
        with ThreadPoolExecutor(max_workers=2) as pool: values = list(pool.map(apply, range(2)))
        self.assertEqual(sorted(values), ['COMMITTED', 'STALE_REVISION'])
        self.assertEqual(self.store.read_profile(self.account)['revision'], 6)
        self.assertEqual(self.store.ledger_count(self.account), 1)

    def test_existing_fixture_bytes_extra_members_and_oversize_fail_closed(self):
        self.migrate()
        for case in ('bytes', 'extra', 'oversize'):
            with self.subTest(case=case):
                result = self.store.publish(self.source, self.account, Path(self.temp.name) / ('fixtures-' + case))
                destination = Path(result['fixture_dir'])
                if case == 'extra': (destination / 'unexpected.bin').write_bytes(b'x')
                elif case == 'oversize': (destination / 'state.bin').write_bytes(b'x' * 65536)
                else:
                    path = destination / 'state.bin'; raw = path.read_bytes(); path.write_bytes(raw[:-1] + b'x')
                before = self.snapshot()
                with self.assertRaises(TransactionError) as error:
                    self.store.publish(self.source, self.account, destination.parent.parent)
                self.assertEqual(error.exception.code, 'FIXTURE_CHANGED')
                self.assertEqual(self.snapshot(), before)

    def test_linked_fixture_directory_is_rejected_before_publication(self):
        self.migrate()
        target = Path(self.temp.name) / 'actual'; target.mkdir()
        link = Path(self.temp.name) / 'redirected'
        if os.name == 'nt':
            quote = lambda path: "'" + str(path).replace("'", "''") + "'"
            result = subprocess.run(['powershell', '-NoProfile', '-Command',
                'New-Item -ItemType Junction -Path ' + quote(link) + ' -Target ' + quote(target) + ' | Out-Null'],
                capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
        else: link.symlink_to(target, target_is_directory=True)
        try:
            with self.assertRaises(ValueError): self.store.publish(self.source, self.account, link)
            self.assertEqual(list(target.iterdir()), [])
        finally:
            if os.name == 'nt': os.rmdir(link)
            else: link.unlink()


if __name__ == '__main__': unittest.main()
