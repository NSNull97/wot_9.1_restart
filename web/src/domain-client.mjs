/** Loopback client of the Domain/Account service (server/domain/protocol.py, wot091-domain.v1). */
import { connect } from 'node:net';
import { createHash, createHmac, randomBytes, timingSafeEqual } from 'node:crypto';

export const DOMAIN_SCHEMA = 'wot091-domain.v1';
// RES-30: one escaped 7..30-row result journal plus header (server/domain/protocol.py).
const MAX_FRAME = 655360 + 8192, MAX_HEADER = 1024;
const SECRET = /^[A-Za-z0-9_-]{43}$/;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

/** Explicit {version:1, endpoint:'127.0.0.1:<port>', secret_file} bridge option. */
export function domainConfiguration(value) {
  const keys = value && typeof value === 'object' && !Array.isArray(value) ? Object.keys(value).sort().join(',') : '';
  if (!value || Array.isArray(value) || typeof value !== 'object'
    || !['endpoint,secret_file,version', 'camouflage_v1,endpoint,secret_file,version'].includes(keys)
    || (value.camouflage_v1 !== undefined && typeof value.camouflage_v1 !== 'boolean')
    || (value.camouflage_v1 === true && process.env.WOT091_TEST_LAB !== '1')
    || value.version !== 1 || typeof value.endpoint !== 'string' || !/^127\.0\.0\.1:[1-9][0-9]{0,4}$/.test(value.endpoint)
    || Number(value.endpoint.split(':')[1]) > 65535 || typeof value.secret_file !== 'string') throw new Error('Domain service configuration');
  return { host: '127.0.0.1', port: Number(value.endpoint.split(':')[1]), secretFile: value.secret_file,
    ...(value.camouflage_v1 === true ? { camouflage: true } : {}) };
}

const CAP_REQUEST = Buffer.from('wot091-domain.v1:camouflage.v1:request\0', 'ascii');
const CAP_RESPONSE = Buffer.from('wot091-domain.v1:camouflage.v1:response\0', 'ascii');
const HEX = /^[0-9a-f]{64}$/;
function capText(value) {
  if (typeof value !== 'string') throw new Error('Domain capability text');
  const raw = Buffer.from(value, 'utf8');
  if (raw.length > MAX_HEADER) throw new Error('Domain capability text bound');
  const length = Buffer.alloc(4); length.writeUInt32BE(raw.length); return Buffer.concat([length, raw]);
}
function capOptional(value) { return value === null ? Buffer.from([0]) : Buffer.concat([Buffer.from([1]), capText(value)]); }
function digest(body) { return createHash('sha256').update(body).digest(); }
export function capabilityRequestProof(secret, serverNonce, header, body) {
  if (!HEX.test(serverNonce) || !HEX.test(header.camouflage_nonce)
      || !(header.camouflage_generation === '-' || HEX.test(header.camouflage_generation))
      || !Number.isInteger(header.id) || header.id < 1 || header.id >= 2 ** 32 || !Buffer.isBuffer(body))
    throw new Error('Domain capability request shape');
  const id = Buffer.alloc(4); id.writeUInt32BE(header.id);
  const bytes = Buffer.concat([CAP_REQUEST, capText(serverNonce), capText(header.camouflage_nonce), capText(header.camouflage_generation),
    id, capText(header.op), capOptional(header.account_id), capOptional(header.key), digest(body)]);
  return createHmac('sha256', Buffer.from(secret, 'ascii')).update(bytes).digest('hex');
}
export function capabilityResponseProof(secret, requestProof, actualGeneration, status, body) {
  if (!HEX.test(requestProof) || !(actualGeneration === '-' || HEX.test(actualGeneration))
      || !Number.isInteger(status) || status < 0 || status > 65535 || !Buffer.isBuffer(body))
    throw new Error('Domain capability response shape');
  const code = Buffer.alloc(2); code.writeUInt16BE(status);
  const bytes = Buffer.concat([CAP_RESPONSE, capText(requestProof), capText(actualGeneration), code, digest(body)]);
  return createHmac('sha256', Buffer.from(secret, 'ascii')).update(bytes).digest('hex');
}
function equalProof(expected, received) {
  return typeof received === 'string' && HEX.test(received) && timingSafeEqual(Buffer.from(expected, 'hex'), Buffer.from(received, 'hex'));
}

function frame(header, body) {
  const raw = Buffer.from(JSON.stringify(header), 'ascii');
  if (raw.length === 0 || raw.length > MAX_HEADER || 2 + raw.length + body.length > MAX_FRAME) throw new Error('Domain frame bound');
  const out = Buffer.alloc(6 + raw.length + body.length);
  out.writeUInt32BE(2 + raw.length + body.length, 0); out.writeUInt16BE(raw.length, 4);
  raw.copy(out, 6); body.copy(out, 6 + raw.length);
  return out;
}

function parse(payload) {
  if (payload.length < 3) throw new Error('Domain payload bound');
  const size = payload.readUInt16BE(0);
  if (size === 0 || size > MAX_HEADER || 2 + size > payload.length) throw new Error('Domain header bound');
  const raw = payload.subarray(2, 2 + size);
  if (raw.some(b => b > 0x7e)) throw new Error('Domain header encoding');
  const header = JSON.parse(raw.toString('ascii'));
  if (!header || typeof header !== 'object' || Array.isArray(header) || header.schema !== DOMAIN_SCHEMA) throw new Error('Domain header schema');
  return { header, body: payload.subarray(2 + size) };
}

