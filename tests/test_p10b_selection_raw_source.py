"""Actual source A/B SQL regression. Fresh temp backups, no grant/HTTP/native."""
from contextlib import closing
from copy import copy
import hashlib,json,os,sqlite3,tempfile,unittest,uuid
from pathlib import Path
ROOT=next(p for p in Path(__file__).resolve().parents if (p/'server/gateway/Cargo.toml').is_file())
from p09e_research_catalog import load_catalog
from p08b_owner_source import projection_source
from p04m_stock_registry import DEFINITION_SHA256
from p04m_pool_projection import PoolProjectionSource
from p06t_mixed_store import MixedAmmoStore,POLICY_SHA256 as MIXED,SOURCE_SHA256
from p06t_mixed_projection import MixedProjectionSource
from p06t_ammo_loss_store import AmmoLossStore,AmmoLossProjectionSource,CONTRACT,POLICY_SHA256 as LOSS,battle_loss_service
from p06t_terminal import MANIFEST_SHA256
from p10b_selection import SelectionReader
from p10b_selection_loss import SelectionLossReader
from p09d_ammo_projection import canonical
from game_profile_tx import TransactionError
SEED=ROOT/'local/evidence/20261016-p06t-owned01/seed01/seed.json'
RUN='481ac43a-1645-4e36-a990-9aba6f2b4ee6'
def sha(b):return hashlib.sha256(b).hexdigest()
def logical(p):
    with closing(sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True))as c:
        c.execute('PRAGMA query_only=ON');return sha('\n'.join(c.iterdump()).encode())
class RawSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.meta=json.loads(SEED.read_bytes());cls.source=Path(cls.meta['database']).resolve();cls.raw=sha(cls.source.read_bytes());cls.rows=logical(cls.source)
        cls.catalog=load_catalog(cls.meta['original']);cls.accounts=[p['account_id']for p in cls.meta['profiles']];assert len(set(cls.accounts))==2
        cls.scratch=Path(tempfile.mkdtemp(prefix='wot-p10b-source04-')).resolve();assert cls.scratch.parent==Path(tempfile.gettempdir()).resolve();cls.receipts=[]
    @classmethod
    def tearDownClass(cls):
        assert sha(cls.source.read_bytes())==cls.raw and logical(cls.source)==cls.rows,'READONLY_SOURCE_CHANGED'
        if os.environ.get('P10B_RAW_SOURCE_EVIDENCE'):
            out=Path(os.environ['P10B_RAW_SOURCE_EVIDENCE']).resolve();out.relative_to(ROOT/'local');out.mkdir(parents=True,exist_ok=False)
            (out/'result.json').write_bytes(canonical(dict(schema='p10b-source-raw-sql04.v1',cases=cls.receipts,source_unchanged=True,new_grants=0,
                scratch=str(cls.scratch),scratch_retained=True,native='NOT_RUN',http='NOT_RUN')))
    def database(self,mode):
        p=self.scratch/(self._testMethodName+'-'+str(mode)+'-'+uuid.uuid4().hex+'.sqlite')
        with closing(sqlite3.connect(self.source.as_uri()+'?mode=ro',uri=True))as old,closing(sqlite3.connect(p))as new:old.backup(new)
        return p
    def prepare(self,p,mode,account):
        store=(AmmoLossStore if mode==4 else MixedAmmoStore)(p,self.catalog,account_id=account,shell_catalog=ROOT/'tests/fixtures/p06t-shell-catalog.json',terminal_policy=ROOT/'tests/fixtures/p06t-device-policy.json');self.addCleanup(store.close)
        before=store.read_profile(account);public=store._project_profile(account,before)
        if not store.pool_active():store.activate_pool(dict(version=1,account_id=account,native_database_id=public['native_database_id'],command_key='source04:pool',expected_revision=before['revision'],definition_sha256=DEFINITION_SHA256,registry_sha256=store.registry.sha256),authenticated_account_id=account)
        if not store.mixed_active():store.activate_mixed(account_id=account,authenticated_account_id=account)
        if mode==4 and not store.loss_active():store.activate_loss(account_id=account,authenticated_account_id=account,expected_revision=store.read_profile(account)['revision'],native_database_id=public['native_database_id'])
        aggregate=store.read_profile(account);run=dict(version=mode,operation='run_open',account_id=account,native_database_id=public['native_database_id'],command_key='source04:run',expected_revision=aggregate['revision'],run_id=RUN)
        if mode==4:run['contract']=CONTRACT;reply=battle_loss_service(store,run,authenticated_account_id=account)
        else:reply=store.battle(run,authenticated_account_id=account)
        self.assertEqual(reply['status'],'ready');self.assertIsNone(reply['reservation']);aggregate=store.read_profile(account)
        self.assertEqual(aggregate['ammunition'],before['ammunition']);self.assertEqual({k:v for k,v in aggregate['depot'].items()if v},{k:v for k,v in before['depot'].items()if v})
        source=projection_source(self.meta['bundle'],self.catalog,p,account);public=store._project_profile(account,aggregate)
        projection=(AmmoLossProjectionSource if mode==4 else MixedProjectionSource)(PoolProjectionSource(source,store),store);files=projection.fixture_files(public,aggregate,store.layouts(account))
        stamp=dict(native_state_sha256=sha(files['state.bin']),owner_source_sha256=source.bundle_sha256,catalog_sha256=store.catalog.sha256,pool_registry_sha256=store.registry.sha256,mixed_policy_sha256=MIXED,shell_catalog_sha256=SOURCE_SHA256,terminal_policy_sha256=MANIFEST_SHA256)
        q=dict(version=4 if mode==4 else 1,operation='select',account_id=account,native_database_id=public['native_database_id'],run_id=RUN,expected_revision=aggregate['revision'],native_inventory_id=1,projection_stamp=stamp)
        if mode==4:q['contract']=CONTRACT;stamp.update(loss_policy_sha256=LOSS,loss_companion_sha256=sha(files['p06t-ammo-loss.json']))
        return store,source,q
    def test_actual_anchor_A_and_owner_B_ready_without_rewriting_old_source_or_rows(self):
        for mode in[2,4]:
            p=self.database(mode)
            for index,account in enumerate(self.accounts):
                with self.subTest(mode=mode,owner=index):
                    store,source,q=self.prepare(p,mode,account);row=store.connection.execute('SELECT base_json,base_sha256,bundle_sha256 FROM p09d_import WHERE account_id=?',(account,)).fetchone()
                    self.assertEqual(source.profile_bytes,row[0].encode('ascii'));self.assertEqual(sha(source.profile_bytes),row[1]);self.assertEqual(source.bundle_sha256,row[2]);self.assertEqual(source.profile,json.loads(row[0]))
                    self.assertEqual(source.profile_bytes==canonical(source.profile),index==1);before=logical(p)
                    reply=(SelectionLossReader if mode==4 else SelectionReader)(store,source).select(q,authenticated_account_id=account)
                    self.assertEqual(reply['status'],'ready');self.assertEqual(reply['account_id'],account);self.assertEqual(logical(p),before)
                    self.receipts.append(dict(mode=mode,owner=index,status='ready',source_raw_sha256=row[1],canonical_sha256=sha(canonical(source.profile)),all_rows_unchanged=True))
    def test_semantically_identical_reordered_raw_source_is_rejected_atomically(self):
        for mode in[2,4]:
            p=self.database(mode)
            for index,account in enumerate(self.accounts):
                with self.subTest(mode=mode,owner=index):
                    store,source,q=self.prepare(p,mode,account);poison=copy(source);poison.profile_bytes=json.dumps(dict(reversed(sorted(source.profile.items()))),ensure_ascii=True,separators=(',',':')).encode('ascii')
                    self.assertNotEqual(poison.profile_bytes,source.profile_bytes);self.assertEqual(json.loads(poison.profile_bytes),source.profile);before=logical(p)
                    with self.assertRaises(TransactionError)as caught:(SelectionLossReader if mode==4 else SelectionReader)(store,poison).select(q,authenticated_account_id=account)
                    self.assertEqual(caught.exception.code,'SOURCE_STAMP_MISMATCH');self.assertEqual(logical(p),before)
                    self.receipts.append(dict(mode=mode,owner=index,status='SOURCE_STAMP_MISMATCH',negative='equal semantic profile; different raw source',all_rows_unchanged=True))
if __name__=='__main__':unittest.main()
