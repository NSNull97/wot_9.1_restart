/** DOM-01 bridge side: Domain client framing/auth, the crew worker lane over it, and the real Python peer. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:net';
import { createHmac, randomBytes } from 'node:crypto';
import { spawn, spawnSync } from 'node:child_process';
import { DatabaseSync } from 'node:sqlite';
import { mkdirSync, writeFileSync, readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createDomainClient, domainConfiguration, DOMAIN_SCHEMA, capabilityRequestProof, capabilityResponseProof } from '../src/domain-client.mjs';
import { createNativeCrewService, CREW_POLICY_SHA256, TRANSFER_POLICY_SHA256, CROSS_CREW_POLICY_SHA256, ROSTER_CREW_POLICY_SHA256,
  PROGRESSION_CREW_POLICY_SHA256, DISMISSAL_CREW_POLICY_SHA256, RESEARCH_POLICY_SHA256 } from '../src/p04d-crew.mjs';
import { BARRACKS_CREW_POLICY_SHA256 } from '../src/p04k-crew.mjs';
import { BATTLE_POLICY_SHA256 } from '../src/p08b-battle.mjs';
import { createIdentityBridge } from '../src/game-adapter.mjs';
import { createLateResultService, canonicalLate, lateHash, LATE_CONTRACT, LATE_POLICY_SHA256 } from '../src/p08c-late-results.mjs';
import { testDirectory, removeTestDirectory } from './helpers.mjs';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const SECRET = 'dom01-test-secret-0123456789abcdefghijklmno';
const ACCOUNT = '5b0b6a52-7d4e-4f1a-9c3b-2e1d0f9a8b7c';

function frame(header, body = Buffer.alloc(0)) {
  const raw = Buffer.from(JSON.stringify(header)), out = Buffer.alloc(6 + raw.length + body.length);
  out.writeUInt32BE(2 + raw.length + body.length, 0); out.writeUInt16BE(raw.length, 4); raw.copy(out, 6); body.copy(out, 6 + raw.length);
  return out;
}
/** Protocol-faithful fake: challenge, HMAC hello, then handler(header, body) per request. */
async function fakeDomain(handler, { proofOverride } = {}) {
  const seen = [];
  const server = createServer(socket => {
    const nonce = randomBytes(32).toString('hex'); let buffer = Buffer.alloc(0), authed = false;
    socket.write(frame({ schema: DOMAIN_SCHEMA, nonce }));
    socket.on('error', () => {});
    socket.on('data', async part => {
      buffer = Buffer.concat([buffer, part]);
      while (buffer.length >= 4 && buffer.length >= 4 + buffer.readUInt32BE(0)) {
        const payload = buffer.subarray(4, 4 + buffer.readUInt32BE(0)); buffer = buffer.subarray(4 + payload.length);
        const size = payload.readUInt16BE(0), header = JSON.parse(payload.subarray(2, 2 + size)), body = payload.subarray(2 + size);
        if (!authed) {
          const expected = createHmac('sha256', SECRET).update(`${DOMAIN_SCHEMA}:${nonce}`).digest('hex');
          if (header.op !== 'hello' || header.proof !== (proofOverride ?? expected)) return socket.destroy();
          authed = true; socket.write(frame({ schema: DOMAIN_SCHEMA, status: 200 })); continue;
        }
        if (header.camouflage_request_proof !== undefined
            && header.camouflage_request_proof !== capabilityRequestProof(SECRET, nonce, header, body)) return socket.destroy();
        seen.push({ header, body: body.toString('utf8') });
        const reply = await handler(header, body);
        if (reply === null) continue; // never answer: client deadline
        const responseBody = Buffer.from(reply.body ?? '');
        const response = { schema: DOMAIN_SCHEMA, id: header.id, status: reply.status, error: reply.error ?? null };
        if (header.camouflage_request_proof !== undefined) {
          response.camouflage_generation = reply.generation ?? header.camouflage_generation;
          response.camouflage_proof = capabilityResponseProof(SECRET, header.camouflage_request_proof, response.camouflage_generation, reply.status, responseBody);
          if (reply.tamperProof) response.camouflage_proof = '0'.repeat(64);
        }
        socket.write(frame(response, responseBody));
      }
    });
  });
  await new Promise(done => server.listen(0, '127.0.0.1', done));
  return { port: server.address().port, seen, close: () => new Promise(done => server.close(done)) };
}

