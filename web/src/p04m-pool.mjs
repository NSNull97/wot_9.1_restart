/** Explicit five-type owner projection; legacy P09E readers remain strict. */
import { nicknameField } from './security.mjs';
import { CATALOG_SHA256, CATALOG_VEHICLES } from './catalog-v1.mjs';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';

export const POOL_WORKER_TIMEOUT_MS = 7000;
export const POOL_MUTATION_TIMEOUT_MS = 9000;
export const LEGACY_REQUEST_TIMEOUT_MS = 4500;
const POOL_NATIVE_REQUEST_ROUTES = new Set(['/internal/native/login', '/internal/native/profile', '/internal/native/ammo', '/internal/native/crew', '/internal/native/crew-recruit-barracks',
  '/internal/native/crew-dismiss', '/internal/native/crew-learn', '/internal/native/crew-transfer',
  '/internal/native/research', '/internal/native/battle', '/internal/native/battle-results']);

export function nativePoolRequestTimeout(method, path, owner, configuredPoolOwners) {
  return method === 'POST' && POOL_NATIVE_REQUEST_ROUTES.has(path) && configuredPoolOwners.includes(owner)
    ? POOL_MUTATION_TIMEOUT_MS : LEGACY_REQUEST_TIMEOUT_MS;
}

export const POOL_POLICY_SHA256 = 'd1acd5590309c80b65307758bbee6f7f6de117f899668a00b1fad96ae6a13d3f';
export const POOL_CREW_POLICY_SHA256 = '6621ad7d3ccb86ebe8cc9db43b135d88155762ed3428e2a12b4002aba431a99b';
export const POOL_CREW_V2_POLICY_SHA256 = '7ff51fd896ab4e9f97c1a4dc7b46e75da08876f025a9afe7408f611f8d8caa1d';
// tools/p04m_pool_crew.py: the account's stored contract (v2 only after its
// explicit migration) fixes the lifetime allocator. Barracks berths stay 16.
const CREW_CONTRACTS = Object.freeze({
  'p04m-pool-crew.v1': Object.freeze({ schema: 'p04m-pool-crew.v1', policySha256: POOL_CREW_POLICY_SHA256, capacity: 16 }),
  'p04m-pool-crew.v2': Object.freeze({ schema: 'p04m-pool-crew.v2', policySha256: POOL_CREW_V2_POLICY_SHA256, capacity: 192 }),
});
export const poolCrewContract = service => {
  const contract = typeof service?.schema === 'string' && Object.hasOwn(CREW_CONTRACTS, service.schema) ? CREW_CONTRACTS[service.schema] : null;
  requireValue(contract && service.policy_sha256 === contract.policySha256, 'pool crew contract');
  return contract;
};
const crewContractBySha = sha => Object.values(CREW_CONTRACTS).find(c => c.policySha256 === sha) ?? null;
// BATTLE-ANY: per-nation passport ID sets, the exact bytes of the pinned #717 table
// (tools/tankman_passports.py). USSR = 1..112/1..1036/1..30 (p04h CATALOG_BOUNDS).
const TANKMAN_PASSPORTS_SHA256 = '7e1900f6244f1e7c7995b99cfe8ba05b68c2ad64990d25ea88f5ed96448198bd';
const PASSPORTS = (() => {
  const raw = readFileSync(new URL('../../config/catalog/tankman_passports.v1.json', import.meta.url));
  if (createHash('sha256').update(raw).digest('hex') !== TANKMAN_PASSPORTS_SHA256) throw new Error('P04M tankman passport table SHA');
  return new Map(JSON.parse(raw).nations.map(r => [r.nation_id, ['first_names', 'last_names', 'icons'].map(k => r[k].ranges)]));
})();
/** Free50 passport of identity `id` for compact type `cd`: the recruited type's nation
 * (header 8 + (nation << 4)) and that nation's passport sets. */
