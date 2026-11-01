/** LATE-BOTS: actual bridge/SQLite with synthetic Session and authored clock.
 * All writes stay in a new worktree-local run directory; source seed is read-only.
 * Native client, UDP and Jolt are NOT_RUN. */
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { spawn, spawnSync, execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync, existsSync, lstatSync, openSync, closeSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { plain, sha, write, database } from './p08c-late-result-composition.mjs';
const ROOT=resolve(dirname(fileURLToPath(import.meta.url)),'../../..');
const TEST='gateway091::shared::server::late_bots_composition_tests::late_bots_real_http_sqlite_release';
const seedPath=plain('D:/WoT_9.1_Server/local/evidence/20261016-p06t-owned01/seed01/seed.json');
const json=path=>JSON.parse(readFileSync(path,'utf8'));
const [exeArg,outArg,parentPid,expectedExeSHA]=process.argv.slice(2);assert.equal(process.argv.length,6);
assert.match(parentPid,/^[1-9][0-9]*$/);assert.equal(Number(parentPid),process.ppid);assert.match(expectedExeSHA,/^[a-f0-9]{64}$/);
const exe=plain(exeArg),output=plain(outArg),base=plain(join(ROOT,'local/test-runs/late-bots-composition'));
assert.equal(dirname(output),base);assert.match(output,/[\\/]run-\d+-\d+$/);assert.match(exe,/[\\/]release[\\/]deps[\\/]sr_gateway-[0-9a-f]+\.exe$/);
assert.equal(dirname(exe),plain(join(process.env.CARGO_TARGET_DIR,'release/deps')));
const git=args=>execFileSync('git',args,{cwd:ROOT,encoding:'utf8',windowsHide:true,maxBuffer:4*1024*1024});
const scopes=['server','tools','client_patch','tests','web/src','web/tests'];const verify=()=>assert.equal(git(['status','--porcelain','--untracked-files=all','--',...scopes]),'');
verify();const head=git(['rev-parse','HEAD']).trim(),exeSHA=sha(readFileSync(exe)),seedSHA=sha(readFileSync(seedPath)),seedInput=json(seedPath);
assert.equal(exeSHA,expectedExeSHA);
const sourceDB=plain(seedInput.database),bundle=plain(seedInput.bundle),original=plain(seedInput.original),dbSHA=sha(readFileSync(sourceDB));
assert.equal(sourceDB,plain(join(dirname(seedPath),'game.sqlite')));assert.equal(seedInput.source_stand_writes,false);
function sourceFileState(path,maximum){
  let before;try{before=lstatSync(path,{bigint:true});}catch(error){if(error.code==='ENOENT')return null;throw error;}
  assert.ok(before.isFile()&&!before.isSymbolicLink(),'source must be a plain regular file');assert.ok(before.size<=BigInt(maximum),'source size bound');
  assert.equal(plain(path),path);const digest=sha(readFileSync(path)),after=lstatSync(path,{bigint:true});
  assert.equal(after.size,before.size);assert.equal(after.mtimeNs,before.mtimeNs);
  return {bytes:Number(after.size),mtime_ns:String(after.mtimeNs),sha256:digest};
}
function sourceState(){return {seed:sourceFileState(seedPath,65536),database:sourceFileState(sourceDB,64*1024*1024),
  wal:sourceFileState(`${sourceDB}-wal`,0),shm:sourceFileState(`${sourceDB}-shm`,16*1024*1024)};}
const initialSourceState=sourceState();assert.ok(initialSourceState.seed&&initialSourceState.database,'required source missing');
const modules=['game-adapter','security','p04d-crew','p04k-crew','p09e-research','p08b-battle','p04m-pool','p06t-mixed','p06t-ammo-loss','p08c-late-results'];
const [{createIdentityBridge},security,crew,barracks,research,battle,pool,mixed,loss,late]=await Promise.all(modules.map(name=>import(pathToFileURL(join(ROOT,`web/src/${name}.mjs`)))));
const pythonRun=spawnSync('python',['-B','-c','import sys;print(sys.executable)'],{encoding:'utf8',windowsHide:true});assert.equal(pythonRun.status,0);
const python=plain(pythonRun.stdout.trim()),game=join(output,'game.sqlite');
const seeded=spawnSync(python,['-B','-X','utf8',join(ROOT,'tests/helpers/late_bots_composition_seed.py'),game,seedPath],{cwd:ROOT,encoding:'utf8',windowsHide:true,timeout:120000});
writeFileSync(join(output,'seed.stdout.log'),seeded.stdout||'',{flag:'wx'});writeFileSync(join(output,'seed.stderr.log'),seeded.stderr||'',{flag:'wx'});assert.equal(seeded.status,0,'seed failed; see logs');
const seed=json(join(output,'game.json'));assert.equal(seed.new_grants,0);assert.equal(seed.new_reservations,0);assert.equal(seed.new_results,0);
assert.equal(seed.source_database.sha256,dbSHA);assert.equal(seed.source_seed.sha256,seedSHA);assert.equal(plain(seed.bundle),bundle);assert.equal(plain(seed.original),original);
const profiles=seed.profiles,accounts=profiles.map(p=>p.account_id),identity=join(output,'identity.sqlite'),tokenFile=join(output,'identity.token'),native=plain(join(bundle,'content/inputs/native-ms1.blob'));
const password=security.token(),passwordHash=await security.hashPassword(password);writeFileSync(tokenFile,security.token(),{flag:'wx',mode:0o600});
const users=profiles.map((p,i)=>({account_id:p.account_id,email:`late-bots-${i}@example.test`,password}));
let db=new DatabaseSync(identity);try{db.exec('PRAGMA user_version=2; CREATE TABLE users(id TEXT PRIMARY KEY,username TEXT,display_nickname TEXT,email TEXT,password_hash TEXT,created_at INTEGER)');
  profiles.forEach((p,i)=>db.prepare('INSERT INTO users VALUES (?,?,?,?,?,?)').run(p.account_id,p.username.toLowerCase(),p.username,users[i].email,passwordHash,p.created_at_ms));}finally{db.close();}
db=new DatabaseSync(game);try{db.prepare('INSERT INTO game_meta VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value').run('native_descriptors_sha256',sha(readFileSync(native)));}finally{db.close();}
const options={version:1,port:0,web_database:identity,game_database:game,fixture_root:join(output,'fixtures'),native_descriptors:native,python_executable:python,token_file:tokenFile,
  ammunition_service:{version:1,bundle_root:bundle,original_root:original,account_id:accounts[0],grant:{grant_id:'p09d-test-depot-v1',quantity_each:100}},
  crew_service:{version:1,policy_sha256:crew.CREW_POLICY_SHA256},crew_transfer:{version:1,policy_sha256:crew.TRANSFER_POLICY_SHA256},crew_cross_vehicle:{version:1,policy_sha256:crew.CROSS_CREW_POLICY_SHA256},
  crew_roster_recruitment:{version:1,policy_sha256:crew.ROSTER_CREW_POLICY_SHA256},crew_progression:{version:1,policy_sha256:crew.PROGRESSION_CREW_POLICY_SHA256},
  crew_dismissal:{version:1,policy_sha256:crew.DISMISSAL_CREW_POLICY_SHA256},crew_barracks_recruitment:{version:1,policy_sha256:barracks.BARRACKS_CREW_POLICY_SHA256},
  research_service:{version:1,policy_sha256:research.RESEARCH_POLICY_SHA256},battle_service:{version:1,policy_sha256:battle.BATTLE_POLICY_SHA256,accounts},pool_service:{version:1,policy_sha256:pool.POOL_POLICY_SHA256,accounts},
  mixed_service:{version:2,policy_sha256:mixed.MIXED_POLICY_SHA256,accounts,shell_catalog:join(ROOT,'tests/fixtures/p06t-shell-catalog.json'),terminal_policy:join(ROOT,'tests/fixtures/p06t-device-policy.json')},
  ammo_loss_service:{version:4,contract:loss.LOSS_CONTRACT,policy_sha256:loss.LOSS_POLICY_SHA256,accounts},late_result_service:{version:1,contract:late.LATE_CONTRACT,policy_sha256:late.LATE_POLICY_SHA256,accounts}};
const read=action=>database(game,action);
const oldTables=()=>read(d=>Object.fromEntries(d.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'p08c_late_%' ORDER BY name").all().map(r=>[r.name,d.prepare(`SELECT * FROM "${r.name.replaceAll('"','""')}"`).all()])));
const ownerRows=id=>read(d=>Object.fromEntries(d.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'p08c_late_%' ORDER BY name").all()
  .filter(r=>d.prepare(`PRAGMA table_info("${r.name.replaceAll('"','""')}")`).all().some(c=>c.name==='account_id'))
  .map(r=>[r.name,d.prepare(`SELECT * FROM "${r.name.replaceAll('"','""')}" WHERE account_id=?`).all(id)])));
function config(port,experimental){const v={login_bind:'127.0.0.1:26111',base_bind:'127.0.0.1:26112',identity_endpoint:`127.0.0.1:${port}`,identity_token_file:tokenFile,local_root:join(ROOT,'local'),session_duration_seconds:600,
  battle_players:4,connection_capacity:4,bots:{policy:'project.bot01.route-hold-visible-aim.v1',human_places:1,seed:1,kinds:['ms1']},late_bots:{policy:'project.late-bots.continue-until-outcome.v1'},
  p08c_late_results:true,p08c_late_results_accounts:accounts,p08c_late_notice_experimental:experimental};
  for(const key of ['ammunition_service','crew_service','crew_transfer','crew_cross_vehicle','crew_roster_recruitment','crew_progression','crew_dismissal','crew_barracks_recruitment','research_service','profile13_battle','p04m_pool','p06t_mixed_ammo','visibility_v1','p06t_ammo_rack_detonation'])v[key]=true;return v;}
async function runPhase(name,control,marker,go){
  const stdout=openSync(join(output,`${name}.stdout.log`),'wx'),stderr=openSync(join(output,`${name}.stderr.log`),'wx');let child,closed,timer;
  try{child=spawn(exe,['--ignored','--exact',TEST,'--nocapture','--test-threads=1'],{cwd:ROOT,windowsHide:true,stdio:['ignore',stdout,stderr],env:{...process.env,LATE_BOTS_COMPOSITION_CONTROL:control,LATE_BOTS_COMPOSITION_OUTPUT:join(output,`${name}.json`)}});
    closed=new Promise((done,fail)=>{child.once('error',fail);child.once('close',(code,signal)=>done({code,signal}));});
    const deadline=performance.now()+120000;while(!existsSync(marker)){assert.ok(performance.now()<deadline,'SQL barrier timed out');await Promise.race([new Promise(r=>setTimeout(r,10)),closed.then(()=>{throw new Error('child exited before barrier');})]);}
    const before=oldTables();write(join(output,`${name}.before.json`),before);writeFileSync(go,'GO\n',{flag:'wx'});
    const result=await Promise.race([closed,new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('child timeout')),120000);})]);assert.equal(result.signal,null);assert.equal(result.code,0);
    assert.deepEqual(oldTables(),before,'late append/query/ack changed old tables');return json(join(output,`${name}.json`));
  }finally{clearTimeout(timer);if(child&&child.exitCode===null&&child.signalCode===null)child.kill();if(closed)await closed.catch(()=>{});closeSync(stdout);closeSync(stderr);}
}
let bridge;
try{
  bridge=await createIdentityBridge(options);const untouchedPeer=ownerRows(accounts[1]);const ca=join(output,'config-a.private.json'),ia=join(output,'control-a.private.json');write(ca,config(bridge.port,false));
  write(ia,{schema:'late-bots-composition.v1',phase:'battle',config:ca,users,barrier:output,arena_id:'9007199254740993',expected_results_json:null});
  const a=await runPhase('phase-a',ia,join(output,'after-finish.ready.json'),join(output,'after-finish.go'));
  assert.equal(a.real_admit,true);assert.equal(a.real_finish,true);assert.equal(a.actual_outcome,true);
  assert.deepEqual(ownerRows(accounts[1]),untouchedPeer,'other owner must not receive bot writes');
  assert.deepEqual(read(d=>d.prepare('SELECT account_id FROM game_profiles ORDER BY account_id').all().map(r=>r.account_id)),[...accounts].sort());
  const saved=read(d=>d.prepare('SELECT * FROM p08c_late_result ORDER BY account_id').all());assert.equal(saved.length,1);assert.equal(saved[0].account_id,accounts[0]);assert.equal(saved[0].acked,0);
  const seal=JSON.parse(read(d=>d.prepare('SELECT seal_json FROM p08c_late_seal').get()).seal_json);assert.equal(seal.version,2);assert.equal(seal.actors.length,1);assert.equal(seal.bots.length,3);
  assert.deepEqual(JSON.parse(seal.results_json),JSON.parse(a.results_json));for(const bot of seal.bots)assert.equal('account_id' in bot,false);
  const before=oldTables();await bridge.close();bridge=null;bridge=await createIdentityBridge(options);assert.deepEqual(oldTables(),before);
  const cb=join(output,'config-b.private.json'),ib=join(output,'control-b.private.json');write(cb,config(bridge.port,true));
  write(ib,{schema:'late-bots-composition.v1',phase:'reopen',config:cb,users,barrier:output,arena_id:a.arena_id,expected_results_json:a.results_json});
  const b=await runPhase('phase-b',ib,join(output,'after-reopen-auth.ready.json'),join(output,'after-reopen-auth.go'));assert.notEqual(a.run,b.run);assert.equal(b.query_1500,true);assert.equal(b.ack_1501,true);
  assert.equal(read(d=>d.prepare('SELECT acked FROM p08c_late_result WHERE account_id=? AND arena_id=?').get(accounts[0],a.arena_id).acked),1);
  assert.deepEqual(sourceState(),initialSourceState,'source seed/database/WAL/SHM changed');assert.equal(sha(readFileSync(exe)),exeSHA);verify();
  assert.equal(git(['rev-parse','HEAD']).trim(),head,'HEAD changed during composition');
  write(join(output,'result.json'),{status:'PASS_ACTUAL_HTTP_SQLITE_SYNTHETIC_BOT_COMPOSITION',head,executable_sha256:exeSHA,source_database_sha256:dbSHA,source_seed_sha256:seedSHA,
    source_sidecars:{wal:initialSourceState.wal,shm:initialSourceState.shm},
    actual_admit_finish:true,actual_final_outcome:true,actual_late_append:true,old_table_equality_barriers:2,bot_accounts_written:0,actual_query1500_ack1501:true,
    synthetic:'Session/ACK; flat terrain; authored shortened lifecycle; no bot movement simulated',native:'NOT_RUN',udp:'NOT_RUN',jolt:'NOT_RUN',experimental_notice:'INFERRED_STATIC_ONLY'});
}finally{if(bridge)await bridge.close();assert.deepEqual(sourceState(),initialSourceState,'source seed/database/WAL/SHM changed');}
