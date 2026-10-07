/** Explicit offline owner CLI. No HTTP route, credentials, purchases or client writes. */
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
import { nicknameField } from './security.mjs';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const LOCAL = resolve(ROOT, 'local');
const SELF = fileURLToPath(import.meta.url);
const GENERATOR = resolve(ROOT, 'tools/test_garage_state.py');
const LEGACY = resolve(ROOT, 'tools/hangar_state.py');
export const LEGACY_ENCODER_SHA256 = 'ac60b6ea2be39eaa59327ef1eefb935595e8111ff13a12720ed3a3ebf02c7e79';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const SHA = /^[0-9a-f]{64}$/;
const PROFILE_FIELDS = ['profile_version', 'account_id', 'username', 'native_database_id',
  'created_at_ms', 'snapshot_revision', 'resources', 'statistics'];
const MAX_DB = 64 * 1024 * 1024;
const digest = value => createHash('sha256').update(value).digest('hex');
const inside = (base, path) => { const rel = relative(base, path); return rel !== '' && !rel.startsWith('..') && !isAbsolute(rel); };
const requireValue = (condition, message) => { if (!condition) throw new Error(message); };
const integer = (n, low = 0, high = 2147483647) => Number.isSafeInteger(n) && n >= low && n <= high;
function keys(value, expected) {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    && Object.keys(value).sort().join(',') === [...expected].sort().join(',');
}
function localPath(value) {
  requireValue(typeof value === 'string' && value.length > 0, 'Local path required');
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
      requireValue(stat.isFile() && rows.length < 64 && stat.size <= 1024 * 1024, 'Snapshot bounds');
      const bytes = read(path, 1024 * 1024); total += bytes.length;
      requireValue(total <= 2 * 1024 * 1024, 'Snapshot total bound');
      rows.push({ file: relative(directory, path).replaceAll('\\', '/'), bytes: bytes.length, sha256: digest(bytes) });
    }
  }
  visit(directory);
  return { sha256: digest(JSON.stringify(rows)), files: rows };
}
function checkSource(item) {
  requireValue(keys(item, ['path', 'bytes', 'sha256']) && SHA.test(item.sha256), 'Source record schema');
  requireValue(isDeepStrictEqual(source(localPath(item.path)), item), 'Source provenance changed');
}
function validateBase(profile) {
  requireValue(keys(profile, PROFILE_FIELDS) && profile.profile_version === 1 && profile.snapshot_revision === 1, 'Exact profile1 required');
  requireValue(UUID.test(profile.account_id) && integer(profile.native_database_id, 1)
    && integer(profile.created_at_ms, 1, 4000000000000), 'Profile identity bounds');
  requireValue(nicknameField(profile.username)?.display === profile.username, 'Stored nickname required');
  requireValue(keys(profile.resources, ['credits', 'gold', 'free_xp'])
    && Object.values(profile.resources).every(n => integer(n)), 'Resource bounds');
  requireValue(keys(profile.statistics, ['battles', 'wins', 'losses', 'draws'])
    && Object.values(profile.statistics).every(n => n === 0), 'Only the explicit zero-battle test profile is supported');
  return profile;
}
function inventory(id) {
  return [['starter-vehicle-v1', 'vehicle:ms1', 90], ['test-is7-v1', 'vehicle:is7', 2150]].map(([suffix, definition, health]) => ({
    inventory_id: `${id}:${suffix}`, vehicle_definition_id: definition, health,
    vehicle_xp: 0, crew_assigned: false, ammunition_count: 0,
  }));
}
export function validateGrantedProfile(profile, baseBytes) {
  requireValue(keys(profile, [...PROFILE_FIELDS, 'inventory', 'test_grant'])
    && profile.profile_version === 2 && profile.snapshot_revision === 2, 'Exact profile2 required');
  const base = Object.fromEntries(PROFILE_FIELDS.map(key => [key, profile[key]]));
  base.profile_version = 1; base.snapshot_revision = 1; validateBase(base);
  requireValue(isDeepStrictEqual(profile.inventory, inventory(profile.account_id)), 'Explicit two-vehicle grant inventory required');
  requireValue(keys(profile.test_grant, ['grant_id', 'granted_at_ms', 'base_profile_sha256'])
    && profile.test_grant.grant_id === 'test-is7-v1' && SHA.test(profile.test_grant.base_profile_sha256)
    && integer(profile.test_grant.granted_at_ms, profile.created_at_ms, 2147483647999), 'Grant schema/time bounds');
  if (baseBytes !== undefined) {
    requireValue(Buffer.isBuffer(baseBytes) && baseBytes.length <= 8192
      && digest(baseBytes) === profile.test_grant.base_profile_sha256
      && isDeepStrictEqual(JSON.parse(baseBytes.toString('utf8')), base), 'Exact historical base profile mismatch');
  }
  return profile;
}
export function grantedOverview(profile) {
  validateGrantedProfile(profile);
  return { schemaVersion: 'web-game-read.v1', state: 'ready', ruleset: 'test_lab', snapshotRevision: 2,
    asOf: new Date(profile.test_grant.granted_at_ms).toISOString(),
    account: { accountId: profile.account_id, nickname: profile.username },
    resources: { credits: profile.resources.credits, gold: profile.resources.gold, freeXP: profile.resources.free_xp },
    inventory: profile.inventory.map(item => ({ inventoryItemId: item.inventory_id,
      vehicleDefinitionId: item.vehicle_definition_id, displayName: item.vehicle_definition_id === 'vehicle:ms1' ? 'МС-1' : 'ИС-7',
      health: item.health, crewAssigned: item.crew_assigned, ammunition: item.ammunition_count })),
    statistics: profile.statistics, capabilities: { battle: false, purchases: false, sales: false } };
}
/** The browser may read exactly this finite test inventory; it cannot submit it. */
export function isGrantedOverview(value, id) {
  if (!keys(value, ['schemaVersion', 'state', 'ruleset', 'snapshotRevision', 'asOf', 'account', 'resources', 'inventory', 'statistics', 'capabilities'])
    || !UUID.test(id) || value.schemaVersion !== 'web-game-read.v1' || value.state !== 'ready'
    || value.ruleset !== 'test_lab' || value.snapshotRevision !== 2 || !Number.isFinite(Date.parse(value.asOf))
    || !keys(value.account, ['accountId', 'nickname']) || value.account.accountId !== id
    || nicknameField(value.account.nickname)?.display !== value.account.nickname
    || !keys(value.resources, ['credits', 'gold', 'freeXP']) || !Object.values(value.resources).every(n => integer(n))
    || !keys(value.statistics, ['battles', 'wins', 'losses', 'draws']) || !Object.values(value.statistics).every(n => n === 0)
    || !isDeepStrictEqual(value.capabilities, { battle: false, purchases: false, sales: false })) return false;
  const expected = inventory(id).map(item => ({ inventoryItemId: item.inventory_id, vehicleDefinitionId: item.vehicle_definition_id,
    displayName: item.vehicle_definition_id === 'vehicle:ms1' ? 'МС-1' : 'ИС-7', health: item.health,
    crewAssigned: item.crew_assigned, ammunition: item.ammunition_count }));
  return isDeepStrictEqual(value.inventory, expected);
}

