/** Shared identity bridge and read-only website boundary. Credentials stay in users. */
import { createServer } from 'node:http';
import { DatabaseSync } from 'node:sqlite';
import { readFileSync, writeFileSync, mkdirSync, existsSync, realpathSync, renameSync, rmSync, statSync } from 'node:fs';
import { dirname, resolve, relative, isAbsolute, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createHash, randomUUID } from 'node:crypto';
import { spawn } from 'node:child_process';
import { openIdentityReader } from './store.mjs';
import { equalToken, validToken, validPassword, verifyPassword, hashPassword, token, nicknameField, emailField, digest } from './security.mjs';
import { grantedOverview, isGrantedOverview, validateGrantedFixture } from './test-garage.mjs';
import { crewOverview, isCrewOverview, validateCrewFixture } from './ms1-crew.mjs';
import { ammoOverview, isAmmoOverview, validateAmmoFixture } from './ms1-ammo.mjs';
import { createNativeAmmoService, nativeAmmoOverview, isNativeAmmoOverview } from './p09d-ammo.mjs';
import { createNativeCrewService, nativeCrewOverview, isNativeCrewOverview } from './p04d-crew.mjs';
import { nativeCrewTransferOverview, isNativeCrewTransferOverview } from './p04f-crew.mjs';
import { nativeCrossVehicleCrewOverview, isNativeCrossVehicleCrewOverview } from './p04g-crew.mjs';
import { nativeResearchOverview, isNativeResearchOverview } from './p09e-research.mjs';
import { battleConfiguration } from './p08b-battle.mjs';
import { nativePoolOverview, isNativePoolOverview, poolConfiguration, nativePoolRequestTimeout, LEGACY_REQUEST_TIMEOUT_MS } from './p04m-pool.mjs';
import { mixedConfiguration, validateMixedResultsRequest, validateMixedResultsReply } from './p06t-mixed.mjs';
import { lossConfiguration, validateLossResultsRequest, validateLossResultsReply } from './p06t-ammo-loss.mjs';
import { lateConfiguration, lateReaderFence, createLateResultService, validateLateRequest, validatePendingRequest, LATE_REQUEST_TIMEOUT_MS } from './p08c-late-results.mjs';
import { ROOM_SELECTION_PATH, SELECTION_REQUEST_TIMEOUT_MS, selectionConfiguration, roomSelectionBody, createRoomSelectionService } from './p10b-selection.mjs';

import { nativeRosterCrewOverview, isNativeRosterCrewOverview } from './p04h-crew.mjs';

import { nativeProgressionCrewOverview, isNativeProgressionCrewOverview } from './p04i-crew.mjs';

import { nativeDismissalCrewOverview, isNativeDismissalCrewOverview } from './p04j-crew.mjs';

import { nativeBarracksCrewOverview, isNativeBarracksCrewOverview } from './p04k-crew.mjs';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const LOCAL = resolve(ROOT, 'local');
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const hash = value => createHash('sha256').update(value).digest('hex');
// Measured pre-email encoder. Existing immutable r1 snapshots are validated,
// not regenerated; IDs, resources and dossier registration date stay intact.
const LEGACY_R1_GENERATORS = [
  'bf026f98e6ccfb84bc2bde4720d9837863beae662a2f4600ad80e78356b040f4',
  '541441a0f38f8ce7600b133b77acad88ee40e01e28093d18e60bbb74261f269a',
];
const CATALOG_REVISION = 2;
const empty = state => ({ schemaVersion: 'web-game-read.v1', state, account: null, inventory: null, statistics: null });
const inside = (root, path) => { const rel = relative(root, path); return rel === '' || (!rel.startsWith('..') && !isAbsolute(rel)); };

function accountId(id) {
  if (typeof id !== 'string' || !UUID.test(id)) throw new TypeError('Authenticated account UUID required');
  return id;
}
function localPath(path, createParent = false) {
  if (typeof path !== 'string' || !isAbsolute(path) || !inside(LOCAL, resolve(path))) throw new Error('Service data must stay in project local');
  let ancestor = resolve(path);
  while (!existsSync(ancestor)) ancestor = dirname(ancestor);
  if (!inside(realpathSync(LOCAL), realpathSync(ancestor))) throw new Error('Redirected service data path');
  if (createParent) mkdirSync(dirname(path), { recursive: true });
  return resolve(path);
}
function readBounded(path, maximum) {
  if (!statSync(path).isFile() || statSync(path).size > maximum) throw new Error('Service file size/type');
  const data = readFileSync(path);
  if (data.length > maximum) throw new Error('Service file size changed');
  return data;
}
function readSecret(path) {
  const value = readBounded(localPath(path), 128).toString('utf8');
  if (!validToken(value)) throw new Error('Service secret must be exactly 43 base64url characters');
  return value;
}

export async function readGameOverview(id) { accountId(id); return empty('not_connected'); }