test('configuration is exact and loopback only', () => {
  assert.deepEqual(domainConfiguration({ version: 1, endpoint: '127.0.0.1:3700', secret_file: 'x' }), { host: '127.0.0.1', port: 3700, secretFile: 'x' });
  for (const bad of [null, {}, { version: 2, endpoint: '127.0.0.1:3700', secret_file: 'x' }, { version: 1, endpoint: '0.0.0.0:3700', secret_file: 'x' },
    { version: 1, endpoint: '127.0.0.1:0', secret_file: 'x' }, { version: 1, endpoint: '127.0.0.1:70000', secret_file: 'x' },
    { version: 1, endpoint: '127.0.0.1:3700', secret_file: 'x', extra: 1 }]) assert.throws(() => domainConfiguration(bad), /Domain service configuration/);
  assert.throws(() => createDomainClient({ host: '127.0.0.1', port: 1, secret: 'short' }), /43 base64url/);
});

test('client authenticates, sends the exact body/key and returns status and raw bytes', async t => {
  const fake = await fakeDomain(header => header.op === 'slow' ? null : ({ status: 200, body: '{"b":1,"a":"\\u00e9"}' }));
  t.after(fake.close);
  const client = createDomainClient({ host: '127.0.0.1', port: fake.port, secret: SECRET });
  const reply = await client.call('battle', ACCOUNT, '{"command_key":"k:1"}', 'k:1', 2000);
  assert.equal(reply.status, 200); assert.equal(reply.body.toString(), '{"b":1,"a":"\\u00e9"}');
  assert.deepEqual(fake.seen[0].header, { schema: DOMAIN_SCHEMA, id: 1, op: 'battle', account_id: ACCOUNT, key: 'k:1' });
  assert.equal(fake.seen[0].body, '{"command_key":"k:1"}');
  await assert.rejects(client.call('slow', ACCOUNT, '', null, 200), /Domain deadline/);
  await assert.rejects(client.call('battle', 'not-a-uuid', '', null, 200), /account identity/);
  const small = createDomainClient({ host: '127.0.0.1', port: fake.port, secret: SECRET, maxReply: 4 });
  await assert.rejects(small.call('fixture', ACCOUNT, '', null, 2000), /reply bound/);
});

test('camouflage mode pins Domain generation and refuses stale or mismatched peers', async t => {
  let current = 'ab'.repeat(32);
  const fake = await fakeDomain(header => {
    if (header.op === 'describe') return { status: 200, generation: current, body: JSON.stringify({ camouflage_v1: true, camouflage_generation: current }) };
    return header.camouflage_generation === current ? { status: 200, generation: current, body: '{}' } : { status: 403, generation: current, error: 'forbidden' };
  });
  t.after(fake.close);
  const client = createDomainClient({ host: '127.0.0.1', port: fake.port, secret: SECRET, camouflage: true });
  await assert.rejects(client.call('fixture', ACCOUNT, '', null, 2000), /handshake required/);
  assert.equal((await client.call('describe', null, '', null, 2000)).status, 200);
  assert.equal((await client.call('fixture', ACCOUNT, '', null, 2000)).status, 200);
  assert.equal(fake.seen.at(-1).header.camouflage_generation, current);
  current = 'cd'.repeat(32); // simulate a restarted Domain on the same endpoint
  await assert.rejects(client.call('fixture', ACCOUNT, '', null, 2000), /generation changed/);
  await assert.rejects(client.call('describe', null, '', null, 2000), /capability mismatch/);
  await assert.rejects(client.call('fixture', ACCOUNT, '', null, 2000), /generation changed/);
  const legacy = createDomainClient({ host: '127.0.0.1', port: fake.port, secret: SECRET });
  await assert.rejects(legacy.call('describe', null, '', null, 2000), /capability mismatch/);
});

