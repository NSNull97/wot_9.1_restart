/** Append-only identity schema migrations. Each migration runs in one transaction. */
export const IDENTITY_SCHEMA_VERSION = 1;
export const IDENTITY_MIGRATIONS = [
  {
    version: 1,
    sql: `
      CREATE TABLE accounts (
        account_id TEXT PRIMARY KEY,
        nickname_key TEXT NOT NULL UNIQUE,
        nickname TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        display_name TEXT NOT NULL,
        bio TEXT NOT NULL DEFAULT '',
        password_hash TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL
      ) STRICT;
      CREATE TABLE sessions (
        token_hash TEXT PRIMARY KEY,
        account_id TEXT REFERENCES accounts(account_id) ON DELETE CASCADE,
        csrf TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        expires_at INTEGER NOT NULL
      ) STRICT;
      CREATE INDEX sessions_account ON sessions(account_id);
      CREATE INDEX sessions_expiry ON sessions(expires_at);
      CREATE TABLE rate_limits (
        key_hash TEXT PRIMARY KEY,
        hits INTEGER NOT NULL,
        resets_at INTEGER NOT NULL
      ) STRICT;
      CREATE INDEX rate_limits_expiry ON rate_limits(resets_at);
      CREATE TABLE schema_migrations (
        version INTEGER PRIMARY KEY,
        applied_at INTEGER NOT NULL
      ) STRICT;
    `,
  },
];
