/** Versioned account contract shared by the portal and identity service. */

export const IDENTITY_CONTRACT = 'identity.account.v1';
export const IDENTITY_OPERATIONS = new Set([
  'session/open', 'session/read', 'register', 'login', 'profile/update', 'session/revoke',
  'credentials/verify',
]);

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const TOKEN = /^[A-Za-z0-9_-]{43}$/;
const MAX_RESPONSE = 32 * 1024;

export class IdentityError extends Error {
  constructor(code, status = 503, message = code) {
    super(message);
    this.name = 'IdentityError';
    this.code = code;
    this.status = status;
  }
}

export function validSessionToken(value) {
  return typeof value === 'string' && TOKEN.test(value);
}

export function validAccountProfile(value) {
  return value && typeof value === 'object' && !Array.isArray(value)
    && UUID.test(value.account_id)
    && typeof value.nickname === 'string' && typeof value.nickname_key === 'string'
    && (typeof value.email === 'string' || value.email === null)
    && typeof value.display_name === 'string' && typeof value.bio === 'string'
    && Number.isSafeInteger(value.created_at) && Number.isSafeInteger(value.updated_at);
}

export function assertOperation(operation) {
  if (typeof operation !== 'string' || !IDENTITY_OPERATIONS.has(operation)) {
    throw new IdentityError('invalid_request', 400, 'Unsupported identity operation');
  }
}

export function requestEnvelope(operation, payload) {
  assertOperation(operation);
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new IdentityError('invalid_request', 400, 'Identity payload must be an object');
  }
  return { contract: IDENTITY_CONTRACT, operation, payload };
}

export function responseEnvelope(operation, data) {
  assertOperation(operation);
  return { contract: IDENTITY_CONTRACT, operation, ok: true, data };
}

export function errorEnvelope(operation, code) {
  assertOperation(operation);
  return { contract: IDENTITY_CONTRACT, operation, ok: false, error: { code } };
}

export function parseResponseEnvelope(bytes, expectedOperation) {
  if (!(bytes instanceof Uint8Array) || bytes.byteLength > MAX_RESPONSE) {
    throw new IdentityError('unavailable', 503, 'Identity response is too large');
  }
  let value;
  try { value = JSON.parse(Buffer.from(bytes).toString('utf8')); }
  catch { throw new IdentityError('unavailable', 503, 'Identity response is not JSON'); }
  if (!value || value.contract !== IDENTITY_CONTRACT || value.operation !== expectedOperation
      || typeof value.ok !== 'boolean' || (value.ok && !Object.hasOwn(value, 'data'))
      || (!value.ok && (!value.error || typeof value.error.code !== 'string'
        || Object.keys(value.error).length !== 1))) {
    throw new IdentityError('contract_mismatch', 409, 'Identity contract mismatch');
  }
  if (!value.ok) throw new IdentityError(value.error.code, statusFor(value.error.code));
  if (!validResponseData(expectedOperation, value.data)) throw new IdentityError('contract_mismatch', 409, 'Identity response data mismatch');
  return value.data;
}

function exactKeys(value, keys) {
  return value && typeof value === 'object' && !Array.isArray(value)
    && Object.keys(value).sort().join(',') === [...keys].sort().join(',');
}

function validSessionData(value) {
  return exactKeys(value, ['session_token', 'csrf', 'expires_at', 'profile'])
    && validSessionToken(value.session_token) && validSessionToken(value.csrf)
    && Number.isSafeInteger(value.expires_at) && (value.profile === null || validAccountProfile(value.profile));
}

function validResponseData(operation, value) {
  if (['session/open', 'session/read', 'register', 'login'].includes(operation)) return validSessionData(value);
  if (operation === 'profile/update') return exactKeys(value, ['profile']) && validAccountProfile(value.profile);
  if (operation === 'session/revoke') return exactKeys(value, ['revoked']) && value.revoked === true;
  if (operation === 'credentials/verify') return exactKeys(value, ['account_id', 'nickname', 'created_at'])
    && UUID.test(value.account_id) && typeof value.nickname === 'string' && Number.isSafeInteger(value.created_at);
  return false;
}

export function statusFor(code) {
  return {
    invalid_request: 400,
    invalid_fields: 422,
    invalid_credentials: 401,
    invalid_session: 401,
    forbidden: 403,
    email_taken: 409,
    nickname_taken: 409,
    contract_mismatch: 409,
    rate_limited: 429,
    unavailable: 503,
  }[code] || 503;
}
