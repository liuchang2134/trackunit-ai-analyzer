/* Continuous records stay bound to the device that supplied the export. */
(function (root) {
  const CHANNELS = {
    coolant_c: {can:'50278', label:'冷却液温度', unit:'°C', color:'#0062c5'},
    oil_pressure_kpa: {can:'50281', label:'机油压力', unit:'kPa', color:'#0894a5'},
    engine_load_percent: {can:'50283', label:'发动机负载', unit:'%', color:'#b87513'},
    engine_rpm: {can:'50286', label:'发动机转速', unit:'rpm', color:'#5367b4'}
  };
  const scopeKey = machine => JSON.stringify([machine?.machine_id, machine?.dataset_id, machine?.serial_number]);
  const MAX_CHANNELS = 96, MAX_EXPORTS = 32, MAX_FILE_BYTES = 3000000, MAX_BATCH_BYTES = 24000000;
  const COLORS = ['#0062c5','#0894a5','#b87513','#5367b4','#ad5270','#478256'];
  const KINDS = {continuous:'传感器',state:'状态',code:'编码/标识',counter:'累计量'};
  // Display aliases only; the imported source labels and measurement metadata are unchanged.
  const DISPLAY_LABELS = {
    'Engine Coolant Temperature (Water Temperature)':'冷却液温度',
    'Engine Oil Pressure':'机油压力',
    'Load Percentage at Current Speed':'发动机负载',
    'Engine Speed':'发动机转速',
    'Intake Air Temp Behind Throttle Valve (Temperature After Intercooling)':'中冷后进气温度',
    'Fuel Consumption Rate':'瞬时油耗',
    'Accelerator Pedal Position':'加速踏板位置',
    'Driver Torque Demand':'驾驶员需求扭矩',
    'Actual Engine Torque Percentage':'发动机实际扭矩百分比',
    'Atmospheric Pressure':'大气压力',
    'Urea Level in Urea Tank':'尿素箱液位',
    'Urea Temperature in Urea Tank':'尿素箱温度',
    'Torque Converter Output Shaft Speed':'变矩器输出轴转速',
    'Torque Converter Input Shaft Speed':'变矩器输入轴转速',
    'Oil Temperature of Torque Converter (Outlet)':'变矩器出口油温',
    'Transmission Oil Reservoir Temperature':'变速箱油池温度'
  };
  const sourceLabel = channel => channel.source_label || channel.label || channel.key;
  const displayLabel = channel => DISPLAY_LABELS[sourceLabel(channel)] || DISPLAY_LABELS[channel.label] || channel.label || channel.key;
  const channelId = channel => CHANNELS[channel.key]?.can ? `CAN ${CHANNELS[channel.key].can}` : /^can_\d+$/.test(channel.key) ? `CAN ${channel.key.slice(4)}` : channel.key;
  const choiceLabel = (channel, all) => displayLabel(channel) + (all.filter(item => displayLabel(item) === displayLabel(channel)).length > 1 ? ` · ${channelId(channel)}` : '');
  function csvHeader(text) {
    const row = []; let value = '', quoted = false;
    const source = String(text || '').replace(/^\uFEFF/,'');
    for (let i = 0; i < source.length; i++) {
      const ch = source[i];
      if (ch === '"') { if (quoted && source[i + 1] === '"') { value += '"'; i++; } else quoted = !quoted; }
      else if (!quoted && ch === ',') { row.push(value.trim()); value = ''; }
      else if (!quoted && /[\r\n]/.test(ch)) { row.push(value.trim()); return row; }
      else value += ch;
      if (value.length > 512 || row.length > MAX_CHANNELS) throw new Error('CSV 表头超出支持范围。');
    }
    if (quoted) throw new Error('CSV 表头格式不完整。');
    row.push(value.trim()); return row;
  }
  const stableKey = can => { const id = String(Number(can)); return Object.keys(CHANNELS).find(key => CHANNELS[key].can === id) || `can_${id}`; };
  const cleanUnit = unit => typeof unit === 'string' && unit.trim().length <= 24 && !/^(?:-|—|unknown|n\/?a|单位待核对)$/i.test(unit.trim()) ? unit.trim() : '';
  function inferKind(label) {
    if (/fault|diagnostic|\bDTC\b|engine[\s_-]*make[\s_-]*model[\s_-]*serial|故障码|故障代码/i.test(label)) return 'code';
    if (/lamp|switch|status|state|current gear|selected gear|^input\s*[1-6]$|^output\s*1$|灯|开关|状态|挡位/i.test(label)) return 'state';
    if (/cumulative|accumulated|total\s*(?:hours|fuel|time|distance)|累计|总工时|总油耗/i.test(label)) return 'counter';
    return 'continuous';
  }
  function channelsForCSV(text, metadata = {}, units = {}, sensors = []) {
    const header = csvHeader(text);
    if (header[0]?.toLowerCase() !== 'date and time' || header.length < 2 || header.length > MAX_CHANNELS + 1) throw new Error('请选择 Trackunit 导出的传感器 CSV。');
    const seen = new Set();
    return header.slice(1).map(name => {
      const match = name.match(/^(.*?)\s*\(CAN\s+(\d{1,10})\)\s*$/i);
      const input = name.match(/^INPUT\s*([1-6])\s*\(INPUT\s*\1\)\s*$/i);
      const output = name.match(/^OUTPUT\s*1\s*\(OUTPUT\s*1\)\s*$/i);
      if (!match && !input && !output) throw new Error('CSV 中有无法识别的传感器列。');
      const key = input ? `input_${input[1]}` : output ? 'output_1' : stableKey(match[2]), label = input ? `Input ${input[1]}` : output ? 'Output 1' : match[1].trim();
      if (!label || label.length > 180) throw new Error('CSV 中的传感器名称超出支持范围。');
      if (seen.has(key)) throw new Error('CSV 中有重复的传感器列。');
      seen.add(key);
      const meta = metadata?.[key] || {};
      const comparableName = value => value.trim().replace(/\s+/g,' ').replace(/^(input|output)\s+([1-6])$/i,'$1$2').toLowerCase();
      const observed = sensors.filter(item => typeof item?.name === 'string' && comparableName(item.name) === comparableName(label));
      const headerUnit = label.match(/(?:\[([^\]]{1,40})\]|\((°C|°F|kPa|MPa|bar|psi|rpm|%|V|A|h|hr|hours|L|L\/h|gallons|gal\/h|km\/h)\))\s*$/i);
      const hasUnit = Object.prototype.hasOwnProperty.call(units || {}, key) || Object.prototype.hasOwnProperty.call(meta, 'unit') || observed.length === 1;
      const unit = hasUnit ? cleanUnit(units?.[key] ?? meta.unit ?? observed[0]?.unit) : cleanUnit(headerUnit?.[1] || headerUnit?.[2] || CHANNELS[key]?.unit);
      const inferred = inferKind(label);
      const kind = inferred === 'code' || inferred === 'state' ? inferred : (Object.hasOwn(KINDS, meta.kind) ? meta.kind : inferred);
      return {key,label,unit,kind};
    });
  }
  function unitsForCSV(text) {
    return Object.fromEntries(channelsForCSV(text).filter(channel => channel.unit).map(channel => [channel.key, channel.unit]));
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
        (url.pathname.replace(/\/$/,'') === `/assets/${asset}/insights` || url.pathname.startsWith(`/assets/${asset}/insights/`));
    } catch { return false; }
  }
  const helpers = {CHANNELS, scopeKey, unitsForCSV, channelsForCSV, csvHeader, chartData, reportMatches, capturePageMatches,displayLabel,choiceLabel};
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
  const intro = make('p', '汇集当前设备的高级传感器，结合连续变化分析故障风险。', 'sensor-series-intro');
  const actions = make('div', '', 'sensor-series-actions');
  const read = button('读取当前曲线', 'sensor-series-read', true);
  const stop = button('停止读取', 'sensor-series-stop'); stop.hidden = true;
  const importOpen = button('导入 Trackunit CSV', 'sensor-series-import-open');
  const file = make('input'); file.type = 'file'; file.accept = '.csv,text/csv'; file.multiple = true; file.hidden = true; file.id = 'sensor-series-file';
  actions.append(read, stop, importOpen, file);
  const status = make('p', '', 'sensor-series-status'); status.id = 'sensor-series-status'; status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
  const review = make('section', '', 'sensor-series-review'); review.hidden = true;
  const reviewTitle = make('h4', '确认曲线来源与单位'), reviewText = make('p');
  const confirmation = make('label', '', 'sensor-series-confirmation'), confirmed = make('input'); confirmed.type = 'checkbox'; confirmed.id = 'sensor-series-confirmed';
  const confirmationText = make('span'); confirmation.append(confirmed, confirmationText);
  const unitReview = make('details', '', 'sensor-series-unit-review'), unitReviewTitle = make('summary'), unitReviewList = make('ul'); unitReview.append(unitReviewTitle,unitReviewList);
  const save = button('载入这些曲线', 'sensor-series-import-save', true), dismiss = button('取消', 'sensor-series-import-cancel');
  const reviewActions = make('div', '', 'sensor-series-actions'); reviewActions.append(save, dismiss);
  review.append(reviewTitle, reviewText, confirmation, unitReview, reviewActions);
  const result = make('div'); result.id = 'sensor-series-result'; result.hidden = true;
  const summary = make('div', '', 'sensor-series-summary');
  const channelPicker = make('div', '', 'sensor-series-channel-picker'); channelPicker.id = 'sensor-series-channel-picker';
  const pickerNote = make('p', '', 'sensor-series-chart-note');
  const codeReadings = make('div', '', 'sensor-series-code-readings'); codeReadings.id = 'sensor-series-code-readings';
  const chart = make('div', '', 'sensor-series-chart'); chart.id = 'sensor-series-chart'; chart.setAttribute('role', 'img');
  const chartNote = make('p', '', 'sensor-series-chart-note');
  const evidence = make('details', '', 'sensor-series-evidence'); evidence.append(make('summary', '查看趋势依据与数据范围'));
  const evidenceBody = make('div'); evidence.append(evidenceBody);
  const aiHead = make('div', '', 'sensor-series-heading'); aiHead.append(make('h3', 'XCMG AI 风险分析'));
  const analyze = button('分析连续工况', 'sensor-series-analyze', true); aiHead.append(analyze);
  const aiResult = make('div', '', 'sensor-series-ai-result'); aiResult.id = 'sensor-series-ai-result';
  result.append(summary, channelPicker, pickerNote, chart, codeReadings, chartNote, evidence, aiHead, aiResult);
  card.append(heading, intro, actions, status, review, result);
  snapshot.parentNode.insertBefore(card, snapshot);
  const snapshotDetails = make('details', '', 'sensor-series-snapshot'); snapshotDetails.append(make('summary', '单次快照 · 补充查看'));
  snapshot.parentNode.insertBefore(snapshotDetails, snapshot); snapshotDetails.append(snapshot);
  snapshotDetails.addEventListener('toggle', () => { if (snapshotDetails.open) void snapshotLoad?.(); });
  const title = document.getElementById('risk-title'); if (title) title.textContent = '连续传感器风险分析';
  let report = null, activeScope = '', generation = 0, busy = false, pending = null, job = null, watchdog = null, chartInstance = null;
  let shownKeys = [], shownSeries = '';
  const origin = location.ancestorOrigins?.[0], connection = new URLSearchParams(location.search).get('panel');
  const embedded = root.parent !== root && /^chrome-extension:\/\/[a-p]{32}$/.test(origin || '') && Boolean(connection);
  let bridgeReady = false;
  const post = data => { if (embedded) root.parent.postMessage({protocol:1,connection_id:connection,...data}, origin); };
  const identity = machine => ({machine_id:machine.machine_id,dataset_id:machine.dataset_id});
  const validMachine = machine => Boolean(machine?.machine_id && machine?.dataset_id && machine.provenance === 'user_supplied');
  const current = (ticket, scope) => ticket === generation && scope === scopeKey(chosen());
  const aiAvailable = data => typeof data?.ai_available === 'boolean' ? data.ai_available : data?.unit_status === 'confirmed_metric';
  const kindOf = channel => channel.kind || inferKind(channel.label || '');
  const unitOf = channel => channel.unit || '单位待核对';
  function controls() {
    const valid = validMachine(chosen());
    read.hidden = !embedded;
    read.disabled = busy || !valid || !embedded || !bridgeReady;
    importOpen.disabled = busy || !valid;
    analyze.disabled = busy || Boolean(pending) || !reportMatches(report, chosen()) || !aiAvailable(report);
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
    root.SensorPotentialParts?.cancelAll();
    generation++; stopCapture(); bridgeReady = false; activeScope = key; pending = null; report = null; review.hidden = true; result.hidden = true; confirmed.checked = false;
    shownKeys = []; shownSeries = ''; channelPicker.replaceChildren(); codeReadings.replaceChildren();
    aiResult.replaceChildren(); summary.replaceChildren(); evidenceBody.replaceChildren(); chartInstance?.clear(); controls();
  }
  function selectedChannels(data) {
    return shownKeys.map(key => (data.channels || []).find(channel => channel.key === key)).filter(Boolean);
  }
  function plottedChannels(data) {
    return selectedChannels(data).filter(channel => kindOf(channel) !== 'code' && (data.chart_points || []).some(point => typeof point[channel.key] === 'number' && Number.isFinite(point[channel.key])));
  }
  function renderChannelPicker(data) {
    const channels = data.channels || [];
    if (shownSeries !== data.series_id) {
      const preferred = Object.keys(CHANNELS).map(key => channels.find(channel => channel.key === key)).filter(Boolean);
      shownKeys = [...preferred,...channels.filter(channel => !preferred.includes(channel) && kindOf(channel) === 'continuous'), ...channels.filter(channel => !preferred.includes(channel) && kindOf(channel) !== 'continuous')].slice(0,4).map(channel => channel.key);
      shownSeries = data.series_id;
    }
    channelPicker.replaceChildren();
    for (let index = 0; index < Math.min(4,channels.length); index++) {
      const label = make('label', '', 'sensor-series-channel-slot');
      label.append(make('span', `显示信号 ${index + 1}`));
      const select = make('select'); select.id = `sensor-series-channel-${index}`; select.setAttribute('aria-label', `显示信号 ${index + 1}`);
      const blank = make('option', '不显示'); blank.value = ''; select.append(blank);
      for (const channel of channels) {
        const option = make('option', `${KINDS[kindOf(channel)] || '传感器'} · ${choiceLabel(channel,channels)} · ${unitOf(channel)}`); option.value = channel.key; option.title = `${sourceLabel(channel)} · ${channelId(channel)}`;
        option.disabled = shownKeys.includes(channel.key) && shownKeys[index] !== channel.key;
        select.append(option);
      }
      select.value = shownKeys[index] || '';
      const selectedChannel = channels.find(channel => channel.key === select.value);
      select.title = selectedChannel ? `${sourceLabel(selectedChannel)} · ${channelId(selectedChannel)}` : '';
      select.onchange = () => {
        if (!reportMatches(data,chosen()) || report?.series_id !== data.series_id) return;
        shownKeys[index] = select.value; renderChannelPicker(data); drawChart(data);
      };
      label.append(select); channelPicker.append(label);
    }
    const groups = Object.entries(KINDS).map(([kind,label]) => { const count = channels.filter(channel => kindOf(channel) === kind).length; return count ? `${label} ${count} 项` : ''; }).filter(Boolean);
    pickerNote.textContent = `${groups.join(' · ')}。上方可切换查看全部 ${channels.length} 项，最多同时显示 4 项。状态、编码与标识不做连续趋势外推。`;
  }
  function chartOption(data) {
    const channels = plottedChannels(data);
    const panel = 132;
    chart.style.height = `${channels.length * panel + 52}px`;
    return {
      animation:false, textStyle:{fontFamily:'Arial, Microsoft YaHei, sans-serif'},
      tooltip:{trigger:'axis',confine:true}, axisPointer:{link:[{xAxisIndex:'all'}]},
      grid:channels.map((row, index) => ({top:24 + index * panel,height:80,left:56,right:24})),
      title:channels.map((row,index) => ({text:`${choiceLabel(row,data.channels)} (${unitOf(row)})`,left:12,top:index * panel,textStyle:{fontSize:12,fontWeight:500,color:'#365b7c'}})),
      xAxis:channels.map((row,index) => ({type:'time',gridIndex:index,axisLabel:{fontSize:10,color:'#6c849a',formatter:value => stamp(value)},splitLine:{show:false},axisLine:{lineStyle:{color:'#c4d5e5'}}})),
      yAxis:channels.map((row,index) => ({type:'value',gridIndex:index,scale:true,minInterval:kindOf(row) === 'state' ? 1 : undefined,axisLabel:{fontSize:10,color:'#6c849a'},splitLine:{lineStyle:{color:'#e8eff6'}}})),
      dataZoom:[{type:'inside',xAxisIndex:channels.map((row,index)=>index),filterMode:'none'},
        {type:'slider',xAxisIndex:channels.map((row,index)=>index),bottom:0,height:20,borderColor:'#d1deec',filterMode:'none',showDetail:false}],
      series:channels.map((row,index) => ({name:`${choiceLabel(row,data.channels)} (${unitOf(row)})`,type:'line',step:kindOf(row) === 'state' ? 'end' : false,xAxisIndex:index,yAxisIndex:index,
        data:chartData(data.chart_points,row.key),showSymbol:false,connectNulls:false,lineStyle:{width:1.8,color:COLORS[index % COLORS.length]},itemStyle:{color:COLORS[index % COLORS.length]}}))
    };
  }
  function drawChart(data) {
    const chosenChannels = selectedChannels(data), plotted = plottedChannels(data);
    chart.title = plotted.map(channel => `${sourceLabel(channel)} · ${channelId(channel)}`).join('\n');
    chart.hidden = plotted.length === 0;
    codeReadings.replaceChildren();
    for (const channel of chosenChannels.filter(row => kindOf(row) === 'code' || (kindOf(row) === 'state' && !plotted.includes(row)))) {
      const block = make('section', '', 'sensor-series-code-card'); block.append(make('h4',choiceLabel(channel,data.channels)),make('p',kindOf(channel) === 'code' ? '原始编码/标识 · 不作连续趋势分析' : '状态记录 · 不作连续趋势外推','sensor-series-citation'));
      const samples = (data.chart_points || []).filter(point => point[channel.key] !== null && point[channel.key] !== undefined).slice(-5);
      const appendReading = (time,value) => { for (const item of Array.isArray(value) ? value : [value]) block.append(make('p',`${stamp(time)} · ${String(item)}`)); };
      for (const sample of samples) appendReading(sample.timestamp,sample[channel.key]);
      if (!samples.length && channel.latest !== null && channel.latest !== undefined) appendReading(channel.latest_at,channel.latest);
      else if (!samples.length) block.append(make('p','所选窗口暂无有效记录。'));
      codeReadings.append(block);
    }
    chart.setAttribute('aria-label', `${plotted.length} 项传感器或状态曲线，${data.sample_count} 条采样，${stamp(data.window.start)} 至 ${stamp(data.window.end)}。数据缺口以断线表示。`);
    if (!plotted.length) { chartInstance?.clear(); return; }
    if (!root.echarts) { chart.textContent = '曲线组件尚未加载，请刷新页面。下方仍可查看数值范围与趋势依据。'; return; }
    if (!chartInstance) chartInstance = root.echarts.init(chart);
    chartInstance.setOption(chartOption(data), true); chartInstance.resize();
  }
  function renderAI(data) {
    root.SensorPotentialParts?.cancelAll();
    aiResult.replaceChildren();
    const renderedScope = scopeKey(chosen()), analysisKey = JSON.stringify(data.ai_analysis);
    const isCurrent = () => reportMatches(data, chosen()) && renderedScope === scopeKey(chosen()) &&
      report?.series_id === data.series_id && JSON.stringify(report?.ai_analysis) === analysisKey;
    const analysis = data.ai_analysis;
    if (!analysis) { aiResult.append(make('p', aiAvailable(data) ? '曲线已载入。运行 XCMG AI，结合多信号变化判断可能的问题和检查顺序。' : '尚无可分析的连续传感器。单位未确认、状态、累计量与原始编码/标识保留供查看。', 'sensor-series-intro')); return; }
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
      const parts = button('潜在故障配件', `sensor-series-parts-${index}`);
      const target = make('div', '', 'sensor-potential-parts');
      target.id = `sensor-potential-parts-${index}`;
      parts.setAttribute('aria-controls', target.id);
      parts.disabled = typeof root.SensorPotentialParts?.open !== 'function';
      parts.onclick = async () => {
        if (parts.disabled || !isCurrent() || typeof root.SensorPotentialParts?.open !== 'function') return;
        parts.disabled = true;
        try {
          await root.SensorPotentialParts.open({target,machine:{...chosen()},seriesId:data.series_id,
            hypothesisIndex:index,hypothesis:{...hypothesis},analysisKey,isCurrent});
        } catch (error) {
          if (isCurrent()) target.textContent = error.message || '备件资料暂时未能打开，请重试。';
        } finally { parts.disabled = false; }
      };
      article.append(parts, target); aiResult.append(article);
    }
    const continuation = data.prediction?.continuation;
    const continuationChannel = (data.channels || []).find(channel => channel.key === continuation?.channel && kindOf(channel) === 'continuous');
    if (continuation && continuationChannel) {
      const note = make('details', '', 'sensor-series-evidence'); note.append(make('summary', '短时走势参考'));
      note.append(make('p', `若末段趋势持续，未来 ${number(continuation.horizon_minutes)} 分钟的变化约为 ${number(continuation.change_if_trend_persists)} ${unitOf(continuationChannel)}。${continuation.condition || ''}`)); aiResult.append(note);
    }
    aiResult.append(make('p', '以上为连续工况的风险线索，需结合现场检查核实；故障发生时间尚未标定。', 'sensor-series-limit'));
  }
  function render(data) {
    if (!reportMatches(data, chosen())) return;
    report = data; result.hidden = false; summary.replaceChildren();
    const samples = make('div'); samples.append(make('strong',number(data.sample_count)),make('span','条连续采样'));
    const signals = make('div'); signals.append(make('strong',String(data.channels.length)),make('span','项传感器与状态通道'));
    const windowBox = make('div', '', 'sensor-series-window'); windowBox.append(make('strong',`${stamp(data.window.start)} — ${stamp(data.window.end)}`),make('span','采集区间 · 按本机时区显示'));
    summary.append(samples,signals,windowBox);
    chartNote.textContent = data.quality.gap_count > 0 ? `曲线保留 ${data.quality.gap_count} 处采集间隔；缺口不连线。` : '各信号按同一时间轴对齐。';
    evidenceBody.replaceChildren();
    evidenceBody.append(make('p',`${data.model} · ${data.binding} · ${data.segments.length} 段记录`, 'sensor-series-citation'));
    const ranges = make('ul');
    for (const channel of data.channels) {
      const name = choiceLabel(channel,data.channels), original = sourceLabel(channel);
      ranges.append(make('li',`${KINDS[kindOf(channel)] || '传感器'} · ${name}${original !== displayLabel(channel) ? `（${original}）` : ''}：${kindOf(channel) === 'code' ? '保留原始文本' : `${number(channel.min)}–${number(channel.max)} ${unitOf(channel)}`}，${channel.count} 个有效值`));
    }
    evidenceBody.append(ranges);
    for (const row of data.evidence || []) { const block = make('div', '', 'sensor-series-evidence-row'); block.append(make('strong',row.title),make('p',row.detail)); evidenceBody.append(block); }
    evidenceBody.append(make('p',`典型采样间隔 ${number(data.quality.median_interval_seconds)} 秒；最长间隔 ${number(data.quality.max_gap_seconds / 3600)} 小时。导出记录未注明聚合方式。`, 'sensor-series-citation'));
    if (!aiAvailable(data)) status.textContent = '记录已载入；暂没有单位已确认的连续传感器，可查看状态与原始读数。';
    else status.textContent = data.ai_analysis ? '已结合连续曲线生成风险线索。' : '连续曲线已载入，可开始 AI 分析。';
    renderChannelPicker(data); drawChart(data); renderAI(data); controls();
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
  function prepareExports(exports, capture, originType, fileName) {
    const machine = chosen(); pending = null; review.hidden = true; confirmed.checked = false; controls();
    if (!validMachine(machine)) throw new Error('请先关联当前设备。');
    if (!Array.isArray(exports) || !exports.length || exports.length > MAX_EXPORTS) throw new Error('一次最多载入 32 份 Trackunit CSV。');
    let totalBytes = 0; const allChannels = new Map();
    const batches = exports.map(entry => {
      if (typeof entry?.csv_text !== 'string') throw new Error('读取的 CSV 内容不完整，请重试。');
      const bytes = new TextEncoder().encode(entry.csv_text).length;
      if (bytes > MAX_FILE_BYTES) throw new Error('CSV 超过 3 MB，请缩小导出时间范围。');
      totalBytes += bytes;
      if (totalBytes > MAX_BATCH_BYTES) throw new Error('整批 CSV 超过 24 MB，请缩小导出时间范围。');
      if ((entry.asset_id && entry.asset_id !== machine.machine_id) || (entry.page_url && !capturePageMatches(entry.page_url,machine.machine_id))) throw new Error('批次来源与当前设备不一致，请重新读取。');
      if (entry.captured_at && !Number.isFinite(Date.parse(entry.captured_at))) throw new Error('批次采集时间无效，请重新读取。');
      const channels = channelsForCSV(entry.csv_text,entry.channel_metadata,entry.units,entry.sensors);
      const units = {}, metadata = {};
      for (const channel of channels) {
        const previous = allChannels.get(channel.key);
        if (previous && previous.unit && channel.unit && previous.unit !== channel.unit) throw new Error('同一传感器的批次单位不一致，请核对后重新导出。');
        allChannels.set(channel.key, previous?.unit && !channel.unit ? previous : channel);
        if (channel.unit) units[channel.key] = channel.unit;
        metadata[channel.key] = {label:channel.label,kind:channel.kind,...(channel.unit ? {unit:channel.unit} : {})};
      }
      const batch = {csv_text:entry.csv_text,units,channel_metadata:metadata};
      for (const key of ['page_url','captured_at']) if (entry[key]) batch[key] = entry[key];
      return batch;
    });
    if (allChannels.size > MAX_CHANNELS) throw new Error('一次最多载入 96 项传感器或状态通道。');
    pending = {exports:batches,capture,originType,machine:{...machine},scope:scopeKey(machine)};
    confirmed.checked = false; review.hidden = false;
    reviewText.textContent = `${machine.model || '当前设备'} · ${machine.serial_number || machine.machine_id} · ${fileName || '当前页面导出'} · ${batches.length} 批 / ${allChannels.size} 项信号`;
    const known = [...allChannels.values()].filter(channel => channel.unit), unknown = allChannels.size - known.length;
    unitReviewTitle.textContent = `查看 ${allChannels.size} 项信号与单位`; unitReviewList.replaceChildren(); unitReview.open = false;
    for (const channel of allChannels.values()) unitReviewList.append(make('li', `${KINDS[channel.kind]} · ${channel.label} · ${channel.unit || '单位待核对'}`));
    confirmationText.textContent = `确认这些记录属于当前设备及同一导出时段，且页面单位与下列信息一致：${known.slice(0,8).map(channel => `${channel.label} ${channel.unit}`).join('、')}${known.length > 8 ? `等 ${known.length} 项` : ''}。${unknown ? `${unknown} 项单位未注明，将保留原值，不纳入连续工况 AI 分析。` : ''}`;
    const partial = capture.collection?.complete === false;
    status.textContent = `${partial ? '部分信号未能读取，已保留成功批次。' : '已收到曲线，'}请核对设备与单位后载入。`; controls();
  }
  read.onclick = () => {
    const machine = chosen(); resetScope(machine);
    if (!validMachine(machine) || !embedded || !bridgeReady || busy) return;
    const bytes = new Uint8Array(16); crypto.getRandomValues(bytes);
    const id = Array.from(bytes, value => value.toString(16).padStart(2,'0')).join('');
    job = {id,machine:{...machine},scope:scopeKey(machine)}; busy = true;
    pending = null; review.hidden = true; confirmed.checked = false;
    status.textContent = '正在读取当前 Advanced Sensors 传感器，请保持页面和时间范围不变…'; controls();
    post({type:'jilian:sensor-series-start',request_id:id,asset_id:machine.machine_id,dataset_id:machine.dataset_id});
    watchdog = setTimeout(() => stopCapture('本次读取已超时。请确认 Advanced Sensors 已显示曲线，再重试。'), 610000);
  };
  stop.onclick = () => stopCapture('已停止读取。已保存的连续记录仍保留。');
  importOpen.onclick = () => { resetScope(chosen()); if (validMachine(chosen()) && !busy) { file.value = ''; file.click(); } };
  file.onchange = async () => {
    const selectedFiles = Array.from(file.files || []), machine = chosen(), scope = scopeKey(machine), ticket = ++generation;
    if (!selectedFiles.length) return;
    pending = null; review.hidden = true; confirmed.checked = false; busy = true; controls();
    try {
      if (selectedFiles.length > MAX_EXPORTS) throw new Error('一次最多载入 32 份 Trackunit CSV。');
      if (selectedFiles.some(item => item.size > MAX_FILE_BYTES)) throw new Error('CSV 超过 3 MB，请缩小导出时间范围。');
      if (selectedFiles.reduce((sum,item) => sum + item.size,0) > MAX_BATCH_BYTES) throw new Error('整批 CSV 超过 24 MB，请缩小导出时间范围。');
      const exports = [];
      for (const selectedFile of selectedFiles) {
        const text = await selectedFile.text(); if (!current(ticket,scope)) return;
        exports.push({csv_text:text});
      }
      prepareExports(exports, {asset_id:machine.machine_id}, 'user_confirmed_export', selectedFiles.length === 1 ? selectedFiles[0].name : `${selectedFiles.length} 份 CSV`);
    } catch (error) { if (current(ticket,scope)) status.textContent = error.message; }
    finally { if (current(ticket,scope)) { busy = false; controls(); } }
  };
  confirmed.onchange = controls;
  dismiss.onclick = () => { pending = null; review.hidden = true; controls(); status.textContent = '已取消导入。'; };
  save.onclick = async () => {
    if (!pending || !confirmed.checked || pending.scope !== scopeKey(chosen()) || busy) return;
    const input = pending, ticket = ++generation; busy = true; controls(); status.textContent = '正在对齐连续传感器记录…';
    const payload = {...identity(input.machine),exports:input.exports,source:'trackunit_advanced_sensors_export',source_asset_id:input.machine.machine_id,
      origin:input.originType};
    for (const key of ['page_url','captured_at']) if (input.capture[key]) payload[key] = input.capture[key];
    try {
      const data = await api('/assistant/sensor-series/import-batch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      if (!current(ticket,input.scope)) return;
      pending = null; review.hidden = true; render(data);
      if (input.capture.collection?.complete === false) status.textContent += ' 本次仅载入成功读取的信号，仍有未读通道。';
    } catch (error) { if (current(ticket,input.scope)) status.textContent = error.message; }
    finally { if (current(ticket,input.scope)) { busy = false; controls(); } }
  };
  analyze.onclick = async () => {
    const machine = chosen(), data = report;
    if (busy || pending || !reportMatches(data,machine) || !aiAvailable(data)) return;
    const ticket = ++generation, scope = scopeKey(machine); busy = true; controls();
    status.textContent = 'XCMG AI 正在关联已确认传感器的连续变化…';
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
    if (capture?.source !== 'trackunit_csv_export' || ![1,2].includes(capture.schema_version) || capture.asset_id !== machine.machine_id ||
      !capturePageMatches(capture.page_url,machine.machine_id) || !Number.isFinite(Date.parse(capture.captured_at)) || (!Array.isArray(capture.exports) && typeof capture.csv_text !== 'string')) {
      stopCapture('曲线来源与当前设备不一致，请重新读取。'); return;
    }
    stopCapture();
    try { prepareExports(capture.exports || [capture],capture,'browser_export_capture'); } catch (error) { status.textContent = error.message; }
  });
  root.addEventListener('hashchange', () => resetScope(chosen()));
  document.getElementById('machine')?.addEventListener('change', () => resetScope(chosen()));
  root.addEventListener('resize', () => chartInstance?.resize());
  if (root.ResizeObserver) new root.ResizeObserver(() => chartInstance?.resize()).observe(card);
  root.renderRiskDemo = load;
  root.SensorSeriesWorkspace.reload = load;
  controls();
})(typeof window !== 'undefined' ? window : globalThis);
