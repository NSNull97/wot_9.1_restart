import test from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { createServer } from 'node:net';
import { createHash, randomUUID } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync, mkdirSync, copyFileSync, unlinkSync, readdirSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { planMs1Crew, applyMs1Crew, rollbackMs1Crew, validateCrewProfile,
  validateCrewFixture, crewOverview, isCrewOverview } from '../src/ms1-crew.mjs';
import { grantTestVehicle, rollbackTestVehicle } from '../src/test-garage.mjs';
import { createIdentityBridge, createGameReader } from '../src/game-adapter.mjs';
import { hashPassword, token } from '../src/security.mjs';
import { testDirectory, removeTestDirectory, freePort } from './helpers.mjs';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const MS1 = resolve(ROOT, 'local/evidence/20261004-p02-hangar/native-descriptors.json');
const IS7 = resolve(ROOT, 'local/evidence/20261004-p02-hangar-ui/ui06-catalog2-manual-runtime/original-vehicle-is7.json');
const EXPORT = process.env.MS1_CREW_TEST_EXPORT ? resolve(ROOT, process.env.MS1_CREW_TEST_EXPORT) : null;
const SHA = bytes => createHash('sha256').update(bytes).digest('hex');
const save = (path, value) => writeFileSync(path, JSON.stringify(value, null, 2) + '\n');
const readJSON = path => JSON.parse(readFileSync(path, 'utf8'));
const needBase = !existsSync(MS1) || !existsSync(IS7) ? 'NOT_RUN: actual previous native MS-1/IS-7 exports required' : false;
const needExport = needBase || (!EXPORT || !existsSync(EXPORT) ? 'NOT_RUN: MS1_CREW_TEST_EXPORT must name an actual trace-bound native export' : false);
function withDb(path, callback, readOnly = false) {
  const db = new DatabaseSync(path, { readOnly }); try { return callback(db); } finally { db.close(); }
}
function profiles(path) { return withDb(path, db => db.prepare('SELECT * FROM game_profiles ORDER BY native_id').all().map(row => ({ ...row })), true); }
function hashes(directory) { return readdirSync(directory).sort().map(file => [file, SHA(readFileSync(join(directory, file)))]); }
function ownProfile2(id = randomUUID()) {
  return { profile_version: 2, account_id: id, username: 'Танкист_Ёж', native_database_id: 1,
    created_at_ms: 1791110000000, snapshot_revision: 2, resources: { credits: 123456, gold: 7, free_xp: 8 },
    statistics: { battles: 0, wins: 0, losses: 0, draws: 0 },
    inventory: [['starter-vehicle-v1', 'vehicle:ms1', 90], ['test-is7-v1', 'vehicle:is7', 2150]].map(([suffix, definition, health]) => ({
      inventory_id: `${id}:${suffix}`, vehicle_definition_id: definition, health, vehicle_xp: 0,
      crew_assigned: false, ammunition_count: 0 })),
    test_grant: { grant_id: 'test-is7-v1', granted_at_ms: 1791110012345, base_profile_sha256: 'a'.repeat(64) } };
}
function ownProfile3(base = ownProfile2()) {
  const value = structuredClone(base);
  value.profile_version = 3; value.snapshot_revision = 3; value.inventory[0].crew_assigned = true;
  value.crew = ['commander', 'driver'].map(role => ({ crew_id: `${base.account_id}:ms1-${role}-v1`,
    vehicle_inventory_id: `${base.account_id}:starter-vehicle-v1`, role, role_level: 100, skills: [] }));
  value.crew_grant = { grant_id: 'test-ms1-crew-v1', granted_at_ms: 1791130000000,
    base_profile_sha256: SHA(JSON.stringify(base)), native_export_sha256: 'b'.repeat(64) };
  return value;
}

test('exact additive profile3 preserves profile2 identity, resources, IS-7 and grant', () => {
  const base = ownProfile2(), value = ownProfile3(base), bytes = Buffer.from(JSON.stringify(base));
  assert.equal(validateCrewProfile(value, bytes), value);
  assert.deepEqual(value.resources, base.resources); assert.deepEqual(value.inventory[1], base.inventory[1]);
  assert.deepEqual(value.test_grant, base.test_grant);
  assert.equal(value.crew.length, 2);
  assert.ok(value.crew.every(member => !Object.keys(member).some(key => /native|database/i.test(key))));
});

