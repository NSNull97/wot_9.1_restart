import test from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { createServer } from 'node:net';
import { createHash, randomUUID } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync, mkdirSync, copyFileSync, unlinkSync, readdirSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { grantTestVehicle, rollbackTestVehicle, validateGrantedProfile, validateGrantedFixture,
  grantedOverview, isGrantedOverview, loadGarageService, LEGACY_ENCODER_SHA256 } from '../src/test-garage.mjs';
import { createIdentityBridge, createGameReader } from '../src/game-adapter.mjs';
import { hashPassword, token } from '../src/security.mjs';
import ejs from 'ejs';
import { testDirectory, removeTestDirectory, freePort } from './helpers.mjs';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const MS1 = resolve(ROOT, 'local/evidence/20261004-p02-hangar/native-descriptors.json');
const IS7 = resolve(ROOT, 'local/evidence/20261004-p02-hangar-ui/ui06-catalog2-manual-runtime/original-vehicle-is7.json');
const SHA = bytes => createHash('sha256').update(bytes).digest('hex');
const readJSON = path => JSON.parse(readFileSync(path, 'utf8'));
const save = (path, value) => writeFileSync(path, JSON.stringify(value, null, 2) + '\n');
const needNative = !existsSync(MS1) || !existsSync(IS7) ? 'NOT_RUN: actual native #717 MS-1 and IS-7 descriptors required' : false;
function withDb(path, callback) { const db = new DatabaseSync(path); try { return callback(db); } finally { db.close(); } }
function profiles(path) { return withDb(path, db => db.prepare('SELECT * FROM game_profiles ORDER BY native_id').all().map(row => ({ ...row }))); }
function hashes(path) { return readdirSync(path).sort().map(file => [file, SHA(readFileSync(join(path, file)))]); }