test('camouflage MAC matches cross-language vector and rejects forged response', async t => {
  const header = { camouflage_nonce: 'cd'.repeat(32), camouflage_generation: '12'.repeat(32), id: 42,
    op: 'research', account_id: ACCOUNT, key: 'k:1' };
  const proof = capabilityRequestProof(SECRET, 'ab'.repeat(32), header, Buffer.from('{"x":1}'));
  assert.equal(proof, '70416858b4c486502cf3aaaedb38957ebf6e3f6332bf5da3c154983e05457fc2');
  assert.equal(capabilityResponseProof(SECRET, proof, '12'.repeat(32), 200, Buffer.from('{"ok":true}')),
    'ab82b8343c9f2e7ce97bf46d748dda79e0038c5d45bf4df424f1ab9fa42a379e');
  const fake = await fakeDomain(() => ({ status: 200, generation: '12'.repeat(32), tamperProof: true,
    body: JSON.stringify({ camouflage_v1: true, camouflage_generation: '12'.repeat(32) }) }));
  t.after(fake.close);
  const client = createDomainClient({ host: '127.0.0.1', port: fake.port, secret: SECRET, camouflage: true });
  await assert.rejects(client.call('describe', null, '', null, 2000), /response authentication/);
  await assert.rejects(client.call('fixture', ACCOUNT, '', null, 2000), /handshake required/);
});

test('camouflage configuration needs explicit test-lab and exact boolean', () => {
  const value = { version: 1, endpoint: '127.0.0.1:3700', secret_file: 'x', camouflage_v1: true };
  const old = process.env.WOT091_TEST_LAB;
  try {
    delete process.env.WOT091_TEST_LAB;
    assert.throws(() => domainConfiguration(value), /Domain service configuration/);
    process.env.WOT091_TEST_LAB = '1';
    assert.equal(domainConfiguration(value).camouflage, true);
    assert.throws(() => domainConfiguration({ ...value, camouflage_v1: 1 }), /Domain service configuration/);
    assert.equal(domainConfiguration({ ...value, camouflage_v1: false }).camouflage, undefined);
  } finally {
    if (old === undefined) delete process.env.WOT091_TEST_LAB; else process.env.WOT091_TEST_LAB = old;
  }
});

test('a wrong secret is refused before any request', async t => {
  const fake = await fakeDomain(() => ({ status: 200, body: '{}' }), { proofOverride: 'never' });
  t.after(fake.close);
  const client = createDomainClient({ host: '127.0.0.1', port: fake.port, secret: SECRET });
  await assert.rejects(client.call('ping', null, '', null, 2000), /Domain closed|Domain unavailable/);
  assert.equal(fake.seen.length, 0);
});

function crewOptions(directory, domain) {
  return { database: join(directory, 'game.sqlite'), fixtureRoot: join(directory, 'fixtures'), python: process.execPath, localPath: p => p, domain,
    transfer: { version: 1, policy_sha256: TRANSFER_POLICY_SHA256 }, crossVehicle: { version: 1, policy_sha256: CROSS_CREW_POLICY_SHA256 },
    rosterRecruitment: { version: 1, policy_sha256: ROSTER_CREW_POLICY_SHA256 }, progression: { version: 1, policy_sha256: PROGRESSION_CREW_POLICY_SHA256 },
    dismissal: { version: 1, policy_sha256: DISMISSAL_CREW_POLICY_SHA256 }, barracksRecruitment: { version: 1, policy_sha256: BARRACKS_CREW_POLICY_SHA256 },
    research: { version: 1, policy_sha256: RESEARCH_POLICY_SHA256 }, battle: { version: 1, policy_sha256: BATTLE_POLICY_SHA256 } };
}
const ammo = directory => ({ version: 1, bundle_root: directory, original_root: directory, account_id: ACCOUNT, grant: { grant_id: 'p09d-test-depot-v1', quantity_each: 100 } });
const crew = { version: 1, policy_sha256: CREW_POLICY_SHA256 };
const described = (row = {}) => JSON.stringify({ schema: DOMAIN_SCHEMA, catalog_sha256: null,
  accounts: [{ account_id: ACCOUNT, native_database_id: 1, mixed: false, ammo_loss: false, owner_hold: false, late: false, catalog: false, ...row }] });

