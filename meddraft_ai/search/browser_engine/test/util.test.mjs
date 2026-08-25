import { test } from 'node:test';
import assert from 'node:assert/strict';
import { withTimeout, jitterDelay } from '../dist/util.js';

test('withTimeout resolves before deadline and returns the value', async () => {
  const result = await withTimeout(Promise.resolve('ok'), 1000, 'fast-op');
  assert.equal(result, 'ok');
});

test('withTimeout rejects with a label-bearing error on expiry', async () => {
  await assert.rejects(
    withTimeout(new Promise(() => {}), 30, 'stuck-op'),
    /Operation timed out after 30ms: stuck-op/,
  );
});

test('withTimeout does not keep the event loop alive after settling', async () => {
  // A ref'd pending timer would hang this process after tests finish; node --test
  // exits only when no ref'd handles remain.
  await withTimeout(new Promise((r) => setTimeout(r, 5)), 60_000, 'should-be-cancelled');
});

test('jitterDelay stays within bounds', async () => {
  const t0 = Date.now();
  await jitterDelay(40, 80);
  const elapsed = Date.now() - t0;
  assert.ok(elapsed >= 40 && elapsed < 500, `elapsed=${elapsed}`);
});
