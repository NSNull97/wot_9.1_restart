"""Real SQLite retirement, sparse follow-up operations and immutable historical replay."""
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

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from tests import test_p04i_crew_store as previous
from p04j_crew_store import NativeCrewDismissalStore, SOURCE_AUDIT_SHA256, DISMISS_COMMAND
from p04j_crew_projection import CrewDismissalProjectionSource, POLICY_SHA256, canonical, native_crew
from p04i_crew_store import NativeCrewProgressionStore
from p04h_crew_store import NativeRosterRecruitmentStore
from p04g_crew_store import NativeCrossVehicleCrewStore
from p04f_crew_store import NativeCrewTransferStore
from p04d_crew_store import NativeCrewStore
from p09d_ammo_store import NativeAmmoStore
from game_profile_tx import TransactionError


class DismissalStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        previous.ProgressionStoreTests.setUpClass.__func__(cls)
        cls.source=CrewDismissalProjectionSource(os.environ.get('P04J_TEST_BUNDLE') or os.environ['P04D_TEST_BUNDLE'])

    def setUp(self):
        previous.ProgressionStoreTests.setUp(self)
        previous.ProgressionStoreTests.activate(self)
        self.store.close();self.store=NativeCrewDismissalStore(self.database)

    profile=previous.ProgressionStoreTests.profile
    public=previous.ProgressionStoreTests.public
    request=previous.ProgressionStoreTests.request
    transfer=previous.ProgressionStoreTests.transfer
    hire=previous.ProgressionStoreTests.hire
    learn=previous.ProgressionStoreTests.learn
    ammo=previous.ProgressionStoreTests.ammo
    state=previous.ProgressionStoreTests.state
    reject=previous.ProgressionStoreTests.reject
    old_request=previous.ProgressionStoreTests.old_request
    reserve=previous.ProgressionStoreTests.reserve

    def activate(self):
        return self.store.migrate_dismissal(self.source,account_id=self.account,original_root=self.original)

    def dismiss(self,identity=3,**changes):
        return self.store.dismiss(self.request([identity,0,0],**changes),authenticated_account_id=self.account)

    def reopen(self):
        self.store.close();self.store=NativeCrewDismissalStore(self.database);self.store.initialize()

    def test_explicit_migration_preserves_every_current_field_and_is_once_only(self):
        self.reject('P04J_MIGRATION_REQUIRED',self.store.initialize)
        with NativeCrewProgressionStore(self.database) as old:before=old.read_profile(self.account)
        result=self.activate();after=self.profile()
        expected=deepcopy(before['crew_inventory']);expected.update(policy_sha256=POLICY_SHA256,retired_members=[])
        self.assertEqual(after['crew_inventory'],expected)
        self.assertEqual((result['revision'],result['retained_tankmen'],result['retired_tankmen']),(12,3,0))
        for key in ('vehicles','ammunition','depot'):self.assertEqual(before[key],after[key])
        self.assertEqual(after['crew_dismissal_source_audit_sha256'],SOURCE_AUDIT_SHA256)
        self.dismiss();self.reopen();before=self.state();self.assertEqual(self.activate()['status'],'already_migrated');self.assertEqual(before,self.state())

    def test_migration_rollback_restores_old_schema_writer_and_no_tombstones(self):
        for point in ('after_dismissal_tables','after_snapshot_update','after_profile_projection','before_dismissal_migration_commit'):
            self.store.failpoint=point;self.reject('INJECTED_FAILURE',self.activate)
            with NativeCrewProgressionStore(self.database) as old:self.assertEqual(old.read_profile(self.account)['revision'],11)
            self.assertIsNone(self.store.connection.execute("SELECT 1 FROM sqlite_master WHERE name='p04j_retired_member'").fetchone())
        self.store.failpoint=None;self.activate()

    def test_old_writers_fail_closed_after_J(self):
        self.activate();before=self.state()
        for writer in (NativeCrewStore,NativeCrewTransferStore,NativeCrossVehicleCrewStore,NativeRosterRecruitmentStore,NativeCrewProgressionStore,NativeAmmoStore):
            with writer(self.database) as old:
                with self.assertRaises(TransactionError):old.read_profile(self.account)
        self.assertEqual(before,self.state())

    def test_learned_barracks_and_seated_retirement_then_sparse_hire_transfer_reopen(self):
        self.activate();self.learn(3,6);self.transfer([1,1,2]);before=self.profile();resources=self.public()['resources']
        terminal=before['crew_inventory']['members'][2]
        self.dismiss(3);self.dismiss(2)
        retired=self.profile()['crew_inventory'];self.assertEqual([r['native_id'] for r in retired['members']],[1])
        self.assertEqual(retired['retired_members'][1],terminal)
        self.assertEqual((retired['next_native_id'],retired['free_recruitment_left']),(4,13))
        self.hire();self.transfer([2,2,4]);self.ammo();self.reopen()
        after=self.profile();self.assertEqual(native_crew(after['crew_inventory'])[1][2][2],4)
        self.assertEqual(after['crew_inventory']['next_native_id'],5)
        self.assertEqual(self.public()['resources'],resources)

    def test_all_deletions_empty_fixture_and_lifetime_allocator_not_refunded(self):
        self.activate()
        for identity in (2,1,3):self.dismiss(identity)
        self.reopen();self.assertEqual(self.public()['crew'],[])
        self.assertEqual(native_crew(self.profile()['crew_inventory']),({'compDescr':{},'vehicle':{}},{1:[None,None],2:[None]*5}))
        self.hire(2,4);self.assertEqual(self.profile()['crew_inventory']['members'][0]['native_id'],4)
        self.assertEqual(self.profile()['crew_inventory']['free_recruitment_left'],12)

    def test_full_lifetime_capacity_remains_exhausted_after_every_retirement(self):
        self.activate()
        for identity in range(4,17):self.hire(2,(identity-4)%5)
        for identity in range(1,17):self.dismiss(identity)
        self.reopen();before=self.state();self.reject('FREE_RECRUITMENT_EXHAUSTED',self.hire)
        self.assertEqual(before,self.state());self.assertEqual(self.profile()['crew_inventory']['next_native_id'],17)

    def test_malformed_foreign_missing_stale_and_reserved_are_atomic(self):
        self.activate()
        for layout in ([True,0,0],[1,False,0],[1,0,False],[0,0,0],[17,0,0],[1,1,0],[1,0,1],[1,0],[1,0,0,0],[1.0,0,0]):
            before=self.state()
            with self.assertRaises(TransactionError):self.store.dismiss(self.request(layout),authenticated_account_id=self.account)
            self.assertEqual(before,self.state())
        self.reject('FOREIGN_ACCOUNT',lambda:self.store.dismiss(self.request([3,0,0]),authenticated_account_id='foreign'))
        self.reject('FOREIGN_ACCOUNT',lambda:self.dismiss(native_database_id=999))
        self.reject('STALE_REVISION',lambda:self.dismiss(expected_revision=11))
        self.reject('UNKNOWN_TANKMAN',lambda:self.dismiss(16))
        self.reserve(1);self.reject('VEHICLE_RESERVED',self.dismiss)
        self.dismiss(2)  # Barracks has no reserved assigned vehicle.
        self.reject('UNKNOWN_TANKMAN',lambda:self.dismiss(2))

    def test_retirement_failpoints_rollback_active_terminal_snapshot_and_ledgers(self):
        self.activate();before=self.state()
        for point in ('after_transfer_unassign','after_retirement_insert','after_retirement_delete','after_transfer_assign',
                'after_transfer_meta_update','after_snapshot_update','after_profile_projection','after_transfer_ledger_insert','before_commit'):
            self.store.failpoint=point;self.reject('INJECTED_FAILURE',self.dismiss);self.reopen();self.assertEqual(before,self.state())

    def test_terminal_rows_immutable_and_provenance_ledger_tamper_rejected(self):
        self.activate();self.learn(3,6);self.dismiss();c=self.store.connection
        for sql in ('UPDATE p04j_retired_member SET descriptor_hex=descriptor_hex','DELETE FROM p04j_retired_member'):
            with self.assertRaises(sqlite3.IntegrityError):c.execute(sql)
            c.rollback()
        ledger=c.execute('SELECT * FROM game_command_ledger WHERE command_type=?',(DISMISS_COMMAND,)).fetchone()
        value=json.loads(ledger['result_json']);value['after_crew']['free_recruitment_left']-=1;raw=canonical(value)
        c.execute('UPDATE game_command_ledger SET result_json=?,p09c_result_sha256=? WHERE command_id=?',(raw.decode(),hashlib.sha256(raw).hexdigest(),ledger['command_id']));c.commit()
        with self.assertRaises((TransactionError,ValueError)):self.profile()

    def test_own_replay_after_retirement_hire_ammo_is_frozen_and_one_namespace(self):
        self.activate();request=self.request([3,0,0]);reply=self.store.dismiss(request,authenticated_account_id=self.account)
        self.hire();self.ammo();self.reopen();before=self.state()
        self.assertEqual(self.store.dismiss(request,authenticated_account_id=self.account),{**reply,'replayed':True})
        self.assertEqual(before,self.state())
        for call in (lambda:self.dismiss(2,command_key=request['command_key']),lambda:self.learn(1,16,command_key=request['command_key']),
                lambda:self.hire(command_key=request['command_key']),lambda:self.ammo(command_key=request['command_key']),lambda:self.transfer([1,0,-1],command_key=request['command_key'])):
            self.reject('DUPLICATE_PAYLOAD_MISMATCH',call)

    def test_D_and_I_receipts_survive_retiring_all_original_identities(self):
        with NativeCrewProgressionStore(self.database) as old:
            request=dict(self.old_request(),expected_revision=11,command_key='I-before-J',layout=[1,16,0])
            response=old.learn(request,authenticated_account_id=self.account)
        self.activate()
        for identity in (3,1,2):self.dismiss(identity)
        self.hire();self.reopen();before=self.state()
        self.assertTrue(self.store.recruit(self.old_request(),authenticated_account_id=self.account)['replayed'])
        self.assertEqual(self.store.learn(request,authenticated_account_id=self.account),{**response,'replayed':True})
        self.assertEqual(before,self.state())

    def test_concurrent_same_dismissal_commits_once(self):
        self.activate();request=self.request([3,0,0]);barrier=threading.Barrier(2)
        def run(_):
            with NativeCrewDismissalStore(self.database) as store:
                barrier.wait();return store.dismiss(request,authenticated_account_id=self.account)
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,range(2)))
        self.assertEqual(sorted(r['replayed'] for r in results),[False,True])
        self.assertEqual(results[0]['update_hex'],results[1]['update_hex'])
        self.assertEqual(len(self.profile()['crew_inventory']['retired_members']),1)

    def test_every_historical_planner_replays_retired_original_and_recruited_passports(self):
        from tests.test_p04f_crew_store import TransferStoreTests
        self.store.close();TransferStoreTests.setUp(self);TransferStoreTests.activate(self)
        frozen=[]
        request=dict(self.old_request(),expected_revision=8,command_key='F-before-J',layout=[1,0,-1])
        frozen.append(('transfer',request,self.store.transfer(request,authenticated_account_id=self.account)))
        self.store.close()
        with NativeCrossVehicleCrewStore(self.database) as g:
            g.migrate_cross(self.source,account_id=self.account,original_root=self.original)
            request=dict(self.old_request(),expected_revision=10,command_key='G-before-J',layout=[2,0,1])
            frozen.append(('transfer',request,g.transfer(request,authenticated_account_id=self.account)))
        with NativeRosterRecruitmentStore(self.database) as h:
            h.migrate_roster(self.source,account_id=self.account,original_root=self.original)
            request=dict(self.old_request(),expected_revision=12,command_key='H-before-J',layout=[3,2,1,0])
            frozen.append(('recruit',request,h.recruit(request,authenticated_account_id=self.account)))
        with NativeCrewProgressionStore(self.database) as i:
            i.migrate_progression(self.source,account_id=self.account,original_root=self.original)
            request=dict(self.old_request(),expected_revision=14,command_key='I-before-J',layout=[1,16,0])
            frozen.append(('learn',request,i.learn(request,authenticated_account_id=self.account)))
        self.store=NativeCrewDismissalStore(self.database);self.activate()
        for identity in (4,3,2,1):self.dismiss(identity)
        self.hire(2,4);self.reopen();before=self.state()
        for operation,request,response in frozen:
            self.assertEqual(getattr(self.store,operation)(request,authenticated_account_id=self.account),{**response,'replayed':True})
        self.assertTrue(self.store.recruit(self.old_request(),authenticated_account_id=self.account)['replayed'])
        self.assertEqual(before,self.state())

    def test_sparse_learning_after_deletion_keeps_current_role_reservation_guards(self):
        self.activate();self.dismiss(2);self.learn(3,6);self.transfer([2,2,3])
        self.assertEqual([r['skills'] for r in self.public()['crew']],[[],[{'skill_id':'repair','level':0}]])
        self.transfer([2,0,1]);self.reject('SKILL_SELECTION_UNSUPPORTED',lambda:self.learn(1,54))
        self.reserve(2);self.reject('VEHICLE_RESERVED',lambda:self.transfer([1,0,1]))
        self.reject('VEHICLE_RESERVED',lambda:self.dismiss(1))

    def test_rehashed_predecessor_public_baseline_cannot_change_retained_crew(self):
        self.activate();c=self.store.connection
        value=json.loads(c.execute('SELECT base_profile_json FROM p04j_crew_meta').fetchone()[0]);value['crew'][0]['role_level']=50
        raw=canonical(value);c.execute('UPDATE p04j_crew_meta SET base_profile_json=?,base_profile_sha256=?',(raw.decode(),hashlib.sha256(raw).hexdigest()));c.commit()
        with self.assertRaises(TransactionError):self.profile()

    def test_terminal_hash_and_command_binding_are_checked_independently_of_trigger(self):
        self.activate();self.dismiss();c=self.store.connection
        c.execute('DROP TRIGGER p04j_retired_no_update')
        c.execute("UPDATE p04j_retired_member SET command_key='other-command'")
        c.execute("CREATE TRIGGER p04j_retired_no_update BEFORE UPDATE ON p04j_retired_member BEGIN SELECT RAISE(ABORT,'terminal crew is immutable'); END")
        c.commit()
        with self.assertRaises(TransactionError):self.profile()

    def test_corrupt_migration_audit_and_rehashed_base_fail_closed(self):
        self.store.connection.execute('UPDATE p04i_crew_meta SET source_audit_sha256=?',('0'*64,));self.store.connection.commit()
        self.reject('MIGRATION_SOURCE_CHANGED',self.activate)

    def test_fixture_exact14_fields_and_no_retired_rows(self):
        self.activate();self.dismiss(2);root=Path(self.temp.name)/'j-fixtures'
        if os.name=='nt':root=Path('\\\\?\\'+str(root.resolve()))
        published=self.store.publish(self.source,self.account,root)
        files={p.name:p.read_bytes() for p in Path(published['fixture_dir']).iterdir()}
        meta=json.loads(files['crew-dismissal.json'])
        self.assertEqual(set(meta),{'version','account_id','native_database_id','revision','wire_revision','policy_sha256','state_sha256','command','transfer_command','role_level','vehicle_count','free_recruitment_left','configuration_revision','battle'})
        self.assertEqual((meta['command'],meta['transfer_command'],meta['role_level'],meta['vehicle_count']),(306,105,50,2))
        self.assertEqual(meta['state_sha256'],hashlib.sha256(files['state.bin']).hexdigest())
        self.assertNotIn('crew-progression.json',files)
        self.assertEqual([r['crew_id'] for r in self.public()['crew']],[r['crew_id'] for r in self.profile()['crew_inventory']['members']])