export function barracksPassport(cd, role, id) {
  const nation = (cd >> 4) & 15; const sets = PASSPORTS.get(nation);
  requireValue(sets, 'barracks tankman nation');
  const names = sets.flatMap(ranges => { const n = passportId(ranges, id); return [n & 255, n >> 8]; });
  return Buffer.from([8 + (nation << 4), cd >> 8, role, 50, 0, 0, 0, ...names, 64, 6, 0, 0, 0, 0, 66, 0, 0, 0, 0, 0]);
}
// (id-1)-th member of a set, modulo its size (P04H project allocation; USSR equals the v1 rule).
const passportId = (ranges, id) => {
  let k = (id - 1) % ranges.reduce((n, [a, b]) => n + b - a + 1, 0);
  for (const [a, b] of ranges) { if (k <= b - a) return a + k; k -= b - a + 1; }
  return 0;
};
export const POOL_REGISTRY_SHA256 = 'e2f4ac21fe8970f3c5d29f6a45d845f9d80e4d2759f0e662c9f3bb9ac04c7b34';
const SCHEMA = 'p04m-curated-stock-pool.v1';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const SHA = /^[0-9a-f]{64}$/;
const VEHICLE = /^vehicle:(ussr|germany|usa|france|uk|china|japan):[A-Za-z0-9_.-]{1,96}$/;
const MODULE_ROLES = ['chassis', 'engine', 'fuelTank', 'radio', 'turret', 'gun'];
const ROLE_IDS = { commander: 1, radioman: 2, driver: 3, gunner: 4, loader: 5 };
// Source PINS in p04m_stock_registry.py / p04m_battle_profiles.py, qualified
// writer fixtures03. These are capacities and primary seats, not admission.
const TYPES = [
  { kind: 'ms1', resource: 'MS-1', cd: 3329, capacity: 96, roles: ['commander', 'driver'], shells: ['ap', 'heat', 'he'] },
  { kind: 'is7', resource: 'IS-7', cd: 7169, capacity: 30, roles: ['commander', 'gunner', 'driver', 'loader', 'loader'], shells: ['ap', 'apcr', 'he'] },
  { kind: 't26', resource: 'T-26', cd: 4609, capacity: 160, roles: ['commander', 'driver', 'gunner'], shells: ['ap', 'apcr', 'he'] },
  { kind: 't34', resource: 'T-34', cd: 1, capacity: 77, roles: ['commander', 'radioman', 'driver', 'loader'], shells: ['ap', 'heat', 'he'] },
  { kind: 't3485', resource: 'T-34-85', cd: 2561, capacity: 68, roles: ['commander', 'gunner', 'radioman', 'driver', 'loader'], shells: ['ap', 'apcr', 'he'] },
];
// CAT-01: the same rows derived from the single catalog (every catalog kind is
// a registry kind; admission is not decided here). Legacy rows stay the default.
export const LEGACY_POOL_TYPES = TYPES;
export const catalogPoolTypes = (vehicles = CATALOG_VEHICLES) => vehicles.map(v => ({ kind: v.kind, resource: v.resource_name,
  cd: v.native_compact_id, capacity: v.ammo_capacity, roles: v.crew.map(c => c.roles[0]), shells: v.shells.map(s => s.suffix) }));
