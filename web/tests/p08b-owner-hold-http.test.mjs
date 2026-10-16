/** Actual staged adapter branch -> own Python reader -> disposable real SQLite. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { request as httpRequest } from 'node:http';
import { readFileSync,writeFileSync,copyFileSync,mkdirSync,realpathSync } from 'node:fs';
import { resolve,join,relative,isAbsolute,delimiter } from 'node:path';
import { pathToFileURL } from 'node:url';
const ROOT='D:/WoT_9.1_Server';
const STAGE=ROOT;
const SOURCE=JSON.parse(readFileSync(process.env.P08B_OWNER_HOLD_SEED));
const EVIDENCE=resolve(process.env.P08B_OWNER_HOLD_HTTP_EVIDENCE);mkdirSync(EVIDENCE,{recursive:true});
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

async function setup(t,{enabled=true,view='view01'}={}){
  const directory=testDirectory(),game=join(directory,'game.sqlite'),identity=join(directory,'identity.sqlite');
  const sourceHash=hash(readFileSync(SOURCE.database));
  const backup=spawnSync(python,['-B','-X','utf8',join(ROOT,'tests/helpers/p08b_owner_hold_http_seed.py'),game],{cwd:directory,env:cleanEnv,encoding:'utf8',windowsHide:true,timeout:90000});
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
    room_selection_service:{version:1,schema:'p10b-owned-selection.v1',accounts:[owner]},
    room_selection_loss_service:{version:4,schema:'p10b-owned-selection-loss.v1',contract:LOSS_CONTRACT,policy_sha256:LOSS_POLICY_SHA256,accounts:[owner]},
    ammo_loss_service:{version:4,contract:LOSS_CONTRACT,policy_sha256:LOSS_POLICY_SHA256,accounts:[owner,other]},
    ...(enabled?{owner_hold_service:{version:5,contract:'p08b-owner-battle-hold.v1',policy_sha256:'98cdc5d657e4cdf30225c26913f2c70a89865de9ae2bb97704fa4b623efd806e',accounts:[owner]}}:{})};
  const {createIdentityBridge}=await import(pathToFileURL(join(STAGE,'web/src/game-adapter.mjs')));
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
  return {get bridge(){return bridge;},call,profile,logical,refresh,request,save,owner,other,options,game,users,password,reopen:async config=>{if(bridge)await bridge.close();bridge=null;bridge=await createIdentityBridge(config);}};
}


const HOLD='p08b-owner-battle-hold.v1';
const canon=v=>JSON.stringify((function sort(x){return Array.isArray(x)?x.map(sort):x&&typeof x==='object'?Object.fromEntries(Object.keys(x).sort().map(k=>[k,sort(x[k])])):x;})(v));
test('actual selected factory5 login/held read/garage denial/one final/garage works/archives/reopen guard; legacy owner stays4',{timeout:240000},async t=>{
 const s=await setup(t);const call=(path,r,opts)=>s.call('/internal/native/'+path,r,opts);let serial=0;const run='e6ef9b6e-1316-4d78-9f6a-18659b03b231';
 const battle=(op,extra={})=>({version:5,contract:HOLD,operation:op,account_id:s.owner,native_database_id:s.profile().native_database_id,command_key:'hold-http:'+ ++serial,expected_revision:s.profile().snapshot_revision,run_id:run,...(['admit','finish'].includes(op)?{battle_id:run+':9007199254740993',native_inventory_id:1}:{}),...extra});
 const garage=(layout)=>({account_id:s.owner,native_database_id:s.profile().native_database_id,command_key:'hold-http:garage:'+ ++serial,expected_revision:s.profile().snapshot_revision,wire_revision:1,layout});
 for(const u of s.users)assert.equal((await call('login',{email:u.email,password:s.password})).http,200);
 const first=await s.refresh(),dir=first.fixture_dir;assert.match(dir,/p08b-hold-v1/);const comp=JSON.parse(readFileSync(join(dir,'p08b-owner-hold.json')));assert.equal(comp.version,5);assert.equal(comp.state_sha256,hash(readFileSync(join(dir,'state.bin'))));
 let r=battle('admit');const admitted=await call('battle',r);assert.equal(admitted.http,200,JSON.stringify(admitted.body));assert.equal(admitted.body.status,'admitted');const receipt=admitted.body.reservation,f=receipt.frozen.loss_frozen.loadout;
 const before=s.logical();const inspected=await call('battle',battle('inspect'));assert.equal(inspected.body.reservation.status,'active');assert.deepEqual(s.logical(),before);
 const active=await s.refresh();const activeComp=JSON.parse(readFileSync(join(active.fixture_dir,'p08b-owner-hold.json')));assert.equal(activeComp.revision,s.profile().snapshot_revision);
 const selected4=s.request(active,s.profile().snapshot_revision);
 const selected2={...selected4,version:1};delete selected2.contract;
 selected2.projection_stamp={...selected4.projection_stamp};delete selected2.projection_stamp.loss_policy_sha256;delete selected2.projection_stamp.loss_companion_sha256;
 const selection2=await import(pathToFileURL(join(ROOT,'web/src/p10b-selection.mjs'))),selection4=await import(pathToFileURL(join(ROOT,'web/src/p10b-selection-loss.mjs')));
 selection2.validateSelectionRequest(selected2,s.owner,s.profile().native_database_id);selection4.validateLossSelectionRequest(selected4,s.owner,s.profile().native_database_id);
 await t.test('selected Hold5 explicitly refuses existing selection2 without SQL/worker fallback',async()=>{
   const unchanged=s.logical(),out=await s.call('/internal/native/room-selection',selected2);assert.equal(out.http,403);assert.deepEqual(out.body,{error:'forbidden'});assert.deepEqual(s.logical(),unchanged);
 });
 await t.test('selected Hold5 explicitly refuses existing selection4 without SQL/worker fallback',async()=>{
   const unchanged=s.logical(),out=await s.call('/internal/native/room-selection-loss',selected4);assert.equal(out.http,403);assert.deepEqual(out.body,{error:'forbidden'});assert.deepEqual(s.logical(),unchanged);
 });

 for(const[path,layout]of[['ammo',[5,1,6,2570,0,2826,3,3082,10,6,0,0,0,0,0,0]],['crew-transfer',[1,0,-1]]]){const out=await call(path,garage(layout));assert.equal(out.http,200,JSON.stringify(out.body));assert.equal(out.body.status,'rejected');}
 assert.deepEqual(s.logical(),before);
 assert.equal((await call('battle',{...battle('inspect'),version:4,contract:LOSS_CONTRACT})).http,400);
 assert.equal((await call('battle',battle('inspect'),{authorization:token()})).http,403);
 assert.equal((await call('battle',battle('inspect'),{headers:{Origin:'https://bad.example.test'}})).http,403);
 const policy=JSON.parse(readFileSync(join(ROOT,'tests/fixtures/p06t-device-policy.json'))),p=policy.profiles.find(x=>x.kind===f.kind);
 const state={policy_revision:policy.policy_revision,roster_size:2,crew_active:true,crew:f.crew_ids.map(crew_id=>({crew_id,alive:true})),devices:p.devices.map(x=>({extra_index:x.extra_index,max_health:x.max_health,health:x.max_health})),fire:{active:false,ticks:0,damage:0},death:{reason:-1,killer_slot:null,tick:0}};
 const own={vehicle_id:0x09100003,account_dbid:s.profile().native_database_id,name:s.profile().username,team:1,type_compact_descr:3329,health:90,shots:0,direct_hits:0,piercings:0,damage_dealt:0,damage_received:0,kills:0,capture_points:0,dropped_capture_points:0,mileage_metres:0,life_time:0,killer_id:0,death_reason:-1,premature_leave:true};
 const peer={...own,vehicle_id:0x09100005,account_dbid:s.profile(s.other).native_database_id,name:s.profile(s.other).username,team:2,premature_leave:false};
 const results={arena_id:9007199254740993n.toString(),arena_type_id:4,created_unix:1792080000,winner_team:2,finish_reason:5,duration_seconds:0,participants:[own,peer],interaction_details:{version:1,policy:'test_lab.authoritative-interactions.v1',spotting_policy:null,rows:[{attacker_vehicle_id:own.vehicle_id,targets:[]},{attacker_vehicle_id:peer.vehicle_id,targets:[]}]}};
 // Keep actual u64 JSON number as text; Node cannot round the arena integer.
 const resultsJSON=canon(results).replace('"arena_id":"9007199254740993"','"arena_id":9007199254740993');
 const link={account_id:s.owner,native_database_id:s.profile().native_database_id,run_id:run,battle_id:receipt.battle_id,reservation_id:receipt.reservation_id,native_inventory_id:1,vehicle_inventory_id:receipt.vehicle_inventory_id,frozen_sha256:receipt.frozen_sha256,source_session_id:11,actor_slot:0,team:1,vehicle_kind:f.kind};
 const ammo=f.ammunition.map(x=>({shell_compact_id:x.shell_compact_id,count:x.count})),zeros=ammo.map(x=>({...x,count:0}));
 const finish=battle('finish',{reservation_id:receipt.reservation_id,remaining_ammunition:ammo,fired_ammunition:zeros,lost_ammunition:zeros,loss_event:null,terminal_hp:90,terminal_state_json:canon(state),reason:'battle_finished',results_json:resultsJSON,source_link:link,departure:{reason:'manual_leave',tick:1001},finalization:{kind:'outcome',tick:1002}});
 const settled=await call('battle',finish);assert.equal(settled.http,200,JSON.stringify(settled.body));assert.equal(settled.body.status,'finished');
 for(const[path,layout]of[['ammo',[5,1,6,2570,0,2826,3,3082,10,6,0,0,0,0,0,0]],['crew-transfer',[1,0,-1]],['crew-transfer',[1,0,1]]]){const out=await call(path,garage(layout));assert.equal(out.http,200,JSON.stringify(out.body));assert.ok(['serviced','transferred'].includes(out.body.status));}
 const q={version:5,contract:HOLD,operation:'query',account_id:s.owner,native_database_id:s.profile().native_database_id,command_key:'hold-http:query',arena_id:'9007199254740993'};
 const found=await call('battle-results',q);assert.equal(found.http,200,JSON.stringify(found.body));assert.equal(found.body.record_contract,'hold-v1');assert.equal(found.body.results_json,resultsJSON);
 const ack=await call('battle-results',{...q,operation:'ack',command_key:'hold-http:ack'});assert.equal(ack.body.acked,true);
 const legacy=await call('battle',{version:4,contract:LOSS_CONTRACT,operation:'inspect',account_id:s.other,native_database_id:s.profile(s.other).native_database_id,command_key:'hold-http:legacy',expected_revision:s.profile(s.other).snapshot_revision,run_id:run});assert.equal(legacy.http,200);assert.equal(legacy.body.version,4);
 const off={...s.options};delete off.owner_hold_service;await assert.rejects(s.reopen(off),/Owner hold/);await s.reopen(s.options);assert.equal((await call('battle-results',q)).body.acked,true);
 s.save('actual-hold5-http.json',{classification:'ACTUAL_HTTP_SQLITE; WORLD_FACTS_AUTHORED; NATIVE_NOT_RUN',admit:admitted.body,finished:settled.body,query:found.body,old_owner_version:legacy.body.version});
});
