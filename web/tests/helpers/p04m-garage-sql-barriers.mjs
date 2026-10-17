/** Independent read-only SQL barriers. No DB mutation helper is exported. */
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {createHash} from 'node:crypto';
export const canonical=v=>JSON.stringify((function sort(x){return Array.isArray(x)?x.map(sort):x&&typeof x==='object'?Object.fromEntries(Object.keys(x).sort().map(k=>[k,sort(x[k])])):x;})(v));
export const sha=v=>createHash('sha256').update(v).digest('hex');
export function snapshot(path,accounts){
 const d=new DatabaseSync(path,{readOnly:true});try{
  d.exec('PRAGMA query_only=ON;BEGIN');const names=d.prepare("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").all().map(r=>r.name);assert.ok(names.length<=256);const rows={};
  for(const n of names){assert.match(n,/^[A-Za-z_][A-Za-z0-9_]*$/);rows[n]=d.prepare(`SELECT * FROM "${n}"`).all();assert.ok(rows[n].length<=100000);}
  const fingerprints=Object.fromEntries(names.map(n=>[n,sha(canonical(rows[n].map(canonical).sort()))]));
  const profiles=accounts.map(a=>{const rs=rows.game_snapshot.filter(r=>r.account_id===a),ps=rows.game_profiles.filter(r=>r.account_id===a);assert.equal(rs.length,1);assert.equal(ps.length,1);assert.equal(sha(rs[0].snapshot_json),rs[0].snapshot_sha256);const p=JSON.parse(ps[0].profile_json);assert.equal(p.snapshot_revision,rs[0].revision);assert.equal(p.native_database_id,ps[0].native_id);const aggregate=JSON.parse(rs[0].snapshot_json);assert.equal(aggregate.account_id,a);assert.equal(aggregate.revision,rs[0].revision);assert.equal(p.account_id,a);return{account_id:a,native_database_id:ps[0].native_id,revision:rs[0].revision,profile:p,aggregate};});
  d.exec('ROLLBACK');return{rows,fingerprints,profiles};
 }finally{if(d.isTransaction)d.exec('ROLLBACK');d.close();}
}
export function unchanged(a,b,except=[]){assert.deepEqual(Object.keys(a.fingerprints),Object.keys(b.fingerprints));for(const n of Object.keys(a.fingerprints))if(!except.includes(n))assert.equal(b.fingerprints[n],a.fingerprints[n],`Unexpected SQL change ${n}`);}
export function noReservations(s){for(const n of['p08b_reservation','p06t_reservation'])assert.ok(s.rows[n].every(r=>r.status!=='active'));if(s.rows.battle_owner_hold_reservation)assert.equal(s.rows.battle_owner_hold_reservation.length,0,'No hold reserve may be manufactured by idle garage');}
export function ammoCommands(s,owner){return s.rows.game_command_ledger.filter(r=>r.account_id===owner&&/^p04m:[0-9a-f]{32}:90[12]$/.test(r.command_id));}
export function mutation(initial,current,count){
 const owner=initial.profiles[0].account_id,other=initial.profiles[1].account_id;noReservations(current);assert.equal(current.profiles[0].revision,initial.profiles[0].revision+count);assert.deepEqual(current.profiles[1],initial.profiles[1]);
 const commands=ammoCommands(current,owner);assert.equal(commands.length,count,'No SQL retry for Fresh/output pressure');commands.sort((a,b)=>a.source_revision-b.source_revision);
 for(let i=0;i<count;i++){
  const r=commands[i];assert.equal(r.source_revision,initial.profiles[0].revision+i);assert.equal(r.destination_revision,r.source_revision+1);assert.equal(r.command_id.split(':').at(-1),String(901+i));
  const native=current.rows.p09d_native_command.filter(n=>n.account_id===owner&&n.command_id===r.command_id);assert.equal(native.length,1);assert.equal(sha(native[0].response_json),native[0].response_sha256);const response=JSON.parse(native[0].response_json);
  assert.equal(response.status,'serviced');assert.equal(response.revision,r.destination_revision);assert.equal(response.wire_revision,2+i);assert.equal(response.command_key,r.command_id);assert.equal(response.replayed,false);assert.equal(response.result_code,0);
 }
 if(count===2)assert.equal(commands[0].command_id.slice(0,-3),commands[1].command_id.slice(0,-3),'No native epoch/key-prefix reset');
 for(const key of['resources','crew','statistics','research'])assert.deepEqual(current.profiles[0].profile[key],initial.profiles[0].profile[key],key);
 const before=initial.profiles[0].profile,after=current.profiles[0].profile;const heat='shell:ms1-stock-heat';const loaded=p=>p.ammunition.find(r=>r.shell_definition_id===heat&&r.vehicle_inventory_id.endsWith(':starter-vehicle-v1')).count;
 assert.equal(loaded(before),4);assert.equal(loaded(after),count===1?3:4);assert.equal(after.ammunition_depot[heat],before.ammunition_depot[heat]+(count===1?1:0));
 for(const shell of Object.keys(before.ammunition_depot))if(shell!==heat)assert.equal(after.ammunition_depot[shell],before.ammunition_depot[shell]);
 for(const table of['p04d_crew_member','p06t_reservation','battle_ammo_loss_reservation','p06t_result'])assert.equal(current.fingerprints[table],initial.fingerprints[table],table);
 for(const table of['battle_owner_hold_schema','battle_owner_hold_owner','battle_owner_hold_reservation','battle_owner_hold_command'])if(Object.hasOwn(initial.fingerprints,table))assert.equal(current.fingerprints[table],initial.fingerprints[table],'Idle ammo must preserve hold metadata '+table);
 assert.equal(ammoCommands(current,other).length,0);return commands;
}
export function nativeUpdate(committed,summary,index){
 const owner=committed.profiles[0].account_id,r=ammoCommands(committed,owner).find(r=>r.command_id.endsWith(':'+String(901+index)));assert.ok(r);const n=committed.rows.p09d_native_command.find(n=>n.account_id===owner&&n.command_id===r.command_id);const reply=JSON.parse(n.response_json);
 assert.equal(summary.native.update_method,0x57);assert.equal(summary.native.update_hex,reply.update_hex);assert.equal(summary.native.callback_after_update,true);assert.equal(summary.native.bodies,2);
 assert.equal(summary.session.revision,reply.revision);assert.equal(summary.session.pool_revision,reply.revision);assert.equal(summary.session.profile13_revision,reply.revision);assert.equal(summary.session.wire_revision,reply.wire_revision);assert.equal(summary.session.phase,'Account');
}

