/* Continuous records stay bound to the device that supplied the export. */
(function (root) {
  const CHANNELS = {
    coolant_c: {can:'50278', label:'冷却液温度', unit:'°C', color:'#0062c5'},
    oil_pressure_kpa: {can:'50281', label:'机油压力', unit:'kPa', color:'#0894a5'},
    engine_load_percent: {can:'50283', label:'发动机负载', unit:'%', color:'#b87513'},
    engine_rpm: {can:'50286', label:'发动机转速', unit:'rpm', color:'#5367b4'}
  };
  const scopeKey = machine => JSON.stringify([machine?.machine_id, machine?.dataset_id, machine?.serial_number]);
  function unitsForCSV(text) {
    const header = String(text || '').split(/\r?\n/, 1)[0];
    return Object.fromEntries(Object.entries(CHANNELS).filter(([, channel]) =>
      new RegExp('\\(CAN\\s+' + channel.can + '\\)').test(header)).map(([key, channel]) => [key, channel.unit]));
  }
  function chartData(points, key) {
    const rows = [];
    for (const point of points || []) {
      const time = Date.parse(point.timestamp);
      if (!Number.isFinite(time)) continue;
      if (point.break_before && rows.length) rows.push([time - 1, null]);
      rows.push([time, typeof point[key] === 'number' && Number.isFinite(point[key]) ? point[key] : null]);
    }
    return rows;
  }
  function reportMatches(report, machine) {
    return Boolean(report && machine && report.machine_id === machine.machine_id && report.dataset_id === machine.dataset_id);
  }
  function capturePageMatches(value, asset) {
    try {
      const url = new URL(value);
      return url.protocol === 'https:' && !url.username && !url.password && !url.port && !url.search && !url.hash &&
        ['new.manager.trackunit.com','manager.trackunit.com'].includes(url.hostname) &&
        url.pathname.replace(/\/$/,'') === `/assets/${asset}/insights`;
    } catch { return false; }
  }
  const helpers = {CHANNELS, scopeKey, unitsForCSV, chartData, reportMatches, capturePageMatches};
  if (typeof module !== 'undefined' && module.exports) { module.exports = helpers; return; }
  root.SensorSeriesWorkspace = helpers;
  if (typeof document === 'undefined') return;
  const view = document.getElementById('risk-view'), snapshot = document.getElementById('risk-live');
  if (!view || !snapshot) return;
  const snapshotLoad = root.renderRiskDemo;
  const chosen = () => typeof selected === 'function' ? selected() : null;
  const make = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  const button = (text, id, primary = false) => {
    const node = make('button', text, primary ? 'primary-button' : ''); node.type = 'button'; node.id = id; return node;
  };
  const number = value => Number.isFinite(value) ? value.toLocaleString('zh-CN', {maximumFractionDigits:2}) : '—';
  const stamp = value => {
    const date = new Date(value);
    return Number.isFinite(date.getTime()) ? date.toLocaleString('zh-CN', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}) : '时间未提供';
  };
  const card = make('div', '', 'sensor-series-workspace'); card.id = 'sensor-series-workspace';
  const heading = make('div', '', 'sensor-series-heading');
  heading.append(make('h3', '连续工况与风险线索'), make('span', 'Trackunit Advanced Sensors', 'sensor-series-source'));
  const intro = make('p', '对齐温度、油压、负载和转速，分析异常组合，再到 XGSS 核对适配备件。', 'sensor-series-intro');
  const actions = make('div', '', 'sensor-series-actions');
  const read = button('读取当前曲线', 'sensor-series-read', true);
  const stop = button('停止读取', 'sensor-series-stop'); stop.hidden = true;
  const importOpen = button('导入 Trackunit CSV', 'sensor-series-import-open');
  const file = make('input'); file.type = 'file'; file.accept = '.csv,text/csv'; file.hidden = true; file.id = 'sensor-series-file';
  actions.append(read, stop, importOpen, file);
  const status = make('p', '', 'sensor-series-status'); status.id = 'sensor-series-status'; status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
  const review = make('section', '', 'sensor-series-review'); review.hidden = true;
  const reviewTitle = make('h4', '确认曲线来源与单位'), reviewText = make('p');
  const confirmation = make('label', '', 'sensor-series-confirmation'), confirmed = make('input'); confirmed.type = 'checkbox'; confirmed.id = 'sensor-series-confirmed';
  const confirmationText = make('span'); confirmation.append(confirmed, confirmationText);
  const save = button('载入这些曲线', 'sensor-series-import-save', true), dismiss = button('取消', 'sensor-series-import-cancel');
  const reviewActions = make('div', '', 'sensor-series-actions'); reviewActions.append(save, dismiss);
  review.append(reviewTitle, reviewText, confirmation, reviewActions);
  const result = make('div'); result.id = 'sensor-series-result'; result.hidden = true;
  const summary = make('div', '', 'sensor-series-summary');
  const chart = make('div', '', 'sensor-series-chart'); chart.id = 'sensor-series-chart'; chart.setAttribute('role', 'img');
  const chartNote = make('p', '', 'sensor-series-chart-note');
  const evidence = make('details', '', 'sensor-series-evidence'); evidence.append(make('summary', '查看趋势依据与数据范围'));
  const evidenceBody = make('div'); evidence.append(evidenceBody);
  const aiHead = make('div', '', 'sensor-series-heading'); aiHead.append(make('h3', 'XCMG AI 风险分析'));
  const analyze = button('分析连续工况', 'sensor-series-analyze', true); aiHead.append(analyze);
  const aiResult = make('div', '', 'sensor-series-ai-result'); aiResult.id = 'sensor-series-ai-result';
  result.append(summary, chart, chartNote, evidence, aiHead, aiResult);
  card.append(heading, intro, actions, status, review, result);
  snapshot.parentNode.insertBefore(card, snapshot);
  const snapshotDetails = make('details', '', 'sensor-series-snapshot'); snapshotDetails.append(make('summary', '单次快照 · 补充查看'));
  snapshot.parentNode.insertBefore(snapshotDetails, snapshot); snapshotDetails.append(snapshot);
  snapshotDetails.addEventListener('toggle', () => { if (snapshotDetails.open) void snapshotLoad?.(); });
  const title = document.getElementById('risk-title'); if (title) title.textContent = '连续传感器风险分析';
  let report = null, activeScope = '', generation = 0, busy = false, pending = null, job = null, watchdog = null, chartInstance = null;
  const origin = location.ancestorOrigins?.[0], connection = new URLSearchParams(location.search).get('panel');
  const embedded = root.parent !== root && /^chrome-extension:\/\/[a-p]{32}$/.test(origin || '') && Boolean(connection);
  let bridgeReady = false;
  const post = data => { if (embedded) root.parent.postMessage({protocol:1,connection_id:connection,...data}, origin); };
  const identity = machine => ({machine_id:machine.machine_id,dataset_id:machine.dataset_id});
  const validMachine = machine => Boolean(machine?.machine_id && machine?.dataset_id && machine.provenance === 'user_supplied');
  const current = (ticket, scope) => ticket === generation && scope === scopeKey(chosen());
  function controls() {
    const valid = validMachine(chosen());
    read.hidden = !embedded;
    read.disabled = busy || !valid || !embedded || !bridgeReady;
    importOpen.disabled = busy || !valid;
    analyze.disabled = busy || !reportMatches(report, chosen()) || report.unit_status !== 'confirmed_metric';
    analyze.hidden = Boolean(report?.ai_analysis);
    save.disabled = busy || !pending || !confirmed.checked;
    dismiss.disabled = busy;
    stop.hidden = !job;
  }
  function stopCapture(message) {
    if (job) post({type:'jilian:sensor-series-cancel',request_id:job.id,asset_id:job.machine.machine_id,dataset_id:job.machine.dataset_id});
    job = null; clearTimeout(watchdog); watchdog = null; busy = false;
    if (message) status.textContent = message;
    controls();
  }
  function resetScope(machine) {
    const key = scopeKey(machine);
    if (key === activeScope) return;
    generation++; stopCapture(); bridgeReady = false; activeScope = key; pending = null; report = null; review.hidden = true; result.hidden = true; confirmed.checked = false;
    aiResult.replaceChildren(); summary.replaceChildren(); evidenceBody.replaceChildren(); chartInstance?.clear(); controls();
  }
  function chartOption(data) {
    const channels = (data.channels || []).filter(row => CHANNELS[row.key]);
    const panel = 132;
    chart.style.height = `${channels.length * panel + 52}px`;
    return {
      animation:false, textStyle:{fontFamily:'Arial, Microsoft YaHei, sans-serif'},
      tooltip:{trigger:'axis',confine:true}, axisPointer:{link:[{xAxisIndex:'all'}]},
      grid:channels.map((row, index) => ({top:24 + index * panel,height:80,left:56,right:24})),
      title:channels.map((row,index) => ({text:`${row.label} (${row.unit})`,left:12,top:index * panel,textStyle:{fontSize:12,fontWeight:500,color:'#365b7c'}})),
      xAxis:channels.map((row,index) => ({type:'time',gridIndex:index,axisLabel:{fontSize:10,color:'#6c849a',formatter:value => stamp(value)},splitLine:{show:false},axisLine:{lineStyle:{color:'#c4d5e5'}}})),
      yAxis:channels.map((row,index) => ({type:'value',gridIndex:index,scale:true,axisLabel:{fontSize:10,color:'#6c849a'},splitLine:{lineStyle:{color:'#e8eff6'}}})),
      dataZoom:[{type:'inside',xAxisIndex:channels.map((row,index)=>index),filterMode:'none'},
        {type:'slider',xAxisIndex:channels.map((row,index)=>index),bottom:0,height:20,borderColor:'#d1deec',filterMode:'none',showDetail:false}],
      series:channels.map((row,index) => ({name:`${row.label} (${row.unit})`,type:'line',xAxisIndex:index,yAxisIndex:index,
        data:chartData(data.chart_points,row.key),showSymbol:false,connectNulls:false,lineStyle:{width:1.8,color:CHANNELS[row.key].color},itemStyle:{color:CHANNELS[row.key].color}}))
    };
  }
  function drawChart(data) {
    chart.setAttribute('aria-label', `${data.channels.length} 项连续传感器曲线，${data.sample_count} 条采样，${stamp(data.window.start)} 至 ${stamp(data.window.end)}。数据缺口以断线表示。`);
    if (!root.echarts) { chart.textContent = '曲线组件尚未加载，请刷新页面。下方仍可查看数值范围与趋势依据。'; return; }
    if (!chartInstance) chartInstance = root.echarts.init(chart);
    chartInstance.setOption(chartOption(data), true); chartInstance.resize();
  }
  function renderAI(data) {
    aiResult.replaceChildren();
    const analysis = data.ai_analysis;
    if (!analysis) { aiResult.append(make('p', '曲线已载入。运行 XCMG AI，结合多信号变化判断可能的问题和检查顺序。', 'sensor-series-intro')); return; }
    aiResult.append(make('p', analysis.summary, 'sensor-series-ai-summary'));
    const priorities = {urgent:'优先核查',watch:'持续关注',routine:'条件性关注'};
    for (const [index, hypothesis] of (analysis.hypotheses || []).entries()) {
      const article = make('article', '', 'sensor-series-hypothesis');
      const header = make('div', '', 'sensor-series-heading'); header.append(make('h4', hypothesis.failure_mode),make('span', priorities[hypothesis.priority] || '待核对', 'sensor-series-priority'));
      article.append(header,make('p',hypothesis.reason));
      const support = (hypothesis.evidence_ids || []).map(id => (data.evidence || []).find(row => row.id === id)).filter(Boolean);
      if (support.length) article.append(make('p', `趋势依据：${support.map(row => row.title).join('；')}`, 'sensor-series-citation'));
      const inspection = Array.isArray(hypothesis.inspection) ? hypothesis.inspection.join('；') : hypothesis.inspection;
      if (inspection) article.append(make('p', `先检查：${inspection}`));
      if (hypothesis.search_terms?.length) article.append(make('p', `部件方向：${hypothesis.search_terms.join('、')}`, 'sensor-series-citation'));
      const parts = button('查找适配备件', `sensor-series-parts-${index}`); parts.disabled = typeof root.openSensorSeriesParts !== 'function';
      parts.onclick = async () => {
        if (!reportMatches(data, chosen()) || typeof root.openSensorSeriesParts !== 'function') return;
        parts.disabled = true;
        try { await root.openSensorSeriesParts({series_id:data.series_id,hypothesis_index:index,...identity(chosen())}); }
        catch (error) { status.textContent = error.message || '备件资料暂时未能打开，请重试。'; }
        finally { parts.disabled = false; }
      };
      article.append(parts); aiResult.append(article);
    }
    const continuation = data.prediction?.continuation;
    if (continuation && CHANNELS[continuation.channel]) {
      const note = make('details', '', 'sensor-series-evidence'); note.append(make('summary', '短时走势参考'));
      note.append(make('p', `若末段趋势持续，未来 ${number(continuation.horizon_minutes)} 分钟的变化约为 ${number(continuation.change_if_trend_persists)} ${CHANNELS[continuation.channel].unit}。${continuation.condition || ''}`)); aiResult.append(note);
    }
    aiResult.append(make('p', '以上为连续工况的风险线索，需结合现场检查核实；故障发生时间尚未标定。', 'sensor-series-limit'));
  }
  function render(data) {
    if (!reportMatches(data, chosen())) return;
    report = data; result.hidden = false; summary.replaceChildren();
    const samples = make('div'); samples.append(make('strong',number(data.sample_count)),make('span','条连续采样'));
    const signals = make('div'); signals.append(make('strong',String(data.channels.length)),make('span','项传感器'));
    const windowBox = make('div', '', 'sensor-series-window'); windowBox.append(make('strong',`${stamp(data.window.start)} — ${stamp(data.window.end)}`),make('span','采集区间 · 按本机时区显示'));
    summary.append(samples,signals,windowBox);
    chartNote.textContent = data.quality.gap_count > 0 ? `曲线保留 ${data.quality.gap_count} 处采集间隔；缺口不连线。` : '各信号按同一时间轴对齐。';
    evidenceBody.replaceChildren();
    evidenceBody.append(make('p',`${data.model} · ${data.binding} · ${data.segments.length} 段记录`, 'sensor-series-citation'));
    const ranges = make('ul');
    for (const channel of data.channels) ranges.append(make('li',`${channel.label}：${number(channel.min)}–${number(channel.max)} ${channel.unit}，${channel.count} 个有效值`));
    evidenceBody.append(ranges);
    for (const row of data.evidence || []) { const block = make('div', '', 'sensor-series-evidence-row'); block.append(make('strong',row.title),make('p',row.detail)); evidenceBody.append(block); }
    evidenceBody.append(make('p',`典型采样间隔 ${number(data.quality.median_interval_seconds)} 秒；最长间隔 ${number(data.quality.max_gap_seconds / 3600)} 小时。导出记录未注明聚合方式。`, 'sensor-series-citation'));
    if (data.unit_status !== 'confirmed_metric') status.textContent = '请重新导入 CSV 并核对单位后再分析。';
    else status.textContent = data.ai_analysis ? '已结合连续曲线生成风险线索。' : '连续曲线已载入，可开始 AI 分析。';
    drawChart(data); renderAI(data); controls();
  }
  async function load() {
    const machine = chosen(); resetScope(machine);
    if (!validMachine(machine)) { status.textContent = '先关联当前 Trackunit 设备，再读取或导入它的连续曲线。'; controls(); return; }
    if (busy || pending) return;
    const ticket = ++generation, scope = scopeKey(machine);
    status.textContent = '正在读取当前设备的连续记录…';
    if (embedded) post({type:'jilian:sensor-series-probe',request_id:'sensor-series-ready',asset_id:machine.machine_id,dataset_id:machine.dataset_id});
    try {
      const data = await api(`/assistant/sensor-series/latest?machine_id=${encodeURIComponent(machine.machine_id)}&dataset_id=${encodeURIComponent(machine.dataset_id)}`);
      if (current(ticket,scope)) render(data);
    } catch (error) {
      if (!current(ticket,scope)) return;
      report = null; result.hidden = true;
      status.textContent = error.status === 404 ? (embedded ? '打开当前设备的 Insights → Advanced Sensors，选好信号和时间范围后读取曲线。' : '可从 Chrome 助手侧栏读取曲线，或导入当前设备在 Advanced Sensors 导出的 CSV。') : error.message;
      controls();
    }
    if (snapshotDetails.open) void snapshotLoad?.();
  }
  function prepareCSV(csvText, capture, originType, fileName) {
    const machine = chosen(), units = unitsForCSV(csvText);
    if (!validMachine(machine) || !Object.keys(units).length) throw new Error('请导出冷却液温度、机油压力、发动机负载或发动机转速曲线。');
    if (new TextEncoder().encode(csvText).length > 3000000) throw new Error('CSV 超过 3 MB，请缩小导出时间范围。');
    pending = {csvText,capture,originType,units,machine:{...machine},scope:scopeKey(machine)};
    confirmed.checked = false; review.hidden = false;
    reviewText.textContent = `${machine.model || '当前设备'} · ${machine.serial_number || machine.machine_id} · ${fileName || '当前页面导出'}`;
    confirmationText.textContent = `确认这些记录属于当前设备，且图表单位为：${Object.keys(units).map(key => `${CHANNELS[key].label} ${CHANNELS[key].unit}`).join('、')}。`;
    status.textContent = '已收到曲线，请核对设备与单位后载入。'; controls();
  }
  read.onclick = () => {
    const machine = chosen(); resetScope(machine);
    if (!validMachine(machine) || !embedded || !bridgeReady || busy) return;
    const bytes = new Uint8Array(16); crypto.getRandomValues(bytes);
    const id = Array.from(bytes, value => value.toString(16).padStart(2,'0')).join('');
    job = {id,machine:{...machine},scope:scopeKey(machine)}; busy = true;
    status.textContent = '正在读取当前 Advanced Sensors 已选择的曲线…'; controls();
    post({type:'jilian:sensor-series-start',request_id:id,asset_id:machine.machine_id,dataset_id:machine.dataset_id});
    watchdog = setTimeout(() => stopCapture('本次读取已超时。请确认 Advanced Sensors 已显示所选曲线，再重试。'), 70000);
  };
  stop.onclick = () => stopCapture('已停止读取。已保存的连续记录仍保留。');
  importOpen.onclick = () => { resetScope(chosen()); if (validMachine(chosen()) && !busy) { file.value = ''; file.click(); } };
  file.onchange = async () => {
    const selectedFile = file.files?.[0], machine = chosen(), scope = scopeKey(machine), ticket = generation;
    if (!selectedFile) return;
    try {
      if (selectedFile.size > 3000000) throw new Error('CSV 超过 3 MB，请缩小导出时间范围。');
      const text = await selectedFile.text();
      if (current(ticket,scope)) prepareCSV(text, {asset_id:machine.machine_id}, 'user_confirmed_export', selectedFile.name);
    } catch (error) { if (current(ticket,scope)) status.textContent = error.message; }
  };
  confirmed.onchange = controls;
  dismiss.onclick = () => { pending = null; review.hidden = true; controls(); status.textContent = '已取消导入。'; };
  save.onclick = async () => {
    if (!pending || !confirmed.checked || pending.scope !== scopeKey(chosen()) || busy) return;
    const input = pending, ticket = ++generation; busy = true; controls(); status.textContent = '正在对齐连续传感器记录…';
    const payload = {...identity(input.machine),csv_text:input.csvText,source:'trackunit_advanced_sensors_export',source_asset_id:input.machine.machine_id,
      origin:input.originType,units:input.units};
    for (const key of ['page_url','captured_at']) if (input.capture[key]) payload[key] = input.capture[key];
    try {
      const data = await api('/assistant/sensor-series/import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      if (!current(ticket,input.scope)) return;
      pending = null; review.hidden = true; render(data);
    } catch (error) { if (current(ticket,input.scope)) status.textContent = error.message; }
    finally { if (current(ticket,input.scope)) { busy = false; controls(); } }
  };
  analyze.onclick = async () => {
    const machine = chosen(), data = report;
    if (busy || !reportMatches(data,machine) || data.unit_status !== 'confirmed_metric') return;
    const ticket = ++generation, scope = scopeKey(machine); busy = true; controls();
    status.textContent = 'XCMG AI 正在关联温度、油压、负载与转速变化…';
    try {
      const updated = await api(`/assistant/sensor-series/${encodeURIComponent(data.series_id)}/analyze`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(identity(machine))});
      if (current(ticket,scope)) render(updated);
    } catch (error) { if (current(ticket,scope)) status.textContent = error.message; }
    finally { if (current(ticket,scope)) { busy = false; controls(); } }
  };
  root.addEventListener('message', event => {
    const data = event.data;
    if (!embedded || event.source !== root.parent || event.origin !== origin || data?.protocol !== 1 || data.connection_id !== connection) return;
    const machine = chosen();
    if (data.asset_id !== machine?.machine_id || data.dataset_id !== machine?.dataset_id) return;
    if (data.type === 'jilian:sensor-series-ready') { bridgeReady = data.available === true; controls(); return; }
    if (!job || data.request_id !== job.id || job.scope !== scopeKey(machine)) return;
    if (data.type === 'jilian:sensor-series-progress') { status.textContent = String(data.message || '').slice(0,300); return; }
    if (data.type === 'jilian:sensor-series-error') { stopCapture(String(data.message || '连续曲线读取未完成，请重试。').slice(0,300)); return; }
    if (data.type !== 'jilian:sensor-series-result') return;
    const capture = data.capture;
    if (capture?.source !== 'trackunit_csv_export' || capture.schema_version !== 1 || capture.asset_id !== machine.machine_id ||
      !capturePageMatches(capture.page_url,machine.machine_id) || !Number.isFinite(Date.parse(capture.captured_at)) || typeof capture.csv_text !== 'string') {
      stopCapture('曲线来源与当前设备不一致，请重新读取。'); return;
    }
    stopCapture();
    try { prepareCSV(capture.csv_text,capture,'browser_export_capture'); } catch (error) { status.textContent = error.message; }
  });
  root.addEventListener('hashchange', () => resetScope(chosen()));
  document.getElementById('machine')?.addEventListener('change', () => resetScope(chosen()));
  root.addEventListener('resize', () => chartInstance?.resize());
  if (root.ResizeObserver) new root.ResizeObserver(() => chartInstance?.resize()).observe(card);
  root.renderRiskDemo = load;
  root.SensorSeriesWorkspace.reload = load;
  controls();
})(typeof window !== 'undefined' ? window : globalThis);