async function context(t) {
  const directory = testDirectory(); t.after(() => removeTestDirectory(directory));
  const runtime = join(directory, 'server'), portal = join(directory, 'identity');
  mkdirSync(runtime); mkdirSync(portal);
  const identityFile = join(portal, 'portal.sqlite'), gameFile = join(runtime, 'game.sqlite');
  const id = randomUUID(), otherId = randomUUID(), stamp = 1791110000000;
  const base = { profile_version: 1, account_id: id, username: 'Танкист_Ёж', native_database_id: 1,
    created_at_ms: stamp, snapshot_revision: 1, resources: { credits: 123456, gold: 7, free_xp: 8 },
    statistics: { battles: 0, wins: 0, losses: 0, draws: 0 } };
  const other = { ...base, account_id: otherId, username: 'second_tester', native_database_id: 2,
    resources: { credits: 99, gold: 0, free_xp: 0 } };
  withDb(identityFile, db => {
    db.exec(`CREATE TABLE users(id TEXT PRIMARY KEY, username TEXT, display_nickname TEXT,
      created_at INTEGER, email TEXT, password_hash TEXT); PRAGMA user_version=2;`);
    const insert = db.prepare('INSERT INTO users VALUES (?,?,?,?,?,?)');
    insert.run(id, base.username.toLowerCase(), base.username, stamp, 'owned@example.test', 'UNIT_TEST_NO_CREDENTIAL');
    insert.run(otherId, other.username, other.username, stamp, 'other@example.test', 'UNIT_TEST_NO_CREDENTIAL');
  });
  const ms1 = join(runtime, 'native-descriptors.json'); copyFileSync(MS1, ms1);
  withDb(gameFile, db => {
    db.exec(`PRAGMA journal_mode=WAL;
      CREATE TABLE game_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
      CREATE TABLE game_profiles(native_id INTEGER PRIMARY KEY AUTOINCREMENT CHECK(native_id BETWEEN 1 AND 2147483647),
        account_id TEXT NOT NULL UNIQUE,profile_json TEXT NOT NULL);
      CREATE TABLE game_limits(key_hash TEXT PRIMARY KEY,hits INTEGER NOT NULL,resets_at INTEGER NOT NULL);
      PRAGMA user_version=1;`);
    db.prepare('INSERT INTO game_meta VALUES (?,?)').run('native_descriptors_sha256', SHA(readFileSync(ms1)));
    for (const profile of [base, other]) db.prepare('INSERT INTO game_profiles(native_id,account_id,profile_json) VALUES (?,?,?)')
      .run(profile.native_database_id, profile.account_id, JSON.stringify(profile));
    db.prepare('INSERT INTO game_limits VALUES (?,?,?)').run('bounded-counter', 3, stamp);
  });
  const pythonProbe = spawnSync('python', ['-c', 'import sys; print(sys.executable)'], { encoding: 'utf8', windowsHide: true, timeout: 5000 });
  assert.equal(pythonProbe.status, 0);
  const python = pythonProbe.stdout.trim();
  const ports = [];
  while (ports.length < 3) { const port = await freePort(); if (!ports.includes(port)) ports.push(port); }
  const service = join(runtime, 'service.json'), bridgeFile = join(runtime, 'bridge.json'), gatewayFile = join(runtime, 'gateway.json');
  const fixtureRoot = join(runtime, 'fixtures'); mkdirSync(fixtureRoot);
  const config = { version: 2, web_mode: 'external', runtime_dir: runtime, portal_data: portal, web_port: 3091,
    node_executable: process.execPath, python_executable: python, gateway_executable: process.execPath };
  const bridge = { version: 1, port: ports[0], web_database: identityFile, game_database: gameFile, fixture_root: fixtureRoot,
    native_descriptors: ms1, python_executable: python, token_file: join(runtime, 'identity.token'),
    test_garage: { version: 1, native_is7: IS7, sha256: SHA(readFileSync(IS7)) } };
  const gateway = { login_bind: `127.0.0.1:${ports[1]}`, base_bind: `127.0.0.1:${ports[2]}`,
    identity_endpoint: `127.0.0.1:${ports[0]}`, identity_token_file: bridge.token_file,
    local_root: resolve(ROOT, 'local'), session_duration_seconds: 1800 };
  save(service, config); save(bridgeFile, bridge); save(gatewayFile, gateway);
  save(join(runtime, 'state.json'), { status: 'STOPPED', processes: [] });
  const previous = join(fixtureRoot, id, 'r1-catalog2'); mkdirSync(previous, { recursive: true });
  const oldInput = join(previous, 'profile-input.json'); save(oldInput, base);
  const generated = spawnSync(python, ['-B', '-X', 'utf8', resolve(ROOT, 'tools/hangar_state.py'), '--out', previous,
    '--native-descriptors', ms1, '--profile', oldInput, '--catalog-version', '2'],
  { encoding: 'utf8', timeout: 10000, windowsHide: true });
  assert.equal(generated.status, 0, generated.stderr);
  const options = { service, accountId: id, nativeIs7: IS7, grantedAtMs: stamp + 12345,
    expectedProfileSha256: SHA(JSON.stringify(base)), journal: join(directory, 'grant-journal') };
  return { directory, runtime, identityFile, gameFile, id, otherId, base, other, python, ports, service,
    bridgeFile, gatewayFile, bridge, gateway, previous, ms1, options };
}

