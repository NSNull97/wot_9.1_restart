/** Real loopback HTTP/Python/SQLite; trusted terminal statistics are synthetic. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync, copyFileSync, existsSync, realpathSync } from 'node:fs';
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
import { testDirectory, removeTestDirectory } from './helpers.mjs';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const SEED = resolve(process.env.P06T_HTTP_SEED || join(ROOT, 'local/evidence/20261016-p06t-owned01/seed01/seed.json'));
const hash = v => createHash('sha256').update(v).digest('hex');
function db(path, fn) { const d = new DatabaseSync(path); try { return fn(d); } finally { d.close(); } }
test('P06T actual HTTP mixed reserve/result/restart and legacy second owner remain separated', {
  skip: existsSync(SEED) ? false : 'NOT_RUN: actual two-owner isolated P06T writer seed required', timeout: 180000,
}, async t => {
  const seed = JSON.parse(readFileSync(SEED)); assert.equal(seed.schema, 'p06t-http-real-writer-seed.v2'); assert.equal(seed.source_stand_writes, false);
  const before = hash(readFileSync(seed.database)), directory = testDirectory();
  const game = join(directory, 'game.sqlite'), identity = join(directory, 'identity.sqlite'), tokenFile = join(directory, 'identity.token');
  const backup = spawnSync('python', ['-B', '-c', 'import sqlite3,sys;from contextlib import closing;from pathlib import Path;\nwith closing(sqlite3.connect(Path(sys.argv[1]).resolve().as_uri()+"?mode=ro",uri=True))as a,closing(sqlite3.connect(sys.argv[2]))as b:a.backup(b)', seed.database, game], { cwd: ROOT, encoding: 'utf8', windowsHide: true });
  assert.equal(backup.status, 0, backup.stderr);
  const secret = token(), password = token(), passwordHash = await hashPassword(password); writeFileSync(tokenFile, secret);
  const native = join(directory, 'native.json'); copyFileSync(join(seed.bundle, 'content/inputs/native-ms1.blob'), native);
  const users = seed.profiles.map((p, i) => ({ profile: p, email: `p06t-http-${i}@example.test` }));
  db(identity, d => {
    d.exec('PRAGMA user_version=2; CREATE TABLE users(id TEXT PRIMARY KEY,username TEXT,display_nickname TEXT,email TEXT,password_hash TEXT,created_at INTEGER)');
    for (const u of users) d.prepare('INSERT INTO users VALUES (?,?,?,?,?,?)').run(u.profile.account_id, u.profile.username.toLowerCase(), u.profile.username, u.email, passwordHash, u.profile.created_at_ms);
  });
  db(game, d => d.prepare('INSERT INTO game_meta VALUES (?,?) ON CONFLICT(key)DO UPDATE SET value=excluded.value').run('native_descriptors_sha256', hash(readFileSync(native))));
  const python = spawnSync('python', ['-B', '-c', 'import sys;print(sys.executable)'], { encoding: 'utf8', windowsHide: true }).stdout.trim();
  const owner = seed.mixed_accounts[0], other = users.find(u => u.profile.account_id !== owner).profile.account_id;
  const options = { version: 1, port: 0, web_database: identity, game_database: game, fixture_root: join(directory, 'fixtures'), native_descriptors: native, python_executable: python, token_file: tokenFile,
    ammunition_service: { version: 1, bundle_root: seed.bundle, original_root: seed.original, account_id: owner, grant: { grant_id: 'p09d-test-depot-v1', quantity_each: 100 } },
    crew_service: { version: 1, policy_sha256: CREW_POLICY_SHA256 }, crew_transfer: { version: 1, policy_sha256: TRANSFER_POLICY_SHA256 },
    crew_cross_vehicle: { version: 1, policy_sha256: CROSS_CREW_POLICY_SHA256 }, crew_roster_recruitment: { version: 1, policy_sha256: ROSTER_CREW_POLICY_SHA256 },
    crew_progression: { version: 1, policy_sha256: PROGRESSION_CREW_POLICY_SHA256 }, crew_dismissal: { version: 1, policy_sha256: DISMISSAL_CREW_POLICY_SHA256 },
    crew_barracks_recruitment: { version: 1, policy_sha256: BARRACKS_CREW_POLICY_SHA256 }, research_service: { version: 1, policy_sha256: RESEARCH_POLICY_SHA256 },
    battle_service: { version: 1, policy_sha256: BATTLE_POLICY_SHA256, accounts: users.map(u => u.profile.account_id) },
    pool_service: { version: 1, policy_sha256: POOL_POLICY_SHA256, accounts: seed.pool_accounts },
    mixed_service: { version: 2, policy_sha256: MIXED_POLICY_SHA256, accounts: seed.mixed_accounts,
      shell_catalog: join(ROOT, 'tests/fixtures/p06t-shell-catalog.json'), terminal_policy: join(ROOT, 'tests/fixtures/p06t-device-policy.json') } };
  let bridge; const events = [];
  const close = async () => { if (bridge) await bridge.close(); bridge = null; };
  t.after(async () => { await close(); assert.equal(hash(readFileSync(seed.database)), before); removeTestDirectory(directory); });
  const profile = (id = owner) => db(game, d => JSON.parse(d.prepare('SELECT profile_json FROM game_profiles WHERE account_id=?').get(id).profile_json));
  const snapshot = (id = owner) => db(game, d => d.prepare('SELECT snapshot_json FROM game_snapshot WHERE account_id=?').get(id).snapshot_json);
  const secondBefore = snapshot(other); let serial = 0, run = '788fa1bf-8a21-4bdb-84de-a63310e390a3';
  const request = (operation, extra = {}) => ({ version: 2, operation, account_id: owner, native_database_id: profile().native_database_id,
    command_key: `p06t-http:${++serial}`, expected_revision: profile().snapshot_revision, run_id: run,
    ...(['admit', 'finish'].includes(operation) ? { battle_id: `${run}:9007199254740993`, native_inventory_id: 1 } : {}), ...extra });
  const call = async (path, data, authorization = secret) => {
    const start = Date.now(), r = await fetch(`http://127.0.0.1:${bridge.port}${path}`, { method: 'POST', headers: { Authorization: `Bearer ${authorization}`, 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
    const body = await r.json(); events.push({ path, http: r.status, status: body.status ?? null, code: body.code ?? null, milliseconds: Date.now() - start }); return { http: r.status, body };
  };
  const battle = async r => { const result = await call('/internal/native/battle', r); assert.equal(result.http, 200, JSON.stringify(result.body)); return result.body; };
  bridge = await createIdentityBridge(options);
  for (const id of [owner, other]) assert.equal((await call('/internal/native/login', { email: users.find(u => u.profile.account_id === id).email, password })).http, 200);
  assert.equal((await call('/internal/native/battle', request('inspect'), token())).http, 403);
  assert.equal((await call('/internal/native/battle', request('inspect', { native_database_id: profile().native_database_id + 1 }))).http, 403);
  assert.equal((await call('/internal/native/battle', { ...request('inspect'), version: 1 })).http, 400);
  assert.equal((await call('/internal/native/battle', { ...request('inspect'), account_id: other, native_database_id: profile(other).native_database_id })).http, 400);
  assert.equal((await battle(request('run_open'))).status, 'ready');
  const admitted = await battle(request('admit')); assert.deepEqual(admitted.reservation.frozen.ammunition.map(a => a.count), [0, 4, 11]);
  const fresh = await call('/internal/native/profile', { account_id: owner, native_database_id: profile().native_database_id }); assert.equal(fresh.http, 200);
  const companion = JSON.parse(readFileSync(join(fresh.body.fixture_dir, 'p06t-ammunition.json'))); assert.equal(companion.capabilities[0].code, 'VEHICLE_RESERVED');
  const garage = await call('/internal/native/ammo', { account_id: owner, native_database_id: profile().native_database_id, command_key: `p06t-http:${++serial}`, expected_revision: profile().snapshot_revision, wire_revision: 1, layout: [5, 1, 6, 2570, 0, 2826, 4, 3082, 10, 6, 0, 0, 0, 0, 0, 0] });
  assert.equal(garage.http, 200); assert.equal(garage.body.status, 'rejected');
  const vector = JSON.parse(readFileSync(join(ROOT, 'tests/fixtures/p06t-writer-vectors.json'))).vectors.find(v => v.request.operation === 'finish');
  const terminal = structuredClone(vector.response.reservation.result.terminal_state);
  terminal.crew = admitted.reservation.frozen.crew_ids.map(crew_id => ({ crew_id, alive: false }));
  const finish = request('finish', { reservation_id: admitted.reservation.reservation_id, remaining_ammunition: [{ shell_compact_id: 2570, count: 0 }, { shell_compact_id: 2826, count: 2 }, { shell_compact_id: 3082, count: 7 }], terminal_hp: 23,
    terminal_state_json: JSON.stringify(terminal), reason: 'battle_finished', results_json: vector.request.results_json });
  assert.equal((await battle(finish)).status, 'finished'); assert.equal((await battle(finish)).replayed, true);
  const query = { version: 2, operation: 'query', account_id: owner, native_database_id: profile().native_database_id, command_key: 'p06t-http:results:1', arena_id: '9007199254740993' };
  let result = await call('/internal/native/battle-results', query); assert.equal(result.http, 200); assert.equal(result.body.results_json, vector.request.results_json);
  assert.equal(profile().inventory[0].ammunition_count, 9); assert.equal(profile().inventory[0].health, 90);
  await close(); bridge = await createIdentityBridge(options); result = await call('/internal/native/battle-results', query); assert.equal(result.body.status, 'found');
  const ack = { ...query, operation: 'ack', command_key: 'p06t-http:results:2' }; assert.equal((await call('/internal/native/battle-results', ack)).body.acked, true);
  assert.equal((await call('/internal/native/battle-results', ack)).body.replayed, true);
  assert.equal((await call('/internal/native/battle-results', { ...ack, arena_id: '9007199254740994' })).body.code, 'DUPLICATE_PAYLOAD_MISMATCH');
  const second = await battle(request('admit', { battle_id: `${run}:9007199254740994` }));
  const oldFinish = request('finish', { battle_id: `${run}:9007199254740994`, reservation_id: second.reservation.reservation_id, remaining_ammunition: second.reservation.frozen.ammunition.map(a => ({ shell_compact_id: a.shell_compact_id, count: a.count })),
    terminal_hp: 23, terminal_state_json: JSON.stringify(terminal), reason: 'disconnect' });
  run = 'd5d1b671-eef4-4cb6-8b41-fc4201fc8aee'; const recovered = await battle(request('run_open'));
  assert.equal(recovered.reservation.status, 'aborted_restart'); assert.equal(recovered.reservation.result.terminal_state, null);
  assert.deepEqual(recovered.reservation.result.remaining_ammunition.map(a => a.count), [0, 2, 7]); assert.equal((await battle(oldFinish)).code, 'RUN_FENCED');
  assert.equal(snapshot(other), secondBefore, 'Every mixed operation preserves the legacy second owner');
  const wrong = structuredClone(options); wrong.mixed_service.accounts = [other]; await assert.rejects(() => createIdentityBridge(wrong), /P06T explicit owner subset/);
  if (process.env.P06T_HTTP_EVIDENCE_DIR) {
    const out = realpathSync(process.env.P06T_HTTP_EVIDENCE_DIR); assert.ok(out.toLowerCase().startsWith(realpathSync(join(ROOT, 'local')).toLowerCase() + '\\'));
    writeFileSync(join(out, 'http.json'), JSON.stringify({ status: 'PASS_REAL_HTTP_PYTHON_SQLITE', owner_count: 2, mixed_owner_count: 1, source_database_unchanged: true, native: 'NOT_RUN', events }, null, 2) + '\n', { flag: 'wx' });
  }
});
