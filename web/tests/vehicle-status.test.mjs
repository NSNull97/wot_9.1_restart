import test from 'node:test';
import assert from 'node:assert/strict';
import { join } from 'node:path';
import { catalog, vehicleStatus } from '../src/catalog.mjs';
import { createApp } from '../src/app.mjs';
import { browser, freePort, testDirectory, removeTestDirectory } from './helpers.mjs';

const vehicle = id => {
  const found=catalog.vehicles.find(item=>item.id===id);
  assert.ok(found,id);
  return found;
};

test('status distinguishes special rewards from premium prices and tier X guns still needing research',()=>{
  for(const id of ['usa-m60','germany-vk7201','ussr-object-907','usa-t95-e6']){
    assert.equal(vehicle(id).premium,true,'old gold-price flag is not the displayed category');
    assert.equal(vehicleStatus(vehicle(id)).kind,'reward',id);
  }
  for(const id of ['ussr-object252','germany-lowe','china-ch01-type59','usa-t23e3']){
    assert.equal(vehicleStatus(vehicle(id)).kind,'premium',id);
    assert.equal(vehicleStatus(vehicle(id)).wreath,true,id);
  }
  for(const id of ['ussr-is-7','ussr-t62a','uk-gb48-fv215b-183','germany-maus']){
    assert.equal(vehicleStatus(vehicle(id)).kind,'elite',id);
    assert.equal(vehicleStatus(vehicle(id)).wreath,true,id);
  }
  for(const id of ['ussr-is-4','germany-e-100','germany-waffentrager-e100','usa-m48a1','france-bat-chatillon25t','ussr-kv-1s']){
    assert.equal(vehicleStatus(vehicle(id)).kind,'researchable',id);
    assert.equal(vehicleStatus(vehicle(id)).wreath,false,id);
  }
  assert.equal(vehicleStatus(vehicle('germany-karl')).kind,'event');
  assert.equal(catalog.vehicles.filter(v=>vehicleStatus(v).kind==='elite').length,27);
});

test('public cards and dossiers expose the same status as text and a wreath without changing account progress',async t=>{
  const directory=testDirectory(),origin=`http://127.0.0.1:${await freePort()}`;
  const runtime=await createApp({databasePath:join(directory,'status.sqlite'),origin});
  const server=runtime.app.listen(Number(new URL(origin).port),'127.0.0.1');
  await new Promise(resolve=>server.once('listening',resolve));
  t.after(async()=>{await new Promise(resolve=>server.close(resolve));runtime.close();removeTestDirectory(directory);});
  const guest=browser(origin);
  for(const [id,name,kind] of [['ussr-object252','ИС-6','premium'],['usa-m60','M60','reward'],['ussr-is-7','ИС-7','elite'],['ussr-is-4','ИС-4','researchable']]){
    const status=vehicleStatus(vehicle(id));
    const detail=await guest.get('/vehicles/'+id);
    assert.equal(detail.status,200,id);
    assert.ok(detail.html.includes(status.label),id);
    assert.ok(detail.html.includes(status.description),id);
    assert.equal(detail.html.includes('class="vehicle-laurel"'),status.wreath,id);
    assert.match(detail.headers.get('content-security-policy'),/script-src 'none'/);
    assert.equal(detail.headers.get('set-cookie'),null);
    const listing=await guest.get('/vehicles?q='+encodeURIComponent(name));
    const tile=listing.html.match(new RegExp(`<a class="vehicle-card" href="/vehicles/${id}"[\\s\\S]*?</a>`))?.[0];
    assert.ok(tile,id);
    assert.ok(tile.includes(`status-${kind}`),id);
    assert.equal(tile.includes('class="vehicle-laurel"'),status.wreath,id);
    if(status.wreath)assert.ok(tile.includes(status.short),id);
    assert.doesNotMatch(tile,/class="card-premium"/);
  }
  const upgraded=await guest.get('/vehicles/ussr-is-4?module=gun-1');
  assert.equal(upgraded.status,200);
  assert.ok(upgraded.html.includes('Исследуемая техника'));
  assert.doesNotMatch(upgraded.html,/class="vehicle-laurel"/);
  assert.equal(runtime.store.db.prepare('SELECT COUNT(*) AS n FROM users').get().n,0);
});
