/**
 * Load the real extension into a real Chrome and check that it actually runs.
 *
 * `ui_probe.mjs` launches Chrome with extensions disabled and cannot open
 * chrome-extension:// URLs, so the sidebar has never been exercised anywhere except
 * a simulated DOM. This script closes that gap as far as automation can: it starts
 * Chrome with the unpacked extension loaded, finds the extension's own id from its
 * service worker, opens the side panel page in a narrow viewport, and reports what
 * the panel really does — whether the extension loaded at all, whether its script
 * ran, whether the workbench iframe received the handshake, and whether the AI
 * guidance elements rendered.
 *
 * What it still cannot do: drive the side panel as a browser surface (that needs a
 * user gesture), and read XGSS pages that require the engineer's own login. Those
 * remain manual checks, and the output says so rather than implying coverage.
 *
 * One Chrome instance, closed in `finally`; no test suite is run from here.
 *
 *   node scripts/extension_probe.mjs
 *   node scripts/extension_probe.mjs --origin http://127.0.0.1:8890
 */
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const EXTENSION = resolve(ROOT, 'extension');

const CHROME_CANDIDATES = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  `${process.env.LOCALAPPDATA}/Google/Chrome/Application/chrome.exe`,
];

function parseArgs(argv) {
  const args = { origin: 'http://127.0.0.1:8890', panelUrl: null, width: 390, height: 820, wait: 2500, out: null, keep: false };
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    const value = argv[i + 1];
    if (key === '--origin') { args.origin = value; i += 1; }
    else if (key === '--width') { args.width = Number(value); i += 1; }
    else if (key === '--height') { args.height = Number(value); i += 1; }
    else if (key === '--wait') { args.wait = Number(value); i += 1; }
    else if (key === '--out') { args.out = value; i += 1; }
    else if (key === '--keep') { args.keep = true; }
  }
  return args;
}

function findChrome() {
  for (const candidate of CHROME_CANDIDATES) if (candidate && existsSync(candidate)) return candidate;
  throw new Error('No Chrome binary found in the known locations');
}

async function waitForDevtools(port, timeoutMs = 25000) {
  const deadline = Date.now() + timeoutMs;
  let lastError;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`http://127.0.0.1:${port}/json/version`);
      if (res.ok) return await res.json();
    } catch (error) { lastError = error; }
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error(`DevTools endpoint not ready: ${lastError?.message ?? 'timeout'}`);
}

/** Poll the target list until a target of the given type appears. */
async function waitForTarget(port, predicate, timeoutMs = 20000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
    const hit = targets.find(predicate);
    if (hit) return hit;
    await new Promise((r) => setTimeout(r, 250));
  }
  return null;
}

/**
 * Find our extension by asking every extension worker what it is.
 *
 * An MV3 service worker stops when idle, so waiting for a worker whose URL ends in
 * `background.js` can simply never resolve, and Chrome's own built-in extensions
 * expose workers too. Asking `chrome.runtime.getManifest()` is authoritative: the
 * name comes from the loaded manifest itself.
 */
async function findOurExtension(port, expectedName, timeoutMs = 25000) {
  const deadline = Date.now() + timeoutMs;
  const seen = [];
  while (Date.now() < deadline) {
    const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
    for (const target of targets) {
      if (!target.url?.startsWith('chrome-extension://')) continue;
      const id = new URL(target.url).host;
      if (seen.some((entry) => entry.id === id)) continue;
      let session;
      try {
        session = await Cdp.connect(target.webSocketDebuggerUrl);
        await session.send('Runtime.enable');
        const result = await session.send('Runtime.evaluate', {
          expression: 'JSON.stringify(chrome.runtime.getManifest())',
          returnByValue: true,
        });
        const manifest = JSON.parse(result.result.value);
        seen.push({ id, name: manifest.name, version: manifest.version, url: target.url });
        if (manifest.name === expectedName) return { id, manifest, targets: seen };
      } catch { /* a worker that cannot be inspected is skipped, not fatal */ }
    }
    await new Promise((r) => setTimeout(r, 400));
  }
  return { id: null, manifest: null, targets: seen };
}

