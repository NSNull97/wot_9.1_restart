/** Explicit v4 accounting. Native/source facts still use the frozen v2 rules. */
import { createHash } from 'node:crypto';
import { MIXED_POLICY_SHA256, validateMixedBattleRequest, validateMixedBattleReply,
  validateMixedResultsRequest, validateMixedResultsReply } from './p06t-mixed.mjs';

export const LOSS_CONTRACT = 'p06t-ammo-rack-loss.v1';
export const LOSS_POLICY_SHA256 = 'f6369197bcf83e4915dbbb16c4c173a6fd3b38103ac08bc2e33913a9071fe94e';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const key = v => typeof v === 'string' && /^[A-Za-z0-9_:-]{1,96}$/.test(v);
const integer = (v, lo, hi = 2147483647) => Number.isSafeInteger(v) && v >= lo && v <= hi;
const exact = (v, names) => v && typeof v === 'object' && !Array.isArray(v)
  && Object.keys(v).sort().join(',') === [...names].sort().join(',');
const requireValue = (ok, message, status) => { if (!ok) throw Object.assign(new Error(`Ammo loss ${message}`), status ? { status } : {}); };
const canonical = v => JSON.stringify((function sort(x) {
  if (Array.isArray(x)) return x.map(sort);
  if (x && typeof x === 'object') return Object.fromEntries(Object.keys(x).sort().map(k => [k, sort(x[k])]));
  return x;
})(v));
const bytes = v => Buffer.byteLength(JSON.stringify(v));
const hash = v => createHash('sha256').update(canonical(v)).digest('hex');
const arrays = ['remaining_ammunition', 'fired_ammunition', 'lost_ammunition'];
const common = ['version', 'contract', 'operation', 'account_id', 'native_database_id', 'command_key', 'expected_revision', 'run_id'];
const extra = { run_open: [], inspect: [], admit: ['battle_id', 'native_inventory_id'],
  finish: ['battle_id', 'native_inventory_id', 'reservation_id', ...arrays, 'loss_event', 'terminal_hp', 'reason', 'terminal_state_json'] };
