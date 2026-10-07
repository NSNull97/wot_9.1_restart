import test from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomUUID, createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { emailField, nicknameField, token, hashPassword, digest } from '../src/security.mjs';
import { createApp } from '../src/app.mjs';
import { openIdentityReader } from '../src/store.mjs';
import { createIdentityBridge } from '../src/game-adapter.mjs';
import { browser, freePort, testDirectory, removeTestDirectory } from './helpers.mjs';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const NATIVE = join(ROOT, 'local/evidence/20261004-p02-hangar/native-descriptors.json');
const OLD_ENCODER = join(ROOT, 'local/evidence/20261004-p02-unified-account/data-agent/username-v1-tools/hangar_state.py');
const OLD_SHA = 'bf026f98e6ccfb84bc2bde4720d9837863beae662a2f4600ad80e78356b040f4';
const sha = bytes => createHash('sha256').update(bytes).digest('hex');

test('finite Russian/Latin nickname policy preserves NFC display case and case-insensitive keys', () => {
  for (const [raw, display, key] of [
    [' Танкист_Ёж ', 'Танкист_Ёж', 'танкист_ёж'], ['Е\u0308жик', 'Ёжик', 'ёжик'],
    ['е\u0308жик', 'ёжик', 'ёжик'], ['И\u0306ван', 'Йван', 'йван'], ['и\u0306ван', 'йван', 'йван'],
    ['Ab9', 'Ab9', 'ab9'], ['Я'.repeat(24), 'Я'.repeat(24), 'я'.repeat(24)],
  ]) assert.deepEqual(nicknameField(raw), { display, key });
  assert.notEqual(nicknameField('Ёжик').key, nicknameField('Ежик').key);
  for (const bad of ['', 'a', 'ab', 'я'.repeat(25), 'a'.repeat(97), 'ab-c', 'ab.c', 'Äbc', 'Їван',
    'a\u0301bc', 'Ё\u0308жик', '\tТанк', 'Танк\n', 'Танк\u00a0', 'a\u200db', 'a\u202eb', '😀ab', 'ab\ud800']) {
    assert.equal(nicknameField(bad), null, JSON.stringify(bad));
  }
});

test('ASCII email contract has explicit dot-atom, domain, case, trim and length bounds', () => {
  for (const raw of ['Player+tag@Example.TEST', ' \tPLAYER@example.test\r\n', "a.!#$%&'*+/=?^_`{|}~-b@x.example"]) {
    assert.equal(emailField(raw), raw.trim().toLowerCase());
  }
  const maximum = `${'a'.repeat(64)}@${'b'.repeat(63)}.${'c'.repeat(63)}.${'d'.repeat(61)}`;
  assert.equal(maximum.length, 254); assert.equal(emailField(maximum), maximum);
  for (const bad of ['', 'nickname', '@example.test', 'a@@example.test', '.a@x.test', 'a.@x.test', 'a..b@x.test',
    'a@localhost', 'a@127.0.0.1', 'a@-x.test', 'a@x-.test', 'a@x..test', 'a@x_test.test', 'a@x.123',
    'п@x.test', 'a@пример.рф', '\u00a0a@x.test', 'a b@x.test', 'a\n@x.test', 'a@x.test\u007f',
    'a@x.test\x00', 'a'.repeat(65) + '@x.test', 'a@' + 'b'.repeat(64) + '.test', maximum + 'x']) {
    assert.equal(emailField(bad), null, JSON.stringify(bad));
  }
});

