/** Explicit v2 owner boundary. Full result JSON stays a string for exact u64. */
import { createHash } from 'node:crypto';
import { readFileSync, realpathSync, statSync } from 'node:fs';
import { isAbsolute, resolve } from 'node:path';
import { BATTLE_POLICY_SHA256, validateBattleReply } from './p08b-battle.mjs';

export const MIXED_POLICY_SHA256 = '71fddc60e36780a4be2eb4dfcfa1709791e23edf1a69d074940024404b37e0d5';
export const MIXED_SHELL_SHA256 = '6af1bdc74aff853360b282c3850e0aa3c97c856a7d39835c198c67fdeb342430';
export const MIXED_TERMINAL_SHA256 = 'cded466bf3c21243c10c0bcee8a013ab4cffc20f31f7275d4eab1672060b3717';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const SHA = /^[0-9a-f]{64}$/;
const key = v => typeof v === 'string' && /^[A-Za-z0-9_:-]{1,96}$/.test(v);
const integer = (v, lo, hi = 2147483647) => Number.isSafeInteger(v) && v >= lo && v <= hi;
const exact = (v, keys) => v && typeof v === 'object' && !Array.isArray(v)
  && Object.keys(v).sort().join(',') === [...keys].sort().join(',');
const requireValue = (ok, message, status) => { if (!ok) throw Object.assign(new Error(`P06T ${message}`), status ? { status } : {}); };
const canonical = v => JSON.stringify((function sort(x) {
  if (Array.isArray(x)) return x.map(sort);
  if (x && typeof x === 'object') return Object.fromEntries(Object.keys(x).sort().map(k => [k, sort(x[k])]));
  return x;
})(v));
const bytes = v => Buffer.byteLength(JSON.stringify(v));
const REASONS = ['manual_leave', 'battle_failure', 'disconnect', 'cancelled', 'battle_finished'];
const TYPES = {
  ms1: { native: 1, suffix: 'starter-vehicle-v1', descriptor: '010d1a000e00c90000001700170000', hp: 90, capacity: 96, crew: 2,
    shells: [2570, 2826, 3082], suffixes: ['ap', 'heat', 'he'], families: ['ARMOR_PIERCING', 'HOLLOW_CHARGE', 'HIGH_EXPLOSIVE'], devices: [25, 60, 100, 90, 40, 40, 54, 50, 30] },
  is7: { native: 2, suffix: 'test-is7-v1', descriptor: '011c3a002400cd000b002f003a0000', hp: 2150, capacity: 30, crew: 5,
    shells: [14602, 14858, 15114], suffixes: ['ap', 'apcr', 'he'], families: ['ARMOR_PIERCING', 'ARMOR_PIERCING_CR', 'HIGH_EXPLOSIVE'], devices: [360, 210, 200, 250, 250, 250, 210, 170, 120] },
};