test('profile3 rejects changed existing data, foreign assignment, duplicate role and invented progress', () => {
  const base = ownProfile2(), good = ownProfile3(base), bytes = Buffer.from(JSON.stringify(base));
  for (const mutate of [p => { p.profile_version = 4; }, p => { p.snapshot_revision = 2; }, p => { p.extra = 1; },
    p => { p.resources.credits++; }, p => { p.username = 'other_nickname'; }, p => { p.native_database_id = 2; },
    p => { p.inventory[1].crew_assigned = true; }, p => { p.inventory[0].ammunition_count = 1; },
    p => { p.inventory[0].crew_assigned = false; }, p => { p.test_grant.granted_at_ms++; },
    p => { p.crew[1] = structuredClone(p.crew[0]); }, p => { p.crew.reverse(); },
    p => { p.crew[0].vehicle_inventory_id = p.inventory[1].inventory_id; }, p => { p.crew[0].role_level = 101; },
    p => { p.crew[0].skills.push('repair'); }, p => { p.crew[0].native_inventory_id = 1; },
    p => { p.crew_grant.granted_at_ms = p.test_grant.granted_at_ms - 1; }, p => { p.crew_grant.granted_at_ms = true; },
    p => { p.crew_grant.native_export_sha256 = 'x'.repeat(64); }, p => { p.crew_grant.base_profile_sha256 = '0'.repeat(64); }]) {
    const invalid = structuredClone(good); mutate(invalid);
    assert.throws(() => validateCrewProfile(invalid, bytes));
  }
  assert.throws(() => validateCrewProfile(good, Buffer.from(JSON.stringify(base, null, 2))), /previous profile2/);
});

test('profile3 overview keeps web shape and rejects foreign identities or false availability', () => {
  const p = ownProfile3(), value = crewOverview(p);
  assert.equal(isCrewOverview(value, p.account_id), true);
  assert.deepEqual(value.inventory.map(item => item.crewAssigned), [true, false]);
  assert.deepEqual(value.capabilities, { battle: false, purchases: false, sales: false });
  assert.equal(isCrewOverview(value, randomUUID()), false);
  for (const mutate of [v => { v.inventory[1].crewAssigned = true; }, v => { v.inventory[0].crewAssigned = false; },
    v => { v.capabilities.battle = true; }, v => { v.crew = []; }, v => { v.snapshotRevision = 4; },
    v => { v.inventory[0].inventoryItemId = 'foreign'; }, v => { v.account.nickname = ''; }]) {
    const invalid = structuredClone(value); mutate(invalid); assert.equal(isCrewOverview(invalid, p.account_id), false);
  }
});

