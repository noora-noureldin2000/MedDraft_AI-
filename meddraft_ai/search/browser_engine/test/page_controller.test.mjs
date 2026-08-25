import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { chromium } from 'playwright';
import { PageController } from '../dist/page_controller.js';

const FIXTURE = `<!doctype html><html><head><title>Fixture Page</title></head><body>
<nav><a id="navlink" href="/nav">Nav Home</a></nav>
<a id="plain" href="/plain">Plain link</a>
<div style="display:none"><a id="hidden-link" href="/hidden">Hidden link</a></div>
<button aria-hidden="true" id="aria-hidden-btn">Invisible button</button>
<span role="button" id="role-btn">Role button</span>
<div onclick="void(0)" id="onclick-div">Clicky div</div>
<input id="search-box" type="search" placeholder="Search papers">
<select id="opts"><option value="a">Option A</option></select>
<a id="svg-link" href="/svg"><svg width="10" height="10"></svg></a>
</body></html>`;

let browser;
let page;
let controller;

before(async () => {
  browser = await chromium.launch({ headless: true });
  page = await browser.newPage();
  await page.setContent(FIXTURE, { waitUntil: 'load' });
  controller = new PageController();
  controller.attach(page);
});

after(async () => {
  await browser.close();
});

function findByHref(snapshot, href) {
  return snapshot.elements.find((e) => e.href && e.href.endsWith(href));
}

test('indexes visible interactive elements across detection heuristics', async () => {
  const snap = await controller.snapshot();
  assert.ok(findByHref(snap, '/plain'), 'plain link missing');
  assert.ok(findByHref(snap, '/nav'), 'nav link missing');
  assert.ok(findByHref(snap, '/svg'), 'link with svg child missing');
  assert.ok(snap.elements.some((e) => e.tag === 'input'), 'input missing');
  assert.ok(snap.elements.some((e) => e.tag === 'select'), 'select missing');
  assert.ok(snap.elements.some((e) => e.text === 'Role button'), 'role=button span missing');
  assert.ok(snap.elements.some((e) => e.text === 'Clicky div'), 'onclick div missing');
});

test('skips hidden and aria-hidden elements', async () => {
  const snap = await controller.snapshot();
  assert.equal(findByHref(snap, '/hidden'), undefined);
  assert.ok(!snap.elements.some((e) => e.text === 'Invisible button'));
});

test('captures whitelisted attributes on inputs', async () => {
  const snap = await controller.snapshot();
  const input = snap.elements.find((e) => e.tag === 'input');
  assert.equal(input.attrs['type'], 'search');
  assert.equal(input.attrs['placeholder'], 'Search papers');
});

test('first snapshot marks nothing new; unchanged re-snapshot stays clean', async () => {
  const first = await controller.snapshot();
  assert.ok(first.elements.every((e) => !e.isNew), 'baseline must not be starred');
  const second = await controller.snapshot();
  assert.ok(second.elements.every((e) => !e.isNew), 'unchanged DOM must not be starred');
});

test('only newly added elements are starred on change', async () => {
  const before = await controller.snapshot();
  await page.evaluate(() => {
    const a = document.createElement('a');
    a.href = '/fresh';
    a.textContent = 'Fresh arrival';
    document.body.appendChild(a);
  });
  const afterSnap = await controller.snapshot();
  const fresh = findByHref(afterSnap, '/fresh');
  assert.ok(fresh, 'new link not indexed');
  assert.equal(fresh.isNew, true);
  const old = findByHref(afterSnap, '/plain');
  assert.equal(old.isNew, false);
  assert.ok(afterSnap.elements.filter((e) => e.isNew).length === 1);
});

test('serialized output carries header line and indexed element lines', async () => {
  const snap = await controller.snapshot();
  assert.match(snap.serialized, /\[Fixture Page\]/);
  assert.match(snap.serialized, /\[\d+\] <a>/);
  assert.match(snap.serialized, /» \/plain/);
});

test('click resolves by index and reports the element text', async () => {
  const snap = await controller.snapshot();
  const target = findByHref(snap, '/plain');
  const result = await controller.click(target.index);
  assert.match(result.clicked, /Plain link/);
  assert.equal(result.newTabIndex, null);
});

test('stale index after DOM replacement fails fast with guidance', async () => {
  await controller.snapshot();
  await page.evaluate(() => document.body.innerHTML = '<p>wiped</p>');
  await assert.rejects(
    () => controller.click(0),
    /Call state/,
  );
});
