"""Actual existing MixedAmmoStore and publisher checks, no HTTP/native claim."""
from contextlib import closing
from copy import deepcopy
import json,os,sqlite3,tempfile,unittest
from pathlib import Path

from game_profile_tx import TransactionError
from p06t_mixed_store import MixedAmmoStore
from p06t_mixed_projection import MixedProjectionSource
from p04m_pool_projection import PoolProjectionSource
from p08b_owner_source import projection_source
from p09e_research_catalog import load_catalog
from p09d_ammo_projection import canonical
from p09d_ammo_store import sha
from p08b_battle_service import battle_service
from p10b_selection import SelectionReader,parse_request,MAX_REPLY

RUN='61ced794-71e9-4719-af94-7a606c431558'


class SelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=Path(os.environ['WOT091_TEST_REPO_ROOT']).resolve(strict=True)
        cls.owners=Path(os.environ['P10B_TEST_OWNERS']).resolve(strict=True)
        cls.bundle=Path(os.environ['P04D_TEST_BUNDLE']).resolve(strict=True)
        cls.evidence=Path(os.environ['P10B_SELECTION_EVIDENCE']);cls.evidence.mkdir()
        original=Path(json.loads((cls.root/'config/project.local.json').read_text('utf-8-sig'))['paths']['original_client_root'])
        cls.catalog=load_catalog(original)
        cls.shell=cls.root/'tests/fixtures/p06t-shell-catalog.json'
        cls.policy=cls.root/'server/gateway/src/shared/p06t_device_policy.json'
        cls.bases={n:json.loads((cls.owners/n/'base1.json').read_bytes())for n in('C','D')}
        cls.input_hashes={p:sha(p.read_bytes())for p in[cls.owners/'C/game.sqlite',cls.owners/'D/game.sqlite']}
        cls.seed_temp=tempfile.TemporaryDirectory(prefix='wot-selection-seed-');cls.seed=Path(cls.seed_temp.name)/'game.sqlite'
        with closing(sqlite3.connect((cls.owners/'C/game.sqlite').as_uri()+'?mode=ro',uri=True))as src:
            with closing(sqlite3.connect(cls.seed))as dst:src.backup(dst)
        with closing(sqlite3.connect(cls.seed))as c:
            c.execute('ATTACH DATABASE ? AS predecessor',(str(cls.owners/'D/game.sqlite'),));c.execute('BEGIN IMMEDIATE')
            for(name,)in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall():
                if 'account_id'in[r[1]for r in c.execute('PRAGMA table_info('+name+')')]:c.execute('INSERT INTO '+name+' SELECT * FROM predecessor.'+name)
            c.commit();c.execute('DETACH DATABASE predecessor');assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
        cls.setup_receipts=[]
        for name,base in cls.bases.items():
            account,native=base['account_id'],base['native_database_id']
            with cls.open_store(cls.seed,account)as store:
                before=store.read_profile(account)
                cls.setup_receipts.append(store.activate_mixed(account_id=account,authenticated_account_id=account,
                    expected_revision=before['revision'],native_database_id=native))
                before=store.read_profile(account)
                totals=dict(before['depot'])
                for row in before['ammunition']:
                    for key,n in row['loaded'].items():totals[key]+=n
                request=dict(account_id=account,native_database_id=native,command_key='selection-setup:owned-ammo',
                    expected_revision=before['revision'],wire_revision=1,layout=[5,1,6,2570,0,2826,4,3082,10,6,0,0,0,0,0,0])
                reply=store.service(request,authenticated_account_id=account);cls.setup_receipts.append(dict(request=request,response=reply))
                after=store.read_profile(account);actual=dict(after['depot'])
                for row in after['ammunition']:
                    for key,n in row['loaded'].items():actual[key]+=n
                assert actual==totals
                request=dict(version=2,operation='run_open',account_id=account,native_database_id=native,
                    command_key='selection-setup:run-open',expected_revision=after['revision'],run_id=RUN)
                cls.setup_receipts.append(dict(request=request,response=store.battle(request,authenticated_account_id=account)))
        cls.sources={n:projection_source(cls.bundle,cls.catalog,cls.seed,b['account_id'])for n,b in cls.bases.items()}
        cls.oracle={}
        for name in('C','D'):
            with cls.open_store(cls.seed,cls.bases[name]['account_id'])as store:cls.oracle[name]=cls.full_projection_oracle(store,cls.sources[name])

    @classmethod
    def tearDownClass(cls):
        for path,digest in cls.input_hashes.items():assert sha(path.read_bytes())==digest,'ORIGINAL_TEST_OWNER_CHANGED'
        (cls.evidence/'setup.json').write_bytes(canonical(dict(receipts=cls.setup_receipts,new_grants=0,v3_activation=False,
            input_hashes={str(p):v for p,v in cls.input_hashes.items()}))+b'\n')
        cls.seed_temp.cleanup()

    @classmethod
    def open_store(cls,path,account):return MixedAmmoStore(path,cls.catalog,account_id=account,shell_catalog=cls.shell,terminal_policy=cls.policy)

    @classmethod
    def full_projection_oracle(cls,store,source):
        store.connection.execute('BEGIN')
        try:
            snapshot=store.read_profile(store.pool_account);profile=store._project_profile(store.pool_account,snapshot)
            projection=MixedProjectionSource(PoolProjectionSource(source,store),store)
            files=projection.fixture_files(profile,snapshot,store.layouts(store.pool_account))
            companion=json.loads(files['p06t-ammunition.json'])
            assert companion['state_sha256']==sha(files['state.bin'])
            return dict(revision=snapshot['revision'],aggregate_sha256=sha(canonical(snapshot)),native_state_sha256=sha(files['state.bin']),
                source_sha256=source.bundle_sha256,catalog_sha256=store.catalog.sha256,registry_sha256=store.registry.sha256,
                mixed_policy_sha256=companion['policy_sha256'],shell_catalog_sha256=companion['shell_catalog_sha256'])
        finally:store.connection.rollback()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='wot-selection-case-');self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/'game.sqlite'
        with closing(sqlite3.connect(self.seed))as src:
            with closing(sqlite3.connect(self.db))as dst:src.backup(dst)
        self.vectors=[]

    def tearDown(self):
        with closing(sqlite3.connect(self.db))as c:
            res=c.execute('SELECT count(*) FROM p06t_reservation').fetchone()[0]
            ledger=c.execute('SELECT count(*) FROM game_command_ledger').fetchone()[0]
        (self.evidence/(self._testMethodName+'.json')).write_bytes(canonical(dict(test=self._testMethodName,vectors=self.vectors,
            reservations=res,ledger_rows=ledger,scope='ACTUAL_SQL_AND_PUBLISHER_NOT_HTTP_NATIVE',new_grants=0))+b'\n')

    def request(self,name='C',native_inventory_id=1,oracle=None):
        base=self.bases[name];oracle=self.oracle[name]if oracle is None else oracle
        from p06t_terminal import MANIFEST_SHA256
        return dict(version=1,operation='select',account_id=base['account_id'],native_database_id=base['native_database_id'],
            run_id=RUN,expected_revision=oracle['revision'],native_inventory_id=native_inventory_id,
            projection_stamp=dict(native_state_sha256=oracle['native_state_sha256'],owner_source_sha256=oracle['source_sha256'],
                catalog_sha256=oracle['catalog_sha256'],pool_registry_sha256=oracle['registry_sha256'],mixed_policy_sha256=oracle['mixed_policy_sha256'],
                shell_catalog_sha256=oracle['shell_catalog_sha256'],terminal_policy_sha256=MANIFEST_SHA256))

    def select(self,request,name='C',auth=None,source=None):
        with self.open_store(self.db,self.bases[name]['account_id'])as store:
            reader=SelectionReader(store,self.sources[name]if source is None else source)
            response=reader.select(request,authenticated_account_id=self.bases[name]['account_id']if auth is None else auth)
            self.assertFalse(store.connection.in_transaction);self.assertEqual(store.connection.execute('PRAGMA query_only').fetchone()[0],0)
        self.vectors.append(dict(request=deepcopy(request),response=response));return response

    def reject(self,code,action):
        before=sha(self.db.read_bytes())
        with self.assertRaises(TransactionError)as caught:action()
        self.assertEqual(caught.exception.code,code);self.assertEqual(sha(self.db.read_bytes()),before)
        self.vectors.append(dict(rejected_code=code))

    def mutate(self,operation,layout,key='selection-case:mutate'):
        base=self.bases['C'];account=base['account_id']
        with self.open_store(self.db,account)as store:
            snapshot=store.read_profile(account)
            request=dict(account_id=account,native_database_id=base['native_database_id'],command_key=key,
                expected_revision=snapshot['revision'],wire_revision=1,layout=layout)
            response=getattr(store,operation)(request,authenticated_account_id=account)
            self.vectors.append(dict(mutation=operation,request=request,response=response))

    def current_oracle(self):
        with self.open_store(self.db,self.bases['C']['account_id'])as store:return self.full_projection_oracle(store,self.sources['C'])

    def test_real_C_D_ready_frozen_and_actual_published_state_hash_are_distinct_from_aggregate_hash(self):
        before=sha(self.db.read_bytes())
        for name in('C','D'):
            request=self.request(name);result=self.select(parse_request(canonical(request),request['account_id']),name)
            self.assertEqual(result['projection_stamp']['native_state_sha256'],self.oracle[name]['native_state_sha256'])
            self.assertEqual(result['aggregate_sha256'],self.oracle[name]['aggregate_sha256'])
            self.assertNotEqual(result['aggregate_sha256'],result['projection_stamp']['native_state_sha256'])
            self.assertEqual([r['count']for r in result['frozen']['ammunition']],[0,4,10])
            self.assertEqual(result['frozen']['initial_shell_compact_id'],2826);self.assertLessEqual(len(canonical(result)),MAX_REPLY)
        self.assertEqual(sha(self.db.read_bytes()),before)

    def test_empty_actual_ammo_and_actual_detached_crew_are_denied(self):
        self.mutate('service',[5,1,6,2570,0,2826,0,3082,0,6,0,0,0,0,0,0])
        self.reject('AMMUNITION_EMPTY',lambda:self.select(self.request(oracle=self.current_oracle())))
        self.mutate('service',[5,1,6,2570,0,2826,4,3082,10,6,0,0,0,0,0,0],key='selection-case:reload')
        self.mutate('transfer',[1,1,-1],key='selection-case:detach-driver')
        self.reject('INCOMPLETE_CREW',lambda:self.select(self.request(oracle=self.current_oracle())))

    def test_existing_owned_IS7_requires_real_hires_and_actual_three_stack_layout(self):
        base=self.bases['C'];account=base['account_id']
        with self.open_store(self.db,account)as store:
            before=store.read_profile(account);members=before['crew_inventory']['members']
            occupied={r['seat']for r in members if r['vehicle_native_id']==2}
        for seat in sorted(set(range(5))-occupied):self.mutate('recruit',[3,2,seat,0],key='selection-case:is7-hire:'+str(seat))
        self.mutate('service',[5,2,6,14602,0,14858,4,15114,10,6,0,0,0,0,0,0],key='selection-case:is7-owned-ammo')
        oracle=self.current_oracle();reply=self.select(self.request(native_inventory_id=2,oracle=oracle))
        self.assertEqual((reply['frozen']['kind'],reply['frozen']['max_hp'],len(reply['frozen']['crew_ids'])),('is7',2150,5))
        self.assertEqual([r['count']for r in reply['frozen']['ammunition']],[0,4,10]);self.assertEqual(reply['frozen']['initial_shell_compact_id'],14858)
        with self.open_store(self.db,account)as store:
            after=store.read_profile(account)
            self.assertEqual(after['crew_inventory']['free_recruitment_left'],before['crew_inventory']['free_recruitment_left']-len(set(range(5))-occupied))

    def test_foreign_owner_native_id_source_and_run_cannot_be_reinterpreted(self):
        request=self.request()
        self.reject('FOREIGN_ACCOUNT',lambda:self.select(request,auth=self.bases['D']['account_id']))
        self.reject('FOREIGN_ACCOUNT',lambda:self.select(dict(request,native_database_id=4)))
        self.reject('FOREIGN_ACCOUNT',lambda:self.select(request,source=self.sources['D']))
        self.reject('RUN_FENCED',lambda:self.select(dict(request,run_id='eaf4add0-f6a1-4a37-85be-4e2f6feafdb0')))
        source=deepcopy(self.sources['C']);source.bundle_sha256='0'*64
        self.reject('SOURCE_STAMP_MISMATCH',lambda:self.select(request,source=source))

    def test_revision_and_every_actual_source_native_stamp_reject_without_ready_or_writes(self):
        request=self.request();self.reject('STALE_REVISION',lambda:self.select(dict(request,expected_revision=request['expected_revision']-1)))
        for key in request['projection_stamp']:
            changed=deepcopy(request);changed['projection_stamp'][key]='0'*64
            self.reject('NATIVE_STATE_STAMP_MISMATCH'if key=='native_state_sha256'else'SOURCE_STAMP_MISMATCH',lambda:self.select(changed))

    def test_any_account_active_reserve_blocks_even_another_available_selected_vehicle(self):
        request=self.request(native_inventory_id=2);base=self.bases['C']
        with self.open_store(self.db,base['account_id'])as store:
            admit=dict(version=2,operation='admit',account_id=base['account_id'],native_database_id=base['native_database_id'],
                command_key='selection-case:admit',expected_revision=store.read_profile(base['account_id'])['revision'],run_id=RUN,
                native_inventory_id=1,battle_id=RUN+':9007199254740993')
            response=store.battle(admit,authenticated_account_id=base['account_id']);request['expected_revision']=response['revision']
            self.vectors.append(dict(request=admit,response=response))
        self.reject('VEHICLE_RESERVED',lambda:self.select(request))

    def test_parser_is_bounded_unique_and_accepts_no_paths_frozen_claims_or_boolean_identity(self):
        request=self.request()
        for changed in[dict(request,original_root='C:/arbitrary'),dict(request,frozen={}),dict(request,native_database_id=True),
                dict(request,native_inventory_id=0),dict(request,expected_revision=12),dict(request,version=2)]:
            self.reject('INVALID_INPUT',lambda:parse_request(canonical(changed),request['account_id']))
        for raw in[b'{"version":1,"version":1}',b' '*2049]:
            before=sha(self.db.read_bytes())
            with self.assertRaises((ValueError,TransactionError)):parse_request(raw,request['account_id'])
            self.assertEqual(sha(self.db.read_bytes()),before)

    def test_query_only_blocks_actual_write_attempt_and_creates_no_ledger_or_reservation(self):
        request=self.request();base=self.bases['C'];before=sha(self.db.read_bytes());attempted=[]
        with self.open_store(self.db,base['account_id'])as store:
            original=store.read_profile
            def checked(account):
                self.assertEqual(store.connection.execute('PRAGMA query_only').fetchone()[0],1)
                with self.assertRaises(sqlite3.OperationalError):store.connection.execute('UPDATE game_vehicle SET state=state')
                attempted.append(True);return original(account)
            store.read_profile=checked
            response=SelectionReader(store,self.sources['C']).select(request,authenticated_account_id=base['account_id'])
            self.vectors.append(dict(request=request,response=response));self.assertTrue(attempted)
            self.assertEqual(store.connection.execute('SELECT count(*) FROM p06t_reservation').fetchone()[0],0)
        self.assertEqual(sha(self.db.read_bytes()),before)

    def test_two_connection_commit_between_snapshot_and_layout_cannot_mix_revisions(self):
        request=self.request();base=self.bases['C'];committed=[]
        with closing(sqlite3.connect(self.db))as c:self.assertEqual(c.execute('PRAGMA journal_mode=WAL').fetchone()[0],'wal')
        with self.open_store(self.db,base['account_id'])as store:
            original=store.read_profile
            def interleaved(account):
                snapshot=original(account)
                if not committed:
                    self.mutate('service',[5,1,6,2570,0,2826,3,3082,11,6,0,0,0,0,0,0],key='selection-case:concurrent-ammo')
                    committed.append(True)
                return snapshot
            store.read_profile=interleaved
            reply=SelectionReader(store,self.sources['C']).select(request,authenticated_account_id=base['account_id'])
            self.assertEqual(reply['aggregate_sha256'],self.oracle['C']['aggregate_sha256'])
            self.assertEqual(reply['projection_stamp']['native_state_sha256'],self.oracle['C']['native_state_sha256'])
            self.assertEqual([r['count']for r in reply['frozen']['ammunition']],[0,4,10]);self.assertEqual(len(committed),1)
            self.vectors.append(dict(request=request,response=reply))
        after=self.current_oracle();self.assertEqual(after['revision'],request['expected_revision']+1)
        self.assertNotEqual(after['aggregate_sha256'],reply['aggregate_sha256'])
        self.assertNotEqual(after['native_state_sha256'],reply['projection_stamp']['native_state_sha256'])
        self.reject('STALE_REVISION',lambda:self.select(request))
        next_reply=self.select(self.request(oracle=after));self.assertEqual([r['count']for r in next_reply['frozen']['ammunition']],[0,3,11])


if __name__=='__main__':unittest.main(verbosity=2)
