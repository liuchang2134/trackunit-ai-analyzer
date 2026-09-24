const {test} = require('node:test');
const assert = require('node:assert/strict');

// The module exports itself for tests and also assigns a global for the page.
const Runner = require('../app/assistant_ui/investigation-runner.js');

/** A response body whose frames the test controls, so nothing is timed. */
function bodyStream() {
  let push;
  const stream = new ReadableStream({
    start(controller) {
      push = (frame, {close = false} = {}) => {
        if (close) { controller.close(); return; }
        controller.enqueue(new TextEncoder().encode(frame));
      };
    },
  });
  return {stream, push};
}

function harness({ok = true, status = ok ? 200 : 503, detail = {}} = {}) {
  const bodies = [], calls = [], progress = [], terminal = [];
  const runner = Runner.create({
    fetchImpl: async (url, init) => {
      const {stream, push} = bodyStream();
      calls.push({url, init, push});
      return {ok, status, body: stream, json: async () => detail};
    },
    machineKey: () => 'machine-a',
    onProgress: event => progress.push(event),
    onTerminal: event => terminal.push(event),
  });
  return {runner, bodies, calls, progress, terminal};
}

const frame = event => 'data: ' + JSON.stringify(event) + '\n\n';

async function settle() {
  // Let the reader loop drain the queued frames.
  for (let i = 0; i < 8; i += 1) await new Promise(resolve => setImmediate(resolve));
}

test('one POST carries the run, and progress is forwarded verbatim', async () => {
  const h = harness();
  await h.runner.start({machine_id: 'M-1'}, 'machine-a');
  assert.equal(h.calls[0].url, '/assistant/investigate/stream');
  assert.equal(h.calls[0].init.method, 'POST');
  h.calls[0].push(frame({type: 'progress', stage: 'reading', message: '正在读取设备快照…', step: 1, total: 6}));
  await settle();
  assert.equal(h.progress.at(-1).message, '正在读取设备快照…');
  assert.equal(h.progress.at(-1).stage, 'reading');
  // A stage the backend does not define is dropped rather than rendered.
  h.calls[0].push(frame({type: 'progress', stage: 'made_up', message: '假进度'}));
  await settle();
  assert.equal(h.progress.at(-1).stage, 'reading');
  assert.ok(!h.progress.some(event => event.message === '假进度'));
});

test('only a complete result reaches the terminal handler', async () => {
  const h = harness();
  await h.runner.start({machine_id: 'M-1'}, 'machine-a');
  h.calls[0].push(frame({type: 'progress', stage: 'finalizing', message: '正在整理报告…'}));
  await settle();
  assert.equal(h.terminal.length, 0, 'partial output must not be published');
  h.calls[0].push(frame({type: 'result', report: {status: 'completed', summary: 'ok'}}));
  await settle();
  assert.equal(h.terminal.length, 1);
  assert.equal(h.terminal[0].report.status, 'completed');
  assert.equal(h.runner.isActive(), false);
});

test('a stream that ends without a terminal event is an error, never a success', async () => {
  const h = harness();
  await h.runner.start({machine_id: 'M-1'}, 'machine-a');
  h.calls[0].push(frame({type: 'progress', stage: 'reading', message: '读取中…'}));
  h.calls[0].push('', {close: true});
  await settle();
  assert.equal(h.terminal.length, 1);
  assert.equal(h.terminal[0].type, 'error');
  assert.equal(h.terminal[0].kind, 'stream_interrupted');
  assert.equal(h.runner.isActive(), false);
});

test('stop aborts the real request and reports itself once', async () => {
  const h = harness();
  await h.runner.start({machine_id: 'M-1'}, 'machine-a');
  const signal = h.calls[0].init.signal;
  assert.equal(signal.aborted, false);
  const outcome = await h.runner.stop('user');
  assert.equal(signal.aborted, true, 'the request must actually be aborted');
  assert.equal(outcome.stopped, true);
  assert.equal(h.progress.at(-1).type, 'stopped');
  assert.match(h.progress.at(-1).message, /不会再发起新的模型请求/);
  assert.equal(h.runner.isActive(), false);
  // A second stop is a no-op.
  assert.deepEqual(await h.runner.stop('user'), {stopped: false});
  assert.equal(h.terminal.length, 1, 'stopping must settle the waiting page exactly once');
  assert.equal(h.terminal[0].type, 'cancelled', 'a deliberate stop is not an error');
});

test('an abort is not reported as a provider failure', async () => {
  const h = harness();
  await h.runner.start({machine_id: 'M-1'}, 'machine-a');
  const reading = h.runner.stop('device_changed');
  await reading;
  await settle();
  assert.ok(!h.terminal.some(event => event.type === 'error'));
  assert.match(h.progress.at(-1).message, /设备已切换/);
});

