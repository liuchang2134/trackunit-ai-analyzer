let faultContextTicket=0, faultContextOpener=null;
function resetFaultContext(restoreFocus=false) {
  ++faultContextTicket;
  $('fault-context').hidden=true;
  $('fault-context-body').replaceChildren();
  if(faultContextOpener?.isConnected){
    faultContextOpener.setAttribute('aria-expanded','false');
    if(restoreFocus)faultContextOpener.focus();
  }
  faultContextOpener=null;
}
function focusFaultInvestigation(code) {
  if(typeof window.focusXGSSResearch==='function'){window.focusXGSSResearch(code);return;}
  if($('run').disabled)return;
  $('task').value='parts';updateTask();$('question-details').open=true;
  $('question').value=`请重点排查故障码 ${code}，结合该设备已有记录说明判断依据、建议检查和适配备件候选。`;
  if(typeof refreshLocalDraftControls==='function')refreshLocalDraftControls();
  $('status').dataset.state='ready';$('status').setAttribute('role','status');
  $('status').textContent='已填入关注的故障码。核对后点击开始分析。';
  $('question').focus({preventScroll:true});document.querySelector('.query').scrollIntoView({block:'start'});
}
function setFaultContextBusy(busy){const button=$('fault-context-ai');if(button)button.disabled=busy;}
function faultText(tag,text,className='') {
  const node=document.createElement(tag);node.textContent=text;
  if(className)node.className=className;
  return node;
}
async function showFaultContext(code,opener) {
  resetFaultContext();
  const machine=selected();if(!machine)return;
  const ticket=faultContextTicket;
  faultContextOpener=opener;opener.setAttribute('aria-expanded','true');
  const panel=$('fault-context'),note=$('fault-context-note');
  panel.hidden=false;panel.setAttribute('aria-busy','true');
  $('fault-context-title').textContent='故障资料 · '+code;
  note.setAttribute('role','status');note.textContent='正在读取当前设备的故障记录和本地备件目录…';
  panel.focus();panel.scrollIntoView({block:'start'});
  const params=new URLSearchParams({machine_id:machine.machine_id,fault_code:code});
  if(machine.dataset_id)params.set('dataset_id',machine.dataset_id);
  try {
    const data=await api('/assistant/fault-context?'+params);
    if(ticket!==faultContextTicket)return;
    renderFaultContext(data);
    panel.scrollIntoView({block:'start'});
  } catch(error) {
    if(ticket!==faultContextTicket)return;
    note.setAttribute('role','alert');note.textContent='资料读取失败：'+error.message;
  } finally {
    if(ticket===faultContextTicket)panel.setAttribute('aria-busy','false');
  }
}
function renderFaultContext(data) {
  const body=$('fault-context-body'),demo=['mock','imported_synthetic'].includes(data.source);
  $('fault-context-note').textContent=`${demo?'模拟数据':'实测记录 · 未验证'} · ${data.model} · ${data.serial_number} · 本地资料查询`;
  const statusNames={open:'未解决',acknowledged:'已确认记录',resolved:'已解决（历史记录）',conflicting:'同一时点状态冲突，需核实'};
  body.append(faultText('p',`最新记录：${displayDate(data.latest_record_at)} · ${statusNames[data.latest_record_status]||data.latest_record_status}`));
  const actions=document.createElement('div');actions.className='fault-context-actions';
  const ai=document.createElement('button');ai.id='fault-context-ai';ai.type='button';ai.textContent='带此故障码进入 AI 排查';ai.disabled=$('run').disabled;
  ai.onclick=()=>focusFaultInvestigation(data.fault_code);actions.append(ai);body.append(actions);
  const history=document.createElement('details');history.append(faultText('summary','查看故障记录原文'));
  history.append(faultText('p',`${data.record_facts.valid_loaded_records} 条有效记录；不代表相同数量的独立故障。资料截止 ${displayDate(data.as_of)}。`,'muted'));
  if(data.source_document)history.append(faultText('p','记录来源：'+data.source_document,'muted'));
  history.append(faultText('p','本页未调用 AI，也未同步外部平台。','muted'));
  const records=document.createElement('ol');
  for(const event of [...data.record_facts.events].reverse()){
    records.append(faultText('li',`${displayDate(event.occurred_at)} · ${statusNames[event.status]||event.status}\n${event.description}`,'pre'));
  }
  history.append(records,faultText('p',`显示最近 ${data.record_facts.events.length} 条对应故障记录。`,'muted'));body.append(history);
  body.append(faultText('h4','适配备件候选 · 本地目录'));
  body.append(faultText('p','按故障码、机型与目录序列号范围匹配；候选需核查整机配置。未查询库存或价格。','muted'));
  const reasons={catalog_empty:'本地尚未导入备件目录。',no_eligible_catalog:'现有目录仅含演示资料，不用于实测设备。',
    model_not_in_catalog:'可用目录没有列明当前机型。',serial_not_applicable:'目录中有当前机型，但序列号不在适用清单内。',
    fault_or_component_not_matched:'机型与序列号范围筛选后，没有条目匹配此故障码。'};
  if(!data.parts_candidates.length)body.append(faultText('p',(reasons[data.search_diagnostics.reason_code]||'没有找到符合约束的候选。')+' 需要补充有出处的对应目录；无匹配不代表该备件不存在。','catalog-empty'));
  for(const part of data.parts_candidates){
    const article=document.createElement('article');article.className='fault-part';
    article.append(faultText('h4',part.name),faultText('p',part.part_number,'part-number'));
    article.append(faultText('p',part.provenance==='demo'?'演示资料 · 不可用于采购':'用户提供目录 · 尚未获得厂家认证','catalog-provenance'));
    article.append(faultText('p',part.serial_verified?'目录清单包含此序列号；整机配置仍需核对。':'仅机型匹配；序列号和整机配置尚未核验。'));
    article.append(faultText('p',`资料出处：${part.source_document} · ${part.source_page} · 版本 ${part.revision}`,'muted'));
    const checks=document.createElement('details');checks.append(faultText('summary','查看检查依据（目录原文）'));
    const list=document.createElement('ol');for(const check of part.checks)list.append(faultText('li',check));
    checks.append(list);article.append(checks);body.append(article);
  }
  if(data.search_diagnostics.truncated)body.append(faultText('p','最多显示 20 项候选，请使用更完整的机型和配置资料进一步核对。','muted'));
  if(!document.documentElement?.classList?.contains?.('competition-focus'))body.append(createXGSSControls(data,data.fault_code));
}
$('fault-context-close').onclick=()=>resetFaultContext(true);
