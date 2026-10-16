"""Real source-backed SQLite/API4 reader; no native, socket or fake ownership."""
from copy import deepcopy
import json,os,subprocess,sys,tempfile,unittest,uuid
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
from tests.helpers.p10b_selection_loss_seed import Fixture,SEED,ROOT,HERE,RUN,SHELLS,TERMINAL,logical,sha,canonical,load_catalog
from p10b_selection_loss import SelectionLossReader,parse_request
from game_profile_tx import TransactionError
OUT=Path(os.environ.get('SELECTION_LOSS_SQL_EVIDENCE',str(ROOT/'local/evidence'/('p10b-loss-selection-sql-'+uuid.uuid4().hex)))).resolve();OUT.relative_to(ROOT/'local/evidence');OUT.mkdir(parents=True,exist_ok=False)

class SelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.catalog=load_catalog(json.loads(SEED.read_bytes())['original'])
    def setUp(self):self.fx=Fixture(catalog=self.catalog);self.addCleanup(self.fx.close)
    def reject(self,code,action):
        before=logical(self.fx.database)
        with self.assertRaises(TransactionError)as caught:action()
        self.assertEqual(caught.exception.code,code);self.assertEqual(logical(self.fx.database),before)
    def test_actual_both_owners_native_bytes_wrapped_frozen_and_clean_cli(self):
        vectors=[]
        for slot in range(2):
            request,files=self.fx.request(slot);before=logical(self.fx.database);reply=self.fx.select(request,slot)
            self.assertEqual([a['count']for a in reply['frozen']['loadout']['ammunition']],[0,4,10])
            self.assertEqual(reply['projection_stamp']['native_state_sha256'],sha(files['state.bin']))
            self.assertEqual(reply['projection_stamp']['loss_companion_sha256'],sha(files['p06t-ammo-loss.json']))
            self.assertNotEqual(reply['aggregate_sha256'],reply['projection_stamp']['native_state_sha256'])
            store=self.fx.stores[slot];self.assertFalse(store.connection.in_transaction);self.assertEqual(store.connection.execute('PRAGMA query_only').fetchone()[0],0)
            self.assertEqual(logical(self.fx.database),before)
            env=dict(os.environ);env.pop('PYTHONPATH',None)
            argv=[sys.executable,'-B','-X','utf8',str(HERE/'tools/p10b_selection_loss_service.py'),'--database',str(self.fx.database),
                '--bundle',self.fx.metadata['bundle'],'--original-root',self.fx.metadata['original'],'--account-id',self.fx.accounts[slot],
                '--shell-catalog',str(SHELLS),'--terminal-policy',str(TERMINAL)]
            with tempfile.TemporaryDirectory(prefix='wot-loss-selection-cwd-')as cwd:
                child=subprocess.run(argv,input=canonical(request),cwd=cwd,env=env,capture_output=True,timeout=30)
            self.assertEqual(child.returncode,0,child.stderr);self.assertEqual(json.loads(child.stdout),reply);self.assertEqual(logical(self.fx.database),before)
            vectors.append(dict(request=request,response=reply))
        (OUT/'vectors.json').write_bytes(canonical(dict(schema='p10b-loss-selection-actual-vectors.v1',native='NOT_RUN',vectors=vectors,source_unchanged=True,new_grants=0)))
    def test_identity_source_revision_current_run_and_empty_uncrewed_denials(self):
        request,_=self.fx.request()
        for code,key,value in [('FOREIGN_ACCOUNT','native_database_id',4),('STALE_REVISION','expected_revision',request['expected_revision']-1),
            ('RUN_FENCED','run_id','890724fb-9efb-42f6-9acc-7aa34d3ab24e'),('UNKNOWN_VEHICLE','native_inventory_id',999)]:
            self.reject(code,lambda:self.fx.select(dict(request,**{key:value})))
        for key in request['projection_stamp']:
            poisoned=deepcopy(request);poisoned['projection_stamp'][key]='0'*64
            code='AMMO_LOSS_POLICY_REQUIRED' if key=='loss_policy_sha256' else 'SOURCE_STAMP_MISMATCH'
            self.reject(code,lambda:self.fx.select(poisoned))
        self.fx.mutate('service',[5,1,6,2570,0,2826,0,3082,0,6,0,0,0,0,0,0]);empty,_=self.fx.request()
        self.reject('AMMUNITION_EMPTY',lambda:self.fx.select(empty))
        self.fx.mutate('service',[5,1,6,2570,0,2826,4,3082,10,6,0,0,0,0,0,0])
        self.fx.mutate('transfer',[1,0,-1]);uncrewed,_=self.fx.request();self.reject('INCOMPLETE_CREW',lambda:self.fx.select(uncrewed))
    def test_actual_any_account_reserve_blocks_ready_and_no_wrong_facade_fallback(self):
        request,_=self.fx.request();store=self.fx.stores[0]
        from p06t_ammo_loss_store import battle_loss_service
        admit={k:request[k]for k in ('version','contract','account_id','native_database_id','run_id','expected_revision')}
        admit.update(operation='admit',command_key='p10b:selection:reserve',battle_id=RUN+':17',native_inventory_id=1)
        self.assertEqual(battle_loss_service(store,admit,authenticated_account_id=self.fx.accounts[0])['status'],'admitted')
        request,_=self.fx.request();self.reject('VEHICLE_RESERVED',lambda:self.fx.select(request))
        from p08c_late_results import LossLateResultsStore
        with LossLateResultsStore(self.fx.database,self.catalog,account_id=self.fx.accounts[0],shell_catalog=SHELLS,terminal_policy=TERMINAL)as facade:
            self.reject('SELECTION_CONFIG_REQUIRED',lambda:SelectionLossReader(facade,self.fx.sources[0]))
    def test_two_connection_wal_commit_cannot_mix_actual_revision_ammo_and_fixture_stamp(self):
        store=self.fx.stores[0];store.connection.execute('PRAGMA journal_mode=WAL');request,_=self.fx.request();expected=self.fx.select(request)
        old_layouts=store.layouts;called=[]
        with self.fx.open(self.fx.accounts[0])as writer:
            def raced(account):
                if not called:
                    called.append(True);self.fx.mutate('service',[5,1,6,2570,0,2826,4,3082,9,6,0,0,0,0,0,0],store=writer)
                return old_layouts(account)
            store.layouts=raced
            try:reply=self.fx.select(request)
            finally:store.layouts=old_layouts
        self.assertEqual(called,[True]);self.assertEqual(reply,expected)
        self.assertEqual(store.read_profile(self.fx.accounts[0])['revision'],request['expected_revision']+1)
        self.reject('STALE_REVISION',lambda:self.fx.select(request))
        latest,_=self.fx.request();self.assertEqual([a['count']for a in self.fx.select(latest)['frozen']['loadout']['ammunition']],[0,4,9])
    def test_bounded_unique_request_parser_no_incoming_paths_or_frozen_claim(self):
        request,_=self.fx.request();self.assertEqual(parse_request(canonical(request),request['account_id']),request)
        for raw in [canonical(dict(request,untrusted_path='C:/untrusted')),canonical(dict(request,frozen={})),
            canonical(dict(request,expected_revision=True)),canonical(request)[:-1]+b',"version":4}',b' '*3073]:
            with self.assertRaises((ValueError,TransactionError)):parse_request(raw,request['account_id'])

if __name__=='__main__':unittest.main()
