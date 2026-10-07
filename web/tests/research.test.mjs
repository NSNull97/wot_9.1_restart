import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { join } from 'node:path';
import { catalog } from '../src/catalog.mjs';
import { researchCatalog, researchView, validModuleQuery } from '../src/research.mjs';
import { createApp } from '../src/app.mjs';
import { browser, freePort, testDirectory, removeTestDirectory } from './helpers.mjs';

test('research covers all 374 historical vehicles and is pinned to unchanged 0.9.1 facts',()=>{
  const hash=createHash('sha256').update(readFileSync(new URL('../data/catalog.v1.json',import.meta.url))).digest('hex');
  assert.equal(hash,'d66aad60c13d83807f49b1ebfc8cc89f330e658ed3223706169f763052547567');
  assert.equal(researchCatalog.factsSha256,hash);
  assert.equal(Object.keys(researchCatalog.vehicles).length,374);
  let nodeCount=0,edgeCount=0;
  const vehicles=new Map(catalog.vehicles.map(v=>[v.id,v]));
  for(const vehicle of catalog.vehicles){
    const tree=researchCatalog.vehicles[vehicle.id],view=researchView(vehicle);
    nodeCount+=tree.nodes.length;edgeCount+=tree.edges.length;
    assert.equal(view.nodes.length,tree.nodes.length);
    assert.equal(new Set(tree.nodes.map(n=>n.id)).size,tree.nodes.length);
    for(const node of tree.nodes){
      assert.ok(node.name.length>0,vehicle.id);
      assert.ok(node.level>=1&&node.level<=10,`${vehicle.id}/${node.id}`);
      if(node.kind==='vehicle') assert.equal(node.key,vehicles.get(node.vehicleId)?.key);
      if(node.price){assert.ok(node.price.amount>=0);assert.ok(['gold','credits'].includes(node.price.currency));}
    }
    for(const edge of view.edges){
      const from=view.byId.get(edge.from),to=view.byId.get(edge.to);
      assert.ok(from&&to);assert.ok(Number.isSafeInteger(edge.xp)&&edge.xp>=0);
      assert.ok(from.rank<to.rank,`acyclic progression: ${vehicle.id}`);
    }
    for(const node of view.nodes){
      assert.ok(node.x>=0&&node.x+188<=view.width);
      assert.ok(node.y>=0&&node.y+92<=view.height);
      if(node.kind==='gun') assert.ok(vehicle.turrets.some(t=>t.guns.some(g=>g.key===node.key)));
    }
  }
  assert.equal(nodeCount,3945);assert.equal(edgeCount,2062);
});

test('KV-1S retains real XP branches, chassis load limits and turret-specific ammunition capacities',()=>{
  const kv=catalog.vehicles.find(v=>v.id==='ussr-kv-1s'),tree=researchView(kv,'gun-0');
  assert.deepEqual(tree.price,{amount:900000,currency:'credits'});
  assert.equal(tree.byId.get('chassis-0').maxLoadKg,42800);
  assert.equal(tree.byId.get('chassis-1').maxLoadKg,48200);
  assert.deepEqual(tree.byId.get('chassis-1').terrainResistance,[1,1.1,2.1]);
  const xp=(from,to)=>tree.edges.find(e=>e.from===from&&e.to===to)?.xp;
  assert.equal(xp('chassis-0','chassis-1'),4915);
  assert.equal(xp('gun-1','turret-1'),5305);
  assert.equal(xp('turret-1','gun-4'),17000);
  assert.equal(xp('gun-3','vehicle-ussr-is'),49480);
  assert.equal(xp('engine-0','vehicle-ussr-mt25'),24400);
  assert.deepEqual(tree.gunVariants.map(v=>[v.turret.key,v.gun.ammoCapacity]),[['KV1S_mod_42',94],['KV1S_mod_43',114]]);
  assert.ok(tree.edges.some(e=>e.selected));
  assert.equal(researchView(catalog.vehicles.find(v=>v.id==='ussr-is-7')).edges.length,0);
  assert.equal(validModuleQuery({module:['gun-0','gun-1']},kv.id),false);
  assert.equal(validModuleQuery({module:'vehicle-ussr-is'},'ussr-is-7'),false);
});

test('module links serve complete historical details and reject invalid selections without enabling scripts',async t=>{
  const directory=testDirectory(),origin=`http://127.0.0.1:${await freePort()}`;
  const runtime=await createApp({databasePath:join(directory,'research.sqlite'),origin});
  const server=runtime.app.listen(Number(new URL(origin).port),'127.0.0.1');
  await new Promise(resolve=>server.once('listening',resolve));
  t.after(async()=>{await new Promise(resolve=>server.close(resolve));runtime.close();removeTestDirectory(directory);});
  const guest=browser(origin),base='/vehicles/ussr-kv-1s';
  for(const [module,text] of [['chassis-1','Предельная нагрузка'],['engine-1','Вероятность пожара'],['radio-1','Дальность связи'],['turret-1','ОРУДИЯ ДЛЯ ЭТОЙ БАШНИ'],['gun-4','122 мм Д2-5Т'],['vehicle-ussr-is','href="/vehicles/ussr-is"']]){
    const response=await guest.get(`${base}?module=${module}`);
    assert.equal(response.status,200,module);assert.ok(response.html.includes(`data-module="${module}"`));assert.ok(response.html.includes(text),module);
    assert.match(response.headers.get('content-security-policy'),/script-src 'none'/);
    assert.doesNotMatch(response.html,/<script|style=|undefined|NaN|Infinity/);
    assert.equal(response.headers.get('set-cookie'),null);
  }
  const shared=await guest.get(base+'?module=gun-0');
  assert.match(shared.html,/КВ-1С обр\. 1942 г\./);assert.match(shared.html,/94 снар\./);assert.match(shared.html,/114 снар\./);
  const fixed=await guest.get('/vehicles/ussr-is-7?module=gun-0');
  assert.equal(fixed.status,200);assert.match(fixed.html,/В данных этой машины нет переходов исследования/);
  for(const query of ['module=missing','module=gun-0&module=gun-1','module=gun-0&evil=x','module=','module='+encodeURIComponent('<script>alert(1)</script>')]){
    const response=await guest.get(base+'?'+query);assert.equal(response.status,400,query);assert.doesNotMatch(response.html,/<script>/);
  }
  const cards=await guest.get('/vehicles');
  for(const label of ['Броня корпуса','Обзор','Мощность','Орудия'])assert.ok(cards.html.includes(label));
  assert.match(cards.html,/class="vehicle-class-badge" title="Тяжёлый танк"/);
  assert.match(cards.html,/ЛЕГЕНДАРНЫЕ\s*<br>\s*МАШИНЫ/);
  assert.equal((cards.html.match(/class="legend-card /g)||[]).length,3);
  for(const path of ['/data/catalog-research.v1.json','/scripts/build-research-tree.py','/src/research.mjs'])assert.equal((await guest.get(path)).status,404);
  assert.equal(runtime.store.db.prepare('SELECT COUNT(*) AS n FROM users').get().n,0);
});
