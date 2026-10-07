import { createServer } from 'node:net';
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
  const socket = createServer();
  await new Promise((resolve, reject) => { socket.once('error', reject); socket.listen(0, '127.0.0.1', resolve); });
  const port = socket.address().port;
  await new Promise(resolve => socket.close(resolve));
  if (port >= 20014 && port <= 20017) return freePort();
  return port;
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
