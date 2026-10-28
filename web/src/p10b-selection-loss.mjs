/** Distinct read-only room selection. No activation, fixture publication or reserve. */
import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { resolve, isAbsolute } from 'node:path';
import { fileURLToPath } from 'node:url';
import { statSync, realpathSync } from 'node:fs';
import { mixedWorkerConfiguration, MIXED_POLICY_SHA256, MIXED_SHELL_SHA256, MIXED_TERMINAL_SHA256 } from './p06t-mixed.mjs';

import { LOSS_CONTRACT, LOSS_POLICY_SHA256 } from './p06t-ammo-loss.mjs';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const WORKER = resolve(ROOT, 'tools/p10b_selection_loss_service.py');
export const ROOM_SELECTION_LOSS_PATH = '/internal/native/room-selection-loss';
export const LOSS_SELECTION_SCHEMA = 'p10b-owned-selection-loss.v1';
export const LOSS_SELECTION_WORKER_TIMEOUT_MS = 7000;
export const LOSS_SELECTION_REQUEST_TIMEOUT_MS = 9000;
const SHA=/^[0-9a-f]{64}$/, UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const CATALOG='1f6b20d1ba564e00186fed77a3da74c3bd9b135f0db30ffdef740fd5888ced80';
const REGISTRY='e2f4ac21fe8970f3c5d29f6a45d845f9d80e4d2759f0e662c9f3bb9ac04c7b34';
const STAMP=['native_state_sha256','owner_source_sha256','catalog_sha256','pool_registry_sha256','mixed_policy_sha256','shell_catalog_sha256','terminal_policy_sha256','loss_policy_sha256','loss_companion_sha256'];
const COMMON=['contract','version','operation','account_id','native_database_id','run_id','expected_revision','native_inventory_id','projection_stamp'];
const DENIALS=new Set(['INVALID_INPUT','STALE_REVISION','SOURCE_STAMP_MISMATCH','NATIVE_STATE_STAMP_MISMATCH','RUN_NOT_OPEN','RUN_FENCED',
  'VEHICLE_RESERVED','UNKNOWN_VEHICLE','BATTLE_PROFILE_UNSUPPORTED','OWNER_ACCEPTANCE_REQUIRED','INCOMPLETE_CREW','AMMUNITION_EMPTY','AMMUNITION_UNSUPPORTED','AMMO_LOSS_POLICY_REQUIRED','OWNER_CONTRACT_UNSUPPORTED']);
const exact=(v,keys)=>v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).sort().join(',')===[...keys].sort().join(',');
const integer=(v,min=1)=>Number.isSafeInteger(v)&&v>=min&&v<=2147483647;
const requireValue=(ok,status=400)=>{if(!ok)throw Object.assign(new Error('P10B selection schema/configuration'),{status});};
const canonical=v=>JSON.stringify((function sort(x){return Array.isArray(x)?x.map(sort):x&&typeof x==='object'
  ?Object.fromEntries(Object.keys(x).sort().map(k=>[k,sort(x[k])])):x;})(v));
const hash=v=>createHash('sha256').update(v).digest('hex');

