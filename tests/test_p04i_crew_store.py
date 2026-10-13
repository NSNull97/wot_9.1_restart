"""Real SQLite I migration, learning, frozen legacy replay and cross-operation atomicity."""
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
from tests import test_p04h_crew_store as previous
from p04i_crew_store import NativeCrewProgressionStore,SOURCE_AUDIT_SHA256,LEARN_COMMAND
from p04i_crew_projection import CrewProgressionProjectionSource,POLICY_SHA256,native_crew,canonical
from p04i_tankman_descriptor import decode_descriptor
from p04h_crew_store import NativeRosterRecruitmentStore
from p04g_crew_store import NativeCrossVehicleCrewStore
from p04f_crew_store import NativeCrewTransferStore
from p04d_crew_store import NativeCrewStore
from p09d_ammo_store import NativeAmmoStore
from game_profile_tx import TransactionError


class ProgressionStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        previous.RosterStoreTests.setUpClass.__func__(cls)
        cls.source=CrewProgressionProjectionSource(os.environ.get('P04I_TEST_BUNDLE') or os.environ['P04D_TEST_BUNDLE'])

    def setUp(self):
        previous.RosterStoreTests.setUp(self)
        previous.RosterStoreTests.activate(self)
        self.store.close();self.store=NativeCrewProgressionStore(self.database)

    profile=previous.RosterStoreTests.profile
    public=previous.RosterStoreTests.public
    request=previous.RosterStoreTests.request
    transfer=previous.RosterStoreTests.transfer
    hire=previous.RosterStoreTests.hire
    ammo=previous.RosterStoreTests.ammo
    state=previous.RosterStoreTests.state
    reject=previous.RosterStoreTests.reject
    old_request=previous.RosterStoreTests.old_request
    reserve=previous.RosterStoreTests.reserve

    def activate(self):
        return self.store.migrate_progression(self.source,account_id=self.account,original_root=self.original)

    def learn(self,native=1,index=16,**changes):
        return self.store.learn(self.request([native,index,0],**changes),authenticated_account_id=self.account)

    def reopen(self):
        self.store.close();self.store=NativeCrewProgressionStore(self.database);self.store.initialize()

    def test_explicit_migration_preserves_all_bytes_quota_xp_and_configuration_once(self):
        self.reject('P04I_MIGRATION_REQUIRED',self.store.initialize)
        with NativeRosterRecruitmentStore(self.database) as old:before=old.read_profile(self.account)
        result=self.activate();after=self.profile()
        self.assertEqual((result['revision'],result['retained_tankmen'],result['xp_granted']),(11,3,0))
        expected=deepcopy(before['crew_inventory']);expected['policy_sha256']=POLICY_SHA256
        self.assertEqual(after['crew_inventory'],expected)
        for key in ('vehicles','ammunition','depot'):self.assertEqual(before[key],after[key])
        self.assertEqual(after['crew_progression_source_audit_sha256'],SOURCE_AUDIT_SHA256)
        self.assertEqual(self.public()['profile_version'],10)
        self.learn();self.reopen();before=self.state();self.assertEqual(self.activate()['status'],'already_migrated');self.assertEqual(before,self.state())

    def test_migration_failure_restores_old_check_markers_index_and_writer(self):
        for point in ('after_progression_table_rebuild','after_snapshot_update','after_profile_projection','before_progression_migration_commit'):
            self.store.failpoint=point;self.reject('INJECTED_FAILURE',self.activate)
            with NativeRosterRecruitmentStore(self.database) as old:self.assertEqual(old.read_profile(self.account)['revision'],10)
        self.store.failpoint=None;self.activate()

    def test_all_old_writers_reject_after_I(self):
        self.activate();before=self.state()
        for writer in (NativeCrewStore,NativeCrewTransferStore,NativeCrossVehicleCrewStore,NativeRosterRecruitmentStore,NativeAmmoStore):
            with writer(self.database) as old:
                with self.assertRaises(TransactionError):old.read_profile(self.account)
        self.assertEqual(before,self.state())

    def test_three_natural_firstskills_zero_no_XP_or_money_and_reopen(self):
        self.activate();before=self.profile()
        for native,index in ((1,16),(2,29),(3,6)):
            result=self.learn(native,index);self.assertEqual((result['status'],result['result_code']),("learned",0))
        self.reopen();after=self.profile()
        self.assertEqual(after['revision'],before['revision']+3)
        self.assertEqual(after['crew_inventory']['configuration_revision'],before['crew_inventory']['configuration_revision']+3)
        for old,row in zip(before['crew_inventory']['members'],after['crew_inventory']['members']):
            self.assertEqual({k:v for k,v in old.items() if k!='descriptor_hex'},{k:v for k,v in row.items() if k!='descriptor_hex'})
            decoded=decode_descriptor(bytes.fromhex(row['descriptor_hex']))
            self.assertEqual((decoded['free_xp'],decoded['last_skill_level'],decoded['role_level']),(0,0,100))
        self.assertEqual([row['skills'] for row in self.public()['crew']],[[{'skill_id':n,'level':0}] for n in ('commander_tutor','driver_smoothDriving','repair')])
        self.assertEqual(self.public()['resources'],self.source.profile['resources'])
        for key in ('vehicles','ammunition','depot'):self.assertEqual(before[key],after[key])

    def test_current_assignment_eligibility_baseSixth_inactive_and_newhire50_reject(self):
        self.activate();self.transfer([1,0,-1])
        for index in (54,18,41,1,255):
            with self.assertRaises(TransactionError):self.learn(1,index)
        self.transfer([2,0,1]);self.reject('SKILL_SELECTION_UNSUPPORTED',lambda:self.learn(1,54))
        self.transfer([1,0,1]);self.learn(1,54);self.transfer([2,0,1]);self.reopen()
        self.assertEqual(self.public()['crew'][0]['skills'],[{'skill_id':'radioman_finder','level':0}])
        self.hire(2,1);self.reject('SKILL_SELECTION_UNSUPPORTED',lambda:self.learn(4,6))

    def test_malformed_foreign_stale_duplicate_previousunfinished_unknown_and_reserved(self):
        self.activate()
        for layout in ([True,6,0],[1,True,0],[1,6,False],[1,6,1],[0,6,0],[17,6,0],[1,6],[1,6,0,0],[1,6.0,0]):
            before=self.state()
            with self.assertRaises(TransactionError):self.store.learn(self.request(layout),authenticated_account_id=self.account)
            self.assertEqual(before,self.state())
        self.reject('FOREIGN_ACCOUNT',lambda:self.store.learn(self.request([1,6,0]),authenticated_account_id='foreign'))
        self.reject('FOREIGN_ACCOUNT',lambda:self.learn(native_database_id=999))
        self.reject('STALE_REVISION',lambda:self.learn(expected_revision=10))
        self.reject('UNKNOWN_TANKMAN',lambda:self.learn(16,6))
        self.learn();self.reject('SKILL_SELECTION_UNSUPPORTED',lambda:self.learn(1,16));self.reject('SKILL_SELECTION_UNSUPPORTED',lambda:self.learn(1,6))
        self.reserve(1);self.reject('VEHICLE_RESERVED',lambda:self.learn(3,6))
        self.learn(2,29)  # Barracks driver has no reserved vehicle.

    def test_every_shared_failpoint_rolls_back_descriptor_snapshot_and_ledgers(self):
        self.activate();before=self.state()
        for point in ('after_transfer_unassign','after_transfer_assign','after_transfer_meta_update','after_snapshot_update',
                'after_profile_projection','after_transfer_ledger_insert','before_commit'):
            self.store.failpoint=point;self.reject('INJECTED_FAILURE',self.learn);self.reopen();self.assertEqual(before,self.state())

    def test_own_replay_after_transfer_ammo_recruit_is_exact_and_single_namespace(self):
        self.activate();request=self.request([1,16,0]);response=self.store.learn(request,authenticated_account_id=self.account)
        self.transfer([2,0,1]);self.hire(2,1);self.ammo();self.reopen();before=self.state()
        self.assertEqual(self.store.learn(request,authenticated_account_id=self.account),{**response,'replayed':True})
        self.assertEqual(before,self.state())
        self.reject('DUPLICATE_PAYLOAD_MISMATCH',lambda:self.transfer([2,0,-1],command_key=request['command_key']))
        self.reject('DUPLICATE_PAYLOAD_MISMATCH',lambda:self.hire(command_key=request['command_key']))
        self.reject('DUPLICATE_PAYLOAD_MISMATCH',lambda:self.ammo(command_key=request['command_key']))
        self.reject('DUPLICATE_PAYLOAD_MISMATCH',lambda:self.learn(2,29,command_key=request['command_key']))

    def test_D_and_H_receipts_replay_after_original_ID_descriptors_changed(self):
        with NativeRosterRecruitmentStore(self.database) as old:
            request=dict(self.old_request(),expected_revision=10,command_key='H-before-I',layout=[2,0,1])
            response=old.transfer(request,authenticated_account_id=self.account)
        self.activate();self.learn(1,16);self.learn(2,29);self.learn(3,6);self.reopen();before=self.state()
        old=self.store.recruit(self.old_request(),authenticated_account_id=self.account)
        self.assertTrue(old['replayed'])
        self.assertEqual(self.store.transfer(request,authenticated_account_id=self.account),{**response,'replayed':True})
        self.assertEqual(before,self.state())

    def test_F_G_receipts_use_frozen_planners_and_passport_identity_after_learning(self):
        # Reuse the independently migrated F fixture, then execute each version
        # before continuing the real SQLite migration chain.
        from tests.test_p04f_crew_store import TransferStoreTests
        self.store.close();TransferStoreTests.setUp(self);TransferStoreTests.activate(self)
        request=dict(self.old_request(),expected_revision=8,command_key='F-before-I',layout=[1,0,-1])
        response=self.store.transfer(request,authenticated_account_id=self.account)
        self.store.close()
        with NativeCrossVehicleCrewStore(self.database) as g:
            g.migrate_cross(self.source,account_id=self.account,original_root=self.original)
            grequest=dict(self.old_request(),expected_revision=10,command_key='G-before-I',layout=[2,0,1])
            gresponse=g.transfer(grequest,authenticated_account_id=self.account)
        with NativeRosterRecruitmentStore(self.database) as h:h.migrate_roster(self.source,account_id=self.account,original_root=self.original)
        self.store=NativeCrewProgressionStore(self.database);self.activate();self.learn(1,16);self.learn(2,29);self.learn(3,6)
        before=self.state()
        for req,reply in ((request,response),(grequest,gresponse)):
            self.assertEqual(self.store.transfer(req,authenticated_account_id=self.account),{**reply,'replayed':True})
        self.assertEqual(before,self.state())

    def test_concurrent_same_learning_commits_once(self):
        self.activate();request=self.request([1,16,0]);barrier=threading.Barrier(2)
        def run(_):
            with NativeCrewProgressionStore(self.database) as store:
                barrier.wait();return store.learn(request,authenticated_account_id=self.account)
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,range(2)))
        self.assertEqual(sorted(row['replayed'] for row in results),[False,True])
        self.assertEqual(results[0]['update_hex'],results[1]['update_hex'])

    def test_rehashed_impossible_transition_and_reply_corruption_reject(self):
        self.activate();request=self.request([1,16,0]);self.store.learn(request,authenticated_account_id=self.account)
        c=self.store.connection
        result=json.loads(c.execute('SELECT result_json FROM game_command_ledger WHERE command_type=?',(LEARN_COMMAND,)).fetchone()[0])
        result['after_crew']['members'][0]['descriptor_hex']=result['before_crew']['members'][0]['descriptor_hex']
        raw=canonical(result);c.execute('UPDATE game_command_ledger SET result_json=?,p09c_result_sha256=? WHERE command_type=?',(raw.decode(),hashlib.sha256(raw).hexdigest(),LEARN_COMMAND));c.commit()
        self.reject('CORRUPT_STORE',lambda:self.store.learn(request,authenticated_account_id=self.account))

    def test_migration_corrupt_retained_source_and_current_source_fail_closed(self):
        self.store.connection.execute('UPDATE p04f_crew_meta SET source_audit_sha256=?',('0'*64,));self.store.connection.commit()
        self.reject('MIGRATION_SOURCE_CHANGED',self.activate)

    def test_immutable_migration_baseline_rehash_cannot_change_D_replay_descriptor(self):
        self.activate();self.learn();c=self.store.connection
        baseline=json.loads(c.execute('SELECT base_crew_json FROM p04i_crew_meta').fetchone()[0])
        baseline['members'][0]['descriptor_hex']=baseline['members'][1]['descriptor_hex'];raw=canonical(baseline)
        c.execute('UPDATE p04i_crew_meta SET base_crew_json=?,base_crew_sha256=?',(raw.decode(),hashlib.sha256(raw).hexdigest()));c.commit()
        with self.assertRaises((ValueError,TransactionError)):self.profile()

    def test_full_fixture_exact14_metadata_and_progressed_descriptors(self):
        self.activate();self.learn();root=Path(self.temp.name)/'i-fixtures'
        if os.name=='nt':root=Path('\\\\?\\'+str(root.resolve()))
        published=self.store.publish(self.source,self.account,root)
        files={p.name:p.read_bytes() for p in Path(published['fixture_dir']).iterdir()}
        meta=json.loads(files['crew-progression.json'])
        self.assertEqual(set(meta),{'version','account_id','native_database_id','revision','wire_revision','policy_sha256','state_sha256','command','transfer_command','role_level','vehicle_count','free_recruitment_left','configuration_revision','battle'})
        self.assertEqual((meta['command'],meta['transfer_command'],meta['role_level'],meta['vehicle_count']),(151,105,50,2))
        self.assertEqual(meta['state_sha256'],hashlib.sha256(files['state.bin']).hexdigest())
        self.assertNotIn('crew-roster.json',files)
