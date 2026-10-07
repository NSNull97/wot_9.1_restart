import test from 'node:test';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import ejs from 'ejs';

// Rendering checks only: no server, account registration or database access.
// Current accepted game-read schema has ammunition=0 in every inventory row.
const template = fileURLToPath(new URL('../views/account.ejs', import.meta.url));
const accountId = 'd19df8cd-0877-4373-b4e2-011084792011';
const vehicle = (name, suffix, health, crewAssigned) => ({
  inventoryItemId: `${accountId}:${suffix}`, displayName: name,
  health, crewAssigned, ammunition: 0,
});

async function render(inventory, snapshotRevision) {
  const game = { state: 'ready', account: { nickname: 'Тестер' },
    resources: { credits: 100000, gold: 0, freeXP: 0 }, inventory,
    statistics: { battles: 0, wins: 0, losses: 0, draws: 0 },
    snapshotRevision, asOf: '2026-10-05T00:00:00.000Z' };
  const before = structuredClone(game);
  const html = await ejs.renderFile(template, {
    title: 'Test account', currentPath: '/account', csrf: 'unit-render-csrf',
    user: { id: accountId, display_name: 'Тестер', display_nickname: 'Тестер',
      email: 'render@example.invalid', created_at: 1791140400000 },
    welcome: false, saved: false, errors: {}, values: {}, game,
  });
  assert.deepEqual(game, before, 'the read-only template must not modify game data');
  return new Map([...html.matchAll(/<dd data-inventory-item="([^"]+)">([^<]*)<\/dd>/g)]
    .map(([, id, text]) => [id, text]));
}

test('profile3 marks only the assigned MS-1 crew while ammunition stays empty', async () => {
  const ms1 = vehicle('МС-1', 'starter-vehicle-v1', 90, true);
  const is7 = vehicle('ИС-7', 'test-is7-v1', 2150, false);
  const rows = await render([ms1, is7], 3);
  assert.equal(rows.size, 2);
  assert.equal(rows.get(ms1.inventoryItemId), 'МС-1 · 90 HP · экипаж назначен · боекомплект не загружен');
  assert.equal(rows.get(is7.inventoryItemId), 'ИС-7 · 2150 HP · экипаж и боекомплект не назначены');
});

test('the previous one-vehicle profile retains its exact unassigned status', async () => {
  const ms1 = vehicle('МС-1', 'starter-vehicle-v1', 90, false);
  const rows = await render([ms1], 1);
  assert.deepEqual([...rows], [[ms1.inventoryItemId, 'МС-1 · 90 HP · экипаж и боекомплект не назначены']]);
});

test('profile2 keeps both previous labels and each vehicle identity unchanged', async () => {
  const ms1 = vehicle('МС-1', 'starter-vehicle-v1', 90, false);
  const is7 = vehicle('ИС-7', 'test-is7-v1', 2150, false);
  const rows = await render([ms1, is7], 2);
  assert.deepEqual([...rows], [
    [ms1.inventoryItemId, 'МС-1 · 90 HP · экипаж и боекомплект не назначены'],
    [is7.inventoryItemId, 'ИС-7 · 2150 HP · экипаж и боекомплект не назначены'],
  ]);
});
