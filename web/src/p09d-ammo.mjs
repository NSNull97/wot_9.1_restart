/** Opt-in bounded IPC to the same-game.sqlite P09C transactional adapter. */
import { spawn } from 'node:child_process';
import { resolve, isAbsolute } from 'node:path';
import { fileURLToPath } from 'node:url';
import { ammoOverview, isAmmoOverview } from './ms1-ammo.mjs';
import { createAccountLane } from './account-worker-lane.mjs';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const exact = (v, keys) => v && typeof v === 'object' && !Array.isArray(v)
  && Object.keys(v).sort().join(',') === [...keys].sort().join(',');
const requireValue = (v, message) => { if (!v) throw new Error(message); };

export async function createNativeAmmoService(options, { database, fixtureRoot, python, localPath }) {
  requireValue(exact(options, ['version', 'bundle_root', 'original_root', 'account_id', 'grant'])
    && options.version === 1 && UUID.test(options.account_id) && isAbsolute(options.original_root)
    && exact(options.grant, ['grant_id', 'quantity_each']) && options.grant.grant_id === 'p09d-test-depot-v1'
    && options.grant.quantity_each === 100, 'Explicit versioned test ammunition configuration required');
  const bundle = localPath(options.bundle_root), db = localPath(database), fixtures = localPath(fixtureRoot);
  // One worker of this account at a time; one more caller may wait.
  const lane = createAccountLane(2, 'Ammunition worker busy');
  async function run(operation, request) {
    return lane(() => new Promise((done, fail) => {
        const child = spawn(python, ['-B', '-X', 'utf8', resolve(ROOT, 'tools/p09d_ammo_store.py'),
          '--database', db, '--bundle', bundle, '--original-root', options.original_root,
          '--account-id', options.account_id, '--fixture-root', fixtures, operation],
        { cwd: ROOT, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'] });
        let size = 0, errorSize = 0, exceeded = false; const parts = [];
        const timer = setTimeout(() => { exceeded = true; child.kill(); }, operation === 'activate' ? 15000 : 3500);
        child.stdout.on('data', part => { size += part.length; if (size > 32768) { exceeded = true; child.kill(); } else parts.push(part); });
        child.stderr.on('data', part => { errorSize += part.length; if (errorSize > 4096) { exceeded = true; child.kill(); } });
        child.once('error', () => { clearTimeout(timer); fail(new Error('Ammunition worker failed')); });
        child.once('close', code => {
          clearTimeout(timer);
          if (code !== 0 || exceeded) return fail(new Error('Ammunition worker unavailable'));
          try { done(JSON.parse(Buffer.concat(parts).toString('utf8'))); }
          catch { fail(new Error('Ammunition worker response invalid')); }
        });
        child.stdin.on('error', () => { exceeded = true; child.kill(); });
        child.stdin.end(request ? JSON.stringify(request) : '');
    }));
  }
  await run('activate');
  return {
    accountId: options.account_id,
    async fixture(profile) {
      requireValue(profile.account_id === options.account_id && profile.profile_version === 5, 'Ammunition profile owner mismatch');
      const value = await run('fixture');
      requireValue(value.profile?.account_id === profile.account_id && value.profile.native_database_id === profile.native_database_id
        && Number.isSafeInteger(value.revision) && value.revision >= 5, 'Ammunition fixture identity mismatch');
      return localPath(value.fixture_dir);
    },
    async service(request) {
      requireValue(exact(request, ['account_id', 'native_database_id', 'command_key', 'expected_revision', 'wire_revision', 'layout'])
        && request.account_id === options.account_id && Number.isSafeInteger(request.native_database_id)
        && request.native_database_id > 0 && typeof request.command_key === 'string'
        && /^[\x21-\x7e]{1,96}$/.test(request.command_key)
        && Number.isSafeInteger(request.expected_revision) && request.expected_revision >= 5
        && Number.isSafeInteger(request.wire_revision) && request.wire_revision >= 1
        && Array.isArray(request.layout) && request.layout.length === 16
        && request.layout.every(v => Number.isInteger(v) && v >= -2147483648 && v <= 2147483647), 'Ammunition request schema');
      const value = await run('service', request);
      requireValue(exact(value, ['status', 'account_id', 'native_database_id', 'command_key', 'revision', 'wire_revision', 'update_hex', 'replayed', 'result_code'])
        && ['serviced', 'rejected'].includes(value.status) && value.account_id === request.account_id
        && value.native_database_id === request.native_database_id && value.command_key === request.command_key
        && Number.isInteger(value.revision) && value.revision >= 5 && Number.isInteger(value.wire_revision)
        && typeof value.replayed === 'boolean' && typeof value.update_hex === 'string'
        && /^(?:[0-9a-f]{2}){0,240}$/.test(value.update_hex)
        && (value.status === 'serviced' ? value.result_code === 0 && value.update_hex.length > 0
          && value.wire_revision === request.wire_revision + 1 : value.result_code === -10 && value.update_hex === ''),
      'Ammunition response schema');
      return value;
    },
  };
}

export function nativeAmmoOverview(profile) {
  requireValue(profile.profile_version === 5 && Number.isSafeInteger(profile.snapshot_revision) && profile.snapshot_revision >= 5
    && profile.ammunition_service?.schema === 'p09d-native-ammo.v1', 'Dynamic ammunition profile required');
  const base = structuredClone(profile);
  delete base.ammunition_service; delete base.ammunition_depot;
  base.profile_version = 4; base.snapshot_revision = 4;
  base.inventory[0].ammunition_count = 20; base.inventory[1].ammunition_count = 0;
  base.ammunition = [{ vehicle_inventory_id: `${base.account_id}:starter-vehicle-v1`, shell_definition_id: 'shell:ms1-stock-ap', count: 20 }];
  const value = ammoOverview(base);
  value.snapshotRevision = profile.snapshot_revision;
  value.inventory.forEach((item, index) => { item.ammunition = profile.inventory[index].ammunition_count; });
  value.ammunitionService = { version: 1, funding: 'owned_test_depot', purchases: false };
  return value;
}

export function isNativeAmmoOverview(value, id) {
  if (!value || !Number.isSafeInteger(value.snapshotRevision) || value.snapshotRevision < 5
    || !exact(value.ammunitionService, ['version', 'funding', 'purchases'])
    || value.ammunitionService.version !== 1 || value.ammunitionService.funding !== 'owned_test_depot'
    || value.ammunitionService.purchases !== false || value.inventory?.length !== 2
    || value.inventory.some((item, i) => !Number.isInteger(item.ammunition) || item.ammunition < 0 || item.ammunition > [96, 30][i])) return false;
  const old = structuredClone(value); delete old.ammunitionService;
  old.snapshotRevision = 4; old.inventory[0].ammunition = 20; old.inventory[1].ammunition = 0;
  return isAmmoOverview(old, id);
}
