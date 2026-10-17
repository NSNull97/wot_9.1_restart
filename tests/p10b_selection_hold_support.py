"""Retained isolated source-owned test DBs. Setup writes are not reader writes."""
from contextlib import closing
from pathlib import Path
import hashlib, json, os, sqlite3, stat, sys, tempfile, uuid

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get('WOT091_ROOT', str(HERE.parents[0]))).resolve(strict=True)
assert (ROOT/'server/gateway/Cargo.toml').is_file()
for p in (ROOT, ROOT/'tools', ROOT/'tests/helpers', HERE, HERE.parent/'tools'):
    sys.path.insert(0, str(p))
from p08b_owner_hold_four_context import context_seed
from p09e_research_catalog import load_catalog
from p08b_owner_source import projection_source
from p08b_owner_hold_store import OwnerHoldStore, OwnerHoldProjectionSource, CONTRACT, POLICY_SHA256 as HOLD
from p06t_ammo_loss_store import POLICY_SHA256 as LOSS
from p06t_mixed_store import POLICY_SHA256 as MIXED, SOURCE_SHA256
from p06t_terminal import MANIFEST_SHA256
from p04m_pool_projection import PoolProjectionSource
from p04m_stock_registry import DEFINITION_SHA256
from p09d_ammo_projection import canonical
from p09d_ammo_store import sha
from p10b_selection_hold import SelectionHoldReader

OUT = Path(tempfile.mkdtemp(prefix='wot091-selection56-'))
assert OUT.drive.lower() == ROOT.drive.lower()
SHELLS = ROOT/'tests/fixtures/p06t-shell-catalog.json'
TERMINAL = ROOT/'tests/fixtures/p06t-device-policy.json'
RUN = '03513b53-dbb1-4b8a-8c18-d8c295e397ed'
VECTORS, SETUPS, SOURCE_OBSERVATIONS = [], [], []

def plain(value):
    p = Path(value)
    assert p.is_absolute() and '..' not in p.parts
    for q in (p,*p.parents):
        try: s=q.lstat()
        except FileNotFoundError: continue
        assert not stat.S_ISLNK(s.st_mode) and not (getattr(s,'st_file_attributes',0)&0x400)
    return p

def source_refs(database):
    result={}
    for p in (database,Path(str(database)+'-wal'),Path(str(database)+'-shm')):
        plain(p)
        result[str(p)] = None if not p.exists() else dict(bytes=p.stat().st_size,sha256=sha(p.read_bytes()))
    return result

def logical(connection):
    return sha('\n'.join(connection.iterdump()).encode('utf8'))

def files(database): return source_refs(database)

def measures(connection):
    rows=lambda table: sorted((list(r) for r in connection.execute('SELECT * FROM '+table)),key=canonical)
    profiles={a:json.loads(raw)['resources'] for a,raw in connection.execute('SELECT account_id,profile_json FROM game_profiles')}
    return dict(resources=profiles,**{t:rows(t) for t in ('p09c_ammo_depot','p09c_ammo_mount','p04d_crew_member','game_vehicle','p09d_native_layout','p09d_import')})

