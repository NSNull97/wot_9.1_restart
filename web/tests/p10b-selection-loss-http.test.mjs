/** Actual tracked adapter branch -> own Python reader -> disposable real SQLite. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { createHash, randomUUID } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { request as httpRequest } from 'node:http';
import { readFileSync,writeFileSync,copyFileSync,mkdirSync,realpathSync } from 'node:fs';
import { resolve,join,relative,isAbsolute,delimiter } from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';
const ROOT=fileURLToPath(new URL('../../',import.meta.url));
const STAGE=ROOT;
const SOURCE=JSON.parse(readFileSync(join(ROOT,'local/night-staging/20261016/p10b-selection-http01/seed01/seed.json')));
const EVIDENCE=join(ROOT,'local/evidence','p10b-loss-selection-http-'+randomUUID());mkdirSync(EVIDENCE,{recursive:true});
const {hashPassword,token}=await import(pathToFileURL(join(ROOT,'web/src/security.mjs')));
const crew=await import(pathToFileURL(join(ROOT,'web/src/p04d-crew.mjs')));
const {BARRACKS_CREW_POLICY_SHA256}=await import(pathToFileURL(join(ROOT,'web/src/p04k-crew.mjs')));
const {RESEARCH_POLICY_SHA256}=await import(pathToFileURL(join(ROOT,'web/src/p09e-research.mjs')));
const {BATTLE_POLICY_SHA256}=await import(pathToFileURL(join(ROOT,'web/src/p08b-battle.mjs')));
const {POOL_POLICY_SHA256}=await import(pathToFileURL(join(ROOT,'web/src/p04m-pool.mjs')));
const {MIXED_POLICY_SHA256,MIXED_TERMINAL_SHA256}=await import(pathToFileURL(join(ROOT,'web/src/p06t-mixed.mjs')));
const {LOSS_CONTRACT,LOSS_POLICY_SHA256}=await import(pathToFileURL(join(ROOT,'web/src/p06t-ammo-loss.mjs')));
const {testDirectory,removeTestDirectory}=await import(pathToFileURL(join(ROOT,'web/tests/helpers.mjs')));
const hash=v=>createHash('sha256').update(v).digest('hex');
const sql=(path,fn)=>{const d=new DatabaseSync(path);try{return fn(d);}finally{d.close();}};
const python=spawnSync('python',['-B','-c','import sys;print(sys.executable)'],{encoding:'utf8',windowsHide:true}).stdout.trim();
const cleanEnv={...process.env};delete cleanEnv.PYTHONPATH;

// Fault injection only: relocate the current byte-bound source, overriding
// one trusted test worker constant. Ordinary cases import the real adapter.
function slowView(){
  const relocate=(text)=>{
    const rootLine="const ROOT = fileURLToPath(new URL('../../', import.meta.url));";
    assert.equal(text.split(rootLine).length,2);text=text.replace(rootLine,`const ROOT = ${JSON.stringify(ROOT)};`);
    return text.replace(/from (['"])(\.\/[^'"]+)\1/g,(_m,_q,path)=>`from ${JSON.stringify(pathToFileURL(resolve(ROOT,'web/src',path)).href)}`);
  };
  const stall=join(EVIDENCE,'stall.py');writeFileSync(stall,'import time\ntime.sleep(30)\n',{flag:'wx'});
  const moduleSource=readFileSync(join(ROOT,'web/src/p10b-selection-loss.mjs'),'utf8');
  const workerLine="const WORKER = resolve(ROOT, 'tools/p10b_selection_loss_service.py');";assert.equal(moduleSource.split(workerLine).length,2);
  const moduleView=join(EVIDENCE,'selection-slow.mjs');writeFileSync(moduleView,relocate(moduleSource).replace(workerLine,`const WORKER = ${JSON.stringify(stall)};`),{flag:'wx'});
  const adapterSource=readFileSync(join(ROOT,'web/src/game-adapter.mjs'),'utf8'),url=JSON.stringify(pathToFileURL(join(ROOT,'web/src/p10b-selection-loss.mjs')).href);
  let adapter=relocate(adapterSource);assert.equal(adapter.split(url).length,2);adapter=adapter.replace(url,JSON.stringify(pathToFileURL(moduleView).href));
  const adapterView=join(EVIDENCE,'adapter-slow.mjs');writeFileSync(adapterView,adapter,{flag:'wx'});
  writeFileSync(join(EVIDENCE,'fault-source.json'),JSON.stringify({schema:'p10b-loss-stalled-worker-source.v1',adapter_sha256:hash(adapterSource),module_sha256:hash(moduleSource),fault_injection:'fixed owned stall script; no success/ownership injection',native:'NOT_RUN'},null,2),{flag:'wx'});
  return pathToFileURL(adapterView);
}

async function setup(t,{enabled=true,view='view01'}={}){
  const directory=testDirectory(),game=join(directory,'game.sqlite'),identity=join(directory,'identity.sqlite');
  const sourceHash=hash(readFileSync(SOURCE.database));
  const backup=spawnSync(python,['-B','-X','utf8',join(ROOT,'tests/helpers/p10b_selection_loss_seed.py'),game],{cwd:directory,env:cleanEnv,encoding:'utf8',windowsHide:true,timeout:90000});
  assert.equal(backup.status,0,backup.stderr);
  const SEED=JSON.parse(readFileSync(game.replace('.sqlite','.json')));
  const secret=token(),password=token(),passwordHash=await hashPassword(password),tokenFile=join(directory,'token');writeFileSync(tokenFile,secret);
  const native=join(directory,'native.json');copyFileSync(join(SEED.bundle,'content/inputs/native-ms1.blob'),native);
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
    ...(enabled?{room_selection_loss_service:{version:4,schema:'p10b-owned-selection-loss.v1',contract:LOSS_CONTRACT,policy_sha256:LOSS_POLICY_SHA256,accounts:[owner]}}:{})};
  const {createIdentityBridge}=await import(view==='view-slow01'?slowView():pathToFileURL(join(ROOT,'web/src/game-adapter.mjs')));
  let bridge=await createIdentityBridge(options);const events=[];
  bridge.server.on('request',(req,res)=>res.once('finish',()=>events.push({path:req.url,host:req.headers.host,http:res.statusCode,socket_timeout_ms:req.socket.timeout})));
  t.after(async()=>{if(bridge)await bridge.close();assert.equal(hash(readFileSync(SOURCE.database)),sourceHash);removeTestDirectory(directory);});
  const call=async(path,value,{authorization=secret,headers={},raw=null}={})=>{
    const start=performance.now(),payload=Buffer.from(raw??JSON.stringify(value));
    const result=await new Promise((done,fail)=>{
      const req=httpRequest({hostname:'127.0.0.1',port:bridge.port,path,method:'POST',headers:{Authorization:`Bearer ${authorization}`,
        'Content-Type':'application/json','Content-Length':payload.length,...headers}},res=>{
        const chunks=[];res.on('data',v=>chunks.push(v));res.once('end',()=>{
          try{done({http:res.statusCode,body:JSON.parse(Buffer.concat(chunks).toString('utf8'))});}catch{fail(new Error('HTTP response schema'));}});});
      req.once('error',fail);req.setTimeout(12000,()=>req.destroy(new Error('HTTP test deadline')));req.end(payload);
    });
    events.push({path,http:result.http,milliseconds:performance.now()-start,code:result.body.code??null});return result;
  };
  const profile=(id=owner)=>sql(game,d=>JSON.parse(d.prepare('SELECT profile_json FROM game_profiles WHERE account_id=?').get(id).profile_json));
  const logical=()=>sql(game,d=>Object.fromEntries(d.prepare("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").all().map(r=>[r.name,d.prepare(`SELECT * FROM "${r.name}"`).all()])));
  const refresh=async(id=owner)=>{const response=await call('/internal/native/profile',{account_id:id,native_database_id:profile(id).native_database_id});assert.equal(response.http,200,JSON.stringify(response.body));return response.body;};
  function stamp(fresh,expected){
    const dir=realpathSync(fresh.fixture_dir),allowed=realpathSync(options.fixture_root),part=relative(allowed,dir);assert.ok(part&&!part.startsWith('..')&&!isAbsolute(part));
    const files=Object.fromEntries(['manifest.json','profile-input.json','p04m-pool.json','p06t-ammunition.json','p06t-ammo-loss.json'].map(name=>[name,JSON.parse(readFileSync(join(dir,name)))]));
    const manifest=files['manifest.json'],p=files['profile-input.json'],pool=files['p04m-pool.json'],mixed=files['p06t-ammunition.json'],loss=files['p06t-ammo-loss.json'];
    assert.equal(p.account_id,fresh.account_id);assert.equal(p.native_database_id,fresh.native_database_id);assert.equal(p.snapshot_revision,expected);assert.equal(manifest.snapshot_revision,expected);
    assert.equal(hash(readFileSync(join(dir,'profile-input.json'))),manifest.profile_sha256);
    const state=readFileSync(join(dir,'state.bin')),entry=manifest.files.find(x=>x.file==='state.bin');assert.equal(entry.sha256,hash(state));assert.equal(entry.bytes,state.length);
    for(const c of[pool,mixed,loss]){assert.equal(c.account_id,fresh.account_id);assert.equal(c.native_database_id,fresh.native_database_id);assert.equal(c.revision,expected);assert.equal(c.state_sha256,hash(state));}
    return {native_state_sha256:hash(state),owner_source_sha256:manifest.source_bundle_sha256,catalog_sha256:manifest.research_catalog_sha256,
      pool_registry_sha256:pool.registry_sha256,mixed_policy_sha256:mixed.policy_sha256,shell_catalog_sha256:mixed.shell_catalog_sha256,terminal_policy_sha256:MIXED_TERMINAL_SHA256,loss_policy_sha256:loss.policy_sha256,loss_companion_sha256:hash(readFileSync(join(dir,'p06t-ammo-loss.json')))};
  }
  const request=(fresh,expected,native=1)=>({version:4,contract:LOSS_CONTRACT,operation:'select',account_id:fresh.account_id,native_database_id:fresh.native_database_id,
    run_id:SEED.run_id,expected_revision:expected,native_inventory_id:native,projection_stamp:stamp(fresh,expected)});
  const save=(name,data)=>writeFileSync(join(EVIDENCE,name),JSON.stringify({status:'PASS_ACTUAL_HTTP_SQLITE',native:'NOT_RUN',wrapper:false,source_database_unchanged:true,new_grants:0,events,...data},null,2)+'\n',{flag:'wx'});
  return {bridge,call,profile,logical,refresh,request,save,owner,other,options,game,users,password};
}

test('actual authenticated adapter branch selects current projection and rejects stale cached hash after owned garage mutation',{timeout:180000},async t=>{
  const s=await setup(t);for(const user of s.users)assert.equal((await s.call('/internal/native/login',{email:user.email,password:s.password})).http,200);
  let expected=s.profile().snapshot_revision;const old=await s.refresh();const initial=s.request(old,expected);const before=s.logical();
  const ready=await s.call('/internal/native/room-selection-loss',initial);assert.equal(ready.http,200,JSON.stringify(ready.body));assert.deepEqual(ready.body.frozen.loadout.ammunition.map(x=>x.count),[0,4,10]);assert.deepEqual(s.logical(),before);
  assert.equal((await s.call('/internal/native/room-selection-loss',initial,{authorization:token()})).http,403);
  assert.equal((await s.call('/internal/native/room-selection-loss',initial,{headers:{Origin:'https://forbidden.example.test'}})).http,403);
  assert.equal((await s.call('/internal/native/room-selection-loss',initial,{headers:{Host:`localhost:${s.bridge.port}`}})).http,403);
  assert.equal((await s.call('/internal/native/room-selection-loss',{...initial,native_database_id:s.profile(s.other).native_database_id})).http,403);
  assert.equal((await s.call('/internal/native/room-selection-loss',{...initial,account_id:s.other,native_database_id:s.profile(s.other).native_database_id})).http,403);
  assert.equal((await s.call('/internal/native/room-selection-loss',initial,{raw:'x'.repeat(3073)})).http,413);
  assert.equal((await s.call('/internal/native/room-selection-loss',{...initial,arbitrary_path:'C:/untrusted'})).http,400);
  const poisoned=structuredClone(initial);poisoned.projection_stamp.shell_catalog_sha256='0'.repeat(64);
  assert.equal((await s.call('/internal/native/room-selection-loss',poisoned)).body.code,'SOURCE_STAMP_MISMATCH');
  assert.equal((await s.call('/internal/native/room-selection-loss',{...initial,version:2})).http,400);
  const duplicate=JSON.stringify(initial).replace('\"version\":4','\"version\":4,\"version\":4');
  assert.notEqual(duplicate,JSON.stringify(initial));assert.notEqual((await s.call('/internal/native/room-selection-loss',initial,{raw:duplicate})).http,200);
  assert.deepEqual(s.logical(),before);
  const changed=await s.call('/internal/native/ammo',{account_id:s.owner,native_database_id:s.profile().native_database_id,
    command_key:'selection-http:actual-owned-layout',expected_revision:expected,wire_revision:1,layout:[5,1,6,2570,0,2826,3,3082,11,6,0,0,0,0,0,0]});
  assert.equal(changed.http,200,JSON.stringify(changed.body));assert.equal(changed.body.status,'serviced');expected=s.profile().snapshot_revision;
  assert.equal((await s.call('/internal/native/room-selection-loss',initial)).body.code,'STALE_REVISION');
  const mixedStamp={...initial,expected_revision:expected};assert.equal((await s.call('/internal/native/room-selection-loss',mixedStamp)).body.code,'SOURCE_STAMP_MISMATCH');
  const fresh=await s.refresh();const current=s.request(fresh,expected);assert.notEqual(current.projection_stamp.native_state_sha256,initial.projection_stamp.native_state_sha256);
  assert.throws(()=>s.request(fresh,expected-1));const final=await s.call('/internal/native/room-selection-loss',current);assert.equal(final.http,200,JSON.stringify(final.body));
  assert.deepEqual(final.body.frozen.loadout.ammunition.map(x=>x.count),[0,3,11]);
  const oldDTO=await s.call('/internal/native/battle',{version:4,contract:LOSS_CONTRACT,operation:'inspect',account_id:s.other,native_database_id:s.profile(s.other).native_database_id,
    command_key:'selection-http:old-inspect',expected_revision:s.profile(s.other).snapshot_revision,run_id:initial.run_id});
  assert.equal(oldDTO.http,200);assert.equal(oldDTO.body.version,4);assert.equal(oldDTO.body.status,'inspected');
  sql(s.game,d=>d.prepare('DELETE FROM battle_ammo_loss_owner WHERE account_id=?').run(s.owner));const beforeAbsent=s.logical();
  const absent=await s.call('/internal/native/room-selection-loss',current);assert.equal(absent.http,409);assert.equal(absent.body.code,'AMMO_LOSS_POLICY_REQUIRED');
  assert.equal(sql(s.game,d=>d.prepare('SELECT count(*) AS n FROM battle_ammo_loss_owner WHERE account_id=?').get(s.owner).n),0);
  assert.deepEqual(s.logical(),beforeAbsent,'No selection activation, reserve, revision or command ledger write');
  s.save('http-current-and-guards.json',{initial,current,ready:ready.body,final:final.body});
});

test('room selection mode absent keeps old endpoint behavior and adds no automatic activation',{timeout:90000},async t=>{
  const s=await setup(t,{enabled:false});const fresh=await s.refresh();const request=s.request(fresh,s.profile().snapshot_revision),before=s.logical();
  assert.equal((await s.call('/internal/native/room-selection-loss',request)).http,404);assert.deepEqual(s.logical(),before);
  s.save('http-mode-absent.json',{});
});

test('same actual adapter branch bounds a stalled owned worker before its scoped outer deadline',{timeout:90000},async t=>{
  const s=await setup(t,{view:'view-slow01'});const fresh=await s.refresh();const request=s.request(fresh,s.profile().snapshot_revision),before=s.logical();
  const start=performance.now();const response=await s.call('/internal/native/room-selection-loss',request);const milliseconds=performance.now()-start;
  assert.equal(response.http,503);assert.ok(milliseconds>=6500&&milliseconds<9500,`actual worker deadline ${milliseconds}`);assert.deepEqual(s.logical(),before);
  s.save('http-worker-timeout.json',{fault_injection:'trusted test worker stalls before invoking actual read; no ownership success fabricated',milliseconds});
});