test('real schema1 migration, existing-session binding, email-only HTTP and owner CLI preserve identity', async t => {
  const directory = testDirectory();
  const database = join(directory, 'portal.sqlite');
  const password = `  пароль_${token()}  `;
  const encoded = await hashPassword(password);
  const ids = [randomUUID(), randomUUID(), randomUUID()];
  const created = Date.now() - 86_400_000;
  const rawSession = token(), csrf = token();
  let old = new DatabaseSync(database);
  old.exec(readFileSync(new URL('../migrations/001_web_profile.sql', import.meta.url), 'utf8'));
  ids.forEach((id, i) => old.prepare('INSERT INTO users VALUES (?,?,?, ?,?,?,?,?)')
    .run(id, `legacy_${i}`, `Старое имя ${i}`, '', encoded, created, created, created));
  old.prepare('INSERT INTO sessions VALUES (?,?,?,?,?)').run(digest(rawSession), ids[0], csrf, Date.now(), Date.now() + 3_600_000);
  const originalUsers = old.prepare('SELECT * FROM users ORDER BY id').all();
  const originalSessions = old.prepare('SELECT * FROM sessions').all();
  old.close();
  assert.throws(() => openIdentityReader(database), /initialized/);
  const origin = `http://127.0.0.1:${await freePort()}`;
  const runtime = await createApp({ databasePath: database, origin });
  const server = runtime.app.listen(Number(new URL(origin).port), '127.0.0.1');
  await new Promise(done => server.once('listening', done));
  t.after(async () => { await new Promise(done => server.close(done)); runtime.close(); removeTestDirectory(directory); });
  const alice = browser(origin); alice.cookie = `web_sid=${rawSession}`; alice.csrf = csrf;

  await t.test('rendered register/login/home forms use email and an explicit nickname; legacy account offers binding', async () => {
    const guest = browser(origin);
    const registration = await guest.get('/register');
    assert.equal(registration.status, 200);
    assert.match(registration.html, /type="email" name="email"/);
    assert.match(registration.html, /name="nickname"/);
    assert.match(registration.html, /русские буквы/);
    assert.doesNotMatch(registration.html, /name="username"|Пароль от игрового аккаунта здесь не нужен/);
    const login = await guest.get('/login');
    assert.match(login.html, /type="email" name="email"/);
    assert.doesNotMatch(login.html, /name="nickname"|name="username"/);
    assert.match((await guest.get('/')).html, /type="email" name="email"/);
    const account = await alice.get('/account');
    assert.match(account.html, /action="\/account\/email"/);
    assert.match(account.html, /name="current_password"/);
    assert.doesNotMatch(account.html, /value=".*пароль/);
  });
  await t.test('migration snapshot remains schema1 and preserves all original records including sessions', () => {
    assert.ok(runtime.store.migrationBackup && existsSync(runtime.store.migrationBackup));
    const backup = new DatabaseSync(runtime.store.migrationBackup, { readOnly: true });
    assert.equal(backup.prepare('PRAGMA user_version').get().user_version, 1);
    assert.ok(JSON.stringify(backup.prepare('SELECT * FROM users ORDER BY id').all()) === JSON.stringify(originalUsers), 'backup identity records are exact');
    assert.ok(JSON.stringify(backup.prepare('SELECT * FROM sessions').all()) === JSON.stringify(originalSessions), 'backup session records are exact'); backup.close();
    for (const original of originalUsers) {
      const current = runtime.store.findUser(original.username);
      assert.equal(current.email, null); assert.equal(current.display_nickname, original.username);
      delete current.email; delete current.display_nickname;
      assert.ok(JSON.stringify(current) === JSON.stringify(original), 'migration preserves every original identity column');
    }
    assert.ok(JSON.stringify(runtime.store.db.prepare('SELECT * FROM sessions WHERE user_id IS NOT NULL').all()) === JSON.stringify(originalSessions), 'existing authenticated session remains exact');
  });
  await t.test('legacy session stays signed in; binding requires CSRF/current password and is immutable', async () => {
    assert.equal((await alice.get('/api/profile')).json().profile.email, null);
    assert.equal((await alice.post('/account/email', { csrf: 'a'.repeat(43), email: 'old@example.test', current_password: password })).status, 403);
    assert.equal((await alice.post('/account/email', { email: 'old@example.test', current_password: token() })).status, 401);
    assert.equal((await alice.post('/account/email', { email: ' OLD@EXAMPLE.TEST ', current_password: password })).status, 303);
    assert.equal((await alice.post('/account/email', { email: 'old@example.test', current_password: password })).status, 303);
    assert.equal((await alice.post('/account/email', { email: 'different@example.test', current_password: password })).status, 409);
    const current = runtime.store.profile(ids[0]);
    assert.equal(current.id, ids[0]); assert.equal(current.email, 'old@example.test');
    assert.equal(current.username, 'legacy_0'); assert.equal(current.created_at, created);
    assert.ok(runtime.store.passwordRecord(ids[0]).password_hash === encoded, 'binding preserves the password record');
    const page = await alice.get('/account');
    assert.match(page.html, /old@example.test/);
    assert.doesNotMatch(page.html, /name="current_password"/);
  });
  await t.test('nickname cannot authenticate; canonical email can, including exact Unicode/space password', async () => {
    const login = browser(origin); await login.get('/login');
    assert.equal((await login.post('/login', { username: 'legacy_0', password })).status, 400);
    assert.equal((await login.post('/login', { email: 'legacy_0', password })).status, 401);
    assert.equal((await login.post('/login', { email: 'old@example.test', password: password.trim() })).status, 401);
    assert.equal((await login.post('/login', { email: 'OLD@EXAMPLE.TEST', password })).status, 303);
    assert.equal((await login.get('/api/profile')).json().profile.id, ids[0]);
  });
  await t.test('new registration uses NFC display nickname; lower/NFD collision and email collision fail', async () => {
    const client = browser(origin); await client.get('/register');
    assert.equal((await client.post('/register', { email: 'new@example.test', nickname: 'Е\u0308ж_Танкист', password, password_confirm: password })).status, 303);
    const result = (await client.get('/api/profile')).json().profile;
    assert.equal(result.nickname, 'Ёж_Танкист'); assert.equal(result.username, 'ёж_танкист');
    assert.equal(result.displayName, result.nickname); assert.equal(result.email, 'new@example.test');
    const other = browser(origin); await other.get('/register');
    assert.equal((await other.post('/register', { email: 'other@example.test', nickname: 'ёж_танкист', password, password_confirm: password })).status, 409);
    assert.equal((await other.post('/register', { email: 'NEW@EXAMPLE.TEST', nickname: 'Другой_Танк', password, password_confirm: password })).status, 409);
    assert.equal((await other.post('/register', { email: 'else@example.test', nickname: 'ab\u202ecd', password, password_confirm: password })).status, 422);
    assert.equal(runtime.store.db.prepare('SELECT COUNT(*) AS n FROM users').get().n, 4);
  });
  await t.test('local CLI binds only an explicitly existing UUID and refuses replacement/collision', () => {
    const input = join(directory, 'assign.json');
    const run = (account_id, email) => {
      writeFileSync(input, JSON.stringify({ account_id, email }));
      return spawnSync(process.execPath, [resolve(ROOT, 'web/scripts/assign-email.mjs'), '--database', database, '--input', input],
        { encoding: 'utf8', windowsHide: true, timeout: 5000 });
    };
    const first = run(ids[1], ' CLI@EXAMPLE.TEST '); assert.equal(first.status, 0);
    assert.equal(JSON.parse(first.stdout).changed, true);
    assert.equal(JSON.parse(run(ids[1], 'cli@example.test').stdout).changed, false);
    assert.equal(run(ids[1], 'different@example.test').status, 1);
    assert.equal(run(ids[2], 'cli@example.test').status, 1);
    assert.equal(run(randomUUID(), 'missing@example.test').status, 1);
    assert.equal(runtime.store.profile(ids[1]).email, 'cli@example.test');
    assert.equal(runtime.store.profile(ids[2]).email, null);
    assert.ok(!first.stdout.includes('CLI') && !first.stdout.includes(ids[1]) && !first.stdout.includes(password));
  });
});

test('measured legacy r1 survives a separate catalogue migration without changing the account', {
  skip: !existsSync(NATIVE) || !existsSync(OLD_ENCODER) ? 'NOT_RUN: measured local descriptors/old encoder required' : false,
}, async t => {
  assert.equal(sha(readFileSync(OLD_ENCODER)), OLD_SHA);
  const directory = testDirectory(), database = join(directory, 'portal.sqlite');
  let runtime, bridge;
  t.after(async () => { if (bridge) await bridge.close(); runtime?.close(); removeTestDirectory(directory); });
  const password = token(), id = randomUUID(), created = Date.now() - 172_800_000;
  let db = new DatabaseSync(database);
  db.exec(readFileSync(new URL('../migrations/001_web_profile.sql', import.meta.url), 'utf8'));
  db.prepare('INSERT INTO users VALUES (?,?,?,?,?,?,?,?)').run(id, 'old_snapshot', 'Original name', '', await hashPassword(password), created, created, created);
  db.close();
  const origin = `http://127.0.0.1:${await freePort()}`;
  runtime = await createApp({ databasePath: database, origin });
  runtime.store.bindEmail(id, 'snapshot@example.test');
  const profile = { profile_version: 1, account_id: id, username: 'old_snapshot', native_database_id: 77,
    created_at_ms: created, snapshot_revision: 1, resources: { credits: 43210, gold: 7, free_xp: 9 },
    statistics: { battles: 0, wins: 0, losses: 0, draws: 0 } };
  const gamePath = join(directory, 'game.sqlite');
  db = new DatabaseSync(gamePath);
  db.exec(`CREATE TABLE game_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
    CREATE TABLE game_profiles(native_id INTEGER PRIMARY KEY AUTOINCREMENT,account_id TEXT UNIQUE,profile_json TEXT);
    CREATE TABLE game_limits(key_hash TEXT PRIMARY KEY,hits INTEGER,resets_at INTEGER); PRAGMA user_version=1;`);
  db.prepare('INSERT INTO game_meta VALUES (?,?)').run('native_descriptors_sha256', sha(readFileSync(NATIVE)));
  db.prepare('INSERT INTO game_profiles VALUES (?,?,?)').run(77, id, JSON.stringify(profile)); db.close();
  const fixtureRoot = join(directory, 'fixtures'), destination = join(fixtureRoot, id, 'r1');
  mkdirSync(destination, { recursive: true });
  const profileFile = join(destination, 'profile-input.json'); writeFileSync(profileFile, JSON.stringify(profile));
  const python = spawnSync('python', ['-c', 'import sys; print(sys.executable)'], { encoding: 'utf8', windowsHide: true }).stdout.trim();
  const generated = spawnSync(python, ['-X', 'utf8', OLD_ENCODER, '--out', destination, '--profile', profileFile, '--native-descriptors', NATIVE],
    { env: { ...process.env, PYTHONPATH: join(ROOT, 'tools') }, encoding: 'utf8', windowsHide: true, timeout: 5000 });
  assert.equal(generated.status, 0, 'real measured old data-only generator');
  const names = ['manifest.json', 'profile-input.json', 'compatibility.json', 'state.bin', 'shop.bin', 'dossier.bin'];
  const before = Object.fromEntries(names.map(name => [name, sha(readFileSync(join(destination, name)))]));
  const secret = token(), tokenFile = join(directory, 'identity.token'); writeFileSync(tokenFile, secret);
  bridge = await createIdentityBridge({ version: 1, port: 0, web_database: database, game_database: gamePath,
    fixture_root: fixtureRoot, native_descriptors: NATIVE, python_executable: python, token_file: tokenFile });
  const login = () => fetch(`http://127.0.0.1:${bridge.port}/internal/native/login`, { method: 'POST',
    headers: { Authorization: `Bearer ${secret}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: 'snapshot@example.test', password }) });
  // A self-consistent legacy hash must not authorize a different account state.
  const statePath = join(destination, 'state.bin'), manifestPath = join(destination, 'manifest.json');
  const originalState = readFileSync(statePath), originalManifest = readFileSync(manifestPath);
  const alteredState = Buffer.from(originalState);
  const creditOffset = alteredState.indexOf(Buffer.from([0x55, 7, ...Buffer.from('credits'), 0x4d]));
  assert.ok(creditOffset >= 0, 'measured protocol2 credit field');
  alteredState.writeUInt16LE(43211, creditOffset + 10);
  const alteredManifest = JSON.parse(originalManifest);
  alteredManifest.files.find(row => row.file === 'state.bin').sha256 = sha(alteredState);
  writeFileSync(statePath, alteredState); writeFileSync(manifestPath, JSON.stringify(alteredManifest));
  assert.equal((await login()).status, 503, 'catalogue must preserve account state even with matching legacy content hash');
  assert.equal(existsSync(join(fixtureRoot, id, 'r1-catalog2')), false, 'invalid migration must not publish');
  assert.equal(sha(readFileSync(statePath)), sha(alteredState), 'legacy is never overwritten');
  writeFileSync(statePath, originalState); writeFileSync(manifestPath, originalManifest);
  const result = await login(); assert.equal(result.status, 200);
  const identity = await result.json(); assert.equal(identity.native_database_id, 77); assert.equal(identity.name, 'old_snapshot');
  assert.equal(identity.fixture_dir, join(fixtureRoot, id, 'r1-catalog2'));
  const migrated = JSON.parse(readFileSync(join(identity.fixture_dir, 'manifest.json')));
  assert.equal(migrated.compatibility_catalog_revision, 2);
  for (const file of ['state.bin', 'dossier.bin']) {
    assert.equal(sha(readFileSync(join(identity.fixture_dir, file))), before[file]);
  }
  assert.notEqual(sha(readFileSync(join(identity.fixture_dir, 'shop.bin'))), before['shop.bin']);
  const ledgerPath = join(identity.fixture_dir, 'catalog-migration.json');
  const ledgerBytes = readFileSync(ledgerPath);
  const published = Object.fromEntries(names.map(name => [name, sha(readFileSync(join(identity.fixture_dir, name)))]));
  writeFileSync(ledgerPath, '{}');
  assert.equal((await login()).status, 503, 'broken catalogue ledger must refuse without regeneration');
  assert.deepEqual(Object.fromEntries(names.map(name => [name, sha(readFileSync(join(identity.fixture_dir, name)))])), published);
  writeFileSync(ledgerPath, ledgerBytes);
  assert.deepEqual(Object.fromEntries(names.map(name => [name, sha(readFileSync(join(destination, name)))])), before);
  db = new DatabaseSync(gamePath, { readOnly: true });
  assert.deepEqual(JSON.parse(db.prepare('SELECT profile_json FROM game_profiles').get().profile_json), profile); db.close();
  const input = readFileSync(profileFile); writeFileSync(profileFile, Buffer.concat([input, Buffer.from(' ')]));
  assert.equal((await login()).status, 503, 'changed provenance must refuse, not regenerate/reset');
  assert.equal(sha(readFileSync(join(destination, 'state.bin'))), before['state.bin']);
});
