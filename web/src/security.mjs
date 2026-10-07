import { createHash, randomBytes, scrypt, timingSafeEqual } from 'node:crypto';
import { promisify } from 'node:util';

const derive = promisify(scrypt);
const COST = { N: 131072, r: 8, p: 1, maxmem: 192 * 1024 * 1024 };
const PREFIX = 'scrypt$v1$131072$8$1';
let activeHashes = 0;

export const token = () => randomBytes(32).toString('base64url');
export const digest = value => createHash('sha256').update(value).digest('hex');
export const validToken = value => typeof value === 'string' && /^[A-Za-z0-9_-]{43}$/.test(value);
export const validPassword = value => typeof value === 'string' && [...value].length >= 15
  && [...value].length <= 128 && Buffer.byteLength(value, 'utf8') <= 512;

export function equalToken(left, right) {
  return validToken(left) && validToken(right)
    && timingSafeEqual(Buffer.from(left), Buffer.from(right));
}

async function key(password, salt) {
  // Reject excess work; do not build an unbounded password-hashing queue.
  if (activeHashes >= 2) {
    const error = new Error('Password service busy');
    error.status = 503;
    throw error;
  }
  activeHashes++;
  try { return await derive(password, salt, 64, COST); }
  finally { activeHashes--; }
}

export async function hashPassword(password) {
  const salt = randomBytes(16).toString('hex');
  return `${PREFIX}$${salt}$${(await key(password, salt)).toString('hex')}`;
}

export async function verifyPassword(password, encoded) {
  const parts = encoded.split('$');
  if (parts.length !== 7 || parts.slice(0, 5).join('$') !== PREFIX
    || !/^[a-f0-9]{32}$/.test(parts[5]) || !/^[a-f0-9]{128}$/.test(parts[6])) {
    throw new Error('Unsupported password record');
  }
  const candidate = await key(password, parts[5]);
  return timingSafeEqual(candidate, Buffer.from(parts[6], 'hex'));
}

export function sessionCookie(raw) {
  if (typeof raw !== 'string' || raw.length > 4096) return null;
  const matches = raw.split(';').map(item => item.trim()).filter(item => item.startsWith('web_sid='));
  if (matches.length !== 1) return null;
  const value = matches[0].slice(8);
  return validToken(value) ? value : null;
}

export function textField(value, min, max) {
  if (typeof value !== 'string') return null;
  const clean = value.normalize('NFC').trim();
  if ([...clean].length < min || [...clean].length > max || /[\p{Cc}\p{Cf}]/u.test(clean)) return null;
  return clean;
}

// Finite alphabet keeps the policy identical across the modern site and #717.
export function nicknameField(value) {
  if (typeof value !== 'string' || value.length > 96) return null;
  const raw = value.replace(/^ +| +$/g, '');
  if (!/^(?:[Ее]\u0308|[Ии]\u0306|[A-Za-zА-Яа-яЁё0-9_])+$/.test(raw)) return null;
  const display = raw.normalize('NFC');
  if ([...display].length < 3 || [...display].length > 24 || Buffer.byteLength(display) > 48) return null;
  return { display, key: display.toLowerCase() };
}

export function emailField(value) {
  if (typeof value !== 'string' || value.length > 1024 || /[^\x00-\x7f]/.test(value)) return null;
  const email = value.replace(/^[\x09-\x0d\x20]+|[\x09-\x0d\x20]+$/g, '').toLowerCase();
  if (email.length > 254 || email.split('@').length !== 2) return null;
  const [local, domain] = email.split('@');
  if (local.length < 1 || local.length > 64 || !/^[a-z0-9.!#$%&'*+/=?^_`{|}~-]+$/.test(local)
      || local.startsWith('.') || local.endsWith('.') || local.includes('..')) return null;
  const labels = domain.split('.');
  if (labels.length < 2 || labels.some(label => label.length > 63
      || !/^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/.test(label)) || !/[a-z]/.test(labels.at(-1))) return null;
  return email;
}
