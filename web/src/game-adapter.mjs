/** Shared identity bridge and read-only website boundary. Credentials stay in users. */
import { createServer } from 'node:http';
import { DatabaseSync } from 'node:sqlite';
import { readFileSync, writeFileSync, mkdirSync, existsSync, realpathSync, renameSync, rmSync, statSync } from 'node:fs';
import { dirname, resolve, relative, isAbsolute, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createHash, randomUUID } from 'node:crypto';
import { spawn } from 'node:child_process';
import { openIdentityReader } from './store.mjs';
import { equalToken, validToken, validPassword, verifyPassword, hashPassword, token, nicknameField, emailField, digest } from './security.mjs';
import { grantedOverview, isGrantedOverview, validateGrantedFixture } from './test-garage.mjs';
import { crewOverview, isCrewOverview, validateCrewFixture } from './ms1-crew.mjs';
import { ammoOverview, isAmmoOverview, validateAmmoFixture } from './ms1-ammo.mjs';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const LOCAL = resolve(ROOT, 'local');
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const hash = value => createHash('sha256').update(value).digest('hex');
// Measured pre-email encoder. Existing immutable r1 snapshots are validated,
// not regenerated; IDs, resources and dossier registration date stay intact.
const LEGACY_R1_GENERATORS = [
  'bf026f98e6ccfb84bc2bde4720d9837863beae662a2f4600ad80e78356b040f4',
  '541441a0f38f8ce7600b133b77acad88ee40e01e28093d18e60bbb74261f269a',
];
const CATALOG_REVISION = 2;
const empty = state => ({ schemaVersion: 'web-game-read.v1', state, account: null, inventory: null, statistics: null });
const inside = (root, path) => { const rel = relative(root, path); return rel === '' || (!rel.startsWith('..') && !isAbsolute(rel)); };

function accountId(id) {
  if (typeof id !== 'string' || !UUID.test(id)) throw new TypeError('Authenticated account UUID required');
  return id;
}
function localPath(path, createParent = false) {
  if (typeof path !== 'string' || !isAbsolute(path) || !inside(LOCAL, resolve(path))) throw new Error('Service data must stay in project local');
  let ancestor = resolve(path);
  while (!existsSync(ancestor)) ancestor = dirname(ancestor);
  if (!inside(realpathSync(LOCAL), realpathSync(ancestor))) throw new Error('Redirected service data path');
  if (createParent) mkdirSync(dirname(path), { recursive: true });
  return resolve(path);
}
function readBounded(path, maximum) {
  if (!statSync(path).isFile() || statSync(path).size > maximum) throw new Error('Service file size/type');
  const data = readFileSync(path);
  if (data.length > maximum) throw new Error('Service file size changed');
  return data;
}
function readSecret(path) {
  const value = readBounded(localPath(path), 128).toString('utf8');
  if (!validToken(value)) throw new Error('Service secret must be exactly 43 base64url characters');
  return value;
}

export async function readGameOverview(id) { accountId(id); return empty('not_connected'); }

