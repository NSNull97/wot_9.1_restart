import { DatabaseSync } from 'node:sqlite';
import { readFileSync, mkdirSync } from 'node:fs';
import { dirname } from 'node:path';
import { randomUUID } from 'node:crypto';
import { digest, token, emailField, nicknameField } from './security.mjs';

export const ANON_TTL = 30 * 60 * 1000;
export const AUTH_TTL = 8 * 60 * 60 * 1000;

/** Read the existing identity registry without migration, sessions or writes. */
export function openIdentityReader(path) {
  const db = new DatabaseSync(path, { readOnly: true });
  db.exec('PRAGMA query_only = ON; PRAGMA busy_timeout = 1000;');
  if (db.prepare('PRAGMA user_version').get().user_version !== 2) {
    db.close();
    throw new Error('Identity database must be initialized by the website');
  }
  const byEmail = db.prepare('SELECT id, username, display_nickname, email, password_hash, created_at FROM users WHERE email = ?');
  const byId = db.prepare('SELECT id, username, display_nickname, created_at FROM users WHERE id = ?');
  return { findByEmail: email => byEmail.get(email), profile: id => byId.get(id), close: () => db.close() };
}

/** Explicit one-time binding; also used by the local owner CLI, never migration. */
export function bindEmail(db, id, email, stamp = Date.now()) {
  if (typeof email !== 'string' || !emailField(email) || emailField(email) !== email) throw new Error('Canonical email required');
  db.exec('BEGIN IMMEDIATE');
  try {
    const row = db.prepare('SELECT email FROM users WHERE id=?').get(id);
    if (!row) throw Object.assign(new Error('Account not found'), { code: 'account_not_found' });
    if (row.email !== null && row.email !== email) throw Object.assign(new Error('Email already bound'), { code: 'already_bound' });
    const other = db.prepare('SELECT id FROM users WHERE email=?').get(email);
    if (other && other.id !== id) throw Object.assign(new Error('Email occupied'), { code: 'email_taken' });
    if (row.email === null) db.prepare('UPDATE users SET email=?,updated_at=? WHERE id=?').run(email, stamp, id);
    db.exec('COMMIT');
    return { changed: row.email === null };
  } catch (error) { db.exec('ROLLBACK'); throw error; }
}

export function openStore(path, now = Date.now) {
  mkdirSync(dirname(path), { recursive: true });
  const db = new DatabaseSync(path);
  db.exec('PRAGMA foreign_keys = ON; PRAGMA journal_mode = WAL; PRAGMA busy_timeout = 5000;');
  const version = db.prepare('PRAGMA user_version').get().user_version;
  if (version > 2) { db.close(); throw new Error('Unsupported database version'); }
  let migrationBackup = null;
  if (version === 1) {
    // A consistent SQLite snapshot includes WAL content; copying only .sqlite does not.
    migrationBackup = `${path}.pre-v2-${randomUUID()}.sqlite`;
    try { db.prepare('VACUUM INTO ?').run(migrationBackup); }
    catch (error) { db.close(); throw error; }
  }
  if (version === 0) {
    db.exec('BEGIN IMMEDIATE');
    try {
      db.exec(readFileSync(new URL('../migrations/001_web_profile.sql', import.meta.url), 'utf8'));
      db.exec('COMMIT');
    } catch (error) { db.exec('ROLLBACK'); db.close(); throw error; }
  }
  if (version < 2) {
    db.exec('BEGIN IMMEDIATE');
    try {
      db.exec(readFileSync(new URL('../migrations/002_email_nickname.sql', import.meta.url), 'utf8'));
      db.exec('COMMIT');
    } catch (error) { db.exec('ROLLBACK'); db.close(); throw error; }
  }
  const sql = text => db.prepare(text);
  const publicColumns = 'id, username, display_nickname, email, display_name, bio, created_at, updated_at, last_login_at';
  const store = {
    db,
    migrationBackup,
    close() { db.close(); },
    findUser(username) { return sql('SELECT * FROM users WHERE username = ?').get(username); },
    findByEmail(email) { return sql('SELECT * FROM users WHERE email = ?').get(email); },
    passwordRecord(id) { return sql('SELECT password_hash FROM users WHERE id=?').get(id); },
    profile(id) { return sql(`SELECT ${publicColumns} FROM users WHERE id = ?`).get(id); },
    createUser({ nickname, email, displayName, passwordHash }) {
      const checked = nicknameField(nickname?.display);
      if (!checked || checked.key !== nickname.key || checked.display !== nickname.display
          || typeof email !== 'string' || !emailField(email) || emailField(email) !== email) throw new Error('Canonical registration fields required');
      const id = randomUUID();
      const stamp = now();
      sql('INSERT INTO users (id, username, display_nickname, email, display_name, password_hash, created_at, updated_at, last_login_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)')
        .run(id, nickname.key, nickname.display, email, displayName, passwordHash, stamp, stamp, stamp);
      return store.profile(id);
    },
    bindEmail(id, email) { return bindEmail(db, id, email, now()); },
    updateProfile(id, displayName, bio) {
      return sql('UPDATE users SET display_name = ?, bio = ?, updated_at = ? WHERE id = ?').run(displayName, bio, now(), id).changes;
    },
    login(id) { sql('UPDATE users SET last_login_at = ? WHERE id = ?').run(now(), id); },
    session(raw) {
      if (!raw) return null;
      return sql('SELECT * FROM sessions WHERE token_hash = ? AND expires_at > ?').get(digest(raw), now());
    },
    createSession(userId = null, previous = null) {
      const raw = token();
      const csrf = token();
      const createdAt = now();
      const ttl = userId ? AUTH_TTL : ANON_TTL;
      db.exec('BEGIN IMMEDIATE');
      try {
        if (previous) sql('DELETE FROM sessions WHERE token_hash = ?').run(previous);
        sql('INSERT INTO sessions VALUES (?, ?, ?, ?, ?)').run(digest(raw), userId, csrf, createdAt, createdAt + ttl);
        // At most five simultaneous authenticated sessions per profile.
        if (userId) sql('DELETE FROM sessions WHERE user_id = ? AND token_hash NOT IN (SELECT token_hash FROM sessions WHERE user_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 5)').run(userId, userId);
        db.exec('COMMIT');
      } catch (error) { db.exec('ROLLBACK'); throw error; }
      return { raw, csrf, ttl, token_hash: digest(raw), user_id: userId };
    },
    revokeSession(hash) { sql('DELETE FROM sessions WHERE token_hash = ?').run(hash); },
    limit(key, maximum, windowMs) {
      const stamp = now();
      const hash = digest(key);
      // One atomic statement also keeps concurrent requests/restarts inside the limit.
      const row = sql(`INSERT INTO rate_limits VALUES (?, 1, ?)
        ON CONFLICT(key_hash) DO UPDATE SET
          hits = CASE WHEN resets_at <= ? THEN 1 ELSE min(hits + 1, ?) END,
          resets_at = CASE WHEN resets_at <= ? THEN excluded.resets_at ELSE resets_at END
        RETURNING hits, resets_at`).get(hash, stamp + windowMs, stamp, maximum + 1, stamp);
      return { allowed: row.hits <= maximum, retryAfter: Math.max(1, Math.ceil((row.resets_at - stamp) / 1000)) };
    },
    cleanup() {
      sql('DELETE FROM sessions WHERE expires_at <= ?').run(now());
      sql('DELETE FROM rate_limits WHERE resets_at <= ?').run(now());
    },
  };
  store.cleanup();
  return store;
}
