/** Isolated persistence checks. Unit adapters are not native compatibility. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { createServer } from 'node:net';
import { createHash, randomUUID } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync, mkdirSync, copyFileSync, unlinkSync, readdirSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { planMs1Ammo, applyMs1Ammo, rollbackMs1Ammo, validateAmmoProfile,
  validateAmmoFixture, ammoOverview, isAmmoOverview } from '../src/ms1-ammo.mjs';
import * as crew from '../src/ms1-crew.mjs';
import { grantTestVehicle, rollbackTestVehicle } from '../src/test-garage.mjs';
import { createIdentityBridge, createGameReader } from '../src/game-adapter.mjs';
import { hashPassword, token } from '../src/security.mjs';
import { testDirectory, removeTestDirectory, freePort } from './helpers.mjs';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const MS1 = resolve(ROOT, 'local/evidence/20261004-p02-hangar/native-descriptors.json');
const IS7 = resolve(ROOT, 'local/evidence/20261004-p02-hangar-ui/ui06-catalog2-manual-runtime/original-vehicle-is7.json');
const CREW_EXPORT = resolve(ROOT, 'local/evidence/20261005-p02-ms1-crew/native-ms1-crew-export01.json');
const OLD_BRIDGE = resolve(ROOT, 'local/evidence/20261005-p02-ms1-ammo/data/design-01/bridge-before.mjs');
const EXPORT = process.env.MS1_AMMO_TEST_EXPORT ? resolve(ROOT, process.env.MS1_AMMO_TEST_EXPORT) : null;
const SHA = bytes => createHash('sha256').update(bytes).digest('hex');
const save = (path, value) => writeFileSync(path, JSON.stringify(value, null, 2) + '\n');
const readJSON = path => JSON.parse(readFileSync(path, 'utf8'));
const needBase = [MS1, IS7, CREW_EXPORT].some(path => !existsSync(path))
  ? 'NOT_RUN: actual previous native MS-1/IS-7/crew exports required' : false;
const needExport = needBase || (!EXPORT || !existsSync(EXPORT)
  ? 'NOT_RUN: MS1_AMMO_TEST_EXPORT must name an actual trace-bound native export' : false);
function withDb(path, callback, readOnly = false) {
  const db = new DatabaseSync(path, { readOnly }); try { return callback(db); } finally { db.close(); }
}
function profiles(path) { return withDb(path, db => db.prepare('SELECT * FROM game_profiles ORDER BY native_id').all().map(row => ({ ...row })), true); }
function hashes(directory) { return readdirSync(directory).sort().map(file => [file, SHA(readFileSync(join(directory, file)))]); }
function ownProfile3(id = randomUUID()) {
  return { profile_version: 3, account_id: id, username: 'Танкист_Ёж', native_database_id: 1,
    created_at_ms: 1791110000000, snapshot_revision: 3, resources: { credits: 123456, gold: 7, free_xp: 8 },
    statistics: { battles: 0, wins: 0, losses: 0, draws: 0 },
    inventory: [['starter-vehicle-v1', 'vehicle:ms1', 90], ['test-is7-v1', 'vehicle:is7', 2150]].map(([suffix, definition, health], i) => ({
      inventory_id: `${id}:${suffix}`, vehicle_definition_id: definition, health, vehicle_xp: 0,
      crew_assigned: i === 0, ammunition_count: 0 })),
    test_grant: { grant_id: 'test-is7-v1', granted_at_ms: 1791110012345, base_profile_sha256: 'a'.repeat(64) },
    crew: ['commander', 'driver'].map(role => ({ crew_id: `${id}:ms1-${role}-v1`,
      vehicle_inventory_id: `${id}:starter-vehicle-v1`, role, role_level: 100, skills: [] })),
    crew_grant: { grant_id: 'test-ms1-crew-v1', granted_at_ms: 1791140000000,
      base_profile_sha256: 'b'.repeat(64), native_export_sha256: 'c'.repeat(64) } };
}
function ownProfile4(base = ownProfile3()) {
  const value = structuredClone(base);
  value.profile_version = 4; value.snapshot_revision = 4; value.inventory[0].ammunition_count = 20;
  value.ammunition = [{ vehicle_inventory_id: `${base.account_id}:starter-vehicle-v1`,
    shell_definition_id: 'shell:ms1-stock-ap', count: 20 }];
  value.ammo_grant = { grant_id: 'test-ms1-ammo-v1', granted_at_ms: 1791170000000,
    base_profile_sha256: SHA(JSON.stringify(base)), native_export_sha256: 'd'.repeat(64) };
  return value;
}

test('profile4 exact domain grant preserves both vehicles, trained crew and balances', () => {
  const base = ownProfile3(), p = ownProfile4(base), raw = Buffer.from(JSON.stringify(base));
  assert.equal(validateAmmoProfile(p, raw), p);
  assert.deepEqual(p.resources, base.resources); assert.deepEqual(p.crew, base.crew);
  assert.deepEqual(p.inventory[1], base.inventory[1]); assert.deepEqual(p.crew_grant, base.crew_grant);
  assert.deepEqual(p.test_grant, base.test_grant);
  assert.deepEqual(p.ammunition, [{ vehicle_inventory_id: base.inventory[0].inventory_id,
    shell_definition_id: 'shell:ms1-stock-ap', count: 20 }]);
  assert.ok(!Object.keys(p.ammunition[0]).some(key => /native|database/i.test(key)));
});

test('profile4 rejects false integer, wrong ammunition, unknown keys and foreign progress', () => {
  const base = ownProfile3(), good = ownProfile4(base), raw = Buffer.from(JSON.stringify(base));
  const changes = [p => { p.profile_version = true; }, p => { p.snapshot_revision = 3; }, p => { p.extra = 1; },
    p => { p.resources.gold++; }, p => { p.statistics.battles = 1; }, p => { p.native_database_id = 2; },
    p => { p.created_at_ms++; }, p => { p.username = 'other_nickname'; }, p => { p.crew[0].role_level = 99; },
    p => { p.crew_grant.granted_at_ms++; }, p => { p.inventory[0].crew_assigned = false; },
    p => { p.inventory[1].ammunition_count = 20; }, p => { p.ammunition[0].shell_definition_id = 'shell:foreign'; },
    p => { p.ammunition[0].vehicle_inventory_id = p.inventory[1].inventory_id; },
    p => { p.ammunition.push(structuredClone(p.ammunition[0])); }, p => { p.ammunition[0].native_id = 2570; },
    p => { p.ammo_grant.base_profile_sha256 = '0'.repeat(64); }, p => { p.ammo_grant.native_export_sha256 = 'no'; },
    p => { p.ammo_grant.granted_at_ms = p.crew_grant.granted_at_ms - 1; }];
  for (const count of [true, -1, 0, 19, 96, 97, Infinity, NaN]) changes.push(p => {
    p.ammunition[0].count = count; p.inventory[0].ammunition_count = count;
  });
  for (const mutate of changes) { const p = structuredClone(good); mutate(p); assert.throws(() => validateAmmoProfile(p, raw)); }
  assert.throws(() => validateAmmoProfile(good, Buffer.from(JSON.stringify(base, null, 2))), /previous profile3/);
});

test('ammo overview exposes actual20 count with all gameplay capabilities still unavailable', () => {
  const p = ownProfile4(), value = ammoOverview(p);
  assert.equal(isAmmoOverview(value, p.account_id), true);
  assert.equal(value.snapshotRevision, 4);
  assert.deepEqual(value.inventory.map(item => item.ammunition), [20, 0]);
  assert.deepEqual(value.inventory.map(item => item.crewAssigned), [true, false]);
  assert.deepEqual(value.capabilities, { battle: false, purchases: false, sales: false });
  assert.equal(isAmmoOverview(value, randomUUID()), false);
  for (const change of [v => { v.inventory[0].ammunition = 96; }, v => { v.inventory[1].ammunition = 20; },
    v => { v.capabilities.battle = true; }, v => { v.inventory[0].crewAssigned = false; },
    v => { v.inventory[0].shells = []; }, v => { v.snapshotRevision = 3; }]) {
    const v = structuredClone(value); change(v); assert.equal(isAmmoOverview(v, p.account_id), false);
  }
});

/** Explicit unit boundary: relocate a byte-checked authored module, redirect
 * only its bridge dependency to a private copy. ROOT/import changes merely
 * retain its existing dependencies after relocation. This is not execution
 * of the production historical journal, and no production source is written. */
