/** Offline, explicit MS-1 crew plan/apply/rollback. No gameplay mutation route. */
import { DatabaseSync } from 'node:sqlite';
import { createHash } from 'node:crypto';
import { createServer } from 'node:net';
import { createSocket } from 'node:dgram';
import { spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync, mkdirSync, existsSync, realpathSync, lstatSync,
  readdirSync, renameSync, unlinkSync, openSync, closeSync, fsyncSync } from 'node:fs';
import { dirname, resolve, relative, isAbsolute, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { isDeepStrictEqual } from 'node:util';
import { openIdentityReader } from './store.mjs';
import { loadGarageService, validateGrantedProfile, validateGrantedFixture,
  grantedOverview, isGrantedOverview, LEGACY_ENCODER_SHA256 } from './test-garage.mjs';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const LOCAL = resolve(ROOT, 'local');
const SELF = fileURLToPath(import.meta.url);
const GENERATOR = resolve(ROOT, 'tools/ms1_crew_state.py');
const LEGACY = resolve(ROOT, 'tools/hangar_state.py');
const GARAGE_GENERATOR = resolve(ROOT, 'tools/test_garage_state.py');
const GARAGE_MODULE = resolve(ROOT, 'web/src/test-garage.mjs');
const GARAGE_GENERATOR_SHA256 = 'dec1f884dd8b22ef0d4a6c21389cb37c075f008feb6a12bc7d43888c5b4c5825';
const GARAGE_MODULE_SHA256 = '86f946a10ee4d2a4088cf73df18c0dd4286807a500b8aeacfedf0a527a0c40e3';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const SHA = /^[0-9a-f]{64}$/;
const MAX_DB = 64 * 1024 * 1024;
const PROFILE_FIELDS = ['profile_version', 'account_id', 'username', 'native_database_id',
  'created_at_ms', 'snapshot_revision', 'resources', 'statistics', 'inventory', 'test_grant', 'crew', 'crew_grant'];
const digest = value => createHash('sha256').update(value).digest('hex');
const requireValue = (condition, message) => { if (!condition) throw new Error(message); };
const integer = (n, low = 0, high = 2147483647) => Number.isSafeInteger(n) && n >= low && n <= high;
const inside = (base, path) => { const rel = relative(base, path); return rel !== '' && !rel.startsWith('..') && !isAbsolute(rel); };
function keys(value, expected) {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    && Object.keys(value).sort().join(',') === [...expected].sort().join(',');
}
function localPath(value) {
  requireValue(typeof value === 'string' && value.length > 0, 'Explicit local path required');
  const path = resolve(ROOT, value);
  requireValue(inside(LOCAL, path), 'Path must remain strictly below project local/');
  let ancestor = path;
  while (!existsSync(ancestor)) ancestor = dirname(ancestor);
  const real = realpathSync(ancestor), root = realpathSync(LOCAL);
  requireValue(real === root || inside(root, real), 'Redirected local path');
  return path;
}
function read(path, maximum) {
  const stat = lstatSync(path);
  requireValue(stat.isFile() && !stat.isSymbolicLink() && stat.size <= maximum, 'File size/type bound');
  const bytes = readFileSync(path);
  requireValue(bytes.length <= maximum, 'File grew beyond bound');
  return bytes;
}
function json(path, maximum = 8192) { return JSON.parse(read(path, maximum).toString('utf8')); }
function writeNew(path, value) {
  const bytes = Buffer.isBuffer(value) ? value : Buffer.from(JSON.stringify(value, null, 2) + '\n');
  const fd = openSync(path, 'wx', 0o600);
  try { writeFileSync(fd, bytes); fsyncSync(fd); } finally { closeSync(fd); }
}
function source(path, maximum = 1024 * 1024) {
  const bytes = read(path, maximum);
  return { path, bytes: bytes.length, sha256: digest(bytes) };
}
function checkSource(item, maximum = 1024 * 1024) {
  requireValue(keys(item, ['path', 'bytes', 'sha256']) && SHA.test(item.sha256)
    && isDeepStrictEqual(source(localPath(item.path), maximum), item), 'Native source provenance changed');
}
function tree(directory) {
  localPath(directory);
  const rows = []; let total = 0, nodes = 0;
  function visit(path, depth = 0) {
    requireValue(++nodes <= 96 && depth <= 4, 'Snapshot directory/node bound');
    const stat = lstatSync(path);
    requireValue(!stat.isSymbolicLink(), 'Snapshot symlink refused');
    if (stat.isDirectory()) {
      for (const name of readdirSync(path).sort()) visit(join(path, name), depth + 1);
    } else {
      requireValue(stat.isFile() && rows.length < 64, 'Snapshot file bound');
      const bytes = read(path, 1024 * 1024); total += bytes.length;
      requireValue(total <= 2 * 1024 * 1024, 'Snapshot total bound');
      rows.push({ file: relative(directory, path).replaceAll('\\', '/'), bytes: bytes.length, sha256: digest(bytes) });
    }
  }
  visit(directory);
  return { sha256: digest(JSON.stringify(rows)), files: rows };
}
function implementation() {
  requireValue(digest(read(LEGACY, 131072)) === LEGACY_ENCODER_SHA256
    && digest(read(GARAGE_GENERATOR, 131072)) === GARAGE_GENERATOR_SHA256
    && digest(read(GARAGE_MODULE, 131072)) === GARAGE_MODULE_SHA256, 'Frozen pre-crew implementation changed');
  return Object.fromEntries([['module', SELF], ['generator', GENERATOR], ['garage_module', GARAGE_MODULE],
    ['garage_generator', GARAGE_GENERATOR], ['legacy_encoder', LEGACY],
    ['client_audit', resolve(ROOT, 'tools/client_audit.py')], ['packed_xml', resolve(ROOT, 'tools/packed_xml.py')],
    ['literal_verifier', resolve(ROOT, 'tools/verify_hangar.py')],
    ['bridge', resolve(ROOT, 'web/src/game-adapter.mjs')], ['identity_reader', resolve(ROOT, 'web/src/store.mjs')],
    ['identity_validation', resolve(ROOT, 'web/src/security.mjs')]]
    .map(([key, path]) => [key, source(path, 131072)]));
}
function domainCrew(id) {
  return ['commander', 'driver'].map(role => ({ crew_id: `${id}:ms1-${role}-v1`,
    vehicle_inventory_id: `${id}:starter-vehicle-v1`, role, role_level: 100, skills: [] }));
}
function baseProfile(profile) {
  const base = structuredClone(profile);
  delete base.crew; delete base.crew_grant;
  base.profile_version = 2; base.snapshot_revision = 2;
  requireValue(Array.isArray(base.inventory) && base.inventory.length === 2
    && base.inventory[0]?.crew_assigned === true, 'Only MS-1 crew assignment is supported');
  base.inventory[0].crew_assigned = false;
  validateGrantedProfile(base);
  return base;
}
export function validateCrewProfile(profile, baseBytes) {
  requireValue(keys(profile, PROFILE_FIELDS) && profile.profile_version === 3 && profile.snapshot_revision === 3,
    'Exact profile3 required');
  const base = baseProfile(profile);
  requireValue(isDeepStrictEqual(profile.crew, domainCrew(profile.account_id)), 'Exact two MS-1 domain crew members required');
  requireValue(keys(profile.crew_grant, ['grant_id', 'granted_at_ms', 'base_profile_sha256', 'native_export_sha256'])
    && profile.crew_grant.grant_id === 'test-ms1-crew-v1'
    && integer(profile.crew_grant.granted_at_ms, profile.test_grant.granted_at_ms, 2147483647999)
    && SHA.test(profile.crew_grant.base_profile_sha256) && SHA.test(profile.crew_grant.native_export_sha256),
  'Crew grant provenance/time bounds');
  if (baseBytes !== undefined) {
    requireValue(Buffer.isBuffer(baseBytes) && baseBytes.length <= 8192
      && digest(baseBytes) === profile.crew_grant.base_profile_sha256
      && isDeepStrictEqual(JSON.parse(baseBytes.toString('utf8')), base), 'Exact previous profile2 mismatch');
  }
  requireValue(Buffer.byteLength(JSON.stringify(profile)) <= 8192, 'Profile size bound');
  return profile;
}
export function crewOverview(profile) {
  validateCrewProfile(profile);
  const value = grantedOverview(baseProfile(profile));
  value.snapshotRevision = 3; value.asOf = new Date(profile.crew_grant.granted_at_ms).toISOString();
  value.inventory[0].crewAssigned = true;
  return value;
}
export function isCrewOverview(value, id) {
  if (value?.snapshotRevision !== 3 || value?.inventory?.[0]?.crewAssigned !== true) return false;
  const previous = structuredClone(value);
  previous.snapshotRevision = 2; previous.inventory[0].crewAssigned = false;
  return isGrantedOverview(previous, id);
}

function checkCrewProof(path) {
  const value = json(path, 32768), proof = value?.source;
  requireValue(keys(value, ['version', 'kind', 'data', 'source']) && value.version === 1
    && value.kind === 'native-ms1-crew' && keys(proof, ['trace_file', 'trace_sha256', 'record_index',
      'install_plan_file', 'install_plan_sha256', 'outcome_file', 'outcome_sha256']), 'Crew proof envelope changed');
  // The generator already validated the original event, compiled probe and
  // clean native outcome. Keep those exact evidence bytes available across
  // plan/apply/relogin; do not silently accept a now-unverifiable reference.
  for (const [name, maximum] of [['trace', 4 * 1024 * 1024], ['install_plan', 1024 * 1024], ['outcome', 65536]]) {
    requireValue(SHA.test(proof[name + '_sha256'])
      && digest(read(localPath(proof[name + '_file']), maximum)) === proof[name + '_sha256'], 'Crew native proof changed');
  }
}

/** This validates local immutable provenance; independent Python acceptance
 * verifies the exact literal state delta and the actual native GUI separately. */
export function validateCrewFixture(directory, profile, { nativeMs1, nativeIs7, baseFixture }) {
  directory = localPath(directory); baseFixture = localPath(baseFixture);
  const baseBytes = read(join(baseFixture, 'profile-input.json'), 8192);
  validateCrewProfile(profile, baseBytes);
  const previous = JSON.parse(baseBytes.toString('utf8'));
  validateGrantedFixture(baseFixture, previous, { nativeMs1, nativeIs7 });
  const manifest = json(join(directory, 'manifest.json'), 65536);
  const manifestFields = ['fixture_version', 'profile_version', 'snapshot_revision', 'wire_sync_revision',
    'compatibility_catalog_revision', 'ruleset', 'account_id', 'native_database_id', 'generator',
    'native_descriptors', 'profile_source', 'base_profile_source', 'files', 'grant', 'preservation', 'native_compatibility'];
  requireValue(keys(manifest, manifestFields), 'Exact crew fixture manifest fields required');
  const raw = read(join(directory, 'profile-input.json'), 8192), storedBase = read(join(directory, 'base-profile-input.json'), 8192);
  requireValue(isDeepStrictEqual(JSON.parse(raw.toString('utf8')), profile) && storedBase.equals(baseBytes), 'Crew fixture profile provenance mismatch');
  requireValue(manifest.fixture_version === 3 && manifest.profile_version === 3 && manifest.snapshot_revision === 3
    && manifest.wire_sync_revision === 1 && manifest.compatibility_catalog_revision === 3 && manifest.ruleset === 'test_lab'
    && manifest.account_id === profile.account_id && manifest.native_database_id === profile.native_database_id
    && isDeepStrictEqual(manifest.grant, profile.test_grant), 'Crew fixture identity/version/grant mismatch');
  const impl = implementation();
  requireValue(isDeepStrictEqual(manifest.generator, { file: GENERATOR, sha256: impl.generator.sha256,
    dependency: { file: LEGACY, sha256: LEGACY_ENCODER_SHA256 },
    base_generator: { file: GARAGE_GENERATOR, sha256: GARAGE_GENERATOR_SHA256 } }), 'Crew generator source changed');
  for (const [field, file, bytes] of [['profile_source', 'profile-input.json', raw], ['base_profile_source', 'base-profile-input.json', storedBase]]) {
    requireValue(isDeepStrictEqual(manifest[field], { file, relative_to: 'fixture_directory', sha256: digest(bytes) }), 'Crew fixture input hash mismatch');
  }
  const native = manifest.native_descriptors;
  requireValue(native?.ms1?.sha256 === digest(read(localPath(nativeMs1), 65536))
    && native?.is7?.sha256 === digest(read(localPath(nativeIs7), 32768))
    && keys(native?.crew, ['file', 'bytes', 'sha256']) && isAbsolute(native.crew.file)
    && native.crew.sha256 === profile.crew_grant.native_export_sha256
    && isDeepStrictEqual(source(localPath(native.crew.file), 65536), { path: native.crew.file,
      bytes: native.crew.bytes, sha256: native.crew.sha256 }), 'Crew native source mismatch');
  checkCrewProof(native.crew.file);
  requireValue(Array.isArray(manifest.files) && manifest.files.length === 3, 'Exactly three native payloads required');
  for (const name of ['state.bin', 'shop.bin', 'dossier.bin']) {
    const rows = manifest.files.filter(item => item.file === name), bytes = read(join(directory, name), 16384);
    requireValue(rows.length === 1 && keys(rows[0], ['file', 'bytes', 'sha256', 'opcodes'])
      && Array.isArray(rows[0].opcodes) && rows[0].opcodes.length <= 32
      && rows[0].opcodes.every(opcode => typeof opcode === 'string' && /^[A-Z0-9_]{1,32}$/.test(opcode))
      && new Set(rows[0].opcodes).size === rows[0].opcodes.length
      && rows[0].sha256 === digest(bytes) && rows[0].bytes === bytes.length, 'Crew payload integrity mismatch');
    if (name !== 'state.bin') requireValue(bytes.equals(read(join(baseFixture, name), 16384)), 'Crew changed preserved shop/dossier');
  }
  const compatibility = json(join(directory, 'compatibility.json'), 8192);
  const oldCompatibility = json(join(baseFixture, 'compatibility.json'), 8192);
  const expected = { ...oldCompatibility, snapshot_revision: 3,
    crew_mapping: profile.crew.map((member, slot) => ({ crew_id: member.crew_id, native_inventory_id: slot + 1,
      native_vehicle_inventory_id: 1, slot_index: slot })) };
  requireValue(isDeepStrictEqual(compatibility, expected), 'Crew compatibility mapping changed');
  const previousManifest = json(join(baseFixture, 'manifest.json'), 65536);
  requireValue(isDeepStrictEqual(native, { ...previousManifest.native_descriptors, crew: native.crew })
    && manifest.native_compatibility === previousManifest.native_compatibility, 'Crew changed preserved native provenance');
  const preserved = { status: 'PASS_LOCAL_INVARIANTS_ONLY', crew_grant: profile.crew_grant,
    base_fixture: { directory: baseFixture, manifest_sha256: digest(read(join(baseFixture, 'manifest.json'), 65536)) },
    base_state_sha256: digest(read(join(baseFixture, 'state.bin'), 16384)),
    restored_state_sha256: digest(read(join(baseFixture, 'state.bin'), 16384)),
    shop_sha256: digest(read(join(baseFixture, 'shop.bin'), 16384)),
    dossier_sha256: digest(read(join(baseFixture, 'dossier.bin'), 16384)),
    account_dossier_sha256: previousManifest.preservation.account_dossier_sha256,
    dossier_cache: previousManifest.preservation.dossier_cache,
    delta: ['inventory[8] two native tankmen assigned to vehicle1', 'inventory[1].crew[1]=[1,2]'],
    native_compatibility: 'NOT_RUN' };
  requireValue(isDeepStrictEqual(manifest.preservation, preserved), 'Crew preservation metadata changed');
  return tree(directory);
}

async function offlineLease(context) {
  const lock = join(context.directory, 'supervisor.lock'), contents = Buffer.from(String(process.pid));
  writeNew(lock, contents);
  const reservations = [];
  async function release() {
    for (const close of reservations.reverse()) await close();
    requireValue(read(lock, 64).equals(contents), 'Offline lock changed; preserved');
    unlinkSync(lock);
  }
  try {
    if (process.platform === 'win32') {
      const commands = context.ports.map(({ protocol, port }) => {
        const method = protocol === 'tcp' ? 'GetActiveTcpListeners' : 'GetActiveUdpListeners';
        return `@([System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().${method}() | Where-Object { $_.Port -eq ${port} }).Count`;
      });
      const probe = spawnSync('powershell', ['-NoProfile', '-NonInteractive', '-Command', commands.join('\n')],
        { encoding: 'utf8', windowsHide: true, timeout: 10000, maxBuffer: 4096 });
      requireValue(probe.status === 0 && probe.stdout.trim().split(/\s+/).length === 3
        && probe.stdout.trim().split(/\s+/).every(n => n === '0'), 'Service port is occupied or listener check failed');
    }
    for (const { protocol, port } of context.ports) {
      if (protocol === 'tcp') {
        const socket = createServer(client => client.destroy());
        try { await new Promise((done, fail) => { socket.once('error', fail); socket.listen({ host: '127.0.0.1', port, exclusive: true }, done); }); }
        catch (error) { socket.close(); throw error; }
        reservations.push(() => new Promise((done, fail) => socket.close(error => error ? fail(error) : done())));
      } else {
        const socket = createSocket({ type: 'udp4', reuseAddr: false });
        try { await new Promise((done, fail) => { socket.once('error', fail); socket.bind({ address: '127.0.0.1', port, exclusive: true }, done); }); }
        catch (error) { socket.close(); throw error; }
        reservations.push(() => new Promise(done => socket.close(done)));
      }
    }
    requireValue(isDeepStrictEqual(loadGarageService(context.path).sources, context.sources), 'Configuration changed during offline acquisition');
    return release;
  } catch (error) { await release(); throw error; }
}
function openGame(context) {
  read(context.bridge.game_database, MAX_DB);
  const db = new DatabaseSync(context.bridge.game_database);
  try {
    db.exec('PRAGMA busy_timeout=1000;');
    requireValue(db.prepare('PRAGMA user_version').get().user_version === 1
      && db.prepare('PRAGMA quick_check').get().quick_check === 'ok', 'Game database version/integrity');
    requireValue(db.prepare('SELECT value FROM game_meta WHERE key=?').get('native_descriptors_sha256')?.value
      === digest(read(context.bridge.native_descriptors, 65536)), 'Database native provenance mismatch');
    return db;
  } catch (error) { db.close(); throw error; }
}
function snapshot(db, identity = false) {
  const tables = identity ? { users: 'id', sessions: 'token_hash', rate_limits: 'key_hash' }
    : { game_meta: 'key', game_profiles: 'native_id', game_limits: 'key_hash', sqlite_sequence: 'name' };
  const schema = db.prepare('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').all().map(value => ({ ...value }));
  requireValue(schema.length <= 24 && schema.filter(row => row.type === 'table').every(row => Object.hasOwn(tables, row.name))
    && schema.every(row => ['table', 'index'].includes(row.type)), 'Unexpected database schema');
  const result = { user_version: db.prepare('PRAGMA user_version').get().user_version, schema };
  for (const table of schema.filter(row => row.type === 'table').map(row => row.name)) {
    requireValue(db.prepare(`SELECT COUNT(*) AS n FROM ${table}`).get().n <= 10000, 'Database row bound');
    result[table] = db.prepare(`SELECT * FROM ${table} ORDER BY ${tables[table]}`).all().map(value => ({ ...value }));
  }
  requireValue(Buffer.byteLength(JSON.stringify(result)) <= 16 * 1024 * 1024, 'Database snapshot bound');
  return result;
}
function row(db, id) {
  const value = db.prepare('SELECT native_id,account_id,profile_json FROM game_profiles WHERE account_id=?').get(id);
  requireValue(value && Buffer.byteLength(value.profile_json) <= 8192, 'Existing bounded game profile required');
  return value;
}
function identity(context, profile) {
  const reader = openIdentityReader(context.bridge.web_database);
  try {
    const user = reader.profile(profile.account_id);
    requireValue(user && user.id === profile.account_id && user.display_nickname === profile.username
      && user.created_at === profile.created_at_ms, 'Read-only identity differs from stored game profile');
    return { account_id: user.id, nickname: user.display_nickname, created_at_ms: user.created_at };
  } finally { reader.close(); }
}
function consistentBackup(db, path, isIdentity = false) {
  // VACUUM INTO works with a readOnly source and includes committed WAL data.
  // The external website may keep running; each backup is its own consistent
  // snapshot, not a claimed cross-database atomic transaction.
  db.prepare('VACUUM INTO ?').run(path);
  const fd = openSync(path, 'r+'); try { fsyncSync(fd); } finally { closeSync(fd); }
  const backup = new DatabaseSync(path, { readOnly: true });
  let logical;
  try {
    requireValue(backup.prepare('PRAGMA quick_check').get().quick_check === 'ok', 'Backup integrity check failed');
    logical = digest(JSON.stringify(snapshot(backup, isIdentity)));
  } finally { backup.close(); }
  return { file: path.split(/[\\/]/).at(-1), sha256: digest(read(path, MAX_DB)), logical_sha256: logical };
}
function crewSources(context, nativeCrew) {
  requireValue(keys(context.bridge.test_garage, ['version', 'native_is7', 'sha256'])
    && context.bridge.test_garage.version === 1, 'Existing pinned test garage required');
  const ms1 = source(localPath(context.bridge.native_descriptors), 65536);
  const is7 = source(localPath(context.bridge.test_garage.native_is7), 32768);
  requireValue(is7.sha256 === context.bridge.test_garage.sha256, 'Pinned IS-7 source changed');
  return { service: context.sources, ms1, is7, crew: source(localPath(nativeCrew), 65536) };
}
function journalPath(value, context) {
  const directory = localPath(value);
  requireValue(directory !== context.directory && directory !== context.bridge.fixture_root
    && !inside(context.bridge.fixture_root, directory) && !inside(directory, context.directory)
    && !inside(directory, context.bridge.fixture_root), 'Journal must be outside fixture storage and service ancestors');
  return directory;
}
function validatePlan(context, directory, plan) {
  requireValue(keys(plan, ['version', 'operation', 'account_id', 'native_database_id', 'granted_at_ms', 'service',
    'sources', 'implementation', 'identity', 'before', 'after', 'backups', 'previous_fixture', 'fixture'])
    && plan.version === 1 && plan.operation === 'test-ms1-crew-v1' && plan.service === context.path
    && UUID.test(plan.account_id) && integer(plan.native_database_id, 1), 'Crew journal schema');
  requireValue(isDeepStrictEqual(plan.implementation, implementation()), 'Crew implementation changed');
  requireValue(keys(plan.sources, ['service', 'ms1', 'is7', 'crew'])
    && isDeepStrictEqual(plan.sources.service, context.sources), 'Journal/service configuration changed');
  for (const item of [plan.sources.ms1, plan.sources.is7, plan.sources.crew]) checkSource(item, 65536);
  requireValue(isDeepStrictEqual(crewSources(context, plan.sources.crew.path), plan.sources), 'Journal native source configuration mismatch');
  requireValue(keys(plan.before, ['file', 'sha256', 'database_sha256']) && plan.before.file === 'before-profile.json'
    && keys(plan.after, ['file', 'sha256']) && plan.after.file === 'after-profile.json', 'Journal profile filenames/schema');
  const beforeBytes = read(join(directory, plan.before.file), 8192), afterBytes = read(join(directory, plan.after.file), 8192);
  requireValue(digest(beforeBytes) === plan.before.sha256 && digest(afterBytes) === plan.after.sha256, 'Journal profile changed');
  const before = validateGrantedProfile(JSON.parse(beforeBytes.toString('utf8'))), after = JSON.parse(afterBytes.toString('utf8'));
  requireValue(before.account_id === plan.account_id && before.native_database_id === plan.native_database_id
    && after.crew_grant?.granted_at_ms === plan.granted_at_ms, 'Journal identity/grant mismatch');
  requireValue(isDeepStrictEqual(identity(context, before), plan.identity), 'Journal identity changed');
  requireValue(keys(plan.backups, ['game', 'identity']), 'Both consistent backups required');
  for (const [name, file] of [['game', 'game-before.sqlite'], ['identity', 'identity-before.sqlite']]) {
    const backup = plan.backups[name];
    requireValue(keys(backup, ['file', 'sha256', 'logical_sha256']) && backup.file === file
      && digest(read(join(directory, file), MAX_DB)) === backup.sha256 && SHA.test(backup.logical_sha256), 'Consistent backup integrity mismatch');
  }
  requireValue(plan.backups.game.logical_sha256 === plan.before.database_sha256, 'Game backup differs from planned state');
  requireValue(keys(plan.previous_fixture, ['directory', 'snapshot']) && plan.previous_fixture.directory ===
    join(context.bridge.fixture_root, plan.account_id, 'r2-catalog3')
    && isDeepStrictEqual(tree(plan.previous_fixture.directory), plan.previous_fixture.snapshot), 'Previous fixture changed');
  const baseBytes = read(join(plan.previous_fixture.directory, 'profile-input.json'), 8192);
  requireValue(isDeepStrictEqual(JSON.parse(baseBytes.toString('utf8')), before), 'Previous fixture differs from planned profile');
  validateCrewProfile(after, baseBytes);
  requireValue(after.crew_grant.native_export_sha256 === plan.sources.crew.sha256, 'Journal crew export binding mismatch');
  requireValue(keys(plan.fixture, ['directory', 'snapshot']) && plan.fixture.directory ===
    join(context.bridge.fixture_root, plan.account_id, 'r3-catalog3'), 'Crew fixture path');
  return { before, after, beforeText: beforeBytes.toString('utf8'), afterText: afterBytes.toString('utf8') };
}
function fixtureCheck(directory, plan, profile) {
  requireValue(isDeepStrictEqual(validateCrewFixture(directory, profile, { nativeMs1: plan.sources.ms1.path,
    nativeIs7: plan.sources.is7.path, baseFixture: plan.previous_fixture.directory }), plan.fixture.snapshot), 'Immutable crew fixture changed');
}
function plannedResult(plan, directory, hash, status = 'PLANNED') {
  return { status, account_id: plan.account_id, native_database_id: plan.native_database_id, snapshot_revision: 3,
    fixture_directory: plan.fixture.directory, journal: directory, journal_sha256: hash,
    profile_sha256: plan.after.sha256, native_compatibility: 'NOT_RUN' };
}

export async function planMs1Crew(options) {
  requireValue(keys(options, ['service', 'accountId', 'nativeCrew', 'grantedAtMs', 'expectedProfileSha256', 'journal'])
    && UUID.test(options.accountId) && SHA.test(options.expectedProfileSha256)
    && integer(options.grantedAtMs, 1, 2147483647999), 'Explicit UUID, timestamp, profile hash and journal required');
  const context = loadGarageService(options.service), directory = journalPath(options.journal, context);
  const release = await offlineLease(context); let db;
  try {
    const sources = crewSources(context, options.nativeCrew), impl = implementation();
    db = openGame(context);
    if (existsSync(directory)) {
      requireValue(!existsSync(join(directory, 'rolled-back.json')), 'Journal already rolled back; no implicit re-grant');
      const plan = json(join(directory, 'prepared.json'), 65536), data = validatePlan(context, directory, plan);
      requireValue(plan.account_id === options.accountId && plan.granted_at_ms === options.grantedAtMs
        && plan.before.sha256 === options.expectedProfileSha256 && isDeepStrictEqual(plan.sources, sources), 'Journal belongs to a different explicit request');
      const current = row(db, plan.account_id);
      requireValue(current.native_id === plan.native_database_id && [data.beforeText, data.afterText].includes(current.profile_json), 'Planned profile changed');
      fixtureCheck(existsSync(plan.fixture.directory) ? plan.fixture.directory : join(directory, 'fixture-staged'), plan, data.after);
      return plannedResult(plan, directory, digest(read(join(directory, 'prepared.json'), 65536)), 'ALREADY_PLANNED');
    }
    const current = row(db, options.accountId), before = validateGrantedProfile(JSON.parse(current.profile_json));
    requireValue(before.account_id === options.accountId && before.native_database_id === current.native_id
      && digest(current.profile_json) === options.expectedProfileSha256, 'Expected target UUID/native identity/profile hash mismatch');
    const user = identity(context, before), previous = join(context.bridge.fixture_root, options.accountId, 'r2-catalog3');
    const historical = validateGrantedFixture(previous, before, { nativeMs1: sources.ms1.path, nativeIs7: sources.is7.path });
    const baseBytes = read(join(previous, 'profile-input.json'), 8192);
    const proposed = structuredClone(before);
    proposed.profile_version = 3; proposed.snapshot_revision = 3; proposed.inventory[0].crew_assigned = true;
    proposed.crew = domainCrew(before.account_id);
    proposed.crew_grant = { grant_id: 'test-ms1-crew-v1', granted_at_ms: options.grantedAtMs,
      base_profile_sha256: digest(baseBytes), native_export_sha256: sources.crew.sha256 };
    validateCrewProfile(proposed, baseBytes);
    const beforeDigest = digest(JSON.stringify(snapshot(db))), afterBytes = Buffer.from(JSON.stringify(proposed));
    mkdirSync(directory, { recursive: false });
    writeNew(join(directory, 'before-profile.json'), Buffer.from(current.profile_json));
    writeNew(join(directory, 'after-profile.json'), afterBytes);
    const gameBackup = consistentBackup(db, join(directory, 'game-before.sqlite'));
    requireValue(gameBackup.logical_sha256 === beforeDigest, 'Game backup snapshot is inconsistent');
    read(context.bridge.web_database, MAX_DB);
    const identityDb = new DatabaseSync(context.bridge.web_database, { readOnly: true });
    let identityBackup;
    try { identityBackup = consistentBackup(identityDb, join(directory, 'identity-before.sqlite'), true); }
    finally { identityDb.close(); }
    const generated = spawnSync(context.config.python_executable, ['-B', '-X', 'utf8', GENERATOR, 'generate',
      '--profile', join(directory, 'after-profile.json'), '--base-fixture', previous,
      '--native-crew', sources.crew.path, '--out', join(directory, 'fixture-staged')],
    { cwd: ROOT, windowsHide: true, encoding: 'utf8', timeout: 10000, maxBuffer: 32768 });
    writeNew(join(directory, 'generator-result.json'), { exit_code: generated.status, signal: generated.signal,
      error: generated.error?.message || null, stdout: (generated.stdout || '').slice(0, 32768),
      stderr: (generated.stderr || '').slice(0, 32768) });
    requireValue(generated.status === 0 && !generated.error, 'Crew generator failed; database unchanged');
    const fixture = validateCrewFixture(join(directory, 'fixture-staged'), proposed,
      { nativeMs1: sources.ms1.path, nativeIs7: sources.is7.path, baseFixture: previous });
    requireValue(isDeepStrictEqual(tree(previous), historical) && isDeepStrictEqual(implementation(), impl)
      && isDeepStrictEqual(crewSources(context, sources.crew.path), sources)
      && digest(JSON.stringify(snapshot(db))) === beforeDigest, 'Inputs changed during crew preparation');
    requireValue(isDeepStrictEqual(identity(context, before), user), 'Identity changed during crew preparation');
    const plan = { version: 1, operation: 'test-ms1-crew-v1', account_id: before.account_id,
      native_database_id: before.native_database_id, granted_at_ms: options.grantedAtMs, service: context.path,
      sources, implementation: impl, identity: user,
      before: { file: 'before-profile.json', sha256: digest(current.profile_json), database_sha256: beforeDigest },
      after: { file: 'after-profile.json', sha256: digest(afterBytes) }, backups: { game: gameBackup, identity: identityBackup },
      previous_fixture: { directory: previous, snapshot: historical },
      fixture: { directory: join(context.bridge.fixture_root, options.accountId, 'r3-catalog3'), snapshot: fixture } };
    writeNew(join(directory, 'prepared.json'), plan);
    return plannedResult(plan, directory, digest(read(join(directory, 'prepared.json'), 65536)));
  } finally { if (db) db.close(); await release(); }
}

function receipt(path, expected) {
  if (!existsSync(path)) return false;
  const value = json(path);
  for (const [key, item] of Object.entries(expected)) requireValue(isDeepStrictEqual(value[key], item), 'Crew receipt changed');
  return true;
}
export async function applyMs1Crew(options) {
  requireValue(keys(options, ['service', 'journal', 'expectedJournalSha256']) && SHA.test(options.expectedJournalSha256), 'Expected journal SHA256 required');
  const context = loadGarageService(options.service), directory = journalPath(options.journal, context);
  requireValue(digest(read(join(directory, 'prepared.json'), 65536)) === options.expectedJournalSha256, 'Unexpected journal hash');
  const release = await offlineLease(context); let db;
  try {
    requireValue(!existsSync(join(directory, 'rolled-back.json')), 'Journal already rolled back; no implicit re-grant');
    const plan = json(join(directory, 'prepared.json'), 65536), data = validatePlan(context, directory, plan);
    const commitFile = join(directory, 'committed.json');
    const hasReceipt = receipt(commitFile, { version: 1, status: 'COMMITTED', prepared_sha256: options.expectedJournalSha256,
      after_profile_sha256: plan.after.sha256 });
    db = openGame(context);
    let already = false, beforeDigest, afterDigest;
    db.exec('BEGIN IMMEDIATE');
    try {
      const current = row(db, plan.account_id), previous = snapshot(db); beforeDigest = digest(JSON.stringify(previous));
      requireValue(current.native_id === plan.native_database_id, 'Native identity changed');
      if (current.profile_json === data.afterText) already = true;
      else requireValue(!hasReceipt && current.profile_json === data.beforeText && beforeDigest === plan.before.database_sha256,
        'Database changed before apply; preserve it and create a new explicit plan');
      // Publish only validated immutable output; a crash after rename keeps a
      // recoverable sibling and never requires replacing the historical fixture.
      const stage = existsSync(plan.fixture.directory) ? plan.fixture.directory : join(directory, 'fixture-staged');
      fixtureCheck(stage, plan, data.after);
      if (stage !== plan.fixture.directory) renameSync(stage, plan.fixture.directory);
      if (!already) {
        requireValue(db.prepare('UPDATE game_profiles SET profile_json=? WHERE account_id=? AND native_id=? AND profile_json=?')
          .run(data.afterText, plan.account_id, plan.native_database_id, data.beforeText).changes === 1, 'Expected exactly one crew target');
        const expected = structuredClone(previous);
        expected.game_profiles.find(item => item.account_id === plan.account_id).profile_json = data.afterText;
        requireValue(isDeepStrictEqual(snapshot(db), expected), 'Crew apply changed unrelated database data');
      }
      afterDigest = digest(JSON.stringify(snapshot(db))); db.exec('COMMIT');
    } catch (error) { db.exec('ROLLBACK'); throw error; }
    if (!hasReceipt) writeNew(commitFile, { version: 1, status: 'COMMITTED', prepared_sha256: options.expectedJournalSha256,
      after_profile_sha256: plan.after.sha256, database_before_sha256: beforeDigest, database_after_sha256: afterDigest,
      recovered_after_commit: already });
    return plannedResult(plan, directory, options.expectedJournalSha256, already ? 'ALREADY_GRANTED' : 'GRANTED');
  } finally { if (db) db.close(); await release(); }
}

export async function rollbackMs1Crew(options) {
  requireValue(keys(options, ['service', 'journal', 'expectedJournalSha256']) && SHA.test(options.expectedJournalSha256), 'Expected journal SHA256 required');
  const context = loadGarageService(options.service), directory = journalPath(options.journal, context);
  requireValue(digest(read(join(directory, 'prepared.json'), 65536)) === options.expectedJournalSha256, 'Unexpected journal hash');
  const release = await offlineLease(context); let db;
  try {
    const plan = json(join(directory, 'prepared.json'), 65536), data = validatePlan(context, directory, plan);
    requireValue(receipt(join(directory, 'committed.json'), { version: 1, status: 'COMMITTED',
      prepared_sha256: options.expectedJournalSha256, after_profile_sha256: plan.after.sha256 }), 'Commit receipt required');
    fixtureCheck(plan.fixture.directory, plan, data.after);
    const rollbackFile = join(directory, 'rolled-back.json');
    const hasReceipt = receipt(rollbackFile, { version: 1, status: 'ROLLED_BACK',
      prepared_sha256: options.expectedJournalSha256, before_profile_sha256: plan.before.sha256 });
    db = openGame(context); let already = false, beforeDigest, afterDigest;
    db.exec('BEGIN IMMEDIATE');
    try {
      const current = row(db, plan.account_id), previous = snapshot(db); beforeDigest = digest(JSON.stringify(previous));
      requireValue(current.native_id === plan.native_database_id, 'Rollback native identity changed');
      if (current.profile_json === data.beforeText) already = true;
      else {
        requireValue(!hasReceipt && current.profile_json === data.afterText, 'Rollback target changed; preserving newer data');
        requireValue(db.prepare('UPDATE game_profiles SET profile_json=? WHERE account_id=? AND native_id=? AND profile_json=?')
          .run(data.beforeText, plan.account_id, plan.native_database_id, data.afterText).changes === 1, 'Expected exactly one rollback target');
        const expected = structuredClone(previous);
        expected.game_profiles.find(item => item.account_id === plan.account_id).profile_json = data.beforeText;
        requireValue(isDeepStrictEqual(snapshot(db), expected), 'Rollback changed unrelated data');
      }
      afterDigest = digest(JSON.stringify(snapshot(db))); db.exec('COMMIT');
    } catch (error) { db.exec('ROLLBACK'); throw error; }
    if (!hasReceipt) writeNew(rollbackFile, { version: 1, status: 'ROLLED_BACK', prepared_sha256: options.expectedJournalSha256,
      before_profile_sha256: plan.before.sha256, database_before_sha256: beforeDigest, database_after_sha256: afterDigest,
      unrelated_data_preserved: true, immutable_fixture_retained: true, original_profile_already_present: already });
    return { status: already ? 'ALREADY_ROLLED_BACK' : 'ROLLED_BACK', account_id: plan.account_id,
      profile_sha256: plan.before.sha256, fixture_retained: plan.fixture.directory, journal: directory };
  } finally { if (db) db.close(); await release(); }
}

function cli(args) {
  const [command, ...flags] = args;
  const allowed = command === 'plan' ? ['service', 'account-id', 'native-crew', 'granted-at-ms', 'expect-profile-sha256', 'journal']
    : ['apply', 'rollback'].includes(command) ? ['service', 'journal', 'expect-journal-sha256'] : [];
  requireValue(allowed.length && flags.length === allowed.length * 2, 'Use explicit plan/apply/rollback flags; no defaults');
  const options = {};
  for (let i = 0; i < flags.length; i += 2) {
    const key = flags[i].slice(2);
    requireValue(flags[i].startsWith('--') && allowed.includes(key) && options[key] === undefined && flags[i + 1], 'Unknown or duplicate CLI flag');
    options[key] = flags[i + 1];
  }
  if (command === 'plan') {
    requireValue(/^[0-9]{1,13}$/.test(options['granted-at-ms']), 'Explicit decimal grant timestamp required');
    return planMs1Crew({ service: options.service, accountId: options['account-id'], nativeCrew: options['native-crew'],
      grantedAtMs: Number(options['granted-at-ms']), expectedProfileSha256: options['expect-profile-sha256'], journal: options.journal });
  }
  return (command === 'apply' ? applyMs1Crew : rollbackMs1Crew)({ service: options.service,
    journal: options.journal, expectedJournalSha256: options['expect-journal-sha256'] });
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try { console.log(JSON.stringify(await cli(process.argv.slice(2)))); }
  catch (error) { console.error(JSON.stringify({ status: 'REFUSED', reason: error.message })); process.exitCode = 1; }
}
