import test from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomBytes } from 'node:crypto';
import { createIdentityClient } from '../server/contracts/identity_client.mjs';
import { IdentityError } from '../server/contracts/identity.mjs';
import { createIdentityService } from '../server/identity/account_service.mjs';

const ROOT = fileURLToPath(new URL('../', import.meta.url));
const STAGING = resolve(ROOT, 'local/staging/identity-boundary');
const token = () => randomBytes(32).toString('base64url');

function fixture(t) {
  mkdirSync(STAGING, { recursive: true });
  const directory = mkdtempSync(join(STAGING, 'run-'));
  return { directory, databasePath: join(directory, 'identity.sqlite'), portalSecret: token(), gameSecret: token() };
}

async function start(fixture) {
  const service = await createIdentityService({ databasePath: fixture.databasePath, tokens: {
    portal: fixture.portalSecret, game: fixture.gameSecret,
  } });
  const portal = createIdentityClient({ origin: `http://127.0.0.1:${service.port}`, secret: fixture.portalSecret, role: 'portal' });
  const game = createIdentityClient({ origin: `http://127.0.0.1:${service.port}`, secret: fixture.gameSecret, role: 'game' });
  return { service, portal, game };
}

test('registration, browser login and game verification share one durable account_id', async t => {
  const fixtureData = fixture(t);
  let running = await start(fixtureData);
  t.after(async () => { if (running) await running.service.close(); rmSync(fixtureData.directory, { recursive: true, force: true }); });
  const opened = await running.portal.call('session/open', { session_token: null });
  assert.match(opened.session_token, /^[A-Za-z0-9_-]{43}$/);
  const registered = await running.portal.call('register', {
    session_token: opened.session_token, csrf: opened.csrf,
    email: 'boundary@example.test', nickname: 'Проверка_Ёж', display_name: 'Проверка',
    password: 'correct horse battery staple',
  });
  assert.match(registered.profile.account_id, /^[0-9a-f-]{36}$/);
  assert.equal(registered.profile.nickname, 'Проверка_Ёж');
  assert.equal(registered.profile.email, 'boundary@example.test');
  assert.equal(registered.profile.nickname_key, 'проверка_ёж');
  assert.equal(typeof registered.profile.created_at, 'number');
  assert.ok(!['password', 'password_hash', 'session_token', 'csrf'].some(key => Object.hasOwn(registered.profile, key)));
  const gameIdentity = await running.game.call('credentials/verify', { email: 'BOUNDARY@EXAMPLE.TEST', password: 'correct horse battery staple' });
  assert.deepEqual(gameIdentity, {
    account_id: registered.profile.account_id, nickname: 'Проверка_Ёж', created_at: registered.profile.created_at,
  });
  const wrongSession = await running.portal.call('session/open', { session_token: null });
  await assert.rejects(() => running.portal.call('login', {
    session_token: wrongSession.session_token, csrf: wrongSession.csrf, email: 'boundary@example.test', password: 'wrong password here',
  }), error => error instanceof IdentityError && error.code === 'invalid_credentials' && error.status === 401);
  await assert.rejects(() => running.game.call('credentials/verify', { email: 'boundary@example.test', password: 'wrong password here' }),
    error => error instanceof IdentityError && error.code === 'invalid_credentials' && error.status === 401);
  const db = new DatabaseSync(fixtureData.databasePath, { readOnly: true });
  try {
    assert.equal(db.prepare('PRAGMA user_version').get().user_version, 1);
    assert.equal(db.prepare('SELECT COUNT(*) AS n FROM accounts').get().n, 1);
    assert.equal(db.prepare('SELECT COUNT(*) AS n FROM sessions').get().n, 2);
    const row = db.prepare('SELECT password_hash FROM accounts').get();
    assert.match(row.password_hash, /^scrypt\$v1\$/);
    assert.doesNotMatch(JSON.stringify(registered), /scrypt|correct horse/);
  } finally { db.close(); }

  await running.service.close(); running = null;
  const restarted = await start(fixtureData); running = restarted;
  const persisted = await restarted.portal.call('session/read', { session_token: registered.session_token });
  assert.equal(persisted.profile.account_id, registered.profile.account_id);
  assert.equal(persisted.profile.nickname, registered.profile.nickname);
});

test('contract mismatch, role isolation and service outage fail closed', async t => {
  const fixtureData = fixture(t); const running = await start(fixtureData);
  t.after(async () => { await running.service.close(); rmSync(fixtureData.directory, { recursive: true, force: true }); });
  const body = Buffer.from(JSON.stringify({ contract: 'identity.account.v0', operation: 'session/open', payload: { session_token: null } }));
  const response = await fetch(running.portal.origin + '/identity/v1/session/open', {
    method: 'POST', headers: { Authorization: `Bearer ${fixtureData.portalSecret}`, 'X-Identity-Role': 'portal',
      'Content-Type': 'application/json', 'Content-Length': String(body.length) }, body,
  });
  assert.equal(response.status, 409); assert.deepEqual((await response.json()).error, { code: 'contract_mismatch' });
  await assert.rejects(() => running.portal.call('credentials/verify', { email: 'a@example.test', password: 'long enough password' }),
    error => error.code === 'forbidden' && error.status === 403);
  const opened = await running.portal.call('session/open', { session_token: null });
  await assert.rejects(() => running.portal.call('login', { session_token: opened.session_token, csrf: opened.csrf,
    email: 'missing@example.test', password: 'long enough password' }), error => error.code === 'invalid_credentials');
  const origin = running.portal.origin; await running.service.close();
  const client = createIdentityClient({ origin, secret: fixtureData.portalSecret, role: 'portal', timeoutMs: 500 });
  await assert.rejects(() => client.call('session/open', { session_token: null }), error => error.code === 'unavailable' && error.status === 503);
});

test('unsupported database version is refused before the listener starts', async t => {
  const fixtureData = fixture(t); mkdirSync(fixtureData.directory, { recursive: true });
  const db = new DatabaseSync(fixtureData.databasePath); db.exec('PRAGMA user_version=99'); db.close();
  assert.throws(() => createIdentityService({ databasePath: fixtureData.databasePath,
    tokens: { portal: fixtureData.portalSecret, game: fixtureData.gameSecret } }), /Unsupported identity database version/);
  rmSync(fixtureData.directory, { recursive: true, force: true });
});
