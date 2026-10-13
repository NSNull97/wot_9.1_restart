/** Real loopback bridge, bounded Python workers and SQLite; native is separate. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync, copyFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createIdentityBridge, createGameReader } from '../src/game-adapter.mjs';
import { hashPassword, token } from '../src/security.mjs';
import { nativeCrewOverview, isNativeCrewOverview, CREW_POLICY_SHA256 } from '../src/p04d-crew.mjs';
import { testDirectory, removeTestDirectory } from './helpers.mjs';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const BUNDLE = resolve(process.env.P04D_TEST_BUNDLE || join(ROOT, 'local/p04d/source-bundle-05'));
const ORIGINAL = process.env.P04D_TEST_ORIGINAL || 'C:\\WoT_0.9.1_RU_0717_original';
const fixture = join(BUNDLE, 'content/fixtures/profile4/profile-input.json.blob');
const skip = !existsSync(fixture) ? 'NOT_RUN: verified portable #717 bundle required' : false;
function db(path, fn, readOnly = false) {
  const value = new DatabaseSync(path, { readOnly }); try { return fn(value); } finally { value.close(); }
}

test('P04D real bridge replaces driver once, preserves ammo, authenticates, replays and restarts', { skip }, async t => {
  const directory = testDirectory(), original = JSON.parse(readFileSync(fixture, 'utf8'));
  const identityFile = join(directory, 'identity.sqlite'), gameFile = join(directory, 'game.sqlite');
  const secret = token(), password = token(), email = 'p04d-isolated@example.test', passwordHash = await hashPassword(password);
  const nativePath = join(directory, 'native.json'), tokenFile = join(directory, 'identity.token');
  copyFileSync(join(BUNDLE, 'content/inputs/native-ms1.blob'), nativePath); writeFileSync(tokenFile, secret);
  db(identityFile, d => {
    d.exec('PRAGMA user_version=2; CREATE TABLE users(id TEXT PRIMARY KEY,username TEXT,display_nickname TEXT,email TEXT,password_hash TEXT,created_at INTEGER)');
    d.prepare('INSERT INTO users VALUES (?,?,?,?,?,?)').run(original.account_id, original.username.toLowerCase(), original.username,
      email, passwordHash, original.created_at_ms);
  });
  db(gameFile, d => {
    d.exec(`PRAGMA user_version=1; CREATE TABLE game_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
      CREATE TABLE game_profiles(native_id INTEGER PRIMARY KEY AUTOINCREMENT,account_id TEXT NOT NULL UNIQUE,profile_json TEXT NOT NULL);
      CREATE TABLE game_limits(key_hash TEXT PRIMARY KEY,hits INTEGER NOT NULL,resets_at INTEGER NOT NULL);`);
    d.prepare('INSERT INTO game_meta VALUES (?,?)').run('native_descriptors_sha256', createHash('sha256').update(readFileSync(nativePath)).digest('hex'));
    d.prepare('INSERT INTO game_profiles VALUES (?,?,?)').run(original.native_database_id, original.account_id, JSON.stringify(original));
  });
  const probe = spawnSync('python', ['-B', '-c', 'import sys;print(sys.executable)'], { encoding: 'utf8', windowsHide: true, timeout: 5000 });
  assert.equal(probe.status, 0);
  const options = { version: 1, port: 0, web_database: identityFile, game_database: gameFile,
    fixture_root: join(directory, 'fixtures'), native_descriptors: nativePath, python_executable: probe.stdout.trim(), token_file: tokenFile,
    ammunition_service: { version: 1, bundle_root: BUNDLE, original_root: ORIGINAL, account_id: original.account_id,
      grant: { grant_id: 'p09d-test-depot-v1', quantity_each: 100 } },
    crew_service: { version: 1, policy_sha256: CREW_POLICY_SHA256 } };
  let bridge = await createIdentityBridge(options);
  t.after(async () => { await bridge.close(); removeTestDirectory(directory); });
  async function call(path, data, auth = secret) {
    const response = await fetch(`http://127.0.0.1:${bridge.port}${path}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${auth}` }, body: JSON.stringify(data),
    }); return { status: response.status, body: await response.json() };
  }
  const profile = () => db(gameFile, d => JSON.parse(d.prepare('SELECT profile_json FROM game_profiles WHERE account_id=?').get(original.account_id).profile_json), true);
  const ledger = () => db(gameFile, d => d.prepare('SELECT COUNT(*) AS n FROM game_command_ledger').get().n, true);
  const login = await call('/internal/native/login', { email, password });
  assert.equal(login.status, 200); assert.match(login.body.fixture_dir, /p09d-r6$/);
  assert.equal(profile().profile_version, 6); assert.equal(profile().crew.length, 2);
  const command = { account_id: original.account_id, native_database_id: original.native_database_id,
    command_key: 'p04d-test:309', expected_revision: 6, wire_revision: 1, layout: [3, 1, 1, 0] };
  const before = profile();
  assert.equal((await call('/internal/native/crew', command, token())).status, 403);
  assert.equal((await call('/internal/native/crew', { ...command, account_id: 'a5326cc1-8524-479c-8bba-72e973489c22' })).status, 403);
  assert.equal((await call('/internal/native/crew', { ...command, layout: [3, 1, 1, 1] })).body.status, 'rejected');
  assert.deepEqual(profile(), before); assert.equal(ledger(), 0);
  const first = await call('/internal/native/crew', command);
  assert.equal(first.status, 200); assert.equal(first.body.status, 'recruited'); assert.equal(first.body.revision, 7);
  assert.equal(first.body.wire_revision, 2); assert.equal(first.body.result_code, 0);
  assert.deepEqual(profile().ammunition, before.ammunition); assert.deepEqual(profile().ammunition_depot, before.ammunition_depot);
  assert.deepEqual(profile().resources, before.resources);
  assert.equal(profile().crew.length, 3); assert.equal(profile().crew[1].vehicle_inventory_id, null);
  assert.equal(profile().crew[2].vehicle_inventory_id, original.inventory[0].inventory_id);
  assert.equal(profile().crew_service.free_recruitment_left, 0); assert.equal(ledger(), 1);
  assert.deepEqual((await call('/internal/native/crew', command)).body, { ...first.body, replayed: true });
  assert.equal((await call('/internal/native/crew', { ...command, command_key: 'second', expected_revision: 7, wire_revision: 2 })).body.status, 'rejected');
  const crew = profile().crew;
  const ammo = { ...command, command_key: 'ammo-after-crew', expected_revision: 7, wire_revision: 2,
    layout: [3, 1, 6, 2570, 30, -2826, 10, 3082, 5, 6, 0, 0, 0, 0, 0, 0] };
  assert.equal((await call('/internal/native/ammo', ammo)).body.status, 'serviced');
  assert.equal(profile().inventory[0].ammunition_count, 45); assert.deepEqual(profile().crew, crew); assert.equal(ledger(), 2);
  const overview = await createGameReader({ origin: `http://127.0.0.1:${bridge.port}`, tokenFile })(original.account_id);
  assert.equal(overview.state, 'ready'); assert.equal(overview.snapshotRevision, 8);
  assert.equal(isNativeCrewOverview(overview, original.account_id), true); assert.equal(overview.crewService.barracks, 1);
  assert.deepEqual(nativeCrewOverview(profile()), overview);
  for (const bad of [p => { p.crew[2].vehicle_inventory_id = null; }, p => { p.crew[1].crew_id = p.crew[0].crew_id; },
    p => { p.crew_service.free_recruitment_left = 1; }, p => { p.crew_service.policy_sha256 = '0'.repeat(64); }]) {
    const changed = structuredClone(profile()); bad(changed); assert.throws(() => nativeCrewOverview(changed));
  }
  const previous = profile(); await bridge.close(); bridge = await createIdentityBridge(options);
  assert.deepEqual(profile(), previous);
  const relogin = await call('/internal/native/login', { email, password });
  assert.equal(relogin.status, 200); assert.match(relogin.body.fixture_dir, /p09d-r8$/);
  assert.deepEqual((await call('/internal/native/crew', command)).body, { ...first.body, replayed: true }); assert.equal(ledger(), 2);
});