/** Authentication may open one current run/cursor, never grant or reshape owned data. */
export function authenticated(before,after,version=4){
 assert.ok(version===4||version===5);
 assert.equal(before.profiles.length,2);assert.equal(after.profiles.length,2);noReservations(before);noReservations(after);
 unchanged(before,after,['game_profiles','game_snapshot','p08b_run','game_command_ledger','game_limits']);
 // Raw storage fingerprints cover the grant/import rows as well as inventory.
 for(const table of['p09d_import','p09c_ammo_mount','p09c_ammo_depot','p09d_native_layout','p04d_crew_member','game_vehicle'])assert.equal(typeof before.fingerprints[table],'string',table+' source evidence required');
 for(let i=0;i<2;i++){
  const a=before.profiles[i],b=after.profiles[i];assert.equal(a.account_id,b.account_id);assert.equal(a.native_database_id,b.native_database_id);assert.equal(b.revision,a.revision+(i===0?1:0));
  const omit=(v,key)=>Object.fromEntries(Object.entries(v).filter(([k])=>k!==key));
  assert.deepEqual(omit(b.profile,'snapshot_revision'),omit(a.profile,'snapshot_revision'),'Auth changed public owned data');
  assert.deepEqual(omit(b.aggregate,'revision'),omit(a.aggregate,'revision'),'Auth changed authoritative owned data');
 }
 const identity=r=>r.account_id+'|'+r.command_id,old=new Map(before.rows.game_command_ledger.map(r=>[identity(r),canonical(r)]));
 for(const row of before.rows.game_command_ledger)assert.equal(canonical(after.rows.game_command_ledger.find(r=>identity(r)===identity(row))),canonical(row),'Auth rewrote old raw journal');
 const added=after.rows.game_command_ledger.filter(r=>!old.has(identity(r)));assert.equal(added.length,1,'Auth may add one actual RunOpen only');const r=added[0];
 assert.equal(r.account_id,before.profiles[0].account_id);assert.equal(r.source_revision,before.profiles[0].revision);assert.equal(r.destination_revision,r.source_revision+1);assert.ok(r.command_id.startsWith('open:'));
 const journal=JSON.parse(r.result_json);assert.equal(journal.request.version,version);assert.equal(journal.request.contract,version===5?'p08b-owner-battle-hold.v1':'p06t-ammo-rack-loss.v1');assert.equal(journal.request.operation,'run_open');assert.equal(journal.request.account_id,r.account_id);assert.equal(journal.response.status,'ready');if(version===5){assert.equal(journal.schema,'p08b-owner-battle-hold-store.v1');for(const table of['battle_owner_hold_schema','battle_owner_hold_owner','battle_owner_hold_reservation','battle_owner_hold_command'])assert.equal(before.fingerprints[table],after.fingerprints[table],'Readonly Inspect5/auth changed hold metadata');}
}