function nativeSources(ms1, is7) {
  requireValue(digest(read(LEGACY, 131072)) === LEGACY_ENCODER_SHA256, 'Frozen legacy encoder changed');
  return { ms1: source(localPath(ms1), 65536), is7: source(localPath(is7), 32768),
    generator_sha256: digest(read(GENERATOR, 131072)), dependency_sha256: LEGACY_ENCODER_SHA256 };
}
/** Read-only bridge integration point: never regenerates or overwrites a snapshot. */
export function validateGrantedFixture(directory, profile, { nativeMs1, nativeIs7 }) {
  directory = localPath(directory);
  const inputs = nativeSources(nativeMs1, nativeIs7), manifest = json(join(directory, 'manifest.json'), 32768);
  const raw = read(join(directory, 'profile-input.json'), 8192), base = read(join(directory, 'base-profile-input.json'), 8192);
  validateGrantedProfile(profile, base);
  requireValue(isDeepStrictEqual(JSON.parse(raw.toString('utf8')), profile), 'Persisted profile differs from immutable fixture');
  requireValue(manifest.fixture_version === 2 && manifest.profile_version === 2 && manifest.snapshot_revision === 2
    && manifest.wire_sync_revision === 1 && manifest.compatibility_catalog_revision === 3 && manifest.ruleset === 'test_lab'
    && manifest.account_id === profile.account_id && manifest.native_database_id === profile.native_database_id
    && manifest.generator?.sha256 === inputs.generator_sha256 && manifest.generator?.dependency?.sha256 === inputs.dependency_sha256
    && manifest.native_descriptors?.ms1?.sha256 === inputs.ms1.sha256 && manifest.native_descriptors?.is7?.sha256 === inputs.is7.sha256
    && isDeepStrictEqual(manifest.grant, profile.test_grant), 'Granted fixture provenance/version mismatch');
  for (const [field, file, bytes] of [['profile_source', 'profile-input.json', raw], ['base_profile_source', 'base-profile-input.json', base]]) {
    requireValue(isDeepStrictEqual(manifest[field], { file, relative_to: 'fixture_directory', sha256: digest(bytes) }), 'Fixture input hash mismatch');
  }
  requireValue(Array.isArray(manifest.files) && manifest.files.length === 3, 'Exactly three native payloads required');
  for (const name of ['state.bin', 'shop.bin', 'dossier.bin']) {
    const rows = manifest.files.filter(item => item.file === name), bytes = read(join(directory, name), 16384);
    requireValue(rows.length === 1 && rows[0].sha256 === digest(bytes) && rows[0].bytes === bytes.length, 'Payload integrity mismatch');
  }
  const compatibility = json(join(directory, 'compatibility.json'), 8192);
  requireValue(compatibility.account_id === profile.account_id && compatibility.native_database_id === profile.native_database_id
    && compatibility.client_name === profile.username && compatibility.compatibility_catalog_revision === 3
    && compatibility.snapshot_revision === 2 && compatibility.wire_sync_revision === 1, 'Compatibility identity mismatch');
  requireValue(Array.isArray(compatibility.vehicle_mapping) && compatibility.vehicle_mapping.length === 2, 'Compatibility inventory mapping bound');
  for (const [index, nativeId, type] of [[0, 1, 3329], [1, 2, 7169]]) {
    const mapping = compatibility.vehicle_mapping[index];
    requireValue(mapping.inventory_id === profile.inventory[index].inventory_id
      && mapping.native_inventory_id === nativeId && mapping.type_compact_descr === type, 'Compatibility inventory mapping mismatch');
  }
  const cache = { version: 1, last_change_time: Math.floor(profile.test_grant.granted_at_ms / 1000), vehicle_type_compact_descr: 7169 };
  requireValue(isDeepStrictEqual(compatibility.dossier_cache, cache)
    && isDeepStrictEqual(manifest.preservation?.dossier_cache, { ...cache, payload_sha256: digest(read(join(directory, 'dossier.bin'), 16384)) }),
  'Dossier cache provenance/time mismatch');
  return tree(directory);
}

