"""Disposable actual C/D SQL only; final World facts in these tests are authored."""
from contextlib import closing
from copy import deepcopy
import hashlib,json,sqlite3,sys,tempfile,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];HERE=ROOT
sys.path[:0]=[str(ROOT/'tools'),str(ROOT)]
from p08b_owner_hold_store import *
from p09e_research_catalog import load_catalog
from p08b_owner_source import projection_source
from p04m_pool_projection import PoolProjectionSource
SEED=Path(os.environ['P08B_OWNER_HOLD_SEED']).resolve(strict=True)
RUN='e6ef9b6e-1316-4d78-9f6a-18659b03b231';ARENA='9007199254740993'
SHELLS=ROOT/'tests/fixtures/p06t-shell-catalog.json';TERMINAL=ROOT/'tests/fixtures/p06t-device-policy.json'
class Fixture:
 def __init__(self,catalog=None,database=None,activate=True,loss=True):
  self.temp=tempfile.TemporaryDirectory(prefix='wot-hold5-')if database is None else None
  self.database=Path(self.temp.name)/'game.sqlite'if database is None else Path(database)
  assert not self.database.exists();self.seed=json.loads(SEED.read_bytes());self.seedpath=Path(self.seed['database']);self.seedsha=sha(self.seedpath.read_bytes());assert self.seedsha==self.seed['database_sha256']
  with closing(sqlite3.connect(self.seedpath.resolve().as_uri()+'?mode=ro',uri=True))as src,closing(sqlite3.connect(self.database))as out:src.backup(out)
  self.catalog=catalog or load_catalog(self.seed['original']);self.accounts=[p['account_id']for p in self.seed['profiles']];self.serial=0;self.vectors=[];self.receipts=[];self.stores=[];self.run=RUN;self.arena=ARENA
  for slot,a in enumerate(self.accounts):
   s=self.open(a);self.stores.append(s);p=self.public(slot)
   if loss and not s.loss_active():s.activate_loss(account_id=a,authenticated_account_id=a,native_database_id=p['native_database_id'],expected_revision=s.read_profile(a)['revision'])
   if activate:self.activate(slot)
 def open(self,a,cls=OwnerHoldStore):return cls(self.database,self.catalog,account_id=a,shell_catalog=SHELLS,terminal_policy=TERMINAL)
 def close(self):
  for s in self.stores:s.close()
  assert sha(self.seedpath.read_bytes())==self.seedsha
  if self.temp:self.temp.cleanup()
 def public(self,slot):
  s=self.stores[slot];return s._project_profile(self.accounts[slot],s.read_profile(self.accounts[slot]))
 def activate(self,slot,**changes):
  s=self.stores[slot];a=self.accounts[slot];r=dict(authenticated_account_id=a,native_database_id=self.public(slot)['native_database_id'],expected_revision=s.read_profile(a)['revision'],old_sessions=0,pending_jobs=0,pending_returns=0);r.update(changes);return s.activate_hold(**r)
 def request(self,slot,op,**changes):
  self.serial+=1;s=self.stores[slot];a=self.accounts[slot];p=self.public(slot)
  r=dict(version=5,contract=CONTRACT,operation=op,account_id=a,native_database_id=p['native_database_id'],command_key='hold5:cmd:'+str(self.serial),expected_revision=s.read_profile(a)['revision'],run_id=self.run)
  if op in('admit','finish'):r.update(battle_id=self.run+':'+self.arena,native_inventory_id=1)
  r.update(changes);return r
 def call(self,r):
  s=self.stores[self.accounts.index(r['account_id'])];reply=s.battle_hold(r,authenticated_account_id=r['account_id']);self.vectors.append(dict(request=deepcopy(r),response=deepcopy(reply)));return reply
 def battle(self,slot,op,**changes):return self.call(self.request(slot,op,**changes))
 def admit_both(self):
  for slot in range(2):self.battle(slot,'run_open');self.receipts.append(self.battle(slot,'admit')['reservation'])
 def final(self,slot,roster=2):
  wrapper=self.receipts[slot]['frozen'];frozen=wrapper['loss_frozen']['loadout']if 'loss_frozen'in wrapper else wrapper['loadout']if 'loadout'in wrapper else wrapper;policy=self.stores[slot].terminal_policy.document;source=policy['profiles'][frozen['kind']]
  state=dict(policy_revision=policy['policy_revision'],roster_size=roster,crew_active=True,crew=[dict(crew_id=i,alive=True)for i in frozen['crew_ids']],devices=[dict(r,health=r['max_health'])for r in source['devices']],fire=dict(active=False,ticks=0,damage=0),death=dict(reason=-1,killer_slot=None,tick=0))
  ammo=[dict(shell_compact_id=r['shell_compact_id'],count=r['count'])for r in frozen['ammunition']];zeros=[dict(r,count=0)for r in ammo]
  return dict(terminal_hp=frozen['max_hp'],terminal_state=state,remaining_ammunition=ammo,fired_ammunition=zeros,lost_ammunition=deepcopy(zeros),loss_event=None)
 def result(self,finals,departed=(True,False)):
  ps=[]
  for slot,t in enumerate(finals):
   p=self.public(slot);ps.append(dict(vehicle_id=vehicle_id(slot),account_dbid=p['native_database_id'],name=p['username'],team=slot+1,type_compact_descr=3329,health=t['terminal_hp'],shots=sum(r['count']for r in t['fired_ammunition']),direct_hits=0,piercings=0,damage_dealt=0,damage_received=90-t['terminal_hp'],kills=0,capture_points=0,dropped_capture_points=0,mileage_metres=0,life_time=0,killer_id=0,death_reason=-1,premature_leave=departed[slot]))
  return dict(arena_id=int(self.arena),arena_type_id=4,created_unix=1792080000,winner_team=2,finish_reason=5,duration_seconds=0,participants=ps,interaction_details=dict(version=1,policy='test_lab.authoritative-interactions.v1',spotting_policy=None,rows=[dict(attacker_vehicle_id=p['vehicle_id'],targets=[])for p in ps]))
 def finish_request(self,slot,final=None,outcome=None,pristine=False,depart=True):
  t=deepcopy(final or self.final(slot,0 if pristine else 2));r=self.receipts[slot]
  link=None if pristine else dict(account_id=self.accounts[slot],native_database_id=self.public(slot)['native_database_id'],run_id=r['run_id'],battle_id=r['battle_id'],reservation_id=r['reservation_id'],native_inventory_id=r['native_inventory_id'],vehicle_inventory_id=r['vehicle_inventory_id'],frozen_sha256=r['frozen_sha256'],source_session_id=11+slot,actor_slot=slot,team=slot+1,vehicle_kind=r['frozen']['loss_frozen']['loadout']['kind'])
  fields=dict(reservation_id=r['reservation_id'],terminal_hp=t['terminal_hp'],terminal_state_json=canonical(t['terminal_state']).decode('ascii'),remaining_ammunition=t['remaining_ammunition'],fired_ammunition=t['fired_ammunition'],lost_ammunition=t['lost_ammunition'],loss_event=t['loss_event'],reason='cancelled'if pristine else'battle_finished'if outcome else'battle_failure',source_link=link,departure=None if pristine or not depart else dict(reason='manual_leave',tick=1001),finalization=dict(kind='pristine_cancel')if pristine else dict(kind='outcome'if outcome else'contained_failure',tick=1002))
  if outcome:fields['results_json']=canonical(outcome).decode('ascii')
  return self.request(slot,'finish',**fields)
 def query(self,slot=0,op='query',**changes):
  self.serial+=1;r=dict(version=5,contract=CONTRACT,operation=op,account_id=self.accounts[slot],native_database_id=self.public(slot)['native_database_id'],command_key='hold5:result:'+str(self.serial),arena_id=self.arena);r.update(changes)
  out=self.stores[slot].results_hold(r,authenticated_account_id=self.accounts[slot]);self.vectors.append(dict(request=r,response=out));return r,out
 def mutate(self,slot,operation,layout):
  s=self.stores[slot];p=self.public(slot);self.serial+=1;r=dict(account_id=self.accounts[slot],native_database_id=p['native_database_id'],expected_revision=s.read_profile(self.accounts[slot])['revision'],wire_revision=1,command_key='hold5:garage:'+str(self.serial),layout=layout)
  from p09e_research_service import existing_service
  return r,existing_service(s,operation,r,authenticated_account_id=self.accounts[slot])
 def dump(self):return '\n'.join(self.stores[0].connection.iterdump())
