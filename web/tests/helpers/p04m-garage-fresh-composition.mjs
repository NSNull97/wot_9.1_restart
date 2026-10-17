/** Ordinary self-orchestrated Cargo39 controller. No ignored production fallback.
 * Real Config/Session/Job -> private HTTP factory -> SQLite -> Fresh. All actual
 * execution is deferred until coherent tracked promotion/canonical Root gate. */
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {spawn,spawnSync,execFileSync} from 'node:child_process';
import {createServer,request} from 'node:http';
import {existsSync,readFileSync,writeFileSync,openSync,closeSync,readdirSync,statSync} from 'node:fs';
import {resolve,join,relative,isAbsolute,dirname,basename} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {localSpelling,plain,readJson,keys,targetGuard,write} from './p08c-late-result-composition.mjs';
import {sourceContext,SHORT_ROOT} from './p04m-garage-source-context.mjs';
import {sha,snapshot,unchanged,noReservations,mutation,nativeUpdate,authenticated} from './p04m-garage-sql-barriers.mjs';
const ROOT=resolve(dirname(localSpelling(fileURLToPath(import.meta.url))),'../../..');
const TEST='gateway091::shared::server::garage_fresh_composition_tests::p04m_garage_fresh39_actual_http_sqlite';
const HOLD_TEST='gateway091::shared::server::garage_fresh_composition_tests::p04m_garage_fresh39_hold5_actual_http_sqlite';
const SCOPES=['server','tools','client_patch','web/src','tests','web/tests'];
const COMPILED=['server/gateway/src/shared/garage_fresh_composition_tests.rs','web/tests/helpers/p04m-garage-fresh-composition.mjs','web/tests/helpers/p04m-garage-sql-barriers.mjs','web/tests/helpers/p04m-garage-source-context.mjs','web/tests/helpers/p08c-late-result-composition.mjs','tests/helpers/p04m_garage_fresh_seed.py','tests/helpers/p04m_garage_fresh_source.py','server/gateway/src/account/ammo_session.rs','server/gateway/src/account/ammo_session_fresh.rs','server/gateway/src/shared/mod.rs'];
function within(root,p){const r=relative(root,p);assert.ok(r&&!r.startsWith('..')&&!isAbsolute(r));return p;}
function sourceGuard(g){
 keys(g,['schema','full_gate','head','files','parent_pid','target_dir','build_output','allocation','compiled_files','test_executable','test_name']);
 assert.equal(g.schema,g.test_name===HOLD_TEST?'p04m-garage-hold5-fresh39-parent-in-progress.v1':'p04m-garage-fresh39-parent-in-progress.v1');assert.equal(g.full_gate,'PENDING_PARENT_FULL_GATE');assert.equal(g.parent_pid,process.ppid);assert.ok(g.test_name===TEST||g.test_name===HOLD_TEST);assert.equal(ROOT,resolve(SHORT_ROOT));
 const git=a=>execFileSync('git',a,{cwd:ROOT,encoding:'utf8',windowsHide:true,maxBuffer:4*1024*1024});assert.equal(git(['rev-parse','HEAD']).trim(),g.head);assert.match(g.head,/^[0-9a-f]{40}$/);assert.equal(git(['status','--porcelain','--untracked-files=all','--',...SCOPES]),'');
 const names=git(['ls-files','-z','--',...SCOPES]).split('\0').filter(Boolean).sort();assert.deepEqual(Object.keys(g.files).sort(),names);for(const n of names)assert.equal(sha(readFileSync(within(ROOT,plain(join(ROOT,n))))),g.files[n]);
 assert.deepEqual(Object.keys(g.compiled_files).sort(),[...COMPILED].sort());for(const n of COMPILED)assert.equal(g.files[n],g.compiled_files[n],n);assert.equal(sha(readFileSync(fileURLToPath(import.meta.url))),g.compiled_files['web/tests/helpers/p04m-garage-fresh-composition.mjs']);return targetGuard(g);
}
function launchChild(executable,control,output,prefix,testName){
 let out,err,owned,closed,timer,spawnError,cleaning;
 async function cleanup(){
  if(cleaning)return cleaning;
  cleaning=(async()=>{clearTimeout(timer);if(owned&&closed){if(owned.exitCode===null&&owned.signalCode===null)owned.kill('SIGKILL');await closed;}try{if(out!==undefined){closeSync(out);out=undefined;}}finally{if(err!==undefined){closeSync(err);err=undefined;}}})();return cleaning;
 }
 let promise;
 try{
  out=openSync(prefix+'.stdout.log','wx');err=openSync(prefix+'.stderr.log','wx');
  owned=spawn(executable,['--exact',testName,'--nocapture','--test-threads=1'],{cwd:ROOT,windowsHide:true,env:{...process.env,P04M_GARAGE_COMPOSITION_CONTROL:control,P04M_GARAGE_COMPOSITION_OUTPUT:output},stdio:['ignore',out,err]});
  closed=new Promise(done=>{owned.once('error',e=>{spawnError=e;});owned.once('close',(code,signal)=>done({code,signal}));});
  promise=(async()=>{try{const timeout=new Promise((_,fail)=>{timer=setTimeout(()=>fail(new Error('own39 Rust deadline')),180000);});const r=await Promise.race([closed,timeout]);if(spawnError)throw spawnError;assert.equal(r.signal,null);assert.equal(r.code,0,'Actual Rust39 failed; retained private logs');return readJson(output,65536);}finally{await cleanup();}})();
 }catch(e){promise=(async()=>{await cleanup();throw e;})();}
 promise.catch(()=>{});return{promise,stop:cleanup};
}
async function closeOwnServer(s){if(!s)return;await new Promise((done,fail)=>{s.close(e=>e?fail(e):done());s.closeAllConnections?.();});}
async function proxyTo(port){
 const counts={login:0,battle:0,battle_success:0,ammo:0,ammo_success:0,ammo_fault503:0,profile:0,profile_success:0,profile_fault503:0,other:0};
 const server=createServer((incoming,outgoing)=>{
  const route=incoming.url,kind=route==='/internal/native/login'?'login':route==='/internal/native/battle'?'battle':route==='/internal/native/ammo'?'ammo':route==='/internal/native/profile'?'profile':'other';counts[kind]++;
  if(incoming.method!=='POST'||kind==='other'){outgoing.writeHead(400,{'Content-Length':'0','Connection':'close'});outgoing.end();return;}
  let bytes=0,parts=[];incoming.on('data',part=>{bytes+=part.length;if(bytes>65536){incoming.destroy(new Error('closed39 request budget'));return;}parts.push(part);});
  incoming.on('end',()=>{
   if(kind==='ammo'&&counts.ammo===3&&counts.ammo_fault503===0){
    // Actual bad HTTP outcome for the third real Job, not forwarded to SQL.
    // No response/Fresh DTO or native callback is synthesized.
    counts.ammo_fault503++;const b=Buffer.from('{"error":"authored_mutation_transport_failure_before_forward"}');outgoing.writeHead(503,{'Content-Type':'application/json','Content-Length':String(b.length),'Connection':'close'});outgoing.end(b);return;
   }
   if(kind==='profile'&&counts.ammo_success===1&&counts.profile_fault503===0){
    // Explicit AUTHORED transient read failure, never a fake Fresh/success/body.
    counts.profile_fault503++;const b=Buffer.from('{"error":"authored_transient_read_failure"}');outgoing.writeHead(503,{'Content-Type':'application/json','Content-Length':String(b.length),'Connection':'close'});outgoing.end(b);return;
   }
   const body=Buffer.concat(parts);parts=[];const req=request({hostname:'127.0.0.1',port,path:route,method:'POST',headers:{Authorization:incoming.headers.authorization,'Content-Type':'application/json','Content-Length':String(body.length),'Connection':'close'}},res=>{
    let n=0,fragments=[];res.on('data',b=>{n+=b.length;if(n>65536){req.destroy(new Error('closed39 response budget'));return;}fragments.push(b);});
    res.once('end',()=>{const raw=Buffer.concat(fragments);if(res.statusCode===200){if(kind==='battle')counts.battle_success++;if(kind==='ammo')counts.ammo_success++;if(kind==='profile')counts.profile_success++;}outgoing.writeHead(res.statusCode,{'Content-Type':'application/json','Content-Length':String(raw.length),'Connection':'close'});outgoing.end(raw);});
   });req.once('error',()=>{if(!outgoing.headersSent)outgoing.writeHead(502,{'Content-Length':'0','Connection':'close'});outgoing.end();});req.setTimeout(22000,()=>req.destroy(new Error('own39 forward timeout')));req.end(body);
  });
 });
 await new Promise((done,fail)=>{server.once('error',fail);server.listen(0,'127.0.0.1',done);});return{server,port:server.address().port,counts};
}
function cachePins(path,fixtureRoot){const dir=plain(path);within(plain(fixtureRoot),dir);const names=readdirSync(dir);assert.ok(names.length>=10&&names.length<=32);const files={};for(const n of names){const p=plain(join(dir,n));assert.equal(dirname(p),dir);assert.ok(statSync(p).isFile()&&statSync(p).size<=1024*1024);files[p]=sha(readFileSync(p));}return files;}
export async function main(args){
 assert.equal(args.length,6);const[mode,guardArg,outArg,bundleArg,originalArg,seedArg]=args;assert.equal(mode,'--parent-full');assert.equal(process.env.PYTHONPATH,undefined);assert.equal(ROOT,resolve(SHORT_ROOT));
 const output=plain(outArg),guard=readJson(guardArg,4*1024*1024),hold5=guard.test_name===HOLD_TEST,base=plain(join(ROOT,'local/test-runs',hold5?'p04m-garage-hold5-fresh39':'p04m-garage-fresh39'));assert.equal(dirname(output),base);assert.match(basename(output),/^run-[0-9]+-[0-9]+$/);assert.equal(plain(guardArg),join(output,'parent-control.json'));
 const executable=sourceGuard(guard),source=sourceContext(1,ROOT,plain(seedArg)),metadata=source.metadata,bundle=plain(bundleArg),original=plain(originalArg);assert.equal(plain(metadata.bundle),bundle);assert.equal(plain(metadata.original),original);const sourceDB=plain(metadata.database),sourceSHA=sha(readFileSync(sourceDB)),contextSHA=sha(readFileSync(seedArg));
 const py=spawnSync('python',['-B','-c','import sys;print(sys.executable)'],{encoding:'utf8',windowsHide:true,timeout:10000});assert.equal(py.status,0);const python=plain(py.stdout.trim());
 const game=join(output,'game.sqlite'),prepared=spawnSync(python,['-B','-X','utf8',join(ROOT,'tests/helpers/p04m_garage_fresh_seed.py'),game,plain(seedArg),hold5?'hold5':'loss4'],{cwd:ROOT,encoding:'utf8',windowsHide:true,timeout:120000});
 writeFileSync(join(output,'seed.stdout.log'),prepared.stdout||'',{flag:'wx'});writeFileSync(join(output,'seed.stderr.log'),prepared.stderr||'',{flag:'wx'});assert.equal(prepared.status,0,'genuine isolated seed failed; retained logs');const seed=readJson(game.replace(/\.sqlite$/,'.json'),65536);for(const k of['new_grants','new_accounts','new_reservations','new_results'])assert.equal(seed[k],0);assert.equal(seed.schema,hold5?'p04m-garage-hold5-fresh39-seed.v1':'p04m-garage-fresh39-seed.v1');assert.equal(seed.writer_version,hold5?5:4);assert.equal(seed.hold_activation,hold5?'ACTUAL_METADATA_ONLY':'NOT_RUN');assert.deepEqual(seed.context_seed,source.context_seed);assert.equal(seed.source_database.sha256,sourceSHA);
 const modules=['game-adapter','security','p04d-crew','p04k-crew','p09e-research','p08b-battle','p04m-pool','p06t-mixed','p06t-ammo-loss','p08b-owner-hold'];const[{createIdentityBridge},security,crew,barracks,research,battle,pool,mixed,loss,hold]=await Promise.all(modules.map(n=>import(pathToFileURL(join(ROOT,`web/src/${n}.mjs`)))));
 const accounts=seed.profiles.map(p=>p.account_id);assert.deepEqual(accounts,['80ad3bc2-476e-4fbd-899d-a4679ea167d2','633ad84f-f33f-4aab-bacd-421f31a93bae']);const identity=join(output,'identity.sqlite'),tokenFile=join(output,'identity.token'),password=security.token(),passwordHash=await security.hashPassword(password);writeFileSync(tokenFile,security.token(),{flag:'wx',mode:0o600});
 const users=seed.profiles.map((p,i)=>({account_id:p.account_id,email:`garage-composition39-${i}@example.test`,password}));let db=new DatabaseSync(identity);try{db.exec('PRAGMA user_version=2;CREATE TABLE users(id TEXT PRIMARY KEY,username TEXT,display_nickname TEXT,email TEXT,password_hash TEXT,created_at INTEGER)');for(let i=0;i<2;i++){const p=seed.profiles[i];db.prepare('INSERT INTO users VALUES(?,?,?,?,?,?)').run(p.account_id,p.username.toLowerCase(),p.username,users[i].email,passwordHash,p.created_at_ms);}}finally{db.close();}
 const native=plain(join(bundle,'content/inputs/native-ms1.blob'));db=new DatabaseSync(game);try{db.prepare('INSERT INTO game_meta VALUES(?,?)ON CONFLICT(key)DO UPDATE SET value=excluded.value').run('native_descriptors_sha256',sha(readFileSync(native)));}finally{db.close();}
 const options={version:1,port:0,web_database:identity,game_database:game,fixture_root:join(output,'fixtures'),native_descriptors:native,python_executable:python,token_file:tokenFile,
  ammunition_service:{version:1,bundle_root:bundle,original_root:original,account_id:accounts[0],grant:{grant_id:'p09d-test-depot-v1',quantity_each:100}},
  crew_service:{version:1,policy_sha256:crew.CREW_POLICY_SHA256},crew_transfer:{version:1,policy_sha256:crew.TRANSFER_POLICY_SHA256},crew_cross_vehicle:{version:1,policy_sha256:crew.CROSS_CREW_POLICY_SHA256},crew_roster_recruitment:{version:1,policy_sha256:crew.ROSTER_CREW_POLICY_SHA256},crew_progression:{version:1,policy_sha256:crew.PROGRESSION_CREW_POLICY_SHA256},crew_dismissal:{version:1,policy_sha256:crew.DISMISSAL_CREW_POLICY_SHA256},crew_barracks_recruitment:{version:1,policy_sha256:barracks.BARRACKS_CREW_POLICY_SHA256},research_service:{version:1,policy_sha256:research.RESEARCH_POLICY_SHA256},battle_service:{version:1,policy_sha256:battle.BATTLE_POLICY_SHA256,accounts},pool_service:{version:1,policy_sha256:pool.POOL_POLICY_SHA256,accounts},mixed_service:{version:2,policy_sha256:mixed.MIXED_POLICY_SHA256,accounts,shell_catalog:join(ROOT,'tests/fixtures/p06t-shell-catalog.json'),terminal_policy:join(ROOT,'tests/fixtures/p06t-device-policy.json')},ammo_loss_service:{version:4,contract:loss.LOSS_CONTRACT,policy_sha256:loss.LOSS_POLICY_SHA256,accounts}};
 if(hold5)options.owner_hold_service={version:5,contract:hold.HOLD_CONTRACT,policy_sha256:hold.HOLD_POLICY_SHA256,accounts};
 let bridge,proxy,job,settled=false,childError;const initial=snapshot(game,accounts);noReservations(initial);write(join(output,'initial-sql.json'),initial);
 async function until(check,code){const end=performance.now()+45000;while(!check()){if(settled)throw childError||new Error('Rust39 ended before '+code);assert.ok(performance.now()<end,code);await new Promise(done=>setTimeout(done,10));}}
 async function barrier(name,check){await until(()=>existsSync(join(output,name+'.ready.json')),'missing '+name);const v=readJson(join(output,name+'.ready.json'),65536);const state=snapshot(game,accounts);await check(v,state);write(join(output,name+'.sql.json'),{summary:v,...state,proxy:{...proxy.counts}});writeFileSync(join(output,name+'.go'),'GO\n',{flag:'wx'});return{summary:v,sql:state};}
 try{
  bridge=await createIdentityBridge(options);proxy=await proxyTo(bridge.port);const cfg=join(output,'config.private.json'),control=join(output,'phase-control.private.json');const config={login_bind:'127.0.0.1:26139',base_bind:'127.0.0.1:26140',identity_endpoint:`127.0.0.1:${proxy.port}`,identity_token_file:tokenFile,local_root:join(ROOT,'local'),session_duration_seconds:600,battle_players:2};
  for(const k of['ammunition_service','crew_service','crew_transfer','crew_cross_vehicle','crew_roster_recruitment','crew_progression','crew_dismissal','crew_barracks_recruitment','research_service','profile13_battle','p04m_pool','p06t_mixed_ammo','p06t_ammo_rack_detonation','visibility_v1'])config[k]=true;
  if(hold5)config.p08b_owner_battle_hold=true;
  write(cfg,config);write(control,{schema:hold5?'p04m-garage-hold5-fresh39.v1':'p04m-garage-fresh39.v1',phase:hold5?'actual_hold5_command_fresh_pressure':'actual_command_fresh_pressure',config:cfg,users,barrier:output});job=launchChild(executable,control,join(output,'phase.json'),join(output,'phase'),guard.test_name);job.promise.then(()=>{settled=true;},e=>{settled=true;childError=e;});
  const auth=await barrier('after-auth',(v,s)=>{authenticated(initial,s,hold5?5:4);assert.equal(v.wire_revision,1);assert.equal(v.phase,'Account');assert.equal(proxy.counts.login,1);assert.equal(proxy.counts.battle,hold5?2:1);assert.equal(proxy.counts.battle_success,hold5?2:1);assert.equal(proxy.counts.profile,1);assert.equal(proxy.counts.profile_success,1);assert.equal(proxy.counts.ammo,0);assert.equal(s.profiles[0].revision,initial.profiles[0].revision+1);assert.deepEqual(s.profiles[1],initial.profiles[1]);noReservations(s);});
  const oldCache=cachePins(auth.summary.fixture_dir,options.fixture_root);
  const committed=await barrier('known-retained',async(v,s)=>{await until(()=>proxy.counts.profile_success===2,'post-mutation actual Fresh retry completed');mutation(auth.sql,s,1);assert.equal(proxy.counts.ammo,1);assert.equal(proxy.counts.ammo_success,1);assert.equal(proxy.counts.profile_fault503,1);assert.equal(proxy.counts.profile,3);assert.equal(proxy.counts.profile_success,2);assert.equal(proxy.counts.battle,hold5?2:1);assert.deepEqual(v.known,[auth.summary.revision+1,2,true]);assert.ok(v.fresh_attempts>=2);assert.equal(v.session.revision,auth.summary.revision);assert.equal(v.session.wire_revision,1);assert.equal(v.session.fixture_dir,auth.summary.fixture_dir);assert.equal(v.session.outbox,127);});
  await barrier('pressure-still-retained',(v,s)=>{unchanged(committed.sql,s);assert.equal(v.revision,auth.summary.revision);assert.equal(v.outbox,127);assert.equal(proxy.counts.ammo,1);});
  const first=await barrier('first-published',(v,s)=>{unchanged(committed.sql,s);nativeUpdate(s,v,0);assert.equal(v.session.account_epoch,auth.summary.account_epoch);assert.notEqual(v.session.fixture_dir,auth.summary.fixture_dir);assert.equal(v.session.outbox,0);assert.equal(v.session.window,0);});
  const final=await barrier('second-published',(v,s)=>{mutation(auth.sql,s,2);nativeUpdate(s,v,1);assert.equal(v.session.account_epoch,auth.summary.account_epoch);assert.notEqual(v.session.fixture_dir,first.summary.session.fixture_dir);assert.equal(proxy.counts.ammo,2);assert.equal(proxy.counts.ammo_success,2);assert.equal(proxy.counts.profile_fault503,1);assert.equal(proxy.counts.profile,4);assert.equal(proxy.counts.profile_success,3);assert.equal(proxy.counts.battle,hold5?2:1);assert.equal(proxy.counts.battle_success,hold5?2:1);assert.equal(proxy.counts.login,1);assert.equal(proxy.counts.other,0);});
  await barrier('unknown-foreign-retired',(v,s)=>{unchanged(final.sql,s);mutation(auth.sql,s,2);assert.equal(v.foreign_recipient_unchanged,true);assert.equal(v.same_sid,true);assert.equal(v.different_account_epoch,true);assert.equal(v.observer_cleared,true);assert.equal(v.callbacks,0);assert.equal(v.session.phase,'Account');assert.equal(proxy.counts.ammo,3);assert.equal(proxy.counts.ammo_success,2);assert.equal(proxy.counts.ammo_fault503,1);assert.equal(proxy.counts.profile,4);assert.equal(proxy.counts.profile_success,3);assert.equal(proxy.counts.other,0);});
  const result=await job.promise;assert.equal(result.status,hold5?'PASS_ACTUAL_GARAGE_HOLD5_JOB_HTTP_SQLITE_FRESH':'PASS_ACTUAL_GARAGE_JOB_HTTP_SQLITE_FRESH');assert.equal(result.writer_version,hold5?5:4);assert.equal(result.actual_login_inspect5,hold5);assert.equal(result.actual_commands,2);assert.equal(result.actual_http_attempts,3);assert.equal(result.unknown_receiver_foreign_channel_preserved,true);for(const[file,pin]of Object.entries(oldCache))assert.equal(sha(readFileSync(file)),pin,'old immutable cache was rewritten');unchanged(final.sql,snapshot(game,accounts));assert.equal(sha(readFileSync(sourceDB)),sourceSHA);assert.equal(sha(readFileSync(seedArg)),contextSHA);sourceGuard(guard);
  write(join(output,'result.json'),{...result,parent_full_gate:'PENDING_PARENT_FULL_GATE',head:guard.head,executable_sha256:sha(readFileSync(executable)),source_context:source.context_seed,source_database_sha256:sourceSHA,observed_http:{...proxy.counts},actual_sql_mutations:2,actual_writer_contract:hold5?hold.HOLD_CONTRACT:loss.LOSS_CONTRACT,third_mutation_not_forwarded:true,foreign_recipient_unchanged_on_actual_unknown_http:true,authentication_owned_data_unchanged:true,authentication_raw_grant_inventory_rows_unchanged:true,readonly_retry_after_authored503:true,observer_pressure_retained:true,source_database_unchanged:true,initial_cache_immutable:true,source_owned_context_owners:2,actual_authenticated_mutation_owners:1,gameplay_udp:'NOT_RUN',native_client:'NOT_RUN',latency_cause:'UNKNOWN_NOT_ASSERTED'});
 }finally{
  if(job){await job.stop();await job.promise.catch(()=>{});}if(proxy)await closeOwnServer(proxy.server);if(bridge)await bridge.close();assert.equal(sha(readFileSync(sourceDB)),sourceSHA);assert.equal(sha(readFileSync(seedArg)),contextSHA);
 }
}
if(process.argv[1]&&localSpelling(process.argv[1])===localSpelling(fileURLToPath(import.meta.url)))main(process.argv.slice(2)).catch(e=>{console.error(e.stack||e);process.exitCode=1;});
