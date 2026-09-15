const $ = id => document.getElementById(id);
document.documentElement.classList.toggle('panel-embedded', window.parent !== window && new URLSearchParams(location.search).has('panel'));
let report = null, machines = [], defaultSource = "mock", priorRecordId = null, pendingPlatformContext = false;
let historyRequest = 0;
let deviceIndexWarnings = [];
let platformIndexState = 'loading';
let deviceIndexRequest = 0;
let aiRuntimeLabel = '正在读取 AI 配置';
let aiFooterLabel = '辅助分析 · 报告保存在本机 · 数据来源可追溯';
let aiProvider = null;
let aiStatusTicket = 0;
const investigationDrafts = new InvestigationDrafts();
const taskQuestions = {
  comprehensive:'综合排查所选设备的故障记录、运行趋势和本地备件候选，说明依据与下一步检查。',
  parts:'读取所选设备的故障记录并匹配本地备件目录，说明适用范围与待核实事项。',
  trends:'分析所选设备的有效工时、怠速趋势与数据缺口，给出有依据的检查建议。',
  overview:'概述所选设备已知状态、最近记录和数据缺口。'
};
const taskHints = {
  comprehensive:'直接开始即可；检查故障记录、运行趋势和本地备件目录。',
  parts:'按故障证据查询本地备件候选；准确料号可通过 XGSS 整机图册核对。',
  trends:'直接开始即可；分析有效区间工时和怠速占比。',
  overview:'直接开始即可；整理已载入的设备状态与数据缺口。',
  auto:'请填写具体问题；AI 将根据问题选择已有数据工具。'
};
function updateTask() {
  const free = $('task').value === 'auto';
  $('question').required = free;
  $('question-details').querySelector('summary').textContent = free ? '填写分析问题（必填）' : '补充问题（选填）';
  if(free) $('question-details').open = true;
  else if(!$('question').value.trim()) $('question-details').open = false;
  $('task-hint').textContent = taskHints[$('task').value];
  if(!$('run').disabled){$('status').dataset.state='idle';$('status').setAttribute('role','status');$('status').textContent=free?'填写具体问题后开始分析。':'选择设备后可直接开始；补充问题选填。';}
}
$('task').onchange=updateTask;
updateTask();
const selected = () => machines.find(m => m.selection_id === $("machine").value);
async function api(path, options) {
  const r = await fetch(path, options);
  let data;
  try{data=await r.json();}catch(e){throw new Error(r.ok?'服务返回的数据格式异常，请刷新重试。':'服务暂时无法响应，请稍后重试。');}
  if(path==='/assistant/investigate' && data.ai_status)applyAIRequestStatus(data.ai_status);
  if (!r.ok) {
    let message=typeof data.detail === 'string' ? data.detail : `请求失败 (${r.status})，请检查输入格式。`;
      if(path==='/assistant/investigate' && ((data.provider_error && (data.ai_status?.provider||aiProvider)==='deepseek') || /DeepSeek|DEEPSEEK_API_KEY/.test(message)))message=formatDeepSeekFailure(data.provider_error);
      else if(/GEMINI_API_KEY is not configured/.test(message))message='尚未配置 Gemini 密钥。请在本机 .env 中填写 GEMINI_API_KEY 并重启此后端；模拟数据、趋势图和预警演示仍可使用。';
      else if(/Gemini returned HTTP 5\d\d/.test(message)){
        const attempts=message.match(/Attempts: (\d+)/)?.[1];
        message=`Gemini 服务暂时不可用${attempts?`，本次请求已尝试 ${attempts} 次`:''}。请稍后重试；本次未生成报告。`;
      }
      else if(/Gemini investigation time limit/.test(message))message='本次排查已达到 120 秒时限，未生成报告。问题和设备数据已保留，可稍后重试。';
      else if(/Investigation reached its step limit/.test(message))message='AI 在限定步骤内未给出符合证据要求的报告。请缩小排查范围后重试。';
    else if(/Gemini.*(rate limit|quota)/i.test(message))message=formatGeminiQuotaFailure(data.provider_error)||'Gemini 调用频率或额度已达到限制。请核查 API 项目配额，暂不要反复重试。';
    else if(/Gemini.*(timed out|network|connect)/i.test(message))message='Gemini 请求超时或网络不可用。请检查网络后重试。';
    const error=new Error(message);error.status=r.status;throw error;
  }
  return data;
}
function setView(view) {
  $('page-title').textContent={demo:'完整案例演示',queue:'待处理工作台',work:'设备排查',data:'资料管理',history:'诊断记录',states:'工况识别实验',cooling:'冷却预警实验'}[view];
  $('secondary-nav').open=false;
  $('demo-view').hidden = view !== 'demo';
  $('demo-entry').hidden = view !== 'work' || Boolean(PlatformContext.asset(location.hash));
  $('queue-view').hidden = view !== 'queue';
  $('work-view').hidden = view !== 'work';
  $('data-view').hidden = view !== 'data';
  $('history-view').hidden = view !== 'history';
  $('states-view').hidden = view !== 'states';
  $('cooling-view').hidden = view !== 'cooling';
  updateRuntimeLabel();
  document.querySelector('.device').hidden=['demo','states','cooling','queue'].includes(view);
  if(view==='demo' && typeof enterDemoCase==='function')enterDemoCase();
  if(view==='cooling' && typeof enterCoolingView==='function')enterCoolingView();
  if(view!=='cooling' && typeof leaveCoolingView==='function')leaveCoolingView();
  updateSourceLabel();
  if(view!=='states' && typeof stopWorkStatePlayback==='function') stopWorkStatePlayback();
  if(view==='history') refreshHistory();
  if(view==='queue' && typeof enterWorklist==='function')enterWorklist();
  document.querySelectorAll('[data-view]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.view===view)));
  window.scrollTo({top:0});
  if(view==='work' && typeof resizeDeviceOverview==='function')requestAnimationFrame(resizeDeviceOverview);
}
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>setView(b.dataset.view));
function clearReport() { report=null; $('current-feedback')?.remove(); $('result').hidden=true; $('empty-result').hidden=false; }
function displayDate(value) {
  const date = new Date(value);
  return value && Number.isFinite(date.getTime()) ? date.toLocaleString('zh-CN',{hour12:false}) : '未知';
}
function renderMetrics(trend) {
  const root=$('metrics');root.replaceChildren();
  const grid=document.createElement('dl');grid.className='metric-grid';
  const hours=value=>value==null?'数据不足':`${Number(value).toLocaleString('zh-CN',{maximumFractionDigits:2})} h`;
  for(const [label,value] of [
    ['窗口时长',hours(trend.window_duration_hours)],
    ['有效区间工时',hours(trend.operating_hours_delta)],
    ['怠速占比',trend.idle_share==null?'数据不足':`${(trend.idle_share*100).toFixed(2)}%`]
  ]) {
    const item=document.createElement('div'),term=document.createElement('dt'),definition=document.createElement('dd');
    term.textContent=label;definition.textContent=value;item.append(term,definition);grid.append(item);
  }
  const windowNote=document.createElement('p'),quality=document.createElement('p');
  windowNote.textContent=`统计窗口（本机时间）：${displayDate(trend.window_start)} — ${displayDate(trend.window_end)}`;
  quality.textContent=`程序计算 · 通过 ${trend.valid_intervals} 个区间 / 排除 ${trend.excluded_intervals} 个区间。有效区间工时不代表完整窗口总量；数据完整性未验证，未触发规则不等于无故障。`;
  root.append(grid,windowNote,quality);
}
function renderFaultFacts(evidence) {
  let root=$('fault-facts');
  if(!root){root=document.createElement('div');root.id='fault-facts';$('result-evidence').append(root);}
  root.replaceChildren();
  const entry=Object.entries(evidence).find(([,value])=>value.method==='fault_record_facts_v1');
  root.hidden=!entry;if(!entry)return;
  const [ref,facts]=entry,heading=document.createElement('h3');heading.textContent='事件记录';root.append(heading);
  if(facts.groups.length){
    const wrap=document.createElement('div');wrap.className='table-wrap';
    const table=document.createElement('table'),head=table.createTHead().insertRow();
    ['故障码','不同时间记录数','首次 → 末次（本机时间）','首末间隔'].forEach(text=>{const th=document.createElement('th');th.scope='col';th.textContent=text;head.append(th);});
    const body=table.createTBody();
    facts.groups.forEach(group=>{
      const row=body.insertRow();
      [group.fault_code,String(group.unique_code_timestamp_records),`${displayDate(group.first_record_at)}\n${displayDate(group.last_record_at)}`,
        group.first_to_last_minutes==null?'仅单个时点':`${group.first_to_last_minutes.toLocaleString('zh-CN',{maximumFractionDigits:2})} 分钟`].forEach(value=>{row.insertCell().textContent=value;});
    });wrap.append(table);root.append(wrap);
  }
  const note=document.createElement('p');note.className='muted';
  note.textContent=`已载入 ${facts.total_loaded_events} 条，时点核验后保留 ${facts.valid_loaded_records} 条；展示 ${facts.groups.length}/${facts.total_fault_code_groups} 个故障码。按故障码和时间去重计数，不能据此认定独立故障次数或复发周期。来源：${ref}。没有记录不等于设备正常。`;
  root.append(note);
}
async function refresh(focusPlatformSelection=false) {
  const request=++deviceIndexRequest;
  platformIndexState='loading';notifyPlatformContext();
  try {
    const [index, catalog] = await Promise.all([api('/assistant/device-index'), api('/assistant/catalog')]);
    if(request!==deviceIndexRequest)return;
    if($('form').getAttribute('aria-busy')==='true'){
      pendingPlatformContext=true;notifyPlatformContext();return;
    }
    const previousSelection = $('machine').value;
    defaultSource = index.data_source;
    machines = index.devices;deviceIndexWarnings=index.warnings;platformIndexState='ready';
    $('source').textContent = defaultSource === 'mock' ? '模拟数据' : '本地真实缓存';
    const groups = new Map();
    for(const m of machines) {
      const group = m.dataset_id ? (m.provenance==='synthetic'?'模拟演示片段':'导入实测数据 · 未验证') : (defaultSource==='mock'?'示例设备':'车联网缓存');
      if(!groups.has(group)){const el=document.createElement('optgroup');el.label=group;groups.set(group,el);}
      const o=document.createElement('option');o.value=m.selection_id;
      o.textContent=`${m.model} · ${m.serial_number}${m.dataset_id?' · '+m.dataset_name+' · 版本 '+m.dataset_id.slice(0,6):''}`;
      groups.get(group).append(o);
    }
    $('catalog-status').textContent = `${catalog.total} 条目录，其中 ${catalog.demo} 条演示资料`;
    // Read the latest hash after loading: navigation may have moved to another asset.
    if(location.hash.startsWith('#trackunit-asset='))applyPlatformContext(focusPlatformSelection===true,true);
    else {
      $('machine').replaceChildren(...groups.values());
      if(machines.some(m=>m.selection_id===previousSelection)) $('machine').value=previousSelection;
      selectMachine();
    }
    if(typeof refreshXGSSSummary==='function')refreshXGSSSummary();
    notifyAssistantPanel('jilian:ready');
    if(typeof enterWorklist==='function' && !$('queue-view').hidden)enterWorklist();
  } catch(e) { if(request!==deviceIndexRequest)return;platformIndexState='error';notifyPlatformContext();$('status').textContent=e.message; $('source').textContent='服务未连接'; }
}
function selectMachine() {
  const m=selected();
  if(typeof faultReferenceDeviceChanged==='function')faultReferenceDeviceChanged(m,defaultSource);
  $('case-open').disabled=!m || $('machine').disabled;
  $('xgss-device-open').disabled=!m || $('machine').disabled;
  const draft=investigationDrafts.switchTo(m?JSON.stringify([m.selection_id,m.dataset_id?m.provenance:defaultSource]):null,
    {question:$('question').value,observations:$('observations').value,task:$('task').value,language:$('language').value,priorRecordId});
  $('question').value=draft.question;$('observations').value=draft.observations;
  $('task').value=draft.task;$('language').value=draft.language;priorRecordId=draft.priorRecordId;
  $('question-details').open=Boolean(draft.question);updateTask();clearReport();
  $('device-facts').replaceChildren();
  if(m) for(const [label,value] of [['机型',m.model],['序列号',m.serial_number],['最近上报',displayDate(m.last_seen_at)]]) {
    const cell=document.createElement('div'),term=document.createElement('dt'),definition=document.createElement('dd');
    term.textContent=label;definition.textContent=value || '未知';cell.append(term,definition);$('device-facts').append(cell);
  }
  $('status').textContent=!m?'暂无可分析设备，请先同步或导入数据。':draft.question||draft.observations?'已保留此设备与数据版本的当前输入；可在下方保存本机草稿。':$('task').value==='auto'?'请填写具体问题后开始分析。':'选择排查任务后可直接开始，无需编写提示词。';
  $('status').dataset.state='idle';$('status').setAttribute('role','status');
  updateSourceLabel();
  $('machine-note').textContent=m ? `${m.dataset_id?'片段 / '+m.sample_count+' 条记录':'当前缓存'} · 数据时间：${displayDate(m.last_seen_at)}（本机时间）` : '暂无设备，请先导入或同步数据。';
  if(!$('history-view').hidden) refreshHistory();
  if(typeof refreshDeviceOverview==='function')refreshDeviceOverview();
  if(typeof refreshCoolingContext==='function')refreshCoolingContext();
  if(typeof updateDeviceFinder==='function')updateDeviceFinder();
  if(typeof selectLocalDraft==='function')selectLocalDraft();
  notifyPlatformContext();
}
function updateSourceLabel() {
  const m=selected();
  $('source').textContent=!$('demo-view').hidden?'模拟案例 · 预设回放':!$('queue-view').hidden?'本机排查工作台':!$('cooling-view').hidden?'独立模拟预警':!$('states-view').hidden?'独立模拟工况':m?.dataset_id ? (m.provenance==='synthetic'?'导入模拟数据':'导入实测 / 未验证') : (defaultSource==='mock'?'模拟数据':'本地真实缓存');
}
function applyPlatformContext(focusSelection=false,refreshSelection=false) {
  if(!location.hash.startsWith('#trackunit-asset='))return;
  const previousSelection=$('machine').value;
  const id=location.hash.slice('#trackunit-asset='.length);
  const valid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(id);
  const matches=valid?PlatformContext.candidates(machines,defaultSource,id):[];
  const choice=PlatformContext.selectDefault(machines,defaultSource,id,previousSelection);
  const sampledAt=m=>Object.hasOwn(m,'latest_telemetry_at')?m.latest_telemetry_at:m.last_seen_at;
  $('machine').replaceChildren(...matches.map(m=>{const o=document.createElement('option');o.value=m.selection_id;o.textContent=`${m.model} · ${m.serial_number} · ${m.dataset_name || '本地真实缓存'}${m.dataset_id?' · '+m.sample_count+' 条 · '+m.dataset_id.slice(0,8):''} · 最近采样 ${displayDate(sampledAt(m))}`;return o;}));
  if(!matches.length){const placeholder=document.createElement('option');placeholder.value='';placeholder.textContent='该设备暂无本地实测数据';$('machine').append(placeholder);}
  $('machine').value=choice.selected?.selection_id || '';
  const selectedVersion=choice.selected;
  if(refreshSelection||previousSelection!==$('machine').value)selectMachine();
  else notifyPlatformContext();
  const choiceNote={retained:'已保留当前版本',latest_sample:'已自动载入最近采样版本',equal_latest_sample:`${choice.tied} 个版本最近采样时间相同，已自动载入其中一个`,undated_default:'已自动载入默认版本，采样时间待核实'}[choice.reason];
  $('machine-note').textContent=selectedVersion?`已定位 ${selectedVersion.model} · ${selectedVersion.serial_number}，共有 ${matches.length} 个本地数据版本。${choiceNote}${matches.length>1?'，可在上方切换':''}。最近采样：${displayDate(sampledAt(selectedVersion))}（本机时间）${selectedVersion.dataset_id?' · '+selectedVersion.sample_count+' 条记录':''}。`:'尚无对应数据，未选择其他设备替代。';
  $('status').textContent=!valid?'平台设备 ID 格式无效。':selectedVersion?'已载入当前平台设备的本地数据，可查看趋势或开始分析。':'平台设备未匹配到本地实测数据，请先同步或导入对应设备。';
  if(!selectedVersion)$('source').textContent='平台设备 · 暂无实测数据';
  if(valid)$('demo-entry').hidden=true;
  if(focusSelection){setView('work');$('machine').focus({preventScroll:true});document.querySelector('.device').scrollIntoView({block:'start'});}
}
window.addEventListener('hashchange',()=>{if($('run').disabled){pendingPlatformContext=true;notifyPlatformContext();$('status').textContent='正在等待当前操作完成，随后应用新的平台设备上下文。';return;}if(location.hash.startsWith('#trackunit-asset='))applyPlatformContext(true);else refresh();});
$('refresh').onclick=refresh;
$('machine').onchange=selectMachine;
$('form').onsubmit=async e=>{
  e.preventDefault();
  if (!selected()) {$('status').textContent='请先选择可分析的设备或数据版本。';$('machine').focus();return;}
  const question=$('question').value.trim() || taskQuestions[$('task').value];
  if(!question){$('question-details').open=true;$('status').textContent='请填写要分析的问题。';$('question').focus();return;}
  const manualFault=typeof getManualFaultReference==='function'?getManualFaultReference():null;
  if(!manualFault&&typeof getManualFaultDraftReference==='function'&&getManualFaultDraftReference()){
    $('status').textContent='草稿中的故障码尚未重新确认。请先核对并带入，或移除该代码后再开始分析。';
    $('status').dataset.state='error';$('fault-reference-panel').open=true;
    $('fault-reference-panel').scrollIntoView({block:'nearest'});$('fault-reference-confirm').focus();return;
  }
  const locked=['sync-history','run','machine','refresh','finder-open','case-open','xgss-device-open','dataset-file','catalog','task','question','observations','language'];
  locked.forEach(id=>$(id).disabled=true);
  if(typeof setFaultReferenceBusy==='function')setFaultReferenceBusy(true);
  if(typeof refreshLocalDraftControls==='function')refreshLocalDraftControls();
  if(typeof setFaultContextBusy==='function')setFaultContextBusy(true);
  $('run').textContent='分析中…';$('form').setAttribute('aria-busy','true');
  $('status').textContent='正在请求 AI 分析并核对数据证据；完成后自动显示结果。';
  $('status').dataset.state='loading';$('status').setAttribute('role','status');
  const started=Date.now();$('elapsed').hidden=false;
  const tick=()=>{$('elapsed').textContent=`已等待 ${Math.floor((Date.now()-started)/1000)} 秒${Date.now()-started>60000?' · 服务仍在处理，请勿重复提交':''}`;};tick();
  const timer=setInterval(tick,1000);
  try {
    const completed=await api('/assistant/investigate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({machine_id:selected().machine_id,dataset_id:selected().dataset_id || null,question,observations:$('observations').value,language:$('language').value,task:$('task').value,prior_record_id:priorRecordId,...(manualFault?{manual_fault:manualFault}:{})})});
    report=completed;
    $('current-feedback')?.remove();
    $('summary').textContent=report.summary;
    $('summary').previousElementSibling.textContent='AI解释 · 待核实';
    let factsRoot=$('data-facts');
    if(!factsRoot){factsRoot=document.createElement('div');factsRoot.id='data-facts';$('result-evidence').insertBefore(factsRoot,$('metrics'));}
    factsRoot.replaceChildren();
    const factsHeading=document.createElement('h3');factsHeading.textContent=report.language==='en'?'Data facts':'数据事实';
    const factsNote=document.createElement('p');factsNote.className='muted';factsNote.textContent=report.language==='en'?'Rendered from loaded evidence. AI interpretation below requires review; these are not verified physical-machine findings.':'根据已载入证据直接整理。下方AI解释仍需复核，这些记录不等于已验证的实机结论。';
    const factsList=document.createElement('ul');
    for(const fact of report.data_facts||[]){const li=document.createElement('li');li.textContent=fact.text;factsList.append(li);}
    factsRoot.append(factsHeading,factsNote,factsList);
    renderFaultFacts(report.evidence);
    const trend=Object.values(report.evidence).find(e=>e.method==='time_window_rules_v1');
    $('metrics').hidden=!trend;
    if(trend) renderMetrics(trend);

    $('checks').replaceChildren(...report.next_checks.map((s,index)=>{
      const li=document.createElement('li');li.textContent=s;
      const evidence=report.check_recommendations?.[index];
      if(evidence){const note=document.createElement('small');note.className='check-source';
        note.textContent=`${{application_rule:'数据核验规则',demo:'演示资料',user_supplied:'用户提供资料'}[evidence.provenance] || '待核实资料'} · ${evidence.source_document} · 依据：${evidence.evidence_ids.join('、')}`;
        li.append(note);}
      return li;
    }));
    if(!report.next_checks.length){const li=document.createElement('li');li.textContent='本次未选择有依据的检查步骤，请补充对应资料。';$('checks').append(li);}
    $('parts').replaceChildren();
    if (report.parts_candidates.length) {
      const table=document.createElement('table'), head=table.createTHead().insertRow();
      ['备件 / 编号','适用范围 / 匹配依据','来源 / 检查要求'].forEach(label=>{const th=document.createElement('th');th.scope='col';th.textContent=label;head.append(th);});
      const body=table.createTBody();
      for(const p of report.parts_candidates) {
        const row=body.insertRow();
        [p.name+'\n'+p.part_number,
         (p.models||[]).join('、')+'\n'+(p.match_reason==='fault_code'?'故障码匹配':'部件匹配')+' · '+(p.serial_verified?'序列号在适用清单':'序列号适用性待确认'),
         (p.provenance==='demo'?'演示资料':'用户提供资料')+' · 候选待核查\n'+p.source_document+' / '+p.source_page+' / '+p.revision+'\n'+p.checks.join('；')
        ].forEach(value=>{row.insertCell().textContent=value;});
      }
      $('parts').append(table);
    } else {
      const search=Object.values(report.evidence||{}).find(item=>item.search_diagnostics?.method==='catalog_filter_stages_v1')?.search_diagnostics;
      const reasons={catalog_empty:'本地备件目录为空，请导入有来源的目录。',
        no_eligible_catalog:'目录中只有演示条目，不能用于当前真实数据来源。',
        model_not_in_catalog:'当前可用目录没有精确匹配此设备机型的条目。',
        serial_not_applicable:'目录有此机型，但设备序列号不在条目的适用范围内。',
        fault_or_component_not_matched:'目录条目通过了机型及序列号限制筛选，但未匹配本次故障码或部件查询。通过筛选不代表已核验整机配置。'};
      $('parts').textContent=search ? (reasons[search.reason_code]||'本次没有可展示的匹配候选。')+' 检索仅覆盖当前本地目录。'
        : '尚无匹配候选。请补充故障证据或对应型号的备件目录。';
    }
    $('evidence').textContent=JSON.stringify({citations:report.citations,tools:report.tool_trace,evidence:report.evidence},null,2);
    $('result-xgss-controls').replaceChildren();
    if(typeof createXGSSControls==='function') {
      const machine=selected();
      $('result-xgss-controls').append(createXGSSControls({...machine,source:machine.dataset_id?'imported_'+machine.provenance:defaultSource},manualFault?.code||null));
    }
    $('result').hidden=false; $('empty-result').hidden=true;
    $('result-feedback').disabled=!report.record_id;
    $('status').textContent=`分析完成 · 用时 ${Math.round((Date.now()-started)/1000)} 秒 · ${report.history_saved===false?'记录保存失败，请导出备份':'已保存诊断记录'}`;
    $('status').dataset.state='complete';
    setView('work');$('result').focus();$('result').scrollIntoView({block:'start'});
  } catch(e){$('status').setAttribute('role','alert');$('status').dataset.state='error';$('status').textContent=`分析未完成：${e.message}${report?' 下方保留上次成功报告，本次未更新。':''}`;$('status').scrollIntoView({block:'nearest'});}
  finally{clearInterval(timer);$('elapsed').hidden=true;locked.forEach(id=>$(id).disabled=false);if(typeof setFaultReferenceBusy==='function')setFaultReferenceBusy(false);if(typeof setFaultContextBusy==='function')setFaultContextBusy(false);if(typeof refreshLocalDraftControls==='function')refreshLocalDraftControls();$('sync-history').disabled=!$('sync-source').value;$('run').textContent='开始分析';$('form').setAttribute('aria-busy','false');if(pendingPlatformContext){pendingPlatformContext=false;await refresh(true);}}
};
$('catalog').onchange=async()=>{
  const file=$('catalog').files[0];if(!file)return;
  try{if(file.size>5*1024*1024)throw new Error('目录文件不能超过 5MB');
    const payload=JSON.parse(await file.text());
    const r=await api('/assistant/catalog/import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    $('catalog-status').textContent=`新增 ${r.added} 条，目录共 ${r.total} 条`;
  }catch(e){$('catalog-status').textContent=e.message;}
};
function exportReport(report){
  if(!report)return;
  const facts=(report.data_facts||[]).map(f=>'- '+f.text+' ['+f.evidence_ids.join(', ')+']').join('\n');
  const text=`# 机联智检 / Local investigation\n\n设备: ${report.machine_id}\n来源: ${report.source}\n时间: ${report.generated_at}\n模型: ${report.model}\n\n## 数据事实 / Data facts\n${facts||'Legacy report: structured facts unavailable.'}\n\n## AI解释（待核实） / AI interpretation (requires review)\n${report.summary}\n\n## Next checks\n${report.next_checks.map(s=>'- '+s).join('\n')}\n\n## Evidence & parts\n\x60\x60\x60json\n${JSON.stringify(report,null,2)}\n\x60\x60\x60\n`;
  const url=URL.createObjectURL(new Blob([text],{type:'text/markdown;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='jilian-investigation.md';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
$('export').onclick=()=>exportReport(report);
refresh();

$('dataset-file').onchange=async()=>{
 const file=$('dataset-file').files[0];if(!file)return;
 $('run').disabled=true;
 try {
  if(file.size>3*1024*1024)throw new Error('数据文件不能超过 3MB');
  const text=await file.text();let payload,path;
  if(file.name.toLowerCase().endsWith('.csv')){
   const m=selected();if(!m)throw new Error('CSV 导入前请选择设备');
   const {selection_id,dataset_id,dataset_name,sample_count,provenance,replay_at,cooling_reference,...machine}=m;
   payload={name:file.name,source_document:file.name,provenance:$('provenance').value,machine,csv_text:text};path='/assistant/datasets/import-csv';
  }else{payload=JSON.parse(text);path='/assistant/datasets/import';}
  const r=await api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  await refresh();$('machine').value='dataset:'+r.dataset_id;selectMachine();
  $('dataset-status').textContent=`已导入 ${r.sample_count} 条记录：${r.name}。已切换至此数据集。`;
 }catch(e){$('dataset-status').textContent=e.message;}
 finally{$('run').disabled=false;if(pendingPlatformContext){pendingPlatformContext=false;await refresh(true);}}
};

async function refreshIntegrationStatus() {
  try {
    const data = await api('/assistant/integration-status');
    $('integration-note').textContent = data.status==='last_verified'
      ? '上次核验：'+displayDate(data.checked_at)+(data.older_than_24h?' · 已超过24小时':'')+'（非实时）'
      : '尚无有效核验记录；当前连接能力未知。';
    const names={operating_hours:'累计工时',idle_hours:'累计怠速工时',fault_events:'故障事件'};
    const states={data:'返回数据',empty:'返回空数据',unauthorized:'无权读取',rate_limited:'请求受限',error:'请求失败',not_checked:'未核验'};
    const table=document.createElement('table'),head=table.createTHead().insertRow();
    ['数据接口','上次结果','记录数'].forEach(x=>{const th=document.createElement('th');th.scope='col';th.textContent=x;head.append(th);});
    const body=table.createTBody();
    for(const c of data.capabilities){const row=body.insertRow();[names[c.name],states[c.status]+(c.http_status?' · HTTP '+c.http_status:''),c.record_count??'未知'].forEach(x=>row.insertCell().textContent=x);}
    $('integration-status').replaceChildren(table);
  } catch(e){$('integration-note').textContent='无法读取接口核验记录；连接能力未知。';}
}
refreshIntegrationStatus();

async function refreshHistory() {
  const ticket=++historyRequest;
  try {
    const m=selected(), current=$('history-scope').value==='current';
    if(current && !m){$('history-note').textContent='请先选择设备，或切换到全部设备。';$('history-list').replaceChildren();return;}
    const params=new URLSearchParams();
    if(current){params.set('machine_id',m.machine_id);params.set('dataset_id',m.dataset_id||'');if(!m.dataset_id)params.set('source',defaultSource);}
    const data=await api('/assistant/history?'+params.toString());
    if(ticket!==historyRequest)return;
    $('history-note').textContent=data.total
      ? `${current?'当前设备与数据版本':'全部设备'}共 ${data.total} 条，显示最近 ${data.records.length} 条。${data.unreadable ? data.unreadable+' 条文件无法读取。' : ''}历史记录不代表当前状态。`
      : '此范围暂无诊断记录。完成一次分析后会自动保存，可在此记录检查结果。';
    $('history-list').replaceChildren();
    for(const record of data.records) {
      const item=document.createElement('details'),title=document.createElement('summary');
      title.textContent=displayDate(record.generated_at)+' · '+record.question;
      const meta=document.createElement('p');meta.className='muted';meta.textContent=record.machine_id+' · '+record.source;
      const summary=document.createElement('p');summary.className='pre';summary.textContent='AI解释（待核实）：'+record.summary;
      const download=document.createElement('button');download.className='quiet';download.textContent='导出完整记录 JSON';
      download.onclick=async()=>{
        download.disabled=true;
        try {
          const full=await api('/assistant/history/'+record.record_id);
          const url=URL.createObjectURL(new Blob([JSON.stringify(full,null,2)],{type:'application/json'}));
          const a=document.createElement('a');a.href=url;a.download='jilian-record-'+record.record_id.slice(0,12)+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
        }catch(e){$('history-note').textContent=e.message;}finally{download.disabled=false;}
      };
      const feedback=document.createElement('button');feedback.className='quiet';feedback.textContent='检查反馈 / 继续分析';
      const view=document.createElement('button');view.className='quiet';view.textContent='查看完整报告';
      const fullPanel=document.createElement('section');fullPanel.hidden=true;
      view.setAttribute('aria-expanded','false');
      view.onclick=async()=>{
        if(!fullPanel.hidden){fullPanel.hidden=true;view.setAttribute('aria-expanded','false');return;}
        view.disabled=true;
        try{
          const full=await api('/assistant/history/'+record.record_id);
          const saved=full.report;fullPanel.replaceChildren();
          const heading=document.createElement('h3');heading.textContent='历史报告 · '+saved.machine_id;
          const note=document.createElement('p');note.className='muted';
          note.textContent=`生成时间：${displayDate(saved.generated_at)} · 来源：${saved.source} · 模型：${saved.model || '未记录'}。以下为保存时的报告，未重新运行分析。`;
          fullPanel.append(heading,note);
          const addSection=(title,lines)=>{
            const h=document.createElement('h4');h.textContent=title;const list=document.createElement('ul');
            for(const line of lines){const li=document.createElement('li');li.className='pre';li.textContent=line;list.append(li);}
            fullPanel.append(h,list);
          };
          addSection('数据依据与人工记录',(saved.data_facts||[]).map(f=>f.text));
          if(!saved.data_facts?.length){const old=document.createElement('p');old.textContent='此旧报告未保存独立的数据事实条目，请查看下方完整证据。';fullPanel.append(old);}
          addSection('AI解释（待核实）',[saved.summary]);
          addSection('建议检查',saved.next_checks||[]);
          addSection('备件候选（需核实）',(saved.parts_candidates||[]).map(p=>`${p.name} / ${p.part_number}\n整机适用型号：${(p.models||[]).join('、')}\n资料：${p.source_document} / ${p.source_page} / ${p.revision}`));
          const raw=document.createElement('details'),label=document.createElement('summary'),pre=document.createElement('pre');
          label.textContent='完整保存记录与证据';pre.textContent=JSON.stringify(full,null,2);raw.append(label,pre);fullPanel.append(raw);
          const markdown=document.createElement('button');markdown.className='quiet';markdown.textContent='导出此历史报告 Markdown';
          markdown.onclick=()=>exportReport({...saved,record_id:full.record_id,history_saved:true});fullPanel.append(markdown);
          fullPanel.hidden=false;view.setAttribute('aria-expanded','true');
        }catch(e){$('history-note').textContent=e.message;}finally{view.disabled=false;}
      };
      const panel=document.createElement('div');
      feedback.onclick=async()=>{
        feedback.disabled=true;
        try{await renderFeedbackPanel(record.record_id,panel);}catch(e){panel.textContent=e.message;}finally{feedback.disabled=false;}
      };
      const actions=document.createElement('div');actions.className='history-actions';actions.append(view,download,feedback);
      item.append(title,meta,summary,actions,fullPanel,panel);$('history-list').append(item);
    }
  } catch(e){$('history-note').textContent='无法读取本地诊断记录。';}
}
$('history-refresh').onclick=refreshHistory;
$('history-scope').onchange=refreshHistory;
$('result-history').onclick=()=>{$('history-scope').value='current';setView('history');};
$('result-feedback').onclick=async()=>{
  if(!report?.record_id)return;
  let panel=$('current-feedback');
  if(!panel){panel=document.createElement('div');panel.id='current-feedback';$('result').append(panel);}
  $('result-feedback').disabled=true;
  try{await renderFeedbackPanel(report.record_id,panel);panel.scrollIntoView({block:'start'});panel.querySelector('select')?.focus();}
  catch(e){panel.textContent='无法读取反馈记录，请稍后重试。';}
  finally{$('result-feedback').disabled=false;}
};

async function renderFeedbackPanel(recordId,panel) {
  const [parent,feedback]=await Promise.all([api('/assistant/history/'+recordId),api('/assistant/history/'+recordId+'/feedback')]);
  panel.replaceChildren();
  const note=document.createElement('p');note.className='muted';note.textContent=`已保存 ${feedback.total} 条现场反馈，均为人工提供、未经验证。继续分析携带本条记录下最近 5 条反馈；原诊断记录保留。`;
  const list=document.createElement('ul');
  const outcomes={observed:'现象已观察到',not_observed:'未观察到该现象',inconclusive:'未能判断'};
  feedback.records.forEach(record=>{const li=document.createElement('li');li.textContent=`${displayDate(record.observed_at)} · ${outcomes[record.outcome]} · ${record.check_text || '补充观察'}：${record.notes}`;list.append(li);});
  const form=document.createElement('form');form.className='feedback-form';
  function field(labelText,input){const label=document.createElement('label');label.textContent=labelText;label.append(input);form.append(label);return input;}
  const checks=field('对应检查项',document.createElement('select'));
  [{check_id:'',text:'补充观察'},...(parent.report.check_recommendations || [])].forEach(check=>{const option=document.createElement('option');option.value=check.check_id;option.textContent=check.text;checks.append(option);});
  const outcome=field('检查结果',document.createElement('select'));
  Object.entries(outcomes).forEach(([value,text])=>{const option=document.createElement('option');option.value=value;option.textContent=text;outcome.append(option);});outcome.value='inconclusive';
  const time=field('观察时间（本机时区）',document.createElement('input'));time.type='datetime-local';time.required=true;
  const now=new Date();time.value=new Date(now.getTime()-now.getTimezoneOffset()*60000).toISOString().slice(0,16);
  const notes=field('观察说明',document.createElement('textarea'));notes.required=true;notes.maxLength=1000;notes.rows=3;notes.placeholder='描述实际观察结果；演示时请注明模拟反馈。';
  const save=document.createElement('button');save.type='submit';save.textContent='保存检查反馈';
  const status=document.createElement('p');status.className='muted';status.setAttribute('role','status');
  form.append(save,status);
  form.onsubmit=async event=>{
    event.preventDefault();save.disabled=true;
    try {
      if(!notes.value.trim())throw new Error('请填写观察说明。');
      await api('/assistant/history/'+recordId+'/feedback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({check_id:checks.value || null,outcome:outcome.value,observed_at:new Date(time.value).toISOString(),notes:notes.value})});
      await renderFeedbackPanel(recordId,panel);
    }catch(e){status.textContent=e.message;}finally{save.disabled=false;}
  };
  const resume=document.createElement('button');resume.className='quiet';resume.textContent='带已保存反馈继续分析';
  resume.onclick=async()=>{
    if($('run').disabled){status.textContent='请等待当前分析或同步完成。';return;}
    const selection=parent.request.dataset_id?'dataset:'+parent.request.dataset_id:'fleet:'+parent.report.machine_id;
    if(!machines.some(m=>m.selection_id===selection)){status.textContent='原设备或原数据集不可用，请先恢复对应数据。';return;}
    $('machine').value=selection;selectMachine();priorRecordId=recordId;
    $('question').value='结合已保存的检查反馈继续分析，说明目前支持的判断和仍缺少的证据。';
    $('language').value=parent.request.language || 'zh';$('task').value=parent.request.task || 'auto';
    updateTask();$('question-details').open=true;
    if(typeof refreshLocalDraftControls==='function')refreshLocalDraftControls();
    setView('work');$('status').textContent='已关联原诊断记录和已保存的检查反馈。点击开始分析生成新记录。';$('question').focus();
    if(typeof restoreManualFaultReference==='function')await restoreManualFaultReference(parent.request.manual_fault);
  };
  panel.append(note,list,form,resume);
}

async function loadSyncSources() {
  try {
    const sources=await api('/assistant/history-sources');
    $('sync-source').replaceChildren(...sources.map(s=>{const option=document.createElement('option');option.value=s.source_id;option.textContent=s.model+' · '+s.serial_number;return option;}));
    $('sync-history').disabled=!sources.length;
    $('sync-note').textContent=sources.length?'仅同步已登记设备的工时与怠速，每台设备至少间隔15分钟。故障事件不在此次同步范围。':'尚无已登记设备，请先配置本地真实设备快照。';
  }catch(e){$('sync-note').textContent='无法读取已登记设备。';}
}
$('sync-history').onclick=async()=>{
  if(!$('sync-source').value)return;
  const disabled=['sync-history','sync-source','sync-days','run','machine','refresh','finder-open','dataset-file'];
  disabled.forEach(id=>$(id).disabled=true);
  $('sync-note').textContent='正在读取 Trackunit 历史数据…';
  try {
    const data=await api('/assistant/sync-history',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({source_id:$('sync-source').value,days:Number($('sync-days').value)})});
    await refreshIntegrationStatus();
    if(data.dataset_id){await refresh();$('machine').value='dataset:'+data.dataset_id;selectMachine();}
    $('sync-note').textContent=data.dataset_id?`已导入 ${data.sample_count} 条记录并选中该数据集。请查看下方各接口结果，再切换至设备排查。`:'未获得可导入数据，请查看下方接口结果。';
  }catch(e){$('sync-note').textContent=e.message;}
  finally{disabled.forEach(id=>$(id).disabled=false);if(pendingPlatformContext){pendingPlatformContext=false;await refresh(true);}}
};
loadSyncSources();

function notifyAssistantPanel(type,fields={}) {
  if(window.parent!==window)window.parent.postMessage({type,protocol:1,
    connection_id:new URLSearchParams(window.location.search).get('panel'),...fields},'*');
}
function notifyPlatformContext(){
  if(window.parent===window)return;
  const origin=location.ancestorOrigins?.[0];
  if(!/^chrome-extension:\/\/[a-p]{32}$/.test(origin||''))return;
  const context=PlatformContext.snapshot({hash:location.hash,machines,source:defaultSource,
    selectionId:$('machine').value,indexState:platformIndexState,pending:pendingPlatformContext});
  if(context)window.parent.postMessage({type:'jilian:context',protocol:1,
    connection_id:new URLSearchParams(location.search).get('panel'),...context},origin);
}
window.addEventListener('message',event=>{
  const origin=location.ancestorOrigins?.[0],data=event.data;
  if(window.parent===window||event.source!==window.parent||event.origin!==origin||!/^chrome-extension:\/\/[a-p]{32}$/.test(origin||''))return;
  if(data?.type!=='jilian:context-request'||data.protocol!==1||data.connection_id!==new URLSearchParams(location.search).get('panel')||data.asset_id!==PlatformContext.asset(location.hash))return;
  notifyPlatformContext();
});
async function refreshAIRuntime() {
  try {
    const runtime=await api('/assistant/runtime');
    aiProvider=runtime.provider;
    notifyAssistantPanel('jilian:runtime',{provider:runtime.provider,model:runtime.model,
      backend_build:runtime.backend_build,inference_location:runtime.inference_location,
      investigation_timeout_seconds:runtime.investigation_timeout_seconds,transient_attempt_limit:runtime.transient_attempt_limit});
    const copy=AIRequestStatus.runtimeView(runtime);
    aiRuntimeLabel=copy.label;
    aiFooterLabel=copy.footer;
    updateRuntimeLabel();
    $('ai-data-note').textContent=copy.note;
  } catch (e) {
    aiRuntimeLabel='AI 配置读取失败';updateRuntimeLabel();
    $('ai-data-note').textContent='请确认后端已启动并刷新页面。';
  }
  await refreshAIRequestStatus();
}
function renderAIRequestStatus(data){
  const state=AIRequestStatus.view(data);
  $('ai-request-state').dataset.tone=state.tone;
  $('ai-request-title').textContent=state.title;
  $('ai-request-time').hidden=!state.time;
  $('ai-request-time').textContent=state.time?'记录时间：'+displayDate(state.time)+'（本机时间）':'';
  $('ai-request-detail').textContent=state.detail;
}
function applyAIRequestStatus(data){
  ++aiStatusTicket;renderAIRequestStatus(data);$('ai-status-refresh').disabled=false;
}
async function refreshAIRequestStatus(){
  const ticket=++aiStatusTicket;$('ai-status-refresh').disabled=true;
  try{const data=await api('/assistant/ai-status');if(ticket===aiStatusTicket)renderAIRequestStatus(data);}
  catch(e){if(ticket===aiStatusTicket)renderAIRequestStatus(null);}
  finally{if(ticket===aiStatusTicket)$('ai-status-refresh').disabled=false;}
}
$('ai-status-refresh').onclick=refreshAIRequestStatus;
function updateRuntimeLabel(){
  $('runtime-footer').textContent=!$('demo-view').hidden?'模拟案例 · 离线预设讲解 · 不调用外部接口':aiFooterLabel;
  $('ai-runtime').textContent=!$('demo-view').hidden?'预设分析示例 · 不调用外部接口':!$('queue-view').hidden?'本机任务与记录 · 不调用 AI':!$('cooling-view').hidden?'本地预警模型 · 不消耗云端额度':!$('states-view').hidden?'本地工况分类模型':aiRuntimeLabel;
}
refreshAIRuntime();