test('crew service runs every worker operation through the Domain, one per account at a time', async t => {
  const directory = testDirectory(); t.after(() => removeTestDirectory(directory));
  let running = 0, peak = 0;
  const fake = await fakeDomain(async header => {
    if (header.op === 'describe') return { status: 200, body: described() };
    if (header.op === 'activate') return { status: 200, body: JSON.stringify({ profile: {} }) };
    running++; peak = Math.max(peak, running); await new Promise(done => setTimeout(done, 150)); running--;
    return header.op === 'research' ? { status: 503, error: 'unavailable' } : { status: 200, body: '{"status":"ready"}' };
  });
  t.after(fake.close);
  const domain = createDomainClient({ host: '127.0.0.1', port: fake.port, secret: SECRET });
  const service = await createNativeCrewService(ammo(directory), crew, crewOptions(directory, domain));
  assert.deepEqual(fake.seen.map(s => s.header.op), ['describe', 'activate']);
  assert.equal(fake.seen[1].header.account_id, ACCOUNT); assert.equal(fake.seen[1].body, '');
  const request = { version: 1, operation: 'inspect', account_id: ACCOUNT, native_database_id: 1, command_key: 'b:1', expected_revision: 13, run_id: ACCOUNT };
  // Two callers of one account: serialized; a third is refused by the unchanged lane.
  const replies = await Promise.allSettled([service.battle(request), service.battle({ ...request, command_key: 'b:2' }), service.battle({ ...request, command_key: 'b:3' })]);
  assert.equal(peak, 1);
  assert.match(String(replies[2].reason), /Crew worker busy/);
  const sent = fake.seen.filter(s => s.header.op === 'battle');
  assert.deepEqual(sent.map(s => s.header.key), ['b:1', 'b:2']); assert.equal(sent[0].body, JSON.stringify(request));
  await assert.rejects(service.research({ account_id: ACCOUNT, native_database_id: 1, command_key: 'r:1', expected_revision: 13, wire_revision: 1, command: 101, arguments: [0, 0, 0] }), /Crew worker unavailable/);
});

test('a Domain serving the account with other worker flags is refused at start', async t => {
  const directory = testDirectory(); t.after(() => removeTestDirectory(directory));
  const fake = await fakeDomain(header => header.op === 'describe' ? { status: 200, body: described({ mixed: true }) } : { status: 200, body: '{}' });
  t.after(fake.close);
  const domain = createDomainClient({ host: '127.0.0.1', port: fake.port, secret: SECRET });
  await assert.rejects(createNativeCrewService(ammo(directory), crew, crewOptions(directory, domain)), /Domain service account configuration mismatch/);
  assert.deepEqual(fake.seen.map(s => s.header.op), ['describe']);
  const missing = { ...crewOptions(directory, domain), battle: null, pool: null };
  await assert.rejects(createNativeCrewService(ammo(directory), crew, missing), /requires the profile13 battle worker/);
});

test('late-result service sends canonical late requests to the Domain late operations', async t => {
  const directory = testDirectory(); t.after(() => removeTestDirectory(directory));
  writeFileSync(join(directory, 'game.sqlite'), '');
  const fake = await fakeDomain((header, body) => {
    const request = JSON.parse(body);
    return { status: 200, body: JSON.stringify({ ...request, request_sha256: lateHash(request), policy_sha256: LATE_POLICY_SHA256,
      status: 'pending', replayed: false, code: null, rows: [], next_arena_id: null }) };
  });
  t.after(fake.close);
  const late = createLateResultService({ database: join(directory, 'game.sqlite'), originalRoot: directory, accountId: ACCOUNT,
    shellCatalog: join(ROOT, 'tests/fixtures/p06t-shell-catalog.json'), terminalPolicy: join(ROOT, 'server/gateway/src/shared/p06t_device_policy.json'),
    loss: true, python: process.execPath, worker: join(ROOT, 'tools/p08c_late_results_service.py'), cwd: ROOT,
    domain: createDomainClient({ host: '127.0.0.1', port: fake.port, secret: SECRET }) });
  const request = { version: 1, contract: LATE_CONTRACT, operation: 'pending', account_id: ACCOUNT, native_database_id: 2, command_key: 'late:pending:1', after_arena_id: null };
  assert.equal((await late.pending(request)).status, 'pending');
  assert.deepEqual(fake.seen[0].header, { schema: DOMAIN_SCHEMA, id: 1, op: 'late-pending', account_id: ACCOUNT, key: 'late:pending:1' });
  assert.equal(fake.seen[0].body, canonicalLate(request).toString());
});

test('bridge accepts the Domain option only for the profile13 battle writer', async () => {
  const base = { version: 1, port: 0, web_database: 'x', game_database: 'x', fixture_root: 'x', native_descriptors: 'x', python_executable: 'x', token_file: 'x' };
  await assert.rejects(createIdentityBridge({ ...base, domain_service: { version: 1, endpoint: '127.0.0.1:3700', secret_file: 'x' } }),
    /Domain service requires profile13 battle without spawned selection writers/);
  await assert.rejects(createIdentityBridge({ ...base, domain_service: { version: 1, endpoint: '127.0.0.2:3700', secret_file: 'x' } }), /Domain service configuration/);
});

