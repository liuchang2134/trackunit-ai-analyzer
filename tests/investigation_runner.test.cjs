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
  assert.equal(h.terminal.length, 0, 'a deliberate stop is not an error');
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
