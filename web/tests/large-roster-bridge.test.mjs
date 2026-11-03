/** RES-30 bridge validators for 7..30-actor battles. The actual saved loss
 * writer vectors are extended with SYNTHETIC bot rows (BOT-01-shaped, no
 * account); no native compatibility claim. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { validateLossBattleRequest, validateLossBattleReply } from '../src/p06t-ammo-loss.mjs';
import { MAX_PARTICIPANTS, MAX_RESULT_BYTES, MAX_RESULT_REQUEST } from '../src/p08b-battle.mjs';

const raw = readFileSync(new URL('../../tests/fixtures/p06t-ammo-loss-writer-vectors.json', import.meta.url));
assert.equal(createHash('sha256').update(raw).digest('hex'), '251c60f587d14d916e5381567d8af2982b26f0f98335af8464b75bbf1cc1f154');
const data = JSON.parse(raw), owner = data.vectors[0].request.account_id;
const vehicle = slot => slot < 2 ? 0x09100003 + 2 * slot : 0x09110003 + 2 * (slot - 2);

/** The saved natural finish with its two real rows plus bot rows up to `n`;
 * the detonating attacker moves to the last slot. */
function roster(n) {
  const row = structuredClone(data.vectors.find(v => v.request.operation === 'finish' && v.request.reason === 'battle_finished'));
  const results = JSON.parse(row.request.results_json);
  const [own, killer] = results.participants;
  const bots = Array.from({ length: n - 2 }, (_, i) => ({ ...killer, vehicle_id: vehicle(i + 1), account_dbid: 0x7F000000 + i + 1,
    name: `Bot-${String(i + 1).padStart(2, '0')}`, team: 1 + ((i + 1) % 2), shots: 0, direct_hits: 0, piercings: 0, damage_dealt: 0, kills: 0 }));
  results.participants = [own, ...bots, { ...killer, vehicle_id: vehicle(n - 1) }];
  row.request.results_json = JSON.stringify(results);
  for (const event of [row.request.loss_event, row.response.reservation.result.loss_event]) event.attacker_slot = n - 1;
  const state = row.response.reservation.result.terminal_state;
  state.roster_size = n; state.death.killer_slot = n - 1;
  row.request.terminal_state_json = JSON.stringify(state);
  return row;
}

test('RES-30 loss bridge accepts a 30-actor natural finish, detonation slot and terminal roster', () => {
  assert.equal(MAX_PARTICIPANTS, 30);
  for (const n of [2, 7, 30]) {
    const row = roster(n); validateLossBattleRequest(row.request, owner); validateLossBattleReply(row.response, row.request);
  }
  const beyond = roster(30);
  beyond.request.loss_event.attacker_slot = 30;
  assert.throws(() => validateLossBattleRequest(beyond.request, owner), /bounded loss event/);
  const wrongRoster = roster(30); wrongRoster.response.reservation.result.terminal_state.roster_size = 29;
  assert.throws(() => validateLossBattleReply(wrongRoster.response, wrongRoster.request));
});

test('RES-30 journal and request byte budgets cover one 7..30-row journal', () => {
  const row = roster(30);
  const padded = { ...row.request, results_json: row.request.results_json + ' '.repeat(MAX_RESULT_BYTES - row.request.results_json.length) };
  validateLossBattleRequest(padded, owner);
  assert.ok(Buffer.byteLength(JSON.stringify(padded)) < MAX_RESULT_REQUEST);
  assert.throws(() => validateLossBattleRequest({ ...padded, results_json: padded.results_json + ' ' }, owner), /full result bound/);
});
