/** Bounded private DTO semantics; actual SQLite vectors are a separate gate. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { BATTLE_POLICY_SHA256, battleConfiguration, validateBattleRequest, validateBattleReply } from '../src/p08b-battle.mjs';

const OWNER = '11111111-1111-4111-8111-111111111111';
const OTHER = '22222222-2222-4222-8222-222222222222';
const RUN = '33333333-3333-4333-8333-333333333333';
const OLD = '44444444-4444-4444-8444-444444444444';
const request = (operation = 'admit', extra = {}) => ({ version: 1, operation, account_id: OWNER,
  native_database_id: 1, command_key: 'p08b-test:1', expected_revision: 14, run_id: RUN,
  ...(['admit', 'finish'].includes(operation) ? { battle_id: `${RUN}:1`, native_inventory_id: 1 } : {}),
  ...(operation === 'finish' ? { reservation_id: 'p08b-test:reserve', remaining_ap: 7, terminal_hp: 23, reason: 'manual_leave' } : {}),
  ...extra });
const frozen = () => ({ kind: 'ms1', descriptor_hex: '010d1a000e00c90000001700170000', native_inventory_id: 1,
  vehicle_inventory_id: `${OWNER}:starter-vehicle-v1`, ap_count: 7, shell_definition_id: 'shell:ms1-stock-ap',
  shell_compact_id: 2570, max_hp: 90, crew_ids: [`${OWNER}:ms1-commander-v1`, `${OWNER}:ms1-driver-v1`] });
const reservation = () => ({ reservation_id: 'p08b-test:1', run_id: RUN, battle_id: `${RUN}:1`, native_inventory_id: 1,
  vehicle_inventory_id: `${OWNER}:starter-vehicle-v1`, status: 'active', frozen: frozen(), frozen_sha256: 'a'.repeat(64), result: null });
const reply = (r, extra = {}) => ({ version: 1, operation: r.operation, status: { run_open: 'ready', inspect: 'inspected', admit: 'admitted', finish: 'finished' }[r.operation],
  account_id: r.account_id, native_database_id: r.native_database_id, command_key: r.command_key, run_id: r.run_id,
  source_revision: r.expected_revision, revision: r.expected_revision + 1, replayed: false, code: null,
  reservation: r.operation === 'admit' ? reservation() : null, policy_sha256: BATTLE_POLICY_SHA256, ...extra });

test('P08B owners require an explicit bounded unique policy configuration', () => {
  const input = { version: 1, policy_sha256: BATTLE_POLICY_SHA256, accounts: [OWNER, OTHER] };
  const output = battleConfiguration(input, OWNER);
  assert.deepEqual(output, [OWNER, OTHER]); output.pop(); assert.equal(input.accounts.length, 2);
  for (const change of [{ version: 2 }, { policy_sha256: '0'.repeat(64) }, { accounts: [] },
    { accounts: [OTHER] }, { accounts: [OWNER, OWNER] }, { accounts: [OWNER, 'invalid'] }, { extra: true }]) {
    assert.throws(() => battleConfiguration({ ...input, ...change }, OWNER));
  }
});

test('P08B preserves string u64 counters beyond JavaScript safe integers and rejects ambiguous values', () => {
  for (const suffix of ['1', '9007199254740993', '18446744073709551615']) {
    const value = request('admit', { battle_id: `${RUN}:${suffix}` });
    assert.equal(validateBattleRequest(value, OWNER), value);
  }
  for (const battle_id of [`${RUN}:0`, `${RUN}:01`, `${RUN}:+1`, `${RUN}:1.0`, `${RUN}:1e3`, `${RUN}:18446744073709551616`,
    `${OLD}:1`, 9007199254740992, null]) assert.throws(() => validateBattleRequest(request('admit', { battle_id }), OWNER));
  for (const change of [{ account_id: OTHER }, { native_database_id: true }, { native_database_id: 0 },
    { native_database_id: 2147483648 }, { native_inventory_id: 0 }, { native_inventory_id: 1.1 },
    { command_key: 'a'.repeat(97) }, { command_key: 'has space' }, { run_id: RUN.toUpperCase().replace('3', 'A') },
    { expected_revision: 9007199254740992 }, { expected_revision: true }, { version: true }, { extra: 1 }]) {
    assert.throws(() => validateBattleRequest(request('admit', change), OWNER));
  }
  assert.throws(() => validateBattleRequest(request('admit'), OTHER));
  assert.throws(() => validateBattleRequest(request('__proto__'), OWNER));
});

test('P08B inspect starts without a known cursor; finish carries only bounded authoritative facts', () => {
  assert.equal(validateBattleRequest(request('inspect', { expected_revision: 0 }), OWNER).expected_revision, 0);
  const value = request('finish'); assert.equal(validateBattleRequest(value, OWNER), value);
  for (const change of [{ remaining_ap: -1 }, { remaining_ap: 97 }, { terminal_hp: -1 }, { terminal_hp: 2151 },
    { remaining_ap: true }, { reason: 'client_says_victory' }, { reservation_id: '' }, { hp: 90 }]) {
    assert.throws(() => validateBattleRequest(request('finish', change), OWNER));
  }
});

test('P08B replies bind identity, operation, revision and admission selection', () => {
  const r = request(), value = reply(r);
  assert.equal(validateBattleReply(value, r), value);
  for (const change of [{ account_id: OTHER }, { native_database_id: 2 }, { command_key: 'another' },
    { run_id: OLD }, { source_revision: 13 }, { policy_sha256: '0'.repeat(64) }, { extra: 1 },
    { status: 'ready', reservation: null }, { reservation: null }, { revision: 14 },
    { reservation: { ...reservation(), battle_id: `${RUN}:2` } },
    { reservation: { ...reservation(), native_inventory_id: 2 } }]) {
    assert.throws(() => validateBattleReply({ ...value, ...change }, r));
  }
  assert.throws(() => validateBattleReply(reply(r, { status: 'rejected', code: 'VEHICLE_RESERVED' }), r));
  assert.doesNotThrow(() => validateBattleReply(reply(r, { status: 'rejected', code: 'VEHICLE_RESERVED', reservation: null, revision: 19 }), r));
});

test('P08B restart can return an old fenced reservation and inspect reports the actual later revision', () => {
  const r = request('run_open'), old = { ...reservation(), run_id: OLD, battle_id: `${OLD}:1`, status: 'aborted_restart',
    result: { reason: 'aborted_restart', remaining_ap: 7, consumed_ap: 0, terminal_hp: null, destroyed: null, repaired_hp: 90, credits: 0, xp: 0 } };
  assert.doesNotThrow(() => validateBattleReply(reply(r, { reservation: old }), r));
  assert.throws(() => validateBattleReply(reply(r, { reservation: reservation() }), r));
  const inspect = request('inspect', { expected_revision: 0 });
  assert.doesNotThrow(() => validateBattleReply(reply(inspect, { revision: 92, reservation: { ...old, status: 'active', result: null } }), inspect));
});

test('P08B accepts actual Python SQLite canonical request/reply vectors', {
  skip: process.env.P08B_WRITER_VECTORS ? false : 'NOT_RUN: P08B_WRITER_VECTORS actual writer evidence required',
}, () => {
  const path = process.env.P08B_WRITER_VECTORS;
  assert.ok(existsSync(path), 'Writer vector evidence missing');
  const raw = readFileSync(path); assert.ok(raw.length <= 128 * 1024);
  const document = JSON.parse(raw); assert.equal(document.version, 1); assert.equal(document.vectors.length, 8);
  for (const { request: r, response } of document.vectors) {
    validateBattleRequest(r, r.account_id); validateBattleReply(response, r);
  }
});
