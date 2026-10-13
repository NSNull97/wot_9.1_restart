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
import { CREW_POLICY_SHA256, TRANSFER_POLICY_SHA256, CROSS_CREW_POLICY_SHA256, ROSTER_CREW_POLICY_SHA256 } from '../src/p04d-crew.mjs';
import { nativeRosterCrewOverview, isNativeRosterCrewOverview } from '../src/p04h-crew.mjs';
import { testDirectory, removeTestDirectory } from './helpers.mjs';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const BUNDLE = resolve(process.env.P04D_TEST_BUNDLE || join(ROOT, 'local/p04d/source-bundle-05'));
const ORIGINAL = process.env.P04D_TEST_ORIGINAL || 'C:\\WoT_0.9.1_RU_0717_original';
const fixture = join(BUNDLE, 'content/fixtures/profile4/profile-input.json.blob');
const skip = !existsSync(fixture) ? 'NOT_RUN: verified portable #717 bundle required' : false;
function db(path, fn, readOnly = false) {
  const value = new DatabaseSync(path, { readOnly }); try { return fn(value); } finally { value.close(); }
}

for (const predecessor of ['F7', 'D6']) test(`P04H real bridge recruits all roles, retains transfers/quota and ${predecessor} historical replay across restart`, { skip }, async t => {
  const directory = testDirectory(), original = JSON.parse(readFileSync(fixture, 'utf8'));
  const identityFile = join(directory, 'identity.sqlite'), gameFile = join(directory, 'game.sqlite');
  const secret = token(), password = token(), email = 'p04h-isolated@example.test', passwordHash = await hashPassword(password);
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
    command_key: 'p04h-seed:309', expected_revision: predecessor === 'F7' ? 7 : 6, wire_revision: 1, layout: [3, 1, 1, 0] };
  const oldRecruitResponse = (await call('/internal/native/crew', command)).body;
  assert.equal(oldRecruitResponse.status, 'recruited');
  if (predecessor === 'D6') {
    await bridge.close(); options.crew_transfer = { version: 1, policy_sha256: TRANSFER_POLICY_SHA256 };
    bridge = await createIdentityBridge(options);
    assert.equal(profile().profile_version, 7); assert.equal(profile().snapshot_revision, 8);
  }
  const oldRequest = { ...command, command_key: 'p04h-seed:105', expected_revision: 8, wire_revision: 2, layout: [1, 1, -1] };
  const oldResponse = (await call('/internal/native/crew-transfer', oldRequest)).body;
  assert.equal(oldResponse.status, 'transferred');
  await bridge.close(); options.crew_cross_vehicle = { version: 1, policy_sha256: CROSS_CREW_POLICY_SHA256 };
  bridge = await createIdentityBridge(options);
  assert.equal(profile().profile_version, 8); assert.equal(profile().snapshot_revision, 10);
  assert.equal((await call('/internal/native/login', { email, password })).status, 200);

  const gRequest = { ...command, command_key: 'p04h-seed:g105', expected_revision: 10, wire_revision: 1, layout: [2, 0, 1] };
  const gResponse = (await call('/internal/native/crew-transfer', gRequest)).body;
  assert.equal(gResponse.status, 'transferred');
  await bridge.close(); options.crew_roster_recruitment = { version: 1, policy_sha256: ROSTER_CREW_POLICY_SHA256 };
  bridge = await createIdentityBridge(options);
  assert.equal(profile().profile_version, 9); assert.equal(profile().snapshot_revision, 12);
  const before = profile(), beforeLedger = ledger();
  assert.equal(before.crew.length, 3); assert.equal(before.crew_service.free_recruitment_left, 13);
  let revision = before.snapshot_revision, wire = 1, savedRequest, savedResponse;
  const hires = [[3,1,0,0],[3,1,1,0],[3,2,0,0],[3,2,1,0],[3,2,2,0],[3,2,3,0],[3,2,4,0]];
  const operations = [...hires.map(layout => ['crew', layout]),
    ...[[2,4,-1],[2,3,10],[2,4,9]].map(layout => ['crew-transfer', layout])];
  for (const [i, [operation, layout]] of operations.entries()) {
    const request = { ...command, command_key: `p04h-test:${i}`, expected_revision: revision, wire_revision: wire, layout };
    if (i === 0) {
      assert.equal((await call('/internal/native/crew', request, token())).status, 403);
      for (const invalid of [[3,1,2,0],[3,2,5,0],[3,2,-1,0],[3,3,0,0],[3,2,1,1],[3,2,1,2],[4,2,1,0]]) {
        assert.equal((await call('/internal/native/crew', { ...request, layout: invalid })).body.status, 'rejected');
        assert.deepEqual(profile(), before); assert.equal(ledger(), beforeLedger);
      }
    }
    const value = await call(`/internal/native/${operation}`, request);
    assert.equal(value.status, 200); assert.equal(value.body.status, operation === 'crew' ? 'recruited' : 'transferred');
    assert.equal(value.body.revision, ++revision); assert.equal(value.body.wire_revision, ++wire);
    assert.ok(value.body.update_hex.length <= 480);
    assert.deepEqual((await call(`/internal/native/${operation}`, request)).body, { ...value.body, replayed: true });
    for (const field of ['resources', 'ammunition', 'ammunition_depot']) assert.deepEqual(profile()[field], before[field]);
    assert.equal(profile().crew_service.free_recruitment_left, 13 - Math.min(7, i + 1));
    if (i === 3) { savedRequest = request; savedResponse = value.body; }
  }
  const complete = profile();
  assert.deepEqual(complete.inventory.map(v => v.crew_assigned), [true, true]);
  assert.equal(complete.crew.length, 10); assert.equal(complete.crew_service.free_recruitment_left, 6);
  assert.deepEqual(complete.crew.map(m => m.role_level), [100,100,100,50,50,50,50,50,50,50]);
  assert.deepEqual(complete.crew.slice(0,3).map(m => m.vehicle_inventory_id), [null,null,null]);
  assert.deepEqual(complete.crew.slice(3).map(m => m.role), ['commander','driver','commander','gunner','driver','loader','loader']);
  assert.equal(ledger(), beforeLedger + 10);
  const overview = await createGameReader({ origin: `http://127.0.0.1:${bridge.port}`, tokenFile })(original.account_id);
  assert.equal(overview.state, 'ready'); assert.deepEqual(overview.inventory.map(v => v.crewAssigned), [true,true]);
  assert.equal(overview.crewService.version, 4); assert.equal(overview.crewService.assigned, 7);
  assert.equal(overview.crewService.barracks, 3); assert.equal(isNativeRosterCrewOverview(overview, original.account_id), true);
  assert.deepEqual(nativeRosterCrewOverview(complete), overview);
  for (const change of [p => { p.crew[8].role = 'gunner'; }, p => { p.crew[9].crew_id = p.crew[8].crew_id; },
    p => { p.inventory[0].crew_assigned = false; }, p => { p.inventory[1].crew_assigned = false; },
    p => { p.crew[0].role_level = 50; }, p => { p.crew[3].role_level = 100; }, p => { p.crew_service.free_recruitment_left = 7; },
    p => { p.crew_service.policy_sha256 = CROSS_CREW_POLICY_SHA256; },
    p => { p.crew[9].vehicle_inventory_id = original.inventory[0].inventory_id; },
    p => { p.crew[2].vehicle_inventory_id = original.inventory[1].inventory_id; }]) {
    const bad = structuredClone(complete); change(bad); assert.throws(() => nativeRosterCrewOverview(bad));
  }
  for (const change of [v => { v.crewService.is7Assigned = 6; }, v => { v.crewService.tankmen = 9; },
    v => { v.crewService.battle = true; }, v => { v.inventory[1].crewAssigned = false; }]) {
    const bad = structuredClone(overview); change(bad); assert.equal(isNativeRosterCrewOverview(bad, original.account_id), false);
  }
  for (let i = 0; i < 6; i++) {
    const request = { ...command, command_key: `p04h-capacity:${i}`, expected_revision: revision, wire_revision: wire, layout: [3,2,4,0] };
    const value = await call('/internal/native/crew', request);
    assert.equal(value.body.status, 'recruited'); assert.equal(value.body.revision, ++revision); assert.equal(value.body.wire_revision, ++wire);
  }
  const full = profile(); assert.equal(full.crew.length, 16); assert.equal(full.crew_service.free_recruitment_left, 0);
  const exhausted = { ...command, command_key: 'p04h-exhausted', expected_revision: revision, wire_revision: wire, layout: [3,1,0,0] };
  assert.equal((await call('/internal/native/crew', exhausted)).body.status, 'rejected');
  assert.deepEqual(profile(), full); assert.equal(ledger(), beforeLedger + 16);
  for (const [request, response, operation] of [[command, oldRecruitResponse, 'crew'], [oldRequest, oldResponse, 'crew-transfer'],
    [gRequest, gResponse, 'crew-transfer'], [savedRequest, savedResponse, 'crew']]) {
    assert.deepEqual((await call(`/internal/native/${operation}`, request)).body, { ...response, replayed: true });
    assert.deepEqual(profile(), full); assert.equal(ledger(), beforeLedger + 16);
  }
  for (const invalid of [{ ...command, command_key: 'missing-historical-key' }, { ...command, layout: [3,1,0,0] },
    { ...command, wire_revision: 2 }]) {
    assert.equal((await call('/internal/native/crew', invalid)).status, 503);
    assert.deepEqual(profile(), full); assert.equal(ledger(), beforeLedger + 16);
  }
  await bridge.close(); bridge = await createIdentityBridge(options);
  assert.deepEqual(profile(), full); assert.equal((await call('/internal/native/login', { email, password })).status, 200);
  assert.deepEqual((await call('/internal/native/crew', savedRequest)).body, { ...savedResponse, replayed: true });
  assert.equal((await call('/internal/native/crew', exhausted)).body.status, 'rejected');
  assert.deepEqual(profile(), full); assert.equal(ledger(), beforeLedger + 16);
  for (const bad of [null, true, { version: 1, policy_sha256: CROSS_CREW_POLICY_SHA256 }]) {
    await assert.rejects(() => createIdentityBridge({ ...options, crew_roster_recruitment: bad }));
  }
  const missing = { ...options }; delete missing.crew_cross_vehicle;
  await assert.rejects(() => createIdentityBridge(missing));
});
