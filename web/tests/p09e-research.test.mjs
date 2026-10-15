/** Structural web boundary tests. No native/UI or historical-source acceptance. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { nativeResearchOverview, isNativeResearchOverview } from '../src/p09e-research.mjs';
import { BARRACKS_CREW_POLICY_SHA256 } from '../src/p04k-crew.mjs';

const ID = '11111111-1111-4111-8111-111111111111';
const HASH = 'a'.repeat(64), TIME = 1700000000000;
const modules = vehicle => Object.fromEntries(['chassis', 'engine', 'fuelTank', 'radio', 'turret', 'gun']
  .map(role => [role, `module:${vehicle.split(':')[1]}:${role}:Fixture_${role}`]));
function fixture() {
  const inventory = [['starter-vehicle-v1', 'vehicle:ms1', 'vehicle:ussr:MS-1', 90, true],
    ['test-is7-v1', 'vehicle:is7', 'vehicle:ussr:IS-7', 2150, false],
    ['p09e-vehicle:3', 'vehicle:ussr:BT-2', 'vehicle:ussr:BT-2', 140, false]]
    .map(([suffix, legacy, vehicle, health, crew]) => ({ inventory_id: `${ID}:${suffix}`,
      vehicle_definition_id: legacy, health, vehicle_xp: 0, crew_assigned: crew, ammunition_count: 0,
      research_vehicle_id: vehicle, modules: modules(vehicle), battle_admission: false }));
  const grant = id => ({ grant_id: id, granted_at_ms: TIME, base_profile_sha256: HASH, native_export_sha256: HASH });
  return { profile_version: 13, account_id: ID, username: 'P09E_Test', native_database_id: 900001,
    created_at_ms: TIME, snapshot_revision: 14, resources: { credits: 100000, gold: 0, free_xp: 0 },
    statistics: { battles: 0, wins: 0, losses: 0, draws: 0 }, inventory,
    test_grant: { grant_id: 'test-is7-v1', granted_at_ms: TIME, base_profile_sha256: HASH },
    crew_grant: grant('test-ms1-crew-v1'), ammo_grant: grant('test-ms1-ammo-v1'),
    crew: ['commander', 'driver', 'driver'].map((role, index) => ({
      crew_id: index < 2 ? `${ID}:ms1-${role}-v1` : `${ID}:recruit-ms1-driver:3`,
      vehicle_inventory_id: index < 2 ? inventory[0].inventory_id : null, role, role_level: 100, skills: [],
    })),
    crew_service: { schema: 'p04k-native-barracks-recruitment.v1', policy_sha256: BARRACKS_CREW_POLICY_SHA256,
      free_recruitment_left: 13, configuration_revision: 2, battle: false },
    ammunition: [], ammunition_depot: {}, ammunition_service: { schema: 'p09d-native-ammo.v1' },
    research: { schema: 'p09e-tank-module-research.v1', catalog_sha256: HASH, garage_slots: 3,
      unlocked_count: 51, depot_types: 2, policy: { id: 'test_lab.research.free-credit-xp.v1', mode: 'test_lab',
        xp: 0, credits: 0, gold: 'UNSUPPORTED', battle_admission: false,
        initial_research: 'retained-source-unlocks-plus-visible-credit-tier1-roots.v1' } } };
}

test('profile13 includes actual purchased vehicle and six modules with explicit no-battle zero-cost policy', () => {
  const profile = fixture(), before = structuredClone(profile), value = nativeResearchOverview(profile);
  assert.deepEqual(profile, before);
  assert.equal(value.inventory.length, 3);
  assert.equal(value.inventory[2].vehicleDefinitionId, 'vehicle:ussr:BT-2');
  assert.equal(value.inventory[2].displayName, 'BT-2');
  assert.equal(value.inventory[2].health, 140);
  assert.deepEqual(value.inventory[2].modules, profile.inventory[2].modules);
  assert.equal(value.researchService.unlockedCount, 51);
  assert.equal(value.researchService.xpCost, 0);
  assert.equal(value.researchService.creditCost, 0);
  assert.equal(value.researchService.goldPurchases, false);
  assert.equal(value.capabilities.battle, false);
  assert.equal(isNativeResearchOverview(value, ID), true);
  value.inventory[2].modules.gun = 'changed';
  assert.deepEqual(profile, before);
});

test('source-projected changed turret health is displayed without changing accepted base validation', () => {
  const profile = fixture();
  profile.inventory[0].health = 100;
  profile.inventory[0].modules.turret = 'module:ussr:turret:T-18_mod';
  const value = nativeResearchOverview(profile);
  assert.equal(value.inventory[0].health, 100);
  assert.equal(isNativeResearchOverview(value, ID), true);
});

test('profile rejects malformed policy, identity, module role/nation, health, counts and manufactured readiness', () => {
  const changes = [p => { p.research.policy.credits = 1; }, p => { p.research.policy.gold = 0; },
    p => { p.research.policy.battle_admission = true; }, p => { p.research.catalog_sha256 = 'fake'; },
    p => { p.research.catalog_sha256 = [HASH]; }, p => { p.account_id = [ID]; },
    p => { p.research.extra = true; }, p => { p.research.unlocked_count = 8193; },
    p => { p.research.unlocked_count = true; },
    p => { p.research.garage_slots = 256; p.inventory = Array(257).fill(p.inventory[0]); },
    p => { p.research.depot_types = -1; }, p => { p.research.garage_slots = 2; },
    p => { p.inventory[2].inventory_id = '22222222-2222-4222-8222-222222222222:p09e-vehicle:3'; },
    p => { p.inventory[2].inventory_id = `${ID}:p09e-vehicle:03`; },
    p => { p.inventory[2].modules.gun = 'module:germany:gun:Fixture'; },
    p => { p.inventory[2].modules.engine = 'module:ussr:radio:Fixture'; },
    p => { delete p.inventory[2].modules.fuelTank; }, p => { p.inventory[2].health = NaN; },
    p => { p.inventory[2].health = 0; }, p => { p.inventory[2].crew_assigned = true; },
    p => { p.inventory[2].ammunition_count = 1; }, p => { p.inventory[2].battle_admission = true; },
    p => { p.inventory[2].mass_grams = 1; }, p => { p.inventory[2].vehicle_definition_id = 'vehicle:ms1'; },
    p => { p.inventory[2].research_vehicle_id = 'vehicle:ussr:MS-1'; },
    p => { p.inventory[1].research_vehicle_id = 'vehicle:ussr:BT-2'; },
    p => { p.crew[0].role_level = 50; }, p => { p.profile_version = 12; }];
  for (const change of changes) {
    const profile = fixture(); change(profile); assert.throws(() => nativeResearchOverview(profile));
  }
});

test('overview validator fails closed for foreign account, extra fields, inconsistent service and duplicate vehicles', () => {
  const value = nativeResearchOverview(fixture());
  assert.equal(isNativeResearchOverview(value, '22222222-2222-4222-8222-222222222222'), false);
  for (const change of [v => { v.researchService.battle = true; }, v => { v.researchService.xpCost = 1; },
    v => { v.researchService.extra = true; }, v => { v.inventory[2].battle = true; },
    v => { v.researchService.catalogSha256 = [HASH]; },
    v => { v.inventory[2].health = Infinity; }, v => { v.inventory[2].modules.gun = false; },
    v => { v.inventory[2].displayName = '<script>'; }, v => { v.researchService.garageSlots = 4; v.inventory.push(structuredClone(v.inventory[2])); },
    v => { v.account.accountId = 'other'; }, v => { v.arbitrary = true; }]) {
    const changed = structuredClone(value); change(changed); assert.equal(isNativeResearchOverview(changed, ID), false);
  }
  for (const invalid of [null, undefined, 1, [], {}, { researchService: null }]) {
    assert.equal(isNativeResearchOverview(invalid, ID), false);
  }
});
