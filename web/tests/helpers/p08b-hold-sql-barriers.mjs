/** Read-only independent SQL observations for the API5 composition.
 * Runtime authenticity comes from the compiled source/real HTTP producer;
 * these checks alone never turn authored rows into a World/native proof. */
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { createHash } from 'node:crypto';

export const POLICY='98cdc5d657e4cdf30225c26913f2c70a89865de9ae2bb97704fa4b623efd806e';
export const CONTRACT='p08b-owner-battle-hold.v1';
export const canonical=value=>JSON.stringify((function sort(v){return Array.isArray(v)?v.map(sort):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,sort(v[k])])):v;})(value));
export const sha=raw=>createHash('sha256').update(raw).digest('hex');
const json=raw=>{assert.equal(typeof raw,'string');assert.ok(Buffer.byteLength(raw)<=1024*1024);return JSON.parse(raw);};
const quoted=name=>'"'+name.replaceAll('"','""')+'"';
const identity=r=>`${r.account_id}:${r.reservation_id}`;
export function snapshot(path,accounts){
  const db=new DatabaseSync(path,{readOnly:true});
  try{
    db.exec('PRAGMA query_only=ON; BEGIN');
    const names=db.prepare("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").all().map(r=>r.name);
    assert.ok(names.length<=128);const rows={};
    for(const name of names){const values=db.prepare(`SELECT * FROM ${quoted(name)}`).all();assert.ok(values.length<=10000);rows[name]=values;}
    for(const name of['game_profiles','game_snapshot','game_vehicle','p09d_native_layout','p06t_reservation','battle_ammo_loss_reservation','battle_owner_hold_reservation','battle_owner_hold_owner'])assert.ok(names.includes(name),name);
    const profiles=accounts.map(account=>{
      const p=rows.game_profiles.filter(r=>r.account_id===account),a=rows.game_snapshot.filter(r=>r.account_id===account);assert.equal(p.length,1);assert.equal(a.length,1);
      const publicProfile=json(p[0].profile_json),aggregate=json(a[0].snapshot_json);assert.equal(publicProfile.account_id,account);assert.equal(aggregate.account_id,account);
      assert.equal(publicProfile.native_database_id,p[0].native_id);assert.equal(publicProfile.snapshot_revision,a[0].revision);
      assert.equal(sha(a[0].snapshot_json),a[0].snapshot_sha256);
      return {account_id:account,native_database_id:p[0].native_id,revision:a[0].revision,profile:publicProfile,aggregate};
    });
    const fingerprints=Object.fromEntries(names.map(n=>[n,{rows:rows[n].length,sha256:sha(canonical(rows[n].map(r=>canonical(r)).sort()))}]));
    db.exec('ROLLBACK');return {rows,profiles,fingerprints};
  }finally{if(db.isTransaction)db.exec('ROLLBACK');db.close();}
}
export function added(before,after,table){const old=new Set((before.rows[table]||[]).map(identity));return (after.rows[table]||[]).filter(r=>!old.has(identity(r)));}
export function active(s){return s.rows.p06t_reservation.filter(r=>r.status==='active');}
export function assertUnchanged(before,after,except=[]){
  assert.deepEqual(Object.keys(after.fingerprints),Object.keys(before.fingerprints));
  const skip=new Set(except);for(const name of Object.keys(before.fingerprints))if(!skip.has(name))assert.deepEqual(after.fingerprints[name],before.fingerprints[name],`Unexpected SQL mutation: ${name}`);
}
export function assertInventoryUnchanged(before,after){
  assert.equal(before.profiles.length,after.profiles.length);
  for(let i=0;i<before.profiles.length;i++){
    const a=before.profiles[i],b=after.profiles[i];assert.equal(a.account_id,b.account_id);assert.equal(a.native_database_id,b.native_database_id);
    for(const key of['resources','ammunition','ammunition_depot'])assert.deepEqual(b.profile[key],a.profile[key],`Actual inventory changed: ${key}`);
    for(const key of['depot','crew_inventory','research'])assert.deepEqual(b.aggregate[key],a.aggregate[key],`Actual aggregate changed: ${key}`);
  }
  for(const table of['p09c_ammo_mount','p09c_ammo_depot','p09d_native_layout','p04d_crew_member'])assert.deepEqual(after.fingerprints[table],before.fingerprints[table],`Source conservation: ${table}`);
}
export function assertReleasedResources(before,after){
  for(let i=0;i<before.profiles.length;i++){
    const a=before.profiles[i],b=after.profiles[i];assert.equal(a.account_id,b.account_id);assert.equal(a.native_database_id,b.native_database_id);
    assert.deepEqual(b.profile.resources,a.profile.resources);
    for(const key of['depot','crew_inventory','research'])assert.deepEqual(b.aggregate[key],a.aggregate[key],`Final changed unrelated inventory: ${key}`);
    assert.deepEqual(b.profile.ammunition_depot,a.profile.ammunition_depot,'Final changed warehouse ammunition');
  }
  for(const table of['p09c_ammo_depot','p04d_crew_member'])assert.deepEqual(after.fingerprints[table],before.fingerprints[table],`Final changed depot/crew: ${table}`);
}
export function assertAdmitted(initial,current,arena){
  const base=added(initial,current,'p06t_reservation'),side=added(initial,current,'battle_owner_hold_reservation');assert.equal(base.length,2);assert.equal(side.length,2);
  assert.equal(active(current).length,2);assert.ok(base.every(r=>r.status==='active'&&r.battle_id.endsWith(':'+arena)));
  const accounts=current.profiles.map(p=>p.account_id);assert.deepEqual(base.map(r=>r.account_id).sort(),[...accounts].sort());
  for(const r of side){assert.equal(r.result_json,null);assert.equal(r.result_sha256,null);assert.equal(sha(r.frozen_json),r.frozen_sha256);assert.equal(json(r.frozen_json).hold_policy_sha256,POLICY);}
  for(const account of accounts){const reserved=current.rows.game_vehicle.filter(r=>r.account_id===account&&r.state==='reserved');assert.equal(reserved.length,1);assert.ok(reserved[0].battle_id.endsWith(':'+arena));}
  for(let i=0;i<accounts.length;i++)assert.equal(current.profiles[i].revision,initial.profiles[i].revision+1);
  assertInventoryUnchanged(initial,current);
}
export function assertHeld(before,current){assertUnchanged(before,current);assert.equal(active(current).length,2);assert.ok(current.rows.battle_owner_hold_reservation.every(r=>r.result_json===null));}
export function assertHeldRelogin(before,current){
  assertUnchanged(before,current,['game_command_ledger','game_limits']);assert.equal(active(current).length,2);assertInventoryUnchanged(before,current);
  for(let i=0;i<before.profiles.length;i++)assert.equal(before.profiles[i].revision,current.profiles[i].revision);
  const old=new Set(before.rows.game_command_ledger.map(r=>`${r.account_id}:${r.command_id}`));
  const commands=current.rows.game_command_ledger.filter(r=>!old.has(`${r.account_id}:${r.command_id}`));
  assert.equal(commands.length,1,'Same-run re-login may only add its actual RunOpen command');
  assert.ok(commands[0].command_type.endsWith(':run_open'));assert.equal(commands[0].source_revision,commands[0].destination_revision);
  const journal=json(commands[0].result_json);assert.equal(journal.schema,'p08b-owner-battle-hold-store.v1');assert.equal(journal.request.operation,'run_open');
  const reply=journal.response;assert.equal(reply.version,5);assert.equal(reply.contract,CONTRACT);assert.equal(reply.status,'ready');assert.equal(reply.reservation.status,'active');
}
export function assertFinal(initial,current,arena,count,admission){
  const base=added(initial,current,'p06t_reservation'),side=added(initial,current,'battle_owner_hold_reservation');assert.equal(base.length,2);assert.equal(side.length,2);
  assert.equal(base.filter(r=>r.status==='finished').length,count);assert.equal(active(current).length,2-count);assertReleasedResources(initial,current);
  const final=side.filter(r=>r.result_json!==null);assert.equal(final.length,count);
  for(const r of final){
    assert.equal(sha(r.result_json),r.result_sha256);const t=json(r.result_json),b=base.find(b=>identity(b)===identity(r));assert.equal(b.status,'finished');
    assert.equal(t.reason,'battle_finished');assert.equal(t.finalization.kind,'outcome');assert.equal(t.source_link.account_id,r.account_id);assert.equal(t.source_link.reservation_id,r.reservation_id);
    assert.equal(t.source_link.frozen_sha256,r.frozen_sha256);assert.equal(t.source_link.battle_id,b.battle_id);assert.ok(b.battle_id.endsWith(':'+arena));
    const frozen=json(r.frozen_json).loss_frozen.loadout;assert.equal(t.source_link.native_database_id,current.profiles.find(p=>p.account_id===r.account_id).native_database_id);
    assert.equal(t.source_link.vehicle_kind,frozen.kind);assert.equal(t.source_link.native_inventory_id,frozen.native_inventory_id);
    for(let i=0;i<3;i++)assert.equal(t.remaining_ammunition[i].count+t.fired_ammunition[i].count+t.lost_ammunition[i].count,frozen.ammunition[i].count);
    assert.equal(t.credits,0);assert.equal(t.xp,0);
    if(admission){const source=admission.source_sessions.find(s=>s.account_id===r.account_id);assert.ok(source);assert.equal(t.source_link.source_session_id,source.session_id);assert.equal(t.source_link.actor_slot,source.actor_slot);}
  }
  if(count===2){
    assert.ok(current.rows.game_vehicle.every(r=>r.state==='available'&&r.battle_id===null));
    const results=current.rows.p06t_result.filter(r=>r.arena_id===arena);assert.equal(results.length,2);assert.deepEqual(results.map(r=>r.account_id).sort(),current.profiles.map(p=>p.account_id).sort());
    assert.equal(results[0].results_json,results[1].results_json,'All owners must receive the same immutable World outcome');
    // Preserve the full u64 as raw JSON text, never round it through Number.
    for(const r of results)assert.equal(/"arena_id"\s*:\s*([0-9]+)/.exec(r.results_json)?.[1],arena);
    assert.equal(final.filter(r=>json(r.result_json).departure?.reason==='manual_leave').length,1);
    for(let i=0;i<initial.profiles.length;i++)assert.equal(current.profiles[i].revision,initial.profiles[i].revision+2);
  }
}
