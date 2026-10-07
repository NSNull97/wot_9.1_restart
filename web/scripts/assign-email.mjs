/** Local owner operation. Exact UUID and email come from a private JSON file. */
import { DatabaseSync } from 'node:sqlite';
import { readFileSync, realpathSync, statSync } from 'node:fs';
import { resolve, relative, isAbsolute } from 'node:path';
import { fileURLToPath } from 'node:url';
import { bindEmail } from '../src/store.mjs';
import { emailField } from '../src/security.mjs';

const local = realpathSync(fileURLToPath(new URL('../../local/', import.meta.url)));
function ownFile(value, maximum) {
  const path = realpathSync(resolve(value));
  const rel = relative(local, path);
  if (!rel || rel.startsWith('..') || isAbsolute(rel) || !statSync(path).isFile()
      || statSync(path).size > maximum) throw new Error('local_file_required');
  return path;
}
let db;
try {
  if (process.argv.length !== 6 || process.argv[2] !== '--database' || process.argv[4] !== '--input') throw new Error('arguments');
  const database = ownFile(process.argv[3], 1024 * 1024 * 1024);
  const value = JSON.parse(readFileSync(ownFile(process.argv[5], 4096), 'utf8'));
  if (!value || Array.isArray(value) || Object.keys(value).sort().join(',') !== 'account_id,email'
      || !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(value.account_id)) throw new Error('input');
  const email = emailField(value.email);
  if (!email) throw new Error('email');
  db = new DatabaseSync(database);
  db.exec('PRAGMA busy_timeout=1000');
  if (db.prepare('PRAGMA user_version').get().user_version !== 2) throw new Error('website_migration_required');
  const result = bindEmail(db, value.account_id, email);
  console.log(JSON.stringify({ status: 'PASS', operation: 'bind_existing_account_email', changed: result.changed }));
} catch (error) {
  const known = ['account_not_found', 'already_bound', 'email_taken'];
  console.error(JSON.stringify({ status: 'FAIL', operation: 'bind_existing_account_email',
    reason: known.includes(error.code) ? error.code : 'invalid_arguments_or_storage' }));
  process.exitCode = 1;
} finally { db?.close(); }
