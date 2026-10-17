/** Independent genuine SQL golden validation; no own round-trip used as native proof. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {Readable,PassThrough} from 'node:stream';
import {EventEmitter} from 'node:events';
import childProcess from 'node:child_process';
import {syncBuiltinESMExports} from 'node:module';
import {fileURLToPath} from 'node:url';
import {holdSelectionConfiguration,validateHoldSelectionRequest,validateHoldSelectionReply,holdRoomSelectionBody,createHoldRoomSelectionService} from '../src/p10b-selection-hold.mjs';
import {MIXED_POLICY_SHA256} from '../src/p06t-mixed.mjs';
import {HOLD_CONTRACT,HOLD_POLICY_SHA256} from '../src/p08b-owner-hold.mjs';
const golden=readFileSync(new URL('../../tests/fixtures/p10b-hold-selection-vectors.json',import.meta.url));
assert.equal(createHash('sha256').update(golden).digest('hex'),'65ef36eb0fdfcb93f2ef6d7ea4ab7a432d7eb617d4d2120565d316ee1d63980b');
const vectors=JSON.parse(golden).vectors;
const canonical=x=>JSON.stringify((function sort(v){return Array.isArray(v)?v.map(sort):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,sort(v[k])])):v;})(x));
const hash=x=>createHash('sha256').update(canonical(x)).digest('hex');
function resign(v){const f=v.frozen,l=f.loss_frozen;l.loadout_sha256=hash(l.loadout);f.loss_frozen_sha256=hash(l);v.frozen_sha256=hash(f);v.fingerprint=hash(Object.fromEntries(['contract','schema','account_id','native_database_id','run_id','native_inventory_id','revision','projection_stamp','aggregate_sha256','frozen_sha256'].map(k=>[k,v[k]])));}
const config=accounts=>({version:5,schema:'p10b-owned-selection-hold.v1',contract:HOLD_CONTRACT,policy_sha256:HOLD_POLICY_SHA256,accounts});
test('four genuine source-owned SQL vectors retain explicit5 wrappers and all11 stamps',()=>{
 assert.equal(vectors.length,4);for(const {request:q,response:r}of vectors){assert.equal(validateHoldSelectionRequest(q,q.account_id,q.native_database_id),q);assert.equal(validateHoldSelectionReply(r,q),r);}
});
test('closed config requires both owner capabilities and refuses duplicate/old2/4 overlap',()=>{
 const id=vectors[0].request.account_id,c=config([id]);assert.deepEqual(holdSelectionConfiguration(c,[id],[id]),[id]);
 for(const args of[[c,[],[id]],[c,[id],[]],[c,[id],[id],[id]],[config([id,id]),[id],[id]],[{...c,version:4},[id],[id]],[{...c,extra:true},[id],[id]]])assert.throws(()=>holdSelectionConfiguration(...args));
});
test('Request9 rejects paths, oldcontract, noninteger CAS and every missing or extra stamp',()=>{
 const q=vectors[0].request,owner=q.account_id,native=q.native_database_id;
 for(const change of[v=>v.version=4,v=>v.extra='C:/bad',v=>v.expected_revision=1.5,v=>v.account_id=vectors[2].request.account_id,v=>v.projection_stamp.extra='0'.repeat(64),...Object.keys(q.projection_stamp).map(k=>v=>delete v.projection_stamp[k])]){const v=structuredClone(q);change(v);assert.throws(()=>validateHoldSelectionRequest(v,owner,native));}
});
test('Reply15 rejects nested semantics even when attacker recomputes every hash',()=>{
 const {request:q,response:r}=vectors[0];
 for(const change of[v=>v.frozen.hold_policy_sha256='0'.repeat(64),v=>v.frozen.loss_frozen.policy_sha256='0'.repeat(64),v=>v.frozen.loss_frozen.loadout.max_hp=91,v=>v.frozen.loss_frozen.loadout.ammunition[0].count=97,v=>v.frozen.loss_frozen.loadout.crew_ids[0]='foreign:crew',v=>v.frozen.loss_frozen.loadout.initial_shell_compact_id=2570,v=>v.frozen.loss_frozen.loadout.ammunition.reverse()]){const v=structuredClone(r);change(v);resign(v);assert.throws(()=>validateHoldSelectionReply(v,q));}
 for(const change of[v=>v.version=4,v=>v.native_database_id++,v=>v.revision++,v=>v.aggregate_sha256='invalid',v=>v.frozen_sha256='0'.repeat(64),v=>v.frozen=v.frozen.loss_frozen,v=>v.extra=true,...Object.keys(q.projection_stamp).map(k=>v=>v.projection_stamp[k]='0'.repeat(64))]){const v=structuredClone(r);change(v);assert.throws(()=>validateHoldSelectionReply(v,q));}
});
test('body keeps duplicate bytes for actual Python parser and refuses encoded/oversized framing',async()=>{
 const raw=Buffer.from('{"version":5,"version":5}'),req=Readable.from([raw]);req.headers={'content-type':'application/json','content-length':String(raw.length)};assert.deepEqual((await holdRoomSelectionBody(req)).raw,raw);
 for(const headers of[{'content-length':'4097'},{'content-encoding':'gzip'},{'transfer-encoding':'chunked'},{'content-type':'text/plain'}]){const r=Readable.from([raw]);r.headers={'content-type':'application/json','content-length':String(raw.length),...headers};await assert.rejects(holdRoomSelectionBody(r));}
});

test('authored readable-pipe failure kills same child and retains owner capacity until close',async()=>{
 // Failure-only OS stream seam. No fabricated success/DTO/Fresh/SQL result.
 const original=childProcess.spawn;let child,killed=0,calls=0;
 childProcess.spawn=()=>{calls++;child=new EventEmitter();child.stdout=new PassThrough();child.stderr=new PassThrough();child.stdin=new PassThrough();child.kill=()=>{killed++;return true;};return child;};syncBuiltinESMExports();
 try{
  const q=vectors[0].request,root=fileURLToPath(new URL('../../',import.meta.url));
  const service=createHoldRoomSelectionService({accountId:q.account_id,nativeDatabaseId:q.native_database_id,database:'unused',bundle:root,original:root,python:'failure-only-owned-child',localPath:x=>x,
   mixed:{version:2,policy_sha256:MIXED_POLICY_SHA256,shell_catalog:fileURLToPath(new URL('../../tests/fixtures/p06t-shell-catalog.json',import.meta.url)),terminal_policy:fileURLToPath(new URL('../../tests/fixtures/p06t-device-policy.json',import.meta.url))}});
  for(const stream of['stdout','stderr']){
   const pending=service.select(q,Buffer.from(JSON.stringify(q)));const refusal=assert.rejects(pending,e=>e.status===503);
   child[stream].emit('error',new Error('AUTHORED_PIPE_IO_FAILURE'));assert.equal(killed,stream==='stdout'?1:2);
   await assert.rejects(service.select(q,Buffer.from('{}')),e=>e.status===503);assert.equal(calls,stream==='stdout'?1:2);
   child.emit('close',null);await refusal;
  }
 }finally{childProcess.spawn=original;syncBuiltinESMExports();}
});
