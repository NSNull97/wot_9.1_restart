import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { MIXED_POLICY_SHA256, mixedConfiguration, validateMixedBattleRequest, validateMixedBattleReply,
  validateMixedResultsRequest, validateMixedResultsReply } from '../src/p06t-mixed.mjs';

const path = new URL('../../tests/fixtures/p06t-writer-vectors.json', import.meta.url);
const raw = readFileSync(path), fixture = JSON.parse(raw);
test('P06T all13 actual SQLite vectors retain exact strings and distinct old/new reservations', () => {
  assert.equal(createHash('sha256').update(raw).digest('hex'), '0e293febb5e3053e34f5b543c19aa2f7420918415b22595aaa4bb16e532b2c21');
  assert.equal(fixture.vectors.length, 13);
  for (const v of fixture.vectors) {
    if (v.operation === 'battle') { validateMixedBattleRequest(v.request, v.request.account_id); validateMixedBattleReply(v.response, v.request); }
    else { validateMixedResultsRequest(v.request, v.request.account_id); validateMixedResultsReply(v.response, v.request); }
  }
  const natural = fixture.vectors.find(v => v.request.operation === 'finish');
  assert.ok(natural.request.results_json.includes('9007199254740993'));
  assert.equal(natural.response.reservation.result.terminal_hp, 23); assert.equal(natural.response.reservation.result.destroyed, true);
  assert.equal(natural.response.reservation.frozen.ammunition[0].count, 0);
});
test('P06T poison owners, amounts, source identities, policy and terminal journal fail closed', () => {
  const source = fixture.vectors.find(v => v.request.operation === 'finish');
  for (const mutate of [v => v.account_id = 'foreign', v => v.policy_sha256 = '0'.repeat(64),
    v => v.reservation.result.remaining_ammunition[1].count = 8, v => v.reservation.result.terminal_state.crew[0].crew_id = 'foreign:crew',
    v => v.reservation.result.terminal_state.devices[0].max_health = 26, v => v.reservation.result.terminal_state.crew_active = true,
    v => v.reservation.frozen.ammunition[1].family = 'ARMOR_PIERCING', v => v.extra = true]) {
    const poisoned = structuredClone(source.response); mutate(poisoned); assert.throws(() => validateMixedBattleReply(poisoned, source.request));
  }
  for (const change of [{ version: 1 }, { expected_revision: 9007199254740992 }, { battle_id: `${source.request.run_id}:18446744073709551616` },
    { remaining_ap: 1 }, { terminal_state_json: 'x'.repeat(8193) }]) assert.throws(() => validateMixedBattleRequest({ ...source.request, ...change }, source.request.account_id));
});
test('P06T configuration pins both source documents and an explicit pool owner subset', () => {
  const owner = fixture.vectors[0].request.account_id;
  const config = { version: 2, policy_sha256: MIXED_POLICY_SHA256, accounts: [owner],
    shell_catalog: fileURLToPath(new URL('../../tests/fixtures/p06t-shell-catalog.json', import.meta.url)),
    terminal_policy: fileURLToPath(new URL('../../tests/fixtures/p06t-device-policy.json', import.meta.url)) };
  assert.deepEqual(mixedConfiguration(config, [owner]), [owner]);
  assert.throws(() => mixedConfiguration(config, [])); assert.throws(() => mixedConfiguration({ ...config, version: 1 }, [owner]));
  assert.throws(() => mixedConfiguration({ ...config, terminal_policy: config.shell_catalog }, [owner]));
});
test('P06T purchased pool kinds admit only on their own purchased inventory and source stacks', () => {
  // Owner full stand 2026-10-20: a committed T-34-85 admission was refused by
  // this closed MS-1/IS-7 list, so the gateway retried "writer unavailable".
  const canonical = v => JSON.stringify((function sort(x) {
    if (Array.isArray(x)) return x.map(sort);
    if (x && typeof x === 'object') return Object.fromEntries(Object.keys(x).sort().map(k => [k, sort(x[k])]));
    return x;
  })(v));
  const source = fixture.vectors.find(v => v.request.operation === 'admit'), owner = source.request.account_id;
  const kinds = {
    t26: ['011224001300c90001001e00100000', 150, 160, 3, [[1034, 'ap', 'ARMOR_PIERCING'], [1290, 'apcr', 'ARMOR_PIERCING_CR'], [1546, 'he', 'HIGH_EXPLOSIVE']]],
    t34: ['010000000000cb0003000000000000', 400, 77, 4, [[7178, 'ap', 'ARMOR_PIERCING'], [7434, 'heat', 'HOLLOW_CHARGE'], [7690, 'he', 'HIGH_EXPLOSIVE']]],
    t3485: ['010a14000100cb0003001100060000', 670, 68, 5, [[7946, 'ap', 'ARMOR_PIERCING'], [8202, 'apcr', 'ARMOR_PIERCING_CR'], [8458, 'he', 'HIGH_EXPLOSIVE']]],
  };
  const build = (kind, native, change = f => f) => {
    const [descriptor, hp, capacity, crew, shells] = kinds[kind];
    const frozen = change({ kind, descriptor_hex: descriptor, native_inventory_id: native, vehicle_inventory_id: `${owner}:p09e-vehicle:${native}`,
      max_hp: hp, crew_ids: Array.from({ length: crew }, (_, i) => `${owner}:recruit-crew:${20 + i}`), capacity,
      ammunition: shells.map(([id, suffix, family], i) => ({ shell_definition_id: `shell:${kind}-stock-${suffix}`, shell_compact_id: id, family, count: i + 1 })),
      initial_shell_compact_id: shells[0][0] });
    const request = { ...source.request, native_inventory_id: native }, response = structuredClone(source.response);
    Object.assign(response.reservation, { native_inventory_id: frozen.native_inventory_id, vehicle_inventory_id: frozen.vehicle_inventory_id,
      frozen, frozen_sha256: createHash('sha256').update(canonical(frozen)).digest('hex') });
    return [response, request];
  };
  for (const [kind, native] of [['t26', 3], ['t34', 4], ['t3485', 3], ['t34', 2147483647]]) validateMixedBattleReply(...build(kind, native));
  for (const [kind, native, change] of [['t34', 1], ['t34', 2], ['t3485', 0],
    ['t34', 4, f => ({ ...f, vehicle_inventory_id: `${owner}:test-is7-v1` })], ['t34', 4, f => ({ ...f, vehicle_inventory_id: `foreign:p09e-vehicle:4` })],
    ['t34', 4, f => ({ ...f, descriptor_hex: kinds.t3485[0] })], ['t3485', 3, f => ({ ...f, crew_ids: f.crew_ids.slice(1) })],
    ['t34', 4, f => ({ ...f, ammunition: [f.ammunition[0], { ...f.ammunition[1], family: 'ARMOR_PIERCING_CR' }, f.ammunition[2]] })],
    ['t26', 3, f => ({ ...f, ammunition: f.ammunition.map(a => ({ ...a, count: 80 })) })],
    ['t34', 4, f => ({ ...f, kind: 'wt-e100-128' })]]) {
    assert.throws(() => validateMixedBattleReply(...build(kind, native, change)), `${kind}:${native}`);
  }
  const ms1 = structuredClone(source.response);
  ms1.reservation.frozen.native_inventory_id = 3;
  ms1.reservation.frozen_sha256 = createHash('sha256').update(canonical(ms1.reservation.frozen)).digest('hex');
  ms1.reservation.native_inventory_id = 3;
  assert.throws(() => validateMixedBattleReply(ms1, { ...source.request, native_inventory_id: 3 }));
});
