/** Actual Config/Job/Capture/Session -> HTTP factory5 -> SQLite composition.
 * This file targets web/tests/helpers after coherent promotion. No ignored
 * module fallback, network UDP/native/Jolt proof or forged World results. */
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { spawn,spawnSync,execFileSync } from 'node:child_process';
import { existsSync,readFileSync,writeFileSync,openSync,closeSync } from 'node:fs';
import { resolve,join,relative,isAbsolute,dirname,basename } from 'node:path';
import { fileURLToPath,pathToFileURL } from 'node:url';
import { localSpelling,plain,readJson,keys,targetGuard,write } from './p08c-late-result-composition.mjs';
import { sha,snapshot,active,assertUnchanged,assertInventoryUnchanged,assertAdmitted,assertHeld,assertHeldRelogin,assertFinal } from './p08b-hold-sql-barriers.mjs';
const HERE=dirname(localSpelling(fileURLToPath(import.meta.url))),ROOT=resolve(HERE,'../../..');
const TEST='gateway091::shared::server::owner_hold_composition_tests::p08b_owner_hold10_actual_http_sqlite';
const SCOPES=['server','tools','client_patch','web/src','tests','web/tests'];
function within(root,path){const r=relative(root,path);assert.ok(r&&!r.startsWith('..')&&!isAbsolute(r));return path;}
function sourceGuard(guard){
  keys(guard,['schema','full_gate','head','files','parent_pid','target_dir','build_output','allocation','compiled_test_source_sha256','compiled_driver_sha256','compiled_common_driver_sha256','compiled_sql_barriers_sha256','test_executable','test_name']);
  assert.equal(guard.schema,'p08b-owner-hold-parent-in-progress.v1');assert.equal(guard.full_gate,'PENDING_PARENT_FULL_GATE');assert.equal(guard.test_name,TEST);assert.equal(guard.parent_pid,process.ppid);assert.match(guard.head,/^[0-9a-f]{40}$/);
  const git=args=>execFileSync('git',args,{cwd:ROOT,encoding:'utf8',windowsHide:true,maxBuffer:4*1024*1024});
  assert.equal(git(['rev-parse','HEAD']).trim(),guard.head);assert.equal(git(['status','--porcelain','--untracked-files=all','--',...SCOPES]),'');
  const names=git(['ls-files','-z','--',...SCOPES]).split('\0').filter(Boolean).sort();assert.deepEqual(Object.keys(guard.files).sort(),names);
  for(const name of names){assert.match(guard.files[name],/^[0-9a-f]{64}$/);assert.equal(sha(readFileSync(within(ROOT,plain(resolve(ROOT,name))))),guard.files[name],name);}
  for(const[path,field]of[['server/gateway/src/shared/owner_hold_composition_tests.rs','compiled_test_source_sha256'],['web/tests/helpers/p08b-owner-hold-composition.mjs','compiled_driver_sha256'],['web/tests/helpers/p08c-late-result-composition.mjs','compiled_common_driver_sha256'],['web/tests/helpers/p08b-hold-sql-barriers.mjs','compiled_sql_barriers_sha256']])assert.equal(guard.files[path],guard[field]);
  assert.equal(sha(readFileSync(plain(fileURLToPath(import.meta.url)))),guard.compiled_driver_sha256);return targetGuard(guard);
}
async function runChild(executable,control,output,prefix){
  let out,err,owned,closed,timer,spawnError;
  try{
    out=openSync(prefix+'.stdout.log','wx');err=openSync(prefix+'.stderr.log','wx');
    owned=spawn(executable,['--exact',TEST,'--nocapture','--test-threads=1'],{cwd:ROOT,windowsHide:true,env:{...process.env,P08B_HOLD_COMPOSITION_CONTROL:control,P08B_HOLD_COMPOSITION_OUTPUT:output},stdio:['ignore',out,err]});
    closed=new Promise(done=>{owned.once('error',e=>{spawnError=e;});owned.once('close',(code,signal)=>done({code,signal}));});
    const timeout=new Promise((_,fail)=>{timer=setTimeout(()=>fail(new Error('Own hold composition test deadline')),180000);});
    const result=await Promise.race([closed,timeout]);if(spawnError)throw spawnError;assert.equal(result.signal,null);assert.equal(result.code,0,'Actual Rust phase failed; retained logs');return readJson(output,65536);
  }finally{
    clearTimeout(timer);if(owned&&closed){if(owned.exitCode===null&&owned.signalCode===null)owned.kill('SIGKILL');await closed;}
    try{if(out!==undefined)closeSync(out);}finally{if(err!==undefined)closeSync(err);}
  }
}
export async function main(args){
  const[mode,guardArgument,outputArgument,bundleArgument,originalArgument,seedArgument]=args;assert.equal(mode,'--parent-full');assert.equal(args.length,6);assert.equal(process.env.PYTHONPATH,undefined);
  const guardPath=plain(guardArgument),output=plain(outputArgument),base=plain(join(ROOT,'local/test-runs/p08b-owner-hold-composition10'));
  assert.equal(dirname(output),base);assert.match(basename(output),/^run-[0-9]+-[0-9]+$/);assert.equal(guardPath,join(output,'parent-control.json'));
  const guard=readJson(guardPath,4*1024*1024),executable=sourceGuard(guard),bundle=plain(bundleArgument),original=plain(originalArgument),sourceSeed=plain(seedArgument);
  assert.equal(sourceSeed,plain(join(ROOT,'local/night-staging/20261016/p10b-selection-http01/seed01/seed.json')));
  const metadata=readJson(sourceSeed,65536),sourceDB=within(plain(join(ROOT,'local')),plain(metadata.database));assert.equal(plain(metadata.bundle),bundle);assert.equal(plain(metadata.original),original);
  const sourceSHA=sha(readFileSync(sourceDB)),metadataSHA=sha(readFileSync(sourceSeed));assert.equal(sourceSHA,'a04216d90e8e9e8b379fc2d34a0fed9f400e373d8d4c591d723bb00a1accc2cf');
  const modules=['game-adapter','security','p04d-crew','p04k-crew','p09e-research','p08b-battle','p04m-pool','p06t-mixed','p06t-ammo-loss','p08b-owner-hold'];
  const[{createIdentityBridge},security,crew,barracks,research,battle,pool,mixed,loss,hold]=await Promise.all(modules.map(n=>import(pathToFileURL(join(ROOT,`web/src/${n}.mjs`)))));
  const py=spawnSync('python',['-B','-c','import sys;print(sys.executable)'],{encoding:'utf8',windowsHide:true});assert.equal(py.status,0,py.stderr);const python=plain(py.stdout.trim());
  const game=join(output,'game.sqlite'),seeded=spawnSync(python,['-B','-X','utf8',join(ROOT,'tests/helpers/p08b_owner_hold_composition_seed.py'),game,sourceSeed],{cwd:ROOT,encoding:'utf8',windowsHide:true,timeout:120000});
  writeFileSync(join(output,'seed.stdout.log'),seeded.stdout||'',{flag:'wx'});writeFileSync(join(output,'seed.stderr.log'),seeded.stderr||'',{flag:'wx'});assert.equal(seeded.status,0,'Actual seed activation failed; retained seed logs');
  const seed=readJson(game.replace(/\.sqlite$/,'.json'),65536);for(const key of['new_grants','new_accounts','new_reservations','new_results'])assert.equal(seed[key],0);assert.equal(seed.source_database.sha256,sourceSHA);assert.equal(seed.source_seed.sha256,metadataSHA);
  const profiles=seed.profiles,accounts=profiles.map(p=>p.account_id);assert.deepEqual(accounts,['80ad3bc2-476e-4fbd-899d-a4679ea167d2','633ad84f-f33f-4aab-bacd-421f31a93bae']);
  const identity=join(output,'identity.sqlite'),tokenFile=join(output,'identity.token'),native=plain(join(bundle,'content/inputs/native-ms1.blob'));
  const password=security.token(),passwordHash=await security.hashPassword(password);writeFileSync(tokenFile,security.token(),{flag:'wx',mode:0o600});
  const users=profiles.map((p,i)=>({account_id:p.account_id,email:`hold-composition-${i}@example.test`,password}));
  let db=new DatabaseSync(identity);try{db.exec('PRAGMA user_version=2;CREATE TABLE users(id TEXT PRIMARY KEY,username TEXT,display_nickname TEXT,email TEXT,password_hash TEXT,created_at INTEGER)');for(let i=0;i<profiles.length;i++){const p=profiles[i];db.prepare('INSERT INTO users VALUES (?,?,?,?,?,?)').run(p.account_id,p.username.toLowerCase(),p.username,users[i].email,passwordHash,p.created_at_ms);}}finally{db.close();}
  db=new DatabaseSync(game);try{db.prepare('INSERT INTO game_meta VALUES (?,?)ON CONFLICT(key)DO UPDATE SET value=excluded.value').run('native_descriptors_sha256',sha(readFileSync(native)));}finally{db.close();}
  const options={version:1,port:0,web_database:identity,game_database:game,fixture_root:join(output,'fixtures'),native_descriptors:native,python_executable:python,token_file:tokenFile,
    ammunition_service:{version:1,bundle_root:bundle,original_root:original,account_id:accounts[0],grant:{grant_id:'p09d-test-depot-v1',quantity_each:100}},
    crew_service:{version:1,policy_sha256:crew.CREW_POLICY_SHA256},crew_transfer:{version:1,policy_sha256:crew.TRANSFER_POLICY_SHA256},crew_cross_vehicle:{version:1,policy_sha256:crew.CROSS_CREW_POLICY_SHA256},crew_roster_recruitment:{version:1,policy_sha256:crew.ROSTER_CREW_POLICY_SHA256},
    crew_progression:{version:1,policy_sha256:crew.PROGRESSION_CREW_POLICY_SHA256},crew_dismissal:{version:1,policy_sha256:crew.DISMISSAL_CREW_POLICY_SHA256},crew_barracks_recruitment:{version:1,policy_sha256:barracks.BARRACKS_CREW_POLICY_SHA256},research_service:{version:1,policy_sha256:research.RESEARCH_POLICY_SHA256},
    battle_service:{version:1,policy_sha256:battle.BATTLE_POLICY_SHA256,accounts},pool_service:{version:1,policy_sha256:pool.POOL_POLICY_SHA256,accounts},mixed_service:{version:2,policy_sha256:mixed.MIXED_POLICY_SHA256,accounts,shell_catalog:join(ROOT,'tests/fixtures/p06t-shell-catalog.json'),terminal_policy:join(ROOT,'tests/fixtures/p06t-device-policy.json')},
    ammo_loss_service:{version:4,contract:loss.LOSS_CONTRACT,policy_sha256:loss.LOSS_POLICY_SHA256,accounts},owner_hold_service:{version:5,contract:hold.HOLD_CONTRACT,policy_sha256:hold.HOLD_POLICY_SHA256,accounts}};
  const initial=snapshot(game,accounts);assert.equal(active(initial).length,0);write(join(output,'initial-sql.json'),initial);
  let bridge,promise,settled=false,childFailure;
  async function barrier(name,check){
    const marker=join(output,name+'.ready.json'),deadline=performance.now()+180000;
    while(!existsSync(marker)){if(settled){if(childFailure)throw childFailure;throw new Error('Rust exited before '+name);}assert.ok(performance.now()<deadline,'Missing SQL checkpoint '+name);await new Promise(done=>setTimeout(done,10));}
    const summary=readJson(marker,65536),current=snapshot(game,accounts);check(summary,current);write(join(output,name+'.sql.json'),{summary,...current});writeFileSync(join(output,name+'.go'),'GO\n',{flag:'wx'});return{summary,sql:current};
  }
  try{
    bridge=await createIdentityBridge(options);const cfg=join(output,'config.private.json'),control=join(output,'control.private.json');
    const config={login_bind:'127.0.0.1:26131',base_bind:'127.0.0.1:26132',identity_endpoint:`127.0.0.1:${bridge.port}`,identity_token_file:tokenFile,local_root:join(ROOT,'local'),session_duration_seconds:600,battle_players:2,p08b_owner_battle_hold:true};
    for(const key of['ammunition_service','crew_service','crew_transfer','crew_cross_vehicle','crew_roster_recruitment','crew_progression','crew_dismissal','crew_barracks_recruitment','research_service','profile13_battle','p04m_pool','p06t_mixed_ammo','visibility_v1','p06t_ammo_rack_detonation'])config[key]=true;
    // Gateway late flag stays false; this fresh predecessor has no old late
    // rows. A historical late reader stays configured independently when used.
    write(cfg,config);const arena='9007199254741193';write(control,{schema:'p08b-owner-hold-composition.v1',phase:'held_relogin_then_outcome',config:cfg,users,barrier:output,arena_id:arena});
    promise=runChild(executable,control,join(output,'phase.json'),join(output,'phase'));promise.then(()=>{settled=true;},e=>{settled=true;childFailure=e;});
    const auth=await barrier('after-auth',(v,s)=>{assert.equal(v.actual_auth,2);assert.equal(active(s).length,0);assertInventoryUnchanged(initial,s);for(let i=0;i<2;i++)assert.equal(s.profiles[i].revision,initial.profiles[i].revision+1);});
    const admitted=await barrier('after-admit',(v,s)=>{assert.equal(v.actual_admitted,2);assert.equal(v.actors,2);assert.equal(v.arena,arena);assert.equal(v.source_sessions.length,2);assertAdmitted(auth.sql,s,arena);});
    const held=await barrier('held-inspect',(v,s)=>{assert.equal(v.actual_inspect,1);assert.equal(v.actual_reserved_fresh,true);assert.equal(v.old_actor_authority,false);assertHeld(admitted.sql,s);});
    const relogin=await barrier('held-relogin',(v,s)=>{assert.equal(v.actual_auth,3);assert.equal(v.new_avatar,false);assert.notEqual(v.source_session_id,v.delivery_session_id);assert.equal(v.account_locked,true);assertHeldRelogin(held.sql,s);});
    const firstFinal=await barrier('first-final',(v,s)=>{assert.equal(v.actual_finished,1);assertFinal(auth.sql,s,arena,1,admitted.summary);});
    const waiting=await barrier('before-final-update',(v,s)=>{assert.equal(v.account_cache_revision,relogin.sql.profiles[0].revision);assert.equal(v.sql_revision,firstFinal.sql.profiles[0].revision);assert.equal(v.account_locked,true);assertUnchanged(firstFinal.sql,s);});
    await barrier('final-update',(v,s)=>{assert.equal(v.method_id,0x57);assert.equal(v.source_revision,waiting.summary.account_cache_revision);assert.equal(v.destination_revision,waiting.summary.sql_revision);assert.equal(v.new_wire_revision,v.old_wire_revision+1);assert.equal(v.lock_removed,true);assert.notEqual(v.source_session_id,v.delivery_session_id);assertUnchanged(firstFinal.sql,s);});
    const final=await barrier('all-final',(v,s)=>{assert.equal(v.actual_finished,2);assert.equal(v.actual_world_results8,true);assert.equal(v.source_link_unchanged,true);assertFinal(auth.sql,s,arena,2,admitted.summary);});
    await barrier('queries-acked',(v,s)=>{assert.equal(v.actual_queries,2);assert.equal(v.actual_acks,2);assert.deepEqual(v.record_contracts,['hold-v1','hold-v1']);assertUnchanged(final.sql,s,['p06t_result','battle_owner_hold_command']);const current=s.rows.p06t_result.filter(r=>r.arena_id===arena);assert.equal(current.length,2);assert.ok(current.every(r=>r.acked===1));});
    const result=await promise;assert.equal(result.status,'PASS_ACTUAL_HOLD5_RUNTIME_HTTP_SQLITE');assert.equal(result.native_client,'NOT_RUN');assert.equal(result.new_grants,0);assert.equal(result.actual_admitted,2);assert.equal(result.actual_finished,2);
    assert.equal(sha(readFileSync(sourceDB)),sourceSHA);assert.equal(sha(readFileSync(sourceSeed)),metadataSHA);sourceGuard(guard);
    write(join(output,'result.json'),{...result,parent_full_gate:'PENDING_PARENT_FULL_GATE',head:guard.head,executable_sha256:sha(readFileSync(executable)),source_database_sha256:sourceSHA,actual_owned_owners:2,native_client:'NOT_RUN',gameplay_udp:'NOT_RUN',jolt:'NOT_RUN',four_owned_runtime:'NOT_RUN',
      authored_boundaries:'Authenticated Session envelopes/Window ACKs/logical clock; held-before-N2-forfeit scheduler pause. No authored Completion/Frozen/HP/results/terminal.',inventory_after_departure_reserved:true,one_final_per_owner:true,actual_relogin:true,actual_incremental_account_update:true});
  }finally{if(promise)await promise.catch(()=>{});if(bridge)await bridge.close();assert.equal(sha(readFileSync(sourceDB)),sourceSHA);assert.equal(sha(readFileSync(sourceSeed)),metadataSHA);}
}
if(process.argv[1]&&localSpelling(process.argv[1])===localSpelling(fileURLToPath(import.meta.url)))main(process.argv.slice(2)).catch(e=>{console.error(e.stack||e);process.exitCode=1;});
