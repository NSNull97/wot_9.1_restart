import test from 'node:test';
import assert from 'node:assert/strict';
import { request } from 'node:http';
import { randomBytes } from 'node:crypto';
import { join } from 'node:path';
import { createApp } from '../src/app.mjs';
import { readNetworkConfig, validateOrigins } from '../src/network.mjs';
import { freePort, testDirectory, removeTestDirectory } from './helpers.mjs';

test('network exposure is explicit and refuses broad or malformed origin configuration',()=>{
  assert.deepEqual(readNetworkConfig({}),{host:'127.0.0.1',port:3091,origins:['http://127.0.0.1:3091']});
  assert.throws(()=>readNetworkConfig({WEB_HOST:'0.0.0.0'}),/WEB_ORIGINS/);
  for(const bad of ['*','http://*','http://0.0.0.0:3091','http://[::]:3091','http://user:password@host.test','http://host.test/path','http://host.test?x=1','http://host.test#hash','https://host.test']) {
    assert.throws(()=>validateOrigins([bad]),undefined,bad);
  }
  assert.throws(()=>readNetworkConfig({WEB_HOST:'host.invalid'}));
  assert.throws(()=>readNetworkConfig({WEB_PORT:'20014'}));
  assert.throws(()=>validateOrigins([]));
  const config=readNetworkConfig({WEB_HOST:'0.0.0.0',WEB_PORT:'3091',WEB_ORIGINS:'http://127.0.0.1:3091, http://192.0.2.10:3091,http://198.51.100.10'});
  assert.equal(config.host,'0.0.0.0');assert.equal(config.port,3091);
  assert.equal(validateOrigins(config.origins).get('198.51.100.10'),'http://198.51.100.10');
});

test('LAN and forwarded public port support real forms while Host and per-host Origin remain strict',async t=>{
  const directory=testDirectory(),port=await freePort();
  const origin=`http://127.0.0.1:${port}`;
  const lan='http://192.0.2.10:3091',wan='http://198.51.100.10';
  const runtime=await createApp({databasePath:join(directory,'network.sqlite'),origin,allowedOrigins:[origin,lan,wan]});
  const server=runtime.app.listen(port,'127.0.0.1');
  await new Promise(resolve=>server.once('listening',resolve));
  t.after(async()=>{await new Promise(resolve=>server.close(resolve));runtime.close();removeTestDirectory(directory);});
  const send=(path,host,{method='GET',headers={},body}={})=>new Promise((resolve,reject)=>{
    const req=request(origin+path,{method,headers:{Host:host,...headers}},res=>{
      let html='';res.setEncoding('utf8');res.on('data',chunk=>{html+=chunk;});
      res.on('end',()=>resolve({status:res.statusCode,headers:res.headers,html}));
    });
    req.on('error',reject);req.end(body);
  });
  assert.equal((await send('/','untrusted.invalid')).status,400);
  assert.equal((await send('/','untrusted.invalid',{headers:{'X-Forwarded-Host':new URL(lan).host}})).status,400);
  assert.equal((await send('/',new URL(lan).host,{headers:{'Sec-Fetch-Site':'cross-site'}})).status,403);
  for(const [i,address] of [lan,wan].entries()) {
    const host=new URL(address).host;
    for (const asset of ['/assets/site.css', '/assets/catalog.css']) {
      const stylesheet=await send(asset,host);
      assert.equal(stylesheet.status,200);
      assert.match(stylesheet.headers['content-type'],/^text\/css(?:;|$)/);
      assert.doesNotMatch(stylesheet.html,/<html|<!doctype/i,'a stylesheet must not be an HTML error page');
    }
    const emblem=await send('/assets/mark.svg',host);
    assert.equal(emblem.status,200);assert.match(emblem.headers['content-type'],/^image\/svg\+xml(?:;|$)/);
    const page=await send('/register',host);assert.equal(page.status,200);
    const cookie=page.headers['set-cookie'][0].split(';')[0];
    const csrf=page.html.match(/name="csrf" value="([A-Za-z0-9_-]{43})"/)[1];
    const password=randomBytes(24).toString('base64url');
    const data={csrf,email:`network_${i}@example.test`,nickname:`network_${i}`,display_name:'Проверка сети',password,password_confirm:password};
    const post=(values,source=address)=>send('/register',host,{method:'POST',headers:{Cookie:cookie,Origin:source,'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams(values).toString()});
    assert.equal((await post(data,i===0?wan:lan)).status,403,'another allowlisted origin must not match this Host');
    assert.equal((await post({...data,csrf:'wrong'})).status,403);
    assert.equal((await post(data,'http://untrusted.invalid')).status,403);
    const registered=await post(data);assert.equal(registered.status,303);assert.equal(registered.headers.location,'/account?welcome=1');
    const signedCookie=registered.headers['set-cookie'][0].split(';')[0];
    const profile=await send('/api/profile',host,{headers:{Cookie:signedCookie}});assert.equal(profile.status,200);
    assert.equal(JSON.parse(profile.html).profile.username,`network_${i}`);
    const login=await send('/login',host);const loginCookie=login.headers['set-cookie'][0].split(';')[0];
    const loginCsrf=login.html.match(/name="csrf" value="([A-Za-z0-9_-]{43})"/)[1];
    const loggedIn=await send('/login',host,{method:'POST',headers:{Cookie:loginCookie,Origin:address,'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({csrf:loginCsrf,email:`network_${i}@example.test`,password}).toString()});
    assert.equal(loggedIn.status,303);assert.equal(loggedIn.headers.location,'/account');
  }
  assert.equal(runtime.store.db.prepare('SELECT COUNT(*) AS count FROM users').get().count,2);
});