async function isolatedCrewBridge(directory) {
  const source = resolve(ROOT, 'web/src/ms1-crew.mjs'), original = readFileSync(source);
  assert.equal(SHA(original), '7800c5f845c731e22c28cd45ab044484b4f5c4b27156c213400570e88f0d3772');
  const bridge = join(directory, 'isolated-bridge-copy.mjs');
  const oldBridge = readFileSync(OLD_BRIDGE);
  assert.equal(SHA(oldBridge), 'b3cef4e5f26c11400a4bc6de8804c53228a39021bef482a38bfeb44fc97a4271');
  writeFileSync(bridge, oldBridge);
  let text = original.toString('utf8');
  const rewrites = [["const ROOT = fileURLToPath(new URL('../../', import.meta.url));", `const ROOT = ${JSON.stringify(ROOT)};`],
    ["'./store.mjs'", JSON.stringify(pathToFileURL(resolve(ROOT, 'web/src/store.mjs')).href)],
    ["'./test-garage.mjs'", JSON.stringify(pathToFileURL(resolve(ROOT, 'web/src/test-garage.mjs')).href)],
    ["['bridge', resolve(ROOT, 'web/src/game-adapter.mjs')]", `['bridge', ${JSON.stringify(bridge)}]`]];
  for (const [before, after] of rewrites) {
    assert.equal(text.split(before).length, 2, 'exact single relocation/dependency edit'); text = text.replace(before, after);
  }
  const path = join(directory, 'relocated-ms1-crew.mjs'); writeFileSync(path, text);
  const module = await import(pathToFileURL(path).href);
  return { module, bridge, oldBytes: readFileSync(bridge), source, sourceSha: SHA(original), adapterPath: path };
}

