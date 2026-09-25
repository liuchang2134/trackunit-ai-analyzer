const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const appSource = fs.readFileSync(path.join(__dirname, '../app/assistant_ui/app.js'), 'utf8');
const start = appSource.indexOf('function setView(');
const end = appSource.indexOf('\n}', start) + 2;
assert.ok(start >= 0 && end > start, 'production navigation function must be available');

function harness(classes) {
  const nodes = new Map();
  const node = id => {
    if (!nodes.has(id)) nodes.set(id, { hidden: false, textContent: '' });
    return nodes.get(id);
  };
  const riskCalls = [];
  const notifications = [];
  const context = {
    activeView: 'work', $: node,
    document: {
      documentElement: {classList: {contains: cls => classes.includes(cls)}},
      querySelector: () => node('device'), querySelectorAll: () => [],
      getElementById: node,
    },
    window: {scrollTo() {}, renderRiskDemo: () => riskCalls.push(true)},
    updateDemoDisclosure() {}, updateRuntimeLabel() {}, updateSourceLabel() {}, updateFlowTrack() {},
    notifyPanelView: reason => notifications.push(reason),
  };
  vm.createContext(context);
  vm.runInContext(appSource.slice(start, end), context);
  return {context, node, riskCalls, notifications};
}

test('fault/parts homepage keeps unrelated history and simulation views out of navigation', () => {
  const h = harness(['competition-focus', 'fault-parts-focus']);
  for (const view of ['history', 'can', 'cooling', 'demo', 'work']) {
    h.context.setView(view, {reason: 'restore'});
    assert.equal(h.context.activeView, 'work');
    assert.equal(h.node('work-view').hidden, false);
    assert.equal(h.node('risk-view').hidden, true);
    assert.equal(h.node('history-view').hidden, true);
    assert.equal(h.node('device').hidden, false);
  }
  assert.equal(h.riskCalls.length, 0);
  assert.equal(h.notifications.length, 5);
});

test('removing fault/parts mode preserves the original risk workspace behavior', () => {
  const h = harness(['competition-focus']);
  h.context.setView('risk');
  assert.equal(h.context.activeView, 'risk');
  assert.equal(h.node('risk-view').hidden, false);
  assert.equal(h.node('work-view').hidden, true);
  assert.equal(h.riskCalls.length, 1);
});


test('secondary risk navigation loads observations and returns without replacing the fault state', () => {
  const h = harness(['competition-focus', 'fault-parts-focus']);
  h.context.report = {research_id:'saved-fault',estimate:42};
  h.node('secondary-nav').open = true;
  h.context.setView('risk', {reason:'user'});
  assert.equal(h.context.activeView,'risk');
  assert.equal(h.node('work-view').hidden,true);
  assert.equal(h.node('risk-view').hidden,false);
  assert.equal(h.node('secondary-nav').open,false);
  assert.equal(h.riskCalls.length,1);
  h.context.setView('work', {reason:'user'});
  assert.equal(h.node('work-view').hidden,false);
  assert.equal(h.node('risk-view').hidden,true);
  assert.deepEqual(h.context.report,{research_id:'saved-fault',estimate:42});
});

test('real sensor scripts are reachable from the prediction button and do not load the independent simulation', () => {
  const html=fs.readFileSync(path.join(__dirname,'../app/assistant_ui/index.html'),'utf8');
  const css=fs.readFileSync(path.join(__dirname,'../app/assistant_ui/fault-parts-shell.css'),'utf8');
  assert.match(html,/<button id="risk-open"[^>]*data-view="risk"[^>]*>故障预测<\/button>/);
  assert.match(html,/sensor-series-workspace.css/);
  assert.ok(html.indexOf('src="app.js')<html.indexOf('src="sensor-risk-live.js'));
  assert.ok(html.indexOf('src="sensor-risk-live.js')<html.indexOf('src="sensor-series-workspace.js'));
  assert.doesNotMatch(html,/src="risk-demo.js/);
  assert.doesNotMatch(css,/#risk-view\s*\{\s*display:\s*none/);
  assert.match(appSource,/setView\(\['can','risk'\]\.includes\(activeView\)/);
});