function endpoint(value) {
  const match = /^127\.0\.0\.1:([0-9]{1,5})$/.exec(value || '');
  requireValue(match && integer(Number(match[1]), 1024, 65535), 'Numeric loopback endpoint required');
  return Number(match[1]);
}
export function loadGarageService(value) {
  const path = localPath(value), config = json(path), directory = localPath(config.runtime_dir);
  const configKeys = ['version', 'runtime_dir', 'portal_data', 'web_port', 'node_executable', 'python_executable', 'gateway_executable'];
  if (config.version === 2) configKeys.push('web_mode');
  requireValue(keys(config, configKeys) && [1, 2].includes(config.version)
    && (config.version === 1 || ['managed', 'external'].includes(config.web_mode)) && path === join(directory, 'service.json'), 'Service schema/path');
  const bridgeFile = join(directory, 'bridge.json'), gatewayFile = join(directory, 'gateway.json');
  const bridge = json(bridgeFile), gateway = json(gatewayFile);
  requireValue(keys(bridge, ['version', 'port', 'web_database', 'game_database', 'fixture_root', 'native_descriptors',
    'python_executable', 'token_file', ...(bridge.test_garage === undefined ? [] : ['test_garage'])]) && bridge.version === 1
    && integer(bridge.port, 1024, 65535), 'Bridge schema/port');
  const portal = localPath(config.portal_data);
  requireValue(inside(join(LOCAL, 'web'), portal), 'Identity directory must stay inside local/web/');
  for (const [field, expected] of Object.entries({ web_database: join(portal, 'portal.sqlite'), game_database: join(directory, 'game.sqlite'),
    fixture_root: join(directory, 'fixtures'), native_descriptors: join(directory, 'native-descriptors.json'), token_file: join(directory, 'identity.token') })) {
    requireValue(localPath(bridge[field]) === expected, 'Bridge/service path mismatch');
  }
  requireValue(isAbsolute(config.python_executable) && config.python_executable === bridge.python_executable
    && lstatSync(config.python_executable).isFile(), 'Configured Python executable required');
  requireValue(localPath(gateway.local_root + '/garage-boundary') === join(LOCAL, 'garage-boundary')
    && localPath(gateway.identity_token_file) === join(directory, 'identity.token')
    && endpoint(gateway.identity_endpoint) === bridge.port, 'Gateway/service mismatch');
  const ports = [{ protocol: 'tcp', port: bridge.port }, { protocol: 'udp', port: endpoint(gateway.login_bind) },
    { protocol: 'udp', port: endpoint(gateway.base_bind) }];
  requireValue(new Set(ports.map(item => item.port)).size === 3, 'Distinct local service ports required');
  const stateFile = join(directory, 'state.json');
  const state = existsSync(stateFile) ? json(stateFile, 16384) : { status: 'NOT_STARTED' };
  requireValue(['NOT_STARTED', 'STOPPED', 'FAILED'].includes(state.status), 'Local service must be stopped');
  requireValue(!state.processes?.some(item => item.exit_code === undefined || item.exit_code === null), 'Owned process exit is unconfirmed');
  return { path, directory, config, bridge, ports, sources: [source(path), source(bridgeFile), source(gatewayFile)] };
}
async function offlineLease(context) {
  const lock = join(context.directory, 'supervisor.lock'), contents = Buffer.from(String(process.pid));
  writeNew(lock, contents); // Same exclusive lock honored by the existing supervisor.
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
        await new Promise((done, fail) => { socket.once('error', fail); socket.listen({ host: '127.0.0.1', port, exclusive: true }, done); });
        reservations.push(() => new Promise((done, fail) => socket.close(error => error ? fail(error) : done())));
      } else {
        const socket = createSocket({ type: 'udp4', reuseAddr: false });
        try { await new Promise((done, fail) => { socket.once('error', fail); socket.bind({ address: '127.0.0.1', port, exclusive: true }, done); }); }
        catch (error) { socket.close(); throw error; }
        reservations.push(() => new Promise(done => socket.close(done)));
      }
    }
    // Re-read state/config after acquiring the supervisor lock; a prior start may have raced us.
    const after = loadGarageService(context.path);
    requireValue(isDeepStrictEqual(after.sources, context.sources), 'Configuration changed during offline acquisition');
    return release;
  } catch (error) { await release(); throw error; }
}
function openGame(context) {
  read(context.bridge.game_database, MAX_DB);
  const db = new DatabaseSync(context.bridge.game_database);
  try {
    db.exec('PRAGMA busy_timeout=1000;');
    requireValue(db.prepare('PRAGMA user_version').get().user_version === 1, 'Existing game database version1 required');
    requireValue(db.prepare('PRAGMA quick_check').get().quick_check === 'ok', 'Game database integrity check');
    requireValue(db.prepare('SELECT value FROM game_meta WHERE key=?').get('native_descriptors_sha256')?.value
      === digest(read(context.bridge.native_descriptors, 65536)), 'Database native provenance mismatch');
    return db;
  } catch (error) { db.close(); throw error; }
}
function snapshot(db) {
  const tables = ['game_meta', 'game_profiles', 'game_limits', 'sqlite_sequence'];
  const schema = db.prepare("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").all().map(value => ({ ...value }));
  requireValue(schema.length <= 12 && schema.filter(row => row.type === 'table').every(row => tables.includes(row.name))
    && schema.every(row => ['table', 'index'].includes(row.type)), 'Unexpected database schema');
  const result = { user_version: db.prepare('PRAGMA user_version').get().user_version, schema };
  for (const [table, order] of [['game_meta', 'key'], ['game_profiles', 'native_id'], ['game_limits', 'key_hash'], ['sqlite_sequence', 'name']]) {
    requireValue(db.prepare(`SELECT COUNT(*) AS n FROM ${table}`).get().n <= 10000, 'Database row bound');
    result[table] = db.prepare(`SELECT * FROM ${table} ORDER BY ${order}`).all().map(value => ({ ...value }));
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
function historicalFixture(directory, base, ms1Hash) {
  const bytes = read(join(directory, 'profile-input.json'), 8192), manifest = json(join(directory, 'manifest.json'), 32768);
  requireValue(isDeepStrictEqual(JSON.parse(bytes.toString('utf8')), base)
    && manifest.generator?.sha256 === LEGACY_ENCODER_SHA256 && manifest.compatibility_catalog_revision === 2
    && manifest.account_id === base.account_id && manifest.native_database_id === base.native_database_id
    && isDeepStrictEqual(manifest.profile_source, { file: 'profile-input.json', relative_to: 'fixture_directory', sha256: digest(bytes) })
    && manifest.native_descriptors?.sha256 === ms1Hash, 'Historical r1-catalog2 provenance required');
  requireValue(Array.isArray(manifest.files) && manifest.files.length === 3, 'Historical payload manifest bound');
  for (const name of ['state.bin', 'shop.bin', 'dossier.bin']) {
    const matching = manifest.files.filter(item => item.file === name), payload = read(join(directory, name), 16384);
    requireValue(matching.length === 1 && matching[0].sha256 === digest(payload) && matching[0].bytes === payload.length, 'Historical payload integrity mismatch');
  }
  const compatibility = json(join(directory, 'compatibility.json'), 4096);
  requireValue(compatibility.account_id === base.account_id && compatibility.native_database_id === base.native_database_id
    && compatibility.client_name === base.username && compatibility.compatibility_catalog_revision === 2, 'Historical compatibility mismatch');
  return bytes;
}
function generate(context, args) {
  const result = spawnSync(context.config.python_executable, ['-B', '-X', 'utf8', GENERATOR, ...args],
    { cwd: ROOT, windowsHide: true, encoding: 'utf8', timeout: 10000, maxBuffer: 32768 });
  requireValue(result.status === 0 && !result.error, 'Test garage generator failed; database unchanged');
}
function verifyPlan(context, directory, plan) {
  requireValue(keys(plan, ['version', 'operation', 'account_id', 'native_database_id', 'granted_at_ms', 'service', 'sources',
    'implementation', 'identity', 'before', 'after', 'backup', 'previous_fixture', 'fixture']) && plan.version === 1
    && plan.operation === 'test-is7-v1' && plan.service === context.path && UUID.test(plan.account_id), 'Grant journal schema');
  requireValue(plan.implementation.module_sha256 === digest(read(SELF, 131072))
    && plan.implementation.generator_sha256 === digest(read(GENERATOR, 131072))
    && plan.implementation.dependency_sha256 === LEGACY_ENCODER_SHA256, 'Grant implementation changed');
  requireValue(isDeepStrictEqual(plan.sources.service, context.sources), 'Journal/service configuration changed');
  checkSource(plan.sources.ms1); checkSource(plan.sources.is7);
  for (const item of [plan.before, plan.after]) {
    requireValue(['before-profile.json', 'after-profile.json'].includes(item.file), 'Journal profile filename');
    requireValue(digest(read(join(directory, item.file), 8192)) === item.sha256, 'Journal profile changed');
  }
  const before = JSON.parse(read(join(directory, plan.before.file), 8192).toString('utf8'));
  const after = JSON.parse(read(join(directory, plan.after.file), 8192).toString('utf8'));
  validateBase(before);
  requireValue(before.account_id === plan.account_id && before.native_database_id === plan.native_database_id
    && after.test_grant?.granted_at_ms === plan.granted_at_ms, 'Journal identity/grant mismatch');
  requireValue(isDeepStrictEqual(identity(context, before), plan.identity), 'Journal identity changed');
  requireValue(plan.backup.file === 'game-before.sqlite'
    && digest(read(join(directory, plan.backup.file), MAX_DB)) === plan.backup.sha256, 'Consistent backup integrity mismatch');
  requireValue(plan.previous_fixture.directory === join(context.bridge.fixture_root, plan.account_id, 'r1-catalog2')
    && isDeepStrictEqual(tree(plan.previous_fixture.directory), plan.previous_fixture.snapshot), 'Historical fixture changed');
  validateGrantedProfile(after, read(join(plan.previous_fixture.directory, 'profile-input.json'), 8192));
  requireValue(plan.fixture.directory === join(context.bridge.fixture_root, plan.account_id, 'r2-catalog3'), 'Grant fixture path');
  return { before, after };
}
function fixtureCheck(plan) {
  const actual = validateGrantedFixture(plan.fixture.directory,
    JSON.parse(read(join(plan.fixture.directory, 'profile-input.json'), 8192).toString('utf8')),
    { nativeMs1: plan.sources.ms1.path, nativeIs7: plan.sources.is7.path });
  requireValue(isDeepStrictEqual(actual, plan.fixture.snapshot), 'Immutable granted fixture changed');
}
function commitPrepared(context, directory, plan, db) {
  const { after } = verifyPlan(context, directory, plan);
  if (!existsSync(plan.fixture.directory)) {
    const stage = join(directory, 'fixture-staged');
    requireValue(isDeepStrictEqual(tree(stage), plan.fixture.snapshot), 'Staged fixture changed');
    renameSync(stage, plan.fixture.directory);
  }
  fixtureCheck(plan);
  const beforeText = read(join(directory, plan.before.file), 8192).toString('utf8');
  const afterText = read(join(directory, plan.after.file), 8192).toString('utf8');
  requireValue(isDeepStrictEqual(JSON.parse(afterText), after), 'After profile parse mismatch');
  const commitFile = join(directory, 'committed.json'), preparedHash = digest(read(join(directory, 'prepared.json'), 32768));
  let already = false, beforeDigest, afterDigest;
  db.exec('BEGIN IMMEDIATE');
  try {
    const current = row(db, plan.account_id);
    requireValue(current.native_id === plan.native_database_id, 'Native identity changed');
    const beforeSnapshot = snapshot(db); beforeDigest = digest(JSON.stringify(beforeSnapshot));
    if (current.profile_json === afterText) already = true;
    else {
      requireValue(!existsSync(commitFile) && current.profile_json === beforeText, 'Grant target differs from expected original profile');
      requireValue(beforeDigest === plan.before.database_sha256, 'Database changed before initial grant; rebuild the reviewable plan');
      const changed = db.prepare('UPDATE game_profiles SET profile_json=? WHERE account_id=? AND native_id=? AND profile_json=?')
        .run(afterText, plan.account_id, plan.native_database_id, beforeText).changes;
      requireValue(changed === 1, 'Expected exactly one grant target');
      const expected = structuredClone(beforeSnapshot);
      expected.game_profiles.find(item => item.account_id === plan.account_id).profile_json = afterText;
      requireValue(isDeepStrictEqual(snapshot(db), expected), 'Grant changed unrelated database data');
    }
    afterDigest = digest(JSON.stringify(snapshot(db))); db.exec('COMMIT');
  } catch (error) { db.exec('ROLLBACK'); throw error; }
  if (existsSync(commitFile)) {
    const receipt = json(commitFile);
    requireValue(receipt.prepared_sha256 === preparedHash && receipt.after_profile_sha256 === plan.after.sha256, 'Commit receipt changed');
  } else writeNew(commitFile, { version: 1, status: 'COMMITTED', prepared_sha256: preparedHash,
    after_profile_sha256: plan.after.sha256, database_before_sha256: beforeDigest, database_after_sha256: afterDigest,
    recovered_after_commit: already });
  return { status: already ? 'ALREADY_GRANTED' : 'GRANTED', account_id: plan.account_id, native_database_id: plan.native_database_id,
    snapshot_revision: 2, fixture_directory: plan.fixture.directory, journal: directory,
    journal_sha256: preparedHash, profile_sha256: plan.after.sha256, native_compatibility: 'NOT_RUN' };
}

export async function grantTestVehicle(options) {
  requireValue(keys(options, ['service', 'accountId', 'nativeIs7', 'grantedAtMs', 'expectedProfileSha256', 'journal'])
    && UUID.test(options.accountId) && SHA.test(options.expectedProfileSha256)
    && integer(options.grantedAtMs, 1, 2147483647999), 'Explicit UUID, timestamp, expected profile hash and journal required');
  const context = loadGarageService(options.service), directory = localPath(options.journal), nativeIs7 = localPath(options.nativeIs7);
  requireValue(!inside(context.bridge.fixture_root, directory) && directory !== context.directory, 'Journal must be outside fixture storage');
  const release = await offlineLease(context); let db;
  try {
    const inputs = nativeSources(context.bridge.native_descriptors, nativeIs7);
    requireValue(isDeepStrictEqual(context.bridge.test_garage, { version: 1, native_is7: nativeIs7, sha256: inputs.is7.sha256 }), 'Enable and pin this explicit garage source in bridge config before granting');
    db = openGame(context);
    if (existsSync(directory)) {
      requireValue(!existsSync(join(directory, 'rolled-back.json')), 'Journal already rolled back; no implicit re-grant');
      const plan = json(join(directory, 'prepared.json'), 32768);
      requireValue(plan.account_id === options.accountId && plan.granted_at_ms === options.grantedAtMs
        && plan.before.sha256 === options.expectedProfileSha256 && plan.sources.is7.path === nativeIs7, 'Existing journal belongs to a different explicit request');
      return commitPrepared(context, directory, plan, db);
    }
    const current = row(db, options.accountId), base = validateBase(JSON.parse(current.profile_json));
    requireValue(base.account_id === options.accountId && current.native_id === base.native_database_id
      && digest(current.profile_json) === options.expectedProfileSha256, 'Expected target UUID/native identity/profile hash mismatch');
    const user = identity(context, base), previous = join(context.bridge.fixture_root, options.accountId, 'r1-catalog2');
    const oldInput = join(previous, 'profile-input.json'), originalBytes = historicalFixture(previous, base, inputs.ms1.sha256);
    const historical = tree(previous), beforeSnapshot = snapshot(db), beforeDigest = digest(JSON.stringify(beforeSnapshot));
    mkdirSync(directory, { recursive: false });
    writeNew(join(directory, 'before-profile.json'), Buffer.from(current.profile_json));
    db.prepare('VACUUM INTO ?').run(join(directory, 'game-before.sqlite'));
    const backupFd = openSync(join(directory, 'game-before.sqlite'), 'r+');
    try { fsyncSync(backupFd); } finally { closeSync(backupFd); }
    const backup = new DatabaseSync(join(directory, 'game-before.sqlite'), { readOnly: true });
    try { requireValue(digest(JSON.stringify(snapshot(backup))) === beforeDigest, 'Backup snapshot is inconsistent'); }
    finally { backup.close(); }
    generate(context, ['promote', '--profile-v1', oldInput, '--granted-at-ms', String(options.grantedAtMs), '--out-profile', join(directory, 'proposed-profile.json')]);
    const proposed = validateGrantedProfile(json(join(directory, 'proposed-profile.json')), originalBytes), afterBytes = Buffer.from(JSON.stringify(proposed));
    writeNew(join(directory, 'after-profile.json'), afterBytes);
    generate(context, ['generate', '--profile', join(directory, 'after-profile.json'), '--base-profile', oldInput,
      '--native-ms1', inputs.ms1.path, '--native-is7', inputs.is7.path, '--out', join(directory, 'fixture-staged')]);
    const generated = validateGrantedFixture(join(directory, 'fixture-staged'), proposed, { nativeMs1: inputs.ms1.path, nativeIs7: inputs.is7.path });
    requireValue(isDeepStrictEqual(tree(previous), historical), 'Historical fixture changed during preparation');
    const plan = { version: 1, operation: 'test-is7-v1', account_id: base.account_id, native_database_id: base.native_database_id,
      granted_at_ms: options.grantedAtMs, service: context.path, sources: { service: context.sources, ms1: inputs.ms1, is7: inputs.is7 },
      implementation: { module_sha256: digest(read(SELF, 131072)), generator_sha256: inputs.generator_sha256, dependency_sha256: inputs.dependency_sha256 },
      identity: user, before: { file: 'before-profile.json', sha256: digest(current.profile_json), database_sha256: beforeDigest },
      after: { file: 'after-profile.json', sha256: digest(afterBytes) },
      backup: { file: 'game-before.sqlite', sha256: digest(read(join(directory, 'game-before.sqlite'), MAX_DB)) },
      previous_fixture: { directory: previous, snapshot: historical },
      fixture: { directory: join(context.bridge.fixture_root, options.accountId, 'r2-catalog3'), snapshot: generated } };
    writeNew(join(directory, 'prepared.json'), plan);
    return commitPrepared(context, directory, plan, db);
  } finally { if (db) db.close(); await release(); }
}

export async function rollbackTestVehicle({ service, journal, expectedJournalSha256 }) {
  requireValue(SHA.test(expectedJournalSha256), 'Explicit expected journal SHA256 required');
  const context = loadGarageService(service), directory = localPath(journal);
  requireValue(digest(read(join(directory, 'prepared.json'), 32768)) === expectedJournalSha256, 'Unexpected journal hash');
  const release = await offlineLease(context); let db;
  try {
    const plan = json(join(directory, 'prepared.json'), 32768);
    verifyPlan(context, directory, plan); fixtureCheck(plan);
    const receipt = json(join(directory, 'committed.json'));
    requireValue(receipt.prepared_sha256 === expectedJournalSha256 && receipt.after_profile_sha256 === plan.after.sha256, 'Commit receipt provenance');
    db = openGame(context);
    const beforeText = read(join(directory, plan.before.file), 8192).toString('utf8');
    const afterText = read(join(directory, plan.after.file), 8192).toString('utf8');
    const rollbackFile = join(directory, 'rolled-back.json'); let already = false, previousDigest, currentDigest;
    if (existsSync(rollbackFile)) {
      const existing = json(rollbackFile);
      requireValue(existing.version === 1 && existing.status === 'ROLLED_BACK'
        && existing.prepared_sha256 === expectedJournalSha256 && existing.before_profile_sha256 === plan.before.sha256,
      'Rollback receipt changed');
    }
    db.exec('BEGIN IMMEDIATE');
    try {
      const current = row(db, plan.account_id), previous = snapshot(db); previousDigest = digest(JSON.stringify(previous));
      requireValue(current.native_id === plan.native_database_id, 'Rollback native identity changed');
      if (current.profile_json === beforeText) already = true;
      else {
        requireValue(current.profile_json === afterText, 'Rollback target changed; preserving newer data');
        requireValue(db.prepare('UPDATE game_profiles SET profile_json=? WHERE account_id=? AND native_id=? AND profile_json=?')
          .run(beforeText, plan.account_id, plan.native_database_id, afterText).changes === 1, 'Expected exactly one rollback target');
        const expected = structuredClone(previous);
        expected.game_profiles.find(item => item.account_id === plan.account_id).profile_json = beforeText;
        requireValue(isDeepStrictEqual(snapshot(db), expected), 'Rollback changed unrelated data');
      }
      currentDigest = digest(JSON.stringify(snapshot(db))); db.exec('COMMIT');
    } catch (error) { db.exec('ROLLBACK'); throw error; }
    if (existsSync(rollbackFile)) requireValue(json(rollbackFile).prepared_sha256 === expectedJournalSha256, 'Rollback receipt changed');
    else writeNew(rollbackFile, { version: 1, status: 'ROLLED_BACK', prepared_sha256: expectedJournalSha256,
      before_profile_sha256: plan.before.sha256, database_before_sha256: previousDigest, database_after_sha256: currentDigest,
      unrelated_data_preserved: true, immutable_fixture_retained: true, original_profile_already_present: already });
    return { status: already ? 'ALREADY_ROLLED_BACK' : 'ROLLED_BACK', account_id: plan.account_id,
      profile_sha256: plan.before.sha256, fixture_retained: plan.fixture.directory, journal: directory };
  } finally { if (db) db.close(); await release(); }
}

function cli(args) {
  const [command, ...flags] = args;
  const allowed = command === 'grant' ? ['service', 'account-id', 'native-is7', 'granted-at-ms', 'expect-profile-sha256', 'journal']
    : command === 'rollback' ? ['service', 'journal', 'expect-journal-sha256'] : [];
  requireValue(allowed.length && flags.length === allowed.length * 2, 'Use explicit grant/rollback flags; no defaults');
  const options = {};
  for (let i = 0; i < flags.length; i += 2) {
    const key = flags[i].slice(2);
    requireValue(flags[i].startsWith('--') && allowed.includes(key) && options[key] === undefined && flags[i + 1], 'Unknown or duplicate CLI flag');
    options[key] = flags[i + 1];
  }
  if (command === 'grant') {
    requireValue(/^[0-9]{1,13}$/.test(options['granted-at-ms']), 'Explicit decimal grant timestamp required');
    return grantTestVehicle({ service: options.service, accountId: options['account-id'], nativeIs7: options['native-is7'],
      grantedAtMs: Number(options['granted-at-ms']), expectedProfileSha256: options['expect-profile-sha256'], journal: options.journal });
  }
  return rollbackTestVehicle({ service: options.service, journal: options.journal, expectedJournalSha256: options['expect-journal-sha256'] });
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try { console.log(JSON.stringify(await cli(process.argv.slice(2)))); }
  catch (error) { console.error(JSON.stringify({ status: 'REFUSED', reason: error.message })); process.exitCode = 1; }
}