async function context(t, adapter = false) {
  const directory = testDirectory(); t.after(() => removeTestDirectory(directory));
  const runtime = join(directory, 'server'), portal = join(directory, 'identity'); mkdirSync(runtime); mkdirSync(portal);
  const identityFile = join(portal, 'portal.sqlite'), gameFile = join(runtime, 'game.sqlite');
  const id = randomUUID(), otherId = randomUUID(), stamp = 1791110000000;
  const base = ownProfile3(id); delete base.inventory; delete base.test_grant; delete base.crew; delete base.crew_grant;
  base.profile_version = 1; base.snapshot_revision = 1;
  const other = { ...base, account_id: otherId, username: 'second_tester', native_database_id: 2,
    resources: { credits: 99, gold: 0, free_xp: 0 } };
  withDb(identityFile, db => {
    db.exec(`CREATE TABLE users(id TEXT PRIMARY KEY,username TEXT,display_nickname TEXT,created_at INTEGER,email TEXT,password_hash TEXT);
      PRAGMA user_version=2;`);
    for (const p of [base, other]) db.prepare('INSERT INTO users VALUES (?,?,?,?,?,?)')
      .run(p.account_id, p.username.toLowerCase(), p.username, stamp, `${p.native_database_id}@example.test`, 'UNIT_TEST_NO_CREDENTIAL');
  });
  const ms1 = join(runtime, 'native-descriptors.json'); copyFileSync(MS1, ms1);
  withDb(gameFile, db => {
    db.exec(`PRAGMA journal_mode=WAL;
      CREATE TABLE game_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
      CREATE TABLE game_profiles(native_id INTEGER PRIMARY KEY AUTOINCREMENT CHECK(native_id BETWEEN 1 AND 2147483647),account_id TEXT NOT NULL UNIQUE,profile_json TEXT NOT NULL);
      CREATE TABLE game_limits(key_hash TEXT PRIMARY KEY,hits INTEGER NOT NULL,resets_at INTEGER NOT NULL);PRAGMA user_version=1;`);
    db.prepare('INSERT INTO game_meta VALUES (?,?)').run('native_descriptors_sha256', SHA(readFileSync(ms1)));
    for (const p of [base, other]) db.prepare('INSERT INTO game_profiles(native_id,account_id,profile_json) VALUES (?,?,?)')
      .run(p.native_database_id, p.account_id, JSON.stringify(p));
    db.prepare('INSERT INTO game_limits VALUES (?,?,?)').run('own-counter', 3, stamp);
  });
  const pythonProbe = spawnSync('python', ['-B', '-c', 'import sys;print(sys.executable)'], { encoding: 'utf8', windowsHide: true, timeout: 5000 });
  assert.equal(pythonProbe.status, 0); const python = pythonProbe.stdout.trim();
  const ports = []; while (ports.length < 3) { const port = await freePort(); if (!ports.includes(port)) ports.push(port); }
  const service = join(runtime, 'service.json'), bridgeFile = join(runtime, 'bridge.json'), gatewayFile = join(runtime, 'gateway.json');
  const fixtureRoot = join(runtime, 'fixtures'); mkdirSync(fixtureRoot);
  const bridge = { version: 1, port: ports[0], web_database: identityFile, game_database: gameFile, fixture_root: fixtureRoot,
    native_descriptors: ms1, token_file: join(runtime, 'identity.token'), python_executable: python,
    test_garage: { version: 1, native_is7: IS7, sha256: SHA(readFileSync(IS7)) } };
  save(bridgeFile, bridge);
  save(gatewayFile, { login_bind: `127.0.0.1:${ports[1]}`, base_bind: `127.0.0.1:${ports[2]}`,
    identity_endpoint: `127.0.0.1:${ports[0]}`, identity_token_file: bridge.token_file, local_root: resolve(ROOT, 'local') });
  save(service, { version: 2, web_mode: 'external', runtime_dir: runtime, portal_data: portal, web_port: 3091,
    node_executable: process.execPath, python_executable: python, gateway_executable: process.execPath });
  save(join(runtime, 'state.json'), { status: 'STOPPED', processes: [] });
  const initial = profiles(gameFile);
  for (const p of [base, other]) {
    const parent = join(fixtureRoot, p.account_id), destination = join(parent, 'r1-catalog2');
    mkdirSync(destination, { recursive: true });
    const input = join(destination, 'profile-input.json'); save(input, p);
    const generated = spawnSync(python, ['-B', '-X', 'utf8', resolve(ROOT, 'tools/hangar_state.py'),
      '--profile', input, '--native-descriptors', ms1, '--catalog-version', '2', '--out', destination],
    { encoding: 'utf8', windowsHide: true, timeout: 10000 });
    assert.equal(generated.status, 0, generated.stderr);
  }
  const oldGrant = await grantTestVehicle({ service, accountId: id, nativeIs7: IS7,
    grantedAtMs: 1791128141411, expectedProfileSha256: SHA(profiles(gameFile)[0].profile_json), journal: join(directory, 'is7-journal') });
  const isolated = adapter ? await isolatedCrewBridge(directory) : null, crewModule = isolated?.module || crew;
  const crewPlan = await crewModule.planMs1Crew({ service, accountId: id, nativeCrew: CREW_EXPORT,
    grantedAtMs: 1791147988422, expectedProfileSha256: SHA(profiles(gameFile)[0].profile_json), journal: join(directory, 'crew-journal') });
  const crewRequest = { service, journal: crewPlan.journal, expectedJournalSha256: crewPlan.journal_sha256 };
  await crewModule.applyMs1Crew(crewRequest);
  const nativeAmmo = EXPORT || join(directory, 'NOT_NATIVE.json');
  if (!EXPORT) save(nativeAmmo, { purpose: 'unit early refusal only, never native evidence' });
  const options = { service, accountId: id, nativeAmmo, grantedAtMs: 1791170000000,
    expectedProfileSha256: SHA(profiles(gameFile)[0].profile_json), journal: join(directory, 'ammo-journal') };
  return { directory, runtime, identityFile, gameFile, id, otherId, base, other, python, ports, service,
    bridgeFile, gatewayFile, bridge, previous: crewPlan.fixture_directory, initial, ms1,
    options, oldGrant, crewPlan, crewRequest, crewModule, isolated };
}

