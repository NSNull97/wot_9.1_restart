"""Real SQLite CMD303, frozen J retirement replay and shared lifetime allocation."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from tests import test_p04j_crew_store as previous
from p04k_crew_store import NativeBarracksRecruitmentStore, SOURCE_AUDIT_SHA256, BARRACKS_COMMAND
from p04k_crew_projection import BarracksRecruitmentProjectionSource, POLICY_SHA256, SHOP_SHA256, canonical, native_crew
from p04j_crew_store import NativeCrewDismissalStore
from p04i_crew_store import NativeCrewProgressionStore
from p04h_crew_store import NativeRosterRecruitmentStore
from p04g_crew_store import NativeCrossVehicleCrewStore
from p04f_crew_store import NativeCrewTransferStore
from p04d_crew_store import NativeCrewStore
from p09d_ammo_store import NativeAmmoStore
from game_profile_tx import TransactionError


class BarracksStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        previous.DismissalStoreTests.setUpClass.__func__(cls)
        cls.source = BarracksRecruitmentProjectionSource(os.environ.get('P04K_TEST_BUNDLE') or os.environ['P04D_TEST_BUNDLE'])

    def setUp(self):
        previous.DismissalStoreTests.setUp(self)
        previous.DismissalStoreTests.activate(self)
        self.store.close(); self.store = NativeBarracksRecruitmentStore(self.database)

    profile = previous.DismissalStoreTests.profile
    public = previous.DismissalStoreTests.public
    request = previous.DismissalStoreTests.request
    transfer = previous.DismissalStoreTests.transfer
    hire = previous.DismissalStoreTests.hire
    learn = previous.DismissalStoreTests.learn
    dismiss = previous.DismissalStoreTests.dismiss
    ammo = previous.DismissalStoreTests.ammo
    state = previous.DismissalStoreTests.state
    reject = previous.DismissalStoreTests.reject
    old_request = previous.DismissalStoreTests.old_request
    reserve = previous.DismissalStoreTests.reserve

    def activate(self):
        return self.store.migrate_barracks(self.source, account_id=self.account, original_root=self.original)

    def bar(self, compact=7169, role=4, **changes):
        return self.store.recruit_barracks(self.request([3,compact,role,0], **changes), authenticated_account_id=self.account)

    def reopen(self):
        self.store.close(); self.store = NativeBarracksRecruitmentStore(self.database); self.store.initialize()

    def test_explicit_migration_preserves_sparse_members_terminal_rows_and_all_resources(self):
        self.reject('P04K_MIGRATION_REQUIRED', self.store.initialize)
        with NativeCrewDismissalStore(self.database) as old:
            old.dismiss(dict(self.old_request(), expected_revision=12, command_key='J-terminal', layout=[3,0,0]), authenticated_account_id=self.account)
            before = old.read_profile(self.account)
            retired = [tuple(r) for r in old.connection.execute('SELECT * FROM p04j_retired_member')]
        result = self.activate(); after = self.profile()
        expected = deepcopy(before['crew_inventory']); expected['policy_sha256'] = POLICY_SHA256
        self.assertEqual(after['crew_inventory'], expected)
        self.assertEqual((result['revision'], result['retained_tankmen'], result['retired_tankmen']), (14,2,1))
        self.assertEqual(retired, [tuple(r) for r in self.store.connection.execute('SELECT * FROM p04j_retired_member')])
        for key in ('vehicles','ammunition','depot'): self.assertEqual(before[key], after[key])
        self.assertEqual(after['crew_barracks_source_audit_sha256'], SOURCE_AUDIT_SHA256)
        self.assertEqual(self.public()['profile_version'], 12)
        self.bar(); self.reopen(); before = self.state()
        self.assertEqual(self.activate()['status'], 'already_migrated'); self.assertEqual(before, self.state())

    def test_migration_failpoints_restore_all_schema_markers_and_old_writer(self):
        for point in ('after_barracks_tables','after_snapshot_update','after_profile_projection','before_barracks_migration_commit'):
            self.store.failpoint = point; self.reject('INJECTED_FAILURE', self.activate)
            with NativeCrewDismissalStore(self.database) as old: self.assertEqual(old.read_profile(self.account)['revision'], 12)
            self.assertIsNone(self.store.connection.execute("SELECT 1 FROM sqlite_master WHERE name='p04k_schema'").fetchone())
        self.store.failpoint = None; self.activate()

    def test_every_old_writer_rejects_migrated_state(self):
        self.activate(); before = self.state()
        for writer in (NativeCrewStore, NativeCrewTransferStore, NativeCrossVehicleCrewStore,
                       NativeRosterRecruitmentStore, NativeCrewProgressionStore, NativeCrewDismissalStore, NativeAmmoStore):
            with writer(self.database) as old:
                with self.assertRaises(TransactionError): old.read_profile(self.account)
        self.assertEqual(before, self.state())

    def test_two_bar_hires_exact_response_and_unchanged_existing_seats_after_reopen(self):
        self.activate(); before = self.profile(); resources = self.public()['resources']
        for compact, role, identity in ((7169,4,4),(3329,1,5)):
            reply = self.bar(compact,role)
            self.assertEqual(len(reply), 11)
            self.assertEqual((reply['status'],reply['result_code'],reply['tankman_inventory_id']), ('recruited',0,identity))
            self.assertEqual(reply['tankman_descriptor_hex'], self.profile()['crew_inventory']['members'][-1]['descriptor_hex'])
            self.assertEqual(len(reply['tankman_descriptor_hex']),50)
        self.reopen(); after = self.profile()
        self.assertEqual(native_crew(after['crew_inventory'])[1], native_crew(before['crew_inventory'])[1])
        self.assertEqual(after['crew_inventory']['members'][:3], before['crew_inventory']['members'])
        self.assertEqual((after['revision'], after['crew_inventory']['next_native_id'], after['crew_inventory']['free_recruitment_left']), (15,6,11))
        self.assertEqual(self.public()['resources'],resources)
        for key in ('vehicles','ammunition','depot'): self.assertEqual(before[key],after[key])

    def test_malformed_foreign_stale_and_wrong_shop_requests_are_atomic(self):
        self.activate()
        for layout in ([True,7169,4,0],[3,7169,False,0],[3,7169,4,False],[3,7169,4.0,0],
                       [0,7169,4,0],[3,1,4,0],[3,7185,4,0],[3,3329,4,0],[3,7169,4,1],[3,7169,4]):
            before = self.state()
            with self.assertRaises(TransactionError): self.store.recruit_barracks(self.request(layout), authenticated_account_id=self.account)
            self.assertEqual(before, self.state())
        self.reject('FOREIGN_ACCOUNT', lambda:self.store.recruit_barracks(self.request([3,7169,4,0]), authenticated_account_id='foreign'))
        self.reject('FOREIGN_ACCOUNT', lambda:self.bar(native_database_id=999))
        self.reject('STALE_REVISION', lambda:self.bar(expected_revision=12))

    def test_barracks_hire_has_no_invented_vehicle_reservation_but_other_commands_retain_it(self):
        self.activate(); self.reserve(1); self.reserve(2); self.bar()
        self.reject('VEHICLE_RESERVED', self.hire)
        self.reject('VEHICLE_RESERVED', lambda:self.transfer([2,1,4]))
        self.reject('VEHICLE_RESERVED', lambda:self.dismiss(1))

    def test_all_writer_failpoints_rollback_member_meta_aggregate_and_both_ledgers(self):
        self.activate(); before = self.state()
        for point in ('after_transfer_unassign','after_transfer_assign','after_transfer_meta_update','after_snapshot_update',
                      'after_profile_projection','after_transfer_ledger_insert','before_commit'):
            self.store.failpoint=point; self.reject('INJECTED_FAILURE', self.bar); self.reopen(); self.assertEqual(before,self.state())

    def test_original_reply_replays_after_new_member_transfer_retirement_and_reopen(self):
        self.activate(); request = self.request([3,7169,4,0]); reply = self.store.recruit_barracks(request, authenticated_account_id=self.account)
        self.transfer([2,1,4]); self.dismiss(4); self.hire(); self.ammo(); self.reopen(); before=self.state()
        self.assertEqual(self.store.recruit_barracks(request,authenticated_account_id=self.account), {**reply,'replayed':True})
        self.assertEqual(before,self.state())
        for call in (lambda:self.bar(3329,1,command_key=request['command_key']), lambda:self.hire(command_key=request['command_key']),
                     lambda:self.dismiss(1,command_key=request['command_key']), lambda:self.ammo(command_key=request['command_key']),
                     lambda:self.learn(1,16,command_key=request['command_key']), lambda:self.transfer([1,0,-1],command_key=request['command_key'])):
            self.reject('DUPLICATE_PAYLOAD_MISMATCH',call)

    def test_frozen_J_all_operations_and_D_replay_survive_new_hires_and_retirements(self):
        frozen=[]
        with NativeCrewDismissalStore(self.database) as old:
            for operation, layout in (('learn',[1,16,0]),('transfer',[1,0,-1]),('recruit',[3,2,1,0]),('dismiss',[3,0,0])):
                request=dict(self.old_request(),expected_revision=old.read_profile(self.account)['revision'],command_key='J-'+operation,layout=layout)
                frozen.append((operation,request,getattr(old,operation)(request,authenticated_account_id=self.account)))
        self.activate(); self.bar(); self.dismiss(4); self.dismiss(1); self.reopen(); before=self.state()
        for operation,request,reply in frozen:
            self.assertEqual(getattr(self.store,operation)(request,authenticated_account_id=self.account),{**reply,'replayed':True})
        self.assertTrue(self.store.recruit(self.old_request(),authenticated_account_id=self.account)['replayed'])
        self.assertEqual(before,self.state())

    def test_every_legacy_version_replays_immutable_history_after_K_retirement(self):
        from tests.test_p04f_crew_store import TransferStoreTests
        self.store.close();TransferStoreTests.setUp(self);TransferStoreTests.activate(self)
        frozen=[]
        request=dict(self.old_request(),expected_revision=8,command_key='F-before-K',layout=[1,0,-1])
        frozen.append(('transfer',request,self.store.transfer(request,authenticated_account_id=self.account)))
        self.store.close()
        with NativeCrossVehicleCrewStore(self.database) as store:
            store.migrate_cross(self.source,account_id=self.account,original_root=self.original)
            request=dict(self.old_request(),expected_revision=10,command_key='G-before-K',layout=[2,0,1])
            frozen.append(('transfer',request,store.transfer(request,authenticated_account_id=self.account)))
        with NativeRosterRecruitmentStore(self.database) as store:
            store.migrate_roster(self.source,account_id=self.account,original_root=self.original)
            request=dict(self.old_request(),expected_revision=12,command_key='H-before-K',layout=[3,2,1,0])
            frozen.append(('recruit',request,store.recruit(request,authenticated_account_id=self.account)))
        with NativeCrewProgressionStore(self.database) as store:
            store.migrate_progression(self.source,account_id=self.account,original_root=self.original)
            request=dict(self.old_request(),expected_revision=14,command_key='I-before-K',layout=[1,16,0])
            frozen.append(('learn',request,store.learn(request,authenticated_account_id=self.account)))
        with NativeCrewDismissalStore(self.database) as store:
            store.migrate_dismissal(self.source,account_id=self.account,original_root=self.original)
            request=dict(self.old_request(),expected_revision=16,command_key='J-before-K',layout=[3,0,0])
            frozen.append(('dismiss',request,store.dismiss(request,authenticated_account_id=self.account)))
        self.store=NativeBarracksRecruitmentStore(self.database);self.activate();self.bar()
        for identity in (4,2,1):self.dismiss(identity)
        self.reopen();before=self.state()
        for operation,request,response in frozen:
            self.assertEqual(getattr(self.store,operation)(request,authenticated_account_id=self.account),{**response,'replayed':True})
        self.assertTrue(self.store.recruit(self.old_request(),authenticated_account_id=self.account)['replayed'])
        self.assertEqual(before,self.state())

    def test_two_concurrent_requests_share_single_303_309_revision_and_allocator(self):
        self.activate(); requests=[self.request([3,7169,4,0],command_key='race303'), self.request([3,2,4,0],command_key='race309')]
        barrier=threading.Barrier(2)
        def run(index):
            with NativeBarracksRecruitmentStore(self.database) as store:
                barrier.wait()
                try:return getattr(store,('recruit_barracks','recruit')[index])(requests[index],authenticated_account_id=self.account)
                except TransactionError as error:return error.code
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(run,range(2)))
        self.assertEqual(sum(type(r) is dict for r in results),1);self.assertIn('STALE_REVISION',results)
        self.assertEqual((self.profile()['crew_inventory']['next_native_id'],self.profile()['revision']),(5,14))
        loser=next(i for i,r in enumerate(results) if type(r) is str)
        requests[loser]['expected_revision']=14;requests[loser]['wire_revision']=2
        getattr(self.store,('recruit_barracks','recruit')[loser])(requests[loser],authenticated_account_id=self.account)
        self.assertEqual(self.profile()['crew_inventory']['next_native_id'],6)

    def test_concurrent_identical_request_commits_once_and_preserves_ext(self):
        self.activate();request=self.request([3,7169,4,0]);barrier=threading.Barrier(2)
        def run(_):
            with NativeBarracksRecruitmentStore(self.database) as store:
                barrier.wait();return store.recruit_barracks(request,authenticated_account_id=self.account)
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,range(2)))
        self.assertEqual(sorted(r['replayed'] for r in results),[False,True])
        self.assertEqual(results[0]['tankman_descriptor_hex'],results[1]['tankman_descriptor_hex'])
        self.assertEqual(self.profile()['crew_inventory']['next_native_id'],5)

    def test_quota_exhaustion_and_all_retirements_cannot_refill_or_reuse(self):
        self.activate()
        for identity in range(4,17):
            self.bar() if identity%2 else self.hire(2,4)
        for identity in range(1,17):self.dismiss(identity)
        self.reopen();before=self.state()
        self.reject('FREE_RECRUITMENT_EXHAUSTED',self.bar);self.reject('FREE_RECRUITMENT_EXHAUSTED',self.hire)
        self.assertEqual(before,self.state());self.assertEqual(self.public()['crew'],[])

    def test_rehashed_response_descriptor_id_and_saved_retirement_contract_fail_closed(self):
        self.activate();request=self.request([3,7169,4,0]);self.store.recruit_barracks(request,authenticated_account_id=self.account)
        c=self.store.connection;ledger=c.execute('SELECT * FROM game_command_ledger WHERE command_type=?',(BARRACKS_COMMAND,)).fetchone()
        value=json.loads(ledger['result_json']);value['response']['tankman_inventory_id']=5;raw=canonical(value)
        c.execute('UPDATE game_command_ledger SET result_json=?,p09c_result_sha256=? WHERE command_id=?',(raw.decode(),hashlib.sha256(raw).hexdigest(),request['command_key']));c.commit()
        self.reject('CORRUPT_STORE',lambda:self.store.recruit_barracks(request,authenticated_account_id=self.account))

    def test_predecessor_audit_and_public_baseline_are_bound(self):
        self.activate();c=self.store.connection
        value=json.loads(c.execute('SELECT base_profile_json FROM p04k_crew_meta').fetchone()[0]);value['crew'][0]['role_level']=50;raw=canonical(value)
        c.execute('UPDATE p04k_crew_meta SET base_profile_json=?,base_profile_sha256=?',(raw.decode(),hashlib.sha256(raw).hexdigest()));c.commit()
        self.reject('CORRUPT_STORE',self.profile)

    def test_wrong_shop_and_retained_J_audit_prevent_migration(self):
        old=self.source.trees['shop.bin']['rev']
        try:self.source.trees['shop.bin']['rev']=4;self.reject('MIGRATION_SOURCE_CHANGED',self.activate)
        finally:self.source.trees['shop.bin']['rev']=old
        self.store.connection.execute('UPDATE p04j_crew_meta SET source_audit_sha256=?',('0'*64,));self.store.connection.commit()
        self.reject('MIGRATION_SOURCE_CHANGED',self.activate)

    def test_fixture_exact14_fields_bound_shop_and_only_active_rows(self):
        self.activate();self.bar();self.dismiss(2)
        root=Path(self.temp.name)/'k-fixtures'
        if os.name=='nt':root=Path('\\\\?\\'+str(root.resolve()))
        published=self.store.publish(self.source,self.account,root)
        files={p.name:p.read_bytes() for p in Path(published['fixture_dir']).iterdir()}
        meta=json.loads(files['crew-barracks.json'])
        self.assertEqual(set(meta),{'version','account_id','native_database_id','revision','wire_revision','policy_sha256','state_sha256',
            'command','transfer_command','role_level','vehicle_count','free_recruitment_left','configuration_revision','battle'})
        self.assertEqual((meta['command'],meta['transfer_command'],meta['role_level'],meta['vehicle_count']),(303,105,50,2))
        self.assertEqual(hashlib.sha256(files['shop.bin']).hexdigest(),SHOP_SHA256)
        self.assertNotIn('crew-dismissal.json',files)
        self.assertEqual(json.loads(files['manifest.json'])['profile_version'],12)
        from verify_ms1_ammo_native import literal_ammo as literal
        self.assertEqual(literal(files['state.bin'])[b'inventory'][1][b'lock'], {})
        self.assertEqual(meta['state_sha256'], hashlib.sha256(files['state.bin']).hexdigest())

    def test_reserved_full_fixture_fails_without_db_or_output_mutation(self):
        self.activate(); self.reserve(1)
        root=Path(self.temp.name)/'reserved-k-fixtures'
        before=self.state()
        with self.assertRaisesRegex(ValueError, 'available native vehicle'):
            self.store.publish(self.source,self.account,root)
        self.assertEqual(before,self.state())
        self.assertFalse(root.exists())