test('offline test grant uses actual descriptors, preserves state and rolls back after unrelated writes', { skip: needNative }, async t => {
  const c = await context(t), before = profiles(c.gameFile), identityHash = SHA(readFileSync(c.identityFile)), previousHashes = hashes(c.previous);
  const granted = await grantTestVehicle(c.options);
  assert.equal(granted.status, 'GRANTED'); assert.equal(granted.account_id, c.id); assert.equal(granted.native_database_id, 1);
  assert.equal(granted.native_compatibility, 'NOT_RUN', 'local generator must never claim native acceptance');
  const current = profiles(c.gameFile), profile = JSON.parse(current[0].profile_json);
  assert.deepEqual(current[1], before[1]);
  assert.deepEqual(profile.resources, c.base.resources); assert.deepEqual(profile.statistics, c.base.statistics);
  assert.equal(profile.created_at_ms, c.base.created_at_ms); assert.equal(profile.username, c.base.username);
  assert.equal(profile.native_database_id, 1); assert.equal(profile.account_id, c.id);
  assert.equal(profile.test_grant.base_profile_sha256, SHA(readFileSync(join(c.previous, 'profile-input.json'))));
  assert.notEqual(profile.test_grant.base_profile_sha256, c.options.expectedProfileSha256, 'exact historical pretty bytes differ from DB JSON bytes');
  assert.deepEqual(profile.inventory.map(item => item.inventory_id), [`${c.id}:starter-vehicle-v1`, `${c.id}:test-is7-v1`]);
  assert.deepEqual(profile.inventory.map(item => item.health), [90, 2150]);
  assert.ok(profile.inventory.every(item => item.crew_assigned === false && item.ammunition_count === 0));
  assert.equal(validateGrantedFixture(granted.fixture_directory, profile, { nativeMs1: c.ms1, nativeIs7: IS7 }).files.length, 10);
  assert.deepEqual(hashes(c.previous), previousHashes); assert.equal(SHA(readFileSync(c.identityFile)), identityHash);
  assert.deepEqual(profiles(join(c.options.journal, 'game-before.sqlite')), before, 'consistent backup has exact pre-grant logical records');
  assert.equal(SHA(readFileSync(resolve(ROOT, 'tools/hangar_state.py'))), LEGACY_ENCODER_SHA256);
  const fixtureHashes = hashes(granted.fixture_directory), journalHashes = hashes(c.options.journal);
  const repeated = await grantTestVehicle(c.options);
  assert.equal(repeated.status, 'ALREADY_GRANTED'); assert.equal(repeated.journal_sha256, granted.journal_sha256);
  assert.deepEqual(hashes(granted.fixture_directory), fixtureHashes); assert.deepEqual(hashes(c.options.journal), journalHashes);
  assert.deepEqual(profiles(c.gameFile), current);
  const web = grantedOverview(profile);
  assert.equal(web.snapshotRevision, 2); assert.deepEqual(web.inventory.map(item => item.displayName), ['МС-1', 'ИС-7']);
  assert.deepEqual(web.resources, { credits: 123456, gold: 7, freeXP: 8 });
  assert.deepEqual(web.capabilities, { battle: false, purchases: false, sales: false });
  withDb(c.gameFile, db => {
    db.prepare('UPDATE game_limits SET hits=?,resets_at=? WHERE key_hash=?').run(9, 1791123333444, 'bounded-counter');
    const other = JSON.parse(before[1].profile_json); other.resources.credits = 765432;
    db.prepare('UPDATE game_profiles SET profile_json=? WHERE account_id=?').run(JSON.stringify(other), c.otherId);
  });
  const changedOther = profiles(c.gameFile)[1];
  const rollback = { service: c.service, journal: c.options.journal, expectedJournalSha256: granted.journal_sha256 };
  assert.equal((await rollbackTestVehicle(rollback)).status, 'ROLLED_BACK');
  assert.deepEqual(profiles(c.gameFile)[0], before[0]); assert.deepEqual(profiles(c.gameFile)[1], changedOther);
  assert.deepEqual(withDb(c.gameFile, db => ({ ...db.prepare('SELECT * FROM game_limits').get() })),
    { key_hash: 'bounded-counter', hits: 9, resets_at: 1791123333444 });
  assert.deepEqual(hashes(granted.fixture_directory), fixtureHashes, 'rollback retains immutable native evidence');
  assert.equal((await rollbackTestVehicle(rollback)).status, 'ALREADY_ROLLED_BACK');
  unlinkSync(join(c.options.journal, 'rolled-back.json'));
  assert.equal((await rollbackTestVehicle(rollback)).status, 'ALREADY_ROLLED_BACK');
  assert.equal(readJSON(join(c.options.journal, 'rolled-back.json')).original_profile_already_present, true,
    'recover interrupted rollback receipt by observing exact original row, without another database mutation');
  assert.equal(SHA(readFileSync(c.identityFile)), identityHash); assert.deepEqual(hashes(c.previous), previousHashes);
  assert.ok(!existsSync(join(c.runtime, 'supervisor.lock')));
  await assert.rejects(grantTestVehicle(c.options), /already rolled back/);
  const explicitRegrant = await grantTestVehicle({ ...c.options, journal: join(c.directory, 'explicit-regrant') });
  assert.equal(explicitRegrant.status, 'GRANTED'); assert.equal(profiles(c.gameFile).length, 2);
  assert.deepEqual(profiles(c.gameFile)[1], changedOther); assert.deepEqual(hashes(explicitRegrant.fixture_directory), fixtureHashes);
  await rollbackTestVehicle({ service: c.service, journal: explicitRegrant.journal, expectedJournalSha256: explicitRegrant.journal_sha256 });
});