test('ammo lease refuses running process, existing owner lock and occupied endpoint without mutations', { skip: needBase }, async t => {
  const c = await context(t), before = profiles(c.gameFile);
  save(join(c.runtime, 'state.json'), { status: 'RUNNING', processes: [] });
  await assert.rejects(planMs1Ammo(c.options), /must be stopped/);
  save(join(c.runtime, 'state.json'), { status: 'STOPPED', processes: [{ pid: 1 }] });
  await assert.rejects(planMs1Ammo(c.options), /exit is unconfirmed/);
  save(join(c.runtime, 'state.json'), { status: 'STOPPED', processes: [] });
  writeFileSync(join(c.runtime, 'supervisor.lock'), 'OTHER_OWNER');
  await assert.rejects(planMs1Ammo(c.options), /EEXIST/); unlinkSync(join(c.runtime, 'supervisor.lock'));
  const listener = createServer(); await new Promise(done => listener.listen(c.ports[0], '127.0.0.1', done));
  try { await assert.rejects(planMs1Ammo(c.options), /occupied|EADDRINUSE/); }
  finally { await new Promise(done => listener.close(done)); }
  assert.deepEqual(profiles(c.gameFile), before); assert.ok(!existsSync(c.options.journal));
});

test('ammo refuses foreign UUID, stale bytes and changed native identity before creating a journal', { skip: needBase }, async t => {
  const c = await context(t), before = profiles(c.gameFile);
  await assert.rejects(planMs1Ammo({ ...c.options, accountId: randomUUID() }), /Existing bounded game profile/);
  await assert.rejects(planMs1Ammo({ ...c.options, expectedProfileSha256: '0'.repeat(64) }), /Expected target/);
  withDb(c.identityFile, db => db.prepare('UPDATE users SET display_nickname=? WHERE id=?').run('other_nickname', c.id));
  await assert.rejects(planMs1Ammo(c.options), /identity differs/);
  assert.deepEqual(profiles(c.gameFile), before); assert.ok(!existsSync(c.options.journal));
});

