/** Actual isolated Python profile/303 vectors plus closed opt-in projections. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { nativePoolOverview, isNativePoolOverview, poolConfiguration, POOL_POLICY_SHA256,
  validatePoolBarracksRecruitmentResponse, nativePoolRequestTimeout, POOL_WORKER_TIMEOUT_MS, POOL_MUTATION_TIMEOUT_MS, LEGACY_REQUEST_TIMEOUT_MS,
  poolCrewContract, POOL_CREW_POLICY_SHA256, POOL_CREW_V2_POLICY_SHA256 } from '../src/p04m-pool.mjs';
import { nativeResearchOverview, isNativeResearchOverview } from '../src/p09e-research.mjs';
import { validateBarracksRecruitmentResponse } from '../src/p04k-crew.mjs';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const FIXTURES = resolve(process.env.P04M_NATIVE_FIXTURES || join(ROOT, 'local/evidence/20261016-p04m-writer01/native-fixtures03'));
const OWNER = '11111111-1111-4111-8111-111111111111', OTHER = '22222222-2222-4222-8222-222222222222';
const digest = b => createHash('sha256').update(b).digest('hex');
const skip = !existsSync(join(FIXTURES, 't26-ap160/profile-input.json')) ? 'NOT_RUN: actual P04M SQLite writer fixtures required' : false;
function profile(name) {
  const directory = join(FIXTURES, name), receipt = JSON.parse(readFileSync(join(directory, 'writer-receipt.json')));
  assert.equal(receipt.classification, 'VERIFIED_ISOLATED_SQLITE_WRITER');
  for (const file of ['profile-input.json', 'actual-snapshot.json', 'writer-vectors.json']) {
    const bytes = readFileSync(join(directory, file)), pin = receipt.files.find(p => p.file === file);
    assert.ok(bytes.length <= 32768); assert.equal(bytes.length, pin.bytes); assert.equal(digest(bytes), pin.sha256);
  }
  return JSON.parse(readFileSync(join(directory, 'profile-input.json')));
}

test('P04M configuration is an explicit unique subset of battle owners', () => {
  const input = { version: 1, policy_sha256: POOL_POLICY_SHA256, accounts: [OTHER] };
  assert.deepEqual(poolConfiguration(input, [OWNER, OTHER]), [OTHER]);
  const copy = poolConfiguration(input, [OWNER, OTHER]); copy.pop(); assert.equal(input.accounts.length, 1);
  for (const change of [{ version: 2 }, { policy_sha256: '0'.repeat(64) }, { accounts: [] },
    { accounts: [OTHER, OTHER] }, { accounts: ['invalid'] }, { extra: true }]) {
    assert.throws(() => poolConfiguration({ ...input, ...change }, [OWNER, OTHER]));
  }
  assert.throws(() => poolConfiguration(input, [OWNER]));
});

test('P04M authenticated selected request deadline contains the actual worker budget and keeps legacy/read routes bounded', () => {
  assert.equal(POOL_WORKER_TIMEOUT_MS, 7000); assert.equal(POOL_MUTATION_TIMEOUT_MS, 9000);
  assert.ok(POOL_MUTATION_TIMEOUT_MS >= POOL_WORKER_TIMEOUT_MS + 2000);
  for (const path of ['/internal/native/login', '/internal/native/profile', '/internal/native/ammo', '/internal/native/crew', '/internal/native/crew-recruit-barracks',
    '/internal/native/crew-dismiss', '/internal/native/crew-learn', '/internal/native/crew-transfer',
    '/internal/native/research', '/internal/native/battle', '/internal/native/battle-results']) {
    assert.equal(nativePoolRequestTimeout('POST', path, OWNER, [OWNER]), POOL_MUTATION_TIMEOUT_MS);
    assert.equal(nativePoolRequestTimeout('POST', path, OTHER, [OWNER]), LEGACY_REQUEST_TIMEOUT_MS);
    assert.equal(nativePoolRequestTimeout('GET', path, OWNER, [OWNER]), LEGACY_REQUEST_TIMEOUT_MS);
  }
  for (const path of [`/internal/accounts/${OWNER}/overview`, '/internal/native/login?extra=1',
    '/internal/native/crew-recruit-barracks/extra', '/internal/native/crew?owner=1', '/unknown']) {
    assert.equal(nativePoolRequestTimeout('POST', path, OWNER, [OWNER]), 4500);
  }
});

test('P04M actual T26 AP160/full primary crew projects without weakening P09E', { skip }, () => {
  const p = profile('t26-ap160'), value = nativePoolOverview(p), tank = value.inventory.find(i => i.researchVehicleId === 'vehicle:ussr:T-26');
  assert.equal(tank.ammunition, 160); assert.equal(tank.crewAssigned, true); assert.equal(tank.battle, false);
  assert.equal(value.poolService.newBattleAdmission, false); assert.equal(isNativePoolOverview(value, p.account_id), true);
  assert.equal(isNativeResearchOverview(value, p.account_id), false); assert.throws(() => nativeResearchOverview(p));
  assert.equal(value.crewService.tankmen, p.crew.length);
  const frozen = JSON.stringify(p); value.inventory[2].modules.gun = 'changed'; assert.equal(JSON.stringify(p), frozen);
});

test('P04M input binds schema, owner, mounted shells, total capacity and primary seats', { skip }, () => {
  const p = profile('t26-ap160');
  const changes = [v => { v.pool_service.policy_sha256 = '0'.repeat(64); }, v => { v.pool_service.registry_sha256 = '0'.repeat(64); },
    v => { v.crew_service.schema = 'p04k-native-barracks-recruitment.v1'; }, v => { v.account_id = OTHER; },
    v => { v.inventory[2].battle_admission = true; }, v => { v.inventory[2].ammunition_count = 161; },
    v => { v.ammunition[0].count = 159; }, v => { v.ammunition[1].shell_definition_id = v.ammunition[0].shell_definition_id; },
    v => { v.ammunition[0].shell_definition_id = 'shell:t34-stock-ap'; }, v => { delete v.ammunition_depot['shell:t34-stock-he']; },
    v => { v.ammunition_depot.unknown = 0; }, v => { v.crew[4].role = 'radioman'; }, v => { v.crew[1].role = 'gunner'; }, v => { v.crew[1].skills = [{ skill_id: 'gunner_gunsmith', level: 0 }]; }, v => { v.crew[4].crew_id = `${v.account_id}:recruit-crew:16`; },
    v => { v.crew[4].vehicle_inventory_id = `${OTHER}:starter-vehicle-v1`; }, v => { v.crew[4].crew_id = v.crew[3].crew_id; },
    v => { v.inventory[2].crew_assigned = false; }, v => { v.extra = true; }];
  for (const change of changes) { const value = structuredClone(p); change(value); assert.throws(() => nativePoolOverview(value)); }
});

test('P04M public projection denies forged admission, stale capacities and identity changes', { skip }, () => {
  const p = profile('t26-ap160'), original = nativePoolOverview(p);
  const changes = [v => { v.poolService.newBattleAdmission = true; }, v => { v.capabilities.battle = true; },
    v => { v.inventory[2].ammunition = 161; }, v => { v.crewService.vehicles[2].capacity = 4; },
    v => { v.crewService.vehicles[2].assigned = 2; }, v => { v.crewService.assigned--; },
    v => { v.account.accountId = OTHER; }, v => { v.poolService.registrySha256 = '0'.repeat(64); },
    v => { v.inventory[2].displayName = '<script>'; }, v => { v.poolService.extra = true; }];
  for (const change of changes) { const value = structuredClone(original); change(value); assert.equal(isNativePoolOverview(value, p.account_id), false); }
  for (const value of [null, undefined, 1, [], {}]) assert.equal(isNativePoolOverview(value, p.account_id), false);
});

test('P04M actual T3485 uses all five primary roles including radioman', { skip }, () => {
  const p = profile('t3485-full-crew'), value = nativePoolOverview(p);
  const tank = value.inventory.find(i => i.researchVehicleId === 'vehicle:ussr:T-34-85');
  assert.equal(tank.crewAssigned, true); assert.equal(tank.ammunition, 0);
  assert.equal(p.crew.filter(m => m.vehicle_inventory_id === tank.inventoryItemId).length, 5);
  assert.equal(isNativePoolOverview(value, p.account_id), true);
});

test('P04M actual T34 type-zero/radioman 303 result matches source passport and immutable delta', {
  skip: skip || (!existsSync(join(FIXTURES, 't34-radioman-barracks/writer-vectors.json')) ? 'NOT_RUN: actual T34 radioman vector required' : false),
}, () => {
  const p = profile('t34-radioman-barracks'), value = nativePoolOverview(p);
  assert.equal(isNativePoolOverview(value, p.account_id), true);
  const rows = JSON.parse(readFileSync(join(FIXTURES, 't34-radioman-barracks/writer-vectors.json')));
  const { request, response } = rows.find(r => r.operation === 'recruit_barracks');
  assert.deepEqual(request.layout, [3, 1, 2, 0]);
  validatePoolBarracksRecruitmentResponse(response, request);
  assert.throws(() => validateBarracksRecruitmentResponse(response, request));
  for (const change of [v => { v.tankman_descriptor_hex = '00' + v.tankman_descriptor_hex.slice(2); },
    v => { v.tankman_inventory_id++; }, v => { v.update_hex = v.update_hex.slice(0, -2) + '00'; }]) {
    const bad = structuredClone(response); change(bad); assert.throws(() => validatePoolBarracksRecruitmentResponse(bad, request));
  }
  assert.throws(() => validatePoolBarracksRecruitmentResponse(response, { ...request, layout: [3, 4609, 2, 0] }));
});

// CREW-ANY: actual v2 writer vectors (tests/test_p04m_pool_crew_v2.py with P04M_TEST_EXPORT).
const V2 = resolve(process.env.P04M_V2_FIXTURES || join(ROOT, 'local/evidence/crew-any-v2-vectors/v2-barracks-32'));
const skipV2 = !existsSync(join(V2, 'writer-vectors.json')) ? 'NOT_RUN: actual P04M crew v2 writer vectors required' : false;

test('P04M crew contracts are closed data: v1 16 and v2 192 by stored schema', () => {
  assert.equal(poolCrewContract({ schema: 'p04m-pool-crew.v1', policy_sha256: POOL_CREW_POLICY_SHA256 }).capacity, 16);
  assert.equal(poolCrewContract({ schema: 'p04m-pool-crew.v2', policy_sha256: POOL_CREW_V2_POLICY_SHA256 }).capacity, 192);
  for (const bad of [{ schema: 'p04m-pool-crew.v2', policy_sha256: POOL_CREW_POLICY_SHA256 }, { schema: 'p04m-pool-crew.v3', policy_sha256: POOL_CREW_V2_POLICY_SHA256 },
    { schema: '__proto__', policy_sha256: POOL_CREW_V2_POLICY_SHA256 }, { schema: 'constructor' }, null, undefined]) assert.throws(() => poolCrewContract(bad));
  assert.throws(() => validatePoolBarracksRecruitmentResponse({ status: 'recruited' }, { layout: [3, 7169, 4, 0], wire_revision: 1 }, 17));
});

test('P04M actual v2 profile and identities above 16 with wrapped passport icon', { skip: skipV2 }, () => {
  const receipt = JSON.parse(readFileSync(join(V2, 'writer-receipt.json')));
  assert.equal(receipt.classification, 'VERIFIED_ISOLATED_SQLITE_WRITER');
  for (const file of ['profile-input.json', 'writer-vectors.json']) {
    const bytes = readFileSync(join(V2, file)), pin = receipt.files.find(p => p.file === file);
    assert.equal(bytes.length, pin.bytes); assert.equal(digest(bytes), pin.sha256);
  }
  const p = JSON.parse(readFileSync(join(V2, 'profile-input.json'))), value = nativePoolOverview(p);
  assert.equal(p.crew_service.schema, 'p04m-pool-crew.v2');
  assert.equal(value.crewService.policySha256, POOL_CREW_V2_POLICY_SHA256);
  assert.ok(p.crew.some(m => /:recruit-crew:3[23]$/.test(m.crew_id)));
  assert.equal(isNativePoolOverview(value, p.account_id), true);
  const forged = structuredClone(value); forged.crewService.policySha256 = POOL_CREW_POLICY_SHA256;
  assert.equal(isNativePoolOverview(forged, p.account_id), false, 'a v1 hash cannot carry more than 16 lifetime tankmen');
  const companion = JSON.parse(readFileSync(join(V2, 'p04m-pool.json')));
  assert.deepEqual([companion.crew_capacity, companion.crew_policy_sha256], [192, POOL_CREW_V2_POLICY_SHA256]);
  const rows = JSON.parse(readFileSync(join(V2, 'writer-vectors.json'))).filter(r => r.operation === 'recruit_barracks');
  const high = rows.filter(r => r.response.tankman_inventory_id > 16);
  assert.ok(high.some(r => r.response.tankman_inventory_id === 32));
  for (const { request, response } of high) {
    validatePoolBarracksRecruitmentResponse(response, request, 192);
    assert.throws(() => validatePoolBarracksRecruitmentResponse(response, request));
    assert.throws(() => validatePoolBarracksRecruitmentResponse(response, request, 16));
  }
  const low = rows.filter(r => r.response.tankman_inventory_id <= 16);
  for (const { request, response } of low) {
    validatePoolBarracksRecruitmentResponse(response, request, 192);
    assert.throws(() => validatePoolBarracksRecruitmentResponse(response, request, 16), 'freeTMenLeft follows the stored contract');
  }
});
