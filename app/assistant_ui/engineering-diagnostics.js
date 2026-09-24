/* One device-scoped engineering investigation; test input never changes telemetry. */
(function (global) {
  const configurations = ['unknown', 'XE55U.00III', 'XE55U.00VI'];
  const isXE55U = machine => String(machine?.model || '').trim().toUpperCase() === 'XE55U';
  const scopeKey = (machine, source) => machine ? JSON.stringify([machine.machine_id, machine.dataset_id || null,
    machine.selection_id, machine.serial_number, machine.model, machine.dataset_id ? machine.provenance : source]) : null;
  function normalizeFault(value) {
    if (!value || value.model !== 'XE55U' || !/^[EAP]\d{3,6}$/.test(String(value.code || '').trim().toUpperCase()) ||
        !configurations.includes(value.configuration) || !['test', 'operator_report'].includes(value.source)) return null;
    return { code: value.code.trim().toUpperCase(), model: 'XE55U', configuration: value.configuration, source: value.source };
  }
  class EngineeringState {
    constructor() { this.key = null; this.entries = new Map(); this.epoch = 0; }
    select(machine, source) { const key = scopeKey(machine, source); if (key !== this.key) { this.key = key; ++this.epoch; } }
    attach(value, machine, source) {
      const fault = normalizeFault(value);
      if (!isXE55U(machine) || !fault || this.key !== scopeKey(machine, source)) throw new Error('请选择 XE55U，并核对故障码、来源和配置。');
      this.entries.set(this.key, fault); return { ...fault };
    }
    payload(machine, source) { const entry = this.entries.get(this.key); return this.key && this.key === scopeKey(machine, source) && isXE55U(machine) && entry ? { ...entry } : null; }
    clear() { if (this.key) this.entries.delete(this.key); }
    ticket() { return { key: this.key, epoch: this.epoch }; }
    accepts(ticket) { return ticket.key === this.key && ticket.epoch === this.epoch; }
  }
  function trustedCapture(data, { origin, expectedOrigin, isParent, connectionId, machine, hash, busy }) {
    return Boolean(!busy && isParent && /^chrome-extension:\/\/[a-p]{32}$/.test(expectedOrigin || '') && origin === expectedOrigin &&
      data?.type === 'jilian:xgss-catalog-capture' && data.protocol === 1 && connectionId && data.connection_id === connectionId &&
      typeof data.request_id === 'string' && /^[\w:-]{1,120}$/.test(data.request_id) && machine && data.asset_id === machine.machine_id &&
      hash === '#trackunit-asset=' + machine.machine_id && (data.dataset_id || null) === (machine.dataset_id || null));
  }
  function safeSourceUrl(value) { try { const u = new URL(value); return u.protocol === 'https:' && !u.username && !u.password ? u.href : null; } catch (_) { return null; } }
  const exports = { EngineeringState, scopeKey, isXE55U, normalizeFault, trustedCapture, safeSourceUrl };
  if (typeof module !== 'undefined' && module.exports) module.exports = exports;
  global.EngineeringDiagnostics = exports;
  if (typeof document === 'undefined') return;

  const byId = id => document.getElementById(id), state = new EngineeringState();
  const machine = () => typeof selected === 'function' ? selected() : null;
  const source = () => typeof defaultSource === 'undefined' ? null : defaultSource;
  const realContext = () => { const m = machine(); return Boolean(m && (m.dataset_id ? m.provenance === 'user_supplied' : source() === 'trackunit_cache')); };
  const text = (tag, value, className) => { const node = document.createElement(tag); node.textContent = value || ''; if (className) node.className = className; return node; };
  let locked = false, catalog = null, catalogTicket = 0, importing = false;
  const draftChanged = () => { if (typeof refreshLocalDraftControls === 'function') refreshLocalDraftControls(); };
  function inputFault() { return { code: byId('engineering-code').value, model: 'XE55U', configuration: byId('engineering-configuration').value, source: byId('engineering-source').value }; }
  function setInputs(fault) {
    byId('engineering-code').value = fault?.code || 'E4030';
    byId('engineering-source').value = fault?.source || 'test';
    byId('engineering-configuration').value = fault?.configuration || 'unknown';
  }
  function renderInput() {
    const available = isXE55U(machine()), fault = state.payload(machine(), source());
    byId('engineering-fault-panel').hidden = !available;
    byId('engineering-start').hidden = !available; byId('engineering-start').disabled = locked;
    byId('engineering-source-note').textContent = byId('engineering-source').value === 'test'
      ? '测试故障：用于验证排查流程，不代表 Trackunit 上报或实机发生该故障。'
      : '人工报告：由操作者提供，尚未与 Trackunit 故障事件核验。';
    byId('engineering-configuration-note').textContent = byId('engineering-configuration').value === 'unknown'
      ? '配置待核对；先按机型查阅资料，不能据此确认零件适配。'
      : '所选配置由人工提供，需与机器铭牌和对应 VIN 图册核对。';
    byId('engineering-linked').hidden = !fault;
    byId('engineering-linked-label').textContent = fault ? `${fault.code} · ${fault.source === 'test' ? '测试故障' : '人工报告'} · ${fault.configuration === 'unknown' ? '配置待核对' : fault.configuration}` : '';
    for (const id of ['engineering-code', 'engineering-source', 'engineering-configuration', 'engineering-attach', 'engineering-remove']) byId(id).disabled = locked || !available;
    byId('engineering-attach').textContent = fault ? '已带入本次 AI 排查' : '带入本次 AI 排查';
    byId('engineering-catalog-refresh').disabled = locked || !available || !realContext() || importing;
    byId('engineering-catalog-continue').disabled = locked || !available || !catalog?.items?.length || !fault || importing;
  }
  function renderCatalog(message) {
    const root = byId('engineering-catalog-items'); root.replaceChildren();
    byId('engineering-catalog-status').textContent = message || (!realContext() ? '当前为模拟设备，用于验证手册排查。XGSS 图册读取需要选择对应的实测设备。' : catalog?.items?.length
      ? `已读取 ${catalog.items.length} 条可见图册条目 · ${typeof displayDate === 'function' ? displayDate(catalog.captured_at) : catalog.captured_at || ''}。仅覆盖已打开页面，不代表整机完整 BOM。`
      : '尚未读取图册条目。打开对应 VIN 的 XGSS 图册，在 Chrome 助手的“图册”中点击“读回当前图册条目”，再回到这里继续分析。');
    if (catalog?.items?.length) {
      const table = document.createElement('table'), head = table.createTHead().insertRow();
      ['图册条目 / 料号', '图号 / 位置'].forEach(label => { const th = text('th', label); th.scope = 'col'; head.append(th); });
      const body = table.createTBody();
      for (const item of catalog.items) {
        const row = body.insertRow(); row.insertCell().textContent = `${item.name}\n${item.part_number}`;
        row.insertCell().textContent = `${item.figure_ref || '未读取图号'}\n${(item.assembly_path || catalog.assembly_path || []).join(' / ') || '位置待核对'}`;
      }
      root.append(table);
    }
    renderInput();
  }
  async function refreshCatalog() {
    const current = machine(), ticket = ++catalogTicket, device = state.ticket();
    if (!isXE55U(current) || !realContext()) { catalog = null; renderCatalog(); return; }
    byId('engineering-catalog-status').textContent = '正在读取此设备保存的 XGSS 图册条目…';
    const params = new URLSearchParams({ machine_id: current.machine_id, vin: String(current.serial_number || '').trim().toUpperCase() });
    if (current.dataset_id) params.set('dataset_id', current.dataset_id);
    try {
      const response = await api('/assistant/xgss/catalog-context?' + params);
      if (ticket !== catalogTicket || !state.accepts(device)) return;
      catalog = response.status === 'captured' ? response : null; renderCatalog();
    } catch (error) { if (ticket === catalogTicket && state.accepts(device)) { catalog = null; renderCatalog('图册条目读取失败：' + error.message); } }
  }
  function referenceLabel(ref) { return `${ref.configuration || ref.model || ''} · ${ref.version || ''} · PDF 第 ${(ref.pdf_pages || []).join('、')} 页`; }
  function renderEngineeringReport(root, saved) {
    root.replaceChildren();
    const refs = saved.manual_references || [], hypotheses = saved.component_hypotheses || [], fault = saved.engineering_fault;
    root.hidden = !fault && !refs.length && !hypotheses.length; if (root.hidden) return;
    root.append(text('h3', '故障 → 可疑部件 → 图册检索'));
    if (fault) root.append(text('p', `${fault.model || 'XE55U'} · ${fault.code} · ${fault.source === 'test' ? '测试故障，非 Trackunit 实机事件' : '人工报告故障'} · ${fault.configuration === 'unknown' ? '配置待核对' : fault.configuration + '（人工选择，适配待核对）'}`, 'engineering-origin'));
    if (!hypotheses.length) root.append(text('p', '本次尚未形成有资料依据的部件判断。可补充现象，或核对故障码与适用配置。', 'muted'));
    for (const hypothesis of hypotheses) {
      const item = text('article', '', 'engineering-hypothesis');
      item.append(text('h4', hypothesis.component), text('p', hypothesis.rationale));
      if (hypothesis.feedback_effect) item.append(text('p', '检查反馈对判断的影响：' + hypothesis.feedback_effect, 'engineering-feedback-effect'));
      const matchedRefs = refs.filter(ref => (hypothesis.reference_ids || []).includes(ref.reference_id));
      item.append(text('p', '依据：' + (matchedRefs.map(referenceLabel).join('；') || '待核对资料引用'), 'check-source'));
      item.append(text('p', '图册检索词：' + (hypothesis.search_terms || []).join(' · '), 'engineering-search-terms'));
      if (hypothesis.checks?.length) {
        const list = document.createElement('ul');
        for (const check of hypothesis.checks) list.append(text('li', check.text || check.title));
        item.append(list);
      }
      const candidates = (saved.parts_candidates || []).filter(part => (hypothesis.part_candidate_ids || []).includes(part.source_id || part.part_id || part.candidate_id));
      item.append(text('p', candidates.length ? '图册候选：' + candidates.map(part => `${part.name} / ${part.part_number}`).join('；') : '尚未关联具体料号；可按以上检索词查阅图册并读取条目。', 'muted'));
      root.append(item);
    }
    if (refs.length) {
      const details = document.createElement('details'); details.append(text('summary', `查看手册摘录与页码（${refs.length} 条）`));
      for (const ref of refs) {
        const item = text('div', '', 'engineering-reference'); item.append(text('strong', ref.title), text('p', referenceLabel(ref), 'muted'));
        if (ref.section) item.append(text('p', ref.section));
        if (ref.text) item.append(text('p', ref.text, 'engineering-excerpt'));
        const href = safeSourceUrl(ref.source_url);
        if (href) { const link = text('a', '打开资料来源 ↗'); link.href = href; link.target = '_blank'; link.rel = 'noopener noreferrer'; item.append(link); }
        details.append(item);
      }
      root.append(details);
    }
  }
  global.getEngineeringFault = () => state.payload(machine(), source());
  global.restoreEngineeringFault = value => {
    state.clear(); const normalized = normalizeFault(value);
    if (normalized && isXE55U(machine())) state.attach(normalized, machine(), source());
    setInputs(state.payload(machine(), source())); renderInput(); draftChanged();
  };
  global.engineeringDeviceChanged = () => {
    state.select(machine(), source()); setInputs(state.payload(machine(), source()));
    catalog = null; ++catalogTicket; renderInput(); renderCatalog(); refreshCatalog();
  };
  global.setEngineeringBusy = busy => { locked = busy; renderInput(); };
  global.renderEngineeringReport = saved => renderEngineeringReport(byId('engineering-report'), saved);
  global.renderEngineeringReportInto = renderEngineeringReport;
  byId('engineering-attach').onclick = () => {
    if (locked) return;
    try {
      const prior = state.payload(machine(), source());
      const attached = state.attach(inputFault(), machine(), source());
      if (JSON.stringify(prior) !== JSON.stringify(attached) && typeof priorRecordId !== 'undefined') priorRecordId = null;
      if (typeof restoreManualFaultReference === 'function') restoreManualFaultReference(null);
      renderInput(); draftChanged();
      if(typeof global.focusXGSSResearch==='function'){global.focusXGSSResearch(attached.code);return;}
      byId('status').textContent = '已带入故障与配置。点击“开始分析”，AI 将结合设备数据和适用手册排查。';
    } catch (error) { byId('engineering-source-note').textContent = error.message; }
  };
  byId('engineering-remove').onclick = () => { if (!locked) { state.clear(); if (typeof priorRecordId !== 'undefined') priorRecordId = null; renderInput(); draftChanged(); } };
  for (const id of ['engineering-code', 'engineering-source', 'engineering-configuration']) byId(id).addEventListener('input', () => { state.clear(); if (typeof priorRecordId !== 'undefined') priorRecordId = null; renderInput(); draftChanged(); });
  byId('engineering-start').onclick = () => {
    if (locked || !isXE55U(machine())) return;
    setInputs({ code: 'E4030', source: 'test', configuration: 'unknown' });
    byId('engineering-attach').onclick(); byId('engineering-fault-panel').open = true;
    byId('engineering-fault-panel').scrollIntoView({ block: 'start' }); byId('engineering-configuration').focus({ preventScroll: true });
  };
  byId('engineering-catalog-refresh').onclick = refreshCatalog;
  byId('engineering-catalog-continue').onclick = () => {
    if (locked || !catalog?.items?.length || !state.payload(machine(), source())) return;
    const competitionFocus=document.documentElement?.classList?.contains?.('competition-focus')===true;
    if (!competitionFocus && typeof report !== 'undefined' && report?.record_id) priorRecordId = report.record_id;
    byId('question').value = competitionFocus
      ? '结合本次故障与当前 VIN 的 XGSS 图册条目，更新可疑部件排序，说明候选料号的依据和待核对事项。'
      : '结合本次故障、已保存检查反馈与当前 VIN 的 XGSS 图册条目，更新可疑部件排序，说明候选料号的依据和待核对事项。';
    byId('question-details').open = true; draftChanged(); byId('form').requestSubmit();
  };
  global.addEventListener('message', async event => {
    const data = event.data, origin = location.ancestorOrigins?.[0], current = machine();
    if (!trustedCapture(data, { origin: event.origin, expectedOrigin: origin, isParent: event.source === global.parent,
      connectionId: new URLSearchParams(location.search).get('panel'), machine: current, hash: location.hash, busy: false })) return;
    const reply = values => global.parent.postMessage({ type: 'jilian:xgss-catalog-result', protocol: 1,
      connection_id: data.connection_id, request_id: data.request_id, ...values }, origin);
    if (locked || importing) { reply({ success: false, message: '当前分析或读取尚未结束，请完成后再次读取图册。' }); return; }
    const device = state.ticket(); importing = true; renderInput();
    try {
      const saved = await api('/assistant/xgss/catalog-context', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ machine_id: current.machine_id, dataset_id: current.dataset_id || null, capture: data.capture }) });
      reply({ success: true, message: '已保存此设备的可见图册条目，可返回助手继续分析。', capture_id: saved.context?.capture_id || saved.capture_id });
      if (state.accepts(device)) await refreshCatalog();
    } catch (error) { reply({ success: false, message: error.message }); if (state.accepts(device)) renderCatalog('图册未导入：' + error.message); }
    finally { importing = false; renderInput(); }
  });
  global.engineeringDeviceChanged();
})(globalThis);