export function mixedWorkerConfiguration(value) {
  requireValue(exact(value, ['version', 'policy_sha256', 'shell_catalog', 'terminal_policy']) && value.version === 2
    && value.policy_sha256 === MIXED_POLICY_SHA256, 'explicit worker policy');
  for (const [name, expected, maximum] of [['shell_catalog', MIXED_SHELL_SHA256, 32768], ['terminal_policy', MIXED_TERMINAL_SHA256, 32768]]) {
    const p = value[name];
    requireValue(typeof p === 'string' && isAbsolute(p) && statSync(p).isFile() && statSync(p).size <= maximum
      && resolve(p).toLowerCase() === realpathSync(p).toLowerCase()
      && createHash('sha256').update(readFileSync(p)).digest('hex') === expected, 'pinned trusted source file');
  }
  return value;
}
export function mixedConfiguration(value, poolOwners) {
  requireValue(exact(value, ['version', 'policy_sha256', 'accounts', 'shell_catalog', 'terminal_policy']) && Array.isArray(value.accounts)
    && value.accounts.length >= 1 && value.accounts.length <= 6 && Array.isArray(poolOwners)
    && value.accounts.every(a => typeof a === 'string' && UUID.test(a) && poolOwners.includes(a))
    && new Set(value.accounts).size === value.accounts.length, 'explicit owner subset/policy');
  const { accounts, ...worker } = value; mixedWorkerConfiguration(worker); return [...accounts];
}
function terminal(v, frozen, hp) {
  const p = TYPES[frozen.kind];
  requireValue(exact(v, ['policy_revision', 'roster_size', 'crew_active', 'crew', 'devices', 'fire', 'death'])
    && v.policy_revision === 'test_lab.p06t.devices-proxy-fire.v1' && integer(v.roster_size, 0, 6) && typeof v.crew_active === 'boolean'
    && Array.isArray(v.crew) && v.crew.length === frozen.crew_ids.length
    && v.crew.every((r, i) => exact(r, ['crew_id', 'alive']) && r.crew_id === frozen.crew_ids[i] && typeof r.alive === 'boolean')
    && v.crew_active === v.crew.some(r => r.alive) && Array.isArray(v.devices) && v.devices.length === p.devices.length
    && v.devices.every((r, i) => exact(r, ['extra_index', 'health', 'max_health']) && r.extra_index === 26 + i
      && r.max_health === p.devices[i] && integer(r.health, 0, r.max_health)), 'terminal source crew/devices');
  requireValue(exact(v.fire, ['active', 'ticks', 'damage']) && typeof v.fire.active === 'boolean'
    && integer(v.fire.ticks, 0, 216000) && integer(v.fire.damage, 0, 60000)
    && exact(v.death, ['reason', 'killer_slot', 'tick']) && integer(v.death.reason, -1, 10) && integer(v.death.tick, 0, 216000)
    && (v.death.killer_slot === null || integer(v.death.killer_slot, 0, v.roster_size - 1))
    && (hp > 0 && v.crew_active ? v.death.reason === -1 && v.death.killer_slot === null : v.death.reason >= 0), 'terminal fire/death');
}
function frozen(v, owner, expectedSha) {
  requireValue(exact(v, ['kind', 'descriptor_hex', 'native_inventory_id', 'vehicle_inventory_id', 'max_hp', 'crew_ids', 'capacity', 'ammunition', 'initial_shell_compact_id'])
    && Object.hasOwn(TYPES, v.kind), 'closed admitted frozen profile');
  const p = TYPES[v.kind];
  requireValue(v.descriptor_hex === p.descriptor && v.native_inventory_id === p.native && v.vehicle_inventory_id === `${owner}:${p.suffix}`
    && v.max_hp === p.hp && v.capacity === p.capacity && Array.isArray(v.crew_ids) && v.crew_ids.length === p.crew
    && new Set(v.crew_ids).size === p.crew && v.crew_ids.every(id => key(id) && id.length > owner.length + 1 && id.startsWith(`${owner}:`))
    && Array.isArray(v.ammunition) && v.ammunition.length === 3
    && v.ammunition.every((a, i) => exact(a, ['shell_definition_id', 'shell_compact_id', 'family', 'count'])
      && a.shell_definition_id === `shell:${v.kind}-stock-${p.suffixes[i]}` && a.shell_compact_id === p.shells[i]
      && a.family === p.families[i] && integer(a.count, 0, p.capacity)), 'frozen source/owner/stacks');
  const total = v.ammunition.reduce((n, a) => n + a.count, 0);
  requireValue(total >= 1 && total <= p.capacity && v.initial_shell_compact_id === v.ammunition.find(a => a.count > 0).shell_compact_id
    && SHA.test(expectedSha) && createHash('sha256').update(canonical(v)).digest('hex') === expectedSha, 'frozen capacity/initial/hash');
}
export function validateMixedBattleRequest(v, owner) {
  const common = ['version', 'operation', 'account_id', 'native_database_id', 'command_key', 'expected_revision', 'run_id'];
  const extra = { run_open: [], inspect: [], admit: ['battle_id', 'native_inventory_id'],
    finish: ['battle_id', 'native_inventory_id', 'reservation_id', 'remaining_ammunition', 'terminal_hp', 'terminal_state_json', 'reason'] };
  const natural = v?.operation === 'finish' && v.reason === 'battle_finished';
  requireValue(v && Object.hasOwn(extra, v.operation) && exact(v, [...common, ...extra[v.operation], ...(natural ? ['results_json'] : [])])
    && v.version === 2 && v.account_id === owner && UUID.test(owner) && integer(v.native_database_id, 1)
    && integer(v.expected_revision, v.operation === 'inspect' ? 0 : 13, 2147483646) && key(v.command_key)
    && typeof v.run_id === 'string' && UUID.test(v.run_id), 'request identity/fields', 400);
  if (['admit', 'finish'].includes(v.operation)) {
    const n = typeof v.battle_id === 'string' && v.battle_id.startsWith(`${v.run_id}:`) ? v.battle_id.slice(37) : '';
    requireValue(/^[1-9][0-9]{0,19}$/.test(n) && BigInt(n) <= 18446744073709551615n && integer(v.native_inventory_id, 1), 'request battle/vehicle', 400);
  }
  if (v.operation === 'finish') requireValue(key(v.reservation_id) && integer(v.terminal_hp, 0, 2150) && REASONS.includes(v.reason)
    && Array.isArray(v.remaining_ammunition) && v.remaining_ammunition.length === 3
    && v.remaining_ammunition.every(a => exact(a, ['shell_compact_id', 'count']) && integer(a.shell_compact_id, 1, 65535) && integer(a.count, 0, 160))
    && typeof v.terminal_state_json === 'string' && Buffer.byteLength(v.terminal_state_json) <= 8192, 'finish bounds', 400);
  if (natural) requireValue(typeof v.results_json === 'string' && v.results_json.length > 0 && Buffer.byteLength(v.results_json) <= 32768, 'full result bound', 400);
  requireValue(bytes(v) <= (natural ? 65536 : v.operation === 'finish' ? 16384 : 2048), 'request byte budget', 400); return v;
}
export function validateMixedBattleReply(v, request) {
  requireValue(exact(v, ['version', 'operation', 'status', 'account_id', 'native_database_id', 'command_key', 'run_id', 'source_revision', 'revision', 'replayed',
    'code', 'reservation', 'legacy_reservation', 'policy_sha256']) && v.version === 2 && v.operation === request.operation
    && v.account_id === request.account_id && v.native_database_id === request.native_database_id && v.command_key === request.command_key
    && v.run_id === request.run_id && v.source_revision === request.expected_revision && integer(v.revision, 13)
    && v.policy_sha256 === MIXED_POLICY_SHA256 && typeof v.replayed === 'boolean' && bytes(v) <= 8192, 'reply identity/policy/budget');
  const status = { run_open: 'ready', inspect: 'inspected', admit: 'admitted', finish: 'finished' }[request.operation];
  if (v.status === 'rejected') {
    requireValue(typeof v.code === 'string' && /^[A-Z0-9_]{1,64}$/.test(v.code) && v.reservation === null && v.legacy_reservation === null && !v.replayed, 'rejected payload'); return v;
  }
  requireValue(v.status === status && v.code === null && (request.operation === 'inspect' || request.operation === 'run_open'
    ? request.operation === 'inspect' || v.revision >= v.source_revision && v.revision <= v.source_revision + 1 : v.revision === v.source_revision + 1)
    && !(v.reservation && v.legacy_reservation), 'reply status/revision');
  if (request.operation === 'inspect') requireValue(!v.replayed, 'non-mutating inspection');
  if (v.legacy_reservation !== null) {
    requireValue(['run_open', 'inspect'].includes(request.operation) && v.reservation === null
      && v.legacy_reservation.vehicle_inventory_id?.startsWith(`${request.account_id}:`), 'legacy recovery owner');
    const { legacy_reservation, ...old } = v;
    validateBattleReply({ ...old, version: 1, policy_sha256: BATTLE_POLICY_SHA256, reservation: legacy_reservation }, { ...request, version: 1 });
  }
  const r = v.reservation;
  if (!r) { requireValue(!['admit', 'finish'].includes(request.operation), 'missing reservation'); return v; }
  requireValue(exact(r, ['reservation_id', 'run_id', 'battle_id', 'native_inventory_id', 'vehicle_inventory_id', 'status', 'frozen', 'frozen_sha256', 'result'])
    && key(r.reservation_id) && UUID.test(r.run_id) && typeof r.battle_id === 'string' && r.battle_id.startsWith(`${r.run_id}:`)
    && ['active', 'finished', 'aborted_restart'].includes(r.status), 'reservation identity/status');
  frozen(r.frozen, request.account_id, r.frozen_sha256);
  requireValue(r.native_inventory_id === r.frozen.native_inventory_id && r.vehicle_inventory_id === r.frozen.vehicle_inventory_id, 'reservation vehicle');
  if (['admit', 'finish'].includes(request.operation)) requireValue(r.run_id === request.run_id && r.battle_id === request.battle_id && r.native_inventory_id === request.native_inventory_id, 'reservation command binding');
  if (request.operation === 'admit') requireValue(r.status === 'active' && r.result === null && r.reservation_id === request.command_key, 'active admission');
  if (request.operation === 'finish') requireValue(r.status === 'finished' && r.result !== null, 'finished result');
  if (request.operation === 'inspect') requireValue(r.status === 'active' && r.result === null && !v.replayed, 'active inspection');
  if (request.operation === 'run_open') requireValue(r.status === 'aborted_restart' && r.run_id !== request.run_id && v.revision === v.source_revision + 1, 'restart recovery');
  if (r.result !== null) {
    const t = r.result;
    requireValue(exact(t, ['reason', 'remaining_ammunition', 'consumed_ammunition', 'terminal_hp', 'destroyed', 'repaired_hp', 'credits', 'xp', 'terminal_state'])
      && t.repaired_hp === r.frozen.max_hp && t.credits === 0 && t.xp === 0, 'terminal repair policy');
    for (const field of ['remaining_ammunition', 'consumed_ammunition']) requireValue(Array.isArray(t[field]) && t[field].length === 3
      && t[field].every((a, i) => exact(a, ['shell_compact_id', 'count']) && a.shell_compact_id === r.frozen.ammunition[i].shell_compact_id
        && integer(a.count, 0, r.frozen.ammunition[i].count)), 'terminal stack identity/bound');
    requireValue(t.remaining_ammunition.every((a, i) => a.count + t.consumed_ammunition[i].count === r.frozen.ammunition[i].count), 'stack conservation');
    if (r.status === 'aborted_restart') requireValue(t.reason === 'aborted_restart' && t.terminal_hp === null && t.destroyed === null && t.terminal_state === null
      && t.consumed_ammunition.every(a => a.count === 0), 'restart unknown/refund');
    else { requireValue(REASONS.includes(t.reason) && integer(t.terminal_hp, 0, r.frozen.max_hp), 'terminal health/reason'); terminal(t.terminal_state, r.frozen, t.terminal_hp);
      requireValue(t.destroyed === (t.terminal_hp === 0 || !t.terminal_state.crew_active), 'terminal destruction'); }
    if (request.operation === 'finish') requireValue(r.status === 'finished' && r.reservation_id === request.reservation_id && t.reason === request.reason
      && t.terminal_hp === request.terminal_hp && canonical(t.remaining_ammunition) === canonical(request.remaining_ammunition)
      && canonical(t.terminal_state) === canonical(JSON.parse(request.terminal_state_json)), 'finish snapshot binding');
  } else requireValue(r.status === 'active', 'terminal result missing');
  return v;
}
export function validateMixedResultsRequest(v, owner) {
  requireValue(exact(v, ['version', 'operation', 'account_id', 'native_database_id', 'command_key', 'arena_id']) && v.version === 2
    && ['query', 'ack'].includes(v.operation) && v.account_id === owner && UUID.test(owner) && integer(v.native_database_id, 1)
    && key(v.command_key) && typeof v.arena_id === 'string' && /^[1-9][0-9]{0,18}$/.test(v.arena_id) && BigInt(v.arena_id) <= 9223372036854775807n
    && bytes(v) <= 2048, 'result request', 400); return v;
}
export function validateMixedResultsReply(v, request) {
  const common = ['version', 'operation', 'account_id', 'native_database_id', 'command_key', 'arena_id'];
  requireValue(exact(v, [...common, 'status', 'acked', 'replayed', 'results_json', 'code', 'policy_sha256']) && common.every(k => v[k] === request[k])
    && v.policy_sha256 === MIXED_POLICY_SHA256 && typeof v.acked === 'boolean' && typeof v.replayed === 'boolean'
    && (request.operation === 'query' ? ['found', 'missing', 'rejected'].includes(v.status) && !v.replayed : ['acked', 'missing', 'rejected'].includes(v.status))
    && (v.status === 'rejected' ? ['RESULT_MISMATCH', 'DUPLICATE_PAYLOAD_MISMATCH'].includes(v.code) : v.code === null)
    && (['missing', 'rejected'].includes(v.status) ? v.results_json === null && !v.acked && !v.replayed
      : typeof v.results_json === 'string' && Buffer.byteLength(v.results_json) <= 32768 && (v.status !== 'acked' || v.acked))
    && bytes(v) <= 65536, 'result reply binding/schema'); return v;
}
