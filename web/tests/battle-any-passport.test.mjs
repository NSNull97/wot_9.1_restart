// BATTLE-ANY 3d: the bridge free50 passport equals the Python writer's for every pilot nation.
import test from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { barracksPassport } from '../src/p04m-pool.mjs';
import { CATALOG_VEHICLES } from '../src/catalog-v1.mjs';

const ROLE_IDS = { commander: 1, radioman: 2, driver: 3, gunner: 4, loader: 5 };
const tools = fileURLToPath(new URL('../../tools', import.meta.url));

test('bridge passport equals tools/p04m_pool_crew.passport (USSR v1 rule and pilot nations)', () => {
  const rows = CATALOG_VEHICLES.filter(v => ['ms1', 't34', 'ussr-KV-3', 'usa-M4_Sherman', 'germany-Waffentrager_E100', 'japan-Chi_Ri'].includes(v.kind));
  const cases = rows.flatMap(v => [4, 32, 150, 192].map(id => [v.kind, v.native_compact_id, v.crew[0].roles[0], id]));
  const script = 'import sys,json;sys.path.insert(0,sys.argv[1]);import catalog_v1,catalog_v1_data,p04m_pool_crew as c;'
    + 'catalog_v1.activate(catalog_v1_data.CATALOG_SHA256);'
    + 'print(json.dumps([c.passport(i,cd>>8,r,192,(cd>>4)&15).hex() for k,cd,r,i in json.loads(sys.argv[2])]))';
  const python = JSON.parse(execFileSync('python', ['-B', '-X', 'utf8', '-c', script, tools, JSON.stringify(cases)], { encoding: 'utf8' }));
  assert.equal(python.length, cases.length);
  cases.forEach(([kind, cd, role, id], i) =>
    assert.equal(barracksPassport(cd, ROLE_IDS[role], id).toString('hex'), python[i], `${kind} #${id}`));
  assert.equal(barracksPassport(1057, 1, 4)[0], 8 + (2 << 4));
});
