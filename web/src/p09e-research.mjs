/** Read-only profile13 research projection over accepted P04K; authority remains in the Python store. */
import { nativeBarracksCrewOverview, isNativeBarracksCrewOverview } from './p04k-crew.mjs';
import { RESEARCH_POLICY_SHA256 } from './p04d-crew.mjs';

export { RESEARCH_POLICY_SHA256 };
const PROFILE_VERSION = 13;
const BASE_PROFILE_VERSION = 12;
const POLICY = 'test_lab.research.free-credit-xp.v1';
const POLICY_FIELDS = ['id', 'mode', 'xp', 'credits', 'gold', 'battle_admission', 'initial_research'];
const ROLES = ['chassis', 'engine', 'fuelTank', 'radio', 'turret', 'gun'];
const NATION = '(?:ussr|germany|usa|france|uk|china|japan)';
const VEHICLE = new RegExp(`^vehicle:${NATION}:[A-Za-z0-9_.-]{1,96}$`);
const SHA = /^[0-9a-f]{64}$/;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const integer = (value, low = 0, high = 2147483647) => Number.isSafeInteger(value) && value >= low && value <= high;
const exact = (value, keys) => value && typeof value === 'object' && !Array.isArray(value)
  && Object.keys(value).sort().join(',') === [...keys].sort().join(',');
const requireValue = (value, message) => { if (!value) throw new Error(message); };
const SERVICE_FIELDS = ['version', 'policy', 'catalogSha256', 'garageSlots', 'unlockedCount',
  'depotTypes', 'xpCost', 'creditCost', 'goldPurchases', 'battle'];
const PUBLIC_ITEM_FIELDS = ['inventoryItemId', 'vehicleDefinitionId', 'displayName', 'health',
  'crewAssigned', 'ammunition', 'researchVehicleId', 'modules', 'battle'];
const INPUT_ITEM_FIELDS = ['inventory_id', 'vehicle_definition_id', 'health', 'vehicle_xp',
  'crew_assigned', 'ammunition_count', 'research_vehicle_id', 'modules', 'battle_admission'];

function modulesValid(modules, vehicle) {
  if (!exact(modules, ROLES) || typeof vehicle !== 'string' || !VEHICLE.test(vehicle)) return false;
  const nation = vehicle.split(':')[1];
  return ROLES.every(role => typeof modules[role] === 'string'
    && new RegExp(`^module:${nation}:${role}:[A-Za-z0-9_.-]{1,96}$`).test(modules[role]));
}

function baselineIdentity(id, index) {
  return index === 0 ? `${id}:starter-vehicle-v1` : `${id}:test-is7-v1`;
}

function identityValid(item, index, id, field) {
  if (index < 2) return item[field] === baselineIdentity(id, index);
  if (typeof item[field] !== 'string' || !item[field].startsWith(`${id}:p09e-vehicle:`)) return false;
  const tail = item[field].slice(`${id}:p09e-vehicle:`.length);
  return /^[1-9][0-9]{0,9}$/.test(tail) && integer(Number(tail), 3);
}

function publicItemsValid(items, id, slots) {
  if (!Array.isArray(items) || !integer(items.length, 2, 256) || items.length > slots) return false;
  const inventoryIds = new Set(), vehicleIds = new Set();
  return items.every((item, index) => {
    if (!exact(item, PUBLIC_ITEM_FIELDS) || !identityValid(item, index, id, 'inventoryItemId')
      || !modulesValid(item.modules, item.researchVehicleId) || item.battle !== false
      || !integer(item.health, 1, 100000) || typeof item.crewAssigned !== 'boolean'
      || !integer(item.ammunition, 0, index < 2 ? [96, 30][index] : 0)
      || (index >= 2 && item.crewAssigned !== false)
      || item.vehicleDefinitionId !== (index < 2 ? ['vehicle:ms1', 'vehicle:is7'][index] : item.researchVehicleId)
      || item.displayName !== (index < 2 ? ['МС-1', 'ИС-7'][index] : item.researchVehicleId.split(':')[2])
      || (index < 2 && item.researchVehicleId !== ['vehicle:ussr:MS-1', 'vehicle:ussr:IS-7'][index])
      || inventoryIds.has(item.inventoryItemId) || vehicleIds.has(item.researchVehicleId)) return false;
    inventoryIds.add(item.inventoryItemId); vehicleIds.add(item.researchVehicleId);
    return true;
  });
}

