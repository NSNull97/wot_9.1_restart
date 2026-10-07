import { mkdirSync, realpathSync, existsSync } from 'node:fs';
import { resolve, relative, isAbsolute, join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createApp } from './app.mjs';
import { readNetworkConfig } from './network.mjs';

const { host, port, origins } = readNetworkConfig();

const webRoot = fileURLToPath(new URL('../', import.meta.url));
const allowedRoot = resolve(webRoot, '../local/web');
const dataDirectory = resolve(process.env.WEB_DATA_DIR || join(allowedRoot, 'runtime'));
const inside = (root, path) => { const rel = relative(root, path); return rel === '' || (!rel.startsWith('..') && !isAbsolute(rel)); };
if (!inside(allowedRoot, dataDirectory)) throw new Error('WEB_DATA_DIR must be inside local/web');
mkdirSync(allowedRoot, { recursive: true });
if (realpathSync(allowedRoot).toLowerCase() !== allowedRoot.toLowerCase()) throw new Error('local/web must not be redirected');
let existingAncestor = dataDirectory;
while (!existsSync(existingAncestor)) existingAncestor = dirname(existingAncestor);
if (!inside(realpathSync(allowedRoot), realpathSync(existingAncestor))) throw new Error('Redirected data ancestor is not allowed');
mkdirSync(dataDirectory, { recursive: true });
if (!inside(realpathSync(allowedRoot), realpathSync(dataDirectory))) throw new Error('Redirected data directory is not allowed');
const runtime = await createApp({ databasePath: join(dataDirectory, 'portal.sqlite'), origin: origins[0], allowedOrigins: origins });
const server = runtime.app.listen(port, host, () => console.log(`Web profile ready: ${origins.join(', ')} (listen ${host}:${port})`));
// Optional, bounded diagnosis of forwarding. Never log cookies, bodies or query strings.
if (process.env.WEB_TRACE_NETWORK === '1') {
  let traceCount = 0;
  server.prependListener('request', (req, res) => {
    if (traceCount++ >= 100) return;
    const rawPath = (req.url || '').split('?')[0];
    const path = /^\/(?:health|assets\/(?:site\.css|catalog\.css|mark\.svg))?$/.test(rawPath) ? rawPath : 'other';
    const requestOrigin = origins.find(value => new URL(value).host === req.headers.host) || 'unlisted';
    const fetchSite = ['same-origin', 'same-site', 'cross-site', 'none'].includes(req.headers['sec-fetch-site']) ? req.headers['sec-fetch-site'] : 'absent-or-other';
    res.once('finish', () => console.log(JSON.stringify({ event: 'web_network_trace', path,
      origin: requestOrigin, fetchSite, status: res.statusCode, contentType: res.getHeader('content-type') || null })));
  });
}
server.requestTimeout = 15_000;
server.headersTimeout = 10_000;
server.timeout = 20_000;
server.keepAliveTimeout = 5_000;
server.maxRequestsPerSocket = 100;
server.on('error', error => {
  console.error(error.code === 'EADDRINUSE' ? 'Web port is in use. Choose a different WEB_PORT.' : 'Web listener failed.');
  runtime.close();
  process.exitCode = 1;
});
let stopping = false;
function shutdown() {
  if (stopping) return;
  stopping = true;
  server.close(() => { runtime.close(); process.exit(0); });
  server.closeIdleConnections();
  setTimeout(() => { server.closeAllConnections(); }, 5000).unref();
}
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
process.on('message', message => { if (message === 'shutdown') shutdown(); });
