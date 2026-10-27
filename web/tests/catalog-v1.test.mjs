import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { CATALOG_SHA256, CATALOG_VEHICLES } from '../src/catalog-v1.mjs';
import { LEGACY_MIXED_TYPES, catalogMixedTypes, useMixedCatalog, mixedTypes } from '../src/p06t-mixed.mjs';
import { LEGACY_POOL_TYPES, catalogPoolTypes, usePoolCatalog, poolTypes } from '../src/p04m-pool.mjs';

const plain = v => JSON.parse(JSON.stringify(v));
const LEGACY = ['ms1', 'is7', 't26', 't34', 't3485'];
// BATTLE-ANY stage 3 pilot (owner 2026-10-27): generated catalog rows, admission "always".
const PILOT = ['ussr-KV-3', 'usa-M4_Sherman', 'germany-Waffentrager_E100', 'japan-Chi_Ri'];
const legacyMixed = types => Object.fromEntries(LEGACY.map(k => [k, types[k]]));

test('CAT-01 bridge binding hash is the committed catalog bytes', () => {
  const raw = readFileSync(new URL('../../config/catalog/catalog.v1.json', import.meta.url));
  assert.equal(createHash('sha256').update(raw).digest('hex'), CATALOG_SHA256);
  assert.deepEqual(plain(CATALOG_VEHICLES), JSON.parse(raw).vehicles);
  assert.ok(Object.isFrozen(CATALOG_VEHICLES) && Object.isFrozen(CATALOG_VEHICLES[0].shells));
});

test('catalog-derived validator tables equal the retained closed lists', () => {
  assert.deepEqual(plain(legacyMixed(catalogMixedTypes())), plain(LEGACY_MIXED_TYPES));
  assert.deepEqual(plain(catalogPoolTypes().slice(0, 5)), plain(LEGACY_POOL_TYPES));
  assert.deepEqual(Object.keys(catalogMixedTypes()), [...LEGACY, ...PILOT]);
});

test('pilot rows carry the catalog facts (any nation, generated label)', () => {
  const mixed = catalogMixedTypes(); const pool = catalogPoolTypes();
  for (const kind of PILOT) {
    const v = CATALOG_VEHICLES.find(row => row.kind === kind);
    assert.deepEqual(plain(mixed[kind]), { native: null, descriptor: v.descriptor_hex, hp: v.max_hp, capacity: v.ammo_capacity,
      crew: v.crew.length, shells: v.shells.map(s => s.native_compact_id), suffixes: v.shells.map(s => s.suffix),
      families: v.shells.map(s => s.family), devices: v.devices.map(d => d.max_health) });
    assert.deepEqual(plain(pool.find(t => t.kind === kind)), { kind, resource: v.resource_name, cd: v.native_compact_id,
      capacity: v.ammo_capacity, roles: v.crew.map(c => c.roles[0]), shells: v.shells.map(s => s.suffix) });
  }
  assert.equal(mixed['germany-Waffentrager_E100'].crew, 6);
});

test('battle_admission is data: none drops a kind from mixed admission, not from the pool registry', () => {
  const rows = plain(CATALOG_VEHICLES).map(v => v.kind === 't34' ? { ...v, battle_admission: 'none' } : v);
  assert.deepEqual(Object.keys(catalogMixedTypes(rows)), ['ms1', 'is7', 't26', 't3485', ...PILOT]);
  assert.equal(catalogPoolTypes(rows).length, 9);
});

test('the flag switches tables only with this build hash', () => {
  assert.equal(mixedTypes(), LEGACY_MIXED_TYPES); assert.equal(poolTypes(), LEGACY_POOL_TYPES);
  assert.throws(() => useMixedCatalog('0'.repeat(64)), /catalog hash differs/);
  assert.throws(() => usePoolCatalog(undefined), /catalog hash differs/);
  assert.equal(mixedTypes(), LEGACY_MIXED_TYPES);
  useMixedCatalog(CATALOG_SHA256); usePoolCatalog(CATALOG_SHA256);
  assert.notEqual(mixedTypes(), LEGACY_MIXED_TYPES);
  assert.deepEqual(plain(legacyMixed(mixedTypes())), plain(LEGACY_MIXED_TYPES));
  assert.deepEqual(plain(poolTypes().slice(0, 5)), plain(LEGACY_POOL_TYPES));
});

test('catalog mode accepts the same actual P06T SQLite writer vectors', async () => {
  const { validateMixedBattleRequest, validateMixedBattleReply, validateMixedResultsRequest, validateMixedResultsReply } = await import('../src/p06t-mixed.mjs');
  useMixedCatalog(CATALOG_SHA256);
  const fixture = JSON.parse(readFileSync(new URL('../../tests/fixtures/p06t-writer-vectors.json', import.meta.url)));
  assert.equal(fixture.vectors.length, 13);
  for (const v of fixture.vectors) {
    if (v.operation === 'battle') { validateMixedBattleRequest(v.request, v.request.account_id); validateMixedBattleReply(v.response, v.request); }
    else { validateMixedResultsRequest(v.request, v.request.account_id); validateMixedResultsReply(v.response, v.request); }
  }
});
