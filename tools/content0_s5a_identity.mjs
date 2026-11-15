// Internal helper for content0_s5a_operator_bootstrap.py. Never prints credentials.
import { openStore } from '../web/src/store.mjs';
import { hashPassword, verifyPassword, token, nicknameField } from '../web/src/security.mjs';
import { writeFileSync } from 'node:fs';
import { join } from 'node:path';

export async function createIdentity(stand) {
  const secret = token();
  const suffix = token().slice(0, 12).toLowerCase().replace(/[^a-z0-9]/g, 'x');
  const nick = 'op' + suffix, email = nick + '@example.test';
  const hash = await hashPassword(secret);
  if (!await verifyPassword(secret, hash)) throw Error('credential hash verification failed');
  const db = openStore(join(stand, 'web.sqlite'));
  db.db.exec('BEGIN IMMEDIATE');
  try {
    const user = db.createUser({nickname: nicknameField(nick), email, displayName:nick, passwordHash:hash});
    writeFileSync(join(stand, 'private-operator', 'credentials.json'), JSON.stringify({
      schema:'content0-s5a-operator-credentials.v1',account_id:user.id,email,password:secret
    }) + '\n', {mode:0o600, flag:'wx'});
    db.db.exec('COMMIT');
    return user.id;
  } catch (error) {
    db.db.exec('ROLLBACK');
    throw error;
  } finally { db.close(); }
}
