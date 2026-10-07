import test from 'node:test';
import assert from 'node:assert/strict';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { catalog, catalogMedia, modernMedia, artOverrides, vehicleImage, counts, readFilters, filterVehicles, filterMaps } from '../src/catalog.mjs';
import { createApp } from '../src/app.mjs';
import { browser, freePort, testDirectory, removeTestDirectory } from './helpers.mjs';

test('0.9.1 historical anchors remain tied to the exact gun and shell',()=>{
  const wt=catalog.vehicles.find(v=>v.id==='germany-waffentrager-e100');
  const guns=wt.turrets[0].guns;
  assert.equal(wt.crew,6); // The descriptor has two separate loader entries.
  assert.equal(guns.find(g=>g.key==='_128mm_K44_2_L61').magazine,6);
  assert.equal(guns.find(g=>g.key==='_150mm_Rohr_L38').magazine,4);
  const fv=catalog.vehicles.find(v=>v.id==='uk-gb48-fv215b-183');
  const hesh=fv.turrets[0].guns.find(g=>g.key==='_183mm_AT_Gun').shots.find(s=>s.key==='_183mm_HESH');
  assert.equal(hesh.premium,true); assert.deepEqual(hesh.penetration,[275,275]); assert.equal(hesh.damage,1750);
  assert.equal(catalog.vehicles.find(v=>v.id==='ussr-kv-1s').tier,6);
  assert.deepEqual(catalog.maps.find(m=>m.id==='11_murovanka').size,[800,800]);
  assert.deepEqual(catalog.maps.find(m=>m.id==='83_kharkiv').size,[800,800]);
});

test('catalog covers all imported definitions, separates archives and keeps map naming independent',()=>{
  assert.equal(catalog.vehicleCount,374); assert.equal(counts.vehicles,351); assert.equal(counts.archive,23);
  assert.equal(catalog.mapCount,45); assert.equal(counts.maps,41);
  assert.equal(new Set(catalog.vehicles.map(v=>v.id)).size,374);
  assert.equal(new Set(catalog.maps.map(m=>m.name)).size,45);
  for(const vehicle of catalog.vehicles){
    assert.match(vehicle.id,/^[a-z0-9-]+$/); assert.ok(vehicle.tier>=1&&vehicle.tier<=10);
    assert.ok(vehicle.hullArmor.length===3); assert.ok(vehicle.turrets.length>0);
    for(const turret of vehicle.turrets){
      assert.ok(turret.hitPoints>0); assert.ok(turret.guns.length>0);
      for(const gun of turret.guns){
        assert.ok(gun.reloadTime>0); assert.ok(gun.shots.length>0);
        for(const shot of gun.shots){assert.equal(shot.penetration.length,2);assert.ok(shot.damage>=0);}
      }
    }
  }
  for(const map of catalog.maps){
    assert.notEqual(map.name,map.originalName); assert.ok(map.size.every(n=>n>0&&n<=2000));
    for(const mode of map.modes){
      assert.ok(mode.durationSeconds>0);
      for(const base of mode.bases){assert.equal(base.position.length,2);assert.ok(base.position.every(Number.isFinite));}
    }
  }
  assert.deepEqual(catalog.maps.filter(m=>!m.registered).map(m=>m.id),['59_asia_great_wall','73_asia_korea']);
});

test('search handles historical names, umlauts and simultaneous filters',()=>{
  assert.deepEqual(filterVehicles(readFilters({q:'Waffentrager'},'vehicles')).map(v=>v.id),['germany-waffentrager-e100','germany-waffentrager-iv','germany-rhb-waffentrager']);
  const sovietSix=filterVehicles(readFilters({nation:'ussr',tier:'6',class:'heavyTank'},'vehicles'));
  assert.ok(sovietSix.some(v=>v.id==='ussr-kv-1s'));
  assert.ok(sovietSix.every(v=>v.nation==='ussr'&&v.tier===6&&v.class==='heavyTank'));
  assert.deepEqual(filterMaps(readFilters({q:'Прохоровка'},'maps')).map(m=>m.name),['Полевой разъезд']);
  assert.equal(filterMaps(readFilters({q:'Полевой разъезд'},'maps')).length,1);
  assert.equal(filterVehicles(readFilters({scope:'archive'},'vehicles')).length,23);
  assert.equal(filterMaps(readFilters({scope:'special'},'maps')).length,2);
  assert.equal(readFilters({q:['x','y']},'vehicles'),null);
  assert.equal(readFilters({page:'-1'},'maps'),null);
});

