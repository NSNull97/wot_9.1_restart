/** Real loopback HTTP -> current Python PoolStore -> isolated SQLite backups. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync, copyFileSync, realpathSync, readdirSync, statSync } from 'node:fs';
import { join, resolve, relative, isAbsolute } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createIdentityBridge, createGameReader } from '../src/game-adapter.mjs';
import { hashPassword, token } from '../src/security.mjs';
import { CREW_POLICY_SHA256, TRANSFER_POLICY_SHA256, CROSS_CREW_POLICY_SHA256, ROSTER_CREW_POLICY_SHA256,
  PROGRESSION_CREW_POLICY_SHA256, DISMISSAL_CREW_POLICY_SHA256 } from '../src/p04d-crew.mjs';
import { BARRACKS_CREW_POLICY_SHA256 } from '../src/p04k-crew.mjs';
import { RESEARCH_POLICY_SHA256 } from '../src/p09e-research.mjs';
import { BATTLE_POLICY_SHA256 } from '../src/p08b-battle.mjs';
import { POOL_POLICY_SHA256, isNativePoolOverview } from '../src/p04m-pool.mjs';
import { testDirectory, removeTestDirectory } from './helpers.mjs';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const SEEDS = resolve(process.env.P04M_HTTP_SEEDS || join(ROOT, 'local/evidence/20261016-p04m-writer01'));
const digest = b => createHash('sha256').update(b).digest('hex');
const seedPath = name => join(SEEDS, name, 'seed.json');
const skipped = name => !existsSync(seedPath(name)) ? 'NOT_RUN: real P04M Python SQLite seed required' : false;
function db(path, fn) { const d = new DatabaseSync(path); try { return fn(d); } finally { d.close(); } }
function receipt(name, value) {
  if (!process.env.P04M_HTTP_EVIDENCE_DIR) return;
  const output = realpathSync(process.env.P04M_HTTP_EVIDENCE_DIR), local = realpathSync(join(ROOT, 'local'));
  const part = relative(local, output);
  assert.ok(part && !part.startsWith('..') && !isAbsolute(part));
  writeFileSync(join(output, name), JSON.stringify(value, null, 2) + '\n', { flag: 'wx' });
}
async function setup(t, name) {
  const directory = testDirectory(), source = JSON.parse(readFileSync(seedPath(name)));
  assert.equal(source.schema, 'p04m-http-real-writer-seed.v1'); assert.equal(source.source_stand_writes, false);
  const gameFile = join(directory, 'game.sqlite'), identityFile = join(directory, 'identity.sqlite');
  const before = digest(readFileSync(source.database));
  const copy = spawnSync('python', ['-B', '-c',
    'import sqlite3,sys,pathlib;from contextlib import closing;\nwith closing(sqlite3.connect(pathlib.Path(sys.argv[1]).resolve().as_uri()+"?mode=ro",uri=True)) as a,closing(sqlite3.connect(sys.argv[2])) as b:a.backup(b)',
    source.database, gameFile], { cwd: ROOT, encoding: 'utf8', windowsHide: true, timeout: 10000 });
  assert.equal(copy.status, 0, copy.stderr); assert.equal(digest(readFileSync(source.database)), before);
  const secret = token(), password = token(), passwordHash = await hashPassword(password);
  const nativePath = join(directory, 'native.json'), tokenFile = join(directory, 'identity.token');
  copyFileSync(join(source.bundle, 'content/inputs/native-ms1.blob'), nativePath); writeFileSync(tokenFile, secret);
  const users = source.profiles.map((p, i) => ({ profile: p, email: `p04m-${name}-${i}@example.test` }));
  db(identityFile, d => {
    d.exec('PRAGMA user_version=2; CREATE TABLE users(id TEXT PRIMARY KEY,username TEXT,display_nickname TEXT,email TEXT,password_hash TEXT,created_at INTEGER)');
    for (const { profile: p, email } of users) d.prepare('INSERT INTO users VALUES (?,?,?,?,?,?)').run(p.account_id,
      p.username.toLowerCase(), p.username, email, passwordHash, p.created_at_ms);
  });
  db(gameFile, d => d.prepare('INSERT INTO game_meta VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value')
    .run('native_descriptors_sha256', digest(readFileSync(nativePath))));
  const py = spawnSync('python', ['-B', '-c', 'import sys;print(sys.executable)'], { encoding: 'utf8', windowsHide: true });
  assert.equal(py.status, 0, py.stderr);
  const options = { version: 1, port: 0, web_database: identityFile, game_database: gameFile,
    fixture_root: join(directory, 'fixtures'), native_descriptors: nativePath, python_executable: py.stdout.trim(), token_file: tokenFile,
    ammunition_service: { version: 1, bundle_root: source.bundle, original_root: source.original, account_id: source.pool_accounts[0],
      grant: { grant_id: 'p09d-test-depot-v1', quantity_each: 100 } },
    crew_service: { version: 1, policy_sha256: CREW_POLICY_SHA256 },
    crew_transfer: { version: 1, policy_sha256: TRANSFER_POLICY_SHA256 },
    crew_cross_vehicle: { version: 1, policy_sha256: CROSS_CREW_POLICY_SHA256 },
    crew_roster_recruitment: { version: 1, policy_sha256: ROSTER_CREW_POLICY_SHA256 },
    crew_progression: { version: 1, policy_sha256: PROGRESSION_CREW_POLICY_SHA256 },
    crew_dismissal: { version: 1, policy_sha256: DISMISSAL_CREW_POLICY_SHA256 },
    crew_barracks_recruitment: { version: 1, policy_sha256: BARRACKS_CREW_POLICY_SHA256 },
    research_service: { version: 1, policy_sha256: RESEARCH_POLICY_SHA256 },
    battle_service: { version: 1, policy_sha256: BATTLE_POLICY_SHA256, accounts: users.map(u => u.profile.account_id) },
    pool_service: { version: 1, policy_sha256: POOL_POLICY_SHA256, accounts: source.pool_accounts } };
  let bridge = null;
  t.after(async () => { if (bridge) await bridge.close(); assert.equal(digest(readFileSync(source.database)), before); removeTestDirectory(directory); });
  const start = async (configuration = options) => { bridge = await createIdentityBridge(configuration); };
  const close = async () => { if (bridge) await bridge.close(); bridge = null; };
  const events = [];
  async function call(path, data, authorization = secret) {
    const r = await fetch(`http://127.0.0.1:${bridge.port}${path}`, { method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${authorization}` }, body: JSON.stringify(data) });
    const result = { status: r.status, body: await r.json() };
    events.push({ path, http: result.status, status: result.body.status ?? null, result_code: result.body.result_code ?? null });
    return result;
  }
  const owner = source.pool_accounts[0]; let serial = 0;
  const profile = (id = owner) => db(gameFile, d => JSON.parse(d.prepare('SELECT profile_json FROM game_profiles WHERE account_id=?').get(id).profile_json));
  const aggregate = (id = owner) => db(gameFile, d => d.prepare('SELECT snapshot_json FROM game_snapshot WHERE account_id=?').get(id).snapshot_json);
  const command = (layout, id = owner) => ({ account_id: id, native_database_id: profile(id).native_database_id,
    command_key: `p04m-http:${++serial}`, expected_revision: profile(id).snapshot_revision, wire_revision: 1, layout });
  const login = id => call('/internal/native/login', { email: users.find(u => u.profile.account_id === id).email, password });
  const read = async id => {
    const begin = Date.now(), response = await fetch(`http://127.0.0.1:${bridge.port}/internal/accounts/${id}/overview`,
      { headers: { Authorization: `Bearer ${secret}` } });
    const raw = await response.json();
    events.push({ path: '/internal/accounts/:owner/overview', http: response.status, milliseconds: Date.now() - begin, state: raw.state ?? null });
    assert.equal(response.status, 200, `Raw overview ${JSON.stringify(raw)}`);
    assert.equal(raw.state, 'ready');
    if (!source.pool_accounts.includes(id)) return raw; // The retained legacy route is checked below and by its unchanged regression.
    const readerStart = Date.now();
    const result = await createGameReader({ origin: `http://127.0.0.1:${bridge.port}`, tokenFile })(id);
    const readerMs = Date.now() - readerStart;
    events.push({ path: 'createGameReader(:pool-owner)', state: result.state, milliseconds: readerMs });
    assert.equal(result.state, 'ready', `Reader unavailable; raw response took ${Date.now() - begin}ms`);
    assert.ok(readerMs < 2500, 'Pool reader stays within the unchanged 2500ms deadline');
    return result;
  };
  const refresh = id => call('/internal/native/profile', { account_id: id, native_database_id: profile(id).native_database_id });
  const fixtureTree = () => JSON.stringify(readdirSync(options.fixture_root, { recursive: true }).sort().map(name => {
    const p = join(options.fixture_root, name); return [name, statSync(p).isFile() ? digest(readFileSync(p)) : null];
  }));
  const malformedOverview = async () => {
    const old = JSON.stringify(profile());
    const bad = JSON.parse(old); bad.pool_service.registry_sha256 = '0'.repeat(64);
    db(gameFile, d => d.prepare('UPDATE game_profiles SET profile_json=? WHERE account_id=?').run(JSON.stringify(bad), owner));
    try {
      const r = await fetch(`http://127.0.0.1:${bridge.port}/internal/accounts/${owner}/overview`, { headers: { Authorization: `Bearer ${secret}` } });
      assert.equal(r.status, 503); assert.deepEqual(await r.json(), { error: 'unavailable' });
    } finally { db(gameFile, d => d.prepare('UPDATE game_profiles SET profile_json=? WHERE account_id=?').run(old, owner)); }
  };
  const complete = extra => receipt(`${name}.json`, { status: 'PASS_REAL_HTTP_PYTHON_SQLITE', seed_sha256: digest(readFileSync(seedPath(name))),
    seed_database_unchanged: digest(readFileSync(source.database)) === before, native_ui: 'NOT_RUN', events,
    snapshot_sha256: digest(Buffer.from(aggregate())), read_gate: 'STRUCTURAL_CURRENT_PROFILE',
    commands_gate: 'CANONICAL_PYTHON_WRITER', ...extra });
  return { options, owner, users, start, close, call, profile, aggregate, command, login, read, refresh, fixtureTree, malformedOverview, complete };
}

test('P04M real HTTP logs in, recruits T26 primary crew, persists AP160 and republishes after restart', {
  skip: skipped('http-seed-t26-02'), timeout: 120000,
}, async t => {
  const s = await setup(t, 'http-seed-t26-02'); await s.start();
  const originalResources = s.profile().resources;
  assert.equal((await s.login(s.owner)).status, 200);
  let view = await s.read(s.owner); assert.equal(isNativePoolOverview(view, s.owner), true);
  assert.equal(view.inventory[2].ammunition, 0); assert.equal(view.inventory[2].crewAssigned, false);
  for (let slot = 0; slot < 3; slot++) {
    const result = await s.call('/internal/native/crew', s.command([3, 3, slot, 0]));
    assert.equal(result.status, 200, JSON.stringify(result.body)); assert.equal(result.body.status, 'recruited');
  }
  const request = s.command([5, 3, 6, 1034, 160, 1290, 0, 1546, 0, 6, 0, 0, 0, 0, 0, 0]);
  const result = await s.call('/internal/native/ammo', request);
  assert.equal(result.status, 200, JSON.stringify(result.body)); assert.equal(result.body.status, 'serviced');
  assert.equal(s.profile().inventory[2].ammunition_count, 160); assert.equal(s.profile().ammunition_depot['shell:t26-stock-ap'], 0);
  assert.deepEqual(s.profile().resources, originalResources);
  const beforeRead = s.aggregate(), beforeReadTree = s.fixtureTree();
  view = await s.read(s.owner); assert.equal(view.snapshotRevision, s.profile().snapshot_revision);
  assert.equal(view.inventory[2].ammunition, 160); assert.equal(view.inventory[2].crewAssigned, true);
  assert.equal(s.aggregate(), beforeRead); assert.equal(s.fixtureTree(), beforeReadTree, 'Overview must not publish native artifacts');
  await s.malformedOverview(); assert.equal(s.aggregate(), beforeRead);
  assert.equal((await s.read(s.owner)).state, 'ready');
  const after = s.aggregate(), duplicate = await s.call('/internal/native/ammo', request);
  assert.equal(duplicate.body.replayed, true); assert.equal(s.aggregate(), after);
  const rejected = await s.call('/internal/native/ammo', s.command([5, 3, 6, 1034, 161, 1290, 0, 1546, 0, 6, 0, 0, 0, 0, 0, 0]));
  assert.equal(rejected.status, 200); assert.equal(rejected.body.status, 'rejected'); assert.equal(rejected.body.result_code, -10);
  assert.equal(s.aggregate(), after);
  const bound = await s.refresh(s.owner); assert.equal(bound.status, 200);
  const companion = JSON.parse(readFileSync(join(bound.body.fixture_dir, 'p04m-pool.json')));
  assert.equal(companion.policy_sha256, POOL_POLICY_SHA256); assert.equal(companion.capabilities.find(c => c.kind === 't26').admission, false);
  assert.equal((await s.call('/internal/native/ammo', request, token())).status, 403);
  await s.close(); await s.start(); assert.equal((await s.login(s.owner)).status, 200);
  view = await s.read(s.owner); assert.equal(view.state, 'ready'); assert.equal(view.inventory[2].ammunition, 160);
  assert.equal(view.inventory[2].crewAssigned, true); assert.equal(view.poolService.newBattleAdmission, false);
  await s.close(); const withoutPool = { ...s.options }; delete withoutPool.pool_service;
  await assert.rejects(() => s.start(withoutPool), /Curated pool activation\/configuration mismatch/);
  assert.equal(s.aggregate(), after); s.complete({ ap: 160, crew_complete: true, admission: false, restart: 'PASS', implicit_pool: 'DENIED' });
});

test('P04M real HTTP hires T34 type-zero radioman through both native crew routes', {
  skip: skipped('http-seed-t34-01'), timeout: 120000,
}, async t => {
  const s = await setup(t, 'http-seed-t34-01'); await s.start(); assert.equal((await s.login(s.owner)).status, 200);
  const assigned = await s.call('/internal/native/crew', s.command([3, 3, 1, 0]));
  assert.equal(assigned.status, 200, JSON.stringify(assigned.body)); assert.equal(assigned.body.status, 'recruited');
  const barracks = await s.call('/internal/native/crew-recruit-barracks', s.command([3, 1, 2, 0]));
  assert.equal(barracks.status, 200, JSON.stringify(barracks.body)); assert.equal(barracks.body.status, 'recruited');
  assert.equal(barracks.body.tankman_descriptor_hex.slice(0, 8), '08000232');
  const after = s.aggregate(), bad = await s.call('/internal/native/crew-recruit-barracks', s.command([3, 4609, 2, 0]));
  assert.equal(bad.status, 200); assert.equal(bad.body.status, 'rejected'); assert.equal(bad.body.tankman_inventory_id, 0);
  assert.equal(s.aggregate(), after);
  const view = await s.read(s.owner); assert.equal(view.state, 'ready'); assert.equal(view.crewService.vehicles[2].assigned, 1);
  assert.equal(view.crewService.vehicles[2].capacity, 4); assert.equal(view.inventory[2].crewAssigned, false);
  s.complete({ t34_type_zero: 'PASS', assigned_radioman: 1, barracks_radioman: 1, invalid_t26_radioman: 'DENIED' });
});

test('P04M real HTTP owner opt-in keeps the second profile13 account on its strict legacy contract', {
  skip: skipped('http-seed-two-01'), timeout: 120000,
}, async t => {
  const s = await setup(t, 'http-seed-two-01'), other = s.users.find(u => u.profile.account_id !== s.owner).profile.account_id;
  const before = s.aggregate(other); await s.start();
  assert.equal((await s.login(s.owner)).status, 200); assert.equal((await s.login(other)).status, 200);
  assert.equal((await s.read(s.owner)).poolService.version, 1);
  const legacy = await s.read(other); assert.equal(legacy.state, 'ready'); assert.equal(legacy.poolService, undefined);
  assert.equal(legacy.crewService.version, 7); assert.equal(legacy.researchService.version, 1);
  const result = await s.call('/internal/native/crew-recruit-barracks', s.command([3, 3329, 1, 0]));
  assert.equal(result.status, 200, JSON.stringify(result.body)); assert.equal(result.body.status, 'recruited');
  assert.equal(s.aggregate(other), before);
  const denied = await s.call('/internal/native/crew-recruit-barracks', s.command([3, 1, 2, 0], other));
  assert.equal(denied.status, 200); assert.equal(denied.body.status, 'rejected'); assert.equal(s.aggregate(other), before);
  assert.equal((await s.login(other)).status, 200);
  const invalid = structuredClone(s.options); invalid.pool_service.accounts = ['11111111-1111-4111-8111-111111111111'];
  await assert.rejects(() => createIdentityBridge(invalid), /explicit owner subset\/policy/);
  s.complete({ owners: 2, opted_in: 1, legacy_second_unchanged: true, legacy_radioman: 'DENIED' });
});
