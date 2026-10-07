import test from 'node:test';
import assert from 'node:assert/strict';
import { join } from 'node:path';
import { randomBytes } from 'node:crypto';
import { request } from 'node:http';
import { createApp } from '../src/app.mjs';
import { browser, freePort, testDirectory, removeTestDirectory } from './helpers.mjs';

test('Local HTTP profile lifecycle and security boundaries', async t => {
  const directory = testDirectory();
  const origin = `http://127.0.0.1:${await freePort()}`;
  let stamp = Date.now();
  const runtime = await createApp({ databasePath: join(directory, 'portal.sqlite'), origin, now: () => stamp });
  const server = runtime.app.listen(Number(new URL(origin).port), '127.0.0.1');
  await new Promise(resolve => server.once('listening', resolve));
  t.after(async () => { await new Promise(resolve => server.close(resolve)); runtime.close(); removeTestDirectory(directory); });
  const alice = browser(origin);
  const guest = browser(origin);
  const password = randomBytes(24).toString('base64url');
  let userId, authenticatedCookie, anonymousCookie;

  await t.test('home renders; anonymous HTML and API access are denied', async () => {
    const home = await guest.get('/');
    assert.equal(home.status, 200);
    assert.match(home.html, /СТАЛЬНОЙ/);
    assert.match(home.html, /Игровая сессия недоступна/);
    assert.equal((await guest.get('/account')).headers.get('location'), '/login?required=1');
    assert.equal((await guest.get('/api/profile')).status, 401);
    assert.equal((await guest.get('/api/game')).status, 401);
    assert.equal((await guest.get('/assets/site.css')).status, 200);
  });
  await t.test('security headers and protected host/origin boundaries', async () => {
    const home = await guest.get('/');
    assert.equal(home.headers.get('cache-control'), 'no-store');
    assert.match(home.headers.get('content-security-policy'), /script-src 'none'/);
    assert.match(home.headers.get('content-security-policy'), /frame-ancestors 'none'/);
    assert.equal(home.headers.get('x-content-type-options'), 'nosniff');
    assert.equal(home.headers.get('x-powered-by'), null);
    assert.equal(home.headers.get('referrer-policy'), 'same-origin');
    // Fetch owns Host; use the raw HTTP client so the forged header is really sent.
    const forgedHostStatus = await new Promise((resolve, reject) => {
      const req = request(origin, { headers: { Host: 'untrusted.invalid' } }, response => {
        response.resume(); response.once('end', () => resolve(response.statusCode));
      });
      req.once('error', reject); req.end();
    });
    assert.equal(forgedHostStatus, 400);
    assert.equal((await guest.request('/', { headers: { 'Sec-Fetch-Site': 'cross-site' } })).status, 403);
  });
  await t.test('registration form creates HttpOnly SameSite session, no password echo', async () => {
    const result = await alice.get('/register');
    assert.equal(result.status, 200);
    assert.match(result.headers.get('set-cookie'), /HttpOnly/);
    assert.match(result.headers.get('set-cookie'), /SameSite=Strict/);
    assert.doesNotMatch(result.headers.get('set-cookie'), /Domain=/);
    assert.equal(alice.csrf.length, 43);
    anonymousCookie = alice.cookie;
    const invalid = await alice.post('/register', { email: 'invalid', nickname: 'bad!', display_name: 'A', password: 'short', password_confirm: 'other' });
    assert.equal(invalid.status, 422);
    assert.match(invalid.html, /aria-invalid=true/);
    assert.doesNotMatch(invalid.html, /value="short"/);
  });
  await t.test('CSRF absent, wrong token and wrong origin are rejected', async () => {
    assert.equal((await guest.post('/register', { csrf: '', username: 'csrf_test' })).status, 403);
    assert.equal((await alice.post('/register', { csrf: 'x'.repeat(43) })).status, 403);
    assert.equal((await alice.post('/register', {}, { Origin: 'http://untrusted.invalid' })).status, 403);
  });
  await t.test('registers real SQLite profile and rotates anonymous session', async () => {
    const result = await alice.post('/register', { email: 'Alpha@Example.Test', nickname: 'Test_Alpha', display_name: 'Тест Альфа', password, password_confirm: password });
    assert.equal(result.status, 303);
    assert.equal(result.headers.get('location'), '/account?welcome=1');
    assert.notEqual(alice.cookie, anonymousCookie);
    authenticatedCookie = alice.cookie;
    const account = await alice.get('/account');
    assert.equal(account.status, 200);
    assert.match(account.html, /Тест Альфа/);
    assert.match(account.html, /Не подключено/);
    const api = (await alice.get('/api/profile')).json();
    userId = api.profile.id;
    assert.equal(api.profile.username, 'test_alpha');
    assert.equal(api.profile.nickname, 'Test_Alpha');
    assert.equal(api.profile.email, 'alpha@example.test');
    assert.equal(api.profile.displayName, 'Тест Альфа');
    assert.match(userId, /^[0-9a-f-]{36}$/);
    const replay = browser(origin); replay.cookie = anonymousCookie;
    assert.equal((await replay.get('/api/profile')).status, 401);
  });
  await t.test('database stores salted scrypt and hashed session IDs only', () => {
    const row = runtime.store.findUser('test_alpha');
    assert.match(row.password_hash, /^scrypt\$v1\$131072\$8\$1\$[a-f0-9]{32}\$[a-f0-9]{128}$/);
    assert.ok(!row.password_hash.includes(password));
    const sessions = runtime.store.db.prepare('SELECT token_hash FROM sessions WHERE user_id = ?').all(userId);
    assert.ok(sessions.every(row => row.token_hash.length === 64 && !authenticatedCookie.includes(row.token_hash)));
    assert.equal(runtime.store.db.prepare('PRAGMA user_version').get().user_version, 2);
  });
  await t.test('case-insensitive duplicate registration is rejected', async () => {
    await guest.get('/register');
    const result = await guest.post('/register', { email: 'other@example.test', nickname: 'TEST_ALPHA', display_name: 'Дубликат', password, password_confirm: password });
    assert.equal(result.status, 409);
    assert.match(result.html, /Проверь отмеченные поля|ник уже занят/);
    assert.equal(runtime.store.db.prepare('SELECT count(*) AS n FROM users').get().n, 1);
  });
  await t.test('unknown and wrong-password login use the same error', async () => {
    await guest.get('/login');
    const wrong = await guest.post('/login', { email: 'alpha@example.test', password: 'not-the-correct-passphrase' });
    const unknown = await guest.post('/login', { email: 'missing@example.test', password: 'not-the-correct-passphrase' });
    assert.equal(wrong.status, 401); assert.equal(unknown.status, 401);
    assert.match(wrong.html, /Неверная почта или пароль/);
    assert.match(unknown.html, /Неверная почта или пароль/);
    assert.doesNotMatch(wrong.html, /not-the-correct-passphrase/);
  });
  await t.test('profile saves and HTML output escapes untrusted display text', async () => {
    const result = await alice.post('/account/profile', { display_name: '<script>alert(1)</script>', bio: 'Мой профиль & личная запись' });
    assert.equal(result.status, 303);
    const account = await alice.get('/account');
    assert.match(account.html, /&lt;script&gt;/);
    assert.doesNotMatch(account.html, /<script>alert/);
    assert.equal((await alice.get('/api/profile')).json().profile.bio, 'Мой профиль & личная запись');
    assert.equal((await alice.post('/account/profile', { display_name: 'Нормальное имя', bio: 'После перезапуска тоже здесь' })).status, 303);
    const bad = await alice.post('/account/profile', { display_name: '', bio: 'x'.repeat(241) });
    assert.equal(bad.status, 422);
    assert.equal((await alice.get('/api/profile')).json().profile.displayName, 'Нормальное имя');
  });
  await t.test('a second user cannot read or overwrite the first user', async () => {
    const bob = browser(origin);
    await bob.get('/register');
    assert.equal((await bob.post('/register', { email: 'beta@example.test', nickname: 'test_beta', display_name: 'Тест Бета', password, password_confirm: password })).status, 303);
    await bob.get('/account');
    const profile = (await bob.get(`/api/profile?id=${userId}`)).json().profile;
    assert.notEqual(profile.id, userId);
    assert.equal(profile.username, 'test_beta');
    assert.equal((await bob.post('/account/profile', { id: userId, display_name: 'Подмена', bio: '' })).status, 400);
    assert.equal((await alice.get('/api/profile')).json().profile.displayName, 'Нормальное имя');
    assert.equal((await bob.post('/account/profile', { display_name: 'Только Бета', bio: '' })).status, 303);
    assert.equal(runtime.store.profile(userId).display_name, 'Нормальное имя');
    const first = runtime.store.findUser('test_alpha').password_hash;
    const second = runtime.store.findUser('test_beta').password_hash;
    assert.notEqual(first, second, 'equal passwords must get distinct salts');
  });
  await t.test('bounded body, repeated fields, and content encoding are rejected', async () => {
    assert.equal((await alice.request('/account/profile', { method: 'POST', body: `csrf=${alice.csrf}&display_name=One&display_name=Two&bio=` })).status, 400);
    assert.equal((await alice.request('/account/profile', { method: 'POST', body: 'x'.repeat(9000) })).status, 413);
    assert.equal((await alice.request('/account/profile', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })).status, 415);
    assert.equal((await alice.request('/account/profile', { method: 'POST', headers: { 'Content-Encoding': 'gzip' }, body: 'invalid' })).status, 415);
  });
  await t.test('disconnected game API is explicit and exposes no fabricated data or writes', async () => {
    const game = (await alice.get('/api/game')).json();
    assert.deepEqual(game, { schemaVersion: 'web-game-read.v1', state: 'not_connected', account: null, inventory: null, statistics: null });
    assert.equal((await alice.post('/api/game', { balance: '999' })).status, 404);
    assert.equal((await alice.get('/api/profile')).html.includes('password'), false);
  });
  await t.test('logout requires CSRF and revokes a copied session token', async () => {
    assert.equal((await alice.get('/logout')).status, 404);
    assert.equal((await alice.post('/logout', { csrf: 'x'.repeat(43) })).status, 403);
    const copied = browser(origin); copied.cookie = alice.cookie;
    assert.equal((await alice.post('/logout')).status, 303);
    assert.equal((await alice.get('/account')).status, 303);
    assert.equal((await copied.get('/api/profile')).status, 401);
  });
  await t.test('homepage login rotates session; forged cookie is rejected', async () => {
    const home = await alice.get('/');
    assert.equal(home.status, 200);
    assert.equal(alice.csrf.length, 43);
    const before = alice.cookie;
    assert.equal((await alice.post('/login', { email: ' ALPHA@EXAMPLE.TEST ', password })).status, 303);
    assert.notEqual(alice.cookie, before);
    assert.equal((await alice.get('/account')).status, 200);
    const forged = browser(origin); forged.cookie = `web_sid=${'a'.repeat(43)}`;
    assert.equal((await forged.get('/api/profile')).status, 401);
  });
  await t.test('sixth email login attempt is limited with Retry-After', async () => {
    const limited = browser(origin); await limited.get('/login');
    for (let i = 0; i < 5; i++) assert.equal((await limited.post('/login', { email: 'limited@example.test', password })).status, 401);
    const result = await limited.post('/login', { email: 'limited@example.test', password }, { 'X-Forwarded-For': '198.51.100.1' });
    assert.equal(result.status, 429); assert.ok(Number(result.headers.get('retry-after')) > 0);
  });
  await t.test('expired sessions cannot access HTML or APIs', async () => {
    stamp += 8 * 60 * 60 * 1000 + 1;
    assert.equal((await alice.get('/account')).status, 303);
    assert.equal((await alice.get('/api/profile')).status, 401);
    runtime.store.cleanup();
    assert.equal(runtime.store.db.prepare('SELECT count(*) AS n FROM sessions').get().n, 0);
  });
});
