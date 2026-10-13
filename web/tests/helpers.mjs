import { createServer } from 'node:net';
import { createSocket } from 'node:dgram';
import { mkdtempSync, mkdirSync, rmSync } from 'node:fs';
import { resolve, relative, isAbsolute } from 'node:path';
import { fileURLToPath } from 'node:url';

export const root = fileURLToPath(new URL('../../local/web/tests/', import.meta.url));
export function testDirectory() {
  mkdirSync(root, { recursive: true });
  return mkdtempSync(resolve(root, 'run-'));
}
export function removeTestDirectory(path) {
  const rel = relative(root, path);
  if (!rel.startsWith('run-') || rel.includes('..') || isAbsolute(rel)) throw new Error('Unsafe test cleanup');
  rmSync(path, { recursive: true, force: true });
}
export async function freePort() {
  // Offline service tests use the selected number for either transport. Keep
  // TCP reserved while probing UDP so a live UDP listener is never mistaken
  // for a free gateway port. Actual service leases still own the final check.
  for (let attempt = 0; attempt < 32; attempt++) {
    const tcp = createServer(), udp = createSocket({ type: 'udp4', reuseAddr: false });
    try {
      await new Promise((done, fail) => {
        tcp.once('error', fail); tcp.listen({ port: 0, host: '127.0.0.1', exclusive: true }, done);
      });
      const port = tcp.address().port;
      if (port >= 20014 && port <= 20017) continue;
      await new Promise((done, fail) => {
        udp.once('error', fail); udp.bind({ port, address: '127.0.0.1', exclusive: true }, done);
      });
      return port;
    } catch (error) {
      if (!['EADDRINUSE', 'EACCES'].includes(error.code)) throw error;
    } finally {
      await new Promise((done, fail) => {
        try { udp.close(done); }
        catch (error) { if (error.code === 'ERR_SOCKET_DGRAM_NOT_RUNNING') done(); else fail(error); }
      });
      if (tcp.listening) await new Promise((done, fail) => tcp.close(error => error ? fail(error) : done()));
    }
  }
  throw new Error('No free loopback TCP/UDP test port after 32 attempts');
}
export function browser(origin) {
  return {
    cookie: '', csrf: '',
    async request(path, { method = 'GET', data, headers = {}, body } = {}) {
      const response = await fetch(origin + path, {
        method, redirect: 'manual',
        headers: { ...(this.cookie ? { Cookie: this.cookie } : {}), ...(method === 'POST' ? { Origin: origin, 'Content-Type': 'application/x-www-form-urlencoded' } : {}), ...headers },
        body: body ?? (data ? new URLSearchParams({ csrf: this.csrf, ...data }) : undefined),
      });
      const cookie = response.headers.get('set-cookie');
      if (cookie) this.cookie = cookie.split(';')[0];
      const html = await response.text();
      const csrf = html.match(/name="csrf" value="([A-Za-z0-9_-]{43})"/);
      if (csrf) this.csrf = csrf[1];
      return { status: response.status, headers: response.headers, html, json: () => JSON.parse(html) };
    },
    get(path) { return this.request(path); },
    post(path, data = {}, headers = {}) { return this.request(path, { method: 'POST', data, headers }); },
  };
}
