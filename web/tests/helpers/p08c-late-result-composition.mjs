/** Regular Cargo test composition controller. Actual HTTP/SQLite only after
 * guarded parent invocation. Authored Session/ACK/ready/Forfeit clock: native/UDP/Jolt NOT_RUN. */
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { createHash } from 'node:crypto';
import { spawn, spawnSync, execFileSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync, mkdirSync, realpathSync, openSync, closeSync, lstatSync } from 'node:fs';
import { resolve, join, relative, isAbsolute, dirname, basename, parse } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = dirname(localSpelling(fileURLToPath(import.meta.url)));
const ROOT = resolve(HERE, '../../..'); // promoted web/tests/helpers -> repository
const TEST = 'gateway091::shared::server::p08c_late_composition_tests::p08c_late_result_runtime05_real_http_phase';
const SCOPES = ['server', 'tools', 'client_patch', 'web/src', 'tests', 'web/tests'];
export const sha = bytes => createHash('sha256').update(bytes).digest('hex');
function within(root, path) { const r = relative(root, path); assert.ok(r && !r.startsWith('..') && !isAbsolute(r)); return path; }
export function localSpelling(value) {
  assert.equal(typeof value, 'string');
  // Rust canonicalize uses \\?\D:\ whereas Python/Node normally retain D:\.
  // Normalize only a local drive spelling, never turn UNC into a local permit.
  if (value.startsWith('\\\\?\\')) value = value.slice(4);
  assert.match(value,/^[A-Za-z]:[\\/]/); assert.ok(isAbsolute(value)); return resolve(value);
}
export function plain(value) {
  const path = localSpelling(value); let cursor = path;
  for (;;) { assert.equal(lstatSync(cursor).isSymbolicLink(), false, 'Linked/junction path refused'); const parent = dirname(cursor); if (parent === cursor) break; cursor = parent; }
  return realpathSync(path);
}
export function readJson(path, budget = 16384) { const bytes = readFileSync(plain(path)); assert.ok(bytes.length <= budget); return JSON.parse(bytes); }
export function keys(value, expected) { assert.ok(value && typeof value === 'object' && !Array.isArray(value)); assert.deepEqual(Object.keys(value).sort(), [...expected].sort()); }
export function ref(value) {
  keys(value, ['path', 'sha256']); assert.match(value.sha256, /^[0-9a-f]{64}$/);
  const path = plain(value.path); assert.equal(sha(readFileSync(path)), value.sha256); return path;
}
const ENV_KEYS = ['CARGO_HOME','RUSTUP_HOME','CARGO_TARGET_DIR','CARGO_TARGET_X86_64_PC_WINDOWS_GNU_LINKER','RUSTFLAGS','CARGO_INCREMENTAL','RUST_TEST_THREADS','CARGO_PROFILE_DEV_DEBUG','CARGO_PROFILE_TEST_DEBUG'];
// Pure metadata constraints are also exercised independently by authored tests.
// All path facts passed here are obtained by plain()/realpath in the real gate.
export function allocationRecord(origin, metadata, environment, facts) {
  keys(origin, ['output','schema','default_os_temp','target','created_utc','retained_for_audit','automatic_delete','source']);
  keys(metadata, ['schema','default_os_temp','target','created_utc','retained_for_audit','automatic_delete','source']);
  const { output, ...rest } = origin; assert.deepEqual(metadata, rest);
  assert.equal(metadata.schema, 'wot091-cargo-temp-target.v1');
  assert.equal(metadata.retained_for_audit, true); assert.equal(metadata.automatic_delete, false);
  assert.equal(metadata.source, 'tempfile.gettempdir(); fresh mkdtemp; no caller path');
  assert.match(metadata.created_utc, /^\d{4}-\d\d-\d\dT.+(?:Z|[+]00:00)$/);
  assert.equal(resolve(output), facts.output); assert.equal(resolve(metadata.target), facts.target);
  assert.equal(resolve(metadata.default_os_temp), facts.temp);
  assert.equal(dirname(facts.target), facts.temp); assert.match(basename(facts.target), /^wot091-cargo-.+$/);
  assert.notEqual(parse(facts.temp).root.toLowerCase(), parse(facts.output).root.toLowerCase());
  keys(environment, Object.keys(environment));
  assert.ok(Object.keys(environment).every(key => ENV_KEYS.includes(key)));
  assert.equal(resolve(environment.CARGO_TARGET_DIR), facts.target);
  for (const [key,value] of Object.entries(environment)) assert.equal(value, facts.env[key], `Cargo environment differs: ${key}`);
}
export function targetGuard(guard) {
  const target = plain(guard.target_dir), output = within(plain(join(ROOT, 'local/build')), plain(guard.build_output));
  const executable = ref(guard.test_executable);
  assert.equal(dirname(executable), plain(join(target, 'debug/deps'))); assert.match(basename(executable), /^sr_gateway-[0-9a-f]+\.exe$/);
  assert.equal(plain(process.env.CARGO_TARGET_DIR), target);
  if (guard.allocation === null) {
    assert.equal(target, plain(join(output, 'target')));
    assert.equal(existsSync(join(output, 'cargo-temp-target.json')), false);
  } else {
    keys(guard.allocation, ['origin','metadata','environment']);
    assert.equal(ref(guard.allocation.origin), join(target, 'wot091-build-origin.json'));
    assert.equal(ref(guard.allocation.metadata), join(output, 'cargo-temp-target.json'));
    assert.equal(ref(guard.allocation.environment), join(output, 'cargo-temp-environment.json'));
    allocationRecord(readJson(guard.allocation.origin.path), readJson(guard.allocation.metadata.path), readJson(guard.allocation.environment.path),
      { output, target, temp: plain(tmpdir()), env: process.env });
  }
  return executable;
}
function sourceGuard(guard) {
  keys(guard,['schema','full_gate','head','files','parent_pid','target_dir','build_output','allocation','compiled_test_source_sha256','compiled_driver_sha256','test_executable','test_name']);
  assert.equal(guard.schema, 'p08c-late-result-parent-in-progress.v1'); assert.equal(guard.full_gate, 'PENDING_PARENT_FULL_GATE');
  assert.equal(guard.test_name, TEST); assert.equal(guard.parent_pid, process.ppid);
  assert.match(guard.head,/^[0-9a-f]{40}$/);
  const git = args => execFileSync('git', args, { cwd: ROOT, encoding: 'utf8', windowsHide: true, maxBuffer: 4*1024*1024 });
  assert.equal(git(['rev-parse','HEAD']).trim(), guard.head);
  assert.equal(git(['status','--porcelain','--untracked-files=all','--',...SCOPES]),'');
  const names = git(['ls-files','-z','--',...SCOPES]).split('\0').filter(Boolean).sort();
  assert.deepEqual(Object.keys(guard.files).sort(),names);
  for (const name of names) {
    assert.match(guard.files[name],/^[0-9a-f]{64}$/);
    const path = within(ROOT,plain(resolve(ROOT,name))); assert.equal(sha(readFileSync(path)),guard.files[name],name);
  }
  assert.equal(guard.files['server/gateway/src/shared/p08c_late_composition_tests.rs'],guard.compiled_test_source_sha256);
  assert.equal(guard.files['web/tests/helpers/p08c-late-result-composition.mjs'],guard.compiled_driver_sha256);
  assert.equal(sha(readFileSync(plain(fileURLToPath(import.meta.url)))),guard.compiled_driver_sha256);
  return targetGuard(guard);
}
export function database(path, action) { const db = new DatabaseSync(path, { readOnly: true }); try { return action(db); } finally { db.close(); } }
export function write(path, value) { writeFileSync(path, JSON.stringify(value, null, 2), { flag: 'wx' }); }
export async function child(exe, control, output, prefix, name, deadlineMs = 100000) {
  assert.ok(deadlineMs === 100000 || deadlineMs === 180000, "Closed test-only child deadline");
  let out, err, owned, closed, timer, spawnError;
  try {
    out = openSync(`${prefix}.stdout.log`, 'wx'); err = openSync(`${prefix}.stderr.log`, 'wx');
    owned = spawn(exe, ['--exact', name, '--nocapture', '--test-threads=1'], { cwd: ROOT, windowsHide: true,
      env: { ...process.env, P08C_LATE_COMPOSITION_CONTROL: control, P08C_LATE_COMPOSITION_OUTPUT: output }, stdio: ['ignore', out, err] });
    // Keep the HTTP event loop alive. close is emitted after this exact child's
    // exit and stdio cleanup; retain its promise before installing the deadline.
    closed = new Promise(done => {
      owned.once('error', error => { spawnError = error; });
      owned.once('close', (code, signal) => done({ code, signal }));
    });
    const timeout = new Promise((_, fail) => { timer = setTimeout(() => fail(new Error('Own composition test timed out')), deadlineMs); });
    const result = await Promise.race([closed, timeout]);
    if (spawnError) throw spawnError;
    assert.equal(result.signal, null, 'Own test exited by signal');
    assert.equal(result.code, 0, `Test failed; retained ${prefix} logs`); assert.ok(existsSync(output));
    return readJson(output, 65536);
  } finally {
    clearTimeout(timer);
    if (owned && closed) {
      if (owned.exitCode === null && owned.signalCode === null) owned.kill('SIGKILL');
      // Never close the bridge/logs while this child can still mutate SQLite.
      await closed;
    }
    try { if (out !== undefined) closeSync(out); } finally { if (err !== undefined) closeSync(err); }
  }
}
/** Source-local successor: real bridge/SQL, two immutable child phases. */
export async function main(args) {
  const [mode, guardArgument, outputArgument, bundleArgument, originalArgument, seedArgument] = args;
  assert.equal(mode, '--parent-full'); assert.equal(args.length, 6);
  assert.equal(process.env.PYTHONPATH, undefined, 'Clean worker environment is part of this composition');
  const guardPath = plain(guardArgument), output = plain(outputArgument);
  const base = plain(join(ROOT, 'local/test-runs/p08c-late-composition05'));
  assert.equal(dirname(output), base); assert.match(basename(output), /^run-[0-9]+-[0-9]+$/);
  assert.equal(guardPath, join(output, 'parent-control.json'));
  const guard = readJson(guardPath, 4 * 1024 * 1024), executable = sourceGuard(guard);
  const bundle = plain(bundleArgument), original = plain(originalArgument), sourceSeed = plain(seedArgument);
  assert.equal(sourceSeed, plain(join(ROOT, 'local/evidence/20261016-p06t-owned01/seed01/seed.json')));
  const sourceMetadata = readJson(sourceSeed, 65536), sourceDB = within(plain(join(ROOT, 'local')), plain(sourceMetadata.database));
  assert.equal(plain(sourceMetadata.bundle), bundle); assert.equal(plain(sourceMetadata.original), original);
  const originalSHA = sha(readFileSync(sourceDB)),sourceSeedSHA=sha(readFileSync(sourceSeed));
  const modules = ['game-adapter','security','p04d-crew','p04k-crew','p09e-research','p08b-battle','p04m-pool','p06t-mixed','p06t-ammo-loss','p08c-late-results'];
  const [{ createIdentityBridge }, security, crew, barracks, research, battle, pool, mixed, loss, late] = await Promise.all(
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
  const profiles = seed.profiles, accounts = profiles.map(p=>p.account_id);assert.equal(new Set(accounts).size,2);
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
    late_result_service:{version:1,contract:late.LATE_CONTRACT,policy_sha256:late.LATE_POLICY_SHA256,accounts}};
  const read=(action)=>database(game,action);
  const oldTables=()=>read(d=>Object.fromEntries(d.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'p08c_late_%' ORDER BY name").all()
    .map(r=>[r.name,d.prepare(`SELECT * FROM "${r.name.replaceAll('"','""')}"`).all()])));
  const roster=()=>read(d=>accounts.map(id=>({profile:JSON.parse(d.prepare('SELECT profile_json FROM game_profiles WHERE account_id=?').get(id).profile_json),
    aggregate:JSON.parse(d.prepare('SELECT snapshot_json FROM game_snapshot WHERE account_id=?').get(id).snapshot_json)})));
  const initial=roster();write(join(output,'initial.json'),initial);
  let bridge;
  function config(port,experimental){const v={login_bind:'127.0.0.1:26111',base_bind:'127.0.0.1:26112',identity_endpoint:`127.0.0.1:${port}`,
    identity_token_file:tokenFile,local_root:join(ROOT,'local'),session_duration_seconds:600,battle_players:2,p08c_late_results:true,p08c_late_results_accounts:accounts,p08c_late_notice_experimental:experimental};
    for(const key of ['ammunition_service','crew_service','crew_transfer','crew_cross_vehicle','crew_roster_recruitment','crew_progression','crew_dismissal',
      'crew_barracks_recruitment','research_service','profile13_battle','p04m_pool','p06t_mixed_ammo','visibility_v1','p06t_ammo_rack_detonation'])v[key]=true;
    return v; // Config ports validated only; no gameplay sockets bound.
  }
  async function withBarrier(phase,control,marker,go){const promise=child(executable,control,join(output,`${phase}.json`),join(output,phase),guard.test_name);
    let before;try{const deadline=performance.now()+120000;while(!existsSync(marker)){assert.ok(performance.now()<deadline,'Rust SQL barrier was not reached');
        await Promise.race([new Promise(done=>setTimeout(done,10)),promise.then(()=>{throw new Error('Child exited before expected SQL barrier');})]);}
      before=oldTables();write(join(output,`${phase}.before-late.json`),before);writeFileSync(go,'GO\n',{flag:'wx'});const result=await promise;assert.deepEqual(oldTables(),before,'Late append/read/ACK must leave every old row unchanged');return result;
    }finally{await promise.catch(()=>{});} // no bridge closure while owned child can mutate SQL
  }
  try{
    bridge=await createIdentityBridge(options);
    const ca=join(output,'config-a.private.json'),ia=join(output,'control-a.private.json');write(ca,config(bridge.port,false));
    write(ia,{schema:'p08c-late-result-composition.v1',phase:'manual_then_natural_append',config:ca,users,barrier:output,arena_id:'9007199254740993',expected_results_json:null,source_run_id:null});
    const a=await withBarrier('phase-a',ia,join(output,'after-finish.ready.json'),join(output,'after-finish.go'));
    assert.equal(a.real_job_admissions,2);assert.equal(a.real_job_finishes,2);assert.equal(a.actual_seal_before_reset,true);assert.equal(a.natural_result_same_arc,true);
    const saved=read(d=>d.prepare('SELECT * FROM p08c_late_result ORDER BY account_id').all());assert.equal(saved.length,1);assert.equal(saved[0].account_id,accounts[0]);assert.equal(saved[0].acked,0);
    const stored=read(d=>d.prepare('SELECT seal_json FROM p08c_late_seal').get());assert.deepEqual(JSON.parse(JSON.parse(stored.seal_json).results_json),JSON.parse(a.results_json));
    const beforeReopen=oldTables();await bridge.close();bridge=null;bridge=await createIdentityBridge(options);assert.deepEqual(oldTables(),beforeReopen);
    const cb=join(output,'config-b.private.json'),ib=join(output,'control-b.private.json');write(cb,config(bridge.port,true));
    write(ib,{schema:'p08c-late-result-composition.v1',phase:'discover_query_ack',config:cb,users,barrier:output,arena_id:a.arena_id,expected_results_json:a.results_json,source_run_id:a.run});
    const b=await withBarrier('phase-b',ib,join(output,'after-reopen-auth.ready.json'),join(output,'after-reopen-auth.go'));
    assert.notEqual(a.run,b.run);assert.equal(b.query_matches_actual_final_world,true);assert.equal(b.notice_experimental_source_static,true);assert.equal(b.real1501,true);
    assert.equal(read(d=>d.prepare('SELECT acked FROM p08c_late_result WHERE account_id=? AND arena_id=?').get(accounts[0],a.arena_id).acked),1);
    const final=roster();for(let i=0;i<2;i++){
      assert.deepEqual(final[i].profile.resources,initial[i].profile.resources);assert.deepEqual(final[i].aggregate.depot,initial[i].aggregate.depot);
      assert.deepEqual(final[i].aggregate.crew_inventory,initial[i].aggregate.crew_inventory);assert.deepEqual(final[i].aggregate.research,initial[i].aggregate.research);
      assert.deepEqual(final[i].profile.ammunition,initial[i].profile.ammunition);assert.ok(final[i].aggregate.vehicles.every(v=>v.state==='available'&&v.battle_id===null));
    }
    assert.equal(read(d=>d.prepare("SELECT count(*) AS n FROM p06t_reservation WHERE status='active'").get().n),0);
    assert.equal(sha(readFileSync(sourceDB)),originalSHA);assert.equal(sha(readFileSync(sourceSeed)),sourceSeedSHA);sourceGuard(guard);
    write(join(output,'result.json'),{status:'PASS_ACTUAL_LATE_HTTP_SQLITE_SYNTHETIC_SESSION_COMPOSITION',parent_full_gate:'PENDING_PARENT_FULL_GATE',native_client:'NOT_RUN',gameplay_udp:'NOT_RUN',jolt:'NOT_RUN',
      experimental_notice_method:'INFERRED_STATIC_ONLY',head:guard.head,executable_sha256:sha(readFileSync(executable)),source_database_sha256:originalSHA,
      actual_admit_finish_hooks:true,actual_seal_before_reset:true,immutable_natural_same_result:true,actual_append:true,bridge_reopen:true,actual_pending_discovery:true,actual_query1500_ack1501:true,
      old_table_equality_barriers:2,source_run:a.run,reopen_run:b.run,arena_id:a.arena_id});
  }finally{if(bridge)await bridge.close();assert.equal(sha(readFileSync(sourceDB)),originalSHA);assert.equal(sha(readFileSync(sourceSeed)),sourceSeedSHA);}
}
if(process.argv[1]&&localSpelling(process.argv[1])===localSpelling(fileURLToPath(import.meta.url))){main(process.argv.slice(2)).catch(error=>{console.error(error.stack||error);process.exitCode=1;});}