test('a failed submit is reported and leaves nothing active', async () => {
  const h = harness({ok: false, detail: {detail: '服务暂时不可用'}});
  const result = await h.runner.start({machine_id: 'M-1'}, 'machine-a');
  assert.equal(result, null);
  assert.equal(h.terminal.at(-1).type, 'error');
  assert.match(h.terminal.at(-1).message, /服务暂时不可用/);
  assert.equal(h.runner.isActive(), false);
});

test('starting a new run retires the previous one instead of stacking runs', async () => {
  const h = harness();
  await h.runner.start({machine_id: 'M-1'}, 'machine-a');
  const first = h.calls[0].init.signal;
  await h.runner.start({machine_id: 'M-2'}, 'machine-b');
  assert.equal(first.aborted, true, 'the previous request must be aborted');
  assert.equal(h.runner.isActive(), true);
  // A late event from the retired run cannot reach the terminal handler.
  h.calls[0].push(frame({type: 'result', report: {status: 'completed', summary: 'stale'}}));
  await settle();
  assert.ok(!h.terminal.some(event => event.report?.summary === 'stale'));
});

test('detaching on a device change aborts and marks the reason', async () => {
  const h = harness();
  await h.runner.start({machine_id: 'M-1'}, 'machine-a');
  await h.runner.detach('device_changed');
  assert.equal(h.calls[0].init.signal.aborted, true);
  assert.match(h.progress.at(-1).message, /设备已切换/);
  assert.equal(h.runner.isActive(), false);
});

test('the runner knows which device a run belongs to and its stage labels', () => {
  const runner = Runner.create({machineKey: () => 'machine-a'});
  assert.equal(runner.matches('machine-a'), true);
  assert.equal(runner.matches('machine-b'), true, 'an idle runner claims no device');
  assert.deepEqual(Runner.stages, ['prepare', 'reading', 'model_decision', 'finalizing']);
  assert.equal(Runner.stageLabels.model_decision, '模型决策');
});

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return {promise, resolve, reject};
}

test('an old aborted or failed submit cannot retire the replacement request', async () => {
  for (const name of ['AbortError', 'TypeError']) {
    const requests = [], terminal = [];
    const runner = Runner.create({fetchImpl: (_url, init) => {
      const request = {...deferred(), signal: init.signal}; requests.push(request); return request.promise;
    }, onTerminal: event => terminal.push(event)});
    const first = runner.start({}, 'A');
    const second = runner.start({}, 'B');
    assert.equal(requests[0].signal.aborted, true);
    requests[0].reject(Object.assign(new Error('old submit failed'), {name}));
    await first;
    assert.equal(runner.isActive(), true);
    assert.equal(runner.matches('B'), true);
    assert.equal(runner.matches('A'), false);
    const body = bodyStream();
    requests[1].resolve({ok: true, body: body.stream}); await second;
    body.push(frame({type: 'result', report: {machine_id: 'B'}}), {});
    body.push('', {close: true}); await settle();
    assert.deepEqual(terminal.map(event => event.type), ['cancelled', 'result']);
    assert.equal(terminal.at(-1).report.machine_id, 'B');
  }
});

test('an old HTTP error body cannot overwrite a newer run while JSON is pending', async () => {
  const detail = deferred(), next = bodyStream(), terminal = [];
  let calls = 0;
  const runner = Runner.create({fetchImpl: async () => ++calls === 1
    ? {ok: false, status: 503, json: () => detail.promise}
    : {ok: true, body: next.stream}, onTerminal: event => terminal.push(event)});
  const old = runner.start({}, 'A'); await settle();
  await runner.start({}, 'B');
  detail.resolve({detail: 'old provider failure'}); await old;
  assert.equal(runner.isActive(), true);
  next.push(frame({type: 'result', report: {machine_id: 'B'}}));
  next.push('', {close: true}); await settle();
  assert.deepEqual(terminal.map(event => event.type), ['cancelled', 'result']);
});