test('actual-export plan/apply/idempotence and exact4→3→2→1 rollback with an isolated bridge dependency', { skip: needExport }, async t => {
  const c = await context(t, true), before = profiles(c.gameFile), identityHash = SHA(readFileSync(c.identityFile));
  const previousHashes = hashes(c.previous), planned = await planMs1Ammo(c.options);
  const configs = [c.service, c.bridgeFile, c.gatewayFile].map(path => [path, SHA(readFileSync(path))]);
  assert.equal(planned.status, 'PLANNED'); assert.equal(planned.native_compatibility, 'NOT_RUN');
  assert.deepEqual(profiles(c.gameFile), before); assert.ok(!existsSync(planned.fixture_directory));
  assert.equal((await planMs1Ammo(c.options)).status, 'ALREADY_PLANNED');
  assert.deepEqual(profiles(join(c.options.journal, 'game-before.sqlite')), before);
  const request = { service: c.service, journal: planned.journal, expectedJournalSha256: planned.journal_sha256 };
  await assert.rejects(applyMs1Ammo({ ...request, expectedJournalSha256: '0'.repeat(64) }), /Unexpected journal hash/);
  const granted = await applyMs1Ammo(request), after = profiles(c.gameFile);
  assert.equal(granted.status, 'GRANTED');
  validateAmmoFixture(granted.fixture_directory, JSON.parse(after[0].profile_json), { nativeMs1: c.ms1, nativeIs7: IS7, baseFixture: c.previous });
  assert.deepEqual(after[1], before[1]); assert.deepEqual(hashes(c.previous), previousHashes);
  assert.deepEqual(configs.map(([path]) => [path, SHA(readFileSync(path))]), configs);
  assert.equal(SHA(readFileSync(c.identityFile)), identityHash);
  for (const name of ['shop.bin', 'dossier.bin']) assert.deepEqual(readFileSync(join(c.previous, name)), readFileSync(join(granted.fixture_directory, name)));
  assert.equal((await applyMs1Ammo(request)).status, 'ALREADY_GRANTED');
  unlinkSync(join(c.options.journal, 'committed.json'));
  assert.equal((await applyMs1Ammo(request)).status, 'ALREADY_GRANTED', 'recover COMMIT without receipt');
  // Simulate only the old dependency changing, in its isolated byte copy.
  const currentBridge = readFileSync(resolve(ROOT, 'web/src/game-adapter.mjs'));
  assert.notEqual(SHA(currentBridge), SHA(c.isolated.oldBytes), 'root must integrate profile4 before the full rollback integration test');
  writeFileSync(c.isolated.bridge, currentBridge);
  assert.equal((await rollbackMs1Ammo(request)).status, 'ROLLED_BACK');
  assert.deepEqual(profiles(c.gameFile), before);
  await assert.rejects(c.crewModule.rollbackMs1Crew(c.crewRequest), /implementation changed/);
  assert.deepEqual(profiles(c.gameFile), before, 'stale crew journal must not mutate profile3');
  writeFileSync(c.isolated.bridge, c.isolated.oldBytes);
  assert.equal((await rollbackMs1Ammo(request)).status, 'ALREADY_ROLLED_BACK');
  unlinkSync(join(c.options.journal, 'rolled-back.json'));
  assert.equal((await rollbackMs1Ammo(request)).status, 'ALREADY_ROLLED_BACK', 'recover rollback COMMIT without receipt');
  await assert.rejects(applyMs1Ammo(request), /already rolled back/);
  assert.equal((await c.crewModule.rollbackMs1Crew(c.crewRequest)).status, 'ROLLED_BACK');
  assert.equal(JSON.parse(profiles(c.gameFile)[0].profile_json).profile_version, 2);
  assert.equal((await rollbackTestVehicle({ service: c.service, journal: c.oldGrant.journal,
    expectedJournalSha256: c.oldGrant.journal_sha256 })).status, 'ROLLED_BACK');
  assert.deepEqual(profiles(c.gameFile), c.initial, 'exact original profile1 and second account bytes restored');
  assert.equal(SHA(readFileSync(c.isolated.source)), c.isolated.sourceSha, 'production old module remains frozen');
});

