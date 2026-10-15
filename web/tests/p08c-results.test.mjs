/** Actual loopback HTTP -> same Python battle writer -> isolated SQLite. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { createHash, randomUUID } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync, copyFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createIdentityBridge } from '../src/game-adapter.mjs';
import { hashPassword, token } from '../src/security.mjs';
import { CREW_POLICY_SHA256, TRANSFER_POLICY_SHA256, CROSS_CREW_POLICY_SHA256, ROSTER_CREW_POLICY_SHA256,
  PROGRESSION_CREW_POLICY_SHA256, DISMISSAL_CREW_POLICY_SHA256 } from '../src/p04d-crew.mjs';
import { BARRACKS_CREW_POLICY_SHA256 } from '../src/p04k-crew.mjs';
import { RESEARCH_POLICY_SHA256 } from '../src/p09e-research.mjs';
import { BATTLE_POLICY_SHA256 } from '../src/p08b-battle.mjs';
import { testDirectory, removeTestDirectory } from './helpers.mjs';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const BUNDLE = resolve(process.env.P04D_TEST_BUNDLE || join(ROOT, 'local/stands/p09e-main-01/source-bundle-05'));
const ORIGINAL = process.env.P04D_TEST_ORIGINAL || 'C:\\WoT_0.9.1_RU_0717_original';
const source = join(BUNDLE, 'content/fixtures/profile4/profile-input.json.blob');
function db(path, callback) { const d = new DatabaseSync(path); try { return callback(d); } finally { d.close(); } }

test('P08C actual HTTP owner result survives reauth/reopen, ack and duplicate store; unsafe arena remains exact',
  { skip: !existsSync(source) ? 'NOT_RUN: verified source bundle unavailable' : false, timeout: 120000 }, async t => {
  const directory = testDirectory(), seeded = join(directory, 'seed'); let bridge = null;
  t.after(async () => { if (bridge) await bridge.close(); removeTestDirectory(directory); });
  const original = JSON.parse(readFileSync(source, 'utf8'));
  const seed = spawnSync('python', ['-B', '-X', 'utf8', join(ROOT, 'tools/p09e_research_harness.py'),
    '--bundle', BUNDLE, '--original', ORIGINAL, '--out', seeded, '--seed-only'],
  { cwd: ROOT, encoding: 'utf8', windowsHide: true, timeout: 120000 });
  assert.equal(seed.status, 0, seed.stderr);
  const gameFile = join(seeded, 'game.sqlite'), identityFile = join(directory, 'identity.sqlite');
  const secret = token(), password = token(), email = 'p08c-isolated@example.test', passwordHash = await hashPassword(password);
  const nativePath = join(directory, 'native.json'), tokenFile = join(directory, 'identity.token');
  copyFileSync(join(BUNDLE, 'content/inputs/native-ms1.blob'), nativePath); writeFileSync(tokenFile, secret);
  db(identityFile, d => {
    d.exec('PRAGMA user_version=2; CREATE TABLE users(id TEXT PRIMARY KEY,username TEXT,display_nickname TEXT,email TEXT,password_hash TEXT,created_at INTEGER)');
    d.prepare('INSERT INTO users VALUES (?,?,?,?,?,?)').run(original.account_id, original.username.toLowerCase(), original.username,
      email, passwordHash, original.created_at_ms);
  });
  db(gameFile, d => d.prepare('INSERT INTO game_meta VALUES (?,?)').run('native_descriptors_sha256', createHash('sha256').update(readFileSync(nativePath)).digest('hex')));
  const python = spawnSync('python', ['-B', '-c', 'import sys;print(sys.executable)'], { encoding: 'utf8', windowsHide: true }).stdout.trim();
  const options = { version: 1, port: 0, web_database: identityFile, game_database: gameFile,
    fixture_root: join(directory, 'fixtures'), native_descriptors: nativePath, python_executable: python, token_file: tokenFile,
    ammunition_service: { version: 1, bundle_root: BUNDLE, original_root: ORIGINAL, account_id: original.account_id,
      grant: { grant_id: 'p09d-test-depot-v1', quantity_each: 100 } },
    crew_service: { version: 1, policy_sha256: CREW_POLICY_SHA256 }, crew_transfer: { version: 1, policy_sha256: TRANSFER_POLICY_SHA256 },
    crew_cross_vehicle: { version: 1, policy_sha256: CROSS_CREW_POLICY_SHA256 }, crew_roster_recruitment: { version: 1, policy_sha256: ROSTER_CREW_POLICY_SHA256 },
    crew_progression: { version: 1, policy_sha256: PROGRESSION_CREW_POLICY_SHA256 }, crew_dismissal: { version: 1, policy_sha256: DISMISSAL_CREW_POLICY_SHA256 },
    crew_barracks_recruitment: { version: 1, policy_sha256: BARRACKS_CREW_POLICY_SHA256 }, research_service: { version: 1, policy_sha256: RESEARCH_POLICY_SHA256 },
    battle_service: { version: 1, policy_sha256: BATTLE_POLICY_SHA256, accounts: [original.account_id] } };
  bridge = await createIdentityBridge(options);
  const profile = () => db(gameFile, d => JSON.parse(d.prepare('SELECT profile_json FROM game_profiles WHERE account_id=?').get(original.account_id).profile_json));
  async function call(path, value, auth = secret, headers = {}) {
    const response = await fetch(`http://127.0.0.1:${bridge.port}${path}`, { method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${auth}`, ...headers }, body: JSON.stringify(value) });
    return { status: response.status, body: await response.json() };
  }
  const login = () => call('/internal/native/login', { email, password });
  assert.equal((await login()).status, 200);
  const run = randomUUID(), arena = '9007199254740993'; let serial = 0;
  const battle = (operation, extra = {}) => ({ version: 1, operation, account_id: original.account_id, native_database_id: original.native_database_id,
    command_key: `p08c-battle:${++serial}`, expected_revision: profile().snapshot_revision, run_id: run,
    ...(['admit', 'finish'].includes(operation) ? { battle_id: `${run}:${arena}`, native_inventory_id: 1 } : {}), ...extra });
  const resultRequest = (operation, extra = {}) => ({ version: 1, operation, account_id: original.account_id,
    native_database_id: original.native_database_id, command_key: `p08c-result:${++serial}`, arena_id: arena, ...extra });
  const results = value => call('/internal/native/battle-results', value);
  assert.equal((await call('/internal/native/battle', battle('run_open'))).body.status, 'ready');
  const admitted = await call('/internal/native/battle', battle('admit')); assert.equal(admitted.body.status, 'admitted');
  const participant = { vehicle_id: 152043523, account_dbid: original.native_database_id, name: 'Owner', team: 1, type_compact_descr: 3329,
    health: 23, shots: 3, direct_hits: 1, piercings: 1, damage_dealt: 7, damage_received: 67, kills: 0, capture_points: 42,
    dropped_capture_points: 3, mileage_metres: 100, life_time: 90, killer_id: 0, death_reason: -1, premature_leave: false };
  const result = { arena_id: 'REPLACE_ARENA_INTEGER', arena_type_id: 4, created_unix: 1792080000, winner_team: 1,
    finish_reason: 1, duration_seconds: 120, participants: [participant, { ...participant, vehicle_id: 152043524,
      account_dbid: participant.account_dbid + 1, name: 'Synthetic peer', team: 2 }] };
  // JSON exact integer is carried as an opaque string across Node, never a Number.
  const raw = JSON.stringify(result).replace('"REPLACE_ARENA_INTEGER"', arena);
  const store = resultRequest('store', { run_id: run, battle_id: `${run}:${arena}`, native_inventory_id: 1,
    reservation_id: admitted.body.reservation.reservation_id, results_json: raw });
  assert.equal((await results(store)).body.code, 'RESULT_NOT_READY');
  const finished = await call('/internal/native/battle', battle('finish', { reservation_id: admitted.body.reservation.reservation_id,
    remaining_ap: 17, terminal_hp: 23, reason: 'battle_finished', results_json: raw }));
  assert.equal(finished.status, 200); assert.equal(finished.body.status, 'finished');
  const atomic = await results(resultRequest('query'));
  assert.equal(atomic.body.status, 'found', 'The finish COMMIT already includes the complete results journal');
  assert.ok(atomic.body.results_json.includes(`"arena_id":${arena}`));
  const before = JSON.stringify(profile());
  const stored = await results(store); assert.equal(stored.status, 200); assert.equal(stored.body.status, 'stored');
  assert.equal(stored.body.arena_id, arena); assert.ok(stored.body.results_json.includes(`"arena_id":${arena}`));
  assert.equal((await results(store)).body.replayed, true);
  const badResult = { ...result, participants: [{ ...participant, health: 24 }, result.participants[1]] };
  const badRaw = JSON.stringify(badResult).replace('"REPLACE_ARENA_INTEGER"', arena);
  assert.equal((await results({ ...store, command_key: 'p08c-result:changed', results_json: badRaw })).body.code, 'RESULT_MISMATCH');
  const query = resultRequest('query');
  assert.equal((await call('/internal/native/battle-results', query, token())).status, 403);
  assert.equal((await results({ ...query, account_id: randomUUID() })).status, 403);
  assert.equal((await results({ ...query, native_database_id: participant.account_dbid + 1 })).status, 403);
  assert.equal((await results({ ...query, arena_id: Number(arena) })).status, 400);
  assert.equal((await call('/internal/native/battle-results', query, secret, { Origin: 'https://foreign.example' })).status, 403);
  assert.equal((await results({ ...store, results_json: 'x'.repeat(32769) })).status, 400);
  await bridge.close(); bridge = await createIdentityBridge(options); assert.equal((await login()).status, 200);
  const found = await results(query); assert.equal(found.status, 200); assert.equal(found.body.status, 'found');
  assert.equal(found.body.results_json, stored.body.results_json); assert.equal(found.body.acked, false);
  const ack = resultRequest('ack'); assert.equal((await results(ack)).body.acked, true);
  assert.equal((await results(ack)).body.replayed, true); assert.equal((await results(query)).body.acked, true);
  assert.equal(JSON.stringify(profile()), before);
  assert.equal(db(gameFile, d => d.prepare('SELECT COUNT(*) AS n FROM p08c_result').get().n), 1);
});
