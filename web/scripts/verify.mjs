import { spawnSync } from 'node:child_process';
import { mkdirSync, writeFileSync, readFileSync, readdirSync } from 'node:fs';
import { resolve, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';

const root = fileURLToPath(new URL('../', import.meta.url));
const stamp = new Date().toISOString().replace(/[:.]/g, '-');
const evidence = resolve(root, '../local/web/evidence', stamp);
mkdirSync(evidence, { recursive: true });
const tests = readdirSync(join(root, 'tests')).filter(name => name.endsWith('.test.mjs')).map(name => join(root, 'tests', name));
const result = spawnSync(process.execPath, ['--test', '--test-concurrency=1', '--test-reporter=tap', ...tests], {
  cwd: root, encoding: 'utf8', windowsHide: true, timeout: 120_000,
});
writeFileSync(join(evidence, 'http-tests.tap'), result.stdout || '');
writeFileSync(join(evidence, 'http-tests.stderr.txt'), result.stderr || '');
const files = [];
function walk(path) {
  for (const entry of readdirSync(path, { withFileTypes: true })) {
    if (['node_modules', '.npm-cache', '.cache'].includes(entry.name)) continue;
    const full = join(path, entry.name);
    if (entry.isDirectory()) walk(full);
    else if (!entry.name.endsWith('.log')) files.push({ path: relative(root, full).replaceAll('\\', '/'), sha256: createHash('sha256').update(readFileSync(full)).digest('hex') });
  }
}
walk(root);
const report = {
  status: result.status === 0 ? 'PASS' : 'FAIL', exitCode: result.status,
  error: result.error?.code || null, recordedAt: new Date().toISOString(),
  platform: process.platform, architecture: process.arch, node: process.version,
  command: 'npm run evidence', testCommand: 'node --test --test-concurrency=1 --test-reporter=tap tests/*.test.mjs',
  scope: 'Local web profile and static 0.9.1 catalog; native/client compatibility NOT_RUN',
  files,
};
writeFileSync(join(evidence, 'summary.json'), JSON.stringify(report, null, 2) + '\n');
console.log(result.stdout);
if (result.stderr) console.error(result.stderr);
console.log(`Evidence: ${evidence}`);
process.exitCode = result.status === 0 ? 0 : 1;
