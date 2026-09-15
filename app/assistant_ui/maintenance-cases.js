/* Operator tasks are independent of machine fault status and AI availability. */
const CaseWorkflow = (() => {
  const labels = {open:'待开始',in_progress:'排查中',waiting:'待补充',archived:'已归档'};
  const source = m => m.source || (m.dataset_id?'imported_'+m.provenance:'mock');
  const matches = (scope, m) => Boolean(m && scope.machine_id===m.machine_id &&
    (scope.dataset_id||null)===(m.dataset_id||null) && scope.source===source(m) &&
    scope.serial_number===m.serial_number);
  const scopeKey = m => JSON.stringify([m.machine_id,m.dataset_id||null,source(m),m.serial_number]);
  const newest = (previous,incoming) => previous && incoming && previous.case_id===incoming.case_id && previous.revision>incoming.revision?previous:incoming;
  function linkEntry(entries,entry,record){
    entries.set('case:'+record.case_id,entry);
    const key='scope:'+scopeKey(record.scope);
    if(record.state!=='archived')entries.set(key,entry);
    else if(entries.get(key)===entry)entries.delete(key);
  }
  class Gate {
    constructor(){this.ticket=0;this.key=null;}
    begin(key){this.key=key;return {key,ticket:++this.ticket};}
    accepts(token){return this.key===token.key && this.ticket===token.ticket;}
    close(){this.key=null;++this.ticket;}
  }
  function ensureSaved(record, pending) {
    if((pending.note || '').trim() || (pending.desired && pending.desired!==record.state))
      throw new Error('请先保存本次检查记录与进度，再带入 AI；当前输入已保留。');
  }
  function handoff(record, inputs) {
    const recorded=record.events.filter(e=>e.note.trim());
    const included=recorded.filter((_,index)=>index===0 || index>=recorded.length-3);
    const notes=included.map(e=>
      `${e.created_at} · ${labels[e.to_state]}\n${e.note}`);
    const coverage=recorded.length>included.length?`仅带入首条原始描述与最近三条有文字的记录（去重）；其余 ${recorded.length-included.length} 条仍在任务历史中，不应视为已读取。\n`:'';
    const block=`本机排查任务 ${record.case_id}：${record.title}\n以下为人工记录，未经验证：\n${coverage}${notes.join('\n\n')}`;
    const observations=inputs.observations.includes(block)?inputs.observations:
      [inputs.observations,block].filter(Boolean).join('\n\n');
    const question=inputs.question || `继续排查“${record.title}”，结合已有设备证据和现场记录说明下一步检查。`;
    if(observations.length>4000 || question.length>3000)throw new Error('带入后超出输入长度，请先整理现场记录；完整原文仍保存在任务历史中。');
    return {question,observations};
  }
  return {labels,source,matches,scopeKey,Gate,handoff,ensureSaved,newest,linkEntry};
})();
if(typeof module!=='undefined')module.exports=CaseWorkflow;