const BUNDLE = process.env.P04D_TEST_BUNDLE;
const CONFIG = process.env.WOT091_CONFIG ?? join(ROOT, 'config/project.local.json');
test('real Python Domain peer: HMAC handshake, describe, authorization', {
  skip: BUNDLE && existsSync(CONFIG) ? false : 'NOT_RUN: P04D_TEST_BUNDLE and config/project.local.json required', timeout: 120000,
}, async t => {
  const directory = testDirectory(); t.after(() => removeTestDirectory(directory));
  const original = JSON.parse(readFileSync(CONFIG, 'utf8').replace(/^﻿/, '')).paths.original_client_root;
  const database = join(directory, 'game.sqlite'), secret = join(directory, 'secret'), config = join(directory, 'domain.json');
  const db = new DatabaseSync(database);
  db.exec('CREATE TABLE game_profiles(native_id INTEGER PRIMARY KEY AUTOINCREMENT,account_id TEXT NOT NULL UNIQUE,profile_json TEXT NOT NULL)');
  db.prepare('INSERT INTO game_profiles VALUES (?,?,?)').run(7, ACCOUNT, JSON.stringify({ account_id: ACCOUNT, native_database_id: 7 }));
  db.close();
  writeFileSync(secret, SECRET); mkdirSync(join(directory, 'fixtures'));
  writeFileSync(config, JSON.stringify({ version: 1, endpoint: '127.0.0.1:0', secret_file: secret, database, bundle: BUNDLE, original_root: original,
    fixture_root: join(directory, 'fixtures'), mixed: null, catalog_sha256: null, workers: 2,
    accounts: [{ account_id: ACCOUNT, mixed: false, ammo_loss: false, owner_hold: false, late: false }] }));
  const python = spawnSync('python', ['-B', '-c', 'import sys;print(sys.executable)'], { encoding: 'utf8', windowsHide: true }).stdout.trim();
  const child = spawn(python, ['-B', '-X', 'utf8', join(ROOT, 'server/domain/service.py'), '--config', config, '--parent-stdin'], { cwd: ROOT, windowsHide: true });
  t.after(() => { if (child.exitCode === null) child.kill(); });
  const ready = await new Promise((done, fail) => {
    let text = ''; child.stdout.on('data', part => { text += part; if (text.includes('\n')) done(JSON.parse(text.split('\n')[0])); });
    child.once('exit', code => fail(new Error(`domain exited ${code}`)));
  });
  assert.equal(ready.event, 'domain_ready');
  const client = createDomainClient({ host: '127.0.0.1', port: ready.port, secret: SECRET });
  assert.equal((await client.call('ping', null, '', null, 5000)).status, 200);
  const value = JSON.parse((await client.call('describe', null, '', null, 5000)).body);
  assert.deepEqual(value.accounts, [{ account_id: ACCOUNT, native_database_id: 7, mixed: false, ammo_loss: false, owner_hold: false, late: false, catalog: false }]);
  assert.equal((await client.call('fixture', '00000000-0000-4000-8000-000000000000', '', null, 5000)).status, 403);
  const foreign = JSON.stringify({ account_id: ACCOUNT, native_database_id: 8, command_key: 'k' });
  assert.equal((await client.call('battle', ACCOUNT, foreign, 'k', 5000)).status, 403);
  // Not an activated profile13 store: the worker fails closed, the service stays up.
  assert.deepEqual([(await client.call('pool-overview', ACCOUNT, '', null, 20000)).status], [503]);
  assert.equal((await client.call('ping', null, '', null, 5000)).status, 200);
  const wrong = createDomainClient({ host: '127.0.0.1', port: ready.port, secret: SECRET.replace('d', 'e') });
  await assert.rejects(wrong.call('ping', null, '', null, 5000), /Domain closed|Domain unavailable/);
  child.stdin.end();
  assert.equal(await new Promise(done => child.once('exit', done)), 0);
});


