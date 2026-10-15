/** Real isolated HTTP -> Python -> same SQLite; original client remains NOT_RUN. */
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
import { CREW_POLICY_SHA256, TRANSFER_POLICY_SHA256, CROSS_CREW_POLICY_SHA256, ROSTER_CREW_POLICY_SHA256,
  PROGRESSION_CREW_POLICY_SHA256, DISMISSAL_CREW_POLICY_SHA256 } from '../src/p04d-crew.mjs';
import { BARRACKS_CREW_POLICY_SHA256 } from '../src/p04k-crew.mjs';
import { RESEARCH_POLICY_SHA256 } from '../src/p09e-research.mjs';
import { testDirectory, removeTestDirectory } from './helpers.mjs';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const BUNDLE = resolve(process.env.P04D_TEST_BUNDLE || join(ROOT, 'local/p04d/source-bundle-05'));
const ORIGINAL = process.env.P04D_TEST_ORIGINAL || 'C:\\WoT_0.9.1_RU_0717_original';
const fixture = join(BUNDLE, 'content/fixtures/profile4/profile-input.json.blob');
const skip = !existsSync(fixture) ? 'NOT_RUN: verified portable #717 source required' : false;
function db(path, callback) { const d = new DatabaseSync(path); try { return callback(d); } finally { d.close(); } }

test('P09E authenticated HTTP research, purchase, install, zero prices and restart replay', { skip }, async t => {
  const directory = testDirectory(), seeded = join(directory, 'seed');
  const original = JSON.parse(readFileSync(fixture, 'utf8'));
  let bridge = null;
  t.after(async () => { if (bridge) await bridge.close(); removeTestDirectory(directory); });
  const prepare = spawnSync('python', ['-B', '-X', 'utf8', join(ROOT, 'tools/p09e_research_harness.py'),
    '--bundle', BUNDLE, '--original', ORIGINAL, '--out', seeded, '--seed-only'],
  { cwd: ROOT, encoding: 'utf8', windowsHide: true, timeout: 120000 });
  assert.equal(prepare.status, 0, prepare.stderr);
  const gameFile = join(seeded, 'game.sqlite'), identityFile = join(directory, 'identity.sqlite');
  const secret = token(), password = token(), email = 'p09e-isolated@example.test', passwordHash = await hashPassword(password);
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
    research_service: { version: 1, policy_sha256: RESEARCH_POLICY_SHA256 } };
  bridge = await createIdentityBridge(options);
  const profile = () => db(gameFile, d => JSON.parse(d.prepare('SELECT profile_json FROM game_profiles WHERE account_id=?').get(original.account_id).profile_json));
  assert.equal(profile().profile_version, 13);
  async function call(path, data, authorization = secret) {
    const response = await fetch(`http://127.0.0.1:${bridge.port}${path}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${authorization}` }, body: JSON.stringify(data),
    }); return { status: response.status, body: await response.json() };
  }
  assert.equal((await call('/internal/native/login', { email, password })).status, 200);
  const read = () => createGameReader({ origin: `http://127.0.0.1:${bridge.port}`, tokenFile })(original.account_id);
  const initial = await read(); assert.equal(initial.state, 'ready');
  const receipts = [];
  for (const [command, args] of [[201, [3329, 0, 0]], [302, [5, 6914, 1, 0]], [101, [1, 6914, 0]],
    [201, [3329, 1, 0]], [301, [5, 3841, 0, -1]]]) {
    const request = { account_id: original.account_id, native_database_id: original.native_database_id,
      command_key: `p09e-http:${receipts.length}`, expected_revision: profile().snapshot_revision,
      wire_revision: receipts.length + 1, command, arguments: args };
    const result = await call('/internal/native/research', request);
    assert.equal(result.status, 200, JSON.stringify(result.body));
    assert.equal(result.body.status, 'researched', JSON.stringify(request));
    receipts.push({ request, result });
  }
  const after = profile(); assert.equal(after.inventory.length, 3);
  assert.deepEqual(after.resources, original.resources);
  assert.equal((await read()).inventory.length, 3);
  const garageRequest = { account_id: original.account_id, native_database_id: original.native_database_id,
    command_key: 'p09e-old-garage-rejection', expected_revision: after.snapshot_revision, wire_revision: 6,
    layout: [999, -1, 0] };
  const rejected = await call('/internal/native/crew-transfer', garageRequest);
  assert.equal(rejected.status, 200, JSON.stringify(rejected.body));
  assert.equal(rejected.body.status, 'rejected');
  assert.equal(rejected.body.result_code, -10);
  assert.deepEqual(profile(), after);
  // Accepted P04K crew operations stay on the same writer in profile13.
  const barracks = await call('/internal/native/crew-recruit-barracks', { account_id: original.account_id,
    native_database_id: original.native_database_id, command_key: 'p09e-barracks', expected_revision: after.snapshot_revision,
    wire_revision: 6, layout: [3, 7169, 4, 0] });
  assert.equal(barracks.status, 200, JSON.stringify(barracks.body));
  assert.equal(barracks.body.status, 'recruited', JSON.stringify(barracks.body));
  const recruited = profile(); assert.equal(recruited.profile_version, 13);
  assert.equal(recruited.inventory.length, 3); assert.equal(recruited.crew.length, after.crew.length + 1);
  for (const request of [{ ...receipts[0].request, account_id: '00000000-0000-0000-0000-000000000000' },
    { ...receipts[0].request, arguments: [3329, 0, 0, 0] }]) {
    assert.notEqual((await call('/internal/native/research', request)).status, 200);
  }
  assert.equal((await call('/internal/native/research', receipts[0].request, token())).status, 403);
  await bridge.close(); bridge = await createIdentityBridge(options);
  for (const { request, result } of receipts) {
    assert.deepEqual(await call('/internal/native/research', request), { status: 200, body: { ...result.body, replayed: true } });
  }
  assert.deepEqual(profile(), recruited);
  assert.equal((await call('/internal/native/login', { email, password })).status, 200);
  assert.equal((await read()).researchService.battle, false);
});
