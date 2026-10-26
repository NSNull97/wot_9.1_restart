/** Narrow project-policy recruitment; ammo and crew share one SQLite worker. */
import { spawn } from 'node:child_process';
import { resolve, isAbsolute } from 'node:path';
import { realpathSync, statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { nativeAmmoOverview, isNativeAmmoOverview } from './p09d-ammo.mjs';
import { createAccountLane } from './account-worker-lane.mjs';

import { BARRACKS_CREW_POLICY_SHA256, validateBarracksRecruitmentResponse } from './p04k-crew.mjs';
import { BATTLE_POLICY_SHA256, validateBattleRequest, validateBattleReply } from './p08b-battle.mjs';
import { POOL_POLICY_SHA256, POOL_WORKER_TIMEOUT_MS, validatePoolBarracksRecruitmentResponse, poolCrewContract } from './p04m-pool.mjs';
import { mixedWorkerConfiguration, validateMixedBattleRequest, validateMixedBattleReply, validateMixedResultsRequest, validateMixedResultsReply } from './p06t-mixed.mjs';
import { holdWorkerConfiguration, validateHoldBattleRequest, validateHoldBattleReply, validateHoldResultsRequest, validateHoldResultsReply } from './p08b-owner-hold.mjs';
import { lossWorkerConfiguration, validateLossBattleRequest, validateLossBattleReply, validateLossResultsRequest, validateLossResultsReply } from './p06t-ammo-loss.mjs';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
export const CREW_POLICY_SHA256 = '7d0e3d7ef28d85bfe32e4fcdea0547696a9b4fd04922a725a2d895e1395f0d55';
export const TRANSFER_POLICY_SHA256 = '35a58c8e13d9b815f8552371bbd6556ba10c091753861e697e522d6a5c877cb2';
export const CROSS_CREW_POLICY_SHA256 = '20f7d65c6d360a17f164cb6e4eaa73056a58a793727d4bfbecc1358e1f21969f';
export const ROSTER_CREW_POLICY_SHA256 = '3e86a495c028570d96a479f409dc578875652e01f60f6ac8c42c5c1bae51737c';
export const PROGRESSION_CREW_POLICY_SHA256 = 'fd79729bbaf926fe2567382be086c5e730c7c6474debe338b3052bb12ba62184';
export const DISMISSAL_CREW_POLICY_SHA256 = 'c7f6d05be033d7ea75b8be50b3a4578d6a4167a9d3d5dc4ea8975878633c74b2';
export const RESEARCH_POLICY_SHA256 = '46875923affb6bd307ad4d35397880fae1dd16fb1992ae2bfbfed607d132361c';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const exact = (v, keys) => v && typeof v === 'object' && !Array.isArray(v)
  && Object.keys(v).sort().join(',') === [...keys].sort().join(',');
const requireValue = (v, message) => { if (!v) throw new Error(message); };
const integer = (v, low, high = 2147483647) => Number.isSafeInteger(v) && v >= low && v <= high;

export async function createNativeCrewService(ammo, crew, { database, fixtureRoot, python, localPath, transfer = null, crossVehicle = null, rosterRecruitment = null, progression = null, dismissal = null, barracksRecruitment = null, research = null, battle = null, pool = null, mixed = null, ammoLoss = null, ownerHold = null, catalogSha256 = null, domain = null }) {
  requireValue(exact(crew, ['version', 'policy_sha256']) && crew.version === 1
    && crew.policy_sha256 === CREW_POLICY_SHA256, 'Explicit project crew policy required');
  requireValue(transfer === null || (exact(transfer, ['version', 'policy_sha256']) && transfer.version === 1
    && transfer.policy_sha256 === TRANSFER_POLICY_SHA256), 'Explicit crew transfer policy required');
  requireValue(crossVehicle === null || (transfer !== null && exact(crossVehicle, ['version', 'policy_sha256'])
    && crossVehicle.version === 1 && crossVehicle.policy_sha256 === CROSS_CREW_POLICY_SHA256), 'Explicit cross-vehicle crew policy required');
  requireValue(rosterRecruitment === null || (crossVehicle !== null && exact(rosterRecruitment, ['version', 'policy_sha256'])
    && rosterRecruitment.version === 1 && rosterRecruitment.policy_sha256 === ROSTER_CREW_POLICY_SHA256), 'Explicit roster recruitment policy required');
  requireValue(progression === null || (rosterRecruitment !== null && exact(progression, ['version', 'policy_sha256'])
    && progression.version === 1 && progression.policy_sha256 === PROGRESSION_CREW_POLICY_SHA256), 'Explicit crew progression policy required');
  requireValue(dismissal === null || (progression !== null && exact(dismissal, ['version', 'policy_sha256'])
    && dismissal.version === 1 && dismissal.policy_sha256 === DISMISSAL_CREW_POLICY_SHA256), 'Explicit crew dismissal policy required');
  requireValue(barracksRecruitment === null || (dismissal !== null && exact(barracksRecruitment, ['version', 'policy_sha256'])
    && barracksRecruitment.version === 1 && barracksRecruitment.policy_sha256 === BARRACKS_CREW_POLICY_SHA256), 'Explicit barracks recruitment policy required');
  requireValue(research === null || (barracksRecruitment !== null && exact(research, ['version', 'policy_sha256']) && research.version === 1
    && research.policy_sha256 === RESEARCH_POLICY_SHA256), 'Explicit research policy required');
  requireValue(battle === null || (research !== null && exact(battle, ['version', 'policy_sha256']) && battle.version === 1
    && battle.policy_sha256 === BATTLE_POLICY_SHA256), 'Explicit profile13 battle policy required');
  requireValue(pool === null || (battle !== null && exact(pool, ['version', 'policy_sha256']) && pool.version === 1
    && pool.policy_sha256 === POOL_POLICY_SHA256), 'Explicit curated pool policy required');
  if (mixed !== null) { requireValue(pool !== null && battle !== null, 'Mixed ammunition requires explicit curated pool/battle'); mixedWorkerConfiguration(mixed); }
  requireValue(catalogSha256 === null || (mixed !== null && typeof catalogSha256 === 'string' && /^[0-9a-f]{64}$/.test(catalogSha256)), 'CAT-01 catalog requires the mixed worker');
  if (ammoLoss !== null) { requireValue(mixed !== null, 'Ammo-rack loss requires explicit mixed ammunition'); lossWorkerConfiguration(ammoLoss); }
  if (ownerHold !== null) { requireValue(ammoLoss !== null, 'Owner hold requires explicit loss4 source'); holdWorkerConfiguration(ownerHold); }
  // DOM-01: the long-lived Domain process runs the same profile13 worker code.
  requireValue(domain === null || (battle !== null && typeof domain.call === 'function'), 'Domain service requires the profile13 battle worker');
  const profileVersion = research !== null ? 13 : barracksRecruitment !== null ? 12 : dismissal !== null ? 11 : progression !== null ? 10 : rosterRecruitment !== null ? 9 : crossVehicle !== null ? 8 : transfer === null ? 6 : 7;
  const worker = battle !== null ? 'tools/p08b_battle_service.py' : research !== null ? 'tools/p09e_research_service.py' : barracksRecruitment !== null ? 'tools/p04k_crew_store.py' : dismissal !== null ? 'tools/p04j_crew_store.py' : progression !== null ? 'tools/p04i_crew_store.py' : rosterRecruitment !== null ? 'tools/p04h_crew_store.py' : crossVehicle !== null ? 'tools/p04g_crew_store.py' : transfer === null ? 'tools/p04d_crew_store.py' : 'tools/p04f_crew_store.py';
  requireValue(exact(ammo, ['version', 'bundle_root', 'original_root', 'account_id', 'grant'])
    && ammo.version === 1 && UUID.test(ammo.account_id) && isAbsolute(ammo.original_root)
    && exact(ammo.grant, ['grant_id', 'quantity_each']) && ammo.grant.grant_id === 'p09d-test-depot-v1'
    && ammo.grant.quantity_each === 100, 'Explicit versioned ammunition configuration required');
  // The research worker reads an existing hash-bound bundle without copying
  // client resources into this worktree. Only the trusted configuration sets
  // this path; every writer/output remains under localPath.
  const bundle = research === null ? localPath(ammo.bundle_root) : (() => {
    requireValue(isAbsolute(ammo.bundle_root) && statSync(ammo.bundle_root).isDirectory()
      && realpathSync(ammo.bundle_root).toLowerCase() === resolve(ammo.bundle_root).toLowerCase(), 'Read-only research bundle path');
    return resolve(ammo.bundle_root);
  })();
  const db = localPath(database), fixtures = localPath(fixtureRoot);
  // One worker of this account at a time; one more caller may wait.
  const lane = createAccountLane(2, 'Crew worker busy');
  const workerTimeout = operation => operation === 'activate' ? 15000 : pool === null ? 3500 : POOL_WORKER_TIMEOUT_MS;
  const replyLimit = research === null ? 32768 : 262144;
  async function run(operation, request) {
    if (domain !== null) return lane(async () => {
      let reply;
      try { reply = await domain.call(operation, ammo.account_id, request ? JSON.stringify(request) : '', request?.command_key ?? null, workerTimeout(operation)); }
      catch { throw new Error('Crew worker unavailable'); }
      if (reply.status !== 200 || reply.body.length > replyLimit) throw new Error('Crew worker unavailable');
      try { return JSON.parse(reply.body.toString('utf8')); }
      catch { throw new Error('Crew worker response invalid'); }
    });
    return lane(() => new Promise((done, fail) => {
        const lossEnvironment = ammoLoss === null ? undefined : { ...process.env };
        if (lossEnvironment !== undefined) delete lossEnvironment.PYTHONPATH;
        const child = spawn(python, ['-B', '-X', 'utf8', resolve(ROOT, worker),
          '--database', db, '--bundle', bundle, '--original-root', ammo.original_root,
          '--account-id', ammo.account_id, '--fixture-root', fixtures,
          ...(mixed === null ? [] : ['--mixed-ammo', '--shell-catalog', mixed.shell_catalog, '--terminal-policy', mixed.terminal_policy]),
          ...(catalogSha256 === null ? [] : ['--catalog-sha256', catalogSha256]),
          ...(ammoLoss === null ? [] : ['--ammo-rack-loss']), ...(ownerHold === null ? [] : ['--owner-battle-hold']), operation],
        { cwd: ROOT, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'], ...(lossEnvironment === undefined ? {} : { env: lossEnvironment }) });
        let size = 0, errorSize = 0, exceeded = false; const parts = [];
        const timer = setTimeout(() => { exceeded = true; child.kill(); }, workerTimeout(operation));
        child.stdout.on('data', part => { size += part.length; if (size > replyLimit) { exceeded = true; child.kill(); } else parts.push(part); });
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
    }));
  }
  async function mutate(operation, request) {
    requireValue(['recruit', 'service', ...(transfer === null ? [] : ['transfer']), ...(progression === null ? [] : ['learn']), ...(dismissal === null ? [] : ['dismiss']), ...(barracksRecruitment === null ? [] : ['recruit-barracks'])].includes(operation), 'Unsupported crew operation');
    // The G/H migrations retain immutable predecessor command receipts. Only that opt-in
    // bridge admits their older cursors; the store binds the complete request
    // to its ledger and older cursors may return successful replays only.
    const minimumRequestRevision = crossVehicle === null ? profileVersion : 6;
    requireValue(exact(request, ['account_id', 'native_database_id', 'command_key', 'expected_revision', 'wire_revision', 'layout'])
      && request.account_id === ammo.account_id && integer(request.native_database_id, 1)
      && typeof request.command_key === 'string' && /^[\x21-\x7e]{1,96}$/.test(request.command_key)
      && integer(request.expected_revision, minimumRequestRevision) && integer(request.wire_revision, 1, 2147483646)
      && Array.isArray(request.layout) && request.layout.length === (['recruit', 'recruit-barracks'].includes(operation) ? 4 : ['transfer', 'learn', 'dismiss'].includes(operation) ? 3 : 16)
      && request.layout.every(v => integer(v, -2147483648)), 'Native crew request schema');
    const value = await run(operation, request), success = operation === 'dismiss' ? 'dismissed' : operation === 'learn' ? 'learned' : ['recruit', 'recruit-barracks'].includes(operation) ? 'recruited' : operation === 'transfer' ? 'transferred' : 'serviced';
    const historicalOnly = request.expected_revision < profileVersion;
    requireValue(exact(value, ['status', 'account_id', 'native_database_id', 'command_key', 'revision', 'wire_revision', 'update_hex', 'replayed', 'result_code', ...(operation === 'recruit-barracks' ? ['tankman_inventory_id', 'tankman_descriptor_hex'] : [])])
      && [success, 'rejected'].includes(value.status) && value.account_id === request.account_id
      && value.native_database_id === request.native_database_id && value.command_key === request.command_key
      && integer(value.revision, historicalOnly ? minimumRequestRevision + 1 : profileVersion) && integer(value.wire_revision, 1)
      && typeof value.replayed === 'boolean' && typeof value.update_hex === 'string'
      && (!historicalOnly || (value.status === success && value.replayed === true))
      && /^(?:[0-9a-f]{2}){0,240}$/.test(value.update_hex)
      && (value.status === success ? value.result_code === 0 && value.update_hex.length > 0
        && value.wire_revision === request.wire_revision + 1 && value.revision === request.expected_revision + 1
        : value.result_code === -10 && value.update_hex === '' && value.wire_revision === request.wire_revision
          && value.revision === request.expected_revision && value.replayed === false),
    'Native crew response schema');
    if (operation === 'recruit-barracks') (pool === null ? validateBarracksRecruitmentResponse : validatePoolBarracksRecruitmentResponse)(value, request, poolCrewCapacity);
    return value;
  }
  if (domain !== null) {
    // The Domain must serve this account with exactly the worker flags this bridge would spawn.
    const described = await domain.call('describe', null, '', null, 5000).catch(() => null);
    let value = null;
    try { value = described?.status === 200 ? JSON.parse(described.body.toString('utf8')) : null; } catch { value = null; }
    const row = Array.isArray(value?.accounts) ? value.accounts.filter(a => a?.account_id === ammo.account_id) : [];
    requireValue(row.length === 1 && row[0].mixed === (mixed !== null) && row[0].ammo_loss === (ammoLoss !== null)
      && row[0].owner_hold === (ownerHold !== null) && row[0].catalog === (catalogSha256 !== null)
      && (catalogSha256 === null || value.catalog_sha256 === catalogSha256), 'Domain service account configuration mismatch');
  }
  const activated = await run('activate');
  requireValue(pool === null ? activated.profile?.pool_service === undefined
    : activated.profile?.pool_service?.policy_sha256 === POOL_POLICY_SHA256,
  'Curated pool activation/configuration mismatch');
  // The crew contract (v1/v2) is the stored one; it changes only offline.
  const poolCrewCapacity = pool === null ? undefined : poolCrewContract(activated.profile.crew_service).capacity;
  async function researchCommand(request) {
    requireValue(research !== null && exact(request, ['account_id', 'native_database_id', 'command_key', 'expected_revision', 'wire_revision', 'command', 'arguments'])
      && request.account_id === ammo.account_id && integer(request.native_database_id, 1)
      && typeof request.command_key === 'string' && /^[\x21-\x7e]{1,96}$/.test(request.command_key)
      && integer(request.expected_revision, 9, 2147483646) && integer(request.wire_revision, 1, 2147483646)
      && [101, 201, 301, 302, 308].includes(request.command) && Array.isArray(request.arguments)
      && request.arguments.length === ({ 101: 3, 201: 3, 301: 4, 302: 4, 308: 6 })[request.command]
      && request.arguments.every(v => integer(v, -2147483648)), 'Native research request schema');
    const value = await run('research', request);
    requireValue(exact(value, ['status', 'account_id', 'native_database_id', 'command_key', 'revision', 'wire_revision', 'update_hex', 'replayed', 'result_code'])
      && ['researched', 'rejected'].includes(value.status) && value.account_id === request.account_id
      && value.native_database_id === request.native_database_id && value.command_key === request.command_key
      && typeof value.replayed === 'boolean' && typeof value.update_hex === 'string' && /^(?:[0-9a-f]{2}){0,240}$/.test(value.update_hex)
      && (value.status === 'researched' ? value.result_code === 0 && value.update_hex.length > 0
        && value.revision === request.expected_revision + 1 && value.wire_revision === request.wire_revision + 1
        : value.result_code === -10 && value.update_hex === '' && value.replayed === false
          && value.revision === request.expected_revision && value.wire_revision === request.wire_revision), 'Native research response schema');
    return value;
  }
  return {
    accountId: ammo.account_id,
    ...(battle === null ? {} : { async battle(request) {
      if (ownerHold !== null) { validateHoldBattleRequest(request, ammo.account_id); return validateHoldBattleReply(await run('battle', request), request); }
      if (ammoLoss !== null) { validateLossBattleRequest(request, ammo.account_id); return validateLossBattleReply(await run('battle', request), request); }
      if (mixed !== null) { validateMixedBattleRequest(request, ammo.account_id); return validateMixedBattleReply(await run('battle', request), request); }
      validateBattleRequest(request, ammo.account_id);
      return validateBattleReply(await run('battle', request), request);
    }, async results(request) {
      if (ownerHold !== null) { validateHoldResultsRequest(request, ammo.account_id); return validateHoldResultsReply(await run('results', request), request); }
      if (ammoLoss !== null) { validateLossResultsRequest(request, ammo.account_id); return validateLossResultsReply(await run('results', request), request); }
      if (mixed !== null) { validateMixedResultsRequest(request, ammo.account_id); return validateMixedResultsReply(await run('results', request), request); }
      return run('results', request);
    } }),
    async fixture(profile) {
      requireValue(profile.account_id === ammo.account_id && profile.profile_version === profileVersion, 'Crew profile owner mismatch');
      const value = await run('fixture');
      requireValue(value.profile?.account_id === profile.account_id && value.profile.native_database_id === profile.native_database_id
        && integer(value.revision, profileVersion) && value.profile.profile_version === profileVersion, 'Crew fixture identity mismatch');
      return localPath(value.fixture_dir);
    },
    ...(barracksRecruitment === null ? {} : { recruitBarracks: request => mutate('recruit-barracks', request) }),
    ...(dismissal === null ? {} : { dismiss: request => mutate('dismiss', request) }),
    ...(progression === null ? {} : { learn: request => mutate('learn', request) }),
    service: request => mutate('service', request),
    recruit: request => mutate('recruit', request),
    ...(transfer === null ? {} : { transfer: request => mutate('transfer', request) }),
    ...(research === null ? {} : { research: researchCommand }),
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
