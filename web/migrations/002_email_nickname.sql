-- Existing IDs, hashes, sessions and nickname keys remain byte-for-byte intact.
-- Missing email is intentional: an owner must explicitly bind it.
ALTER TABLE users ADD COLUMN email TEXT;
ALTER TABLE users ADD COLUMN display_nickname TEXT NOT NULL DEFAULT '';
UPDATE users SET display_nickname = username;
CREATE UNIQUE INDEX users_email ON users(email);
PRAGMA user_version = 2;
