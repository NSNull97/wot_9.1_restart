"""Fresh two-owner backup + real loss activation; no reservation/result seed.

Only the regular test's new local/test-runs/p08c-late-composition05/run-* is
mutable. Source DB is opened URI mode=ro and its raw SHA is checked afterwards.
No new grants, no original client execution, no credentials emitted.
"""
from contextlib import closing
import hashlib,json,sqlite3,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from p08c_late_results import LossLateResultsStore
from p09e_research_catalog import load_catalog
from p04m_stock_registry import DEFINITION_SHA256
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def no_links(path):
    path=Path(path)
    if not path.is_absolute() or '..' in path.parts:raise ValueError('absolute lexical path required')
    for part in [path,*path.parents]:
        if part.exists() and (part.is_symlink() or part.is_junction()):raise ValueError('links refused')
    return path.resolve()
def main():
    if len(sys.argv)!=3:raise ValueError('destination and exact own seed required')
    destination=no_links(sys.argv[1]);source_seed=no_links(sys.argv[2])
    expected=(ROOT/'local/evidence/20261016-p06t-owned01/seed01/seed.json').resolve()
    if source_seed!=expected:raise ValueError('closed actual own source seed required')
    roots=[(ROOT/'local/test-runs'/name).resolve() for name in ['p08c-late-composition05','p10b-loss-composition09']]
    matches=[base for base in roots if destination.is_relative_to(base)]
    if len(matches)!=1:raise ValueError('closed regular composition output scope required')
    relative=destination.relative_to(matches[0])
    if len(relative.parts)!=2 or not relative.parts[0].startswith('run-') or relative.parts[1]!='game.sqlite' or destination.exists():raise ValueError('fresh controlled test destination required')
    if source_seed.stat().st_size>65536:raise ValueError('source metadata bound')
    seed=json.loads(source_seed.read_bytes())
    if seed.get('schema')!='p06t-http-real-writer-seed.v2' or seed.get('source_stand_writes') is not False:raise ValueError('exact preserved seed lineage required')
    source=no_links(seed['database'])
    if source!=(source_seed.parent/'game.sqlite').resolve():raise ValueError('closed preserved source database required')
    before=sha(source)
    with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as old,closing(sqlite3.connect(destination)) as fresh:old.backup(fresh)
    sys.path.append(str(ROOT/'tests/helpers'));from cat_nations_test_restamp import restamp_copy
    restamp_copy(destination)
    catalog=load_catalog(seed['original']);accounts=[p['account_id'] for p in seed['profiles']]
    if len(accounts)!=2 or len(set(accounts))!=2:raise ValueError('actual two distinct source owners required')
    with closing(sqlite3.connect(destination.as_uri()+'?mode=ro',uri=True)) as db:
        baseline=[json.loads(db.execute('SELECT profile_json FROM game_profiles WHERE account_id=?',(account,)).fetchone()[0]) for account in accounts]
    for account in accounts:
        with LossLateResultsStore(destination,catalog,account_id=account,shell_catalog=ROOT/'tests/fixtures/p06t-shell-catalog.json',terminal_policy=ROOT/'tests/fixtures/p06t-device-policy.json') as store:
            public=json.loads(store.connection.execute('SELECT profile_json FROM game_profiles WHERE account_id=?',(account,)).fetchone()[0])
            if not store.pool_active():store.activate_pool(dict(version=1,account_id=account,native_database_id=public['native_database_id'],command_key='late:composition:pool',
                expected_revision=store.read_profile(account)['revision'],definition_sha256=DEFINITION_SHA256,registry_sha256=store.registry.sha256),authenticated_account_id=account)
            if not store.mixed_active():store.activate_mixed(account_id=account,authenticated_account_id=account)
            if not store.loss_active():store.activate_loss(account_id=account,authenticated_account_id=account,expected_revision=store.read_profile(account)['revision'],native_database_id=public['native_database_id'])
    with closing(sqlite3.connect(destination.as_uri()+'?mode=ro',uri=True)) as db:
        for table in ['p08b_reservation','p06t_reservation']:
            if db.execute(f'SELECT count(*) FROM {table} WHERE status=\'active\'').fetchone()[0]:raise ValueError('seed has unsettled reservations')
        profiles=[json.loads(db.execute('SELECT profile_json FROM game_profiles WHERE account_id=?',(account,)).fetchone()[0]) for account in accounts]
        for old,new in zip(baseline,profiles):
            if old['resources']!=new['resources']:raise ValueError('activation changed resources')
            loaded=lambda p:{(r['vehicle_inventory_id'],r['shell_definition_id']):r['count'] for r in p['ammunition']}
            if loaded(old)!=loaded(new):raise ValueError('activation granted/changed loaded ammunition')
            depot=old['ammunition_depot'];expanded=new['ammunition_depot']
            if any(expanded.get(k)!=v for k,v in depot.items()) or any(v!=0 for k,v in expanded.items() if k not in depot):raise ValueError('activation granted/changed depot ammunition')
        info=[{key:p[key] for key in ['account_id','native_database_id','username','created_at_ms']} for p in profiles]
        if db.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='p08c_late_result'").fetchone()[0]:
            if db.execute('SELECT count(*) FROM p08c_late_result').fetchone()[0]:raise ValueError('late results must not be preseeded')
    if sha(source)!=before:raise ValueError('readonly source DB bytes changed')
    result=dict(schema='p08c-late-composition-seed.v1',database=str(destination),profiles=info,bundle=str(no_links(seed['bundle'])),original=str(no_links(seed['original'])),
        source_seed=dict(path=str(source_seed),sha256=sha(source_seed)),source_database=dict(path=str(source),sha256=before),new_grants=0,
        new_reservations=0,new_results=0,native_client='NOT_RUN')
    with destination.with_suffix('.json').open('x',encoding='utf8') as out:json.dump(result,out,sort_keys=True,separators=(',',':'),ensure_ascii=False)
    print('PREPARED_REAL_TWO_OWNER_LOSS_SEED_NO_RESERVE_NO_NEW_GRANT')
if __name__=='__main__':main()
