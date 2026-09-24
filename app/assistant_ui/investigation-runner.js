/**
 * Streamed investigation lifecycle for the workbench.
 *
 * One POST returns the live event stream for one run, so the page keeps no
 * server-side handle to look up later. The backend reports real progress: which
 * device read finished, which model decision started. This module renders those
 * events verbatim and never invents progress of its own.
 *
 * Stop and retry map onto the real request lifecycle:
 *  - Stop aborts the request. The server sees the reader go away and cancels the
 *    investigation before its next model call. One provider request already in
 *    flight still finishes there; the UI says so rather than claiming the
 *    upstream call was cut off mid-response.
 *  - Retry aborts anything still running before starting again, so one report can
 *    never be assembled from two runs.
 *  - Switching device or leaving the page aborts too; a late event from a
 *    previous run is dropped by device, so it cannot land on the machine the user
 *    is now looking at.
 */
const InvestigationRunner = (() => {
  const stages = ['prepare', 'reading', 'model_decision', 'finalizing'];
  const stageLabels = {prepare: '准备', reading: '读取设备数据', model_decision: '模型决策', finalizing: '整理报告'};

  /** Split a byte stream of SSE frames into decoded events. */
  function createDecoder(onEvent) {
    let buffer = '';
    return chunk => {
      buffer += chunk;
      let boundary = buffer.indexOf('\n\n');
      while (boundary !== -1) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        for (const line of frame.split('\n')) {
          if (!line.startsWith('data: ')) continue;
          let event;
          try { event = JSON.parse(line.slice(6)); } catch { continue; }
          if (event && event.type) onEvent(event);
        }
        boundary = buffer.indexOf('\n\n');
      }
    };
  }

  function create(options) {
    const url = options.requestUrl || '/assistant/investigate/stream';
    const doFetch = options.fetchImpl || ((input, init) => fetch(input, init));
    const onProgress = options.onProgress || (() => {});
    const onTerminal = options.onTerminal || (() => {});
    const machineKey = options.machineKey || (() => '');

    let controller = null;
    let activeKey = null;
    function release(mine) {
      if (controller !== mine) return false;
      controller = null;
      activeKey = null;
      return true;
    }

    function complete(mine, event) {
      if (release(mine)) onTerminal(event);
    }

    /** Abort the running request. Safe to call when nothing is running. */
    function stop(reason = 'user') {
      if (!controller) return Promise.resolve({stopped: false});
      const active = controller;
      release(active);
      active.abort();
      const message = reason === 'device_changed' ? '设备已切换，本次分析已停止。' : '已停止本次分析；不会再发起新的模型请求。';
      onProgress({type: 'stopped', stage: 'stopped', reason,
        message});
      // The page awaits a terminal event to unlock its form. An aborted fetch
      // alone cannot settle that promise, including before headers arrive.
      onTerminal({type: 'cancelled', reason, message});
      return Promise.resolve({stopped: true});
    }

    /** Called when the device or view changes: nothing from a previous run may land. */
    function detach(reason = 'device_changed') {
      if (!controller) return Promise.resolve({stopped: false});
      return stop(reason);
    }

    async function start(request, key = machineKey()) {
      // Retire synchronously: two starts in the same tick must not both pass
      // an awaited detach before either installs its controller.
      detach();
      activeKey = key;
      controller = new AbortController();
      const mine = controller;
      onProgress({type: 'starting', stage: 'prepare', message: '正在提交分析请求…'});
      let response;
      try {
        response = await doFetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(request), signal: mine.signal});
      } catch (error) {
        complete(mine, {type: 'error', message: `分析请求未能提交：${error.message}`, kind: 'network'});
        return null;
      }
      if (controller !== mine) {
        await response.body?.cancel().catch(() => {});
        return null;
      }
      if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        const message = typeof detail.detail === 'string' ? detail.detail : `分析请求失败 (${response.status})。`;
        complete(mine, {type: 'error', message, kind: detail.provider_error?.kind || 'analysis_incomplete'});
        return null;
      }
      readBody(response, mine);
      return true;
    }

    async function readBody(response, mine) {
      let finished = false;
      const handle = event => {
        if (event.type === 'progress') {
          if (event.stage && !stages.includes(event.stage)) return;
          if (controller === mine) onProgress(event);
          return;
        }
        if (!['result', 'error', 'cancelled'].includes(event.type)) return;
        // result / error / cancelled all end the run. A retired run publishes nothing.
        if (controller !== mine) return;
        finished = true;
        complete(mine, event);
      };
      const decoder = createDecoder(handle);
      try {
        const reader = response.body.getReader();
        const text = new TextDecoder();
        for (;;) {
          const {done, value} = await reader.read();
          if (done) break;
          decoder(text.decode(value, {stream: true}));
        }
      } catch (error) {
        if (finished || controller !== mine) return;
        complete(mine, {type: 'error', kind: 'stream_interrupted',
          message: '分析与服务的连接中断，未收到完整结果。请重试。'});
        return;
      }
      if (finished || controller !== mine) return;
      // The server closed without a terminal event: never treat that as success.
      complete(mine, {type: 'error', kind: 'stream_interrupted',
        message: '分析与服务的连接提前结束，未收到完整结果。请重试。'});
    }

    function isActive() { return Boolean(controller); }

    function matches(key) { return activeKey === null || activeKey === key; }

    return {start, stop, detach, isActive, matches};
  }

  return {create, stageLabels, stages};
})();
if (typeof module !== 'undefined') module.exports = InvestigationRunner;
