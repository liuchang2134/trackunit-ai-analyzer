const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../app/assistant_ui/xgss-viewer.js'), 'utf8');

/**
 * Run the viewer against a fake page and report what it did to the dialog.
 *
 * The photographed failure was this dialog embedding the whole XGSS site inside
 * the ~360px side panel, producing stacked scrollbars around an unreadable
 * table. These tests assert the contract that replaced it: below the embed
 * threshold no iframe is ever pointed at XGSS, and the address is handed over as
 * a single next action instead.
 */
function runViewer({width, openSite = false}) {
  const nodes = [];
  function element(tag) {
    const classes = new Set();
    const el = {
      tag, children: [], textContent: '', className: '', type: '', title: '', href: '', src: '',
      disabled: false, hidden: false, required: false, checked: true, open: false, id: '',
      style: {}, dataset: {}, attributes: {},
      classList: {
        add: (...names) => names.forEach(name => classes.add(name)),
        remove: (...names) => names.forEach(name => classes.delete(name)),
        contains: name => classes.has(name),
        toString: () => [...classes].join(' '),
      },
      append(...kids) { this.children.push(...kids); },
      replaceChildren(...kids) { this.children = [...kids]; },
      setAttribute(k, v) { this.attributes[k] = v; },
      getAttribute(k) { return this.attributes[k] ?? null; },
      removeAttribute(k) { delete this.attributes[k]; },
      addEventListener() {}, showModal() { el.modalOpen = true; }, close() { el.modalOpen = false; },
      remove() {}, focus() {}, querySelector() { return null; }, querySelectorAll() { return []; },
    };
    // className reflects classList, which is what the dialog code uses.
    Object.defineProperty(el, 'className', {
      get: () => [...classes].join(' '),
      set: value => { classes.clear(); String(value).split(/\s+/).filter(Boolean).forEach(name => classes.add(name)); },
    });
    nodes.push(el);
    return el;
  }
  const byId = new Map();
  const document = {
    createElement: element,
    createTextNode: value => ({text: value}),
    getElementById: id => byId.get(id) || null,
    body: element('body'),
    documentElement: {clientWidth: width},
  };
  const alerts = [];
  const sandbox = {
    document,
    window: {innerWidth: width, open: (url) => { alerts.push(url); return null; }},
    location: {hash: '', search: ''},
    URL,
    URLSearchParams,
    console,
    $: id => byId.get(id) || (byId.set(id, element('div')), byId.get(id)),
    // The status call resolves immediately; the submit call returns the entry URL.
    api: async (route) => (route === '/assistant/xgss/status'
      ? {reason: '本机已配置', fault_ready: true, catalog_ready: true}
      : {url: 'https://xgss.xcmg.com/catalog/abc', message: '已取得官方图册地址。'}),
  };
  sandbox.globalThis = sandbox;
  vm.runInNewContext(source, sandbox);
  return {
    document, sandbox, nodes, alerts,
    openViewer: (machine, code) => {
      // createXGSSControls wires the button; use it the way the workbench does.
      const controls = sandbox.window.createXGSSControls(machine, code);
      const button = controls.children.find(child => child.className === 'fault-context-actions').children
        .find(candidate => candidate.onclick);
      button.disabled = false;
      button.onclick();
    },
    frame: () => nodes.find(node => node.tag === 'iframe'),
    dialog: () => nodes.find(node => node.tag === 'dialog'),
    submit: async () => {
      // The dialog enables its submit button only after the status call resolves,
      // so the test has to let that microtask land before submitting.
      await new Promise(resolve => setImmediate(resolve));
      const dialog = nodes.find(node => node.tag === 'dialog');
      const form = dialog.children.find(child => child.tag === 'form');
      const button = form.children.find(child => child.tag === 'button');
      assert.equal(button.disabled, false, 'the dialog must allow submitting once the VIN is confirmed');
      return form.onsubmit({preventDefault() {}});
    },
  };
}

const machine = {machine_id: 'XUGC055UARKA02003', serial_number: 'XUGC055UARKA02003',
  model: 'XE55U', source: 'trackunit_cache'};

test('at side-panel widths the dialog never points an iframe at the official catalog', async () => {
  for (const width of [320, 360, 390, 480, 600, 759]) {
    const harness = runViewer({width});
    harness.openViewer(machine, null);
    await harness.submit();
    assert.equal(harness.frame().src, '', `${width}px must not load the catalog into the panel`);
    assert.equal(harness.frame().hidden, true, `${width}px must keep the iframe hidden`);
    assert.match(harness.dialog().className, /xgss-dialog-narrow/);
  }
});

test('at side-panel widths the address is offered as one explicit next action', async () => {
  const harness = runViewer({width: 390});
  harness.openViewer(machine, null);
  await harness.submit();
  const dialog = harness.dialog();
  const actions = dialog.children.find(child => child.className === 'fault-context-actions');
  const open = actions.children.find(child => child.tag === 'button' && /在新标签页打开图册/.test(child.textContent));
  assert.ok(open, 'the panel must offer to open the catalog in its own tab');
  open.onclick();
  assert.deepEqual(harness.alerts, ['https://xgss.xcmg.com/catalog/abc']);
  // The AI guidance stays useful: the dialog explains where the terms live.
  const status = dialog.children.find(child => child.tag === 'p' && /独立标签页/.test(child.textContent));
  assert.ok(status, 'the dialog must say the terms stay on the panel side');
});

test('a standalone wide page still embeds the catalog', async () => {
  for (const width of [760, 1024, 1440]) {
    const harness = runViewer({width});
    harness.openViewer(machine, null);
    await harness.submit();
    assert.equal(harness.frame().src, 'https://xgss.xcmg.com/catalog/abc',
      `${width}px is wide enough to embed`);
    assert.equal(harness.frame().hidden, false);
    assert.doesNotMatch(harness.dialog().className, /xgss-dialog-narrow/);
  }
});
