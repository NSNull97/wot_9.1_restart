import { createDemoApp } from './demo-app.mjs';

const port = Number(process.env.DEMO_PORT || 3091);
const origin = process.env.DEMO_ORIGIN || `http://127.0.0.1:${port}`;
if (!Number.isInteger(port) || port < 1024 || port > 65535 || (port >= 20014 && port <= 20020)) {
  throw new Error('Use a dedicated unprivileged demo port outside the game service ports');
}
const app = createDemoApp({ origin });
const server = app.listen(port, '127.0.0.1', () => console.log(`Catalog demo ready: ${origin} (loopback:${port})`));
server.requestTimeout = 15_000;
server.headersTimeout = 10_000;
server.timeout = 20_000;
server.keepAliveTimeout = 5_000;
server.maxRequestsPerSocket = 100;
server.on('error', error => {
  console.error(error.code === 'EADDRINUSE' ? 'Catalog demo port is occupied.' : 'Catalog demo listener failed.');
  process.exitCode = 1;
});
let stopping = false;
function shutdown() {
  if (stopping) return;
  stopping = true;
  server.close(() => process.exit(0));
  server.closeIdleConnections();
  setTimeout(() => server.closeAllConnections(), 5000).unref();
}
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