/** Only the site's authenticated session supplies id; browsers cannot select it. */
export function createGameReader({ origin, tokenFile } = {}) {
  if (!origin && !tokenFile) return readGameOverview;
  const url = new URL(origin);
  if (url.protocol !== 'http:' || url.hostname !== '127.0.0.1' || !url.port || url.username || url.password
      || url.pathname !== '/' || url.search || url.hash) throw new Error('Game bridge must be a numeric loopback origin');
  const secret = readSecret(tokenFile);
  return async id => {
    accountId(id);
    try {
      const response = await fetch(`${url.origin}/internal/accounts/${id}/overview`, {
        headers: { Authorization: `Bearer ${secret}` }, signal: AbortSignal.timeout(2500), redirect: 'error',
      });
      if (!response.ok || Number(response.headers.get('content-length')) > 32768) return empty('unavailable');
      const reader = response.body.getReader();
      const chunks = []; let bytes = 0;
      while (true) {
        const part = await reader.read(); if (part.done) break;
        bytes += part.value.length;
        if (bytes > 32768) { await reader.cancel(); return empty('unavailable'); }
        chunks.push(part.value);
      }
      const value = JSON.parse(Buffer.concat(chunks).toString('utf8'));
      if (value.schemaVersion !== 'web-game-read.v1' || !['ready', 'unlinked'].includes(value.state)) return empty('unavailable');
      if (value.state === 'unlinked') return empty('unlinked');
      if (value.poolService !== undefined) return isNativePoolOverview(value, id) ? value : empty('unavailable');
      if (value.researchService !== undefined) return isNativeResearchOverview(value, id) ? value : empty('unavailable');
      if (value.crewService !== undefined) return (value.crewService?.version === 7 ? isNativeBarracksCrewOverview(value, id) : value.crewService?.version === 6 ? isNativeDismissalCrewOverview(value, id) : value.crewService?.version === 5 ? isNativeProgressionCrewOverview(value, id) : value.crewService?.version === 4 ? isNativeRosterCrewOverview(value, id) : value.crewService?.version === 3 ? isNativeCrossVehicleCrewOverview(value, id) : value.crewService?.version === 2
        ? isNativeCrewTransferOverview(value, id) : isNativeCrewOverview(value, id)) ? value : empty('unavailable');
      if (value.snapshotRevision >= 5) return isNativeAmmoOverview(value, id) ? value : empty('unavailable');
      if (value.snapshotRevision === 4) return isAmmoOverview(value, id) ? value : empty('unavailable');
      if (value.snapshotRevision === 3) return isCrewOverview(value, id) ? value : empty('unavailable');
      if (value.snapshotRevision === 2) return isGrantedOverview(value, id) ? value : empty('unavailable');
      if (value.account?.accountId !== id || value.ruleset !== 'test_lab' || value.snapshotRevision !== 1
          || !nicknameField(value.account?.nickname) || nicknameField(value.account.nickname).display !== value.account.nickname || !Array.isArray(value.inventory) || value.inventory.length !== 1
          || value.inventory[0]?.inventoryItemId !== `${id}:starter-vehicle-v1`
          || value.inventory[0]?.vehicleDefinitionId !== 'vehicle:ms1' || value.inventory[0]?.displayName !== 'МС-1'
          || value.inventory[0]?.health !== 90 || value.inventory[0]?.crewAssigned !== false || value.inventory[0]?.ammunition !== 0
          || !Number.isFinite(Date.parse(value.asOf))
          || !value.statistics || ['battles', 'wins', 'losses', 'draws'].some(k => value.statistics[k] !== 0)
          || !value.resources || ['credits', 'gold', 'freeXP'].some(k => !Number.isSafeInteger(value.resources[k]) || value.resources[k] < 0)) return empty('unavailable');
      return value;
    } catch { return empty('unavailable'); } // Explicit unavailable, never fake zero/ready.
  };
}

function openGameStore(path, sourceHash, now) {
  const db = new DatabaseSync(localPath(path, true));
  db.exec('PRAGMA journal_mode=WAL; PRAGMA busy_timeout=1000;');
  const version = db.prepare('PRAGMA user_version').get().user_version;
  if (version > 1) { db.close(); throw new Error('Unsupported game database version'); }
  if (version === 0) {
    db.exec(`BEGIN IMMEDIATE;
      CREATE TABLE game_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
      CREATE TABLE game_profiles (
        native_id INTEGER PRIMARY KEY AUTOINCREMENT CHECK(native_id BETWEEN 1 AND 2147483647),
        account_id TEXT NOT NULL UNIQUE, profile_json TEXT NOT NULL);
      CREATE TABLE game_limits (key_hash TEXT PRIMARY KEY, hits INTEGER NOT NULL, resets_at INTEGER NOT NULL);
      PRAGMA user_version=1; COMMIT;`);
  }
  const previous = db.prepare('SELECT value FROM game_meta WHERE key=?').get('native_descriptors_sha256');
  if (previous && previous.value !== sourceHash) { db.close(); throw new Error('Native source changed: explicit profile migration required'); }
  if (!previous) db.prepare('INSERT INTO game_meta VALUES (?,?)').run('native_descriptors_sha256', sourceHash);
  const read = id => {
    const row = db.prepare('SELECT profile_json FROM game_profiles WHERE account_id=?').get(id);
    return row ? JSON.parse(row.profile_json) : null;
  };
  return {
    close: () => db.close(), read,
    ensure(user) {
      accountId(user.id);
      let value = read(user.id);
      if (value) {
        if (value.username !== user.display_nickname || value.created_at_ms !== user.created_at) throw new Error('Stored game identity changed: explicit migration required');
        return value;
      }
      db.exec('BEGIN IMMEDIATE');
      try {
        value = read(user.id);
        if (!value) {
          const inserted = db.prepare('INSERT INTO game_profiles(account_id,profile_json) VALUES (?,?)').run(user.id, '{}');
          const nativeId = Number(inserted.lastInsertRowid);
          value = { profile_version: 1, account_id: user.id, username: user.display_nickname,
            native_database_id: nativeId, created_at_ms: user.created_at, snapshot_revision: 1,
            resources: { credits: 100000, gold: 0, free_xp: 0 },
            statistics: { battles: 0, wins: 0, losses: 0, draws: 0 } };
          db.prepare('UPDATE game_profiles SET profile_json=? WHERE account_id=?').run(JSON.stringify(value), user.id);
        }
        db.exec('COMMIT'); return value;
      } catch (error) { db.exec('ROLLBACK'); throw error; }
    },
    limit(key, maximum, windowMs) {
      const stamp = now();
      db.prepare('DELETE FROM game_limits WHERE resets_at<=?').run(stamp);
      const keyHash = digest(key);
      if (!db.prepare('SELECT 1 FROM game_limits WHERE key_hash=?').get(keyHash)
          && db.prepare('SELECT COUNT(*) AS n FROM game_limits').get().n >= 1024) return false;
      const row = db.prepare(`INSERT INTO game_limits VALUES (?,1,?) ON CONFLICT(key_hash) DO UPDATE SET
        hits=min(hits+1,?) RETURNING hits`).get(keyHash, stamp + windowMs, maximum + 1);
      return row.hits <= maximum;
    },
  };
}

