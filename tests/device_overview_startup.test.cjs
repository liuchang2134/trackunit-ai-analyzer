const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../app/assistant_ui/device-overview.js'), 'utf8');
class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.textContent = ''; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; this.textContent = ''; }
  querySelector(tag) { return this.children.find(child => child.tagName === tag) || null; }
}
function harness() {
  let selectedMachine = null;
  const nodes = new Map();
  const get = id => { if (!nodes.has(id)) nodes.set(id, new Element('div')); return nodes.get(id); };
  const metric = new Element('div'); metric.append(new Element('dt'), new Element('dd'));
  get('overview-metrics').append(new Element('div'), new Element('div'), metric);
  get('overview-faults').textContent = 'unchanged';
  const context = vm.createContext({window: {}, selected: () => selectedMachine, $: get,
    document: {createElement: tag => new Element(tag)},
    ResizeObserver: class { observe() {} }});
  vm.runInContext(source, context);
  return {context, get, metric,
    select(machine) { selectedMachine = machine; },
    loadOverview(machineId) {
      context.overviewFixture = {machine_id: machineId, faults: {valid_loaded_records: 0, events: []}};
      vm.runInContext('overview = overviewFixture', context);
    },
    sync(capture) { context.window.syncVisibleTrackunitEvents(capture); },
    visible() { return vm.runInContext('visibleTrackunitEvents', context); }};
}
const capture = asset_id => ({asset_id, faults: [{code: 'SPN 444 / FMI 1', status: 'OPEN',
  description: 'Test fault', displayed_at: '2026-09-24'}], services: []});

test('no selected device: clearing page events before overview initialization does not render or throw', () => {
  const h = harness();
  assert.doesNotThrow(() => h.sync(null));
  assert.equal(h.visible(), null);
  assert.equal(h.get('overview-faults').textContent, 'unchanged');
  assert.equal(h.metric.querySelector('dd').textContent, '');
});

test('undefined selection during startup does not compare missing identities as a loaded machine', () => {
  const h = harness(); h.select(undefined);
  assert.doesNotThrow(() => h.sync(null));
  assert.equal(h.get('overview-faults').textContent, 'unchanged');
});

test('capture arriving before the selected machine overview is retained without early rendering', () => {
  const h = harness(); h.select({machine_id: 'machine-a'});
  const observed = capture('machine-a');
  assert.doesNotThrow(() => h.sync(observed));
  assert.equal(h.visible(), observed);
  assert.equal(h.get('overview-faults').textContent, 'unchanged');
  h.loadOverview('machine-a'); h.sync(observed);
  assert.equal(h.metric.querySelector('dd').textContent, '1 条');
  assert.equal(h.get('overview-faults').children.length, 2);
});

test('switching machines never paints new page events into the prior machine overview', () => {
  const h = harness(); h.select({machine_id: 'machine-a'}); h.loadOverview('machine-a');
  h.sync(capture('machine-a'));
  const priorRows = h.get('overview-faults').children;
  h.select({machine_id: 'machine-b'});
  h.sync(capture('machine-a'));
  assert.equal(h.visible(), null);
  assert.equal(h.get('overview-faults').children, priorRows);
  const next = capture('machine-b'); h.sync(next);
  assert.equal(h.visible(), next);
  assert.equal(h.get('overview-faults').children, priorRows);
  h.loadOverview('machine-b'); h.sync(next);
  assert.notEqual(h.get('overview-faults').children, priorRows);
});

test('loaded same-machine overview updates page fault rows and restores loaded fault count on clear', () => {
  const h = harness(); h.select({machine_id: 'machine-a'}); h.loadOverview('machine-a');
  h.sync(capture('machine-a'));
  assert.equal(h.metric.querySelector('dt').textContent, '页面可见故障');
  assert.equal(h.metric.querySelector('dd').textContent, '1 条');
  assert.equal(h.get('overview-fault-title').textContent, 'Trackunit 页面事件');
  assert.match(h.get('overview-faults').children[1].children[0].textContent, /SPN 444/);
  h.sync(null);
  assert.equal(h.metric.querySelector('dt').textContent, '已载入故障');
  assert.equal(h.metric.querySelector('dd').textContent, '0 条');
  assert.equal(h.get('overview-fault-title').textContent, '故障记录');
  assert.match(h.get('overview-faults').textContent, /当前数据版本未载入故障记录/);
});
