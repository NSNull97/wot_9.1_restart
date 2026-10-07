CREATE TABLE users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    bio TEXT NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    last_login_at INTEGER NOT NULL
) STRICT;

CREATE TABLE sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
    csrf TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL
) STRICT;
CREATE INDEX sessions_expiry ON sessions(expires_at);
CREATE INDEX sessions_user ON sessions(user_id);

CREATE TABLE rate_limits (
    key_hash TEXT PRIMARY KEY,
    hits INTEGER NOT NULL,
    resets_at INTEGER NOT NULL
) STRICT;
CREATE INDEX rate_limits_expiry ON rate_limits(resets_at);
PRAGMA user_version = 1;