test('two starts in the same tick abort the first and discard its late response', async () => {
  const requests = [], progress = [], terminal = [];
  const runner = Runner.create({fetchImpl: (_url, init) => {
    const request = {...deferred(), signal: init.signal}; requests.push(request); return request.promise;
  }, onProgress: event => progress.push(event), onTerminal: event => terminal.push(event)});
  const first = runner.start({}, 'A');
  const second = runner.start({}, 'B');
  assert.equal(requests.length, 2);
  assert.equal(requests[0].signal.aborted, true);
  let discarded = false;
  requests[0].resolve({ok: true, body: new ReadableStream({cancel() { discarded = true; }})});
  await first;
  assert.equal(discarded, true);
  assert.equal(runner.isActive(), true);
  const next = bodyStream(); requests[1].resolve({ok: true, body: next.stream}); await second;
  next.push(frame({type: 'result', report: {machine_id: 'B'}}));
  next.push('', {close: true}); await settle();
  assert.deepEqual(terminal.map(event => event.type), ['cancelled', 'result']);
  assert.equal(progress.filter(event => event.type === 'stopped').length, 1);
});

// Execute the real form handler and lifecycle wrapper, not a second version of
// their logic. Only DOM nodes, clocks and the network are replaced.
function appHarness(fetchImpl, {competitionFocus = false} = {}) {
  const fs = require('node:fs'), vm = require('node:vm');
  const source = fs.readFileSync(require.resolve('../app/assistant_ui/app.js'), 'utf8');
  const formStart = source.indexOf("$('form').onsubmit=async e=>{");
  const formEnd = source.indexOf('\n/**', formStart);
  const lifecycleStart = source.indexOf('let investigationRunner=null');
  const lifecycleEnd = source.indexOf('\n/**\n * Render one validated investigation report.', lifecycleStart);
  assert.ok(formStart >= 0 && formEnd > formStart && lifecycleStart >= 0 && lifecycleEnd > lifecycleStart);
  const nodes = new Map(), timers = new Set(), renders = [], requests = [];
  const get = id => {
    if (!nodes.has(id)) nodes.set(id, {value: '', disabled: false, hidden: true, dataset: {}, textContent: '',
      attributes: {}, listeners: {}, setAttribute(key, value) { this.attributes[key] = value; },
      getAttribute(key) { return this.attributes[key] ?? null; },
      addEventListener(name, handler) { this.listeners[name] = handler; }, focus() {}, scrollIntoView() {}});
    return nodes.get(id);
  };
  get('question').value = 'Test communication fault';
  const previousReport = {summary: 'previous successful report'};
  const context = {Date, Promise, $: get,
    setInterval: callback => {timers.add(callback); return callback;}, clearInterval: token => timers.delete(token),
    document: {documentElement: {dataset: {}, classList: {contains: name => competitionFocus && name === 'competition-focus'}}}, location: {hash: ''},
    selected: () => ({machine_id: 'SIM-TEST', selection_id: 'SIM-TEST'}),
    report: previousReport, defaultSource: 'demo', priorRecordId: null, taskQuestions: {}, pendingPlatformContext: false,
    refresh: async () => {}, setView() {}, renderInvestigationReport: value => renders.push(value),
    InvestigationRunner: {create: options => Runner.create({...options, fetchImpl: (url, init) => {
      requests.push({url, init}); return fetchImpl(url, init);
    }})},
  };
  vm.runInNewContext(source.slice(lifecycleStart, lifecycleEnd) + '\n' + source.slice(formStart, formEnd), context);
  return {context, get, timers, renders, requests, previousReport,
    submit: () => get('form').onsubmit({preventDefault() {}}),
    stop: () => get('ai-progress-stop').listeners.click()};
}

async function assertSettles(promise) {
  let settled = false;
  promise.then(() => {settled = true;}, () => {settled = true;});
  await settle();
  assert.equal(settled, true, 'the form must finish without waiting for a cancelled provider response');
  await promise;
}

function assertUnlocked(h) {
  for (const id of ['run', 'machine', 'refresh', 'question', 'task']) assert.equal(h.get(id).disabled, false, id);
  assert.equal(h.get('form').getAttribute('aria-busy'), 'false');
  assert.equal(h.get('run').textContent, '开始分析');
  assert.equal(h.get('ai-progress').hidden, true);
  assert.equal(h.get('elapsed').hidden, true);
  assert.equal(h.timers.size, 0);
}

test('stopping an accepted stream unlocks the actual form and retains its previous report', async () => {
  const body = bodyStream();
  const h = appHarness(async () => ({ok: true, body: body.stream}));
  const submission = h.submit(); await settle();
  body.push(frame({type: 'progress', stage: 'reading', message: 'reading'})); await settle();
  assert.equal(h.get('run').disabled, true);
  assert.equal(h.get('ai-progress').hidden, false);
  await h.stop(); await assertSettles(submission); assertUnlocked(h);
  assert.equal(h.context.report, h.previousReport);
  body.push(frame({type: 'result', report: {summary: 'late cancelled result'}}));
  body.push('', {close: true}); await settle();
  assert.equal(h.renders.length, 0);
  assert.equal(h.get('status').dataset.state, 'idle');
});

