import test from 'node:test';
import assert from 'node:assert/strict';
import { fork } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { randomBytes } from 'node:crypto';
import { browser, freePort, testDirectory, removeTestDirectory } from './helpers.mjs';

test('Real process restart preserves profile, login, session and rate limit', { timeout: 45_000 }, async t => {
  const directory = testDirectory();
  const port = await freePort();
  const origin = `http://127.0.0.1:${port}`;
  const password = randomBytes(24).toString('base64url');
  let child;
  let output = '';
  async function start() {
    child = fork(fileURLToPath(new URL('../src/server.mjs', import.meta.url)), [], {
      env: { ...process.env, WEB_PORT: String(port), WEB_DATA_DIR: directory },
      stdio: ['ignore', 'pipe', 'pipe', 'ipc'], windowsHide: true,
    });
    await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error('Local process startup timed out')), 15_000);
      child.once('error', error => { clearTimeout(timeout); reject(error); });
      child.once('exit', code => { clearTimeout(timeout); reject(new Error(`Local process exited before readiness (${code})`)); });
      child.stderr.on('data', data => { output += data; });
      child.stdout.on('data', data => {
        output += data;
        if (String(data).includes('Web profile ready:')) { clearTimeout(timeout); resolve(); }
      });
    });
  }
  async function stop() {
    if (!child || child.exitCode !== null) return;
    await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => { child.kill(); reject(new Error('Local process shutdown timed out')); }, 10_000);
      child.once('exit', code => { clearTimeout(timeout); code === 0 ? resolve() : reject(new Error(`Unexpected exit (${code})`)); });
      child.send('shutdown');
    });
  }
  t.after(async () => { await stop(); removeTestDirectory(directory); });
  await start();
  const user = browser(origin);
  await user.get('/register');
  assert.equal((await user.post('/register', { email: 'restart@example.test', nickname: 'restart_user', display_name: 'До перезапуска', password, password_confirm: password })).status, 303);
  await user.get('/account');
  assert.equal((await user.post('/account/profile', { display_name: 'Сохранённый профиль', bio: 'Эта запись переживает завершение процесса' })).status, 303);
  const initial = (await user.get('/api/profile')).json().profile;
  const limited = browser(origin); await limited.get('/login');
  for (let i = 0; i < 5; i++) assert.equal((await limited.post('/login', { email: 'restart_limit@example.test', password })).status, 401);
  await stop();
  await start();
  const after = (await user.get('/api/profile')).json().profile;
  assert.deepEqual(after, initial);
  assert.equal(after.displayName, 'Сохранённый профиль');
  assert.equal((await limited.post('/login', { email: 'restart_limit@example.test', password })).status, 429);
  await user.get('/account');
  assert.equal((await user.post('/logout')).status, 303);
  await user.get('/login');
  assert.equal((await user.post('/login', { email: 'restart@example.test', password })).status, 303);
  assert.equal((await user.get('/api/profile')).json().profile.id, initial.id);
  assert.ok(!output.includes(password));
  assert.ok(!output.includes(user.cookie));
  assert.ok(!output.includes('restart_user'));
  await stop();
});
