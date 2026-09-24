(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const {atTime, clock, visibleEvidence} = CanReplayCore;
  let data, cursor = 120, selected = 'coolant', playing = false, loadVersion = 0, busy = false, report = null;
  const chart = echarts.init($('trend'));
  const embedded = window.parent !== window && new URLSearchParams(location.search).get('embedded') === '1';
  document.documentElement.classList.toggle('can-embedded', embedded);
  let hostAsset = null;
  const colors = {coolant: '#51c9ff', rpm: '#799bff', oil: '#50d3b5', voltage: '#c4a0ff', load: '#f0ba66', fuel: '#77bcff', hours: '#a2bccf'};
  const el = (tag, text, className) => { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (className) node.className = className; return node; };
  const format = n => n === null || n === undefined ? '—' : Number(n.toFixed(2)).toLocaleString('zh-CN');
  function pause() { playing = false; $('play').textContent = '▶ 播放'; }
  function currentSignal(key) { return data?.signals.find(s => s.key === key); }
  function clearAI() {
    report = null;
    $('ai-result').replaceChildren();
    const empty = el('div', undefined, 'empty-ai');
    empty.append(el('span', '01 → 02 → 03'), el('p', '信号趋势 · 原因假设 · 验证步骤'), el('small', '每项建议都附有数据依据。'));
    $('ai-result').append(empty);
    $('part-terms').replaceChildren(el('span', '分析后生成检索词'));
    $('ai-status').textContent = '';
  }
  function setBusy(value) {
    busy = value;
    $('analyze').disabled = value || !data;
    $('stop').hidden = !value;
    $('analyze').textContent = value ? '分析中…' : data?.scenario === 'synthetic' ? '分析当前模拟工况 →' : '切换模拟并分析 →';
  }
  const runner = InvestigationRunner.create({
    requestUrl: '/assistant/can-replay/synthetic-analysis',
    machineKey: () => `${loadVersion}:${data?.scenario}`,
    onProgress: event => { $('ai-status').textContent = event.message || ''; },
    onTerminal: event => {
      setBusy(false);
      if (event.type === 'result') {
        report = event.report;
        $('ai-status').textContent = `已完成 · ${report.provider} / ${report.model} · 模拟 ${clock(report.input.at)} 时刻`;
        renderReport(report);
      } else $('ai-status').textContent = event.message || '分析未完成，可重试。';
    }
  });
  function openDetails(title, nodes) {
    $('frame-dialog').querySelector('h2').textContent = title;
    $('frame-detail').replaceChildren(...nodes);
    $('frame-dialog').showModal();
  }
  function showFrame(signal, point) {
    if (data.scenario === 'synthetic') {
      openDetails('模拟数据依据', [el('p', `${signal.name} · ${point.t.toFixed(3)} s`), el('pre', `${format(point.value)} ${signal.unit}`), el('p', '此读数由独立公式生成，没有对应的实车 CAN 帧。')]);
      return;
    }
    openDetails('原始帧证据', [el('p', `${data.source_file} · 第 ${point.line} 行`),
      el('pre', `${point.t.toFixed(4)} s    ${point.can_id}\n${point.raw}`),
      el('p', `${signal.name} / SPN ${signal.spn} / PGN ${signal.pgn}`),
      el('strong', `字节 ${signal.byte_start}–${signal.byte_start + signal.byte_length - 1}，小端整数 × ${signal.factor} ${signal.offset >= 0 ? '+' : '−'} ${Math.abs(signal.offset)} = ${format(point.value)} ${signal.unit}`),
      el('p', `${data.reference_workbook} · References 第 ${signal.reference_row} 行。使用通用 J1939 定义，未套用起重机专有 CAN Profile。`),
      el('p', '当前曲线点和本页读数都使用这一秒的首帧。缺测不补零。')]);
  }
  function renderMetrics() {
    $('metrics').replaceChildren(...['coolant', 'rpm', 'oil', 'voltage'].map(key => {
      const s = currentSignal(key), point = atTime(s, cursor);
      const box = el('div', undefined, 'metric');
      const label = el('div', undefined, 'metric-label'); label.append(el('span', s.name), el('span', data.scenario === 'recorded' ? `SPN ${s.spn}` : 'SIM'));
      const value = el('div', format(point?.value), 'metric-value'); value.append(el('small', s.unit));
      box.append(label, value, el('div', point ? `采样 ${point.t.toFixed(2)} s` : '当前时刻暂无有效采样', 'metric-note'));
      return box;
    }));
  }
  function renderEvidence() {
    $('evidence').replaceChildren(...visibleEvidence(data, cursor).map(row => {
      const tr = el('tr'); tr.append(el('td', row.name), el('td', row.point ? `${format(row.point.value)} ${row.unit}` : '—'), el('td', row.point ? `${row.point.t.toFixed(3)} s` : '缺测'));
      const source = el('td');
      if (row.point) { const button = el('button', data.scenario === 'recorded' ? `L${row.point.line} ↗` : '模拟值 ↗', 'evidence-button'); button.addEventListener('click', () => showFrame(currentSignal(row.key), row.point)); source.append(button); }
      else source.textContent = '—';
      tr.append(source); return tr;
    }));
  }
  function lineSeries(s, axis, name) {
    const points = [];
    s.points.forEach((p, i) => { if (i && p.t - s.points[i - 1].t > (s.key === 'hours' ? 15 : 2)) points.push([s.points[i - 1].t + .1, null]); points.push([p.t, p.value]); });
    return {name, type: 'line', xAxisIndex: axis, yAxisIndex: axis, data: points, showSymbol: false, connectNulls: false,
      lineStyle: {width: axis ? 1.5 : 2, color: colors[s.key]}, itemStyle: {color: colors[s.key]},
      areaStyle: {color: colors[s.key], opacity: axis ? .035 : .075},
      markLine: {silent: true, symbol: 'none', label: {show: false}, lineStyle: {color: '#d5e9ff', type: 'dashed', width: 1}, data: [{xAxis: cursor}]}};
  }
  function renderChart(full = false) {
    const signal = currentSignal(selected), rpm = currentSignal('rpm');
    if (!full) { chart.setOption({series: [{markLine: {data: [{xAxis: cursor}]}}, {markLine: {data: [{xAxis: cursor}]}}]}); return; }
    const axis = {type: 'value', min: 0, max: data.duration, axisLine: {lineStyle: {color: '#314964'}}, axisLabel: {color: '#6e8aab', fontSize: 10, formatter: value => clock(value)}, splitLine: {show: false}};
    const valueAxis = unit => ({type: 'value', scale: true, name: unit, nameTextStyle: {color: '#82a4ca', fontSize: 10}, axisLabel: {color: '#6e8aab', fontSize: 10}, splitLine: {lineStyle: {color: '#203249', type: 'dashed'}}});
    chart.setOption({animation: false, backgroundColor: 'transparent', textStyle: {fontFamily: 'Segoe UI, Microsoft YaHei, sans-serif'},
      tooltip: {trigger: 'axis', confine: true, backgroundColor: '#0a1729', borderColor: '#365777', textStyle: {color: '#d7e9ff'}, valueFormatter: value => format(value)},
      axisPointer: {link: [{xAxisIndex: 'all'}]},
      grid: [{left: 57, right: 24, top: 35, height: '48%'}, {left: 57, right: 24, top: '72%', height: '15%'}],
      xAxis: [{...axis, gridIndex: 0, axisLabel: {show: false}}, {...axis, gridIndex: 1}],
      yAxis: [{...valueAxis(signal.unit), gridIndex: 0}, {...valueAxis('rpm'), gridIndex: 1, min: 0}],
      series: [lineSeries(signal, 0, signal.name), lineSeries(rpm, 1, '发动机转速')]}, true);
  }
  function renderCursor() {
    $('clock').textContent = `${clock(cursor)} / ${clock(data.duration)}`;
    $('timeline').value = cursor;
    renderMetrics(); renderEvidence(); renderChart();
  }
  function renderContext() {
    const real = data.scenario === 'recorded';
    $('machine-title').replaceChildren(el('strong', real ? 'XC948U' : 'SIM / COOLING'), el('span', real ? '实车数据回放' : '模拟升温工况'));
    $('subtitle').textContent = real ? `${data.capture_date} · 仓库采集 · ${data.frame_count.toLocaleString()} 帧 · 7 项信号` : '独立生成的教学场景 · 转速与负载基本稳定 · 冷却液逐步升温';
    $('source-tag').textContent = real ? '原始采集 · 本机读取' : '独立模拟 · 全部数值为合成';
    $('context-tag').textContent = real ? 'XC948U' : 'SIM-COOLING-001';
    $('footer-source').textContent = real ? 'CAN 采集回放，不代表 Trackunit 云端实时数据' : '模拟工况用于展示排查流程，不代表实车故障或预测精度';
    $('ai-intro').textContent = real ? '真实采集保存在本机；AI 分析使用模拟工况。' : '分析当前游标前 120 秒的模拟信号。';
    $('event-jump').textContent = real ? '查看 02:00 读数 ↗' : '定位升温 · 06:30 ↗';
    $('sample-note').textContent = real ? '每秒首帧 · 缺测留空' : '1 秒采样 · 全部为模拟';
    $('duration-note').textContent = `${clock(data.duration)} 结束`;
    $('diagnostic').replaceChildren();
    if (real) {
      const dtc = data.diagnostics.find(d => d.spn);
      if (dtc) $('diagnostic').append(el('div', 'DM1 原始诊断字段 · 含义待核实', 'diagnostic-title'), el('div', `SPN ${dtc.spn} / FMI ${dtc.fmi} / SA ${dtc.source_address_hex}`, 'diagnostic-code'), el('small', `${dtc.frames} 次重复广播，不等于 ${dtc.frames} 次故障。`));
      $('diagnostic').append(el('small', `来信描述无仪表报警；${data.unassembled_dm1} 条多帧 DM1 待组包，当前不是整车完整故障清单。`));
    } else $('diagnostic').append(el('div', '现象：冷却液持续升温', 'diagnostic-title'), el('small', '未注入厂商故障码。先从测量、散热与循环方向建立排查假设。'));
    $('source-detail').replaceChildren(el('p', data.source_note), el('p', data.sampling));
    if (real) $('source-detail').append(el('p', data.source_file), el('p', `SHA-256: ${data.sha256}`), el('p', '温度、压力、转速范围来自本次采集，不是厂商正常范围。停机后的零压力不可单独认定为故障。'));
  }
  async function load(scenario) {
    const version = ++loadVersion;
    runner.detach('device_changed'); pause(); clearAI();
    data = null; setBusy(false); $('play').disabled = $('timeline').disabled = $('export').disabled = true;
    $('load-error').hidden = true;
    try {
      const response = await fetch(`/assistant/can-replay?scenario=${scenario}`, {cache: 'no-store'});
      if (!response.ok) throw new Error((await response.json()).detail || '无法读取回放数据');
      const next = await response.json();
      if (version !== loadVersion) return false;
      data = next; cursor = scenario === 'recorded' ? 120 : 390;
      ['recorded', 'synthetic'].forEach(id => { $(id).classList.toggle('selected', id === scenario); $(id).setAttribute('aria-pressed', String(id === scenario)); });
      $('timeline').max = Math.floor(data.duration);
      $('play').disabled = $('timeline').disabled = $('export').disabled = false;
      $('signal-tabs').replaceChildren(...data.signals.filter(s => s.key !== 'hours').map(s => {
        const b = el('button', s.name, s.key === selected ? 'selected' : ''); b.setAttribute('aria-pressed', String(s.key === selected));
        b.onclick = () => { selected = s.key; [...$('signal-tabs').children].forEach(c => { c.classList.toggle('selected', c === b); c.setAttribute('aria-pressed', String(c === b)); }); renderChart(true); };
        return b;
      }));
      renderContext(); renderChart(true); renderCursor(); setBusy(false); return true;
    } catch (error) {
      if (version === loadVersion) { $('load-error').textContent = error.message; $('load-error').hidden = false; }
      return false;
    }
  }
  function renderReport(result) {
    const area = $('ai-result'); area.replaceChildren(el('p', result.report.summary, 'report-summary'));
    for (const [index, item] of result.report.hypotheses.entries()) {
      const card = el('article', undefined, 'hypothesis'); card.append(el('h3', `${String(index + 1).padStart(2, '0')}  ${item.component}`), el('p', item.reasoning));
      const citations = el('div', undefined, 'citations');
      item.evidence_ids.forEach(id => { const evidence = result.input.evidence.find(e => e.id === id); if (!evidence) return;
        const button = el('button', `${id} · ${evidence.name}`, 'citation'); button.onclick = () => openDetails(`${id} · AI 输入证据`, [el('p', '独立模拟数据；以下是本次模型实际收到的窗口统计。'), el('pre', `${evidence.name}\n${evidence.start_s}–${evidence.end_s} s · ${evidence.samples} 个采样\n起点 ${format(evidence.first)} → 终点 ${format(evidence.last)} ${evidence.unit}\n范围 ${format(evidence.min)}–${format(evidence.max)} ${evidence.unit}`)]); citations.append(button); });
      card.append(citations, el('p', item.inspection, 'inspection')); area.append(card);
    }
    const missing = el('details', undefined, 'missing'); missing.append(el('summary', '仍需补充的证据')); const list = el('ul'); result.report.missing_evidence.forEach(text => list.append(el('li', text))); missing.append(list); area.append(missing);
    const terms = [...new Set(result.report.hypotheses.flatMap(h => h.search_terms))];
    $('part-terms').replaceChildren(...terms.map(text => el('span', text, 'term')));
  }
  $('recorded').onclick = () => load('recorded'); $('synthetic').onclick = () => load('synthetic');
  $('timeline').oninput = () => { pause(); cursor = Number($('timeline').value); renderCursor(); };
  $('play').onclick = () => { if (playing) pause(); else { if (cursor >= Math.floor(data.duration)) cursor = 0; playing = true; $('play').textContent = 'Ⅱ 暂停'; } };
  $('event-jump').onclick = () => { pause(); cursor = data.scenario === 'recorded' ? 120 : 390; renderCursor(); };
  $('analyze').onclick = async () => {
    if (busy) return;
    if (data.scenario === 'recorded' && !await load('synthetic')) return;
    pause(); clearAI(); setBusy(true);
    await runner.start({scenario: 'synthetic', at: Math.floor(cursor)}, `${loadVersion}:${data.scenario}`);
  };
  $('stop').onclick = () => runner.stop();
  $('close-frame').onclick = () => $('frame-dialog').close();
  $('export').onclick = () => {
    const output = {source_kind: data.source_kind, capture_id: data.capture_id, cursor, source_file: data.source_file, sha256: data.sha256,
      evidence: visibleEvidence(data, cursor), ai: data.scenario === 'synthetic' ? report : null};
    const url = URL.createObjectURL(new Blob([JSON.stringify(output, null, 2)], {type: 'application/json'}));
    const a = el('a'); a.href = url; a.download = `${data.capture_id}-${Math.floor(cursor)}s.json`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  setInterval(() => { if (!playing || !data) return; cursor = Math.min(Math.floor(data.duration), cursor + Number($('speed').value) / 2); if (cursor >= Math.floor(data.duration)) pause(); renderCursor(); }, 500);
  window.addEventListener('resize', () => chart.resize());
  window.addEventListener('pagehide', () => { pause(); runner.detach(); });
  function hostContext(context) {
    const newIdentity = `${context.asset_id || ''}:${context.serial || ''}`;
    if (hostAsset !== null && newIdentity !== hostAsset) { pause(); runner.detach('device_changed'); clearAI(); }
    hostAsset = newIdentity;
    $('trackunit-context').hidden = false;
    $('platform-title').textContent = `${context.model || '机型待核对'}${context.hint ? ' · ' + context.hint : ''}`;
    $('platform-identity').textContent = `${context.serial ? 'VIN / PIN '+context.serial+' · ' : ''}${context.asset_id ? '资产 '+context.asset_id : '请在 Trackunit 打开设备页'}`;
    $('platform-values').replaceChildren();
    const sample = context.sample;
    if (sample) {
      for (const [label, value, unit] of [['累计工时',sample.operating_hours,'h'],['累计怠速',sample.idle_hours,'h'],['剩余燃油',sample.fuel_remaining_percent,'%']]) {
        const item = el('div'); item.append(el('small',label),el('strong',`${format(value)} ${unit}`)); $('platform-values').append(item);
      }
    }
    const sampleLabel = sample?.recorded_at ? `已载入记录 · ${new Date(sample.recorded_at).toLocaleString('zh-CN',{hour12:false})}` : context.state==='loading'?'正在读取本机设备记录…':'暂无已核实的运行样本';
    $('platform-note').textContent = `${sampleLabel}。下方是 XC948U 参考采集 / 独立模拟工况，尚未与此 VIN 绑定。`;
  }
  function returnToDevice(event) {
    if(!embedded)return;
    event?.preventDefault();
    window.parent.postMessage({type:'jilian:can-open-work'},location.origin);
  }
  $('platform-work').onclick = returnToDevice;
  document.querySelector('.catalog-link').addEventListener('click',returnToDevice);
  window.addEventListener('message', event => {
    if(!embedded||event.source!==window.parent||event.origin!==location.origin)return;
    if(event.data?.type==='jilian:can-host-context' && event.data.context)hostContext(event.data.context);
    if(event.data?.type==='jilian:can-hidden'){pause();runner.detach();}
  });
  if(embedded){$('trackunit-context').hidden=false;window.parent.postMessage({type:'jilian:can-ready'},location.origin);}
  load('recorded');
})();