/** Only the site's authenticated session supplies id; browsers cannot select it. */
export function createGameReader({ origin, tokenFile } = {}) {
  if (!origin && !tokenFile) return readGameOverview;
  const url = new URL(origin);
  if (url.protocol !== 'http:' || url.hostname !== '127.0.0.1' || !url.port || url.username || url.password
      || url.pathname !== '/' || url.search || url.hash) throw new Error('Game bridge must be a numeric loopback origin');
  const secret = readSecret(tokenFile);
  return async id => {
    accountId(id);
    try {
      const response = await fetch(`${url.origin}/internal/accounts/${id}/overview`, {
        headers: { Authorization: `Bearer ${secret}` }, signal: AbortSignal.timeout(2500), redirect: 'error',
      });
      if (!response.ok || Number(response.headers.get('content-length')) > 32768) return empty('unavailable');
      const reader = response.body.getReader();
      const chunks = []; let bytes = 0;
      while (true) {
        const part = await reader.read(); if (part.done) break;
        bytes += part.value.length;
        if (bytes > 32768) { await reader.cancel(); return empty('unavailable'); }
        chunks.push(part.value);
      }
      const value = JSON.parse(Buffer.concat(chunks).toString('utf8'));
      if (value.schemaVersion !== 'web-game-read.v1' || !['ready', 'unlinked'].includes(value.state)) return empty('unavailable');
      if (value.state === 'unlinked') return empty('unlinked');
      if (value.snapshotRevision === 4) return isAmmoOverview(value, id) ? value : empty('unavailable');
      if (value.snapshotRevision === 3) return isCrewOverview(value, id) ? value : empty('unavailable');
      if (value.snapshotRevision === 2) return isGrantedOverview(value, id) ? value : empty('unavailable');
      if (value.account?.accountId !== id || value.ruleset !== 'test_lab' || value.snapshotRevision !== 1
          || !nicknameField(value.account?.nickname) || nicknameField(value.account.nickname).display !== value.account.nickname || !Array.isArray(value.inventory) || value.inventory.length !== 1
          || value.inventory[0]?.inventoryItemId !== `${id}:starter-vehicle-v1`
          || value.inventory[0]?.vehicleDefinitionId !== 'vehicle:ms1' || value.inventory[0]?.displayName !== 'МС-1'
          || value.inventory[0]?.health !== 90 || value.inventory[0]?.crewAssigned !== false || value.inventory[0]?.ammunition !== 0
          || !Number.isFinite(Date.parse(value.asOf))
          || !value.statistics || ['battles', 'wins', 'losses', 'draws'].some(k => value.statistics[k] !== 0)
          || !value.resources || ['credits', 'gold', 'freeXP'].some(k => !Number.isSafeInteger(value.resources[k]) || value.resources[k] < 0)) return empty('unavailable');
      return value;
    } catch { return empty('unavailable'); } // Explicit unavailable, never fake zero/ready.
  };
}

function openGameStore(path, sourceHash, now) {
  const db = new DatabaseSync(localPath(path, true));
  db.exec('PRAGMA journal_mode=WAL; PRAGMA busy_timeout=1000;');
  const version = db.prepare('PRAGMA user_version').get().user_version;
  if (version > 1) { db.close(); throw new Error('Unsupported game database version'); }
  if (version === 0) {
    db.exec(`BEGIN IMMEDIATE;
      CREATE TABLE game_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
      CREATE TABLE game_profiles (
        native_id INTEGER PRIMARY KEY AUTOINCREMENT CHECK(native_id BETWEEN 1 AND 2147483647),
        account_id TEXT NOT NULL UNIQUE, profile_json TEXT NOT NULL);
      CREATE TABLE game_limits (key_hash TEXT PRIMARY KEY, hits INTEGER NOT NULL, resets_at INTEGER NOT NULL);
      PRAGMA user_version=1; COMMIT;`);
  }
  const previous = db.prepare('SELECT value FROM game_meta WHERE key=?').get('native_descriptors_sha256');
  if (previous && previous.value !== sourceHash) { db.close(); throw new Error('Native source changed: explicit profile migration required'); }
  if (!previous) db.prepare('INSERT INTO game_meta VALUES (?,?)').run('native_descriptors_sha256', sourceHash);
  const read = id => {
    const row = db.prepare('SELECT profile_json FROM game_profiles WHERE account_id=?').get(id);
    return row ? JSON.parse(row.profile_json) : null;
  };
  return {
    close: () => db.close(), read,
    ensure(user) {
      accountId(user.id);
      let value = read(user.id);
      if (value) {
        if (value.username !== user.display_nickname || value.created_at_ms !== user.created_at) throw new Error('Stored game identity changed: explicit migration required');
        return value;
      }
      db.exec('BEGIN IMMEDIATE');
      try {
        value = read(user.id);
        if (!value) {
          const inserted = db.prepare('INSERT INTO game_profiles(account_id,profile_json) VALUES (?,?)').run(user.id, '{}');
          const nativeId = Number(inserted.lastInsertRowid);
          value = { profile_version: 1, account_id: user.id, username: user.display_nickname,
            native_database_id: nativeId, created_at_ms: user.created_at, snapshot_revision: 1,
            resources: { credits: 100000, gold: 0, free_xp: 0 },
            statistics: { battles: 0, wins: 0, losses: 0, draws: 0 } };
          db.prepare('UPDATE game_profiles SET profile_json=? WHERE account_id=?').run(JSON.stringify(value), user.id);
        }
        db.exec('COMMIT'); return value;
      } catch (error) { db.exec('ROLLBACK'); throw error; }
    },
    limit(key, maximum, windowMs) {
      const stamp = now();
      db.prepare('DELETE FROM game_limits WHERE resets_at<=?').run(stamp);
      const keyHash = digest(key);
      if (!db.prepare('SELECT 1 FROM game_limits WHERE key_hash=?').get(keyHash)
          && db.prepare('SELECT COUNT(*) AS n FROM game_limits').get().n >= 1024) return false;
      const row = db.prepare(`INSERT INTO game_limits VALUES (?,1,?) ON CONFLICT(key_hash) DO UPDATE SET
        hits=min(hits+1,?) RETURNING hits`).get(keyHash, stamp + windowMs, maximum + 1);
      return row.hits <= maximum;
    },
  };
}

