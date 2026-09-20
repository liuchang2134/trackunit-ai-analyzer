/**
 * Verify that the AI's search terms are marked on the right catalog rows.
 *
 * The marking path had never been exercised outside a fake DOM: it runs as a
 * content script on a page that requires the engineer's own XGSS login, so the one
 * claim that matters — "the terms the AI produced land on the rows they refer to" —
 * was untested.
 *
 * This runs the real `extension/xgss-catalog.js` against a local table over real
 * HTTPS at the real hostname. `isXGSS()` requires both the https scheme and
 * `xgss.xcmg.com`, so the fixture is served under that name with
 * `--host-resolver-rules` sending it to loopback; nothing touches the network or the
 * live site. The table deliberately contains rows that must NOT be marked, so a
 * matcher that marks everything fails here.
 *
 *   node scripts/xgss_marking_probe.mjs
 *   node scripts/xgss_marking_probe.mjs --out .tmp/marked.png
 */
import { spawn, spawnSync } from 'node:child_process';
import { createServer } from 'node:https';
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const FIXTURE = resolve(ROOT, '.tmp/xgss-fixture');
const CERT = resolve(ROOT, '.tmp/fixture-cert/cert.pem');
const KEY = resolve(ROOT, '.tmp/fixture-cert/key.pem');
const HOST = 'xgss.xcmg.com';

const CHROME_CANDIDATES = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  `${process.env.LOCALAPPDATA}/Google/Chrome/Application/chrome.exe`,
];

function parseArgs(argv) {
  const args = { port: 443, width: 1000, height: 700, wait: 2200, out: null };
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    if (key === '--port') { args.port = Number(argv[i + 1]); i += 1; }
    else if (key === '--width') { args.width = Number(argv[i + 1]); i += 1; }
    else if (key === '--height') { args.height = Number(argv[i + 1]); i += 1; }
    else if (key === '--wait') { args.wait = Number(argv[i + 1]); i += 1; }
    else if (key === '--out') { args.out = argv[i + 1]; i += 1; }
  }
  return args;
}

