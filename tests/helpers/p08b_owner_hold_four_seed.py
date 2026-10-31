"""Future tracked helper: actual four-source TEST import and real mode opt-in.

No RunOpen/admission/final facts. Source C,D,A,B is immutable; B's legitimate
Pool activation advances25->26 and adds zero metadata, never ammunition.
"""
from contextlib import closing
from pathlib import Path
import hashlib
import json
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(Path(__file__).resolve().parent),str(ROOT/'tools'),str(ROOT)]
from p08b_owner_hold_four_source import build_fixture, SOURCES
from p08b_owner_hold_four_context import original_root, context_seed
OWNERS=('80ad3bc2-476e-4fbd-899d-a4679ea167d2','633ad84f-f33f-4aab-bacd-421f31a93bae',
        'c5326cc1-8524-479c-8bba-72e973489c22','271022a3-41e0-406e-b6fa-59930c320442')

def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('ascii')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def plain(v,exists=True):
    p=Path(v)
    if not p.is_absolute()or'..'in p.parts:raise ValueError('absolute lexical path required')
    for q in(p,*p.parents):
        if q.exists()and(q.is_symlink()or q.is_junction()):raise ValueError('links refused')
    return p.resolve(strict=exists)

def measures(db):
    profiles={a:json.loads(raw)for a,raw in db.execute('SELECT account_id,profile_json FROM game_profiles')}
    if set(profiles)!=set(OWNERS):raise ValueError('exact source owners required')
    quantities={a:{}for a in OWNERS}
    for a,shell,n in db.execute('SELECT account_id,shell_id,quantity FROM p09c_ammo_depot'):
        if n:quantities[a][shell]=quantities[a].get(shell,0)+n
    for a,raw in db.execute('SELECT account_id,loaded_json FROM p09c_ammo_mount'):
        for shell,n in json.loads(raw).items():
            if n:quantities[a][shell]=quantities[a].get(shell,0)+n
    rows=lambda t:[list(r)for r in db.execute('SELECT * FROM '+t+' ORDER BY account_id')]
    return dict(resources={a:profiles[a]['resources']for a in OWNERS},quantities=quantities,
        crew=sorted(rows('p04d_crew_member'),key=canonical),vehicles=sorted(rows('game_vehicle'),key=canonical),
        layouts=sorted(rows('p09d_native_layout'),key=canonical),
        revisions={a:profiles[a]['snapshot_revision']for a in OWNERS})

def activate_all(database,original):
    from p08b_owner_hold_store import OwnerHoldStore
    from p09e_research_catalog import load_catalog
    from p04m_stock_registry import DEFINITION_SHA256
    catalog=load_catalog(original)
    with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True))as db:before=measures(db)
    activations=[]
    for account in OWNERS:
        with OwnerHoldStore(database,catalog,account_id=account,shell_catalog=ROOT/'tests/fixtures/p06t-shell-catalog.json',terminal_policy=ROOT/'tests/fixtures/p06t-device-policy.json')as store:
            def current():
                aggregate=store.read_profile(account)
                return aggregate,store._project_profile(account,aggregate)
            aggregate,public=current();native=public['native_database_id'];pool=False
            if not store.pool_active():
                response=store.activate_pool(dict(version=1,account_id=account,native_database_id=native,command_key='hold17:pool:'+account,
                    expected_revision=aggregate['revision'],definition_sha256=DEFINITION_SHA256,registry_sha256=store.registry.sha256),authenticated_account_id=account)
                if response['ammunition_granted']!=0:raise ValueError('pool unexpectedly granted ammunition')
                pool=True
            aggregate,public=current()
            if not store.mixed_active():store.activate_mixed(account_id=account,authenticated_account_id=account,expected_revision=aggregate['revision'],native_database_id=native)
            if not store.loss_active():store.activate_loss(account_id=account,authenticated_account_id=account,expected_revision=aggregate['revision'],native_database_id=native)
            if store.hold_active():raise ValueError('preexisting Hold5 is not this predecessor fixture')
            store.activate_hold(authenticated_account_id=account,native_database_id=native,expected_revision=aggregate['revision'],old_sessions=0,pending_jobs=0,pending_returns=0)
            activations.append(dict(account_id=account,pool_activated=pool,revision=aggregate['revision']))
    with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True))as db:
        after=measures(db)
        for key in('resources','quantities','crew','vehicles','layouts'):
            if after[key]!=before[key]:raise ValueError('activation changed real inventory:'+key)
        for account in OWNERS:
            expected=before['revisions'][account]+int(account==OWNERS[3])
            if after['revisions'][account]!=expected:raise ValueError('unexpected activation revision')
        for table in('p06t_reservation','battle_ammo_loss_reservation','battle_owner_hold_reservation','battle_owner_hold_command'):
            if db.execute('SELECT count(*)FROM '+table).fetchone()[0]:raise ValueError('seed contains new battle authority')
        if db.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]or db.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('activated fixture integrity')
        profiles=[]
        for account in OWNERS:
            raw=db.execute('SELECT profile_json FROM game_profiles WHERE account_id=?',(account,)).fetchone()[0];p=json.loads(raw)
            profiles.append({k:p[k]for k in('account_id','native_database_id','username','created_at_ms','snapshot_revision')})
    return profiles,activations,before,after