function cause(e, status) {
  requireValue(e === null || exact(e, ['shot', 'attacker_slot', 'target_slot', 'tick', 'device_sequence'])
    && integer(e.shot, 1, 960) && integer(e.attacker_slot, 0, 5) && integer(e.target_slot, 0, 5)
    && e.attacker_slot !== e.target_slot && integer(e.tick, 1000, 216000) && integer(e.device_sequence, 1, 15360), 'bounded loss event', status);
}
function stackRows(a, status) {
  requireValue(Array.isArray(a) && a.length === 3 && a.every(r => exact(r, ['shell_compact_id', 'count'])
    && integer(r.shell_compact_id, 1, 65535) && integer(r.count, 0, 160))
    && new Set(a.map(r => r.shell_compact_id)).size === 3, 'three bounded source stacks', status);
}
export function lossWorkerConfiguration(v) {
  requireValue(exact(v, ['version', 'contract', 'policy_sha256']) && v.version === 4 && v.contract === LOSS_CONTRACT
    && v.policy_sha256 === LOSS_POLICY_SHA256, 'explicit worker policy'); return v;
}
export function lossConfiguration(v, mixedOwners) {
  requireValue(exact(v, ['version', 'contract', 'policy_sha256', 'accounts']) && Array.isArray(v.accounts) && v.accounts.length >= 1 && v.accounts.length <= 6
    && Array.isArray(mixedOwners) && v.accounts.every(a => UUID.test(a) && mixedOwners.includes(a)) && new Set(v.accounts).size === v.accounts.length, 'explicit owner subset');
  const { accounts, ...worker } = v; lossWorkerConfiguration(worker); return [...accounts];
}
function oldRequest(v) {
  const { contract, fired_ammunition, lost_ammunition, loss_event, ...old } = v;
  return { ...old, version: 2 };
}
export function validateLossBattleRequest(v, owner) {
  const natural = v?.operation === 'finish' && v.reason === 'battle_finished';
  requireValue(v && Object.hasOwn(extra, v.operation) && exact(v, [...common, ...extra[v.operation], ...(natural ? ['results_json'] : [])])
    && v.version === 4 && v.contract === LOSS_CONTRACT, 'request contract/fields', 400);
  validateMixedBattleRequest(oldRequest(v), owner);
  if (v.operation === 'finish') { for (const name of arrays) stackRows(v[name], 400); cause(v.loss_event, 400); }
  requireValue(bytes(v) <= (natural ? 65536 : v.operation === 'finish' ? 16384 : 2048), 'request byte budget', 400); return v;
}
export function validateLossBattleReply(v, request) {
  requireValue(exact(v, ['version', 'contract', 'operation', 'account_id', 'native_database_id', 'command_key', 'run_id', 'source_revision', 'revision', 'replayed',
    'status', 'code', 'reservation', 'legacy_reservation', 'policy_sha256']) && v.version === 4 && v.contract === LOSS_CONTRACT
    && v.policy_sha256 === LOSS_POLICY_SHA256 && v.legacy_reservation === null && bytes(v) <= 8192, 'reply contract/schema/budget');
  const { contract, ...legacyView } = v;
  const old = { ...legacyView, version: 2, policy_sha256: MIXED_POLICY_SHA256 };
  const row = v.reservation;
  if (row !== null) {
    requireValue(exact(row.frozen, ['policy_sha256', 'loadout', 'loadout_sha256']) && row.frozen.policy_sha256 === LOSS_POLICY_SHA256
      && row.frozen_sha256 === hash(row.frozen), 'frozen immutable spending wrapper');
    old.reservation = { ...row, frozen: row.frozen.loadout, frozen_sha256: row.frozen.loadout_sha256 };
    const t = row.result, f = row.frozen.loadout;
    if (t !== null) {
      requireValue(exact(t, ['reason', ...arrays, 'loss_event', 'terminal_hp', 'destroyed', 'repaired_hp', 'credits', 'xp', 'terminal_state']), 'terminal accounting fields');
      for (const name of arrays) stackRows(t[name]); cause(t.loss_event);
      requireValue(t.remaining_ammunition.every((a, i) => arrays.every(name => t[name][i].shell_compact_id === f.ammunition[i].shell_compact_id)
        && a.count + t.fired_ammunition[i].count + t.lost_ammunition[i].count === f.ammunition[i].count), 'source stack conservation');
      const { fired_ammunition, lost_ammunition, loss_event, ...baseTerminal } = t;
      old.reservation.result = { ...baseTerminal, consumed_ammunition: f.ammunition.map((a, i) => ({ shell_compact_id: a.shell_compact_id, count: a.count - t.remaining_ammunition[i].count })) };
      if (row.status === 'aborted_restart') requireValue(t.loss_event === null && t.fired_ammunition.every(a => a.count === 0) && t.lost_ammunition.every(a => a.count === 0), 'restart no fabricated spending');
      else if (t.loss_event === null) requireValue(t.lost_ammunition.every(a => a.count === 0), 'loss without causal detonation');
      else {
        const e = t.loss_event, s = t.terminal_state;
        requireValue(t.lost_ammunition.some(a => a.count > 0) && t.remaining_ammunition.every(a => a.count === 0) && t.terminal_hp === 0
          && t.reason !== 'cancelled' && s.devices.find(a => a.extra_index === 27)?.health === 0
          && e.attacker_slot < s.roster_size && e.target_slot < s.roster_size
          && s.death.killer_slot === e.attacker_slot && s.death.tick === e.tick, 'actual nonempty rack loss/death linkage');
      }
      if (t.reason === 'cancelled') requireValue(t.terminal_hp === f.max_hp && t.loss_event === null && [...t.fired_ammunition, ...t.lost_ammunition].every(a => a.count === 0), 'pristine queue cancel');
      if (request.operation === 'finish') {
        requireValue(arrays.every(name => canonical(t[name]) === canonical(request[name])) && canonical(t.loss_event) === canonical(request.loss_event), 'finish exact accounting');
        if (request.results_json !== undefined) {
          const results = JSON.parse(request.results_json), own = results.participants.find(p => p.account_dbid === request.native_database_id);
          requireValue(own && own.shots === t.fired_ammunition.reduce((n, a) => n + a.count, 0)
            && own.health === t.terminal_hp && results.participants.length === t.terminal_state.roster_size, 'actual fired result statistics');
          if (t.loss_event !== null) requireValue(results.participants[t.loss_event.target_slot]?.account_dbid === request.native_database_id
            && t.loss_event.shot <= results.participants.reduce((n, a) => n + a.shots, 0), 'result causal target/shot');
        }
      }
    }
  }
  // This internal validation view reuses unchanged SOURCE/crew/terminal checks.
  // It is never returned, persisted, routed or sent to the old writer.
  validateMixedBattleReply(old, oldRequest(request)); return v;
}
export function validateLossResultsRequest(v, owner) {
  requireValue(exact(v, ['version', 'contract', 'operation', 'account_id', 'native_database_id', 'command_key', 'arena_id'])
    && v.version === 4 && v.contract === LOSS_CONTRACT && bytes(v) <= 2048, 'result request contract', 400);
  const { contract, ...old } = v; validateMixedResultsRequest({ ...old, version: 2 }, owner); return v;
}
export function validateLossResultsReply(v, request) {
  requireValue(exact(v, ['version', 'contract', 'operation', 'account_id', 'native_database_id', 'command_key', 'arena_id', 'status', 'acked', 'results_json',
    'replayed', 'code', 'policy_sha256', 'record_contract']) && v.version === 4 && v.contract === LOSS_CONTRACT && v.policy_sha256 === LOSS_POLICY_SHA256
    && (['missing', 'rejected'].includes(v.status) ? v.record_contract === null : ['mixed-v2', 'loss-v1'].includes(v.record_contract)), 'result record contract');
  if (v.status === 'rejected') {
    requireValue(['version', 'contract', 'operation', 'account_id', 'native_database_id', 'command_key', 'arena_id'].every(k => v[k] === request[k])
      && ['RESULT_MISMATCH', 'DUPLICATE_PAYLOAD_MISMATCH', 'AMMO_LOSS_POLICY_REQUIRED'].includes(v.code)
      && v.acked === false && v.replayed === false && v.results_json === null && bytes(v) <= 65536, 'rejected result binding'); return v;
  }
  const { contract, record_contract, ...old } = v, { contract: ignored, ...oldRequestValue } = request;
  validateMixedResultsReply({ ...old, version: 2, policy_sha256: MIXED_POLICY_SHA256 }, { ...oldRequestValue, version: 2 });
  requireValue(bytes(v) <= 65536, 'result reply budget'); return v;
}
