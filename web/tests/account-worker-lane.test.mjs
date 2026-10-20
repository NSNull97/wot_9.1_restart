import test from 'node:test';
import assert from 'node:assert/strict';
import { createAccountLane } from '../src/account-worker-lane.mjs';

const gate = () => { let open; const done = new Promise(resolve => { open = resolve; }); return { done, open }; };

test('one account runs its workers strictly in turn and refuses beyond the bound', async () => {
  const lane = createAccountLane(2, 'Crew worker busy');
  const trace = []; const first = gate();
  const a = lane(async () => { trace.push('a:start'); await first.done; trace.push('a:end'); return 'a'; });
  const b = lane(async () => { trace.push('b:start'); return 'b'; });
  await assert.rejects(lane(async () => 'c'), /Crew worker busy/);
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(trace, ['a:start']);
  assert.equal(lane.pending(), 2);
  first.open();
  assert.deepEqual(await Promise.all([a, b]), ['a', 'b']);
  assert.deepEqual(trace, ['a:start', 'a:end', 'b:start']);
  assert.equal(lane.pending(), 0);
});

test('a failed worker releases its account lane', async () => {
  const lane = createAccountLane(1, 'busy');
  await assert.rejects(lane(async () => { throw new Error('worker unavailable'); }), /worker unavailable/);
  assert.equal(await lane(async () => 'next'), 'next');
});

test('different accounts own separate lanes and overlap', async () => {
  const alpha = createAccountLane(2, 'busy'), bravo = createAccountLane(2, 'busy');
  const hold = gate(); let overlapping = false;
  const a = alpha(async () => { await hold.done; return 'alpha'; });
  const b = bravo(async () => { overlapping = alpha.pending() === 1; hold.open(); return 'bravo'; });
  assert.deepEqual(await Promise.all([a, b]), ['alpha', 'bravo']);
  assert.ok(overlapping);
  assert.throws(() => createAccountLane(0, 'busy'), /bound required/);
});