test('offline lease refuses live state, existing owner lock, occupied loopback port and nonlocal endpoint', { skip: needNative }, async t => {
  const c = await context(t), original = profiles(c.gameFile);
  save(join(c.runtime, 'state.json'), { status: 'RUNNING', processes: [] });
  await assert.rejects(grantTestVehicle(c.options), /must be stopped/);
  save(join(c.runtime, 'state.json'), { status: 'STOPPED', processes: [{ role: 'gateway', pid: 123 }] });
  await assert.rejects(grantTestVehicle(c.options), /exit is unconfirmed/);
  save(join(c.runtime, 'state.json'), { status: 'STOPPED', processes: [] });
  writeFileSync(join(c.runtime, 'supervisor.lock'), 'OTHER_OWNER');
  await assert.rejects(grantTestVehicle(c.options), /EEXIST/);
  assert.equal(readFileSync(join(c.runtime, 'supervisor.lock'), 'utf8'), 'OTHER_OWNER');
  unlinkSync(join(c.runtime, 'supervisor.lock'));
  const listener = createServer(socket => socket.destroy());
  await new Promise(done => listener.listen(c.ports[0], '127.0.0.1', done));
  try { await assert.rejects(grantTestVehicle(c.options), /occupied|EADDRINUSE/); }
  finally { await new Promise(done => listener.close(done)); }
  assert.ok(!existsSync(join(c.runtime, 'supervisor.lock')));
  save(c.gatewayFile, { ...c.gateway, login_bind: '192.0.2.1:20014' });
  assert.throws(() => loadGarageService(c.service), /loopback/);
  assert.deepEqual(profiles(c.gameFile), original); assert.ok(!existsSync(c.options.journal));
});

test('wrong UUID/hash, mismatched identity and corrupted historical payload fail before any grant', { skip: needNative }, async t => {
  const c = await context(t), original = profiles(c.gameFile);
  await assert.rejects(grantTestVehicle({ ...c.options, accountId: randomUUID() }), /Existing bounded game profile/);
  await assert.rejects(grantTestVehicle({ ...c.options, expectedProfileSha256: '0'.repeat(64) }), /Expected target/);
  withDb(c.identityFile, db => db.prepare('UPDATE users SET display_nickname=? WHERE id=?').run('ChangedNickname', c.id));
  await assert.rejects(grantTestVehicle(c.options), /identity differs/);
  withDb(c.identityFile, db => db.prepare('UPDATE users SET display_nickname=? WHERE id=?').run(c.base.username, c.id));
  const state = join(c.previous, 'state.bin'), originalBytes = readFileSync(state), corrupt = Buffer.from(originalBytes); corrupt[0] ^= 1;
  writeFileSync(state, corrupt);
  await assert.rejects(grantTestVehicle(c.options), /Historical payload integrity/);
  writeFileSync(state, originalBytes);
  assert.deepEqual(profiles(c.gameFile), original); assert.ok(!existsSync(c.options.journal));
});