if(typeof document!=='undefined') {
  const entries=new Map(),gate=new CaseWorkflow.Gate();
  let activeEntry=null,opener=null,closeAction=null,listTicket=0,casePage=0,attentionPage=0;
  const size=20;
  const platform=()=>location.hash.startsWith('#trackunit-asset=')?location.hash.slice('#trackunit-asset='.length):null;
  const allowedDevice=scope=>DeviceFinder.filter(machines,{platformId:platform()}).find(m=>CaseWorkflow.matches(scope,m));
  const say=(message,error=false)=>{
    $('case-status').textContent=message;$('case-status').setAttribute('role',error?'alert':'status');
  };
  const element=(tag,text,className)=>{const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(className)el.className=className;return el;};
  function button(text,action,className='quiet'){
    const el=element('button',text,className);el.type='button';el.onclick=action;return el;
  }
  function openDevice(scope){
    const m=allowedDevice(scope);
    if(!m || $('machine').disabled || ![...$('machine').options].some(o=>o.value===m.selection_id))return false;
    if($('machine').value!==m.selection_id){$('machine').value=m.selection_id;selectMachine();}
    setView('work');return true;
  }
  function remember(){
    if(!activeEntry || activeEntry.loading)return;
    activeEntry.note=$('case-note').value;
    activeEntry.title=$('case-new-title').value;
    activeEntry.desired=$('case-state').value;
  }
  function renderCase(){
    const e=activeEntry,record=e?.record;
    if(!e)return;
    $('case-dialog-title').textContent=record?record.title:'建立设备排查任务';
    const scope=record?.scope || e.scope || {};
    $('case-scope').textContent=scope.machine_id?`${scope.model || ''} · ${scope.serial_number} · ${DeviceFinder.sourceLabel(scope)} · ${scope.dataset_id?'版本 '+scope.dataset_id.slice(0,8):'建立时缓存摘要'}`:'正在读取任务对应的设备…';
    $('case-summary').textContent=record?`${CaseWorkflow.labels[record.state]} · 保存于 ${displayDate(record.updated_at)} · ${record.revision} 条记录`:'此设备与数据版本尚无进行中的任务。';
    $('case-create-title').hidden=!!record;
    $('case-state-label').hidden=!record;
    $('case-new-title').value=e.title || '';
    $('case-note').value=e.note || '';
    $('case-state').value=e.desired || record?.state || 'open';
    $('case-save').textContent=record?'保存记录与进度':'建立任务';
    $('case-fields').disabled=Boolean(e.loading || e.busy);
    $('case-reload').disabled=Boolean(e.loading || e.busy);
    $('case-save').disabled=Boolean(e.loading || e.busy || e.conflict);
    $('case-export').hidden=!record;
    $('case-export').href=record?`/assistant/cases/${record.case_id}/export.md`:'';
    $('case-history').replaceChildren();
    for(const event of record?.events || []){
      const li=element('li');li.append(element('strong',`${CaseWorkflow.labels[event.to_state]} · ${displayDate(event.created_at)}`));
      li.append(element('p',event.note || '建立任务，尚未填写现场记录。','pre'));
      if(event.report_id)li.append(element('small','关联 AI 报告：'+event.report_id));
      $('case-history').append(li);
    }
    $('case-history-details').hidden=!record;
    const linked=record && report?.record_id && CaseWorkflow.matches(record.scope,selected());
    $('case-link-report-label').hidden=!linked;
    $('case-link-report').checked=false;
    const available=Boolean(allowedDevice(scope)) && !$('machine').disabled;
    $('case-evidence').disabled=!available;
    $('case-ai-handoff').disabled=!available || !record || e.busy;
    $('case-device-limit').hidden=available;
    $('case-device-limit').textContent=$('machine').disabled?'当前 AI 操作进行中，暂不能切换设备。':'对应设备版本当前不可用；任务仍可查看、追加记录与导出，不会改选其他设备。';
  }
  async function loadEntry(key, entry, path){
    const token=gate.begin(key);activeEntry=entry;entry.loading=true;renderCase();say('读取本机任务…');
    try{
      const data=await api(path);if(!gate.accepts(token))return;
      entry.record=CaseWorkflow.newest(entry.record,data.case);entry.conflict=false;
      if(entry.desired===undefined)entry.desired=data.case?.state || 'open';
      if(entry.record)CaseWorkflow.linkEntry(entries,entry,entry.record);
      say('任务记录只保存在本机；更新进度不会修改设备上报的故障状态。');
    }catch(error){if(gate.accepts(token)){entry.conflict=true;say(error.message,true);}}
    finally{if(gate.accepts(token)){entry.loading=false;renderCase();}}
  }
  async function openTask(item=null,caseId=null){
    remember();opener=document.activeElement;
    const key=caseId?'case:'+caseId:'scope:'+CaseWorkflow.scopeKey(item);
    let entry=entries.get(key);
    if(!entry){entry={scope:item,title:item?`${item.model} 设备排查`:'',note:'',record:null};entries.set(key,entry);}
    if(!$('case-dialog').open)$('case-dialog').showModal();
    let path='/assistant/cases/'+caseId;
    if(!caseId){
      const params=new URLSearchParams({machine_id:item.machine_id,source:CaseWorkflow.source(item)});
      if(item.dataset_id)params.set('dataset_id',item.dataset_id);
      path='/assistant/cases/current?'+params;
    }
    entry.path=path;await loadEntry(key,entry,path);
    if(activeEntry===entry && $('case-dialog').open)$('case-note').focus();
  }
  $('case-open').onclick=()=>{const m=selected();if(m)openTask(m);};
  function closeTask(action=null){closeAction=action;$('case-dialog').close();}
  $('case-close').onclick=()=>closeTask();
  $('case-dialog').addEventListener('close',()=>{remember();gate.close();
    const action=closeAction;closeAction=null;
    if(action){action();return;}
    const target=opener?.isConnected?opener:!$('queue-view').hidden?document.querySelector('[data-view="queue"]'):$('case-open');target?.focus();});
  for(const id of ['case-note','case-new-title','case-state'])$(id).addEventListener('input',remember);
  $('case-reload').onclick=()=>{remember();if(activeEntry)loadEntry(gate.key,activeEntry,activeEntry.path);};
  $('case-form').onsubmit=async event=>{
    event.preventDefault();remember();const entry=activeEntry;
    if(!entry || entry.busy || entry.loading || entry.conflict)return;
    const token=gate.begin(gate.key),previous=entry.record;
    const note=entry.note || '',state=entry.desired || previous?.state || 'open';
    if(previous && !note.trim()){say('请填写本次检查结果或进度变更原因。',true);$('case-note').focus();return;}
    if(!previous && !(entry.title || '').trim()){say('请填写任务名称。',true);$('case-new-title').focus();return;}
    let payload,path;
    if(previous){
      payload={expected_revision:previous.revision,state,note,
        report_id:$('case-link-report').checked && report?.record_id && CaseWorkflow.matches(previous.scope,selected())?report.record_id:null};
      path=`/assistant/cases/${previous.case_id}/events`;
    }else{
      payload={machine_id:entry.scope.machine_id,source:CaseWorkflow.source(entry.scope),dataset_id:entry.scope.dataset_id||null,title:entry.title,note};path='/assistant/cases';
    }
    entry.busy=true;renderCase();say('正在保存本机任务…');
    try{
      const data=await api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      entry.record=CaseWorkflow.newest(entry.record,data.case);entry.path='/assistant/cases/'+data.case.case_id;CaseWorkflow.linkEntry(entries,entry,entry.record);
      if(data.created!==false){entry.note='';entry.desired=data.case.state;}
      if(gate.accepts(token))say(data.created===false?'此设备已有进行中的任务，已打开原任务；刚才输入的文字尚未追加，请核对后保存。':`已保存 · ${CaseWorkflow.labels[data.case.state]}。${data.case.state==='archived'?'仅归档本次任务，不代表设备已修复。':''}`);
      if(!$('queue-view').hidden)enterWorklist();
    }catch(error){entry.conflict=error.status===409;if(gate.accepts(token))say(error.message,true);}
    finally{entry.busy=false;if(activeEntry===entry && $('case-dialog').open){renderCase();
      if(gate.accepts(token)){$('case-status').tabIndex=-1;$('case-status').focus({preventScroll:true});}}}
  };
  $('case-evidence').onclick=()=>{
    const scope=activeEntry?.record?.scope || activeEntry?.scope;
    if(scope && openDevice(scope))closeTask(()=>{$('overview-title').scrollIntoView({block:'start'});$('overview-title').focus();});
  };
  $('case-ai-handoff').onclick=()=>{
    remember();
    const entry=activeEntry,record=entry?.record;if(!record)return;
    try{
      CaseWorkflow.ensureSaved(record,entry);
      if(!openDevice(record.scope))return;
      const values=CaseWorkflow.handoff(record,{question:$('question').value,observations:$('observations').value});
      $('question').value=values.question;$('observations').value=values.observations;
      updateTask();$('question-details').open=true;document.querySelector('.observations').open=true;
      if(typeof refreshLocalDraftControls==='function')refreshLocalDraftControls();
      closeTask(()=>{document.querySelector('.query').scrollIntoView({block:'start'});$('question').focus({preventScroll:true});});
      $('status').textContent='已带入首条原始描述与最近三条有文字的人工记录（去重）；尚未调用 AI，请核对后开始分析。';
    }catch(error){say(error.message,true);}
  };

  function renderAttention(){
    const rows=DeviceFinder.filter(machines,{source:$('queue-source').value,attention:true,platformId:platform()});
    attentionPage=Math.min(attentionPage,Math.max(0,Math.ceil(rows.length/size)-1));
    $('queue-device-count').textContent=`${rows.length} 个数据版本有未解决或冲突记录`;
    $('queue-device-list').replaceChildren();
    for(const m of rows.slice(attentionPage*size,(attentionPage+1)*size)){
      const li=element('li',undefined,'worklist-row'),identity=element('div');
      identity.append(element('strong',`${m.model} · ${m.serial_number}`),element('small',`${DeviceFinder.sourceLabel(m)} · ${m.dataset_id?'版本 '+m.dataset_id.slice(0,8):'当前缓存'}`));
      const evidence=element('div');evidence.append(element('span',DeviceFinder.faultLabel(m.fault_summary)),element('small','记录时间：'+displayDate(m.fault_summary.latest_record_at)));
      li.append(identity,evidence,button('进入设备',()=>{if(openDevice(m)){$('case-open').focus();}}));
      $('queue-device-list').append(li);
    }
    $('queue-device-empty').hidden=Boolean(rows.length);
    $('queue-device-empty').textContent=machines.length?'所选范围没有待核对记录。这不表示设备均正常；可查找其他设备或检查数据来源。':'尚未载入设备，请刷新或进入数据与备件库导入。';
    $('queue-device-warning').textContent=deviceIndexWarnings.join(' ');
    $('queue-device-warning').hidden=!deviceIndexWarnings.length;
    $('queue-device-pages').hidden=rows.length<=size;
    $('queue-device-prev').disabled=attentionPage===0;$('queue-device-next').disabled=(attentionPage+1)*size>=rows.length;
    $('queue-device-page').textContent=`第 ${attentionPage+1} 页`;
  }
  window.enterWorklist=async()=>{
    renderAttention();const ticket=++listTicket;
    const id=platform();
    if(id!==null && !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(id)){
      $('queue-case-list').replaceChildren();$('queue-case-status').textContent='平台设备 ID 无效，未显示其他设备任务。';return;
    }
    const params=new URLSearchParams({state:$('queue-case-filter').value,limit:size,offset:casePage*size});
    if(id!==null){params.set('machine_id',id);params.set('real_only','true');}
    $('queue-case-status').textContent='读取本机排查任务…';$('queue-case-list').replaceChildren();
    try{
      const data=await api('/assistant/cases?'+params);if(ticket!==listTicket)return;
      if(casePage>0 && casePage*size>=data.total){casePage=Math.max(0,Math.ceil(data.total/size)-1);return enterWorklist();}
      $('queue-case-status').textContent=data.total?`${data.total} 条${$('queue-case-filter').value==='archived'?'已归档':'进行中'}任务`:'当前没有任务。可从下方进入设备，点击“排查任务”建立。';
      for(const item of data.cases){
        const li=element('li',undefined,'worklist-row'),identity=element('div');
        identity.append(element('strong',item.title),element('small',`${item.scope.model || ''} · ${item.scope.serial_number} · ${DeviceFinder.sourceLabel(item.scope)} · ${item.dataset_id?'版本 '+item.dataset_id.slice(0,8):'建立时缓存'}`));
        const state=element('div');state.append(element('span',CaseWorkflow.labels[item.state],'case-state-tag'),element('small','更新：'+displayDate(item.updated_at)));
        li.append(identity,state,button(item.state==='archived'?'查看归档':'继续处理',()=>openTask(null,item.case_id)));
        $('queue-case-list').append(li);
      }
      $('queue-case-pages').hidden=data.total<=size;
      $('queue-case-prev').disabled=casePage===0;$('queue-case-next').disabled=(casePage+1)*size>=data.total;
      $('queue-case-page').textContent=`第 ${casePage+1} / ${Math.max(1,Math.ceil(data.total/size))} 页`;
    }catch(error){if(ticket===listTicket)$('queue-case-status').textContent='任务未载入：'+error.message;}
  };
  $('queue-refresh').onclick=()=>refresh();
  $('queue-case-filter').onchange=()=>{casePage=0;enterWorklist();};
  $('queue-source').onchange=()=>{attentionPage=0;renderAttention();};
  $('queue-find').onclick=()=>{setView('work');$('finder-open').click();};
  for(const [id,delta] of [['queue-case-prev',-1],['queue-case-next',1]])$(id).onclick=()=>{casePage+=delta;enterWorklist();};
  for(const [id,delta] of [['queue-device-prev',-1],['queue-device-next',1]])$(id).onclick=()=>{attentionPage+=delta;renderAttention();};
  setView(platform()===null?'queue':'work');
}
