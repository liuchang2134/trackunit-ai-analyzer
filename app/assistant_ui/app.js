const $ = id => document.getElementById(id);
document.documentElement.classList.toggle('panel-embedded', window.parent !== window && new URLSearchParams(location.search).has('panel'));
let report = null, openedReport = null, machines = [], defaultSource = "mock", priorRecordId = null, pendingPlatformContext = false;
let historyRequest = 0;
let deviceIndexWarnings = [];
let platformIndexState = 'loading';
let deviceIndexRequest = 0;
let appliedPlatformHash = null;
let activeView = 'work';
const platformEquipmentHints = new Map();
let aiRuntimeLabel = '正在连接 AI';
let aiFooterLabel = '机联智检 · 工程机械运维助手';
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
  comprehensive:'结合故障、运行趋势和备件资料，给出检查建议。',
  parts:'按故障证据推荐候选部件，在 XGSS 核对料号。',
  trends:'分析工时变化与怠速占比。',
  overview:'整理设备概况与最近记录。',
  auto:'输入你想了解的设备问题。'
};
function updateTask() {
  const free = $('task').value === 'auto';
  $('question').required = free;
  $('question-details').querySelector('summary').textContent = free ? '填写分析问题（必填）' : '补充问题（选填）';
  if(free) $('question-details').open = true;
  else if(!$('question').value.trim()) $('question-details').open = false;
  $('task-hint').textContent = taskHints[$('task').value];
  if(!$('run').disabled){$('status').dataset.state='idle';$('status').setAttribute('role','status');$('status').textContent=free?'填写问题后开始分析。':'选择设备与任务后开始分析。';}
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
    let message=typeof data.detail === 'string' ? data.detail : typeof data.detail?.message==='string' ? data.detail.message : `请求失败 (${r.status})，请检查输入格式。`;
      if(path==='/assistant/investigate' && ((data.provider_error && (data.ai_status?.provider||aiProvider)==='deepseek') || /DeepSeek|DEEPSEEK_API_KEY/.test(message)))message=formatDeepSeekFailure(data.provider_error);
      else if(/GEMINI_API_KEY is not configured/.test(message))message='AI 服务尚未配置，请检查连接设置。设备资料仍可使用。';
      else if(/Gemini returned HTTP 5\d\d/.test(message)){
        const attempts=message.match(/Attempts: (\d+)/)?.[1];
        message=`Gemini 服务暂时不可用${attempts?`，本次请求已尝试 ${attempts} 次`:''}。请稍后重试；本次未生成报告。`;
      }
      else if(/Gemini investigation time limit/.test(message))message='本次分析超时，未生成报告。输入已保留，请稍后重试。';
      else if(/Investigation reached its step limit/.test(message))message='AI 在限定步骤内未给出符合证据要求的报告。请缩小排查范围后重试。';
    else if(/Gemini.*(rate limit|quota)/i.test(message))message=formatGeminiQuotaFailure(data.provider_error)||'Gemini 调用频率或额度已达到限制。请核查 API 项目配额，暂不要反复重试。';
    else if(/Gemini.*(timed out|network|connect)/i.test(message))message='Gemini 请求超时或网络不可用。请检查网络后重试。';
    const error=new Error(message);error.status=r.status;error.code=data.detail?.code||null;throw error;
  }
  return data;
}
function setView(view,{reason='initial'}={}) {
  // Presentation only: deferred views remain available when competition-focus is removed.
  if(document.documentElement?.classList?.contains?.('competition-focus') && !['work','risk'].includes(view))view='work';
  activeView=view;
  $('page-title').textContent={can:'CAN 工况',demo:'历史分析回放',queue:'待处理',work:'AI 设备服务',risk:'风险预警',data:'资料管理',history:'诊断记录',states:'工况识别',cooling:'冷却预警'}[view];
  updateDemoDisclosure();
  $('demo-view').hidden = view !== 'demo';
  $('can-view').hidden = view !== 'can';
  if(typeof enterCanWorkspace==='function')enterCanWorkspace(view==='can');
  $('demo-entry').hidden = true;
  $('queue-view').hidden = view !== 'queue';
  $('work-view').hidden = view !== 'work';
  if($('risk-view'))$('risk-view').hidden=view!=='risk';
  if(view==='risk'&&typeof window.renderRiskDemo==='function')void window.renderRiskDemo();
  $('data-view').hidden = view !== 'data';
  $('history-view').hidden = view !== 'history';
  $('states-view').hidden = view !== 'states';
  $('cooling-view').hidden = view !== 'cooling';
  updateRuntimeLabel();
  document.querySelector('.device').hidden=['demo','states','cooling','queue','can'].includes(view)||
    view==='risk'&&window.JilianDataMode?.mode==='demo';
  if(view==='demo' && typeof enterDemoReplay==='function')enterDemoReplay();
  if(view==='cooling' && typeof enterCoolingView==='function')enterCoolingView();
  if(view!=='cooling' && typeof leaveCoolingView==='function')leaveCoolingView();
  updateSourceLabel();
  if(view!=='states' && typeof stopWorkStatePlayback==='function') stopWorkStatePlayback();
  if(view==='history') refreshHistory();
  if(view==='queue' && typeof enterWorklist==='function')enterWorklist();
  const navigationView = view === 'demo' ? 'history' : view;
  document.querySelectorAll('[data-view]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.view===(b.closest('nav') ? navigationView : view))));
  window.scrollTo({top:0});
  if(view==='work' && typeof resizeDeviceOverview==='function')requestAnimationFrame(resizeDeviceOverview);
  // The track belongs to the troubleshooting view only: on the case demo it would
  // read as if a simulated run had really touched a machine.
  const track=document.getElementById('flow-track');
  if(track)track.hidden=view!=='work';
  if(view==='work')updateFlowTrack();
  notifyPanelView(reason);
  if(typeof platformLoaderChanged==='function')platformLoaderChanged();
}
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>setView(b.dataset.view,{reason:'user'}));
function clearReport() { report=null; openedReport=null; $('current-feedback')?.remove(); $('result').hidden=true; $('empty-result').hidden=false; }
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
  quality.textContent=`计入 ${trend.valid_intervals} 个有效区间，排除 ${trend.excluded_intervals} 个异常区间。统计可能不覆盖完整工况，未触发预警不代表无故障。`;
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
  note.textContent=`载入 ${facts.total_loaded_events} 条，核验后保留 ${facts.valid_loaded_records} 条；展示 ${facts.groups.length}/${facts.total_fault_code_groups} 个故障码。记录数不等于故障次数；无记录不代表设备正常。来源：${ref}。`;
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
    $('source').textContent = defaultSource === 'trackunit_cache' ? 'Trackunit 数据' : defaultSource === 'demo' ? '演示数据' : '模拟数据';
    window.JilianDataMode?.display(defaultSource==='trackunit_cache'?'live':'demo');
    const groups = new Map();
    for(const m of machines) {
      const group = machineSourceLabel(m);
      if(!groups.has(group)){const el=document.createElement('optgroup');el.label=group;groups.set(group,el);}
      const o=document.createElement('option');o.value=m.selection_id;
      o.textContent=machineOptionLabel(m);
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
function machineSampleTime(machine){
  return Object.hasOwn(machine,'latest_telemetry_at')?machine.latest_telemetry_at:machine.last_seen_at;
}
function machineSourceLabel(machine){
  if(machine?.provenance==='synthetic'||machine?.source==='mock'||machine?.source==='imported_synthetic')return '模拟数据';
  if(machine?.dataset_id)return /^Trackunit\b/i.test(machine.source_document||'')?'Trackunit 数据':'导入数据';
  return defaultSource==='trackunit_cache'?'Trackunit 数据':defaultSource==='demo'?'演示数据':'模拟数据';
}
function displayMachineModel(value){return /^(?:Data not available|未提供|unknown)$/i.test(value||'')||!value?'机型待确认':value;}
function machineOptionLabel(machine){
  const versions=machines.filter(row=>row.machine_id===machine.machine_id)
    .map(row=>row.selection_id).sort();
  const version=versions.length>1?' · 版本 '+(versions.indexOf(machine.selection_id)+1):'';
  return `${displayMachineModel(machine.model)} · ${machine.serial_number} · ${displayDate(machineSampleTime(machine))}${version}`;
}
/**
 * Show an identifier in a form a person can read out loud.
 *
 * Trackunit asset ids are full UUIDs; a screen full of them is unreadable and
 * useless for a walkthrough. The full value stays available where traceability
 * matters (the data-detail disclosure, the saved record and the exported pack),
 * so shortening here loses nothing.
 */
function shortIdentifier(value, keep=8){
  const text=String(value==null?'':value).trim();
  if(!text)return '';
  if(text.length<=keep+3)return text;
  return text.slice(0,keep)+'…';
}
function machineRecordNote(machine){
  return machine?`最近采样 ${displayDate(machineSampleTime(machine))}${machine.dataset_id?' · '+machine.sample_count+' 条记录':''}`:'等待设备数据';
}
function renderDeviceVitals(machine){
  if(typeof window!=='undefined')window.MachinePhotos?.renderDevice(machine);
  const root=$('device-vitals');
  const wide=new Set(['VIN / PIN','数据版本','来源说明']);
  root.replaceChildren();
  if(!machine){const cell=document.createElement('div');cell.dataset.wide='1';
    const dd=document.createElement('dd');dd.textContent='尚未识别设备';cell.append(dd);root.append(cell);return;}
  const compact=document.documentElement?.classList?.contains?.('competition-focus')===true;
  const uncertain=/^\d{1,16}$/.test(machine.serial_number||'')&&machine.serial_number===machine.equipment_id;
  const facts=[['机型',displayMachineModel(machine.model)],[uncertain?'设备编号':'VIN / PIN',machine.serial_number]];
  if(!compact){facts.push(['最近采样',displayDate(machineSampleTime(machine))],['数据来源',machineSourceLabel(machine)]);
    if(machine.dataset_id)facts.push(['数据记录',machine.sample_count+' 条']);}
  for(const [label,value] of facts){
    const cell=document.createElement('div'),term=document.createElement('dt'),definition=document.createElement('dd');
    if(wide.has(label))cell.dataset.wide='1';
    term.textContent=label;definition.textContent=value||'未知';cell.append(term,definition);root.append(cell);
  }
}
function renderDeviceFacts(machine,selectionNote='',platformId=''){
  renderDeviceVitals(machine);
  const compact=document.documentElement?.classList?.contains?.('competition-focus')===true;
  if(compact){
    const maintenance=document.querySelector?.('.device-maintenance'),details=document.querySelector?.('.device-details');
    if(maintenance&&details&&!maintenance.hidden){details.append($('machine'),$('refresh'));maintenance.hidden=true;}
  }
  $('device-facts').replaceChildren();
  const facts=machine?[['机型',displayMachineModel(machine.model)],['VIN / PIN',machine.serial_number],
    ['最近采样',displayDate(machineSampleTime(machine))],['数据来源',machineSourceLabel(machine)],
    ['设备 ID',machine.machine_id],...(machine.dataset_id?[['数据版本',machine.dataset_id],['来源说明',machine.source_document]]:[])]:[];
  if(selectionNote)facts.push(['版本选择',selectionNote]);
  if(compact&&machine?.dataset_id)facts.push(['数据记录',machine.sample_count+' 条']);
  if(!machine&&platformId)facts.push(['设备 ID',platformId]);
  for(const [label,value] of facts){
    const cell=document.createElement('div'),term=document.createElement('dt'),definition=document.createElement('dd');
    term.textContent=label;definition.textContent=value||'未知';cell.append(term,definition);$('device-facts').append(cell);
  }
}
function selectMachine() {
  const m=selected();
  const evidence=document.querySelector('.device-evidence-disclosure');if(evidence)evidence.open=false;
  const telemetry=document.getElementById('overview-telemetry');if(telemetry)telemetry.open=false;
  // Leaving the device a streamed analysis belongs to retires that analysis, so
  // its late progress or report can never land on the newly selected machine.
  const root=document.documentElement;
  const previousDevice=root?.dataset.runningAnalysisDevice ?? null;
  if(previousDevice!==null&&previousDevice!==$('machine').value){
    if(typeof stopStreamedInvestigation==='function')stopStreamedInvestigation().then(()=>{
      $('status').dataset.state='idle';
      $('status').textContent='设备已切换，上一台设备的分析已停止。';
    });
  }
  if(root)root.dataset.runningAnalysisDevice=$('machine').value;
  if(typeof faultReferenceDeviceChanged==='function')faultReferenceDeviceChanged(m,defaultSource);
  if(typeof engineeringDeviceChanged==='function')engineeringDeviceChanged();
  $('case-open').disabled=!m || $('machine').disabled;
  $('xgss-device-open').disabled=!m || $('machine').disabled;
  const draft=investigationDrafts.switchTo(m?JSON.stringify([m.selection_id,m.dataset_id?m.provenance:defaultSource]):null,
    {question:$('question').value,observations:$('observations').value,task:$('task').value,language:$('language').value,priorRecordId});
  $('question').value=draft.question;$('observations').value=draft.observations;
  $('task').value=draft.task;$('language').value=draft.language;priorRecordId=draft.priorRecordId;
  $('question-details').open=Boolean(draft.question);updateTask();clearReport();
  renderDeviceFacts(m);
  $('status').textContent=!m?'暂无设备数据，请同步或导入。':draft.question||draft.observations?'已恢复当前设备的分析输入。':$('task').value==='auto'?'填写问题后开始分析。':'选择任务后开始分析。';
  $('status').dataset.state='idle';$('status').setAttribute('role','status');
  updateSourceLabel();
  $('machine-note').textContent=machineRecordNote(m);
  if(!$('history-view').hidden) refreshHistory();
  if(typeof refreshDeviceOverview==='function')refreshDeviceOverview();
  if(typeof refreshCoolingContext==='function')refreshCoolingContext();
  if(typeof updateDeviceFinder==='function')updateDeviceFinder();
  if(typeof selectLocalDraft==='function')selectLocalDraft();
  if(typeof updateFlowTrack==='function')updateFlowTrack();
  // The panel must receive the new dataset before the sensor bridge probes it.
  notifyPlatformContext();
  if(activeView==='risk'&&typeof window.renderRiskDemo==='function')void window.renderRiskDemo();
}
/**
 * Label the demo view. It shows saved real model output and nothing else, so the
 * labels are fixed: the view used to hold a simulation beside the replay, which forced
 * a check of which one was on screen. That check is gone with the simulation.
 */
function updateDemoDisclosure(){
  // Tolerate a partial DOM: this runs from setView, which some harnesses drive
  // with only the nodes that path needs.
  const demoView=$('demo-view');
  if(!demoView||demoView.hidden)return;
  const header=$('ai-runtime');
  if(header)header.textContent='AI 排查回放';
  const badge=$('source');
  if(badge)badge.textContent='真实记录回放';
}
function updateSourceLabel() {
  const m=selected(),demoView=$('demo-view');
  if(demoView&&!demoView.hidden){$('source').textContent='真实记录回放';return;}
  $('source').textContent=!$('queue-view').hidden?'排查工作台':!$('cooling-view').hidden||!$('states-view').hidden?'模拟数据':machineSourceLabel(m);
}
function applyPlatformContext(focusSelection=false,refreshSelection=false) {
  if(!location.hash.startsWith('#trackunit-asset='))return;
  const platformChanged=appliedPlatformHash!==location.hash;
  appliedPlatformHash=location.hash;
  const previousSelection=$('machine').value;
  const id=location.hash.slice('#trackunit-asset='.length);
  const valid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(id);
  const matches=valid?PlatformContext.candidates(machines,defaultSource,id):[];
  let choice=PlatformContext.selectDefault(machines,defaultSource,id,previousSelection);
  const linkQuery=new URLSearchParams(location.search),linkedDataset=linkQuery.get('dataset');
  if(!window.researchLinkContextApplied&&/^[a-f0-9]{32}$/.test(linkQuery.get('research')||'')&&/^[a-f0-9]{64}$/.test(linkedDataset||'')){
    window.researchLinkContextApplied=true;
    choice={selected:matches.find(m=>m.dataset_id===linkedDataset)||null,reason:'research_link'};
  }
  $('machine').replaceChildren(...matches.map(m=>{const o=document.createElement('option');o.value=m.selection_id;o.textContent=machineOptionLabel(m);return o;}));
  if(!matches.length){const placeholder=document.createElement('option');placeholder.value='';placeholder.textContent='正在关联当前设备';$('machine').append(placeholder);}
  $('machine').value=choice.selected?.selection_id || '';
  const selectedVersion=choice.selected;
  if(refreshSelection||previousSelection!==$('machine').value)selectMachine();
  else notifyPlatformContext();
  const choiceNote={retained:'已保留当前版本',latest_sample:'已自动载入最近采样版本',equal_latest_sample:`${choice.tied} 个版本最近采样时间相同，已自动载入其中一个`,undated_default:'已自动载入默认版本，采样时间待核实',research_link:'已载入当前排查使用的数据版本'}[choice.reason];
  $('machine-note').textContent=machineRecordNote(selectedVersion);
  renderDeviceFacts(selectedVersion,selectedVersion?`${matches.length} 个数据版本 · ${choiceNote}`:'',valid?id:'格式无效');
  $('status').textContent=!valid?'设备链接无效，请重新读取当前设备。':selectedVersion?'当前设备已关联，可开始分析。':'正在关联当前设备。';
  if(!selectedVersion)$('source').textContent='等待设备数据';
  if(valid)$('demo-entry').hidden=true;
  if(focusSelection||platformChanged)setView(activeView==='can'?'can':'work',{reason:'platform'});
  if(focusSelection&&activeView!=='can'){$('machine').focus({preventScroll:true});document.querySelector('.device').scrollIntoView({block:'start'});}
  if(typeof platformLoaderChanged==='function')platformLoaderChanged();
}
window.addEventListener('hashchange',()=>{if($('run').disabled){pendingPlatformContext=true;notifyPlatformContext();$('status').textContent='正在等待当前操作完成，随后应用新的平台设备上下文。';return;}if(location.hash.startsWith('#trackunit-asset='))applyPlatformContext(true);else refresh();});
$('refresh').onclick=refresh;
$('machine').onchange=selectMachine;
$('form').onsubmit=async e=>{
  e.preventDefault();
  if($('form').getAttribute('aria-busy')==='true')return;
  if (!selected()) {$('status').textContent='请先选择可分析的设备或数据版本。';$('machine').focus();return;}
  const question=$('question').value.trim() || taskQuestions[$('task').value];
  if(!question){$('question-details').open=true;$('status').textContent='请填写要分析的问题。';$('question').focus();return;}
  const manualFault=typeof getManualFaultReference==='function'?getManualFaultReference():null;
  const engineeringFault=typeof getEngineeringFault==='function'?getEngineeringFault():null;
  if(manualFault&&engineeringFault){$('status').textContent='一次排查只能使用一套故障资料，请移除不适用的故障码关联。';return;}
  if(!manualFault&&typeof getManualFaultDraftReference==='function'&&getManualFaultDraftReference()){
    $('status').textContent='故障码尚未确认适用范围。请先核对并带入，或移除该代码后再开始分析。';
    $('status').dataset.state='error';$('fault-reference-panel').open=true;
    $('fault-reference-panel').scrollIntoView({block:'nearest'});$('fault-reference-confirm').focus();return;
  }
  const locked=['sync-history','run','machine','refresh','finder-open','case-open','xgss-device-open','dataset-file','catalog','task','question','observations','language'];
  locked.forEach(id=>$(id).disabled=true);
  if(typeof setFaultReferenceBusy==='function')setFaultReferenceBusy(true);
  if(typeof setEngineeringBusy==='function')setEngineeringBusy(true);
  if(typeof refreshLocalDraftControls==='function')refreshLocalDraftControls();
  if(typeof setFaultContextBusy==='function')setFaultContextBusy(true);
  $('run').textContent='分析中…';$('form').setAttribute('aria-busy','true');
  $('status').textContent='正在请求 AI 分析并核对数据证据；完成后自动显示结果。';
  $('status').dataset.state='loading';$('status').setAttribute('role','status');
  const started=Date.now();$('elapsed').hidden=false;
  const tick=()=>{$('elapsed').textContent=`已等待 ${Math.floor((Date.now()-started)/1000)} 秒${Date.now()-started>60000?' · 服务仍在处理，请勿重复提交':''}`;};tick();
  const timer=setInterval(tick,1000);
  const analysisMachine=selected(),analysisSelection=analysisMachine.selection_id,analysisHash=location.hash;
  const analysisKey=analysisSelection+'@'+(analysisMachine.dataset_id||defaultSource);
  try {
    const competitionFocus=document.documentElement?.classList?.contains?.('competition-focus')===true;
    const completed=await runStreamedInvestigation({
      machine_id:analysisMachine.machine_id,dataset_id:analysisMachine.dataset_id || null,question,
      observations:competitionFocus?'':$('observations').value,language:$('language').value,task:$('task').value,
      prior_record_id:competitionFocus?null:priorRecordId,
      ...(manualFault?{manual_fault:manualFault}:{}),...(engineeringFault?{engineering_fault:engineeringFault}:{})},analysisKey);
    if(completed===null)return;
    if(selected()?.selection_id!==analysisSelection||location.hash!==analysisHash){$('status').textContent='原设备分析已完成；正在切换当前设备。';return;}
    report=completed;
    const historyNote=competitionFocus?'':completed.history_saved===false?'记录保存失败，请导出备份':'已保存诊断记录';
    renderInvestigationReport(completed,started,(text,state)=>{$('status').textContent=text;$('status').dataset.state=state;},historyNote);
    setView('work');$('result').focus();$('result').scrollIntoView({block:'start'});
  } catch(e){$('status').setAttribute('role','alert');$('status').dataset.state='error';$('status').textContent=`分析未完成：${e.message}${report?' 下方保留上次成功报告，本次未更新。':''}`;$('status').scrollIntoView({block:'nearest'});}
  finally{clearInterval(timer);$('elapsed').hidden=true;resetInvestigationProgress();locked.forEach(id=>$(id).disabled=false);if(typeof setFaultReferenceBusy==='function')setFaultReferenceBusy(false);if(typeof setEngineeringBusy==='function')setEngineeringBusy(false);if(typeof setFaultContextBusy==='function')setFaultContextBusy(false);if(typeof refreshLocalDraftControls==='function')refreshLocalDraftControls();$('sync-history').disabled=!$('sync-source').value;$('run').textContent='开始分析';$('form').setAttribute('aria-busy','false');if(pendingPlatformContext){pendingPlatformContext=false;await refresh(true);}}
};
/**
 * Show what the AI contributed to this run, from the summary the backend derived
 * out of the saved report. The model's work and the program's work are listed
 * separately so neither is credited to the other.
 */
function renderAIContribution(report, target){
  // Reopening a saved record renders through its own path, so the caller can
  // supply the container instead of relying on the live-result element.
  const root=target||$('ai-contribution');
  if(!root)return;
  const summary=report?.ai_contribution;
  root.replaceChildren();
  if(!summary){root.hidden=true;return;}
  root.hidden=false;
  const ai=summary.ai||{},program=summary.program||{};
  const head=document.createElement('div');head.className='ai-contribution-head';
  const badge=document.createElement('span');badge.className='ai-badge';badge.textContent='AI';
  const title=document.createElement('strong');title.textContent='分析概况';
  const model=(summary.model||{}).model;
  const meta=document.createElement('span');meta.className='ai-contribution-meta';
  meta.textContent=[model,ai.duration_seconds!=null?`${ai.duration_seconds} 秒`:null].filter(Boolean).join(' · ');
  head.append(badge,title,meta);
  root.append(head);
  const facts=document.createElement('ul');facts.className='ai-facts';
  const add=(label,value,note)=>{
    if(!value&&value!==0)return;
    const li=document.createElement('li');
    const strong=document.createElement('strong');strong.textContent=label;
    const span=document.createElement('span');span.textContent=value;
    li.append(strong,span);
    if(note){const small=document.createElement('small');small.textContent=note;li.append(small);}
    facts.append(li);
  };
  add('分析轮次',`${ai.model_decisions||0} 次`);
  add('追加资料',(ai.model_selected_actions||[]).length?ai.model_selected_actions.join(' / '):'无');
  add('推断的可疑部件',`${ai.hypothesis_count||0} 个`);
  add('提出的检查方向',`${ai.check_directions||0} 条`);
  add('引用的证据',`${ai.citation_count||0} 条`);
  root.append(facts);
  // Every reference the report makes is resolved against the recorded evidence.
  // A dangling citation is the one defect that would make the whole report
  // untrustworthy, so its result is stated outright rather than implied.
  const audit=summary.audit;
  if(audit){
    const line=document.createElement('p');
    line.className='ai-audit';
    line.dataset.verdict=audit.verdict;
    line.textContent=audit.dangling_count===0
      ?`来源核对：${audit.checked} 条引用均有对应资料。`
      :`来源核对：${audit.checked} 条引用中有 ${audit.dangling_count} 条缺少对应资料，相关结论待核实。`;
    root.append(line);
    if(audit.dangling_count){
      const list=document.createElement('ul');list.className='ai-dangling';
      for(const [where,items] of Object.entries(audit.dangling||{})){
        for(const ref of items){
          const li=document.createElement('li');li.textContent=`${where}：${ref}`;list.append(li);
        }
      }
      root.append(list);
    }
  }
  if((ai.hypotheses||[]).length){
    const list=document.createElement('ol');list.className='ai-hypotheses';
    for(const row of ai.hypotheses){
      const li=document.createElement('li');
      const name=document.createElement('strong');name.textContent=row.component;li.append(name);
      const grounds=[];
      if(row.pdf_pages&&row.pdf_pages.length)grounds.push(`手册第 ${row.pdf_pages.join('、')} 页`);
      if(row.check_count)grounds.push(`${row.check_count} 条检查`);
      if(row.part_candidate_count)grounds.push(`${row.part_candidate_count} 个目录候选`);
      if(grounds.length){const span=document.createElement('span');span.textContent=grounds.join(' · ');li.append(span);}
      list.append(li);
    }
    root.append(list);
  }
  const programLine=document.createElement('p');programLine.className='ai-program';
  const families=Object.entries(program.evidence_by_family||{}).map(([name,count])=>`${name} ${count}`).join('，');
  programLine.textContent=`已读取 ${program.reads_total||0} 项资料 · ${program.evidence_sources||0} 处来源${families?`（${families}）`:''} · ${program.data_facts||0} 条数据记录。`;
  root.append(programLine);
  const boundary=document.createElement('p');boundary.className='muted ai-boundary';
  boundary.textContent=(summary.boundary||[]).join(' ');
  root.append(boundary);
}
/**
 * Light up the three-step track from state the workspace actually reached:
 * the machine is selected, its current analysis has a plan/report, and current
 * catalog evidence has been analyzed. A URL or saved image alone is not completion.
 */
function updateFlowTrack(){
  const root=document.getElementById('flow-track');
  if(!root)return;
  const machine=selected(),asset=PlatformContext.asset(location.hash);
  const associated=Boolean(machine&&(!location.hash.startsWith('#trackunit-asset=')||asset===machine.machine_id));
  const research=window.currentXGSSResearchProgress?.();
  const currentReport=associated&&report&&report.machine_id===machine.machine_id&&
    (report.dataset_id||null)===(machine.dataset_id||null)?report:null;
  const diagnosed=associated&&Boolean(research?research.diagnosed:currentReport);
  const verified=associated&&Boolean(research?research.verified:currentReport&&(
    (currentReport.parts_candidates||[]).some(p=>String(p.source_id||'').startsWith('xgss:')||p.provenance==='xgss_visible_dom')||
    currentReport.xgss_catalog_context));
  const order=['connect','diagnose','verify'];
  const done={connect:associated,diagnose:diagnosed,verify:verified};
  let activeSet=false;
  for(const key of order){
    const li=root.querySelector(`li[data-step="${key}"]`);
    if(!li)continue;
    if(done[key])li.dataset.state='done';
    else if(!activeSet){li.dataset.state='active';activeSet=true;}
    else li.dataset.state='';
  }
}
$('catalog').onchange=async()=>{  const file=$('catalog').files[0];if(!file)return;
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
      const meta=document.createElement('p');meta.className='muted';meta.textContent=shortIdentifier(record.machine_id)+' · '+record.source;
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
          const saved=full.report;openedReport=saved;fullPanel.replaceChildren();
          const heading=document.createElement('h3');heading.textContent='历史报告 · '+(saved.machine_id||'当前设备');
          const note=document.createElement('p');note.className='muted';
          note.textContent=`生成时间：${displayDate(saved.generated_at)} · 来源：${saved.source} · 模型：${saved.model || '未记录'}。以下为保存时的报告，未重新运行分析。`;
          fullPanel.append(heading,note);
          // Show the same AI-contribution summary the live run displayed, so a
          // reopened record does not look like it had less AI involvement.
          const contribution=document.createElement('div');contribution.className='ai-contribution';
          renderAIContribution(saved,contribution);
          if(!contribution.hidden)fullPanel.append(contribution);
          const addSection=(title,lines)=>{
            const h=document.createElement('h4');h.textContent=title;const list=document.createElement('ul');
            for(const line of lines){const li=document.createElement('li');li.className='pre';li.textContent=line;list.append(li);}
            fullPanel.append(h,list);
          };
          addSection('数据依据与人工记录',(saved.data_facts||[]).map(f=>f.text));
          if(!saved.data_facts?.length){const old=document.createElement('p');old.textContent='此旧报告未保存独立的数据事实条目，请查看下方完整证据。';fullPanel.append(old);}
          addSection('AI解释（待核实）',[saved.summary]);
          if(typeof renderEngineeringReportInto==='function'){const engineering=document.createElement('div');renderEngineeringReportInto(engineering,saved);fullPanel.append(engineering);}
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
  if(!panel){panel=document.createElement('div');panel.id='current-feedback';panel.setAttribute('data-deferred-feature','inspection-feedback');$('result').append(panel);}
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
    if(selected()?.selection_id===selection&&typeof restoreEngineeringFault==='function')restoreEngineeringFault(parent.request.engineering_fault);
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
function notifyPanelView(reason='initial') {
  if(document.readyState==='loading'||window.parent===window)return;
  const origin=location.ancestorOrigins?.[0],connectionId=new URLSearchParams(location.search).get('panel');
  if(!connectionId||!/^chrome-extension:\/\/[a-p]{32}$/.test(origin||''))return;
  window.parent.postMessage({type:'jilian:view',protocol:1,connection_id:connectionId,
    view:activeView==='demo'?'demo':'work',asset_id:PlatformContext.asset(location.hash),reason},origin);
}
document.addEventListener('DOMContentLoaded',()=>notifyPanelView('initial'),{once:true});
function notifyPlatformContext(){
  if(typeof syncXGSSResearch==='function')syncXGSSResearch();
  if(typeof syncCanWorkspace==='function')syncCanWorkspace();
  if(window.parent===window)return;
  const origin=location.ancestorOrigins?.[0];
  if(!/^chrome-extension:\/\/[a-p]{32}$/.test(origin||''))return;
  const context=PlatformContext.snapshot({hash:location.hash,machines,source:defaultSource,
    selectionId:$('machine').value,indexState:platformIndexState,pending:pendingPlatformContext});
  if(context)window.parent.postMessage({type:'jilian:context',protocol:1,
    connection_id:new URLSearchParams(location.search).get('panel'),...context},origin);
}
function getPlatformEquipmentHint(assetId){return {...(platformEquipmentHints.get(assetId)||{confirmed:false,value:null})};}
/**
 * What the AI currently suggests the engineer should look for.
 *
 * The panel cannot judge what a parts page means; it needs the AI's hypotheses
 * to mark the right rows and to explain a match. Only suggestion text, its
 * stated reason and manual reference ids leave the frame — never device data.
 */
function currentAISearchGuidance(){
  // A report the engineer opened from the history counts as much as a fresh run: the
  // sidebar asks for the AI's search terms whenever they want to mark the catalog, and
  // "you have to re-run the analysis first" is not an acceptable answer when the report
  // is already on screen. The opened report is kept separately so the live-run state
  // (flow track, export, feedback) is not silently switched to a historical snapshot.
  const source=report||openedReport;
  const hypotheses=Array.isArray(source?.component_hypotheses)?source.component_hypotheses:[];
  const terms=[],components=[];
  for(const row of hypotheses){
    const name=typeof row?.component==='string'?row.component.trim():'';
    if(name&&!components.some(item=>item.name===name)){
      components.push({name,reason:(typeof row.rationale==='string'?row.rationale:'').slice(0,220),
        reference_ids:(row.reference_ids||[]).slice(0,4)});
    }
    for(const term of row?.search_terms||[]){
      const clean=typeof term==='string'?term.trim():'';
      if(clean&&clean.length>=2&&clean.length<=40&&!terms.includes(clean))terms.push(clean);
    }
  }
  return {terms:terms.slice(0,12),components:components.slice(0,6),
    // Both flags describe the report the terms came from, so an opened report is not
    // announced as "no AI suggestion" while its terms are being sent.
    fault_code:source?.engineering_fault?.code||null,has_report:Boolean(source),
    has_search_terms:terms.length>0,
    machine_model:selected()?.model||null};
}
function handleAIGuidanceRequest(event){
  const origin=location.ancestorOrigins?.[0],data=event.data;
  if(window.parent===window||event.source!==window.parent||event.origin!==origin||!/^chrome-extension:\/\/[a-p]{32}$/.test(origin||''))return;
  if(data?.type!=='jilian:ai-guidance-request'||data.protocol!==1||data.connection_id!==new URLSearchParams(location.search).get('panel'))return;
  window.parent.postMessage({type:'jilian:ai-guidance',protocol:1,connection_id:data.connection_id,
    request_id:typeof data.request_id==='string'?data.request_id.slice(0,64):null,...currentAISearchGuidance()},origin);
}
window.addEventListener('message',handleAIGuidanceRequest);
function handlePlatformContextRequest(event){
  const origin=location.ancestorOrigins?.[0],data=event.data;
  if(window.parent===window||event.source!==window.parent||event.origin!==origin||!/^chrome-extension:\/\/[a-p]{32}$/.test(origin||''))return;
  if(data?.type!=='jilian:context-request'||data.protocol!==1||data.connection_id!==new URLSearchParams(location.search).get('panel')||data.asset_id!==PlatformContext.asset(location.hash))return;
  if(!PlatformContext.asset(location.hash))return;
  const hint=PlatformContext.equipmentHint(data.equipment_id_hint);
  if(hint===undefined)return;
  platformEquipmentHints.set(data.asset_id,{confirmed:true,value:hint});
  if(data.show_work===true){
    if($('run').disabled||$('form').getAttribute('aria-busy')==='true'){
      pendingPlatformContext=true;notifyPlatformContext();
      $('status').textContent='当前分析完成后将返回平台设备排查。';return;
    }
    applyPlatformContext(true);
  }
  notifyPlatformContext();
  if(typeof platformLoaderChanged==='function')platformLoaderChanged();
}
window.addEventListener('message',handlePlatformContextRequest);
async function refreshAIRuntime() {
  try {
    const runtime=await api('/assistant/runtime');
    aiProvider=runtime.provider;
    notifyAssistantPanel('jilian:runtime',{provider:runtime.provider,model:runtime.model,
      backend_build:runtime.backend_build,inference_location:runtime.inference_location,
      investigation_timeout_seconds:runtime.investigation_timeout_seconds,transient_attempt_limit:runtime.transient_attempt_limit});
    const copy=AIRequestStatus.runtimeView(runtime);
    aiRuntimeLabel=runtime.inference_location==='cloud'&&runtime.cloud_credentials_configured===false?'AI 待连接':'AI 辅助分析';
    aiFooterLabel='机联智检 · 工程机械运维助手';
    updateRuntimeLabel();
    $('ai-data-note').textContent=copy.note;
  } catch (e) {
    aiRuntimeLabel='AI 未连接';updateRuntimeLabel();
    $('ai-data-note').textContent='请检查服务连接后刷新。';
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
  $('runtime-footer').textContent=aiFooterLabel;
  $('ai-runtime').textContent=!$('demo-view').hidden?'AI 排查回放':!$('queue-view').hidden?'任务与记录':!$('cooling-view').hidden?'模拟预警':!$('states-view').hidden?'模拟工况':aiRuntimeLabel;
}
refreshAIRuntime();


/**
 * Drive one streamed investigation and resolve with its report.
 *
 * Resolves `null` when the run was stopped or interrupted, so the caller keeps
 * whatever report it already had instead of rendering a partial one. Progress is
 * rendered from real backend events only.
 */
let investigationRunner=null, investigationProgressTimer=null, investigationProgressStartedAt=0;
function resetInvestigationProgress(){
  clearInterval(investigationProgressTimer);investigationProgressTimer=null;
  const panel=$('ai-progress');if(panel)panel.hidden=true;
}
function renderInvestigationProgress(event){
  const panel=$('ai-progress'),text=$('ai-progress-text'),step=$('ai-progress-step');
  if(!panel||!text||!step)return;
  panel.hidden=false;
  panel.dataset.state=event.type==='stopped'?'stopped':event.type==='error'?'error':'running';
  text.textContent=event.message||'正在分析…';
  const label={prepare:'准备',reading:'读取设备数据',model_decision:'模型决策',finalizing:'整理报告'}[event.stage];
  step.textContent=event.stage==='model_decision'&&event.step
    ? `${label||'模型决策'} ${event.step}${event.total?` / ${event.total}`:''}`:(label||'');
}
/**
 * Run one streamed investigation and resolve with its validated report.
 *
 * Resolves null when the run was stopped, so the caller keeps the report it
 * already had instead of rendering a partial one. What the user sees comes only
 * from backend events, and every terminal path clears the progress panel.
 */
async function runStreamedInvestigation(payload,analysisKey){
  let settle;
  const outcome=new Promise(resolve=>{settle=resolve;});
  const runner=InvestigationRunner.create({
    machineKey:()=>analysisKey,
    onProgress:event=>{if(investigationRunner===runner)renderInvestigationProgress(event);},
    onTerminal:event=>settle(event),
  });
  investigationRunner=runner;
  investigationProgressStartedAt=Date.now();
  investigationProgressTimer=setInterval(()=>{
    const elapsed=$('ai-progress-elapsed'),panel=$('ai-progress');
    if(elapsed&&panel&&!panel.hidden)elapsed.textContent=`已等待 ${Math.floor((Date.now()-investigationProgressStartedAt)/1000)} 秒`;
  },1000);
  // Await completion, not response headers: stopping must unlock the form even
  // while fetch is still pending. Submission failures use the same error path.
  runner.start(payload,analysisKey).catch(error=>settle({type:'error',message:error.message,kind:'network'}));
  try{
    const event=await outcome;
    if(event?.type==='result')return event.report;
    if(event?.type==='cancelled'){
      if(investigationRunner===runner){$('status').dataset.state='idle';$('status').textContent=event.message;}
      return null;
    }
    const error=new Error(event?.message||'分析未完成。');error.kind=event?.kind;throw error;
  }finally{
    if(investigationRunner===runner){resetInvestigationProgress();investigationRunner=null;}
  }
}
/** Withdraw locally; this does not acknowledge an upstream provider abort. */
async function stopStreamedInvestigation(){
  if(!investigationRunner)return null;
  const root=document.documentElement;
  if(root)delete root.dataset.runningAnalysisDevice;
  return investigationRunner.stop('user');
}
$('ai-progress-stop')?.addEventListener('click',async()=>{
  await stopStreamedInvestigation();
  $('status').dataset.state='idle';
  $('status').textContent='分析已停止，已读取的资料和输入已保留。';
});
$('ai-retry')?.addEventListener('click',()=>{$('form').requestSubmit();});

/**
 * Render one validated investigation report. Every caller passes a report that
 * already passed the backend checks, so a stream that is still incomplete can
 * never reach this function. Returns the reported duration in seconds.
 */
function renderInvestigationReport(report, started, onStatus, historyNote=''){
  // Read the applied fault from the report itself: the streamed path and the
  // direct path must agree, so neither may depend on local form state here.
  const engineeringFault=report.engineering_fault||null;
  const manualFault=report.evidence?.['manual:retrieval']||null;
  $('current-feedback')?.remove();
  if(typeof renderAIContribution==='function')renderAIContribution(report);
  $('summary').textContent=report.summary;
  $('summary').previousElementSibling.textContent='AI解释 · 待核实';
  if(typeof renderEngineeringReport==='function')renderEngineeringReport(report);
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
      note.textContent=`${{application_rule:'数据核验规则',demo:'演示资料',user_supplied:'用户提供资料',ai_inference_from_manual:'AI依据手册推断'}[evidence.provenance] || '待核实资料'} · ${evidence.source_document} · 依据：${evidence.evidence_ids.join('、')}`;
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
      const fromXGSS=p.provenance==='xgss_visible_dom'||p.source==='xgss_visible_dom'||String(p.source_id||'').startsWith('xgss:');
      [p.name+'\n'+p.part_number,
       (p.models||[]).join('、')+'\n'+(p.ranking_reason||(p.match_reason==='fault_code'?'故障码匹配':'部件匹配'))+' · '+(p.serial_verified?'序列号在适用清单':'整机适用性待确认'),
       (fromXGSS?'XGSS 可见图册条目':p.provenance==='demo'?'演示资料':'用户提供资料')+' · 候选待核查\n'+(p.source_document||'')+' / '+(p.source_page||p.figure_ref||'位置待核对')+' / '+(p.revision||'版本待核对')+'\n'+(p.checks||[]).join('；')
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
    $('parts').textContent=engineeringFault?'本次尚未关联具体料号。可先查看可疑部件和检索词，读取对应 VIN 的 XGSS 图册后继续分析。':search ? (reasons[search.reason_code]||'本次没有可展示的匹配候选。')+' 检索仅覆盖当前本地目录。'
      : '尚无匹配候选。请补充故障证据或对应型号的备件目录。';
  }
  $('evidence').textContent=JSON.stringify({citations:report.citations,tools:report.tool_trace,evidence:report.evidence},null,2);
  $('result-xgss-controls').replaceChildren();
  if(typeof createXGSSControls==='function') {
    const machine=selected();
    $('result-xgss-controls').append(createXGSSControls({...machine,source:machine.dataset_id?'imported_'+machine.provenance:defaultSource},engineeringFault?.code||manualFault?.code||null));
  }
  $('result').hidden=false; $('empty-result').hidden=true;
  $('result-feedback').disabled=!report.record_id;
  onStatus([`分析完成 · 用时 ${Math.round((Date.now()-started)/1000)} 秒`,historyNote].filter(Boolean).join(' · '),'complete');
  if(typeof updateFlowTrack==='function')updateFlowTrack();
}