function overview(profile) {
  if (profile.pool_service !== undefined) return nativePoolOverview(profile);
  if (profile.profile_version === 13) return nativeResearchOverview(profile);
  if (profile.profile_version === 12) return nativeBarracksCrewOverview(profile);
  if (profile.profile_version === 11) return nativeDismissalCrewOverview(profile);
  if (profile.profile_version === 10) return nativeProgressionCrewOverview(profile);
  if (profile.profile_version === 9) return nativeRosterCrewOverview(profile);
  if (profile.profile_version === 8) return nativeCrossVehicleCrewOverview(profile);
  if (profile.profile_version === 7) return nativeCrewTransferOverview(profile);
  if (profile.profile_version === 6) return nativeCrewOverview(profile);
  if (profile.profile_version === 5) return nativeAmmoOverview(profile);
  if (profile.profile_version === 4) return ammoOverview(profile);
  if (profile.profile_version === 3) return crewOverview(profile);
  if (profile.profile_version === 2) return grantedOverview(profile);
  return { schemaVersion: 'web-game-read.v1', state: 'ready', ruleset: 'test_lab',
    snapshotRevision: profile.snapshot_revision, asOf: new Date(profile.created_at_ms).toISOString(),
    account: { accountId: profile.account_id, nickname: profile.username },
    resources: { credits: profile.resources.credits, gold: profile.resources.gold, freeXP: profile.resources.free_xp },
    inventory: [{ inventoryItemId: `${profile.account_id}:starter-vehicle-v1`, vehicleDefinitionId: 'vehicle:ms1',
      displayName: 'МС-1', health: 90, crewAssigned: false, ammunition: 0 }],
    statistics: profile.statistics,
    capabilities: { battle: false, purchases: false, sales: false },
  };
}

