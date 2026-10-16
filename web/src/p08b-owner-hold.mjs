/** Explicit owner hold5; old on-wire contracts remain closed and unchanged. */
import {createHash} from 'node:crypto';
import {DatabaseSync} from 'node:sqlite';
import {LOSS_CONTRACT,LOSS_POLICY_SHA256,validateLossBattleRequest,validateLossBattleReply,validateLossResultsRequest} from './p06t-ammo-loss.mjs';
import {MIXED_POLICY_SHA256,MIXED_SHELL_SHA256,MIXED_TERMINAL_SHA256,validateMixedResultsReply} from './p06t-mixed.mjs';
export const HOLD_CONTRACT='p08b-owner-battle-hold.v1';
export const HOLD_POLICY_SHA256='98cdc5d657e4cdf30225c26913f2c70a89865de9ae2bb97704fa4b623efd806e';
const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const SHA=/^[0-9a-f]{64}$/;const LINK=['account_id','native_database_id','run_id','battle_id','reservation_id','native_inventory_id','vehicle_inventory_id','frozen_sha256','source_session_id','actor_slot','team','vehicle_kind'];
const META=['source_link','departure','finalization'];
const CODES=['STALE_REVISION','RUN_FENCED','RUN_NOT_OPEN','VEHICLE_RESERVED','UNKNOWN_VEHICLE','BATTLE_PROFILE_UNSUPPORTED','OWNER_ACCEPTANCE_REQUIRED','INCOMPLETE_CREW','AMMUNITION_EMPTY','AMMUNITION_UNSUPPORTED','RESERVATION_TERMINAL','RESERVATION_MISMATCH','DUPLICATE_PAYLOAD_MISMATCH','INVALID_RESULT','RESULT_MISMATCH','INVALID_TERMINAL_STATE','OWNER_HOLD_POLICY_REQUIRED','OWNER_HOLD_WRONG_ACTIVE_CONTRACT','INVALID_SOURCE_LINK'];
const exact=(v,keys)=>v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).sort().join(',')===[...keys].sort().join(',');
const integer=(v,l=1,h=2147483647)=>Number.isSafeInteger(v)&&v>=l&&v<=h;
const valid=(yes,msg,status)=>{if(!yes)throw Object.assign(new Error(`Owner hold ${msg}`),status?{status}:{});};
export function canonicalHold(x){return JSON.stringify((function sort(v){if(Array.isArray(v))return v.map(sort);if(v&&typeof v==='object')return Object.fromEntries(Object.keys(v).sort().map(k=>[k,sort(v[k])]));return v;})(x));}
const hash=v=>createHash('sha256').update(canonicalHold(v)).digest('hex');const bytes=v=>Buffer.byteLength(JSON.stringify(v));
export function holdWorkerConfiguration(v){valid(exact(v,['version','contract','policy_sha256'])&&v.version===5&&v.contract===HOLD_CONTRACT&&v.policy_sha256===HOLD_POLICY_SHA256,'explicit policy');return v;}
export function holdConfiguration(v,lossOwners){valid(exact(v,['version','contract','policy_sha256','accounts'])&&Array.isArray(v.accounts)&&integer(v.accounts.length,1,6)&&new Set(v.accounts).size===v.accounts.length&&v.accounts.every(a=>typeof a==='string'&&UUID.test(a)&&lossOwners.includes(a)),'owner subset');const {accounts,...worker}=v;holdWorkerConfiguration(worker);return [...accounts];}
/** Refuse rollback to an older factory even after a held reservation finishes. */
export function holdReaderFence(database,owners){const d=new DatabaseSync(database,{readOnly:true});try{d.exec('PRAGMA query_only=ON; BEGIN');
 const tables=d.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'battle_owner_hold_%' LIMIT 5").all().map(r=>r.name).sort();
 if(!tables.length){valid(owners.length===0,'activation required');return;}
 valid(tables.join(',')===['battle_owner_hold_schema','battle_owner_hold_owner','battle_owner_hold_reservation','battle_owner_hold_command'].sort().join(','),'namespace');
 const schema=d.prepare('SELECT * FROM battle_owner_hold_schema LIMIT 2').all();valid(schema.length===1&&exact(schema[0],['version','policy_sha256','loss_policy_sha256','source_sha256','terminal_sha256','catalog_sha256'])&&schema[0].version==='p08b-owner-battle-hold-store.v1'&&schema[0].policy_sha256===HOLD_POLICY_SHA256&&schema[0].loss_policy_sha256===LOSS_POLICY_SHA256&&schema[0].source_sha256===MIXED_SHELL_SHA256&&schema[0].terminal_sha256===MIXED_TERMINAL_SHA256&&SHA.test(schema[0].catalog_sha256),'schema pins');
 const actual=d.prepare('SELECT * FROM battle_owner_hold_owner LIMIT 7').all();valid(actual.length<=6&&actual.every(r=>exact(r,['account_id','policy_sha256','activated_revision','native_database_id'])&&UUID.test(r.account_id)&&r.policy_sha256===HOLD_POLICY_SHA256&&integer(r.activated_revision,13)&&integer(r.native_database_id))&&actual.map(r=>r.account_id).sort().join(',')===[...owners].sort().join(','),'configured marker owners');
 for(const table of['battle_owner_hold_reservation','battle_owner_hold_command'])valid(!d.prepare(`SELECT 1 FROM ${table} s LEFT JOIN battle_owner_hold_owner o ON o.account_id=s.account_id WHERE o.account_id IS NULL LIMIT 1`).get(),'orphan rows');
 }finally{if(d.isTransaction)d.exec('ROLLBACK');d.close();}}