async function context(t) {
  const directory = testDirectory(); t.after(() => removeTestDirectory(directory));
  const runtime = join(directory, 'server'), portal = join(directory, 'identity'); mkdirSync(runtime); mkdirSync(portal);
  const identityFile = join(portal, 'portal.sqlite'), gameFile = join(runtime, 'game.sqlite');
  const id = randomUUID(), otherId = randomUUID(), stamp = 1791110000000;
  const base = ownProfile2(id); delete base.inventory; delete base.test_grant;
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
  const pythonProbe = spawnSync('python', ['-c', 'import sys;print(sys.executable)'], { encoding: 'utf8', windowsHide: true, timeout: 5000 });
  assert.equal(pythonProbe.status, 0); const python = pythonProbe.stdout.trim();
  const ports = []; while (ports.length < 3) { const port = await freePort(); if (!ports.includes(port)) ports.push(port); }
  const service = join(runtime, 'service.json'), bridgeFile = join(runtime, 'bridge.json'), gatewayFile = join(runtime, 'gateway.json');
  const fixtureRoot = join(runtime, 'fixtures'); mkdirSync(fixtureRoot);
  const bridge = { version: 1, port: ports[0], web_database: identityFile, game_database: gameFile, fixture_root: fixtureRoot,
    native_descriptors: ms1, python_executable: python, token_file: join(runtime, 'identity.token'),
    test_garage: { version: 1, native_is7: IS7, sha256: SHA(readFileSync(IS7)) } };
  save(service, { version: 2, web_mode: 'external', runtime_dir: runtime, portal_data: portal, web_port: 3091,
    node_executable: process.execPath, python_executable: python, gateway_executable: process.execPath });
  save(bridgeFile, bridge);
  save(gatewayFile, { login_bind: `127.0.0.1:${ports[1]}`, base_bind: `127.0.0.1:${ports[2]}`,
    identity_endpoint: `127.0.0.1:${ports[0]}`, identity_token_file: bridge.token_file, local_root: resolve(ROOT, 'local'), session_duration_seconds: 1800 });
  save(join(runtime, 'state.json'), { status: 'STOPPED', processes: [] });
  const initial = join(fixtureRoot, id, 'r1-catalog2'); mkdirSync(initial, { recursive: true });
  save(join(initial, 'profile-input.json'), base);
  const generated = spawnSync(python, ['-B', '-X', 'utf8', resolve(ROOT, 'tools/hangar_state.py'), '--out', initial,
    '--native-descriptors', ms1, '--profile', join(initial, 'profile-input.json'), '--catalog-version', '2'],
  { encoding: 'utf8', timeout: 10000, windowsHide: true });
  assert.equal(generated.status, 0, generated.stderr);
  const oldGrant = await grantTestVehicle({ service, accountId: id, nativeIs7: IS7, grantedAtMs: stamp + 12345,
    expectedProfileSha256: SHA(JSON.stringify(base)), journal: join(directory, 'old-grant') });
  const previous = oldGrant.fixture_directory;
  // This file enables only early refusal tests while native export is absent;
  // the real generator must reject it and no compatibility PASS is claimed.
  const nativeCrew = EXPORT || join(directory, 'NOT_NATIVE.json');
  if (!EXPORT) save(nativeCrew, { purpose: 'unit-only early validation, never native evidence' });
  const options = { service, accountId: id, nativeCrew, grantedAtMs: 1791130000000,
    expectedProfileSha256: SHA(profiles(gameFile)[0].profile_json), journal: join(directory, 'crew-journal') };
  return { directory, runtime, identityFile, gameFile, id, otherId, base, other, python, ports, service,
    bridgeFile, gatewayFile, bridge, previous, initial, ms1, options, oldGrant };
}

test('crew offline lease rejects running state, unconfirmed exit, existing lock and occupied port', { skip: needBase }, async t => {
  const c = await context(t), before = profiles(c.gameFile);
  save(join(c.runtime, 'state.json'), { status: 'RUNNING', processes: [] });
  await assert.rejects(planMs1Crew(c.options), /must be stopped/);
  save(join(c.runtime, 'state.json'), { status: 'STOPPED', processes: [{ pid: 1 }] });
  await assert.rejects(planMs1Crew(c.options), /exit is unconfirmed/);
  save(join(c.runtime, 'state.json'), { status: 'STOPPED', processes: [] });
  writeFileSync(join(c.runtime, 'supervisor.lock'), 'OTHER_OWNER');
  await assert.rejects(planMs1Crew(c.options), /EEXIST/); unlinkSync(join(c.runtime, 'supervisor.lock'));
  const listener = createServer(); await new Promise(done => listener.listen(c.ports[0], '127.0.0.1', done));
  try { await assert.rejects(planMs1Crew(c.options), /occupied|EADDRINUSE/); }
  finally { await new Promise(done => listener.close(done)); }
  assert.deepEqual(profiles(c.gameFile), before); assert.ok(!existsSync(c.options.journal));
});

test('crew plan refuses foreign identity and stale expected profile before generator or writes', { skip: needBase }, async t => {
  const c = await context(t), before = profiles(c.gameFile);
  await assert.rejects(planMs1Crew({ ...c.options, accountId: randomUUID() }), /Existing bounded game profile/);
  await assert.rejects(planMs1Crew({ ...c.options, expectedProfileSha256: '0'.repeat(64) }), /Expected target/);
  withDb(c.identityFile, db => db.prepare('UPDATE users SET display_nickname=? WHERE id=?').run('different', c.id));
  await assert.rejects(planMs1Crew(c.options), /identity differs/);
  assert.deepEqual(profiles(c.gameFile), before); assert.ok(!existsSync(c.options.journal));
});

