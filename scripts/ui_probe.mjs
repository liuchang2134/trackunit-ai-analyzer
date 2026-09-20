/**
 * Local UI probe over the Chrome DevTools Protocol.
 *
 * Purpose: load a localhost page that this project already serves, capture a
 * screenshot, and read back layout facts (horizontal overflow, text widths).
 * This talks to a normal page over loopback only. It deliberately does not
 * open chrome-extension:// URLs, and it does not touch the production
 * platforms; the installed sidebar still has to be verified in real Chrome.
 *
 * Usage:
 *   node scripts/ui_probe.mjs --url <url> --out <png> [--width 1440] [--height 1000]
 *                            [--full] [--wait <ms>] [--eval "<expression>"]
 */
import { spawn } from 'node:child_process';
import { mkdirSync, writeFileSync, existsSync, rmSync, readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, '..');

const CHROME_CANDIDATES = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  `${process.env.LOCALAPPDATA}/Google/Chrome/Application/chrome.exe`,
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
];

function parseArgs(argv) {
  const out = { width: 1440, height: 1000, wait: 2500, full: false, url: 'http://127.0.0.1:8890/assistant-ui/' };
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    const val = argv[i + 1];
    if (key === '--full') { out.full = true; continue; }
    if (key === '--url') { out.url = val; i += 1; continue; }
    if (key === '--out') { out.out = val; i += 1; continue; }
    if (key === '--width') { out.width = Number(val); i += 1; continue; }
    if (key === '--height') { out.height = Number(val); i += 1; continue; }
    if (key === '--wait') { out.wait = Number(val); i += 1; continue; }
    if (key === '--eval') { out.eval = val; i += 1; continue; }
  }
  return out;
}

function findChrome() {
  for (const candidate of CHROME_CANDIDATES) {
    if (candidate && existsSync(candidate)) return candidate;
  }
  throw new Error('No Chrome or Edge binary found');
}

async function waitForDevtools(port, timeoutMs = 20000) {
  const deadline = Date.now() + timeoutMs;
  let lastError;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`http://127.0.0.1:${port}/json/version`);
      if (res.ok) return await res.json();
    } catch (error) { lastError = error; }
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error(`DevTools endpoint not ready: ${lastError?.message ?? 'timeout'}`);
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

const OVERFLOW_PROBE = `(() => {
  const de = document.documentElement;
  const offenders = [];
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    if (r.right > de.clientWidth + 1 || r.left < -1) {
      const style = getComputedStyle(el);
      if (style.position === 'fixed') continue;
      offenders.push({
        tag: el.tagName.toLowerCase(),
        id: el.id || null,
        cls: (typeof el.className === 'string' ? el.className : '').slice(0, 70) || null,
        left: Math.round(r.left), right: Math.round(r.right), width: Math.round(r.width),
      });
    }
  }
  return {
    viewport: { w: window.innerWidth, h: window.innerHeight },
    docScrollWidth: de.scrollWidth,
    docClientWidth: de.clientWidth,
    horizontalOverflow: de.scrollWidth - de.clientWidth,
    bodyScrollHeight: document.body.scrollHeight,
    offenders: offenders.slice(0, 25),
  };
})()`;

async function main() {
  const args = parseArgs(process.argv);
  const chrome = findChrome();
  const port = 9333 + Math.floor(Math.random() * 500);
  const profile = `${tmpdir()}/jilian-ui-probe-${Date.now()}`;
  mkdirSync(profile, { recursive: true });

  const child = spawn(chrome, [
    '--headless=new',
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profile}`,
    '--no-first-run', '--no-default-browser-check',
    '--disable-extensions', '--hide-scrollbars=false',
    '--force-device-scale-factor=1',
    `--window-size=${args.width},${args.height}`,
    'about:blank',
  ], { stdio: 'ignore' });

  let exitCode = 0;
  try {
    await waitForDevtools(port);
    const version = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json();
    const cdp = await Cdp.connect(version.webSocketDebuggerUrl);
    const { targetId } = await cdp.send('Target.createTarget', { url: 'about:blank' });
    const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
    const page = targets.find((t) => t.id === targetId);
    const session = await Cdp.connect(page.webSocketDebuggerUrl);

    await session.send('Page.enable');
    await session.send('Runtime.enable');
    // Local assets are edited between runs; a cached copy would make the probe
    // report the previous revision as if it were current.
    await session.send('Network.enable');
    await session.send('Network.setCacheDisabled', { cacheDisabled: true });
    await session.send('Emulation.setDeviceMetricsOverride', {
      width: args.width, height: args.height, deviceScaleFactor: 1, mobile: false,
    });
    await session.send('Page.navigate', { url: args.url });
    await new Promise((r) => setTimeout(r, args.wait));

    const probe = await session.send('Runtime.evaluate', { expression: OVERFLOW_PROBE, returnByValue: true });
    const extra = args.eval
      ? (await session.send('Runtime.evaluate', { expression: args.eval, returnByValue: true, awaitPromise: true })).result?.value
      : undefined;

    const shot = await session.send('Page.captureScreenshot', {
      format: 'png', captureBeyondViewport: !!args.full,
    });
    if (args.out) {
      const outPath = resolve(ROOT, args.out);
      mkdirSync(dirname(outPath), { recursive: true });
      writeFileSync(outPath, Buffer.from(shot.data, 'base64'));
    }
    const errors = session.events
      .filter((e) => e.method === 'Runtime.exceptionThrown')
      .map((e) => e.params.exceptionDetails.exception?.description ?? e.params.exceptionDetails.text);

    console.log(JSON.stringify({
      url: args.url,
      chrome: version.Browser,
      layout: probe.result.value,
      evalResult: extra,
      pageErrors: errors,
      screenshot: args.out ?? null,
    }, null, 2));
  } catch (error) {
    console.error(`probe failed: ${error.message}`);
    exitCode = 1;
  } finally {
    child.kill();
    await new Promise((r) => setTimeout(r, 300));
    try { rmSync(profile, { recursive: true, force: true }); } catch { /* profile cleanup is best effort */ }
  }
  process.exit(exitCode);
}

main();
