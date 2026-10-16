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
