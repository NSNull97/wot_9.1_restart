"""Fresh C/D source backup and explicit API5 activation; no run/admit/results.

This file targets tracked tests/helpers after promotion. It deliberately cannot
fall back to an ignored writer module or a caller-supplied source database.
"""
from contextlib import closing
from pathlib import Path
import hashlib
import json
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
SOURCE = ROOT / 'local/night-staging/20261016/p10b-selection-http01/seed01/seed.json'
SOURCE_DB_SHA = 'a04216d90e8e9e8b379fc2d34a0fed9f400e373d8d4c591d723bb00a1accc2cf'


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def plain(value,existing=True):
    path=Path(value)
    if not path.is_absolute() or '..' in path.parts:raise ValueError('absolute lexical path required')
    for p in (path,*path.parents):
        if p.exists() and (p.is_symlink() or p.is_junction()):raise ValueError('links refused')
    return path.resolve(strict=existing)


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('ascii')


def main():
    if len(sys.argv)!=3:raise ValueError('fresh destination and exact source metadata required')
    destination=plain(sys.argv[1],False);seed_path=plain(sys.argv[2]);expected=plain(SOURCE)
    if seed_path!=expected:raise ValueError('closed actual C/D source required')
    base=plain(ROOT/'local/test-runs/p08b-owner-hold-composition10')
    part=destination.relative_to(base)
    if len(part.parts)!=2 or not part.parts[0].startswith('run-') or part.parts[1]!='game.sqlite' or destination.exists():raise ValueError('fresh regular composition destination required')
    raw=seed_path.read_bytes()
    if len(raw)>65536:raise ValueError('bounded source metadata required')
    seed=json.loads(raw);source=plain(seed['database'])
    if source.parent!=seed_path.parent or sha(source)!=SOURCE_DB_SHA or seed['database_sha256']!=SOURCE_DB_SHA:raise ValueError('actual preserved source pin mismatch')
    accounts=[p['account_id'] for p in seed['profiles']]
    if accounts!=['80ad3bc2-476e-4fbd-899d-a4679ea167d2','633ad84f-f33f-4aab-bacd-421f31a93bae']:raise ValueError('exact existing C/D order required')
    with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True))as old,closing(sqlite3.connect(destination))as new:old.backup(new)
    def public(db,a):return json.loads(db.execute('SELECT profile_json FROM game_profiles WHERE account_id=?',(a,)).fetchone()[0])
    with closing(sqlite3.connect(destination.as_uri()+'?mode=ro',uri=True))as db:
        before=[public(db,a) for a in accounts]
        for table in ('p08b_reservation','p06t_reservation'):
            if db.execute('SELECT count(*) FROM '+table+" WHERE status='active'").fetchone()[0]:raise ValueError('source contains unfinished reservation')
    from p08b_owner_hold_store import OwnerHoldStore
    from p09e_research_catalog import load_catalog
    catalog=load_catalog(seed['original'])
    for a in accounts:
        with OwnerHoldStore(destination,catalog,account_id=a,shell_catalog=ROOT/'tests/fixtures/p06t-shell-catalog.json',terminal_policy=ROOT/'tests/fixtures/p06t-device-policy.json')as store:
            p=store._project_profile(a,store.read_profile(a))
            if not store.loss_active():store.activate_loss(account_id=a,authenticated_account_id=a,native_database_id=p['native_database_id'],expected_revision=store.read_profile(a)['revision'])
            if store.hold_active():raise ValueError('source already activated5; fresh predecessor required')
            store.activate_hold(authenticated_account_id=a,native_database_id=p['native_database_id'],expected_revision=store.read_profile(a)['revision'],old_sessions=0,pending_jobs=0,pending_returns=0)
    with closing(sqlite3.connect(destination.as_uri()+'?mode=ro',uri=True))as db:
        after=[public(db,a)for a in accounts]
        for old,new in zip(before,after):
            for key in ('account_id','native_database_id','snapshot_revision','resources','ammunition','ammunition_depot'):
                if old[key]!=new[key]:raise ValueError('activation changed actual inventory/identity/revision')
        if db.execute('SELECT count(*) FROM battle_owner_hold_reservation').fetchone()[0]or db.execute('SELECT count(*) FROM battle_owner_hold_command').fetchone()[0]:raise ValueError('seed must not contain Hold5 commands/results')
        info=[{k:p[k]for k in ('account_id','native_database_id','username','created_at_ms','snapshot_revision')}for p in after]
    if sha(source)!=SOURCE_DB_SHA or seed_path.read_bytes()!=raw:raise ValueError('readonly source changed')
    result=dict(schema='p08b-owner-hold-composition-seed.v1',database=str(destination),profiles=info,bundle=str(plain(seed['bundle'])),original=str(plain(seed['original'])),
        source_seed=dict(path=str(seed_path),sha256=hashlib.sha256(raw).hexdigest()),source_database=dict(path=str(source),sha256=SOURCE_DB_SHA),
        new_grants=0,new_accounts=0,new_reservations=0,new_results=0,source_unchanged=True,native_client='NOT_RUN')
    with destination.with_suffix('.json').open('xb')as out:out.write(canonical(result)+b'\n')
    print('PREPARED_ACTUAL_C_D_HOLD5_NO_RUN_NO_RESERVATION_NO_NEW_GRANT')


if __name__=='__main__':main()
