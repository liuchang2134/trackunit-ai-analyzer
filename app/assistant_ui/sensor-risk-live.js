/* Real Trackunit snapshot triage. Every channel keeps its own sample time. */
(() => {
  const byId = id => document.getElementById(id);
  const live = byId('risk-live');
  if (!live) return;
  let request = 0, snapshotRequest = 0;
  const stamp = value => {
    const date = new Date(value);
    return Number.isFinite(date.getTime()) ? date.toLocaleString('zh-CN', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}) : '时间未知';
  };
  const item = (tag, className, content) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    node.textContent = content;
    return node;
  };
  const chosen = () => typeof selected === 'function' ? selected() : null;
  const selectionScope = machine => JSON.stringify([machine?.machine_id,machine?.dataset_id,machine?.selection_id,machine?.serial_number]);
  const url = (path, machine) => `${path}?machine_id=${encodeURIComponent(machine.machine_id)}&dataset_id=${encodeURIComponent(machine.dataset_id)}`;
  const clear = (message) => {
    byId('risk-sensor-grid').replaceChildren();
    byId('risk-check-list').replaceChildren();
    byId('risk-result').hidden = true;
    byId('risk-ai-run').disabled = true;
    byId('risk-status').textContent = message;
    byId('risk-source').textContent = '';
  };
  const formatValue = row => {
    if (typeof row.value === 'boolean') return row.key === 'engine_running' ? (row.value ? '运行中' : '已停机') : (row.value ? '曾点亮' : '未点亮');
    const number = Number(row.value);
    return `${number.toLocaleString('zh-CN', {maximumFractionDigits:2})}${row.unit ? ' '+row.unit : ''}`;
  };
  const render = (report) => {
    const grid = byId('risk-sensor-grid');
    grid.replaceChildren();
    byId('risk-source').textContent = `${report.model} · ${report.source} · ${report.observations.length} 项信号`;
    if (!report.observations.length) {
      clear('这份设备数据尚未包含可核验的传感器值。点击“读取最新快照”重新获取 Trackunit 扩展数据。');
      return;
    }
    for (const row of report.observations) {
      const card = item('div','risk-sensor-card','');
      card.append(item('span','risk-sensor-label',row.label));
      card.append(item('strong','risk-sensor-value',formatValue(row)));
      card.append(item('small','risk-sensor-time',`${stamp(row.recorded_at)} · ${row.freshness === 'historical' ? '历史采样' : '近 24 小时采样'}`));
      grid.append(card);
    }
    byId('risk-status').textContent = '已读取传感器快照。各信号的采样时间独立，先核对时间再判断工况。';
    byId('risk-ai-run').disabled = false;
    byId('risk-result').hidden = false;
    const list = byId('risk-check-list');
    list.replaceChildren();
    const priorities = report.ai_priorities?.priority_ids || [];
    const checks = priorities.length ? priorities.map(id => report.checks.find(check => check.id === id)).filter(Boolean) : report.checks;
    for (const check of checks) {
      const li = item('li','risk-check','');
      li.append(item('strong','',check.title));
      li.append(item('p','',check.detail));
      const evidence = check.source_keys.map(key => report.observations.find(row => row.key === key)).filter(Boolean);
      if (evidence.length) li.append(item('small','',`依据：${evidence.map(row => `${row.label} ${formatValue(row)}（${stamp(row.recorded_at)}）`).join('；')}`));
      list.append(li);
    }
    byId('risk-ai-heading').textContent = priorities.length ? 'XCMG AI 检查优先级' : '可核对的检查方向';
    byId('risk-ai-run').textContent = priorities.length ? '查看已生成的 AI 排序' : 'XCMG AI 分析传感器';
    byId('risk-limit').textContent = report.limit;
  };
  async function load() {
    const ticket = ++request;
    const machine = chosen();
    const scope = selectionScope(machine);
    if (!machine?.dataset_id || !/^Trackunit\b/i.test(machine.source_document || '')) {
      clear('请选择当前 Trackunit 设备，然后读取最新快照。');
      return;
    }
    byId('risk-status').textContent = '正在读取该设备的实测传感器数据…';
    try {
      const report = await api(url('/assistant/risk-overview',machine));
      if (ticket !== request || selectionScope(chosen()) !== scope) return;
      render(report);
    } catch (error) {
      if (ticket !== request || selectionScope(chosen()) !== scope) return;
      clear(error.message);
    }
  }
  byId('risk-ai-run').onclick = async () => {
    const machine = chosen();
    if (!machine?.dataset_id) return;
    const button = byId('risk-ai-run');
    button.disabled = true;
    byId('risk-status').textContent = 'XCMG AI 正在按传感器数值和采样时间排列检查优先级…';
    try {
      const report = await api(url('/assistant/risk-analyze',machine),{method:'POST'});
      if (chosen()?.selection_id === machine.selection_id) render(report);
    } catch (error) {
      byId('risk-status').textContent = error.message;
    } finally { button.disabled = false; }
  };
  byId('risk-snapshot-refresh').onclick = async () => {
    const machine = chosen() ? {...chosen()} : null;
    if (!machine?.machine_id || !/^[0-9a-f-]{36}$/.test(machine.machine_id)) return;
    const ticket = ++snapshotRequest, scope = selectionScope(machine);
    const sameSelection = () => ticket === snapshotRequest && selectionScope(chosen()) === scope;
    const button = byId('risk-snapshot-refresh');
    button.disabled = true;
    byId('risk-status').textContent = '正在从 Trackunit 读取当前设备的扩展快照…';
    try {
      const hint = typeof getPlatformEquipmentHint === 'function' ? getPlatformEquipmentHint(machine.machine_id)?.value : null;
      const options = hint ? {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({equipment_id_hint:hint})} : {method:'POST'};
      const result = await api(`/assistant/platform-asset/${machine.machine_id}/load`,options);
      if (!sameSelection()) return;
      if (result.state !== 'loaded' || !result.dataset_id) throw new Error(result.message || '快照未返回有效样本。');
      await refresh();
      // refresh may itself select this returned dataset. Any other selection,
      // or an intervening user navigation, belongs to a different operation.
      if (ticket !== snapshotRequest || !sameSelection() &&
        !(chosen()?.machine_id === machine.machine_id && chosen()?.dataset_id === result.dataset_id)) return;
      const updated = machines.find(row => row.dataset_id === result.dataset_id && row.machine_id === machine.machine_id);
      if (updated) { byId('machine').value = updated.selection_id; selectMachine(); }
      await load();
    } catch (error) { if (sameSelection()) byId('risk-status').textContent = error.message; }
    finally { if (ticket === snapshotRequest) button.disabled = false; }
  };
  const invalidateSnapshotRefresh = () => { snapshotRequest++; request++; byId('risk-snapshot-refresh').disabled = false; };
  byId('machine')?.addEventListener('change',invalidateSnapshotRefresh);
  window.addEventListener('hashchange',invalidateSnapshotRefresh);
  window.renderRiskDemo = load;
})();
