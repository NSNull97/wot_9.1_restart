"""Profile-only late decoder bounds; no network, real DB or battle claim."""
import json
from pathlib import Path
import sqlite3
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT)]
from game_profile_tx import TransactionError
from p08c_late_results import LateResults, decode, decode_stored_profile
from p09c_ammo_service import _object
from p09e_research_store import MAX_OWNED, _json
from p04m_pool_crew import CrewContract, CrewContractV2

ACCOUNT = '12345678-1234-4234-8234-123456789000'


class OwnProfileStore:
    """Legacy writer's real bounded JSON reader, with authored shell keys."""
    def __init__(self, shells, version=1):
        self.shells = {f'shell:test-{i}': object() for i in range(shells)}
        self.contract = CrewContractV2 if version == 2 else CrewContract
    def _crew_contract(self):
        return self.contract
    def _stored_json(self, raw):
        return _json(raw) if self.contract is CrewContractV2 and len(raw) > 16384 else _object(raw)


def profile(store):
    return {'account_id': ACCOUNT, 'native_database_id': 1, 'profile_version': 13,
            'ammunition_depot': {key: 0 for key in store.shells}}


def raw(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


class StoredProfileBounds(unittest.TestCase):
    def test_legacy_and_catalog_depot_accepted_only_by_the_profile_decoder(self):
        for shells in (15, 32, 36):
            with self.subTest(shells=shells):
                store = OwnProfileStore(shells)
                value = profile(store)
                self.assertEqual(decode_stored_profile(raw(value), store), value)
        with self.assertRaises(TransactionError):
            decode(raw(profile(OwnProfileStore(36))))  # Network cap remains 32.

    def test_exact_depot_and_bounded_values_are_required(self):
        store = OwnProfileStore(36)
        for mode in ('extra', 'missing', 'negative', 'too_many', 'bool'):
            value = profile(store)
            if mode == 'extra': value['ammunition_depot']['shell:unexpected'] = 0
            if mode == 'missing': value['ammunition_depot'].pop(next(iter(store.shells)))
            if mode == 'negative': value['ammunition_depot'][next(iter(store.shells))] = -1
            if mode == 'too_many': value['ammunition_depot'][next(iter(store.shells))] = 1000001
            if mode == 'bool': value['ammunition_depot'][next(iter(store.shells))] = True
            with self.subTest(mode=mode), self.assertRaises(TransactionError):
                decode_stored_profile(raw(value), store)

    def test_profile_array_cap_and_network_array_cap_are_separate(self):
        store = OwnProfileStore(36)
        value = profile(store)
        value['ammunition'] = [0] * (MAX_OWNED * 3)  # Authored bound only, not a valid full profile.
        self.assertEqual(len(decode_stored_profile(raw(value), store)['ammunition']), MAX_OWNED * 3)
        with self.assertRaises(TransactionError): decode(raw(value))
        value['ammunition'].append(0)
        with self.assertRaises(TransactionError): decode_stored_profile(raw(value), store)

    def test_catalog_shell_count_is_not_bounded_by_one_owners_garage(self):
        # Authored future catalog, within v1 byte bound; no claim of acceptance
        # by today's pinned CAT catalog or any actual game profile.
        store = OwnProfileStore(MAX_OWNED * 3 + 1)
        value = profile(store)
        self.assertLessEqual(len(raw(value).encode('ascii')), CrewContract.PROFILE_BOUND)
        self.assertEqual(decode_stored_profile(raw(value), store), value)

    def test_duplicate_deep_float_and_oversized_json_are_refused(self):
        store = OwnProfileStore(36)
        duplicate = raw(profile(store)).replace('"profile_version":13', '"profile_version":13,"profile_version":13')
        values = [duplicate, '{"x":' * 14 + '0' + '}' * 14,
                  raw(profile(store))[:-1] + ',"bad":1.5}',
                  raw(profile(store))[:-1] + ',"bad":"' + 'x' * (16 * 1024) + '"}']
        for value in values:
            with self.subTest(length=len(value)), self.assertRaises(TransactionError):
                decode_stored_profile(value, store)

    def test_stored_profile_bytes_follow_selected_crew_contract(self):
        for version, limit in ((1, CrewContract.PROFILE_BOUND), (2, CrewContractV2.PROFILE_BOUND)):
            store = OwnProfileStore(36, version)
            value = profile(store); value['padding'] = ''
            empty = raw(value); value['padding'] = 'x' * (limit - len(empty))
            bounded = raw(value)
            self.assertEqual(len(bounded.encode('ascii')), limit)
            self.assertEqual(decode_stored_profile(bounded, store), value)
            value['padding'] += 'x'
            with self.assertRaises(TransactionError): decode_stored_profile(raw(value), store)

    def test_native_owner_binding_and_read_only(self):
        store = OwnProfileStore(36)
        with sqlite3.connect(':memory:') as db:
            db.execute('CREATE TABLE game_profiles(account_id TEXT PRIMARY KEY, profile_json TEXT)')
            db.execute('INSERT INTO game_profiles VALUES (?,?)', (ACCOUNT, raw(profile(store))))
            db.commit(); before = db.total_changes
            adapter = object.__new__(LateResults); adapter.store = store; adapter.connection = db
            self.assertIsNone(adapter.native(ACCOUNT, 1)); self.assertEqual(db.total_changes, before)
            for account, native in ((ACCOUNT, 2), ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 1)):
                with self.assertRaises(TransactionError): adapter.native(account, native)
            self.assertEqual(db.total_changes, before)


if __name__ == '__main__':
    unittest.main()
