/** Canonical identity entrypoint boundaries; not native client compatibility. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { spawn, spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync, copyFileSync, mkdirSync, mkdtempSync, rmSync } from 'node:fs';
import { join, resolve, relative, isAbsolute } from 'node:path';
import { fileURLToPath } from 'node:url';
import { once } from 'node:events';
import { readConfiguration, startIdentity } from '../server/identity/service.mjs';
import { openStore } from '../web/src/store.mjs';
import { token, hashPassword, nicknameField } from '../web/src/security.mjs';

const ROOT = fileURLToPath(new URL('../', import.meta.url));
const TEST_ROOT = resolve(ROOT, 'local/web/tests');
const NATIVE = resolve(ROOT, 'local/evidence/20261004-p02-hangar/native-descriptors.json');
const CLI = resolve(ROOT, 'server/identity/service.mjs');
const sha = bytes => createHash('sha256').update(bytes).digest('hex');

function directory(t) {
  mkdirSync(TEST_ROOT, { recursive: true });
  const path = mkdtempSync(join(TEST_ROOT, 'run-identity-'));
  t.after(() => {
    const rel = relative(TEST_ROOT, path);
    assert.ok(rel.startsWith('run-identity-') && !rel.includes('..') && !isAbsolute(rel));
    rmSync(path, { recursive: true, force: true });
  });
  return path;
}
function users(path) {
  const db = new DatabaseSync(path, { readOnly: true });
  try { return db.prepare('SELECT * FROM users ORDER BY id').all().map(row => ({ ...row })); }
  finally { db.close(); }
}
function profileCount(path) {
  const db = new DatabaseSync(path, { readOnly: true });
  try { return db.prepare('SELECT COUNT(*) AS count FROM game_profiles').get().count; }
  finally { db.close(); }
}
async function fixture(t) {
  const path = directory(t);
  const source = readFileSync(NATIVE);
  const native = JSON.parse(source.toString('utf8'));
  assert.equal(native.vehicle.type_name, 'ussr:MS-1');
  assert.equal(native.vehicle.max_health, 90);
  const nativePath = join(path, 'native-descriptors.json');
  copyFileSync(NATIVE, nativePath);
  assert.equal(sha(readFileSync(nativePath)), sha(source));
  t.after(() => assert.equal(sha(readFileSync(NATIVE)), sha(source), 'verified descriptor source must remain unchanged'));
  const python = spawnSync('python', ['-B', '-X', 'utf8', '-c', 'import sys; print(sys.executable)'],
    { encoding: 'utf8', windowsHide: true, timeout: 5000 });
  assert.equal(python.status, 0, 'real Python executable must be discoverable');
  const secret = token();
  const tokenFile = join(path, 'identity.token');
  writeFileSync(tokenFile, secret, { flag: 'wx', mode: 0o600 });
  const options = { version: 1, port: 0, web_database: join(path, 'portal.sqlite'),
    game_database: join(path, 'game.sqlite'), fixture_root: join(path, 'fixtures'),
    native_descriptors: nativePath, python_executable: python.stdout.trim(), token_file: tokenFile };
  const store = openStore(options.web_database);
  try {
    assert.equal(store.db.prepare('PRAGMA user_version').get().user_version, 2);
    store.createUser({ nickname: nicknameField('Проверка_Ёж'), email: 'identity-boundary@example.test',
      displayName: 'Проверка', passwordHash: await hashPassword(token()) });
  } finally { store.close(); }
  const configPath = join(path, 'bridge.json');
  writeFileSync(configPath, JSON.stringify(options), { flag: 'wx' });
  return { path, options, configPath, secret, beforeUsers: users(options.web_database) };
}
async function request(origin, secret, { email = 'identity-boundary@example.test', password = token() } = {}) {
  const body = JSON.stringify({ email, password });
  const response = await fetch(`${origin}/internal/native/login`, {
    method: 'POST', redirect: 'error', signal: AbortSignal.timeout(5000),
    headers: { Authorization: `Bearer ${secret}`, 'Content-Type': 'application/json',
      'Content-Length': Buffer.byteLength(body) }, body });
  return { status: response.status, body: await response.json() };
}

test('canonical identity configuration refuses outside paths, directories, oversize and invalid JSON', t => {
  const path = directory(t);
  assert.throws(() => readConfiguration(CLI), /local/);
  assert.throws(() => readConfiguration(path), /bound/);
  const oversize = join(path, 'oversize.json');
  writeFileSync(oversize, Buffer.alloc(8193, 32), { flag: 'wx' });
  assert.throws(() => readConfiguration(oversize), /bound/);
  const invalid = join(path, 'invalid.json');
  writeFileSync(invalid, '{', { flag: 'wx' });
  assert.throws(() => readConfiguration(invalid), SyntaxError);
  const valid = join(path, 'valid.json');
  const input = { version: 1, note: 'data only; schema is checked by startIdentity' };
  writeFileSync(valid, JSON.stringify(input), { flag: 'wx' });
  assert.deepEqual(readConfiguration(valid), input);
});

test('canonical identity real HTTP readiness and rejected authentication preserve shared users', async t => {
  const state = await fixture(t);
  assert.deepEqual(readConfiguration(state.configPath), state.options);
  const bridge = await startIdentity(readConfiguration(state.configPath));
  t.after(async () => { await bridge.close(); });
  const address = bridge.server.address();
  assert.equal(address.address, '127.0.0.1');
  assert.ok(address.port > 0);
  const origin = `http://127.0.0.1:${address.port}`;
  const health = await fetch(`${origin}/health`, { signal: AbortSignal.timeout(5000) });
  assert.equal(health.status, 200);
  assert.deepEqual(await health.json(), { status: 'ok', scope: 'game-identity-bridge' });
  assert.deepEqual(await request(origin, token()), { status: 403, body: { error: 'forbidden' } });
  const wrong = await request(origin, state.secret);
  const unknown = await request(origin, state.secret, { email: 'unknown@example.test' });
  assert.deepEqual(wrong, { status: 401, body: { error: 'invalid_credentials' } });
  assert.deepEqual(unknown, wrong);
  assert.equal(profileCount(state.options.game_database), 0, 'failed login must not create game profiles');
  assert.deepEqual(users(state.options.web_database), state.beforeUsers, 'bridge must not mutate users or password hashes');
  await bridge.close();
  await assert.rejects(fetch(`${origin}/health`, { signal: AbortSignal.timeout(1000) }), TypeError);
});

test('invalid canonical CLI exits unsuccessfully without publishing readiness', t => {
  const path = directory(t);
  const config = join(path, 'invalid.json');
  writeFileSync(config, '{', { flag: 'wx' });
  for (const args of [['--config', config], []]) {
    const child = spawnSync(process.execPath, [CLI, ...args], { cwd: ROOT, encoding: 'utf8',
      windowsHide: true, timeout: 5000, maxBuffer: 16384 });
    assert.equal(child.status, 1);
    assert.doesNotMatch(child.stdout, /game_bridge_ready/);
    assert.match(child.stderr, /game_bridge_start_failed: configuration_or_storage/);
  }
});

test('canonical CLI starts on its own ephemeral endpoint and shuts down through its own IPC', async t => {
  const state = await fixture(t);
  const child = spawn(process.execPath, [CLI, '--config', state.configPath], {
    cwd: ROOT, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe', 'ipc'] });
  let stdout = '', stderr = '';
  child.stdout.setEncoding('utf8'); child.stderr.setEncoding('utf8');
  child.stderr.on('data', data => { stderr += data; assert.ok(stderr.length <= 16384); });
  const exited = once(child, 'exit');
  t.after(async () => {
    if (child.exitCode === null && child.signalCode === null) { child.kill(); await exited; }
  });
  const ready = await new Promise((done, fail) => {
    const timer = setTimeout(() => fail(new Error('Owned identity CLI readiness timed out')), 5000);
    child.once('error', error => { clearTimeout(timer); fail(error); });
    child.once('exit', () => { clearTimeout(timer); fail(new Error('Owned identity CLI exited before readiness')); });
    child.stdout.on('data', data => {
      stdout += data;
      if (stdout.length > 16384) { clearTimeout(timer); fail(new Error('Owned CLI output exceeded bound')); return; }
      for (const line of stdout.split('\n')) {
        try {
          const value = JSON.parse(line);
          if (value.event === 'game_bridge_ready') { clearTimeout(timer); done(value); return; }
        } catch { /* incomplete or non-JSON line; bounded until readiness or timeout */ }
      }
    });
  });
  assert.equal(ready.host, '127.0.0.1');
  assert.equal(ready.pid, child.pid);
  assert.ok(Number.isInteger(ready.port) && ready.port > 0);
  const response = await fetch(`http://127.0.0.1:${ready.port}/health`, { signal: AbortSignal.timeout(5000) });
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { status: 'ok', scope: 'game-identity-bridge' });
  assert.equal(profileCount(state.options.game_database), 0);
  assert.deepEqual(users(state.options.web_database), state.beforeUsers);
  // The owner closes its IPC channel after delivering shutdown. A connected
  // channel with a message listener keeps Node alive even after HTTP closes.
  await new Promise((done, fail) => child.send('shutdown', error => error ? fail(error) : done()));
  child.disconnect();
  const timeout = new Promise((_, fail) => {
    const timer = setTimeout(() => fail(new Error('Owned CLI shutdown timed out')), 5000);
    exited.finally(() => clearTimeout(timer));
  });
  const [exitCode, signal] = await Promise.race([exited, timeout]);
  assert.equal(exitCode, 0);
  assert.equal(signal, null);
  await assert.rejects(fetch(`http://127.0.0.1:${ready.port}/health`, { signal: AbortSignal.timeout(1000) }), TypeError);
  assert.doesNotMatch(stdout + stderr, /identity-boundary@example\.test|password_hash|Bearer /);
});
