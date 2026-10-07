/**
 * Authoritative account service for the opt-in infrastructure boundary.
 * It owns account credentials, browser sessions and account profile fields.
 * The legacy website and native bridge deliberately do not use this entrypoint
 * until a separately accepted migration switches their configuration.
 */
import { createServer } from 'node:http';
import { DatabaseSync } from 'node:sqlite';
import { existsSync, mkdirSync, readFileSync, realpathSync, statSync } from 'node:fs';
import { dirname, isAbsolute, relative, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { randomUUID, timingSafeEqual } from 'node:crypto';
import {
  IDENTITY_CONTRACT, assertOperation, errorEnvelope, responseEnvelope, statusFor,
} from '../contracts/identity.mjs';
import {
  digest, emailField, hashPassword, nicknameField, token, validPassword,
  validToken, verifyPassword,
} from './security.mjs';
import { IDENTITY_MIGRATIONS, IDENTITY_SCHEMA_VERSION } from './schema.mjs';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const LOCAL = resolve(ROOT, 'local');
const ANON_TTL = 30 * 60 * 1000;
const AUTH_TTL = 8 * 60 * 60 * 1000;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const DUMMY_HASH = 'scrypt$v1$131072$8$1$00000000000000000000000000000000$'
  + '00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000';

function isInside(root, path) {
  const rel = relative(root, path);
  return rel === '' || (!rel.startsWith('..') && !isAbsolute(rel));
}

function localPath(value, { createParent = false } = {}) {
  if (typeof value !== 'string' || !isAbsolute(value)) throw new Error('Identity database path must be absolute');
  const path = resolve(value);
  if (!isInside(LOCAL, path)) throw new Error('Identity database must stay in local/');
  let ancestor = path;
  while (!existsSync(ancestor)) ancestor = dirname(ancestor);
  if (!isInside(realpathSync(LOCAL), realpathSync(ancestor))) throw new Error('Redirected identity path');
  if (createParent) mkdirSync(dirname(path), { recursive: true });
  return path;
}

function exact(value, keys) {
  return value && typeof value === 'object' && !Array.isArray(value)
    && Object.keys(value).sort().join(',') === [...keys].sort().join(',');
}

function constantEqual(left, right) {
  if (typeof left !== 'string' || typeof right !== 'string') return false;
  const a = Buffer.from(left); const b = Buffer.from(right);
  return a.length === b.length && timingSafeEqual(a, b);
}

function textField(value, min, max) {
  if (typeof value !== 'string') return null;
  const clean = value.normalize('NFC').trim();
  if ([...clean].length < min || [...clean].length > max || /[\p{Cc}\p{Cf}]/u.test(clean)) return null;
  return clean;
}

function profile(row) {
  return {
    account_id: row.account_id, nickname: row.nickname, nickname_key: row.nickname_key,
    email: row.email, display_name: row.display_name, bio: row.bio,
    created_at: row.created_at, updated_at: row.updated_at,
  };
}

function ensureProfile(row) {
  if (!row || !UUID.test(row.account_id)) throw new Error('Stored account identity invalid');
  return profile(row);
}

function sessionValue(row, account, raw = row.raw) {
  return {
    session_token: raw,
    csrf: row.csrf,
    expires_at: row.expires_at,
    profile: account ? ensureProfile(account) : null,
  };
}

function readJson(path, maximum = 8192) {
  const absolute = localPath(resolve(path));
  const stat = statSync(absolute);
  if (!stat.isFile() || stat.size > maximum) throw new Error('Identity configuration bound');
  const bytes = readFileSync(absolute);
  if (bytes.length > maximum) throw new Error('Identity configuration grew');
  return JSON.parse(bytes.toString('utf8'));
}

function openDatabase(path, now) {
  const db = new DatabaseSync(localPath(path, { createParent: true }));
  db.exec('PRAGMA foreign_keys = ON; PRAGMA journal_mode = WAL; PRAGMA busy_timeout = 5000;');
  const version = db.prepare('PRAGMA user_version').get().user_version;
  if (!Number.isInteger(version) || version > IDENTITY_SCHEMA_VERSION) {
    db.close(); throw new Error('Unsupported identity database version');
  }
  try {
    for (const migration of IDENTITY_MIGRATIONS.filter(item => item.version > version)) {
      db.exec('BEGIN IMMEDIATE');
      try {
        db.exec(migration.sql);
        db.prepare('INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)')
          .run(migration.version, now());
        db.exec(`PRAGMA user_version = ${migration.version};`);
        db.exec('COMMIT');
      } catch (error) { db.exec('ROLLBACK'); throw error; }
    }
    const applied = db.prepare('SELECT version FROM schema_migrations ORDER BY version').all();
    if (applied.length !== IDENTITY_SCHEMA_VERSION || applied.at(-1).version !== IDENTITY_SCHEMA_VERSION) {
      throw new Error('Identity migration ledger mismatch');
    }
    return db;
  } catch (error) { db.close(); throw error; }
}

function createStore(databasePath, now) {
  const db = openDatabase(databasePath, now);
  const stmt = sql => db.prepare(sql);
  const store = {
    db,
    close: () => db.close(),
    userByEmail(email) { return stmt('SELECT * FROM accounts WHERE email=?').get(email); },
    userById(id) { return stmt('SELECT * FROM accounts WHERE account_id=?').get(id); },
    userByNickname(key) { return stmt('SELECT account_id FROM accounts WHERE nickname_key=?').get(key); },
    session(raw) {
      if (!validToken(raw)) return null;
      const row = stmt('SELECT * FROM sessions WHERE token_hash=? AND expires_at>?').get(digest(raw), now());
      if (!row) return null;
      const user = row.account_id ? store.userById(row.account_id) : null;
      if (row.account_id && !user) return null;
      return { ...row, raw, user };
    },
    issueSession(accountId = null) {
      const raw = token(); const csrf = token(); const created = now();
      const expires = created + (accountId ? AUTH_TTL : ANON_TTL);
      stmt('INSERT INTO sessions(token_hash,account_id,csrf,created_at,expires_at) VALUES (?,?,?,?,?)')
        .run(digest(raw), accountId, csrf, created, expires);
      if (accountId) stmt(`DELETE FROM sessions WHERE account_id=? AND token_hash NOT IN
        (SELECT token_hash FROM sessions WHERE account_id=? ORDER BY created_at DESC, rowid DESC LIMIT 5)`)
        .run(accountId, accountId);
      return { raw, csrf, expires_at: expires };
    },
    rotate(row, accountId) {
      db.exec('BEGIN IMMEDIATE');
      try {
        stmt('DELETE FROM sessions WHERE token_hash=?').run(row.token_hash);
        const next = store.issueSession(accountId);
        db.exec('COMMIT');
        return next;
      } catch (error) { db.exec('ROLLBACK'); throw error; }
    },
    createUser({ nickname, email, displayName, passwordHash }) {
      const id = randomUUID(); const stamp = now();
      stmt(`INSERT INTO accounts(account_id,nickname_key,nickname,email,display_name,bio,password_hash,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?)`).run(id, nickname.key, nickname.display, email, displayName, '', passwordHash, stamp, stamp);
      return store.userById(id);
    },
    updateProfile(id, displayName, bio) {
      const updated = now();
      stmt('UPDATE accounts SET display_name=?,bio=?,updated_at=? WHERE account_id=?').run(displayName, bio, updated, id);
      return store.userById(id);
    },
    revoke(row) { stmt('DELETE FROM sessions WHERE token_hash=?').run(row.token_hash); },
    limit(key, maximum, windowMs) {
      const stamp = now(); const hash = digest(key);
      const row = stmt(`INSERT INTO rate_limits(key_hash,hits,resets_at) VALUES(?,?,?)
        ON CONFLICT(key_hash) DO UPDATE SET
          hits=CASE WHEN resets_at<=? THEN 1 ELSE min(hits+1,?) END,
          resets_at=CASE WHEN resets_at<=? THEN excluded.resets_at ELSE resets_at END
        RETURNING hits,resets_at`).get(hash, 1, stamp + windowMs, stamp, maximum + 1, stamp);
      return { allowed: row.hits <= maximum, retryAfter: Math.max(1, Math.ceil((row.resets_at - stamp) / 1000)) };
    },
    cleanup() {
      stmt('DELETE FROM sessions WHERE expires_at<=?').run(now());
      stmt('DELETE FROM rate_limits WHERE resets_at<=?').run(now());
    },
  };
  store.cleanup();
  return store;
}

function configTokens(value) {
  if (!value || typeof value !== 'object' || !validToken(value.portal) || !validToken(value.game)) {
    throw new Error('Identity service tokens are required for both roles');
  }
  return { portal: value.portal, game: value.game };
}

function requestBody(req) {
  if (req.headers['content-type'] !== 'application/json' || req.headers['content-encoding']
      || req.headers['transfer-encoding'] || !/^\d{1,5}$/.test(req.headers['content-length'] || '')) {
    throw Object.assign(new Error('Invalid identity request framing'), { code: 'invalid_request' });
  }
  const length = Number(req.headers['content-length']);
  if (length < 2 || length > 16384) throw Object.assign(new Error('Identity request size'), { code: 'invalid_request' });
  return new Promise((resolveBody, reject) => {
    const chunks = []; let bytes = 0;
    req.on('data', chunk => {
      bytes += chunk.length;
      if (bytes > length || bytes > 16384) { req.destroy(); reject(Object.assign(new Error('Identity request size'), { code: 'invalid_request' })); return; }
      chunks.push(chunk);
    });
    req.on('end', () => {
      if (bytes !== length) return reject(Object.assign(new Error('Identity request length'), { code: 'invalid_request' }));
      try { resolveBody(JSON.parse(Buffer.concat(chunks).toString('utf8'))); }
      catch { reject(Object.assign(new Error('Identity JSON'), { code: 'invalid_request' })); }
    });
    req.on('error', error => reject(Object.assign(error, { code: 'unavailable' })));
  });
}

export function createIdentityService({ databasePath, port = 0, host = '127.0.0.1', tokens, now = Date.now } = {}) {
  if (host !== '127.0.0.1' || !Number.isInteger(port) || port < 0 || port > 65535) throw new Error('Identity listener must be loopback');
  const serviceTokens = configTokens(tokens);
  const store = createStore(databasePath, now);
  const server = createServer({ maxHeaderSize: 4096 }, (req, res) => {
    void handle(req, res).catch(() => reply(res, 503, 'unavailable', null));
  });
  server.requestTimeout = 5000; server.headersTimeout = 3000; server.timeout = 5000;
  server.keepAliveTimeout = 1; server.maxRequestsPerSocket = 1; server.maxConnections = 32;
  let closed = false; let closing = null;

  function reply(res, status, code, data, operation = null) {
    if (res.destroyed || res.writableEnded) return;
    const body = Buffer.from(JSON.stringify(code ? errorEnvelope(operation || 'session/read', code) : responseEnvelope(operation, data)));
    res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Content-Length': body.length, Connection: 'close', 'Cache-Control': 'no-store' });
    res.end(body);
  }

  async function handle(req, res) {
    const expectedHost = `127.0.0.1:${server.address()?.port}`;
    if (req.socket.remoteAddress !== '127.0.0.1' || req.headers.host !== expectedHost || req.headers.origin) return reply(res, 403, 'forbidden', null, 'session/read');
    const match = /^\/identity\/v1\/([^?]+)$/.exec(req.url || '');
    if (req.method !== 'POST' || !match) return reply(res, 404, 'invalid_request', null, 'session/read');
    let operation;
    try { operation = decodeURIComponent(match[1]); assertOperation(operation); }
    catch { return reply(res, 400, 'invalid_request', null, 'session/read'); }
    const role = req.headers['x-identity-role'];
    if (!['portal', 'game'].includes(role) || !constantEqual(req.headers.authorization?.startsWith('Bearer ') ? req.headers.authorization.slice(7) : '', serviceTokens[role])) {
      return reply(res, 403, 'forbidden', null, operation);
    }
    if (role === 'portal' && operation === 'credentials/verify' || role === 'game' && operation !== 'credentials/verify') {
      return reply(res, 403, 'forbidden', null, operation);
    }
    let envelope;
    try { envelope = await requestBody(req); }
    catch (error) { return reply(res, statusFor(error.code || 'invalid_request'), error.code || 'invalid_request', null, operation); }
    if (!envelope || envelope.contract !== IDENTITY_CONTRACT || envelope.operation !== operation
        || !envelope.payload || typeof envelope.payload !== 'object' || Array.isArray(envelope.payload)) {
      return reply(res, 409, 'contract_mismatch', null, operation);
    }
    try {
      const data = await operationHandler(operation, envelope.payload, role);
      reply(res, 200, null, data, operation);
    } catch (error) {
      const code = ['invalid_request', 'invalid_fields', 'invalid_credentials', 'invalid_session', 'forbidden',
        'email_taken', 'nickname_taken', 'rate_limited', 'unavailable', 'contract_mismatch'].includes(error.code)
        ? error.code : 'unavailable';
      reply(res, statusFor(code), code, null, operation);
    }
  }

  async function operationHandler(operation, payload, role) {
    const requireKeys = (keys) => { if (!exact(payload, keys)) throw Object.assign(new Error('Payload keys'), { code: 'invalid_request' }); };
    const session = raw => {
      const row = store.session(raw);
      if (!row) throw Object.assign(new Error('Session invalid'), { code: 'invalid_session' });
      return row;
    };
    const csrfSession = (keys) => {
      requireKeys(keys); const row = session(payload.session_token);
      if (!constantEqual(payload.csrf, row.csrf)) throw Object.assign(new Error('CSRF invalid'), { code: 'invalid_session' });
      return row;
    };
    if (operation === 'session/open') {
      requireKeys(['session_token']);
      if (payload.session_token !== null) return sessionValue(session(payload.session_token), session(payload.session_token).user);
      const issued = store.issueSession();
      return { session_token: issued.raw, csrf: issued.csrf, expires_at: issued.expires_at, profile: null };
    }
    if (operation === 'session/read') {
      requireKeys(['session_token']); const row = session(payload.session_token);
      return sessionValue(row, row.user);
    }
    if (operation === 'session/revoke') {
      const row = csrfSession(['session_token', 'csrf']); store.revoke(row); return { revoked: true };
    }
    if (operation === 'register') {
      const row = csrfSession(['session_token', 'csrf', 'email', 'nickname', 'display_name', 'password']);
      if (row.account_id) throw Object.assign(new Error('Already authenticated'), { code: 'invalid_session' });
      if (!store.limit('register:global', 20, 60 * 60_000).allowed) throw Object.assign(new Error('Rate'), { code: 'rate_limited' });
      const email = emailField(payload.email); const nickname = nicknameField(payload.nickname);
      const displayName = textField(payload.display_name ?? nickname?.display, 2, 48);
      if (!email || !nickname || !displayName || !validPassword(payload.password)) throw Object.assign(new Error('Fields'), { code: 'invalid_fields' });
      if (store.userByEmail(email)) throw Object.assign(new Error('Email'), { code: 'email_taken' });
      if (store.userByNickname(nickname.key)) throw Object.assign(new Error('Nickname'), { code: 'nickname_taken' });
      const passwordHash = await hashPassword(payload.password);
      if (store.userByEmail(email)) throw Object.assign(new Error('Email'), { code: 'email_taken' });
      if (store.userByNickname(nickname.key)) throw Object.assign(new Error('Nickname'), { code: 'nickname_taken' });
      const user = store.createUser({ nickname, email, displayName, passwordHash });
      const issued = store.rotate(row, user.account_id);
      return { ...sessionValue({ ...issued, raw: issued.raw }, user, issued.raw), profile: ensureProfile(user) };
    }
    if (operation === 'login') {
      const row = csrfSession(['session_token', 'csrf', 'email', 'password']);
      if (!store.limit(`login:ipless:${payload.email}`, 10, 15 * 60_000).allowed) throw Object.assign(new Error('Rate'), { code: 'rate_limited' });
      const email = emailField(payload.email); const user = email ? store.userByEmail(email) : null;
      const matches = await verifyPassword(validPassword(payload.password) ? payload.password : 'invalid-password-input', user?.password_hash || DUMMY_HASH);
      if (!email || !user || !validPassword(payload.password) || !matches) throw Object.assign(new Error('Credentials'), { code: 'invalid_credentials' });
      const issued = store.rotate(row, user.account_id);
      return { ...sessionValue({ ...issued, raw: issued.raw }, user, issued.raw), profile: ensureProfile(user) };
    }
    if (operation === 'profile/update') {
      const row = csrfSession(['session_token', 'csrf', 'display_name', 'bio']);
      if (!row.account_id) throw Object.assign(new Error('Auth required'), { code: 'invalid_session' });
      const displayName = textField(payload.display_name, 2, 48); const bio = textField(payload.bio, 0, 240);
      if (!displayName || bio === null) throw Object.assign(new Error('Fields'), { code: 'invalid_fields' });
      return { profile: ensureProfile(store.updateProfile(row.account_id, displayName, bio)) };
    }
    if (operation === 'credentials/verify') {
      if (role !== 'game') throw Object.assign(new Error('Role'), { code: 'forbidden' });
      requireKeys(['email', 'password']);
      if (!store.limit('game:global', 60, 60_000).allowed) throw Object.assign(new Error('Rate'), { code: 'rate_limited' });
      const email = emailField(payload.email); const user = email ? store.userByEmail(email) : null;
      const matches = await verifyPassword(validPassword(payload.password) ? payload.password : 'invalid-password-input', user?.password_hash || DUMMY_HASH);
      if (!email || !user || !validPassword(payload.password) || !matches) throw Object.assign(new Error('Credentials'), { code: 'invalid_credentials' });
      return { account_id: user.account_id, nickname: user.nickname, created_at: user.created_at };
    }
    throw Object.assign(new Error('Operation'), { code: 'invalid_request' });
  }

  return new Promise((resolveService, rejectService) => {
    server.once('error', rejectService);
    server.listen(port, host, () => {
      server.removeListener('error', rejectService);
      resolveService({
        server, port: server.address().port, host, contract: IDENTITY_CONTRACT, schemaVersion: IDENTITY_SCHEMA_VERSION,
        store,
        async close() {
          if (closing) return closing;
          closed = true;
          closing = new Promise(done => server.close(() => { store.close(); done(); }));
          server.closeAllConnections();
          return closing;
        },
      });
    });
  }).catch(error => { if (!closed) store.close(); throw error; });
}

export function readIdentityConfiguration(path) {
  const config = readJson(path);
  if (!config || config.version !== 1 || config.host !== '127.0.0.1'
      || !Number.isInteger(config.port) || config.port < 0 || config.port > 65535
      || typeof config.database_path !== 'string') throw new Error('Unsupported identity configuration');
  config.tokens = configTokens(config.tokens);
  config.database_path = localPath(resolve(config.database_path));
  return config;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    if (process.argv.length !== 4 || process.argv[2] !== '--config') throw new Error('Use --config');
    const service = await createIdentityService(readIdentityConfiguration(process.argv[3]));
    console.log(JSON.stringify({ event: 'identity_account_ready', host: service.host, port: service.port, contract: service.contract, schemaVersion: service.schemaVersion }));
    let stopping = false;
    const stop = async () => { if (stopping) return; stopping = true; await service.close(); };
    process.on('SIGINT', stop); process.on('SIGTERM', stop); process.on('message', message => { if (message === 'shutdown') stop(); });
  } catch { console.error('identity_account_start_failed: configuration_or_storage'); process.exitCode = 1; }
}
