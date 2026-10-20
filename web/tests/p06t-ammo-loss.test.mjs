/** Actual isolated writer response vectors; no native compatibility claim. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { LOSS_CONTRACT, LOSS_POLICY_SHA256, lossConfiguration, validateLossBattleRequest,
  validateLossBattleReply, validateLossResultsRequest, validateLossResultsReply } from '../src/p06t-ammo-loss.mjs';

const raw = readFileSync(new URL('../../tests/fixtures/p06t-ammo-loss-writer-vectors.json', import.meta.url));
assert.equal(createHash('sha256').update(raw).digest('hex'), '251c60f587d14d916e5381567d8af2982b26f0f98335af8464b75bbf1cc1f154');
const data = JSON.parse(raw), owner = data.vectors[0].request.account_id;
test('v4 validates all nine actual SQLite request/reply vectors with explicit fired/lost accounting', () => {
  for (const { request, response } of data.vectors) {
    if (['query', 'ack'].includes(request.operation)) { validateLossResultsRequest(request, owner); validateLossResultsReply(response, request); }
    else { validateLossBattleRequest(request, owner); validateLossBattleReply(response, request); }
  }
});
test('v4 rejects invented shots, causal poison and foreign frozen wrapper without loosening v2', () => {
  const row = data.vectors.find(v => v.request.operation === 'finish');
  for (const alter of [v => v.reservation.result.lost_ammunition[1].count--,
    v => v.reservation.result.loss_event.target_slot = 1, v => v.reservation.result.loss_event.tick++,
    v => v.reservation.result.terminal_hp = 18, v => v.reservation.frozen.policy_sha256 = '0'.repeat(64)]) {
    const bad = structuredClone(row.response); alter(bad); assert.throws(() => validateLossBattleReply(bad, row.request));
  }
  const wrong = structuredClone(row.request), result = JSON.parse(wrong.results_json); result.participants[0].shots = 14; wrong.results_json = JSON.stringify(result);
  assert.throws(() => validateLossBattleReply(row.response, wrong), /fired result/);
  assert.throws(() => validateLossBattleRequest({ ...row.request, version: 2 }, owner));
});
test('v4 requires explicit closed policy/account subset and read result record contract', () => {
  const config = { version: 4, contract: LOSS_CONTRACT, policy_sha256: LOSS_POLICY_SHA256, accounts: [owner] };
  assert.deepEqual(lossConfiguration(config, [owner]), [owner]);
  for (const bad of [{ ...config, version: 3 }, { ...config, contract: 'unknown' }, { ...config, accounts: [owner, owner] }, { ...config, extra: true }]) assert.throws(() => lossConfiguration(bad, [owner]));
  assert.throws(() => lossConfiguration(config, []));
  const row = data.vectors.find(v => v.request.operation === 'query');
  assert.throws(() => validateLossResultsReply({ ...row.response, record_contract: null }, row.request));
  assert.throws(() => validateLossResultsRequest({ ...row.request, account_id: 'foreign' }, owner));
});
