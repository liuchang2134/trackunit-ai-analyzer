/* Offline reference selection is separate from confirmed device diagnosis context. */
(function (global) {
  const MODEL = 'TV12U', VERSION = '260224';
  const isTV12U = machine => String(machine?.model || '').trim().toUpperCase() === MODEL;
  function deviceKey(machine, source) {
    return machine?.machine_id ? JSON.stringify([
      machine.selection_id || machine.machine_id, machine.machine_id, machine.dataset_id || null,
      machine.dataset_id ? machine.provenance : source, String(machine.model || '').trim().toUpperCase()
    ]) : null;
  }
  class FaultAssociation {
    constructor() { this.key = null; this.candidate = null; this.linked = null; this.restored = null; }
    switchDevice(machine, source) {
      const next = deviceKey(machine, source), changed = next !== this.key;
      if (changed) { this.linked = null; this.restored = null; }
      this.key = next;
      return changed;
    }
    choose(item, catalog, preserveRestored = false) {
      this.linked = null;
      if (!preserveRestored) this.restored = null;
      this.candidate = item && catalog?.model === MODEL && catalog?.version === VERSION
        && /^[EH][0-9]{5}$/.test(item.code) ? { code: item.code, model: MODEL, version: VERSION } : null;
    }
    attach(machine, source, confirmed) {
      if (!isTV12U(machine)) throw new Error('当前设备型号不是 TV12U，可独立查阅，不能带入该设备诊断。');
      if (confirmed !== true || !this.candidate || !this.key || deviceKey(machine, source) !== this.key)
        throw new Error('请先核对当前设备与协议适用范围，再确认带入。');
      this.linked = { ...this.candidate, applicability_confirmed: true };
      this.restored = null;
      return { ...this.linked };
    }
    payload(machine, source) {
      return this.linked && this.key === deviceKey(machine, source) && isTV12U(machine) ? { ...this.linked } : null;
    }
    stageRestore(manual, machine, source) {
      this.clear(); this.candidate = null;
      if (!isTV12U(machine) || this.key !== deviceKey(machine, source) || manual?.model !== MODEL
        || manual.version !== VERSION || manual.applicability_confirmed !== true || !/^[EH][0-9]{5}$/.test(manual.code)) return false;
      this.restored = { code: manual.code, model: MODEL, version: VERSION, applicability_confirmed: true };
      return true;
    }
    draftPayload(machine, source) {
      const linked = this.payload(machine, source);
      return linked || (this.restored && this.key === deviceKey(machine, source) && isTV12U(machine) ? { ...this.restored } : null);
    }
    clear() { this.linked = null; this.restored = null; }
  }
  function xgssSummary(data) {
    if (!data) return 'XGSS 配置状态读取失败，可稍后刷新。';
    if (!data.catalog_ready) return 'XGSS 通用图册入口尚未就绪。' + (data.reason || '请检查本机配置。');
    return 'XGSS 通用图册入口已配置；' + (data.fault_ready ? '故障手册查询字段已配置。' : '故障手册直达字段待确认。')
      + '具体图册和手册内容需打开官方页面后核对。';
  }
  const exported = { FaultAssociation, deviceKey, isTV12U, xgssSummary };
  if (typeof module !== 'undefined' && module.exports) module.exports = exported;
  global.FaultReference = exported;
  if (typeof document === 'undefined') return;

  const byId = id => document.getElementById(id), binding = new FaultAssociation();
  let catalog = null, candidate = null, requestTicket = 0, locked = false, querying = false;
  let statusLoaded = false, xgssTicket = 0, restoringScope = null;
  const text = (tag, value, className) => {
    const node = document.createElement(tag); node.textContent = value;
    if (className) node.className = className;
    return node;
  };
  const currentMachine = () => typeof selected === 'function' ? selected() : null;
  const currentSource = () => typeof defaultSource === 'undefined' ? null : defaultSource;
  const notifyDraft = () => { if (typeof refreshLocalDraftControls === 'function') refreshLocalDraftControls(); };
  function renderLink() {
    const machine = currentMachine(), attached = binding.payload(machine, currentSource()), saved = binding.draftPayload(machine, currentSource());
    byId('manual-fault-linked').hidden = !saved;
    byId('manual-fault-label').textContent = saved ? `${saved.code} · TV12U / 260224 · ${attached?'人工提供':'待重新确认'}` : '';
    byId('manual-fault-linked').querySelector('p').textContent = attached
      ? '此代码由人工提供；不代表 Trackunit 已上传该故障。'
      : '已恢复故障码供查阅；重新确认适用性并带入后，才会用于本次 AI 排查。';
    byId('manual-fault-remove').disabled = locked;
    byId('fault-reference-confirm').disabled = locked || !candidate || !isTV12U(machine);
    byId('fault-reference-attach').disabled = locked || !candidate || !isTV12U(machine) || !byId('fault-reference-confirm').checked;
    byId('fault-reference-attach').textContent = attached ? '已带入本次排查' : '带入本次排查';
    byId('fault-reference-device').textContent = !machine ? '尚未选择设备，可独立查询资料。'
      : !isTV12U(machine) ? `当前设备型号为 ${machine.model || '未知'}，不是 TV12U。可独立查阅，不能带入该设备诊断。`
      : `${machine.model} · ${machine.serial_number || machine.machine_id}。请核对该设备是否使用 260224 协议。`;
  }
  function clearCandidate(preserveRestored = false) {
    catalog = null; candidate = null; binding.choose(null, null, preserveRestored);
    byId('fault-reference-detail').replaceChildren();
    byId('fault-reference-confirm').checked = false;
    byId('fault-reference-association').hidden = true;
    renderLink(); notifyDraft();
  }
  function showCandidate(item, reference, preserveRestored = false) {
    candidate = item; catalog = reference; binding.choose(item, reference, preserveRestored);
    byId('fault-reference-confirm').checked = false;
    const body = byId('fault-reference-detail'); body.replaceChildren();
    body.append(text('h3', item.code + ' · 原表定义'), text('p', item.description, 'reference-description'));
    const list = document.createElement('dl'); list.className = 'reference-facts';
    for (const [label, value] of [['仪表提示', item.display_prompt], ['提醒方式（原文）', item.reminder_description],
      ['资料来源', `${reference.source.file_name} · ${item.source_sheet} · 第 ${item.source_row} 行`]]) {
      const group = document.createElement('div'); group.append(text('dt', label), text('dd', value)); list.append(group);
    }
    const details = document.createElement('details');
    details.append(text('summary', '查看 CAN 位置与单元格来源'),
      text('p', `CAN ${item.can_id} · Byte ${item.byte_index} / Bit ${item.bit_index}（从 0 编号）`, 'muted'),
      text('p', `${item.display_rule_raw}：${item.display_text_raw}；提醒模式 ${item.reminder_mode}。`, 'muted'),
      text('p', Object.entries(item.source_cells).map(([column, cell]) => `${column}列：${cell}`).join('；'), 'muted'));
    body.append(list, details, text('p', '故障定义不等于确认零件损坏；提醒方式不代表风险等级。维修步骤和准确料号须核对官方资料。', 'muted'));
    byId('fault-reference-association').hidden = false;
    renderLink(); notifyDraft();
  }
  function renderResults(data, exact, preserveRestored = false) {
    byId('fault-reference-results').replaceChildren();
    byId('fault-reference-count').textContent = data.total ? `找到 ${data.total} 条 · TV12U / 260224` : '没有匹配条目，请调整关键词。';
    if (data.items.length === 1) showCandidate(data.items[0], data, preserveRestored);
    if (exact || data.items.length <= 1) return;
    const list = document.createElement('ul'); list.className = 'reference-list';
    for (const item of data.items) {
      const row = document.createElement('li'), button = text('button', item.code + ' · ' + item.description, 'quiet');
      button.type = 'button'; button.disabled = locked;
      button.onclick = () => {
        if (locked) return;
        showCandidate(item, data);
        byId('fault-reference-detail').focus({ preventScroll: true });
        byId('fault-reference-detail').scrollIntoView({ block: 'nearest' });
      };
      row.append(button); list.append(row);
    }
    byId('fault-reference-results').append(list);
  }
  async function queryReference(all = false, restore = null) {
    if (locked) return;
    const ticket = ++requestTicket, params = new URLSearchParams({ model: MODEL, version: VERSION });
    const restoreScope = restore ? deviceKey(currentMachine(), currentSource()) : null;
    restoringScope = restoreScope;
    const value = restore?.code || byId('fault-reference-query').value.trim();
    const exact = Boolean(restore) || byId('fault-reference-mode').value === 'code';
    if (!all && !value) { byId('fault-reference-count').textContent = '请输入故障码或关键词。'; byId('fault-reference-query').focus(); return; }
    if (!all) params.set(exact ? 'code' : 'q', exact ? value.toUpperCase() : value);
    clearCandidate(Boolean(restore)); byId('fault-reference-results').replaceChildren(); querying = true; setBusy(locked);
    byId('fault-reference-count').textContent = '正在查询本机资料…';
    try {
      const data = await api('/assistant/fault-reference?' + params);
      if (ticket !== requestTicket || (restore && restoreScope !== deviceKey(currentMachine(), currentSource()))) return;
      renderResults(data, !all && exact, Boolean(restore));
      if (restore) byId('fault-reference-count').textContent = '已恢复故障码供查阅；再次带入前请重新确认协议适用性。';
    } catch (error) {
      if (ticket === requestTicket) byId('fault-reference-count').textContent = error.message;
    } finally { if (ticket === requestTicket) { querying = false; restoringScope = null; setBusy(locked); } }
  }
  function setBusy(value) {
    locked = Boolean(value);
    for (const id of ['fault-reference-scope', 'fault-reference-mode', 'fault-reference-query', 'fault-reference-search', 'fault-reference-all'])
      byId(id).disabled = locked || querying;
    byId('fault-reference-results').querySelectorAll('button').forEach(button => { button.disabled = locked; });
    renderLink();
  }
  global.faultReferenceDeviceChanged = (machine, source) => {
    const changed = binding.switchDevice(machine, source);
    if (changed) {
      byId('fault-reference-confirm').checked = false;
      if (restoringScope !== null) {
        ++requestTicket; restoringScope = null; querying = false; clearCandidate(); setBusy(locked);
        byId('fault-reference-count').textContent = '设备已变化，旧草稿的故障码未带入。';
      }
    }
    renderLink(); notifyDraft();
  };
  global.getManualFaultReference = () => binding.payload(currentMachine(), currentSource());
  global.getManualFaultDraftReference = () => binding.draftPayload(currentMachine(), currentSource());
  global.setFaultReferenceBusy = setBusy;
  global.restoreManualFaultReference = async manual => {
    ++requestTicket; restoringScope = null; querying = false;
    const ready = binding.stageRestore(manual, currentMachine(), currentSource());
    clearCandidate(true); setBusy(locked);
    if (!ready) {
      byId('fault-reference-count').textContent = manual ? '此故障码资料不适用于当前设备，未恢复关联。' : '当前草稿未关联故障码。';
      return;
    }
    byId('fault-reference-panel').open = true;
    byId('fault-reference-mode').value = 'code'; byId('fault-reference-query').value = manual.code;
    await queryReference(false, manual);
  };
  global.refreshXGSSSummary = async () => {
    const ticket = ++xgssTicket;
    try {
      const data = await api('/assistant/xgss/status');
      if (ticket === xgssTicket) document.querySelectorAll('[data-xgss-summary]').forEach(node => { node.textContent = xgssSummary(data); });
    } catch (_) {
      if (ticket === xgssTicket) document.querySelectorAll('[data-xgss-summary]').forEach(node => { node.textContent = xgssSummary(null); });
    }
  };
  byId('fault-reference-form').onsubmit = event => { event.preventDefault(); queryReference(); };
  byId('fault-reference-all').onclick = () => queryReference(true);
  byId('fault-reference-confirm').onchange = renderLink;
  byId('fault-reference-attach').onclick = () => {
    if (locked) return;
    try {
      binding.attach(currentMachine(), currentSource(), byId('fault-reference-confirm').checked);
      renderLink(); notifyDraft(); byId('fault-reference-panel').open = false;
      byId('manual-fault-linked').scrollIntoView({ block: 'nearest' });
      byId('observations').closest('details').open = true; byId('observations').focus();
    } catch (error) { byId('fault-reference-count').textContent = error.message; }
  };
  byId('manual-fault-remove').onclick = () => {
    if (locked) return;
    if (restoringScope !== null) {
      ++requestTicket; restoringScope = null; querying = false;
      byId('fault-reference-count').textContent = '已移除故障码关联；可重新查询资料。';
    }
    binding.clear(); byId('fault-reference-confirm').checked = false; setBusy(locked); notifyDraft();
  };
  byId('fault-reference-mode').onchange = () => {
    byId('fault-reference-query').placeholder = byId('fault-reference-mode').value === 'code' ? '例如 H10101' : '例如 左泵、比例阀';
  };
  byId('fault-reference-panel').addEventListener('toggle', async () => {
    if (!byId('fault-reference-panel').open || statusLoaded) return;
    try {
      const data = await api('/assistant/fault-reference/status');
      byId('fault-reference-status').textContent = data.available ? `本机已载入 ${data.fault_count} 个故障码 · 查询不调用 AI。` : data.message;
      statusLoaded = data.available;
    } catch (_) { byId('fault-reference-status').textContent = '无法读取本机参考资料状态，请稍后重试。'; }
  });
  global.faultReferenceDeviceChanged(currentMachine(), currentSource());
  global.refreshXGSSSummary();
})(globalThis);