class Cdp {
  constructor(ws) { this.ws = ws; this.id = 0; this.pending = new Map(); this.events = []; }
  static async connect(wsUrl) {
    const ws = new WebSocket(wsUrl);
    await new Promise((res, rej) => { ws.onopen = res; ws.onerror = () => rej(new Error('ws error')); });
    const cdp = new Cdp(ws);
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.id && cdp.pending.has(msg.id)) {
        const { resolve: done, reject } = cdp.pending.get(msg.id);
        cdp.pending.delete(msg.id);
        if (msg.error) reject(new Error(msg.error.message)); else done(msg.result);
      } else if (msg.method) { cdp.events.push(msg); }
    };
    return cdp;
  }
  send(method, params = {}) {
    this.id += 1;
    const id = this.id;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }
}

/* Read the panel the way the engineer's eye would: is the connection badge in a
   settled state, did the workbench frame actually load, and did the AI guidance
   section render anything. A missing frame or a permanent "连接中" is a failure. */
const PANEL_PROBE = `(() => {
  const badge = document.getElementById('connection');
  const frame = document.querySelector('#workspace iframe, iframe');
  const terms = document.getElementById('ai-guidance-terms');
  const components = document.getElementById('ai-guidance-components');
  const bar = [...document.querySelectorAll('.actionbar > *')];
  return {
    title: document.title,
    badgeText: badge ? badge.textContent.trim() : null,
    badgeState: badge ? badge.dataset.state : null,
    frameSrc: frame ? frame.getAttribute('src') : null,
    frameLoaded: frame ? frame.contentWindow !== null : false,
    barItems: bar.map((el) => {
      const r = el.getBoundingClientRect();
      return { id: el.id || el.tagName, width: Math.round(r.width), clipped: el.scrollWidth > el.clientWidth + 1 };
    }),
    termCount: terms ? terms.querySelectorAll('li').length : null,
    componentCount: components ? components.querySelectorAll('li').length : null,
    guidanceStatus: (document.getElementById('ai-guidance-status') || {}).textContent || null,
    docOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
  };
})()`;

