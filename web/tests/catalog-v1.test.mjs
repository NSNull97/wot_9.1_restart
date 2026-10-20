import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { CATALOG_SHA256, CATALOG_VEHICLES } from '../src/catalog-v1.mjs';
import { LEGACY_MIXED_TYPES, catalogMixedTypes, useMixedCatalog, mixedTypes } from '../src/p06t-mixed.mjs';
import { LEGACY_POOL_TYPES, catalogPoolTypes, usePoolCatalog, poolTypes } from '../src/p04m-pool.mjs';

const plain = v => JSON.parse(JSON.stringify(v));

test('CAT-01 bridge binding hash is the committed catalog bytes', () => {
  const raw = readFileSync(new URL('../../config/catalog/catalog.v1.json', import.meta.url));
  assert.equal(createHash('sha256').update(raw).digest('hex'), CATALOG_SHA256);
  assert.deepEqual(plain(CATALOG_VEHICLES), JSON.parse(raw).vehicles);
  assert.ok(Object.isFrozen(CATALOG_VEHICLES) && Object.isFrozen(CATALOG_VEHICLES[0].shells));
});

test('catalog-derived validator tables equal the retained closed lists', () => {
  assert.deepEqual(plain(catalogMixedTypes()), plain(LEGACY_MIXED_TYPES));
  assert.deepEqual(plain(catalogPoolTypes()), plain(LEGACY_POOL_TYPES));
});

test('battle_admission is data: none drops a kind from mixed admission, not from the pool registry', () => {
  const rows = plain(CATALOG_VEHICLES).map(v => v.kind === 't34' ? { ...v, battle_admission: 'none' } : v);
  assert.deepEqual(Object.keys(catalogMixedTypes(rows)), ['ms1', 'is7', 't26', 't3485']);
  assert.equal(catalogPoolTypes(rows).length, 5);
});

test('the flag switches tables only with this build hash', () => {
  assert.equal(mixedTypes(), LEGACY_MIXED_TYPES); assert.equal(poolTypes(), LEGACY_POOL_TYPES);
  assert.throws(() => useMixedCatalog('0'.repeat(64)), /catalog hash differs/);
  assert.throws(() => usePoolCatalog(undefined), /catalog hash differs/);
  assert.equal(mixedTypes(), LEGACY_MIXED_TYPES);
  useMixedCatalog(CATALOG_SHA256); usePoolCatalog(CATALOG_SHA256);
  assert.notEqual(mixedTypes(), LEGACY_MIXED_TYPES);
  assert.deepEqual(plain(mixedTypes()), plain(LEGACY_MIXED_TYPES));
  assert.deepEqual(plain(poolTypes()), plain(LEGACY_POOL_TYPES));
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
