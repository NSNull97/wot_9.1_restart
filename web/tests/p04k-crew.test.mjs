/** Real loopback bridge, bounded Python workers and SQLite; native is separate. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync, copyFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createIdentityBridge, createGameReader } from '../src/game-adapter.mjs';
import { hashPassword, token } from '../src/security.mjs';
import { CREW_POLICY_SHA256, TRANSFER_POLICY_SHA256, CROSS_CREW_POLICY_SHA256, ROSTER_CREW_POLICY_SHA256, PROGRESSION_CREW_POLICY_SHA256, DISMISSAL_CREW_POLICY_SHA256 } from '../src/p04d-crew.mjs';
import { BARRACKS_CREW_POLICY_SHA256, nativeBarracksCrewOverview, isNativeBarracksCrewOverview, validateBarracksRecruitmentResponse } from '../src/p04k-crew.mjs';
import { testDirectory, removeTestDirectory } from './helpers.mjs';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const BUNDLE = resolve(process.env.P04D_TEST_BUNDLE || join(ROOT, 'local/p04d/source-bundle-05'));
const ORIGINAL = process.env.P04D_TEST_ORIGINAL || 'C:\\WoT_0.9.1_RU_0717_original';
const fixture = join(BUNDLE, 'content/fixtures/profile4/profile-input.json.blob');
const skip = !existsSync(fixture) ? 'NOT_RUN: verified portable #717 bundle required' : false;
function db(path, fn, readOnly = false) {
  const value = new DatabaseSync(path, { readOnly }); try { return fn(value); } finally { value.close(); }
}

for (const predecessor of ['F7']) test(`P04K native303 bridge preserves assignments and historical ${predecessor} replies through retirement and restart`, { skip }, async t => {
  const directory = testDirectory(), original = JSON.parse(readFileSync(fixture, 'utf8'));
  const identityFile = join(directory, 'identity.sqlite'), gameFile = join(directory, 'game.sqlite');
  const secret = token(), password = token(), email = 'p04k-isolated@example.test', passwordHash = await hashPassword(password);
  const nativePath = join(directory, 'native.json'), tokenFile = join(directory, 'identity.token');
  copyFileSync(join(BUNDLE, 'content/inputs/native-ms1.blob'), nativePath); writeFileSync(tokenFile, secret);
  db(identityFile, d => {
    d.exec('PRAGMA user_version=2; CREATE TABLE users(id TEXT PRIMARY KEY,username TEXT,display_nickname TEXT,email TEXT,password_hash TEXT,created_at INTEGER)');
    d.prepare('INSERT INTO users VALUES (?,?,?,?,?,?)').run(original.account_id, original.username.toLowerCase(), original.username,
      email, passwordHash, original.created_at_ms);
  });
  db(gameFile, d => {
    d.exec(`PRAGMA user_version=1; CREATE TABLE game_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
      CREATE TABLE game_profiles(native_id INTEGER PRIMARY KEY AUTOINCREMENT,account_id TEXT NOT NULL UNIQUE,profile_json TEXT NOT NULL);
      CREATE TABLE game_limits(key_hash TEXT PRIMARY KEY,hits INTEGER NOT NULL,resets_at INTEGER NOT NULL);`);
    d.prepare('INSERT INTO game_meta VALUES (?,?)').run('native_descriptors_sha256', createHash('sha256').update(readFileSync(nativePath)).digest('hex'));
    d.prepare('INSERT INTO game_profiles VALUES (?,?,?)').run(original.native_database_id, original.account_id, JSON.stringify(original));
  });
  const probe = spawnSync('python', ['-B', '-c', 'import sys;print(sys.executable)'], { encoding: 'utf8', windowsHide: true, timeout: 5000 });
  assert.equal(probe.status, 0);
  const options = { version: 1, port: 0, web_database: identityFile, game_database: gameFile,
    fixture_root: join(directory, 'fixtures'), native_descriptors: nativePath, python_executable: probe.stdout.trim(), token_file: tokenFile,
    ammunition_service: { version: 1, bundle_root: BUNDLE, original_root: ORIGINAL, account_id: original.account_id,
      grant: { grant_id: 'p09d-test-depot-v1', quantity_each: 100 } },
    crew_service: { version: 1, policy_sha256: CREW_POLICY_SHA256 } };
  let completed = false;
  async function startBridge(value) {
    try { return await createIdentityBridge(value); }
    catch (error) {
      const stored = db(gameFile, d => JSON.parse(d.prepare('SELECT profile_json FROM game_profiles').get().profile_json), true);
      t.diagnostic(`Bridge start failed: retained=${directory}; profile=${stored.profile_version}; revision=${stored.snapshot_revision}`);
      throw error;
    }
  }
  let bridge = await startBridge(options);
  t.after(async () => { await bridge.close(); if (completed) removeTestDirectory(directory); else t.diagnostic(`Failed run retained at ${directory}`); });
  const profile = () => db(gameFile, d => JSON.parse(d.prepare('SELECT profile_json FROM game_profiles WHERE account_id=?').get(original.account_id).profile_json), true);
  const ledger = () => db(gameFile, d => d.prepare('SELECT COUNT(*) AS n FROM game_command_ledger').get().n, true);
  assert.equal(profile().profile_version, 6);
  if (predecessor === 'F7') {
    await bridge.close(); options.crew_transfer = { version: 1, policy_sha256: TRANSFER_POLICY_SHA256 };
    bridge = await startBridge(options);
    assert.equal(profile().profile_version, 7); assert.equal(profile().snapshot_revision, 7);
  }
  async function call(path, data, auth = secret) {
    const response = await fetch(`http://127.0.0.1:${bridge.port}${path}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${auth}` }, body: JSON.stringify(data),
    }); return { status: response.status, body: await response.json() };
  }
  const command = { account_id: original.account_id, native_database_id: original.native_database_id,
    command_key: 'p04h-seed:309', expected_revision: predecessor === 'F7' ? 7 : 6, wire_revision: 1, layout: [3, 1, 1, 0] };
  const oldRecruitResponse = (await call('/internal/native/crew', command)).body;
  assert.equal(oldRecruitResponse.status, 'recruited');
  if (predecessor === 'D6') {
    await bridge.close(); options.crew_transfer = { version: 1, policy_sha256: TRANSFER_POLICY_SHA256 };
    bridge = await startBridge(options);
    assert.equal(profile().profile_version, 7); assert.equal(profile().snapshot_revision, 8);
  }
  const oldRequest = { ...command, command_key: 'p04h-seed:105', expected_revision: 8, wire_revision: 2, layout: [1, 1, -1] };
  const oldResponse = (await call('/internal/native/crew-transfer', oldRequest)).body;
  assert.equal(oldResponse.status, 'transferred');
  await bridge.close(); options.crew_cross_vehicle = { version: 1, policy_sha256: CROSS_CREW_POLICY_SHA256 };
  bridge = await startBridge(options);
  assert.equal(profile().profile_version, 8); assert.equal(profile().snapshot_revision, 10);
  assert.equal((await call('/internal/native/login', { email, password })).status, 200);

  const gRequest = { ...command, command_key: 'p04h-seed:g105', expected_revision: 10, wire_revision: 1, layout: [2, 0, 1] };
  const gResponse = (await call('/internal/native/crew-transfer', gRequest)).body;
  assert.equal(gResponse.status, 'transferred');
  await bridge.close(); options.crew_roster_recruitment = { version: 1, policy_sha256: ROSTER_CREW_POLICY_SHA256 };
  bridge = await startBridge(options);
  assert.equal(profile().profile_version, 9); assert.equal(profile().snapshot_revision, 12);
  const hRequest = { ...command, command_key: 'p04i-seed:h309', expected_revision: 12, wire_revision: 1, layout: [3,1,0,0] };
  const hResponse = (await call('/internal/native/crew', hRequest)).body;
  assert.equal(hResponse.status, 'recruited');
  const hProfile = profile();
  assert.equal((await call('/internal/native/crew-learn', { ...command, layout: [1,16,0] })).status, 404);
  await bridge.close(); options.crew_progression = { version: 1, policy_sha256: PROGRESSION_CREW_POLICY_SHA256 };
  bridge = await startBridge(options);
  assert.equal(profile().profile_version, 10); assert.equal(profile().snapshot_revision, 14);
  assert.deepEqual(profile().crew, hProfile.crew);
  const before = profile(), beforeLedger = ledger();
  let revision = before.snapshot_revision, wire = 1;
  const make = (key, layout) => ({ ...command, command_key: `p04i:${key}`, expected_revision: revision, wire_revision: wire, layout });
  const saved = [];
  const learnRequest = make('learn-survivor', [2,29,0]);
  const learnResponse = (await call('/internal/native/crew-learn', learnRequest)).body;
  assert.equal(learnResponse.status, 'learned'); revision++; wire++;
  saved.push([learnRequest,learnResponse,'crew-learn']);
  await bridge.close(); options.crew_dismissal = { version: 1, policy_sha256: DISMISSAL_CREW_POLICY_SHA256 };
  bridge = await startBridge(options); revision++; wire = 1;
  const retire = make('retire-before-k', [3,0,0]);
  const retired = (await call('/internal/native/crew-dismiss', retire)).body;
  assert.equal(retired.status, 'dismissed'); revision++; wire++;
  saved.push([retire,retired,'crew-dismiss']);
  const beforeK = profile();
  assert.equal((await call('/internal/native/crew-recruit-barracks', make('disabled', [3,7169,4,0]))).status, 404);
  await bridge.close(); options.crew_barracks_recruitment = { version: 1, policy_sha256: BARRACKS_CREW_POLICY_SHA256 };
  bridge = await startBridge(options); revision++; wire = 1;
  assert.equal(profile().profile_version,12);
  assert.equal(profile().snapshot_revision,revision);
  assert.deepEqual(profile().crew,beforeK.crew);
  const k = profile(), count = ledger();
  for (const layout of [[0,7169,4,0],[4,7169,4,0],[3,1,4,0],[3,7170,4,0],[3,3329,4,0],
    [3,7169,2,0],[3,7169,4,1],[3,7169,4,-1]]) {
    const reply = await call('/internal/native/crew-recruit-barracks',make('reject',layout));
    assert.equal(reply.status,200); assert.equal(reply.body.status,'rejected');
    assert.equal(reply.body.tankman_inventory_id,0);assert.equal(reply.body.tankman_descriptor_hex,'');
    assert.deepEqual(profile(),k);assert.equal(ledger(),count);
  }
  const candidate=make('first',[3,7169,4,0]);
  assert.equal((await call('/internal/native/crew-recruit-barracks',candidate,token())).status,403);
  for (const bad of [{...candidate, layout:[3,7169,4]}, {...candidate,layout:[3,7169,true,0]},
    {...candidate,account_id:'00000000-0000-4000-8000-000000000001'}, {...candidate,qualification:100}]) {
    assert.notEqual((await call('/internal/native/crew-recruit-barracks',bad)).status,200);
    assert.deepEqual(profile(),k);assert.equal(ledger(),count);
  }
  for (const [i,layout] of [[3,7169,4,0],[3,3329,1,0]].entries()) {
    const request=make('hire:'+i,layout), response=(await call('/internal/native/crew-recruit-barracks',request)).body;
    assert.equal(response.status,'recruited');assert.equal(response.revision,++revision);assert.equal(response.wire_revision,++wire);
    assert.equal(Object.keys(response).length,11);assert.equal(response.tankman_inventory_id,5+i);
    assert.equal(response.tankman_descriptor_hex.length,50);
    validateBarracksRecruitmentResponse(response,request);
    assert.deepEqual((await call('/internal/native/crew-recruit-barracks',request)).body,{...response,replayed:true});
    saved.push([request,response,'crew-recruit-barracks']);
  }
  const complete=profile(), finalCount=ledger();
  assert.equal(complete.crew.length,k.crew.length+2);
  assert.deepEqual(complete.crew.slice(0,k.crew.length),k.crew);
  assert.deepEqual(complete.inventory,k.inventory);
  for (const field of ['resources','ammunition','ammunition_depot']) assert.deepEqual(complete[field],k[field]);
  assert.deepEqual(complete.crew.slice(-2).map(m=>[m.role,m.role_level,m.vehicle_inventory_id,m.skills]),[
    ['gunner',50,null,[]],['commander',50,null,[]]]);
  assert.equal(complete.crew_service.free_recruitment_left,k.crew_service.free_recruitment_left-2);
  const overview=await createGameReader({origin:`http://127.0.0.1:${bridge.port}`,tokenFile})(original.account_id);
  assert.equal(overview.crewService.version,7);assert.deepEqual(nativeBarracksCrewOverview(complete),overview);
  assert.equal(isNativeBarracksCrewOverview(overview,original.account_id),true);
  for (const change of [p=>{p.profile_version=11;},p=>{p.crew_service.policy_sha256=DISMISSAL_CREW_POLICY_SHA256;},
    p=>{p.crew.at(-1).skills=[{skill_id:'repair',level:0}];},p=>{p.crew.at(-1).crew_id=p.crew[0].crew_id;}]) {
    const bad=structuredClone(complete);change(bad);assert.throws(()=>nativeBarracksCrewOverview(bad));
  }
  for (const [request,response,op] of [[command,oldRecruitResponse,'crew'],[oldRequest,oldResponse,'crew-transfer'],
    [gRequest,gResponse,'crew-transfer'],[hRequest,hResponse,'crew'],...saved]) {
    assert.deepEqual((await call(`/internal/native/${op}`,request)).body,{...response,replayed:true});
  }
  assert.deepEqual(profile(),complete);assert.equal(ledger(),finalCount);
  // The saved303 response must retain its original passport after later retirement.
  const retireNew=make('retire-new',[5,0,0]);
  const retireNewResponse=(await call('/internal/native/crew-dismiss',retireNew)).body;
  assert.equal(retireNewResponse.status,'dismissed');revision++;wire++;
  const durable=profile();
  await bridge.close();bridge=await startBridge(options);
  assert.deepEqual(profile(),durable);assert.equal((await call('/internal/native/login',{email,password})).status,200);
  for (const [request,response,op] of saved) assert.deepEqual((await call(`/internal/native/${op}`,request)).body,{...response,replayed:true});
  assert.deepEqual(profile(),durable);
  for (const bad of [null,true,{version:1,policy_sha256:DISMISSAL_CREW_POLICY_SHA256}])
    await assert.rejects(()=>createIdentityBridge({...options,crew_barracks_recruitment:bad}));
  const missing={...options};delete missing.crew_dismissal;await assert.rejects(()=>createIdentityBridge(missing));
  completed=true;
});

test('P04K typed303 result rejects forged descriptor, delta, quota and rejection allocation',()=>{
  const request={layout:[3,7169,4,0],wire_revision:1};
  const value={status:'recruited',tankman_inventory_id:12,
    tankman_descriptor_hex:'081c04320000000c000c000c00400600000000420000000000',
    update_hex:'80027d285507707265765265764b0155037265764b025509696e76656e746f72797d284b087d285509636f6d7044657363727d284b0c5519081c04320000000c000c000c0040060000000042000000000075550776656869636c657d284b0c4affffffff757575550573746174737d28550c66726565544d656e4c6566744b0475752e'};
  assert.doesNotThrow(()=>validateBarracksRecruitmentResponse(value,request));
  for(let i=0;i<value.update_hex.length;i+=2){const bad={...value,update_hex:value.update_hex.slice(0,i)+(value.update_hex.slice(i,i+2)==='00'?'01':'00')+value.update_hex.slice(i+2)};
    assert.throws(()=>validateBarracksRecruitmentResponse(bad,request));}
  for(const bad of [{...value,tankman_inventory_id:13},{...value,tankman_descriptor_hex:value.tankman_descriptor_hex.toUpperCase()},
    {...value,tankman_descriptor_hex:'00'.repeat(25)},{...value,status:'rejected'}]) assert.throws(()=>validateBarracksRecruitmentResponse(bad,request));
  for(const layout of [[3,3329,4,0],[3,7169,5,0],[0,7169,4,0]]) assert.throws(()=>validateBarracksRecruitmentResponse(value,{...request,layout}));
});