let ACTIVE_TYPES = TYPES;
let BY_VEHICLE = new Map(TYPES.map(t => [`vehicle:ussr:${t.resource}`, t]));
let SHELLS = TYPES.flatMap(t => t.shells.map(s => `shell:${t.kind}-stock-${s}`));
export function usePoolCatalog(sha256) {
  requireValue(sha256 === CATALOG_SHA256, 'catalog hash differs from this bridge build');
  ACTIVE_TYPES = catalogPoolTypes();
  BY_VEHICLE = new Map(CATALOG_VEHICLES.map(v => [v.vehicle_id, ACTIVE_TYPES.find(t => t.kind === v.kind)]));
  SHELLS = ACTIVE_TYPES.flatMap(t => t.shells.map(s => `shell:${t.kind}-stock-${s}`));
}
export const poolTypes = () => ACTIVE_TYPES;
const SHARED_SKILLS = new Set(['repair', 'fireFighting', 'camouflage', 'brotherhood']);
const ROLE_SKILLS = {
  commander: ['tutor', 'eagleEye', 'expert', 'universalist'],
  driver: ['virtuoso', 'smoothDriving', 'badRoadsKing', 'rammingMaster', 'tidyPerson'],
  gunner: ['gunsmith', 'sniper', 'smoothTurret', 'rancorous'], loader: ['pedant', 'desperado', 'intuition'],
  radioman: ['inventor', 'finder', 'retransmitter', 'lastEffort'],
};
// Public crew rows omit trained type. The exact passport remains checked by
// Python; the structural display permits the union of source combined roles
// for that primary seat, including while its member is in the barracks.
const SOURCE_ROLES = { commander: ['commander', 'gunner', 'radioman', 'loader'],
  radioman: ['radioman'], driver: ['driver'], gunner: ['gunner', 'loader'], loader: ['loader', 'radioman'] };
const exact = (value, keys) => value && typeof value === 'object' && !Array.isArray(value)
  && Object.keys(value).sort().join(',') === [...keys].sort().join(',');
const integer = (v, lo = 0, hi = 2147483647) => Number.isSafeInteger(v) && v >= lo && v <= hi;
const requireValue = (v, reason) => { if (!v) throw new Error(`P04M ${reason}`); };
const researchPolicy = value => exact(value, ['id', 'mode', 'xp', 'credits', 'gold', 'battle_admission', 'initial_research'])
  && value.id === 'test_lab.research.free-credit-xp.v1' && value.mode === 'test_lab' && value.xp === 0 && value.credits === 0
  && value.gold === 'UNSUPPORTED' && value.battle_admission === false
  && value.initial_research === 'retained-source-unlocks-plus-visible-credit-tier1-roots.v1';

export function poolConfiguration(value, battleOwners) {
  requireValue(exact(value, ['version', 'policy_sha256', 'accounts']) && value.version === 1
    && value.policy_sha256 === POOL_POLICY_SHA256 && Array.isArray(value.accounts) && integer(value.accounts.length, 1, 6)
    && value.accounts.every(id => typeof id === 'string' && UUID.test(id) && battleOwners.includes(id))
    && new Set(value.accounts).size === value.accounts.length, 'explicit owner subset/policy');
  return [...value.accounts];
}

