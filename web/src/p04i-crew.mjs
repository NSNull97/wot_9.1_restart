/** Profile10: source-bound seats, independent training and bounded free recruitment. */
import { nativeAmmoOverview, isNativeAmmoOverview } from './p09d-ammo.mjs';
import { PROGRESSION_CREW_POLICY_SHA256 } from './p04d-crew.mjs';

const exact = (v, keys) => v && typeof v === 'object' && !Array.isArray(v)
  && Object.keys(v).sort().join(',') === [...keys].sort().join(',');
const integer = (v, low, high = 2147483647) => Number.isSafeInteger(v) && v >= low && v <= high;
const requireValue = (v, message) => { if (!v) throw new Error(message); };
const POLICY = 'test_lab.ms1-is7-crew-progression.v1';
const FIELDS = ['version', 'policy', 'freeRecruitmentLeft', 'configurationRevision', 'tankmen',
  'assigned', 'barracks', 'ms1Assigned', 'is7Assigned', 'battle'];
const CAPACITY = [{ commander: 1, driver: 1 }, { commander: 1, gunner: 1, driver: 1, loader: 2 }];

const LEARNABLE = new Set(["repair", "fireFighting", "camouflage", "brotherhood", "commander_tutor", "commander_eagleEye", "commander_expert", "commander_universalist", "driver_virtuoso", "driver_smoothDriving", "driver_badRoadsKing", "driver_rammingMaster", "driver_tidyPerson", "gunner_gunsmith", "gunner_sniper", "gunner_smoothTurret", "gunner_rancorous", "loader_pedant", "loader_desperado", "loader_intuition", "radioman_inventor", "radioman_finder", "radioman_retransmitter", "radioman_lastEffort"]);
function validSkills(skills) {
  return Array.isArray(skills) && skills.length <= LEARNABLE.size && new Set(skills.map(s => s?.skill_id)).size === skills.length
    && skills.every((s, i) => exact(s, ['skill_id', 'level']) && LEARNABLE.has(s.skill_id)
      && integer(s.level, 0, 100) && (i === skills.length - 1 || s.level === 100));
}

export function nativeProgressionCrewOverview(profile) {
  const c = profile.crew_service, members = profile.crew, id = profile.account_id;
  requireValue(profile.profile_version === 10 && integer(profile.snapshot_revision, 10)
    && exact(c, ['schema', 'policy_sha256', 'free_recruitment_left', 'configuration_revision', 'battle'])
    && c.schema === 'p04i-native-crew-progression.v1' && c.policy_sha256 === PROGRESSION_CREW_POLICY_SHA256
    && c.battle === false && integer(c.free_recruitment_left, 0, 13) && integer(c.configuration_revision, 2)
    && Array.isArray(members) && integer(members.length, 3, 16)
    && c.free_recruitment_left === 16 - members.length, 'Roster recruitment profile required');
  const vehicles = [`${id}:starter-vehicle-v1`, `${id}:test-is7-v1`], occupied = [{}, {}], counts = [0, 0];
  members.forEach((m, i) => {
    const oldRole = i === 0 ? 'commander' : 'driver', vehicle = vehicles.indexOf(m.vehicle_inventory_id);
    const expectedId = i < 2 ? `${id}:ms1-${oldRole}-v1` : i === 2 ? `${id}:recruit-ms1-driver:3` : `${id}:recruit-crew:${i + 1}`;
    requireValue(exact(m, ['crew_id', 'vehicle_inventory_id', 'role', 'role_level', 'skills'])
      && m.crew_id === expectedId && (vehicle >= 0 || m.vehicle_inventory_id === null)
      && (i < 3 ? m.role === oldRole : ['commander', 'gunner', 'driver', 'loader'].includes(m.role))
      && m.role_level === (i < 3 ? 100 : 50) && validSkills(m.skills) && (m.skills.length === 0 || m.role_level === 100),
    'Roster member identity/training/assignment mismatch');
    if (vehicle >= 0) {
      const n = (occupied[vehicle][m.role] ?? 0) + 1;
      requireValue(n <= (CAPACITY[vehicle][m.role] ?? 0), 'Occupied role exceeds source vehicle seats');
      occupied[vehicle][m.role] = n; counts[vehicle]++;
    }
  });
  const complete = [counts[0] === 2, counts[1] === 5];
  requireValue(profile.inventory?.length === 2 && profile.inventory.every((v, i) =>
    v.inventory_id === vehicles[i] && v.crew_assigned === complete[i]), 'Both vehicle readiness bindings required');
  const base = structuredClone(profile); delete base.crew_service;
  base.profile_version = 5; base.inventory[0].crew_assigned = true; base.inventory[1].crew_assigned = false;
  base.crew = ['commander', 'driver'].map(role => ({ crew_id: `${id}:ms1-${role}-v1`,
    vehicle_inventory_id: vehicles[0], role, role_level: 100, skills: [] }));
  const value = nativeAmmoOverview(base);
  value.inventory.forEach((v, i) => { v.crewAssigned = complete[i]; });
  value.crewService = { version: 5, policy: POLICY, freeRecruitmentLeft: c.free_recruitment_left,
    configurationRevision: c.configuration_revision, tankmen: members.length, assigned: counts[0] + counts[1],
    barracks: members.length - counts[0] - counts[1], ms1Assigned: counts[0], is7Assigned: counts[1], battle: false };
  return value;
}

export function isNativeProgressionCrewOverview(value, id) {
  const c = value?.crewService;
  if (!integer(value?.snapshotRevision, 10) || !exact(c, FIELDS) || c.version !== 5 || c.policy !== POLICY
    || !integer(c.tankmen, 3, 16) || c.freeRecruitmentLeft !== 16 - c.tankmen || !integer(c.configurationRevision, 2)
    || !integer(c.ms1Assigned, 0, 2) || !integer(c.is7Assigned, 0, 5) || !integer(c.assigned, 0, Math.min(7, c.tankmen))
    || c.assigned !== c.ms1Assigned + c.is7Assigned || c.barracks !== c.tankmen - c.assigned || c.battle !== false
    || value.inventory?.length !== 2 || value.inventory[0].crewAssigned !== (c.ms1Assigned === 2)
    || value.inventory[1].crewAssigned !== (c.is7Assigned === 5)) return false;
  const base = structuredClone(value); delete base.crewService;
  base.inventory[0].crewAssigned = true; base.inventory[1].crewAssigned = false;
  return isNativeAmmoOverview(base, id);
}
