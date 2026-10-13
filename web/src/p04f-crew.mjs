/** Read-only projection of the source-bound mutable crew profile. */
import { nativeAmmoOverview, isNativeAmmoOverview } from './p09d-ammo.mjs';
import { TRANSFER_POLICY_SHA256 } from './p04d-crew.mjs';

const exact = (v, keys) => v && typeof v === 'object' && !Array.isArray(v)
  && Object.keys(v).sort().join(',') === [...keys].sort().join(',');
const integer = (v, low, high = 2147483647) => Number.isSafeInteger(v) && v >= low && v <= high;
const requireValue = (v, message) => { if (!v) throw new Error(message); };
const POLICY = 'test_lab.ms1-crew-transfer.v1';

export function nativeCrewTransferOverview(profile) {
  const c = profile.crew_service, members = profile.crew, id = profile.account_id;
  requireValue(profile.profile_version === 7 && integer(profile.snapshot_revision, 7)
    && exact(c, ['schema', 'policy_sha256', 'free_recruitment_left', 'configuration_revision', 'battle'])
    && c.schema === 'p04f-native-crew-transfer.v1' && c.policy_sha256 === TRANSFER_POLICY_SHA256 && c.battle === false
    && integer(c.free_recruitment_left, 0, 1) && integer(c.configuration_revision, 2 - c.free_recruitment_left)
    && Array.isArray(members) && members.length === 3 - c.free_recruitment_left, 'Crew transfer profile required');
  const vehicle = `${id}:starter-vehicle-v1`, assignedRoles = new Set();
  members.forEach((m, i) => {
    const role = i === 0 ? 'commander' : 'driver';
    requireValue(exact(m, ['crew_id', 'vehicle_inventory_id', 'role', 'role_level', 'skills'])
      && m.crew_id === (i < 2 ? `${id}:ms1-${role}-v1` : `${id}:recruit-ms1-driver:3`)
      && (m.vehicle_inventory_id === vehicle || m.vehicle_inventory_id === null)
      && m.role === role && m.role_level === 100 && Array.isArray(m.skills) && m.skills.length === 0,
    'Crew transfer member binding');
    if (m.vehicle_inventory_id === vehicle) {
      requireValue(!assignedRoles.has(role), 'Duplicate occupied crew seat'); assignedRoles.add(role);
    }
  });
  const complete = assignedRoles.size === 2;
  requireValue(profile.inventory?.[0]?.crew_assigned === complete, 'Crew readiness mismatch');
  // Validate the unchanged predecessor fields without persisting this adapter view.
  const base = structuredClone(profile); delete base.crew_service;
  base.profile_version = 5; base.inventory[0].crew_assigned = true;
  base.crew = ['commander', 'driver'].map(role => ({ crew_id: `${id}:ms1-${role}-v1`,
    vehicle_inventory_id: vehicle, role, role_level: 100, skills: [] }));
  const value = nativeAmmoOverview(base); value.inventory[0].crewAssigned = complete;
  value.crewService = { version: 2, policy: POLICY, freeRecruitmentLeft: c.free_recruitment_left,
    configurationRevision: c.configuration_revision, tankmen: members.length,
    assigned: assignedRoles.size, barracks: members.length - assignedRoles.size, battle: false };
  return value;
}

export function isNativeCrewTransferOverview(value, id) {
  const c = value?.crewService;
  if (!integer(value?.snapshotRevision, 7)
    || !exact(c, ['version', 'policy', 'freeRecruitmentLeft', 'configurationRevision', 'tankmen', 'assigned', 'barracks', 'battle'])
    || c.version !== 2 || c.policy !== POLICY || c.battle !== false
    || !integer(c.freeRecruitmentLeft, 0, 1) || !integer(c.configurationRevision, 2 - c.freeRecruitmentLeft)
    || c.tankmen !== 3 - c.freeRecruitmentLeft || !integer(c.assigned, 0, 2)
    || c.barracks !== c.tankmen - c.assigned || value.inventory?.[0]?.crewAssigned !== (c.assigned === 2)) return false;
  const base = structuredClone(value); delete base.crewService; base.inventory[0].crewAssigned = true;
  return isNativeAmmoOverview(base, id);
}