test('journal tamper and changed target reject; rollback preserves newer unrelated rows', { skip: needExport }, async t => {
  const c = await context(t), planned = await planMs1Ammo(c.options), before = profiles(c.gameFile);
  const request = { service: c.service, journal: planned.journal, expectedJournalSha256: planned.journal_sha256 };
  const file = join(planned.journal, 'game-before.sqlite'), saved = readFileSync(file);
  writeFileSync(file, Buffer.from('damaged-backup'));
  await assert.rejects(applyMs1Ammo(request), /backup integrity/); writeFileSync(file, saved);
  withDb(c.gameFile, db => db.prepare('UPDATE game_limits SET hits=4 WHERE key_hash=?').run('own-counter'));
  await assert.rejects(applyMs1Ammo(request), /Database changed before apply/);
  assert.deepEqual(profiles(c.gameFile), before); assert.ok(!existsSync(planned.fixture_directory));
  withDb(c.gameFile, db => db.prepare('UPDATE game_limits SET hits=3 WHERE key_hash=?').run('own-counter'));
  await applyMs1Ammo(request);
  const after = profiles(c.gameFile), newer = JSON.parse(after[0].profile_json); newer.resources.credits++;
  withDb(c.gameFile, db => db.prepare('UPDATE game_profiles SET profile_json=? WHERE account_id=?').run(JSON.stringify(newer), c.id));
  await assert.rejects(rollbackMs1Ammo(request), /target changed/);
  withDb(c.gameFile, db => {
    db.prepare('UPDATE game_profiles SET profile_json=? WHERE account_id=?').run(after[0].profile_json, c.id);
    const other = JSON.parse(before[1].profile_json); other.resources.credits = 765432;
    db.prepare('UPDATE game_profiles SET profile_json=? WHERE account_id=?').run(JSON.stringify(other), c.otherId);
    db.prepare('UPDATE game_limits SET hits=9 WHERE key_hash=?').run('own-counter');
  });
  const changedOther = profiles(c.gameFile)[1], fixtureHashes = hashes(planned.fixture_directory);
  await rollbackMs1Ammo(request);
  assert.deepEqual(profiles(c.gameFile)[0], before[0]); assert.deepEqual(profiles(c.gameFile)[1], changedOther);
  assert.equal(withDb(c.gameFile, db => db.prepare('SELECT hits FROM game_limits').get().hits, true), 9);
  assert.deepEqual(hashes(planned.fixture_directory), fixtureHashes);
});

