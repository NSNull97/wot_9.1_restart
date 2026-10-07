import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { mkdtempSync, rmSync, mkdirSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomBytes } from 'node:crypto';
import { createIdentityService } from '../server/identity/account_service.mjs';
import { createAccountPortalApp } from '../web/src/account_portal.mjs';

const ROOT = fileURLToPath(new URL('../', import.meta.url));
const STAGING = resolve(ROOT, 'local/staging/identity-boundary');
const secret = () => randomBytes(32).toString('base64url');
async function freePort() {
  const server = createServer(); await new Promise(resolvePromise => server.listen(0, '127.0.0.1', resolvePromise));
  const value = server.address().port; await new Promise(resolvePromise => server.close(resolvePromise)); return value;
}
function cookie(response) {
  const value = response.headers.get('set-cookie');
  return value?.match(/^web_sid=([^;]+)/)?.[1] || null;
}
function csrf(html) { return html.match(/name="csrf" value="([^"]+)"/)?.[1] || null; }
async function form(origin, path, values, cookieValue) {
  const body = new URLSearchParams(values).toString();
  return fetch(origin + path, { method: 'POST', redirect: 'manual', headers: {
    Origin: origin, Cookie: `web_sid=${cookieValue}`, 'Content-Type': 'application/x-www-form-urlencoded', 'Content-Length': String(Buffer.byteLength(body)),
  }, body });
}

test('opt-in portal completes registration/login/profile over identity.account.v1', async t => {
  mkdirSync(STAGING, { recursive: true });
  const directory = mkdtempSync(join(STAGING, 'portal-'));
  const portalSecret = secret(); const gameSecret = secret();
  const identity = await createIdentityService({ databasePath: join(directory, 'identity.sqlite'), tokens: { portal: portalSecret, game: gameSecret } });
  const port = await freePort(); const origin = `http://127.0.0.1:${port}`;
  const runtime = createAccountPortalApp({ origin, identityOrigin: `http://127.0.0.1:${identity.port}`, identitySecret: portalSecret });
  const server = createServer(runtime.app); await new Promise(resolvePromise => server.listen(port, '127.0.0.1', resolvePromise));
  t.after(async () => { await new Promise(resolvePromise => { server.close(resolvePromise); server.closeAllConnections(); }); await identity.close(); rmSync(directory, { recursive: true, force: true }); });

  const registerPage = await fetch(origin + '/register'); assert.equal(registerPage.status, 200);
  const anonymous = cookie(registerPage); assert.match(anonymous, /^[A-Za-z0-9_-]{43}$/); const token = csrf(await registerPage.text()); assert.match(token, /^[A-Za-z0-9_-]{43}$/);
  const registered = await form(origin, '/register', { csrf: token, email: 'portal@example.test', nickname: 'Портал_Ёж', display_name: 'Портал', password: 'correct horse battery staple', password_confirm: 'correct horse battery staple' }, anonymous);
  assert.equal(registered.status, 303); assert.equal(registered.headers.get('location'), '/account'); const authenticated = cookie(registered); assert.match(authenticated, /^[A-Za-z0-9_-]{43}$/);
  const api = await fetch(origin + '/api/profile', { headers: { Cookie: `web_sid=${authenticated}` } }); const profile = (await api.json()).profile;
  assert.equal(api.status, 200); assert.equal(profile.nickname, 'Портал_Ёж'); assert.match(profile.account_id, /^[0-9a-f-]{36}$/);
  const account = await fetch(origin + '/account', { headers: { Cookie: `web_sid=${authenticated}` } }); assert.equal(account.status, 200); const accountHtml = await account.text(); assert.match(accountHtml, /not_connected/);
  const updated = await form(origin, '/profile', { csrf: csrf(accountHtml), display_name: 'Портал Обновлён', bio: 'сохранено через identity boundary' }, authenticated); assert.equal(updated.status, 303);
  const updatedProfile = (await (await fetch(origin + '/api/profile', { headers: { Cookie: `web_sid=${authenticated}` } })).json()).profile; assert.equal(updatedProfile.display_name, 'Портал Обновлён'); assert.equal(updatedProfile.bio, 'сохранено через identity boundary');
  const loggedOut = await form(origin, '/logout', { csrf: csrf(accountHtml) }, authenticated); assert.equal(loggedOut.status, 303);
  const loginPage = await fetch(origin + '/login'); assert.equal(loginPage.status, 200); const loginCookie = cookie(loginPage); const loginCsrf = csrf(await loginPage.text());
  const loggedIn = await form(origin, '/login', { csrf: loginCsrf, email: 'portal@example.test', password: 'correct horse battery staple' }, loginCookie); assert.equal(loggedIn.status, 303); const authenticatedAgain = cookie(loggedIn);
  const reloginProfile = (await (await fetch(origin + '/api/profile', { headers: { Cookie: `web_sid=${authenticatedAgain}` } })).json()).profile; assert.equal(reloginProfile.account_id, profile.account_id); assert.equal(reloginProfile.nickname, profile.nickname);
  const wrongPage = await fetch(origin + '/login'); const wrongCookie = cookie(wrongPage); const wrongCsrf = csrf(await wrongPage.text());
  const wrong = await form(origin, '/login', { csrf: wrongCsrf, email: 'portal@example.test', password: 'wrong password here' }, wrongCookie); assert.equal(wrong.status, 401); assert.match(await wrong.text(), /Неверная почта или пароль/);
  const source = readFileSync(resolve(ROOT, 'web/src/account_portal.mjs'), 'utf8');
  for (const forbidden of ['../web/src/store.mjs', '../web/src/security.mjs', './game-adapter.mjs', './test-garage.mjs', 'node:sqlite']) assert.doesNotMatch(source, new RegExp(forbidden.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
});

test('portal reports identity outage instead of creating a guest account', async t => {
  mkdirSync(STAGING, { recursive: true }); const directory = mkdtempSync(join(STAGING, 'portal-outage-'));
  const portalSecret = secret(); const identity = await createIdentityService({ databasePath: join(directory, 'identity.sqlite'), tokens: { portal: portalSecret, game: secret() } });
  const port = await freePort(); const origin = `http://127.0.0.1:${port}`; const runtime = createAccountPortalApp({ origin, identityOrigin: `http://127.0.0.1:${identity.port}`, identitySecret: portalSecret, timeoutMs: 500 });
  const server = createServer(runtime.app); await new Promise(resolvePromise => server.listen(port, '127.0.0.1', resolvePromise));
  t.after(async () => { await new Promise(resolvePromise => { server.close(resolvePromise); server.closeAllConnections(); }); await identity.close(); rmSync(directory, { recursive: true, force: true }); });
  const page = await fetch(origin + '/register'); const sessionCookie = cookie(page); assert.match(sessionCookie, /^[A-Za-z0-9_-]{43}$/); await identity.close();
  const unavailable = await fetch(origin + '/account', { headers: { Cookie: `web_sid=${sessionCookie}` } }); assert.equal(unavailable.status, 503); assert.match(await unavailable.text(), /Авторизация недоступна/);
});
