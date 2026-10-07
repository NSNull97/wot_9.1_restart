/** Build a server-owned game.account.v1 ownership assertion. */

import { createHash } from 'node:crypto';
import {
  GAME_ACCOUNT_CONTRACT, GAME_ACCOUNT_OWNERSHIP_SOURCE, GameAccountError,
  responseEnvelope,
} from '../contracts/game_account.mjs';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const NICKNAME = /^[A-Za-zА-Яа-яЁё0-9_]{3,24}$/u;
const MAX_PROFILE_BYTES = 8192;

function exactKeys(value, keys) {
  return value && typeof value === 'object' && !Array.isArray(value)
    && Object.keys(value).sort().join(',') === [...keys].sort().join(',');
}

function validIdentityAssertion(value) {
  return exactKeys(value, ['account_id', 'nickname', 'created_at'])
    && UUID.test(value.account_id) && typeof value.nickname === 'string'
    && NICKNAME.test(value.nickname) && Number.isSafeInteger(value.created_at)
    && value.created_at >= 1 && value.created_at <= 4000000000000;
}

function validProfile(value) {
  return value && typeof value === 'object' && !Array.isArray(value)
    && UUID.test(value.account_id) && typeof value.username === 'string'
    && NICKNAME.test(value.username)
    && Number.isSafeInteger(value.native_database_id)
    && value.native_database_id >= 1 && value.native_database_id <= 0x7fffffff
    && Number.isSafeInteger(value.created_at_ms) && value.created_at_ms >= 1
    && value.created_at_ms <= 4000000000000
    && Number.isSafeInteger(value.profile_version) && value.profile_version >= 1
    && value.profile_version <= 0x7fffffff
    && Number.isSafeInteger(value.snapshot_revision) && value.snapshot_revision >= 1
    && value.snapshot_revision <= 0x7fffffff;
}

function profileDigest(bytes) {
  if (!(bytes instanceof Uint8Array) || bytes.byteLength < 2 || bytes.byteLength > MAX_PROFILE_BYTES) {
    throw new GameAccountError('invalid_profile', 'Game profile bytes are outside bounds');
  }
  return createHash('sha256').update(bytes).digest('hex');
}

export function createOwnershipAssertion({ identityAssertion, gameProfile, profileBytes, ruleset = 'test_lab' } = {}) {
  if (!validIdentityAssertion(identityAssertion)) {
    throw new GameAccountError('identity_mismatch', 'Identity assertion shape is invalid');
  }
  if (!validProfile(gameProfile)) {
    throw new GameAccountError('profile_mismatch', 'Game profile shape is invalid');
  }
  if (gameProfile.account_id !== identityAssertion.account_id
      || gameProfile.username !== identityAssertion.nickname
      || gameProfile.created_at_ms !== identityAssertion.created_at) {
    throw new GameAccountError('ownership_mismatch', 'Identity and game profile subjects differ');
  }
  const profile_sha256 = profileDigest(profileBytes);
  return responseEnvelope({
    account_id: gameProfile.account_id,
    native_database_id: gameProfile.native_database_id,
    nickname: gameProfile.username,
    created_at: gameProfile.created_at_ms,
    profile_version: gameProfile.profile_version,
    snapshot_revision: gameProfile.snapshot_revision,
    profile_sha256,
    ruleset,
    identity_contract: 'identity.account.v1',
    ownership_source: GAME_ACCOUNT_OWNERSHIP_SOURCE,
  });
}

export { GAME_ACCOUNT_CONTRACT };