test('real Python Domain and opted-in bridge authenticate every camouflage RPC', {
  skip: BUNDLE && existsSync(CONFIG) ? false : 'NOT_RUN: P04D_TEST_BUNDLE and WOT091_CONFIG required', timeout: 120000,
}, async t => {
  const directory = testDirectory(); t.after(() => removeTestDirectory(directory));
  const original = JSON.parse(readFileSync(CONFIG, 'utf8').replace(/^\ufeff/, '')).paths.original_client_root;
  const database = join(directory, 'game.sqlite'), secret = join(directory, 'secret'), config = join(directory, 'domain.json');
  const db = new DatabaseSync(database);
  db.exec('CREATE TABLE game_profiles(native_id INTEGER PRIMARY KEY AUTOINCREMENT,account_id TEXT NOT NULL UNIQUE,profile_json TEXT NOT NULL)');
  db.prepare('INSERT INTO game_profiles VALUES (?,?,?)').run(7, ACCOUNT, JSON.stringify({ account_id: ACCOUNT, native_database_id: 7 }));
  db.close();
  writeFileSync(secret, SECRET); mkdirSync(join(directory, 'fixtures'));
  const guardSecret = join(directory, 'guard-secret');
  const guardKey = 'guard1-test-secret-0123456789abcdefghijklmn';
  writeFileSync(guardSecret, guardKey);
  let guardGeneration = null;
  const guard = createServer(socket => {
    let input = Buffer.alloc(0);
    socket.on('data', part => {
      input = Buffer.concat([input, part]);
      if (input.length > 32) return socket.destroy();
      if (input.length === 32) {
        if (guardGeneration === null) return socket.destroy();
        const signature = createHmac('sha256', guardKey).update('wot091-domain.v1:camouflage-live.v1\0', 'ascii')
          .update(guardGeneration, 'ascii').update(input).digest();
        socket.end(signature);
      }
    });
  });
  await new Promise(done => guard.listen(0, '127.0.0.1', done));
  t.after(() => new Promise(done => guard.close(done)));
  writeFileSync(config, JSON.stringify({ version: 1, endpoint: '127.0.0.1:0', secret_file: secret, database, bundle: BUNDLE, original_root: original,
    fixture_root: join(directory, 'fixtures'), mixed: null, catalog_sha256: null, workers: 2, camouflage_v1: true,
    camouflage_guard: { version: 1, endpoint: `127.0.0.1:${guard.address().port}`, secret_file: guardSecret },
    accounts: [{ account_id: ACCOUNT, mixed: false, ammo_loss: false, owner_hold: false, late: false }] }));
  const python = spawnSync('python', ['-B', '-c', 'import sys;print(sys.executable)'], { encoding: 'utf8', windowsHide: true }).stdout.trim();
  const child = spawn(python, ['-B', '-X', 'utf8', join(ROOT, 'server/domain/service.py'), '--config', config, '--parent-stdin'],
    { cwd: ROOT, windowsHide: true, env: { ...process.env, WOT091_TEST_LAB: '1' } });
  t.after(() => { if (child.exitCode === null) child.kill(); });
  const ready = await new Promise((done, fail) => {
    let text = ''; child.stdout.on('data', part => { text += part; if (text.includes('\n')) done(JSON.parse(text.split('\n')[0])); });
    child.once('exit', code => fail(new Error(`domain exited ${code}`)));
  });
  assert.equal(ready.event, 'domain_ready');
  const client = createDomainClient({ host: '127.0.0.1', port: ready.port, secret: SECRET, camouflage: true });
  await assert.rejects(client.call('ping', null, '', null, 5000), /handshake required/);
  const describe = JSON.parse((await client.call('describe', null, '', null, 5000)).body);
  assert.equal(describe.camouflage_v1, true);
  assert.match(describe.camouflage_generation, /^[0-9a-f]{64}$/);
  assert.equal((await client.call('ping', null, '', null, 5000)).status, 503);
  guardGeneration = describe.camouflage_generation;
  assert.equal((await client.call('ping', null, '', null, 5000)).status, 200);
  assert.equal((await client.call('fixture', '00000000-0000-4000-8000-000000000000', '', null, 5000)).status, 403);
  const legacy = createDomainClient({ host: '127.0.0.1', port: ready.port, secret: SECRET });
  await assert.rejects(legacy.call('describe', null, '', null, 5000), /capability mismatch/);
  child.stdin.end();
  assert.equal(await new Promise(done => child.once('exit', done)), 0);
});
