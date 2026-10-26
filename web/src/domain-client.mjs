/** Loopback client of the Domain/Account service (server/domain/protocol.py, wot091-domain.v1). */
import { connect } from 'node:net';
import { createHmac } from 'node:crypto';

export const DOMAIN_SCHEMA = 'wot091-domain.v1';
const MAX_FRAME = 73728, MAX_HEADER = 1024;
const SECRET = /^[A-Za-z0-9_-]{43}$/;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

/** Explicit {version:1, endpoint:'127.0.0.1:<port>', secret_file} bridge option. */
export function domainConfiguration(value) {
  if (!value || Array.isArray(value) || typeof value !== 'object' || Object.keys(value).sort().join(',') !== 'endpoint,secret_file,version'
    || value.version !== 1 || typeof value.endpoint !== 'string' || !/^127\.0\.0\.1:[1-9][0-9]{0,4}$/.test(value.endpoint)
    || Number(value.endpoint.split(':')[1]) > 65535 || typeof value.secret_file !== 'string') throw new Error('Domain service configuration');
  return { host: '127.0.0.1', port: Number(value.endpoint.split(':')[1]), secretFile: value.secret_file };
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
export function createDomainClient({ host, port, secret, maxReply = MAX_FRAME }) {
  if (!SECRET.test(secret)) throw new Error('Domain secret must be exactly 43 base64url characters');
  let serial = 0;
  function call(op, accountId, body, key, timeoutMs) {
    if (accountId !== null && !UUID.test(accountId)) return Promise.reject(new Error('Domain account identity'));
    const request = Buffer.from(body ?? '', 'utf8'), id = ++serial;
    return new Promise((done, fail) => {
      const socket = connect({ host, port, noDelay: true });
      let buffer = Buffer.alloc(0), stage = 'challenge', settled = false;
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
            const proof = createHmac('sha256', Buffer.from(secret, 'ascii')).update(`${DOMAIN_SCHEMA}:${message.header.nonce}`).digest('hex');
            socket.write(frame({ schema: DOMAIN_SCHEMA, op: 'hello', proof }, Buffer.alloc(0))); stage = 'ready';
          } else if (stage === 'ready') {
            if (message.header.status !== 200) return finish(new Error('Domain authentication refused'));
            socket.write(frame({ schema: DOMAIN_SCHEMA, id, op, account_id: accountId, key: key ?? null }, request)); stage = 'reply';
          } else {
            if (message.header.id !== id || !Number.isInteger(message.header.status)) return finish(new Error('Domain reply identity'));
            if (message.body.length > maxReply) return finish(new Error('Domain reply bound'));
            return finish(null, { status: message.header.status, error: message.header.error ?? null, body: message.body });
          }
        }
      });
    });
  }
  return { call };
}
