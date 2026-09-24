/**
 * Replay a real saved AI investigation.
 *
 * This is the only thing the demo view shows. A scripted simulation used to sit beside
 * it, which meant a reviewer saw a preset walkthrough before seeing what the model
 * actually produced; presenting a simulation next to genuine output only weakens the
 * genuine output. The page reads saved records straight from disk, so a reviewer sees
 * real model behaviour without an API call and without mistaking a recording for a live
 * run.
 *
 * It renders only what the backend replay payload contains: no wording about the AI is
 * written here, so the page cannot claim more than the record shows.
 */
(() => {
  const byId = id => document.getElementById(id);
  const node = (tag, value, className) => {
    const item = document.createElement(tag);
    item.textContent = value;
    if (className) item.className = className;
    return item;
  };
  let listing = null, current = null, loading = null;

  /** Load the listing on entry; the view has nothing else to fall back to. */
  function show() {
    if (typeof updateDemoDisclosure === 'function') updateDemoDisclosure();
    return loadListing();
  }

  function shortId(value, keep = 8) {
    const text = String(value == null ? '' : value).trim();
    if (!text) return '';
    return text.length <= keep + 3 ? text : text.slice(0, keep) + '…';
  }

  function renderMeta(record) {
    const root = byId('replay-meta');
    root.replaceChildren();
    // Read the machine as a person would say it, using the fields the backend
    // resolved from the record. The full identifiers stay on the record and in the
    // exported pack, so shortening the screen loses nothing.
    const machine = [record.machine_model || '机型未记录',
      record.machine_serial || shortId(record.machine_id)].filter(Boolean).join(' · ');
    const rows = [
      ['设备', machine],
      ['数据来源', record.source],
      ['AI 模型', [record.provider, record.ai_model].filter(Boolean).join(' / ') || '未记录'],
      ['数据版本', record.dataset_id ? shortId(record.dataset_id) : '无（车队缓存）'],
      ['生成时间', record.generated_at],
      ['分析任务', record.task],
      ['本次提问', record.question],
      ['故障输入', record.fault ? `${record.fault.code}（来源：${record.fault.source}，配置：${record.fault.configuration || '未核对'}）` : '无'],
      ['承接记录', record.prior_record_id ? `是（${shortId(record.prior_record_id)}）` : '否'],
      ['AI 运行位置', record.inference_location],
    ];
    for (const [label, value] of rows) {
      if (value === null || value === undefined || value === '') continue;
      const cell = document.createElement('div');
      const term = node('dt', label), definition = node('dd', value);
      cell.append(term, definition);
      root.append(cell);
    }
    const full = document.createElement('details');
    full.className = 'replay-identifiers';
    // Collapsed by default: the readable identifiers are the point of the header,
    // and the full values are one click away for anyone tracing the record.
    full.open = false;
    full.append(node('summary', '完整标识（用于追溯）'));
    const list = document.createElement('ul');
    for (const [label, value] of [['设备', record.machine_id], ['数据版本', record.dataset_id],
      ['记录编号', current?.record_id], ['承接记录', record.prior_record_id]]) {
      if (value) list.append(node('li', `${label}：${value}`));
    }
    full.append(list);
    root.append(full);
  }

  function renderStages(data) {
    const root = byId('replay-stages');
    root.replaceChildren();
    for (const stage of data.stages || []) {
      const item = document.createElement('li');
      item.dataset.origin = stage.origin;
      const head = document.createElement('div');
      head.className = 'replay-stage-head';
      const tag = node('span', {program: '数据', ai: 'AI', mixed: '记录'}[stage.origin] || stage.origin, 'replay-origin');
      head.append(tag, node('strong', stage.title));
      item.append(head);
      const list = document.createElement('ul');
      for (const line of stage.lines || []) list.append(node('li', line, 'pre'));
      if (!(stage.lines || []).length) list.append(node('li', '本次没有可展示的条目。', 'muted'));
      item.append(list);
      if (stage.note) item.append(node('p', stage.note, 'muted'));
      root.append(item);
    }
  }

  function render(data) {
    current = data;
    byId('replay-title').textContent = data.title;
    byId('replay-disclosure').textContent = data.disclosure;
    renderMeta(data.record || {});
    if (typeof renderAIContribution === 'function') {
      renderAIContribution({ai_contribution: data.ai_contribution}, byId('replay-contribution'));
    }
    renderStages(data);
    const facts = byId('replay-facts');
    facts.replaceChildren();
    for (const text of data.data_facts || []) facts.append(node('li', text));
    if (!(data.data_facts || []).length) facts.append(node('li', '该记录没有独立的数据事实条目。', 'muted'));
    byId('replay-content').hidden = false;
    byId('replay-status').hidden = true;
    // The pack is generated by the backend from the same record, so the download
    // cannot drift from what this page shows.
    const exportLink = byId('replay-export');
    if (exportLink) exportLink.href = '/assistant/demo-replay/' + encodeURIComponent(data.record_id) + '/report.md';
  }

  function renderPicker(records) {
    const picker = byId('replay-picker');
    picker.replaceChildren();
    for (const row of records) {
      const option = document.createElement('option');
      option.value = row.record_id;
      const parts = [row.generated_at, row.machine_model || shortId(row.machine_id),
        row.ai_model, `决策 ${row.model_decisions} 次`];
      if (row.fault_code) parts.push(row.fault_code);
      if (row.hypothesis_count) parts.push(`${row.hypothesis_count} 个部件假设`);
      option.textContent = parts.filter(Boolean).join(' · ');
      picker.append(option);
    }
  }

  async function openRecord(recordId) {
    byId('replay-status').hidden = false;
    byId('replay-status').textContent = '正在读取该记录…';
    try {
      const data = await api('/assistant/demo-replay/' + encodeURIComponent(recordId));
      render(data);
    } catch (error) {
      byId('replay-content').hidden = true;
      byId('replay-status').hidden = false;
      byId('replay-status').textContent = '该记录无法回放：' + error.message;
    }
  }

  function loadListing() {
    if (listing || loading) return loading;
    byId('replay-status').hidden = false;
    byId('replay-status').textContent = '正在读取本机记录…';
    loading = api('/assistant/demo-replay').then(data => {
      listing = data;
      byId('replay-disclosure').textContent = [data.scope, ...(data.disclosure || [])].join(' ');
      if (!(data.records || []).length) {
        byId('replay-status').textContent = '本机还没有可回放的真实 AI 记录。请先在工作区完成一次分析并保存。';
        return;
      }
      renderPicker(data.records);
      return openRecord(data.records[0].record_id);
    }).catch(error => {
      byId('replay-status').textContent = '无法读取本机记录：' + error.message;
    }).finally(() => { loading = null; });
    return loading;
  }

  byId('replay-picker').onchange = event => openRecord(event.target.value);
  // The demo view has one source now, so entry loads the listing directly.
  window.showReplayMode = show;
  window.enterDemoReplay = show;
})();
