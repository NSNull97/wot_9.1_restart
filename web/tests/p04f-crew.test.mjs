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
import { CREW_POLICY_SHA256, TRANSFER_POLICY_SHA256 } from '../src/p04d-crew.mjs';
import { nativeCrewTransferOverview, isNativeCrewTransferOverview } from '../src/p04f-crew.mjs';
import { testDirectory, removeTestDirectory } from './helpers.mjs';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const BUNDLE = resolve(process.env.P04D_TEST_BUNDLE || join(ROOT, 'local/p04d/source-bundle-05'));
const ORIGINAL = process.env.P04D_TEST_ORIGINAL || 'C:\\WoT_0.9.1_RU_0717_original';
const fixture = join(BUNDLE, 'content/fixtures/profile4/profile-input.json.blob');
const skip = !existsSync(fixture) ? 'NOT_RUN: verified portable #717 bundle required' : false;
function db(path, fn, readOnly = false) {
  const value = new DatabaseSync(path, { readOnly }); try { return fn(value); } finally { value.close(); }
}

test('P04F real bridge migrates retained crew, transfers every path, preserves ammo and restores partial crew after restart', { skip }, async t => {
  const directory = testDirectory(), original = JSON.parse(readFileSync(fixture, 'utf8'));
  const identityFile = join(directory, 'identity.sqlite'), gameFile = join(directory, 'game.sqlite');
  const secret = token(), password = token(), email = 'p04f-isolated@example.test', passwordHash = await hashPassword(password);
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
  const profile = () => db(gameFile, d => JSON.parse(d.prepare('SELECT profile_json FROM game_profiles WHERE account_id=?').get(original.account_id).profile_json), true);
  const ledger = () => db(gameFile, d => d.prepare('SELECT COUNT(*) AS n FROM game_command_ledger').get().n, true);
  assert.equal(profile().profile_version, 6);
  await bridge.close(); options.crew_transfer = { version: 1, policy_sha256: TRANSFER_POLICY_SHA256 };
  bridge = await createIdentityBridge(options);
  assert.equal(profile().profile_version, 7); assert.equal(profile().snapshot_revision, 7);
  async function call(path, data, auth = secret) {
    const response = await fetch(`http://127.0.0.1:${bridge.port}${path}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${auth}` }, body: JSON.stringify(data),
    }); return { status: response.status, body: await response.json() };
  }
  const login = await call('/internal/native/login', { email, password }); assert.equal(login.status, 200);
  const command = { account_id: original.account_id, native_database_id: original.native_database_id,
    command_key: 'p04f-test:309', expected_revision: 7, wire_revision: 1, layout: [3, 1, 1, 0] };
  const recruited = await call('/internal/native/crew', command);
  assert.equal(recruited.status, 200); assert.equal(recruited.body.status, 'recruited'); assert.equal(ledger(), 1);
  const before = profile(); assert.equal(before.crew.length, 3);
  let revision = 8, wire = 2; let savedRequest, savedResponse;
  const layouts = [[1, 1, -1], [1, 1, 2], [1, 1, 3], [1, 0, -1], [1, 0, 1], [1, -1, -1], [1, 0, 1]];
  for (const [i, layout] of layouts.entries()) {
    const request = { ...command, command_key: `p04f-test:105:${i}`, expected_revision: revision, wire_revision: wire, layout };
    if (i === 0) {
      assert.equal((await call('/internal/native/crew-transfer', request, token())).status, 403);
      assert.equal((await call('/internal/native/crew-transfer', { ...request, account_id: 'a5326cc1-8524-479c-8bba-72e973489c22' })).status, 403);
      assert.equal((await call('/internal/native/crew-transfer', { ...request, layout: [1, 0, 2] })).body.status, 'rejected');
      assert.deepEqual(profile(), before); assert.equal(ledger(), 1);
    }
    const value = await call('/internal/native/crew-transfer', request);
    assert.equal(value.status, 200); assert.equal(value.body.status, 'transferred');
    assert.equal(value.body.revision, ++revision); assert.equal(value.body.wire_revision, ++wire);
    assert.deepEqual((await call('/internal/native/crew-transfer', request)).body, { ...value.body, replayed: true });
    const current = profile();
    assert.deepEqual(current.resources, before.resources); assert.deepEqual(current.ammunition, before.ammunition);
    assert.deepEqual(current.ammunition_depot, before.ammunition_depot);
    assert.deepEqual(current.crew.map(({ vehicle_inventory_id, ...rest }) => rest), before.crew.map(({ vehicle_inventory_id, ...rest }) => rest));
    assert.equal(current.crew_service.free_recruitment_left, 0);
    assert.equal(ledger(), i + 2);
    if (i === 0) { savedRequest = request; savedResponse = value.body; }
  }
  assert.equal(profile().inventory[0].crew_assigned, false);
  assert.deepEqual(profile().crew.map(m => m.vehicle_inventory_id), [original.inventory[0].inventory_id, null, null]);
  const previous = profile();
  const overview = await createGameReader({ origin: `http://127.0.0.1:${bridge.port}`, tokenFile })(original.account_id);
  assert.equal(overview.state, 'ready'); assert.equal(overview.inventory[0].crewAssigned, false);
  assert.equal(overview.crewService.assigned, 1); assert.equal(overview.crewService.barracks, 2);
  assert.equal(isNativeCrewTransferOverview(overview, original.account_id), true);
  assert.deepEqual(nativeCrewTransferOverview(previous), overview);
  for (const change of [p => { p.crew[1].role = 'commander'; }, p => { p.crew[1].crew_id = p.crew[0].crew_id; },
    p => { p.inventory[0].crew_assigned = true; }, p => { p.crew_service.policy_sha256 = '0'.repeat(64); },
    p => { p.crew[1].vehicle_inventory_id = p.crew[2].vehicle_inventory_id = original.inventory[0].inventory_id; }]) {
    const bad = structuredClone(previous); change(bad); assert.throws(() => nativeCrewTransferOverview(bad));
  }
  const badOverview = structuredClone(overview); badOverview.crewService.assigned = 2;
  assert.equal(isNativeCrewTransferOverview(badOverview, original.account_id), false);
  const noop = { ...savedRequest, command_key: 'noop', expected_revision: revision, wire_revision: wire };
  assert.equal((await call('/internal/native/crew-transfer', noop)).body.status, 'rejected');
  assert.deepEqual(profile(), previous); assert.equal(ledger(), 8);
  await bridge.close(); bridge = await createIdentityBridge(options);
  assert.deepEqual(profile(), previous);
  assert.equal((await call('/internal/native/login', { email, password })).status, 200);
  assert.deepEqual((await call('/internal/native/crew-transfer', savedRequest)).body, { ...savedResponse, replayed: true });
  assert.deepEqual(profile(), previous); assert.equal(ledger(), 8);
});
