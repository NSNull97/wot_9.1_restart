import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { DatabaseSync } from 'node:sqlite';
import { join } from 'node:path';
import { testDirectory, removeTestDirectory } from './helpers.mjs';
import { canonicalLate, LATE_CONTRACT, LATE_POLICY_SHA256, lateConfiguration, lateReaderFence, validateLateRequest, validateLateReply,
  validatePendingRequest, validatePendingReply } from '../src/p08c-late-results.mjs';
const fixture = JSON.parse(readFileSync(new URL('../../tests/fixtures/p08c-late-loss-two-owner-vectors.json', import.meta.url)));
test('actual Python SQL vectors bind UTF8 canonical request and stored release/seal hashes', () => {
  assert.equal(fixture.policy_sha256, LATE_POLICY_SHA256);
  for (const { request, response } of fixture.append_vectors) {
    validateLateRequest(request, request.account_id); validateLateReply(response, request);
    assert.equal(typeof request.arena_id, 'string'); assert.equal(request.arena_id, '9007199254740993');
  }
});
test('closed opt-in config cannot add a non-mixed owner or retag old policies', () => {
  const owner = fixture.append_vectors[0].request.account_id;
  const config = { version: 1, contract: LATE_CONTRACT, policy_sha256: LATE_POLICY_SHA256, accounts: [owner] };
  assert.deepEqual(lateConfiguration(config, [owner]), [owner]);
  for (const value of [{ ...config, version: 2 }, { ...config, policy_sha256: '0'.repeat(64) }, { ...config, accounts: [owner, owner] }, { ...config, path: 'unsafe' }])
    assert.throws(() => lateConfiguration(value, [owner]));
  assert.throws(() => lateConfiguration(config, []));
});
test('request and response foreign/revision/hash/arena poison is refused', () => {
  const { request, response } = fixture.append_vectors.find(v => v.request.operation === 'append');
  for (const bad of [{ ...request, arena_id: 9007199254740993 }, { ...request, arena_id: '9223372036854775808' }, { ...request, version: 4 },
    /* RES-30 roster30 seal budget */ { ...request, seal_json: 'я'.repeat(393216 / 2 + 1) }, { ...request, finished_revision: true }, { ...request, worker: 'unsafe' }])
    assert.throws(() => validateLateRequest(bad, request.account_id));
  for (const bad of [{ ...response, request_sha256: '0'.repeat(64) }, { ...response, seal_sha256: '0'.repeat(64) },
    { ...response, release_stamp: { ...response.release_stamp, finished_revision: response.release_stamp.finished_revision + 1 } },
    { ...response, replayed: 1 }, { ...response, native_database_id: 123 }]) assert.throws(() => validateLateReply(bad, request));
  assert.equal(canonicalLate({ имя: 'Ёж', a: 1 }), '{"a":1,"имя":"Ёж"}');
});
test('actual readonly SQLite startup fence covers partial schema and acked owners', t => {
  const directory = testDirectory(), path = join(directory, 'fence.sqlite'), owner = fixture.append_vectors[0].request.account_id;
  t.after(() => removeTestDirectory(directory));
  let db = new DatabaseSync(path); db.exec('CREATE TABLE harmless(x)'); db.close();
  const hash = () => createHash('sha256').update(readFileSync(path)).digest('hex');
  const fresh = hash(); lateReaderFence(path, []); assert.equal(hash(), fresh);
  db = new DatabaseSync(path); db.exec('CREATE TABLE p08c_late_schema(version,policy_sha256,catalog_sha256)'); db.close();
  assert.throws(() => lateReaderFence(path, [owner]), /reader namespace/);
  db = new DatabaseSync(path); db.exec('CREATE TABLE p08c_late_seal(x); CREATE TABLE p08c_late_command(x); CREATE TABLE p08c_late_result(account_id,acked)');
  db.prepare('INSERT INTO p08c_late_schema VALUES (?,?,?)').run('p08c-late-results.v1', LATE_POLICY_SHA256, '1'.repeat(64)); db.close();
  lateReaderFence(path, []);  // A fresh namespace without committed late records can be off.
  db = new DatabaseSync(path); db.prepare('INSERT INTO p08c_late_result VALUES (?,1)').run(owner); db.close();
  const committed = hash(); assert.throws(() => lateReaderFence(path, []), /reader policy required/);
  lateReaderFence(path, [owner]); assert.equal(hash(), committed);
});
test('actual pending SQL vectors bind source vehicle type, cursor and ACK-only removal', () => {
  const raw = readFileSync(new URL('../../tests/fixtures/p08c-late-loss-two-owner-discovery-vectors.json', import.meta.url));
  assert.equal(createHash('sha256').update(raw).digest('hex'), 'c2124ddb960630a86ff3e399993f8711214167d2f6cabd2c94452316141181fa');
  const vectors = JSON.parse(raw).pending_vectors;
  for (const { request, response } of vectors) { validatePendingRequest(request, request.account_id); validatePendingReply(response, request); }
  const { request, response } = vectors[0]; assert.equal(response.rows[0].vehicle_type_compact_id, 3329);
  assert.equal(vectors[1].response.rows.length, 0);
  assert.throws(() => validatePendingRequest({ ...request, after_arena_id: 9007199254740993 }, request.account_id));
  assert.throws(() => validatePendingReply({ ...response, next_arena_id: response.rows[0].arena_id }, request));
  assert.throws(() => validatePendingReply({ ...response, rows: [response.rows[0], response.rows[0]] }, request));
  assert.throws(() => validatePendingReply({ ...response, rows: [{ ...response.rows[0], vehicle_type_compact_id: 0 }] }, request));
});
