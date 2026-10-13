/** Narrow project-policy recruitment; ammo and crew share one SQLite worker. */
import { spawn } from 'node:child_process';
import { resolve, isAbsolute } from 'node:path';
import { fileURLToPath } from 'node:url';
import { nativeAmmoOverview, isNativeAmmoOverview } from './p09d-ammo.mjs';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
export const CREW_POLICY_SHA256 = '7d0e3d7ef28d85bfe32e4fcdea0547696a9b4fd04922a725a2d895e1395f0d55';
export const TRANSFER_POLICY_SHA256 = '35a58c8e13d9b815f8552371bbd6556ba10c091753861e697e522d6a5c877cb2';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const exact = (v, keys) => v && typeof v === 'object' && !Array.isArray(v)
  && Object.keys(v).sort().join(',') === [...keys].sort().join(',');
const requireValue = (v, message) => { if (!v) throw new Error(message); };
const integer = (v, low, high = 2147483647) => Number.isSafeInteger(v) && v >= low && v <= high;

export async function createNativeCrewService(ammo, crew, { database, fixtureRoot, python, localPath, transfer = null }) {
  requireValue(exact(crew, ['version', 'policy_sha256']) && crew.version === 1
    && crew.policy_sha256 === CREW_POLICY_SHA256, 'Explicit project crew policy required');
  requireValue(transfer === null || (exact(transfer, ['version', 'policy_sha256']) && transfer.version === 1
    && transfer.policy_sha256 === TRANSFER_POLICY_SHA256), 'Explicit crew transfer policy required');
  const profileVersion = transfer === null ? 6 : 7;
  const worker = transfer === null ? 'tools/p04d_crew_store.py' : 'tools/p04f_crew_store.py';
  requireValue(exact(ammo, ['version', 'bundle_root', 'original_root', 'account_id', 'grant'])
    && ammo.version === 1 && UUID.test(ammo.account_id) && isAbsolute(ammo.original_root)
    && exact(ammo.grant, ['grant_id', 'quantity_each']) && ammo.grant.grant_id === 'p09d-test-depot-v1'
    && ammo.grant.quantity_each === 100, 'Explicit versioned ammunition configuration required');
  const bundle = localPath(ammo.bundle_root), db = localPath(database), fixtures = localPath(fixtureRoot);
  let active = 0;
  async function run(operation, request) {
    requireValue(active < 2, 'Crew worker busy'); active++;
    try {
      return await new Promise((done, fail) => {
        const child = spawn(python, ['-B', '-X', 'utf8', resolve(ROOT, worker),
          '--database', db, '--bundle', bundle, '--original-root', ammo.original_root,
          '--account-id', ammo.account_id, '--fixture-root', fixtures, operation],
        { cwd: ROOT, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'] });
        let size = 0, errorSize = 0, exceeded = false; const parts = [];
        const timer = setTimeout(() => { exceeded = true; child.kill(); }, operation === 'activate' ? 15000 : 3500);
        child.stdout.on('data', part => { size += part.length; if (size > 32768) { exceeded = true; child.kill(); } else parts.push(part); });
        child.stderr.on('data', part => { errorSize += part.length; if (errorSize > 4096) { exceeded = true; child.kill(); } });
        child.once('error', () => { clearTimeout(timer); fail(new Error('Crew worker failed')); });
        child.once('close', code => {
          clearTimeout(timer);
          if (code !== 0 || exceeded) return fail(new Error('Crew worker unavailable'));
          try { done(JSON.parse(Buffer.concat(parts).toString('utf8'))); }
          catch { fail(new Error('Crew worker response invalid')); }
        });
        child.stdin.on('error', () => { exceeded = true; child.kill(); });
        child.stdin.end(request ? JSON.stringify(request) : '');
      });
    } finally { active--; }
  }
  async function mutate(operation, request) {
    requireValue(['recruit', 'service', ...(transfer === null ? [] : ['transfer'])].includes(operation), 'Unsupported crew operation');
    requireValue(exact(request, ['account_id', 'native_database_id', 'command_key', 'expected_revision', 'wire_revision', 'layout'])
      && request.account_id === ammo.account_id && integer(request.native_database_id, 1)
      && typeof request.command_key === 'string' && /^[\x21-\x7e]{1,96}$/.test(request.command_key)
      && integer(request.expected_revision, profileVersion) && integer(request.wire_revision, 1, 2147483646)
      && Array.isArray(request.layout) && request.layout.length === (operation === 'recruit' ? 4 : operation === 'transfer' ? 3 : 16)
      && request.layout.every(v => integer(v, -2147483648)), 'Native crew request schema');
    const value = await run(operation, request), success = operation === 'recruit' ? 'recruited' : operation === 'transfer' ? 'transferred' : 'serviced';
    requireValue(exact(value, ['status', 'account_id', 'native_database_id', 'command_key', 'revision', 'wire_revision', 'update_hex', 'replayed', 'result_code'])
      && [success, 'rejected'].includes(value.status) && value.account_id === request.account_id
      && value.native_database_id === request.native_database_id && value.command_key === request.command_key
      && integer(value.revision, profileVersion) && integer(value.wire_revision, 1)
      && typeof value.replayed === 'boolean' && typeof value.update_hex === 'string'
      && /^(?:[0-9a-f]{2}){0,240}$/.test(value.update_hex)
      && (value.status === success ? value.result_code === 0 && value.update_hex.length > 0
        && value.wire_revision === request.wire_revision + 1 && value.revision === request.expected_revision + 1
        : value.result_code === -10 && value.update_hex === '' && value.wire_revision === request.wire_revision
          && value.revision === request.expected_revision && value.replayed === false),
    'Native crew response schema');
    return value;
  }
  await run('activate');
  return {
    accountId: ammo.account_id,
    async fixture(profile) {
      requireValue(profile.account_id === ammo.account_id && profile.profile_version === profileVersion, 'Crew profile owner mismatch');
      const value = await run('fixture');
      requireValue(value.profile?.account_id === profile.account_id && value.profile.native_database_id === profile.native_database_id
        && integer(value.revision, profileVersion) && value.profile.profile_version === profileVersion, 'Crew fixture identity mismatch');
      return localPath(value.fixture_dir);
    },
    service: request => mutate('service', request),
    recruit: request => mutate('recruit', request),
    ...(transfer === null ? {} : { transfer: request => mutate('transfer', request) }),
  };
}

export function nativeCrewOverview(profile) {
  const c = profile.crew_service, members = profile.crew, id = profile.account_id;
  requireValue(profile.profile_version === 6 && integer(profile.snapshot_revision, 6)
    && exact(c, ['schema', 'policy_sha256', 'free_recruitment_left', 'configuration_revision', 'battle'])
    && c.schema === 'p04d-native-crew.v1' && c.policy_sha256 === CREW_POLICY_SHA256 && c.battle === false
    && integer(c.free_recruitment_left, 0, 1) && c.configuration_revision === 2 - c.free_recruitment_left
    && Array.isArray(members) && members.length === 3 - c.free_recruitment_left, 'Dynamic crew profile required');
  const vehicle = `${id}:starter-vehicle-v1`;
  members.forEach((m, i) => {
    const role = i === 0 ? 'commander' : 'driver';
    requireValue(exact(m, ['crew_id', 'vehicle_inventory_id', 'role', 'role_level', 'skills'])
      && m.crew_id === (i < 2 ? `${id}:ms1-${role}-v1` : `${id}:recruit-ms1-driver:3`)
      && m.vehicle_inventory_id === (i === 0 || i === members.length - 1 ? vehicle : null)
      && m.role === role && m.role_level === 100 && Array.isArray(m.skills) && m.skills.length === 0,
    'Crew inventory/assignment mismatch');
  });
  // Validate historical immutable fields through the existing profile5 reader;
  // this temporary view never becomes stored state. The actual dynamic crew
  // has been checked above and its counts are exposed separately below.
  const base = structuredClone(profile); delete base.crew_service;
  base.profile_version = 5;
  base.crew = ['commander', 'driver'].map(role => ({ crew_id: `${id}:ms1-${role}-v1`,
    vehicle_inventory_id: vehicle, role, role_level: 100, skills: [] }));
  const value = nativeAmmoOverview(base);
  value.crewService = { version: 1, policy: 'test_lab.free100.ms1-driver.v1',
    freeRecruitmentLeft: c.free_recruitment_left, configurationRevision: c.configuration_revision,
    tankmen: members.length, assigned: 2, barracks: members.length - 2, battle: false };
  return value;
}

export function isNativeCrewOverview(value, id) {
  const c = value?.crewService;
  if (!integer(value?.snapshotRevision, 6)
    || !exact(c, ['version', 'policy', 'freeRecruitmentLeft', 'configurationRevision', 'tankmen', 'assigned', 'barracks', 'battle'])
    || c.version !== 1 || c.policy !== 'test_lab.free100.ms1-driver.v1' || c.battle !== false
    || !integer(c.freeRecruitmentLeft, 0, 1) || c.configurationRevision !== 2 - c.freeRecruitmentLeft
    || c.tankmen !== 3 - c.freeRecruitmentLeft || c.assigned !== 2 || c.barracks !== c.tankmen - 2) return false;
  const base = structuredClone(value); delete base.crewService;
  return isNativeAmmoOverview(base, id);
}
