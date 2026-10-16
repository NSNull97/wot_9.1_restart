/** Actual Loss4 readiness -> Host/Saga -> SQLite compensation -> same-run
 * fresh launch -> Forfeit/Finished claim-release composition. No native/Jolt. */
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { spawnSync,execFileSync } from 'node:child_process';
import { existsSync,readFileSync,writeFileSync } from 'node:fs';
import { resolve,join,relative,isAbsolute,dirname,basename } from 'node:path';
import { fileURLToPath,pathToFileURL } from 'node:url';
import { localSpelling,plain,readJson,keys,targetGuard,database,write,sha,child } from './p08c-late-result-composition.mjs';
const HERE=dirname(localSpelling(fileURLToPath(import.meta.url)));
const ROOT=resolve(HERE,'../../..');
const TEST='gateway091::shared::server::p10b_host::loss_composition_tests::p10b_loss_composition09_actual_http_host';
const SCOPES=['server','tools','client_patch','web/src','tests','web/tests'];
function within(root,path){const r=relative(root,path);assert.ok(r&&!r.startsWith('..')&&!isAbsolute(r));return path;}
function sourceGuard(guard){
  keys(guard,['schema','full_gate','head','files','parent_pid','target_dir','build_output','allocation','compiled_test_source_sha256','compiled_driver_sha256','compiled_common_driver_sha256','test_executable','test_name']);
  assert.equal(guard.schema,'p10b-loss-parent-in-progress.v1');assert.equal(guard.full_gate,'PENDING_PARENT_FULL_GATE');
  assert.equal(guard.test_name,TEST);assert.equal(guard.parent_pid,process.ppid);assert.match(guard.head,/^[0-9a-f]{40}$/);
  const git=args=>execFileSync('git',args,{cwd:ROOT,encoding:'utf8',windowsHide:true,maxBuffer:4*1024*1024});
  assert.equal(git(['rev-parse','HEAD']).trim(),guard.head);assert.equal(git(['status','--porcelain','--untracked-files=all','--',...SCOPES]),'');
  const names=git(['ls-files','-z','--',...SCOPES]).split('\0').filter(Boolean).sort();assert.deepEqual(Object.keys(guard.files).sort(),names);
  for(const name of names){assert.match(guard.files[name],/^[0-9a-f]{64}$/);assert.equal(sha(readFileSync(within(ROOT,plain(resolve(ROOT,name))))),guard.files[name],name);}
  assert.equal(guard.files['server/gateway/src/shared/p10b_loss_composition_tests.rs'],guard.compiled_test_source_sha256);
  assert.equal(guard.files['web/tests/helpers/p10b-loss-composition.mjs'],guard.compiled_driver_sha256);
  assert.equal(guard.files['web/tests/helpers/p08c-late-result-composition.mjs'],guard.compiled_common_driver_sha256);
  assert.equal(sha(readFileSync(plain(fileURLToPath(import.meta.url)))),guard.compiled_driver_sha256);
  return targetGuard(guard);
}
export async function main(args){
  const[mode,guardArgument,outputArgument,bundleArgument,originalArgument,seedArgument]=args;
  assert.equal(mode,'--parent-full');assert.equal(args.length,6);assert.equal(process.env.PYTHONPATH,undefined);
  const guardPath=plain(guardArgument),output=plain(outputArgument),base=plain(join(ROOT,'local/test-runs/p10b-loss-composition09'));
  assert.equal(dirname(output),base);assert.match(basename(output),/^run-[0-9]+-[0-9]+$/);assert.equal(guardPath,join(output,'parent-control.json'));
  const guard=readJson(guardPath,4*1024*1024),executable=sourceGuard(guard);
  const bundle=plain(bundleArgument),original=plain(originalArgument),sourceSeed=plain(seedArgument);
  assert.equal(sourceSeed,plain(join(ROOT,'local/evidence/20261016-p06t-owned01/seed01/seed.json')));
  const sourceMetadata=readJson(sourceSeed,65536),sourceDB=within(plain(join(ROOT,'local')),plain(sourceMetadata.database));
  assert.equal(plain(sourceMetadata.bundle),bundle);assert.equal(plain(sourceMetadata.original),original);
  const originalSHA=sha(readFileSync(sourceDB)),sourceSeedSHA=sha(readFileSync(sourceSeed));
  const modules = ['game-adapter','security','p04d-crew','p04k-crew','p09e-research','p08b-battle','p04m-pool','p06t-mixed','p06t-ammo-loss','p08c-late-results','p10b-selection-loss'];
  const [{ createIdentityBridge }, security, crew, barracks, research, battle, pool, mixed, loss, late, selection] = await Promise.all(
    modules.map(name => import(pathToFileURL(join(ROOT, `web/src/${name}.mjs`)))));
  const py = spawnSync('python', ['-B','-c','import sys;print(sys.executable)'], { encoding:'utf8', windowsHide:true });
  assert.equal(py.status,0,py.stderr); const python = plain(py.stdout.trim());
  const game = join(output,'game.sqlite');
  const seeded = spawnSync(python, ['-B','-X','utf8',join(ROOT,'tests/helpers/p08c_late_composition_seed.py'),game,sourceSeed],
    { cwd:ROOT,encoding:'utf8',windowsHide:true,timeout:120000 });
  writeFileSync(join(output,'seed.stdout.log'),seeded.stdout||'',{flag:'wx'});writeFileSync(join(output,'seed.stderr.log'),seeded.stderr||'',{flag:'wx'});
  assert.equal(seeded.status,0,'Actual own seed preparation failed; see retained seed logs');
  const seed = readJson(game.replace(/\.sqlite$/,'.json'),65536);assert.equal(seed.new_grants,0);assert.equal(seed.new_reservations,0);assert.equal(seed.new_results,0);
  assert.equal(seed.source_database.sha256,originalSHA);assert.equal(seed.source_seed.sha256,sourceSeedSHA);assert.equal(sha(readFileSync(sourceDB)),originalSHA);
  const profiles = seed.profiles, accounts = profiles.map(p=>p.account_id);assert.equal(new Set(accounts).size,2);assert.ok(accounts[1]<accounts[0],'Actual preserved pair must exercise frozen B,A against A,B arrival');
  const identity=join(output,'identity.sqlite'),tokenFile=join(output,'identity.token'),native=plain(join(bundle,'content/inputs/native-ms1.blob'));
  const password=security.token(),passwordHash=await security.hashPassword(password);writeFileSync(tokenFile,security.token(),{flag:'wx',mode:0o600});
  const users=profiles.map((p,i)=>({account_id:p.account_id,email:`late-composition-${i}@example.test`,password}));
  let db=new DatabaseSync(identity);try{db.exec('PRAGMA user_version=2; CREATE TABLE users(id TEXT PRIMARY KEY,username TEXT,display_nickname TEXT,email TEXT,password_hash TEXT,created_at INTEGER)');
    profiles.forEach((p,i)=>db.prepare('INSERT INTO users VALUES (?,?,?,?,?,?)').run(p.account_id,p.username.toLowerCase(),p.username,users[i].email,passwordHash,p.created_at_ms));}finally{db.close();}
  db=new DatabaseSync(game);try{db.prepare('INSERT INTO game_meta VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value').run('native_descriptors_sha256',sha(readFileSync(native)));}finally{db.close();}
  const options={version:1,port:0,web_database:identity,game_database:game,fixture_root:join(output,'fixtures'),native_descriptors:native,python_executable:python,token_file:tokenFile,
    ammunition_service:{version:1,bundle_root:bundle,original_root:original,account_id:accounts[0],grant:{grant_id:'p09d-test-depot-v1',quantity_each:100}},
    crew_service:{version:1,policy_sha256:crew.CREW_POLICY_SHA256},crew_transfer:{version:1,policy_sha256:crew.TRANSFER_POLICY_SHA256},
    crew_cross_vehicle:{version:1,policy_sha256:crew.CROSS_CREW_POLICY_SHA256},crew_roster_recruitment:{version:1,policy_sha256:crew.ROSTER_CREW_POLICY_SHA256},
    crew_progression:{version:1,policy_sha256:crew.PROGRESSION_CREW_POLICY_SHA256},crew_dismissal:{version:1,policy_sha256:crew.DISMISSAL_CREW_POLICY_SHA256},
    crew_barracks_recruitment:{version:1,policy_sha256:barracks.BARRACKS_CREW_POLICY_SHA256},research_service:{version:1,policy_sha256:research.RESEARCH_POLICY_SHA256},
    battle_service:{version:1,policy_sha256:battle.BATTLE_POLICY_SHA256,accounts},pool_service:{version:1,policy_sha256:pool.POOL_POLICY_SHA256,accounts},
    mixed_service:{version:2,policy_sha256:mixed.MIXED_POLICY_SHA256,accounts,shell_catalog:join(ROOT,'tests/fixtures/p06t-shell-catalog.json'),terminal_policy:join(ROOT,'tests/fixtures/p06t-device-policy.json')},
    ammo_loss_service:{version:4,contract:loss.LOSS_CONTRACT,policy_sha256:loss.LOSS_POLICY_SHA256,accounts},
    late_result_service:{version:1,contract:late.LATE_CONTRACT,policy_sha256:late.LATE_POLICY_SHA256,accounts},
    room_selection_loss_service:{version:4,schema:selection.LOSS_SELECTION_SCHEMA,contract:loss.LOSS_CONTRACT,policy_sha256:loss.LOSS_POLICY_SHA256,accounts}};
  const read=action=>database(game,action);
  const tables=()=>read(d=>Object.fromEntries(d.prepare("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").all()
    .map(r=>[r.name,d.prepare(`SELECT * FROM "${r.name.replaceAll('"','""')}"`).all()])));
  const roster=()=>read(d=>accounts.map(id=>({profile:JSON.parse(d.prepare('SELECT profile_json FROM game_profiles WHERE account_id=?').get(id).profile_json),
    aggregate:JSON.parse(d.prepare('SELECT snapshot_json FROM game_snapshot WHERE account_id=?').get(id).snapshot_json)})));
  const reservations=()=>read(d=>d.prepare('SELECT * FROM p06t_reservation ORDER BY account_id,reservation_id').all());
  const wrapperRows=()=>read(d=>d.prepare('SELECT * FROM battle_ammo_loss_reservation ORDER BY account_id,reservation_id').all());
  const active=()=>reservations().filter(r=>r.status==='active');
  const frozenResources=()=>roster().map(r=>({resources:r.profile.resources,ammunition:r.profile.ammunition,depot:r.aggregate.depot,
    crew_inventory:r.aggregate.crew_inventory,research:r.aggregate.research}));
  const resources=frozenResources();write(join(output,'initial-resources.json'),resources);
  let bridge,promise,settled=false,childFailure;
  const config=port=>{const v={login_bind:'127.0.0.1:26121',base_bind:'127.0.0.1:26122',identity_endpoint:`127.0.0.1:${port}`,
    identity_token_file:tokenFile,local_root:join(ROOT,'local'),session_duration_seconds:600,battle_players:6,training_rooms:true,
    p08c_late_results:true,p08c_late_results_accounts:accounts,p08c_late_notice_experimental:false};
    for(const key of['ammunition_service','crew_service','crew_transfer','crew_cross_vehicle','crew_roster_recruitment','crew_progression','crew_dismissal',
      'crew_barracks_recruitment','research_service','profile13_battle','p04m_pool','p06t_mixed_ammo','visibility_v1','p06t_ammo_rack_detonation'])v[key]=true;
    return v; // Ports are validated only. No gameplay UDP socket is bound.
  };
  async function barrier(name,check){
    const marker=join(output,`${name}.ready.json`),deadline=performance.now()+180000;
    while(!existsSync(marker)){if(settled){if(childFailure)throw childFailure;throw new Error(`Child completed before ${name}`);}
      assert.ok(performance.now()<deadline,`Missing actual SQL checkpoint ${name}`);await new Promise(done=>setTimeout(done,10));}
    const summary=readJson(marker,65536);check(summary);write(join(output,`${name}.sql.json`),{summary,tables:tables()});
    writeFileSync(join(output,`${name}.go`),'GO\n',{flag:'wx'});return summary;
  }
  try{
    bridge=await createIdentityBridge(options);
    const cfg=join(output,'config.private.json'),control=join(output,'control.private.json');write(cfg,config(bridge.port));
    write(control,{schema:'p10b-loss-composition.v1',phase:'abort_then_launch',config:cfg,users,barrier:output,arena_id:'9007199254741093'});
    promise=child(executable,control,join(output,'phase.json'),join(output,'phase'),TEST,180000);
    // Observe rejection immediately; retain and await exact child termination
    // before closing the HTTP service or any controller-owned resource.
    promise.then(result=>{settled=true;},error=>{settled=true;childFailure=error;});
    let baseline,afterCompensation,oldReservations,oldWrappers;
    await barrier('after-auth',v=>{assert.equal(v.actual_auth,2);assert.equal(v.native,'NOT_RUN');assert.equal(active().length,0);
      baseline=tables();oldReservations=reservations();oldWrappers=wrapperRows();assert.deepEqual(frozenResources(),resources);});
    await barrier('first-ready',v=>{assert.equal(v.actual_http_ready,2);assert.deepEqual(tables(),baseline,'Ready must be actual readonly HTTP/SQL');});
    const first=await barrier('first-admit',v=>{assert.equal(v.actual_admitted,1);assert.equal(v.actors,0);assert.equal(active().length,1);
      assert.equal(reservations().length,oldReservations.length+1);assert.equal(wrapperRows().length,oldWrappers.length+1);
      assert.equal(active()[0].battle_id,v.battle);assert.deepEqual(frozenResources(),resources);});
    const compensated=await barrier('compensated',v=>{assert.equal(v.claims_released,2);assert.equal(v.world_started,false);assert.notEqual(v.new_battle,first.battle);
      assert.equal(active().length,0);const added=reservations().filter(r=>!oldReservations.some(old=>old.account_id===r.account_id&&old.reservation_id===r.reservation_id));
      assert.equal(added.length,1);assert.equal(added[0].status,'finished');assert.equal(added[0].battle_id,first.battle);
      assert.deepEqual(frozenResources(),resources);afterCompensation=tables();});
    await barrier('second-ready',v=>{assert.equal(v.actual_http_ready,2);assert.equal(v.run,compensated.same_actual_run);
      assert.deepEqual(tables(),afterCompensation,'Second Ready must not issue writes/activate/recover');});
    const launched=await barrier('launched',v=>{assert.equal(v.actual_admitted,2);assert.equal(v.arena,compensated.new_battle);assert.deepEqual(v.teams,[2,1]);
      assert.equal(v.frozen_order,'B,A');assert.equal(v.arrival,'A,B');assert.equal(v.final411_acked,true);assert.equal(active().length,2);
      assert.ok(active().every(r=>r.battle_id===v.arena));assert.equal(reservations().length,oldReservations.length+3);assert.equal(wrapperRows().length,oldWrappers.length+3);
      assert.deepEqual(frozenResources(),resources);});
    await barrier('one-finished',v=>{assert.equal(v.actual_finished,1);assert.equal(v.both_claims_still_battle,true);assert.equal(v.arena,launched.arena);
      assert.equal(active().length,1);assert.deepEqual(frozenResources(),resources);});
    await barrier('all-finished',v=>{assert.equal(v.actual_finished,2);assert.equal(v.claims_released,2);assert.equal(v.actual_training_late_capture,true);
      assert.equal(active().length,0);const added=reservations().filter(r=>!oldReservations.some(old=>old.account_id===r.account_id&&old.reservation_id===r.reservation_id));
      assert.equal(added.length,3);assert.ok(added.every(r=>r.status==='finished'));assert.deepEqual(frozenResources(),resources);
      assert.ok(roster().every(r=>r.aggregate.vehicles.every(v=>v.state==='available'&&v.battle_id===null)));});
    const result=await promise;assert.equal(result.status,'PASS_ACTUAL_P10B_LOSS_HOST_HTTP_SQLITE');assert.equal(result.actual_readies,4);
    assert.equal(result.actual_admits,3);assert.equal(result.actual_finishes,3);assert.equal(result.native_client,'NOT_RUN');assert.equal(result.jolt,'NOT_RUN');
    assert.equal(sha(readFileSync(sourceDB)),originalSHA);assert.equal(sha(readFileSync(sourceSeed)),sourceSeedSHA);sourceGuard(guard);
    write(join(output,'result.json'),{...result,parent_full_gate:'PENDING_PARENT_FULL_GATE',head:guard.head,source_database_sha256:originalSHA,
      executable_sha256:sha(readFileSync(executable)),new_grants:0,actual_readiness_readonly:true,actual_same_run_compensation_then_launch:true,
      actual_loss4_reservations:true,actual_claim_release_after_both_finished:true,actual_late_capture_hook:true,
      native_client:'NOT_RUN',gameplay_udp:'NOT_RUN',jolt:'NOT_RUN',warm_avatar_cycle:'NOT_IN_THIS_TEST (covered by composition06)',
      control:'Synthetic authenticated Session envelope/Window ACKs, engine binding gates, source Prohorovka terrain, ready/Forfeit clock; no authored ReadySelection/receipt/HP/death'});
  }finally{
    if(promise)await promise.catch(()=>{});
    if(bridge)await bridge.close();assert.equal(sha(readFileSync(sourceDB)),originalSHA);assert.equal(sha(readFileSync(sourceSeed)),sourceSeedSHA);
  }
}
if(process.argv[1]&&localSpelling(process.argv[1])===localSpelling(fileURLToPath(import.meta.url))){main(process.argv.slice(2)).catch(error=>{console.error(error.stack||error);process.exitCode=1;});}
