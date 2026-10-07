// Listening interfaces and browser origins are separate, especially behind port forwarding.
export function validateOrigins(origins) {
  if (!Array.isArray(origins) || origins.length < 1 || origins.length > 8) {
    throw new Error('Configure between one and eight exact HTTP origins');
  }
  const result = new Map();
  for (const origin of origins) {
    if (typeof origin !== 'string' || origin.length > 253) throw new Error('Invalid web origin');
    const target = new URL(origin);
    if (target.protocol !== 'http:' || target.origin !== origin || target.username || target.password
      || !target.hostname || target.hostname.includes('*') || ['0.0.0.0','[::]'].includes(target.hostname)) {
      throw new Error('Use an exact http://HOST[:PORT] browser origin, not a wildcard listener');
    }
    result.set(target.host, target.origin);
  }
  return result;
}

export function readNetworkConfig(env = process.env) {
  const host = env.WEB_HOST || '127.0.0.1';
  if (!['127.0.0.1','0.0.0.0'].includes(host)) throw new Error('WEB_HOST must be 127.0.0.1 or 0.0.0.0');
  const port = Number(env.WEB_PORT || 3091);
  if (!Number.isInteger(port) || port < 1024 || port > 65535 || (port >= 20014 && port <= 20017)) {
    throw new Error('Use an unprivileged dedicated web port outside 20014–20017');
  }
  if (host === '0.0.0.0' && !env.WEB_ORIGINS) throw new Error('WEB_ORIGINS is required for network access');
  const origins = env.WEB_ORIGINS ? env.WEB_ORIGINS.split(',').map(value=>value.trim()) : [`http://127.0.0.1:${port}`];
  validateOrigins(origins);
  return { host, port, origins };
}