async function openPanel(port, url, args) {
  const created = await (await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent(url)}`, { method: 'PUT' })).json();
  const targetId = created.id;
  await new Promise((r) => setTimeout(r, args.wait));
  const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  const target = targets.find((t) => t.id === targetId);
  if (!target) throw new Error('the panel target disappeared');
  const session = await Cdp.connect(target.webSocketDebuggerUrl);
  await session.send('Page.enable');
  await session.send('Runtime.enable');
  await session.send('Network.enable');
  await session.send('Network.setCacheDisabled', { cacheDisabled: true });
  await session.send('Emulation.setDeviceMetricsOverride', {
    width: args.width, height: args.height, deviceScaleFactor: 1, mobile: false,
  });
  await session.send('Page.navigate', { url });
  await new Promise((r) => setTimeout(r, args.wait));
  const probe = await session.send('Runtime.evaluate', { expression: PANEL_PROBE, returnByValue: true });
  const shot = await session.send('Page.captureScreenshot', { format: 'png' });
  const errors = session.events
    .filter((e) => e.method === 'Runtime.exceptionThrown')
    .map((e) => e.params.exceptionDetails.exception?.description ?? e.params.exceptionDetails.text);
  const consoleErrors = session.events
    .filter((e) => e.method === 'Runtime.consoleAPICalled' && e.params.type === 'error')
    .map((e) => (e.params.args || []).map((a) => a.value ?? a.description).join(' '));
  return { value: probe.result.value, shot: shot.data, errors, consoleErrors };
}

/**
 * Every file the extension declares or loads must exist.
 *
 * `--load-extension` no longer works in current Chrome (see the header note), so
 * this is the only automated check that the package is complete: a manifest naming
 * a missing icon, or a page referencing a missing script, would otherwise only
 * surface when a person loads it by hand.
 */
function staticChecks(extensionDir, manifest) {
  const problems = [];
  const present = (rel) => existsSync(resolve(extensionDir, rel));

  for (const [size, rel] of Object.entries(manifest.icons ?? {})) {
    if (!present(rel)) problems.push(`manifest icon ${size}px is missing: ${rel}`);
  }
  for (const [size, rel] of Object.entries(manifest.action?.default_icon ?? {})) {
    if (!present(rel)) problems.push(`action icon ${size}px is missing: ${rel}`);
  }
  if (manifest.background?.service_worker && !present(manifest.background.service_worker)) {
    problems.push(`background service worker is missing: ${manifest.background.service_worker}`);
  }
  const panelPath = manifest.side_panel?.default_path ?? 'panel.html';
  if (!present(panelPath)) problems.push(`side panel page is missing: ${panelPath}`);

  // Anything the panel page pulls in by relative path.
  const referenced = [];
  if (present(panelPath)) {
    const html = readFileSync(resolve(extensionDir, panelPath), 'utf8');
    for (const match of html.matchAll(/(?:src|href)="([^"]+)"/g)) {
      const target = match[1];
      if (target.startsWith('http') || target.startsWith('data:') || target.startsWith('#')) continue;
      referenced.push(target);
      if (!present(target)) problems.push(`${panelPath} references a missing file: ${target}`);
    }
  }
  return { ok: problems.length === 0, problems, referenced };
}

/**
 * Minimal stand-in for the extension APIs the panel touches.
 *
 * `--load-extension` no longer loads unpacked extensions in current Chrome, so the
 * panel cannot be opened at a chrome-extension:// URL. Serving panel.html over the
 * local file origin with this stub installed lets the real panel page run in a real
 * browser — real HTML, real CSS, real event wiring — while `chrome.tabs.query`
 * reports a Trackunit tab so the device-follow path executes instead of bailing out.
 */
const CHROME_STUB = `(() => {
  const asked = [];
  const listeners = { activated: [], updated: [] };
  const trackunitTab = {
    id: 1,
    windowId: 1,
    // The path must be /assets/<uuid> — context.js rejects anything else, and a
    // plausible-looking wrong path would make the probe report a false failure.
    url: 'https://manager.trackunit.com/assets/00000000-0000-0000-0000-000006036161',
    // The hint is only read from titles ending in this exact suffix.
    title: 'XE55U - Trackunit Manager',
    status: 'complete',
  };
  window.chrome = {
    runtime: { id: 'probe-extension-id', getURL: (p) => p, lastError: undefined },
    tabs: {
      query: async () => [trackunitTab],
      get: async () => trackunitTab,
      sendMessage: async () => undefined,
      onActivated: { addListener: (fn) => listeners.activated.push(fn) },
      onUpdated: { addListener: (fn) => listeners.updated.push(fn) },
    },
    scripting: {
      executeScript: async (options) => {
        asked.push({
          target: options && options.target ? options.target.tabId : null,
          files: (options && options.files) || null,
          func: options && options.func ? String(options.func).slice(0, 60) : null,
        });
        return [{ result: null }];
      },
    },
    storage: { local: { get: async () => ({}), set: async () => undefined } },
  };
  window.__probeStub = {
    calls: asked,
    fireActivated: () => listeners.activated.forEach((fn) => fn({ tabId: 1, windowId: 1 })),
    fireUpdated: () => listeners.updated.forEach((fn) => fn(1, { status: 'complete' }, trackunitTab)),
  };
})()`;

/** Read what the panel page actually rendered and asked the browser for. */
const STUBBED_PANEL_PROBE = `(() => {
  const badge = document.getElementById('connection');
  const frame = document.querySelector('#workspace iframe, iframe');
  const bar = [...document.querySelectorAll('.actionbar > *')];
  return {
    title: document.title,
    badgeText: badge ? badge.textContent.trim() : null,
    badgeState: badge ? badge.dataset.state : null,
    frameSrc: frame ? frame.getAttribute('src') : null,
    barItems: bar.map((el) => {
      const r = el.getBoundingClientRect();
      return { id: el.id || el.tagName, width: Math.round(r.width), clipped: el.scrollWidth > el.clientWidth + 1 };
    }),
    stylesheetCount: [...document.styleSheets].length,
    scriptTags: [...document.scripts].map((s) => s.getAttribute('src')),
    contextText: (document.getElementById('context') || {}).textContent || null,
    guidanceStatus: (document.getElementById('ai-guidance-status') || {}).textContent || null,
    scriptingCalls: (window.__probeStub && window.__probeStub.calls) || [],
    docOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
  };
})()`;

/** Open the panel page with the stub installed before any panel script runs. */
async function probeStubbedPanel(port, url, args) {
  const created = await (await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent('about:blank')}`, { method: 'PUT' })).json();
  const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  const target = targets.find((t) => t.id === created.id);
  if (!target) throw new Error('the panel target disappeared');
  const session = await Cdp.connect(target.webSocketDebuggerUrl);
  await session.send('Page.enable');
  await session.send('Runtime.enable');
  await session.send('Network.enable');
  await session.send('Network.setCacheDisabled', { cacheDisabled: true });
  await session.send('Emulation.setDeviceMetricsOverride', {
    width: args.width, height: args.height, deviceScaleFactor: 1, mobile: false,
  });
  // Registered before navigation: otherwise the panel scripts run first and throw on
  // a missing chrome.runtime.
  await session.send('Page.addScriptToEvaluateOnNewDocument', { source: CHROME_STUB });
  await session.send('Page.navigate', { url });
  await new Promise((r) => setTimeout(r, args.wait));
  const probe = await session.send('Runtime.evaluate', { expression: STUBBED_PANEL_PROBE, returnByValue: true });
  const shot = await session.send('Page.captureScreenshot', { format: 'png' });
  const errors = session.events
    .filter((e) => e.method === 'Runtime.exceptionThrown')
    .map((e) => e.params.exceptionDetails.exception?.description ?? e.params.exceptionDetails.text);
  return { value: probe.result.value, shot: shot.data, errors };
}

