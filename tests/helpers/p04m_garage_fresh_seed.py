"""Composition39 only: actual C/D backup + Loss4 metadata activation.
No RunOpen/mutation/grant/reserve/result authored. Invoked only by promoted test.
"""
from pathlib import Path
from contextlib import closing
import hashlib,json,sqlite3,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tests/helpers'),str(ROOT/'tools'),str(ROOT)]
from p04m_garage_fresh_source import context_seed,plain,digest,parse

def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('ascii')
def main():
 if len(sys.argv)!=4 or sys.argv[3]not in('loss4','hold5'):raise ValueError('exact destination,context seed and closed loss4/hold5 mode required')
 hold5=sys.argv[3]=='hold5'
 if ROOT not in (Path('C:/wot091-night-20261017-01/w'),Path('D:/WoT_9.1_Server')):raise ValueError('composition39 requires a verified C or D workspace')
 seed,context=context_seed(1,ROOT)
 if plain(sys.argv[2])!=plain(context['path']):raise ValueError('closed C/D source path')
 destination=Path(sys.argv[1]);parent=plain(destination.parent);base=plain(ROOT/'local/test-runs'/('p04m-garage-hold5-fresh39'if hold5 else'p04m-garage-fresh39'))
 relative=parent.relative_to(base)
 if len(relative.parts)!=1 or not relative.parts[0].startswith('run-')or destination.name!='game.sqlite'or destination.exists():raise ValueError('fresh closed output')
 destination=parent/'game.sqlite';source=plain(seed['database']);source_sha=digest(source.read_bytes())
 with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True,timeout=3))as old,closing(sqlite3.connect(destination))as new:
  old.execute('PRAGMA query_only=ON');old.backup(new)
 accounts=[p['account_id']for p in seed['profiles']]
 if accounts!=['80ad3bc2-476e-4fbd-899d-a4679ea167d2','633ad84f-f33f-4aab-bacd-421f31a93bae']:raise ValueError('exact source C/D owner order')
 def profiles():
  with closing(sqlite3.connect(destination.as_uri()+'?mode=ro',uri=True,timeout=3))as db:
   db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
   out=[json.loads(db.execute('SELECT profile_json FROM game_profiles WHERE account_id=?',(a,)).fetchone()[0])for a in accounts]
   for table in('p08b_reservation','p06t_reservation'):
    if db.execute('SELECT COUNT(*)FROM '+table+" WHERE status='active'").fetchone()[0]:raise ValueError('source active reserve')
   db.rollback();return out
 before=profiles()
 from p06t_ammo_loss_store import AmmoLossStore
 from p09e_research_catalog import load_catalog
 catalog=load_catalog(seed['original'])
 for a in accounts:
  with AmmoLossStore(destination,catalog,account_id=a,shell_catalog=ROOT/'tests/fixtures/p06t-shell-catalog.json',terminal_policy=ROOT/'tests/fixtures/p06t-device-policy.json')as store:
   if not store.loss_active():
    profile=store._project_profile(a,store.read_profile(a));store.activate_loss(account_id=a,authenticated_account_id=a,native_database_id=profile['native_database_id'],expected_revision=store.read_profile(a)['revision'])
 if hold5:
  from p08b_owner_hold_store import OwnerHoldStore
  for a in accounts:
   with OwnerHoldStore(destination,catalog,account_id=a,shell_catalog=ROOT/'tests/fixtures/p06t-shell-catalog.json',terminal_policy=ROOT/'tests/fixtures/p06t-device-policy.json')as store:
    aggregate=store.read_profile(a);profile=store._project_profile(a,aggregate)
    reply=store.activate_hold(authenticated_account_id=a,native_database_id=profile['native_database_id'],expected_revision=aggregate['revision'],old_sessions=0,pending_jobs=0,pending_returns=0)
    if reply.get('status')!='active'or reply.get('ammunition_granted')!=0:raise ValueError('actual metadata-only Hold5 activation required')
 after=profiles()
 for old,new in zip(before,after):
  for key in('account_id','native_database_id','snapshot_revision','resources','ammunition','ammunition_depot','crew'):
   if old[key]!=new[key]:raise ValueError('activation mutated source inventory/cursor')
 if digest(source.read_bytes())!=source_sha:raise ValueError('source DB changed')
 result=dict(schema='p04m-garage-hold5-fresh39-seed.v1'if hold5 else'p04m-garage-fresh39-seed.v1',database=str(destination),bundle=seed['bundle'],original=seed['original'],profiles=[{k:v[k]for k in('account_id','native_database_id','username','created_at_ms','snapshot_revision')}for v in after],context_seed=context,source_database=dict(path=str(source),sha256=source_sha),new_grants=0,new_accounts=0,new_reservations=0,new_results=0,writer_version=5 if hold5 else 4,hold_activation='ACTUAL_METADATA_ONLY'if hold5 else'NOT_RUN',run_open='NOT_RUN_BY_SEED',source_unchanged=True)
 with destination.with_suffix('.json').open('xb')as f:f.write(canonical(result)+b'\n')
 print('PREPARED_GENUINE_SOURCE_C_D_HOLD5_NO_RUN_GRANT_OR_RESERVATION'if hold5 else'PREPARED_GENUINE_SOURCE_C_D_LOSS4_NO_RUN_GRANT_OR_RESERVATION')
if __name__=='__main__':main()
