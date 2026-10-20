"""Actual disposable SQLite cutover/authority tests; native endpoint NOT_RUN.

C/D sources are immutable receipts from real predecessor onboarding, source
research and purchase. No test authors WT/FV ammo quantities. Terminal stats
are explicitly synthetic trusted-server input, not native compatibility proof.
"""
from copy import deepcopy
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
import uuid

import test_p06t_owned_registry_v3 as facts
from p06t_owned_registry_v3 import *
from p06t_owned_store_v3 import OwnedV3Store, crew_native
from p04m_pool_store import PoolStore
from p08b_owner_source import OwnerProjectionSource
from game_profile_tx import TransactionError

from p06t_owned_fixture_v3 import ROOT,bundle_root,prepared_owners,terminal_manifest,verify_projection_cache27
MANIFEST=terminal_manifest()
RUN='6e79bd02-b833-49a1-8577-1dbd36cf2a10'
NEW_RUN='acb80861-0df4-416b-872b-b6fecc7411e4'
GENERATION='97e6a655-81cb-4b96-8f97-3a5511b91a63'


def logical(c,*,legacy=False,exclude_vehicle=False,owner=None):
    values=[]
    for name,sql in c.execute("SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name"):
        if legacy and name.startswith('p06v3_')or exclude_vehicle and name=='game_vehicle':continue
        columns=[r[1]for r in c.execute('PRAGMA table_info('+name+')')]
        where=' WHERE account_id=?'if owner is not None and'account_id'in columns else''
        rows=c.execute('SELECT * FROM '+name+where,()if not where else(owner,)).fetchall()
        values.append([name,sql,sorted([list(row)for row in rows],key=repr)])
    return sha(canonical(values))


class OwnedStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        facts.OverlayTests.setUpClass()
        cls.catalog=facts.OverlayTests.catalog;cls.encoding=facts.OverlayTests.encoding
        cls.registry=facts.OverlayTests.registry;cls.codec=facts.OverlayTests.codec
        cls.owners=prepared_owners(cls.catalog,cls.encoding,cls.registry)
        cls.source_hashes={slot:sha((cls.owners/slot/'game.sqlite').read_bytes())for slot in('C','D')}

    @classmethod
    def tearDownClass(cls):
        for slot,digest in cls.source_hashes.items():
            assert sha((cls.owners/slot/'game.sqlite').read_bytes())==digest,'IMMUTABLE_SOURCE_CHANGED'

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='wot-owned-v3-');self.addCleanup(self.tmp.cleanup)
        self.db=Path(self.tmp.name)/'game.sqlite';self.serial=0;self.store=None
        self.base=json.loads((self.owners/'C/base1.json').read_bytes());self.account=self.base['account_id'];self.native=self.base['native_database_id']
        with closing(sqlite3.connect('file:'+str((self.owners/'C/game.sqlite').resolve())+'?mode=ro',uri=True))as source:
            with closing(sqlite3.connect(self.db))as target:source.backup(target)
        self.open()

    def tearDown(self):
        if self.store:self.store.connection.close()

    def open(self):
        if self.store:self.store.connection.close()
        self.store=OwnedV3Store(self.db,self.catalog,account_id=self.account,registry=self.registry,
            encoding=self.encoding,codec=self.codec,terminal_policy=MANIFEST)

    def activation(self,**changes):
        with PoolStore(self.db,self.catalog,account_id=self.account)as old:revision=old.read_profile(self.account)['revision']
        value=dict(authenticated_account_id=self.account,native_database_id=self.native,expected_revision=revision,
            cache_generation=GENERATION,old_sessions=0,pending_jobs=0);value.update(changes)
        return self.store.activate(**value)

    def rq(self,operation,**extra):
        self.serial+=1
        request=dict(version=3,operation=operation,account_id=self.account,native_database_id=self.native,
            command_key='p06t.v3:test:'+str(self.serial),expected_revision=self.store.read_profile()['revision'],source_binding=self.store.binding())
        if operation in('recruit','recruit_barracks','transfer','ammo'):request.update(wire_revision=1)
        if operation in('run_open','admit','finish'):request.update(run_id=RUN)
        if operation in('admit','finish'):request.update(battle_id=RUN+':9007199254740993',native_inventory_id=1)
        request.update(extra);return request

    def send(self,request):return self.store.execute(request,authenticated_account_id=self.account)

    def reject(self,code,action):
        before=logical(self.store.connection)
        with self.assertRaises((OverlayError,TransactionError,sqlite3.IntegrityError))as caught:action()
        self.assertEqual(getattr(caught.exception,'code',str(caught.exception)),code)
        self.assertEqual(logical(self.store.connection),before,'failure partially committed')

    def ammo(self,counts,native=1):
        p=self.registry.profiles['ms1'if native==1 else'wt-e100-128']
        layout=[6,native,6]+[v for shot,n in zip(p.shots,counts)for v in(shot[0],n)]+[6]+[0]*6
        return self.send(self.rq('ammo',layout=layout))

    def terminal(self,f,hp,*,alive=True,roster=2):
        p=self.store.terminal.document['profiles'][f['kind']]
        return dict(policy_revision=self.store.terminal.document['policy_revision'],roster_size=roster,crew_active=alive,
            crew=[dict(crew_id=k,alive=alive)for k in f['crew_ids']],devices=[dict(r,health=r['max_health'])for r in p['devices']],
            fire=dict(active=False,ticks=0,damage=0),death=dict(reason=-1 if hp>0 and alive else 0,killer_slot=None,tick=0))

    def start(self):
        self.ammo((0,4,10));self.send(self.rq('run_open'));r=self.rq('admit');return r,self.send(r)['reservation']

    def finish(self,reservation,*,counts=(0,2,7),reason='manual_leave',hp=23,alive=True):
        f=reservation['frozen']
        return self.rq('finish',reservation_id=reservation['reservation_id'],remaining_ammunition=[dict(shell_compact_id=s['shell_compact_id'],count=n)for s,n in zip(f['ammunition'],counts)],
            terminal_hp=hp,reason=reason,terminal_state_json=canonical(self.terminal(f,hp,alive=alive)).decode())

    def result(self,shots=5):
        own=dict(vehicle_id=152043523,account_dbid=self.native,name='Fixture owner C',team=1,type_compact_descr=3329,
            health=23,shots=shots,direct_hits=1,piercings=1,damage_dealt=7,damage_received=67,kills=0,capture_points=42,
            dropped_capture_points=3,mileage_metres=135,life_time=90,killer_id=0,death_reason=-1,premature_leave=False)
        return dict(arena_id=9007199254740993,arena_type_id=4,created_unix=1792080000,winner_team=1,finish_reason=1,
            duration_seconds=120,participants=[own,dict(own,vehicle_id=152043524,account_dbid=self.native+1,name='Synthetic peer',team=2,health=83,shots=1)])

    def test_failed_activation_rolls_back_entire_DDL_and_every_legacy_row_marker(self):
        before=list(self.store.connection.iterdump())
        for point in('after_schema','before_activation_commit'):
            self.store.failpoint=point
            self.reject('FAILPOINT:'+point,lambda:self.activation())
            self.assertFalse(self.store.active());self.assertEqual(list(self.store.connection.iterdump()),before)
        self.store.failpoint=None
        for changes,code in[({'pending_jobs':1},'ENCODING_NOT_QUIESCENT'),({'old_sessions':1},'ENCODING_NOT_QUIESCENT'),
                ({'native_database_id':99},'FOREIGN_ACCOUNT'),({'expected_revision':1},'STALE_REVISION')]:
            self.reject(code,lambda:self.activation(**changes))
        old=logical(self.store.connection,legacy=True)
        response=self.activation();self.assertEqual((response['ammunition_granted'],response['crew_granted']),(0,0))
        self.assertEqual(logical(self.store.connection,legacy=True),old)
        state=self.store.read_profile();self.assertEqual(state['crew_inventory']['next_native_id'],4)
        self.assertEqual(state['schema'],'p06t-owned-current.v3')
        self.assertEqual(state['research']['garage_slots'],3);self.assertEqual(len(state['research']['vehicles']),3)
        self.assertEqual(len(state['depot']),21);self.assertTrue(all(state['depot'][s]==0 for p in self.registry.profiles.values()if p.nation_id!=0 for s in p.shell_ids))

    def test_real_WT_six_free50_hires_transfer_replay_CAS_and_zero_owned_ammo(self):
        self.activation();old=logical(self.store.connection,legacy=True)
        for seat in range(6):
            request=self.rq('recruit',layout=[6,3,seat,0]);response=self.send(request)
            self.assertEqual(response['recruitment']['tankman_inventory_id'],seat+4)
            raw=bytes.fromhex(response['recruitment']['tankman_descriptor_hex']);self.assertEqual((raw[0],raw[1],raw[3]),(0x18,66,50))
            self.assertEqual(self.send(request),dict(response,replayed=True))
        state=self.store.read_profile();crew=state['crew_inventory'];self.assertEqual((crew['next_native_id'],crew['free_recruitment_left']),(10,7))
        inv,seats=crew_native(crew,self.registry,self.codec);self.assertEqual(seats[3],[4,5,6,7,8,9])
        self.reject('AMMUNITION_NOT_OWNED',lambda:self.ammo((6,0,0),native=3))
        self.send(self.rq('run_open'));self.reject('AMMUNITION_EMPTY',lambda:self.send(self.rq('admit',native_inventory_id=3)))
        detach=self.send(self.rq('transfer',layout=[3,3,-1]));self.assertEqual(detach['status'],'transferred')
        self.send(self.rq('transfer',layout=[3,3,7]))
        self.reject('INCOMPATIBLE_CREW_NATION_OR_TYPE',lambda:self.send(self.rq('transfer',layout=[1,0,4])))
        self.reject('STALE_REVISION',lambda:self.send(dict(request,command_key='p06t.v3:stale')))
        self.assertEqual(logical(self.store.connection,legacy=True),old)
        self.assertEqual(self.store.read_profile()['depot'],state['depot'])

    def test_real_FV_corrected_nation5_five_hires_and_barracks_primary_role(self):
        self.store.connection.close();self.store=None
        with closing(sqlite3.connect('file:'+str((self.owners/'D/game.sqlite').resolve())+'?mode=ro',uri=True))as source:
            # Replace only our disposable destination, not its immutable source.
            with closing(sqlite3.connect(self.db))as target:source.backup(target)
        self.base=json.loads((self.owners/'D/base1.json').read_bytes());self.account=self.base['account_id'];self.native=self.base['native_database_id'];self.open();self.activation()
        for seat in range(5):self.send(self.rq('recruit',layout=[6,3,seat,0]))
        self.ammo((0,4,10))
        source=OwnerProjectionSource(bundle_root(),self.catalog,self.base,granted_at_ms=1792070000000)
        verify_projection_cache27(self.store.project(source),self.store.read_profile()['crew_inventory'],self.registry.profiles['fv215b-183'],Path(self.tmp.name)/'cache27')
        self.send(self.rq('recruit_barracks',layout=[6,9297,1,0]))
        crew=self.store.read_profile()['crew_inventory'];self.assertEqual((crew['next_native_id'],crew['free_recruitment_left']),(10,7))
        for row in crew['members'][3:]:self.assertEqual(bytes.fromhex(row['descriptor_hex'])[:2],bytes([0x58,36]))
        self.send(self.rq('transfer',layout=[3,0,9]))
        self.reject('RECRUIT_SELECTION_UNSUPPORTED',lambda:self.send(self.rq('recruit_barracks',layout=[6,9281,1,0])))
        self.reject('RECRUIT_SELECTION_UNSUPPORTED',lambda:self.send(self.rq('recruit_barracks',layout=[6,9297,2,0])))
        self.reject('UNKNOWN_VEHICLE',lambda:self.send(self.rq('recruit_barracks',layout=[6,16913,1,0])))
        self.send(self.rq('run_open'));self.reject('AMMUNITION_EMPTY',lambda:self.send(self.rq('admit',native_inventory_id=3)))

    def test_current_revision_native_owner_binding_payload_and_allocator_are_strict(self):
        self.activation();request=self.rq('recruit',layout=[6,3,0,0])
        for field,value,code in [('native_database_id',4,'FOREIGN_ACCOUNT'),('expected_revision',1,'STALE_REVISION')]:
            self.reject(code,lambda:self.send(dict(request,**{field:value})))
        bad=deepcopy(request);bad['source_binding']['cache_generation']=str(uuid.uuid4())
        self.reject('ENCODING_EPOCH_MISMATCH',lambda:self.send(bad))
        self.reject('FOREIGN_ACCOUNT',lambda:self.store.execute(request,authenticated_account_id='633ad84f-f33f-4aab-bacd-421f31a93bae'))
        response=self.send(request);self.assertEqual(self.send(request),dict(response,replayed=True))
        self.reject('DUPLICATE_PAYLOAD_MISMATCH',lambda:self.send(dict(request,layout=[6,3,1,0])))
        for _ in range(12):self.send(self.rq('recruit',layout=[6,3,0,0]))
        self.assertEqual((self.store.read_profile()['crew_inventory']['next_native_id'],self.store.read_profile()['crew_inventory']['free_recruitment_left']),(17,0))
        self.reject('FREE_RECRUITMENT_EXHAUSTED',lambda:self.send(self.rq('recruit',layout=[6,3,0,0])))

    def test_actual_MS1_mixed_owned_conservation_cancel_and_legacy_activated_owner_fenced(self):
        self.activation();legacy=logical(self.store.connection,legacy=True,exclude_vehicle=True)
        before=self.store.read_profile();sums={s:before['depot'][s]+next(r for r in before['ammunition']if r['mount_id']=='ms1-stock')['loaded'][s]for s in self.registry.profiles['ms1'].shell_ids}
        self.ammo((0,4,10));self.ammo((0,0,0));self.ammo((0,4,10))
        state=self.store.read_profile()
        for s in sums:self.assertEqual(state['depot'][s]+next(r for r in state['ammunition']if r['mount_id']=='ms1-stock')['loaded'][s],sums[s])
        with PoolStore(self.db,self.catalog,account_id=self.account)as old:
            old_request=dict(account_id=self.account,native_database_id=self.native,command_key='legacy:must-fail',expected_revision=old.read_profile(self.account)['revision'],wire_revision=1,layout=[3,1,1,0])
            self.reject('P06V3_OWNER_FENCED',lambda:old.recruit(old_request,authenticated_account_id=self.account))
        self.send(self.rq('run_open'));admit=self.rq('admit');reservation=self.send(admit)['reservation']
        self.reject('VEHICLE_RESERVED',lambda:self.ammo((0,4,9)))
        self.reject('VEHICLE_RESERVED',lambda:self.send(self.rq('transfer',layout=[1,0,-1])))
        finish=self.finish(reservation,reason='cancelled');result=self.send(finish)
        self.assertEqual([r['count']for r in result['reservation']['result']['consumed_ammunition']],[0,2,3])
        self.assertEqual(result['reservation']['result']['terminal_hp'],23);self.assertEqual(result['reservation']['result']['repaired_hp'],90)
        self.assertEqual(self.send(finish),dict(result,replayed=True))
        self.reject('RESERVATION_TERMINAL',lambda:self.send(admit))
        self.assertEqual(logical(self.store.connection,legacy=True,exclude_vehicle=True),legacy)

    def test_finish_failpoints_full_result_atomic_query_ack_and_reopen(self):
        self.activation();admit,reservation=self.start()
        finish=self.finish(reservation,reason='battle_finished');finish['results_json']=canonical(self.result()).decode()
        bad=dict(finish,results_json=canonical(self.result(6)).decode());self.reject('RESULT_MISMATCH',lambda:self.send(bad))
        for point in('after_terminal','after_full_result','after_ledger','before_commit'):
            self.store.failpoint=point;self.reject('FAILPOINT:'+point,lambda:self.send(finish))
        self.store.failpoint=None;response=self.send(finish);self.open()
        self.assertEqual(self.send(finish),dict(response,replayed=True))
        query=self.send(self.rq('query',arena_id='9007199254740993'));self.assertEqual(json.loads(query['results_json']),self.result())
        self.assertFalse(query['acked']);ack=self.rq('ack',arena_id='9007199254740993');acked=self.send(ack)
        self.assertTrue(acked['acked']);self.assertEqual(self.send(ack),dict(acked,replayed=True))
        self.assertTrue(self.send(self.rq('query',arena_id='9007199254740993'))['acked'])

    def test_reservation_failpoints_restart_refund_exactly_once_and_late_old_run_fenced(self):
        self.activation();self.ammo((0,4,10));self.send(self.rq('run_open'))
        admit=self.rq('admit')
        for point in('after_reservation','after_ledger','before_commit'):
            self.store.failpoint=point;self.reject('FAILPOINT:'+point,lambda:self.send(admit))
        self.store.failpoint=None;reservation=self.send(admit)['reservation'];before=self.store.read_profile()['ammunition'];late=self.finish(reservation)
        self.open();restart=self.rq('run_open',run_id=NEW_RUN);response=self.send(restart)
        self.assertEqual(response['reservation']['status'],'aborted_restart');terminal=response['reservation']['result']
        self.assertEqual([r['count']for r in terminal['remaining_ammunition']],[0,4,10]);self.assertIsNone(terminal['terminal_hp']);self.assertIsNone(terminal['terminal_state'])
        self.assertEqual(self.store.read_profile()['ammunition'],before)
        self.assertEqual(self.send(restart),dict(response,replayed=True))
        self.reject('RUN_FENCED',lambda:self.send(late));self.reject('RUN_FENCED',lambda:self.send(admit))
        self.reject('RUN_FENCED',lambda:self.send(self.rq('run_open')))

    def test_other_unactivated_real_owner_keeps_legacy_SQL_writer_under_owner_fences(self):
        c=self.store.connection
        c.execute('ATTACH DATABASE ? AS other',(str(self.owners/'D/game.sqlite'),))
        c.execute('BEGIN IMMEDIATE');c.execute('PRAGMA defer_foreign_keys=ON')
        names=[r[0]for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for name in names:
            columns=[r[1]for r in c.execute('PRAGMA table_info('+name+')')]
            if'account_id'in columns:c.execute('INSERT INTO '+name+' SELECT * FROM other.'+name)
        c.commit();c.execute('DETACH DATABASE other')
        other=json.loads((self.owners/'D/base1.json').read_bytes());self.activation()
        with PoolStore(self.db,self.catalog,account_id=other['account_id'])as old:
            before=old.read_profile(other['account_id']);req=dict(account_id=other['account_id'],native_database_id=other['native_database_id'],command_key='other:real-recruit',expected_revision=before['revision'],wire_revision=1,layout=[3,1,1,0])
            response=old.recruit(req,authenticated_account_id=other['account_id']);after=old.read_profile(other['account_id'])
            self.assertEqual(response['status'],'recruited');self.assertEqual(after['revision'],before['revision']+1)
            self.assertEqual(after['crew_inventory']['next_native_id'],before['crew_inventory']['next_native_id']+1)
        self.assertEqual(self.store.read_profile()['crew_inventory']['next_native_id'],4)

    def test_real_full_cache_projects_foreign_seats_sourceCDs_and_loaded_APzero(self):
        self.activation()
        for seat in range(6):self.send(self.rq('recruit',layout=[6,3,seat,0]))
        self.ammo((0,4,10))
        source=OwnerProjectionSource(bundle_root(),self.catalog,self.base,granted_at_ms=1792070000000)
        value=self.store.project(source);state=value['state'];records=state['inventory'][1]
        self.assertEqual(records['crew'][3],[4,5,6,7,8,9]);self.assertEqual(records['compDescr'][3].hex(),self.registry.profiles['wt-e100-128'].descriptor_hex)
        self.assertEqual(records['shells'][1],[2570,0,2826,4,3082,10]);self.assertEqual(records['shells'][3],[13850,0,14106,0,14362,0])
        self.assertEqual(value['shop']['rev'],6);self.assertEqual(len(state['inventory'][10]),21);self.assertFalse(value['manifest']['battle_admission'])
        self.assertEqual(state['inventory'][8]['compDescr'][7][0],0x18)
        # Actual trusted CPython 2.7 fixture auditing is performed by the export
        # receipt helper; this assertion itself does not claim native delivery.
        for raw in value['files'].values():self.assertLessEqual(len(raw),32768)
        receipt=verify_projection_cache27(value,self.store.read_profile()['crew_inventory'],self.registry.profiles['wt-e100-128'],Path(self.tmp.name)/'cache27')
        self.assertEqual(receipt['status'],'PASS_CPYTHON273_OWN_PRIMITIVE_OUTPUT_ONLY')

    def test_cold_connection_generation_fences_late_garage_command_without_resetting_revision(self):
        self.activation();old=self.rq('recruit',layout=[6,3,0,0]);snapshot=self.store.read_profile()
        value=dict(authenticated_account_id=self.account,expected_revision=snapshot['revision'],native_database_id=self.native,
            cache_generation=NEW_RUN,old_sessions=0,pending_jobs=0)
        self.store.failpoint='before_cold_open_commit';self.reject('FAILPOINT:before_cold_open_commit',lambda:self.store.cold_open(**value))
        self.store.failpoint=None;binding=self.store.cold_open(**value)
        self.assertEqual(self.store.read_profile(),snapshot);self.assertEqual(binding['cache_generation'],NEW_RUN)
        self.reject('ENCODING_EPOCH_MISMATCH',lambda:self.send(old))
        self.reject('ENCODING_GENERATION_REUSED',lambda:self.store.cold_open(**dict(value,cache_generation=GENERATION)))
        self.reject('ENCODING_NOT_QUIESCENT',lambda:self.store.cold_open(**dict(value,pending_jobs=1)))
        self.start();self.reject('VEHICLE_RESERVED',lambda:self.store.cold_open(**dict(value,expected_revision=self.store.read_profile()['revision'],cache_generation=str(uuid.uuid4()))))

    def test_crew_ammo_failpoints_and_poisoned_current_or_terminal_never_return_success(self):
        self.activation()
        for operation,layout,point in [('recruit',[6,3,0,0],'after_crew'),('ammo',[6,1,6,2570,0,2826,4,3082,10,6,0,0,0,0,0,0],'after_ammo')]:
            for stage in(point,'after_ledger','before_commit'):
                request=self.rq(operation,layout=layout);self.store.failpoint=stage
                self.reject('FAILPOINT:'+stage,lambda:self.send(request))
        self.store.failpoint=None
        before=self.store.read_profile();current=self.store.connection.execute('SELECT current_json FROM p06v3_owner WHERE account_id=?',(self.account,)).fetchone()[0]
        self.store.connection.execute("UPDATE p06v3_owner SET current_json='{}' WHERE account_id=?",(self.account,))
        self.reject('CORRUPT_STORE',lambda:self.store.read_profile())
        self.store.connection.execute('UPDATE p06v3_owner SET current_json=? WHERE account_id=?',(current,self.account));self.assertEqual(self.store.read_profile(),before)
        _,reservation=self.start();finish=self.finish(reservation);response=self.send(finish)
        result=deepcopy(response['reservation']['result']);result['terminal_state']['devices'][0]['health']+=1
        raw=canonical(result).decode();self.store.connection.execute('UPDATE p06v3_reservation SET result_json=?,result_sha256=? WHERE account_id=?',(raw,sha(raw.encode()),self.account))
        self.reject('INVALID_TERMINAL_STATE',lambda:self.send(finish))

    def test_two_connection_cold_epoch_rotation_between_parse_and_begin_rechecks_locked_owner(self):
        self.activation();request=self.rq('recruit',layout=[6,3,0,0]);before=self.store.read_profile()
        original=self.store._request
        with OwnedV3Store(self.db,self.catalog,account_id=self.account,registry=self.registry,
                encoding=self.encoding,codec=self.codec,terminal_policy=MANIFEST)as other:
            def interleaved(value,authenticated):
                parsed=original(value,authenticated)
                # Real second SQLite connection commits after actual validation
                # and before execute() takes its writer lock. No response mocks.
                other.cold_open(authenticated_account_id=self.account,expected_revision=before['revision'],
                    native_database_id=self.native,cache_generation=NEW_RUN,old_sessions=0,pending_jobs=0)
                return parsed
            self.store._request=interleaved
            with self.assertRaises(OverlayError)as caught:self.send(request)
            self.assertEqual(str(caught.exception),'ENCODING_EPOCH_MISMATCH')
        self.store._request=original
        self.assertEqual(self.store.read_profile(),before)
        self.assertEqual(self.store.binding()['cache_generation'],NEW_RUN)
        self.assertEqual(self.store.connection.execute('SELECT count(*) FROM p06v3_ledger').fetchone()[0],0)
        self.assertEqual(self.send(self.rq('recruit',layout=[6,3,0,0]))['status'],'recruited')

    def test_cold_open_return_receipt_captures_its_own_epoch_before_second_commit(self):
        self.activation();revision=self.store.read_profile()['revision'];actual=self.store.connection
        generation2='1865940d-695e-4c15-acd7-15f5fd68ba32'
        with OwnedV3Store(self.db,self.catalog,account_id=self.account,registry=self.registry,
                encoding=self.encoding,codec=self.codec,terminal_policy=MANIFEST)as other:
            class CommitInterleave:
                def __getattr__(proxy,name):return getattr(actual,name)
                def commit(proxy):
                    actual.commit()
                    # Real second writer commits in the first caller's return
                    # gap. Only commit scheduling is controlled, not SQL data.
                    other.cold_open(authenticated_account_id=self.account,expected_revision=revision,native_database_id=self.native,
                        cache_generation=generation2,old_sessions=0,pending_jobs=0)
            self.store.connection=CommitInterleave()
            try:returned=self.store.cold_open(authenticated_account_id=self.account,expected_revision=revision,
                native_database_id=self.native,cache_generation=NEW_RUN,old_sessions=0,pending_jobs=0)
            finally:self.store.connection=actual
        self.assertEqual(returned['cache_generation'],NEW_RUN)
        self.assertEqual(self.store.binding()['cache_generation'],generation2)
        self.reject('ENCODING_EPOCH_MISMATCH',lambda:self.send(dict(self.rq('recruit',layout=[6,3,0,0]),source_binding=returned)))

    def test_projection_rejects_same_account_source_with_wrong_native_database_header(self):
        self.activation();wrong=deepcopy(self.base);wrong['native_database_id']=99
        source=OwnerProjectionSource(bundle_root(),self.catalog,wrong,granted_at_ms=1792070000000)
        self.reject('FOREIGN_ACCOUNT',lambda:self.store.project(source))

    def test_WAL_current_read_keeps_one_snapshot_when_real_second_writer_commits(self):
        self.activation()
        self.assertEqual(self.store.connection.execute('PRAGMA journal_mode=WAL').fetchone()[0],'wal')
        before=self.store.read_profile();request=self.rq('recruit',layout=[6,3,0,0])
        committed=[];original=self.store._snapshot
        with OwnedV3Store(self.db,self.catalog,account_id=self.account,registry=self.registry,
                encoding=self.encoding,codec=self.codec,terminal_policy=MANIFEST)as other:
            def interleaved():
                if not committed:
                    # Commit real normalized rows/current JSON after the reader
                    # selected its owner, before its remaining SELECTs. WAL lets
                    # this happen even when the reader correctly holds a snapshot.
                    committed.append(other.execute(request,authenticated_account_id=self.account))
                return original()
            self.store._snapshot=interleaved
            try:observed=self.store.read_profile()
            finally:self.store._snapshot=original
        self.assertEqual(len(committed),1)
        self.assertEqual(committed[0]['revision'],before['revision']+1)
        self.assertEqual(observed,before,'one read must not mix pre/post-commit rows')
        self.assertFalse(self.store.connection.in_transaction)
        current=self.store.read_profile()
        self.assertEqual(current['revision'],before['revision']+1)
        self.assertEqual(len(current['crew_inventory']['members']),len(before['crew_inventory']['members'])+1)

    def test_WAL_projection_does_not_bind_old_snapshot_to_new_cold_generation(self):
        self.activation()
        self.assertEqual(self.store.connection.execute('PRAGMA journal_mode=WAL').fetchone()[0],'wal')
        before=self.store.read_profile();request=self.rq('recruit',layout=[6,3,0,0])
        source=OwnerProjectionSource(bundle_root(),self.catalog,self.base,granted_at_ms=1792070000000)
        committed=[];original=self.store.read_profile
        with OwnedV3Store(self.db,self.catalog,account_id=self.account,registry=self.registry,
                encoding=self.encoding,codec=self.codec,terminal_policy=MANIFEST)as other:
            def interleaved():
                observed=original()
                if not committed:
                    # These two actual commits create (R+1,G1), then (R+1,G2).
                    # No committed state ever has the old revision R with G2.
                    changed=other.execute(request,authenticated_account_id=self.account)
                    binding=other.cold_open(authenticated_account_id=self.account,
                        expected_revision=changed['revision'],native_database_id=self.native,
                        cache_generation=NEW_RUN,old_sessions=0,pending_jobs=0)
                    committed.append((changed,binding))
                return observed
            self.store.read_profile=interleaved
            try:projected=self.store.project(source)
            finally:self.store.read_profile=original
        self.assertEqual(len(committed),1)
        self.assertEqual(projected['binding'].snapshot_revision,before['revision'])
        self.assertEqual(projected['binding'].cache_generation,GENERATION,
            'cache must use the generation from the same read snapshot')
        self.assertEqual(projected['state']['stats']['freeTMenLeft'],before['crew_inventory']['free_recruitment_left'])
        self.assertFalse(self.store.connection.in_transaction)
        self.assertEqual(self.store.binding()['cache_generation'],NEW_RUN)
        self.assertEqual(self.store.read_profile()['revision'],before['revision']+1)

    def test_current_read_failure_releases_only_its_own_transaction(self):
        self.activation();before=self.store.read_profile();c=self.store.connection
        digest=c.execute('SELECT current_sha256 FROM p06v3_owner WHERE account_id=?',(self.account,)).fetchone()[0]
        c.execute('UPDATE p06v3_owner SET current_sha256=? WHERE account_id=?',('0'*64,self.account))
        with self.assertRaisesRegex(OverlayError,'^CORRUPT_STORE$'):self.store.read_profile()
        self.assertFalse(c.in_transaction,'failed standalone read must release its snapshot')
        c.execute('UPDATE p06v3_owner SET current_sha256=? WHERE account_id=?',(digest,self.account))
        c.execute('BEGIN IMMEDIATE')
        try:
            c.execute('UPDATE p06v3_owner SET current_sha256=? WHERE account_id=?',('0'*64,self.account))
            with self.assertRaisesRegex(OverlayError,'^CORRUPT_STORE$'):self.store.read_profile()
            self.assertTrue(c.in_transaction,'nested read must leave caller transaction open')
            self.assertEqual(c.execute('SELECT current_sha256 FROM p06v3_owner WHERE account_id=?',(self.account,)).fetchone()[0],'0'*64,
                'nested read must not roll back the caller write')
        finally:c.rollback()
        self.assertEqual(self.store.read_profile(),before)


if __name__=='__main__':unittest.main(verbosity=2)