def seed(destination,metadata_path):
    expected=plain(ROOT/SOURCES[1][0]);metadata_path=plain(metadata_path)
    if metadata_path!=expected:raise ValueError('closed actual C/D metadata required')
    metadata,context=context_seed(1,ROOT)
    base=plain(ROOT/'local/test-runs/p08b-owner-hold-composition17')
    destination=plain(destination,False);part=destination.relative_to(base)
    if len(part.parts)!=2 or not part.parts[0].startswith('run-')or part.parts[1]!='game.sqlite'or destination.exists():raise ValueError('fresh composition17 destination required')
    imported=build_fixture();source=plain(imported['database']);source_sha=sha(source)
    if imported['new_game_accounts']or imported['new_grants']:raise ValueError('importer authority boundary')
    with destination.open('xb'):pass
    with closing(sqlite3.connect(source.as_uri()+'?mode=ro&immutable=1',uri=True))as old,closing(sqlite3.connect(destination))as out:old.backup(out)
    from cat_nations_test_restamp import restamp_copy
    restamp_copy(destination)
    profiles,activated,before,after=activate_all(destination,metadata['original'])
    if sha(source)!=source_sha:raise ValueError('four-owner imported predecessor changed')
    source_databases=[];source_seeds=[]
    for relative,meta_sha,db_sha,_ in SOURCES:
        path=plain(original_root(ROOT)/relative);content=json.loads(path.read_bytes());db=plain(content['database'])
        if sha(path)!=meta_sha or sha(db)!=db_sha:raise ValueError('preserved source changed')
        source_databases.append(dict(path=str(db),sha256=db_sha));source_seeds.append(dict(path=str(path),sha256=meta_sha))
    result=dict(schema='p08b-owner-hold-four-composition-seed.v2',database=str(destination),profiles=profiles,
        bundle=str(plain(metadata['bundle'])),original=str(plain(metadata['original'])),source_databases=source_databases,source_seeds=source_seeds,context_seed=context,
        imported_predecessor=dict(path=str(source),sha256=source_sha,receipt_sha256=sha(source.with_name('receipt.json'))),
        activations=activated,inventory_before=before,inventory_after=after,
        new_grants=0,new_accounts=0,new_reservations=0,new_results=0,source_unchanged=True,native_client='NOT_RUN')
    with destination.with_suffix('.json').open('xb')as out:out.write(canonical(result)+b'\n')
    return result

if __name__=='__main__':
    if len(sys.argv)!=3:raise ValueError('fresh output and exact C/D metadata required')
    result=seed(sys.argv[1],sys.argv[2]);print('PREPARED_ACTUAL_FOUR_HOLD5_NO_RUN_NO_ADMIT_NO_GRANTS')
