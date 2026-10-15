/** Real loopback HTTP -> Python -> one isolated profile13 SQLite owner. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { createHash, randomUUID } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync, copyFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createIdentityBridge } from '../src/game-adapter.mjs';
import { hashPassword, token } from '../src/security.mjs';
import { CREW_POLICY_SHA256, TRANSFER_POLICY_SHA256, CROSS_CREW_POLICY_SHA256, ROSTER_CREW_POLICY_SHA256,
  PROGRESSION_CREW_POLICY_SHA256, DISMISSAL_CREW_POLICY_SHA256 } from '../src/p04d-crew.mjs';
import { BARRACKS_CREW_POLICY_SHA256 } from '../src/p04k-crew.mjs';
import { RESEARCH_POLICY_SHA256 } from '../src/p09e-research.mjs';
import { BATTLE_POLICY_SHA256 } from '../src/p08b-battle.mjs';
import { testDirectory, removeTestDirectory } from './helpers.mjs';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const BUNDLE = resolve(process.env.P04D_TEST_BUNDLE || join(ROOT, 'local/stands/p09e-main-01/source-bundle-05'));
const ORIGINAL = process.env.P04D_TEST_ORIGINAL || 'C:\\WoT_0.9.1_RU_0717_original';
const source = join(BUNDLE, 'content/fixtures/profile4/profile-input.json.blob');
const skip = !existsSync(source) ? 'NOT_RUN: verified profile4 portable source required' : false;
function db(path, callback) { const d = new DatabaseSync(path); try { return callback(d); } finally { d.close(); } }

test('P08B real HTTP reserves an owned tank, blocks garage writes, persists AP/results and fences restart', { skip, timeout: 120000 }, async t => {
  const directory = testDirectory(), seeded = join(directory, 'seed');
  const original = JSON.parse(readFileSync(source, 'utf8'));
  let bridge = null;
  t.after(async () => { if (bridge) await bridge.close(); removeTestDirectory(directory); });
  const prepare = spawnSync('python', ['-B', '-X', 'utf8', join(ROOT, 'tools/p09e_research_harness.py'),
    '--bundle', BUNDLE, '--original', ORIGINAL, '--out', seeded, '--seed-only'],
  { cwd: ROOT, encoding: 'utf8', windowsHide: true, timeout: 120000 });
  assert.equal(prepare.status, 0, prepare.stderr);
  const gameFile = join(seeded, 'game.sqlite'), identityFile = join(directory, 'identity.sqlite');
  const secret = token(), password = token(), email = 'p08b-isolated@example.test', passwordHash = await hashPassword(password);
  const nativePath = join(directory, 'native.json'), tokenFile = join(directory, 'identity.token');
  copyFileSync(join(BUNDLE, 'content/inputs/native-ms1.blob'), nativePath); writeFileSync(tokenFile, secret);
  db(identityFile, d => {
    d.exec('PRAGMA user_version=2; CREATE TABLE users(id TEXT PRIMARY KEY,username TEXT,display_nickname TEXT,email TEXT,password_hash TEXT,created_at INTEGER)');
    d.prepare('INSERT INTO users VALUES (?,?,?,?,?,?)').run(original.account_id, original.username.toLowerCase(), original.username,
      email, passwordHash, original.created_at_ms);
  });
  db(gameFile, d => d.prepare('INSERT INTO game_meta VALUES (?,?)').run('native_descriptors_sha256', createHash('sha256').update(readFileSync(nativePath)).digest('hex')));
  const python = spawnSync('python', ['-B', '-c', 'import sys;print(sys.executable)'], { encoding: 'utf8', windowsHide: true }).stdout.trim();
  const options = { version: 1, port: 0, web_database: identityFile, game_database: gameFile,
    fixture_root: join(directory, 'fixtures'), native_descriptors: nativePath, python_executable: python, token_file: tokenFile,
    ammunition_service: { version: 1, bundle_root: BUNDLE, original_root: ORIGINAL, account_id: original.account_id,
      grant: { grant_id: 'p09d-test-depot-v1', quantity_each: 100 } },
    crew_service: { version: 1, policy_sha256: CREW_POLICY_SHA256 },
    crew_transfer: { version: 1, policy_sha256: TRANSFER_POLICY_SHA256 },
    crew_cross_vehicle: { version: 1, policy_sha256: CROSS_CREW_POLICY_SHA256 },
    crew_roster_recruitment: { version: 1, policy_sha256: ROSTER_CREW_POLICY_SHA256 },
    crew_progression: { version: 1, policy_sha256: PROGRESSION_CREW_POLICY_SHA256 },
    crew_dismissal: { version: 1, policy_sha256: DISMISSAL_CREW_POLICY_SHA256 },
    crew_barracks_recruitment: { version: 1, policy_sha256: BARRACKS_CREW_POLICY_SHA256 },
    research_service: { version: 1, policy_sha256: RESEARCH_POLICY_SHA256 },
    battle_service: { version: 1, policy_sha256: BATTLE_POLICY_SHA256, accounts: [original.account_id] } };
  bridge = await createIdentityBridge(options);
  const profile = () => db(gameFile, d => JSON.parse(d.prepare('SELECT profile_json FROM game_profiles WHERE account_id=?').get(original.account_id).profile_json));
  const aggregate = () => db(gameFile, d => JSON.parse(d.prepare('SELECT snapshot_json FROM game_snapshot WHERE account_id=?').get(original.account_id).snapshot_json));
  const initial = profile(); assert.equal(initial.profile_version, 13);
  async function call(path, data, authorization = secret) {
    const response = await fetch(`http://127.0.0.1:${bridge.port}${path}`, { method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${authorization}` }, body: JSON.stringify(data) });
    return { status: response.status, body: await response.json() };
  }
  let serial = 0, run = randomUUID();
  const request = (operation, extra = {}) => ({ version: 1, operation, account_id: original.account_id,
    native_database_id: original.native_database_id, command_key: `p08b-http:${++serial}`,
    expected_revision: profile().snapshot_revision, run_id: run,
    ...(['admit', 'finish'].includes(operation) ? { battle_id: `${run}:9007199254740993`, native_inventory_id: 1 } : {}), ...extra });
  const mutate = async value => {
    const result = await call('/internal/native/battle', value);
    assert.equal(result.status, 200, JSON.stringify(result.body)); return result.body;
  };
  const login = await call('/internal/native/login', { email, password }); assert.equal(login.status, 200);
  const fresh = () => call('/internal/native/profile', { account_id: original.account_id, native_database_id: original.native_database_id });
  assert.equal((await mutate(request('inspect', { expected_revision: 0 }))).revision, initial.snapshot_revision);
  const open = await mutate(request('run_open')); assert.equal(open.status, 'ready');
  const admissionRequest = request('admit'), admitted = await mutate(admissionRequest);
  assert.equal(admitted.status, 'admitted'); assert.equal(admitted.reservation.frozen.ap_count, 20);
  assert.equal(admitted.reservation.battle_id, `${run}:9007199254740993`);
  assert.equal(aggregate().vehicles.filter(v => v.state === 'reserved').length, 1);
  const bound = await fresh(); assert.equal(bound.status, 200);
  const companion = JSON.parse(readFileSync(join(bound.body.fixture_dir, 'p08b-battle.json')));
  assert.equal(companion.policy_sha256, BATTLE_POLICY_SHA256);
  assert.equal(companion.capabilities[0].code, 'VEHICLE_RESERVED');
  assert.equal(companion.state_sha256, createHash('sha256').update(readFileSync(join(bound.body.fixture_dir, 'state.bin'))).digest('hex'));
  // Inspect the closed primitive protocol2 field directly; never unpickle
  // arbitrary objects or execute client code to check this wire projection.
  const reservedState = readFileSync(join(bound.body.fixture_dir, 'state.bin'));
  assert.ok(reservedState.length <= 32768);
  const lockKey = Buffer.from([0x55, 4, ...Buffer.from('lock')]);
  assert.ok(reservedState.includes(Buffer.concat([lockKey, Buffer.from([0x7d, 0x28, 0x4b, 1, 0x4b, 1, 0x75])])), 'inventory lock must encode {1: 1}');
  const captchaKey = Buffer.from('battlesTillCaptcha');
  assert.ok(reservedState.includes(Buffer.from([0x55, captchaKey.length, ...captchaKey, 0x4b, 1])), 'Full account state retains the explicit service CAPTCHA counter');
  const beforeGarage = JSON.stringify(aggregate());
  const garage = { account_id: original.account_id, native_database_id: original.native_database_id,
    expected_revision: profile().snapshot_revision, wire_revision: 1 };
  const operations = [
    ['/internal/native/research', { command: 201, arguments: [3329, 0, 0] }],
    ['/internal/native/ammo', { layout: [5, 1, 6, 2570, 19, 2826, 0, 3082, 0, 6, 0, 0, 0, 0, 0, 0] }],
    ['/internal/native/crew', { layout: [3, 1, 1, 0] }],
    ['/internal/native/crew-transfer', { layout: [1, 1, -1] }],
    ['/internal/native/crew-learn', { layout: [1, 6, 0] }],
    ['/internal/native/crew-dismiss', { layout: [1, 0, 0] }],
    ['/internal/native/crew-recruit-barracks', { layout: [3, 7169, 4, 0] }],
  ];
  for (const [path, extra] of operations) {
    const result = await call(path, { ...garage, command_key: `p08b-denied:${++serial}`, ...extra });
    assert.equal(result.status, 200, `${path}: ${JSON.stringify(result.body)}`);
    assert.equal(result.body.status, 'rejected'); assert.equal(result.body.result_code, -10);
    assert.equal(JSON.stringify(aggregate()), beforeGarage);
  }
  const finishRequest = request('finish', { reservation_id: admitted.reservation.reservation_id,
    remaining_ap: 17, terminal_hp: 0, reason: 'manual_leave' });
  const finished = await mutate(finishRequest); assert.equal(finished.status, 'finished');
  assert.deepEqual(finished.reservation.result, { reason: 'manual_leave', remaining_ap: 17, consumed_ap: 3,
    terminal_hp: 0, destroyed: true, repaired_hp: 90, credits: 0, xp: 0 });
  assert.equal(profile().inventory[0].ammunition_count, 17); assert.equal(profile().inventory[0].health, 90);
  assert.deepEqual(profile().resources, initial.resources);
  const returned = await fresh(); assert.equal(returned.status, 200);
  const returnedState = readFileSync(join(returned.body.fixture_dir, 'state.bin'));
  const lockPosition = returnedState.indexOf(lockKey); assert.ok(lockPosition >= 0);
  assert.equal(returnedState[lockPosition + lockKey.length], 0x7d);
  assert.notEqual(returnedState[lockPosition + lockKey.length + 1], 0x28, 'Available state must encode an empty lock dictionary');
  const unchanged = JSON.stringify(aggregate());
  assert.deepEqual(await mutate(finishRequest), { ...finished, replayed: true });
  assert.equal(JSON.stringify(aggregate()), unchanged);
  const secondRequest = request('admit', { battle_id: `${run}:9007199254740994` });
  const second = await mutate(secondRequest); assert.equal(second.reservation.frozen.ap_count, 17);
  await bridge.close(); bridge = await createIdentityBridge(options);
  assert.equal(aggregate().vehicles.filter(v => v.state === 'reserved').length, 1, 'Bridge restart must not guess a gateway crash');
  assert.deepEqual(await mutate(secondRequest), { ...second, replayed: true });
  const oldRun = run; run = randomUUID();
  const recovered = await mutate(request('run_open')); assert.equal(recovered.reservation.status, 'aborted_restart');
  assert.equal(recovered.reservation.run_id, oldRun);
  assert.deepEqual(recovered.reservation.result, { reason: 'aborted_restart', remaining_ap: 17, consumed_ap: 0,
    terminal_hp: null, destroyed: null, repaired_hp: 90, credits: 0, xp: 0 });
  assert.equal(profile().inventory[0].ammunition_count, 17);
  assert.equal(aggregate().vehicles.filter(v => v.state === 'reserved').length, 0);
  assert.equal((await mutate(secondRequest)).code, 'RUN_FENCED');
  assert.equal((await call('/internal/native/battle', request('inspect'), token())).status, 403);
  assert.equal((await call('/internal/native/battle', request('inspect', { account_id: randomUUID() }))).status, 403);
  assert.equal((await call('/internal/native/profile', { account_id: original.account_id, native_database_id: original.native_database_id + 1 })).status, 403);
  assert.equal((await fresh()).status, 200);
});
