/** Runs the actual tracked adapter, worker and isolated SQLite owner gates. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync, copyFileSync, mkdirSync } from 'node:fs';
import { join, resolve, basename } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createIdentityBridge } from '../src/game-adapter.mjs';
import { LATE_CONTRACT, LATE_POLICY_SHA256 } from '../src/p08c-late-results.mjs';
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
const STAGE = fileURLToPath(new URL('../../', import.meta.url));
const hash = v => createHash('sha256').update(v).digest('hex');
const cleanEnv = { ...process.env }; delete cleanEnv.PYTHONPATH;
function db(path, fn) { const d = new DatabaseSync(path); try { return fn(d); } finally { d.close(); } }
test('actual adapter HTTP append/read/ack/reopen with owner gates and old-owner isolation', { timeout: 180000 }, async t => {
  const directory = testDirectory(), game = join(directory, 'game.sqlite');
  const python = spawnSync('python', ['-B', '-c', 'import sys;print(sys.executable)'], { encoding: 'utf8', windowsHide: true, env: cleanEnv }).stdout.trim();
  const seeded = spawnSync(python, ['-B', join(ROOT, 'tests/p08c_late_http_seed.py'), game], { cwd: directory, encoding: 'utf8', windowsHide: true, env: cleanEnv, timeout: 60000 });
  assert.equal(seeded.status, 0, seeded.stderr);
  const seed = JSON.parse(readFileSync(game.replace('.sqlite', '.json'))), owner = seed.request.account_id, other = seed.profiles.find(p => p.account_id !== owner).account_id;
  const identity = join(directory, 'identity.sqlite'), tokenFile = join(directory, 'identity.token'), native = join(directory, 'native.json');
  const secret = token(), passwordHash = await hashPassword(token()); writeFileSync(tokenFile, secret);
  copyFileSync(join(seed.bundle, 'content/inputs/native-ms1.blob'), native);
  db(identity, d => { d.exec('PRAGMA user_version=2; CREATE TABLE users(id TEXT PRIMARY KEY,username TEXT,display_nickname TEXT,email TEXT,password_hash TEXT,created_at INTEGER)');
    seed.profiles.forEach((p, i) => d.prepare('INSERT INTO users VALUES (?,?,?,?,?,?)').run(p.account_id, p.username.toLowerCase(), p.username, `late-${i}@example.test`, passwordHash, p.created_at_ms)); });
  db(game, d => d.prepare('INSERT INTO game_meta VALUES (?,?) ON CONFLICT(key)DO UPDATE SET value=excluded.value').run('native_descriptors_sha256', hash(readFileSync(native))));
  const shellCatalog = join(ROOT, 'tests/fixtures/p06t-shell-catalog.json'), terminalPolicy = join(ROOT, 'tests/fixtures/p06t-device-policy.json');
  const accounts = seed.profiles.map(p => p.account_id);
  const options = { version: 1, port: 0, web_database: identity, game_database: game, fixture_root: join(directory, 'fixtures'), native_descriptors: native, python_executable: python, token_file: tokenFile,
    ammunition_service: { version: 1, bundle_root: seed.bundle, original_root: seed.original, account_id: owner, grant: { grant_id: 'p09d-test-depot-v1', quantity_each: 100 } },
    crew_service: { version: 1, policy_sha256: CREW_POLICY_SHA256 }, crew_transfer: { version: 1, policy_sha256: TRANSFER_POLICY_SHA256 }, crew_cross_vehicle: { version: 1, policy_sha256: CROSS_CREW_POLICY_SHA256 },
    crew_roster_recruitment: { version: 1, policy_sha256: ROSTER_CREW_POLICY_SHA256 }, crew_progression: { version: 1, policy_sha256: PROGRESSION_CREW_POLICY_SHA256 }, crew_dismissal: { version: 1, policy_sha256: DISMISSAL_CREW_POLICY_SHA256 },
    crew_barracks_recruitment: { version: 1, policy_sha256: BARRACKS_CREW_POLICY_SHA256 }, research_service: { version: 1, policy_sha256: RESEARCH_POLICY_SHA256 },
    battle_service: { version: 1, policy_sha256: BATTLE_POLICY_SHA256, accounts }, pool_service: { version: 1, policy_sha256: POOL_POLICY_SHA256, accounts },
    mixed_service: { version: 2, policy_sha256: MIXED_POLICY_SHA256, accounts, shell_catalog: shellCatalog, terminal_policy: terminalPolicy },
    ammo_loss_service: { version: 4, contract: LOSS_CONTRACT, policy_sha256: LOSS_POLICY_SHA256, accounts },
    late_result_service: { version: 1, contract: LATE_CONTRACT, policy_sha256: LATE_POLICY_SHA256, accounts: [owner] } };
  let bridge; const events = []; const close = async () => { if (bridge) await bridge.close(); bridge = null; };
  t.after(async () => { await close(); removeTestDirectory(directory); });
  const readOld = () => db(game, d => Object.fromEntries(d.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'p08c_late_%'").all()
    .map(r => [r.name, d.prepare(`SELECT * FROM "${r.name}"`).all()])));
  const profile = id => db(game, d => JSON.parse(d.prepare('SELECT profile_json FROM game_profiles WHERE account_id=?').get(id).profile_json));
  const call = async (path, value, headers = {}) => {
    const start = performance.now(), response = await fetch(`http://127.0.0.1:${bridge.port}${path}`, { method: 'POST', headers: { Authorization: `Bearer ${secret}`, 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(value) });
    const body = await response.json(); events.push({ path, http: response.status, status: body.status ?? null, code: body.code ?? null, milliseconds: Math.round(performance.now() - start) }); return { http: response.status, body };
  };
  const { late_result_service, ...oldConfig } = options;
  bridge = await createIdentityBridge(oldConfig);
  assert.equal((await call('/internal/native/late-result-append', seed.request)).http, 404); await close();
  bridge = await createIdentityBridge(options); const before = readOld(), request = seed.request;
  const route = '/internal/native/late-result-append';
  const pendingRoute = '/internal/native/late-result-pending';
  const pending = { version: 1, contract: LATE_CONTRACT, operation: 'pending', account_id: owner,
    native_database_id: request.native_database_id, command_key: 'late:http:pending', after_arena_id: null };
  assert.deepEqual((await call(pendingRoute, pending)).body.rows, []);
  assert.equal((await call(pendingRoute, { ...pending, after_arena_id: 9007199254740993 })).http, 400);
  assert.equal((await call(route, request, { Authorization: `Bearer ${token()}` })).http, 403);
  assert.equal((await call(route, request, { Origin: 'http://127.0.0.1' })).http, 403);
  assert.equal((await call(route, { ...request, account_id: other, native_database_id: profile(other).native_database_id })).http, 403);
  assert.equal((await call(route, { ...request, native_database_id: request.native_database_id + 1 })).http, 403);
  assert.equal((await call(route, { ...request, version: 4 })).http, 400);
  assert.equal((await call(route, { ...request, seal_json: 'x'.repeat(65537) })).http, 413);
  const wrong = await call(route, { ...request, release_terminal_sha256: '0'.repeat(64) });
  assert.equal(wrong.http, 200); assert.equal(wrong.body.code, 'RESULT_MISMATCH');
  const stamp = { ...request, operation: 'release_stamp', command_key: 'late:http:stamp' }; delete stamp.release_terminal_sha256; delete stamp.finished_revision; delete stamp.seal_json;
  assert.equal((await call(route, stamp)).body.status, 'stamped');
  const appended = await call(route, request); assert.equal(appended.http, 200); assert.equal(appended.body.status, 'appended');
  assert.equal((await call(route, request)).body.replayed, true); assert.deepEqual(readOld(), before);
  const waiting = await call(pendingRoute, pending); assert.equal(waiting.http, 200); assert.equal(waiting.body.rows.length, 1);
  assert.equal(waiting.body.rows[0].arena_id, request.arena_id); assert.equal(waiting.body.rows[0].vehicle_type_compact_id, 3329);
  assert.equal((await call(pendingRoute, pending)).body.rows[0].seal_sha256, waiting.body.rows[0].seal_sha256);
  const query = { version: 4, contract: LOSS_CONTRACT, operation: 'query', account_id: owner, native_database_id: request.native_database_id, command_key: 'late:http:query', arena_id: request.arena_id };
  const found = await call('/internal/native/battle-results', query); assert.equal(found.http, 200); assert.equal(found.body.results_json, seed.results_json); assert.equal(found.body.record_contract, 'loss-v1');
  const conflictingAck = await call('/internal/native/battle-results', { ...query, operation: 'ack', command_key: request.command_key });
  assert.equal(conflictingAck.http, 200); assert.equal(conflictingAck.body.code, 'DUPLICATE_PAYLOAD_MISMATCH'); assert.equal(conflictingAck.body.acked, false);
  await close(); bridge = await createIdentityBridge(options);
  assert.equal((await call('/internal/native/battle-results', query)).body.status, 'found');
  const ack = { ...query, operation: 'ack', command_key: 'late:http:ack' };
  assert.equal((await call('/internal/native/battle-results', ack)).body.acked, true);
  assert.equal((await call('/internal/native/battle-results', ack)).body.replayed, true); assert.deepEqual(readOld(), before);
  assert.deepEqual((await call(pendingRoute, pending)).body.rows, []);
  const peerQuery = { ...query, account_id: other, native_database_id: profile(other).native_database_id, command_key: 'late:http:peer' };
  const peer = await call('/internal/native/battle-results', peerQuery); assert.equal(peer.http, 200); assert.equal(peer.body.status, 'found');
  await close();
  await assert.rejects(createIdentityBridge(oldConfig), /reader policy required/);
  bridge = await createIdentityBridge(options); assert.equal((await call('/internal/native/battle-results', query)).body.acked, true);
  assert.deepEqual(readOld(), before);
  // The selected public battle method must use the very same late-aware store.
  const currentRun = '918a034b-cba0-426a-85e9-a1a095aa0162'; let serial = 0;
  const battleRequest = (operation, extra = {}) => ({ version: 4, contract: LOSS_CONTRACT, operation, account_id: owner,
    native_database_id: request.native_database_id, command_key: `late:http:battle:${++serial}`,
    expected_revision: profile(owner).snapshot_revision, run_id: currentRun, ...extra });
  const battle = async value => { const reply = await call('/internal/native/battle', value); assert.equal(reply.http, 200); return reply.body; };
  const sourceFinal = JSON.parse(request.seal_json).actors.find(a => a.account_id === owner).final_actor;
  const finishRequest = (receipt, natural) => battleRequest('finish', { battle_id: receipt.battle_id, native_inventory_id: 1,
    reservation_id: receipt.reservation_id, remaining_ammunition: sourceFinal.remaining_ammunition,
    fired_ammunition: sourceFinal.fired_ammunition, lost_ammunition: sourceFinal.lost_ammunition, loss_event: null,
    terminal_hp: sourceFinal.terminal_hp, terminal_state_json: JSON.stringify(sourceFinal.terminal_state),
    reason: natural ? 'battle_finished' : 'cancelled', ...(natural ? { results_json: natural } : {}) });
  const peerOld = db(game, d => Object.fromEntries(d.prepare("SELECT name FROM sqlite_master WHERE type='table'").all()
    .filter(r => d.prepare(`PRAGMA table_info("${r.name}")`).all().some(c => c.name === 'account_id'))
    .map(r => [r.name, d.prepare(`SELECT * FROM "${r.name}" WHERE account_id=?`).all(other)])));
  assert.equal((await battle(battleRequest('run_open'))).status, 'ready');
  const reserved = await battle(battleRequest('admit', { battle_id: `${currentRun}:${request.arena_id}`, native_inventory_id: 1 }));
  assert.equal(reserved.status, 'admitted');
  const collision = finishRequest(reserved.reservation, seed.results_json), oldBeforeCollision = readOld();
  const denied = await battle(collision); assert.equal(denied.status, 'rejected'); assert.equal(denied.code, 'RESULT_MISMATCH');
  assert.deepEqual(readOld(), oldBeforeCollision); // Finish/CAS/ammo/ledger all roll back.
  assert.equal((await battle(finishRequest(reserved.reservation, null))).status, 'finished');
  const newArena = '9007199254740994';
  const next = await battle(battleRequest('admit', { battle_id: `${currentRun}:${newArena}`, native_inventory_id: 1 }));
  assert.equal(next.status, 'admitted');
  const natural = seed.results_json.replace('"arena_id":9007199254740993', '"arena_id":9007199254740994');
  assert.notEqual(natural, seed.results_json);
  const finished = await battle(finishRequest(next.reservation, natural)); assert.equal(finished.status, 'finished');
  assert.equal((await battle(finishRequest(next.reservation, natural))).code, 'RESERVATION_TERMINAL');
  assert.equal((await call('/internal/native/battle-results', query)).body.results_json, seed.results_json);
  assert.equal((await call('/internal/native/battle-results', { ...query, arena_id: newArena, command_key: 'late:http:next-query' })).body.results_json, natural.replace(/[\u0080-\uffff]/g, c => '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0')));
  const peerAfter = db(game, d => Object.fromEntries(d.prepare("SELECT name FROM sqlite_master WHERE type='table'").all()
    .filter(r => d.prepare(`PRAGMA table_info("${r.name}")`).all().some(c => c.name === 'account_id'))
    .map(r => [r.name, d.prepare(`SELECT * FROM "${r.name}" WHERE account_id=?`).all(other)])));
  assert.deepEqual(peerAfter, peerOld);
  assert.equal((await call('/internal/native/battle', { ...battleRequest('inspect'), version: 2 })).http, 400);
  const receipt = { status: 'PASS_ACTUAL_HTTP_SQL_COMPONENT', native: 'NOT_RUN', active_source_mutations: false, source_database_sha256: seed.source_database_sha256,
    PYTHONPATH_removed_in_worker: true, adapter: { mode: 'ACTUAL_TRACKED_SOURCE', sha256: hash(readFileSync(join(ROOT, 'web/src/game-adapter.mjs'))) }, events,
    worker_sha256: hash(readFileSync(join(STAGE, 'tools/p08c_late_results_service.py'))), module_sha256: hash(readFileSync(join(STAGE, 'web/src/p08c-late-results.mjs'))) };
  const output = join(ROOT, 'local/evidence/20261017-p08c-late-active01', basename(directory)); mkdirSync(output, { recursive: true });
  writeFileSync(join(output, `${process.env.LATE_HTTP_RECEIPT || 'http01'}.json`), JSON.stringify(receipt, null, 2) + '\n', { flag: 'wx' });
});
