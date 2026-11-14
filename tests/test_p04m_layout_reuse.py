"""Layout validation with isolated synthetic SQLite; no client or account fixture."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from game_profile_tx import TransactionError
from p04m_pool_store import PoolStore


class LayoutStore(PoolStore):
    """Only unrelated research and ammunition projections are test inputs."""
    def __init__(self):
        self.connection = sqlite3.connect(':memory:')
        self.connection.execute('CREATE TABLE p09d_native_layout (account_id TEXT, native_vehicle_id INTEGER, layout_json TEXT)')
        self.pool_account = 'account-test'
        self.registry = SimpleNamespace(by_vehicle={
            'vehicle-a': SimpleNamespace(assembly_id='mount-a'),
            'vehicle-b': SimpleNamespace(assembly_id='mount-b'),
        })
        self.pair_mount = {}
        self.mounts = {
            'mount-a': SimpleNamespace(shell_ids=('a1', 'a2', 'a3'), capacity=10),
            'mount-b': SimpleNamespace(shell_ids=('b1', 'b2', 'b3'), capacity=12),
        }
        self.shells = {key: SimpleNamespace(native_compact_id=cd) for key, cd in (
            ('a1', 101), ('a2', 102), ('a3', 103), ('b1', 201), ('b2', 202), ('b3', 203))}
        self.vehicles = [self._vehicle(1, 'vehicle-a', 'inventory-a'), self._vehicle(2, 'vehicle-b', 'inventory-b')]
        self.loads = {'inventory-a': {'a1': 1, 'a2': 2, 'a3': 3},
                      'inventory-b': {'b1': 2, 'b2': 1, 'b3': 0}}
        self.connection.executemany('INSERT INTO p09d_native_layout VALUES (?,?,?)', [
            (self.pool_account, 1, json.dumps([101, 1, 102, 2, 103, 3])),
            (self.pool_account, 2, json.dumps([201, 2, 202, 1, 203, 0])),
        ])
        self.connection.commit()
        self.research_reads = 0
        self.active_checks = 0
        self.corrupt_research = False

    @staticmethod
    def _vehicle(native_id, vehicle_id, inventory_id):
        return {'native_id': native_id, 'vehicle_id': vehicle_id, 'vehicle_inventory_id': inventory_id,
                'modules': {'turret': 'stock-turret', 'gun': 'stock-gun'}}

    def pool_active(self):
        self.active_checks += 1
        return True

    def _research(self, account):
        self.research_reads += 1
        if account != self.pool_account or self.corrupt_research:
            raise TransactionError('CORRUPT_STORE')
        return {'vehicles': deepcopy(self.vehicles)}

    def _ammo_projection(self, account):
        return ([{'vehicle_id': key, 'loaded': deepcopy(value)} for key, value in self.loads.items()], {})


class LayoutReuseTests(unittest.TestCase):
    def setUp(self):
        self.store = LayoutStore()
        self.addCleanup(self.store.connection.close)

    def test_transaction_reuses_checked_research_and_checks_each_layout(self):
        c = self.store.connection
        c.execute('BEGIN')
        try:
            result = self.store.layouts(self.store.pool_account)
            self.assertEqual(result, {1: [101, 1, 102, 2, 103, 3], 2: [201, 2, 202, 1, 203, 0]})
            self.assertEqual(self.store.research_reads, 1)
            self.assertEqual(self.store.active_checks, 3)  # layouts + each layout
        finally:
            c.rollback()

    def test_outside_transaction_and_direct_command_read_fresh_research(self):
        self.store.layouts(self.store.pool_account)
        self.assertEqual(self.store.research_reads, 3)
        request = [5, 1, 6, 101, 1, 102, 2, 103, 3, 6, 0, 0, 0, 0, 0, 0]
        self.store._validate_layout(request)
        self.store.vehicles = [self.store.vehicles[1]]
        with self.assertRaises(TransactionError) as caught:
            self.store._validate_layout(request)
        self.assertEqual(caught.exception.code, 'UNKNOWN_VEHICLE')
        self.assertEqual(self.store.research_reads, 5)

    def test_research_not_retained_between_transactions(self):
        c = self.store.connection
        c.execute('BEGIN')
        self.store.layouts(self.store.pool_account)
        c.rollback()
        self.store.corrupt_research = True
        c.execute('BEGIN')
        try:
            with self.assertRaises(TransactionError) as caught:
                self.store.layouts(self.store.pool_account)
            self.assertEqual(caught.exception.code, 'CORRUPT_STORE')
        finally:
            c.rollback()

    def test_invalid_layouts_fail_in_transaction(self):
        c = self.store.connection
        for invalid in ('not-json', json.dumps([999, 1, 102, 2, 103, 3]),
                        json.dumps([101, 11, 102, 0, 103, 0])):
            c.execute('BEGIN')
            try:
                c.execute('UPDATE p09d_native_layout SET layout_json=? WHERE native_vehicle_id=1', (invalid,))
                with self.assertRaises(TransactionError) as caught:
                    self.store.layouts(self.store.pool_account)
                self.assertEqual(caught.exception.code, 'CORRUPT_STORE')
            finally:
                c.rollback()

    def test_changed_owned_ids_are_not_reused_in_next_transaction(self):
        c = self.store.connection
        c.execute('BEGIN')
        self.store.layouts(self.store.pool_account)
        c.rollback()
        self.store.vehicles[0]['native_id'] = 7
        c.execute('UPDATE p09d_native_layout SET native_vehicle_id=7 WHERE native_vehicle_id=1')
        c.commit()
        c.execute('BEGIN')
        try:
            self.assertEqual(set(self.store.layouts(self.store.pool_account)), {2, 7})
        finally:
            c.rollback()

    def test_research_is_rechecked_for_each_call_even_in_one_transaction(self):
        c = self.store.connection
        c.execute('BEGIN')
        try:
            self.store.layouts(self.store.pool_account)
            self.store.corrupt_research = True
            with self.assertRaises(TransactionError) as caught:
                self.store.layouts(self.store.pool_account)
            self.assertEqual(caught.exception.code, 'CORRUPT_STORE')
        finally:
            c.rollback()

    def test_valid_layout_must_also_match_authoritative_ammo(self):
        self.store.loads['inventory-b']['b1'] = 3
        c = self.store.connection
        c.execute('BEGIN')
        try:
            with self.assertRaises(TransactionError) as caught:
                self.store.layouts(self.store.pool_account)
            self.assertEqual(caught.exception.code, 'CORRUPT_STORE')
        finally:
            c.rollback()

    def test_foreign_account_and_unowned_or_unsupported_command_are_rejected(self):
        with self.assertRaises(TransactionError) as caught:
            self.store.layouts('another-account')
        self.assertEqual(caught.exception.code, 'FOREIGN_ACCOUNT')
        request = [5, 99, 6, 101, 1, 102, 2, 103, 3, 6, 0, 0, 0, 0, 0, 0]
        with self.assertRaises(TransactionError) as caught:
            self.store._validate_layout(request)
        self.assertEqual(caught.exception.code, 'UNKNOWN_VEHICLE')
        self.store.vehicles.append(self.store._vehicle(99, 'unsupported-vehicle', 'inventory-unsupported'))
        with self.assertRaises(TransactionError) as caught:
            self.store._validate_layout(request)
        self.assertEqual(caught.exception.code, 'UNSUPPORTED_MOUNT')


if __name__ == '__main__':
    unittest.main()