function modulesValid(modules, vehicle) {
  return typeof vehicle === 'string' && VEHICLE.test(vehicle) && exact(modules, MODULE_ROLES)
    && MODULE_ROLES.every(role => typeof modules[role] === 'string'
      && new RegExp(`^module:${vehicle.split(':')[1]}:${role}:[A-Za-z0-9_.-]{1,96}$`).test(modules[role]));
}
function inventoryValid(items, id, slots, publicShape) {
  if (!Array.isArray(items) || !integer(items.length, 2, slots)) return false;
  const seen = new Set(), resources = new Set(); let previous = 2;
  return items.every((item, index) => {
    const fields = publicShape ? ['inventoryItemId', 'vehicleDefinitionId', 'displayName', 'health', 'crewAssigned', 'ammunition', 'researchVehicleId', 'modules', 'battle']
      : ['inventory_id', 'vehicle_definition_id', 'health', 'vehicle_xp', 'crew_assigned', 'ammunition_count', 'research_vehicle_id', 'modules', 'battle_admission'];
    if (!exact(item, fields)) return false;
    const identity = publicShape ? item.inventoryItemId : item.inventory_id;
    const vehicle = publicShape ? item.researchVehicleId : item.research_vehicle_id;
    const definition = publicShape ? item.vehicleDefinitionId : item.vehicle_definition_id;
    const count = publicShape ? item.ammunition : item.ammunition_count;
    const crew = publicShape ? item.crewAssigned : item.crew_assigned;
    if (index < 2 ? identity !== `${id}:${['starter-vehicle-v1', 'test-is7-v1'][index]}`
      || vehicle !== ['vehicle:ussr:MS-1', 'vehicle:ussr:IS-7'][index]
      : typeof identity !== 'string' || !identity.startsWith(`${id}:p09e-vehicle:`)) return false;
    if (index >= 2) {
      const suffix = identity.slice(`${id}:p09e-vehicle:`.length);
      if (!/^[1-9][0-9]{0,9}$/.test(suffix) || !integer(Number(suffix), previous + 1)) return false;
      previous = Number(suffix);
    }
    const type = BY_VEHICLE.get(vehicle);
    if (!modulesValid(item.modules, vehicle) || definition !== (index < 2 ? ['vehicle:ms1', 'vehicle:is7'][index] : vehicle)
      || !integer(item.health, 1, 100000) || typeof crew !== 'boolean' || !integer(count, 0, type?.capacity ?? 0)
      || (!type && crew) || (publicShape ? item.battle !== false
        || item.displayName !== (index < 2 ? ['МС-1', 'ИС-7'][index] : vehicle.split(':')[2])
        : item.battle_admission !== false || item.vehicle_xp !== 0)
      || seen.has(identity) || resources.has(vehicle)) return false;
    seen.add(identity); resources.add(vehicle); return true;
  });
}
function grantValid(value, extra = []) {
  return exact(value, ['base_profile_sha256', 'grant_id', 'granted_at_ms', ...extra])
    && typeof value.base_profile_sha256 === 'string' && SHA.test(value.base_profile_sha256)
    && typeof value.grant_id === 'string' && /^[A-Za-z0-9-]{1,64}$/.test(value.grant_id)
    && integer(value.granted_at_ms, 1, Number.MAX_SAFE_INTEGER)
    && extra.every(key => typeof value[key] === 'string' && SHA.test(value[key]));
}