test('stopping before response headers unlocks immediately and a fresh submit succeeds', async () => {
  const old = deferred(), next = bodyStream(); let calls = 0;
  const h = appHarness(() => ++calls === 1 ? old.promise : Promise.resolve({ok: true, body: next.stream}));
  const submission = h.submit(); await settle();
  await h.stop(); await assertSettles(submission); assertUnlocked(h);
  const replacement = h.submit(); await settle();
  old.reject(Object.assign(new Error('old abort'), {name: 'AbortError'})); await settle();
  assert.equal(h.get('run').disabled, true, 'late old cleanup must not unlock the replacement');
  next.push(frame({type: 'result', report: {summary: 'replacement report'}}));
  next.push('', {close: true}); await assertSettles(replacement);
  assertUnlocked(h);
  assert.equal(h.renders.length, 1);
  assert.equal(h.renders[0].summary, 'replacement report');
});

test('submit failures remain visible and unlock the actual form', async () => {
  for (const failure of ['network', 'http']) {
    const h = appHarness(async () => {
      if (failure === 'network') throw new Error('test network unavailable');
      return {ok: false, status: 503, json: async () => ({detail: 'test provider unavailable'})};
    });
    await assertSettles(h.submit()); assertUnlocked(h);
    assert.equal(h.get('status').dataset.state, 'error');
    assert.match(h.get('status').textContent, /test (network|provider) unavailable/);
    assert.equal(h.context.report, h.previousReport);
  }
});

test('the busy form ignores repeat submits and clears a deferred device change after stop', async () => {
  const old = deferred();
  const h = appHarness(() => old.promise);
  let refreshes = 0;
  h.context.refresh = async force => {assert.equal(force, true); refreshes++;};
  const first = h.submit(); await settle();
  await h.submit();
  assert.equal(h.requests.length, 1, 'requestSubmit must not stack analyses while busy');
  h.context.pendingPlatformContext = true;
  await h.stop(); await assertSettles(first); assertUnlocked(h);
  assert.equal(refreshes, 1);
  assert.equal(h.context.pendingPlatformContext, false);
  old.reject(Object.assign(new Error('old abort'), {name: 'AbortError'})); await settle();
});

for (const competitionFocus of [true, false]) {
  test(`${competitionFocus ? 'competition' : 'full'} mode submits the real form with the intended observation and feedback scope`, async () => {
    for (const [faultField, fault] of [
      ['manual_fault', {code: 'H10101', model: 'TV12U', version: '260224', applicability_confirmed: true}],
      ['engineering_fault', {code: 'E4030', model: 'XE55U', configuration: 'unknown', source: 'test'}],
    ]) {
      const body = bodyStream();
      const h = appHarness(async () => ({ok: true, body: body.stream}), {competitionFocus});
      const machine = {machine_id: 'REAL-DEVICE', selection_id: 'dataset:verified-device', dataset_id: 'verified-device'};
      h.context.selected = () => machine;
      h.context.priorRecordId = 'previous-report-with-saved-feedback';
      h.context[faultField === 'manual_fault' ? 'getManualFaultReference' : 'getEngineeringFault'] = () => fault;
      h.get('question').value = '  请分析当前故障，并核对适配。  ';
      h.get('observations').value = '之前保留的现场观察，不属于当前展示流程。';
      h.get('task').value = 'parts';
      h.get('language').value = 'en';

      const submission = h.submit(); await settle();
      assert.equal(h.requests.length, 1);
      assert.equal(h.requests[0].url, '/assistant/investigate/stream');
      assert.equal(h.requests[0].init.method, 'POST');
      const payload = JSON.parse(h.requests[0].init.body);
      assert.deepEqual(payload, {
        machine_id: machine.machine_id,
        dataset_id: machine.dataset_id,
        question: '请分析当前故障，并核对适配。',
        observations: competitionFocus ? '' : h.get('observations').value,
        language: 'en',
        task: 'parts',
        prior_record_id: competitionFocus ? null : 'previous-report-with-saved-feedback',
        [faultField]: fault,
      });
      assert.equal(h.get('observations').value, '之前保留的现场观察，不属于当前展示流程。', 'request filtering must preserve stored inputs');
      assert.equal(h.context.priorRecordId, 'previous-report-with-saved-feedback', 'request filtering must preserve the original record reference');

      body.push(frame({type: 'result', report: {machine_id: machine.machine_id, summary: 'current report', history_saved: true}}));
      body.push('', {close: true});
      await assertSettles(submission); assertUnlocked(h);
      assert.equal(h.renders.length, 1);
      assert.equal(h.renders[0].summary, 'current report');
    }
  });
}
