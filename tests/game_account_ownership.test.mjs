import test from 'node:test';
import assert from 'node:assert/strict';
import { createOwnershipAssertion } from '../server/identity/ownership.mjs';
import { parseResponse } from '../server/contracts/game_account.mjs';

const accountId = 'c5326cc1-8524-479c-8bba-72e973489c22';
const identity = { account_id: accountId, nickname: 'sr_ascii_f4d1e9', created_at: 1791114365310 };
const profile = {
  account_id: accountId, username: 'sr_ascii_f4d1e9', native_database_id: 1,
  created_at_ms: 1791114365310, profile_version: 4, snapshot_revision: 4,
};
const profileBytes = Buffer.from(JSON.stringify({ profile_version: 4, account_id: accountId }));

test('builds and parses a game-owned account assertion without credentials', () => {
  const response = createOwnershipAssertion({ identityAssertion: identity, gameProfile: profile, profileBytes });
  const data = parseResponse(response);
  assert.deepEqual(Object.keys(data).sort(), [
    'account_id', 'created_at', 'identity_contract', 'native_database_id', 'nickname',
    'ownership_source', 'profile_sha256', 'profile_version', 'ruleset', 'snapshot_revision',
  ].sort());
  assert.equal(data.account_id, accountId);
  assert.equal(data.native_database_id, 1);
  assert.equal(data.profile_version, 4);
  assert.equal(data.snapshot_revision, 4);
  assert.equal(data.identity_contract, 'identity.account.v1');
  assert.equal(data.ownership_source, 'game-account-owner');
  assert.equal(Object.hasOwn(data, 'password'), false);
  assert.equal(Object.hasOwn(data, 'session_token'), false);
  assert.equal(Object.hasOwn(data, 'fixture_path'), false);
});

test('rejects identity and game profile subject mismatch', () => {
  assert.throws(
    () => createOwnershipAssertion({
      identityAssertion: { ...identity, account_id: '12345678-1234-4234-8234-123456789abc' },
      gameProfile: profile, profileBytes,
    }),
    error => error.code === 'ownership_mismatch',
  );
  assert.throws(
    () => createOwnershipAssertion({
      identityAssertion: { ...identity, nickname: 'other_user' },
      gameProfile: profile, profileBytes,
    }),
    error => error.code === 'ownership_mismatch',
  );
});

test('rejects invalid or oversized server profile bytes', () => {
  assert.throws(
    () => createOwnershipAssertion({ identityAssertion: identity, gameProfile: profile, profileBytes: Buffer.alloc(1) }),
    error => error.code === 'invalid_profile',
  );
  assert.throws(
    () => createOwnershipAssertion({ identityAssertion: identity, gameProfile: profile, profileBytes: Buffer.alloc(8193) }),
    error => error.code === 'invalid_profile',
  );
  assert.throws(
    () => createOwnershipAssertion({ identityAssertion: identity, gameProfile: { ...profile, native_database_id: 0 }, profileBytes }),
    error => error.code === 'profile_mismatch',
  );
});

test('rejects response envelope with leaked or extra fields', () => {
  const response = createOwnershipAssertion({ identityAssertion: identity, gameProfile: profile, profileBytes });
  assert.throws(() => parseResponse({ ...response, data: { ...response.data, email: 'owner@example.invalid' } }),
    error => error.code === 'contract_mismatch');
  assert.throws(() => parseResponse({ ...response, data: { ...response.data, session_token: 'token' } }),
    error => error.code === 'contract_mismatch');
  assert.throws(() => parseResponse({ ...response, operation: 'ownership/read' }),
    error => error.code === 'contract_mismatch');
});