test('profile4 shared bridge reads owned20 count and payload; secondary profile1 stays unchanged', { skip: needExport }, async t => {
  const c = await context(t), planned = await planMs1Ammo(c.options);
  await applyMs1Ammo({ service: c.service, journal: planned.journal, expectedJournalSha256: planned.journal_sha256 });
  const password = 'own-ammo-http-unit-only-123', secret = token(), passwordHash = await hashPassword(password);
  withDb(c.identityFile, db => db.prepare('UPDATE users SET password_hash=? WHERE id=?').run(passwordHash, c.id));
  writeFileSync(c.bridge.token_file, secret);
  const server = await createIdentityBridge({ ...c.bridge, port: 0 });
  try {
    const origin = `http://127.0.0.1:${server.port}`, reader = createGameReader({ origin, tokenFile: c.bridge.token_file });
    const own = await reader(c.id), other = await reader(c.otherId);
    assert.equal(own.snapshotRevision, 4); assert.deepEqual(own.inventory.map(v => v.ammunition), [20, 0]);
    assert.equal(other.snapshotRevision, 1); assert.equal(other.inventory[0].ammunition, 0);
    const response = await fetch(origin + '/internal/native/login', { method: 'POST',
      headers: { Authorization: `Bearer ${secret}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: '1@example.test', password }) });
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), { account_id: c.id, native_database_id: 1, name: c.base.username, fixture_dir: planned.fixture_directory });
    const path = join(planned.fixture_directory, 'state.bin'), original = readFileSync(path);
    const manifestPath = join(planned.fixture_directory, 'manifest.json'), manifestRaw = readFileSync(manifestPath);
    // A well-formed integer mutation plus matching metadata hashes must still
    // fail the independent exact two-field delta comparison, not just a hash.
    const credits = Buffer.from('5507637265646974734a40e20100', 'hex');
    const offset = original.indexOf(credits);
    assert.ok(offset >= 0); assert.equal(original.indexOf(credits, offset + 1), -1);
    const changed = Buffer.from(original); changed[offset + credits.length - 4]++;
    const manifest = JSON.parse(manifestRaw); manifest.files.find(row => row.file === 'state.bin').sha256 = SHA(changed);
    writeFileSync(path, changed); save(manifestPath, manifest);
    assert.equal((await reader(c.id)).state, 'unavailable', 'self-consistent foreign state mutation refused');
    writeFileSync(path, original); writeFileSync(manifestPath, manifestRaw);
    assert.equal((await reader(c.id)).state, 'ready');
  } finally { await server.close(); }
});