/**
 * One authenticated connection per call: challenge, hello, one request, close.
 * The deadline covers the whole exchange; on expiry the socket is destroyed
 * (the Domain may still finish the command; its ledger makes a retry a replay).
 */
export function createDomainClient({ host, port, secret, maxReply = MAX_FRAME, camouflage = false }) {
  if (!SECRET.test(secret)) throw new Error('Domain secret must be exactly 43 base64url characters');
  if (typeof camouflage !== 'boolean') throw new Error('Domain camouflage option');
  let serial = 0, generation = null;
  function call(op, accountId, body, key, timeoutMs) {
    if (accountId !== null && !UUID.test(accountId)) return Promise.reject(new Error('Domain account identity'));
    if (camouflage && op !== 'describe' && generation === null) return Promise.reject(new Error('Domain camouflage handshake required'));
    const request = Buffer.from(body ?? '', 'utf8'), id = ++serial;
    return new Promise((done, fail) => {
      const socket = connect({ host, port, noDelay: true });
      let buffer = Buffer.alloc(0), stage = 'challenge', settled = false, serverNonce = null, requestProof = null;
      const finish = (error, value) => {
        if (settled) return; settled = true; clearTimeout(timer); socket.destroy();
        if (error) fail(error); else done(value);
      };
      const timer = setTimeout(() => finish(new Error('Domain deadline')), timeoutMs);
      socket.on('error', () => finish(new Error('Domain unavailable')));
      socket.on('close', () => finish(new Error('Domain closed')));
      socket.on('data', part => {
        buffer = Buffer.concat([buffer, part]);
        if (buffer.length > 4 + MAX_FRAME) return finish(new Error('Domain frame bound'));
        while (buffer.length >= 4) {
          const length = buffer.readUInt32BE(0);
          if (length === 0 || length > MAX_FRAME) return finish(new Error('Domain frame length'));
          if (buffer.length < 4 + length) return;
          let message;
          try { message = parse(buffer.subarray(4, 4 + length)); } catch (error) { return finish(error); }
          buffer = buffer.subarray(4 + length);
          if (stage === 'challenge') {
            if (typeof message.header.nonce !== 'string' || !/^[0-9a-f]{64}$/.test(message.header.nonce)) return finish(new Error('Domain challenge'));
            serverNonce = message.header.nonce;
            const proof = createHmac('sha256', Buffer.from(secret, 'ascii')).update(`${DOMAIN_SCHEMA}:${serverNonce}`).digest('hex');
            socket.write(frame({ schema: DOMAIN_SCHEMA, op: 'hello', proof }, Buffer.alloc(0))); stage = 'ready';
          } else if (stage === 'ready') {
            if (message.header.status !== 200) return finish(new Error('Domain authentication refused'));
            const header = { schema: DOMAIN_SCHEMA, id, op, account_id: accountId, key: key ?? null };
            if (camouflage) {
              header.camouflage_generation = op === 'describe' ? '-' : generation;
              header.camouflage_nonce = randomBytes(32).toString('hex');
              header.camouflage_request_proof = capabilityRequestProof(secret, serverNonce, header, request);
              requestProof = header.camouflage_request_proof;
            }
            socket.write(frame(header, request)); stage = 'reply';
          } else {
            if (message.header.id !== id || !Number.isInteger(message.header.status)) return finish(new Error('Domain reply identity'));
            if (message.body.length > maxReply) return finish(new Error('Domain reply bound'));
            if (camouflage) {
              let expected;
              try { expected = capabilityResponseProof(secret, requestProof, message.header.camouflage_generation, message.header.status, message.body); }
              catch { return finish(new Error('Domain capability response authentication')); }
              if (!equalProof(expected, message.header.camouflage_proof)) return finish(new Error('Domain capability response authentication'));
              if (op !== 'describe' && message.header.camouflage_generation !== generation) return finish(new Error('Domain camouflage generation changed'));
            }
            if (op === 'describe' && message.header.status === 200) {
              let value;
              try { value = JSON.parse(message.body.toString('utf8')); } catch { return finish(new Error('Domain capability response')); }
              if (camouflage) {
                if (value?.camouflage_v1 !== true || typeof value.camouflage_generation !== 'string'
                    || !/^[0-9a-f]{64}$/.test(value.camouflage_generation)
                    || message.header.camouflage_generation !== value.camouflage_generation
                    || (generation !== null && generation !== value.camouflage_generation))
                  return finish(new Error('Domain camouflage capability mismatch'));
                generation = value.camouflage_generation;
              } else if (value?.camouflage_v1 === true
                  || (value?.camouflage_v1 !== undefined && value.camouflage_v1 !== false)
                  || (value?.camouflage_generation !== undefined && value.camouflage_generation !== null)) {
                return finish(new Error('Domain camouflage capability mismatch'));
              }
            }
            return finish(null, { status: message.header.status, error: message.header.error ?? null, body: message.body });
          }
        }
      });
    });
  }
  return { call };
}
