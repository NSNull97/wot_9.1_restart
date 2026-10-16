/** Regular Cargo test composition controller. Actual HTTP/SQLite only after
 * guarded parent invocation. Authored Session/ACK/HP0: native/UDP NOT_RUN. */
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { createHash } from 'node:crypto';
import { spawn, spawnSync, execFileSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync, mkdirSync, realpathSync, openSync, closeSync, lstatSync } from 'node:fs';
import { resolve, join, relative, isAbsolute, dirname, basename, parse } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, '../../..'); // promoted web/tests/helpers -> repository
const TEST = 'gateway091::shared::server::p08b_restart_cas_tests::p08b_restart_cas_composition02_real_http_session_phase';
const SCOPES = ['server', 'tools', 'client_patch', 'web/src', 'tests', 'web/tests'];
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
function within(root, path) { const r = relative(root, path); assert.ok(r && !r.startsWith('..') && !isAbsolute(r)); return path; }
export function localSpelling(value) {
  assert.equal(typeof value, 'string');
  // Rust canonicalize uses \\?\D:\ whereas Python/Node normally retain D:\.
  // Normalize only a local drive spelling, never turn UNC into a local permit.
  if (value.startsWith('\\\\?\\')) value = value.slice(4);
  assert.match(value,/^[A-Za-z]:[\\/]/); assert.ok(isAbsolute(value)); return resolve(value);
}
function plain(value) {
  const path = localSpelling(value); let cursor = path;
  for (;;) { assert.equal(lstatSync(cursor).isSymbolicLink(), false, 'Linked/junction path refused'); const parent = dirname(cursor); if (parent === cursor) break; cursor = parent; }
  return realpathSync(path);
}
function readJson(path, budget = 16384) { const bytes = readFileSync(plain(path)); assert.ok(bytes.length <= budget); return JSON.parse(bytes); }
function keys(value, expected) { assert.ok(value && typeof value === 'object' && !Array.isArray(value)); assert.deepEqual(Object.keys(value).sort(), [...expected].sort()); }
function ref(value) {
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
function targetGuard(guard) {
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
  assert.equal(guard.schema, 'p08b-restart-cas-parent-in-progress.v1'); assert.equal(guard.full_gate, 'PENDING_PARENT_FULL_GATE');
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
  assert.equal(guard.files['server/gateway/src/shared/profile13_restart_cas_tests.rs'],guard.compiled_test_source_sha256);
  assert.equal(guard.files['web/tests/helpers/p08b-restart-cas.mjs'],guard.compiled_driver_sha256);
  assert.equal(sha(readFileSync(plain(fileURLToPath(import.meta.url)))),guard.compiled_driver_sha256);
  return targetGuard(guard);
}
function database(path, action) { const db = new DatabaseSync(path, { readOnly: true }); try { return action(db); } finally { db.close(); } }
function observe(path, account) {
  return database(path, db => ({
    profile: JSON.parse(db.prepare('SELECT profile_json FROM game_profiles WHERE account_id=?').get(account).profile_json),
    aggregate: JSON.parse(db.prepare('SELECT snapshot_json FROM game_snapshot WHERE account_id=?').get(account).snapshot_json),
    reservations: db.prepare('SELECT * FROM p08b_reservation WHERE account_id=? ORDER BY reservation_id').all(account),
    ledger: db.prepare('SELECT * FROM game_command_ledger WHERE account_id=? ORDER BY command_id').all(account),
    ammo: db.prepare('SELECT * FROM p09d_native_command WHERE account_id=? ORDER BY command_id').all(account),
    layouts: db.prepare('SELECT * FROM p09d_native_layout WHERE account_id=? ORDER BY native_vehicle_id').all(account),
  }));
}
function write(path, value) { writeFileSync(path, JSON.stringify(value, null, 2), { flag: 'wx' }); }
async function child(exe, control, output, prefix, name) {
  let out, err, owned, closed, timer, spawnError;
  try {
    out = openSync(`${prefix}.stdout.log`, 'wx'); err = openSync(`${prefix}.stderr.log`, 'wx');
    owned = spawn(exe, ['--exact', name, '--nocapture', '--test-threads=1'], { cwd: ROOT, windowsHide: true,
      env: { ...process.env, P08B_COMPOSITION_CONTROL: control, P08B_COMPOSITION_OUTPUT: output }, stdio: ['ignore', out, err] });
    // Keep the HTTP event loop alive. close is emitted after this exact child's
    // exit and stdio cleanup; retain its promise before installing the deadline.
    closed = new Promise(done => {
      owned.once('error', error => { spawnError = error; });
      owned.once('close', (code, signal) => done({ code, signal }));
    });
    const timeout = new Promise((_, fail) => { timer = setTimeout(() => fail(new Error('Own composition test timed out')), 100000); });
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
export async function main(args) {
const [mode, guardArgument, outputArgument, bundleArgument, originalArgument] = args;
assert.equal(mode, '--parent-full', 'This version only accepts the regular parent full-suite context');
assert.equal(args.length, 5);
const guardPath = plain(guardArgument), output = plain(outputArgument);
const outputBase = plain(join(ROOT, 'local/test-runs/p08b-composition02'));
assert.equal(dirname(output), outputBase); assert.match(output.slice(outputBase.length + 1), /^run-[0-9]+-[0-9]+$/);
assert.equal(guardPath, join(output, 'parent-control.json'));
const guard = readJson(guardPath, 4 * 1024 * 1024), executable = sourceGuard(guard);
const bundle = realpathSync(bundleArgument), original = realpathSync(originalArgument);
const [{ createIdentityBridge }, security, crew, barracks, research, battle] = await Promise.all([
  import(pathToFileURL(join(ROOT, 'web/src/game-adapter.mjs'))), import(pathToFileURL(join(ROOT, 'web/src/security.mjs'))),
  import(pathToFileURL(join(ROOT, 'web/src/p04d-crew.mjs'))), import(pathToFileURL(join(ROOT, 'web/src/p04k-crew.mjs'))),
  import(pathToFileURL(join(ROOT, 'web/src/p09e-research.mjs'))), import(pathToFileURL(join(ROOT, 'web/src/p08b-battle.mjs'))),
]);
const seeded = join(output, 'seed');
const prepared = spawnSync('python', ['-B', '-X', 'utf8', join(ROOT, 'tools/p09e_research_harness.py'),
  '--bundle', bundle, '--original', original, '--out', seeded, '--seed-only'], { cwd: ROOT, encoding: 'utf8', windowsHide: true, timeout: 120000 });
writeFileSync(join(output, 'seed.stdout.log'), prepared.stdout || '', { flag: 'wx' });
writeFileSync(join(output, 'seed.stderr.log'), prepared.stderr || '', { flag: 'wx' });assert.equal(prepared.status, 0);
const source = JSON.parse(readFileSync(join(bundle, 'content/fixtures/profile4/profile-input.json.blob')));
const native = join(bundle, 'content/inputs/native-ms1.blob'), game = join(seeded, 'game.sqlite'), identity = join(output, 'identity.sqlite');
const email = 'p08b-composition-own@example.test', password = security.token(), tokenFile = join(output, 'identity.token');
writeFileSync(tokenFile, security.token(), { flag: 'wx', mode: 0o600 });
const hash = await security.hashPassword(password);const db = new DatabaseSync(identity);
try {
  db.exec('PRAGMA user_version=2; CREATE TABLE users(id TEXT PRIMARY KEY,username TEXT,display_nickname TEXT,email TEXT,password_hash TEXT,created_at INTEGER)');
  db.prepare('INSERT INTO users VALUES (?,?,?,?,?,?)').run(source.account_id, source.username.toLowerCase(), source.username, email, hash, source.created_at_ms);
} finally { db.close(); }
const descriptorDB = new DatabaseSync(game);try { descriptorDB.prepare('INSERT INTO game_meta VALUES (?,?)').run('native_descriptors_sha256', sha(readFileSync(native))); } finally { descriptorDB.close(); }
const python = spawnSync('python', ['-B', '-c', 'import sys;print(sys.executable)'], { encoding: 'utf8', windowsHide: true });assert.equal(python.status, 0);
const options = { version: 1, port: 0, web_database: identity, game_database: game, fixture_root: join(output, 'fixtures'),
  native_descriptors: native, python_executable: python.stdout.trim(), token_file: tokenFile,
  ammunition_service: { version: 1, bundle_root: bundle, original_root: original, account_id: source.account_id,
    grant: { grant_id: 'p09d-test-depot-v1', quantity_each: 100 } },
  crew_service: { version: 1, policy_sha256: crew.CREW_POLICY_SHA256 }, crew_transfer: { version: 1, policy_sha256: crew.TRANSFER_POLICY_SHA256 },
  crew_cross_vehicle: { version: 1, policy_sha256: crew.CROSS_CREW_POLICY_SHA256 }, crew_roster_recruitment: { version: 1, policy_sha256: crew.ROSTER_CREW_POLICY_SHA256 },
  crew_progression: { version: 1, policy_sha256: crew.PROGRESSION_CREW_POLICY_SHA256 }, crew_dismissal: { version: 1, policy_sha256: crew.DISMISSAL_CREW_POLICY_SHA256 },
  crew_barracks_recruitment: { version: 1, policy_sha256: barracks.BARRACKS_CREW_POLICY_SHA256 }, research_service: { version: 1, policy_sha256: research.RESEARCH_POLICY_SHA256 },
  battle_service: { version: 1, policy_sha256: battle.BATTLE_POLICY_SHA256, accounts: [source.account_id] } };
let bridge;
function config(endpoint) {
  const value = { login_bind: '127.0.0.1:26101', base_bind: '127.0.0.1:26102', identity_endpoint: `127.0.0.1:${endpoint}`,
    identity_token_file: tokenFile, local_root: join(ROOT, 'local'), session_duration_seconds: 600,
    battle_players: 2 };
  for (const key of ['ammunition_service', 'crew_service', 'crew_transfer', 'crew_cross_vehicle', 'crew_roster_recruitment', 'crew_progression',
    'crew_dismissal', 'crew_barracks_recruitment', 'research_service', 'profile13_battle']) value[key] = true;
  return value; // Login/Base are validated only; NO game sockets are bound.
}
try {
  bridge = await createIdentityBridge(options);const initial = observe(game, source.account_id);write(join(output, 'initial.json'), initial);
  assert.equal(initial.profile.inventory[0].ammunition_count, 20);
  const configA = join(output, 'config-a.private.json'), controlA = join(output, 'control-a.private.json');
  write(configA, config(bridge.port));write(controlA, { schema: 'p08b-restart-cas-composition.v1', phase: 'reserve_then_exit', config: configA, email, password });
  const a = await child(executable, controlA, join(output, 'phase-a.json'), join(output, 'phase-a'), guard.test_name);
  const crashed = observe(game, source.account_id);write(join(output, 'after-child-exit.json'), crashed);
  assert.equal(crashed.reservations.length, 1);assert.equal(crashed.reservations[0].status, 'active');
  assert.equal(crashed.reservations[0].reservation_id, a.reservation);
  await bridge.close();bridge = null;bridge = await createIdentityBridge(options);
  assert.deepEqual(observe(game, source.account_id), crashed, 'Bridge reopen alone must not guess gateway crash');
  const configB = join(output, 'config-b.private.json'), controlB = join(output, 'control-b.private.json');
  write(configB, config(bridge.port));write(controlB, { schema: 'p08b-restart-cas-composition.v1', phase: 'restart_warm_then_cas', config: configB, email, password });
  const b = await child(executable, controlB, join(output, 'phase-b.json'), join(output, 'phase-b'), guard.test_name);
  const final = observe(game, source.account_id);write(join(output, 'final.json'), final);
  assert.notEqual(a.run,b.run,'Config::load creates the real new gateway run');
  assert.equal(b.initial_revision, a.revision + 1);assert.equal(b.final_revision, b.initial_revision + 4);
  assert.equal(final.profile.snapshot_revision, b.final_revision);assert.equal(b.warm_revision, 2);assert.equal(b.full_revision, 1);assert.equal(b.final_wire, 2);
  assert.equal(final.reservations.length, 2);const recovered = final.reservations.find(row => row.reservation_id === a.reservation);
  const finished = final.reservations.find(row => row.reservation_id === b.reservation);
  assert.equal(recovered.status, 'aborted_restart');assert.equal(finished.status, 'finished');
  assert.equal(JSON.parse(recovered.result_json).consumed_ap, 0);assert.equal(JSON.parse(recovered.result_json).remaining_ap, 20);
  assert.deepEqual(JSON.parse(finished.result_json), { reason: 'manual_leave', remaining_ap: 19, consumed_ap: 0, terminal_hp: 0, destroyed: true, repaired_hp: 90, credits: 0, xp: 0 });
  for (const key of ['resources']) assert.deepEqual(final.profile[key], initial.profile[key]);
  for (const key of ['crew_inventory', 'research']) assert.deepEqual(final.aggregate[key], initial.aggregate[key]);
  for (const [shell,count] of Object.entries(initial.aggregate.depot)) assert.equal(final.aggregate.depot[shell],count+(shell==='shell:ms1-stock-ap'?2:0));
  assert.ok(final.aggregate.vehicles.every(row => row.state === 'available' && row.battle_id === null));
  assert.equal(final.profile.inventory[0].ammunition_count, 18);assert.equal(final.profile.inventory[0].health, 90);
  assert.equal(final.ammo.length, initial.ammo.length + 2);
  for(const old of initial.ledger)assert.deepEqual(final.ledger.find(row=>row.command_id===old.command_id),old);
  assert.deepEqual(JSON.parse(final.layouts.find(row=>row.native_vehicle_id===1).layout_json),[2570,18,2826,0,3082,0]);
  for(const old of initial.reservations)assert.deepEqual(final.reservations.find(row=>row.reservation_id===old.reservation_id),old);
  assert.equal(sha(readFileSync(join(b.fresh_fixture, 'state.bin'))), b.fresh_state_sha256);
  sourceGuard(guard);
  write(join(output, 'result.json'), { status: 'PASS_ACTUAL_HTTP_SQLITE_SYNTHETIC_SESSION_COMPOSITION', native_client: 'NOT_RUN', gameplay_udp: 'NOT_RUN',
    geometry_death: 'NOT_RUN_AUTHORED_HP0', parent_full_gate: 'PENDING_PARENT_FULL_GATE', account: source.account_id, executable_sha256: sha(readFileSync(executable)), head: guard.head,
    process_restart: true, bridge_reopen: true, recovery_once: true, full_state_sha256: b.fresh_state_sha256,
    warm_source: 2, full_source: 1, post_full_cas_wire: 2, baseline_revision: initial.profile.snapshot_revision, final_revision: b.final_revision });
} finally { if (bridge) await bridge.close(); }

}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main(process.argv.slice(2)).catch(error => { console.error(error.stack || error); process.exitCode = 1; });
}