test('expected-hash rollback refuses target/fixture/backup tampering and preserves newer data', { skip: needNative }, async t => {
  const c = await context(t), grant = await grantTestVehicle(c.options), post = profiles(c.gameFile);
  const request = { service: c.service, journal: c.options.journal, expectedJournalSha256: grant.journal_sha256 };
  await assert.rejects(rollbackTestVehicle({ ...request, expectedJournalSha256: '0'.repeat(64) }), /Unexpected journal hash/);
  withDb(c.gameFile, db => {
    const current = JSON.parse(post[0].profile_json); current.resources.credits++;
    db.prepare('UPDATE game_profiles SET profile_json=? WHERE account_id=?').run(JSON.stringify(current), c.id);
  });
  const newer = profiles(c.gameFile);
  await assert.rejects(rollbackTestVehicle(request), /target changed/); assert.deepEqual(profiles(c.gameFile), newer);
  withDb(c.gameFile, db => db.prepare('UPDATE game_profiles SET profile_json=? WHERE account_id=?').run(post[0].profile_json, c.id));
  for (const path of [join(grant.fixture_directory, 'state.bin'), join(c.options.journal, 'game-before.sqlite')]) {
    const before = readFileSync(path), corrupt = Buffer.from(before); corrupt[corrupt.length - 1] ^= 1; writeFileSync(path, corrupt);
    await assert.rejects(rollbackTestVehicle(request), /integrity|changed/i);
    assert.deepEqual(profiles(c.gameFile), post); writeFileSync(path, before);
  }
  assert.equal((await rollbackTestVehicle(request)).status, 'ROLLED_BACK');
});

test('replaying journal recovers missing post-commit receipt without a duplicate grant', { skip: needNative }, async t => {
  const c = await context(t), grant = await grantTestVehicle(c.options), after = profiles(c.gameFile);
  unlinkSync(join(c.options.journal, 'committed.json'));
  const recovered = await grantTestVehicle(c.options);
  assert.equal(recovered.status, 'ALREADY_GRANTED'); assert.equal(recovered.journal_sha256, grant.journal_sha256);
  assert.equal(readJSON(join(c.options.journal, 'committed.json')).recovered_after_commit, true);
  assert.deepEqual(profiles(c.gameFile), after);
  await assert.rejects(grantTestVehicle({ ...c.options, grantedAtMs: c.options.grantedAtMs + 1 }), /different explicit request/);
  await assert.rejects(grantTestVehicle({ ...c.options, journal: join(c.directory, 'other-journal') }), /Exact profile1 required/);
});

test('domain profile validation rejects hidden changes and exposes no native identifiers in website inventory', () => {
  const id = randomUUID(), base = { profile_version: 1, account_id: id, username: 'Test_Ёж', native_database_id: 9,
    created_at_ms: 1791110000000, snapshot_revision: 1, resources: { credits: 15, gold: 0, free_xp: 0 },
    statistics: { battles: 0, wins: 0, losses: 0, draws: 0 } };
  const bytes = Buffer.from(JSON.stringify(base));
  const profile = { ...base, profile_version: 2, snapshot_revision: 2,
    inventory: [['starter-vehicle-v1', 'vehicle:ms1', 90], ['test-is7-v1', 'vehicle:is7', 2150]].map(([suffix, definition, health]) => ({
      inventory_id: `${id}:${suffix}`, vehicle_definition_id: definition, health, vehicle_xp: 0, crew_assigned: false, ammunition_count: 0 })),
    test_grant: { grant_id: 'test-is7-v1', granted_at_ms: 1791110001000, base_profile_sha256: SHA(bytes) } };
  assert.equal(validateGrantedProfile(profile, bytes), profile);
  for (const mutate of [p => { p.inventory[1].health = 99999; }, p => { p.inventory[1].crew_assigned = true; },
    p => { p.resources.credits++; }, p => { p.native_database_id++; }, p => { p.statistics.battles = 1; },
    p => { p.inventory.push({ ...p.inventory[1] }); }, p => { p.test_grant.granted_at_ms = 1; },
    p => { p.inventory[1].native_inventory_id = 2; }]) {
    const invalid = structuredClone(profile); mutate(invalid); assert.throws(() => validateGrantedProfile(invalid, bytes));
  }
  assert.equal(JSON.stringify(grantedOverview(profile)).includes('native_'), false);
  assert.equal(isGrantedOverview(grantedOverview(profile), id), true);
  assert.equal(isGrantedOverview(grantedOverview(profile), randomUUID()), false);
  for (const mutate of [v => { v.inventory.pop(); }, v => { v.inventory[1].health = 100; },
    v => { v.capabilities.purchases = true; }, v => { v.resources.credits = -1; },
    v => { v.statistics.battles = 1; }, v => { v.inventory[0].native_id = 1; }]) {
    const invalid = structuredClone(grantedOverview(profile)); mutate(invalid); assert.equal(isGrantedOverview(invalid, id), false);
  }
});

