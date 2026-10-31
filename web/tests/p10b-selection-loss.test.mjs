import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { lossSelectionConfiguration,validateLossSelectionRequest,validateLossSelectionReply,LOSS_SELECTION_SCHEMA } from '../src/p10b-selection-loss.mjs';
import { LOSS_CONTRACT,LOSS_POLICY_SHA256 } from '../src/p06t-ammo-loss.mjs';
const raw=readFileSync(new URL('../../tests/fixtures/p10b-loss-selection-vectors.json',import.meta.url));
assert.equal(createHash('sha256').update(raw).digest('hex'),'d9f22734afbc6a7501eff76bcd0d0f4762a7bb0da36a6fbeb0f2047e977218a5');
const fixture=JSON.parse(raw);
test('real two-owner SQL selection vectors preserve mode4 AP0 and both actual byte stamps',()=>{
  assert.equal(fixture.vectors.length,2);
  for(const{request,response}of fixture.vectors){
    validateLossSelectionRequest(request,request.account_id,request.native_database_id);validateLossSelectionReply(response,request);
    assert.equal(Object.keys(response).length,15);assert.equal(Object.keys(response.projection_stamp).length,9);
    assert.deepEqual(response.frozen.loadout.ammunition.map(x=>x.count),[0,4,10]);
    assert.notEqual(response.aggregate_sha256,response.projection_stamp.native_state_sha256);
  }
});
test('closed opt-in owner subset requires loss4 and rejects malformed UUID variants',()=>{
  const owner=fixture.vectors[0].request.account_id;
  const config={version:4,schema:LOSS_SELECTION_SCHEMA,contract:LOSS_CONTRACT,policy_sha256:LOSS_POLICY_SHA256,accounts:[owner]};
  assert.deepEqual(lossSelectionConfiguration(config,[owner]),[owner]);
  for(const bad of [{...config,version:1},{...config,contract:'mixed-v2'},{...config,policy_sha256:'0'.repeat(64)},
    {...config,accounts:[owner,owner]},{...config,accounts:[owner.slice(0,19)+'0'+owner.slice(20)]},{...config,worker:'untrusted'}])
    assert.throws(()=>lossSelectionConfiguration(bad,[owner]));
  assert.throws(()=>lossSelectionConfiguration(config,[]));
});
test('wrong source/native/revision/wrapper/hash field cannot produce a ready reply',()=>{
  const{request,response}=fixture.vectors[0];
  for(const bad of [{...request,version:2},{...request,contract:'old'},{...request,expected_revision:true},{...request,untrusted_path:'C:/x'},
    {...request,projection_stamp:{...request.projection_stamp,extra:'0'.repeat(64)}}])
    assert.throws(()=>validateLossSelectionRequest(bad,request.account_id,request.native_database_id));
  for(const edit of [v=>v.revision++,v=>v.native_database_id++,v=>v.contract='old',v=>v.projection_stamp.loss_policy_sha256='0'.repeat(64),
    v=>v.projection_stamp.loss_companion_sha256='0'.repeat(64),v=>v.frozen.policy_sha256='0'.repeat(64),
    v=>v.frozen.loadout.ammunition[0].count=1,v=>v.frozen.loadout.crew_ids.pop(),v=>v.frozen_sha256='0'.repeat(64),v=>v.fingerprint='0'.repeat(64)]){
    const v=structuredClone(response);edit(v);assert.throws(()=>validateLossSelectionReply(v,request));
  }
});
test('actual fixture remains source-safe compact DTOs with bounded encoded messages',()=>{
  assert.ok(raw.length<20000);assert.match(createHash('sha256').update(raw).digest('hex'),/^[0-9a-f]{64}$/);
  for(const{request,response}of fixture.vectors){assert.ok(Buffer.byteLength(JSON.stringify(request))<=3072);assert.ok(Buffer.byteLength(JSON.stringify(response))<=6144);}
});
