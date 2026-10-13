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
import { CREW_POLICY_SHA256, TRANSFER_POLICY_SHA256, CROSS_CREW_POLICY_SHA256, ROSTER_CREW_POLICY_SHA256, PROGRESSION_CREW_POLICY_SHA256 } from '../src/p04d-crew.mjs';
import { nativeProgressionCrewOverview, isNativeProgressionCrewOverview } from '../src/p04i-crew.mjs';
import { testDirectory, removeTestDirectory } from './helpers.mjs';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const BUNDLE = resolve(process.env.P04D_TEST_BUNDLE || join(ROOT, 'local/p04d/source-bundle-05'));
const ORIGINAL = process.env.P04D_TEST_ORIGINAL || 'C:\\WoT_0.9.1_RU_0717_original';
const fixture = join(BUNDLE, 'content/fixtures/profile4/profile-input.json.blob');
const skip = !existsSync(fixture) ? 'NOT_RUN: verified portable #717 bundle required' : false;
function db(path, fn, readOnly = false) {
  const value = new DatabaseSync(path, { readOnly }); try { return fn(value); } finally { value.close(); }
}

for (const predecessor of ['F7', 'D6']) test(`P04I real bridge learns skills, retains old command receipts and ${predecessor} historical replay across restart`, { skip }, async t => {
  const directory = testDirectory(), original = JSON.parse(readFileSync(fixture, 'utf8'));
  const identityFile = join(directory, 'identity.sqlite'), gameFile = join(directory, 'game.sqlite');
  const secret = token(), password = token(), email = 'p04i-isolated@example.test', passwordHash = await hashPassword(password);
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
  const hRequest = { ...command, command_key: 'p04i-seed:h309', expected_revision: 12, wire_revision: 1, layout: [3,1,0,0] };
  const hResponse = (await call('/internal/native/crew', hRequest)).body;
  assert.equal(hResponse.status, 'recruited');
  const hProfile = profile();
  assert.equal((await call('/internal/native/crew-learn', { ...command, layout: [1,16,0] })).status, 404);
  await bridge.close(); options.crew_progression = { version: 1, policy_sha256: PROGRESSION_CREW_POLICY_SHA256 };
  bridge = await createIdentityBridge(options);
  assert.equal(profile().profile_version, 10); assert.equal(profile().snapshot_revision, 14);
  assert.deepEqual(profile().crew, hProfile.crew);
  const before = profile(), beforeLedger = ledger();
  let revision = before.snapshot_revision, wire = 1;
  const make = (key, layout) => ({ ...command, command_key: `p04i:${key}`, expected_revision: revision, wire_revision: wire, layout });
  const saved = [];
  for (const [i, layout] of [[1,16,0],[2,29,0],[3,6,0]].entries()) {
    const request = make(`learn:${i}`, layout);
    if (i === 0) {
      assert.equal((await call('/internal/native/crew-learn', request, token())).status, 403);
      for (const invalid of [[4,6,0],[1,18,0],[1,41,0],[1,53,0],[1,37,0],[17,6,0],[1,16,1]]) {
        const response = await call('/internal/native/crew-learn', { ...request, layout: invalid });
        assert.equal(response.status, 200); assert.equal(response.body.status, 'rejected');
        assert.deepEqual(profile(), before); assert.equal(ledger(), beforeLedger);
      }
      for (const invalid of [{ ...request, layout: [1,16] }, { ...request, layout: [true,16,0] },
        { ...request, account_id: '00000000-0000-4000-8000-000000000001' }, { ...request, xp: 100000 }]) {
        assert.notEqual((await call('/internal/native/crew-learn', invalid)).status, 200);
        assert.deepEqual(profile(), before); assert.equal(ledger(), beforeLedger);
      }
    }
    const result = (await call('/internal/native/crew-learn', request)).body;
    assert.equal(result.status, 'learned'); assert.equal(result.revision, ++revision); assert.equal(result.wire_revision, ++wire);
    assert.ok(result.update_hex.length > 0 && result.update_hex.length <= 480);
    assert.deepEqual((await call('/internal/native/crew-learn', request)).body, { ...result, replayed: true });
    saved.push([request, result, 'crew-learn']);
  }
  assert.deepEqual(profile().crew.slice(0,3).map(m => m.skills), [
    [{ skill_id: 'commander_tutor', level: 0 }], [{ skill_id: 'driver_smoothDriving', level: 0 }], [{ skill_id: 'repair', level: 0 }]]);
  const learned = profile();
  for (const layout of [[1,16,0],[1,6,0],[2,30,0],[3,8,0]]) {
    assert.equal((await call('/internal/native/crew-learn', make('reject-next', layout))).body.status, 'rejected');
    assert.deepEqual(profile(), learned); assert.equal(ledger(), beforeLedger + 3);
  }
  for (const [op, layout, status] of [['crew-transfer',[1,0,1],'transferred'], ['crew',[3,2,4,0],'recruited']]) {
    const request = make(op, layout), response = (await call(`/internal/native/${op}`, request)).body;
    assert.equal(response.status, status); assert.equal(response.revision, ++revision); assert.equal(response.wire_revision, ++wire);
    saved.push([request, response, op]);
  }
  const complete = profile(), count = ledger();
  for (const field of ['resources','ammunition','ammunition_depot']) assert.deepEqual(complete[field], before[field]);
  assert.deepEqual(complete.crew.slice(0,3).map(m => m.skills), learned.crew.slice(0,3).map(m => m.skills));
  assert.equal(complete.crew_service.free_recruitment_left, before.crew_service.free_recruitment_left - 1);
  const overview = await createGameReader({ origin: `http://127.0.0.1:${bridge.port}`, tokenFile })(original.account_id);
  assert.equal(overview.state, 'ready'); assert.equal(overview.crewService.version, 5);
  assert.deepEqual(nativeProgressionCrewOverview(complete), overview);
  assert.equal(isNativeProgressionCrewOverview(overview, original.account_id), true);
  for (const change of [p => { p.crew[0].skills[0].skill_id = 'commander_sixthSense'; },
    p => { p.crew[0].skills.push(p.crew[0].skills[0]); }, p => { p.crew[0].skills[0].level = 101; },
    p => { p.crew[3].skills = [{ skill_id: 'repair', level: 0 }]; }, p => { p.crew_service.policy_sha256 = ROSTER_CREW_POLICY_SHA256; }]) {
    const bad = structuredClone(complete); change(bad); assert.throws(() => nativeProgressionCrewOverview(bad));
  }
  for (const [request,response,op] of [[command,oldRecruitResponse,'crew'],[oldRequest,oldResponse,'crew-transfer'],
    [gRequest,gResponse,'crew-transfer'],[hRequest,hResponse,'crew'],...saved]) {
    assert.deepEqual((await call(`/internal/native/${op}`, request)).body, { ...response, replayed: true });
    assert.deepEqual(profile(), complete); assert.equal(ledger(), count);
  }
  await bridge.close(); bridge = await createIdentityBridge(options);
  assert.deepEqual(profile(), complete); assert.equal((await call('/internal/native/login', { email,password })).status, 200);
  for (const [request,response,op] of saved) {
    assert.deepEqual((await call(`/internal/native/${op}`, request)).body, { ...response, replayed: true });
  }
  assert.deepEqual(profile(), complete); assert.equal(ledger(), count);
  for (const bad of [null,true,{version:1,policy_sha256:ROSTER_CREW_POLICY_SHA256}]) {
    await assert.rejects(() => createIdentityBridge({ ...options, crew_progression: bad }));
  }
  const missing = { ...options }; delete missing.crew_roster_recruitment;
  await assert.rejects(() => createIdentityBridge(missing));
});
