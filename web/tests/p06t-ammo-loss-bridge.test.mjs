/** Actual HTTP -> selected Python worker -> fresh SQLite backup. No native UI. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync, copyFileSync, existsSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createIdentityBridge } from '../src/game-adapter.mjs';
import { hashPassword, token } from '../src/security.mjs';
import { CREW_POLICY_SHA256, TRANSFER_POLICY_SHA256, CROSS_CREW_POLICY_SHA256, ROSTER_CREW_POLICY_SHA256,
  PROGRESSION_CREW_POLICY_SHA256, DISMISSAL_CREW_POLICY_SHA256 } from '../src/p04d-crew.mjs';
import { BARRACKS_CREW_POLICY_SHA256 } from '../src/p04k-crew.mjs';
import { RESEARCH_POLICY_SHA256 } from '../src/p09e-research.mjs';
import { BATTLE_POLICY_SHA256 } from '../src/p08b-battle.mjs';
import { POOL_POLICY_SHA256 } from '../src/p04m-pool.mjs';
import { MIXED_POLICY_SHA256 } from '../src/p06t-mixed.mjs';
import { LOSS_CONTRACT, LOSS_POLICY_SHA256 } from '../src/p06t-ammo-loss.mjs';
import { testDirectory, removeTestDirectory } from './helpers.mjs';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const SEED = resolve(process.env.P06T_HTTP_SEED || join(ROOT, 'local/evidence/20261016-p06t-owned01/seed01/seed.json'));
const hash = v => createHash('sha256').update(v).digest('hex');
function db(path, fn) { const d = new DatabaseSync(path); try { return fn(d); } finally { d.close(); } }
test('v4 actual HTTP loss accounting, native projection, reopen/archive and old-owner isolation', {
  skip: existsSync(SEED) ? false : 'NOT_RUN: actual two-owner P06T source seed required', timeout: 240000,
}, async t => {
  const seed = JSON.parse(readFileSync(SEED)); assert.equal(seed.schema, 'p06t-http-real-writer-seed.v2'); assert.equal(seed.source_stand_writes, false);
  const originalSha = hash(readFileSync(seed.database)), directory = testDirectory(), game = join(directory, 'game.sqlite');
  const cleanEnv = { ...process.env }; delete cleanEnv.PYTHONPATH;
  const backup = spawnSync('python', ['-B', '-c', 'import sqlite3,sys;from contextlib import closing;from pathlib import Path;\nwith closing(sqlite3.connect(Path(sys.argv[1]).resolve().as_uri()+"?mode=ro",uri=True))as a,closing(sqlite3.connect(sys.argv[2]))as b:a.backup(b)', seed.database, game], { cwd: ROOT, encoding: 'utf8', windowsHide: true, env: cleanEnv });
  assert.equal(backup.status, 0, backup.stderr);
  const python = spawnSync('python', ['-B', '-c', 'import sys;print(sys.executable)'], { encoding: 'utf8', windowsHide: true, env: cleanEnv }).stdout.trim();
  const profile = id => db(game, d => JSON.parse(d.prepare('SELECT profile_json FROM game_profiles WHERE account_id=?').get(id).profile_json));
  const owner = seed.mixed_accounts[0], other = seed.profiles.find(p => p.account_id !== owner).account_id;
  const snapshot = id => db(game, d => d.prepare('SELECT snapshot_json FROM game_snapshot WHERE account_id=?').get(id).snapshot_json);
  const sourcePaths = ['--mixed-ammo', '--shell-catalog', join(ROOT, 'tests/fixtures/p06t-shell-catalog.json'), '--terminal-policy', join(ROOT, 'tests/fixtures/p06t-device-policy.json')];
  const activate = spawnSync(python, ['-B', join(ROOT, 'tools/p08b_battle_service.py'), '--database', game, '--bundle', seed.bundle, '--original-root', seed.original,
    '--account-id', owner, '--fixture-root', join(directory, 'fixtures'), ...sourcePaths, '--ammo-rack-loss', 'loss-activate'],
  { cwd: directory, encoding: 'utf8', windowsHide: true, env: cleanEnv, timeout: 40000,
    input: JSON.stringify({ version: 4, contract: LOSS_CONTRACT, account_id: owner, native_database_id: profile(owner).native_database_id,
      expected_revision: profile(owner).snapshot_revision, policy_sha256: LOSS_POLICY_SHA256 }) });
  assert.equal(activate.status, 0, activate.stderr); assert.equal(JSON.parse(activate.stdout).status, 'active');
  const identity = join(directory, 'identity.sqlite'), tokenFile = join(directory, 'identity.token'), native = join(directory, 'native.json');
  const secret = token(), password = token(), passwordHash = await hashPassword(password); writeFileSync(tokenFile, secret);
  copyFileSync(join(seed.bundle, 'content/inputs/native-ms1.blob'), native);
  const users = seed.profiles.map((p, i) => ({ profile: p, email: `loss-http-${i}@example.test` }));
  db(identity, d => { d.exec('PRAGMA user_version=2; CREATE TABLE users(id TEXT PRIMARY KEY,username TEXT,display_nickname TEXT,email TEXT,password_hash TEXT,created_at INTEGER)');
    for (const u of users) d.prepare('INSERT INTO users VALUES (?,?,?,?,?,?)').run(u.profile.account_id, u.profile.username.toLowerCase(), u.profile.username, u.email, passwordHash, u.profile.created_at_ms); });
  db(game, d => d.prepare('INSERT INTO game_meta VALUES (?,?) ON CONFLICT(key)DO UPDATE SET value=excluded.value').run('native_descriptors_sha256', hash(readFileSync(native))));
  const options = { version: 1, port: 0, web_database: identity, game_database: game, fixture_root: join(directory, 'fixtures'), native_descriptors: native, python_executable: python, token_file: tokenFile,
    ammunition_service: { version: 1, bundle_root: seed.bundle, original_root: seed.original, account_id: owner, grant: { grant_id: 'p09d-test-depot-v1', quantity_each: 100 } },
    crew_service: { version: 1, policy_sha256: CREW_POLICY_SHA256 }, crew_transfer: { version: 1, policy_sha256: TRANSFER_POLICY_SHA256 },
    crew_cross_vehicle: { version: 1, policy_sha256: CROSS_CREW_POLICY_SHA256 }, crew_roster_recruitment: { version: 1, policy_sha256: ROSTER_CREW_POLICY_SHA256 },
    crew_progression: { version: 1, policy_sha256: PROGRESSION_CREW_POLICY_SHA256 }, crew_dismissal: { version: 1, policy_sha256: DISMISSAL_CREW_POLICY_SHA256 },
    crew_barracks_recruitment: { version: 1, policy_sha256: BARRACKS_CREW_POLICY_SHA256 }, research_service: { version: 1, policy_sha256: RESEARCH_POLICY_SHA256 },
    battle_service: { version: 1, policy_sha256: BATTLE_POLICY_SHA256, accounts: users.map(u => u.profile.account_id) }, pool_service: { version: 1, policy_sha256: POOL_POLICY_SHA256, accounts: seed.pool_accounts },
    mixed_service: { version: 2, policy_sha256: MIXED_POLICY_SHA256, accounts: seed.mixed_accounts, shell_catalog: sourcePaths[2], terminal_policy: sourcePaths[4] },
    ammo_loss_service: { version: 4, contract: LOSS_CONTRACT, policy_sha256: LOSS_POLICY_SHA256, accounts: [owner] } };
  let bridge, serial = 0; const events = []; const close = async () => { if (bridge) await bridge.close(); bridge = null; };
  t.after(async () => { await close(); assert.equal(hash(readFileSync(seed.database)), originalSha); removeTestDirectory(directory); });
  const call = async (path, value, authorization = secret) => {
    const start = Date.now(), response = await fetch(`http://127.0.0.1:${bridge.port}${path}`, { method: 'POST', headers: { Authorization: `Bearer ${authorization}`, 'Content-Type': 'application/json' }, body: JSON.stringify(value) });
    const body = await response.json(); events.push({ path, http: response.status, status: body.status ?? null, code: body.code ?? null, milliseconds: Date.now() - start }); return { http: response.status, body };
  };
  const battle = async value => { const r = await call('/internal/native/battle', value); assert.equal(r.http, 200, JSON.stringify(r.body)); return r.body; };
  const run = '788fa1bf-8a21-4bdb-84de-a63310e390a3';
  const request = (operation, fields = {}) => ({ version: 4, contract: LOSS_CONTRACT, operation, account_id: owner, native_database_id: profile(owner).native_database_id,
    command_key: `loss-http:${++serial}`, expected_revision: profile(owner).snapshot_revision, run_id: run,
    ...(['admit', 'finish'].includes(operation) ? { battle_id: `${run}:9007199254740993`, native_inventory_id: 1 } : {}), ...fields });
  bridge = await createIdentityBridge(options); const otherBefore = snapshot(other);
  for (const u of users) assert.equal((await call('/internal/native/login', { email: u.email, password })).http, 200);
  assert.equal((await call('/internal/native/battle', request('inspect'), token())).http, 403);
  assert.equal((await call('/internal/native/battle', request('inspect', { native_database_id: profile(owner).native_database_id + 1 }))).http, 403);
  const old = request('inspect'); delete old.contract; old.version = 2; assert.equal((await call('/internal/native/battle', old)).http, 400);
  assert.equal((await call('/internal/native/battle', request('inspect', { account_id: other, native_database_id: profile(other).native_database_id }))).http, 400);
  const load = await call('/internal/native/ammo', { account_id: owner, native_database_id: profile(owner).native_database_id, command_key: `loss-http:${++serial}`,
    expected_revision: profile(owner).snapshot_revision, wire_revision: 1, layout: [5,1,6,2570,0,2826,4,3082,10,6,0,0,0,0,0,0] });
  assert.equal(load.http, 200); assert.notEqual(load.body.status, 'rejected');
  const depotBefore = db(game, d => d.prepare('SELECT shell_id,quantity FROM p09c_ammo_depot WHERE account_id=? ORDER BY shell_id').all(owner));
  assert.equal((await battle(request('run_open'))).status, 'ready');
  const admitted = await battle(request('admit')); const frozen = admitted.reservation.frozen.loadout;
  assert.deepEqual(frozen.ammunition.map(a => a.count), [0,4,10]);
  const vector = JSON.parse(readFileSync(join(ROOT, 'tests/fixtures/p06t-ammo-loss-writer-vectors.json'))).vectors.find(v => v.request.operation === 'finish');
  const terminal = JSON.parse(vector.request.terminal_state_json); terminal.crew = frozen.crew_ids.map(crew_id => ({ crew_id, alive: true }));
  const stats = JSON.parse(vector.request.results_json), own = stats.participants[0], peer = stats.participants[1];
  own.account_dbid = profile(owner).native_database_id; own.name = profile(owner).username;
  peer.account_dbid = profile(other).native_database_id; peer.name = profile(other).username;
  // JSON.parse cannot retain this >2^53 arena integer. Preserve the original
  // canonical token while changing only the authored owner identity fields.
  const arenaToken = vector.request.results_json.match(/"arena_id":([1-9][0-9]*)/)[1];
  assert.equal(arenaToken, '9007199254740993');
  const resultsJson = JSON.stringify(stats).replace(/"arena_id":[1-9][0-9]*/, `"arena_id":${arenaToken}`);
  const finish = request('finish', { reservation_id: admitted.reservation.reservation_id,
    remaining_ammunition: vector.request.remaining_ammunition, fired_ammunition: vector.request.fired_ammunition,
    lost_ammunition: vector.request.lost_ammunition, loss_event: vector.request.loss_event, terminal_hp: 0, reason: 'battle_finished',
    terminal_state_json: JSON.stringify(terminal), results_json: resultsJson });
  const finished = await battle(finish); assert.equal(finished.status, 'finished', JSON.stringify(finished)); assert.equal((await battle(finish)).replayed, true);
  assert.equal(profile(owner).inventory[0].ammunition_count, 0); assert.equal(profile(owner).inventory[0].health, 90);
  assert.deepEqual(db(game, d => d.prepare('SELECT shell_id,quantity FROM p09c_ammo_depot WHERE account_id=? ORDER BY shell_id').all(owner)), depotBefore);
  const fresh = await call('/internal/native/profile', { account_id: owner, native_database_id: profile(owner).native_database_id }); assert.equal(fresh.http, 200);
  const companion = JSON.parse(readFileSync(join(fresh.body.fixture_dir, 'p06t-ammo-loss.json'))); assert.equal(companion.policy_sha256, LOSS_POLICY_SHA256);
  assert.equal(companion.state_sha256, hash(readFileSync(join(fresh.body.fixture_dir, 'state.bin'))));
  const query = { version: 4, contract: LOSS_CONTRACT, operation: 'query', account_id: owner, native_database_id: profile(owner).native_database_id, command_key: 'loss-http:query', arena_id: '9007199254740993' };
  let result = await call('/internal/native/battle-results', query); assert.equal(result.http, 200); assert.equal(result.body.record_contract, 'loss-v1');
  assert.equal(JSON.parse(result.body.results_json).participants[0].shots, 3);
  await close(); bridge = await createIdentityBridge(options); result = await call('/internal/native/battle-results', query); assert.equal(result.body.status, 'found');
  const ack = { ...query, operation: 'ack', command_key: 'loss-http:ack' }; assert.equal((await call('/internal/native/battle-results', ack)).body.acked, true);
  assert.equal((await call('/internal/native/battle-results', ack)).body.replayed, true);
  assert.equal((await battle(request('admit', { battle_id: `${run}:9007199254740994` }))).code, 'AMMUNITION_EMPTY');
  assert.equal(snapshot(other), otherBefore, 'Global loss namespace preserves actual legacy second owner');
  if (process.env.P06T_LOSS_HTTP_EVIDENCE) writeFileSync(process.env.P06T_LOSS_HTTP_EVIDENCE,
    JSON.stringify({ status: 'PASS_REAL_HTTP_PYTHON_SQLITE', source_database_unchanged: true, new_owner_count: 1, legacy_owner_count: 1, fired: 3, loaded_after: 0, depot_preserved: true, native: 'NOT_RUN', events }, null, 2) + '\n', { flag: 'wx' });
});
