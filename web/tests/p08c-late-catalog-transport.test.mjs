/** Unit-only subprocess argv probe. Acceptance must use the real late worker. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync, realpathSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { testDirectory } from './helpers.mjs';
import { CATALOG_SHA256 } from '../src/catalog-v1.mjs';
import { createLateResultService, LATE_CONTRACT } from '../src/p08c-late-results.mjs';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const ACCOUNT = '12345678-1234-4234-8234-123456789000';
const request = { version: 1, contract: LATE_CONTRACT, operation: 'pending', account_id: ACCOUNT,
  native_database_id: 1, command_key: 'late:catalog:probe', after_arena_id: null };

test('legacy and CAT subprocess argv differ only by the pinned catalog flag', { timeout: 30000 }, async () => {
  const directory = testDirectory();
  // This worker only records argv and fails; it cannot produce an acceptance PASS.
  const worker = join(directory, 'argv-probe.py');
  writeFileSync(worker, [
    'import json, pathlib, sys',
    'args = sys.argv[1:]',
    'database = pathlib.Path(args[args.index("--database") + 1])',
    'database.with_suffix(".argv.json").write_text(json.dumps(args), encoding="utf8")',
    'sys.stdin.buffer.read()',
    'sys.exit(1)',
    '',
  ].join('\n'), { flag: 'wx' });
  const detected = spawnSync('python', ['-B', '-c', 'import sys;print(sys.executable)'], { encoding: 'utf8', timeout: 10000 });
  assert.equal(detected.status, 0);
  const python = realpathSync(detected.stdout.trim());
  const common = { originalRoot: ROOT, accountId: ACCOUNT, shellCatalog: join(ROOT, 'tests/fixtures/p06t-shell-catalog.json'),
    terminalPolicy: join(ROOT, 'tests/fixtures/p06t-device-policy.json'), loss: true, python, worker, cwd: ROOT };
  async function probe(name, pin) {
    const database = join(directory, `${name}.sqlite`);
    writeFileSync(database, '', { flag: 'wx' });
    const service = createLateResultService({ ...common, database, ...(pin === undefined ? {} : { catalogSha256: pin }) });
    await assert.rejects(service.pending(request), /Late result worker unavailable/);
    return JSON.parse(readFileSync(database.replace(/\.sqlite$/, '.argv.json'), 'utf8'));
  }
  const legacy = await probe('legacy');
  const catalog = await probe('catalog', CATALOG_SHA256);
  assert.equal(legacy.includes('--catalog-sha256'), false);
  const at = catalog.indexOf('--catalog-sha256');
  assert.ok(at >= 0);
  assert.equal(catalog[at + 1], CATALOG_SHA256);
  assert.equal(catalog.lastIndexOf('--catalog-sha256'), at);
  const withoutPin = catalog.filter((_, index) => index !== at && index !== at + 1);
  // The database filename is the only other intentional difference.
  legacy[legacy.indexOf('--database') + 1] = '<own-db>';
  withoutPin[withoutPin.indexOf('--database') + 1] = '<own-db>';
  assert.deepEqual(withoutPin, legacy);
  const wrongDb = join(directory, 'wrong.sqlite');
  writeFileSync(wrongDb, '', { flag: 'wx' });
  assert.throws(() => createLateResultService({ ...common, database: wrongDb, catalogSha256: '0'.repeat(64) }), /trusted catalog pin/);
  assert.equal(existsSync(wrongDb.replace(/\.sqlite$/, '.argv.json')), false);
});
