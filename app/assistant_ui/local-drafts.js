// A stored draft is operator input, never a successful diagnosis.
const cloneDraftContent=content=>({...content,...(Object.prototype.hasOwnProperty.call(content,'manual_fault')
  ?{manual_fault:content.manual_fault?{...content.manual_fault}:null}:{}),...(Object.prototype.hasOwnProperty.call(content,'engineering_fault')
  ?{engineering_fault:content.engineering_fault?{...content.engineering_fault}:null}:{})});
const cloneStoredDraft=saved=>saved?{...saved,content:cloneDraftContent(saved.content)}:null;
const manualFaultValue=fault=>fault?[fault.code,fault.model,fault.version,fault.applicability_confirmed]:null;
const engineeringFaultValue=fault=>fault?[fault.code,fault.model,fault.configuration,fault.source]:null;
const meaningfulDraft=content=>Boolean(content.question.trim()||content.observations.trim()||content.prior_record_id||
  (content.manual_fault?.code&&content.manual_fault.applicability_confirmed===true)||content.engineering_fault?.code);
class LocalDraftState {
  constructor(){this.key=null;this.entries=new Map();}
  select(key){this.key=key;if(key!==null&&!this.entries.has(key))this.entries.set(key,{saved:null,loaded:false,loading:false,busy:false,error:null,conflict:false,ticket:0,undo:null});return this.entry();}
  entry(){return this.entries.get(this.key)||null;}
  beginRead(){const e=this.entry();e.loading=true;e.error=null;return {key:this.key,ticket:++e.ticket};}
  acceptRead(token,saved){const e=this.entries.get(token.key);if(e?.ticket!==token.ticket)return false;e.saved=cloneStoredDraft(saved);e.loaded=true;e.loading=false;e.error=null;return this.key===token.key;}
  failRead(token,error){const e=this.entries.get(token.key);if(e?.ticket!==token.ticket)return false;e.loading=false;e.error=error;return this.key===token.key;}
  beginSave(content){const e=this.entry();e.busy=true;e.error=null;return {key:this.key,ticket:++e.ticket,expected_revision:e.saved?.revision||null,content:cloneDraftContent(content)};}
  finishSave(token,saved){const e=this.entries.get(token.key);if(e?.ticket!==token.ticket)return false;e.busy=false;e.loaded=true;e.saved=cloneStoredDraft(saved);e.error=null;return this.key===token.key;}
  failSave(token,error,conflict=false){const e=this.entries.get(token.key);if(e?.ticket!==token.ticket)return false;e.busy=false;e.error=error;e.conflict=conflict;return this.key===token.key;}
  dirty(content){const saved=this.entry()?.saved?.content;return !saved||['question','observations','task','language','prior_record_id'].some(field=>content[field]!==saved[field])||JSON.stringify(manualFaultValue(content.manual_fault))!==JSON.stringify(manualFaultValue(saved.manual_fault))||JSON.stringify(engineeringFaultValue(content.engineering_fault))!==JSON.stringify(engineeringFaultValue(saved.engineering_fault));}
  restore(current){const e=this.entry();if(!e?.saved||(e.conflict&&e.error))return null;e.undo=cloneDraftContent(current);e.conflict=false;e.error=null;return cloneDraftContent(e.saved.content);}
  undoRestore(){const e=this.entry();if(!e?.undo)return null;const value=cloneDraftContent(e.undo);e.undo=null;return value;}
}
if(typeof module!=='undefined')module.exports={LocalDraftState,meaningfulDraft};