function oldRequest(v){const o=Object.fromEntries(Object.entries(v).filter(([k])=>!META.includes(k)));return {...o,version:4,contract:LOSS_CONTRACT};}
function metadata(t,row,request=null){valid(exact(t.finalization,t.reason==='aborted_restart'||t.reason==='cancelled'?['kind']:['kind','tick']),'finalization fields');
 const kind=t.finalization.kind;
 if(t.reason==='aborted_restart'){valid(kind==='aborted_restart'&&t.source_link===null&&t.departure===null,'restart metadata');return;}
 if(t.reason==='cancelled'){const s=t.terminal_state;valid(kind==='pristine_cancel'&&t.source_link===null&&t.departure===null&&s.roster_size===0&&s.crew_active&&s.crew.every(x=>x.alive)&&s.devices.every(x=>x.health===x.max_health)&&canonicalHold(s.fire)===canonicalHold({active:false,ticks:0,damage:0})&&canonicalHold(s.death)===canonicalHold({reason:-1,killer_slot:null,tick:0}),'pristine cancel');return;}
 valid((kind==='outcome'&&t.reason==='battle_finished'||kind==='contained_failure'&&t.reason==='battle_failure')&&integer(t.finalization.tick,1000,37000),'finalization cause');
 const l=t.source_link;valid(exact(l,LINK)&&integer(l.source_session_id,1,4294967295)&&integer(l.actor_slot,0,5)&&integer(l.team,1,2)&&['ms1','is7'].includes(l.vehicle_kind),'immutable source link');
 valid(l.account_id===request.account_id&&l.native_database_id===request.native_database_id&&['run_id','battle_id','reservation_id','native_inventory_id','vehicle_inventory_id','frozen_sha256'].every(k=>l[k]===row[k])&&l.vehicle_kind===row.frozen.loss_frozen.loadout.kind&&l.actor_slot<t.terminal_state.roster_size&&(t.loss_event===null||t.loss_event.target_slot===l.actor_slot)&&t.terminal_state.death.tick<=t.finalization.tick,'admission source link');
 if(t.departure!==null)valid(exact(t.departure,['reason','tick'])&&['manual_leave','disconnect'].includes(t.departure.reason)&&integer(t.departure.tick,1000,37000)&&t.departure.tick<=t.finalization.tick,'departure cause');
}
export function validateHoldBattleRequest(v,owner){valid(v?.version===5&&v.contract===HOLD_CONTRACT,'request contract',400);const old=oldRequest(v);validateLossBattleRequest(old,owner);
 valid(exact(v,[...Object.keys(old),...(v.operation==='finish'?META:[])])&&bytes(v)<=(v.operation==='finish'?65536:2048),'request fields/budget',400);
 if(v.operation==='finish'){valid(['battle_finished','battle_failure','cancelled'].includes(v.reason)&&exact(v.finalization,v.reason==='cancelled'?['kind']:['kind','tick'])&&v.finalization.kind===({battle_finished:'outcome',battle_failure:'contained_failure',cancelled:'pristine_cancel'})[v.reason],'finish policy',400);
 if(v.reason==='cancelled')valid(v.source_link===null&&v.departure===null,'pristine metadata',400);
 else{const l=v.source_link;valid(integer(v.finalization.tick,1000,37000)&&exact(l,LINK)&&['account_id','native_database_id','run_id','battle_id','reservation_id','native_inventory_id'].every(k=>l[k]===v[k])&&typeof l.vehicle_inventory_id==='string'&&l.vehicle_inventory_id.startsWith(`${v.account_id}:`)&&l.vehicle_inventory_id.length<=96&&SHA.test(l.frozen_sha256)&&integer(l.source_session_id,1,4294967295)&&integer(l.actor_slot,0,5)&&integer(l.team,1,2)&&['ms1','is7'].includes(l.vehicle_kind),'bounded source link',400);
 if(v.departure!==null)valid(exact(v.departure,['reason','tick'])&&['manual_leave','disconnect'].includes(v.departure.reason)&&integer(v.departure.tick,1000,37000)&&v.departure.tick<=v.finalization.tick,'bounded departure',400);}
 if(v.reason==='battle_finished'){let r;try{r=JSON.parse(v.results_json);}catch{}valid(r?.interaction_details!==undefined,'Results8 required',400);}}
 return v;}