function findChrome() {
  for (const candidate of CHROME_CANDIDATES) if (candidate && existsSync(candidate)) return candidate;
  throw new Error('No Chrome binary found');
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

/** The terms a real E4030 run produced, plus the rows they should and should not reach. */
const TERMS = ['ECU fuse', 'fuse blow', 'E4030', 'CANH2', 'CANL2', 'lead wire break',
  'short circuit', 'connector', 'pin rusted', 'seal damaged', 'ECU failure', 'controller fault'];
const MUST_MARK = ['803100048', '803100112', '803100113', '803100220', '803100301'];
const MUST_NOT_MARK = ['803200001', '803200002', '803100049'];

const MARKING_PROBE = `(() => {
  const rowsOf = (selector) => [...document.querySelectorAll(selector)];
  const isXGSS = XGSSCatalog.isXGSS(location.href);
  const result = XGSSCatalog.mark(${JSON.stringify(TERMS)});
  const marked = rowsOf('tr.jilian-ai-mark-row');
  // Read the applied styling BEFORE clearing. Reading it inside the same object
  // literal after clearMarks() had already run reported the cleared state, which made
  // the visual check meaningless. The mark is inline with !important, so computed
  // style is exactly what the engineer sees.
  const markedBackground = marked.length ? getComputedStyle(marked[0]).backgroundColor : null;
  const markedShadow = marked.length ? getComputedStyle(marked[0]).boxShadow : null;
  // Snapshot the raw attributes BEFORE clearing: after clearMarks every mark class,
  // inline style and data attribute is gone by design, so reading them afterwards
  // reports the cleared state and hides whether the mark was applied at all.
  const firstMarkedDump = marked.length ? {
    className: marked[0].className,
    styleAttribute: marked[0].getAttribute('style'),
    hasMarkClass: marked[0].classList.contains('jilian-ai-mark'),
    hasRowClass: marked[0].classList.contains('jilian-ai-mark-row'),
    dataset: marked[0].getAttribute('data-jilian-ai'),
  } : null;
  // Clearing is a separate step so the screenshot taken next still shows the marks.
  window.__clearMarks = () => {
    const count = (() => { XGSSCatalog.clearMarks(document); return rowsOf('tr.jilian-ai-mark-row').length; })();
    return {
      clearedCount: count,
      clearedInlineBackground: marked.length ? marked[0].style.getPropertyValue('background-color') : null,
      clearedInlineShadow: marked.length ? marked[0].style.getPropertyValue('box-shadow') : null,
    };
  };
  const clearedBackground = marked.length ? getComputedStyle(marked[0]).backgroundColor : null;
  // Deterministic check of the two API calls the marking code makes, so a failure
  // can be attributed to the call rather than guessed at.
  const apiProbe = (() => {
    const probe = document.createElement('tr');
    probe.style.setProperty('box-shadow', 'inset 3px 0 0 0 #38c8d8', 'important');
    probe.style.setProperty('background-color', '#0f2c33', 'important');
    const viaSetProperty = {
      shadow: probe.style.getPropertyValue('box-shadow'),
      background: probe.style.getPropertyValue('background-color'),
      backgroundPriority: probe.style.getPropertyPriority('background-color'),
    };
    const probe2 = document.createElement('tr');
    probe2.style.setProperty('background-color', '#0f2c33', 'important');
    const backgroundOnly = probe2.style.getPropertyValue('background-color');
    const probe3 = document.createElement('tr');
    probe3.style.backgroundColor = '#0f2c33';
    const viaProperty = probe3.style.getPropertyValue('background-color');
    return { viaSetProperty, backgroundOnly, viaProperty };
  })();
  return {
    apiProbe,
    href: location.href,
    isXGSS,
    result,
    markedCount: marked.length,
    markedPartNumbers: marked.map((r) => (r.querySelectorAll('td')[2] || {}).textContent || '').map((s) => s.trim()),
    markedFirstCells: marked.map((r) => (r.querySelectorAll('td')[1] || {}).textContent || '').map((s) => s.trim()),
    markedTerms: marked.map((r) => r.getAttribute('data-jilian-ai')),
    markedBackground,
    markedShadow,
    // Read the inline values back too: if the inline background survives but the
    // computed one does not, something else on the page is overriding it.
    markedInlineBackground: marked.length ? marked[0].style.getPropertyValue('background-color') : null,
    markedInlineBackgroundPriority: marked.length ? marked[0].style.getPropertyPriority('background-color') : null,
    headerRowMarked: rowsOf('thead tr.jilian-ai-mark-row').length,
    totalRows: rowsOf('#parts tbody tr').length,
    firstMarkedDump,
  };
})()`;

async function main() {
  const args = parseArgs(process.argv);
  if (!existsSync(CERT) || !existsSync(KEY)) {
    // The fixture needs its own certificate because the reader insists on https.
    const venv = process.platform === 'win32'
      ? resolve(ROOT, '.tmp/venv/Scripts/python.exe')
      : resolve(ROOT, '.tmp/venv/bin/python');
    const made = spawnSync(existsSync(venv) ? venv : 'python',
      [resolve(ROOT, 'scripts/make_fixture_certificate.py')], { stdio: 'inherit' });
    if (made.status !== 0 || !existsSync(CERT)) {
      console.error('could not generate the fixture certificate; run scripts/make_fixture_certificate.py by hand');
      process.exit(1);
    }
  }
  const files = new Map([
    ['/parts', ['index.html', 'text/html; charset=utf-8']],
    ['/', ['index.html', 'text/html; charset=utf-8']],
    ['/xgss-catalog.js', ['xgss-catalog.js', 'application/javascript; charset=utf-8']],
  ]);
  const server = createServer({ cert: readFileSync(CERT), key: readFileSync(KEY) }, (req, res) => {
    const entry = files.get(new URL(req.url, 'https://' + HOST).pathname);
    if (!entry) { res.writeHead(404).end('not found'); return; }
    res.writeHead(200, { 'content-type': entry[1], 'cache-control': 'no-store' });
    res.end(readFileSync(resolve(FIXTURE, entry[0])));
  });
  // `isXGSS()` rejects any URL carrying a port, so the fixture has to be on the https
  // default port. A conflict is reported as a plain sentence rather than a stack trace.
  try {
    await new Promise((done, fail) => {
      server.once('error', (error) => {
        fail(new Error(`cannot listen on 127.0.0.1:${args.port} (${error.code || error.message}). `
          + 'The catalog reader rejects URLs with an explicit port, so the fixture must use the '
          + 'https default port. Free that port and retry.'));
      });
      server.listen(args.port, '127.0.0.1', done);
    });
  } catch (error) {
    console.error(`xgss marking probe stopped: ${error.message}`);
    server.close();
    process.exit(1);
  }

  const chrome = findChrome();
  const port = 9700 + Math.floor(Math.random() * 200);
  const profile = resolve(ROOT, `.tmp/xgss-probe-${process.pid}`);
  mkdirSync(profile, { recursive: true });
  // isXGSS() rejects a URL with an explicit port, so the default https port is
  // used and omitted from the URL, exactly as the live site appears.
  const url = args.port === 443 ? `https://${HOST}/parts` : `https://${HOST}:${args.port}/parts`;
  const report = { fixture: { url, terms: TERMS }, mustMark: MUST_MARK, mustNotMark: MUST_NOT_MARK };

  const child = spawn(chrome, [
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profile}`,
    // Send the real hostname to the local fixture; the page still believes it is XGSS.
    `--host-resolver-rules=MAP ${HOST} 127.0.0.1`,
    '--ignore-certificate-errors',
    '--disable-extensions',
    '--no-first-run', '--no-default-browser-check',
    `--window-size=${args.width},${args.height}`,
    'about:blank',
  ], { stdio: 'ignore' });

  try {
    const version = await waitForDevtools(port);
    report.chrome = version.Browser;
    const created = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: 'PUT' })).json();
    const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
    const target = targets.find((t) => t.id === created.id);
    const session = await Cdp.connect(target.webSocketDebuggerUrl);
    await session.send('Page.enable');
    await session.send('Runtime.enable');
    await session.send('Emulation.setDeviceMetricsOverride', {
      width: args.width, height: args.height, deviceScaleFactor: 1, mobile: false,
    });
    await session.send('Page.navigate', { url });
    await new Promise((r) => setTimeout(r, args.wait));

    const probe = await session.send('Runtime.evaluate', { expression: MARKING_PROBE, returnByValue: true });
    if (probe.exceptionDetails) {
      report.verdict = 'probe_threw';
      report.error = probe.exceptionDetails.exception?.description ?? probe.exceptionDetails.text;
      console.log(JSON.stringify(report, null, 2));
      process.exitCode = 1;
      return;
    }
    const value = probe.result.value;
    report.page = value;

    // The page is still marked at this point: this is the shot that shows the engineer
    // what the AI asked them to look for.
    const shot = await session.send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true });
    if (args.out) {
      const outPath = resolve(ROOT, args.out);
      mkdirSync(dirname(outPath), { recursive: true });
      writeFileSync(outPath, Buffer.from(shot.data, 'base64'));
      report.screenshot = args.out;
    }
    const cleared = await session.send('Runtime.evaluate', {
      expression: 'JSON.stringify(window.__clearMarks())', returnByValue: true,
    });
    Object.assign(value, JSON.parse(cleared.result.value));

    const marked = new Set(value.markedPartNumbers);
    report.checks = {
      url_is_recognised_as_xgss: value.isXGSS === true,
      // If the page were rejected, mark() returns null and nothing else is meaningful.
      mark_returned_a_result: value.result !== null && typeof value.result === 'object',
      every_expected_row_marked: MUST_MARK.every((part) => marked.has(part)),
      no_unrelated_row_marked: MUST_NOT_MARK.every((part) => !marked.has(part)),
      header_row_not_marked: value.headerRowMarked === 0,
      // The mark carries `!important` and a background transition. Asserting on computed
      // style would race that transition — right after clearMarks() the computed
      // background is still mid-fade — so the inline declaration is asserted, plus the
      // shadow's computed value, which has no transition and settles immediately.
      mark_is_visually_applied: Boolean(value.firstMarkedDump?.styleAttribute)
        && /background-color:\s*rgb\(15,\s*44,\s*51\)\s*!important/.test(value.firstMarkedDump.styleAttribute)
        && value.markedShadow !== 'none',
      unmatched_terms_reported: Array.isArray(value.result?.unmatched),
      clear_removes_every_mark: value.clearedCount === 0 && value.firstMarkedDump?.hasMarkClass === true,
      cleared_rows_lose_the_highlight: value.clearedInlineBackground === '',
    };
    const failed = Object.entries(report.checks).filter(([, ok]) => ok === false).map(([name]) => name);
    report.verdict = failed.length ? `failed: ${failed.join(', ')}` : 'all_checks_passed';
    report.loadedWithRealScript = 'extension/xgss-catalog.js';
    console.log(JSON.stringify(report, null, 2));
    if (failed.length) process.exitCode = 1;
  } catch (error) {
    console.error(`xgss marking probe failed: ${error.message}`);
    process.exitCode = 1;
  } finally {
    child.kill();
    server.close();
    await new Promise((r) => setTimeout(r, 400));
    try { rmSync(profile, { recursive: true, force: true }); } catch { /* best effort */ }
  }
}

main();