if(typeof window!=='undefined')(()=>{
  const state=new LocalDraftState();
  let restoreEpoch=0;
  const get=()=>({question:$('question').value,observations:$('observations').value,task:$('task').value,language:$('language').value,prior_record_id:priorRecordId,
    manual_fault:typeof getManualFaultDraftReference==='function'?getManualFaultDraftReference():typeof getManualFaultReference==='function'?getManualFaultReference():null,
    engineering_fault:typeof getEngineeringFault==='function'?getEngineeringFault():null});
  const scope=()=>{const m=selected();return m?{machine_id:m.machine_id,dataset_id:m.dataset_id||null,source:m.dataset_id?'imported_'+m.provenance:defaultSource}:null;};
  const key=s=>s?JSON.stringify([s.machine_id,s.dataset_id,s.source]):null;
  const meaningful=meaningfulDraft;
  function apply(content){
    if(!content)return;
    const epoch=++restoreEpoch,applyKey=key(scope());
    $('question').value=content.question;$('observations').value=content.observations;
    $('task').value=content.task;$('language').value=content.language;priorRecordId=content.prior_record_id;
    updateTask();$('question-details').open=Boolean(content.question)||content.task==='auto';
    document.querySelector('details.observations').open=Boolean(content.observations);
    // Text is applied synchronously. Late reference responses must never reapply it.
    if(typeof restoreManualFaultReference==='function')Promise.resolve(restoreManualFaultReference(content.manual_fault||null)).catch(()=>{
      if(epoch===restoreEpoch&&applyKey===key(scope()))$('draft-state').textContent='文字已恢复；故障码资料暂未载入，请重新查码并确认。';
    });
    if(typeof restoreEngineeringFault==='function')restoreEngineeringFault(content.engineering_fault||null);
    render();
    $(content.observations?'observations':content.question?'question':'task').focus({preventScroll:true});
  }
  function render(){
    const e=state.entry(),current=get(),blocked=!e||e.loading||e.busy||$('run').disabled;
    $('draft-save').disabled=blocked||!e.loaded||Boolean(e.error)||e.conflict||!meaningful(current)||!state.dirty(current);
    $('draft-restore').disabled=blocked||!e.saved||(e.conflict&&Boolean(e.error))||(!state.dirty(current)&&!e.conflict);
    $('draft-undo').hidden=!e?.undo;$('draft-undo').disabled=blocked;
    $('draft-reload').hidden=!e?.error&&!e?.conflict;$('draft-reload').disabled=blocked;
    const message=$('draft-state');message.dataset.tone=e?.error?'warning':'neutral';
    message.textContent=!e?'选择设备后可保存排查草稿。':e.busy?'正在保存本机草稿…':e.loading?'正在读取此设备的本机草稿…':e.error?e.error:e.conflict?'已读取新版本；请先查看已存内容并恢复，再编辑保存。':
      e.saved?`已存于 ${displayDate(e.saved.saved_at)}${state.dirty(current)?'；当前输入与已存草稿不同。':'；当前输入已保存。'}`:
      meaningful(current)?'尚未保存；刷新或关闭页面会清空当前输入。':'此设备与数据版本尚无已存草稿。';
    const m=selected();$('draft-device').textContent=m?`${m.model} · ${m.serial_number} · ${m.dataset_id?'数据版本 '+m.dataset_id.slice(0,8):'当前来源 '+defaultSource}`:'';
    $('draft-preview').hidden=!e?.saved;
    $('draft-preview-body').textContent=e?.saved?`问题：${e.saved.content.question||'（使用任务默认问题）'}\n\n现场检查记录：${e.saved.content.observations||'（未填写）'}\n\n故障码：${e.saved.content.engineering_fault?`${e.saved.content.engineering_fault.code} · XE55U / ${e.saved.content.engineering_fault.configuration} · ${e.saved.content.engineering_fault.source==='test'?'测试故障':'人工报告'}`:e.saved.content.manual_fault?`${e.saved.content.manual_fault.code} · ${e.saved.content.manual_fault.model} / ${e.saved.content.manual_fault.version}（恢复后需重新确认）`:'（未关联）'}\n\n报告语言：${e.saved.content.language==='zh'?'中文':'English'}${e.saved.content.prior_record_id?'\n已关联原诊断记录及其检查反馈。':''}`:'';
  }
  async function load(){
    const s=scope();if(!s||state.entry()?.busy)return;
    const token=state.beginRead();render();
    const params=new URLSearchParams({machine_id:s.machine_id,source:s.source});if(s.dataset_id)params.set('dataset_id',s.dataset_id);
    try{state.acceptRead(token,(await api('/assistant/draft?'+params)).draft);}
    catch(error){state.failRead(token,error.message);}
    render();
  }
  window.selectLocalDraft=()=>{
    const e=state.select(key(scope()));render();
    if(e&&!e.loaded&&!e.loading&&!e.busy)load();
  };
  window.refreshLocalDraftControls=render;
  for(const id of ['question','observations','task','language']){
    $(id).addEventListener('input',render);$(id).addEventListener('change',render);
  }
  $('draft-save').onclick=async()=>{
    const s=scope(),e=state.entry();if(!s||$('draft-save').disabled||!e.loaded)return;
    const token=state.beginSave(get());render();
    try{state.finishSave(token,(await api('/assistant/draft',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({...s,content:token.content,expected_revision:token.expected_revision})})).draft);}
    catch(error){state.failSave(token,error.message,error.status===409);}
    render();
  };
  $('draft-reload').onclick=load;
  $('draft-restore').onclick=()=>{if(!$('draft-restore').disabled)apply(state.restore(get()));};
  $('draft-undo').onclick=()=>{if(!$('draft-undo').disabled)apply(state.undoRestore());};
  window.selectLocalDraft();
})();