export function validateHoldBattleReply(v,request){valid(exact(v,['version','contract','operation','account_id','native_database_id','command_key','run_id','source_revision','revision','replayed','status','code','reservation','legacy_reservation','policy_sha256'])&&v.version===5&&v.contract===HOLD_CONTRACT&&v.policy_sha256===HOLD_POLICY_SHA256&&v.legacy_reservation===null&&bytes(v)<=8192,'reply contract/budget');
 if(v.status==='rejected')valid(CODES.includes(v.code),'known denial');
 const old={...v,version:4,contract:LOSS_CONTRACT,policy_sha256:LOSS_POLICY_SHA256};let validationRequest=oldRequest(request);const r=v.reservation;
 if(r!==null){valid(exact(r.frozen,['hold_policy_sha256','loss_frozen','loss_frozen_sha256'])&&r.frozen.hold_policy_sha256===HOLD_POLICY_SHA256&&r.frozen.loss_frozen_sha256===hash(r.frozen.loss_frozen)&&r.frozen_sha256===hash(r.frozen),'frozen wrapper');old.reservation={...r,frozen:r.frozen.loss_frozen,frozen_sha256:r.frozen.loss_frozen_sha256};
 if(r.result!==null){valid(exact(r.result,['reason','remaining_ammunition','fired_ammunition','lost_ammunition','loss_event','terminal_hp','destroyed','repaired_hp','credits','xp','terminal_state',...META]),'terminal fields');metadata(r.result,r,request);old.reservation.result=Object.fromEntries(Object.entries(r.result).filter(([k])=>!META.includes(k)));if(request.operation==='finish')valid(META.every(k=>canonicalHold(r.result[k])===canonicalHold(request[k])),'exact final metadata');}
 if(request.operation==='run_open'&&r.status==='active'){valid(v.status==='ready'&&r.run_id===request.run_id&&v.revision===v.source_revision&&r.result===null,'same-run active retained');old.operation='inspect';old.status='inspected';old.replayed=false;validationRequest={...validationRequest,operation:'inspect'};}
 }
 validateLossBattleReply(old,validationRequest);return v;}
export function validateHoldResultsRequest(v,owner){valid(v?.version===5&&v.contract===HOLD_CONTRACT,'result contract',400);validateLossResultsRequest({...v,version:4,contract:LOSS_CONTRACT},owner);return v;}
export function validateHoldResultsReply(v,request){valid(exact(v,['version','contract','operation','account_id','native_database_id','command_key','arena_id','status','acked','results_json','replayed','code','policy_sha256','record_contract'])&&v.version===5&&v.contract===HOLD_CONTRACT&&v.policy_sha256===HOLD_POLICY_SHA256&&(['missing','rejected'].includes(v.status)?v.record_contract===null:['ap-v1','mixed-v2','loss-v1','hold-v1'].includes(v.record_contract)),'result schema');
 if(v.status==='rejected'){valid(['RESULT_MISMATCH','DUPLICATE_PAYLOAD_MISMATCH','OWNER_HOLD_POLICY_REQUIRED'].includes(v.code)&&Object.keys(request).every(k=>v[k]===request[k])&&v.acked===false&&v.replayed===false&&v.results_json===null&&bytes(v)<=65536,'result denial');return v;}
 const {contract,record_contract,...old}=v,{contract:unused,...oldRequestValue}=request;validateMixedResultsReply({...old,version:2,policy_sha256:MIXED_POLICY_SHA256},{...oldRequestValue,version:2});return v;}

