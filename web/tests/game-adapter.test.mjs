import test from 'node:test';
import assert from 'node:assert/strict';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { DatabaseSync } from 'node:sqlite';
import { request } from 'node:http';
import { createApp } from '../src/app.mjs';
import { createIdentityBridge, createGameReader } from '../src/game-adapter.mjs';
import { token } from '../src/security.mjs';
import { browser, freePort, testDirectory, removeTestDirectory } from './helpers.mjs';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const NATIVE = resolve(ROOT, 'local/evidence/20261004-p02-hangar/native-descriptors.json');
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const jsonFile = path => JSON.parse(readFileSync(path, 'utf8'));
const getPair = (tree, key) => tree.pairs.find(([name]) => name === key)[1];

test('Unified real HTTP registration, shared credentials and persistent account data', {
  skip: !existsSync(NATIVE) ? 'NOT_RUN: verified local #717 descriptors are required' : false,
}, async t => {
  const directory = testDirectory();
  const identityFile = join(directory, 'portal.sqlite');
  const gameFile = join(directory, 'game.sqlite');
  const tokenFile = join(directory, 'identity.token');
  const secret = token();
  writeFileSync(tokenFile, secret, { flag: 'wx', mode: 0o600 });
  const pythonProbe = spawnSync('python', ['-c', 'import sys; print(sys.executable)'], { encoding: 'utf8', timeout: 5000, windowsHide: true });
  assert.equal(pythonProbe.status, 0, 'Python 3 must be installed for the real payload generator');
  const python = pythonProbe.stdout.trim();
  const origin = `http://127.0.0.1:${await freePort()}`;
  const bridgePort = await freePort();
  const bridgeOrigin = `http://127.0.0.1:${bridgePort}`;
  const runtime = await createApp({ databasePath: identityFile, origin,
    gameBridgeOrigin: bridgeOrigin, gameBridgeTokenFile: tokenFile });
  const server = runtime.app.listen(Number(new URL(origin).port), '127.0.0.1');
  await new Promise(done => server.once('listening', done));
  const options = { version: 1, port: bridgePort, web_database: identityFile, game_database: gameFile,
    fixture_root: join(directory, 'fixtures'), native_descriptors: NATIVE,
    python_executable: python, token_file: tokenFile };
  let bridge = await createIdentityBridge(options);
  t.after(async () => {
    await bridge.close();
    await new Promise(done => server.close(done)); runtime.close(); removeTestDirectory(directory);
  });
  const alice = browser(origin), bob = browser(origin), guest = browser(origin);
  const passwordA = token(), passwordB = `  пароль_${token()}_żółw  `;
  let idA, idB, loginA, loginB, firstHashes;
  async function internal(path, { method = 'GET', body, authorization = secret, headers = {} } = {}) {
    const bytes = body === undefined ? undefined : (typeof body === 'string' ? body : JSON.stringify(body));
    const response = await fetch(bridgeOrigin + path, { method, redirect: 'error', signal: AbortSignal.timeout(6000),
      headers: { Authorization: `Bearer ${authorization}`, ...(bytes === undefined ? {} : {
        'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(bytes),
      }), ...headers }, body: bytes });
    const text = await response.text();
    return { status: response.status, text, body: JSON.parse(text) };
  }
  const authenticate = (email, password) => internal('/internal/native/login', { method: 'POST', body: { email, password } });
  const profileCount = () => {
    const db = new DatabaseSync(gameFile, { readOnly: true });
    const result = db.prepare('SELECT COUNT(*) AS n FROM game_profiles').get().n;
    db.close(); return result;
  };

  await t.test('readiness and real web registrations create one shared UUID each', async () => {
    const health = await fetch(`${bridgeOrigin}/health`);
    assert.deepEqual(await health.json(), { status: 'ok', scope: 'game-identity-bridge' });
    for (const [client, email, nickname, display, password] of [[alice, 'unified_alpha@example.test', 'unified_alpha', 'Альфа', passwordA], [bob, 'unified_beta@example.test', 'Танкист_Ёж', 'Бета', passwordB]]) {
      assert.equal((await client.get('/register')).status, 200);
      assert.equal((await client.post('/register', { email, nickname, display_name: display, password, password_confirm: password })).status, 303);
    }
    idA = (await alice.get('/api/profile')).json().profile.id;
    idB = (await bob.get('/api/profile')).json().profile.id;
    assert.notEqual(idA, idB);
    assert.equal(profileCount(), 0, 'registration alone must not fabricate a played game profile');
    assert.equal((await alice.get('/api/game')).json().state, 'unlinked');
    assert.match((await alice.get('/account')).html, /Аккаунт готов к входу/);
    assert.equal((await guest.get('/api/game')).status, 401);
  });
  await t.test('wrong and unknown credentials return the same response and create no profile', async () => {
    const wrong = await authenticate('unified_alpha@example.test', 'wrong-but-long-enough-password');
    const unknown = await authenticate('unified_unknown@example.test', passwordA);
    assert.equal(wrong.status, 401); assert.equal(unknown.status, 401);
    assert.deepEqual(wrong.body, { error: 'invalid_credentials' });
    assert.deepEqual(wrong.body, unknown.body);
    assert.equal(profileCount(), 0);
    assert.ok(!wrong.text.includes(idA) && !wrong.text.includes(passwordA));
  });
  await t.test('native bridge verifies the exact existing web hashes and produces actual bounded payloads', async () => {
    const before = runtime.store.db.prepare('SELECT * FROM users ORDER BY id').all();
    const a = await authenticate('unified_alpha@example.test', passwordA);
    assert.equal(a.status, 200, a.text);
    const b = await authenticate('unified_beta@example.test', passwordB);
    assert.equal(b.status, 200, b.text);
    loginA = a.body; loginB = b.body;
    assert.deepEqual(Object.keys(loginA).sort(), ['account_id', 'fixture_dir', 'name', 'native_database_id']);
    assert.equal(loginA.account_id, idA); assert.equal(loginB.account_id, idB);
    assert.equal(loginA.name, 'unified_alpha'); assert.equal(loginB.name, 'Танкист_Ёж');
    assert.notEqual(loginA.native_database_id, loginB.native_database_id);
    assert.notEqual(loginA.fixture_dir, loginB.fixture_dir);
    assert.equal(profileCount(), 2);
    assert.ok(JSON.stringify(runtime.store.db.prepare('SELECT * FROM users ORDER BY id').all()) === JSON.stringify(before),
      'bridge must not modify users, hashes, created_at or last_login');
    firstHashes = {};
    for (const value of [loginA, loginB]) {
      const manifest = jsonFile(join(value.fixture_dir, 'manifest.json'));
      const compat = jsonFile(join(value.fixture_dir, 'compatibility.json'));
      assert.equal(manifest.account_id, value.account_id);
      assert.equal(manifest.profile_source.file, 'profile-input.json');
      assert.equal(manifest.profile_source.relative_to, 'fixture_directory');
      assert.equal(manifest.profile_source.sha256, sha(readFileSync(join(value.fixture_dir, 'profile-input.json'))));
      assert.equal(compat.account_id, value.account_id);
      assert.equal(compat.client_name, value.name);
      assert.equal(compat.native_database_id, value.native_database_id);
      assert.equal(manifest.compatibility_catalog_revision, 2);
      assert.equal(compat.compatibility_catalog_revision, 2);
      assert.equal(value.fixture_dir, join(options.fixture_root, value.account_id, 'r1-catalog2'));
      assert.deepEqual(jsonFile(join(value.fixture_dir, 'catalog-migration.json')),
        { version: 1, catalog_revision: 2, previous: null });
      const catalog = getPair(jsonFile(join(value.fixture_dir, 'payloads.json'))['shop.bin'], 'items');
      assert.deepEqual(getPair(catalog, 'itemPrices').pairs.map(([id]) => id).sort((a,b) => a-b),
        [7, 3329, 3589, 5891, 5892, 6658]);
      for (const file of ['state.bin', 'shop.bin', 'dossier.bin']) {
        const bytes = readFileSync(join(value.fixture_dir, file));
        const row = manifest.files.find(x => x.file === file);
        assert.ok(bytes.length <= 16384); assert.equal(row.bytes, bytes.length); assert.equal(row.sha256, sha(bytes));
        firstHashes[value.account_id + '/' + file] = sha(bytes);
      }
    }
  });
  await t.test('fresh native dossier creation time comes from registration, other bytes remain original zero-battle data', () => {
    const original = Buffer.from(jsonFile(NATIVE).account_dossier_hex, 'hex');
    for (const login of [loginA, loginB]) {
      const payloads = jsonFile(join(login.fixture_dir, 'payloads.json'));
      const dossier = Buffer.from(getPair(getPair(payloads['state.bin'], 'stats'), 'dossier').bytes_hex, 'hex');
      assert.equal(dossier.length, 88);
      assert.deepEqual(dossier.subarray(0, 70), original.subarray(0, 70));
      assert.deepEqual(dossier.subarray(74), original.subarray(74));
      assert.ok(dossier.subarray(74).every(x => x === 0));
      assert.equal(dossier.readUInt32LE(70), Math.floor(runtime.store.profile(login.account_id).created_at / 1000));
      assert.equal(getPair(getPair(payloads['state.bin'], 'stats'), 'credits'), 100000);
      const snapshot = jsonFile(join(login.fixture_dir, 'fixture.json'));
      assert.deepEqual(snapshot.statistics, { battles: 0, wins: 0, losses: 0, draws: 0 });
      assert.equal(snapshot.inventory[0].inventory_id, `${login.account_id}:starter-vehicle-v1`);
    }
  });
  await t.test('own website overview matches game state and ignores another account ID supplied by browser', async () => {
    const first = (await alice.get(`/api/game?account_id=${idB}`)).json();
    const second = (await bob.get(`/api/game?account_id=${idA}`)).json();
    assert.equal(first.state, 'ready'); assert.equal(second.state, 'ready');
    assert.equal(first.account.accountId, idA); assert.equal(second.account.accountId, idB);
    assert.equal(first.account.nickname, loginA.name); assert.equal(second.account.nickname, loginB.name);
    assert.deepEqual(first.resources, { credits: 100000, gold: 0, freeXP: 0 });
    assert.deepEqual(first.statistics, { battles: 0, wins: 0, losses: 0, draws: 0 });
    assert.equal(first.inventory[0].inventoryItemId, `${idA}:starter-vehicle-v1`);
    assert.ok(!JSON.stringify(first).includes(idB));
    const account = await alice.get('/account');
    assert.equal(account.status, 200); assert.match(account.html, /Тестовый профиль/);
    assert.match(account.html, /МС-1/); assert.match(account.html, /Бои: 0/);
    assert.equal((await alice.post('/api/game', { credits: '999999' })).status, 404);
  });
  await t.test('same exact credentials log in through normal website forms, including Unicode and spaces', async () => {
    const a = browser(origin), b = browser(origin);
    for (const [client, email, password, id] of [[a, 'unified_alpha@example.test', passwordA, idA], [b, 'unified_beta@example.test', passwordB, idB]]) {
      assert.equal((await client.get('/login')).status, 200);
      assert.equal((await client.post('/login', { email, password })).status, 303);
      assert.equal((await client.get('/api/profile')).json().profile.id, id);
      assert.equal((await client.get('/api/game')).json().account.accountId, id);
    }
    assert.equal((await authenticate('unified_beta@example.test', passwordB.trim())).status, 401, 'password whitespace is significant');
  });
  await t.test('bridge rejects unauthorized, cross-origin, malformed and excessive input', async () => {
    assert.equal((await internal('/internal/accounts/' + idA + '/overview', { authorization: token() })).status, 403);
    assert.equal((await internal('/internal/accounts/' + idA + '/overview', { headers: { Origin: origin } })).status, 403);
    assert.equal((await internal('/internal/native/login', { method: 'POST', body: '{' })).status, 413);
    assert.equal((await internal('/internal/native/login', { method: 'POST', body: '[]' })).status, 400);
    assert.equal((await internal('/internal/native/login', { method: 'POST', body: { email: 'unified_alpha@example.test', password: passwordA, id: idB } })).status, 400);
    assert.equal((await internal('/internal/native/login', { method: 'POST', body: { username: 'unified_alpha', password: passwordA } })).status, 400);
    assert.equal((await authenticate('unified_alpha', passwordA)).status, 401);
    assert.equal((await internal('/internal/native/login', { method: 'POST', body: 'x'.repeat(2049) })).status, 413);
    const forged = await new Promise((done, fail) => {
      const req = request(bridgeOrigin + '/health', { headers: { Host: 'external.invalid' } }, res => { res.resume(); res.once('end', () => done(res.statusCode)); });
      req.once('error', fail); req.end();
    });
    assert.equal(forged, 403);
    assert.equal(profileCount(), 2);
  });
  await t.test('bounded parallel password verification returns explicit busy without extra accounts', async () => {
    const attempts = await Promise.all(Array.from({ length: 6 }, (_, i) => authenticate(`missing_parallel_${i}@example.test`, passwordA)));
    assert.ok(attempts.every(x => [401, 503].includes(x.status)));
    assert.ok(attempts.some(x => x.status === 503));
    assert.equal(profileCount(), 2);
  });
  await t.test('bridge restart preserves UUID mapping, resources, native IDs and immutable payload bytes', async () => {
    await bridge.close();
    bridge = await createIdentityBridge(options);
    for (const [before, password] of [[loginA, passwordA], [loginB, passwordB]]) {
      const after = await authenticate(before.account_id === idA ? 'unified_alpha@example.test' : 'unified_beta@example.test', password);
      assert.equal(after.status, 200); assert.deepEqual(after.body, before);
      for (const file of ['state.bin', 'shop.bin', 'dossier.bin']) {
        assert.equal(sha(readFileSync(join(after.body.fixture_dir, file))), firstHashes[before.account_id + '/' + file]);
      }
    }
  });
  await t.test('stopped bridge becomes unavailable, never ready with invented data', async () => {
    await bridge.close();
    const value = await createGameReader({ origin: bridgeOrigin, tokenFile })(idA);
    assert.equal(value.state, 'unavailable'); assert.equal(value.account, null); assert.equal(value.inventory, null);
    assert.equal((await alice.get('/api/game')).json().state, 'unavailable');
    assert.match((await alice.get('/account')).html, /Временно недоступно/);
  });
});