function overview(profile) {
  if (profile.profile_version === 4) return ammoOverview(profile);
  if (profile.profile_version === 3) return crewOverview(profile);
  if (profile.profile_version === 2) return grantedOverview(profile);
  return { schemaVersion: 'web-game-read.v1', state: 'ready', ruleset: 'test_lab',
    snapshotRevision: profile.snapshot_revision, asOf: new Date(profile.created_at_ms).toISOString(),
    account: { accountId: profile.account_id, nickname: profile.username },
    resources: { credits: profile.resources.credits, gold: profile.resources.gold, freeXP: profile.resources.free_xp },
    inventory: [{ inventoryItemId: `${profile.account_id}:starter-vehicle-v1`, vehicleDefinitionId: 'vehicle:ms1',
      displayName: 'МС-1', health: 90, crewAssigned: false, ammunition: 0 }],
    statistics: profile.statistics,
    capabilities: { battle: false, purchases: false, sales: false },
  };
}

async function runGenerator(python, args) {
  await new Promise((resolvePromise, reject) => {
    const child = spawn(python, ['-X', 'utf8', join(ROOT, 'tools/hangar_state.py'), ...args],
      { cwd: ROOT, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
    let bytes = 0; let exceeded = false;
    const timer = setTimeout(() => { exceeded = true; child.kill(); }, 2500);
    for (const stream of [child.stdout, child.stderr]) stream.on('data', part => {
      bytes += part.length; if (bytes > 16384) { exceeded = true; child.kill(); }
    });
    child.once('error', () => { clearTimeout(timer); reject(new Error('Profile generator could not start')); });
    child.once('close', code => { clearTimeout(timer); code === 0 && !exceeded ? resolvePromise() : reject(new Error('Profile generation failed')); });
  });
}

function readJson(path, max) { return JSON.parse(readBounded(path, max).toString('utf8')); }

/** No listener is created until the original web DB and service inputs validate. */
export async function createIdentityBridge(options, { now = Date.now } = {}) {
  const allowed = ['version', 'port', 'web_database', 'game_database', 'fixture_root', 'native_descriptors', 'python_executable', 'token_file'];
  if (options?.test_garage !== undefined) allowed.push('test_garage');
  if (!options || options.version !== 1 || Object.keys(options).some(k => !allowed.includes(k))
      || allowed.some(k => !(k in options)) || !Number.isInteger(options.port) || options.port < 0 || options.port > 65535) throw new Error('Bridge config schema');
  const secret = readSecret(options.token_file);
  const webPath = localPath(options.web_database);
  const nativePath = localPath(options.native_descriptors);
  const nativeBytes = readBounded(nativePath, 65536);
  const generatorHash = hash(readBounded(join(ROOT, 'tools/hangar_state.py'), 65536));
  const native = JSON.parse(nativeBytes.toString('utf8'));
  if (native.vehicle?.type_name !== 'ussr:MS-1' || native.vehicle?.max_health !== 90) throw new Error('Unverified starter descriptor');
  let garage = null;
  if (options.test_garage !== undefined) {
    const value = options.test_garage;
    if (!value || Array.isArray(value) || Object.keys(value).sort().join(',') !== 'native_is7,sha256,version'
        || value.version !== 1 || !/^[0-9a-f]{64}$/.test(value.sha256)) throw new Error('Explicit pinned test garage configuration required');
    const path = localPath(value.native_is7);
    if (hash(readBounded(path, 32768)) !== value.sha256) throw new Error('Test garage native source hash mismatch');
    garage = { nativeMs1: nativePath, nativeIs7: path };
  }
  if (typeof options.python_executable !== 'string' || !isAbsolute(options.python_executable)
      || !statSync(options.python_executable).isFile()) throw new Error('Absolute Python executable required');
  const fixtureRoot = localPath(options.fixture_root, true);
  mkdirSync(fixtureRoot, { recursive: true });
  const identity = openIdentityReader(webPath);
  let game;
  try { game = openGameStore(options.game_database, hash(nativeBytes), now); }
  catch (error) { identity.close(); throw error; }
  let dummyHash;
  try { dummyHash = await hashPassword(token()); }
  catch (error) { identity.close(); game.close(); throw error; }
  const creating = new Map();
  async function fixture(profile) {
    const id = accountId(profile.account_id);
    if (profile.profile_version === 4) {
      if (!garage) throw new Error('Explicit offline test garage is not enabled');
      const destination = join(fixtureRoot, id, 'r4-catalog3');
      if (hash(readBounded(garage.nativeIs7, 32768)) !== options.test_garage.sha256) throw new Error('Pinned test garage source changed');
      validateAmmoFixture(destination, profile, { ...garage, baseFixture: join(fixtureRoot, id, 'r3-catalog3') });
      return destination;
    }
    if (profile.profile_version === 3) {
      if (!garage) throw new Error('Explicit offline test garage is not enabled');
      const destination = join(fixtureRoot, id, 'r3-catalog3');
      if (hash(readBounded(garage.nativeIs7, 32768)) !== options.test_garage.sha256) throw new Error('Pinned test garage source changed');
      validateCrewFixture(destination, profile, { ...garage, baseFixture: join(fixtureRoot, id, 'r2-catalog3') });
      return destination;
    }
    if (profile.profile_version === 2) {
      if (!garage) throw new Error('Explicit offline test garage is not enabled');
      const destination = join(fixtureRoot, id, 'r2-catalog3');
      if (hash(readBounded(garage.nativeIs7, 32768)) !== options.test_garage.sha256) throw new Error('Pinned test garage source changed');
      validateGrantedFixture(destination, profile, garage);
      return destination;
    }
    if (profile.profile_version !== 1 || profile.snapshot_revision !== 1) throw new Error('Unsupported stored profile version');
    // The domain snapshot remains r1. Only its native display catalogue changes.
    // Existing r1 is immutable; publishing a sibling is an atomic, reversible step.
    const legacy = localPath(join(fixtureRoot, id, 'r1'), true);
    const destination = localPath(join(fixtureRoot, id, 'r1-catalog2'), true);
    const validateRepresentation = (directory, old) => {
      const manifestPath = localPath(join(directory, 'manifest.json'));
      const manifest = readJson(manifestPath, 32768);
      if (manifest.account_id !== id || manifest.native_database_id !== profile.native_database_id) throw new Error('Fixture identity mismatch');
      const allowedGenerators = old ? [...LEGACY_R1_GENERATORS,
        ...(manifest.compatibility_catalog_revision === 1 ? [generatorHash] : [])] : [generatorHash];
      if (!allowedGenerators.includes(manifest.generator?.sha256)
          || manifest.native_descriptors?.sha256 !== hash(nativeBytes)) throw new Error('Fixture source migration required');
      if (old ? manifest.compatibility_catalog_revision !== undefined && manifest.compatibility_catalog_revision !== 1
        : manifest.compatibility_catalog_revision !== CATALOG_REVISION) throw new Error('Fixture catalogue revision mismatch');
      const files = {};
      for (const name of ['state.bin', 'shop.bin', 'dossier.bin']) {
        const rows = manifest.files?.filter(x => x.file === name);
        const bytes = readBounded(localPath(join(directory, name)), 16384);
        if (rows?.length !== 1 || rows[0].sha256 !== hash(bytes) || rows[0].bytes !== bytes.length) throw new Error('Fixture content mismatch');
        files[name] = hash(bytes);
      }
      const compat = readJson(localPath(join(directory, 'compatibility.json')), 4096);
      if (compat.account_id !== id || compat.native_database_id !== profile.native_database_id || compat.client_name !== profile.username) throw new Error('Fixture mapping mismatch');
      if (!old && compat.compatibility_catalog_revision !== CATALOG_REVISION) throw new Error('Fixture catalogue mapping mismatch');
      const profileBytes = readBounded(localPath(join(directory, 'profile-input.json')), 8192);
      if (manifest.profile_source?.file !== 'profile-input.json'
          || manifest.profile_source?.relative_to !== 'fixture_directory'
          || manifest.profile_source?.sha256 !== hash(profileBytes)) throw new Error('Fixture profile provenance mismatch');
      const persisted = JSON.parse(profileBytes.toString('utf8'));
      if (JSON.stringify(persisted) !== JSON.stringify(profile)) throw new Error('Fixture snapshot mismatch');
      return { manifest_sha256: hash(readBounded(manifestPath, 32768)), files,
        profile_sha256: hash(profileBytes) };
    };
    const previous = () => existsSync(legacy) ? { directory: 'r1', ...validateRepresentation(legacy, true) } : null;
    const validate = () => {
      const current = validateRepresentation(destination, false);
      const before = previous();
      const migration = readJson(localPath(join(destination, 'catalog-migration.json')), 4096);
      if (JSON.stringify(migration) !== JSON.stringify({ version: 1, catalog_revision: CATALOG_REVISION, previous: before })) throw new Error('Catalogue migration provenance changed');
      if (before && ['state.bin', 'dossier.bin'].some(name => current.files[name] !== before.files[name])) throw new Error('Catalogue migration changed account payload');
      return destination;
    };
    if (existsSync(destination)) return validate();
    if (creating.has(id)) return creating.get(id);
    if (creating.size >= 2) throw Object.assign(new Error('Generator busy'), { status: 503 });
    const task = (async () => {
      const before = previous(); // Refuse corrupt legacy data; never regenerate over it.
      const stage = localPath(join(fixtureRoot, id, `pending-${randomUUID()}`));
      mkdirSync(stage);
      try {
        const profileFile = join(stage, 'profile-input.json');
        writeFileSync(profileFile, JSON.stringify(profile), { flag: 'wx', mode: 0o600 });
        await runGenerator(options.python_executable, ['--out', stage, '--native-descriptors', nativePath, '--profile', profileFile,
          '--catalog-version', String(CATALOG_REVISION)]);
        const generated = validateRepresentation(stage, false);
        if (before && ['state.bin', 'dossier.bin'].some(name => generated.files[name] !== before.files[name])) throw new Error('Catalogue generation changed account payload');
        if (JSON.stringify(previous()) !== JSON.stringify(before)) throw new Error('Legacy fixture changed during catalogue generation');
        writeFileSync(join(stage, 'catalog-migration.json'), JSON.stringify({ version: 1, catalog_revision: CATALOG_REVISION, previous: before }), { flag: 'wx', mode: 0o600 });
        renameSync(stage, destination);
        return validate();
      } catch (error) {
        // Only this freshly allocated, checked local staging directory is removed.
        if (existsSync(stage)) rmSync(localPath(stage), { recursive: true, force: true });
        throw error;
      }
    })();
    creating.set(id, task);
    try { return await task; } finally { creating.delete(id); }
  }
  let active = 0;
  const pending = new Set();
  function json(res, status, value) {
    if (res.destroyed || res.writableEnded) return;
    const body = Buffer.from(JSON.stringify(value));
    res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Content-Length': body.length,
      'Cache-Control': 'no-store', Connection: 'close' });
    res.end(body);
  }
  async function body(req) {
    if (req.headers['content-type'] !== 'application/json' || req.headers['content-encoding']
        || req.headers['transfer-encoding'] || !/^\d{1,4}$/.test(req.headers['content-length'] || '')) throw Object.assign(new Error('Body shape'), { status: 400 });
    const length = Number(req.headers['content-length']);
    if (length < 2 || length > 2048) throw Object.assign(new Error('Body size'), { status: 413 });
    const parts = []; let bytes = 0;
    for await (const part of req) { bytes += part.length; if (bytes > length) throw Object.assign(new Error('Body size'), { status: 413 }); parts.push(part); }
    if (bytes !== length) throw Object.assign(new Error('Body size'), { status: 400 });
    try { return JSON.parse(Buffer.concat(parts).toString('utf8')); }
    catch { throw Object.assign(new Error('Body JSON'), { status: 400 }); }
  }
  async function request(req, res) {
    const expectedHost = `127.0.0.1:${server.address()?.port}`;
    if (req.socket.remoteAddress !== '127.0.0.1' || req.headers.host !== expectedHost || req.headers.origin) return json(res, 403, { error: 'forbidden' });
    if (req.method === 'GET' && req.url === '/health') return json(res, 200, { status: 'ok', scope: 'game-identity-bridge' });
    const authorization = req.headers.authorization;
    if (typeof authorization !== 'string' || !authorization.startsWith('Bearer ') || !equalToken(authorization.slice(7), secret)) return json(res, 403, { error: 'forbidden' });
    if (active >= 4) return json(res, 503, { error: 'busy' });
    active++;
    const timer = setTimeout(() => { json(res, 503, { error: 'timeout' }); req.destroy(); }, 4500);
    try {
      if (req.method === 'POST' && req.url === '/internal/native/login') {
        const value = await body(req);
        if (!value || Array.isArray(value) || Object.keys(value).sort().join(',') !== 'email,password'
            || typeof value.email !== 'string' || value.email.length > 1024 || typeof value.password !== 'string'
            || Buffer.byteLength(value.password) > 512) return json(res, 400, { error: 'invalid_request' });
        const email = emailField(value.email);
        if (!game.limit('bridge-global', 60, 60_000) || !game.limit(`login-email:${email || 'invalid'}`, 10, 15 * 60_000)) return json(res, 429, { error: 'rate_limited' });
        const user = email ? identity.findByEmail(email) : null;
        const eligible = validPassword(value.password);
        const matches = await verifyPassword(eligible ? value.password : 'invalid-password-input', user?.password_hash || dummyHash);
        if (!user || !eligible || !matches) return json(res, 401, { error: 'invalid_credentials' });
        if (res.destroyed || res.writableEnded) return;
        const profile = game.ensure(user);
        const directory = await fixture(profile);
        return json(res, 200, { account_id: user.id, native_database_id: profile.native_database_id,
          name: profile.username, fixture_dir: directory });
      }
      const matched = /^\/internal\/accounts\/([0-9a-f-]{36})\/overview$/.exec(req.url);
      if (req.method === 'GET' && matched && UUID.test(matched[1])) {
        if (!identity.profile(matched[1])) return json(res, 404, { error: 'account_not_found' });
        const profile = game.read(matched[1]);
        if ([2, 3, 4].includes(profile?.profile_version)) await fixture(profile);
        return json(res, 200, profile ? overview(profile) : empty('unlinked'));
      }
      return json(res, 404, { error: 'not_found' });
    } catch (error) {
      // Never expose/log request bodies, password hashes, account IDs or error details.
      const status = [400, 413, 503].includes(error.status) ? error.status : 503;
      json(res, status, { error: status === 503 ? 'unavailable' : 'invalid_request' });
    } finally { clearTimeout(timer); active--; }
  }
  const server = createServer({ maxHeaderSize: 4096 }, (req, res) => {
    const task = request(req, res).catch(() => json(res, 503, { error: 'unavailable' }));
    pending.add(task); void task.finally(() => pending.delete(task));
  });
  server.requestTimeout = 5000; server.headersTimeout = 3000; server.timeout = 5000;
  server.keepAliveTimeout = 1; server.maxRequestsPerSocket = 1; server.maxConnections = 16;
  await new Promise((done, fail) => { server.once('error', fail); server.listen(options.port, '127.0.0.1', done); })
    .catch(error => { identity.close(); game.close(); throw error; });
  let closing = null;
  return { server, port: server.address().port, close() {
    if (closing) return closing;
    closing = (async () => {
    const closed = new Promise(done => server.close(done)); server.closeAllConnections();
    await Promise.allSettled([...pending]); await closed; identity.close(); game.close();
    })();
    return closing;
  } };
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    if (process.argv.length !== 4 || process.argv[2] !== '--config') throw new Error('Use --config');
    const options = readJson(localPath(resolve(process.argv[3])), 8192);
    const bridge = await createIdentityBridge(options);
    console.log(JSON.stringify({ event: 'game_bridge_ready', host: '127.0.0.1', port: bridge.port, pid: process.pid }));
    let closing = false;
    const stop = async () => { if (closing) return; closing = true; await bridge.close(); };
    process.on('SIGINT', stop); process.on('SIGTERM', stop);
    process.on('message', value => { if (value === 'shutdown') stop(); });
  } catch { console.error('game_bridge_start_failed: configuration_or_storage'); process.exitCode = 1; }
}