class Fixture:
    def __init__(self,index,catalog):
        self.index=index;self.catalog=catalog;self.serial=0;self.stores=[];self.sources=[]
        metadata,lineage=context_seed(index,ROOT)
        self.metadata=metadata;self.source=plain(metadata['database']);self.source_before=source_refs(self.source)
        # The preserved metadata attests the raw main DB. A nonempty unbound WAL
        # cannot silently become another historical seed. Empty WAL is handled
        # by actual SQLite RO backup, never immutable=1/checkpoint/deletion.
        wal=self.source_before[str(self.source)+'-wal']
        if wal is not None and wal['bytes'] != 0: raise RuntimeError('SEED_NONEMPTY_UNATTESTED_WAL_NOT_RUN')
        self.directory=Path(tempfile.mkdtemp(prefix=('anchor-' if index==0 else 'owners-'),dir=OUT))
        self.database=self.directory/'game.sqlite'
        try:
            with closing(sqlite3.connect(self.source.as_uri()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(self.database)) as dest:
                src.execute('PRAGMA query_only=ON');src.execute('BEGIN')
                source_logical=logical(src);src.backup(dest)
                assert logical(dest)==source_logical
                src.rollback()
            self.assert_source()
            self.accounts=[p['account_id'] for p in metadata['profiles']]
            with closing(sqlite3.connect(self.database)) as c: initial=measures(c)
            activations=[]
            for account in self.accounts:
                store=self.open(account);self.stores.append(store)
                aggregate=store.read_profile(account);public=store._project_profile(account,aggregate)
                original_revision=aggregate['revision'];pool_receipt=None
                assert not store._active_mixed(account)
                pool=False
                if not store.pool_active():
                    r=store.activate_pool(dict(version=1,account_id=account,native_database_id=public['native_database_id'],command_key='selection56:pool:'+account,expected_revision=aggregate['revision'],definition_sha256=DEFINITION_SHA256,registry_sha256=store.registry.sha256),authenticated_account_id=account)
                    assert r['ammunition_granted']==0;pool=True;pool_receipt=r
                aggregate=store.read_profile(account)
                if not store.mixed_active():
                    r=store.activate_mixed(account_id=account,authenticated_account_id=account,expected_revision=aggregate['revision'],native_database_id=public['native_database_id']);assert r['ammunition_granted']==0
                if not store.loss_active():
                    r=store.activate_loss(account_id=account,authenticated_account_id=account,expected_revision=aggregate['revision'],native_database_id=public['native_database_id']);assert r['ammunition_granted']==0
                assert not store.hold_active()
                r=store.activate_hold(authenticated_account_id=account,native_database_id=public['native_database_id'],expected_revision=aggregate['revision'],old_sessions=0,pending_jobs=0,pending_returns=0);assert r['ammunition_granted']==0
                command=dict(version=5,contract=CONTRACT,operation='run_open',account_id=account,native_database_id=public['native_database_id'],run_id=RUN,expected_revision=aggregate['revision'],command_key='selection56:run-open')
                reply=store.battle_hold(command,authenticated_account_id=account)
                assert reply['status']=='ready' and reply['reservation'] is None
                activations.append(dict(account_id=account,native_database_id=public['native_database_id'],pool_activated=pool,pool_receipt=pool_receipt,original_revision=original_revision,before_runopen_revision=aggregate['revision'],after_revision=reply['revision'],run_open=reply))
                self.sources.append(projection_source(metadata['bundle'],catalog,self.database,account))
            with closing(sqlite3.connect(self.database)) as c:
                after=measures(c)
            # Real Pool activation of legacy B inserts nine zero-quantity stock
            # depot metadata rows. Existing rows must remain byte-equivalent;
            # exact source-known new row set/zero quantities is setup evidence,
            # never an exception to post-setup reader conservation.
            depot='p09c_ammo_depot'
            assert all(initial[k]==after[k] for k in initial if k!=depot)
            old={(r[0],r[1]):r[2:]for r in initial[depot]}
            new={(r[0],r[1]):r[2:]for r in after[depot]}
            assert all(k in new and new[k]==v for k,v in old.items())
            from p04m_stock_registry import NEW_KINDS
            expected_added=set()
            for step,store in zip(activations,self.stores):
                if step['pool_activated']:
                    for kind in NEW_KINDS:
                        p=store.registry.profiles[kind]
                        expected_added.update((step['account_id'],shell)for shell in store.mounts[p.assembly_id].shell_ids)
            expected_added-=set(old)
            assert set(new)-set(old)==expected_added and all(new[k]==[0] for k in expected_added)
            zero_rows=[dict(account_id=a,shell_id=shell,quantity=0)for a,shell in sorted(expected_added)]
            self.assert_source()
            SETUPS.append(dict(source_index=index,source_lineage=lineage,database=str(self.database),source_before=self.source_before,source_after=source_refs(self.source),schema_and_rows_sha256_after_setup=logical(self.stores[0].connection),activations=activations,new_grants=0,resources_existing_ammo_depot_crew_vehicles_layouts_raw_import_unchanged=True,source_known_zero_depot_rows_added_by_pool_setup=zero_rows,owned_before_sha256={k:sha(canonical(v))for k,v in initial.items()},owned_after_sha256={k:sha(canonical(v))for k,v in after.items()},setup_is_separate_writer_operations=True))
        except BaseException:
            for store in self.stores: store.close()
            SOURCE_OBSERVATIONS.append(dict(source_index=self.index,before=self.source_before,after=source_refs(self.source),unchanged=source_refs(self.source)==self.source_before,setup_failed=True))
            raise
    def assert_source(self):
        current=source_refs(self.source)
        assert current==self.source_before, 'SOURCE_MAIN_OR_WAL_SHM_CHANGED'
    def open(self,account):
        return OwnerHoldStore(self.database,self.catalog,account_id=account,shell_catalog=SHELLS,terminal_policy=TERMINAL)
    def close(self):
        for store in self.stores:store.close()
        self.assert_source()
        SOURCE_OBSERVATIONS.append(dict(source_index=self.index,before=self.source_before,after=source_refs(self.source),unchanged=True))
        # Retain every new test DB; no delete/cleanup of old or new data.
    def request(self,slot=0,native=1):
        account=self.accounts[slot];store=self.stores[slot];source=self.sources[slot]
        aggregate=store.read_profile(account);public=store._project_profile(account,aggregate)
        projection=OwnerHoldProjectionSource(PoolProjectionSource(source,store),store)
        projected=projection.fixture_files(public,aggregate,store.layouts(account))
        request=dict(version=5,contract=CONTRACT,operation='select',account_id=account,native_database_id=public['native_database_id'],run_id=RUN,expected_revision=aggregate['revision'],native_inventory_id=native,projection_stamp=dict(native_state_sha256=sha(projected['state.bin']),owner_source_sha256=source.bundle_sha256,catalog_sha256=store.catalog.sha256,pool_registry_sha256=store.registry.sha256,mixed_policy_sha256=MIXED,shell_catalog_sha256=SOURCE_SHA256,terminal_policy_sha256=MANIFEST_SHA256,loss_policy_sha256=LOSS,loss_companion_sha256=sha(projected['p06t-ammo-loss.json']),hold_policy_sha256=HOLD,hold_companion_sha256=sha(projected['p08b-owner-hold.json'])))
        return request,projected
    def select(self,request,slot=0):
        return SelectionHoldReader(self.stores[slot],self.sources[slot]).select(request,authenticated_account_id=self.accounts[slot])
    def mutate(self,operation,layout,slot=0,store=None):
        store=store or self.stores[slot];account=self.accounts[slot];aggregate=store.read_profile(account);public=store._project_profile(account,aggregate);self.serial+=1
        request=dict(account_id=account,native_database_id=public['native_database_id'],expected_revision=aggregate['revision'],wire_revision=1,command_key='selection56:garage:'+str(self.serial),layout=layout)
        response=getattr(store,operation)(request,authenticated_account_id=account)
        assert response['status']!='rejected';return response
    def service_counts(self,counts,slot=0,store=None):
        layout=list((store or self.stores[slot]).layouts(self.accounts[slot])[1])
        assert len(layout)==6
        for i,n in enumerate(counts):layout[2*i+1]=n
        return self.mutate('service',[5,1,6,*layout,6,0,0,0,0,0,0],slot,store)

def save_report(result):
    data=dict(schema='p10b-selection-hold56-actual-sql.v1',status='PASS_ACTUAL_READER_SQLITE_ONLY' if result.wasSuccessful() else 'FAIL_ACTUAL_READER_SQLITE',tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),skips=len(result.skipped),vectors=VECTORS,setups=SETUPS,source_observations=SOURCE_OBSERVATIONS,cli='NOT_IMPLEMENTED',http='NOT_RUN',rust='NOT_RUN',native_training5='FORBIDDEN_UNIMPLEMENTED',new_grants=0,retained_output=str(OUT))
    with (OUT/'result.json').open('xb') as stream:stream.write(canonical(data))
    return OUT/'result.json'
