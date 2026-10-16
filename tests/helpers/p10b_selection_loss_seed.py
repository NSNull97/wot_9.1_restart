"""Disposable C/D backup and actual API4 activation; no grants or reserve."""
from contextlib import closing
from copy import deepcopy
import hashlib,json,sqlite3,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];HERE=ROOT
sys.path[:0]=[str(HERE/'tools'),str(ROOT/'tools'),str(ROOT)]
from p09e_research_catalog import load_catalog
from p08b_owner_source import projection_source
from p06t_ammo_loss_store import AmmoLossStore,AmmoLossProjectionSource,battle_loss_service,CONTRACT,POLICY_SHA256 as LOSS
from p04m_pool_projection import PoolProjectionSource
from p06t_mixed_store import POLICY_SHA256 as MIXED,SOURCE_SHA256
from p06t_terminal import MANIFEST_SHA256
from p09d_ammo_projection import canonical
from p09d_ammo_store import sha
from p10b_selection_loss import SelectionLossReader
SEED=ROOT/'local/night-staging/20261016/p10b-selection-http01/seed01/seed.json'
RUN='f5019710-c15f-431e-a390-d1910acf5cb1'
SHELLS=ROOT/'tests/fixtures/p06t-shell-catalog.json';TERMINAL=ROOT/'tests/fixtures/p06t-device-policy.json'

def logical(path):
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True))as c:
        return sha('\n'.join(c.iterdump()).encode('utf8'))

class Fixture:
    def __init__(self,database=None,catalog=None):
        self.temporary=tempfile.TemporaryDirectory(prefix='wot-p10b-loss-selection-') if database is None else None
        self.database=Path(self.temporary.name)/'game.sqlite' if database is None else Path(database).resolve()
        assert not self.database.exists()
        self.metadata=json.loads(SEED.read_bytes());self.source=Path(self.metadata['database'])
        self.source_sha=sha(self.source.read_bytes());self.source_logical=logical(self.source)
        assert self.source_sha==self.metadata['database_sha256']
        with closing(sqlite3.connect(self.source.resolve().as_uri()+'?mode=ro',uri=True))as src,closing(sqlite3.connect(self.database))as out:src.backup(out)
        self.catalog=catalog or load_catalog(self.metadata['original']);self.serial=0;self.stores=[];self.sources=[];self.run_vectors=[]
        self.accounts=[p['account_id'] for p in self.metadata['profiles']]
        for account in self.accounts:
            store=self.open(account);self.stores.append(store)
            before=store.read_profile(account);public=store._project_profile(account,before)
            assert store.pool_active() and store.mixed_active() and not store._active_mixed(account)
            store.activate_loss(account_id=account,authenticated_account_id=account,expected_revision=before['revision'],native_database_id=public['native_database_id'])
            assert store.read_profile(account)==before
            request=dict(version=4,contract=CONTRACT,operation='run_open',account_id=account,native_database_id=public['native_database_id'],
                command_key='p10b:loss-selection:run-open',expected_revision=before['revision'],run_id=RUN)
            reply=battle_loss_service(store,request,authenticated_account_id=account);assert reply['status']=='ready' and reply['reservation'] is None
            after=store.read_profile(account);assert after['ammunition']==before['ammunition'] and after['depot']==before['depot']
            self.run_vectors.append(dict(request=request,response=reply))
            self.sources.append(projection_source(self.metadata['bundle'],self.catalog,self.database,account))
        self.assert_source()

    def open(self,account):return AmmoLossStore(self.database,self.catalog,account_id=account,shell_catalog=SHELLS,terminal_policy=TERMINAL)
    def assert_source(self):
        assert sha(self.source.read_bytes())==self.source_sha and logical(self.source)==self.source_logical
    def close(self):
        for store in self.stores:store.close()
        self.assert_source()
        if self.temporary:self.temporary.cleanup()
    def request(self,slot=0,native=1):
        store=self.stores[slot];account=self.accounts[slot];aggregate=store.read_profile(account);public=store._project_profile(account,aggregate)
        source=self.sources[slot];projection=AmmoLossProjectionSource(PoolProjectionSource(source,store),store)
        files=projection.fixture_files(public,aggregate,store.layouts(account))
        return dict(version=4,contract=CONTRACT,operation='select',account_id=account,native_database_id=public['native_database_id'],run_id=RUN,
            expected_revision=aggregate['revision'],native_inventory_id=native,projection_stamp=dict(native_state_sha256=sha(files['state.bin']),
            owner_source_sha256=source.bundle_sha256,catalog_sha256=store.catalog.sha256,pool_registry_sha256=store.registry.sha256,
            mixed_policy_sha256=MIXED,shell_catalog_sha256=SOURCE_SHA256,terminal_policy_sha256=MANIFEST_SHA256,
            loss_policy_sha256=LOSS,loss_companion_sha256=sha(files['p06t-ammo-loss.json']))),files
    def select(self,request,slot=0):return SelectionLossReader(self.stores[slot],self.sources[slot]).select(request,authenticated_account_id=self.accounts[slot])
    def mutate(self,operation,layout,slot=0,store=None):
        store=store or self.stores[slot];account=self.accounts[slot];aggregate=store.read_profile(account);public=store._project_profile(account,aggregate);self.serial+=1
        request=dict(account_id=account,native_database_id=public['native_database_id'],expected_revision=aggregate['revision'],wire_revision=1,
            command_key='p10b:loss-selection:mutation:'+str(self.serial),layout=layout)
        response=getattr(store,operation)(request,authenticated_account_id=account)
        assert response['status']!='rejected';return request,response

def main():
    destination=Path(sys.argv[1]).resolve();relative=destination.relative_to(ROOT/'local/web/tests')
    assert len(relative.parts)==2 and relative.parts[0].startswith('run-') and relative.parts[1]=='game.sqlite' and not destination.exists()
    f=Fixture(destination)
    try:
        profiles=[s._project_profile(a,s.read_profile(a)) for a,s in zip(f.accounts,f.stores)]
        metadata=dict(schema='p10b-loss-selection-actual-seed.v1',database=str(destination),bundle=f.metadata['bundle'],original=f.metadata['original'],profiles=profiles,
            run_id=RUN,source_database_sha256=f.source_sha,source_database_logical_sha256=f.source_logical,new_grants=0,source_unchanged=True)
        with destination.with_suffix('.json').open('xb')as out:out.write(canonical(metadata))
        print('PREPARED_LOSS_SELECTION_C_D_NO_GRANTS')
    finally:f.close()

if __name__=='__main__':main()
