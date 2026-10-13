/** Read-only profile8 projection: original training is separate from assignment. */
import { nativeAmmoOverview, isNativeAmmoOverview } from './p09d-ammo.mjs';
import { CROSS_CREW_POLICY_SHA256 } from './p04d-crew.mjs';

const exact = (v, keys) => v && typeof v === 'object' && !Array.isArray(v)
  && Object.keys(v).sort().join(',') === [...keys].sort().join(',');
const integer = (v, low, high = 2147483647) => Number.isSafeInteger(v) && v >= low && v <= high;
const requireValue = (v, message) => { if (!v) throw new Error(message); };
const POLICY = 'test_lab.ms1-is7-crew-transfer.v1';
const FIELDS = ['version', 'policy', 'freeRecruitmentLeft', 'configurationRevision', 'tankmen',
  'assigned', 'barracks', 'ms1Assigned', 'is7Assigned', 'battle'];

export function nativeCrossVehicleCrewOverview(profile) {
  const c = profile.crew_service, members = profile.crew, id = profile.account_id;
  requireValue(profile.profile_version === 8 && integer(profile.snapshot_revision, 8)
    && exact(c, ['schema', 'policy_sha256', 'free_recruitment_left', 'configuration_revision', 'battle'])
    && c.schema === 'p04g-native-cross-vehicle-crew.v1' && c.policy_sha256 === CROSS_CREW_POLICY_SHA256
    && c.battle === false && c.free_recruitment_left === 0 && integer(c.configuration_revision, 2)
    && Array.isArray(members) && members.length === 3, 'Cross-vehicle crew profile required');
  const vehicles = [`${id}:starter-vehicle-v1`, `${id}:test-is7-v1`], occupied = [new Set(), new Set()];
  members.forEach((m, i) => {
    const role = i === 0 ? 'commander' : 'driver', vehicle = vehicles.indexOf(m.vehicle_inventory_id);
    requireValue(exact(m, ['crew_id', 'vehicle_inventory_id', 'role', 'role_level', 'skills'])
      && m.crew_id === (i < 2 ? `${id}:ms1-${role}-v1` : `${id}:recruit-ms1-driver:3`)
      && (vehicle >= 0 || m.vehicle_inventory_id === null) && m.role === role
      && m.role_level === 100 && Array.isArray(m.skills) && m.skills.length === 0,
    'Cross-vehicle member identity/training/assignment mismatch');
    if (vehicle >= 0) {
      requireValue(!occupied[vehicle].has(role), 'Duplicate occupied role/seat'); occupied[vehicle].add(role);
    }
  });
  const counts = occupied.map(v => v.size), complete = [counts[0] === 2, false];
  requireValue(profile.inventory?.length === 2 && profile.inventory.every((v, i) =>
    v.inventory_id === vehicles[i] && v.crew_assigned === complete[i]), 'Both vehicle readiness bindings required');
  const base = structuredClone(profile); delete base.crew_service;
  base.profile_version = 5; base.inventory[0].crew_assigned = true; base.inventory[1].crew_assigned = false;
  base.crew = ['commander', 'driver'].map(role => ({ crew_id: `${id}:ms1-${role}-v1`,
    vehicle_inventory_id: vehicles[0], role, role_level: 100, skills: [] }));
  const value = nativeAmmoOverview(base);
  value.inventory.forEach((v, i) => { v.crewAssigned = complete[i]; });
  value.crewService = { version: 3, policy: POLICY, freeRecruitmentLeft: 0,
    configurationRevision: c.configuration_revision, tankmen: 3, assigned: counts[0] + counts[1],
    barracks: 3 - counts[0] - counts[1], ms1Assigned: counts[0], is7Assigned: counts[1], battle: false };
  return value;
}

export function isNativeCrossVehicleCrewOverview(value, id) {
  const c = value?.crewService;
  if (!integer(value?.snapshotRevision, 8) || !exact(c, FIELDS) || c.version !== 3 || c.policy !== POLICY
    || c.freeRecruitmentLeft !== 0 || !integer(c.configurationRevision, 2) || c.tankmen !== 3
    || !integer(c.ms1Assigned, 0, 2) || !integer(c.is7Assigned, 0, 2) || !integer(c.assigned, 0, 3)
    || c.assigned !== c.ms1Assigned + c.is7Assigned || c.barracks !== 3 - c.assigned || c.battle !== false
    || value.inventory?.length !== 2 || value.inventory[0].crewAssigned !== (c.ms1Assigned === 2)
    || value.inventory[1].crewAssigned !== false) return false;
  const base = structuredClone(value); delete base.crewService; base.inventory[0].crewAssigned = true;
  return isNativeAmmoOverview(base, id);
}
