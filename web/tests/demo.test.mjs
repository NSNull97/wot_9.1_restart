import test from 'node:test';
import assert from 'node:assert/strict';
import { request } from 'node:http';
import { createDemoApp } from '../src/demo-app.mjs';
import { catalog, vehicleImage, mapImage } from '../src/catalog.mjs';

test('public demo serves the real catalog without account forms, sessions or write endpoints', async t => {
  const app = createDemoApp({ origin: 'https://tanks.example.test' });
  const server = app.listen(0, '127.0.0.1');
  await new Promise(resolve => server.once('listening', resolve));
  t.after(() => new Promise(resolve => server.close(resolve)));
  const base = `http://127.0.0.1:${server.address().port}`;
  const send = (path, options = {}) => new Promise((resolve, reject) => {
    const req = request(base + path, { method: options.method || 'GET',
      headers: { host: 'tanks.example.test', ...options.headers } }, res => {
      const chunks = [];
      res.on('data', chunk => chunks.push(chunk));
      res.on('end', () => {
        const body = Buffer.concat(chunks);
        resolve({ status: res.statusCode, headers: new Headers(res.headers),
          text: async () => body.toString('utf8'), json: async () => JSON.parse(body),
          arrayBuffer: async () => body });
      });
    });
    req.on('error', reject);
    req.end(options.body);
  });
  const home = await send('/');
  const html = await home.text();
  assert.equal(home.status, 200);
  assert.equal(home.headers.get('set-cookie'), null);
  assert.match(html, /ДЕМОНСТРАЦИЯ ПРОЕКТА/);
  assert.doesNotMatch(html, /(?:href|action)="\/(?:login|register|account|logout)\b/);
  assert.doesNotMatch(html, /type="password"|name="email"/);
  assert.equal((await send('/', { headers: { 'sec-fetch-site': 'cross-site' } })).status, 200,
    'a shared public link must remain navigable from another website');
  const health = await (await send('/health')).json();
  assert.deepEqual(health, { status: 'ok', scope: 'catalog-demo', accounts: false, game: false });
  const vehicle = catalog.vehicles.find(value => !value.archived && value.name === 'ИС-4');
  assert.ok(vehicle);
  const map = catalog.maps.find(value => value.registered && !value.special && mapImage(value));
  for (const path of ['/vehicles', '/vehicles?nation=ussr&tier=10', `/vehicles/${vehicle.id}`, '/maps', `/maps/${map.id}`]) {
    const response = await send(path);
    assert.equal(response.status, 200, path);
    assert.equal(response.headers.get('set-cookie'), null);
    assert.doesNotMatch(await response.text(), /href="\/(?:login|register|account)\b/);
  }
  const details = await (await send(`/vehicles/${vehicle.id}`)).text();
  const moduleLink = details.match(/href="([^"<>]*\?module=[^"<>]+)"/);
  assert.ok(moduleLink, 'real research tree links must be present');
  const modulePath = new URL(moduleLink[1].replaceAll('&amp;', '&'), `${base}/vehicles/${vehicle.id}`);
  assert.equal((await send(modulePath.pathname + modulePath.search)).status, 200);
  for (const path of [vehicleImage(vehicle).url, mapImage(map).url, '/catalog-media/v1/classes/heavyTank.png']) {
    const response = await send(path);
    assert.equal(response.status, 200, path);
    assert.match(response.headers.get('content-type'), /^image\/png/);
    assert.ok((await response.arrayBuffer()).byteLength > 50);
  }
  for (const path of ['/login', '/register', '/account', '/logout']) {
    assert.equal((await send(path)).status, 410);
    const post = await send(path, { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: 'email=nobody%40example.test&password=not-a-real-secret' });
    assert.equal(post.status, 405);
    assert.equal(post.headers.get('set-cookie'), null);
  }
  assert.equal((await send('/api/game')).status, 404);
  assert.equal((await send('/vehicles?unknown=value')).status, 400);
  assert.equal((await send('/catalog-media/v1/classes/not-a-file.png')).status, 404);
  assert.equal((await send('/.env')).status, 404);
  assert.equal((await send('/', { headers: { host: 'other.example.test', 'x-forwarded-host': 'tanks.example.test' } })).status, 400);
});
