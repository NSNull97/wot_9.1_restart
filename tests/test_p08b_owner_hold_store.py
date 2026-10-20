import sys,unittest,json
from copy import deepcopy
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];sys.path[:0]=[str(HERE/'tests/helpers'),str(HERE/'tools'),str(HERE)]
from p08b_owner_hold_fixture import *
class Hold5Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.catalog=load_catalog(json.loads(SEED.read_bytes())['original'])
 def fixture(self,**kw):
  f=Fixture(self.catalog,**kw);self.addCleanup(f.close);return f
 def raises(self,code,call):
  with self.assertRaises(TransactionError)as e:call()
  self.assertEqual(e.exception.code,code)
 def test_active_inspect_projection_garage_refusal_then_final_and_ordinary_writes(self):
  f=self.fixture();f.admit_both();s=f.stores[0];a=f.accounts[0];before=f.dump();r=f.receipts[0]
  self.assertEqual(f.battle(0,'inspect')['reservation'],r);self.assertEqual(f.dump(),before)
  g=s.read_profile(a);self.assertEqual(next(v for v in g['vehicles']if v['vehicle_id']==r['vehicle_inventory_id'])['state'],'reserved');source=projection_source(f.seed['bundle'],f.catalog,f.database,a)
  files=OwnerHoldProjectionSource(PoolProjectionSource(source,s),s).fixture_files(f.public(0),g,s.layouts(a));c=json.loads(files['p08b-owner-hold.json'])
  self.assertEqual(c['state_sha256'],sha(files['state.bin']));self.assertEqual(c['native_layouts'][0]['shells_layout'],s.layouts(a)[1])
  ammo=[5,1,6,2570,0,2826,3,3082,10,6,0,0,0,0,0,0]
  for op,layout in [('service',ammo),('transfer',[1,0,-1])]:
   self.assertEqual(f.mutate(0,op,layout)[1]['status'],'rejected');self.assertEqual(f.dump(),before)
  ts=[f.final(0),f.final(1)];f.call(f.finish_request(0,ts[0],f.result(ts)));self.assertEqual(next(v for v in s.read_profile(a)['vehicles']if v['vehicle_id']==r['vehicle_inventory_id'])['state'],'available')
  depot=deepcopy(s.read_profile(a)['depot']);self.assertEqual(f.mutate(0,'service',ammo)[1]['status'],'serviced')
  self.assertEqual(s.read_profile(a)['depot']['shell:ms1-stock-heat'],depot['shell:ms1-stock-heat']+1)
  self.assertEqual(f.mutate(0,'transfer',[1,0,-1])[1]['status'],'transferred');self.assertEqual(f.mutate(0,'transfer',[1,0,1])[1]['status'],'transferred')
 def test_activation_quiescence_cas_native_ddl_failpoint_rollback(self):
  f=self.fixture(activate=False);before=f.dump()
  for kw,code in[({'old_sessions':1},'OWNER_HOLD_NOT_QUIESCENT'),({'pending_jobs':1},'OWNER_HOLD_NOT_QUIESCENT'),({'pending_returns':1},'OWNER_HOLD_NOT_QUIESCENT'),({'native_database_id':9},'FOREIGN_ACCOUNT'),({'expected_revision':99},'STALE_REVISION')]:
   self.raises(code,lambda:f.activate(0,**kw));self.assertEqual(f.dump(),before)
  for point in('after_hold_schema','before_hold_activation_commit'):
   f.stores[0].failpoint=point
   with self.assertRaises(TransactionError):f.activate(0)
   self.assertEqual(f.dump(),before)
  f.stores[0].failpoint=None;self.assertEqual(f.activate(0)['ammunition_granted'],0)
 def test_active_old_loss_cannot_upgrade(self):
  f=self.fixture(activate=False);s=f.stores[0]
  for op in('run_open','admit'):
   r=f.request(0,op);r.update(version=4,contract=LOSS_CONTRACT);AmmoLossStore.battle_loss(s,r,authenticated_account_id=f.accounts[0])
  before=f.dump();self.raises('VEHICLE_RESERVED',lambda:f.activate(0));self.assertEqual(f.dump(),before)
 def test_same_run_ready_and_restart_once_refund_no_fake_world(self):
  f=self.fixture();f.admit_both();s=f.stores[0];a=f.accounts[0];before=s.read_profile(a)
  ready=f.battle(0,'run_open');self.assertEqual(ready['revision'],before['revision']);self.assertEqual(ready['reservation'],f.receipts[0])
  r=f.request(0,'run_open',run_id='705c317c-2190-4db9-9b58-258bff3425b5');out=f.call(r);t=out['reservation']['result'];self.assertEqual(out['reservation']['status'],'aborted_restart');self.assertIsNone(t['terminal_hp']);self.assertIsNone(t['terminal_state']);self.assertEqual(t['finalization'],{'kind':'aborted_restart'})
  after=s.read_profile(a);self.assertEqual(after['ammunition'],before['ammunition']);self.assertEqual(after['depot'],before['depot']);self.assertTrue(f.call(r)['replayed']);self.assertEqual(s.read_profile(a),after)
  self.raises('RESERVATION_TERMINAL',lambda:f.call(f.vectors[1]['request']))
 def test_old_factories_and_old_public_api_fenced_before_after_final(self):
  from p06t_mixed_store import MixedAmmoStore
  from p04m_pool_store import PoolStore
  from p08c_battle_results import ResultsStore
  from p09e_research_store import ResearchStore
  from game_profile_tx import GameProfileStore
  f=self.fixture();f.admit_both();a=f.accounts[0]
  for phase in('held','released'):
   if phase=='released':f.call(f.finish_request(0,pristine=True))
   before=f.dump()
   for cls in(MixedAmmoStore,AmmoLossStore,PoolStore,ResultsStore,ResearchStore,GameProfileStore):
    old=f.open(a,cls)if cls in(MixedAmmoStore,AmmoLossStore)else cls(f.database,f.catalog,account_id=a)if cls is PoolStore else cls(f.database,f.catalog)if cls in(ResearchStore,ResultsStore)else cls(f.database)
    try:self.raises('AMMO_LOSS_POLICY_REQUIRED'if cls is MixedAmmoStore else'OWNER_HOLD_POLICY_REQUIRED',lambda:old.read_profile(a))
    finally:old.close()
   for method in('battle_loss','battle_mixed','reserve_vehicle'):
    self.raises('OWNER_HOLD_POLICY_REQUIRED',lambda:getattr(f.stores[0],method)({},authenticated_account_id=a))
   self.assertEqual(f.dump(),before)
 def test_unactivated_peer_still_uses_actual_old_loss_writer(self):
  f=self.fixture(activate=False);f.activate(0);old=f.open(f.accounts[1],AmmoLossStore);self.addCleanup(old.close)
  r=f.request(1,'run_open');r.update(version=4,contract=LOSS_CONTRACT);self.assertEqual(old.battle(r,authenticated_account_id=f.accounts[1])['status'],'ready')
 def test_admit_finish_atomic_failpoints_all_authorities(self):
  f=self.fixture();f.battle(0,'run_open');s=f.stores[0]
  for point in('after_hold_vehicle','after_hold_reservation','after_hold_ledger','before_hold_commit'):
   before=f.dump();s.failpoint=point
   with self.assertRaises(TransactionError):f.battle(0,'admit')
   self.assertEqual(f.dump(),before)
  s.failpoint=None;f.receipts=[f.battle(0,'admit')['reservation']];finish=f.finish_request(0,pristine=True)
  for point in('after_hold_terminal_metadata','after_ammo_loss_accounting','after_hold_ledger','before_hold_commit'):
   before=f.dump();s.failpoint=point
   with self.assertRaises(TransactionError):f.call(finish)
   self.assertEqual(f.dump(),before)
  s.failpoint=None;self.assertEqual(f.call(finish)['status'],'finished');self.assertTrue(f.call(finish)['replayed'])
 def test_source_link_departure_results_and_manual_finish_poison_atomic(self):
  f=self.fixture();f.admit_both();ts=[f.final(0),f.final(1)];r=f.finish_request(0,ts[0],f.result(ts));before=f.dump();qs=[]
  for key,v in [('account_id',f.accounts[1]),('native_database_id',4),('frozen_sha256','0'*64),('source_session_id',0),('actor_slot',1),('team',2),('vehicle_kind','is7')]:
   q=deepcopy(r);q['source_link'][key]=v;qs.append(q)
  q=deepcopy(r);q['departure']['tick']=1003;qs.append(q)
  q=deepcopy(r);q['reason']='manual_leave';qs.append(q)
  q=deepcopy(r);v=json.loads(q['results_json']);del v['interaction_details'];q['results_json']=canonical(v).decode('ascii');qs.append(q)
  for q in qs:
   with self.assertRaises(TransactionError):f.call(q)
   self.assertEqual(f.dump(),before)
 def test_cancel_must_pristine_actual_full_state(self):
  f=self.fixture();f.admit_both();before=f.dump()
  for change in('hp','device','crew','fire','roster'):
   t=f.final(0,0)
   if change=='hp':t['terminal_hp']-=1
   elif change=='device':t['terminal_state']['devices'][0]['health']-=1
   elif change=='crew':t['terminal_state']['crew'][0]['alive']=False
   elif change=='fire':t['terminal_state']['fire']['active']=True
   else:t['terminal_state']['roster_size']=2
   with self.assertRaises(TransactionError):f.call(f.finish_request(0,t,pristine=True))
   self.assertEqual(f.dump(),before)
 def test_query_ack_key_replay_and_reopen_finished(self):
  f=self.fixture();f.admit_both();ts=[f.final(0),f.final(1)];f.call(f.finish_request(0,ts[0],f.result(ts)));r,out=f.query(op='ack');self.assertEqual(out['record_contract'],'hold-v1');before=f.dump()
  self.assertTrue(f.stores[0].results_hold(r,authenticated_account_id=f.accounts[0])['replayed']);self.assertEqual(f.dump(),before)
  self.raises('DUPLICATE_PAYLOAD_MISMATCH',lambda:f.call(f.request(0,'admit',command_key=r['command_key'],battle_id=f.run+':2')));self.assertEqual(f.dump(),before)
  f.stores[0].close();f.stores[0]=f.open(f.accounts[0]);self.assertEqual(f.query()[1]['results_json'],out['results_json'])
 def test_inspect_ambient_transaction_kept(self):
  f=self.fixture();s=f.stores[0];r=f.request(0,'inspect');s.connection.execute('BEGIN');prior=s.connection.execute('PRAGMA query_only').fetchone()[0]
  self.raises('OWNER_HOLD_TRANSACTION_REQUIRED',lambda:f.call(r));self.assertTrue(s.connection.in_transaction);self.assertEqual(s.connection.execute('PRAGMA query_only').fetchone()[0],prior);s.connection.rollback()
 def test_actual_loss_archive_and_committed_late_history_keep_original_tags_after_activation(self):
  from p08c_late_results import CONTRACT as LATE,POLICY_NAME,canonical as utf8
  f=self.fixture(activate=False);old=[f.open(a,AmmoLossStore)for a in f.accounts]
  self.addCleanup(lambda:[s.close()for s in old]);vectors=[]
  def call(slot,op,**fields):
   r=f.request(slot,op,**fields);r.update(version=4,contract=LOSS_CONTRACT);out=old[slot].battle_loss(r,authenticated_account_id=f.accounts[slot]);vectors.append((r,out));return out
  for slot in range(2):call(slot,'run_open');f.receipts.append(call(slot,'admit')['reservation'])
  finals=[f.final(0),f.final(1)];results=f.result(finals)
  for slot in range(2):
   t=finals[slot];fields=dict(reservation_id=f.receipts[slot]['reservation_id'],reason='manual_leave'if slot==0 else'battle_finished',terminal_hp=90,remaining_ammunition=t['remaining_ammunition'],fired_ammunition=t['fired_ammunition'],lost_ammunition=t['lost_ammunition'],loss_event=None,terminal_state_json=canonical(t['terminal_state']).decode('ascii'))
   if slot:fields['results_json']=canonical(results).decode('ascii')
   call(slot,'finish',**fields)
  receipt=f.receipts[0];request=dict(version=1,contract=LATE,operation='release_stamp',account_id=f.accounts[0],native_database_id=f.public(0)['native_database_id'],command_key='hold5:old-stamp',run_id=f.run,battle_id=receipt['battle_id'],arena_id=f.arena,native_inventory_id=1,reservation_id=receipt['reservation_id'],source_contract='loss-v1',frozen_sha256=receipt['frozen_sha256'])
  helper=LateResults(f.stores[0]);stamp=helper.release_stamp(request,f.accounts[0])['release_stamp'];actors=[]
  for slot in range(2):
   r=f.receipts[slot];actors.append(dict(account_id=f.accounts[slot],native_database_id=f.public(slot)['native_database_id'],slot=slot,vehicle_id=vehicle_id(slot),team=slot+1,reservation_id=r['reservation_id'],native_inventory_id=1,source_contract='loss-v1',frozen_sha256=r['frozen_sha256'],final_actor=finals[slot]))
  seal=dict(version=1,policy=POLICY_NAME,run_id=f.run,battle_id=receipt['battle_id'],arena_id=f.arena,results_json=utf8(results).decode('utf8'),actors=actors)
  append=dict(request,operation='append',command_key='hold5:old-append',release_terminal_sha256=stamp['release_terminal_sha256'],finished_revision=stamp['finished_revision'],seal_json=utf8(seal).decode('utf8'))
  self.assertEqual(helper.append(append,f.accounts[0])['status'],'appended')
  oldrows={table:[tuple(r)for r in old[0].connection.execute('SELECT * FROM '+table)]for table in('p06t_reservation','battle_ammo_loss_reservation','p06t_result','p08c_late_seal','p08c_late_result','p08c_late_command','game_command_ledger')}
  f.activate(0);f.activate(1)
  for slot in range(2):
   _,found=f.query(slot);self.assertEqual(found['record_contract'],'loss-v1');self.assertEqual(json.loads(found['results_json']),results)
  for table,rows in oldrows.items():self.assertEqual([tuple(r)for r in old[0].connection.execute('SELECT * FROM '+table)],rows)
  _,acked=f.query(op='ack');self.assertTrue(acked['acked']);self.assertEqual(acked['record_contract'],'loss-v1')
  self.raises('OWNER_HOLD_POLICY_REQUIRED',lambda:LateResults(f.stores[0]).append(append,f.accounts[0]))
  self.raises('OWNER_HOLD_POLICY_REQUIRED',lambda:old[1].read_profile(f.accounts[1]))
  f.stores[0].close();f.stores[0]=f.open(f.accounts[0]);self.assertTrue(f.query()[1]['acked'])
 def test_real_ap1_and_mixed2_archives_survive_loss_then_hold_activation(self):
  from p06t_mixed_store import MixedAmmoStore
  f=self.fixture(activate=False,loss=False);a=f.accounts[0];old=f.open(a,MixedAmmoStore);self.addCleanup(old.close)
  f.mutate(0,'service',[5,1,6,2570,14,2826,0,3082,0,6,0,0,0,0,0,0])
  def call(version,op,**fields):
   r=f.request(0,op,**fields);r['version']=version;del r['contract'];return old.battle(r,authenticated_account_id=a)
  call(1,'run_open');ap=call(1,'admit')['reservation'];zeros=[{'count':0}]*3
  finals=[dict(terminal_hp=90,fired_ammunition=zeros)]*2;result=f.result(finals,departed=(False,False))
  call(1,'finish',reservation_id=ap['reservation_id'],remaining_ap=14,terminal_hp=90,reason='battle_finished',results_json=canonical(result).decode('ascii'))
  ap_arena=f.arena;aprow=[tuple(r)for r in old.connection.execute('SELECT * FROM p08c_result')]
  f.mutate(0,'service',[5,1,6,2570,0,2826,4,3082,10,6,0,0,0,0,0,0]);f.arena='9007199254740994';call(2,'run_open');mix=call(2,'admit')['reservation'];f.receipts=[mix];t=f.final(0);result=f.result([t,dict(terminal_hp=90,fired_ammunition=zeros)],departed=(False,False))
  call(2,'finish',reservation_id=mix['reservation_id'],remaining_ammunition=t['remaining_ammunition'],terminal_hp=90,reason='battle_finished',terminal_state_json=canonical(t['terminal_state']).decode('ascii'),results_json=canonical(result).decode('ascii'))
  mix_arena=f.arena;mixrow=[tuple(r)for r in old.connection.execute('SELECT * FROM p06t_result')]
  for slot,s in enumerate(f.stores):
   s.activate_loss(account_id=f.accounts[slot],authenticated_account_id=f.accounts[slot],expected_revision=s.read_profile(f.accounts[slot])['revision'],native_database_id=f.public(slot)['native_database_id']);f.activate(slot)
  for arena,tag in[(ap_arena,'ap-v1'),(mix_arena,'mixed-v2')]:
   f.arena=arena;self.assertEqual(f.query()[1]['record_contract'],tag)
  self.assertEqual([tuple(r)for r in old.connection.execute('SELECT * FROM p08c_result')],aprow);self.assertEqual([tuple(r)for r in old.connection.execute('SELECT * FROM p06t_result')],mixrow)
 def test_real_source_valid_owned3_factory_refuses_hold5_before_and_after_release(self):
  from p06t_owned_registry_v3 import NativeEncodingV2,Registry7,ForeignCrewCodec
  from p06t_owned_store_v3 import OwnedV3Store
  f=self.fixture();f.admit_both();enc=NativeEncodingV2.from_original(f.seed['original'],f.catalog);registry=Registry7(f.catalog,enc,SHELLS.read_bytes());codec=ForeignCrewCodec(f.seed['original'])
  v3=OwnedV3Store(f.database,f.catalog,account_id=f.accounts[0],registry=registry,encoding=enc,codec=codec,terminal_policy=ROOT/'server/gateway/src/shared/p06t_device_policy_v2.json');self.addCleanup(v3.connection.close)
  for phase in('held','released'):
   if phase=='released':f.call(f.finish_request(0,pristine=True))
   before=f.dump();self.raises('OWNER_HOLD_POLICY_REQUIRED',lambda:v3._owner())
   self.raises('OWNER_HOLD_POLICY_REQUIRED',lambda:v3.activate(authenticated_account_id=f.accounts[0],native_database_id=3,expected_revision=f.public(0)['snapshot_revision'],cache_generation='f082b977-01bd-46f7-9a7e-03ad51e396be',old_sessions=0,pending_jobs=0));self.assertEqual(f.dump(),before)
 def test_clean_environment_existing_cli_all_method_mode_and_old_mode_refusal(self):
  import subprocess,os
  f=self.fixture(activate=False);account=f.accounts[0];p=f.public(0);before=f.stores[0].read_profile(account)
  base=[sys.executable,'-B','-X','utf8',str(HERE/'tools/p08b_battle_service.py'),'--database',str(f.database),'--bundle',f.seed['bundle'],'--original-root',f.seed['original'],'--account-id',account,'--fixture-root',str(f.database.parent/'fixtures'),'--mixed-ammo','--shell-catalog',str(SHELLS),'--terminal-policy',str(TERMINAL),'--ammo-rack-loss'];env=dict(os.environ);env.pop('PYTHONPATH',None)
  def invoke(action,request=None,hold=True):
   return subprocess.run(base+(['--owner-battle-hold']if hold else[])+[action],input=b''if request is None else canonical(request),capture_output=True,cwd=f.database.parent,env=env,timeout=40)
  activation=dict(version=5,contract=CONTRACT,account_id=account,native_database_id=p['native_database_id'],expected_revision=before['revision'],policy_sha256=POLICY_SHA256,old_sessions=0,pending_jobs=0,pending_returns=0)
  actual=invoke('hold-activate',activation);self.assertEqual(actual.returncode,0,actual.stderr.decode('utf8'));self.assertEqual(json.loads(actual.stdout)['ammunition_granted'],0);self.assertEqual(f.stores[0].read_profile(account),before)
  old=invoke('fixture',hold=False);self.assertNotEqual(old.returncode,0);self.assertIn(b'OWNER_HOLD_POLICY_REQUIRED',old.stderr)
  good=invoke('fixture');self.assertEqual(good.returncode,0,good.stderr.decode('utf8'));out=json.loads(good.stdout);directory=Path(out['fixture_dir']);self.assertEqual(directory.relative_to(f.database.parent/'fixtures').parts[:3],('p08b-hold-v1','p08b-v1',account));comp=json.loads((directory/'p08b-owner-hold.json').read_bytes());self.assertEqual(comp['state_sha256'],sha((directory/'state.bin').read_bytes()))
  request=f.request(0,'inspect');actual=invoke('battle',request);self.assertEqual(actual.returncode,0,actual.stderr.decode('utf8'));self.assertEqual(json.loads(actual.stdout)['status'],'inspected');self.assertEqual(f.stores[0].read_profile(account),before)
 def test_post_departure_actual_final_loss_receipt_loses_loaded_only_and_is_not_shots(self):
  f=self.fixture();f.admit_both();before=[s.read_profile(a)for s,a in zip(f.stores,f.accounts)];self.assertEqual(f.battle(0,'inspect')['reservation']['status'],'active')
  ts=[f.final(0),f.final(1)];a,b=ts;a['terminal_hp']=0;a['lost_ammunition']=deepcopy(a['remaining_ammunition']);a['remaining_ammunition']=[dict(r,count=0)for r in a['remaining_ammunition']]
  next(r for r in a['terminal_state']['devices']if r['extra_index']==27)['health']=0;a['terminal_state']['death']=dict(reason=0,killer_slot=1,tick=1002);a['loss_event']=dict(shot=1,attacker_slot=1,target_slot=0,tick=1002,device_sequence=1)
  b['fired_ammunition'][2]['count']=1;b['remaining_ammunition'][2]['count']-=1;results=f.result(ts);pa,pb=results['participants'];pa.update(death_reason=0,killer_id=pb['vehicle_id']);pb.update(direct_hits=1,piercings=1,damage_dealt=90,kills=1)
  results['interaction_details']['rows'][1]['targets']=[dict(vehicle_id=pa['vehicle_id'],spotted=0,death_reason=0,direct_hits=1,explosion_hits=0,piercings=1,damage_dealt=90,damage_assisted_track=0,damage_assisted_radio=0,crits=0,fire=0)]
  for slot,t in enumerate(ts):
   r=f.finish_request(slot,t,results,depart=slot==0);out=f.call(r);terminal=out['reservation']['result'];self.assertEqual(sum(x['count']for x in terminal['fired_ammunition']),results['participants'][slot]['shots']);self.assertTrue(f.call(r)['replayed'])
  for slot,(store,owner)in enumerate(zip(f.stores,f.accounts)):
   after=store.read_profile(owner);self.assertEqual(after['depot'],before[slot]['depot']);loaded=next(r for r in after['ammunition']if r['vehicle_id']==f.receipts[slot]['vehicle_inventory_id'])['loaded'];self.assertEqual(sum(loaded.values()),0 if slot==0 else 13)
  f.battle(0,'run_open',run_id='583d1844-c3eb-4127-a3a3-f2b8037c18ec');self.assertEqual(sum(next(r for r in f.stores[0].read_profile(f.accounts[0])['ammunition']if r['vehicle_id']==f.receipts[0]['vehicle_inventory_id'])['loaded'].values()),0)
 def test_contained_failure_loss_target_must_equal_original_source_link_actor(self):
  f=self.fixture();f.admit_both();t=f.final(0,3);t['terminal_hp']=0;t['lost_ammunition']=deepcopy(t['remaining_ammunition']);t['remaining_ammunition']=[dict(r,count=0)for r in t['remaining_ammunition']]
  next(r for r in t['terminal_state']['devices']if r['extra_index']==27)['health']=0;t['terminal_state']['death']=dict(reason=0,killer_slot=2,tick=1002);t['loss_event']=dict(shot=1,attacker_slot=2,target_slot=1,tick=1002,device_sequence=1)
  before=f.dump();self.raises('INVALID_SOURCE_LINK',lambda:f.call(f.finish_request(0,t)));self.assertEqual(f.dump(),before)
  t['loss_event']['target_slot']=0;self.assertEqual(f.call(f.finish_request(0,t))['status'],'finished')
if __name__=='__main__':unittest.main()
