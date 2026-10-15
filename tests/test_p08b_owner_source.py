"""Real SQLite owner grant/onboarding controls; no native B delivery claim."""
from copy import deepcopy
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from p08b_owner_source import OwnerProjectionSource, projection_source, stage, EVIDENCE, DEFINITIONS
from p08b_owner_onboard import onboard, _owner_digest, _rows, ACCOUNT_TABLES, GLOBAL_TABLES
from p08b_battle_store import BattleStore
from p08b_battle_projection import BattleProjectionSource
from p09e_research_catalog import load_catalog
from p09d_ammo_projection import canonical
from game_profile_tx import TransactionError

A = 'c5326cc1-8524-479c-8bba-72e973489c22'
B = '271022a3-41e0-406e-b6fa-59930c320442'
BUNDLE = Path(os.environ.get('P04D_TEST_BUNDLE', ROOT/'local/stands/p09e-main-01/source-bundle-05'))
ORIGINAL = 'C:/WoT_0.9.1_RU_0717_original'


def backup(source, target):
    with closing(sqlite3.connect(Path(source).resolve().as_uri() + '?mode=ro', uri=True)) as before, closing(sqlite3.connect(target)) as after:
        before.backup(after)


class SourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not BUNDLE.is_dir(): raise unittest.SkipTest('NOT_RUN: source bundle unavailable')
        cls.catalog = load_catalog(ORIGINAL)
        cls.anchor = BattleProjectionSource(BUNDLE, cls.catalog)
        cls.base = cls.anchor.bundle.read_json('fixtures/profile1/profile-input.json')
        cls.source = OwnerProjectionSource(BUNDLE, cls.catalog, cls.base, granted_at_ms=1792070000000)

    def test_real_second_identity_and_naturally_owned_grant_ids(self):
        source = self.source
        self.assertIsInstance(source, BattleProjectionSource)
        self.assertEqual(source.profile['account_id'], B)
        self.assertEqual(source.profile['native_database_id'], 2)
        self.assertTrue(all(row['inventory_id'].startswith(B + ':') for row in source.profile['inventory']))
        self.assertTrue(all(row['crew_id'].startswith(B + ':') for row in source.profile['crew']))
        self.assertEqual(source.trees['state.bin']['inventory'][1]['crew'][1], [1, 2])
        self.assertEqual(source.profile['ammunition'][0]['count'], 20)
        self.assertEqual(source.proof['native_owner_export'], 'NOT_RUN')
        self.assertTrue(all(row['observed_account_id'] == A and row['observed_native_database_id'] == 1
                            for row in source.proof['definition_exports']))

    def test_anchor_original_exports_and_inventory_are_unchanged(self):
        for content_id, digest in DEFINITIONS.items():
            self.assertEqual(hashlib.sha256(self.anchor.bundle.read(content_id)).hexdigest(), digest)
        self.assertEqual(self.anchor.profile['account_id'], A)
        self.assertEqual(self.anchor.profile['native_database_id'], 1)
        self.assertEqual(self.anchor.trees['state.bin']['inventory'][1]['shells'][1], [2570, 20, 2826, 0, 3082, 0])

    def test_reopen_recomputes_entire_own_grant_chain(self):
        rebuilt = OwnerProjectionSource.from_profile4(BUNDLE, self.catalog, self.source.profile)
        self.assertEqual(rebuilt.bundle_sha256, self.source.bundle_sha256)
        self.assertEqual(rebuilt.raw, self.source.raw)
        for mutate in ('foreign_crew', 'ammo_count', 'parent_hash', 'timestamp'):
            profile = deepcopy(self.source.profile)
            if mutate == 'foreign_crew': profile['crew'][0]['crew_id'] = A + ':ms1-commander-v1'
            elif mutate == 'ammo_count': profile['ammunition'][0]['count'] = 21
            elif mutate == 'parent_hash': profile['crew_grant']['base_profile_sha256'] = '0' * 64
            else: profile['ammo_grant']['granted_at_ms'] += 100
            with self.subTest(mutate=mutate), self.assertRaises(TransactionError):
                OwnerProjectionSource.from_profile4(BUNDLE, self.catalog, profile)

    def test_unknown_fields_and_anchor_regrant_are_rejected(self):
        base = deepcopy(self.base); base['inventory'] = []
        with self.assertRaises(ValueError): OwnerProjectionSource(BUNDLE, self.catalog, base, granted_at_ms=1792070000000)
        base = {key: self.anchor.profile[key] for key in self.base}
        base.update(profile_version=1, snapshot_revision=1)
        with self.assertRaises(TransactionError): OwnerProjectionSource(BUNDLE, self.catalog, base, granted_at_ms=1792070000000)


class OnboardingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        paths = [BUNDLE, ROOT/'local/server/game.sqlite', ROOT/'local/web/runtime/portal.sqlite',
                 ROOT/'local/stands/p09e-main-01/game.sqlite']
        if not all(path.exists() for path in paths):
            raise unittest.SkipTest('NOT_RUN: explicit local source/real-owner snapshots unavailable')
        cls.temp = tempfile.TemporaryDirectory(prefix='owner-tests-', dir=EVIDENCE)
        cls.base = Path(cls.temp.name).resolve()
        if not cls.base.is_relative_to(EVIDENCE.resolve()): raise ValueError('test output escaped evidence root')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.catalog = load_catalog(ORIGINAL)
        result = stage(ROOT/'local/server/game.sqlite', ROOT/'local/web/runtime/portal.sqlite', B,
            BUNDLE, ORIGINAL, cls.base/'stage', granted_at_ms=1792070000000)
        cls.stage_database = Path(result['database'])
        cls.a_database = cls.base/'a.sqlite'
        backup(ROOT/'local/stands/p09e-main-01/game.sqlite', cls.a_database)
        with BattleStore(cls.a_database, cls.catalog) as store:
            store.activate(account_id=A, authenticated_account_id=A)
            cls.real_a = canonical(store.read_profile(A))

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix='case-', dir=self.base))
        self.target, self.staged = self.directory/'target.sqlite', self.directory/'stage.sqlite'
        backup(self.a_database, self.target)
        backup(self.stage_database, self.staged)

    def merge(self, name='receipt.json'):
        return onboard(self.target, self.staged, BUNDLE, ORIGINAL, B, self.directory/name)

    def snapshot(self):
        with closing(sqlite3.connect(self.target)) as db:
            return canonical({table: _rows(db, table) for table in ACCOUNT_TABLES + GLOBAL_TABLES})

    def test_two_real_owners_in_one_database_reopen_publish_and_no_a_replacement(self):
        result = self.merge()
        self.assertEqual(result['status'], 'ONBOARDED')
        self.assertTrue(result['global_ddl_policy_catalog_equal'])
        with BattleStore(self.target, self.catalog) as store:
            self.assertEqual(canonical(store.read_profile(A)), self.real_a)
            second = store.read_profile(B)
            self.assertEqual(second['account_id'], B)
            self.assertEqual([row['native_id'] for row in second['crew_inventory']['members']], [1, 2, 3])
            source = projection_source(BUNDLE, self.catalog, self.target, B)
            published = store.publish(source, B, self.directory/'fixtures')
            self.assertEqual(published['profile']['native_database_id'], 2)
            self.assertEqual(published['profile']['profile_version'], 13)
        before = self.snapshot()
        self.assertEqual(self.merge('replay.json')['status'], 'ALREADY_ONBOARDED')
        self.assertEqual(self.snapshot(), before)

    def test_global_schema_policy_and_native_id_collisions_leave_target_unchanged(self):
        for mutation in ('policy', 'extra_table', 'native_collision'):
            with self.subTest(mutation=mutation):
                backup(self.a_database, self.target)
                with closing(sqlite3.connect(self.target)) as db, db:
                    if mutation == 'policy': db.execute("UPDATE p08b_schema SET policy_sha256=?", ('0'*64,))
                    elif mutation == 'extra_table': db.execute('CREATE TABLE unknown_table(account_id TEXT)')
                    else: db.execute('UPDATE game_profiles SET native_id=2 WHERE account_id=?', (A,))
                before = self.snapshot()
                with self.assertRaises(TransactionError): self.merge(mutation+'.json')
                self.assertEqual(self.snapshot(), before)

    def test_tampered_source_binding_never_inserts_second_owner(self):
        with closing(sqlite3.connect(self.staged)) as db, db:
            db.execute('UPDATE p09d_import SET bundle_sha256=? WHERE account_id=?', ('f'*64, B))
        before = self.snapshot()
        with self.assertRaises(TransactionError): self.merge()
        self.assertEqual(self.snapshot(), before)

    def test_already_imported_owner_cannot_be_replaced_with_different_state(self):
        self.merge()
        with closing(sqlite3.connect(self.target)) as db, db:
            db.execute('UPDATE game_profiles SET profile_json=profile_json||char(32) WHERE account_id=?', (B,))
        before = self.snapshot()
        with self.assertRaises(TransactionError): self.merge('changed.json')
        self.assertEqual(self.snapshot(), before)

    def test_owner_with_real_open_battle_run_is_not_fresh_onboarding(self):
        with BattleStore(self.staged, self.catalog) as store:
            revision = store.read_profile(B)['revision']
            request = dict(version=1, operation='run_open', account_id=B, native_database_id=2,
                command_key='owner-test:run', expected_revision=revision,
                run_id='3285cb7e-8572-4f85-bb55-b126b827f343')
            store.battle(request, authenticated_account_id=B)
        before = self.snapshot()
        with self.assertRaises(TransactionError): self.merge()
        self.assertEqual(self.snapshot(), before)

    def test_live_hangar_database_is_outside_mutation_boundary(self):
        with self.assertRaises(TransactionError):
            onboard(ROOT/'local/stands/p09e-main-01/game.sqlite', self.staged, BUNDLE, ORIGINAL, B,
                    self.directory/'forbidden.json')


if __name__ == '__main__': unittest.main()
