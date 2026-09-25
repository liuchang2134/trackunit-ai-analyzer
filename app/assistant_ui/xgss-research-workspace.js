/* Device-scoped two-pass research. Credentials stay on the local backend. */
(() => {
  const workspace=document.getElementById('work-view');if(!workspace)return;
  const partsFocus=document.documentElement?.classList?.contains?.('fault-parts-focus')===true;
  const focused=document.documentElement?.classList?.contains?.('competition-focus')===true;
  const host=workspace.querySelector?.('.output')||workspace;
  const el=(tag,text)=>{const e=document.createElement(tag);if(text)e.textContent=text;return e;};
  const disclosure=(title,open=false)=>{const d=el('details');d.open=open;d.className='research-disclosure';d.append(el('summary',title));return d;};
  // Translate implementation vocabulary only in AI prose, never in catalog
  // identifiers or the original manual excerpts used as evidence.
  function readable(text,data){
    let value=String(text||'').replace(/`?fault_coverage\s*=\s*unknown`?/g,'故障记录覆盖范围未知')
      .replace(/`?service_history_status\s*=\s*unknown`?/g,'上次保养记录尚未核实');
    const names={fault_coverage:'故障记录覆盖范围',machine_context:'设备数据快照',quantity:'图示用量',observed_at:'采样时间',
      age_hours:'采样距今小时数',stale_after_24h:'历史采样标记',source_id:'资料引用',manual_excerpt:'手册原文',ai_inspection_suggestion:'AI 检查建议'};
    value=value.replace(/\b(fault_coverage|machine_context|quantity|observed_at|age_hours|stale_after_24h|source_id|manual_excerpt|ai_inspection_suggestion)\b/g,key=>names[key]);
    if(data?.machine_context?.metrics?.fuel_remaining_percent?.value===null)
      value=value.replace(/空燃油余量|燃油余量为空/g,'未采集到有效燃油余量');
    // Only rephrase known model-rule echoes. Do not drop sentences or strip
    // negations: they can be essential inspection/replacement conditions.
    value=value.replace(/(?:也)?不能补造温度、压力(?:、维修周期或实时测量|或维修周期)/g,'温度、压力和维修周期需另行核实')
      .replace(/因此不(?:编造|给出)拆装、带压检测、扭矩或阈值[等类]官方步骤，仅提供保守检查方向/g,'具体维修步骤和参数需查阅适用手册')
      .replace(/不编造拆装步骤、带压检测、扭矩或阈值，仅提供保守检查方向/g,'具体维修步骤和参数需查阅适用手册');
    return value;
  }
  const card=el('section');card.className='card';card.id='xgss-research';
  card.append(el('h2',partsFocus?'故障配件':'AI 设备服务'));
  const faultPicker=el('section');faultPicker.id='fault-parts-picker';faultPicker.hidden=!partsFocus;
  const estimateView=el('section');estimateView.id='fault-parts-estimates';estimateView.hidden=true;
  let estimateHandle=null,estimateKey=null,faultFocusTab='current',faultGroupResearchId=null;
  const modeLabel=el('label','分析方式'),mode=el('select');mode.id='research-analysis-mode';modeLabel.htmlFor=mode.id;
  for(const [value,label] of [['maintenance','AI 工时保养'],['fault','AI 故障排查']]){const option=el('option',label);option.value=value;mode.append(option);}
  const aiBrief=el('p');aiBrief.id='research-ai-brief';aiBrief.className='research-ai-brief';
  const maintenanceView=el('div');maintenanceView.id='research-maintenance-context';maintenanceView.className='research-maintenance-context';
  const identity=el('p');
  const demoGate=el('section');demoGate.id='research-demo-gate';demoGate.hidden=true;
  const demoLive=el('button','关联当前设备');demoLive.type='button';demoLive.className='primary-button';
  demoLive.onclick=()=>window.JilianDataMode?.switchTo('live');
  demoGate.append(el('h3','请关联 Trackunit 设备'),
    el('p','读取当前设备后，按故障码匹配该设备适用的 XGSS 图册和配件。'),demoLive);
  const faultAlert=el('section');faultAlert.id='research-page-fault-banner';faultAlert.hidden=true;
  const resultHero=el('section');resultHero.id='research-result-hero';resultHero.hidden=true;
  resultHero.setAttribute('aria-label','当前 AI 分析结果');
  const vinBox=el('div');vinBox.id='research-vin-repair';vinBox.className='research-vin-repair';vinBox.hidden=true;
  const vinNote=el('p'),vinLabel=el('label','整机 VIN / PIN'),vinInput=el('input'),vinSave=el('button','核对并关联图册');
  vinInput.id='research-vin';vinLabel.htmlFor=vinInput.id;vinInput.maxLength=32;vinInput.placeholder='填写铭牌或设备规格中的整机编号';vinSave.type='button';
  const vinConfirmed=el('input');vinConfirmed.type='checkbox';vinConfirmed.id='research-vin-confirmed';
  const vinConfirmation=el('label');vinConfirmation.htmlFor=vinConfirmed.id;vinConfirmation.append(vinConfirmed,el('span','已核对编号属于当前这台机器'));
  const vinFeedback=el('p');vinFeedback.setAttribute('role','status');
  vinBox.append(el('strong','整机编号待核对'),vinNote,vinLabel,vinInput,vinConfirmation,vinSave,vinFeedback);
  const preliminaryView=el('section');preliminaryView.id='research-preliminary';preliminaryView.className='research-preliminary';preliminaryView.hidden=true;
  const eventLabel=el('label','Trackunit 故障记录'),eventSelect=el('select');eventSelect.id='research-fault-event';eventLabel.htmlFor=eventSelect.id;
  const eventNote=el('p'),eventFacts=el('p'),eventRefresh=el('button','重新读取故障接口');eventNote.id='research-fault-event-note';eventNote.setAttribute('role','status');eventFacts.className='muted research-fault-facts';eventRefresh.type='button';
  const eventPageRead=el('button','读取当前 Events 页故障');eventPageRead.type='button';eventPageRead.id='research-page-fault-read';
  const eventTools=disclosure('故障数据来源');eventTools.append(eventFacts,eventRefresh);
  const symptomLabel=el('label','故障现象'),symptom=el('textarea');symptom.id='research-symptom';symptomLabel.htmlFor=symptom.id;symptom.rows=3;
  symptom.placeholder='补充异常表现、发生工况或已确认的现场现象。';
  const sourceLabel=el('label','现象来源'),source=el('select');source.id='research-symptom-source';sourceLabel.htmlFor=source.id;
  for(const [value,label] of [['simulation','模拟现象'],['operator_report','人工报告 · 待核实'],['user_question','分析问题 · 未确认实车故障']]){const option=el('option',label);option.value=value;source.append(option);}source.value='simulation';
  if(focused)source.value='operator_report';
  const eventSource=el('option','Trackunit 故障事件');eventSource.value='trackunit_event';eventSource.disabled=true;source.append(eventSource);
  const pageSource=el('option','Trackunit 当前页面 · 局部记录');pageSource.value='trackunit_page';pageSource.disabled=true;source.append(pageSource);
  const planStart=el('button','查找备件与维修资料'),analyze=el('button','更新备件与维修建议');planStart.type=analyze.type='button';analyze.disabled=true;
  planStart.id='research-run';if(focused)planStart.textContent='分析故障';
  const replan=el('button','重新生成检索计划');replan.type='button';replan.hidden=true;
  const planView=el('div'),adviceView=el('div'),usedContextView=el('div'),continuationView=el('p');continuationView.className='muted';continuationView.hidden=true;
  if(focused)planView.setAttribute('data-deferred-feature','research-process');
  const unlinkContext=el('button','取消本次关联');unlinkContext.type='button';unlinkContext.hidden=true;
  const resume=el('button','恢复上次资料排查');resume.type='button';resume.setAttribute('data-deferred-feature','history');
  const localEvidence=el('button','查看设备证据');localEvidence.type='button';
  const contextView=el('div');
  const label=el('label','部件检索词'),input=el('input');input.id='research-terms';input.placeholder='例如：冷却系统、散热器、风扇';label.htmlFor=input.id;
  const useAI=el('button','采用当前 AI 检索词'),start=el('button','查找并提取资料'),stop=el('button','停止');
  for(const button of [useAI,start,stop])button.type='button';stop.hidden=true;
  const actions=el('div');actions.className='row research-main-actions';actions.append(planStart,analyze,stop);
  const options=disclosure('更多操作与检索词'),tools=el('div');tools.className='row';tools.append(useAI,start,replan,resume,localEvidence);
  options.append(label,input,tools);
  if(focused){options.setAttribute('data-deferred-feature','legacy-research-tools');analyze.setAttribute('data-deferred-feature','legacy-research-tools');}
  const status=el('p');status.setAttribute('role','status');
  const captureState=el('p');captureState.className='muted';captureState.id='research-capture-state';
  const coverage=el('p');coverage.className='muted';
  const galleryView=el('div'),results=el('div');
  const references=disclosure('人工补充故障码与适用配置');references.id='research-fault-references';
  if(focused)for(const id of ['engineering-fault-panel','fault-reference-panel','manual-fault-linked']){const node=document.getElementById(id);if(node)references.append(node);}
  const inputPanel=disclosure('故障与补充说明',true);inputPanel.id='research-input-panel';
  let inputPanelOutcome;
  if(partsFocus){
    inputPanel.replaceChildren(el('summary','补充故障信息（选填）'),symptomLabel,symptom,references,unlinkContext);
    inputPanel.open=false;inputPanel.className='fault-parts-supplement';
    const refreshTools=el('div');refreshTools.className='fault-parts-refresh';refreshTools.append(eventPageRead,eventTools);
    card.append(identity,demoGate,faultPicker,refreshTools,continuationView,vinBox,inputPanel,actions,status,captureState,
      preliminaryView,resultHero,estimateView,adviceView);
    // Legacy tools remain available to the shared workflow, outside the main UI.
    const deferred=el('div');deferred.hidden=true;deferred.id='fault-parts-deferred';
    deferred.append(modeLabel,mode,aiBrief,maintenanceView,eventLabel,eventSelect,eventNote,sourceLabel,source,
      options,coverage,contextView,usedContextView,planView,results,galleryView);card.append(deferred);
  }else{
    inputPanel.append(modeLabel,mode,aiBrief,maintenanceView,eventLabel,eventSelect,eventPageRead,eventNote,eventTools,
      continuationView,unlinkContext,symptomLabel,symptom,sourceLabel,source,references,actions,captureState,status,options);
    card.append(identity,demoGate,faultAlert,vinBox,resultHero,adviceView,preliminaryView,inputPanel,
      coverage,contextView,usedContextView,planView,results,galleryView);
  }
  if(focused&&host.prepend)host.prepend(card);else host.append(card);
  const handoff=el('button','继续查找备件');handoff.type='button';handoff.id='research-handoff';handoff.className='primary-button';
  document.getElementById('result')?.append(handoff);
  const origin=location.ancestorOrigins?.[0],connection=new URLSearchParams(location.search).get('panel');
  const embedded=window.parent!==window && /^chrome-extension:\/\/[a-p]{32}$/.test(origin||'') && Boolean(connection);
  let available=false,job=null,scope='',generation=0,watchdog=null,controller=null,record=null,recordScope=null,preparing=false;
  let evidenceRequest=0,evidenceBusy=false;
  let catalogIdentity=null,vinTicket=0,vinBusy=false;
  let planDetails=null;
  let preferredTerms=null;
  let imageDialog=null;
  let galleryGeneration=0,entryNote='';
  let activeResearchId=null,activeLookup=0,handoffBusy=false,handoffSeed=null,linkedFaults=null,inputsEdited=false,pendingFaultKey=null;
  let modeChoice=null,modelFailure=null;
  let sensorHandoffScope=null;
  let faultEventId=null,faultEvents=[],pageFaults=[],pageServices=[],pageFault=null,pageObservation=null,pageObservedAt=null,pageSourceUrl='',pageCaptureIssue='',pageReadPending=false,pageReadTimer=null,pageReadTicket=0,apiEventNote='',eventRequest=0,eventBusy=false,emailTicket=0,emailPreview=null;
  let faultState=null,activeResolvedScope=null,automaticFault=null;
  const faultPollInterval=1800000;
  let faultPoll=null,eventLastAttempt=0;
  const continuedPlans=new Set();
  const initialResearchLink=new URLSearchParams(location.search).get('research');
  let researchLinkConsumed=false,pinnedResearchScope=null;
  const key=m=>JSON.stringify([m?.machine_id,m?.dataset_id,m?.serial_number]);
  const currentFaults=()=>linkedFaults||{manual_fault:typeof getManualFaultReference==='function'?getManualFaultReference():null,
    engineering_fault:typeof getEngineeringFault==='function'?getEngineeringFault():null};
  const faultKey=f=>JSON.stringify([f?.manual_fault?[f.manual_fault.code,f.manual_fault.model,f.manual_fault.version,f.manual_fault.applicability_confirmed]:null,
    f?.engineering_fault?[f.engineering_fault.code,f.engineering_fault.model,f.engineering_fault.configuration||'unknown',f.engineering_fault.source]:null]);
  const analysisMode=()=>partsFocus?'fault':modeChoice||(faultEventId||currentFaults()?.manual_fault||currentFaults()?.engineering_fault||symptom.value.trim()?'fault':'maintenance');
  const isHistoricalFault=item=>['CLOSED','RESOLVED','CLEARED'].includes(String(item?.status||'').toUpperCase());
  const selectedHistorical=()=>isHistoricalFault(pageFault)||isHistoricalFault(faultEvents.find(item=>item.event_id===faultEventId))||Boolean(planMatchesInput()&&record?.advice?.analysis_scope==='historical');
  const selectionMatchesFaultTab=()=>!partsFocus||faultFocusTab===(selectedHistorical()?'historical':'current');
  const recordMode=data=>data?.analysis_mode==='maintenance'?'maintenance':'fault';
  const codedSymptom=value=>/\bSPN\s*[:：]?\s*\d+[\s\S]*?\bFMI\s*[:：]?\s*\d+|故障码\s*[:：]?\s*[A-Z][A-Z0-9._-]{1,30}\b/i.test(String(value||''));
  const isFaultResearch=data=>Boolean(data&&recordMode(data)==='fault'&&(data.fault_event_id||data.fault_context?.trackunit_page||data.manual_fault||data.manual_fault_reference||data.engineering_fault||
    ['trackunit_page','operator_report'].includes(data.symptom_source)&&codedSymptom(data.symptom)));
  const selectedFaultReady=()=>Boolean(faultEventId||pageFault||currentFaults()?.manual_fault||currentFaults()?.engineering_fault||
    source.value==='operator_report'&&codedSymptom(symptom.value)||record&&isFaultResearch(record)&&planMatchesInput());
  function destroyEstimates(){estimateHandle?.destroy?.();estimateHandle=null;estimateKey=null;estimateView.replaceChildren();estimateView.hidden=true;}
  function mountEstimates(data,parts){
    const identity=JSON.stringify([data.research_id,data.analysis_revision,data.machine_id,data.dataset_id,data.vin,data.advice.analysis_scope]);
    if(estimateKey===identity&&estimateHandle){estimateView.hidden=false;return;}
    destroyEstimates();if(!parts.length)return;
    const unique=[...new Map(parts.map(part=>[JSON.stringify([part.part_number,part.capture_id||part.source_id]),part])).values()];
    estimateView.hidden=false;estimateKey=identity;
    if(window.JilianPartEstimates?.mount)estimateHandle=window.JilianPartEstimates.mount(estimateView,{researchId:data.research_id,machineId:data.machine_id,vin:data.vin,datasetId:data.dataset_id||null,scope:data.advice.analysis_scope==='historical'?'historical':'current',parts:unique});
    else estimateView.append(el('p','参考估价：待询价'));
  }
  const inputSource=()=>analysisMode()==='maintenance'?'user_question':source.value;
  const defaultMaintenanceQuestion='请结合当前机型与已载入工时，在同机 XGSS 资料中筛选保养件和易损件，说明检查优先级、推荐理由及考虑更换的条件。';
  const recordInput=data=>recordMode(data)==='maintenance'&&data?.symptom===defaultMaintenanceQuestion?'':data?.fault_event_id||data?.fault_context?.trackunit_page?(data.fault_context?.operator_supplement||''):data?.symptom;
  const pageObservationInput=value=>value?Object.fromEntries(['asset_id','source_url','observed_at','description','code','spn','fmi','sa','status','occurred_at','cleared_at','page_event_id'].filter(name=>value[name]!==undefined).map(name=>[name,value[name]])):null;
  function recordFaultLabel(data){
    // Scope the result to its saved input, never to another currently visible card.
    const observation=data?.fault_context?.trackunit_page;
    if(observation)return {label:observation.code||observation.description||'历史故障记录',description:observation.description||''};
    const text=String(data?.symptom||'').replace(/\s+/g,' ').trim();
    const values=name=>[...new Set([...text.matchAll(new RegExp('\\b'+name+'\\s*[:：]?\\s*(\\d{1,7})\\b','gi'))].map(match=>match[1]))];
    const spn=values('SPN'),fmi=values('FMI'),sa=values('SA');
    const multiple=spn.length>1||fmi.length>1||sa.length>1;
    const tuple=!multiple&&spn.length===1&&fmi.length===1?`SPN ${spn[0]} / FMI ${fmi[0]}${sa.length===1?' · SA '+sa[0]:''}`:null;
    const oem=!multiple&&!spn.length&&!fmi.length?text.match(/故障码\s*[:：]?\s*([A-Z][A-Z0-9._-]{1,30})\b/i)?.[1]:null;
    const description=text.match(/(?:^|[；;])\s*描述\s*[:：]\s*([^；;]+)/)?.[1]?.trim();
    return {label:multiple?'已保存的多项故障现象':tuple||oem||'已保存的故障现象',
      description:(description||(!tuple&&!oem?text:'')).slice(0,120)};
  }
  const pageObservationKey=value=>value?JSON.stringify([value.asset_id,value.source_url,value.observed_at,value.description,value.code||'',value.spn??null,value.fmi??null,value.sa??null,value.status||'UNKNOWN',value.occurred_at||'',value.cleared_at||'',value.page_event_id||null]):null;
  const modelInputKey=()=>JSON.stringify([key(selected()),analysisMode(),inputSource(),symptom.value.trim(),
    faultEventId,pageObservationKey(pageObservation),faultKey(currentFaults()),handoffSeed?.source_report_id||null]);
  const planMatchesInput=()=>Boolean(record?.plan&&recordScope===key(selected())&&recordInput(record)===symptom.value.trim()&&record.symptom_source===inputSource()&&recordMode(record)===analysisMode()&&
    (record.source_report_id||null)===(handoffSeed?.source_report_id||null)&&(record.fault_event_id||null)===faultEventId&&faultKey(record)===faultKey(currentFaults())&&
    (!record?.fault_context?.trackunit_page||pageObservationKey(record.fault_context.trackunit_page)===pageObservationKey(pageObservation))&&
    (!activeResearchId||record.research_id===activeResearchId));
  // The extension marks the currently displayed, device-bound AI plan. Never
  // fall back to an older report after its input or selected fault changes.
  window.currentXGSSResearchSearchSource=()=>{
    if(!record)return null;
    const m=selected();
    if(!m||record.machine_id!==m.machine_id||(record.dataset_id||null)!==(m.dataset_id||null)||
      record.vin!==m.serial_number||!planMatchesInput()||!selectionMatchesFaultTab())
      return {component_hypotheses:[],has_report:false};
    return {has_report:true,engineering_fault:{code:record.catalog_fault_code||record.engineering_fault?.code||record.manual_fault?.code||null},
      component_hypotheses:(Array.isArray(record.plan.directions)?record.plan.directions:[]).map(direction=>({
        component:direction.component,rationale:direction.reason,
        search_terms:Array.isArray(direction.search_terms)?direction.search_terms.slice():[]}))};
  };
  window.currentXGSSResearchProgress=()=>{
    const current=record&&recordScope===key(selected());
    if(!current&&!symptom.value.trim()&&!controller&&!job&&!preparing)return null;
    const diagnosed=planMatchesInput();
    return {diagnosed,verified:Boolean(diagnosed&&record.pages?.length&&record.advice&&
      Number.isInteger(record.revision)&&record.analysis_revision===record.revision)};
  };
  const refreshFlow=()=>{
    if(typeof updateFlowTrack==='function')updateFlowTrack();
    const m=selected();
    if(m)post({type:'jilian:research-active',asset_id:m.machine_id,dataset_id:m.dataset_id||null,
      research_id:planMatchesInput()&&record.research_id===activeResearchId?activeResearchId:null});
  };
  const changedContextNote='现象或来源已更改，请重新查找备件与维修资料。';
  const post=data=>{if(embedded)window.parent.postMessage({protocol:1,connection_id:connection,...data},origin);};
  const matches=()=>job && job.scope===key(selected()) && job.asset===PlatformContext.asset(location.hash);
  const realDevice=m=>Boolean(m&&(m.dataset_id?m.provenance==='user_supplied':defaultSource==='trackunit_cache'));
  function captureAvailability(){captureState.textContent=!realDevice(selected())?'选择真实设备后可读取图册。':
    available?'XGSS 直读已启用，插件可作为备用读取。':'可直接读取 XGSS 图册，无需连接 Chrome 插件。';}
  function touch(){clearTimeout(watchdog);watchdog=setTimeout(()=>cancel('插件未继续回应，已停止等待；已提取资料仍保留。'),25000);}
  function compactFaultPicker(busy){
    faultPicker.hidden=false;faultPicker.replaceChildren();
    const entries=[...faultEvents.map(item=>({item,source:'API',choose:()=>selectFaultEvent(item),selected:item.event_id===faultEventId})),
      ...pageFaults.map(item=>({item,source:'页面观察',choose:()=>selectPageFault(item),selected:item===pageFault}))];
    if(pageFault&&!pageFaults.includes(pageFault))entries.push({item:pageFault,source:'已保存页面观察',choose:()=>selectPageFault(pageFault),selected:true});
    if(record&&isFaultResearch(record)&&planMatchesInput()&&!entries.some(entry=>entry.selected)){
      const saved=record.fault_context?.trackunit_event||record.fault_context?.trackunit_page||{};
      entries.push({item:{...saved,code:record.manual_fault?.code||record.manual_fault_reference?.code||record.engineering_fault?.code||recordFaultLabel(record).label,description:recordFaultLabel(record).description,
        status:record.advice?.analysis_scope==='historical'?'CLOSED':saved.status||'UNKNOWN'},source:record.symptom_source==='trackunit_event'?'API 记录':record.symptom_source==='trackunit_page'?'已保存页面观察':'人工补充',selected:true,choose:()=>{}});
    }
    const current=entries.filter(entry=>String(entry.item.status||'').toUpperCase()==='OPEN'),historical=entries.filter(entry=>isHistoricalFault(entry.item));
    const unknown=entries.filter(entry=>!current.includes(entry)&&!historical.includes(entry));
    const tabs=el('div');tabs.className='fault-parts-tabs';tabs.setAttribute('role','tablist');tabs.setAttribute('aria-label','故障记录范围');
    for(const [value,label,list] of [['current','当前故障',current],['historical','历史故障',historical]]){
      const button=el('button',`${label} ${list.length}`);button.type='button';button.disabled=busy;button.setAttribute('role','tab');
      button.setAttribute('aria-selected',String(faultFocusTab===value));button.onclick=()=>{faultFocusTab=value;status.textContent='';controls(busy);};tabs.append(button);
    }
    faultPicker.append(tabs);const list=el('div');list.className='fault-parts-faults';list.setAttribute('role','tabpanel');faultPicker.append(list);
    const appendEntry=(target,entry)=>{
      const item=entry.item,button=el('button');button.type='button';button.className='fault-parts-fault';button.disabled=busy;
      button.setAttribute('aria-pressed',String(entry.selected));
      const title=item.code||(/transmission.*abnormal update rate/i.test(item.description||'')?'变速箱通信异常':item.description||'故障码未显示');
      button.append(el('strong',`${title}${item.sa!==null&&item.sa!==undefined?' · SA '+item.sa:''}`));
      if(item.description&&item.description!==title)button.append(el('span',item.description));
      const state=isHistoricalFault(item)?'已解除':String(item.status||'').toUpperCase()==='OPEN'?'未解除':'状态待核实';
      const time=item.displayed_at||item.occurred_at||item.event_time;
      const meta=el('small',`${state} · ${entry.source}${time?' · '+time:''}`);button.append(meta);
      button.onclick=()=>{entry.choose();renderEventOptions();if(!busy)planStart.focus?.();};target.append(button);
    };
    const shown=faultFocusTab==='historical'?historical:current;
    for(const entry of shown)appendEntry(list,entry);
    if(!shown.length)list.append(el('p',faultFocusTab==='historical'?'尚未读取已解除的历史故障。':'尚未读取状态明确的未解除故障。'));
    if(unknown.length&&faultFocusTab==='current'){
      const details=disclosure(`状态待核实 · ${unknown.length} 条`,unknown.some(entry=>entry.selected));details.className='fault-parts-unknown';
      for(const entry of unknown)appendEntry(details,entry);faultPicker.append(details);
    }
    if(!entries.length)faultPicker.append(el('p','在 Trackunit Events 页读取故障，或在下方补充明确的故障码。'));
  }
  function compactControls(busy,real,changed){
    compactFaultPicker(busy);
    const eligible=record&&isFaultResearch(record),matching=eligible&&planMatchesInput();
    const valid=matching&&record.advice&&record.analysis_revision===record.revision;
    const resultInGroup=Boolean(valid&&faultFocusTab===(record.advice.analysis_scope==='historical'?'historical':'current'));
    for(const node of [modeLabel,mode,aiBrief,maintenanceView,eventLabel,eventSelect,eventNote,sourceLabel,source,analyze,
      faultAlert,options,coverage,contextView,usedContextView,planView,results,galleryView,handoff])node.hidden=true;
    inputPanel.hidden=!real;
    // Keep manual context available without opening the form after each result.
    inputPanel.querySelector?.('summary')?.replaceChildren(document.createTextNode('补充故障信息（选填）'));
    symptomLabel.textContent='故障码或补充现象';symptom.placeholder='例如：SPN 444 / FMI 1；或补充已选择故障的发生工况。';
    references.hidden=false;eventTools.hidden=false;eventFacts.hidden=false;
    eventPageRead.textContent='刷新页面故障';eventRefresh.textContent='刷新接口故障';
    eventPageRead.hidden=!embedded||!real;eventPageRead.className=eventRefresh.className='fault-parts-refresh-button';
    eventTools.open=false;
    eventFacts.textContent=pageCaptureIssue||`页面观察与 API 记录分别标注；仅覆盖已读取的故障。${apiEventNote?' '+apiEventNote:''}`;
    const pending=matching&&!hasComponentSources(record);
    planStart.hidden=false;planStart.className='primary-button';
    planStart.disabled=busy||!real||!selectedFaultReady()||!selectionMatchesFaultTab();
    planStart.textContent=busy?'正在生成配件推荐…':pending?'继续读取 XGSS 并推荐配件':valid?'更新配件推荐':'生成配件推荐';
    resultHero.hidden=!resultInGroup;adviceView.hidden=!resultInGroup;
    if(changed||!valid){destroyEstimates();}
    else estimateView.hidden=!resultInGroup||!estimateKey;
    if(!eligible)preliminaryView.hidden=true;
    captureState.hidden=true;
    if(!eligible&&!busy&&!selectedFaultReady())status.textContent='选择故障后，查看对应配件、图示和参考估价。';
    else if(!busy&&!selectionMatchesFaultTab())status.textContent='请选择本组故障，生成对应配件推荐。';
  }
  function compactPartGroups(data,entries){
    // Repeated captures are evidence, not extra units to buy. Keep each source's
    // conditions, and bind the displayed figure/reference to that exact source.
    const groups=new Map(),normalize=value=>String(value||'').trim().replace(/\s+/g,'').toUpperCase();
    for(const entry of entries){
      const {part}=entry;
      const id=JSON.stringify([normalize(part.part_number),normalize(part.name)]);
      const existing=groups.get(id);
      const diagram=part.capture_id?diagramsFor(data,part.capture_id)[0]:null;
      if(!existing){groups.set(id,{...entry,diagram,sources:[entry]});continue;}
      existing.sources.push(entry);
      if(!existing.diagram&&diagram){existing.part=part;existing.diagram=diagram;existing.kind=entry.kind;}
    }
    return [...groups.values()];
  }
  function showCompactAdvice(data){
    const historical=data.advice.analysis_scope==='historical';
    const inspectionOnly=part=>part?.evidence_level==='inspection_only'||part?.status==='inspection_only';
    const entries=historical?(data.advice.historical_candidates||[]).map(part=>({part,kind:'historical'})):
      [...(data.advice.parts||[]).map(part=>({part,kind:inspectionOnly(part)?'inspection':'candidate'})),
        ...(data.advice.inspection_targets||[]).map(part=>({part,kind:'inspection'}))];
    const unique=compactPartGroups(data,entries);
    const overview=el('div');overview.className='fault-parts-result-title';
    const sourceName=data.symptom_source==='trackunit_event'?'API 记录':data.symptom_source==='trackunit_page'?'页面观察':'人工补充';
    const faultLabel=data.manual_fault?.code||data.manual_fault_reference?.code||data.engineering_fault?.code||recordFaultLabel(data).label;
    overview.append(el('h3',`${historical?'历史故障配件参考':'故障相关配件'} · ${unique.length} 项`),
      el('strong',`${historical?'历史 · 已解除':String((data.fault_context?.trackunit_event||data.fault_context?.trackunit_page)?.status||'').toUpperCase()==='OPEN'?'当前 · 未解除':sourceName+' · 状态待核实'} · ${faultLabel}`),
      el('p',historical?'历史故障已解除，供复发备库参考。':'按故障相关性推荐；核查适配与更换条件后再决定备件。'));
    resultHero.append(overview);resultHero.hidden=false;
    const list=el('div');list.className='fault-parts-grid';adviceView.append(list);
    for(const {part,kind,diagram,sources} of unique){
      const item=el('article');item.className='fault-parts-card';
      if(diagram)item.append(diagramFigure(data,diagram,part));
      else{const placeholder=el('div','该分类尚未采集图示');placeholder.className='fault-parts-image-empty';item.append(placeholder);}
      const body=el('div');body.className='fault-parts-card-body';
      body.append(el('h4',part.name));const number=el('p',part.part_number);number.className='research-part-number';body.append(number);
      const label=el('small',kind==='historical'?'历史备库参考':kind==='inspection'?'待核查适配与原因':'条件性备件');label.className='fault-parts-kind';body.append(label);
      const reason=el('p',readable(part.reason,data));reason.className='fault-parts-reason';body.append(reason);
      const details=disclosure('查看依据');details.className='fault-parts-basis';
      details.append(el('p',readable(part.reason,data)),el('strong',kind==='historical'?'备库条件':kind==='inspection'?'核查条件':'更换条件'),
        el('p',readable(kind==='historical'?(part.preparation_condition||part.replacement_condition):part.replacement_condition,data)));
      details.append(el('p',`XGSS 来源：${part.page_title||part.assembly_path?.join(' / ')||'同 VIN 图册'}${part.figure_ref?' · 图中序号 '+part.figure_ref:''}${part.captured_at?' · '+part.captured_at:''}`));
      const seenSources=new Set([part.source_id||part.capture_id]);
      for(const entry of sources){
        const other=entry.part,id=other.source_id||other.capture_id;
        if(seenSources.has(id))continue;seenSources.add(id);
        details.append(el('strong','补充图册依据'),el('p',readable(other.reason,data)),
          el('p',readable(other.preparation_condition||other.replacement_condition,data)),
          el('p',`XGSS 来源：${other.assembly_path?.join(' / ')||other.page_title||'同 VIN 图册'}${other.figure_ref?' · 图中序号 '+other.figure_ref:''}${other.captured_at?' · '+other.captured_at:''}`));
      }
      body.append(details);item.append(body);list.append(item);
    }
    if(!unique.length)adviceView.append(el('p','暂未匹配到可核对料号的配件，补充故障信息或继续读取 XGSS 图册。'));
    mountEstimates(data,unique.map(entry=>({...entry.part,evidence_level:entry.part.evidence_level||(entry.kind==='historical'?'historical_reference':entry.kind==='inspection'?'inspection_only':'conditional_candidate')})));
  }
  function controls(busy){
    busy=busy||handoffBusy||vinBusy;
    vinInput.disabled=vinConfirmed.disabled=vinSave.disabled=busy;
    const real=realDevice(selected());
    const syntheticDemo=!real&&defaultSource==='demo';
    demoGate.hidden=!syntheticDemo;
    inputPanel.hidden=syntheticDemo;
    if(syntheticDemo){
      for(const node of [faultAlert,vinBox,resultHero,modeLabel,mode,aiBrief,maintenanceView,eventLabel,eventSelect,eventPageRead,eventNote,eventTools,continuationView,unlinkContext,symptomLabel,symptom,sourceLabel,source,references,actions,captureState,status,options,coverage,contextView,preliminaryView,adviceView,galleryView,usedContextView,planView,results])node.hidden=true;
      refreshFlow();
      return;
    }
    const changed=Boolean(record?.plan&&!planMatchesInput());
    renderPageFaultBanner();
    if(changed){closeImage();if(partsFocus)destroyEstimates();}
    planView.hidden=adviceView.hidden=usedContextView.hidden=changed;
    // A new symptom invalidates the association between the previous XGSS
    // captures and this investigation, even though the raw record is retained.
    galleryView.hidden=results.hidden=coverage.hidden=changed;
    resultHero.hidden=changed||!record?.advice||record.analysis_revision!==record.revision;
    start.disabled=busy||!real;planStart.disabled=busy||!real;analyze.disabled=busy||!planMatchesInput()||!record?.pages?.length;
    analyze.hidden=!record?.plan||!record?.pages?.length||Boolean(record.advice&&record.analysis_revision===record.revision);
    replan.hidden=!record?.plan;replan.disabled=busy||!real;
    handoff.disabled=busy||!real;
    input.disabled=symptom.disabled=source.disabled=useAI.disabled=busy;stop.hidden=!busy;
    eventSelect.disabled=busy||eventBusy;eventRefresh.disabled=busy||eventBusy||!real;
    eventPageRead.hidden=!embedded||!real;
    eventPageRead.textContent=pageObservedAt?'刷新当前页故障与历史记录':'读取当前 Events 页故障';
    eventPageRead.disabled=busy||pageReadPending;
    source.disabled=busy||Boolean(faultEventId)||Boolean(pageFault);
    const maintenance=analysisMode()==='maintenance';mode.value=analysisMode();mode.disabled=busy;
    for(const node of [eventLabel,eventSelect,eventNote,eventFacts,eventTools,references,sourceLabel,source])node.hidden=maintenance;
    // A saved maintenance result must not conceal newly observed faults on the
    // same Trackunit Events page. Selecting one enters fault analysis explicitly.
    if(maintenance&&(pageFaults.length||pageServices.length||pageCaptureIssue)){
      eventNote.hidden=false;
      if(pageFaults.length)eventLabel.hidden=eventSelect.hidden=false;
    }
    if(maintenance&&faultState?.auto_sync?.status==='paused'){
      eventNote.hidden=eventFacts.hidden=eventTools.hidden=false;
    }
    symptomLabel.textContent=maintenance?'补充保养问题（选填）':'故障现象';
    symptom.placeholder=maintenance?'如有已知保养记录或需要关注的部件，可在此补充。':'补充异常表现、发生工况或已确认的现场现象。';
    aiBrief.textContent=maintenance?'AI 结合设备工时检索 XGSS，筛选保养件与易损件，并解释推荐原因。':'AI 结合故障与工况检索 XGSS，分析维修方向并核对备件料号。';
    maintenanceView.hidden=!maintenance||changed;
    if(focused&&!partsFocus){
      const currentAdvice=planMatchesInput()&&record?.advice&&record.analysis_revision===record.revision;
      const pendingSources=planMatchesInput()&&!record?.advice&&!hasComponentSources(record);
      const readyForAdvice=planMatchesInput()&&!record?.advice_error&&hasComponentSources(record)&&!currentAdvice;
      const outcome=currentAdvice?record.research_id+'|'+record.analysis_revision:null;
      if(inputPanelOutcome!==outcome){inputPanel.open=!currentAdvice;inputPanelOutcome=outcome;}
      inputPanel.querySelector?.('summary')?.replaceChildren(document.createTextNode(currentAdvice?'调整故障与重新分析':'选择故障并推荐备件'));
      planStart.textContent=busy?'正在查询与分析…':currentAdvice?'更新备件建议':
        readyForAdvice?'生成备件与维修建议':
        pendingSources?'查询 XGSS 并推荐备件':
        !embedded?'分析故障并查找备件':maintenance?'AI 推荐保养与易损件':'分析故障并推荐备件';
      if(!busy&&!maintenance&&selectedHistorical())planStart.textContent='历史故障备件参考';
      planStart.hidden=false;
      captureState.hidden=available;
    }
    else{planStart.hidden=false;planStart.textContent=busy?'AI 分析中…':'查找备件与维修资料';}
    resume.disabled=busy||!real;
    localEvidence.disabled=busy||evidenceBusy||!real;captureAvailability();
    unlinkContext.disabled=busy;
    unlinkContext.hidden=continuationView.hidden;
    showPreliminary();if(partsFocus)compactControls(busy,real,changed);
    if(modelFailure&&modelFailure.inputKey!==modelInputKey())modelFailure=null;
    if(!busy&&modelFailure&&(!partsFocus||selectionMatchesFaultTab())){
      planStart.hidden=false;planStart.textContent=modelFailure.phase==='plan'?'重试配件推荐':'重试配件分析';
    }
    refreshFlow();
  }
  function cancel(message){automaticFault=null;generation++;preparing=false;handoffBusy=false;pendingFaultKey=null;controller?.abort();controller=null;if(job)post({type:'jilian:research-cancel',request_id:job.id});job=null;clearTimeout(watchdog);controls(false);status.textContent=message;}
  window.syncXGSSResearch=()=>{
    const m=selected(),next=key(m);
    if(scope!==next){if(partsFocus){destroyEstimates();faultFocusTab='current';faultGroupResearchId=null;}sensorHandoffScope=null;pinnedResearchScope=null;faultState=null;activeResolvedScope=null;clearTimeout(faultPoll);faultPoll=null;eventLastAttempt=0;}
    if(job&&!matches()){cancel('设备已切换，资料收集已停止。');results.replaceChildren();}
    if(scope!==next){catalogIdentity=null;vinTicket++;vinBusy=false;vinInput.value='';vinConfirmed.checked=false;vinFeedback.textContent='';vinBox.hidden=true;preliminaryView.replaceChildren();preliminaryView.hidden=true;closeImage();galleryGeneration++;galleryView.replaceChildren();scope=next;record=null;recordScope=null;preferredTerms=null;activeResearchId=null;activeLookup++;handoffBusy=false;handoffSeed=null;linkedFaults=null;inputsEdited=false;modeChoice=null;faultEventId=null;faultEvents=[];pageFaults=[];pageServices=[];pageFault=null;pageObservation=null;pageObservedAt=null;pageSourceUrl='';pageCaptureIssue='';window.syncVisibleTrackunitEvents?.(null);clearTimeout(pageReadTimer);pageReadTimer=null;pageReadPending=false;pageReadTicket++;apiEventNote='';eventRequest++;eventBusy=false;emailTicket++;emailPreview=null;continuationView.hidden=true;evidenceRequest++;evidenceBusy=false;contextView.replaceChildren();maintenanceView.replaceChildren();usedContextView.replaceChildren();resultHero.replaceChildren();resultHero.hidden=true;symptom.value='';source.value=focused?'operator_report':'simulation';cancel('');results.replaceChildren();planView.replaceChildren();adviceView.replaceChildren();input.value='';coverage.textContent='';loadDeviceDiagrams(m,galleryGeneration);loadActiveResearch();loadFaultEvents();loadCatalogIdentity(m);}
    identity.textContent=m?`${typeof displayMachineModel==='function'?displayMachineModel(m.model):m.model} · ${m.serial_number}`:'请选择设备';
    const risk=document.getElementById('risk-device');if(risk)risk.textContent=m?`当前设备：${m.model} · ${m.serial_number}。尚未发布此设备的风险时间窗口。`:'请先选择设备。';
    const real=realDevice(m);captureAvailability();
    start.disabled=Boolean(job)||Boolean(controller)||preparing||!real;planStart.disabled=Boolean(job)||Boolean(controller)||preparing||!real;
    localEvidence.disabled=Boolean(job)||Boolean(controller)||preparing||evidenceBusy||!real;
    if(!job&&!controller&&!preparing&&record?.plan&&!planMatchesInput())status.textContent=changedContextNote;
    controls(Boolean(job)||Boolean(controller)||preparing);
  };
  const identityBody=m=>({machine_id:m.machine_id,dataset_id:m.dataset_id||null,vin:m.serial_number});
  function suspectIdentifier(m){
    return Boolean(m&&(!/^[A-Z0-9]{8,32}$/.test(m.serial_number||'')||/^\d{1,16}$/.test(m.serial_number||'')&&m.serial_number===m.equipment_id));
  }
  function needsVin(){return catalogIdentity?.needs_verification===true;}
  function showVinRepair(message){
    vinBox.hidden=false;vinNote.textContent=message||'请核对当前机器的整机编号，再查找适配图册。';
  }
  function showPreliminary(){
    preliminaryView.replaceChildren();preliminaryView.hidden=true;
    if(!record?.plan||recordScope!==key(selected())||!planMatchesInput()||record.advice||hasComponentSources(record)||(!focused&&!needsVin()))return;
    preliminaryView.hidden=false;
    if(partsFocus){
      preliminaryView.append(el('p',needsVin()?'核对整机 VIN 后，继续读取本机 XGSS 图册。':'AI 已确定检索方向。点击“继续读取 XGSS 并推荐配件”取得图示与料号。'));
      return;
    }
    preliminaryView.append(el('h3','等待同 VIN XGSS 图册'),
      el('p','AI 已生成检索方向，但尚未读取该设备适用的零件或手册；目前不能推荐具体料号或维修步骤。'));
    if(needsVin())preliminaryView.append(el('p','先核对上方整机 VIN / PIN，再继续查找图册。'));
    else{
      const continueButton=el('button','继续读取 XGSS 并生成备件建议');continueButton.type='button';
      continueButton.className='primary-button';continueButton.onclick=()=>collect(record);
      preliminaryView.append(continueButton);
    }
    const directions=disclosure(recordMode(record)==='maintenance'?'AI 初步保养方向':'AI 初步排查方向');
    directions.append(el('p',readable(record.plan.summary,record)));
    for(const d of record.plan.directions){const item=el('article');item.append(el('strong',d.component),el('p',readable(d.reason,record)));directions.append(item);}
    preliminaryView.append(directions);
  }
  function continueActivePlan(){
    if(partsFocus||!focused||!embedded||!available||!realDevice(selected())||needsVin()||controller||job||preparing||
      !record?.plan||record?.pages?.length||record.advice||!planMatchesInput()||continuedPlans.has(record.research_id))return;
    continuedPlans.add(record.research_id);
    status.textContent='正在连接同 VIN XGSS 图册，查找故障相关备件…';
    void collect(record,{analyzeAfter:false});
  }
  async function selectCorrectedDataset(m,datasetId,draft=null){
    if(!/^[a-f0-9]{64}$/.test(datasetId||'')||typeof refresh!=='function'||key(m)!==key(selected()))return false;
    const originalScope=key(m);
    await refresh();
    const current=selected();
    if(current?.machine_id!==m.machine_id||typeof machines==='undefined'||
      (key(current)!==originalScope&&current.dataset_id!==datasetId))return false;
    const replacement=machines.find(row=>row.machine_id===m.machine_id&&row.dataset_id===datasetId&&row.provenance==='user_supplied');
    if(!replacement)return false;
    $('machine').value=replacement.selection_id;selectMachine();
    if(draft){symptom.value=draft.symptom;source.value=draft.source;modeChoice=draft.mode;inputsEdited=true;controls(false);}
    return true;
  }
  async function loadCatalogIdentity(m){
    if(!realDevice(m)||!suspectIdentifier(m))return;
    const mine=++vinTicket,machineScope=key(m);
    catalogIdentity={needs_verification:true};
    showVinRepair(`当前读到设备编号 ${m.serial_number}，尚未核实整机 VIN/PIN。AI 可先分析现象，具体备件需关联本机图册。`);showPreliminary();
    try{
      const response=await fetch('/assistant/xgss/identity',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(identityBody(m))});
      if(!response.ok)return;
      const data=await response.json();
      if(mine!==vinTicket||machineScope!==key(selected())||data.machine_id!==m.machine_id||data.dataset_id!==(m.dataset_id||null)||data.vin!==m.serial_number)return;
      catalogIdentity=data;
      if(data.replacement_dataset_id){
        if(controller||job||preparing||vinBusy)return;
        await selectCorrectedDataset(m,data.replacement_dataset_id,{symptom:symptom.value,source:source.value,mode:analysisMode()});return;
      }
      vinBox.hidden=!data.needs_verification;if(data.needs_verification)showVinRepair(data.message);showPreliminary();
    }catch{/* Keep the visible identity check when the local status cannot be read. */}
  }
  vinSave.onclick=async()=>{
    const m=selected();if(!m||controller||job||preparing||vinBusy)return;
    const newVin=vinInput.value.trim().toUpperCase();
    if(!/^[A-Z0-9]{8,32}$/.test(newVin)){vinFeedback.textContent='请输入 8–32 位字母或数字组成的整机编号。';return;}
    if(!vinConfirmed.checked){vinFeedback.textContent='请先核对该编号属于当前机器。';return;}
    const mine=++vinTicket,machineScope=key(m),draft={symptom:symptom.value,source:source.value,mode:analysisMode()};
    vinBusy=true;controls(true);vinFeedback.textContent='正在核对 XGSS 图册…';
    try{
      const result=await api('/assistant/xgss/identity/correct',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({machine_id:m.machine_id,dataset_id:m.dataset_id||null,current_vin:m.serial_number,new_vin:newVin,confirmed:true})});
      if(mine!==vinTicket||machineScope!==key(selected()))return;
      if(result.machine?.machine_id!==m.machine_id||result.machine?.serial_number!==newVin)throw new Error('返回设备身份不一致，未切换。');
      vinBusy=false;
      const switched=await selectCorrectedDataset(m,result.dataset_id,draft);
      if(!switched){vinFeedback.textContent='编号已保存；重新选择当前设备后继续。';return;}
      updateResearchLink(null);status.textContent='整机编号已核对，原工时与故障现象已保留。点击 AI 分析继续查找本机资料。';
    }catch(error){if(mine===vinTicket&&machineScope===key(selected()))vinFeedback.textContent=error.message;}
    finally{if(mine===vinTicket){vinBusy=false;controls(false);}}
  };
  function rememberContext(data){
    modeChoice=recordMode(data);mode.value=modeChoice;
    if(partsFocus&&data.research_id&&data.research_id!==faultGroupResearchId){
      faultFocusTab=data.advice?.analysis_scope==='historical'||isHistoricalFault(data.fault_context?.trackunit_page)||isHistoricalFault(data.fault_context?.trackunit_event)?'historical':'current';
      faultGroupResearchId=data.research_id;
    }
    handoffSeed=data.source_report_id?{source_report_id:data.source_report_id,symptom:data.symptom,symptom_source:data.symptom_source}:null;
    linkedFaults={manual_fault:data.manual_fault||null,engineering_fault:data.engineering_fault||null};
    faultEventId=data.fault_event_id||null;
    pageObservation=pageObservationInput(data.fault_context?.trackunit_page);
    if(pageObservation)pageFault={...pageObservation,displayed_at:pageObservation.occurred_at||'',code:pageObservation.code||null};
    else if(data.symptom_source!=='trackunit_page')pageFault=null;
    renderEventOptions();
    const code=linkedFaults.manual_fault?.code||linkedFaults.engineering_fault?.code;
    continuationView.textContent=(handoffSeed?'已沿用上一步的原始问题与分析依据。':'')+(code?' 已关联故障码 '+code+'。':'')+(faultEventId?' 已关联 Trackunit 故障事件。':'')+(pageObservation?`${isHistoricalFault(pageObservation)?'历史 · 已解除':'页面观察'} · ${pageObservation.description} · ${pageObservation.occurred_at||'时间待核实'}`:'');
    continuationView.hidden=!continuationView.textContent;
    unlinkContext.hidden=continuationView.hidden;
  }
  unlinkContext.onclick=()=>{
    if(controller||job||preparing||handoffBusy)return;
    automaticFault=null;sensorHandoffScope=null;
    handoffSeed=null;linkedFaults={manual_fault:null,engineering_fault:null};faultEventId=null;pageFault=null;pageObservation=null;renderEventOptions();if(['trackunit_event','trackunit_page'].includes(source.value))source.value='operator_report';inputsEdited=true;activeLookup++;emailTicket++;emailPreview=null;
    continuationView.hidden=unlinkContext.hidden=true;controls(false);status.textContent='已取消带入的分析与故障关联，原始问题仍保留。';
  };
  window.syncXGSSResearchFaults=()=>{
    if(scope!==key(selected()))return;
    sensorHandoffScope=null;
    const next={manual_fault:typeof getManualFaultReference==='function'?getManualFaultReference():null,
      engineering_fault:typeof getEngineeringFault==='function'?getEngineeringFault():null};
    if(faultKey(next)===(pendingFaultKey||faultKey(linkedFaults)))return;
    automaticFault=null;
    if(controller||job||preparing||handoffBusy)cancel('故障关联已改变，请重新查找资料。');
    modeChoice='fault';faultEventId=null;pageFault=null;pageObservation=null;if(['trackunit_event','trackunit_page'].includes(source.value))source.value='operator_report';
    sensorHandoffScope=null;handoffSeed=null;linkedFaults=next;inputsEdited=true;activeLookup++;
    rememberContext({...next});controls(false);
  };
  window.focusXGSSResearch=(code='')=>{
    modeChoice='fault';
    if(typeof setView==='function')setView('work',{reason:'user'});
    if(code&&!symptom.value.trim()){symptom.value=`分析故障码 ${code}，核对可能原因、维修方向和适用备件。`;source.value='user_question';inputsEdited=true;activeLookup++;}
    window.syncXGSSResearchFaults();inputPanel.open=true;card.scrollIntoView?.({block:'start',behavior:'smooth'});symptom.focus?.({preventScroll:true});
  };
  function validPageSourceUrl(value,asset){
    try{const url=new URL(value);return url.protocol==='https:'&&['new.manager.trackunit.com','manager.trackunit.com'].includes(url.hostname)&&!url.port&&!url.username&&!url.password&&url.pathname.replace(/\/$/,'')===`/assets/${asset}/events`?url.origin+url.pathname:'';}catch{return ''; }
  }
  function renderEventOptions(){
    eventSelect.replaceChildren();const none=el('option','选择故障事件，或补充人工现象');none.value='';eventSelect.append(none);
    for(const item of faultEvents){const option=el('option',`${item.code||'未提供故障码'} · ${item.occurred_at||item.event_time||'时间待核实'} · ${isHistoricalFault(item)?'历史 · 已解除':item.status||'状态未核验'}`);option.value=item.event_id;eventSelect.append(option);}
    for(const [index,item] of pageFaults.entries()){const option=el('option',`${isHistoricalFault(item)?'历史 · 已解除':'页面记录'} · ${item.code||item.description||'未显示故障码'} · ${item.displayed_at||'时间待核实'}`);option.value='page:'+index;eventSelect.append(option);}
    if(faultEventId&&!faultEvents.some(e=>e.event_id===faultEventId)){const option=el('option','当前处理已保存的 Trackunit 故障事件');option.value=faultEventId;eventSelect.append(option);}
    if(pageFault&&!pageFaults.includes(pageFault)){const option=el('option',`${isHistoricalFault(pageFault)?'历史 · 已解除':'已保存页面记录'} · ${pageFault.code||pageFault.description||'故障记录'}`);option.value='page:saved';eventSelect.append(option);}
    eventSelect.value=faultEventId||(pageFault?(pageFaults.includes(pageFault)?'page:'+pageFaults.indexOf(pageFault):'page:saved'):'');
    if(eventSelect.value==='page:-1')eventSelect.value='';
  }
  function pageFaultNote(){return [pageObservedAt?`Trackunit 当前页：${pageFaults.length} 条故障、${pageServices.length} 条保养提醒；含 ${pageFaults.filter(isHistoricalFault).length} 条已解除历史故障，仅覆盖已显示记录。`:'',
    pageFault&&(!record||!planMatchesInput())?'已带入当前页故障；页面记录尚未由故障 API 核验。点击 AI 分析故障继续。':'',pageCaptureIssue].filter(Boolean).join(' ');}
  const pageFaultKey=item=>JSON.stringify([item?.code,item?.spn,item?.fmi,item?.sa,item?.description,item?.displayed_at,item?.status,item?.page_event_id]);
  function showFaultSources(){eventNote.textContent=[apiEventNote,pageFaultNote()].filter(Boolean).join(' ');}
  function selectPageFault(item){
    if(!item)return;
    if(partsFocus){destroyEstimates();faultFocusTab=isHistoricalFault(item)?'historical':'current';}
    automaticFault=null;if(controller||job||preparing)cancel('故障记录已改变，原分析已停止。');
    pageFault=item;faultEventId=null;
    pageObservation=pageSourceUrl?{asset_id:selected().machine_id,source_url:pageSourceUrl,observed_at:pageObservedAt,description:item.description||'',code:item.code||'',spn:item.spn??null,fmi:item.fmi??null,sa:item.sa??null,status:item.status||'UNKNOWN',occurred_at:item.displayed_at||'',cleared_at:item.cleared_at||'',page_event_id:item.page_event_id||null}:null;modeChoice='fault';handoffSeed=null;linkedFaults={manual_fault:null,engineering_fault:null};
    inputsEdited=true;activeLookup++;emailTicket++;emailPreview=null;
    source.value='trackunit_page';
    symptom.value=`Trackunit 当前 Events 页${isHistoricalFault(item)?'历史已解除':'可见'}故障：${item.code||'未显示故障码'}${item.sa!==null?`，SA ${item.sa}`:''}；描述：${item.description||'页面未显示描述'}；页面显示时间：${item.displayed_at||'未显示'}。${isHistoricalFault(item)?'页面状态：已解除（历史记录），请生成历史故障备件参考与复发时的核查和备库条件，不代表当前需要换件。':'该卡片为页面局部观察，事件状态及完整历史尚未通过故障 API 核验。'}`;
    if(pageObservation)symptom.value='';
    continuationView.textContent=`${isHistoricalFault(item)?'历史故障备件参考 · 已解除':'当前页观察'} · ${item.code||'未显示故障码'} · ${item.description||''} · ${item.displayed_at||'时间待核实'}`;
    continuationView.hidden=false;controls(false);
  }
  window.selectVisibleTrackunitFault=index=>{
    const item=pageFaults[index];if(!item)return false;
    selectPageFault(item);renderEventOptions();card.scrollIntoView?.({block:'start',behavior:'smooth'});
    planStart.focus?.();return true;
  };
  function selectPageService(item){
    if(controller||job||preparing)cancel('已切换为保养分析。');
    automaticFault=null;pageFault=null;pageObservation=null;faultEventId=null;modeChoice='maintenance';
    handoffSeed=null;linkedFaults={manual_fault:null,engineering_fault:null};
    source.value='user_question';
    symptom.value=`Trackunit 当前 Events 页显示${item.kind==='overdue'?'逾期':'即将'}保养：${item.plan||'保养计划'}${item.target_hours!==null?`，计划工时 ${item.target_hours} h`:''}${item.hours_offset!==null?`，页面提示 ${item.hours_offset} h ${item.kind==='overdue'?'逾期':'剩余'}`:''}。请结合当前设备工时和同 VIN 的 XGSS 图册，推荐待检查的保养件与易损件；保养记录和适配需核对。`;
    inputsEdited=true;activeLookup++;emailTicket++;emailPreview=null;renderEventOptions();controls(false);
    card.scrollIntoView?.({block:'start',behavior:'smooth'});planStart.focus?.();
  }
  function renderPageFaultBanner(){
    faultAlert.replaceChildren();if(partsFocus){faultAlert.hidden=true;return;}
    faultAlert.hidden=!embedded||!realDevice(selected())||!pageObservedAt||!pageFaults.length&&!pageServices.length;
    if(faultAlert.hidden)return;
    faultAlert.append(el('strong',`Trackunit 当前页：${pageFaults.length} 条故障${pageFaults.some(isHistoricalFault)?`（历史 ${pageFaults.filter(isHistoricalFault).length} 条）`:''} · ${pageServices.length} 条保养提醒`),
      el('p','选择故障码后，AI 对照同 VIN 的 XGSS 资料推荐检查和备件；页面事件尚未经故障接口核验。'));
    if(record?.plan&&!pageFault&&record.symptom_source==='operator_report')
      faultAlert.append(el('p','下方已保存结果基于此前人工报告，尚未与这些页面故障码绑定。'));
    if(record?.plan&&!pageFault&&record.symptom_source==='trackunit_page')
      faultAlert.append(el('p',`下方已保存结果仅针对 ${recordFaultLabel(record).label}。分析其他故障，请先选择对应故障码。`));
    const list=el('div');list.className='research-page-fault-actions';
    const quickFaults=[...pageFaults.filter(item=>!isHistoricalFault(item)).slice(0,2),...pageFaults.filter(isHistoricalFault).slice(0,1)];
    if(!quickFaults.some(isHistoricalFault))quickFaults.push(...pageFaults.filter(item=>!quickFaults.includes(item)).slice(0,3-quickFaults.length));
    for(const item of quickFaults){
      const button=el('button');
      button.type='button';button.disabled=pageFault===item;
      button.title=`${item.code||'无故障码'}${item.sa!==null?' · SA '+item.sa:''} · ${item.description||'页面未显示描述'}`;
      button.append(el('strong',`${isHistoricalFault(item)?'历史 · 已解除 · ':''}${item.code||'故障码未显示'}${item.sa!==null?' · SA '+item.sa:''}`),
        el('span',item.description||'页面未显示描述'));
      button.onclick=()=>{selectPageFault(item);renderEventOptions();planStart.scrollIntoView?.({block:'center',behavior:'smooth'});planStart.focus?.();};
      list.append(button);
    }
    faultAlert.append(list);
    if(pageFaults.length>3)faultAlert.append(el('p',`其余 ${pageFaults.length-3} 条可在下方“Trackunit 故障记录”中选择。`));
    if(pageServices.length){
      const serviceList=el('div');serviceList.className='research-page-service-actions';
      for(const service of pageServices){
        const action=el('button',`${service.kind==='overdue'?'逾期保养':'即将保养'} · ${service.plan||'保养计划'} · AI 推荐保养件`);
        action.type='button';action.onclick=()=>selectPageService(service);serviceList.append(action);
      }
      faultAlert.append(serviceList);
    }
  }
  function associateVisiblePageFault(){
    // The page is only a partial observation. Use it as a default solely when
    // the official event API is unavailable and exactly one current card was
    // captured for this machine; never silently start a model request.
    if(!focused||!embedded||activeResolvedScope!==key(selected())||record||activeResearchId||
      inputsEdited||modeChoice!==null||faultEventId||pageFault||symptom.value.trim()||
      controller||job||preparing||handoffBusy||vinBusy||pageFaults.length!==1||isHistoricalFault(pageFaults[0])||faultEvents.length||
      !['unauthorized','forbidden','rate_limited','unavailable','schema_error'].includes(faultState?.status))return false;
    const age=Date.now()-Date.parse(pageObservedAt);
    if(!Number.isFinite(age)||age<0||age>120000)return false;
    selectPageFault(pageFaults[0]);renderEventOptions();
    showFaultSources();
    return true;
  }
  function associateCurrentFault(){
    // Wait for both local reads: an existing investigation or a user's input
    // takes precedence over a default choice, regardless of response order.
    if(partsFocus||!focused||activeResolvedScope!==key(selected())||pinnedResearchScope===key(selected())||
      record||activeResearchId||inputsEdited||modeChoice!==null||faultEventId||symptom.value.trim()||
      controller||job||preparing||handoffBusy||vinBusy||handoffSeed||
      currentFaults()?.manual_fault||currentFaults()?.engineering_fault)return;
    const checked=Date.parse(faultState?.checked_at),age=Date.now()-checked;
    // A failed/partial query can retain old OPEN records. Only use a complete,
    // recent query and an event actually observed in that query.
    if(['paused','busy'].includes(faultState?.auto_sync?.status)||faultState?.status!=='data'||faultState.http_status!==200||faultState.coverage!=='queried_window'||
      !Number.isFinite(checked)||age<0||age>1800000)return;
    const open=faultEvents.filter(event=>event.status==='OPEN');
    if(open.length!==1)return;
    const event=open[0];
    if(event.cleared_at||event.source!=='trackunit_asset_event_v3'||
      !faultState.trackunit_asset_id||event.trackunit_asset_id!==faultState.trackunit_asset_id||
      Date.parse(event.observed_at)!==checked||!(event.code||(Number.isInteger(event.spn)&&Number.isInteger(event.fmi))))return;
    selectFaultEvent(event);
    renderEventOptions();
    eventNote.textContent='已关联最近查询中的未解除故障，点击 AI 分析故障继续。';
    automaticFault={scope:key(selected()),eventId:event.event_id,checkedAt:checked};
    startAutomaticFault();
  }
  function startAutomaticFault(){
    const next=automaticFault;
    if(!next||!embedded||!available||controller||job||preparing||handoffBusy||vinBusy)return;
    automaticFault=null;
    if(next.scope!==key(selected())||next.eventId!==faultEventId||record||activeResearchId||
      symptom.value.trim()||analysisMode()!=='fault'||source.value!=='trackunit_event'||
      currentFaults()?.manual_fault||currentFaults()?.engineering_fault||Date.now()-next.checkedAt>1800000)return;
    eventNote.textContent='已关联最近查询中的未解除故障，正在分析并查找适用资料。';
    void planStart.onclick({automatic:true});
  }
  function scheduleFaultRead(){
    clearTimeout(faultPoll);
    if(!realDevice(selected()))return;
    const machineScope=key(selected());
    faultPoll=setTimeout(async()=>{
      faultPoll=null;if(machineScope!==key(selected()))return;
      if(document.visibilityState==='hidden'||controller||job||preparing||handoffBusy||eventBusy){scheduleFaultRead();return;}
      await loadFaultEvents();
    },faultPollInterval);
  }
  async function loadFaultEvents(refresh=false){
    const m=selected();renderEventOptions();if(!realDevice(m)){eventNote.textContent='选择真实设备后读取故障事件。';return;}
    const mine=++eventRequest,machineScope=key(m);faultState=null;eventBusy=true;eventLastAttempt=Date.now();clearTimeout(faultPoll);faultPoll=null;eventNote.textContent='正在读取故障事件…';controls(Boolean(controller)||Boolean(job)||preparing);
    try{
      const response=await fetch(refresh?'/assistant/fault-events/refresh':'/assistant/fault-events/sync',
        {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(identityBody(m))});
      if(!response.ok)throw new Error('故障事件暂时无法读取。');const data=await response.json();
      if(mine!==eventRequest||machineScope!==key(selected()))return;
      if(data.machine_id!==m.machine_id||(data.dataset_id||null)!==(m.dataset_id||null)||data.vin!==m.serial_number)throw new Error('故障事件与当前设备不一致，未载入。');
      faultEvents=(data.events||[]).filter(e=>/^[a-f0-9]{64}$/.test(e.event_id||'')&&e.machine_id===m.machine_id&&e.vin===m.serial_number);renderEventOptions();
      const labels={not_checked:'尚未读取 Trackunit 故障接口。',data:`已载入 ${faultEvents.length} 条故障事件。`,empty:'查询时段内未返回故障事件，不代表设备无故障。',unauthorized:'官方故障接口未授权；当前设备 Events 页的可见故障仍可用于排查。',forbidden:'官方故障接口无访问权限；当前设备 Events 页的可见故障仍可用于排查。',rate_limited:'故障接口限流，请稍后重试。',unavailable:'故障接口暂不可用；已保存记录仅供参考。',schema_error:'故障接口响应无法识别，尚未完成读取。',partial:'仅取得部分故障事件。',busy:'故障读取正在进行。'};
      apiEventNote=['paused','busy'].includes(data.auto_sync?.status)?data.auto_sync.message:(labels[data.status]||'故障事件读取状态待核实。');showFaultSources();
      const faultTime=value=>{const date=new Date(value);return value&&Number.isFinite(date.getTime())?
        date.toLocaleString('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}):'未记录';};
      const accessDenied=['unauthorized','forbidden'].includes(data.status);
      const accessLabel=data.status==='unauthorized'?'未授权（HTTP 401）':data.status==='forbidden'?'无访问权限（HTTP 403）':
        data.status==='data'?'已读取':data.status==='empty'?'查询窗口无返回':data.status==='partial'?'部分读取':'暂未取得数据';
      const checked=data.checked_at?`上次核查 ${faultTime(data.checked_at)}`:'尚未核查';
      const range=data.window_start&&data.window_end?` · 范围 ${faultTime(data.window_start)}—${faultTime(data.window_end)}`:'';
      eventFacts.textContent=`官方故障接口：${accessLabel}\n${checked}${range}\n`+
        (accessDenied?'接口未返回可核验的故障记录，不能据此判断设备无故障。打开当前设备的 Trackunit Events 页，可读取页面可见故障继续排查。':data.message||'');
      eventRefresh.textContent=accessDenied?'权限更新后重试':'重新读取故障接口';
      faultState=data;associateCurrentFault();associateVisiblePageFault();
    }catch(error){if(mine===eventRequest&&machineScope===key(selected())){apiEventNote=error.message;showFaultSources();}}
    finally{if(mine===eventRequest){eventBusy=false;controls(Boolean(controller)||Boolean(job)||preparing);scheduleFaultRead();}}
  }
  eventRefresh.onclick=()=>loadFaultEvents(true);
  eventPageRead.onclick=()=>{
    const m=selected();if(!embedded||!realDevice(m)||pageReadPending)return;
    const mine=++pageReadTicket,machineScope=key(m);pageReadPending=true;
    pageCaptureIssue='正在读取当前设备的 Trackunit Events 页…';showFaultSources();controls(Boolean(controller)||Boolean(job)||preparing);
    post({type:'jilian:trackunit-page-faults-request',asset_id:m.machine_id,dataset_id:m.dataset_id||null});
    pageReadTimer=setTimeout(()=>{
      if(mine!==pageReadTicket||machineScope!==key(selected()))return;
      pageReadTimer=null;pageReadPending=false;pageCaptureIssue='当前 Events 页读取超时，请重试。';
      showFaultSources();controls(Boolean(controller)||Boolean(job)||preparing);
    },12000);
  };
  function finishPageRead(){clearTimeout(pageReadTimer);pageReadTimer=null;pageReadTicket++;pageReadPending=false;}
  function selectFaultEvent(event){
    if(partsFocus){destroyEstimates();faultFocusTab=isHistoricalFault(event)?'historical':'current';}
    automaticFault=null;
    if(controller||job||preparing)cancel('故障事件已改变，原分析已停止。');
    const nextEventId=event?.event_id||null;
    // A supplement belongs to one event. Never carry a visible-page fault or
    // another event's observations into the newly selected official event.
    if(pageFault||faultEventId!==nextEventId)symptom.value='';
    pageFault=null;pageObservation=null;faultEventId=nextEventId;modeChoice=faultEventId?'fault':null;
    handoffSeed=null;linkedFaults={manual_fault:null,engineering_fault:null};inputsEdited=true;activeLookup++;emailTicket++;emailPreview=null;
    source.value=faultEventId?'trackunit_event':'operator_report';continuationView.textContent=event?`${event.code||'故障码未提供'} · ${event.description||''}`:'';continuationView.hidden=!event;controls(false);
  }
  eventSelect.onchange=()=>eventSelect.value.startsWith('page:')?
    selectPageFault(pageFaults[Number(eventSelect.value.slice(5))]):selectFaultEvent(faultEvents.find(e=>e.event_id===eventSelect.value));
  function updateResearchLink(id){
    if(!window.history?.replaceState)return;
    const query=new URLSearchParams(location.search);
    if(id){query.set('research',id);if(selected()?.dataset_id)query.set('dataset',selected().dataset_id);else query.delete('dataset');}
    else{query.delete('research');query.delete('dataset');}
    window.history.replaceState(null,'','?'+query.toString()+location.hash);
  }
  async function loadActiveResearch(){
    const m=selected();
    if(!realDevice(m)||controller||job||preparing||handoffBusy||inputsEdited||pinnedResearchScope===key(m))return;
    const candidate=!researchLinkConsumed&&/^[a-f0-9]{32}$/.test(initialResearchLink||'')?initialResearchLink:null;
    const linkedAsset=PlatformContext.asset(location.hash);
    if(candidate&&linkedAsset&&linkedAsset!==m.machine_id)return;
    // A standalone tab may retain a research query after a device change. With
    // no asset hash, that query is not bound to a machine; read its active plan.
    const link=candidate&&linkedAsset===m.machine_id?candidate:null;
    if(candidate&&!linkedAsset)researchLinkConsumed=true;
    if(link){researchLinkConsumed=true;pinnedResearchScope=key(m);}
    const mine=++activeLookup,machineScope=key(m),inputAtStart=JSON.stringify([symptom.value,source.value,record?.research_id]);activeResolvedScope=null;
    try{
      const response=await fetch(link?'/assistant/xgss/research/'+link:'/assistant/xgss/research/active',link?undefined:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(identityBody(m))});
      if(!response.ok){if(response.status===404&&!link){if(mine===activeLookup&&machineScope===key(selected())){activeResolvedScope=machineScope;associateCurrentFault();associateVisiblePageFault();}return;}throw new Error(link?'链接中的故障处理记录无法读取，未替换为其他结果。':'当前排查暂时无法读取，已保留本页输入。');}
      const data=await response.json();
      if(mine!==activeLookup||machineScope!==key(selected())||controller||job||preparing||handoffBusy||inputsEdited||inputAtStart!==JSON.stringify([symptom.value,source.value,record?.research_id]))return;
      if(data.machine_id!==m.machine_id||(data.dataset_id||null)!==(m.dataset_id||null)||data.vin!==m.serial_number||!data.plan||!/^[a-f0-9]{32}$/.test(data.research_id||'')||(link&&data.research_id!==link))throw new Error('当前排查与设备不一致，未载入。');
      if(partsFocus&&!isFaultResearch(data)){
        pinnedResearchScope=null;record=null;recordScope=null;
        symptom.value='';source.value='operator_report';destroyEstimates();updateResearchLink(null);
        // A shared link is not the server's active pointer. Resolve the real
        // active record before retaining a compare-and-swap ID for a new plan.
        if(link){controls(false);await loadActiveResearch();return;}
        activeResearchId=data.research_id;activeResolvedScope=machineScope;
        controls(false);status.textContent='选择当前或历史故障，生成对应配件推荐。';return;
      }
      record=data;recordScope=machineScope;activeResearchId=data.research_id;symptom.value=recordInput(data);source.value=data.symptom_source;
      rememberContext(data);showPlan(data);render(data);updateResearchLink(activeResearchId);
      status.textContent=data.advice_error||(data.advice?'已载入备件与维修建议。':data.pages?.length?'已载入 XGSS 资料，可继续生成备件建议。':
        '已接续 AI 排查，可继续读取同 VIN XGSS 图册。');
      continueActivePlan();
    }catch(error){if(mine===activeLookup&&machineScope===key(selected())&&!inputsEdited&&!controller&&!job)status.textContent=error.message;}
  }
  async function refreshActiveIdentity(machine,mine){
    try{
      const response=await fetch('/assistant/xgss/research/active',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(identityBody(machine))});
      if(!response.ok)return;
      const data=await response.json();
      if(mine===generation&&key(machine)===key(selected())&&data.machine_id===machine.machine_id&&
        (data.dataset_id||null)===(machine.dataset_id||null)&&data.vin===machine.serial_number&&/^[a-f0-9]{32}$/.test(data.research_id||''))activeResearchId=data.research_id;
    }catch{/* Preserve the entered problem when another workspace's state cannot be read. */}
  }
  async function refreshForeground(){
    const loading=loadActiveResearch();
    if(document.visibilityState!=='hidden'&&!eventBusy&&!controller&&!job&&!preparing&&!handoffBusy&&Date.now()-eventLastAttempt>=faultPollInterval)void loadFaultEvents();
    await loading;
  }
  window.addEventListener('focus',refreshForeground);
  document.addEventListener?.('visibilitychange',()=>{if(document.visibilityState==='visible')void refreshForeground();});
  for(const id of ['fault-reference-attach','manual-fault-remove','engineering-attach','engineering-remove','engineering-start'])
    document.getElementById(id)?.addEventListener('click',window.syncXGSSResearchFaults);
  for(const id of ['engineering-code','engineering-source','engineering-configuration'])
    document.getElementById(id)?.addEventListener('input',window.syncXGSSResearchFaults);
  function reportModelFailure(error,phase){
    if(error.name==='AbortError'){cancel('分析已停止。');return;}
    if(error.kind!=='schema_validation'){cancel(error.message);return;}
    // Retain the typed failure for retry logic, but do not expose internal schema details.
    modelFailure={error,phase,inputKey:modelInputKey()};
    const matching=planMatchesInput(),hasSources=matching&&record?.pages?.length;
    const previous=matching&&record?.advice&&record.analysis_revision===record.revision;
    cancel((phase==='plan'?'检索方向暂未生成。':'本次配件分析暂未完成。')+
      (hasSources?'已选故障和已读取的 XGSS 资料仍保留。':'已选故障与补充信息仍保留。')+
      (previous?'下方仍为上次建议，尚未更新。':'')+'请点击重试。');
  }
  async function modelRequest(url,body,signal){
    const response=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined,signal});
    if(!response.ok){
      const problem=await response.json().catch(()=>({})),detail=problem.detail;
      const error=new Error(typeof detail==='string'?detail:detail?.message||problem.message||'请求未完成，请重试。');
      error.kind=detail?.kind||detail?.code||problem.kind||problem.code;throw error;
    }
    const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='',result=null;
    try{while(true){const chunk=await reader.read();if(chunk.done)break;buffer+=decoder.decode(chunk.value,{stream:true}).replace(/\r/g,'');
      let end;while((end=buffer.indexOf('\n\n'))>=0){const block=buffer.slice(0,end);buffer=buffer.slice(end+2);if(!block.startsWith('data: '))continue;
        if(signal.aborted)throw new DOMException('Stopped','AbortError');
        const event=JSON.parse(block.slice(6));if(event.type==='progress')status.textContent=event.message;
        if(event.type==='error'){const error=new Error(event.message);error.kind=event.kind;throw error;}if(event.type==='result')result=event.record;
      }
    }}finally{reader.releaseLock();}
    if(!result)throw new Error('本次分析未产生完整结果。');return result;
  }
  function contextDetails(target,c={},analysis='fault'){
    target.append(el('p',`${c.sample_count===undefined?'有效采样数量待核实':c.sample_count+' 条有效采样'} · ${c.source==='trackunit_cache'?'Trackunit 本地缓存':'已导入设备数据'} · 非实时查询`));
    for(const [field,name] of [['operating_hours','累计工时'],['idle_hours','累计怠速'],['fuel_remaining_percent','燃油余量']]){
      const metric=c.metrics?.[field];target.append(el('p',metric?.value===null||metric?.value===undefined?`${name}：未载入有效值`:
        `${name}：${metric.value} ${metric.unit||''} · ${metric.observed_at||'采样时间待核实'}${metric.stale_after_24h?' · 历史采样':''}`));
    }
    if(analysis!=='maintenance'){
      const faults=Array.isArray(c.faults)?c.faults:[];
      target.append(el('p',faults.length?faults.map(f=>`${f.fault_code} · ${f.status} · ${f.occurred_at}`).join('；'):'未载入有效故障记录，不能据此判断无故障。'));
    }
  }
  function showPlan(data){
    maintenanceView.replaceChildren();
    if(recordMode(data)==='maintenance'){
      const context=data.maintenance_context||{},hours=context.operating_hours||data.machine_context?.metrics?.operating_hours;
      maintenanceView.append(el('strong',hours?.value!==null&&hours?.value!==undefined?`AI 工时依据：${hours.value} ${hours.unit||'h'}`:'尚无有效工时：AI 先筛选适用保养件'));
      if(hours?.observed_at)maintenanceView.append(el('p',`采样：${hours.observed_at}${hours.stale_after_24h?' · 历史采样':''}`));
      maintenanceView.append(el('p','保养周期与上次保养记录尚未核实；推荐用于检查与备件准备，不判定已到更换周期。'));
    }
    usedContextView.replaceChildren();
    if(data.machine_context){
      const details=el('details');details.append(el('summary','本次 AI 使用的设备证据'));
      contextDetails(details,data.machine_context,recordMode(data));details.append(el('p','取数时间：'+(data.machine_context.as_of||'待核实')));usedContextView.append(details);
    }else usedContextView.append(el('p','本次资料排查未包含设备观测；重新生成计划可纳入已载入数据。'));
    planView.replaceChildren();planDetails=disclosure(`AI 检索方向 · ${data.plan.directions.length} 项`,!focused&&(!data.advice||data.analysis_revision!==data.revision));
    planDetails.append(el('p',readable(data.plan.summary,data)));planView.append(planDetails);
    for(const d of data.plan.directions){const item=el('article');item.append(el('strong',d.component),el('p',readable(d.reason,data)));planDetails.append(item);}
    input.value=[...new Set(data.plan.directions.flatMap(d=>d.search_terms))].slice(0,12).join('、');
  }
  function showAdvice(data){
    emailTicket++;emailPreview=null;adviceView.replaceChildren();resultHero.replaceChildren();resultHero.hidden=true;const advice=data.advice;
    const valid=Boolean(advice&&data.analysis_revision===data.revision&&(!partsFocus||isFaultResearch(data)));if(planDetails)planDetails.open=!focused&&!valid;if(!valid)return;
    if(partsFocus){showCompactAdvice(data);return;}
    const maintenance=recordMode(data)==='maintenance',historical=!maintenance&&advice.analysis_scope==='historical';
    const historicalCandidates=historical&&Array.isArray(advice.historical_candidates)?advice.historical_candidates:[];
    const inspectionOnly=part=>part?.evidence_level==='inspection_only'||part?.status==='inspection_only';
    const parts=historical?[]:maintenance?advice.parts:advice.parts.filter(part=>!inspectionOnly(part));
    const inspectionTargets=maintenance?[]:[...(Array.isArray(advice.inspection_targets)?advice.inspection_targets:[]),...advice.parts.filter(inspectionOnly)];
    const classified=Array.isArray(advice.inspection_targets)||inspectionTargets.length>0;
    const overview=el('div');overview.className='research-result-overview';
    const badge=el('span',historical?'历史故障备件参考':maintenance?'AI 工时保养 · XGSS 图册依据':data.symptom_source==='simulation'?'模拟排查 · 真实图册资料':'AI 备件与维修建议');badge.className='research-result-badge';
    overview.append(badge);
    if(!maintenance){
      const fault=recordFaultLabel(data),scopeLabel=el('p');scopeLabel.className='research-fault-facts';
      scopeLabel.append(el('strong',`${historical?'历史故障 · 已解除':'本次故障'}：${fault.label}`));overview.append(scopeLabel);
      if(fault.description)overview.append(el('p',fault.description));
    }
    const countLabel=historical?`${historicalCandidates.length} 项历史备件候选`:maintenance?`${parts.length} 项保养与易损件推荐`:classified?`${inspectionTargets.length} 项优先核查 · ${parts.length} 项条件性备件`:`${parts.length} 项备件候选`;
    overview.append(el('h3',countLabel),el('p',historical?'用于复发准备；核对相关回路或部件与适配后，再决定备库或更换，不代表当前需要换件。':maintenance?'按 AI 推荐理由安排检查，核对保养记录与适配后准备备件。':inspectionTargets.length&&!parts.length?'先按检查顺序定位原因，核查对象暂不列入备件准备。':'需经现场检查确认，再核对适配与更换条件。'));
    const imageCount=data.pages.reduce((count,page)=>count+(page.illustrations||[]).length,0);
    const meta=el('p',`${data.pages.length} 页来源 · ${data.evidence.parts.length} 条零件 · ${imageCount} 张图纸 · ${data.evidence.manuals.length} 项手册摘录`);meta.className='muted';overview.append(meta);
    if(data.symptom_source==='operator_report')overview.append(el('p','故障现象来自人工报告，Trackunit 故障接口尚未核验。'));
    if(!data.evidence.manuals.length)overview.append(el('p','尚未读取维修手册；以下检查方向由 AI 提供。'));
    if(focused){
      const preview=el('p',[...historicalCandidates,...parts,...inspectionTargets].slice(0,2).map(part=>`${part.name} · ${part.part_number}`).join('  /  '));
      preview.className='research-result-preview';
      const jump=el('button',historical?'查看历史备件、图册与备库条件':inspectionTargets.length&&!parts.length?'查看核查部件、图册与检查建议':'查看备件、依据与维修建议');jump.type='button';jump.className='primary-button';
      jump.onclick=()=>adviceView.scrollIntoView?.({block:'start',behavior:'smooth'});
      resultHero.append(overview);
      if(preview.textContent)resultHero.append(preview);
      resultHero.append(jump);resultHero.hidden=false;
    }else adviceView.append(overview);
    const reasoning=disclosure(maintenance?'AI 推荐依据':'AI 判断与依据',!focused);reasoning.append(el('p',readable(advice.summary,data)));
    if(!parts.length&&!inspectionTargets.length&&!historicalCandidates.length)adviceView.append(el('p','本次没有足够依据推荐具体料号。'));
    function partCard(part,inspection=false,history=false){const item=el('article');item.className='engineering-hypothesis';
      const diagram=part.capture_id?diagramsFor(data,part.capture_id)[0]:null;
      if(!maintenance&&diagram)item.append(diagramFigure(data,diagram,part));
      item.append(el('h4',part.name));
      if(history)item.append(el('strong','历史备件候选 · 复发核查后备库'));
      if(inspection)item.append(el('strong','先检查，暂不列入备件准备'));
      if(maintenance){const role=el('span',{maintenance:'保养件',wear:'易损件',repair:'待核对部件'}[part.part_role]||'待核对部件');role.className='research-part-role';item.append(role);}const code=el('p',part.part_number);code.className='research-part-number';item.append(code);
      if(part.figure_ref){const position=el('p',`图中序号 ${part.figure_ref} · ${part.assembly_path?.at(-1)||'所属图册'}`);position.className='research-part-position';item.append(position);}
      if(!maintenance){const reason=el('p',`AI 匹配依据：${readable(part.reason,data)}`);reason.className='research-part-reason';item.append(reason);}
      const rationale=disclosure(history?'推荐依据与备库条件':inspection?'核查后再决定':maintenance?'AI 推荐理由与检查条件':'匹配理由与更换条件',maintenance||inspection||history);if(!inspection)rationale.append(el('p',readable(part.reason,data)));rationale.append(el('strong',history?'备库与更换条件':inspection?'需核实的条件':maintenance?'保养与更换条件':'考虑更换的条件'),el('p',readable(history?(part.preparation_condition||part.replacement_condition):part.replacement_condition,data)));item.append(rationale);
      if(maintenance){if(diagram)item.append(diagramFigure(data,diagram,part));else item.append(el('p','当前分类尚未取得 XGSS 图示。'));}
      const cite=el('button','查看图册依据');cite.type='button';cite.onclick=()=>openSource(part.source_id);item.append(cite);return item;
    }
    if(historicalCandidates.length){
      adviceView.append(el('h3','历史故障备件候选'));
      const candidates=el('div');candidates.className='research-part-list';adviceView.append(candidates);
      for(const part of historicalCandidates)candidates.append(partCard(part,false,true));
    }
    if(parts.length){
      if(classified&&!maintenance)adviceView.append(el('h3','条件性备件'));
      const candidates=el('div');candidates.className='research-part-list';adviceView.append(candidates);
      for(const part of parts)candidates.append(partCard(part));
    }
    if(inspectionTargets.length){
      adviceView.append(el('h3','优先核查的部件'));
      const targets=el('div');targets.className='research-part-list';adviceView.append(targets);
      for(const part of inspectionTargets)targets.append(partCard(part,true));
    }
    adviceView.append(reasoning);
    const checks=disclosure(`${maintenance?'保养检查建议':'维修与检查顺序'} · ${advice.repair_steps.length} 项`,focused),list=el('ol');
    for(const step of advice.repair_steps){const item=el('li');item.append(el('strong',step.basis==='manual_excerpt'?'手册依据':'AI 检查建议'));
      if(step.basis!=='manual_excerpt'||!step.source_quote)item.append(el('p',step.basis==='manual_excerpt'?step.instruction:readable(step.instruction,data)));
      if(step.source_quote){const quote=el('blockquote',step.source_quote),cite=el('button','查看手册原文');cite.type='button';cite.onclick=()=>openSource(step.source_id);item.append(quote,cite);}list.append(item);
    }checks.append(list);adviceView.append(checks);
    if(advice.missing_evidence.length){const missing=disclosure(`待补充证据 · ${advice.missing_evidence.length} 项`),items=el('ul');
      for(const text of advice.missing_evidence)items.append(el('li',readable(text,data)));missing.append(items);adviceView.append(missing);
    }
    const email=el('button','备件准备邮件');email.type='button';email.id='research-email-preview';
    email.hidden=!parts.length;
    const emailView=el('div');emailView.className='research-email-preview';emailView.hidden=true;adviceView.append(email,emailView);
    email.onclick=async()=>{
      if(!planMatchesInput()||controller||job||preparing)return;
      const mine=++emailTicket,machine=selected(),current=record;email.disabled=true;emailView.hidden=false;emailView.replaceChildren(el('p','正在生成邮件预览…'));
      const currentPreview=()=>mine===emailTicket&&record===current&&planMatchesInput()&&key(machine)===key(selected());
      try{
        const preview=await api(`/assistant/xgss/research/${current.research_id}/email-preview`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(identityBody(machine))});
        if(!currentPreview())return;
        if(!Number.isInteger(current.analysis_revision)||!current.analyzed_at||preview.research_id!==current.research_id||
          preview.analysis_revision!==current.analysis_revision||preview.analyzed_at!==current.analyzed_at){
          const updated=await api('/assistant/xgss/research/'+current.research_id);
          if(!currentPreview())return;
          if(updated.research_id!==current.research_id||updated.machine_id!==machine.machine_id||
            (updated.dataset_id||null)!==(machine.dataset_id||null)||updated.vin!==machine.serial_number||
            updated.symptom!==current.symptom||updated.symptom_source!==current.symptom_source||recordMode(updated)!==recordMode(current))
            throw new Error('更新结果与当前设备或问题不一致，请重新载入。');
          if(!Number.isInteger(updated.analysis_revision)||!updated.analyzed_at||!updated.advice)
            throw new Error('当前结果尚未完成分析，请重新分析后再预览邮件。');
          emailTicket++;emailPreview=null;record=updated;showPlan(record);render(record);
          status.textContent='建议已更新，已载入最新结果；请核对后重新预览备件准备邮件。';return;
        }
        emailPreview=preview;emailView.replaceChildren(el('h3',preview.subject),el('p','收件人：'+(preview.recipients?.join('；')||'未配置')));
        const body=el('pre',preview.body||preview.text||'');body.className='research-email-body';body.tabIndex=0;body.setAttribute('role','region');body.setAttribute('aria-label','备件准备邮件正文，可滚动查看全部');
        const previewState={sent:'邮件服务器已接受，送达待确认。',not_configured:'尚未配置发信渠道或收件人，邮件未发送。',sending:'邮件正在发送，请勿重复操作。',failed:'上次邮件发送失败。',uncertain:'上次发送结果待核实，请勿重复发送。'}[preview.notification_status]||'邮件预览，尚未发送。';
        const note=el('p',preview.message||previewState);note.setAttribute('role','status');
        const send=el('button','发送备件准备邮件');send.type='button';send.id='research-email-send';send.disabled=preview.can_send!==true||!preview.preview_hash;
        emailView.append(body,note,send);
        send.onclick=async()=>{
          if(!currentPreview()||emailPreview!==preview||send.disabled||preview.can_send!==true)return;
          send.disabled=true;email.disabled=true;note.textContent='正在发送，请勿重复操作。';
          try{
            const result=await api(`/assistant/xgss/research/${current.research_id}/email-send`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...identityBody(machine),preview_hash:preview.preview_hash})});
            if(!currentPreview())return;
            const names={sent:'邮件服务器已接受，送达待确认。',not_configured:'尚未配置发信渠道或收件人，邮件未发送。',ready:'邮件已准备，尚未发送。',sending:'邮件正在发送，请勿重复操作。',failed:'邮件发送失败。',uncertain:'发送结果待核实，请先检查邮箱，勿重复发送。'};
            note.textContent=result.message||names[result.status]||'发送状态待核实。';
            send.disabled=result.can_send!==true||!['ready','failed'].includes(result.status);
          }catch(error){if(currentPreview())note.textContent='未确认邮件发送成功：'+error.message+' 请重新查看邮件状态后再操作。';}
          finally{if(currentPreview())email.disabled=false;}
        };
      }catch(error){if(currentPreview())emailView.replaceChildren(el('p','邮件预览未生成：'+error.message));}
      finally{if(currentPreview())email.disabled=false;}
    };
  }
  const sourceNodes=new Map();
  function openSource(id){const item=sourceNodes.get(id);if(item){item.open=true;item.parentElement.open=true;item.scrollIntoView({block:'center',behavior:'smooth'});}}
  function diagramsFor(data,captureId){
    if(!/^[a-f0-9]{32}$/.test(data.research_id||''))return [];
    return (data.pages||[]).filter(p=>/^[a-f0-9]{64}$/.test(p.capture_id||'')&&(!captureId||p.capture_id===captureId))
      .flatMap(page=>(page.illustrations||[]).filter(image=>/^[a-f0-9]{64}$/.test(image.image_id||''))
        .map(image=>({page,image,url:`/assistant/xgss/research/${data.research_id}/images/${image.image_id}`})));
  }
  function closeImage(){if(imageDialog){const old=imageDialog;imageDialog=null;old.close?.();old.remove?.();}}
  function openImage(data,diagram,part,opener){
    closeImage();
    const dialog=el('dialog');imageDialog=dialog;dialog.className='research-image-dialog';dialog.setAttribute('aria-label','XGSS 图册图示');
    const header=el('div');header.className='research-image-header';
    const title=el('h2',part?part.name+' · 图册图示':diagram.image.title||diagram.page.content?.assembly_path?.at(-1)||'XGSS 图册图示');
    const close=el('button','关闭');close.type='button';close.onclick=closeImage;header.append(title,close);
    const toolbar=el('div');toolbar.className='research-image-toolbar';
    const smaller=el('button','缩小'),larger=el('button','放大'),reset=el('button','适合窗口'),zoomLabel=el('span','100%');
    for(const b of [smaller,larger,reset])b.type='button';zoomLabel.setAttribute('aria-live','polite');toolbar.append(smaller,zoomLabel,larger,reset);
    const viewport=el('div');viewport.className='research-image-viewport';viewport.tabIndex=0;viewport.setAttribute('aria-label','图纸，可滚动查看放大区域');
    const image=el('img');image.src=diagram.url;image.alt=title.textContent;image.draggable=false;
    const error=el('p','图示暂时无法读取，请重新采集该分类。');error.hidden=true;error.setAttribute('role','status');
    image.onerror=()=>{image.hidden=true;error.hidden=false;smaller.disabled=larger.disabled=reset.disabled=true;};viewport.append(image,error);
    let zoom=1;const applyZoom=()=>{
      const fit=viewport.clientWidth&&viewport.clientHeight&&image.naturalWidth&&image.naturalHeight?
        Math.min(1,(viewport.clientHeight-2)*image.naturalWidth/image.naturalHeight/viewport.clientWidth):1;
      image.style.width=`${fit*zoom*100}%`;image.style.maxWidth='none';zoomLabel.textContent=`${Math.round(zoom*100)}%`;smaller.disabled=zoom<=1;larger.disabled=zoom>=3;
    };image.onload=applyZoom;
    smaller.onclick=()=>{zoom=Math.max(1,zoom-.5);applyZoom();};larger.onclick=()=>{zoom=Math.min(3,zoom+.5);applyZoom();};reset.onclick=()=>{zoom=1;applyZoom();viewport.scrollTop=viewport.scrollLeft=0;};applyZoom();
    const caption=el('p',part?`${part.name} · ${part.part_number}${part.figure_ref?' · 图中序号 '+part.figure_ref:''}`:'按图中序号与零件表核对位置。');caption.className='research-image-caption';
    const provenance=el('p',`XGSS 原图 · ${diagram.image.document_ref||'已采集图示'} · 采集时间 ${diagram.image.captured_at||diagram.page.captured_at}`);provenance.className='muted';
    dialog.append(header,caption,toolbar,viewport,provenance);document.body.append(dialog);
    const resize=typeof ResizeObserver==='function'?new ResizeObserver(applyZoom):null;
    dialog.addEventListener('close',()=>{resize?.disconnect();if(imageDialog===dialog)imageDialog=null;dialog.remove();if(opener?.isConnected)opener.focus();},{once:true});
    dialog.showModal();resize?.observe(viewport);applyZoom();close.focus();
  }
  function diagramFigure(data,diagram,part=null){
    const figure=el('figure');figure.className='research-diagram';
    const button=el('button');button.type='button';button.className='research-diagram-open';
    const title=part?part.name+' · 图册图示':diagram.image.title||diagram.page.content?.assembly_path?.at(-1)||'XGSS 图册图示';
    button.setAttribute('aria-label',`放大图示：${title}${part?.figure_ref?'，图中序号 '+part.figure_ref:''}`);
    const image=el('img');image.src=diagram.url;image.alt=`${title} · XGSS 原图`;image.loading='lazy';image.decoding='async';
    button.append(image,el('span','查看大图'));button.onclick=()=>openImage(data,diagram,part,button);
    const caption=el('figcaption',part?.figure_ref?`图中序号 ${part.figure_ref}`:title);
    image.onerror=()=>{button.hidden=true;caption.textContent='图示暂时无法读取，请重新采集该分类。';};figure.append(button,caption);return figure;
  }
  function showDiagrams(data){
    galleryView.replaceChildren();const diagrams=diagramsFor(data);if(!diagrams.length)return;
    const gallery=el('section');gallery.className='research-diagram-gallery';gallery.setAttribute('aria-label','XGSS 原图');
    gallery.append(el('h3','当前设备图册'));const grid=el('div');grid.className='research-diagram-grid';
    for(const diagram of diagrams){
      const figure=diagramFigure(data,diagram);
      const parts=(data.evidence?.parts||[]).filter(p=>p.capture_id===diagram.page.capture_id&&p.figure_ref);
      if(parts.length){const labels=el('p',parts.slice(0,8).map(p=>`${p.figure_ref} ${p.name}`).join(' · '));labels.className='research-diagram-legend';figure.append(labels);}
      grid.append(figure);
    }
    gallery.append(grid);galleryView.append(gallery);
  }
  async function loadDeviceDiagrams(machine,mine){
    if(!realDevice(machine))return;
    // Reuse only the current device's locally collected diagrams. This does not
    // restore a prior analysis, symptom, task or historical navigation entry.
    try{
      const response=await fetch('/assistant/xgss/research/latest',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({machine_id:machine.machine_id,dataset_id:machine.dataset_id||null,vin:machine.serial_number})});
      if(!response.ok)return;
      const data=await response.json();
      if(mine!==galleryGeneration||key(machine)!==key(selected())||record||controller||job||preparing)return;
      if(data.machine_id!==machine.machine_id||(data.dataset_id||null)!==(machine.dataset_id||null)||data.vin!==machine.serial_number)return;
      showDiagrams(data);
    }catch{/* Optional illustration lookup must not block device analysis. */}
  }
  function render(record){
    galleryGeneration++;closeImage();showDiagrams(record);results.replaceChildren();sourceNodes.clear();const ev=record.evidence;
    const sourceList=el('details');sourceList.append(el('summary','查看已提取的原始资料'));results.append(sourceList);
    results.append(el('p',`已读取 ${record.pages.length} 页 · 零件 ${ev.parts.length} 条 · 手册章节 ${ev.manuals.length} 条`));
    for(const p of ev.parts){
      const item=el('details');item.append(el('summary',`${p.name} · ${p.part_number}`));
      item.append(el('p',`分类：${p.assembly_path.join(' / ')||'未识别'} · 图示位置：${p.figure_ref||'未标明'} · 图示用量：${p.quantity||'未标明'}`));
      item.append(el('p',`来源：${p.page_title} · ${p.captured_at}`));sourceNodes.set(p.source_id,item);sourceList.append(item);
    }
    for(const p of ev.manuals){const item=el('details');item.append(el('summary',p.title),el('p',p.text),el('p',`来源：${p.page_title} · ${p.captured_at}`));sourceNodes.set(p.source_id,item);sourceList.append(item);}
    showAdvice(record);controls(Boolean(job)||Boolean(controller));
  }
  function hasComponentSources(data){
    if(!data?.pages?.length)return false;
    if(data.evidence?.manuals?.length)return true;
    return (data.evidence?.parts||[]).some(part=>{
      const name=String(part.name||'').trim();
      return name&&!/^(?:[\u4e00-\u9fffA-Za-z -]*(?:起重机|装载机|挖掘机|压路机)|整机)(?:总成)?$/.test(name)&&
        !/^(?:[A-Za-z -]*\s)?(?:crane|loader|excavator)$/i.test(name);
    });
  }
  function catalogSearchTerms(terms){
    const text=terms.join(' ').toLocaleLowerCase(),categories=[];
    // XGSS uses assembly names rather than the fault vocabulary supplied by AI.
    if(/操纵杆|joystick|theta/.test(text))categories.push('驾驶室系统','操纵模块');
    if(/操纵杆|joystick|theta|线束|harness|接插件|connector/.test(text))categories.push('电气系统','驾驶室电气');
    if(/蓄电池|电瓶|电源|供电|充电|发电机|\bbattery\b|\bpower\s+(?:input|supply)\b|\balternator\b|\bcharging\b/.test(text))
      categories.push('电气系统','后车架电气','蓄电池','电源开关','发电机');
    return [...new Set([...categories,...terms])].slice(0,12);
  }
  planStart.onclick=async({force=false,automatic=false}={})=>{
    const m=selected();if(!m||controller||job||preparing||handoffBusy)return;
    automaticFault=null;
    if(partsFocus&&(!selectedFaultReady()||!selectionMatchesFaultTab())){status.textContent='请先选择本组故障记录，或补充明确的故障码。';return;}
    const maintenance=analysisMode()==='maintenance';
    if(!maintenance&&!faultEventId&&!pageObservation&&symptom.value.trim().length<(source.value==='user_question'?1:5)){status.textContent='请选择故障事件，或补充故障现象。';return;}
    // Continuing an unchanged investigation reuses its plan; a new symptom must
    // create a fresh plan before any old source can be analyzed again.
    force=force||Boolean(modelFailure?.phase==='plan'&&modelFailure.inputKey===modelInputKey());
    if(!force&&planMatchesInput()&&!record.advice_error){
      inputsEdited=false;
      if(focused&&hasComponentSources(record)&&(partsFocus||!record.advice||record.analysis_revision!==record.revision)){await analyzeRecord();return;}
      await collect(record);return;
    }
    const {manual_fault:manualFault,engineering_fault:engineeringFault}=maintenance?{}:currentFaults();
    if(manualFault&&engineeringFault){status.textContent='请只保留当前设备适用的一套故障资料。';return;}
    // Only this verified same-device sensor question excludes an unrelated draft.
    // Ordinary user questions and edited handoffs must still confirm fault scope.
    const sensorQuestion=sensorHandoffScope?.scope===key(m)&&sensorHandoffScope.symptom===symptom.value.trim()&&
      source.value==='user_question'&&!manualFault&&!engineeringFault&&!faultEventId&&!pageFault;
    if(!maintenance&&!faultEventId&&!pageObservation&&!manualFault&&!sensorQuestion&&typeof getManualFaultDraftReference==='function'&&getManualFaultDraftReference()){
      status.textContent='故障码尚未确认适用范围，请先核对并带入，或移除该代码。';return;
    }
    const parentId=!maintenance&&handoffSeed&&handoffSeed.symptom===symptom.value.trim()&&handoffSeed.symptom_source===source.value?handoffSeed.source_report_id:null;
    const mine=++generation,machineScope=key(m),expectedActive=activeResearchId;pendingFaultKey=faultKey({manual_fault:manualFault,engineering_fault:engineeringFault});controller=new AbortController();const signal=controller.signal;modelFailure=null;controls(true);if(!planMatchesInput())adviceView.replaceChildren();status.textContent=maintenance?'AI 正在结合工时筛选保养与易损件方向…':'AI 正在分析故障并生成检索方向…';
    let activating=false;
    try{
      const created=await modelRequest('/assistant/xgss/research/plan',{machine_id:m.machine_id,dataset_id:m.dataset_id||null,vin:m.serial_number,
        analysis_mode:maintenance?'maintenance':'fault',symptom:symptom.value.trim(),symptom_source:inputSource(),
        ...(automatic?{automatic:true}:{}),
        ...(!maintenance&&pageObservation?{page_fault:pageObservation}:{}),
        ...(!maintenance&&faultEventId?{fault_event_id:faultEventId}:{}),...(parentId?{source_report_id:parentId}:{}),...(manualFault?{manual_fault:manualFault}:{}),...(engineeringFault?{engineering_fault:engineeringFault}:{})},signal);
      if(mine!==generation||machineScope!==key(selected()))return;
      activating=true;
      const activated=await api('/assistant/xgss/research/'+created.research_id+'/activate',{method:'POST',headers:{'Content-Type':'application/json'},signal,
        body:JSON.stringify({...identityBody(m),expected_research_id:expectedActive})});
      if(mine!==generation||machineScope!==key(selected()))return;
      record=activated;recordScope=machineScope;activeResearchId=record.research_id;pinnedResearchScope=null;inputsEdited=false;symptom.value=recordInput(record);source.value=record.symptom_source;rememberContext(record);updateResearchLink(activeResearchId);
      galleryGeneration++;closeImage();showDiagrams(record);results.replaceChildren();coverage.textContent='';showPlan(record);
      if(preferredTerms?.scope===machineScope)input.value=preferredTerms.terms.join('、');
      controller=null;pendingFaultKey=null;controls(false);
      if(automatic&&record.advice&&record.analysis_revision===record.revision){render(record);status.textContent='已载入该故障的备件与维修建议。';return;}
      if(automatic&&hasComponentSources(record)&&!record.advice){await analyzeRecord();return;}
      await collect(record);
    }catch(error){
      if(mine===generation&&activating&&error.name!=='AbortError')await refreshActiveIdentity(m,mine);
      if(mine===generation&&automatic&&['auto_fault_pending','auto_fault_active'].includes(error.kind))inputsEdited=false;
      if(mine===generation)reportModelFailure(error,'plan');
    }
  };
  replan.onclick=()=>planStart.onclick({force:true});
  async function analyzeRecord(){
    if(!record?.pages?.length||!planMatchesInput()||controller||job)return;
    const mine=++generation,id=record.research_id;controller=new AbortController();modelFailure=null;controls(true);
    try{const updated=await modelRequest('/assistant/xgss/research/'+id+'/analyze',null,controller.signal);
      if(mine!==generation||recordScope!==key(selected()))return;record=updated;controller=null;render(record);if(!resultHero.hidden)resultHero.scrollIntoView?.({block:'start'});status.textContent=recordMode(record)==='maintenance'?'已生成 AI 保养建议，可逐条查看原始资料。':'已生成备件与维修建议，可逐条查看原始资料。';
    }catch(error){if(mine===generation)reportModelFailure(error,'analyze');}
  }
  analyze.onclick=analyzeRecord;
  localEvidence.onclick=async()=>{
    const m=selected();if(!m||evidenceBusy)return;
    const mine=++evidenceRequest,machineScope=key(m);evidenceBusy=true;localEvidence.disabled=true;
    contextView.replaceChildren(el('p','正在读取本机已载入的设备证据…'));
    try{
      const data=await api('/assistant/xgss/research/machine-context',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({machine_id:m.machine_id,dataset_id:m.dataset_id||null,vin:m.serial_number})});
      if(mine!==evidenceRequest||machineScope!==key(selected()))return;
      contextView.replaceChildren(el('h3','已载入设备证据 · 本地查看'));contextDetails(contextView,data.context,analysisMode());
    }catch(error){if(mine===evidenceRequest)contextView.replaceChildren(el('p',error.message));}
    finally{if(mine===evidenceRequest){evidenceBusy=false;controls(Boolean(job)||Boolean(controller)||preparing);}}
  };
  resume.onclick=async()=>{
    const m=selected();if(!m||controller||job||preparing)return;
    const mine=++generation,machineScope=key(m);preparing=true;controls(true);
    try{
      const restored=await api('/assistant/xgss/research/latest',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({machine_id:m.machine_id,dataset_id:m.dataset_id||null,vin:m.serial_number})});
      if(mine!==generation||machineScope!==key(selected()))return;
      if(partsFocus&&!isFaultResearch(restored)){preparing=false;controls(false);status.textContent='选择当前或历史故障，生成对应配件推荐。';return;}
      record=restored;recordScope=machineScope;preparing=false;symptom.value=recordInput(record);source.value=record.symptom_source;rememberContext(record);
      showPlan(record);render(record);status.textContent=record.advice_error||'已恢复上次资料排查，可继续读取资料或查看建议。';
    }catch(error){if(mine===generation)cancel(error.message);}
  };
  function useReportTerms(){
    const displayed=report||openedReport,m=selected();
    if(!displayed||!m||displayed.machine_id!==m.machine_id||(displayed.dataset_id||null)!==(m.dataset_id||null)){
      status.textContent='当前没有属于此设备和数据版本的 AI 报告。';return false;
    }
    const guidance=currentAISearchGuidance();
    if(!guidance.terms.length){status.textContent='当前没有 AI 部件检索词，可先分析或人工补充检索词。';return false;}
    preferredTerms={scope:key(m),terms:[...guidance.terms]};
    input.value=guidance.terms.join('、');status.textContent='已带入设备分析的检索词，请核对现象后查找资料。';return true;
  }
  useAI.onclick=useReportTerms;
  input.oninput=()=>{preferredTerms=null;};
  mode.onchange=()=>{
    if(controller||job||preparing||handoffBusy)return;
    automaticFault=null;
    sensorHandoffScope=null;modeChoice=mode.value==='maintenance'?'maintenance':'fault';
    handoffSeed=null;linkedFaults={manual_fault:null,engineering_fault:null};faultEventId=null;pageFault=null;pageObservation=null;
    symptom.value='';source.value=modeChoice==='maintenance'?'user_question':'operator_report';
    inputsEdited=true;activeLookup++;emailTicket++;emailPreview=null;preferredTerms=null;
    continuationView.hidden=unlinkContext.hidden=true;renderEventOptions();controls(false);
    status.textContent=record?.plan&&!planMatchesInput()?'分析方式已更改，请重新运行 AI 分析。':'';
  };
  symptom.onfocus=()=>{if(modeChoice===null)modeChoice=analysisMode();};
  symptom.oninput=source.onchange=()=>{
    automaticFault=null;sensorHandoffScope=null;
    inputsEdited=true;activeLookup++;emailTicket++;emailPreview=null;
    if(handoffSeed&&(handoffSeed.symptom!==symptom.value.trim()||handoffSeed.symptom_source!==source.value)){handoffSeed=null;continuationView.textContent=linkedFaults?.manual_fault?.code||linkedFaults?.engineering_fault?.code?'已保留确认的故障码背景；现象已更新。':'';continuationView.hidden=!continuationView.textContent;}
    preferredTerms=null;
    controls(Boolean(job)||Boolean(controller)||preparing);
    if(record?.plan&&!planMatchesInput())status.textContent=changedContextNote;
    else if(status.textContent===changedContextNote)status.textContent='';
  };
  handoff.onclick=async()=>{
    const displayed=report||openedReport,m=selected();
    if(job||controller||preparing||handoffBusy||!m)return;
    if(!displayed||displayed.machine_id!==m.machine_id||(displayed.dataset_id||null)!==(m.dataset_id||null)||!/^[a-f0-9]{64}$/.test(displayed.record_id||'')){
      status.textContent='当前报告未保存或不属于此设备，无法接续。请先完成当前设备的分析。';return;
    }
    if(symptom.value.trim()&&(inputsEdited||record?.plan)){
      status.textContent='下方已有排查输入，已保留。清空现象后可带入上一步的原始问题。';card.scrollIntoView?.({block:'start',behavior:'smooth'});symptom.focus?.();return;
    }
    const mine=++generation,machineScope=key(m);handoffBusy=true;controls(true);
    try{
      const seed=await api('/assistant/xgss/research/handoff',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...identityBody(m),source_report_id:displayed.record_id})});
      if(mine!==generation||machineScope!==key(selected()))return;
      symptom.value=seed.symptom;source.value=seed.symptom_source;rememberContext(seed);inputsEdited=true;activeLookup++;
      useReportTerms();options.open=false;status.textContent='已带入原问题、故障背景和分析依据。核对后可继续查找资料。';
      card.scrollIntoView?.({block:'start',behavior:'smooth'});symptom.focus?.();
    }catch(error){if(mine===generation)status.textContent=error.message;}
    finally{if(mine===generation){handoffBusy=false;controls(Boolean(job)||Boolean(controller)||preparing);}}
  };
  // An explicit risk-card action starts a new, server-verified question. The
  // existing fault investigation stays saved and is never relabelled as a trend.
  window.openSensorSeriesParts=async request=>{
    if(partsFocus)return false;
    const m=selected();
    if(!m||m.machine_id!==request?.machine_id||(m.dataset_id||null)!==request?.dataset_id)
      throw new Error('设备已切换，请在当前设备重新选择风险方向。');
    if(job||controller||preparing||handoffBusy)throw new Error('当前排查仍在进行，请完成后再查看风险相关备件。');
    const mine=++generation,machineScope=key(m);handoffBusy=true;controls(true);
    try{
      const seed=await api('/assistant/sensor-series/'+encodeURIComponent(request.series_id)+'/parts-handoff',{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({machine_id:m.machine_id,dataset_id:m.dataset_id,hypothesis_index:request.hypothesis_index})});
      if(mine!==generation||machineScope!==key(selected()))throw new Error('设备已切换，未载入旧设备的风险问题。');
      if(seed.series_id!==request.series_id||seed.machine_id!==m.machine_id||seed.dataset_id!==m.dataset_id||
        seed.vin!==m.serial_number||seed.symptom_source!=='user_question'||!seed.symptom||!Array.isArray(seed.search_terms))
        throw new Error('风险资料与当前设备不一致，未开始图册查询。');
      automaticFault=null;handoffSeed=null;linkedFaults={manual_fault:null,engineering_fault:null};
      faultEventId=null;pageFault=null;pageObservation=null;modeChoice='fault';mode.value='fault';
      symptom.value=seed.symptom;source.value='user_question';inputsEdited=true;activeLookup++;
      sensorHandoffScope={scope:machineScope,symptom:seed.symptom.trim()};
      emailTicket++;emailPreview=null;preferredTerms={scope:machineScope,terms:seed.search_terms};
      continuationView.textContent='来自本机连续传感器趋势分析，备件需在图册中核对。';continuationView.hidden=false;
      inputPanel.open=true;renderEventOptions();
      if(typeof setView==='function')setView('work',{reason:'sensor-parts'});
      card.scrollIntoView?.({block:'start'});
    }finally{
      if(mine===generation){handoffBusy=false;controls(Boolean(job)||Boolean(controller)||preparing);}
    }
    if(mine===generation&&machineScope===key(selected()))await planStart.onclick({force:true});
  };
  async function collect(planned=null,{analyzeAfter=true}={}){
    const m=selected(),enteredTerms=[...new Set(input.value.split(/[、,，;；\n]/).map(t=>t.trim()).filter(Boolean))],terms=catalogSearchTerms(enteredTerms);
    if(!m||job||controller||preparing)return;
    if(needsVin()){status.textContent='AI 初步方向已保留；补充整机 VIN/PIN 后继续核对图册与料号。';showPreliminary();return;}
    if(!enteredTerms.length||enteredTerms.length>12||enteredTerms.some(t=>t.length<2||t.length>40)){status.textContent='请输入 1–12 个部件检索词，每个 2–40 字。';return;}
    const current=++generation,currentScope=key(m);preparing=true;controls(true);
    status.textContent='正在从 XGSS 读取同 VIN 图册与部件资料…';coverage.textContent='';entryNote='';
    try{
      const collected=planned||await api('/assistant/xgss/research',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({machine_id:m.machine_id,dataset_id:m.dataset_id||null,vin:m.serial_number})});
      if(current!==generation||currentScope!==key(selected()))return;
      record=collected;recordScope=currentScope;
      try{
        // A loaded version is required for the backend's atomic evidence update.
        if(!Number.isInteger(collected.revision)||collected.revision<0)
          throw Object.assign(new Error('资料版本尚未确认，请重新读取当前排查。'),{kind:'direct_unavailable'});
        controller=new AbortController();
        const updated=await modelRequest('/assistant/xgss/research/'+collected.research_id+'/collect-direct',
          {expected_revision:collected.revision,terms},controller.signal);
        if(current!==generation||currentScope!==key(selected()))return;
        if(updated?.research_id!==collected.research_id||updated.machine_id!==m.machine_id||
          (updated.dataset_id||null)!==(m.dataset_id||null)||updated.vin!==m.serial_number||
          !Number.isInteger(updated.revision)||updated.revision<collected.revision)
          throw Object.assign(new Error('返回资料与当前排查不一致，未载入。'),{kind:'direct_identity'});
        const direct=updated.direct_collection;
        if(!direct||!['completed','partial','cached'].includes(direct.status)||!updated.pages?.length)
          throw Object.assign(new Error('XGSS 未返回完整的资料读取结果。'),{kind:'direct_schema'});
        record=updated;controller=null;preparing=false;render(record);
        const unmatched=Array.isArray(direct.unmatched_terms)?direct.unmatched_terms:[];
        const unresolved=Array.isArray(direct.unresolved)?direct.unresolved:[];
        coverage.textContent=(direct.status==='partial'?'已读取可用图册，部分分类尚未匹配。':'已读取 XGSS 图册。')+
          (unmatched.length?' 尚未匹配：'+unmatched.join('、')+'。':'')+(unresolved.length?' 未完成：'+unresolved.join('、')+'。':'');
        status.textContent=hasComponentSources(record)?'XGSS 资料已读取，可生成配件建议。':'已读取图册目录，尚未取得可核对的部件，请继续读取。';
        if(analyzeAfter&&record.plan&&hasComponentSources(record)&&planMatchesInput())await analyzeRecord();
        return;
      }catch(error){
        if(current!==generation||currentScope!==key(selected()))return;
        if(controller?.signal.aborted||error.name==='AbortError')throw error;
        controller=null;
        if(!['direct_unavailable','direct_auth','direct_schema','direct_no_match'].includes(error.kind))throw error;
        if(!available)throw new Error('XGSS 暂未完成读取。已保存资料仍保留，请稍后重试；也可连接 Chrome 助手使用备用读取。');
        entryNote='直读暂未完成，正在通过插件读取同 VIN 图册。';status.textContent=entryNote;
      }
      const openBody={...identityBody(m),vin_confirmed:true,language:'zh'},code=collected.catalog_fault_code||null;
      let faultReady=false;
      if(code){
        try{faultReady=(await api('/assistant/xgss/status')).fault_ready===true;}catch{/* The general catalog remains usable when fault lookup is unavailable. */}
        if(current!==generation||currentScope!==key(selected()))return;
        if(!faultReady)entryNote+='故障资料入口暂不可用，改为读取同 VIN 图册；故障背景仍保留。';
      }
      let page;
      try{page=await api('/assistant/xgss/open',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...openBody,...(faultReady?{fault_code:code}:{})})});}
      catch(error){
        if(!faultReady)throw error;
        if(current!==generation||currentScope!==key(selected()))return;
        entryNote+='故障资料未能打开，改为读取同 VIN 图册；尚未取得该故障的官方手册。';
        page=await api('/assistant/xgss/open',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(openBody)});
      }
      if(current!==generation||currentScope!==key(selected()))return;
      coverage.textContent=entryNote;
      job={id:collected.research_id,scope:currentScope,asset:m.machine_id,dataset:m.dataset_id||null,analyzeAfter};
      preparing=false;
      controls(true);
      results.replaceChildren();touch();
      post({type:'jilian:research-start',request_id:job.id,asset_id:job.asset,dataset_id:job.dataset,vin:m.serial_number,terms,url:page.url});
    }catch(error){if(current===generation){
      if(error.code==='vin_required'||error.code==='vin_not_found'||/VIN\/PIN.*不存在/.test(error.message)){
        catalogIdentity={needs_verification:true};showVinRepair(error.message);
      }
      cancel(error.name==='AbortError'?'资料读取已停止；已保存内容仍保留。':error.message);showPreliminary();
    }}
  };
  start.onclick=()=>{
    if(record?.plan&&!planMatchesInput()){status.textContent='现象或来源已更改，请重新查找备件与维修资料。';return;}
    return collect(planMatchesInput()?record:null);
  };
  stop.onclick=()=>cancel('已停止资料收集，已读取内容仍保留。');
  window.addEventListener('message',async event=>{
    const d=event.data;
    if(!embedded||event.source!==window.parent||event.origin!==origin||d?.protocol!==1||d.connection_id!==connection)return;
    if(d.type==='jilian:research-ready'){available=true;window.syncXGSSResearch();startAutomaticFault();continueActivePlan();return;}
    if(d.type==='jilian:trackunit-page-faults-error'){
      const m=selected();
      if(m&&realDevice(m)&&d.asset_id===m.machine_id&&d.dataset_id===(m.dataset_id||null)){
        finishPageRead();
        pageCaptureIssue=d.reason==='wrong_page'?'请打开当前设备的 Trackunit Events 页再读取。':
          d.reason==='identity_pending'?'正在核对当前设备，请稍后重新读取 Events 页。':
          '当前 Events 页读取失败，请检查插件对 Trackunit 的站点访问权限或刷新页面。';
        showFaultSources();controls(Boolean(controller)||Boolean(job)||preparing);
      }
      return;
    }
    if(d.type==='jilian:trackunit-page-faults'){
      const m=selected(),capture=d.capture;
      if(!m||!realDevice(m)||d.asset_id!==m.machine_id||d.dataset_id!==(m.dataset_id||null)||
        capture?.schema_version!==1||capture.source!=='trackunit_visible_events_page'||
        capture.asset_id!==m.machine_id||!['visible_fault_cards','no_visible_fault_cards'].includes(capture.capture_status)||
        !Array.isArray(capture.faults)||capture.faults.length>20||!Number.isFinite(Date.parse(capture.observed_at)))return;
      const services=Array.isArray(capture.services)?capture.services:[];
      if(services.length>20||!services.every(item=>item&&['overdue','upcoming'].includes(item.kind)&&
        typeof item.title==='string'&&item.title.length<=40&&typeof item.plan==='string'&&item.plan.length<=120&&
        (item.target_hours===null||Number.isFinite(item.target_hours))&&
        (item.hours_offset===null||Number.isFinite(item.hours_offset))&&
        typeof item.displayed_at==='string'&&item.displayed_at.length<=100))return;
      const valid=capture.faults.every(item=>item&&typeof item.description==='string'&&item.description.length<=500&&
        (item.code===null||typeof item.code==='string'&&item.code.length<=40)&&
        (item.spn===null||Number.isInteger(item.spn))&&(item.fmi===null||Number.isInteger(item.fmi))&&
        (item.sa===null||Number.isInteger(item.sa))&&typeof item.displayed_at==='string'&&item.displayed_at.length<=100&&
        (item.status===undefined||['OPEN','CLOSED','UNKNOWN'].includes(item.status))&&
        (item.cleared_at===undefined||typeof item.cleared_at==='string'&&item.cleared_at.length<=100)&&
        (item.page_event_id==null||typeof item.page_event_id==='string'&&item.page_event_id.length<=150));
      if(!valid)return;
      const chosen=pageFault? pageFaultKey(pageFault):null;
      pageFaults=capture.faults;pageServices=services;window.syncVisibleTrackunitEvents?.(capture);
      pageFault=chosen?pageFaults.find(item=>pageFaultKey(item)===chosen)||pageFault:null;
      pageObservedAt=capture.observed_at;pageSourceUrl=validPageSourceUrl(capture.source_url,m.machine_id);finishPageRead();pageCaptureIssue='';
      // Page faults are actionable only if the fault selector is visible. Do
      // not silently pick one when several cards belong to the same machine.
      if(!associateVisiblePageFault()&&pageFaults.length>1&&modeChoice===null&&!record&&!activeResearchId&&!inputsEdited&&
        !symptom.value.trim())modeChoice='fault';
      renderEventOptions();showFaultSources();controls(Boolean(controller)||Boolean(job)||preparing);return;
    }
    if(!matches()||d.request_id!==job.id||d.asset_id!==job.asset||d.dataset_id!==job.dataset)return;
    if(d.type==='jilian:research-progress'){touch();status.textContent=String(d.message||'').slice(0,250);return;}
    if(d.type==='jilian:research-page'){
      const active=job;touch();
      try{
        const updated=await api('/assistant/xgss/research/'+active.id+'/pages',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d.capture)});
        if(job!==active||!matches())return;
        record=updated;
        render(record);post({type:'jilian:research-ack',request_id:active.id,page_id:d.page_id,success:true});touch();
      }catch(error){if(job===active){post({type:'jilian:research-ack',request_id:active.id,page_id:d.page_id,success:false});cancel(error.message);}}
    }
    if(d.type==='jilian:research-done'){
      const unmatched=Array.isArray(d.result?.unmatched_terms)?d.result.unmatched_terms:[];
      const unresolved=Array.isArray(d.result?.unresolved)?d.result.unresolved.filter(t=>typeof t==='string').slice(0,12):[];
      coverage.textContent=entryNote+'本次仅覆盖已展开并读取的资料。'+(unmatched.length?' 尚未命中的检索词：'+unmatched.join('、')+'。':'')+
        (unresolved.length?' 未完成读取：'+unresolved.join('、')+'。':'');
      const usable=hasComponentSources(record),analyzeAfter=job.analyzeAfter!==false;
      cancel(!usable?'尚未读到部件或手册内容，请重试以继续读取分类。':d.result?.status==='completed'?'资料收集完成。':'已收集可读取的资料；部分分类未展开或尚未匹配。');
      if(analyzeAfter&&record?.plan&&usable)await analyzeRecord();
    }
    if(d.type==='jilian:research-error')cancel(String(d.message||'资料收集失败。').slice(0,250));
  });
  window.syncXGSSResearch();
  if(embedded)post({type:'jilian:research-probe',request_id:'research-ready'});
})();
