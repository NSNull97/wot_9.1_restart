import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { copyFileSync, mkdirSync, readFileSync, writeFileSync, renameSync, symlinkSync, unlinkSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { checkNativeEvidenceProof } from '../src/native-evidence.mjs';
import { testDirectory, removeTestDirectory } from './helpers.mjs';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const sha = raw => createHash('sha256').update(raw).digest('hex');
const save = (path, value) => writeFileSync(path, JSON.stringify(value, null, 2) + '\n');
function fixture(t, kind = 'crew') {
  const directory = testDirectory(); t.after(() => removeTestDirectory(directory));
  const name = `native-ms1-${kind}-export01.json`;
  const source = resolve(ROOT, `local/evidence/20261005-p02-ms1-${kind}`, name);
  const path = join(directory, name), sidecar = path + '.relocation.json';
  const manifest = JSON.parse(readFileSync(source + '.relocation.json', 'utf8'));
  copyFileSync(source, path); copyFileSync(source + '.relocation.json', sidecar);
  for (const row of manifest.files) {
    const target = join(directory, row.file); mkdirSync(dirname(target), { recursive: true });
    copyFileSync(join(dirname(source), row.file), target);
  }
  return { directory, path, sidecar, manifest, check: () => checkNativeEvidenceProof(path, 'native-ms1-' + kind) };
}

for (const kind of ['crew', 'ammo']) test(`actual immutable ${kind} export and all copied proof bytes revalidate`, t => {
  const c = fixture(t, kind), before = readFileSync(c.path);
  assert.doesNotThrow(c.check); assert.deepEqual(readFileSync(c.path), before);
});

test('relocation refuses hostile schema, roots, paths, duplicate roles and hashes', t => {
  const c = fixture(t);
  const changes = [m => { m.version = true; }, m => { m.extra = 1; }, m => { m.files.pop(); },
    m => { m.files[1].role = 'trace'; }, m => { m.files[0].role = 'unknown'; },
    m => { m.files[0].file = '../outside'; }, m => { m.files[0].file = c.path; },
    m => { m.files[0].file = 'noncanonical\\file'; }, m => { m.files[0].bytes = true; },
    m => { m.files[0].sha256 = '0'.repeat(64); }, m => { m.files[0].source = join(c.directory, 'other'); },
    m => { m.source_roots.original = c.directory; }, m => { m.target_roots.original = c.directory; }];
  for (const change of changes) {
    const m = structuredClone(c.manifest); change(m); save(c.sidecar, m); assert.throws(c.check);
  }
});

test('rewritten export with recomputed sidecar hashes cannot claim a new native observation', t => {
  const c = fixture(t), value = JSON.parse(readFileSync(c.path, 'utf8'));
  value.data.version = true; save(c.path, value); const raw = readFileSync(c.path);
  c.manifest.export.bytes = raw.length; c.manifest.export.sha256 = sha(raw); save(c.sidecar, c.manifest);
  assert.throws(c.check, /Unaccepted historical export checkpoint/);
});

test('every artifact is checked and producer metadata cannot be rehashed into acceptance', t => {
  const c = fixture(t);
  for (const row of c.manifest.files) {
    const path = join(c.directory, row.file), before = readFileSync(path);
    writeFileSync(path, Buffer.concat([before, Buffer.from('changed')])); assert.throws(c.check);
    writeFileSync(path, before);
  }
  for (const role of ['compiled', 'metadata', 'bundle']) {
    const m = structuredClone(c.manifest), row = m.files.find(item => item.role === role);
    const path = join(c.directory, row.file), before = readFileSync(path), changed = Buffer.concat([before, Buffer.from('changed')]);
    writeFileSync(path, changed); row.bytes = changed.length; row.sha256 = sha(changed); save(c.sidecar, m);
    assert.throws(c.check, /Historical producer closure changed/); writeFileSync(path, before);
  }
});

test('missing sidecar retains strict historical local path boundary', t => {
  const c = fixture(t); unlinkSync(c.sidecar); assert.throws(c.check, /below local/);
});

test('real directory junction cannot redirect a relocated proof', t => {
  const c = fixture(t), path = join(c.directory, 'native-ms1-crew-export01.relocated'), target = join(c.directory, 'target');
  renameSync(path, target); symlinkSync(target, path, 'junction');
  try { assert.throws(c.check, /Linked evidence path/); }
  finally { unlinkSync(path); renameSync(target, path); }
});

test('duplicate JSON keys, noncanonical serialization and oversized sidecar are rejected', t => {
  const c = fixture(t), original = readFileSync(c.sidecar, 'utf8');
  for (const changed of [original.replace('"version": 1', '"version": 1, "version": 1'),
    original.replaceAll('\n', '\r\n'), ' '.repeat(16385)]) {
    writeFileSync(c.sidecar, changed); assert.throws(c.check);
  }
});