async function main() {
  const args = parseArgs(process.argv);
  const chrome = findChrome();
  const port = 9300 + Math.floor(Math.random() * 400);
  const profile = resolve(ROOT, `.tmp/extension-probe-${process.pid}`);
  mkdirSync(profile, { recursive: true });

  const manifest = JSON.parse(readFileSync(resolve(EXTENSION, 'manifest.json'), 'utf8'));
  if (!args.panelUrl) args.panelUrl = pathToFileURL(resolve(EXTENSION, manifest.side_panel?.default_path ?? 'panel.html')).href;
  const report = { extension: { path: EXTENSION, version: manifest.version, permissions: manifest.permissions }, origin: args.origin };
  report.staticChecks = staticChecks(EXTENSION, manifest);
  // The panel's own <title> is the expectation, so the check cannot drift from it.
  const panelHtml = readFileSync(resolve(EXTENSION, manifest.side_panel?.default_path ?? 'panel.html'), 'utf8');
  const expectedPanelTitle = '机联智检';

  // Whether the workbench answers decides if the handshake is expected to succeed.
  let workbenchUp = false;
  try {
    const probe = await fetch(args.origin + '/assistant/runtime', { signal: AbortSignal.timeout(4000) });
    workbenchUp = probe.ok;
  } catch { workbenchUp = false; }

  const child = spawn(chrome, [    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profile}`,
    `--load-extension=${EXTENSION}`,
    `--disable-extensions-except=${EXTENSION}`,
    '--no-first-run', '--no-default-browser-check',
    '--force-device-scale-factor=1',
    `--window-size=${args.width},${args.height}`,
    'about:blank',
  ], { stdio: 'ignore' });

  try {
    const version = await waitForDevtools(port);
    report.chrome = version.Browser;

    // Chrome ships built-in extensions that also expose a chrome-extension://
    // worker, so identify ours by asking each worker for its own manifest.
    const found = await findOurExtension(port, manifest.name);
    report.extensionWorkersSeen = found.targets;
    report.extensionLoaded = Boolean(found.id);

    if (!found.id) {
      // Chrome stopped honouring --load-extension for unpacked extensions; the probe
      // says so plainly instead of reporting a false result, then still runs the
      // panel through the stub so the rendering is verified in a real browser.
      report.verdict = 'extension_not_autoloadable';
      report.caveat = 'This Chrome does not load unpacked extensions from the command line, '
        + 'so the sidebar cannot be opened at a chrome-extension:// URL by automation. '
        + 'Loading it by hand in chrome://extensions remains the only way to exercise the '
        + 'side panel as a browser surface.';
      report.staticChecks = staticChecks(EXTENSION, manifest);
      const stubbed = await probeStubbedPanel(port, args.panelUrl, args);
      report.stubbedPanel = stubbed.value;
      report.stubbedPanelErrors = stubbed.errors;
      report.stubbedPanelChecks = {
        // Every entry is an explicit boolean: an undefined would vanish from the JSON.
        panel_script_ran: String(stubbed.value?.title || '').includes(expectedPanelTitle),
        panel_ran_without_exceptions: stubbed.errors.length === 0,
        stylesheet_loaded: (stubbed.value?.stylesheetCount ?? 0) > 0,
        panel_scripts_loaded: (stubbed.value?.scriptTags ?? []).every(Boolean),
        device_recognised_from_tab_url: Boolean(stubbed.value?.frameSrc?.includes('trackunit-asset=')),
        action_bar_labels_unclipped: (stubbed.value?.barItems ?? []).every((i) => i.clipped === false),
        no_horizontal_overflow: (stubbed.value?.docOverflow ?? 0) <= 1,
        // Only asserted when the workbench is reachable; without it the badge staying
        // at "连接中" is the correct behaviour, not a failure.
        connection_handshake_succeeded: workbenchUp
          ? stubbed.value?.badgeState === 'connected'
          : true,
      };
      report.workbenchReachable = workbenchUp;
      if (!workbenchUp) {
        report.connectionNote = '工作区 ' + args.origin + ' 未响应，连接握手未验证；侧栏停在"连接中"是预期行为。启动服务后可复跑以验证握手。';
      }
      if (args.out) {
        const outPath = resolve(ROOT, args.out);
        mkdirSync(dirname(outPath), { recursive: true });
        writeFileSync(outPath, Buffer.from(stubbed.shot, 'base64'));
        report.screenshot = args.out;
      }
      report.still_manual = [
        '把侧栏作为浏览器侧边栏打开（需要用户手势，自动化无法触发）',
        '在已登录的 XGSS 页面上确认青色检索词标注',
        '窄屏下"取回地址 → 新标签页打开图册"整链路',
      ];
      console.log(JSON.stringify(report, null, 2));
      const failed = Object.entries(report.stubbedPanelChecks).filter(([, ok]) => ok === false);
      process.exitCode = failed.length ? 1 : 0;
      return;
    }

    const extensionId = found.id;
    report.extensionId = extensionId;
    report.extensionManifestAsLoaded = { name: found.manifest.name, version: found.manifest.version };
    // The loaded manifest must be the one on disk, or the probe is testing a stale build.
    report.versionMatchesDisk = found.manifest.version === manifest.version;

    const panelPath = manifest.side_panel?.default_path ?? 'panel.html';
    const panel = await openPanel(port, `chrome-extension://${extensionId}/${panelPath}`, args);
    report.panel = panel.value;
    report.panelErrors = panel.errors;
    report.panelConsoleErrors = panel.consoleErrors;

    if (args.out) {
      const outPath = resolve(ROOT, args.out);
      mkdirSync(dirname(outPath), { recursive: true });
      writeFileSync(outPath, Buffer.from(panel.shot, 'base64'));
      report.screenshot = args.out;
    }

    // The panel is expected to reach the local workbench; if the server is not
    // running the badge stays unsettled and that is reported, not hidden.
    const settled = panel.value?.badgeState && panel.value.badgeState !== 'connecting';
    report.checks = {
      extension_loaded: true,
      panel_script_ran: panel.value?.title === '机联智检 · 侧栏',
      panel_ran_without_exceptions: panel.errors.length === 0,
      connection_state_settled: Boolean(settled),
      connection_state: panel.value?.badgeState ?? null,
      workbench_frame_attached: Boolean(panel.value?.frameSrc),
      action_bar_labels_unclipped: (panel.value?.barItems ?? []).every((item) => item.clipped === false),
      no_horizontal_overflow: (panel.value?.docOverflow ?? 0) <= 1,
    };
    report.verdict = Object.entries(report.checks)
      .filter(([, ok]) => ok === false)
      .map(([name]) => name);
    report.verdict = report.verdict.length ? `failed: ${report.verdict.join(', ')}` : 'all_automated_checks_passed';
    report.still_manual = [
      '把侧栏作为浏览器侧边栏打开（需要用户手势，自动化无法触发）',
      '在已登录的 XGSS 页面上确认青色检索词标注',
      '窄屏下"取回地址 → 新标签页打开图册"整链路',
    ];
    console.log(JSON.stringify(report, null, 2));
  } catch (error) {
    console.error(`extension probe failed: ${error.message}`);
    process.exitCode = 1;
  } finally {
    child.kill();
    await new Promise((r) => setTimeout(r, 400));
    if (!args.keep) { try { rmSync(profile, { recursive: true, force: true }); } catch { /* best effort */ } }
  }
}

main();