export function lossSelectionConfiguration(value,lossOwners){
  requireValue(exact(value,['version','schema','contract','policy_sha256','accounts'])&&value.version===4&&value.schema===LOSS_SELECTION_SCHEMA&&value.contract===LOSS_CONTRACT&&value.policy_sha256===LOSS_POLICY_SHA256
    &&Array.isArray(value.accounts)&&value.accounts.length>=1&&value.accounts.length<=6&&new Set(value.accounts).size===value.accounts.length
    &&value.accounts.every(id=>typeof id==='string'&&UUID.test(id)&&lossOwners.includes(id)));
  return [...value.accounts];
}
export function validateLossSelectionRequest(v,owner,native){
  requireValue(exact(v,COMMON)&&v.version===4&&v.contract===LOSS_CONTRACT&&v.operation==='select'&&v.account_id===owner&&UUID.test(owner)
    &&integer(v.native_database_id)&&v.native_database_id===native&&typeof v.run_id==='string'&&UUID.test(v.run_id)
    &&integer(v.expected_revision,13)&&integer(v.native_inventory_id)&&exact(v.projection_stamp,STAMP)
    &&STAMP.every(k=>typeof v.projection_stamp[k]==='string'&&SHA.test(v.projection_stamp[k]))&&Buffer.byteLength(JSON.stringify(v))<=3072);
  return v;
}
function baseFrozen(v,r){
  const p={ms1:{native:1,suffix:'starter-vehicle-v1',descriptor:'010d1a000e00c90000001700170000',hp:90,capacity:96,crew:2,
    cds:[2570,2826,3082],suffixes:['ap','heat','he'],families:['ARMOR_PIERCING','HOLLOW_CHARGE','HIGH_EXPLOSIVE']},
    is7:{native:2,suffix:'test-is7-v1',descriptor:'011c3a002400cd000b002f003a0000',hp:2150,capacity:30,crew:5,
      cds:[14602,14858,15114],suffixes:['ap','apcr','he'],families:['ARMOR_PIERCING','ARMOR_PIERCING_CR','HIGH_EXPLOSIVE']}}[v?.kind];
  requireValue(p&&exact(v,['kind','descriptor_hex','native_inventory_id','vehicle_inventory_id','max_hp','crew_ids','capacity','ammunition','initial_shell_compact_id'])
    &&v.native_inventory_id===r.native_inventory_id&&v.native_inventory_id===p.native&&v.vehicle_inventory_id===`${r.account_id}:${p.suffix}`
    &&v.descriptor_hex===p.descriptor&&v.max_hp===p.hp&&v.capacity===p.capacity&&Array.isArray(v.crew_ids)&&v.crew_ids.length===p.crew
    &&new Set(v.crew_ids).size===p.crew&&v.crew_ids.every(s=>typeof s==='string'&&/^[A-Za-z0-9_:-]{1,96}$/.test(s)&&s.startsWith(`${r.account_id}:`))
    &&Array.isArray(v.ammunition)&&v.ammunition.length===3&&v.ammunition.every((a,i)=>exact(a,['shell_definition_id','shell_compact_id','family','count'])
      &&a.shell_definition_id===`shell:${v.kind}-stock-${p.suffixes[i]}`&&a.shell_compact_id===p.cds[i]&&a.family===p.families[i]&&integer(a.count,0)&&a.count<=p.capacity),503);
  const total=v.ammunition.reduce((n,a)=>n+a.count,0);
  requireValue(total>=1&&total<=p.capacity&&v.initial_shell_compact_id===v.ammunition.find(a=>a.count>0).shell_compact_id,503);
}
function frozen(v,r){
  requireValue(exact(v,['policy_sha256','loadout','loadout_sha256'])&&v.policy_sha256===LOSS_POLICY_SHA256
    &&typeof v.loadout_sha256==='string'&&SHA.test(v.loadout_sha256),503);
  baseFrozen(v.loadout,r);requireValue(hash(canonical(v.loadout))===v.loadout_sha256,503);
}
export function validateLossSelectionReply(v,r){
  requireValue(exact(v,['contract','version','schema','operation','status','account_id','native_database_id','run_id','native_inventory_id','revision',
    'projection_stamp','aggregate_sha256','frozen','frozen_sha256','fingerprint'])&&v.version===4&&v.contract===LOSS_CONTRACT&&v.schema===LOSS_SELECTION_SCHEMA&&v.operation==='select'&&v.status==='ready'
    &&['account_id','native_database_id','run_id','native_inventory_id'].every(k=>v[k]===r[k])&&v.revision===r.expected_revision
    &&exact(v.projection_stamp,STAMP)&&canonical(v.projection_stamp)===canonical(r.projection_stamp)
    &&['aggregate_sha256','frozen_sha256','fingerprint'].every(k=>typeof v[k]==='string'&&SHA.test(v[k]))&&Buffer.byteLength(JSON.stringify(v))<=6144,503);
  const s=v.projection_stamp;
  requireValue(s.catalog_sha256===CATALOG&&s.pool_registry_sha256===REGISTRY&&s.mixed_policy_sha256===MIXED_POLICY_SHA256
    &&s.shell_catalog_sha256===MIXED_SHELL_SHA256&&s.terminal_policy_sha256===MIXED_TERMINAL_SHA256&&s.loss_policy_sha256===LOSS_POLICY_SHA256,503);
  frozen(v.frozen,r);requireValue(hash(canonical(v.frozen))===v.frozen_sha256,503);
  const binding=Object.fromEntries(['contract','schema','account_id','native_database_id','run_id','native_inventory_id','revision','projection_stamp','aggregate_sha256','frozen_sha256'].map(k=>[k,v[k]]));
  requireValue(hash(canonical(binding))===v.fingerprint,503);return v;
}
export async function lossRoomSelectionBody(req){
  requireValue(req.headers['content-type']==='application/json'&&!req.headers['content-encoding']&&!req.headers['transfer-encoding']&&/^\d{1,5}$/.test(req.headers['content-length']||''));
  const length=Number(req.headers['content-length']);requireValue(length>=2&&length<=3072,413);
  const parts=[];let size=0;
  for await(const part of req){size+=part.length;requireValue(size<=length,413);parts.push(part);}
  requireValue(size===length);const raw=Buffer.concat(parts);
  let value;try{value=JSON.parse(raw.toString('utf8'));}catch{requireValue(false);}
  return {value,raw}; // Original bytes reach the unique-key Python parser.
}