test('crew plan/apply/rollback are separate, idempotent and preserve old IS-7 rollback', { skip: needExport }, async t => {
  const c = await context(t), before = profiles(c.gameFile), identityHash = SHA(readFileSync(c.identityFile));
  const configs = [c.service, c.bridgeFile, c.gatewayFile].map(file => [file, SHA(readFileSync(file))]);
  const previousHashes = hashes(c.previous), planned = await planMs1Crew(c.options);
  assert.equal(planned.status, 'PLANNED'); assert.equal(planned.native_compatibility, 'NOT_RUN');
  assert.deepEqual(profiles(c.gameFile), before); assert.ok(!existsSync(planned.fixture_directory));
  assert.equal((await planMs1Crew(c.options)).status, 'ALREADY_PLANNED');
  assert.deepEqual(profiles(join(c.options.journal, 'game-before.sqlite')), before);
  assert.deepEqual(withDb(join(c.options.journal, 'identity-before.sqlite'), db => db.prepare('SELECT * FROM users ORDER BY id').all(), true),
    withDb(c.identityFile, db => db.prepare('SELECT * FROM users ORDER BY id').all(), true));
  const request = { service: c.service, journal: planned.journal, expectedJournalSha256: planned.journal_sha256 };
  await assert.rejects(applyMs1Crew({ ...request, expectedJournalSha256: '0'.repeat(64) }), /Unexpected journal hash/);
  const applied = await applyMs1Crew(request); assert.equal(applied.status, 'GRANTED');
  const after = profiles(c.gameFile), profile = JSON.parse(after[0].profile_json);
  validateCrewProfile(profile, readFileSync(join(c.previous, 'profile-input.json')));
  assert.deepEqual(after[1], before[1]); assert.deepEqual(hashes(c.previous), previousHashes);
  assert.deepEqual(configs.map(([file]) => [file, SHA(readFileSync(file))]), configs);
  assert.equal(SHA(readFileSync(c.identityFile)), identityHash);
  validateCrewFixture(applied.fixture_directory, profile, { nativeMs1: c.ms1, nativeIs7: IS7, baseFixture: c.previous });
  const fixtureHashes = hashes(applied.fixture_directory);
  for (const name of ['shop.bin', 'dossier.bin']) assert.deepEqual(readFileSync(join(c.previous, name)), readFileSync(join(applied.fixture_directory, name)));
  assert.equal((await applyMs1Crew(request)).status, 'ALREADY_GRANTED');
  unlinkSync(join(c.options.journal, 'committed.json'));
  assert.equal((await applyMs1Crew(request)).status, 'ALREADY_GRANTED', 'recover crash after COMMIT before receipt');
  withDb(c.gameFile, db => {
    const other = JSON.parse(before[1].profile_json); other.resources.credits = 765432;
    db.prepare('UPDATE game_profiles SET profile_json=? WHERE account_id=?').run(JSON.stringify(other), c.otherId);
    db.prepare('UPDATE game_limits SET hits=? WHERE key_hash=?').run(9, 'own-counter');
  });
  const changedOther = profiles(c.gameFile)[1];
  assert.equal((await rollbackMs1Crew(request)).status, 'ROLLED_BACK');
  assert.deepEqual(profiles(c.gameFile)[0], before[0]); assert.deepEqual(profiles(c.gameFile)[1], changedOther);
  assert.equal(withDb(c.gameFile, db => db.prepare('SELECT hits FROM game_limits WHERE key_hash=?').get('own-counter').hits, true), 9);
  assert.deepEqual(hashes(applied.fixture_directory), fixtureHashes);
  assert.equal((await rollbackMs1Crew(request)).status, 'ALREADY_ROLLED_BACK');
  unlinkSync(join(c.options.journal, 'rolled-back.json'));
  assert.equal((await rollbackMs1Crew(request)).status, 'ALREADY_ROLLED_BACK', 'recover crash after rollback COMMIT');
  await assert.rejects(applyMs1Crew(request), /already rolled back/);
  assert.equal((await rollbackTestVehicle({ service: c.service, journal: c.oldGrant.journal,
    expectedJournalSha256: c.oldGrant.journal_sha256 })).status, 'ROLLED_BACK');
  assert.equal(JSON.parse(profiles(c.gameFile)[0].profile_json).profile_version, 1, 'frozen old rollback remains valid');
  assert.deepEqual(profiles(c.gameFile)[1], changedOther);
});