test('CLI grant, real bridge authentication/restart and rendered account read the same immutable inventory', { skip: needNative }, async t => {
  const c = await context(t), password = '  locally-owned-test-password_Ё  ', secret = token();
  const encoded = await hashPassword(password);
  withDb(c.identityFile, db => db.prepare('UPDATE users SET password_hash=?').run(encoded));
  writeFileSync(c.bridge.token_file, secret, { flag: 'wx' });
  const args = ['web/src/test-garage.mjs', 'grant', '--service', c.service, '--account-id', c.id, '--native-is7', IS7,
    '--granted-at-ms', String(c.options.grantedAtMs), '--expect-profile-sha256', c.options.expectedProfileSha256, '--journal', c.options.journal];
  const result = spawnSync(process.execPath, args, { cwd: ROOT, encoding: 'utf8', windowsHide: true, timeout: 15000 });
  assert.equal(result.status, 0, result.stderr); const grant = JSON.parse(result.stdout);
  assert.equal(grant.status, 'GRANTED'); assert.ok(!result.stdout.includes(password) && !result.stdout.includes(encoded));
  const before = profiles(c.gameFile), immutable = hashes(grant.fixture_directory), identityBefore = SHA(readFileSync(c.identityFile));
  let bridge;
  try {
    bridge = await createIdentityBridge(c.bridge);
    const reader = createGameReader({ origin: `http://127.0.0.1:${bridge.port}`, tokenFile: c.bridge.token_file });
    for (let pass = 0; pass < 2; pass++) {
      const response = await fetch(`http://127.0.0.1:${bridge.port}/internal/native/login`, { method: 'POST',
        signal: AbortSignal.timeout(6000), headers: { Authorization: `Bearer ${secret}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: 'owned@example.test', password }) });
      assert.equal(response.status, 200); assert.deepEqual(await response.json(), { account_id: c.id, native_database_id: 1,
        name: c.base.username, fixture_dir: grant.fixture_directory });
      const game = await reader(c.id); assert.equal(game.state, 'ready'); assert.equal(game.snapshotRevision, 2);
      assert.deepEqual(game.inventory.map(item => item.displayName), ['МС-1', 'ИС-7']);
      assert.equal((await reader(c.otherId)).inventory.length, 1, 'other account remains r1/MS-1');
      const view = await ejs.renderFile(resolve(ROOT, 'web/views/account.ejs'), {
        title: 'Test account', description: '', user: { id: c.id, display_name: 'Тестер', display_nickname: c.base.username,
          email: 'owned@example.test', created_at: c.base.created_at_ms }, game,
        welcome: false, saved: false, errors: {}, values: {}, csrf: token(), currentPath: '/account',
      });
      assert.match(view, /МС-1 · 90 HP/); assert.match(view, /ИС-7 · 2150 HP/);
      assert.equal((view.match(/data-inventory-item=/g) || []).length, 2);
      assert.ok(view.includes(`${c.id}:starter-vehicle-v1`) && view.includes(`${c.id}:test-is7-v1`));
      assert.ok(!view.includes(c.otherId)); assert.doesNotMatch(view, /undefined|NaN|Infinity/);
      await bridge.close(); bridge = null;
      assert.deepEqual(profiles(c.gameFile), before); assert.deepEqual(hashes(grant.fixture_directory), immutable);
      assert.equal(SHA(readFileSync(c.identityFile)), identityBefore);
      if (pass === 0) bridge = await createIdentityBridge(c.bridge);
    }
  } finally { if (bridge) await bridge.close(); }
  const rolledBack = spawnSync(process.execPath, ['web/src/test-garage.mjs', 'rollback', '--service', c.service,
    '--journal', c.options.journal, '--expect-journal-sha256', grant.journal_sha256],
  { cwd: ROOT, encoding: 'utf8', windowsHide: true, timeout: 15000 });
  assert.equal(rolledBack.status, 0, rolledBack.stderr); assert.equal(JSON.parse(rolledBack.stdout).status, 'ROLLED_BACK');
  assert.equal(profiles(c.gameFile)[0].profile_json, JSON.stringify(c.base));
  assert.deepEqual(hashes(grant.fixture_directory), immutable);
});
