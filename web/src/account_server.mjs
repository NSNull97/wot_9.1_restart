/** Opt-in account portal entrypoint; legacy web/src/server.mjs remains untouched. */
import { createServer } from 'node:http';
import { existsSync, readFileSync, realpathSync, statSync } from 'node:fs';
import { dirname, isAbsolute, relative, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createAccountPortalApp } from './account_portal.mjs';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const LOCAL = resolve(ROOT, 'local');
function inside(root, path) { const rel = relative(root, path); return rel === '' || (!rel.startsWith('..') && !isAbsolute(rel)); }
function localFile(value, maximum) {
  const path = resolve(value); if (!inside(LOCAL, path)) throw new Error('Portal file must stay in local/');
  let ancestor = path; while (!existsSync(ancestor)) ancestor = dirname(ancestor);
  if (!inside(realpathSync(LOCAL), realpathSync(ancestor))) throw new Error('Redirected portal path');
  const stat = statSync(path); if (!stat.isFile() || stat.size > maximum) throw new Error('Portal file bound');
  return path;
}
function config(path) {
  const file = localFile(path, 8192); const value = JSON.parse(readFileSync(file, 'utf8'));
  if (!value || value.version !== 1 || value.host !== '127.0.0.1' || !Number.isInteger(value.port) || value.port < 0 || value.port > 65535
      || typeof value.origin !== 'string' || typeof value.identity_origin !== 'string' || typeof value.identity_token_file !== 'string') throw new Error('Unsupported account portal configuration');
  const tokenPath = localFile(value.identity_token_file, 128); const secret = readFileSync(tokenPath, 'utf8');
  if (!/^[A-Za-z0-9_-]{43}$/.test(secret)) throw new Error('Portal identity token shape');
  return { ...value, secret };
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    if (process.argv.length !== 4 || process.argv[2] !== '--config') throw new Error('Use --config');
    const value = config(process.argv[3]);
    const runtime = createAccountPortalApp({ origin: value.origin, identityOrigin: value.identity_origin, identitySecret: value.secret });
    const server = createServer(runtime.app); server.listen(value.port, value.host, () => console.log(JSON.stringify({ event: 'account_portal_ready', host: value.host, port: server.address().port, contract: 'identity.account.v1' })));
    server.requestTimeout = 15000; server.headersTimeout = 10000; server.timeout = 20000; server.keepAliveTimeout = 5000;
    let stopping = false; const stop = () => { if (stopping) return; stopping = true; server.close(() => process.exit(0)); server.closeAllConnections(); };
    process.on('SIGINT', stop); process.on('SIGTERM', stop); process.on('message', message => { if (message === 'shutdown') stop(); });
  } catch { console.error('account_portal_start_failed: configuration_or_identity'); process.exitCode = 1; }
}