test('crew journal rejects tampering, changed target and unrelated writes before first apply', { skip: needExport }, async t => {
  const c = await context(t), planned = await planMs1Crew(c.options), before = profiles(c.gameFile);
  const request = { service: c.service, journal: planned.journal, expectedJournalSha256: planned.journal_sha256 };
  const backupPath = join(planned.journal, 'identity-before.sqlite'), saved = readFileSync(backupPath);
  writeFileSync(backupPath, Buffer.from('damaged-backup'));
  await assert.rejects(applyMs1Crew(request), /backup integrity/); writeFileSync(backupPath, saved);
  withDb(c.gameFile, db => db.prepare('UPDATE game_limits SET hits=? WHERE key_hash=?').run(4, 'own-counter'));
  await assert.rejects(applyMs1Crew(request), /Database changed before apply/);
  assert.deepEqual(profiles(c.gameFile), before); assert.ok(!existsSync(planned.fixture_directory));
  withDb(c.gameFile, db => db.prepare('UPDATE game_limits SET hits=? WHERE key_hash=?').run(3, 'own-counter'));
  await applyMs1Crew(request);
  const after = profiles(c.gameFile), newer = JSON.parse(after[0].profile_json); newer.resources.credits++;
  withDb(c.gameFile, db => db.prepare('UPDATE game_profiles SET profile_json=? WHERE account_id=?').run(JSON.stringify(newer), c.id));
  await assert.rejects(rollbackMs1Crew(request), /target changed/);
  assert.equal(JSON.parse(profiles(c.gameFile)[0].profile_json).resources.credits, newer.resources.credits);
});

test('profile3 bridge serves exact authenticated fixture and owned overview; profile1/2 stay separate', { skip: needExport }, async t => {
  const c = await context(t), planned = await planMs1Crew(c.options);
  await applyMs1Crew({ service: c.service, journal: planned.journal, expectedJournalSha256: planned.journal_sha256 });
  const password = 'owned-test-password-only-123', passwordHash = await hashPassword(password), secret = token();
  withDb(c.identityFile, db => db.prepare('UPDATE users SET password_hash=? WHERE id=?').run(passwordHash, c.id));
  writeFileSync(c.bridge.token_file, secret);
  const server = await createIdentityBridge({ ...c.bridge, port: 0 });
  try {
  const origin = `http://127.0.0.1:${server.port}`, reader = createGameReader({ origin, tokenFile: c.bridge.token_file });
  const own = await reader(c.id); assert.equal(own.snapshotRevision, 3); assert.deepEqual(own.inventory.map(v => v.crewAssigned), [true, false]);
  const other = await reader(c.otherId); assert.equal(other.snapshotRevision, 1); assert.equal(other.inventory[0].crewAssigned, false);
  const response = await fetch(origin + '/internal/native/login', { method: 'POST',
    headers: { Authorization: `Bearer ${secret}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ email: '1@example.test', password }) });
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { account_id: c.id, native_database_id: 1, name: c.base.username, fixture_dir: planned.fixture_directory });
  const manifestPath = join(planned.fixture_directory, 'manifest.json'), manifest = readFileSync(manifestPath);
  const changed = JSON.parse(manifest); changed.preservation.crew_grant.native_export_sha256 = '0'.repeat(64); save(manifestPath, changed);
  assert.equal((await reader(c.id)).state, 'unavailable'); writeFileSync(manifestPath, manifest);
  assert.equal((await reader(c.id)).state, 'ready');
  } finally { await server.close(); }
});
