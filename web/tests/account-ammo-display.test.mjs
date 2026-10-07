import test from 'node:test';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import ejs from 'ejs';

const template=fileURLToPath(new URL('../views/account.ejs',import.meta.url));
const id='d19df8cd-0877-4373-b4e2-011084792011';

test('profile4 renders the server ammunition total only on the intended vehicle',async()=>{
  const game={state:'ready',account:{nickname:'Тестер'},resources:{credits:100000,gold:0,freeXP:0},
    inventory:[{inventoryItemId:`${id}:starter-vehicle-v1`,displayName:'МС-1',health:90,crewAssigned:true,ammunition:20},
               {inventoryItemId:`${id}:test-is7-v1`,displayName:'ИС-7',health:2150,crewAssigned:false,ammunition:0}],
    statistics:{battles:0,wins:0,losses:0,draws:0},snapshotRevision:4,asOf:'2026-10-05T06:00:00.000Z'};
  const before=structuredClone(game);
  const html=await ejs.renderFile(template,{title:'Unit render',currentPath:'/account',csrf:'unit-csrf',
    user:{id,display_name:'Тестер',display_nickname:'Тестер',email:'own@example.invalid',created_at:1791140400000},
    welcome:false,saved:false,errors:{},values:{},game});
  const rows=new Map([...html.matchAll(/<dd data-inventory-item="([^"]+)">([^<]*)<\/dd>/g)].map(([,key,text])=>[key,text]));
  assert.equal(rows.get(`${id}:starter-vehicle-v1`),'МС-1 · 90 HP · экипаж назначен · боекомплект: 20 шт.');
  assert.equal(rows.get(`${id}:test-is7-v1`),'ИС-7 · 2150 HP · экипаж и боекомплект не назначены');
  assert.deepEqual(game,before);
});
