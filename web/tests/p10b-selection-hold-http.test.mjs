/** Actual tracked adapter branch -> own Python reader -> disposable real SQLite. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { createHash, randomUUID } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { request as httpRequest } from 'node:http';
import { readFileSync,writeFileSync,copyFileSync,mkdirSync,realpathSync,existsSync } from 'node:fs';
import { resolve,join,relative,isAbsolute } from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';
const ROOT=fileURLToPath(new URL('../../',import.meta.url));
// Trusted attested seed resolution belongs to the fixture-only Python helper.
const EVIDENCE=join(ROOT,'local/evidence','p10b-hold-selection-http-'+randomUUID());mkdirSync(EVIDENCE,{recursive:true});
const {hashPassword,token}=await import(pathToFileURL(join(ROOT,'web/src/security.mjs')));
const crew=await import(pathToFileURL(join(ROOT,'web/src/p04d-crew.mjs')));
const {BARRACKS_CREW_POLICY_SHA256}=await import(pathToFileURL(join(ROOT,'web/src/p04k-crew.mjs')));
const {RESEARCH_POLICY_SHA256}=await import(pathToFileURL(join(ROOT,'web/src/p09e-research.mjs')));
const {BATTLE_POLICY_SHA256}=await import(pathToFileURL(join(ROOT,'web/src/p08b-battle.mjs')));
const {POOL_POLICY_SHA256}=await import(pathToFileURL(join(ROOT,'web/src/p04m-pool.mjs')));
const {MIXED_POLICY_SHA256,MIXED_TERMINAL_SHA256}=await import(pathToFileURL(join(ROOT,'web/src/p06t-mixed.mjs')));
const {HOLD_CONTRACT,HOLD_POLICY_SHA256}=await import(pathToFileURL(join(ROOT,'web/src/p08b-owner-hold.mjs')));
const {LOSS_CONTRACT,LOSS_POLICY_SHA256}=await import(pathToFileURL(join(ROOT,'web/src/p06t-ammo-loss.mjs')));
const {testDirectory}=await import(pathToFileURL(join(ROOT,'web/tests/helpers.mjs')));
const hash=v=>createHash('sha256').update(v).digest('hex');
const sql=(path,fn)=>{const d=new DatabaseSync(path);try{return fn(d);}finally{d.close();}};
const python=spawnSync('python',['-B','-c','import sys;print(sys.executable)'],{encoding:'utf8',windowsHide:true}).stdout.trim();
const cleanEnv={...process.env};delete cleanEnv.PYTHONPATH;

async function setup(t,{enabled=true}={}){
  const directory=testDirectory(),game=join(directory,'game.sqlite'),identity=join(directory,'identity.sqlite');

  const backup=spawnSync(python,['-B','-X','utf8',join(ROOT,'tests/helpers/p10b_selection_hold_http_seed.py'),game],{cwd:directory,env:cleanEnv,encoding:'utf8',windowsHide:true,timeout:90000});
  assert.equal(backup.status,0,backup.stderr);
  const SEED=JSON.parse(readFileSync(game.replace('.sqlite','.json')));
  const secret=token(),password=token(),passwordHash=await hashPassword(password),tokenFile=join(directory,'token');writeFileSync(tokenFile,secret);
  const native=join(directory,'native.json'),sourceNative=join(SEED.bundle,'content/inputs/native-ms1.blob'),nativeSHA=hash(readFileSync(sourceNative));copyFileSync(sourceNative,native);assert.equal(hash(readFileSync(native)),nativeSHA);assert.equal(hash(readFileSync(sourceNative)),nativeSHA);
  const users=SEED.profiles.map((p,i)=>({profile:p,email:`selection-http-${i}@example.test`}));
  sql(identity,d=>{d.exec('PRAGMA user_version=2;CREATE TABLE users(id TEXT PRIMARY KEY,username TEXT,display_nickname TEXT,email TEXT,password_hash TEXT,created_at INTEGER)');
    for(const {profile:p,email}of users)d.prepare('INSERT INTO users VALUES (?,?,?,?,?,?)').run(p.account_id,p.username.toLowerCase(),p.username,email,passwordHash,p.created_at_ms);});
  sql(game,d=>d.prepare('INSERT INTO game_meta VALUES (?,?)ON CONFLICT(key)DO UPDATE SET value=excluded.value').run('native_descriptors_sha256',hash(readFileSync(native))));
  const owner=users[0].profile.account_id,other=users[1].profile.account_id;
  const options={version:1,port:0,web_database:identity,game_database:game,fixture_root:join(directory,'fixtures'),native_descriptors:native,python_executable:python,token_file:tokenFile,
    ammunition_service:{version:1,bundle_root:SEED.bundle,original_root:SEED.original,account_id:owner,grant:{grant_id:'p09d-test-depot-v1',quantity_each:100}},
    crew_service:{version:1,policy_sha256:crew.CREW_POLICY_SHA256},crew_transfer:{version:1,policy_sha256:crew.TRANSFER_POLICY_SHA256},
    crew_cross_vehicle:{version:1,policy_sha256:crew.CROSS_CREW_POLICY_SHA256},crew_roster_recruitment:{version:1,policy_sha256:crew.ROSTER_CREW_POLICY_SHA256},
    crew_progression:{version:1,policy_sha256:crew.PROGRESSION_CREW_POLICY_SHA256},crew_dismissal:{version:1,policy_sha256:crew.DISMISSAL_CREW_POLICY_SHA256},
    crew_barracks_recruitment:{version:1,policy_sha256:BARRACKS_CREW_POLICY_SHA256},research_service:{version:1,policy_sha256:RESEARCH_POLICY_SHA256},
    battle_service:{version:1,policy_sha256:BATTLE_POLICY_SHA256,accounts:[owner,other]},pool_service:{version:1,policy_sha256:POOL_POLICY_SHA256,accounts:[owner,other]},
    mixed_service:{version:2,policy_sha256:MIXED_POLICY_SHA256,accounts:[owner,other],shell_catalog:join(ROOT,'tests/fixtures/p06t-shell-catalog.json'),terminal_policy:join(ROOT,'server/gateway/src/shared/p06t_device_policy.json')},
    ammo_loss_service:{version:4,contract:LOSS_CONTRACT,policy_sha256:LOSS_POLICY_SHA256,accounts:[owner,other]},
    owner_hold_service:{version:5,contract:HOLD_CONTRACT,policy_sha256:HOLD_POLICY_SHA256,accounts:[owner,other]},
    ...(enabled?{room_selection_hold_service:{version:5,schema:'p10b-owned-selection-hold.v1',contract:HOLD_CONTRACT,policy_sha256:HOLD_POLICY_SHA256,accounts:[owner]}}:{})};
  const {createIdentityBridge}=await import(pathToFileURL(join(ROOT,'web/src/game-adapter.mjs')));
  let bridge=await createIdentityBridge(options);const events=[];
  bridge.server.on('request',(req,res)=>res.once('finish',()=>events.push({path:req.url,host:req.headers.host,http:res.statusCode,socket_timeout_ms:req.socket.timeout})));
  t.after(async()=>{if(bridge)await bridge.close();assert.equal(hash(readFileSync(sourceNative)),nativeSHA);assert.deepEqual(SEED.source_before,SEED.source_after);});
  const call=async(path,value,{authorization=secret,headers={},raw=null}={})=>{
    const start=performance.now(),payload=Buffer.from(raw??JSON.stringify(value));
    const result=await new Promise((done,fail)=>{
      const req=httpRequest({hostname:'127.0.0.1',port:bridge.port,path,method:'POST',headers:{Authorization:`Bearer ${authorization}`,
        'Content-Type':'application/json','Content-Length':payload.length,...headers}},res=>{
        const chunks=[];res.on('data',v=>chunks.push(v));res.once('end',()=>{
          try{done({http:res.statusCode,body:JSON.parse(Buffer.concat(chunks).toString('utf8'))});}catch{fail(new Error('HTTP response schema'));}});});
      req.once('error',fail);req.setTimeout(12000,()=>req.destroy(new Error('HTTP test deadline')));req.end(payload);
    });
    const milliseconds=performance.now()-start;events.push({path,http:result.http,milliseconds,code:result.body.code??null});if(path==='/internal/native/room-selection-hold')assert.ok(milliseconds<9000,'Scoped outer selection deadline');return result;
  };
  const sourceRefs=()=>Object.fromEntries(Object.keys(SEED.source_before).map(path=>[path,existsSync(path)?{bytes:readFileSync(path).length,sha256:hash(readFileSync(path))}:null]));
  t.after(()=>assert.deepEqual(sourceRefs(),SEED.source_before));
  const physical=()=>Object.fromEntries([game,game+'-wal'].map(path=>[path,existsSync(path)?hash(readFileSync(path)):null]));
  const economy=()=>sql(game,d=>{const totals={};for(const r of d.prepare('SELECT * FROM p09c_ammo_depot').all())totals[r.account_id+':'+r.shell_id]=(totals[r.account_id+':'+r.shell_id]??0)+r.quantity;for(const r of d.prepare('SELECT * FROM p09c_ammo_mount').all())for(const [shell,n]of Object.entries(JSON.parse(r.loaded_json)))totals[r.account_id+':'+shell]=(totals[r.account_id+':'+shell]??0)+n;return {totals,resources:d.prepare('SELECT account_id,profile_json FROM game_profiles ORDER BY account_id').all().map(r=>({account:r.account_id,resources:JSON.parse(r.profile_json).resources})),crew:d.prepare('SELECT * FROM p04d_crew_member ORDER BY account_id,crew_id').all()};});
  const profile=(id=owner)=>sql(game,d=>JSON.parse(d.prepare('SELECT profile_json FROM game_profiles WHERE account_id=?').get(id).profile_json));
  const logical=()=>sql(game,d=>Object.fromEntries(d.prepare("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").all().map(r=>[r.name,d.prepare(`SELECT * FROM "${r.name}"`).all()])));
  const refresh=async(id=owner)=>{const response=await call('/internal/native/profile',{account_id:id,native_database_id:profile(id).native_database_id});assert.equal(response.http,200,JSON.stringify(response.body));return response.body;};
  function stamp(fresh,expected){
    const dir=realpathSync(fresh.fixture_dir),allowed=realpathSync(options.fixture_root),part=relative(allowed,dir);assert.ok(part&&!part.startsWith('..')&&!isAbsolute(part));
    const files=Object.fromEntries(['manifest.json','profile-input.json','p04m-pool.json','p06t-ammunition.json','p06t-ammo-loss.json','p08b-owner-hold.json'].map(name=>[name,JSON.parse(readFileSync(join(dir,name)))]));
    const manifest=files['manifest.json'],p=files['profile-input.json'],pool=files['p04m-pool.json'],mixed=files['p06t-ammunition.json'],loss=files['p06t-ammo-loss.json'],hold=files['p08b-owner-hold.json'];
    assert.equal(p.account_id,fresh.account_id);assert.equal(p.native_database_id,fresh.native_database_id);assert.equal(p.snapshot_revision,expected);assert.equal(manifest.snapshot_revision,expected);
    assert.equal(hash(readFileSync(join(dir,'profile-input.json'))),manifest.profile_sha256);
    const state=readFileSync(join(dir,'state.bin')),entry=manifest.files.find(x=>x.file==='state.bin');assert.equal(entry.sha256,hash(state));assert.equal(entry.bytes,state.length);
    for(const c of[pool,mixed,loss,hold]){assert.equal(c.account_id,fresh.account_id);assert.equal(c.native_database_id,fresh.native_database_id);assert.equal(c.revision,expected);assert.equal(c.state_sha256,hash(state));}
    return {native_state_sha256:hash(state),owner_source_sha256:manifest.source_bundle_sha256,catalog_sha256:manifest.research_catalog_sha256,
      pool_registry_sha256:pool.registry_sha256,mixed_policy_sha256:mixed.policy_sha256,shell_catalog_sha256:mixed.shell_catalog_sha256,terminal_policy_sha256:MIXED_TERMINAL_SHA256,loss_policy_sha256:loss.policy_sha256,loss_companion_sha256:hash(readFileSync(join(dir,'p06t-ammo-loss.json'))),hold_policy_sha256:hold.policy_sha256,hold_companion_sha256:hash(readFileSync(join(dir,'p08b-owner-hold.json')))};
  }
  const request=(fresh,expected,native=1)=>({version:5,contract:HOLD_CONTRACT,operation:'select',account_id:fresh.account_id,native_database_id:fresh.native_database_id,
    run_id:SEED.run_id,expected_revision:expected,native_inventory_id:native,projection_stamp:stamp(fresh,expected)});
  const save=(name,data)=>writeFileSync(join(EVIDENCE,name),JSON.stringify({status:'PASS_ACTUAL_HTTP_SQLITE',native:'NOT_RUN',wrapper:false,source_database_unchanged:true,new_grants:0,events,...data},null,2)+'\n',{flag:'wx'});
  return {bridge,call,profile,logical,refresh,request,save,owner,other,options,game,users,password,physical,economy};
}

test('actual authenticated adapter branch selects current projection and rejects stale cached hash after owned garage mutation',{timeout:180000},async t=>{
  const s=await setup(t);for(const user of s.users)assert.equal((await s.call('/internal/native/login',{email:user.email,password:s.password})).http,200);
  let expected=s.profile().snapshot_revision;const old=await s.refresh();const initial=s.request(old,expected);const before=s.logical(),physicalBefore=s.physical(),economyBefore=s.economy();
  const ready=await s.call('/internal/native/room-selection-hold',initial);assert.equal(ready.http,200,JSON.stringify(ready.body));assert.deepEqual(ready.body.frozen.loss_frozen.loadout.ammunition.map(x=>x.count),[0,4,10]);assert.deepEqual(s.logical(),before);
  assert.equal((await s.call('/internal/native/room-selection-hold',initial,{authorization:token()})).http,403);
  assert.equal((await s.call('/internal/native/room-selection-hold',initial,{headers:{Origin:'https://forbidden.example.test'}})).http,403);
  assert.equal((await s.call('/internal/native/room-selection-hold',initial,{headers:{Host:`localhost:${s.bridge.port}`}})).http,403);
  assert.equal((await s.call('/internal/native/room-selection-hold',{...initial,native_database_id:s.profile(s.other).native_database_id})).http,403);
  assert.equal((await s.call('/internal/native/room-selection-hold',{...initial,account_id:s.other,native_database_id:s.profile(s.other).native_database_id})).http,403);
  assert.equal((await s.call('/internal/native/room-selection-hold',initial,{raw:'x'.repeat(4097)})).http,413);
  assert.equal((await s.call('/internal/native/room-selection-hold',{...initial,arbitrary_path:'C:/untrusted'})).http,400);
  const poisoned=structuredClone(initial);poisoned.projection_stamp.shell_catalog_sha256='0'.repeat(64);
  assert.equal((await s.call('/internal/native/room-selection-hold',poisoned)).body.code,'SOURCE_STAMP_MISMATCH');
  assert.equal((await s.call('/internal/native/room-selection-hold',{...initial,version:2})).http,400);
  const duplicate=JSON.stringify(initial).replace('\"version\":5','\"version\":5,\"version\":5');
  assert.notEqual(duplicate,JSON.stringify(initial));const dup=await s.call('/internal/native/room-selection-hold',initial,{raw:duplicate});assert.equal(dup.http,409);assert.equal(dup.body.code,'INVALID_INPUT');
  assert.deepEqual(s.logical(),before);
  assert.deepEqual(s.physical(),physicalBefore,'Selection requests preserve actual main/WAL bytes');
  const concurrent=await Promise.all([s.call('/internal/native/room-selection-hold',initial),s.call('/internal/native/room-selection-hold',initial)]);
  assert.deepEqual(concurrent.map(x=>x.http).sort(),[200,503]);assert.deepEqual(s.logical(),before);assert.deepEqual(s.physical(),physicalBefore);
  const inspected=await s.call('/internal/native/battle',{version:5,contract:HOLD_CONTRACT,operation:'inspect',account_id:s.owner,native_database_id:s.profile().native_database_id,command_key:'selection64:old-hold-inspect',expected_revision:expected,run_id:initial.run_id});
  assert.equal(inspected.http,200);assert.equal(inspected.body.status,'inspected');assert.equal(inspected.body.version,5);assert.equal(inspected.body.reservation,null);assert.deepEqual(s.logical(),before);
  const changed=await s.call('/internal/native/ammo',{account_id:s.owner,native_database_id:s.profile().native_database_id,
    command_key:'selection-http:actual-owned-layout',expected_revision:expected,wire_revision:1,layout:[5,1,6,2570,0,2826,3,3082,11,6,0,0,0,0,0,0]});
  assert.equal(changed.http,200,JSON.stringify(changed.body));assert.equal(changed.body.status,'serviced');expected=s.profile().snapshot_revision;assert.deepEqual(s.economy(),economyBefore,'Existing owned ammo plus depot totals/resources/crew are conserved by normal layout mutation; no grants');
  assert.equal((await s.call('/internal/native/room-selection-hold',initial)).body.code,'STALE_REVISION');
  const mixedStamp={...initial,expected_revision:expected};assert.equal((await s.call('/internal/native/room-selection-hold',mixedStamp)).body.code,'SOURCE_STAMP_MISMATCH');
  const fresh=await s.refresh();const current=s.request(fresh,expected);assert.notEqual(current.projection_stamp.native_state_sha256,initial.projection_stamp.native_state_sha256);
  assert.throws(()=>s.request(fresh,expected-1));const final=await s.call('/internal/native/room-selection-hold',current);assert.equal(final.http,200,JSON.stringify(final.body));
  assert.deepEqual(final.body.frozen.loss_frozen.loadout.ammunition.map(x=>x.count),[0,3,11]);
  const admitted=await s.call('/internal/native/battle',{version:5,contract:HOLD_CONTRACT,operation:'admit',account_id:s.owner,native_database_id:s.profile().native_database_id,
    command_key:'selection64:actual-admit',expected_revision:expected,run_id:initial.run_id,battle_id:initial.run_id+':64',native_inventory_id:1});
  assert.equal(admitted.http,200,JSON.stringify(admitted.body));assert.equal(admitted.body.status,'admitted');
  const heldFresh=await s.refresh();const held=s.request(heldFresh,s.profile().snapshot_revision,2),heldBefore=s.logical();
  const refused=await s.call('/internal/native/room-selection-hold',held);assert.equal(refused.http,409);assert.equal(refused.body.code,'VEHICLE_RESERVED');
  assert.deepEqual(s.logical(),heldBefore,'actual active reserve stays exact; selection never releases/adds a reserve');
  s.save('http-current-and-guards.json',{initial,current,ready:ready.body,final:final.body,admitted:admitted.body,held_refused:refused.body,physical_selection_unchanged:true,owned_totals_resources_crew_conserved:true,descriptor_sha256:hash(readFileSync(s.options.native_descriptors))});
});

test('room selection mode absent keeps old endpoint behavior and adds no automatic activation',{timeout:90000},async t=>{
  const s=await setup(t,{enabled:false});const fresh=await s.refresh();const request=s.request(fresh,s.profile().snapshot_revision),before=s.logical();
  assert.equal((await s.call('/internal/native/room-selection-hold',request)).http,404);assert.deepEqual(s.logical(),before);
  s.save('http-mode-absent.json',{});
});