test('public catalog routes render real data with bounded, escaped filters',async t=>{
  const directory=testDirectory(),origin=`http://127.0.0.1:${await freePort()}`;
  const runtime=await createApp({databasePath:join(directory,'catalog.sqlite'),origin});
  const server=runtime.app.listen(Number(new URL(origin).port),'127.0.0.1');
  await new Promise(resolve=>server.once('listening',resolve));
  t.after(async()=>{await new Promise(resolve=>server.close(resolve));runtime.close();removeTestDirectory(directory);});
  const guest=browser(origin);
  await t.test('home links to both catalogs, pages and styles work without creating user sessions',async()=>{
    const home=await guest.get('/');assert.equal(home.status,200);assert.match(home.html,/href="\/vehicles"/);assert.match(home.html,/href="\/maps"/);
    const fresh=browser(origin);
    for(const path of ['/vehicles','/maps','/assets/catalog.css']){const r=await fresh.get(path);assert.equal(r.status,200);assert.equal(r.headers.get('set-cookie'),null);}
    assert.match((await fresh.get('/vehicles')).headers.get('content-security-policy'),/script-src 'none'/);
    assert.equal(runtime.store.db.prepare('SELECT COUNT(*) AS n FROM users').get().n,0);
  });
  await t.test('all 374 vehicle dossiers and 66 map-mode pages render without missing data errors',async()=>{
    for(const vehicle of catalog.vehicles){const r=await guest.get(`/vehicles/${vehicle.id}`);assert.equal(r.status,200,vehicle.id);assert.doesNotMatch(r.html,/undefined|NaN|Infinity/);}
    for(const map of catalog.maps){for(const mode of map.modes){const r=await guest.get(`/maps/${map.id}?mode=${mode.id}`);assert.equal(r.status,200,`${map.id}/${mode.id}`);assert.doesNotMatch(r.html,/undefined|NaN|Infinity/);assert.ok(r.html.includes(map.name));}}
  });
  await t.test('old-name map search returns the renamed page and no unrelated records',async()=>{
    const r=await guest.get('/maps?q='+encodeURIComponent('Прохоровка'));
    assert.equal(r.status,200);assert.match(r.html,/class="map-card climate-/);assert.equal((r.html.match(/class="map-card climate-/g)||[]).length,1);assert.match(r.html,/Полевой разъезд/);
  });
  await t.test('all 420 allowlisted PNGs match the historic member hashes; no cache directory is exposed',async()=>{
    const media=Object.values(catalogMedia.vehicles).filter(Boolean).concat(Object.values(catalogMedia.maps),Object.values(catalogMedia.nations));
    assert.equal(media.length,420);assert.equal(Object.values(catalogMedia.nations).length,7);
    for(const vehicle of catalog.vehicles.filter(v=>!v.archived)) assert.equal(catalogMedia.vehicles[vehicle.id]?.kind,'render',vehicle.id);
    for(const row of media){
      const response=await fetch(origin+row.url);assert.equal(response.status,200,row.url);assert.match(response.headers.get('content-type'),/^image\/png/);
      assert.equal(response.headers.get('set-cookie'),null);
      const data=Buffer.from(await response.arrayBuffer());assert.equal(data.length,row.bytes);assert.equal(createHash('sha256').update(data).digest('hex'),row.sha256,row.url);
    }
    for(const path of ['/catalog-media/v1/nations/unknown.png','/catalog-media/v1/maps/','/catalog-media/v1/maps/catalog.v1.json','/catalog-media/v1/vehicles/%2e%2e%2fportal.sqlite','/catalog-media/v2/maps/05_prohorovka.png']) assert.equal((await guest.get(path)).status,404,path);
    const dossier=await guest.get('/vehicles/germany-waffentrager-e100');assert.match(dossier.html,/nations\/germany\.png/);assert.match(dossier.html,/vehicles\/germany-waffentrager-e100\.png/);
    const map=await guest.get('/maps/05_prohorovka');assert.match(map.html,/<image href="\/catalog-media\/v1\/maps\/05_prohorovka\.png"/);assert.match(map.html,/МИНИКАРТА/);
    const t23=await guest.get('/vehicles/usa-t23');assert.match(t23.html,/HD-рендер: T23E3/);assert.doesNotMatch(t23.html,/Изображение этой архивной машины отсутствует/);
  });
  await t.test('pagination and combined vehicle filters select matching records',async()=>{
    const r=await guest.get('/vehicles?nation=ussr&class=heavyTank&tier=6');assert.equal(r.status,200);assert.match(r.html,/href="\/vehicles\/ussr-kv-1s"/);assert.doesNotMatch(r.html,/href="\/vehicles\/usa-/);
    const first=await guest.get('/vehicles'),second=await guest.get('/vehicles?page=2');
    const ids=html=>[...html.matchAll(/class="vehicle-card" href="([^"]+)"/g)].map(m=>m[1]);
    assert.equal(ids(first.html).length,24);assert.equal(ids(second.html).length,24);assert.ok(ids(first.html).every(id=>!ids(second.html).includes(id)));
    const empty=await guest.get('/vehicles?q=no-such-machine-12345');assert.equal(empty.status,200);assert.match(empty.html,/Машин не найдено/);
  });
  await t.test('modern renders are served intact, correctly mapped and separate from 0.9.1 facts',async()=>{
    const entries=Object.entries(modernMedia.vehicles);assert.equal(entries.length,362);
    const exceptions=catalog.vehicles.filter(v=>!v.archived&&!modernMedia.vehicles[v.id]).map(v=>v.id);
    assert.deepEqual(exceptions,['germany-pziii-a','usa-t57','usa-t18','usa-m48a1']);
    assert.equal(modernMedia.vehicles['usa-t49'].modelId,'a58_t67');assert.equal(modernMedia.vehicles['usa-t71'].modelId,'a103_t71e1');
    for(const [id,row] of entries){
      assert.ok(row.width>=600&&row.height>0);assert.equal(row.viewBox.length,4);
      assert.equal(vehicleImage(catalog.vehicles.find(v=>v.id===id)),row);
      const response=await fetch(origin+row.url);assert.equal(response.status,200,id);assert.match(response.headers.get('content-type'),/^image\/png/);
      const data=Buffer.from(await response.arrayBuffer());assert.equal(createHash('sha256').update(data).digest('hex'),row.sha256,id);
    }
    const wt=await guest.get('/vehicles/germany-waffentrager-e100');assert.match(wt.html,/catalog-media\/v2\/vehicles\/germany-waffentrager-e100\.png/);assert.match(wt.html,/Современный HD-рендер/);
    const replacements=Object.entries(artOverrides.vehicles);assert.equal(replacements.length,11);
    for(const [id,row] of replacements){
      assert.equal(vehicleImage(catalog.vehicles.find(v=>v.id===id)),row);
      const response=await fetch(origin+row.url);assert.equal(response.status,200,id);assert.match(response.headers.get('content-type'),/^image\/png/);
      const data=Buffer.from(await response.arrayBuffer());assert.equal(data.length,row.bytes);assert.equal(createHash('sha256').update(data).digest('hex'),row.sha256,id);
      const dossier=await guest.get(`/vehicles/${id}`);assert.ok(dossier.html.includes(row.url));assert.doesNotMatch(dossier.html,/Изображение этой архивной машины отсутствует/);
    }
    assert.match((await guest.get('/vehicles/usa-m48a1')).html,/HD-рендер: M48A5 Patton/);
    assert.match((await guest.get('/vehicles/usa-t57')).html,/AI-апскейл оригинала/);
    assert.match((await guest.get('/vehicles/germany-karl')).html,/Архивный рендер/);
    for(const vehicle of catalog.vehicles) assert.ok(vehicleImage(vehicle),vehicle.id);
    assert.equal(vehicleImage(catalog.vehicles.find(v=>v.id==='germany-karl')),catalogMedia.vehicles['germany-karl']);
    assert.equal(artOverrides.vehicles['usa-t18'].modelId,'a108_t18_hmc');
    assert.equal(catalog.vehicles.find(v=>v.id==='usa-t18').tier,2);assert.equal(catalog.vehicles.find(v=>v.id==='usa-t18').class,'AT-SPG');
    assert.equal(artOverrides.vehicles['ussr-t-50-2'].modelId,'r160_t_50_2');assert.equal(catalog.vehicles.find(v=>v.id==='ussr-t-50-2').tier,5);
    for(const path of ['/catalog-media/v3/vehicles/unknown.png','/catalog-media/v3/maps/05_prohorovka.png','/catalog-media/v3/vehicles/%2e%2e%2fportal.sqlite']) assert.equal((await guest.get(path)).status,404,path);
    assert.equal(catalog.vehicles.find(v=>v.id==='ussr-kv-1s').tier,6);
  });
  await t.test('malformed filters and unknown IDs fail honestly; source files are not served',async()=>{
    for(const path of ['/vehicles?q=a&q=b','/vehicles?nation=unknown','/vehicles?tier=11','/maps?scope=unknown','/maps?page=0','/maps?q='+ 'x'.repeat(81),'/maps/05_prohorovka?mode=unknown']) assert.equal((await guest.get(path)).status,400,path);
    for(const path of ['/vehicles/unknown','/maps/unknown','/data/catalog.v1.json','/scripts/build-catalog.py']) assert.equal((await guest.get(path)).status,404,path);
  });
  await t.test('search text is escaped and catalog does not expose accounts or game state',async()=>{
    const payload='\"><script>alert(1)</script>';
    const r=await guest.get('/vehicles?q='+encodeURIComponent(payload));assert.equal(r.status,200);assert.doesNotMatch(r.html,/<script>/);assert.match(r.html,/&lt;script&gt;/);
    assert.equal((await browser(origin).get('/api/profile')).status,401);assert.equal((await browser(origin).get('/api/game')).status,401);
  });
});