export function nativePoolOverview(profile) {
  const fields = ['profile_version', 'account_id', 'username', 'native_database_id', 'created_at_ms', 'snapshot_revision',
    'resources', 'statistics', 'inventory', 'test_grant', 'crew', 'crew_grant', 'ammunition', 'ammo_grant',
    'ammunition_service', 'ammunition_depot', 'crew_service', 'research', 'pool_service'];
  const id = profile?.account_id, pool = profile?.pool_service, crew = profile?.crew_service, research = profile?.research;
  requireValue(exact(profile, fields) && profile.profile_version === 13 && integer(profile.snapshot_revision, 14)
    && typeof id === 'string' && UUID.test(id) && integer(profile.native_database_id, 1)
    && nicknameField(profile.username)?.display === profile.username && integer(profile.created_at_ms, 1, 8640000000000000)
    && exact(pool, ['schema', 'registry_sha256', 'policy_sha256']) && pool.schema === SCHEMA
    && pool.registry_sha256 === POOL_REGISTRY_SHA256 && pool.policy_sha256 === POOL_POLICY_SHA256,
  'explicit source-bound profile required');
  requireValue(exact(profile.resources, ['credits', 'gold', 'free_xp'])
    && Object.values(profile.resources).every(n => integer(n, 0))
    && exact(profile.statistics, ['battles', 'wins', 'losses', 'draws']) && Object.values(profile.statistics).every(n => n === 0)
    && grantValid(profile.test_grant) && grantValid(profile.crew_grant, ['native_export_sha256'])
    && grantValid(profile.ammo_grant, ['native_export_sha256']), 'retained identity/resources/grants');
  requireValue(exact(research, ['schema', 'policy', 'catalog_sha256', 'garage_slots', 'unlocked_count', 'depot_types'])
    && research.schema === 'p09e-tank-module-research.v1' && researchPolicy(research.policy)
    && research.catalog_sha256 === 'b6baecd204444d1e894253fa6c19c61478993b8ae87c71373633989d3a8ee460'
    && integer(research.garage_slots, 2, 256) && integer(research.unlocked_count, 1, 8192)
    && integer(research.depot_types, 0, 8192) && inventoryValid(profile.inventory, id, research.garage_slots, false),
  'research inventory bounds');
  const crewContract = exact(crew, ['schema', 'policy_sha256', 'battle', 'free_recruitment_left', 'configuration_revision'])
    && Object.hasOwn(CREW_CONTRACTS, crew.schema) ? CREW_CONTRACTS[crew.schema] : null;
  const capacity = crewContract?.capacity ?? 0;
  requireValue(crewContract && crew.policy_sha256 === crewContract.policySha256 && crew.battle === false
    && integer(crew.free_recruitment_left, 0, capacity - 3) && integer(crew.configuration_revision, 2)
    && Array.isArray(profile.crew) && integer(profile.crew.length, 0, capacity - crew.free_recruitment_left), 'pool crew schema');
  const types = new Map(profile.inventory.map(item => [item.inventory_id, BY_VEHICLE.get(item.research_vehicle_id)]));
  const occupied = new Map(), identities = new Set(); let assigned = 0;
  for (const member of profile.crew) {
    const legacy = [`${id}:ms1-commander-v1`, `${id}:ms1-driver-v1`, `${id}:recruit-ms1-driver:3`];
    const match = typeof member?.crew_id === 'string' ? new RegExp(`^${id}:recruit-crew:([1-9][0-9]{0,2})$`).exec(member.crew_id) : null;
    requireValue(exact(member, ['crew_id', 'vehicle_inventory_id', 'role', 'role_level', 'skills'])
      && (legacy.includes(member.crew_id)
        ? member.role === (legacy.indexOf(member.crew_id) === 0 ? 'commander' : 'driver') && member.role_level === 100
        : match && integer(Number(match[1]), 4, capacity - crew.free_recruitment_left) && member.role_level === 50)
      && !identities.has(member.crew_id)
      && Object.hasOwn(ROLE_IDS, member.role) && integer(member.role_level, 50, 100)
      && Array.isArray(member.skills) && member.skills.length <= 1
      && member.skills.every(s => exact(s, ['skill_id', 'level']) && s.level === 0 && member.role_level === 100
        && (SHARED_SKILLS.has(s.skill_id) || SOURCE_ROLES[member.role].some(role => ROLE_SKILLS[role].some(skill => s.skill_id === `${role}_${skill}`))))
      && (member.vehicle_inventory_id === null || types.get(member.vehicle_inventory_id)), 'pool member identity/assignment');
    identities.add(member.crew_id);
    if (member.vehicle_inventory_id !== null) {
      const type = types.get(member.vehicle_inventory_id), roles = occupied.get(member.vehicle_inventory_id) ?? [];
      roles.push(member.role); occupied.set(member.vehicle_inventory_id, roles); assigned++;
      requireValue(roles.filter(r => r === member.role).length <= type.roles.filter(r => r === member.role).length, 'source primary-seat capacity');
    }
  }
  for (const item of profile.inventory) {
    const type = types.get(item.inventory_id), count = occupied.get(item.inventory_id)?.length ?? 0;
    requireValue(item.crew_assigned === Boolean(type && count === type.roles.length), 'crew completeness binding');
  }
  const ammo = profile.ammunition_service;
  requireValue(exact(ammo, ['schema', 'base_profile_sha256', 'catalog_sha256', 'test_grant_sha256', 'financial_status'])
    && ammo.schema === 'p09d-native-ammo.v1' && ammo.financial_status === 'UNSUPPORTED'
    && ['base_profile_sha256', 'catalog_sha256', 'test_grant_sha256'].every(k => typeof ammo[k] === 'string' && SHA.test(ammo[k]))
    && exact(profile.ammunition_depot, SHELLS) && Object.values(profile.ammunition_depot).every(n => integer(n, 0, 1000000))
    && Array.isArray(profile.ammunition) && profile.ammunition.length === [...types.values()].filter(Boolean).length * 3,
  'pool ammunition schema/depot');
  const ammoSeen = new Set(), totals = new Map();
  for (const row of profile.ammunition) {
    const type = types.get(row?.vehicle_inventory_id), unique = `${row?.vehicle_inventory_id}|${row?.shell_definition_id}`;
    requireValue(exact(row, ['vehicle_inventory_id', 'shell_definition_id', 'count']) && type
      && type.shells.some(s => row.shell_definition_id === `shell:${type.kind}-stock-${s}`)
      && integer(row.count, 0, type.capacity) && !ammoSeen.has(unique), 'pool mounted shell identity/count');
    ammoSeen.add(unique); totals.set(row.vehicle_inventory_id, (totals.get(row.vehicle_inventory_id) ?? 0) + row.count);
  }
  requireValue(profile.inventory.every(item => item.ammunition_count === (totals.get(item.inventory_id) ?? 0)), 'pool ammo totals');
  const value = { schemaVersion: 'web-game-read.v1', state: 'ready', ruleset: 'test_lab', snapshotRevision: profile.snapshot_revision,
    asOf: new Date(profile.created_at_ms).toISOString(), account: { accountId: id, nickname: profile.username },
    resources: { credits: profile.resources.credits, gold: profile.resources.gold, freeXP: profile.resources.free_xp },
    statistics: structuredClone(profile.statistics), capabilities: { battle: false, purchases: false, sales: false },
    inventory: profile.inventory.map((item, index) => ({ inventoryItemId: item.inventory_id, vehicleDefinitionId: item.vehicle_definition_id,
      displayName: index < 2 ? ['МС-1', 'ИС-7'][index] : item.research_vehicle_id.split(':')[2], health: item.health,
      crewAssigned: item.crew_assigned, ammunition: item.ammunition_count, researchVehicleId: item.research_vehicle_id,
      modules: structuredClone(item.modules), battle: false })),
    poolService: { version: 1, schema: SCHEMA, policySha256: POOL_POLICY_SHA256, registrySha256: POOL_REGISTRY_SHA256,
      newBattleAdmission: false, garageSlots: research.garage_slots },
    crewService: { version: 8, policySha256: crewContract.policySha256, freeRecruitmentLeft: crew.free_recruitment_left,
      configurationRevision: crew.configuration_revision, tankmen: profile.crew.length, assigned, barracks: profile.crew.length - assigned,
      vehicles: profile.inventory.filter(i => types.get(i.inventory_id)).map(i => ({ inventoryItemId: i.inventory_id,
        assigned: occupied.get(i.inventory_id)?.length ?? 0, capacity: types.get(i.inventory_id).roles.length })), battle: false },
    ammunitionService: { version: 2, funding: 'owned_test_depot', purchases: false } };
  requireValue(isNativePoolOverview(value, id), 'public projection consistency'); return value;
}

