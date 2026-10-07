/** Versioned game-account ownership contract for domain services. */

export const GAME_ACCOUNT_CONTRACT = 'game.account.v1';
export const GAME_ACCOUNT_OPERATIONS = new Set(['ownership/assert']);
export const GAME_ACCOUNT_OWNERSHIP_SOURCE = 'game-account-owner';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const SHA256 = /^[0-9a-f]{64}$/;
const NICKNAME = /^[A-Za-zА-Яа-яЁё0-9_]{3,24}$/u;
const RULESET = /^[a-z][a-z0-9_]{1,31}$/;

export class GameAccountError extends Error {
  constructor(code, message = code) {
    super(message);
    this.name = 'GameAccountError';
    this.code = code;
  }
}

function exactKeys(value, keys) {
  return value && typeof value === 'object' && !Array.isArray(value)
    && Object.keys(value).sort().join(',') === [...keys].sort().join(',');
}

function boundedRevision(value) {
  return Number.isSafeInteger(value) && value >= 1 && value <= 0x7fffffff;
}

export function validOwnershipData(value) {
  return exactKeys(value, [
    'account_id', 'native_database_id', 'nickname', 'created_at',
    'profile_version', 'snapshot_revision', 'profile_sha256', 'ruleset',
    'identity_contract', 'ownership_source',
  ])
    && UUID.test(value.account_id)
    && Number.isSafeInteger(value.native_database_id)
    && value.native_database_id >= 1 && value.native_database_id <= 0x7fffffff
    && typeof value.nickname === 'string' && NICKNAME.test(value.nickname)
    && Number.isSafeInteger(value.created_at) && value.created_at >= 1 && value.created_at <= 4000000000000
    && boundedRevision(value.profile_version) && boundedRevision(value.snapshot_revision)
    && SHA256.test(value.profile_sha256)
    && value.identity_contract === 'identity.account.v1'
    && value.ownership_source === GAME_ACCOUNT_OWNERSHIP_SOURCE
    && typeof value.ruleset === 'string' && RULESET.test(value.ruleset);
}

export function assertOwnershipData(value) {
  if (!validOwnershipData(value)) throw new GameAccountError('contract_mismatch', 'Invalid game ownership data');
  return value;
}

export function responseEnvelope(data) {
  assertOwnershipData(data);
  return { contract: GAME_ACCOUNT_CONTRACT, operation: 'ownership/assert', ok: true, data };
}

export function parseResponse(value) {
  if (!exactKeys(value, ['contract', 'operation', 'ok', 'data'])
      || value.contract !== GAME_ACCOUNT_CONTRACT || value.operation !== 'ownership/assert'
      || value.ok !== true) {
    throw new GameAccountError('contract_mismatch', 'Game ownership response envelope mismatch');
  }
  return assertOwnershipData(value.data);
}

export { UUID as GAME_ACCOUNT_UUID, SHA256 as GAME_ACCOUNT_SHA256 };
