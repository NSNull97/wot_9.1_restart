import { IdentityError, IDENTITY_CONTRACT, assertOperation, requestEnvelope, parseResponseEnvelope } from './identity.mjs';

const TOKEN = /^[A-Za-z0-9_-]{43}$/;

function endpoint(value) {
  let url;
  try { url = new URL(value); } catch { throw new TypeError('Identity origin must be a URL'); }
  if (url.protocol !== 'http:' || url.hostname !== '127.0.0.1' || !url.port
      || url.username || url.password || url.pathname !== '/' || url.search || url.hash) {
    throw new TypeError('Identity origin must be a numeric loopback HTTP origin');
  }
  return url;
}

export function createIdentityClient({ origin, secret, role, timeoutMs = 2500 } = {}) {
  const url = endpoint(origin);
  if (!TOKEN.test(secret || '')) throw new TypeError('Identity service secret shape');
  if (!['portal', 'game'].includes(role)) throw new TypeError('Identity service role');
  if (!Number.isInteger(timeoutMs) || timeoutMs < 100 || timeoutMs > 10000) throw new TypeError('Identity timeout');
  return {
    origin: url.origin,
    role,
    async call(operation, payload) {
      assertOperation(operation);
      if (role === 'portal' && operation === 'credentials/verify') {
        throw new IdentityError('forbidden', 403, 'Portal role cannot verify game credentials');
      }
      if (role === 'game' && operation !== 'credentials/verify') {
        throw new IdentityError('forbidden', 403, 'Game role cannot manage browser sessions');
      }
      const envelope = requestEnvelope(operation, payload);
      const body = Buffer.from(JSON.stringify(envelope));
      if (body.length > 16384) throw new IdentityError('invalid_request', 400, 'Identity request is too large');
      let response;
      try {
        response = await fetch(`${url.origin}/identity/v1/${encodeURIComponent(operation)}`, {
          method: 'POST', redirect: 'error', signal: AbortSignal.timeout(timeoutMs),
          headers: {
            Authorization: `Bearer ${secret}`,
            'X-Identity-Role': role,
            'Content-Type': 'application/json',
            'Content-Length': String(body.length),
            Connection: 'close',
          }, body,
        });
      } catch (error) {
        throw new IdentityError('unavailable', 503, error?.name === 'TimeoutError' ? 'Identity timeout' : 'Identity unavailable');
      }
      const declared = response.headers.get('content-length');
      if (!/^\d{1,6}$/.test(declared || '') || Number(declared) > 32768
          || response.headers.get('transfer-encoding')) {
        throw new IdentityError('contract_mismatch', 409, 'Identity response framing mismatch');
      }
      let bytes;
      try { bytes = new Uint8Array(await response.arrayBuffer()); }
      catch { throw new IdentityError('unavailable', 503, 'Identity response read failed'); }
      if (bytes.byteLength !== Number(declared)) throw new IdentityError('contract_mismatch', 409, 'Identity response length mismatch');
      const data = parseResponseEnvelope(bytes, operation);
      if (!response.ok) throw new IdentityError('contract_mismatch', 409, 'Identity HTTP status mismatch');
      return data;
    },
  };
}

export { IDENTITY_CONTRACT, IdentityError };