function stripPublicResearch(value) {
  const base = structuredClone(value);
  delete base.researchService;
  base.inventory = base.inventory.slice(0, 2).map((item, index) => {
    delete item.researchVehicleId; delete item.modules; delete item.battle;
    // Validate retained accepted identity/ammo/crew independently of changed mounts.
    item.health = [90, 2150][index];
    return item;
  });
  return base;
}

export function nativeResearchOverview(profile) {
  const id = profile?.account_id, research = profile?.research;
  requireValue(typeof id === 'string' && UUID.test(id) && profile?.profile_version === PROFILE_VERSION && integer(profile.snapshot_revision, PROFILE_VERSION)
    && exact(research, ['schema', 'policy', 'catalog_sha256', 'garage_slots', 'unlocked_count', 'depot_types'])
    && research.schema === 'p09e-tank-module-research.v1' && typeof research.catalog_sha256 === 'string' && SHA.test(research.catalog_sha256)
    && exact(research.policy, POLICY_FIELDS) && research.policy.id === POLICY
    && research.policy.mode === 'test_lab' && research.policy.xp === 0 && research.policy.credits === 0
    && research.policy.gold === 'UNSUPPORTED' && research.policy.battle_admission === false
    && research.policy.initial_research === 'retained-source-unlocks-plus-visible-credit-tier1-roots.v1'
    && integer(research.garage_slots, 2, 256) && integer(research.unlocked_count, 1, 8192)
    && integer(research.depot_types, 0, 8192) && Array.isArray(profile.inventory)
    && integer(profile.inventory.length, 2, research.garage_slots), 'Bounded authoritative research profile required');
  for (const item of profile.inventory) {
    requireValue(exact(item, INPUT_ITEM_FIELDS) && item.vehicle_xp === 0
      && item.battle_admission === false && modulesValid(item.modules, item.research_vehicle_id),
    'Research inventory schema/battle boundary');
  }
  const base = structuredClone(profile);
  delete base.research;
  base.profile_version = BASE_PROFILE_VERSION;
  base.inventory = base.inventory.slice(0, 2).map((item, index) => {
    delete item.research_vehicle_id; delete item.modules; delete item.battle_admission;
    item.health = [90, 2150][index];
    return item;
  });
  const overview = nativeBarracksCrewOverview(base);
  overview.inventory = profile.inventory.map((item, index) => ({
    inventoryItemId: item.inventory_id, vehicleDefinitionId: item.vehicle_definition_id,
    displayName: index < 2 ? ['МС-1', 'ИС-7'][index] : String(item.research_vehicle_id).split(':')[2],
    health: item.health, crewAssigned: item.crew_assigned, ammunition: item.ammunition_count,
    researchVehicleId: item.research_vehicle_id, modules: structuredClone(item.modules), battle: false,
  }));
  overview.researchService = { version: 1, policy: POLICY, catalogSha256: research.catalog_sha256,
    garageSlots: research.garage_slots, unlockedCount: research.unlocked_count, depotTypes: research.depot_types,
    xpCost: 0, creditCost: 0, goldPurchases: false, battle: false };
  requireValue(isNativeResearchOverview(overview, id), 'Invalid research overview identity/state');
  return overview;
}

export function isNativeResearchOverview(value, id) {
  try {
    const service = value?.researchService;
    if (typeof id !== 'string' || !UUID.test(id) || !integer(value?.snapshotRevision, PROFILE_VERSION) || !exact(service, SERVICE_FIELDS)
      || service.version !== 1 || service.policy !== POLICY || typeof service.catalogSha256 !== 'string' || !SHA.test(service.catalogSha256)
      || !integer(service.garageSlots, 2, 256) || !integer(service.unlockedCount, 1, 8192)
      || !integer(service.depotTypes, 0, 8192) || service.xpCost !== 0 || service.creditCost !== 0
      || service.goldPurchases !== false || service.battle !== false
      || !publicItemsValid(value.inventory, id, service.garageSlots)) return false;
    return isNativeBarracksCrewOverview(stripPublicResearch(value), id);
  } catch { return false; }
}