export function isNativePoolOverview(value, id) {
  try {
    const p = value?.poolService, c = value?.crewService, contract = crewContractBySha(c?.policySha256);
    if (!exact(value, ['schemaVersion', 'state', 'ruleset', 'snapshotRevision', 'asOf', 'account', 'resources', 'statistics',
      'capabilities', 'inventory', 'poolService', 'crewService', 'ammunitionService'])
      || typeof id !== 'string' || !UUID.test(id) || value.schemaVersion !== 'web-game-read.v1' || value.state !== 'ready' || value.ruleset !== 'test_lab'
      || !integer(value.snapshotRevision, 14) || typeof value.asOf !== 'string' || !Number.isFinite(Date.parse(value.asOf))
      || !exact(value.account, ['accountId', 'nickname']) || value.account.accountId !== id || nicknameField(value.account.nickname)?.display !== value.account.nickname
      || !exact(value.resources, ['credits', 'gold', 'freeXP']) || !Object.values(value.resources).every(n => integer(n))
      || !exact(value.statistics, ['battles', 'wins', 'losses', 'draws']) || Object.values(value.statistics).some(n => n !== 0)
      || !exact(value.capabilities, ['battle', 'purchases', 'sales']) || Object.values(value.capabilities).some(v => v !== false)
      || !exact(p, ['version', 'schema', 'policySha256', 'registrySha256', 'newBattleAdmission', 'garageSlots'])
      || p.version !== 1 || p.schema !== SCHEMA || p.policySha256 !== POOL_POLICY_SHA256 || p.registrySha256 !== POOL_REGISTRY_SHA256
      || p.newBattleAdmission !== false || !integer(p.garageSlots, 2, 256) || !inventoryValid(value.inventory, id, p.garageSlots, true)
      || !exact(c, ['version', 'policySha256', 'freeRecruitmentLeft', 'configurationRevision', 'tankmen', 'assigned', 'barracks', 'vehicles', 'battle'])
      || c.version !== 8 || contract === null || c.battle !== false || !integer(c.freeRecruitmentLeft, 0, contract.capacity - 3)
      || !integer(c.configurationRevision, 2) || !integer(c.tankmen, 0, contract.capacity - c.freeRecruitmentLeft)
      || !integer(c.assigned, 0, c.tankmen) || c.barracks !== c.tankmen - c.assigned
      || !exact(value.ammunitionService, ['version', 'funding', 'purchases']) || value.ammunitionService.version !== 2
      || value.ammunitionService.funding !== 'owned_test_depot' || value.ammunitionService.purchases !== false) return false;
    const vehicles = value.inventory.filter(i => BY_VEHICLE.has(i.researchVehicleId));
    return Array.isArray(c.vehicles) && c.vehicles.length === vehicles.length
      && c.vehicles.every((row, index) => exact(row, ['inventoryItemId', 'assigned', 'capacity'])
        && row.inventoryItemId === vehicles[index].inventoryItemId && row.capacity === BY_VEHICLE.get(vehicles[index].researchVehicleId).roles.length
        && integer(row.assigned, 0, row.capacity) && vehicles[index].crewAssigned === (row.assigned === row.capacity))
      && c.vehicles.reduce((sum, row) => sum + row.assigned, 0) === c.assigned;
  } catch { return false; }
}