async function runGenerator(python, args) {
  await new Promise((resolvePromise, reject) => {
    const child = spawn(python, ['-X', 'utf8', join(ROOT, 'tools/hangar_state.py'), ...args],
      { cwd: ROOT, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
    let bytes = 0; let exceeded = false;
    const timer = setTimeout(() => { exceeded = true; child.kill(); }, 2500);
    for (const stream of [child.stdout, child.stderr]) stream.on('data', part => {
      bytes += part.length; if (bytes > 16384) { exceeded = true; child.kill(); }
    });
    child.once('error', () => { clearTimeout(timer); reject(new Error('Profile generator could not start')); });
    child.once('close', code => { clearTimeout(timer); code === 0 && !exceeded ? resolvePromise() : reject(new Error('Profile generation failed')); });
  });
}

function readJson(path, max) { return JSON.parse(readBounded(path, max).toString('utf8')); }

/** No listener is created until the original web DB and service inputs validate. */
export async function createIdentityBridge(options, { now = Date.now } = {}) {
  const allowed = ['version', 'port', 'web_database', 'game_database', 'fixture_root', 'native_descriptors', 'python_executable', 'token_file'];
  if (options?.test_garage !== undefined) allowed.push('test_garage');
  if (options?.ammunition_service !== undefined) allowed.push('ammunition_service');
  if (options?.crew_service !== undefined) allowed.push('crew_service');
  if (options?.crew_transfer !== undefined) allowed.push('crew_transfer');
  if (options?.crew_cross_vehicle !== undefined) allowed.push('crew_cross_vehicle');
  if (options?.crew_roster_recruitment !== undefined) allowed.push('crew_roster_recruitment');
  if (options?.crew_barracks_recruitment !== undefined) allowed.push('crew_barracks_recruitment');
  if (options?.crew_dismissal !== undefined) allowed.push('crew_dismissal');
  if (options?.crew_progression !== undefined) allowed.push('crew_progression');
  if (options?.research_service !== undefined) allowed.push('research_service');
  if (options?.battle_service !== undefined) allowed.push('battle_service');
  if (options?.pool_service !== undefined) allowed.push('pool_service');
  if (options?.mixed_service !== undefined) allowed.push('mixed_service');
  if (options?.ammo_loss_service !== undefined) allowed.push('ammo_loss_service');
  if (options?.late_result_service !== undefined) allowed.push('late_result_service');
  if (options?.room_selection_service !== undefined) allowed.push('room_selection_service');
  if (!options || options.version !== 1 || Object.keys(options).some(k => !allowed.includes(k))
      || allowed.some(k => !(k in options)) || !Number.isInteger(options.port) || options.port < 0 || options.port > 65535) throw new Error('Bridge config schema');
  if (options.crew_service !== undefined && options.ammunition_service === undefined) throw new Error('Crew requires the shared ammunition writer');
  if (options.crew_transfer !== undefined && options.crew_service === undefined) throw new Error('Crew transfer requires the shared crew writer');
  if (options.crew_transfer !== undefined && (options.crew_transfer === null || typeof options.crew_transfer !== 'object')) throw new Error('Explicit crew transfer policy required');
  if (options.crew_cross_vehicle !== undefined && (options.crew_transfer === undefined || options.crew_cross_vehicle === null || typeof options.crew_cross_vehicle !== 'object')) throw new Error('Cross-vehicle crew requires explicit transfer policy');
  if (options.crew_progression !== undefined && (options.crew_roster_recruitment === undefined || options.crew_progression === null || typeof options.crew_progression !== 'object')) throw new Error('Crew progression requires explicit roster recruitment');
  if (options.crew_roster_recruitment !== undefined && (options.crew_cross_vehicle === undefined || options.crew_roster_recruitment === null || typeof options.crew_roster_recruitment !== 'object')) throw new Error('Roster recruitment requires explicit cross-vehicle policy');
  if (options.crew_dismissal !== undefined && (options.crew_progression === undefined || options.crew_dismissal === null || typeof options.crew_dismissal !== 'object')) throw new Error('Crew dismissal requires explicit progression');
  if (options.crew_barracks_recruitment !== undefined && (options.crew_dismissal === undefined || options.crew_barracks_recruitment === null || typeof options.crew_barracks_recruitment !== 'object')) throw new Error('Barracks recruitment requires explicit dismissal');
  if (options.research_service !== undefined && (options.crew_barracks_recruitment === undefined || options.research_service === null || typeof options.research_service !== 'object')) throw new Error('Research requires the accepted barracks crew writer');
  if (options.battle_service !== undefined && options.research_service === undefined) throw new Error('Profile13 battle requires the complete research writer');
  if (options.pool_service !== undefined && options.battle_service === undefined) throw new Error('Curated pool requires the profile13 battle writer');
  const battleOwners = options.battle_service === undefined ? null
    : battleConfiguration(options.battle_service, options.ammunition_service?.account_id);
  const poolOwners = options.pool_service === undefined ? [] : poolConfiguration(options.pool_service, battleOwners);
  const mixedOwners = options.mixed_service === undefined ? [] : mixedConfiguration(options.mixed_service, poolOwners);
  const lossOwners = options.ammo_loss_service === undefined ? [] : lossConfiguration(options.ammo_loss_service, mixedOwners);
  const lateOwners = options.late_result_service === undefined ? [] : lateConfiguration(options.late_result_service, mixedOwners);
  const selectionOwners = options.room_selection_service === undefined ? [] : selectionConfiguration(options.room_selection_service, mixedOwners);
  const secret = readSecret(options.token_file);
  const webPath = localPath(options.web_database);
  const nativePath = localPath(options.native_descriptors);
  const nativeBytes = readBounded(nativePath, 65536);
  const generatorHash = hash(readBounded(join(ROOT, 'tools/hangar_state.py'), 65536));
  const native = JSON.parse(nativeBytes.toString('utf8'));
  if (native.vehicle?.type_name !== 'ussr:MS-1' || native.vehicle?.max_health !== 90) throw new Error('Unverified starter descriptor');
  let garage = null;
  if (options.test_garage !== undefined) {
    const value = options.test_garage;
    if (!value || Array.isArray(value) || Object.keys(value).sort().join(',') !== 'native_is7,sha256,version'
        || value.version !== 1 || !/^[0-9a-f]{64}$/.test(value.sha256)) throw new Error('Explicit pinned test garage configuration required');
    const path = localPath(value.native_is7);
    if (hash(readBounded(path, 32768)) !== value.sha256) throw new Error('Test garage native source hash mismatch');
    garage = { nativeMs1: nativePath, nativeIs7: path };
  }
  if (typeof options.python_executable !== 'string' || !isAbsolute(options.python_executable)
      || !statSync(options.python_executable).isFile()) throw new Error('Absolute Python executable required');
  const fixtureRoot = localPath(options.fixture_root, true);
  mkdirSync(fixtureRoot, { recursive: true });
  const identity = openIdentityReader(webPath);
  let game;
  try { game = openGameStore(options.game_database, hash(nativeBytes), now); lateReaderFence(localPath(options.game_database), lateOwners); }
  catch (error) { identity.close(); game?.close(); throw error; }
  let dummyHash;
  try { dummyHash = await hashPassword(token()); }
  catch (error) { identity.close(); game.close(); throw error; }
  let ammunition = null;
  const accountServices = new Map();
  const roomSelections = new Map();
  try {
    if (options.ammunition_service !== undefined) {
      const owners = battleOwners ?? [options.ammunition_service.account_id];
      for (const id of owners) {
        const owner = identity.profile(accountId(id)), profile = game.read(id);
        if (!owner || !profile || profile.account_id !== owner.id || profile.username !== owner.display_nickname
            || profile.created_at_ms !== owner.created_at) throw new Error('Ammunition migration identity binding failed');
        const context = { database: options.game_database, fixtureRoot, python: options.python_executable, localPath };
        const ammo = { ...options.ammunition_service, account_id: id };
        const service = options.crew_service === undefined
          ? await createNativeAmmoService(ammo, context)
          : await createNativeCrewService(ammo, options.crew_service,
            { ...context, transfer: options.crew_transfer ?? null, crossVehicle: options.crew_cross_vehicle ?? null,
              rosterRecruitment: options.crew_roster_recruitment ?? null, progression: options.crew_progression ?? null,
              dismissal: options.crew_dismissal ?? null, barracksRecruitment: options.crew_barracks_recruitment ?? null,
              research: options.research_service ?? null, battle: options.battle_service === undefined ? null
                : { version: options.battle_service.version, policy_sha256: options.battle_service.policy_sha256 },
              pool: poolOwners.includes(id) ? { version: options.pool_service.version, policy_sha256: options.pool_service.policy_sha256 } : null,
              mixed: mixedOwners.includes(id) ? { version: options.mixed_service.version, policy_sha256: options.mixed_service.policy_sha256,
                shell_catalog: options.mixed_service.shell_catalog, terminal_policy: options.mixed_service.terminal_policy } : null,
              ammoLoss: lossOwners.includes(id) ? { version: options.ammo_loss_service.version, contract: options.ammo_loss_service.contract,
                policy_sha256: options.ammo_loss_service.policy_sha256 } : null });
        if (lateOwners.includes(id)) {
          const late = createLateResultService({ database: localPath(options.game_database), originalRoot: ammo.original_root,
            accountId: id, shellCatalog: options.mixed_service.shell_catalog, terminalPolicy: options.mixed_service.terminal_policy,
            loss: lossOwners.includes(id), python: options.python_executable,
            worker: resolve(ROOT, 'tools/p08c_late_results_service.py'), cwd: ROOT });
          service.battle = late.battle; service.results = late.results; service.lateResults = late.append; service.latePending = late.pending;
        }
        accountServices.set(id, service);
      }
      for (const id of selectionOwners) {
        const profile = game.read(id);
        roomSelections.set(id, createRoomSelectionService({ accountId: id, nativeDatabaseId: profile.native_database_id,
          database: options.game_database, bundle: options.ammunition_service.bundle_root, original: options.ammunition_service.original_root,
          python: options.python_executable, localPath, mixed: { version: options.mixed_service.version, policy_sha256: options.mixed_service.policy_sha256,
            shell_catalog: options.mixed_service.shell_catalog, terminal_policy: options.mixed_service.terminal_policy } }));
      }
      ammunition = accountServices.get(options.ammunition_service.account_id);
    }
  } catch (error) { identity.close(); game.close(); throw error; }
  const creating = new Map();
  async function fixture(profile) {
    const id = accountId(profile.account_id);
    const ammunition = accountServices.get(id);
    if (profile.profile_version === 13) {
      if (options.research_service === undefined || !ammunition?.research) throw new Error('Research service is not enabled');
      return ammunition.fixture(profile);
    }
    if (profile.profile_version === 12) {
      if (options.crew_barracks_recruitment === undefined || !ammunition?.recruitBarracks) throw new Error('Barracks recruitment is not enabled');
      return ammunition.fixture(profile);
    }
    if (profile.profile_version === 11) {
      if (options.crew_dismissal === undefined || !ammunition?.dismiss) throw new Error('Crew dismissal is not enabled');
      return ammunition.fixture(profile);
    }
    if (profile.profile_version === 10) {
      if (options.crew_progression === undefined || !ammunition?.learn) throw new Error('Crew progression is not enabled');
      return ammunition.fixture(profile);
    }
    if (profile.profile_version === 9) {
      if (options.crew_roster_recruitment === undefined || !ammunition?.recruit || !ammunition?.transfer) throw new Error('Roster recruitment is not enabled');
      return ammunition.fixture(profile);
    }
    if (profile.profile_version === 8) {
      if (options.crew_cross_vehicle === undefined || !ammunition?.transfer) throw new Error('Cross-vehicle crew is not enabled');
      return ammunition.fixture(profile);
    }
    if (profile.profile_version === 7) {
      if (!ammunition?.transfer) throw new Error('Crew transfer is not enabled');
      return ammunition.fixture(profile);
    }
    if (profile.profile_version === 6) {
      if (!ammunition?.recruit) throw new Error('Crew service is not enabled');
      return ammunition.fixture(profile);
    }
    if (profile.profile_version === 5) {
      if (!ammunition) throw new Error('Ammunition service is not enabled');
      return ammunition.fixture(profile);
    }
    if (profile.profile_version === 4) {
      if (!garage) throw new Error('Explicit offline test garage is not enabled');
      const destination = join(fixtureRoot, id, 'r4-catalog3');
      if (hash(readBounded(garage.nativeIs7, 32768)) !== options.test_garage.sha256) throw new Error('Pinned test garage source changed');
      validateAmmoFixture(destination, profile, { ...garage, baseFixture: join(fixtureRoot, id, 'r3-catalog3') });
      return destination;
    }
    if (profile.profile_version === 3) {
      if (!garage) throw new Error('Explicit offline test garage is not enabled');
      const destination = join(fixtureRoot, id, 'r3-catalog3');
      if (hash(readBounded(garage.nativeIs7, 32768)) !== options.test_garage.sha256) throw new Error('Pinned test garage source changed');
      validateCrewFixture(destination, profile, { ...garage, baseFixture: join(fixtureRoot, id, 'r2-catalog3') });
      return destination;
    }
    if (profile.profile_version === 2) {
      if (!garage) throw new Error('Explicit offline test garage is not enabled');
      const destination = join(fixtureRoot, id, 'r2-catalog3');
      if (hash(readBounded(garage.nativeIs7, 32768)) !== options.test_garage.sha256) throw new Error('Pinned test garage source changed');
      validateGrantedFixture(destination, profile, garage);
      return destination;
    }
    if (profile.profile_version !== 1 || profile.snapshot_revision !== 1) throw new Error('Unsupported stored profile version');
    // The domain snapshot remains r1. Only its native display catalogue changes.
    // Existing r1 is immutable; publishing a sibling is an atomic, reversible step.
    const legacy = localPath(join(fixtureRoot, id, 'r1'), true);
    const destination = localPath(join(fixtureRoot, id, 'r1-catalog2'), true);
    const validateRepresentation = (directory, old) => {
      const manifestPath = localPath(join(directory, 'manifest.json'));
      const manifest = readJson(manifestPath, 32768);
      if (manifest.account_id !== id || manifest.native_database_id !== profile.native_database_id) throw new Error('Fixture identity mismatch');
      const allowedGenerators = old ? [...LEGACY_R1_GENERATORS,
        ...(manifest.compatibility_catalog_revision === 1 ? [generatorHash] : [])] : [generatorHash];
      if (!allowedGenerators.includes(manifest.generator?.sha256)
          || manifest.native_descriptors?.sha256 !== hash(nativeBytes)) throw new Error('Fixture source migration required');
      if (old ? manifest.compatibility_catalog_revision !== undefined && manifest.compatibility_catalog_revision !== 1
        : manifest.compatibility_catalog_revision !== CATALOG_REVISION) throw new Error('Fixture catalogue revision mismatch');
      const files = {};
      for (const name of ['state.bin', 'shop.bin', 'dossier.bin']) {
        const rows = manifest.files?.filter(x => x.file === name);
        const bytes = readBounded(localPath(join(directory, name)), 16384);
        if (rows?.length !== 1 || rows[0].sha256 !== hash(bytes) || rows[0].bytes !== bytes.length) throw new Error('Fixture content mismatch');
        files[name] = hash(bytes);
      }
      const compat = readJson(localPath(join(directory, 'compatibility.json')), 4096);
      if (compat.account_id !== id || compat.native_database_id !== profile.native_database_id || compat.client_name !== profile.username) throw new Error('Fixture mapping mismatch');
      if (!old && compat.compatibility_catalog_revision !== CATALOG_REVISION) throw new Error('Fixture catalogue mapping mismatch');
      const profileBytes = readBounded(localPath(join(directory, 'profile-input.json')), 8192);
      if (manifest.profile_source?.file !== 'profile-input.json'
          || manifest.profile_source?.relative_to !== 'fixture_directory'
          || manifest.profile_source?.sha256 !== hash(profileBytes)) throw new Error('Fixture profile provenance mismatch');
      const persisted = JSON.parse(profileBytes.toString('utf8'));
      if (JSON.stringify(persisted) !== JSON.stringify(profile)) throw new Error('Fixture snapshot mismatch');
      return { manifest_sha256: hash(readBounded(manifestPath, 32768)), files,
        profile_sha256: hash(profileBytes) };
    };
    const previous = () => existsSync(legacy) ? { directory: 'r1', ...validateRepresentation(legacy, true) } : null;
    const validate = () => {
      const current = validateRepresentation(destination, false);
      const before = previous();
      const migration = readJson(localPath(join(destination, 'catalog-migration.json')), 4096);
      if (JSON.stringify(migration) !== JSON.stringify({ version: 1, catalog_revision: CATALOG_REVISION, previous: before })) throw new Error('Catalogue migration provenance changed');
      if (before && ['state.bin', 'dossier.bin'].some(name => current.files[name] !== before.files[name])) throw new Error('Catalogue migration changed account payload');
      return destination;
    };
    if (existsSync(destination)) return validate();
    if (creating.has(id)) return creating.get(id);
    if (creating.size >= 2) throw Object.assign(new Error('Generator busy'), { status: 503 });
    const task = (async () => {
      const before = previous(); // Refuse corrupt legacy data; never regenerate over it.
      const stage = localPath(join(fixtureRoot, id, `pending-${randomUUID()}`));
      mkdirSync(stage);
      try {
        const profileFile = join(stage, 'profile-input.json');
        writeFileSync(profileFile, JSON.stringify(profile), { flag: 'wx', mode: 0o600 });
        await runGenerator(options.python_executable, ['--out', stage, '--native-descriptors', nativePath, '--profile', profileFile,
          '--catalog-version', String(CATALOG_REVISION)]);
        const generated = validateRepresentation(stage, false);
        if (before && ['state.bin', 'dossier.bin'].some(name => generated.files[name] !== before.files[name])) throw new Error('Catalogue generation changed account payload');
        if (JSON.stringify(previous()) !== JSON.stringify(before)) throw new Error('Legacy fixture changed during catalogue generation');
        writeFileSync(join(stage, 'catalog-migration.json'), JSON.stringify({ version: 1, catalog_revision: CATALOG_REVISION, previous: before }), { flag: 'wx', mode: 0o600 });
        renameSync(stage, destination);
        return validate();
      } catch (error) {
        // Only this freshly allocated, checked local staging directory is removed.
        if (existsSync(stage)) rmSync(localPath(stage), { recursive: true, force: true });
        throw error;
      }
    })();
    creating.set(id, task);
    try { return await task; } finally { creating.delete(id); }
  }
  let active = 0;
  const pending = new Set();
  function json(res, status, value) {
    if (res.destroyed || res.writableEnded) return;
    const body = Buffer.from(JSON.stringify(value));
    res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Content-Length': body.length,
      'Cache-Control': 'no-store', Connection: 'close' });
    res.end(body);
  }
  async function body(req, maximum = 2048) {
    if (req.headers['content-type'] !== 'application/json' || req.headers['content-encoding']
        || req.headers['transfer-encoding'] || !/^\d{1,5}$/.test(req.headers['content-length'] || '')) throw Object.assign(new Error('Body shape'), { status: 400 });
    const length = Number(req.headers['content-length']);
    if (length < 2 || length > maximum) throw Object.assign(new Error('Body size'), { status: 413 });
    const parts = []; let bytes = 0;
    for await (const part of req) { bytes += part.length; if (bytes > length) throw Object.assign(new Error('Body size'), { status: 413 }); parts.push(part); }
    if (bytes !== length) throw Object.assign(new Error('Body size'), { status: 400 });
    try { return JSON.parse(Buffer.concat(parts).toString('utf8')); }
    catch { throw Object.assign(new Error('Body JSON'), { status: 400 }); }
  }
  async function request(req, res) {
    const expectedHost = `127.0.0.1:${server.address()?.port}`;
    if (req.socket.remoteAddress !== '127.0.0.1' || req.headers.host !== expectedHost || req.headers.origin) return json(res, 403, { error: 'forbidden' });
    if (req.method === 'GET' && req.url === '/health') return json(res, 200, { status: 'ok', scope: 'game-identity-bridge' });
    const authorization = req.headers.authorization;
    if (typeof authorization !== 'string' || !authorization.startsWith('Bearer ') || !equalToken(authorization.slice(7), secret)) return json(res, 403, { error: 'forbidden' });
    if (active >= 4) return json(res, 503, { error: 'busy' });
    active++;
    const started = performance.now();
    const timedOut = () => { json(res, 503, { error: 'timeout' }); req.destroy(); };
    let timer = setTimeout(timedOut, LEGACY_REQUEST_TIMEOUT_MS);
    function poolRequestBudget(owner) {
      const budget = nativePoolRequestTimeout(req.method, req.url, owner, poolOwners);
      if (budget === LEGACY_REQUEST_TIMEOUT_MS) return;
      const remaining = Math.max(1, budget - (performance.now() - started));
      clearTimeout(timer); timer = setTimeout(timedOut, remaining);
      // Response sockets otherwise inherit server.timeout=5000, shorter than
      // the selected pool worker. This connection serves exactly one request.
      req.socket.setTimeout(remaining);
    }
    try {
      if (req.method === 'POST' && req.url === '/internal/native/login') {
        const value = await body(req);
        if (!value || Array.isArray(value) || Object.keys(value).sort().join(',') !== 'email,password'
            || typeof value.email !== 'string' || value.email.length > 1024 || typeof value.password !== 'string'
            || Buffer.byteLength(value.password) > 512) return json(res, 400, { error: 'invalid_request' });
        const email = emailField(value.email);
        if (!game.limit('bridge-global', 60, 60_000) || !game.limit(`login-email:${email || 'invalid'}`, 10, 15 * 60_000)) return json(res, 429, { error: 'rate_limited' });
        const user = email ? identity.findByEmail(email) : null;
        const eligible = validPassword(value.password);
        const matches = await verifyPassword(eligible ? value.password : 'invalid-password-input', user?.password_hash || dummyHash);
        if (!user || !eligible || !matches) return json(res, 401, { error: 'invalid_credentials' });
        if (res.destroyed || res.writableEnded) return;
        if (options.battle_service !== undefined && !accountServices.has(user.id)) return json(res, 403, { error: 'forbidden' });
        const profile = game.ensure(user);
        poolRequestBudget(user.id); // Only after password and configured-account authorization.
        const directory = await fixture(profile);
        return json(res, 200, { account_id: user.id, native_database_id: profile.native_database_id,
          name: profile.username, fixture_dir: directory });
      }
      if (req.method === 'POST' && req.url === ROOM_SELECTION_PATH) {
        if (options.room_selection_service === undefined) return json(res, 404, { error: 'not_found' });
        const { value, raw } = await roomSelectionBody(req), service = roomSelections.get(value?.account_id);
        if (!service || !identity.profile(value.account_id)) return json(res, 403, { error: 'forbidden' });
        const profile = game.read(value.account_id);
        if (!profile || profile.native_database_id !== value.native_database_id) return json(res, 403, { error: 'forbidden' });
        // Same private auth gate above; extend only this enabled, bound owner route.
        const remaining = Math.max(1, SELECTION_REQUEST_TIMEOUT_MS - (performance.now() - started));
        clearTimeout(timer); timer = setTimeout(timedOut, remaining); req.socket.setTimeout(remaining);
        const selected = await service.select(value, raw);
        if (selected.error === 'selection_not_ready') return json(res, 409, selected);
        return json(res, 200, selected);
      }
      if (req.method === 'POST' && req.url === '/internal/native/profile') {
        if (options.battle_service === undefined) return json(res, 404, { error: 'not_found' });
        const value = await body(req), service = accountServices.get(value?.account_id);
        if (!value || Object.keys(value).sort().join(',') !== 'account_id,native_database_id'
            || !service || !identity.profile(value.account_id)) return json(res, 403, { error: 'forbidden' });
        const profile = game.read(value.account_id);
        if (!profile || profile.native_database_id !== value.native_database_id) return json(res, 403, { error: 'forbidden' });
        poolRequestBudget(value.account_id); // Identity and native database ID were checked above.
        return json(res, 200, { account_id: profile.account_id, native_database_id: profile.native_database_id,
          name: profile.username, fixture_dir: await fixture(profile) });
      }
      if (req.method === 'POST' && ['/internal/native/late-result-append', '/internal/native/late-result-pending'].includes(req.url)) {
        if (options.late_result_service === undefined) return json(res, 404, { error: 'not_found' });
        const pending = req.url === '/internal/native/late-result-pending';
        const value = await body(req, pending ? 2048 : 65536), service = accountServices.get(value?.account_id);
        if (!service || !lateOwners.includes(value.account_id) || !identity.profile(value.account_id)) return json(res, 403, { error: 'forbidden' });
        const profile = game.read(value.account_id);
        if (!profile || profile.native_database_id !== value.native_database_id) return json(res, 403, { error: 'forbidden' });
        (pending ? validatePendingRequest : validateLateRequest)(value, value.account_id);
        const remaining = Math.max(1, LATE_REQUEST_TIMEOUT_MS - (performance.now() - started));
        clearTimeout(timer); timer = setTimeout(timedOut, remaining); req.socket.setTimeout(remaining);
        return json(res, 200, await (pending ? service.latePending : service.lateResults)(value));
      }
      if (req.method === 'POST' && req.url === '/internal/native/battle-results') {
        if (options.battle_service === undefined) return json(res, 404, { error: 'not_found' });
        const value = await body(req, 65536), service = accountServices.get(value?.account_id);
        if (!service || !identity.profile(value.account_id)) return json(res, 403, { error: 'forbidden' });
        const profile = game.read(value.account_id);
        if (!profile || profile.native_database_id !== value.native_database_id) return json(res, 403, { error: 'forbidden' });
        if (lossOwners.includes(value.account_id)) {
          validateLossResultsRequest(value, value.account_id); poolRequestBudget(value.account_id);
          return json(res, 200, validateLossResultsReply(await service.results(value), value));
        }
        if (mixedOwners.includes(value.account_id)) {
          validateMixedResultsRequest(value, value.account_id); poolRequestBudget(value.account_id);
          return json(res, 200, validateMixedResultsReply(await service.results(value), value));
        }
        const valid = condition => { if (!condition) throw Object.assign(new Error('Results schema'), { status: 400 }); };
        const common = ['version', 'operation', 'account_id', 'native_database_id', 'command_key', 'arena_id'];
        const extra = ['run_id', 'battle_id', 'native_inventory_id', 'reservation_id', 'results_json'];
        valid(value && !Array.isArray(value) && ['store', 'query', 'ack'].includes(value.operation));
        valid(Object.keys(value).sort().join(',') === [...common, ...(value.operation === 'store' ? extra : [])].sort().join(',')
          && value.version === 1 && typeof value.command_key === 'string' && /^[A-Za-z0-9_:-]{1,96}$/.test(value.command_key)
          && typeof value.arena_id === 'string' && /^[1-9][0-9]{0,18}$/.test(value.arena_id)
          && BigInt(value.arena_id) <= 9223372036854775807n);
        if (value.operation === 'store') valid(typeof value.run_id === 'string' && UUID.test(value.run_id)
          && value.battle_id === `${value.run_id}:${value.arena_id}`
          && Number.isInteger(value.native_inventory_id) && value.native_inventory_id > 0 && value.native_inventory_id <= 2147483647
          && typeof value.reservation_id === 'string' && /^[A-Za-z0-9_:-]{1,96}$/.test(value.reservation_id)
          && typeof value.results_json === 'string' && Buffer.byteLength(value.results_json) <= 32768);
        poolRequestBudget(value.account_id);
        const result = await service.results(value);
        const replyKeys = [...common, 'status', 'acked', 'replayed', 'results_json', 'code'];
        if (!result || Object.keys(result).sort().join(',') !== replyKeys.sort().join(',')
          || common.some(key => result[key] !== value[key]) || typeof result.acked !== 'boolean' || typeof result.replayed !== 'boolean'
          || !['stored', 'found', 'missing', 'acked', 'rejected'].includes(result.status)
          || (result.status === 'rejected' ? !['RESULT_NOT_READY', 'RESULT_MISMATCH', 'DUPLICATE_PAYLOAD_MISMATCH'].includes(result.code) : result.code !== null)
          || (['missing', 'rejected'].includes(result.status) ? result.results_json !== null || result.acked
            : typeof result.results_json !== 'string' || Buffer.byteLength(result.results_json) > 32768)
          || Buffer.byteLength(JSON.stringify(result)) > 65536) throw new Error('Results worker response schema');
        return json(res, 200, result);
      }
      const nativeMethod = new Map([
        ['/internal/native/ammo', 'service'], ['/internal/native/crew', 'recruit'],
        ['/internal/native/crew-recruit-barracks', 'recruitBarracks'], ['/internal/native/crew-dismiss', 'dismiss'],
        ['/internal/native/crew-learn', 'learn'], ['/internal/native/crew-transfer', 'transfer'],
        ['/internal/native/research', 'research'], ['/internal/native/battle', 'battle'],
      ]).get(req.url);
      if (req.method === 'POST' && nativeMethod) {
        if (!ammunition || typeof ammunition[nativeMethod] !== 'function') return json(res, 404, { error: 'not_found' });
        const value = await body(req, nativeMethod === 'battle' ? 65536 : 2048), service = accountServices.get(value?.account_id);
        if (!service || !identity.profile(service.accountId)) return json(res, 403, { error: 'forbidden' });
        if (typeof service[nativeMethod] !== 'function') return json(res, 404, { error: 'not_found' });
        if (nativeMethod === 'battle' && options.mixed_service !== undefined
          && value.version !== (lossOwners.includes(value.account_id) ? 4 : mixedOwners.includes(value.account_id) ? 2 : 1)) return json(res, 400, { error: 'invalid_request' });
        if (poolOwners.includes(value.account_id)) {
          const profile = game.read(value.account_id);
          if (!profile || profile.native_database_id !== value.native_database_id) return json(res, 403, { error: 'forbidden' });
          poolRequestBudget(value.account_id);
        }
        return json(res, 200, await service[nativeMethod](value));
      }
      const matched = /^\/internal\/accounts\/([0-9a-f-]{36})\/overview$/.exec(req.url);
      if (req.method === 'GET' && matched && UUID.test(matched[1])) {
        if (!identity.profile(matched[1])) return json(res, 404, { error: 'account_not_found' });
        const profile = game.read(matched[1]);
        if (profile?.pool_service !== undefined && !poolOwners.includes(matched[1])) throw new Error('Curated pool overview is not enabled');
        // Pool GET validates the current stored representation structurally.
        // Native login/profile and every command still use the canonical writer.
        // Publishing a native fixture here adds seconds to a read-only website GET.
        if (profile?.pool_service === undefined && [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13].includes(profile?.profile_version)) await fixture(profile);
        return json(res, 200, profile ? overview(profile) : empty('unlinked'));
      }
      return json(res, 404, { error: 'not_found' });
    } catch (error) {
      // Never expose/log request bodies, password hashes, account IDs or error details.
      const status = [400, 413, 503].includes(error.status) ? error.status : 503;
      json(res, status, { error: status === 503 ? 'unavailable' : 'invalid_request' });
    } finally { clearTimeout(timer); active--; }
  }
  const server = createServer({ maxHeaderSize: 4096 }, (req, res) => {
    const task = request(req, res).catch(() => json(res, 503, { error: 'unavailable' }));
    pending.add(task); void task.finally(() => pending.delete(task));
  });
  server.requestTimeout = 5000; server.headersTimeout = 3000; server.timeout = 5000;
  server.keepAliveTimeout = 1; server.maxRequestsPerSocket = 1; server.maxConnections = 16;
  await new Promise((done, fail) => { server.once('error', fail); server.listen(options.port, '127.0.0.1', done); })
    .catch(error => { identity.close(); game.close(); throw error; });
  let closing = null;
  return { server, port: server.address().port, close() {
    if (closing) return closing;
    closing = (async () => {
    const closed = new Promise(done => server.close(done)); server.closeAllConnections();
    await Promise.allSettled([...pending]); await closed; identity.close(); game.close();
    })();
    return closing;
  } };
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    if (process.argv.length !== 4 || process.argv[2] !== '--config') throw new Error('Use --config');
    const options = readJson(localPath(resolve(process.argv[3])), 8192);
    const bridge = await createIdentityBridge(options);
    console.log(JSON.stringify({ event: 'game_bridge_ready', host: '127.0.0.1', port: bridge.port, pid: process.pid }));
    let closing = false;
    const stop = async () => { if (closing) return; closing = true; await bridge.close(); };
    process.on('SIGINT', stop); process.on('SIGTERM', stop);
    process.on('message', value => { if (value === 'shutdown') stop(); });
  } catch { console.error('game_bridge_start_failed: configuration_or_storage'); process.exitCode = 1; }
}
