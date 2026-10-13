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
import { CREW_POLICY_SHA256, TRANSFER_POLICY_SHA256, CROSS_CREW_POLICY_SHA256 } from '../src/p04d-crew.mjs';
import { nativeCrossVehicleCrewOverview, isNativeCrossVehicleCrewOverview } from '../src/p04g-crew.mjs';
import { testDirectory, removeTestDirectory } from './helpers.mjs';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const BUNDLE = resolve(process.env.P04D_TEST_BUNDLE || join(ROOT, 'local/p04d/source-bundle-05'));
const ORIGINAL = process.env.P04D_TEST_ORIGINAL || 'C:\\WoT_0.9.1_RU_0717_original';
const fixture = join(BUNDLE, 'content/fixtures/profile4/profile-input.json.blob');
const skip = !existsSync(fixture) ? 'NOT_RUN: verified portable #717 bundle required' : false;
function db(path, fn, readOnly = false) {
  const value = new DatabaseSync(path, { readOnly }); try { return fn(value); } finally { value.close(); }
}

for (const predecessor of ['F7', 'D6']) test(`P04G real bridge preserves two-vehicle moves, partial crews and ${predecessor} historical replay across restart`, { skip }, async t => {
  const directory = testDirectory(), original = JSON.parse(readFileSync(fixture, 'utf8'));
  const identityFile = join(directory, 'identity.sqlite'), gameFile = join(directory, 'game.sqlite');
  const secret = token(), password = token(), email = 'p04g-isolated@example.test', passwordHash = await hashPassword(password);
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
  if (predecessor === 'F7') {
    await bridge.close(); options.crew_transfer = { version: 1, policy_sha256: TRANSFER_POLICY_SHA256 };
    bridge = await createIdentityBridge(options);
    assert.equal(profile().profile_version, 7); assert.equal(profile().snapshot_revision, 7);
  }
  async function call(path, data, auth = secret) {
    const response = await fetch(`http://127.0.0.1:${bridge.port}${path}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${auth}` }, body: JSON.stringify(data),
    }); return { status: response.status, body: await response.json() };
  }
  const command = { account_id: original.account_id, native_database_id: original.native_database_id,
    command_key: 'p04g-seed:309', expected_revision: predecessor === 'F7' ? 7 : 6, wire_revision: 1, layout: [3, 1, 1, 0] };
  const oldRecruitResponse = (await call('/internal/native/crew', command)).body;
  assert.equal(oldRecruitResponse.status, 'recruited');
  if (predecessor === 'D6') {
    await bridge.close(); options.crew_transfer = { version: 1, policy_sha256: TRANSFER_POLICY_SHA256 };
    bridge = await createIdentityBridge(options);
    assert.equal(profile().profile_version, 7); assert.equal(profile().snapshot_revision, 8);
  }
  const oldRequest = { ...command, command_key: 'p04g-seed:105', expected_revision: 8, wire_revision: 2, layout: [1, 1, -1] };
  const oldResponse = (await call('/internal/native/crew-transfer', oldRequest)).body;
  assert.equal(oldResponse.status, 'transferred');
  await bridge.close(); options.crew_cross_vehicle = { version: 1, policy_sha256: CROSS_CREW_POLICY_SHA256 };
  bridge = await createIdentityBridge(options);
  assert.equal(profile().profile_version, 8); assert.equal(profile().snapshot_revision, 10);
  assert.equal((await call('/internal/native/login', { email, password })).status, 200);
  const before = profile(), beforeLedger = ledger();
  assert.deepEqual(await call('/internal/native/crew', command), { status: 200, body: { ...oldRecruitResponse, replayed: true } });
  assert.deepEqual(profile(), before); assert.equal(ledger(), beforeLedger);
  for (const invalid of [{ ...command, command_key: 'missing-historical-key' },
    { ...command, layout: [3, 1, 0, 0] }, { ...command, wire_revision: 2 }]) {
    assert.deepEqual(await call('/internal/native/crew', invalid), { status: 503, body: { error: 'unavailable' } });
    assert.deepEqual(profile(), before); assert.equal(ledger(), beforeLedger);
  }
  let revision = 10, wire = 1, savedRequest, savedResponse;
  const layouts = [[1,0,-1],[2,0,1],[1,1,3],[1,1,-1],[2,2,3],[2,2,2],[2,0,-1],
    [1,0,1],[2,2,-1],[1,1,2],[2,2,3],[2,-1,-1],[1,0,-1],[2,0,1]];
  for (const [i, layout] of layouts.entries()) {
    const request = { ...command, command_key: `p04g-test:105:${i}`, expected_revision: revision, wire_revision: wire, layout };
    if (i === 0) {
      assert.equal((await call('/internal/native/crew-transfer', request, token())).status, 403);
      for (const invalid of [[2,1,1],[2,2,1],[2,0,2],[3,0,1],[2,5,1],[2,-1,1]]) {
        assert.equal((await call('/internal/native/crew-transfer', { ...request, layout: invalid })).body.status, 'rejected');
        assert.deepEqual(profile(), before); assert.equal(ledger(), beforeLedger);
      }
    }
    const value = await call('/internal/native/crew-transfer', request);
    assert.equal(value.status, 200); assert.equal(value.body.status, 'transferred');
    assert.equal(value.body.revision, ++revision); assert.equal(value.body.wire_revision, ++wire);
    assert.deepEqual((await call('/internal/native/crew-transfer', request)).body, { ...value.body, replayed: true });
    const current = profile();
    for (const field of ['resources', 'ammunition', 'ammunition_depot']) assert.deepEqual(current[field], before[field]);
    assert.deepEqual(current.crew.map(({ vehicle_inventory_id, ...rest }) => rest),
      before.crew.map(({ vehicle_inventory_id, ...rest }) => rest));
    assert.equal(current.crew_service.free_recruitment_left, 0); assert.equal(ledger(), beforeLedger + i + 1);
    if (i === 1) { savedRequest = request; savedResponse = value.body; }
  }
  const previous = profile();
  assert.deepEqual(previous.crew.map(m => m.vehicle_inventory_id), [original.inventory[1].inventory_id, original.inventory[0].inventory_id, null]);
  assert.deepEqual(previous.inventory.map(v => v.crew_assigned), [false, false]);
  const overview = await createGameReader({ origin: `http://127.0.0.1:${bridge.port}`, tokenFile })(original.account_id);
  assert.equal(overview.state, 'ready'); assert.deepEqual(overview.inventory.map(v => v.crewAssigned), [false, false]);
  assert.equal(overview.crewService.ms1Assigned, 1); assert.equal(overview.crewService.is7Assigned, 1);
  assert.equal(overview.crewService.barracks, 1); assert.equal(isNativeCrossVehicleCrewOverview(overview, original.account_id), true);
  assert.deepEqual(nativeCrossVehicleCrewOverview(previous), overview);
  for (const change of [p => { p.crew[1].role = 'commander'; }, p => { p.crew[1].crew_id = p.crew[0].crew_id; },
    p => { p.inventory[0].crew_assigned = true; }, p => { p.inventory[1].crew_assigned = true; },
    p => { p.crew[0].role_level = 50; }, p => { p.crew_service.free_recruitment_left = 1; },
    p => { p.crew_service.policy_sha256 = TRANSFER_POLICY_SHA256; },
    p => { p.crew[1].vehicle_inventory_id = p.crew[2].vehicle_inventory_id = original.inventory[1].inventory_id; }]) {
    const bad = structuredClone(previous); change(bad); assert.throws(() => nativeCrossVehicleCrewOverview(bad));
  }
  const badOverview = structuredClone(overview); badOverview.crewService.is7Assigned = 2;
  assert.equal(isNativeCrossVehicleCrewOverview(badOverview, original.account_id), false);
  const noop = { ...savedRequest, command_key: 'noop', expected_revision: revision, wire_revision: wire };
  assert.equal((await call('/internal/native/crew-transfer', noop)).body.status, 'rejected');
  assert.deepEqual(profile(), previous); assert.equal(ledger(), beforeLedger + 14);
  await bridge.close(); bridge = await createIdentityBridge(options);
  assert.deepEqual(profile(), previous); assert.equal((await call('/internal/native/login', { email, password })).status, 200);
  assert.deepEqual((await call('/internal/native/crew-transfer', savedRequest)).body, { ...savedResponse, replayed: true });
  assert.deepEqual((await call('/internal/native/crew-transfer', oldRequest)).body, { ...oldResponse, replayed: true });
  assert.deepEqual(await call('/internal/native/crew', command), { status: 200, body: { ...oldRecruitResponse, replayed: true } });
  assert.deepEqual(profile(), previous); assert.equal(ledger(), beforeLedger + 14);
  assert.deepEqual(profile(), previous); assert.equal(ledger(), beforeLedger + 14);
});
