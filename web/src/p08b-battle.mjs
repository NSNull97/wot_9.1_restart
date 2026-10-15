/** Private P08B DTO boundary. Native input never selects another owner or paths. */
export const BATTLE_POLICY_SHA256 = 'cddd7d8cfabe8a4df5543fdcef14dd5518c36bc8bce431cfb502a5c72903ccda';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const exact = (v, keys) => v && typeof v === 'object' && !Array.isArray(v)
  && Object.keys(v).sort().join(',') === [...keys].sort().join(',');
const integer = (v, min, max = 2147483646) => Number.isSafeInteger(v) && v >= min && v <= max;
const requireValue = (v, reason) => { if (!v) throw new Error(`P08B ${reason}`); };
const key = v => typeof v === 'string' && /^[A-Za-z0-9_:-]{1,96}$/.test(v);

export function battleConfiguration(value, primary) {
  requireValue(exact(value, ['version', 'policy_sha256', 'accounts']) && value.version === 1
    && value.policy_sha256 === BATTLE_POLICY_SHA256 && Array.isArray(value.accounts)
    && value.accounts.length >= 1 && value.accounts.length <= 6
    && value.accounts.every(v => typeof v === 'string' && UUID.test(v))
    && new Set(value.accounts).size === value.accounts.length && value.accounts.includes(primary), 'configured owners/policy');
  return [...value.accounts];
}

export function validateBattleRequest(request, owner) {
  const common = ['version', 'operation', 'account_id', 'native_database_id', 'command_key', 'expected_revision', 'run_id'];
  const extra = { run_open: [], inspect: [], admit: ['battle_id', 'native_inventory_id'],
    finish: ['battle_id', 'native_inventory_id', 'reservation_id', 'remaining_ap', 'terminal_hp', 'reason'] };
  requireValue(request && Object.hasOwn(extra, request.operation) && exact(request, [...common, ...extra[request.operation]])
    && request.version === 1 && request.account_id === owner && UUID.test(owner)
    && integer(request.native_database_id, 1, 2147483647) && integer(request.expected_revision, request.operation === 'inspect' ? 0 : 13)
    && key(request.command_key) && typeof request.run_id === 'string' && UUID.test(request.run_id), 'request context');
  if (request.operation === 'admit' || request.operation === 'finish') {
    const prefix = `${request.run_id}:`;
    const suffix = typeof request.battle_id === 'string' && request.battle_id.startsWith(prefix) ? request.battle_id.slice(prefix.length) : '';
    requireValue(/^[1-9][0-9]{0,19}$/.test(suffix) && BigInt(suffix) <= 18446744073709551615n
      && integer(request.native_inventory_id, 1, 2147483647), 'battle/selected inventory');
  }
  if (request.operation === 'finish') requireValue(key(request.reservation_id)
    && integer(request.remaining_ap, 0, 96) && integer(request.terminal_hp, 0, 2150)
    && ['manual_leave', 'battle_failure', 'disconnect', 'cancelled'].includes(request.reason), 'result bounds');
  requireValue(Buffer.byteLength(JSON.stringify(request)) <= 4096, 'request size');
  return request;
}

export function validateBattleReply(value, request) {
  requireValue(exact(value, ['version', 'operation', 'status', 'account_id', 'native_database_id', 'command_key',
    'run_id', 'source_revision', 'revision', 'replayed', 'code', 'reservation', 'policy_sha256'])
    && value.version === 1 && value.operation === request.operation && value.account_id === request.account_id
    && value.native_database_id === request.native_database_id && value.command_key === request.command_key
    && value.run_id === request.run_id && value.source_revision === request.expected_revision
    && integer(value.revision, 13) && typeof value.replayed === 'boolean'
    && ['ready', 'inspected', 'admitted', 'finished', 'rejected'].includes(value.status)
    && (value.code === null || typeof value.code === 'string' && /^[A-Z0-9_]{1,64}$/.test(value.code))
    && value.policy_sha256 === BATTLE_POLICY_SHA256 && Buffer.byteLength(JSON.stringify(value)) <= 8192,
  'reply identity/revision/schema');
  if (value.status === 'rejected') requireValue(value.code !== null && value.reservation === null, 'rejection payload');
  else {
    const expectedStatus = {run_open: 'ready', inspect: 'inspected', admit: 'admitted', finish: 'finished'}[request.operation];
    requireValue(value.status === expectedStatus && value.code === null && (request.operation === 'inspect'
      || request.operation === 'run_open' && value.revision >= value.source_revision && value.revision <= value.source_revision + 1
      || ['admit', 'finish'].includes(request.operation) && value.revision === value.source_revision + 1), 'successful revision');
    if (request.operation === 'admit' || request.operation === 'finish') requireValue(value.reservation !== null, 'missing reservation');
  }
  // Rust revalidates every frozen/result field and its canonical hash. The
  // bridge also bounds the nested envelope before returning any trusted DTO.
  if (value.reservation !== null) {
    const r = value.reservation;
    requireValue(exact(r, ['reservation_id', 'run_id', 'battle_id', 'native_inventory_id', 'vehicle_inventory_id',
      'status', 'frozen', 'frozen_sha256', 'result']) && key(r.reservation_id)
      && typeof r.run_id === 'string' && UUID.test(r.run_id)
      && typeof r.battle_id === 'string' && r.battle_id.startsWith(`${r.run_id}:`)
      && integer(r.native_inventory_id, 1, 2147483647) && typeof r.vehicle_inventory_id === 'string'
      && r.vehicle_inventory_id.length <= 128 && ['active', 'finished', 'aborted_restart'].includes(r.status)
      && typeof r.frozen_sha256 === 'string' && /^[0-9a-f]{64}$/.test(r.frozen_sha256)
      && r.frozen && typeof r.frozen === 'object' && !Array.isArray(r.frozen), 'reservation envelope');
    if (request.operation === 'admit' || request.operation === 'finish') requireValue(r.battle_id === request.battle_id
      && r.run_id === request.run_id && r.native_inventory_id === request.native_inventory_id, 'reservation selection');
    if (request.operation === 'run_open') requireValue(r.status === 'aborted_restart' && r.run_id !== request.run_id,
      'restart recovery binding');
    if (request.operation === 'inspect') requireValue(r.status === 'active', 'inspection reservation');
    if (value.status === 'admitted') requireValue(r.status === 'active' && r.result === null, 'admitted reservation');
    if (value.status === 'finished') requireValue(r.status === 'finished' && r.result !== null, 'finished reservation');
  }
  return value;
}
