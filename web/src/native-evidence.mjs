/** Explicit relocation sidecars for unchanged historical native proof bytes. */
import { createHash } from 'node:crypto';
import { existsSync, readFileSync, lstatSync, realpathSync } from 'node:fs';
import { basename, dirname, extname, isAbsolute, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { isDeepStrictEqual } from 'node:util';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const LOCAL = resolve(ROOT, 'local');
const PYTHON = resolve(ROOT, 'tools/native_evidence_relocation.py');
const SHA = /^[0-9a-f]{64}$/;
const CHECKPOINTS = {
  'native-ms1-crew': ['df0a9c26181a4efd65bfc8e9c34e2fbabc6f92a860db5676355890e400377a65',
    '6f41620908c318964213e8a64ccad91cdcb9f7dc78bae267fe29a48470ebd41e'],
  'native-ms1-ammo': ['683daac81143a9d7edfbe671870ba163db088c54f5101fa52e077f596ebbfc74',
    '263df3ff06a92458b4096627da2fd93b81d25e624d2eca283efbf37a2214e9a4'],
};
const LIMITS = { trace: 4194304, install_plan: 1048576, outcome: 65536,
  compiled: 262144, metadata: 8192, bundle: 262144 };
const digest = raw => createHash('sha256').update(raw).digest('hex');
const requireValue = (ok, message) => { if (!ok) throw new Error(message); };
const keys = (value, names) => value !== null && typeof value === 'object' && !Array.isArray(value)
  && Object.keys(value).sort().join(',') === [...names].sort().join(',');
const inside = (root, path) => { const rel = relative(root, path); return rel !== '' && !rel.startsWith('..') && !isAbsolute(rel); };

function noLinks(path) {
  requireValue(typeof path === 'string' && path.length <= 2048 && !path.includes('\0')
    && !path.split(/[\\/]/).includes('..'), 'Evidence path bound');
  path = resolve(path);
  for (let part = path; ; part = dirname(part)) {
    if (existsSync(part)) requireValue(!lstatSync(part).isSymbolicLink()
      && realpathSync(part).toLowerCase() === part.toLowerCase(), 'Linked evidence path');
    if (dirname(part) === part) break;
  }
  return path;
}
function local(path) {
  path = noLinks(path);
  requireValue(inside(LOCAL, path), 'Evidence must remain below local/');
  return path;
}
function read(path, maximum) {
  path = noLinks(path); const stat = lstatSync(path);
  requireValue(stat.isFile() && stat.size > 0 && stat.size <= maximum, 'Evidence file bound');
  const raw = readFileSync(path);
  requireValue(raw.length > 0 && raw.length <= maximum, 'Evidence read bound');
  return raw;
}
function absolute(value) {
  requireValue(typeof value === 'string' && value.length > 0 && value.length <= 1024
    && isAbsolute(value) && !value.includes('\0') && !value.split(/[\\/]/).includes('..'), 'Historical absolute path required');
  return resolve(value);
}
function relativeFile(value) {
  requireValue(typeof value === 'string' && value.length > 0 && value.length <= 256
    && !/[\\:\0]/.test(value) && !isAbsolute(value)
    && value.split('/').every(part => part !== '' && part !== '.' && part !== '..'), 'Evidence relative path escape');
  return value;
}
export function evidenceGenerator() {
  return { version: 1, file: PYTHON, sha256: digest(read(PYTHON, 131072)) };
}
export function evidenceImplementation() {
  return Object.fromEntries([['evidence_python', PYTHON], ['evidence_node', fileURLToPath(import.meta.url)]]
    .map(([key, path]) => { const raw = read(path, 131072); return [key, { path, bytes: raw.length, sha256: digest(raw) }]; }));
}

export function checkNativeEvidenceProof(path, kind) {
  path = local(path); const raw = read(path, 32768), value = JSON.parse(raw.toString('utf8')), proof = value?.source;
  requireValue(keys(value, ['version', 'kind', 'data', 'source']) && value.version === 1 && value.kind === kind
    && ['native-ms1-crew', 'native-ms1-ammo'].includes(kind)
    && keys(proof, ['trace_file', 'trace_sha256', 'record_index', 'install_plan_file',
      'install_plan_sha256', 'outcome_file', 'outcome_sha256']), 'Native proof envelope changed');
  const sidecar = noLinks(path + '.relocation.json');
  const files = {};
  if (existsSync(sidecar)) {
    requireValue(digest(raw) === CHECKPOINTS[kind][0], 'Unaccepted historical export checkpoint');
    const manifestRaw = read(local(sidecar), 16384), m = JSON.parse(manifestRaw.toString('utf8'));
    requireValue(Buffer.from(JSON.stringify(m, null, 2) + '\n').equals(manifestRaw), 'Canonical relocation manifest required');
    requireValue(keys(m, ['version', 'kind', 'export', 'source_roots', 'target_roots', 'files'])
      && m.version === 1 && m.kind === 'native-evidence-relocation', 'Relocation schema/version');
    requireValue(isDeepStrictEqual(m.export, { file: basename(path), bytes: raw.length, sha256: digest(raw), kind }), 'Relocation export binding changed');
    const config = JSON.parse(readFileSync(resolve(ROOT, 'config/project.local.json'), 'utf8').replace(/^\uFEFF/, ''));
    requireValue(isDeepStrictEqual(m.target_roots, Object.fromEntries(['original', 'research']
      .map(key => [key, realpathSync(config.paths[key + '_client_root'])]))), 'Relocation target client roots changed');
    requireValue(Array.isArray(m.files) && m.files.length === 6, 'Exact evidence closure required');
    for (const row of m.files) {
      requireValue(keys(row, ['role', 'source', 'file', 'bytes', 'sha256'])
        && Object.hasOwn(LIMITS, row.role) && !Object.hasOwn(files, row.role), 'Relocation file schema/role');
      const target = local(resolve(dirname(path), relativeFile(row.file)));
      requireValue(inside(dirname(path), target) && target !== path, 'Relocation target escaped export directory');
      const content = read(target, LIMITS[row.role]);
      requireValue(Number.isSafeInteger(row.bytes) && row.bytes === content.length
        && SHA.test(row.sha256) && row.sha256 === digest(content), 'Relocated evidence bytes changed');
      files[row.role] = { source: absolute(row.source), target, content, file: row.file };
    }
    const plan = JSON.parse(files.install_plan.content.toString('utf8')), prepared = dirname(absolute(proof.install_plan_file));
    requireValue(basename(proof.install_plan_file) === 'install-plan.json'
      && absolute(proof.outcome_file) === join(prepared, 'native-outcome.json'), 'Prepared run mismatch');
    const module = kind.slice(7).replaceAll('-', '_') + '_probe';
    const producers = plan.sources?.filter(row => row?.path === 'client_patch/' + module + '.py');
    requireValue(producers?.length === 1, 'One native producer required');
    const prefix = basename(path, extname(path)) + '.relocated/';
    const expected = {};
    for (const role of ['trace', 'install_plan', 'outcome']) expected[role] = [absolute(proof[role + '_file']),
      (role === 'trace' ? 'trace/' : 'prepared/') + basename(proof[role + '_file'])];
    for (const role of ['compiled', 'metadata']) {
      const rel = relativeFile(producers[0][role].replaceAll('\\', '/'));
      expected[role] = [join(prepared, rel), 'prepared/' + rel];
    }
    const bundle = 'bundle/res_mods/0.9.1/scripts/client/' + module + '.pyc';
    expected.bundle = [join(prepared, bundle), 'prepared/' + bundle];
    requireValue(new Set(Object.values(expected).map(row => row[0])).size === 6
      && new Set(Object.values(expected).map(row => row[1])).size === 6, 'Duplicate evidence mapping');
    for (const [role, [source, target]] of Object.entries(expected)) requireValue(files[role].source === source
      && files[role].file === prefix + target, 'Relocation mapping differs from original closure');
    requireValue(isDeepStrictEqual(m.source_roots, Object.fromEntries(['original', 'research']
      .map(key => [key, absolute(plan[key + '_root'])]))), 'Historical client root binding changed');
    requireValue(dirname(files.trace.source) === absolute(plan.settings.trace_dir), 'Historical trace root changed');
    const installed = plan.files?.filter(row => row?.path === 'res_mods/0.9.1/scripts/client/' + module + '.pyc');
    requireValue(installed?.length === 1 && digest(files.compiled.content) === installed[0].installed_sha256
      && digest(files.bundle.content) === installed[0].installed_sha256
      && digest(files.metadata.content) === CHECKPOINTS[kind][1], 'Historical producer closure changed');
  }
  // Full Python validation still establishes producer/event/clean process and
  // resource identity. Relogin rechecks every original hash and copied closure.
  for (const role of ['trace', 'install_plan', 'outcome']) {
    const content = files[role]?.content ?? read(local(proof[role + '_file']), LIMITS[role]);
    requireValue(SHA.test(proof[role + '_sha256']) && digest(content) === proof[role + '_sha256'], 'Native proof bytes changed');
  }
}