export function validatePoolBarracksRecruitmentResponse(value, request, capacity = CREW_CONTRACTS['p04m-pool-crew.v1'].capacity) {
  requireValue(Object.values(CREW_CONTRACTS).some(c => c.capacity === capacity), 'pool crew capacity');
  requireValue(['recruited', 'rejected'].includes(value.status), 'barracks response status');
  if (value.status === 'rejected') {
    requireValue(value.tankman_inventory_id === 0 && value.tankman_descriptor_hex === '', 'rejected barracks allocation'); return;
  }
  const id = value.tankman_inventory_id, [shop, cd, role, cost] = request.layout;
  const type = ACTIVE_TYPES.find(t => t.cd === cd);
  requireValue(integer(request.wire_revision, 1, 2147483646) && shop === 3 && cost === 0 && type
    && type.roles.some(r => ROLE_IDS[r] === role) && integer(id, 4, capacity), 'barracks selected type/primary role');
  const descriptor = barracksPassport(cd, role, id);
  requireValue(descriptor.toString('hex') === value.tankman_descriptor_hex, 'barracks source passport');
  function encodedInt(n) {
    if (n <= 255) return Buffer.from([75, n]);
    const b = Buffer.alloc(n <= 65535 ? 3 : 5); b[0] = n <= 65535 ? 77 : 74;
    if (n <= 65535) b.writeUInt16LE(n, 1); else b.writeInt32LE(n, 1); return b;
  }
  const raw = text => Buffer.from(text, 'latin1');
  const delta = Buffer.concat([raw('\x80\x02}(U\x07prevRev'), encodedInt(request.wire_revision), raw('U\x03rev'), encodedInt(request.wire_revision + 1),
    raw('U\x09inventory}(K\x08}(U\x07vehicle}(K'), Buffer.from([id]), raw('J\xff\xff\xff\xffuU\x09compDescr}(K'),
    Buffer.from([id]), raw('U\x19'), descriptor, raw('uuuU\x05stats}(U\x0cfreeTMenLeftK'), Buffer.from([capacity - id]), raw('uu.')]);
  requireValue(delta.toString('hex') === value.update_hex, 'barracks delta/allocator binding');
}