export function createLossRoomSelectionService({accountId,nativeDatabaseId,database,bundle,original,python,localPath,mixed}){
  requireValue(UUID.test(accountId)&&integer(nativeDatabaseId)&&typeof python==='string');
  mixedWorkerConfiguration(mixed);const db=localPath(database);
  requireValue(isAbsolute(bundle)&&statSync(bundle).isDirectory()&&resolve(bundle).toLowerCase()===realpathSync(bundle).toLowerCase());
  let active=0;
  return {accountId,async select(value,raw){
    validateLossSelectionRequest(value,accountId,nativeDatabaseId);requireValue(active<1,503);active++;
    try{
      const output=await new Promise((done,fail)=>{
        const env={...process.env};delete env.PYTHONPATH;
        const child=spawn(python,['-B','-X','utf8',WORKER,'--database',db,'--bundle',bundle,'--original-root',original,
          '--account-id',accountId,'--shell-catalog',mixed.shell_catalog,'--terminal-policy',mixed.terminal_policy],
          {cwd:ROOT,env,windowsHide:true,stdio:['pipe','pipe','pipe']});
        let size=0,stderr=0,failed=false;const chunks=[];
        const timeout=setTimeout(()=>{failed=true;child.kill();},LOSS_SELECTION_WORKER_TIMEOUT_MS);
        child.stdout.on('data',chunk=>{size+=chunk.length;if(size>6144){failed=true;child.kill();}else chunks.push(chunk);});
        child.stderr.on('data',chunk=>{stderr+=chunk.length;if(stderr>4096){failed=true;child.kill();}});
        child.once('error',()=>{clearTimeout(timeout);fail(Object.assign(new Error('Selection worker unavailable'),{status:503}));});
        child.once('close',code=>{clearTimeout(timeout);if(code!==0||failed)return fail(Object.assign(new Error('Selection worker unavailable'),{status:503}));
          try{done(JSON.parse(Buffer.concat(chunks).toString('utf8')));}catch{fail(Object.assign(new Error('Selection worker schema'),{status:503}));}});
        child.stdin.on('error',()=>{failed=true;child.kill();});child.stdin.end(raw);
      });
      if(exact(output,['error','code'])&&output.error==='selection_not_ready'&&DENIALS.has(output.code))return output;
      return validateLossSelectionReply(output,value);
    }finally{active--;}
  }};
}
