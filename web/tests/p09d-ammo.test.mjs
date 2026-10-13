/** Real loopback bridge + Python worker + one SQLite database; no native claim. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync, mkdirSync, copyFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createIdentityBridge, createGameReader } from '../src/game-adapter.mjs';
import { hashPassword, token } from '../src/security.mjs';
import { nativeAmmoOverview, isNativeAmmoOverview } from '../src/p09d-ammo.mjs';
import { testDirectory, removeTestDirectory } from './helpers.mjs';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const BUNDLE = resolve(process.env.P09D_TEST_BUNDLE || join(ROOT, 'local/p09d/source-bundle-05'));
const ORIGINAL = process.env.P09D_TEST_ORIGINAL || 'C:\\WoT_0.9.1_RU_0717_original';
const SHA = bytes => createHash('sha256').update(bytes).digest('hex');
const fixture = name => join(BUNDLE, 'content', 'fixtures', 'profile4', name + '.blob');
const needSource = !existsSync(fixture('profile-input.json')) ? 'NOT_RUN: real portable #717 bundle required' : false;
function withDb(path, callback, readOnly = false) {
  const db = new DatabaseSync(path, { readOnly }); try { return callback(db); } finally { db.close(); }
}

test('P09D authenticated loopback service persists both loads, replays, rejects and restarts against one DB', { skip: needSource }, async t => {
  const directory = testDirectory();
  const original = JSON.parse(readFileSync(fixture('profile-input.json'), 'utf8'));
  const identityFile = join(directory, 'identity.sqlite'), gameFile = join(directory, 'game.sqlite');
  const secret = token(), password = token(), email = 'p09d-isolated@example.test';
  const passwordHash = await hashPassword(password);
  const nativePath = join(directory, 'native.json'); copyFileSync(join(BUNDLE, 'content/inputs/native-ms1.blob'), nativePath);
  const tokenFile = join(directory, 'identity.token'); writeFileSync(tokenFile, secret);
  withDb(identityFile, db => {
    db.exec('PRAGMA user_version=2; CREATE TABLE users(id TEXT PRIMARY KEY,username TEXT,display_nickname TEXT,email TEXT,password_hash TEXT,created_at INTEGER)');
    db.prepare('INSERT INTO users VALUES (?,?,?,?,?,?)').run(original.account_id, original.username.toLowerCase(), original.username,
      email, passwordHash, original.created_at_ms);
  });
  withDb(gameFile, db => {
    db.exec(`PRAGMA user_version=1; CREATE TABLE game_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
      CREATE TABLE game_profiles(native_id INTEGER PRIMARY KEY AUTOINCREMENT,account_id TEXT NOT NULL UNIQUE,profile_json TEXT NOT NULL);
      CREATE TABLE game_limits(key_hash TEXT PRIMARY KEY,hits INTEGER NOT NULL,resets_at INTEGER NOT NULL);`);
    db.prepare('INSERT INTO game_meta VALUES (?,?)').run('native_descriptors_sha256', SHA(readFileSync(nativePath)));
    db.prepare('INSERT INTO game_profiles VALUES (?,?,?)').run(original.native_database_id, original.account_id, JSON.stringify(original));
  });
  const probe = spawnSync('python', ['-B', '-c', 'import sys;print(sys.executable)'], { encoding: 'utf8', windowsHide: true, timeout: 5000 });
  assert.equal(probe.status, 0);
  const options = { version: 1, port: 0, web_database: identityFile, game_database: gameFile,
    fixture_root: join(directory, 'fixtures'), native_descriptors: nativePath, python_executable: probe.stdout.trim(), token_file: tokenFile,
    ammunition_service: { version: 1, bundle_root: BUNDLE, original_root: ORIGINAL, account_id: original.account_id,
      grant: { grant_id: 'p09d-test-depot-v1', quantity_each: 100 } } };
  let bridge = await createIdentityBridge(options);
  t.after(async () => { await bridge.close(); removeTestDirectory(directory); });
  async function call(path, data, auth = secret) {
    const response = await fetch(`http://127.0.0.1:${bridge.port}${path}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${auth}` }, body: JSON.stringify(data),
    });
    return { status: response.status, body: await response.json() };
  }
  const login = await call('/internal/native/login', { email, password });
  assert.equal(login.status, 200); assert.equal(login.body.account_id, original.account_id);
  assert.match(login.body.fixture_dir, /p09d-r5$/);
  const profile = () => withDb(gameFile, db => JSON.parse(db.prepare('SELECT profile_json FROM game_profiles WHERE account_id=?').get(original.account_id).profile_json), true);
  const ledger = () => withDb(gameFile, db => db.prepare('SELECT COUNT(*) AS count FROM game_command_ledger').get().count, true);
  const command = { account_id: original.account_id, native_database_id: original.native_database_id, command_key: 'session-one:cmd-225',
    expected_revision: 5, wire_revision: 1, layout: [3, 1, 6, 2570, 30, -2826, 10, 3082, 5, 6, 0, 0, 0, 0, 0, 0] };
  assert.equal((await call('/internal/native/ammo', command, token())).status, 403);
  const first = await call('/internal/native/ammo', command);
  assert.equal(first.status, 200); assert.equal(first.body.status, 'serviced'); assert.equal(first.body.revision, 6);
  assert.equal(first.body.wire_revision, 2); assert.equal(first.body.result_code, 0);
  assert.ok(first.body.update_hex.length < 481);
  assert.equal(profile().inventory[0].ammunition_count, 45); assert.equal(ledger(), 1);
  const replay = await call('/internal/native/ammo', command);
  assert.deepEqual(replay.body, { ...first.body, replayed: true }); assert.equal(ledger(), 1);
  const before = profile();
  const stale = await call('/internal/native/ammo', { ...command, command_key: 'other' });
  assert.equal(stale.body.status, 'rejected'); assert.equal(stale.body.result_code, -10); assert.deepEqual(profile(), before);
  const second = { ...command, command_key: 'session-one:cmd-226', expected_revision: 6, wire_revision: 2,
    layout: [3, 2, 6, 15114, 5, 14602, 15, -14858, 10, 6, 0, 0, 0, 0, 0, 0] };
  assert.equal((await call('/internal/native/ammo', second)).body.status, 'serviced');
  assert.deepEqual(profile().inventory.map(item => item.ammunition_count), [45, 30]);
  const overview = await createGameReader({ origin: `http://127.0.0.1:${bridge.port}`, tokenFile })(original.account_id);
  assert.equal(overview.state, 'ready'); assert.equal(overview.snapshotRevision, 7);
  assert.equal(isNativeAmmoOverview(overview, original.account_id), true);
  const wrong = structuredClone(overview); wrong.inventory[1].ammunition = 31;
  assert.equal(isNativeAmmoOverview(wrong, original.account_id), false);
  const profileBeforeRestart = profile();
  await bridge.close(); bridge = await createIdentityBridge(options);
  assert.deepEqual(profile(), profileBeforeRestart);
  const relogin = await call('/internal/native/login', { email, password });
  assert.equal(relogin.status, 200); assert.match(relogin.body.fixture_dir, /p09d-r7$/);
  assert.deepEqual((await call('/internal/native/ammo', command)).body, { ...first.body, replayed: true });
  assert.equal(ledger(), 2);
});
