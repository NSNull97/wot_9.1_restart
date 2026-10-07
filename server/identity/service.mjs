/** Canonical identity CLI. Frozen profile encoders remain explicit shared dependencies. */
import { readFileSync, statSync, realpathSync, existsSync } from 'node:fs';
import { resolve, relative, isAbsolute, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createIdentityBridge } from '../../web/src/game-adapter.mjs';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const LOCAL = resolve(ROOT, 'local');
const inside = (root, path) => {
  const rel = relative(root, path);
  return rel !== '' && !rel.startsWith('..') && !isAbsolute(rel);
};

export function readConfiguration(value) {
  const path = resolve(value);
  if (!inside(LOCAL, path)) throw new Error('Identity configuration must be in local/');
  if (!existsSync(LOCAL) || !inside(realpathSync(LOCAL), realpathSync(path))) {
    throw new Error('Redirected identity configuration');
  }
  const stat = statSync(path);
  if (!stat.isFile() || stat.size > 8192) throw new Error('Identity configuration bound');
  const bytes = readFileSync(path);
  if (bytes.length > 8192) throw new Error('Identity configuration grew');
  return JSON.parse(bytes.toString('utf8'));
}

export async function startIdentity(options) {
  return createIdentityBridge(options);
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    if (process.argv.length !== 4 || process.argv[2] !== '--config') throw new Error('Use --config');
    const bridge = await startIdentity(readConfiguration(process.argv[3]));
    console.log(JSON.stringify({ event: 'game_bridge_ready', host: '127.0.0.1', port: bridge.port, pid: process.pid }));
    let closing = false;
    const stop = async () => { if (closing) return; closing = true; await bridge.close(); };
    process.on('SIGINT', stop); process.on('SIGTERM', stop);
    process.on('message', value => { if (value === 'shutdown') stop(); });
  } catch {
    console.error('game_bridge_start_failed: configuration_or_storage');
    process.exitCode = 1;
  }
}
