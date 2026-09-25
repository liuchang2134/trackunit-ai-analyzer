const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function harness({fetchIdentity=async()=>({ok:false,status:503}),ready=true,fetchDiagrams=async()=>({ok:false,status:404}),fetchActive=async()=>({ok:false,status:404}),fetchFaults=async()=>({ok:false,status:404}),fetchLinked=async()=>({ok:false,status:404}),fetchDirect=async()=>streamedFailure('direct_unavailable'),flowTrack=false,focused=false,partsFocus=false,estimates=null,search='?panel=connection',hash='#trackunit-asset=asset'}={}){
  const nodes=[],messages=[],requests=[],listeners={},fetchCalls=[],timers=[],documentListeners={};
  function node(tag){const n={tag,children:[],textContent:'',value:'',style:{},attributes:{},events:{},append(...xs){this.children.push(...xs);},replaceChildren(...xs){this.children=[...xs];},setAttribute(k,v){this.attributes[k]=v;},addEventListener(k,v){this.events[k]=v;},showModal(){this.open=true;},close(){this.open=false;this.events.close?.();},remove(){this.removed=true;},focus(){this.focused=true;}};nodes.push(n);return n;}
  const host=node('main'),parent={postMessage:d=>messages.push(d)};
  const flow=node('ol'),steps=Object.fromEntries(['connect','diagnose','verify'].map(name=>[name,{dataset:{}}]));
  flow.querySelector=selector=>steps[selector.match(/data-step="([^"]+)"/)?.[1]]||null;
  const machineSelect=node('select');machineSelect.value='dataset:'+'a'.repeat(64);
  const extras=Object.fromEntries(['engineering-fault-panel','fault-reference-panel','manual-fault-linked','risk-device'].map(id=>[id,node('div')]));
  const getNode=id=>id==='flow-track'?flow:id==='machine'?machineSelect:extras[id]||host;
  const state={machine:{machine_id:'asset',dataset_id:'a'.repeat(64),serial_number:'XUGTEST000000001',model:'XC948U',provenance:'user_supplied'}};
  const window={parent,...(estimates?{JilianPartEstimates:estimates}:{}),addEventListener:(n,fn)=>listeners[n]=fn};
  const location={ancestorOrigins:['chrome-extension://'+'a'.repeat(32)],search,hash};
  const sandbox={window,location,document:{visibilityState:'visible',addEventListener:(name,fn)=>documentListeners[name]=fn,documentElement:{classList:{contains:name=>name==='fault-parts-focus'?partsFocus:focused}},getElementById:getNode,createElement:node,body:node('body')},selected:()=>state.machine,$:getNode,
    PlatformContext:{asset:hash=>hash.split('=')[1]},defaultSource:'demo',report:null,openedReport:null,
    currentAISearchGuidance:()=>({terms:['散热器']}),URL,URLSearchParams,setTimeout:(callback,delay)=>{const timer={id:timers.length+1,callback,delay,cleared:false};timers.push(timer);return timer.id;},clearTimeout:id=>{const timer=timers.find(t=>t.id===id);if(timer)timer.cleared=true;},
    fetch:(url,options)=>{fetchCalls.push({url,options});return url==='/assistant/xgss/identity'?fetchIdentity(url,options):url==='/assistant/xgss/research/active'?fetchActive(url,options):
      url==='/assistant/xgss/research/latest'?fetchDiagrams(url,options):url.endsWith('/collect-direct')?fetchDirect(url,options):url.startsWith('/assistant/fault-events')?fetchFaults(url,options):/\/research\/[a-f0-9]{32}$/.test(url)?fetchLinked(url,options):Promise.reject(new Error('Unexpected fetch: '+url));},AbortController,TextDecoder,DOMException,
    api:(url,options)=>new Promise((resolve,reject)=>requests.push({url,options,resolve,reject}))};
  if(flowTrack){
    const app=fs.readFileSync(require.resolve('../app/assistant_ui/app.js'),'utf8');
    const begin=app.indexOf('function updateFlowTrack(){'),end=app.indexOf("$('catalog').onchange",begin);
    assert.ok(begin>=0&&end>begin,'load the actual flow renderer, not a test copy');
    vm.runInNewContext(app.slice(begin,end),sandbox);
  }
  vm.runInNewContext(fs.readFileSync(require.resolve('../app/assistant_ui/xgss-research-workspace.js'),'utf8'),sandbox);
  const send=(data,extra={})=>listeners.message({source:parent,origin:location.ancestorOrigins[0],data:{protocol:1,connection_id:'connection',...data},...extra});
  if(ready)send({type:'jilian:research-ready'});
  const start=nodes.find(n=>n.textContent==='查找并提取资料'),stop=nodes.find(n=>n.textContent==='停止'),input=nodes.find(n=>n.id==='research-terms');
  const launch=async()=>{input.value='散热器';const action=start.onclick();requests[0].resolve({research_id:'b'.repeat(32)});await tick();requests[1].resolve({url:'https://xgss.xcmg.com/'});await action;};
  return {nodes,messages,requests,state,window,location,sandbox,send,start,stop,input,launch,listeners,fetchCalls,timers,documentListeners,
    flowState:()=>Object.fromEntries(Object.entries(steps).map(([name,li])=>[name,li.dataset.state]))};
}
test('source persistence ignores messages from other windows and mismatched datasets',async()=>{
  const h=harness();await h.launch();
  const page={type:'jilian:research-page',request_id:'b'.repeat(32),asset_id:'asset',dataset_id:'a'.repeat(64),page_id:'p',capture:{vin:'XUGTEST000000001'}};
  h.send(page,{source:{}});h.send({...page,dataset_id:'other'});assert.equal(h.requests.length,2);
  h.send(page);assert.equal(h.requests.length,3);
});
test('switching device during entry lookup discards the late signed URL',async()=>{
  const h=harness();h.input.value='散热器';const action=h.start.onclick();
  h.requests[0].resolve({research_id:'b'.repeat(32)});await tick();
  h.state.machine={...h.state.machine,machine_id:'other'};h.location.hash='#trackunit-asset=other';h.window.syncXGSSResearch();
  h.requests[1].resolve({url:'https://xgss.xcmg.com/'});await action;
  assert.equal(h.messages.some(m=>m.type==='jilian:research-start'),false);
});
test('stop unlocks input and ignores late saved pages',async()=>{
  const h=harness();await h.launch();
  const saving=h.send({type:'jilian:research-page',request_id:'b'.repeat(32),asset_id:'asset',dataset_id:'a'.repeat(64),page_id:'p',capture:{}});
  h.stop.onclick();h.requests[2].resolve({pages:[],evidence:{parts:[],manuals:[]}});await saving;
  assert.equal(h.input.disabled,false);assert.equal(h.stop.hidden,true);
  assert.equal(h.messages.some(m=>m.type==='jilian:research-ack'),false);
});
test('AI search terms must belong to current machine and dataset',()=>{
  const h=harness(),use=h.nodes.find(n=>n.textContent==='采用当前 AI 检索词');
  h.sandbox.report={machine_id:'other',dataset_id:'a'.repeat(64)};use.onclick();assert.equal(h.input.value,'');
  h.sandbox.report={machine_id:'asset',dataset_id:'a'.repeat(64)};use.onclick();assert.equal(h.input.value,'散热器');
});

test('resume ignores a late record after switching devices',async()=>{
  const h=harness(),resume=h.nodes.find(n=>n.textContent==='恢复上次资料排查');
  const action=resume.onclick();assert.equal(resume.disabled,true);
  assert.equal(h.requests[0].url,'/assistant/xgss/research/latest');
  h.state.machine={...h.state.machine,machine_id:'other'};h.window.syncXGSSResearch();
  h.requests[0].resolve({symptom:'old device',plan:{summary:'stale'}});await action;
  assert.notEqual(h.nodes.find(n=>n.id==='research-symptom').value,'old device');
  assert.equal(resume.disabled,false);
});

test('local equipment evidence never calls a model and ignores a changed device',async()=>{
  const h=harness(),button=h.nodes.find(n=>n.textContent==='查看设备证据');
  const action=button.onclick();assert.equal(h.requests[0].url,'/assistant/xgss/research/machine-context');
  h.state.machine={...h.state.machine,machine_id:'other'};h.window.syncXGSSResearch();
  h.requests[0].resolve({context:{sample_count:999}});await action;
  assert.equal(h.nodes.some(n=>n.textContent.includes('999 条')),false);
  assert.equal(h.requests.length,1);
});

test('restored AI evidence retains the saved snapshot and old reports do not claim current data',async()=>{
  const h=harness(),resume=h.nodes.find(n=>n.textContent==='恢复上次资料排查');
  const old={research_id:'b'.repeat(32),symptom:'模拟温升现象',symptom_source:'simulation',plan:{summary:'模拟计划',directions:[]},pages:[],evidence:{parts:[],manuals:[]}};
  let action=resume.onclick();h.requests[0].resolve(old);await action;
  assert.ok(h.nodes.some(n=>n.textContent.includes('本次资料排查未包含设备观测')));
  action=resume.onclick();h.requests[1].resolve({...old,machine_context:{as_of:'2026-09-21T12:00:00Z',source:'trackunit_cache',sample_count:3,faults:[],metrics:{
    operating_hours:{value:123.5,unit:'h',observed_at:'2020-01-01T12:00:00Z',stale_after_24h:true},idle_hours:{value:null},fuel_remaining_percent:{value:null}
  }}});await action;
  assert.ok(h.nodes.some(n=>n.textContent==='本次 AI 使用的设备证据'));
  assert.ok(h.nodes.some(n=>n.textContent.includes('123.5 h · 2020-01-01T12:00:00Z · 历史采样')));
  assert.ok(h.nodes.some(n=>n.textContent.includes('不能据此判断无故障')));
  assert.equal(h.requests.length,2);
});

test('result cards translate AI vocabulary but preserve part identifiers and official quotations',async()=>{
  const h=harness(),resume=h.nodes.find(n=>n.textContent==='恢复上次资料排查');
  const original='手册原文：quantity 是本文件中的字段名，不得改写。';
  const part={source_id:'part-1',name:'测试风扇',part_number:'TEST-001',assembly_path:['冷却系统'],figure_ref:'4',quantity:'1',page_title:'测试图册',captured_at:'2026-09-20T10:00:00Z'};
  const data={research_id:'b'.repeat(32),revision:1,analysis_revision:1,pages:[{}],symptom:'模拟温升现象',symptom_source:'simulation',
    plan:{summary:'模拟 machine_context 分析',directions:[{component:'风扇',reason:'核对 observed_at',search_terms:['风扇']}]},
    machine_context:{as_of:'2026-09-21T12:00:00Z',source:'trackunit_cache',sample_count:0,faults:[],metrics:{
      operating_hours:{value:null},idle_hours:{value:null},fuel_remaining_percent:{value:null}}},
    evidence:{parts:[part],manuals:[{source_id:'manual-1',title:'测试手册',text:original}]},
    advice:{summary:'模拟 fault_coverage=unknown；空燃油余量。图册 quantity 需核对。也不能补造温度、压力、维修周期或实时测量；未提供手册，因此不给出拆装、带压检测、扭矩或阈值类官方步骤，仅提供保守检查方向。禁止带压拆卸，必须停机泄压。',
      parts:[{...part,reason:'fault_coverage=unknown，需核验',replacement_condition:'现场检查确认损坏后再核对配置。'}],
      repair_steps:[{basis:'manual_excerpt',instruction:original,source_quote:original,source_id:'manual-1'}],missing_evidence:['补充 observed_at']}};
  const action=resume.onclick();h.requests[0].resolve(data);await action;
  assert.ok(h.nodes.some(n=>n.textContent==='1 项备件候选'));
  assert.ok(h.nodes.some(n=>n.textContent==='TEST-001'));
  assert.ok(h.nodes.some(n=>n.textContent.includes('故障记录覆盖范围未知；未采集到有效燃油余量')));
  // The original appears once in the step quote, plus once in its source entry.
  const manualStep=h.nodes.find(n=>n.tag==='li'&&n.children.some(c=>c.tag==='blockquote'));
  assert.equal(manualStep.children.filter(n=>n.textContent===original).length,1);
  assert.ok(h.nodes.some(n=>n.tag==='blockquote'&&n.textContent===original));
  assert.equal(h.nodes.some(n=>n.textContent.includes('fault_coverage')),false);
  const plan=h.nodes.find(n=>n.tag==='details'&&n.children.some(c=>c.textContent==='AI 检索方向 · 1 项'));
  assert.equal(plan.open,false);
  const reasons=h.nodes.find(n=>n.tag==='details'&&n.children.some(c=>c.textContent==='匹配理由与更换条件'));
  assert.equal(reasons.open,false);
  assert.ok(h.nodes.some(n=>n.textContent==='现场检查确认损坏后再核对配置。'));
  assert.ok(h.nodes.some(n=>n.textContent.includes('温度、压力和维修周期需另行核实')));
  assert.ok(h.nodes.some(n=>n.textContent.includes('具体维修步骤和参数需查阅适用手册')));
  assert.ok(h.nodes.some(n=>n.textContent.includes('禁止带压拆卸，必须停机泄压。')));
  assert.equal(h.nodes.some(n=>/不能补造|仅提供保守检查方向/.test(n.textContent)),false);
  assert.ok(data.advice.summary.includes('也不能补造温度'));
});

test('restoring a report keeps direct collection available without a plugin and labels the optional backup',async()=>{
  const h=harness({ready:false}),resume=h.nodes.find(n=>n.textContent==='恢复上次资料排查');
  const action=resume.onclick();h.requests[0].resolve({research_id:'b'.repeat(32),symptom:'模拟温升现象',symptom_source:'simulation',
    plan:{summary:'模拟计划',directions:[]},pages:[],evidence:{parts:[],manuals:[]}});await action;
  assert.equal(h.start.disabled,false);
  assert.match(h.nodes.find(n=>n.id==='research-capture-state').textContent,/无需连接 Chrome 插件/);
  h.send({type:'jilian:research-ready'});
  assert.equal(h.start.disabled,false);
  assert.match(h.nodes.find(n=>n.id==='research-capture-state').textContent,/插件可作为备用读取/);
});

test('report handoff preserves edited user input and rejects an unsaved or mismatched report',async()=>{
  const h=harness(),handoff=h.nodes.find(n=>n.id==='research-handoff'),symptom=h.nodes.find(n=>n.id==='research-symptom');
  for(const overrides of [{machine_id:'other'},{dataset_id:'other'},{record_id:undefined}]){
    h.sandbox.report={machine_id:'asset',dataset_id:'a'.repeat(64),record_id:'f'.repeat(64),...overrides};await handoff.onclick();
    assert.equal(h.requests.length,0);
  }
  symptom.value='人工记录的现象，待核实';symptom.oninput();
  h.sandbox.report={machine_id:'asset',dataset_id:'a'.repeat(64),record_id:'f'.repeat(64)};await handoff.onclick();
  assert.equal(symptom.value,'人工记录的现象，待核实');
  assert.equal(h.requests.length,0);
});

test('continuing an unchanged restored plan collects without another AI plan request',async()=>{
  const h=harness(),resume=h.nodes.find(n=>n.textContent==='恢复上次资料排查');
  const action=resume.onclick();h.requests[0].resolve({research_id:'b'.repeat(32),symptom:'模拟温升现象',symptom_source:'simulation',
    plan:{summary:'模拟计划',directions:[{component:'风扇',reason:'检查风扇',search_terms:['风扇']}]},pages:[],evidence:{parts:[],manuals:[]}});await action;
  const continuing=h.nodes.find(n=>n.textContent==='查找备件与维修资料').onclick();
  assert.equal(h.requests[1].url,'/assistant/xgss/open');
  h.requests[1].resolve({url:'https://xgss.xcmg.com/'});await continuing;
  assert.equal(h.requests.length,2);
  assert.ok(h.messages.some(m=>m.type==='jilian:research-start'&&m.terms[0]==='风扇'));
});

test('editing the symptom invalidates plan reuse before collecting old sources',async()=>{
  const h=harness(),resume=h.nodes.find(n=>n.textContent==='恢复上次资料排查');
  const action=resume.onclick();h.requests[0].resolve({research_id:'b'.repeat(32),symptom:'模拟温升现象',symptom_source:'simulation',
    plan:{summary:'模拟计划',directions:[]},pages:[],evidence:{parts:[],manuals:[]}});await action;
  h.nodes.find(n=>n.id==='research-symptom').value='新现象：启动无响应';
  h.nodes.find(n=>n.id==='research-symptom').oninput();
  h.start.onclick();
  assert.equal(h.requests.length,1,'changed symptoms cannot collect under the previous plan');
  h.sandbox.AbortController=AbortController;
  h.sandbox.fetch=async(url,options)=>{h.requests.push({url,options});return {ok:false,json:async()=>({detail:'测试中止模型调用'})};};
  await h.nodes.find(n=>n.textContent==='查找备件与维修资料').onclick();
  assert.equal(h.requests[1].url,'/assistant/xgss/research/plan');
  assert.equal(JSON.parse(h.requests[1].options.body).symptom,'新现象：启动无响应');
  assert.equal(h.messages.some(m=>m.type==='jilian:research-start'),false);
});

test('a different machine or dataset cannot inherit the previous symptom and its source',()=>{
  const h=harness(),symptom=h.nodes.find(n=>n.id==='research-symptom'),source=h.nodes.find(n=>n.id==='research-symptom-source');
  symptom.value='设备 A 人工报告：启动无响应';source.value='operator_report';
  h.window.syncXGSSResearch();assert.equal(symptom.value,'设备 A 人工报告：启动无响应','same-device refresh preserves input');
  h.state.machine={...h.state.machine,machine_id:'other'};h.window.syncXGSSResearch();
  assert.equal(symptom.value,'');assert.equal(source.value,'simulation');
  symptom.value='新版本尚未确认的现象';source.value='operator_report';
  h.state.machine={...h.state.machine,dataset_id:'c'.repeat(64)};h.window.syncXGSSResearch();
  assert.equal(symptom.value,'');assert.equal(source.value,'simulation');assert.equal(h.requests.length,0);
});

test('changing phenomenon or origin hides stale AI conclusions and source display while retaining the saved record',async()=>{
  const h=harness(),resume=h.nodes.find(n=>n.textContent==='恢复上次资料排查');
  const symptom=h.nodes.find(n=>n.id==='research-symptom'),source=h.nodes.find(n=>n.id==='research-symptom-source');
  const action=resume.onclick();h.requests[0].resolve({research_id:'b'.repeat(32),revision:1,analysis_revision:1,
    symptom:'模拟温升现象',symptom_source:'simulation',pages:[{}],
    plan:{summary:'旧现象的检索判断',directions:[]},evidence:{parts:[],manuals:[]},
    advice:{summary:'旧现象的维修建议',parts:[],repair_steps:[],missing_evidence:[]}});await action;
  const card=h.nodes.find(n=>n.id==='xgss-research');
  const visibleText=n=>n.hidden?'':n.textContent+' '+n.children.map(visibleText).join(' ');
  assert.match(visibleText(card),/旧现象的维修建议/);
  symptom.value='人工描述的新现象：无法启动';symptom.oninput();
  assert.doesNotMatch(visibleText(card),/旧现象的维修建议|旧现象的检索判断/);
  assert.match(visibleText(card),/已更改/);
  assert.doesNotMatch(visibleText(card),/已读取 1 页/);
  symptom.value='模拟温升现象';symptom.oninput();
  assert.match(visibleText(card),/旧现象的维修建议|已读取 1 页/);
  source.value='operator_report';source.onchange();
  assert.doesNotMatch(visibleText(card),/旧现象的维修建议|旧现象的检索判断/);
  assert.equal(h.requests.length,1,'editing does not silently invoke a model or discard saved sources');
});

test('explicit replan creates a new plan for the same phenomenon instead of reusing an overfull collection',async()=>{
  const h=harness(),resume=h.nodes.find(n=>n.textContent==='恢复上次资料排查');
  const action=resume.onclick();h.requests[0].resolve({research_id:'b'.repeat(32),symptom:'模拟温升现象',symptom_source:'simulation',
    plan:{summary:'原检索计划',directions:[]},pages:[{}],evidence:{parts:[],manuals:[]}});await action;
  const replan=h.nodes.find(n=>n.textContent==='重新生成检索计划');assert.equal(replan.hidden,false);
  h.sandbox.AbortController=AbortController;
  h.sandbox.fetch=async(url,options)=>{h.requests.push({url,options});return {ok:false,json:async()=>({detail:'测试中止模型调用'})};};
  await replan.onclick();
  assert.equal(h.requests[1].url,'/assistant/xgss/research/plan');
  assert.equal(JSON.parse(h.requests[1].options.body).symptom,'模拟温升现象');
  assert.equal(h.requests.some(r=>r.url==='/assistant/xgss/open'),false);
});

function illustratedRecord(){
  const capture='c'.repeat(64),image='d'.repeat(64);
  const part={source_id:`xpart:${capture}:0`,capture_id:capture,name:'风扇',part_number:'800160318',figure_ref:'4',assembly_path:['冷却系统']};
  return {research_id:'b'.repeat(32),revision:1,analysis_revision:1,analyzed_at:'2026-09-22T03:00:00Z',symptom:'模拟温升现象',symptom_source:'simulation',
    plan:{summary:'模拟计划',directions:[]},pages:[{capture_id:capture,content:{assembly_path:['冷却系统']},
      illustrations:[{image_id:image,title:'冷却系统',document_ref:'3944450.svg',width:1200,height:900,captured_at:'2026-09-22T03:00:00Z'}]}],
    evidence:{parts:[part],manuals:[]},advice:{summary:'模拟排查',parts:[{...part,reason:'检查风扇',replacement_condition:'核对后更换'}],repair_steps:[],missing_evidence:[]}};
}

test('parts use only their exact source page illustration and never an arbitrary image URL',async()=>{
  const h=harness(),data=illustratedRecord();
  data.advice.parts.push({...data.advice.parts[0],capture_id:'e'.repeat(64),name:'其他分类零件'});
  data.advice.parts.push({...data.advice.parts[0],capture_id:undefined,name:'来源不完整'});
  data.pages.push({capture_id:'f'.repeat(64),illustrations:[{image_id:'https://example.com/leak.png'}]});
  const action=h.nodes.find(n=>n.textContent==='恢复上次资料排查').onclick();h.requests[0].resolve(data);await action;
  const cards=h.nodes.filter(n=>n.className==='engineering-hypothesis');
  assert.equal(cards[0].children.filter(n=>n.tag==='figure').length,1);
  assert.equal(cards[1].children.filter(n=>n.tag==='figure').length,0);
  assert.equal(cards[2].children.filter(n=>n.tag==='figure').length,0);
  const images=h.nodes.filter(n=>n.tag==='img');assert.equal(images.length,2,'one candidate preview plus one source gallery image');
  assert.ok(images.every(i=>i.src===`/assistant/xgss/research/${data.research_id}/images/${'d'.repeat(64)}`));
  assert.ok(h.nodes.some(n=>n.textContent==='图中序号 4 · 冷却系统'));
});

test('diagram opens with the part reference, zooms and closes on device change',async()=>{
  const h=harness(),data=illustratedRecord();
  const action=h.nodes.find(n=>n.textContent==='恢复上次资料排查').onclick();h.requests[0].resolve(data);await action;
  const preview=h.nodes.find(n=>n.className==='research-diagram-open'&&n.attributes['aria-label'].includes('序号 4'));preview.onclick();
  const dialog=h.nodes.find(n=>n.tag==='dialog');assert.equal(dialog.open,true);
  assert.ok(dialog.children.some(n=>n.textContent==='风扇 · 800160318 · 图中序号 4'));
  const viewport=h.nodes.find(n=>n.className==='research-image-viewport'),image=viewport.children[0];
  h.nodes.find(n=>n.textContent==='放大').onclick();assert.equal(image.style.width,'150%');
  h.nodes.find(n=>n.textContent==='适合窗口').onclick();assert.equal(image.style.width,'100%');
  h.state.machine={...h.state.machine,machine_id:'other'};h.window.syncXGSSResearch();
  assert.equal(dialog.open,false);assert.equal(dialog.removed,true);
});

test('broken illustration explains the missing image without hiding grounded text',async()=>{
  const h=harness(),data=illustratedRecord();
  const action=h.nodes.find(n=>n.textContent==='恢复上次资料排查').onclick();h.requests[0].resolve(data);await action;
  h.nodes.find(n=>n.tag==='img').onerror();
  assert.ok(h.nodes.some(n=>n.tag==='figcaption'&&n.textContent.includes('图示暂时无法读取')));
  assert.ok(h.nodes.some(n=>n.textContent==='800160318'));
  assert.ok(h.nodes.some(n=>n.textContent==='匹配理由与更换条件'));
});

test('current device gallery loads local images without restoring historical AI or a symptom',async()=>{
  const data={...illustratedRecord(),machine_id:'asset',dataset_id:'a'.repeat(64),vin:'XUGTEST000000001'};
  const h=harness({fetchDiagrams:async()=>({ok:true,json:async()=>data})});await tick();
  assert.ok(h.nodes.some(n=>n.textContent==='当前设备图册'));
  assert.equal(h.nodes.find(n=>n.id==='research-symptom').value,'');
  assert.equal(h.nodes.some(n=>n.textContent==='1 项备件候选'),false);
  assert.equal(h.nodes.filter(n=>n.tag==='img').length,1);
  assert.equal(h.requests.length,0);
});

test('late device-gallery lookup and mismatched VIN never display another device image',async()=>{
  let resolve;const pending=new Promise(r=>resolve=r);
  const h=harness({fetchDiagrams:()=>pending});h.state.machine={...h.state.machine,machine_id:'other'};h.window.syncXGSSResearch();
  resolve({ok:true,json:async()=>({...illustratedRecord(),machine_id:'asset',dataset_id:'a'.repeat(64),vin:'XUGTEST000000001'})});await tick();
  assert.equal(h.nodes.some(n=>n.tag==='img'),false);
  const mismatch=harness({fetchDiagrams:async()=>({ok:true,json:async()=>({...illustratedRecord(),machine_id:'asset',dataset_id:'a'.repeat(64),vin:'OTHER0000000001'})})});await tick();
  assert.equal(mismatch.nodes.some(n=>n.tag==='img'),false);
});

// Exercise the real app flow renderer together with the real research module.
// Model responses are controlled SSE fixtures; no network or model is called.
function streamedRecord(record){
  let sent=false;
  return {ok:true,body:{getReader:()=>({
    read:async()=>sent?{done:true}:(sent=true,{done:false,value:new TextEncoder().encode('data: '+JSON.stringify({type:'result',record})+'\n\n')}),
    releaseLock(){}
  })}};
}
function streamedFailure(kind,message=kind){
  let sent=false;
  return {ok:true,body:{getReader:()=>({read:async()=>sent?{done:true}:(sent=true,{done:false,value:new TextEncoder().encode('data: '+JSON.stringify({type:'error',kind,message})+'\n\n')}),releaseLock(){}})}};
}
function controlledModels(h){
  const calls=[];
  h.sandbox.fetch=(url,options)=>{
    if(['/assistant/xgss/research/latest','/assistant/xgss/research/active'].includes(url)||url.startsWith('/assistant/fault-events'))return Promise.resolve({ok:false,status:404});
    if(url.endsWith('/collect-direct'))return Promise.resolve(streamedFailure('direct_unavailable'));
    return new Promise(resolve=>calls.push({url,options,resolve:record=>resolve(streamedRecord(record))}));
  };
  return calls;
}
function controlledModelErrors(h){
  const calls=[];
  h.sandbox.fetch=(url,options)=>{
    if(['/assistant/xgss/research/latest','/assistant/xgss/research/active'].includes(url)||url.startsWith('/assistant/fault-events'))return Promise.resolve({ok:false,status:404});
    if(url.endsWith('/collect-direct'))return Promise.resolve(streamedFailure('direct_unavailable'));
    return new Promise(resolve=>calls.push({url,options,
      result:record=>resolve(streamedRecord(record)),
      fail:(kind='schema_validation',message='schema_validation: directions[0] value_error')=>{
        let sent=false;
        resolve({ok:true,body:{getReader:()=>({read:async()=>sent?{done:true}:(sent=true,{done:false,value:new TextEncoder().encode('data: '+JSON.stringify({type:'error',kind,message})+'\n\n')}),releaseLock(){}})}});
      }}));
  };
  return calls;
}
function researchInputs(h){
  return {symptom:h.nodes.find(n=>n.id==='research-symptom'),source:h.nodes.find(n=>n.id==='research-symptom-source'),
    begin:h.nodes.find(n=>n.textContent==='查找备件与维修资料'),analyze:h.nodes.find(n=>n.textContent==='更新备件与维修建议')};
}
async function restoreResearch(h,record){
  const action=h.nodes.find(n=>n.textContent==='恢复上次资料排查').onclick();
  h.requests.at(-1).resolve(record);await action;
}
const connectedFlow={connect:'done',diagnose:'active',verify:''};
const plannedFlow={connect:'done',diagnose:'done',verify:'active'};
const completeFlow={connect:'done',diagnose:'done',verify:'done'};

test('flow follows a new research plan, collected sources, and the completed current AI advice',async()=>{
  const h=harness({flowTrack:true}),models=controlledModels(h),ui=researchInputs(h);
  assert.deepEqual(h.flowState(),connectedFlow);
  const advice=illustratedRecord();
  const plan={...advice,revision:0,analysis_revision:undefined,pages:[],advice:undefined,evidence:{parts:[],manuals:[]},
    plan:{summary:'检查冷却系统',directions:[{component:'风扇',reason:'核对冷却风量',search_terms:['风扇']}]}};
  ui.symptom.value=plan.symptom;ui.symptom.oninput();
  const starting=ui.begin.onclick();
  assert.equal(models[0].url,'/assistant/xgss/research/plan');
  assert.deepEqual(h.flowState(),connectedFlow,'a pending plan does not complete AI diagnosis');
  models[0].resolve(plan);await tick();
  assert.deepEqual(h.flowState(),connectedFlow,'a saved plan is not current before activation succeeds');
  assert.equal(h.requests[0].url,'/assistant/xgss/research/'+plan.research_id+'/activate');
  assert.deepEqual(JSON.parse(h.requests[0].options.body),{machine_id:'asset',dataset_id:'a'.repeat(64),vin:'XUGTEST000000001',expected_research_id:null});
  assert.equal(h.messages.some(m=>m.type==='jilian:research-start'),false);
  h.requests[0].resolve(plan);await tick();
  assert.deepEqual(h.flowState(),plannedFlow);
  assert.equal(h.requests[1].url,'/assistant/xgss/open');
  h.requests[1].resolve({url:'https://xgss.xcmg.com/'});await starting;
  const captured={...advice,advice:undefined,analysis_revision:undefined,plan:plan.plan};
  const saving=h.send({type:'jilian:research-page',request_id:plan.research_id,asset_id:'asset',dataset_id:'a'.repeat(64),page_id:'page',capture:{}});
  h.requests[2].resolve(captured);await saving;
  assert.deepEqual(h.flowState(),plannedFlow,'parts and diagrams alone do not complete the advice step');
  const finishing=h.send({type:'jilian:research-done',request_id:plan.research_id,asset_id:'asset',dataset_id:'a'.repeat(64),result:{status:'completed'}});
  assert.equal(models[1].url,'/assistant/xgss/research/'+plan.research_id+'/analyze');
  assert.deepEqual(h.flowState(),plannedFlow,'the second AI request must actually finish');
  models[1].resolve({...advice,plan:plan.plan});await finishing;
  assert.deepEqual(h.flowState(),completeFlow);
});

test('flow does not count cached diagrams or a manual source-only collection as AI completion',async()=>{
  const data={...illustratedRecord(),machine_id:'asset',dataset_id:'a'.repeat(64),vin:'XUGTEST000000001'};
  const h=harness({flowTrack:true,fetchDiagrams:async()=>({ok:true,json:async()=>data})});await tick();
  assert.ok(h.nodes.some(n=>n.tag==='img'),'the current device gallery really loaded');
  assert.deepEqual(h.flowState(),connectedFlow);
  await h.launch();
  const saving=h.send({type:'jilian:research-page',request_id:data.research_id,asset_id:'asset',dataset_id:'a'.repeat(64),page_id:'page',capture:{}});
  h.requests[2].resolve({...data,plan:undefined,advice:undefined,analysis_revision:undefined});await saving;
  await h.send({type:'jilian:research-done',request_id:data.research_id,asset_id:'asset',dataset_id:'a'.repeat(64),result:{status:'completed'}});
  assert.deepEqual(h.flowState(),connectedFlow,'collecting real source pages is not the AI research result');
});

test('flow falls back when research phenomenon or source changes despite an older ordinary report',async()=>{
  const h=harness({flowTrack:true}),data=illustratedRecord(),ui=researchInputs(h);
  h.sandbox.report={machine_id:'asset',dataset_id:'a'.repeat(64),parts_candidates:[{source_id:'xgss:old'}]};
  await restoreResearch(h,data);assert.deepEqual(h.flowState(),completeFlow);
  ui.symptom.value='新的现象：发动机无法启动';ui.symptom.oninput();
  assert.deepEqual(h.flowState(),connectedFlow,'an unrelated ordinary report cannot override edited research');
  ui.symptom.value=data.symptom;ui.symptom.oninput();assert.deepEqual(h.flowState(),completeFlow);
  ui.source.value='operator_report';ui.source.onchange();assert.deepEqual(h.flowState(),connectedFlow);
  ui.source.value=data.symptom_source;ui.source.onchange();assert.deepEqual(h.flowState(),completeFlow);
  ui.symptom.value='';ui.symptom.oninput();assert.deepEqual(h.flowState(),connectedFlow);
  assert.equal(h.requests.length,1,'editing completion state does not issue AI or collection requests');
});

test('flow requires advice for the exact integer source revision and a nonempty source collection',async()=>{
  for(const overrides of [
    {advice:undefined}, {pages:[]}, {revision:2,analysis_revision:1},
    {revision:undefined,analysis_revision:undefined}, {revision:'1',analysis_revision:'1'},
    {revision:1.5,analysis_revision:1.5}
  ]){
    const h=harness({flowTrack:true});await restoreResearch(h,{...illustratedRecord(),...overrides});
    assert.deepEqual(h.flowState(),plannedFlow,'incomplete or stale advice cannot mark source verification done');
  }
});

test('flow ignores a late AI plan after switching the device or its data version',async()=>{
  for(const field of ['machine_id','dataset_id']){
    const h=harness({flowTrack:true}),models=controlledModels(h),ui=researchInputs(h);
    ui.symptom.value='模拟温升现象';ui.symptom.oninput();const action=ui.begin.onclick();
    h.state.machine={...h.state.machine,[field]:field==='machine_id'?'other':'c'.repeat(64)};
    if(field==='machine_id')h.location.hash='#trackunit-asset=other';
    h.window.syncXGSSResearch();
    models[0].resolve({...illustratedRecord(),advice:undefined,pages:[]});await action;
    assert.deepEqual(h.flowState(),connectedFlow,field+' switching must discard late progress');
    assert.equal(h.requests.length,0,'a stale plan cannot start a source collection');
    assert.equal(h.window.currentXGSSResearchProgress(),null);
  }
});

test('flow ignores late AI advice after switching the device or its data version',async()=>{
  for(const field of ['machine_id','dataset_id']){
    const h=harness({flowTrack:true}),models=controlledModels(h),ui=researchInputs(h);
    await restoreResearch(h,{...illustratedRecord(),advice:undefined,analysis_revision:undefined});
    const action=ui.analyze.onclick();assert.equal(models.length,1);
    h.state.machine={...h.state.machine,[field]:field==='machine_id'?'other':'c'.repeat(64)};
    if(field==='machine_id')h.location.hash='#trackunit-asset=other';
    h.window.syncXGSSResearch();models[0].resolve(illustratedRecord());await action;
    assert.deepEqual(h.flowState(),connectedFlow,field+' switching must discard late completed advice');
    assert.equal(h.window.currentXGSSResearchProgress(),null);
  }
});

test('flow needs loaded data for the platform device, not just a UUID in the URL',()=>{
  const h=harness({flowTrack:true});
  h.state.machine=null;h.location.hash='#trackunit-asset=00000000-0000-0000-0000-000004760361';
  h.window.syncXGSSResearch();
  assert.deepEqual(h.flowState(),{connect:'active',diagnose:'',verify:''});
  h.state.machine={machine_id:'other',dataset_id:'a'.repeat(64),serial_number:'XUGTEST000000002',model:'XC948U',provenance:'user_supplied'};
  h.window.syncXGSSResearch();
  assert.deepEqual(h.flowState(),{connect:'active',diagnose:'',verify:''},'loaded data for another device is not association');
});

test('ordinary report flow remains supported only for the selected device and data version',()=>{
  const h=harness({flowTrack:true});
  h.sandbox.report={machine_id:'asset',dataset_id:'a'.repeat(64),parts_candidates:[]};
  h.sandbox.updateFlowTrack();assert.deepEqual(h.flowState(),plannedFlow);
  h.sandbox.report.xgss_catalog_context={};h.sandbox.updateFlowTrack();assert.deepEqual(h.flowState(),completeFlow);
  delete h.sandbox.report.xgss_catalog_context;h.sandbox.report.parts_candidates=[{provenance:'xgss_visible_dom'}];
  h.sandbox.updateFlowTrack();assert.deepEqual(h.flowState(),completeFlow);
  for(const overrides of [{machine_id:'other'},{dataset_id:'c'.repeat(64)},{dataset_id:null}]){
    h.sandbox.report={machine_id:'asset',dataset_id:'a'.repeat(64),parts_candidates:[{source_id:'xgss:old'}],...overrides};
    h.sandbox.updateFlowTrack();assert.deepEqual(h.flowState(),connectedFlow);
  }
  h.sandbox.report={machine_id:'asset',dataset_id:'a'.repeat(64),parts_candidates:[{source_id:'xgss:old'}]};
  const ui=researchInputs(h);ui.symptom.value='即将查找的新现象';ui.symptom.oninput();
  assert.deepEqual(h.flowState(),connectedFlow,'new research input takes ownership before its first plan request');
});

function activeRecord(overrides={}){
  return {...illustratedRecord(),machine_id:'asset',dataset_id:'a'.repeat(64),vin:'XUGTEST000000001',...overrides};
}
function visibleText(n){return n.hidden?'':n.textContent+' '+n.children.map(visibleText).join(' ');}

function focusedPartRecord(overrides={}){
  return activeRecord({symptom_source:'trackunit_page',symptom:'Trackunit 页面可见故障：SPN 444 / FMI 1，SA 163；描述：Battery Potential。',...overrides});
}
function treeNodes(node){return [node,...node.children.flatMap(treeNodes)];}

test('focused parts: restores saved page fault cards and exact images without AI or long legacy sections',async()=>{
  const saved=focusedPartRecord();const base=saved.advice.parts[0];
  saved.advice={...saved.advice,parts:[],inspection_targets:[0,1,2].map(index=>({...base,part_number:'REAL-'+index,name:'核查部件'+index,evidence_level:'inspection_only'})),
    repair_steps:[{instruction:'不得出现在主页的维修长文',basis:'ai_inspection_suggestion'}],missing_evidence:['不得出现在主页的缺证清单']};
  const mounts=[];const h=harness({focused:true,partsFocus:true,estimates:{mount:(root,options)=>{mounts.push(options);return {destroy(){}};}},fetchActive:async()=>faultReply(saved)});await tick();
  const cards=h.nodes.filter(node=>node.className==='fault-parts-card');assert.equal(cards.length,3);
  for(const card of cards){assert.equal(card.children.filter(node=>node.tag==='figure').length,1);assert.ok(treeNodes(card).some(node=>node.textContent==='查看依据'&&node.tag==='summary'));}
  const screen=visibleText(h.nodes.find(node=>node.id==='xgss-research'));
  assert.doesNotMatch(screen,/不得出现在主页|维修与检查顺序|备件准备邮件|当前设备图册|查看已提取/);
  assert.match(screen,/SPN 444/);assert.match(screen,/故障相关配件 · 3 项/);
  assert.equal(h.nodes.find(node=>node.id==='research-input-panel').open,false);
  assert.equal(mounts.length,1);assert.equal(mounts[0].parts.length,3);assert.equal(mounts[0].scope,'current');
  assert.equal(h.requests.length,0);assert.equal(h.fetchCalls.some(call=>/\/plan|\/analyze/.test(call.url)),false);
});

test('focused parts: unknown page status is separate from current and resolved history remains selectable',async()=>{
  const h=harness({focused:true,partsFocus:true});await tick();
  const faults=[{code:'SPN 444 / FMI 1',spn:444,fmi:1,sa:163,description:'Battery input',status:'OPEN',displayed_at:'Sep 24, 2026'},
    {code:null,spn:null,fmi:null,sa:null,description:'Transmission / Abnormal Update Rate',status:'CLOSED',displayed_at:'Jun 29, 2026'},
    {code:'E100',spn:null,fmi:null,sa:null,description:'Unverified observation',status:'UNKNOWN',displayed_at:'Sep 23, 2026'}];
  h.send({type:'jilian:trackunit-page-faults',asset_id:'asset',dataset_id:'a'.repeat(64),capture:{schema_version:1,source:'trackunit_visible_events_page',asset_id:'asset',
    capture_status:'visible_fault_cards',coverage:'rendered_events_only',observed_at:new Date().toISOString(),faults}});
  const picker=h.nodes.find(node=>node.id==='fault-parts-picker');
  assert.ok(treeNodes(picker).some(node=>node.textContent==='当前故障 1'));
  assert.ok(treeNodes(picker).some(node=>node.textContent==='历史故障 1'));
  assert.ok(treeNodes(picker).some(node=>node.textContent==='状态待核实 · 1 条'));
  const main=h.nodes.find(node=>node.id==='research-run');assert.equal(main.disabled,true,'no event is automatically selected or analyzed');
  treeNodes(picker).find(node=>node.textContent==='历史故障 1').onclick();
  const history=treeNodes(picker).find(node=>node.className==='fault-parts-fault'&&treeNodes(node).some(child=>child.textContent==='变速箱通信异常'));
  history.onclick();assert.equal(main.disabled,false);assert.equal(main.textContent,'生成配件推荐');
  assert.equal(h.nodes.find(node=>node.id==='research-fault-event').value,'page:1');assert.equal(h.requests.length,0);
});

test('focused parts: filters a sensor result but preserves the server active ID for the next activation',async()=>{
  const prior=activeRecord({research_id:'e'.repeat(32),symptom_source:'user_question',symptom:'连续传感器趋势分析：6项核查方向'});
  const h=harness({focused:true,partsFocus:true,ready:false,fetchActive:async()=>faultReply(prior)});await tick();
  assert.equal(h.nodes.find(node=>node.id==='research-result-hero').hidden,true);
  assert.equal(h.nodes.filter(node=>node.className==='fault-parts-card').length,0);
  const symptom=h.nodes.find(node=>node.id==='research-symptom');symptom.value='SPN 639 / FMI 9 通信异常';symptom.oninput();
  const models=controlledModels(h),action=h.nodes.find(node=>node.id==='research-run').onclick();
  const next=focusedPartRecord({research_id:'f'.repeat(32),symptom_source:'operator_report',symptom:symptom.value,advice:undefined,pages:[],analysis_revision:undefined});
  models[0].resolve(next);await tick();
  assert.equal(JSON.parse(h.requests[0].options.body).expected_research_id,prior.research_id);
  h.requests[0].resolve(next);await action;
});

test('focused parts: manual fault references remain supported even with user_question provenance',async()=>{
  const saved=focusedPartRecord({symptom_source:'user_question',symptom:'查询E4030',manual_fault:{code:'E4030',model:'XC948U',version:'test',applicability_confirmed:true}});
  const h=harness({focused:true,partsFocus:true,fetchActive:async()=>faultReply(saved)});await tick();
  assert.equal(h.nodes.find(node=>node.id==='research-result-hero').hidden,false);
  assert.equal(h.nodes.filter(node=>node.className==='fault-parts-card').length,1);
});

test('focused parts: resume rejects maintenance and free sensor questions without replacing the current fault result',async()=>{
  const saved=focusedPartRecord(),h=harness({focused:true,partsFocus:true,fetchActive:async()=>faultReply(saved)});await tick();
  for(const invalid of [maintenanceRecord(),activeRecord({symptom_source:'user_question',symptom:'传感器检查建议'})]){
    const action=h.nodes.find(node=>node.textContent==='恢复上次资料排查').onclick();h.requests.at(-1).resolve(invalid);await action;
    assert.equal(h.nodes.find(node=>node.id==='research-result-hero').hidden,false);
    assert.match(visibleText(h.nodes.find(node=>node.id==='fault-parts-picker')),/SPN 444/);
  }
});

test('focused parts: pending source collection keeps a single usable XGSS action',async()=>{
  const saved=focusedPartRecord({advice:undefined,pages:[],evidence:{parts:[],manuals:[]},analysis_revision:undefined,
    plan:{summary:'核对通信回路',directions:[{component:'线束',reason:'通信故障',search_terms:['线束']}]}});
  const h=harness({focused:true,partsFocus:true,fetchActive:async()=>faultReply(saved)});await tick();
  const action=h.nodes.find(node=>node.id==='research-run');
  assert.equal(action.hidden,false);assert.equal(action.disabled,false);assert.equal(action.textContent,'继续读取 XGSS 并推荐配件');
  assert.equal(h.requests.length,0,'source collection waits for the one explicit main action');
  const pending=action.onclick();await tick();assert.equal(h.requests[0].url,'/assistant/xgss/open');
  h.requests[0].resolve({url:'https://xgss.xcmg.com/'});await pending;
  assert.ok(h.messages.some(message=>message.type==='jilian:research-start'));
  h.stop.onclick();
});

test('focused parts: changing a fault or dataset destroys its estimate and hides the old cards',async()=>{
  let destroyed=0;const saved=focusedPartRecord();
  const h=harness({focused:true,partsFocus:true,estimates:{mount:()=>({destroy(){destroyed++;}})},fetchActive:async()=>faultReply(saved)});await tick();
  assert.equal(h.nodes.find(node=>node.id==='fault-parts-estimates').hidden,false);
  const symptom=h.nodes.find(node=>node.id==='research-symptom');symptom.value='SPN 2664 / FMI 3';symptom.oninput();
  assert.equal(destroyed,1);assert.equal(h.nodes.find(node=>node.id==='fault-parts-estimates').hidden,true);
  assert.equal(h.nodes.find(node=>node.id==='research-result-hero').hidden,true);
  h.state.machine={...h.state.machine,dataset_id:'c'.repeat(64)};h.window.syncXGSSResearch();
  assert.equal(h.nodes.find(node=>node.id==='fault-parts-estimates').hidden,true);
});

test('focused parts: group switches hide the other group result and estimate without losing its saved selection',async()=>{
  let mounts=0,destroyed=0;const saved=focusedPartRecord();
  const h=harness({focused:true,partsFocus:true,estimates:{mount:()=>{mounts++;return {destroy(){destroyed++;}};}},fetchActive:async()=>faultReply(saved)});await tick();
  const picker=h.nodes.find(node=>node.id==='fault-parts-picker'),hero=h.nodes.find(node=>node.id==='research-result-hero'),estimate=h.nodes.find(node=>node.id==='fault-parts-estimates');
  const card=h.nodes.find(node=>node.id==='xgss-research');assert.ok(card.children.indexOf(estimate)>card.children.indexOf(hero));
  assert.equal(hero.hidden,false);assert.match(visibleText(hero),/SPN 444/);
  treeNodes(picker).find(node=>/^历史故障 /.test(node.textContent)).onclick();
  assert.equal(hero.hidden,true);assert.equal(estimate.hidden,true);assert.equal(h.nodes.find(node=>node.id==='research-run').disabled,true);
  treeNodes(picker).find(node=>/^当前故障 /.test(node.textContent)).onclick();
  assert.equal(hero.hidden,false);assert.equal(estimate.hidden,false);assert.equal(mounts,1);assert.equal(destroyed,0);
  assert.match(visibleText(hero),/SPN 444/);assert.equal(h.requests.length,0);
});

test('focused parts: excluding a sensor research link removes only the stale research query and dataset binding',async()=>{
  const prior=activeRecord({research_id:'e'.repeat(32),symptom_source:'user_question',symptom:'连续传感器趋势分析'});
  const h=harness({focused:true,partsFocus:true,search:'?panel=connection&research='+'e'.repeat(32)+'&dataset='+'a'.repeat(64),fetchLinked:async()=>faultReply(prior)});
  const links=[];h.window.history={replaceState:(_data,_title,url)=>links.push(url)};await tick();
  assert.ok(links.length);assert.doesNotMatch(links.at(-1),/research=|dataset=/);
  assert.match(links.at(-1),/panel=connection/);assert.match(links.at(-1),/#trackunit-asset=asset/);
  assert.equal(h.nodes.find(node=>node.id==='research-result-hero').hidden,true);
});

test('focused parts: filtered links resolve the actual active record and never use the linked ID for activation',async()=>{
  const linked=activeRecord({research_id:'e'.repeat(32),symptom_source:'user_question',symptom:'连续传感器趋势分析'});
  for(const active of [focusedPartRecord({research_id:'c'.repeat(32)}),activeRecord({research_id:'d'.repeat(32),symptom_source:'user_question',symptom:'另一项传感器研究'})]){
    const h=harness({focused:true,partsFocus:true,ready:false,search:'?panel=connection&research='+linked.research_id+'&dataset='+'a'.repeat(64),
      fetchLinked:async()=>faultReply(linked),fetchActive:async()=>faultReply(active)});
    await tick();
    assert.equal(h.fetchCalls.filter(call=>call.url==='/assistant/xgss/research/active').length,1);
    assert.equal(h.nodes.find(node=>node.id==='research-result-hero').hidden,active.symptom_source==='user_question');
    if(active.symptom_source==='trackunit_page')assert.match(visibleText(h.nodes.find(node=>node.id==='research-result-hero')),/SPN 444/);
    assert.equal(h.requests.length,0,'restoration reads saved results without requesting AI');
    const symptom=h.nodes.find(node=>node.id==='research-symptom');
    h.nodes.find(node=>node.id==='research-symptom-source').value='operator_report';symptom.value='SPN 639 / FMI 9 通信异常';symptom.oninput();
    const models=controlledModels(h),action=h.nodes.find(node=>node.id==='research-run').onclick();
    const next=focusedPartRecord({research_id:'f'.repeat(32),symptom_source:'operator_report',symptom:symptom.value,advice:undefined,pages:[],analysis_revision:undefined});
    models[0].resolve(next);await tick();
    assert.equal(JSON.parse(h.requests[0].options.body).expected_research_id,active.research_id);
    h.requests[0].resolve(next);await action;
  }
});

test('focused parts: foreground reload of the same research preserves the chosen history tab and hides current estimates',async()=>{
  let mounts=0;const saved=focusedPartRecord();
  const h=harness({focused:true,partsFocus:true,estimates:{mount:()=>{mounts++;return {destroy(){}};}},fetchActive:async()=>faultReply(saved)});await tick();
  const picker=h.nodes.find(node=>node.id==='fault-parts-picker'),hero=h.nodes.find(node=>node.id==='research-result-hero'),estimate=h.nodes.find(node=>node.id==='fault-parts-estimates');
  treeNodes(picker).find(node=>/^历史故障 /.test(node.textContent)).onclick();
  await h.listeners.focus();await tick();
  assert.equal(treeNodes(picker).find(node=>/^历史故障 /.test(node.textContent)).attributes['aria-selected'],'true');
  assert.equal(hero.hidden,true);assert.equal(estimate.hidden,true);
  assert.equal(h.nodes.find(node=>node.id==='research-run').disabled,true);
  treeNodes(picker).find(node=>/^当前故障 /.test(node.textContent)).onclick();
  assert.equal(hero.hidden,false);assert.equal(estimate.hidden,false);assert.match(visibleText(hero),/SPN 444/);
  assert.equal(mounts,1);assert.equal(h.requests.length,0);
});

test('fault attribution keeps saved SPN FMI SA when another communication fault is visible',async()=>{
  const saved=activeRecord({symptom_source:'trackunit_page',symptom:'Trackunit 当前 Events 页可见故障：SPN 444 / FMI 1，SA 163；描述：Battery Potential / Power Input 2；页面显示时间：Jul 20, 2026, 11:20 AM。'});
  const h=harness({focused:true,fetchActive:async()=>({ok:true,json:async()=>saved})});await tick();
  const hero=h.nodes.find(n=>n.id==='research-result-hero');
  const fault={code:'SPN 639 / FMI 9',spn:639,fmi:9,sa:160,description:'J1939 Network communication',severity:'Critical',displayed_at:'Sep 24, 2026'};
  h.send({type:'jilian:trackunit-page-faults',asset_id:'asset',dataset_id:'a'.repeat(64),capture:{schema_version:1,source:'trackunit_visible_events_page',asset_id:'asset',capture_status:'visible_fault_cards',observed_at:new Date().toISOString(),faults:[fault]}});
  assert.match(visibleText(hero),/本次故障：SPN 444 \/ FMI 1 · SA 163/);
  assert.match(visibleText(hero),/Battery Potential \/ Power Input 2/);
  assert.doesNotMatch(visibleText(hero),/SPN 639|SA 160|J1939/);
  const banner=h.nodes.find(n=>n.id==='research-page-fault-banner');
  assert.match(visibleText(banner),/下方已保存结果仅针对 SPN 444 \/ FMI 1 · SA 163/);
  banner.children.find(n=>n.className==='research-page-fault-actions').children[0].onclick();
  assert.equal(hero.hidden,true,'selecting communication fault must conceal the old power result');
  assert.doesNotMatch(visibleText(h.nodes.find(n=>n.id==='xgss-research')),/本次故障：SPN 444/);
  assert.match(h.nodes.find(n=>n.id==='research-symptom').value,/SPN 639 \/ FMI 9/);
  assert.equal(saved.symptom.includes('SPN 444'),true,'the saved result is retained unchanged');
});

test('fault attribution does not invent a single identity from multiple saved fault codes',async()=>{
  const saved=activeRecord({symptom_source:'operator_report',symptom:'人工报告 SPN 444 / FMI 1，SA 163；另有 SPN 639 / FMI 9，SA 160。'});
  const h=harness({focused:true,fetchActive:async()=>({ok:true,json:async()=>saved})});await tick();
  const hero=visibleText(h.nodes.find(n=>n.id==='research-result-hero'));
  assert.match(hero,/本次故障：已保存的多项故障现象/);
  assert.doesNotMatch(hero,/本次故障：SPN 444/);
});

test('inspection targets retain exact diagrams with zero prepared parts and no mail action',async()=>{
  const saved=activeRecord({symptom_source:'trackunit_page',symptom:'Trackunit 当前 Events 页可见故障：SPN 639 / FMI 9，SA 160；描述：J1939 Network communication；页面显示时间：Sep 24, 2026。'});
  const base=saved.advice.parts[0];
  saved.advice={...saved.advice,parts:[],inspection_targets:[0,1,2].map(index=>({...base,name:'待核查线束'+index,part_number:'HARNESS-'+index,evidence_level:'inspection_only',reason:'先核对该线束是否经过故障节点。',replacement_condition:'核对回路和端子，并确认部件异常后再决定。'}))};
  const h=harness({focused:true,fetchActive:async()=>({ok:true,json:async()=>saved})});await tick();
  const hero=visibleText(h.nodes.find(n=>n.id==='research-result-hero'));
  assert.match(hero,/3 项优先核查 · 0 项条件性备件/);
  assert.match(hero,/查看核查部件、图册与检查建议/);
  const cards=h.nodes.filter(n=>n.className==='engineering-hypothesis');
  assert.equal(cards.length,3);
  for(const [index,card] of cards.entries()){
    assert.match(visibleText(card),new RegExp('HARNESS-'+index));
    assert.match(visibleText(card),/先检查，暂不列入备件准备|核查后再决定/);
    assert.equal(card.children.filter(n=>n.tag==='figure').length,1);
    assert.doesNotMatch(visibleText(card),/考虑更换的条件/);
  }
  assert.equal(h.nodes.find(n=>n.id==='research-email-preview').hidden,true);
  assert.doesNotMatch(visibleText(h.nodes.find(n=>n.id==='xgss-research')),/本次没有足够依据推荐具体料号/);
  assert.equal(saved.advice.parts.length,0,'rendering must not promote targets into prepared parts');
});

test('inspection targets are counted separately from conditional candidates',async()=>{
  const saved=activeRecord();const base=saved.advice.parts[0];
  saved.advice={...saved.advice,parts:[{...base,evidence_level:'conditional_candidate'}],inspection_targets:[{...base,name:'核查线束',evidence_level:'inspection_only'}]};
  const h=harness({focused:true,fetchActive:async()=>({ok:true,json:async()=>saved})});await tick();
  assert.match(visibleText(h.nodes.find(n=>n.id==='research-result-hero')),/1 项优先核查 · 1 项条件性备件/);
  assert.equal(h.nodes.find(n=>n.id==='research-email-preview').hidden,false);
  const cards=h.nodes.filter(n=>n.className==='engineering-hypothesis');
  assert.equal(cards.length,2);
  assert.doesNotMatch(visibleText(cards[0]),/先检查，暂不列入备件准备/);
  assert.match(visibleText(cards[1]),/先检查，暂不列入备件准备/);
});

test('inspection-only legacy entries cannot masquerade as prepared parts',async()=>{
  const saved=activeRecord();saved.advice.parts[0].evidence_level='inspection_only';
  const h=harness({focused:true,fetchActive:async()=>({ok:true,json:async()=>saved})});await tick();
  assert.match(visibleText(h.nodes.find(n=>n.id==='research-result-hero')),/1 项优先核查 · 0 项条件性备件/);
  assert.equal(h.nodes.find(n=>n.id==='research-email-preview').hidden,true);
});

test('historical candidates show diagrams, provenance and preparation conditions without mail or current repair claims',async()=>{
  const observation={asset_id:'asset',source_url:'https://new.manager.trackunit.com/assets/asset/events',observed_at:'2026-09-24T12:00:00Z',
    description:'Transmission / Manufacturer assignable SPN / Abnormal Update Rate',code:'',spn:null,fmi:null,sa:null,status:'CLOSED',
    occurred_at:'June 29, 2026, 9:06 AM',cleared_at:'',page_event_id:null};
  const saved=activeRecord({symptom_source:'trackunit_page',symptom:'历史已解除变速箱通信异常',fault_context:{trackunit_page:observation}});
  const base=saved.advice.parts[0];
  saved.advice={...saved.advice,analysis_scope:'historical',parts:[],inspection_targets:[],historical_candidates:[{...base,
    name:'历史线束候选',part_number:'HISTORY-HARNESS',evidence_level:'historical_reference',reason:'历史通信异常：核对总线段与端子',
    replacement_condition:'复发并确认对应回路异常，核对VIN适配后决定备库。'}]};
  const h=harness({focused:true,fetchActive:async()=>faultReply(saved)});await tick();
  const hero=visibleText(h.nodes.find(n=>n.id==='research-result-hero'));
  assert.match(hero,/历史故障备件参考/);assert.match(hero,/1 项历史备件候选/);assert.match(hero,/已解除/);
  const card=h.nodes.find(n=>n.className==='engineering-hypothesis');
  assert.match(visibleText(card),/HISTORY-HARNESS/);assert.match(visibleText(card),/复发并确认对应回路异常/);
  assert.ok(card.children.some(n=>n.tag==='figure'));assert.ok(card.children.some(n=>n.textContent==='查看图册依据'));
  assert.equal(h.nodes.find(n=>n.id==='research-email-preview').hidden,true);
  assert.equal(h.nodes.find(n=>n.id==='research-fault-event').value,'page:saved');
  assert.equal(h.requests.some(r=>/email/.test(r.url)),false);
});

test('choosing a resolved visible history row binds original status and identity and does not invent an SPN',async()=>{
  const h=harness({focused:true});const asset='00000000-0000-0000-0000-000004760361';
  h.state.machine={...h.state.machine,machine_id:asset};h.location.hash='#trackunit-asset='+asset;h.window.syncXGSSResearch();
  const capture={schema_version:1,source:'trackunit_visible_events_page',source_url:`https://new.manager.trackunit.com/assets/${asset}/events`,asset_id:asset,
    capture_status:'visible_fault_cards',coverage:'rendered_events_only',observed_at:new Date().toISOString(),faults:[{
      code:null,spn:null,fmi:null,sa:null,description:'Transmission / Manufacturer assignable SPN / Abnormal Update Rate',status:'CLOSED',
      displayed_at:'June 29, 2026, 9:06 AM',cleared_at:'',page_event_id:'visible-history-row-1'}]};
  h.send({type:'jilian:trackunit-page-faults',asset_id:asset,dataset_id:'a'.repeat(64),capture});
  const select=h.nodes.find(n=>n.id==='research-fault-event');
  assert.equal(select.value,'','a resolved event is never an automatic active-fault choice');
  select.value='page:0';select.onchange();
  assert.equal(h.nodes.find(n=>n.id==='research-run').textContent,'历史故障备件参考');
  const models=controlledModels(h),action=h.nodes.find(n=>n.id==='research-run').onclick();
  const body=JSON.parse(models[0].options.body);
  assert.equal(body.page_fault.asset_id,asset);assert.equal(body.page_fault.status,'CLOSED');
  assert.equal(body.page_fault.description,capture.faults[0].description);
  assert.equal(body.page_fault.spn,null);assert.equal(body.page_fault.fmi,null);assert.equal(body.page_fault.code,'');
  assert.equal(body.page_fault.page_event_id,'visible-history-row-1');assert.equal(body.fault_event_id,undefined);
  assert.equal(body.page_fault.occurred_at,'June 29, 2026, 9:06 AM');assert.equal(body.symptom_source,'trackunit_page');
  assert.equal(body.symptom,'','the authoritative page observation is separate from an optional operator supplement');
  h.stop.onclick();models[0].resolve(activeRecord());await action;
});

test('restored page history replans with only allowed observation fields and the original operator supplement',async()=>{
  const page={asset_id:'asset',source_url:'https://new.manager.trackunit.com/assets/asset/events',observed_at:'2026-09-24T12:00:00Z',
    description:'Transmission / Abnormal Update Rate',code:'',spn:null,fmi:null,sa:null,status:'CLOSED',occurred_at:'Jun 29, 2026',cleared_at:null,page_event_id:null,
    source:'trackunit_visible_events_page',coverage:'selected_visible_event_only'};
  const saved=activeRecord({symptom_source:'trackunit_page',symptom:'SERVER GENERATED HISTORICAL FACTS',fault_context:{trackunit_page:page,operator_supplement:'在雨后出现过'}});
  const h=harness({focused:true,fetchActive:async()=>faultReply(saved)});await tick();
  assert.equal(h.nodes.find(n=>n.id==='research-symptom').value,'在雨后出现过');
  const models=controlledModels(h),action=h.nodes.find(n=>n.id==='research-run').onclick({force:true});
  const body=JSON.parse(models[0].options.body);
  assert.equal(body.symptom,'在雨后出现过');assert.equal(body.page_fault.status,'CLOSED');
  assert.equal(body.page_fault.source,undefined);assert.equal(body.page_fault.coverage,undefined);
  assert.equal(body.page_fault.cleared_at,null);assert.equal(body.page_fault.spn,null);
  h.stop.onclick();models[0].resolve(saved);await action;
});

test('a new active card hides historical candidates and a repeated capture does not rebind the saved observation',async()=>{
  const observation={asset_id:'asset',source_url:'https://new.manager.trackunit.com/assets/asset/events',observed_at:'2026-09-24T12:00:00Z',
    description:'Transmission communication history',code:'',spn:null,fmi:null,sa:null,status:'CLOSED',occurred_at:'Jun 29, 2026',cleared_at:'',page_event_id:null};
  const saved=activeRecord({symptom_source:'trackunit_page',symptom:'历史通信异常',fault_context:{trackunit_page:observation}});
  saved.advice={...saved.advice,analysis_scope:'historical',parts:[],historical_candidates:[saved.advice.parts[0]],inspection_targets:[]};
  const h=harness({focused:true,fetchActive:async()=>faultReply(saved)});await tick();
  const hero=h.nodes.find(n=>n.id==='research-result-hero');assert.equal(hero.hidden,false);
  const capture={schema_version:1,source:'trackunit_visible_events_page',asset_id:'asset',capture_status:'visible_fault_cards',coverage:'rendered_events_only',
    observed_at:new Date().toISOString(),faults:[{code:'SPN 444 / FMI 1',spn:444,fmi:1,sa:163,status:'OPEN',description:'Battery potential',displayed_at:'Sep 24, 2026'}]};
  h.send({type:'jilian:trackunit-page-faults',asset_id:'asset',dataset_id:'a'.repeat(64),capture});
  assert.equal(hero.hidden,false);assert.equal(h.nodes.find(n=>n.id==='research-fault-event').value,'page:saved');
  const select=h.nodes.find(n=>n.id==='research-fault-event');select.value='page:0';select.onchange();
  assert.equal(hero.hidden,true);assert.doesNotMatch(h.nodes.find(n=>n.id==='research-run').textContent,/历史/);
});

function freshFaultState(overrides={}){
  const checked_at=new Date(Date.now()-1000).toISOString();
  return {machine_id:'asset',dataset_id:'a'.repeat(64),vin:'XUGTEST000000001',trackunit_asset_id:'asset',
    status:'data',http_status:200,coverage:'queried_window',checked_at,
    events:[{event_id:'e'.repeat(64),machine_id:'asset',trackunit_asset_id:'asset',vin:'XUGTEST000000001',
      code:'E4030',description:'通信异常',status:'OPEN',occurred_at:checked_at,observed_at:checked_at,source:'trackunit_asset_event_v3'}],...overrides};
}
const faultReply=data=>({ok:true,json:async()=>data});

const pollTimer=h=>h.timers.filter(t=>!t.cleared&&t.delay===1800000).at(-1);
const runPoll=async h=>{const timer=pollTimer(h);assert.ok(timer);timer.cleared=true;await timer.callback();};
const emptyFaultState=()=>freshFaultState({status:'empty',events:[],auto_sync:{status:'cached',reason:'recent_attempt'}});

test('automatic fault reads use bounded sync on open and at the next interval without duplicating bridge handshakes',async()=>{
  const h=harness({focused:true,fetchFaults:async()=>faultReply(emptyFaultState())});await tick();
  const initial=h.fetchCalls.filter(r=>r.url==='/assistant/fault-events/sync');
  assert.equal(initial.length,1);assert.equal(initial[0].options.method,'POST');
  assert.deepEqual(JSON.parse(initial[0].options.body),{machine_id:'asset',dataset_id:'a'.repeat(64),vin:'XUGTEST000000001'});
  h.send({type:'jilian:research-ready'});h.send({type:'jilian:research-ready'});
  assert.equal(h.fetchCalls.filter(r=>r.url==='/assistant/fault-events/sync').length,1);
  await runPoll(h);assert.equal(h.fetchCalls.filter(r=>r.url==='/assistant/fault-events/sync').length,2);
  assert.equal(h.fetchCalls.some(r=>r.url.endsWith('/refresh')||r.url.endsWith('/plan')),false);
  assert.equal(h.timers.filter(t=>!t.cleared&&t.delay===1800000).length,1);
});

test('opening an unfinished joystick investigation resumes same-VIN XGSS collection once and maps AI terms to catalog assemblies',async()=>{
  const plan=activeRecord({symptom:'操纵杆 Theta 轴电压过高，待核实',symptom_source:'operator_report',
    revision:0,analysis_revision:undefined,pages:[],advice:undefined,evidence:{parts:[],manuals:[]},
    plan:{summary:'检查操纵杆信号',directions:[
      {component:'操纵杆位置传感器',reason:'电压异常',search_terms:['操纵杆','Theta 轴位置传感器']},
      {component:'线束接插件',reason:'排查短路',search_terms:['线束','接插件']}]}});
  const h=harness({focused:true,ready:false,fetchActive:async()=>faultReply(plan)});await tick();
  assert.equal(h.nodes.find(n=>n.id==='research-run').textContent,'查询 XGSS 并推荐备件');
  assert.equal(h.requests.length,0,'reopening must not repeat the paid AI planning pass');
  h.send({type:'jilian:research-ready'});await tick();
  assert.equal(h.requests[0].url,'/assistant/xgss/open');
  h.requests[0].resolve({url:'https://xgss.xcmg.com/'});await tick();
  const handoff=h.messages.find(m=>m.type==='jilian:research-start');
  assert.ok(handoff);
  assert.deepEqual(Array.from(handoff.terms.slice(0,4)),['驾驶室系统','操纵模块','电气系统','驾驶室电气']);
  h.send({type:'jilian:research-ready'});await tick();
  assert.equal(h.requests.length,1,'bridge reconnect cannot start duplicate XGSS collection');
});

test('battery power investigation reaches rear-frame electrical assemblies with bounded deduplicated terms',async()=>{
  const plan=activeRecord({symptom:'SPN 444 FMI 1 供电电压低',symptom_source:'operator_report',
    revision:0,analysis_revision:undefined,pages:[],advice:undefined,evidence:{parts:[],manuals:[]},
    plan:{summary:'核对供电回路',directions:[
      {component:'供电回路',reason:'核对低电压',search_terms:['电气系统 电源 蓄电池','battery power supply circuit','power input 2 low voltage','SPN 444 FMI 1']},
      {component:'蓄电池',reason:'检查状态',search_terms:['电气系统 蓄电池','battery','battery voltage low','电气系统']},
      {component:'充电系统',reason:'核对输出',search_terms:['电气系统 充电 发电机','alternator charging system','charging voltage low','发电机']}]}});
  const h=harness({focused:true,ready:false,fetchActive:async()=>faultReply(plan)});await tick();
  h.send({type:'jilian:research-ready'});await tick();
  assert.equal(h.requests[0].url,'/assistant/xgss/open');
  h.requests[0].resolve({url:'https://xgss.xcmg.com/'});await tick();
  const handoff=h.messages.find(m=>m.type==='jilian:research-start');
  assert.ok(handoff);
  assert.deepEqual(Array.from(handoff.terms.slice(0,5)),['电气系统','后车架电气','蓄电池','电源开关','发电机']);
  assert.equal(handoff.terms.length,12);
  assert.equal(new Set(handoff.terms).size,handoff.terms.length);
  assert.ok(handoff.terms.includes('电气系统 电源 蓄电池'),'retain the AI query as well as navigable assembly labels');
  assert.equal(h.requests.some(r=>r.url.endsWith('/plan')),false,'classification does not repeat model planning');
});

test('English battery and charging queries map to the same actual XGSS electrical categories',async()=>{
  for(const query of ['Battery Potential / Power Input 2','alternator charging system']){
    const h=harness();h.input.value=query;const action=h.start.onclick();
    h.requests[0].resolve({research_id:'b'.repeat(32)});await tick();
    h.requests[1].resolve({url:'https://xgss.xcmg.com/'});await action;
    const handoff=h.messages.find(m=>m.type==='jilian:research-start');
    assert.deepEqual(Array.from(handoff.terms),['电气系统','后车架电气','蓄电池','电源开关','发电机',query]);
  }
});

test('hydraulic power searches are not broadened into battery or charging assemblies',async()=>{
  const h=harness();h.input.value='hydraulic power unit';const action=h.start.onclick();
  h.requests[0].resolve({research_id:'b'.repeat(32)});await tick();
  h.requests[1].resolve({url:'https://xgss.xcmg.com/'});await action;
  const handoff=h.messages.find(m=>m.type==='jilian:research-start');
  assert.deepEqual(Array.from(handoff.terms),['hydraulic power unit']);
});

test('an exact linked unfinished investigation resumes XGSS collection after the bridge becomes ready',async()=>{
  const linked=activeRecord({research_id:'c'.repeat(32),symptom:'操纵杆 Theta 轴电压过高',symptom_source:'operator_report',
    revision:0,analysis_revision:undefined,pages:[],advice:undefined,evidence:{parts:[],manuals:[]},
    plan:{summary:'核对操纵模块',directions:[{component:'操纵杆',reason:'电压异常',search_terms:['操纵杆']}]}});
  const h=harness({focused:true,ready:false,search:'?panel=connection&research='+linked.research_id,
    fetchLinked:async()=>({ok:true,json:async()=>linked})});
  await tick();
  assert.equal(h.requests.length,0,'the linked record waits for the Chrome bridge');
  h.send({type:'jilian:research-ready'});await tick();
  assert.equal(h.requests[0].url,'/assistant/xgss/open');
  h.requests[0].resolve({url:'https://xgss.xcmg.com/'});await tick();
  assert.ok(h.messages.some(m=>m.type==='jilian:research-start'&&m.request_id===linked.research_id));
  assert.equal(h.fetchCalls.filter(r=>r.url.endsWith('/active')).length,0,'the exact link is not replaced by another active record');
});

test('automatic fault reads pause in hidden documents and resume when foreground data is due',async()=>{
  const h=harness({focused:true,fetchFaults:async()=>faultReply(emptyFaultState())});await tick();
  h.sandbox.document.visibilityState='hidden';await runPoll(h);
  assert.equal(h.fetchCalls.filter(r=>r.url.endsWith('/sync')).length,1);
  const later=Date.now()+1800001;h.sandbox.Date=class extends Date{static now(){return later;}};
  h.sandbox.document.visibilityState='visible';h.documentListeners.visibilitychange();await tick();
  assert.equal(h.fetchCalls.filter(r=>r.url.endsWith('/sync')).length,2);
  assert.equal(h.timers.filter(t=>!t.cleared&&t.delay===1800000).length,1);
});

test('automatic fault reads skip active analysis and do not poll a previous device',async()=>{
  const h=harness({focused:true,fetchFaults:async()=>faultReply(emptyFaultState())});await tick();
  const models=controlledModels(h),symptom=h.nodes.find(n=>n.id==='research-symptom');
  symptom.value='需要检查通信故障';symptom.oninput();const action=h.nodes.find(n=>n.id==='research-run').onclick();
  await runPoll(h);assert.equal(models.length,1);
  h.stop.onclick();models[0].resolve(activeRecord());await action;
  const old=pollTimer(h),before=h.fetchCalls.length;
  h.state.machine={...h.state.machine,machine_id:'other'};h.window.syncXGSSResearch();
  assert.equal(old.cleared,true);const after=h.fetchCalls.length;await old.callback();
  assert.equal(h.fetchCalls.length,after);assert.ok(after>=before);
});

test('formal fault access warning uses readable time and keeps the Events-page path',async()=>{
  const state=freshFaultState({status:'unauthorized',http_status:401,events:[],
    checked_at:'2026-09-24T01:31:23+00:00',window_start:'2026-09-17T01:31:23+00:00',
    window_end:'2026-09-24T01:31:23+00:00',message:'Trackunit 拒绝故障事件访问，请核对接口授权。'});
  const h=harness({focused:true,fetchFaults:async()=>faultReply(state)});await tick();
  const facts=h.nodes.find(n=>n.className==='muted research-fault-facts');
  assert.match(facts.textContent,/官方故障接口：未授权（HTTP 401）/);
  assert.match(facts.textContent,/Events 页/);
  assert.doesNotMatch(facts.textContent,/T01:31:23|\+00:00|Trackunit 拒绝故障事件访问/);
  assert.equal(h.nodes.find(n=>n.textContent==='权限更新后重试').disabled,false);
  assert.equal(h.nodes.find(n=>n.id==='research-page-fault-read').hidden,false);
  assert.equal(h.fetchCalls.some(r=>r.url.endsWith('/plan')),false);
});

test('automatic fault reads preserve authorization suspension and cannot auto-analyze retained OPEN events',async()=>{
  const h=harness({focused:true,fetchFaults:async()=>faultReply(freshFaultState({auto_sync:{status:'paused',reason:'authorization_required',message:'故障接口授权未恢复，自动读取已暂停。'}}))});await tick();
  assert.equal(h.nodes.find(n=>n.id==='research-fault-event').value,'');
  assert.ok(h.nodes.some(n=>n.textContent==='故障接口授权未恢复，自动读取已暂停。'));
  assert.match(visibleText(h.nodes.find(n=>n.id==='xgss-research')),/故障接口授权未恢复，自动读取已暂停/);
  assert.equal(h.fetchCalls.some(r=>r.url.endsWith('/plan')),false);
  assert.ok(pollTimer(h),'later local checks may observe a successful manual refresh from another workspace');
});

test('automatic fault reads keep explicit refresh distinct and never schedule demo devices',async()=>{
  const h=harness({focused:true,fetchFaults:async()=>faultReply(emptyFaultState())});await tick();
  await h.nodes.find(n=>n.textContent==='重新读取故障接口').onclick();
  assert.equal(h.fetchCalls.filter(r=>r.url.endsWith('/refresh')).length,1);
  h.state.machine={...h.state.machine,machine_id:'demo',provenance:'demo'};h.window.syncXGSSResearch();
  assert.equal(h.timers.filter(t=>!t.cleared&&t.delay===1800000).length,0);
});

test('automatic fault workflow runs from one loaded event through both AI passes and XGSS collection',async()=>{
  const h=harness({ready:false,focused:true,fetchFaults:async()=>faultReply(freshFaultState())});await tick();
  const models=controlledModels(h);
  h.send({type:'jilian:research-ready'});
  assert.equal(models.length,1);
  const request=JSON.parse(models[0].options.body);
  assert.equal(request.automatic,true);assert.equal(request.fault_event_id,'e'.repeat(64));assert.equal(request.symptom,'');
  const result=activeRecord({fault_event_id:'e'.repeat(64),symptom_source:'trackunit_event',fault_context:{operator_supplement:''},
    plan:{summary:'检查通信故障相关部件',directions:[{component:'控制器',reason:'检查连接',search_terms:['控制器']}]}});
  const plan={...result,revision:0,analysis_revision:undefined,pages:[],advice:undefined,evidence:{parts:[],manuals:[]}};
  models[0].resolve(plan);await tick();
  assert.match(h.requests[0].url,/\/activate$/);h.requests[0].resolve(plan);await tick();
  assert.equal(h.requests[1].url,'/assistant/xgss/open');h.requests[1].resolve({url:'https://xgss.xcmg.com/'});await tick();
  assert.ok(h.messages.some(m=>m.type==='jilian:research-start'&&m.request_id===plan.research_id));
  h.send({type:'jilian:research-ready'});assert.equal(models.length,1,'bridge reconnect cannot duplicate first AI call');
  const saved=h.send({type:'jilian:research-page',request_id:plan.research_id,asset_id:'asset',dataset_id:'a'.repeat(64),page_id:'page',capture:{}});
  h.requests[2].resolve({...result,advice:undefined,analysis_revision:undefined});await saved;
  const done=h.send({type:'jilian:research-done',request_id:plan.research_id,asset_id:'asset',dataset_id:'a'.repeat(64),result:{status:'completed'}});
  assert.match(models[1].url,/\/analyze$/);models[1].resolve(result);await done;
  assert.equal(h.window.currentXGSSResearchProgress().verified,true);
  assert.ok(h.nodes.some(n=>n.id==='research-email-preview'));
  assert.equal(h.requests.some(r=>/email-send/.test(r.url)),false,'automatic recommendations never send mail');
});

test('automatic fault workflow respects edits unlink explicit mode stop and device switch before the bridge is ready',async()=>{
  for(const change of ['edit','unlink','mode','stop','device']){
    const h=harness({ready:false,focused:true,fetchFaults:async()=>faultReply(freshFaultState())});await tick();
    const models=controlledModels(h);
    if(change==='edit'){const symptom=h.nodes.find(n=>n.id==='research-symptom');symptom.value='用户自己的补充';symptom.oninput();}
    if(change==='unlink')h.nodes.find(n=>n.textContent==='取消本次关联').onclick();
    if(change==='mode'){const mode=h.nodes.find(n=>n.id==='research-analysis-mode');mode.value='maintenance';mode.onchange();}
    if(change==='stop')h.stop.onclick();
    if(change==='device'){h.state.machine={...h.state.machine,machine_id:'other'};h.window.syncXGSSResearch();}
    h.send({type:'jilian:research-ready'});await tick();assert.equal(models.length,0,change);
  }
});

test('automatic fault workflow stays off in the standalone webpage and does not retry a failed automatic request',async()=>{
  const web=harness({focused:true,search:'',fetchFaults:async()=>faultReply(freshFaultState())});await tick();
  assert.equal(web.fetchCalls.some(r=>r.url.endsWith('/plan')),false);
  assert.equal(web.nodes.find(n=>n.id==='research-fault-event').value,'e'.repeat(64));
  const h=harness({ready:false,focused:true,fetchFaults:async()=>faultReply(freshFaultState())});await tick();
  const calls=[];h.sandbox.fetch=async(url,options)=>{calls.push({url,options});return {ok:false,json:async()=>({detail:'此故障正在另一工作区分析。'})};};
  h.send({type:'jilian:research-ready'});await tick();
  assert.equal(calls.length,1);h.send({type:'jilian:research-ready'});await tick();assert.equal(calls.length,1);
  assert.equal(h.nodes.find(n=>n.id==='research-run').disabled,false,'manual retry remains available');
  assert.ok(h.nodes.some(n=>n.textContent==='此故障正在另一工作区分析。'));
});

test('automatic fault workflow reuses an already completed event result without another collection or AI call',async()=>{
  const h=harness({ready:false,focused:true,fetchFaults:async()=>faultReply(freshFaultState())});await tick();
  const models=controlledModels(h);h.send({type:'jilian:research-ready'});
  const result=activeRecord({fault_event_id:'e'.repeat(64),symptom_source:'trackunit_event',fault_context:{operator_supplement:''}});
  models[0].resolve(result);await tick();h.requests[0].resolve(result);await tick();
  assert.equal(models.length,1);assert.equal(h.requests.length,1);
  assert.equal(h.messages.some(m=>m.type==='jilian:research-start'),false);
  assert.equal(h.window.currentXGSSResearchProgress().verified,true);
});

test('automatic fault workflow can load the winning workspace result on focus without retrying AI',async()=>{
  const h=harness({ready:false,focused:true,fetchFaults:async()=>faultReply(freshFaultState())});await tick();
  let calls=0;
  h.sandbox.fetch=async()=>({ok:true,body:{getReader:()=>({
    read:async()=>calls++?{done:true}:{done:false,value:new TextEncoder().encode('data: '+JSON.stringify({type:'error',kind:'auto_fault_pending',message:'此故障正在另一工作区分析。'})+'\n\n')},releaseLock(){}
  })}});
  h.send({type:'jilian:research-ready'});await tick();
  const result=activeRecord({fault_event_id:'e'.repeat(64),symptom_source:'trackunit_event',fault_context:{operator_supplement:''}});
  h.sandbox.fetch=async url=>{assert.equal(url,'/assistant/xgss/research/active');return faultReply(result);};
  await h.listeners.focus();assert.equal(h.window.currentXGSSResearchProgress().verified,true);
  assert.equal(calls,1);assert.equal(h.requests.length,0);
});

test('automatic fault association waits for both reads and passes the real event into AI without inventing text',async()=>{
  for(const first of ['events','active']){
    let events,active;
    const state=freshFaultState(),h=harness({ready:false,focused:true,fetchFaults:()=>new Promise(done=>events=done),fetchActive:()=>new Promise(done=>active=done)});
    const select=h.nodes.find(n=>n.id==='research-fault-event');
    if(first==='events')events(faultReply(state));else active({ok:false,status:404});
    await tick();assert.equal(select.value,'','one read is not enough');
    if(first==='events')active({ok:false,status:404});else events(faultReply(state));
    await tick();assert.equal(select.value,state.events[0].event_id,first);
    assert.equal(h.nodes.find(n=>n.id==='research-analysis-mode').value,'fault');
    assert.equal(h.nodes.find(n=>n.id==='research-symptom').value,'');
    assert.equal(h.nodes.find(n=>n.id==='research-symptom-source').value,'trackunit_event');
    assert.equal(h.requests.length,0);
    assert.equal(h.fetchCalls.some(r=>/\/refresh|\/plan|\/analyze|\/email/.test(r.url)),false);
    const models=controlledModels(h),action=h.nodes.find(n=>n.id==='research-run').onclick();
    const payload=JSON.parse(models[0].options.body);
    assert.equal(payload.fault_event_id,state.events[0].event_id);assert.equal(payload.symptom,'');assert.equal(payload.symptom_source,'trackunit_event');
    h.stop.onclick();models[0].resolve(activeRecord({fault_event_id:state.events[0].event_id}));await action;
  }
});

test('automatic fault association never replaces a saved investigation in either response order',async()=>{
  for(const first of ['events','active']){
    let events,active;const saved=activeRecord(),h=harness({ready:false,focused:true,fetchFaults:()=>new Promise(done=>events=done),fetchActive:()=>new Promise(done=>active=done)});
    if(first==='events')events(faultReply(freshFaultState()));else active(faultReply(saved));
    await tick();
    if(first==='events')active(faultReply(saved));else events(faultReply(freshFaultState()));
    await tick();assert.equal(h.nodes.find(n=>n.id==='research-symptom').value,saved.symptom);
    assert.equal(h.nodes.find(n=>n.id==='research-fault-event').value,'');
    assert.equal(h.window.currentXGSSResearchProgress().verified,true);
  }
});

test('automatic fault association rejects failed partial stale ambiguous cleared or unverified event data',async()=>{
  const variants=[
    state=>({...state,status:'unauthorized'}),state=>({...state,status:'partial'}),
    state=>({...state,coverage:'unknown'}),state=>({...state,checked_at:new Date(Date.now()-1801000).toISOString()}),
    state=>({...state,checked_at:new Date(Date.now()+60000).toISOString()}),state=>({...state,checked_at:null}),
    state=>({...state,events:[...state.events,{...state.events[0],event_id:'f'.repeat(64)}]}),
    ...[{status:'CLOSED'},{cleared_at:'2026-09-20T10:00:00Z'},{observed_at:'2026-01-01T10:00:00Z'},
      {source:'simulation'},{trackunit_asset_id:'another-asset'},{machine_id:'other'},{vin:'OTHER000000001'}]
      .map(patch=>state=>({...state,events:[{...state.events[0],...patch}]}))
  ];
  for(const [index,variant] of variants.entries()){
    const h=harness({ready:false,focused:true,fetchFaults:async()=>faultReply(variant(freshFaultState()))});await tick();
    assert.equal(h.nodes.find(n=>n.id==='research-fault-event').value,'',String(index));
    assert.equal(h.nodes.find(n=>n.id==='research-symptom-source').value,'operator_report',String(index));
  }
});

test('automatic fault association respects edits mode choice manual fault context and a failed result link',async()=>{
  for(const change of ['text','mode','manual','unlink','link','active-error']){
    let events;
    const h=harness({ready:false,focused:true,search:change==='link'?'?panel=connection&research='+'b'.repeat(32):'?panel=connection',
      fetchActive:async()=>({ok:false,status:change==='active-error'?503:404}),fetchFaults:()=>new Promise(done=>events=done)});
    const symptom=h.nodes.find(n=>n.id==='research-symptom');
    if(change==='text'){symptom.value='用户补充的行走异常';symptom.oninput();}
    if(change==='mode'){const mode=h.nodes.find(n=>n.id==='research-analysis-mode');mode.value='maintenance';mode.onchange();}
    if(change==='manual')h.sandbox.getManualFaultReference=()=>({code:'H10101'});
    if(change==='unlink')h.nodes.find(n=>n.textContent==='取消本次关联').onclick();
    await tick();events(faultReply(freshFaultState()));await tick();
    assert.equal(h.nodes.find(n=>n.id==='research-fault-event').value,'',change);
    if(change==='text')assert.equal(symptom.value,'用户补充的行走异常');
  }
});

test('automatic fault association ignores responses for a previous machine dataset or VIN',async()=>{
  for(const field of ['machine_id','dataset_id','serial_number']){
    const replies=[],h=harness({ready:false,focused:true,fetchFaults:()=>new Promise(done=>replies.push(done))});await tick();
    h.state.machine={...h.state.machine,[field]:field==='dataset_id'?'c'.repeat(64):'OTHER000000001'};h.window.syncXGSSResearch();
    replies[0](faultReply(freshFaultState()));await tick();
    assert.equal(h.nodes.find(n=>n.id==='research-fault-event').value,'',field);
  }
});

test('automatic fault association is not repeated after an explicit unlink and refresh',async()=>{
  const h=harness({ready:false,focused:true,fetchFaults:async()=>faultReply(freshFaultState())});await tick();
  assert.equal(h.nodes.find(n=>n.id==='research-fault-event').value,'e'.repeat(64));
  h.nodes.find(n=>n.textContent==='取消本次关联').onclick();
  await h.nodes.find(n=>n.textContent==='重新读取故障接口').onclick();
  assert.equal(h.nodes.find(n=>n.id==='research-fault-event').value,'');
});

test('automatic fault association waits for a newer focus lookup instead of using the earlier absence',async()=>{
  for(const saved of [true,false]){
    const replies=[];let events;
    const h=harness({ready:false,focused:true,fetchActive:()=>new Promise(done=>replies.push(done)),fetchFaults:()=>new Promise(done=>events=done)});
    replies[0]({ok:false,status:404});await tick();
    const focusing=h.listeners.focus();events(faultReply(freshFaultState()));await tick();
    assert.equal(h.nodes.find(n=>n.id==='research-fault-event').value,'');
    replies[1](saved?faultReply(activeRecord()):{ok:false,status:404});await focusing;
    assert.equal(h.nodes.find(n=>n.id==='research-fault-event').value,saved?'':'e'.repeat(64));
    if(saved)assert.equal(h.window.currentXGSSResearchProgress().verified,true);
  }
});

test('automatic fault association cannot be unlocked by an old active lookup after switching datasets',async()=>{
  const replies=[];const h=harness({ready:false,focused:true,fetchActive:()=>new Promise(done=>replies.push(done)),
    fetchFaults:async()=>faultReply(freshFaultState({dataset_id:replies.length===1?'a'.repeat(64):'c'.repeat(64)}))});
  await tick();h.state.machine={...h.state.machine,dataset_id:'c'.repeat(64)};h.window.syncXGSSResearch();await tick();
  replies[0]({ok:false,status:404});await tick();
  assert.equal(h.nodes.find(n=>n.id==='research-fault-event').value,'');
  replies[1]({ok:false,status:404});await tick();
  assert.equal(h.nodes.find(n=>n.id==='research-fault-event').value,'e'.repeat(64));
});

test('focused fault handling uses a server event without inventing phenomenon text or calling refresh automatically',async()=>{
  const event={event_id:'e'.repeat(64),machine_id:'asset',vin:'XUGTEST000000001',code:'E4030',description:'通信异常',status:'OPEN',occurred_at:'2026-09-22T10:00:00Z'};
  const h=harness({focused:true,fetchFaults:async()=>({ok:true,json:async()=>({machine_id:'asset',dataset_id:'a'.repeat(64),vin:event.vin,status:'data',events:[event]})})});
  await tick();
  assert.equal(h.nodes.find(n=>n.id==='research-symptom-source').value,'operator_report');
  const select=h.nodes.find(n=>n.id==='research-fault-event');assert.equal(select.children.length,2);
  select.value=event.event_id;select.onchange();
  const models=controlledModels(h),action=h.nodes.find(n=>n.id==='research-run').onclick();
  const payload=JSON.parse(models[0].options.body);
  assert.equal(payload.fault_event_id,event.event_id);assert.equal(payload.symptom,'');assert.equal(payload.symptom_source,'trackunit_event');
  assert.equal(payload.manual_fault,undefined);assert.equal(payload.engineering_fault,undefined);
  assert.equal(h.fetchCalls.some(r=>r.url.includes('/fault-events/refresh')),false);
  h.stop.onclick();models[0].resolve(activeRecord({fault_event_id:event.event_id}));await action;
  assert.equal(h.requests.length,0,'stopped event analysis cannot activate or collect');
});

test('fault loading distinguishes an empty window from failed authorization and rejects late cross-device events',async()=>{
  let resolve;const h=harness({focused:true,fetchFaults:()=>new Promise(done=>{resolve=done;})});
  const original=resolve;h.state.machine={...h.state.machine,machine_id:'other',serial_number:'OTHER'};h.window.syncXGSSResearch();
  original({ok:true,json:async()=>({machine_id:'asset',dataset_id:'a'.repeat(64),vin:'XUGTEST000000001',status:'data',events:[{event_id:'e'.repeat(64),machine_id:'asset',vin:'XUGTEST000000001'}]})});await tick();
  assert.equal(h.nodes.find(n=>n.id==='research-fault-event').children.length,1);
  resolve({ok:true,json:async()=>({machine_id:'other',dataset_id:'a'.repeat(64),vin:'OTHER',status:'unauthorized',events:[]})});await tick();
  assert.ok(h.nodes.some(n=>n.textContent.includes('官方故障接口未授权')));
  const empty=harness({fetchFaults:async()=>({ok:true,json:async()=>({machine_id:'asset',dataset_id:'a'.repeat(64),vin:'XUGTEST000000001',status:'empty',events:[]})})});await tick();
  assert.ok(empty.nodes.some(n=>n.textContent.includes('不代表设备无故障')));
});

test('restored event investigations keep server fault facts out of the editable operator supplement',async()=>{
  const h=harness({focused:true,fetchActive:async()=>({ok:true,json:async()=>activeRecord({fault_event_id:'e'.repeat(64),symptom_source:'trackunit_event',
    symptom:'Trackunit E4030 故障事件与人工补充：持续通信报警',fault_context:{operator_supplement:'持续通信报警',trackunit_event:{code:'E4030'}}})})});
  await tick();
  assert.equal(h.nodes.find(n=>n.id==='research-symptom').value,'持续通信报警');
  assert.equal(h.nodes.find(n=>n.id==='research-symptom-source').disabled,true);
  assert.equal(h.window.currentXGSSResearchProgress().verified,true,'the event-backed saved advice remains valid without editing its frozen source facts');
});

test('focused manual fault entry uses the same symptom input and hides process-only controls',()=>{
  const h=harness({focused:true});h.sandbox.getManualFaultReference=()=>({code:'H10101',model:'TV12U',version:'260224',applicability_confirmed:true});
  h.window.focusXGSSResearch('H10101');
  assert.match(h.nodes.find(n=>n.id==='research-symptom').value,/H10101/);
  assert.equal(h.nodes.find(n=>n.id==='research-run').textContent,'分析故障并推荐备件');
  assert.equal(h.nodes.find(n=>n.textContent==='更新备件与维修建议').attributes['data-deferred-feature'],'legacy-research-tools');
  assert.ok(h.nodes.some(n=>n.textContent===' 已关联故障码 H10101。'));
});

test('email remains a preview when not configured and cannot send after the problem changes',async()=>{
  const h=harness();await restoreResearch(h,activeRecord());
  let action=h.nodes.find(n=>n.id==='research-email-preview').onclick();
  assert.match(h.requests.at(-1).url,/\/email-preview$/);
  h.requests.at(-1).resolve({research_id:'b'.repeat(32),analysis_revision:1,analyzed_at:'2026-09-22T03:00:00Z',subject:'备件准备',body:'请核对零件',can_send:false,configured:false,recipients:[],message:'邮件未配置'});await action;
  assert.ok(h.nodes.some(n=>n.textContent==='邮件未配置'),'show the authoritative message once without a duplicate local prefix');
  const body=h.nodes.find(n=>n.className==='research-email-body');assert.equal(body.tabIndex,0);assert.equal(body.attributes.role,'region');assert.match(body.attributes['aria-label'],/邮件正文.*滚动/);
  let send=h.nodes.filter(n=>n.id==='research-email-send').at(-1);assert.equal(send.disabled,true);await send.onclick();
  assert.equal(h.requests.some(r=>r.url.endsWith('/email-send')),false);
  action=h.nodes.find(n=>n.id==='research-email-preview').onclick();
  h.requests.at(-1).resolve({research_id:'b'.repeat(32),analysis_revision:1,analyzed_at:'2026-09-22T03:00:00Z',subject:'备件准备',body:'请核对零件',can_send:true,preview_hash:'preview-v1',recipients:['test@example.invalid']});await action;
  send=h.nodes.filter(n=>n.id==='research-email-send').at(-1);assert.equal(send.disabled,false);
  const symptom=h.nodes.find(n=>n.id==='research-symptom');symptom.value='人工修改后的现象';symptom.oninput();await send.onclick();
  assert.equal(h.requests.some(r=>r.url.endsWith('/email-send')),false,'old preview cannot send after input changes');
});

test('email sends only by explicit click with the preview version and never labels failed or uncertain delivery as sent',async()=>{
  for(const state of ['sent','failed','uncertain']){
    const h=harness();await restoreResearch(h,activeRecord());
    const action=h.nodes.find(n=>n.id==='research-email-preview').onclick();
    h.requests.at(-1).resolve({research_id:'b'.repeat(32),analysis_revision:1,analyzed_at:'2026-09-22T03:00:00Z',subject:'备件准备',body:'条件性准备清单',can_send:true,preview_hash:'v1',recipients:['test@example.invalid']});await action;
    const send=h.nodes.find(n=>n.id==='research-email-send');assert.equal(h.requests.some(r=>r.url.endsWith('/email-send')),false);
    const sending=send.onclick(),request=h.requests.at(-1);assert.match(request.url,/\/email-send$/);
    assert.equal(JSON.parse(request.options.body).preview_hash,'v1');assert.equal(send.disabled,true);
    request.resolve({status:state,can_send:state==='failed'});await sending;
    assert.equal(h.nodes.some(n=>n.textContent==='邮件服务器已接受，送达待确认。'),state==='sent');
    assert.equal(send.disabled,state!=='failed');
  }
});

test('email preview and send preserve backend delivery qualifications instead of adding a success claim',async()=>{
  const h=harness();await restoreResearch(h,activeRecord());
  const action=h.nodes.find(n=>n.id==='research-email-preview').onclick();
  const message='邮件服务器已接受请求；收件箱是否送达尚未确认。';
  h.requests.at(-1).resolve({research_id:'b'.repeat(32),analysis_revision:1,analyzed_at:'2026-09-22T03:00:00Z',subject:'备件准备',body:'清单',notification_status:'sent',message,can_send:true,preview_hash:'v1',recipients:['test@example.invalid']});await action;
  assert.equal(h.nodes.filter(n=>n.textContent===message).length,1);
  const sending=h.nodes.find(n=>n.id==='research-email-send').onclick();h.requests.at(-1).resolve({status:'sent',message,can_send:false});await sending;
  assert.equal(h.nodes.filter(n=>n.textContent===message).length,1);
  assert.equal(h.nodes.some(n=>n.textContent.includes('备件准备邮件已发送')),false);
});

test('late email previews never restore a result for another machine',async()=>{
  const h=harness();await restoreResearch(h,activeRecord());
  const action=h.nodes.find(n=>n.id==='research-email-preview').onclick();
  h.state.machine={...h.state.machine,machine_id:'other'};h.window.syncXGSSResearch();
  h.requests.at(-1).resolve({subject:'OLD-MACHINE-MAIL',body:'old evidence',can_send:true,preview_hash:'old'});await action;
  assert.equal(h.nodes.some(n=>n.textContent==='OLD-MACHINE-MAIL'),false);
});

test('research links load their exact result once without silently substituting the current active investigation',async()=>{
  const linked=activeRecord({research_id:'c'.repeat(32),symptom:'链接对应的原始问题'}),newer=activeRecord({research_id:'d'.repeat(32),symptom:'另一条活动排查'});
  const h=harness({search:'?panel=connection&research='+linked.research_id,fetchLinked:async()=>({ok:true,json:async()=>linked}),fetchActive:async()=>({ok:true,json:async()=>newer})});
  await tick();assert.equal(h.nodes.find(n=>n.id==='research-symptom').value,linked.symptom);
  await h.listeners.focus();assert.equal(h.fetchCalls.filter(r=>r.url.endsWith('/active')).length,0);
  assert.equal(h.requests.some(r=>r.url.endsWith('/activate')),false,'opening a mail link does not mutate the shared active pointer');
  h.state.machine={...h.state.machine,machine_id:'other'};h.location.hash='#trackunit-asset=other';h.window.syncXGSSResearch();await tick();
  assert.equal(h.fetchCalls.filter(r=>r.url.endsWith('/'+linked.research_id)).length,1,'the original link cannot bind later device selection');
});

test('missing or mismatched research links remain explicit failures and preserve any newly entered text',async()=>{
  for(const response of [{ok:false,status:404},{ok:true,json:async()=>activeRecord({machine_id:'other'})}]){
    const h=harness({search:'?panel=connection&research='+'b'.repeat(32),fetchLinked:async()=>response,fetchActive:async()=>({ok:true,json:async()=>activeRecord()})});
    await tick();await h.listeners.focus();assert.equal(h.nodes.find(n=>n.id==='research-symptom').value,'');
    assert.equal(h.fetchCalls.some(r=>r.url.endsWith('/active')),false);
  }
  let resolve;const h=harness({search:'?panel=connection&research='+'b'.repeat(32),fetchLinked:()=>new Promise(done=>resolve=done)});
  const input=h.nodes.find(n=>n.id==='research-symptom');input.value='用户已补充新问题';input.oninput();
  resolve({ok:true,json:async()=>activeRecord()});await tick();assert.equal(input.value,'用户已补充新问题');
});

test('handoff takes the server original question and source, never the AI summary, and carries its saved report into planning',async()=>{
  const h=harness(),ui=researchInputs(h),handoff=h.nodes.find(n=>n.id==='research-handoff');
  const reportId='f'.repeat(64);
  h.sandbox.report={record_id:reportId,machine_id:'asset',dataset_id:'a'.repeat(64),summary:'AI 推测发动机已损坏'};
  const action=handoff.onclick();
  assert.equal(h.requests[0].url,'/assistant/xgss/research/handoff');
  assert.deepEqual(JSON.parse(h.requests[0].options.body),{machine_id:'asset',dataset_id:'a'.repeat(64),vin:'XUGTEST000000001',source_report_id:reportId});
  h.requests[0].resolve({source_report_id:reportId,symptom:'修',symptom_source:'user_question'});await action;
  assert.equal(ui.symptom.value,'修');assert.equal(ui.source.value,'user_question');
  assert.equal(ui.symptom.value.includes('AI 推测'),false);
  assert.equal(h.requests.length,1,'handoff itself does not generate an AI plan');
  const models=controlledModels(h),planning=ui.begin.onclick();
  assert.equal(models.length,1,'a one-character user question is valid');
  assert.deepEqual(JSON.parse(models[0].options.body),{machine_id:'asset',dataset_id:'a'.repeat(64),vin:'XUGTEST000000001',analysis_mode:'fault',symptom:'修',symptom_source:'user_question',source_report_id:reportId});
  h.stop.onclick();models[0].resolve(activeRecord());await planning;
  assert.equal(h.requests.length,1,'a stopped plan cannot activate or collect');
});

test('handoff late replies cannot override a different device or a stopped operation and controls unlock',async()=>{
  for(const change of ['machine_id','dataset_id','stop']){
    const h=harness(),ui=researchInputs(h),handoff=h.nodes.find(n=>n.id==='research-handoff');
    h.sandbox.report={record_id:'f'.repeat(64),machine_id:'asset',dataset_id:'a'.repeat(64)};
    const action=handoff.onclick();assert.equal(handoff.disabled,true);
    if(change==='stop')h.stop.onclick();else{
      h.state.machine={...h.state.machine,[change]:change==='machine_id'?'other':'c'.repeat(64)};
      if(change==='machine_id')h.location.hash='#trackunit-asset=other';
      h.window.syncXGSSResearch();
    }
    h.requests[0].resolve({source_report_id:'f'.repeat(64),symptom:'过期设备的问题',symptom_source:'user_question'});await action;
    assert.equal(ui.symptom.value,'',change);assert.equal(handoff.disabled,false,change);
    assert.equal(ui.symptom.disabled,false,change);assert.equal(h.stop.hidden,true,change);
  }
});

test('short unconfirmed questions do not lower the minimum for simulated or reported symptoms',async()=>{
  for(const source of ['simulation','operator_report']){
    const h=harness(),models=controlledModels(h),ui=researchInputs(h);
    ui.symptom.value='修';ui.source.value=source;await ui.begin.onclick();
    assert.equal(models.length,0);assert.equal(h.requests.length,0);
  }
});

test('activation conflict never opens XGSS or announces the newly generated plan as current',async()=>{
  const h=harness(),models=controlledModels(h),ui=researchInputs(h);
  ui.symptom.value='模拟温升现象';ui.symptom.oninput();const action=ui.begin.onclick();
  models[0].resolve(activeRecord({advice:undefined,pages:[]}));await tick();
  assert.match(h.requests[0].url,/\/activate$/);
  h.requests[0].reject(new Error('当前活动排查已更改，请刷新后继续。'));await action;
  assert.equal(h.requests.some(r=>r.url==='/assistant/xgss/open'),false);
  assert.equal(h.messages.some(m=>m.type==='jilian:research-start'||m.type==='jilian:research-active'&&m.research_id),false);
  assert.equal(ui.symptom.disabled,false);assert.equal(h.stop.hidden,true);
});

test('activation conflict refreshes only the active pointer and lets unchanged user input retry',async()=>{
  const h=harness({ready:false});await tick();
  const models=controlledModels(h),ui=researchInputs(h),fetchModel=h.sandbox.fetch;
  const other=activeRecord({research_id:'f'.repeat(32),symptom:'另一工作区的问题'});
  h.sandbox.fetch=(url,options)=>url==='/assistant/xgss/research/active'?
    Promise.resolve({ok:true,json:async()=>other}):fetchModel(url,options);
  ui.symptom.value='模拟温升现象';ui.symptom.oninput();
  let action=ui.begin.onclick();models[0].resolve(activeRecord({pages:[],advice:undefined}));await tick();
  h.requests[0].reject(new Error('其他工作区已切换活动排查'));await action;
  assert.equal(ui.symptom.value,'模拟温升现象','conflict recovery must not replace the local problem');
  action=ui.begin.onclick();const replacement=activeRecord({research_id:'e'.repeat(32),pages:[],advice:undefined});
  models[1].resolve(replacement);await tick();
  assert.equal(JSON.parse(h.requests[1].options.body).expected_research_id,other.research_id);
  h.requests[1].resolve(replacement);await action;
  assert.ok(h.messages.some(m=>m.type==='jilian:research-active'&&m.research_id===replacement.research_id));
  assert.equal(h.requests.some(r=>r.url==='/assistant/xgss/open'),false);
});

test('new activation supplies the previously active ID and discards late activation after device change',async()=>{
  const prior=activeRecord(),h=harness({fetchActive:async()=>({ok:true,json:async()=>prior})});await tick();
  const ui=researchInputs(h),models=controlledModels(h);
  ui.symptom.value='新的人工问题：检查启动电路';ui.symptom.oninput();const action=ui.begin.onclick();
  const next=activeRecord({research_id:'e'.repeat(32),symptom:ui.symptom.value,advice:undefined,pages:[]});
  models[0].resolve(next);await tick();
  assert.equal(JSON.parse(h.requests[0].options.body).expected_research_id,prior.research_id);
  h.state.machine={...h.state.machine,machine_id:'other'};h.location.hash='#trackunit-asset=other';h.window.syncXGSSResearch();
  h.requests[0].resolve(next);await action;
  assert.equal(h.requests.some(r=>r.url==='/assistant/xgss/open'),false);
  assert.equal(h.messages.some(m=>m.type==='jilian:research-active'&&m.research_id===next.research_id),false);
  assert.equal(ui.symptom.value,'');
});

test('active research restores the exact device investigation on startup and focus without a model call',async()=>{
  let current=activeRecord();
  const h=harness({fetchActive:async()=>({ok:true,json:async()=>current})});await tick();
  const ui=researchInputs(h);
  assert.equal(ui.symptom.value,current.symptom);assert.equal(ui.source.value,current.symptom_source);
  assert.ok(h.nodes.some(n=>n.textContent==='1 项备件候选'));
  assert.ok(h.messages.some(m=>m.type==='jilian:research-active'&&m.research_id===current.research_id&&m.asset_id==='asset'&&m.dataset_id==='a'.repeat(64)));
  const fetch=h.fetchCalls.find(r=>r.url==='/assistant/xgss/research/active');
  assert.equal(fetch.options.method,'POST');
  assert.deepEqual(JSON.parse(fetch.options.body),{machine_id:'asset',dataset_id:'a'.repeat(64),vin:'XUGTEST000000001'});
  current=activeRecord({research_id:'c'.repeat(32),symptom:'同设备其它工作区更新的原始问题',symptom_source:'user_question'});
  await h.listeners.focus();
  assert.equal(ui.symptom.value,current.symptom);
  assert.ok(h.messages.some(m=>m.type==='jilian:research-active'&&m.research_id===current.research_id));
  assert.equal(h.requests.length,0);assert.equal(h.fetchCalls.some(r=>/\/(plan|analyze)$/.test(r.url)),false);
});

test('active research rejects a different machine, version or VIN even if the research ID is valid',async()=>{
  for(const overrides of [{machine_id:'other'},{dataset_id:'c'.repeat(64)},{vin:'OTHER0000000001'}]){
    const h=harness({fetchActive:async()=>({ok:true,json:async()=>activeRecord(overrides)})});await tick();
    assert.equal(researchInputs(h).symptom.value,'');
    assert.equal(h.nodes.some(n=>n.textContent==='1 项备件候选'),false);
    assert.equal(h.messages.some(m=>m.type==='jilian:research-active'&&m.research_id),false);
  }
});

test('late active lookup cannot overwrite edited inputs or an in-flight plan and cannot cross device scope',async()=>{
  for(const change of ['edit','planning','machine_id','dataset_id']){
    let resolve;const pending=new Promise(done=>resolve=done);
    const h=harness({fetchActive:()=>pending}),ui=researchInputs(h);
    let planning,models;
    if(change==='edit'){
      ui.symptom.value='用户正在编辑自己的问题';ui.symptom.oninput();
    }else if(change==='planning'){
      models=controlledModels(h);ui.symptom.value='正在提交的新故障现象';planning=ui.begin.onclick();
    }else{
      h.state.machine={...h.state.machine,[change]:change==='machine_id'?'other':'c'.repeat(64)};
      if(change==='machine_id')h.location.hash='#trackunit-asset=other';h.window.syncXGSSResearch();
    }
    const expected=ui.symptom.value;resolve({ok:true,json:async()=>activeRecord()});await tick();
    assert.equal(ui.symptom.value,expected,change);
    assert.equal(h.nodes.some(n=>n.textContent==='1 项备件候选'),false,change);
    assert.equal(h.messages.some(m=>m.type==='jilian:research-active'&&m.research_id),false,change);
    if(planning){h.stop.onclick();models[0].resolve(activeRecord());await planning;}
  }
});

test('focus does not restore active research over edited inputs',async()=>{
  const h=harness(),ui=researchInputs(h);await tick();
  ui.symptom.value='我正在检查起动电路';ui.symptom.oninput();
  const before=h.fetchCalls.length;await h.listeners.focus();
  assert.equal(h.fetchCalls.length,before);assert.equal(ui.symptom.value,'我正在检查起动电路');
});

test('confirmed catalog fault code is sent only when XGSS reports fault support',async()=>{
  for(const ready of [true,false]){
    const data=activeRecord({catalog_fault_code:'E4030',plan:{summary:'检查通信',directions:[{component:'控制器',reason:'核对通信',search_terms:['控制器']}]}});
    const h=harness({fetchActive:async()=>({ok:true,json:async()=>data})});await tick();
    const action=researchInputs(h).begin.onclick();await tick();
    assert.equal(h.requests[0].url,'/assistant/xgss/status');
    h.requests[0].resolve({fault_ready:ready,catalog_ready:true});await tick();
    assert.equal(h.requests[1].url,'/assistant/xgss/open');
    const body=JSON.parse(h.requests[1].options.body);
    assert.equal(body.fault_code,ready?'E4030':undefined);
    h.requests[1].resolve({url:'https://xgss.xcmg.com/'});await action;
    assert.ok(h.messages.some(m=>m.type==='jilian:research-start'));
  }
});

test('failed fault-manual entry falls back once to the same VIN catalog and explains the source limitation',async()=>{
  const data=activeRecord({catalog_fault_code:'E4030',plan:{summary:'检查通信',directions:[{component:'控制器',reason:'核对通信',search_terms:['控制器']}]}});
  const h=harness({fetchActive:async()=>({ok:true,json:async()=>data})});await tick();
  const action=researchInputs(h).begin.onclick();await tick();
  h.requests[0].resolve({fault_ready:true,catalog_ready:true});await tick();
  assert.equal(JSON.parse(h.requests[1].options.body).fault_code,'E4030');
  h.requests[1].reject(new Error('故障手册入口不可用'));await tick();
  assert.equal(h.requests[2].url,'/assistant/xgss/open');
  const fallback=JSON.parse(h.requests[2].options.body);
  assert.equal(fallback.fault_code,undefined);assert.equal(fallback.vin,data.vin);
  h.requests[2].resolve({url:'https://xgss.xcmg.com/'});await action;
  assert.equal(h.requests.filter(r=>r.url==='/assistant/xgss/open').length,2);
  assert.match(visibleText(h.nodes.find(n=>n.id==='xgss-research')),/故障.*(?:入口|手册).*|(?:改|退).*图册/);
  assert.ok(h.messages.some(m=>m.type==='jilian:research-start'));
});

test('confirmed fault changes invalidate the old plan for code, applicability and engineering configuration',async()=>{
  const manual={code:'H10101',model:'TV12U',version:'260224',applicability_confirmed:true};
  const engineering={code:'E4030',model:'XE55U',configuration:'XE55U.00III',source:'test'};
  for(const [kind,original,replacement] of [
    ['manual_fault',manual,{...manual,code:'H10102'}],
    ['manual_fault',manual,{...manual,version:'260225'}],
    ['manual_fault',manual,{...manual,applicability_confirmed:false}],
    ['engineering_fault',engineering,{...engineering,configuration:'XE55U.00VI'}],
  ]){
    const data=activeRecord({[kind]:original}),h=harness({fetchActive:async()=>({ok:true,json:async()=>data})});await tick();
    assert.equal(h.window.currentXGSSResearchProgress().diagnosed,true);
    h.sandbox.getManualFaultReference=()=>kind==='manual_fault'?replacement:null;
    h.sandbox.getEngineeringFault=()=>kind==='engineering_fault'?replacement:null;
    h.window.syncXGSSResearchFaults();
    assert.equal(h.window.currentXGSSResearchProgress().diagnosed,false,kind+' changed');
    assert.equal(researchInputs(h).symptom.value,data.symptom,'changing fault evidence must not discard the original question');
    await h.start.onclick();assert.equal(h.requests.length,0,'changed fault evidence cannot reuse the old collection plan');
    assert.equal(h.messages.at(-1).research_id,null);
  }
});

test('confirmed fault changes during planning or activation reject the late result and unlock controls',async()=>{
  for(const phase of ['planning','activation']){
    const h=harness(),models=controlledModels(h),ui=researchInputs(h);
    let current={code:'E4030',model:'XE55U',configuration:'XE55U.00III',source:'test'};
    h.sandbox.getEngineeringFault=()=>current;ui.symptom.value='通信异常请核对故障与资料';ui.symptom.oninput();
    const action=ui.begin.onclick(),old=activeRecord({symptom:ui.symptom.value,engineering_fault:{...current}});
    assert.deepEqual(JSON.parse(models[0].options.body).engineering_fault,current);
    if(phase==='activation'){models[0].resolve(old);await tick();assert.match(h.requests[0].url,/\/activate$/);}
    current={...current,configuration:'XE55U.00VI'};h.window.syncXGSSResearchFaults();
    assert.equal(ui.symptom.disabled,false,phase);assert.equal(h.stop.hidden,true,phase);
    if(phase==='planning')models[0].resolve(old);else h.requests[0].resolve(old);
    await action;
    assert.equal(h.requests.some(r=>r.url==='/assistant/xgss/open'),false,phase);
    assert.equal(h.messages.some(m=>m.type==='jilian:research-start'||m.type==='jilian:research-active'&&m.research_id),false,phase);
    assert.equal(h.window.currentXGSSResearchProgress().diagnosed,false,phase);
  }
});

test('unlinking the prior report and fault keeps the original question and replans without either association',async()=>{
  const fault={code:'H10101',model:'TV12U',version:'260224',applicability_confirmed:true};
  const data=activeRecord({source_report_id:'f'.repeat(64),manual_fault:fault,symptom:'左侧行走缓慢怎么办',symptom_source:'user_question'});
  const h=harness({fetchActive:async()=>({ok:true,json:async()=>data})});await tick();
  const ui=researchInputs(h),unlink=h.nodes.find(n=>n.textContent==='取消本次关联');
  h.sandbox.getManualFaultReference=()=>fault;
  assert.equal(unlink.hidden,false);unlink.onclick();
  assert.equal(ui.symptom.value,data.symptom);assert.equal(ui.source.value,'user_question');
  assert.equal(unlink.hidden,true);assert.equal(h.window.currentXGSSResearchProgress().diagnosed,false);
  const models=controlledModels(h),action=ui.begin.onclick(),body=JSON.parse(models[0].options.body);
  assert.equal(body.symptom,data.symptom);assert.equal(body.source_report_id,undefined);
  assert.equal(body.manual_fault,undefined);assert.equal(body.engineering_fault,undefined);
  h.stop.onclick();models[0].resolve(activeRecord());await action;
});

test('maintenance starts from an empty fault workspace without manufacturing a fault or automatically calling AI',async()=>{
  const h=harness({focused:true});await tick();
  assert.equal(h.nodes.find(n=>n.id==='research-analysis-mode').value,'maintenance');
  assert.equal(h.fetchCalls.some(r=>r.url.endsWith('/plan')),false);
  const run=h.nodes.find(n=>n.id==='research-run');assert.equal(run.textContent,'AI 推荐保养与易损件');
  const models=controlledModels(h),action=run.onclick(),body=JSON.parse(models[0].options.body);
  assert.equal(body.analysis_mode,'maintenance');assert.equal(body.symptom,'');assert.equal(body.symptom_source,'user_question');
  for(const key of ['fault_event_id','manual_fault','engineering_fault','source_report_id'])assert.equal(body[key],undefined,key);
  h.stop.onclick();models[0].resolve(activeRecord({analysis_mode:'maintenance'}));await action;
  assert.equal(h.requests.length,0,'stopped maintenance cannot activate or open an XGSS page');
});

test('switching to maintenance removes fault associations and allows an optional maintenance question',async()=>{
  const fault={code:'E4030',model:'XC948U',configuration:'test',source:'operator_report'};
  const h=harness({focused:true});await restoreResearch(h,activeRecord({engineering_fault:fault,source_report_id:'f'.repeat(64)}));
  h.sandbox.getEngineeringFault=()=>fault;
  const mode=h.nodes.find(n=>n.id==='research-analysis-mode');mode.value='maintenance';mode.onchange();
  const symptom=h.nodes.find(n=>n.id==='research-symptom');symptom.value='检查适用滤芯';symptom.oninput();
  const models=controlledModels(h),action=h.nodes.find(n=>n.id==='research-run').onclick(),body=JSON.parse(models[0].options.body);
  assert.equal(body.analysis_mode,'maintenance');assert.equal(body.symptom,'检查适用滤芯');
  for(const key of ['fault_event_id','manual_fault','engineering_fault','source_report_id'])assert.equal(body[key],undefined,key);
  h.stop.onclick();models[0].resolve(activeRecord());await action;
});

test('typing into the initial maintenance question keeps the displayed mode instead of relabeling it as a fault',async()=>{
  const h=harness({focused:true}),symptom=h.nodes.find(n=>n.id==='research-symptom');
  symptom.onfocus();symptom.value='希望检查空气滤芯';symptom.oninput();
  assert.equal(h.nodes.find(n=>n.id==='research-analysis-mode').value,'maintenance');
  const models=controlledModels(h),action=h.nodes.find(n=>n.id==='research-run').onclick();
  assert.equal(JSON.parse(models[0].options.body).analysis_mode,'maintenance');
  h.stop.onclick();models[0].resolve(activeRecord());await action;
});

function maintenanceRecord(overrides={}){
  const base=activeRecord();
  return {...base,analysis_mode:'maintenance',symptom:'按工时检查保养件',symptom_source:'user_question',
    maintenance_context:{operating_hours:{value:419.73,unit:'h',observed_at:'2026-09-20T12:00:00Z',stale_after_24h:true},interval_status:'unverified',service_history_status:'unknown',last_service_hours:null},
    advice:{...base.advice,summary:'AI 结合工时与图册建议检查风扇状态，是否更换取决于现场检查。',parts:base.advice.parts.map(p=>({...p,part_role:'wear'}))},...overrides};
}

test('maintenance explains its hours evidence and keeps the exact XGSS illustration below AI recommendation conditions',async()=>{
  const h=harness({focused:true}),data=maintenanceRecord();await restoreResearch(h,data);
  assert.equal(h.nodes.find(n=>n.id==='research-analysis-mode').value,'maintenance');
  assert.ok(h.nodes.some(n=>n.textContent==='AI 工时依据：419.73 h'));
  assert.ok(h.nodes.some(n=>n.textContent.includes('2026-09-20T12:00:00Z · 历史采样')));
  assert.ok(h.nodes.some(n=>n.textContent.includes('不判定已到更换周期')));
  assert.ok(h.nodes.some(n=>n.textContent==='AI 推荐依据'));
  const card=h.nodes.find(n=>n.className==='engineering-hypothesis');
  const reason=card.children.findIndex(n=>n.tag==='details'),picture=card.children.findIndex(n=>n.tag==='figure');
  assert.ok(reason>=0&&picture>reason,'diagram is below the recommendation and inspection conditions');
  assert.equal(card.children[reason].open,true,'AI rationale is visible without another click');
  assert.ok(card.children.some(n=>n.textContent==='易损件'));assert.ok(card.children.some(n=>n.textContent==='800160318'));
  assert.ok(h.nodes.filter(n=>n.tag==='img').every(n=>n.src===`/assistant/xgss/research/${data.research_id}/images/${'d'.repeat(64)}`));
});

test('missing hours and missing exact source diagrams remain explicit in maintenance results',async()=>{
  const h=harness({focused:true}),data=maintenanceRecord({maintenance_context:{operating_hours:{value:null},interval_status:'unverified'}});
  data.advice.parts[0].capture_id='f'.repeat(64);await restoreResearch(h,data);
  assert.ok(h.nodes.some(n=>n.textContent==='尚无有效工时：AI 先筛选适用保养件'));
  const card=h.nodes.find(n=>n.className==='engineering-hypothesis');
  assert.equal(card.children.some(n=>n.tag==='figure'),false);
  assert.ok(card.children.some(n=>n.textContent==='当前分类尚未取得 XGSS 图示。'));
});

test('maintenance context and source selection cannot survive a device switch or a late AI plan',async()=>{
  const h=harness({focused:true}),data=maintenanceRecord();await restoreResearch(h,data);
  const context=h.nodes.find(n=>n.id==='research-maintenance-context');assert.ok(context.children.length);
  const mode=h.nodes.find(n=>n.id==='research-analysis-mode');mode.value='maintenance';mode.onchange();
  const models=controlledModels(h),action=h.nodes.find(n=>n.id==='research-run').onclick();
  h.state.machine={...h.state.machine,machine_id:'other'};h.location.hash='#trackunit-asset=other';h.window.syncXGSSResearch();
  assert.equal(context.children.length,0);assert.equal(mode.value,'maintenance');
  const before=h.requests.length;models[0].resolve(data);await action;
  assert.equal(h.requests.length,before,'late maintenance cannot activate for another machine');
  assert.equal(h.nodes.find(n=>n.id==='research-symptom').value,'');
});

test('maintenance renders the backend context projection without faults and tolerates missing metric fields',async()=>{
  const projected={as_of:'2026-09-22T12:00:00Z',last_sample_at:'2026-09-20T12:00:00Z',sample_count:3,excluded_samples:0,source:'trackunit_cache',
    metrics:{operating_hours:{value:419.73,unit:'h',observed_at:'2026-09-20T12:00:00Z',age_hours:48,stale_after_24h:true},
      idle_hours:{value:null},fuel_remaining_percent:{value:null}}};
  for(const context of [projected,{...projected,metrics:{operating_hours:projected.metrics.operating_hours}},
    {as_of:projected.as_of,sample_count:3,source:'trackunit_cache'}]){
    const h=harness({focused:true}),data=maintenanceRecord({machine_context:context});await restoreResearch(h,data);
    assert.equal(Object.hasOwn(context,'faults'),false,'fixture matches the maintenance backend projection');
    assert.ok(h.nodes.some(n=>n.textContent==='AI 推荐依据'),'showPlan completed and advice rendered');
    assert.ok(h.nodes.some(n=>n.textContent==='本次 AI 使用的设备证据'));
    assert.ok(h.nodes.some(n=>n.textContent==='燃油余量：未载入有效值'));
    assert.equal(h.nodes.some(n=>n.textContent==='未载入有效故障记录，不能据此判断无故障。'),false,'maintenance evidence does not invent a fault conclusion');
    assert.ok(h.nodes.some(n=>n.textContent==='800160318'),'exact catalog part still renders');
  }
});

test('maintenance hides only the exact server default question while retaining reusable plans and real user questions',async()=>{
  const defaultQuestion='请结合当前机型与已载入工时，在同机 XGSS 资料中筛选保养件和易损件，说明检查优先级、推荐理由及考虑更换的条件。';
  for(const question of [defaultQuestion,'请检查空气滤芯，还有上周已换的燃油滤清器']){
    const h=harness({focused:true}),data=maintenanceRecord({symptom:question,plan:{summary:'按工时查找滤芯',directions:[{component:'空气滤清器',reason:'核对工时与保养记录',search_terms:['发动机系统','进排气组件','空气滤清器']}]}});await restoreResearch(h,data);
    assert.equal(h.nodes.find(n=>n.id==='research-symptom').value,question===defaultQuestion?'':question);
    assert.equal(h.window.currentXGSSResearchProgress().diagnosed,true,'display-only default removal must retain plan matching');
    const models=controlledModels(h),run=h.nodes.find(n=>n.id==='research-run').onclick();await tick();
    assert.equal(models.length,0,'an unchanged restored plan is reused without a new AI request');
    const opening=h.requests.at(-1);assert.equal(opening.url,'/assistant/xgss/open');
    opening.resolve({url:'https://xgss.xcmg.com/'});await run;
  }
});


test('short equipment-number identity retains AI directions and never requests XGSS',async()=>{
  const h=harness({focused:true});
  h.state.machine={...h.state.machine,serial_number:'10046253',equipment_id:'10046253',model:'XE80U'};
  h.window.syncXGSSResearch();await tick();
  const resume=h.nodes.find(n=>n.textContent==='恢复上次资料排查');
  const pending=resume.onclick();
  h.requests[0].resolve({research_id:'b'.repeat(32),symptom:'显示通讯故障',symptom_source:'operator_report',plan:{summary:'检查通信连接',directions:[{component:'线束与接插件',reason:'通讯中断需先核对连接',search_terms:['线束']}]},pages:[],evidence:{parts:[],manuals:[]}});
  await pending;
  const result=h.nodes.find(n=>n.id==='research-preliminary');assert.equal(result.hidden,false);
  assert.ok(h.nodes.some(n=>n.textContent==='AI 初步排查方向'));
  assert.equal(h.nodes.find(n=>n.id==='research-vin-repair').hidden,false);
  await h.start.onclick();assert.equal(h.requests.length,1);
  assert.equal(h.messages.some(m=>m.type==='jilian:research-start'),false);
  const symptom=h.nodes.find(n=>n.id==='research-symptom');symptom.value='另一个新现象';symptom.oninput();
  assert.equal(result.hidden,true,'old directions cannot survive edited symptoms');
});

test('VIN correction requires explicit current-machine confirmation and ignores late replies',async()=>{
  const h=harness();h.state.machine={...h.state.machine,serial_number:'10046253',equipment_id:'10046253'};h.window.syncXGSSResearch();await tick();
  const input=h.nodes.find(n=>n.id==='research-vin'),confirmed=h.nodes.find(n=>n.id==='research-vin-confirmed'),save=h.nodes.find(n=>n.textContent==='核对并关联图册');
  input.value='XUGTEST000000999';await save.onclick();assert.equal(h.requests.length,0);
  confirmed.checked=true;const pending=save.onclick();assert.equal(h.requests[0].url,'/assistant/xgss/identity/correct');
  const sent=JSON.parse(h.requests[0].options.body);assert.equal(sent.current_vin,'10046253');assert.equal(sent.confirmed,true);
  h.state.machine={...h.state.machine,machine_id:'other',serial_number:'XUGOTHER00000001'};h.window.syncXGSSResearch();
  h.requests[0].resolve({dataset_id:'f'.repeat(64),machine:{machine_id:'asset',serial_number:'XUGTEST000000999'}});await pending;
  assert.equal(h.state.machine.machine_id,'other');assert.equal(h.nodes.find(n=>n.id==='research-vin-repair').hidden,true);
  assert.equal(save.disabled,false);
});

test('late VIN status cannot expose repair inputs for a different device',async()=>{
  let finish;const h=harness({fetchIdentity:()=>new Promise(r=>finish=r)});
  h.state.machine={...h.state.machine,serial_number:'10046253',equipment_id:'10046253'};h.window.syncXGSSResearch();await tick();
  h.state.machine={...h.state.machine,machine_id:'other',serial_number:'XUGOTHER00000001'};h.window.syncXGSSResearch();
  finish({ok:true,json:async()=>({machine_id:'asset',dataset_id:'a'.repeat(64),vin:'10046253',needs_verification:true,message:'old identity'})});await tick();
  assert.equal(h.nodes.find(n=>n.id==='research-vin-repair').hidden,true);
});

test('structured missing-VIN error preserves preliminary AI results without part claims',async()=>{
  const h=harness({focused:true}),resume=h.nodes.find(n=>n.textContent==='恢复上次资料排查');
  const pending=resume.onclick();h.requests[0].resolve({research_id:'b'.repeat(32),symptom:'显示通讯故障',symptom_source:'operator_report',plan:{summary:'连接需检查',directions:[{component:'接插件',reason:'待实测',search_terms:['接插件']}]},pages:[],evidence:{parts:[],manuals:[]}});await pending;
  const run=h.nodes.find(n=>n.id==='research-run').onclick();await tick();
  assert.equal(h.requests[1].url,'/assistant/xgss/open');h.requests[1].reject(Object.assign(new Error('整机 VIN 待核对'),{code:'vin_required'}));await run;
  assert.equal(h.nodes.find(n=>n.id==='research-vin-repair').hidden,false);
  assert.equal(h.nodes.find(n=>n.id==='research-preliminary').hidden,false);
  assert.equal(h.messages.some(m=>m.type==='jilian:research-start'),false);
});


test('VIN correction preserves entered symptom in the new data version',async()=>{
  const h=harness({focused:true});h.state.machine={...h.state.machine,serial_number:'10046253',equipment_id:'10046253'};h.window.syncXGSSResearch();await tick();
  const symptom=h.nodes.find(n=>n.id==='research-symptom'),source=h.nodes.find(n=>n.id==='research-symptom-source');symptom.value='显示通讯故障';source.value='operator_report';symptom.oninput();
  h.nodes.find(n=>n.id==='research-vin').value='XUGTEST000000999';h.nodes.find(n=>n.id==='research-vin-confirmed').checked=true;
  const replacement={...h.state.machine,dataset_id:'f'.repeat(64),selection_id:'dataset:'+'f'.repeat(64),serial_number:'XUGTEST000000999'};
  h.sandbox.machines=[h.state.machine,replacement];h.sandbox.refresh=async()=>{};h.sandbox.selectMachine=()=>{h.state.machine=replacement;h.window.syncXGSSResearch();};
  const run=h.nodes.find(n=>n.textContent==='核对并关联图册').onclick();h.requests[0].resolve({dataset_id:replacement.dataset_id,machine:replacement});await run;
  assert.equal(h.state.machine.dataset_id,replacement.dataset_id);assert.equal(symptom.value,'显示通讯故障');assert.equal(source.value,'operator_report');
  assert.equal(h.nodes.find(n=>n.id==='research-preliminary').hidden,true);assert.equal(h.nodes.find(n=>n.textContent==='核对并关联图册').disabled,false);
});

test('VIN correction cannot overwrite a same-machine version switched during refresh',async()=>{
  const h=harness();h.state.machine={...h.state.machine,serial_number:'10046253',equipment_id:'10046253'};h.window.syncXGSSResearch();await tick();
  h.nodes.find(n=>n.id==='research-vin').value='XUGTEST000000999';h.nodes.find(n=>n.id==='research-vin-confirmed').checked=true;
  const replacement={...h.state.machine,dataset_id:'f'.repeat(64),selection_id:'dataset:'+'f'.repeat(64),serial_number:'XUGTEST000000999'};
  let done,switched=false;h.sandbox.machines=[replacement];h.sandbox.refresh=()=>new Promise(r=>done=r);h.sandbox.selectMachine=()=>{switched=true;};
  const run=h.nodes.find(n=>n.textContent==='核对并关联图册').onclick();h.requests[0].resolve({dataset_id:replacement.dataset_id,machine:replacement});await tick();
  h.state.machine={...h.state.machine,dataset_id:'e'.repeat(64)};h.window.syncXGSSResearch();const symptom=h.nodes.find(n=>n.id==='research-symptom');symptom.value='另一数据版本输入';symptom.oninput();done();await run;
  assert.equal(switched,false);assert.equal(symptom.value,'另一数据版本输入');assert.equal(h.state.machine.dataset_id,'e'.repeat(64));
});

test('VIN correction permits explicitly confirmed numeric identity and preserves data when XGSS rejects it',async()=>{
  const h=harness();h.state.machine={...h.state.machine,serial_number:'10046253',equipment_id:'10046253'};h.window.syncXGSSResearch();await tick();
  const original=h.state.machine,input=h.nodes.find(n=>n.id==='research-vin'),confirmed=h.nodes.find(n=>n.id==='research-vin-confirmed'),save=h.nodes.find(n=>n.textContent==='核对并关联图册');
  input.value='10046253';await save.onclick();assert.equal(h.requests.length,0);
  confirmed.checked=true;const run=save.onclick();assert.equal(h.requests[0].url,'/assistant/xgss/identity/correct');
  const sent=JSON.parse(h.requests[0].options.body);assert.equal(sent.new_vin,'10046253');assert.equal(sent.confirmed,true);
  h.requests[0].reject(new Error('XGSS 未找到该编号'));await run;
  assert.equal(h.state.machine,original);assert.equal(save.disabled,false);
  assert.equal(h.nodes.find(n=>n.id==='research-vin-repair').hidden,false);
});

test('focused result shows same-VIN parts, reasons and diagram before the form',async()=>{
  const saved=activeRecord();
  const h=harness({focused:true,fetchActive:async()=>({ok:true,json:async()=>saved})});await tick();
  const card=h.nodes.find(n=>n.id==='xgss-research'),hero=h.nodes.find(n=>n.id==='research-result-hero');
  const mode=h.nodes.find(n=>n.id==='research-input-panel'),primary=h.nodes.find(n=>n.id==='research-run');
  assert.equal(hero.hidden,false);
  assert.ok(card.children.indexOf(hero)<card.children.indexOf(mode),'saved AI result must appear before the input form');
  const advice=card.children.find(child=>child.children.some(n=>n.className==='research-part-list'));
  const gallery=card.children.find(child=>child.children.some(n=>n.className==='research-diagram-gallery'));
  const rawSources=card.children.find(child=>child.children.some(n=>n.textContent==='已读取 1 页 · 零件 1 条 · 手册章节 0 条'));
  assert.ok(advice&&card.children.indexOf(advice)<card.children.indexOf(mode),'part cards and repair advice must precede the input form');
  assert.ok(advice.children.find(n=>n.className==='research-part-list'),'part cards remain above the form');
  assert.equal(mode.open,false,'completed result collapses editable inputs');
  assert.match(visibleText(hero),/1 项备件候选/);
  assert.match(visibleText(hero),/1 张图纸/);
  assert.equal(primary.textContent,'更新备件建议');
  const jump=hero.children.find(n=>n.tag==='button');assert.equal(jump.textContent,'查看备件、依据与维修建议');
  jump.onclick();
  assert.equal(h.requests.length,0,'viewing a saved result must not reopen XGSS or call the model');
  const symptom=h.nodes.find(n=>n.id==='research-symptom');symptom.value='新故障现象';symptom.oninput();
  assert.equal(hero.hidden,true,'an edited problem must hide the prior AI result');
  assert.equal(gallery.hidden,true,'old same-VIN drawings must not appear as evidence for a different symptom');
  assert.equal(rawSources.hidden,true,'old source rows must not appear under the new symptom');
  assert.equal(primary.textContent,'分析故障并推荐备件');
});

test('unfinished standalone analysis identifies missing XGSS evidence without promising parts',async()=>{
  const saved=activeRecord({revision:0,analysis_revision:undefined,pages:[],advice:undefined,evidence:{parts:[],manuals:[]}});
  const h=harness({focused:true,ready:false,search:'',fetchActive:async()=>faultReply(saved)});await tick();
  const card=h.nodes.find(n=>n.id==='xgss-research'),pending=h.nodes.find(n=>n.id==='research-preliminary');
  const mode=h.nodes.find(n=>n.id==='research-input-panel'),run=h.nodes.find(n=>n.id==='research-run');
  assert.equal(pending.hidden,false);
  assert.ok(card.children.indexOf(pending)<card.children.indexOf(mode));
  assert.match(visibleText(pending),/尚未读取该设备适用的零件或手册/);
  assert.match(visibleText(pending),/继续读取 XGSS 并生成备件建议/);
  assert.equal(run.hidden,false);
  assert.equal(h.nodes.find(n=>n.id==='research-result-hero').hidden,true);
});

test('focused result identifies unverified human fault reports in its overview',async()=>{
  const saved=activeRecord({symptom_source:'operator_report'});
  const h=harness({focused:true,fetchActive:async()=>({ok:true,json:async()=>saved})});await tick();
  const hero=h.nodes.find(n=>n.id==='research-result-hero');
  assert.match(visibleText(hero),/人工报告，Trackunit 故障接口尚未核验/);
});

test('fault part cards show AI matching evidence without opening the replacement-condition disclosure',async()=>{
  const h=harness({focused:true,fetchActive:async()=>faultReply(activeRecord({symptom_source:'operator_report'}))});
  await tick();
  const card=h.nodes.find(n=>n.className==='engineering-hypothesis');
  const reason=card.children.find(n=>n.className==='research-part-reason');
  const conditions=card.children.find(n=>n.tag==='details');
  assert.match(reason.textContent,/AI 匹配依据：检查风扇/);
  assert.equal(conditions.open,false);
  assert.ok(conditions.children.some(n=>n.textContent==='核对后更换'));
});

test('a selected Trackunit page fault survives a repeat capture of the same visible card',()=>{
  const h=harness({focused:true}),fault={code:'SPN 2664 / FMI 3',spn:2664,fmi:3,sa:160,
    description:'Joystick 1 Theta-Axis Position - Voltage Above Normal',severity:'Low',displayed_at:'Sep 12, 2026, 7:37 AM'};
  const capture={schema_version:1,source:'trackunit_visible_events_page',asset_id:'asset',
    capture_status:'visible_fault_cards',coverage:'rendered_active_fault_cards_only',
    observed_at:'2026-09-23T06:00:00Z',faults:[fault]};
  h.send({type:'jilian:trackunit-page-faults',asset_id:'asset',dataset_id:'a'.repeat(64),capture});
  const select=h.nodes.find(n=>n.id==='research-fault-event'),symptom=h.nodes.find(n=>n.id==='research-symptom');
  select.value='page:0';select.onchange();
  const before=symptom.value;
  h.send({type:'jilian:trackunit-page-faults',asset_id:'asset',dataset_id:'a'.repeat(64),
    capture:{...capture,observed_at:'2026-09-23T06:01:00Z',faults:[{...fault}]}});
  assert.equal(select.value,'page:0');
  assert.equal(symptom.value,before);
  assert.equal(h.nodes.find(n=>n.id==='research-symptom-source').value,'trackunit_page');
  assert.equal(h.requests.length,0);
});

test('visible Trackunit faults reveal the fault selector before the user chooses a card',()=>{
  const h=harness({focused:true}),select=h.nodes.find(n=>n.id==='research-fault-event');
  assert.equal(select.hidden,true,'the untouched workspace starts in maintenance mode');
  const faults=[{code:'SPN 2664 / FMI 3',spn:2664,fmi:3,sa:160,
    description:'Joystick 1 Theta-Axis Position',severity:'Low',displayed_at:'Sep 12, 2026'},
    {code:'SPN 168 / FMI 16',spn:168,fmi:16,sa:160,
      description:'Battery Potential',severity:'Low',displayed_at:'Sep 11, 2026'}];
  h.send({type:'jilian:trackunit-page-faults',asset_id:'asset',dataset_id:'a'.repeat(64),
    capture:{schema_version:1,source:'trackunit_visible_events_page',asset_id:'asset',
      capture_status:'visible_fault_cards',coverage:'rendered_active_fault_cards_only',
      observed_at:'2026-09-23T06:00:00Z',faults}});
  assert.equal(select.hidden,false);
  assert.equal(h.nodes.find(n=>n.id==='research-analysis-mode').value,'fault');
  assert.equal(select.value,'','multiple faults require an explicit choice');
  assert.equal(select.children.length,3);
});

test('multiple visible Events faults offer a result-first choice without reusing saved XGSS advice',async()=>{
  const saved=activeRecord({symptom_source:'operator_report'});
  const h=harness({focused:true,fetchActive:async()=>({ok:true,json:async()=>saved})});await tick();
  const card=h.nodes.find(n=>n.id==='xgss-research');
  const banner=h.nodes.find(n=>n.id==='research-page-fault-banner');
  const hero=h.nodes.find(n=>n.id==='research-result-hero');
  const faults=[{code:'SPN 2664 / FMI 3',spn:2664,fmi:3,sa:160,
    description:'Joystick 1 Theta-Axis Position',severity:'Low',displayed_at:'Sep 12, 2026'},
    {code:'SPN 444 / FMI 1',spn:444,fmi:1,sa:160,
      description:'Battery Potential',severity:'Low',displayed_at:'Sep 11, 2026'}];
  h.send({type:'jilian:trackunit-page-faults',asset_id:'asset',dataset_id:'a'.repeat(64),
    capture:{schema_version:1,source:'trackunit_visible_events_page',asset_id:'asset',
      capture_status:'visible_fault_cards',coverage:'rendered_active_fault_cards_only',
      observed_at:new Date().toISOString(),faults}});
  assert.equal(banner.hidden,false);
  assert.ok(card.children.indexOf(banner)<card.children.indexOf(hero));
  assert.equal(hero.hidden,false,'the saved advice remains visible until a different fault is selected');
  const choices=banner.children.find(n=>n.className==='research-page-fault-actions');
  assert.equal(choices.children.length,2);
  assert.match(visibleText(banner),/下方已保存结果基于此前人工报告，尚未与这些页面故障码绑定/);
  assert.equal(choices.children[0].children[0].textContent,'SPN 2664 / FMI 3 · SA 160');
  assert.equal(choices.children[0].children[1].textContent,'Joystick 1 Theta-Axis Position');
  choices.children[0].onclick();
  assert.equal(h.nodes.find(n=>n.id==='research-fault-event').value,'page:0');
  assert.equal(h.nodes.find(n=>n.id==='research-symptom-source').value,'trackunit_page');
  assert.match(h.nodes.find(n=>n.id==='research-symptom').value,/SPN 2664 \/ FMI 3/);
  assert.equal(hero.hidden,true,'advice for the prior symptom must disappear');
  assert.equal(h.nodes.find(n=>n.id==='research-run').focused,true);
  assert.equal(h.requests.length,0,'choosing a card does not call AI without the user clicking Analyze');
  const models=controlledModels(h),action=h.nodes.find(n=>n.id==='research-run').onclick();
  assert.equal(models.length,1,'Analyze must start a fresh plan for the selected page fault');
  const request=JSON.parse(models[0].options.body);
  assert.equal(request.analysis_mode,'fault');
  assert.equal(request.symptom_source,'trackunit_page');
  assert.match(request.symptom,/SPN 2664 \/ FMI 3/);
  assert.equal(request.fault_event_id,undefined,'a page observation is not an API-verified event');
  h.stop.onclick();models[0].resolve(saved);await action;
});

test('one visible Events fault becomes the pending input when the official API is unauthorized',async()=>{
  const state=freshFaultState({status:'unauthorized',http_status:401,events:[]});
  const h=harness({focused:true,fetchFaults:async()=>faultReply(state)});
  const observed_at=new Date().toISOString();
  h.send({type:'jilian:trackunit-page-faults',asset_id:'asset',dataset_id:'a'.repeat(64),
    capture:{schema_version:1,source:'trackunit_visible_events_page',asset_id:'asset',
      capture_status:'visible_fault_cards',coverage:'rendered_active_fault_cards_only',observed_at,
      faults:[{code:'SPN 2664 / FMI 3',spn:2664,fmi:3,sa:160,
        description:'Joystick 1 Theta-Axis Position',severity:'Low',displayed_at:'Sep 12, 2026'}]}});
  await tick();
  assert.equal(h.nodes.find(n=>n.id==='research-fault-event').value,'page:0');
  assert.equal(h.nodes.find(n=>n.id==='research-symptom-source').value,'trackunit_page');
  assert.match(h.nodes.find(n=>n.id==='research-symptom').value,/SPN 2664 \/ FMI 3/);
  assert.match(h.nodes.find(n=>n.id==='research-fault-event-note').textContent,/页面记录尚未由故障 API 核验/);
  assert.equal(h.requests.length,0,'page observation prepares the input but never silently invokes AI');
});

test('page faults do not displace an available official event query',async()=>{
  const state=freshFaultState({status:'data',events:[]});
  const h=harness({focused:true,fetchFaults:async()=>faultReply(state)});await tick();
  h.send({type:'jilian:trackunit-page-faults',asset_id:'asset',dataset_id:'a'.repeat(64),
    capture:{schema_version:1,source:'trackunit_visible_events_page',asset_id:'asset',
      capture_status:'visible_fault_cards',coverage:'rendered_active_fault_cards_only',observed_at:new Date().toISOString(),
      faults:[{code:'SPN 2664 / FMI 3',spn:2664,fmi:3,sa:160,
        description:'Joystick 1 Theta-Axis Position',severity:'Low',displayed_at:'Sep 12, 2026'}]}});
  assert.equal(h.nodes.find(n=>n.id==='research-fault-event').value,'');
  assert.equal(h.nodes.find(n=>n.id==='research-symptom').value,'');
  assert.equal(h.requests.length,0);
});

test('a saved maintenance result still exposes newly observed page faults',async()=>{
  const saved=maintenanceRecord(),h=harness({focused:true,fetchActive:async()=>faultReply(saved)});
  await tick();
  const select=h.nodes.find(n=>n.id==='research-fault-event');
  assert.equal(h.nodes.find(n=>n.id==='research-analysis-mode').value,'maintenance');
  assert.equal(select.hidden,true);
  h.send({type:'jilian:trackunit-page-faults',asset_id:'asset',dataset_id:'a'.repeat(64),
    capture:{schema_version:1,source:'trackunit_visible_events_page',asset_id:'asset',
      capture_status:'visible_fault_cards',coverage:'rendered_active_fault_cards_only',
      observed_at:'2026-09-23T06:00:00Z',faults:[{code:'SPN 2664 / FMI 3',spn:2664,fmi:3,sa:160,
        description:'Joystick 1 Theta-Axis Position',severity:'Low',displayed_at:'Sep 12, 2026'}]}});
  assert.equal(select.hidden,false);
  assert.equal(h.nodes.find(n=>n.id==='research-analysis-mode').value,'maintenance','the saved result remains intact until selection');
  select.value='page:0';select.onchange();
  assert.equal(h.nodes.find(n=>n.id==='research-analysis-mode').value,'fault');
  assert.equal(h.nodes.find(n=>n.id==='research-result-hero').hidden,true,'old maintenance advice is hidden for this fault');
  assert.equal(h.nodes.find(n=>n.id==='research-run').hidden,false);
});

test('switching from a page fault to an official event clears the old page observation',async()=>{
  const state=freshFaultState({status:'unauthorized',http_status:401});
  const h=harness({focused:true,fetchFaults:async()=>faultReply(state)});await tick();
  const select=h.nodes.find(n=>n.id==='research-fault-event');
  h.send({type:'jilian:trackunit-page-faults',asset_id:'asset',dataset_id:'a'.repeat(64),
    capture:{schema_version:1,source:'trackunit_visible_events_page',asset_id:'asset',
      capture_status:'visible_fault_cards',coverage:'rendered_active_fault_cards_only',
      observed_at:'2026-09-23T06:00:00Z',faults:[{code:'SPN 2664 / FMI 3',spn:2664,fmi:3,sa:160,
        description:'Joystick 1 Theta-Axis Position',severity:'Low',displayed_at:'Sep 12, 2026'}]}});
  select.value='page:0';select.onchange();
  assert.match(h.nodes.find(n=>n.id==='research-symptom').value,/SPN 2664/);
  select.value=state.events[0].event_id;select.onchange();
  assert.equal(h.nodes.find(n=>n.id==='research-symptom').value,'');
  assert.equal(h.nodes.find(n=>n.id==='research-symptom-source').value,'trackunit_event');
});

test('a selected visible page fault flows through AI planning, same-VIN collection and source-grounded advice',async()=>{
  const h=harness({focused:true});
  h.send({type:'jilian:trackunit-page-faults',asset_id:'asset',dataset_id:'a'.repeat(64),
    capture:{schema_version:1,source:'trackunit_visible_events_page',asset_id:'asset',
      capture_status:'visible_fault_cards',coverage:'rendered_active_fault_cards_only',
      observed_at:'2026-09-23T06:00:00Z',faults:[{code:'SPN 2664 / FMI 3',spn:2664,fmi:3,sa:160,
        description:'Joystick 1 Theta-Axis Position',severity:'Low',displayed_at:'Sep 12, 2026'}]}});
  const select=h.nodes.find(n=>n.id==='research-fault-event');select.value='page:0';select.onchange();
  const symptom=h.nodes.find(n=>n.id==='research-symptom').value;
  const models=controlledModels(h),action=h.nodes.find(n=>n.id==='research-run').onclick();
  assert.equal(models.length,1);
  const request=JSON.parse(models[0].options.body);
  assert.equal(request.analysis_mode,'fault');assert.equal(request.symptom_source,'trackunit_page');
  assert.equal(request.symptom,symptom);assert.equal(request.fault_event_id,undefined);
  const result=activeRecord({symptom,symptom_source:'trackunit_page',fault_event_id:null,
    plan:{summary:'检查操纵杆与电气连接',directions:[{component:'操纵杆',reason:'核对电气连接',search_terms:['操纵杆']}]}});
  const plan={...result,revision:0,analysis_revision:undefined,pages:[],advice:undefined,evidence:{parts:[],manuals:[]}};
  models[0].resolve(plan);await tick();
  h.requests[0].resolve(plan);await tick();
  assert.equal(h.requests[1].url,'/assistant/xgss/open');
  assert.equal(JSON.parse(h.requests[1].options.body).vin,'XUGTEST000000001');
  h.requests[1].resolve({url:'https://xgss.xcmg.com/'});await action;
  assert.ok(h.messages.some(m=>m.type==='jilian:research-start'&&m.request_id===plan.research_id));
  const saving=h.send({type:'jilian:research-page',request_id:plan.research_id,asset_id:'asset',dataset_id:'a'.repeat(64),page_id:'page',capture:{}});
  h.requests[2].resolve({...result,advice:undefined,analysis_revision:undefined});await saving;
  const done=h.send({type:'jilian:research-done',request_id:plan.research_id,asset_id:'asset',dataset_id:'a'.repeat(64),result:{status:'completed'}});
  assert.match(models[1].url,/\/analyze$/);models[1].resolve(result);await done;
  assert.equal(h.window.currentXGSSResearchProgress().verified,true);
  assert.ok(h.nodes.some(n=>n.id==='research-email-preview'));
  assert.equal(h.requests.some(r=>/email-send/.test(r.url)),false);
});

test('page capture errors show a recovery message and a later valid capture clears it',()=>{
  const h=harness({focused:true}),note=h.nodes.find(n=>n.id==='research-fault-event-note');
  h.send({type:'jilian:trackunit-page-faults-error',asset_id:'asset',dataset_id:'a'.repeat(64)});
  assert.match(note.textContent,/当前 Events 页读取失败/);
  h.send({type:'jilian:trackunit-page-faults',asset_id:'asset',dataset_id:'a'.repeat(64),
    capture:{schema_version:1,source:'trackunit_visible_events_page',asset_id:'asset',
      capture_status:'no_visible_fault_cards',coverage:'rendered_active_fault_cards_only',
      observed_at:'2026-09-23T06:00:00Z',faults:[]}});
  assert.doesNotMatch(note.textContent,/读取失败/);
  assert.match(note.textContent,/0 条故障、0 条保养提醒/);
});

test('manual Events-page read exposes recovery when the page is wrong and then accepts visible faults',()=>{
  const h=harness({focused:true}),button=h.nodes.find(n=>n.id==='research-page-fault-read');
  const note=h.nodes.find(n=>n.id==='research-fault-event-note');
  assert.equal(button.hidden,false);
  button.onclick();
  assert.equal(button.disabled,true);
  assert.ok(h.messages.some(m=>m.type==='jilian:trackunit-page-faults-request'&&m.asset_id==='asset'&&m.dataset_id==='a'.repeat(64)));
  h.send({type:'jilian:trackunit-page-faults-error',asset_id:'asset',dataset_id:'a'.repeat(64),reason:'wrong_page'});
  assert.match(note.textContent,/打开当前设备的 Trackunit Events 页/);
  assert.equal(button.disabled,false);
  button.onclick();
  h.send({type:'jilian:trackunit-page-faults-error',asset_id:'asset',dataset_id:'a'.repeat(64),reason:'identity_pending'});
  assert.match(note.textContent,/正在核对当前设备/);
  assert.equal(button.disabled,false);
  button.onclick();
  h.send({type:'jilian:trackunit-page-faults',asset_id:'asset',dataset_id:'a'.repeat(64),
    capture:{schema_version:1,source:'trackunit_visible_events_page',asset_id:'asset',
      capture_status:'visible_fault_cards',coverage:'rendered_active_fault_cards_only',
      observed_at:'2026-09-23T06:00:00Z',faults:[{code:'SPN 2664 / FMI 3',spn:2664,fmi:3,sa:160,
        description:'Joystick 1 Theta-Axis Position',severity:'Low',displayed_at:'Sep 12, 2026'}]}});
  assert.equal(button.hidden,false);
  assert.equal(button.textContent,'刷新当前页故障与历史记录');
  assert.equal(h.nodes.find(n=>n.id==='research-fault-event').hidden,false);
  assert.doesNotMatch(note.textContent,/读取失败|打开当前设备/);
});

test('synthetic demo equipment shows a usable route instead of disabled XGSS actions',()=>{
  const h=harness({focused:true});let switched=null;
  h.window.JilianDataMode={switchTo:mode=>switched=mode};
  h.state.machine={...h.state.machine,provenance:'demo'};
  h.window.syncXGSSResearch();
  const gate=h.nodes.find(n=>n.id==='research-demo-gate');
  assert.equal(gate.hidden,false);
  assert.ok(gate.children.some(n=>n.textContent.includes('读取当前设备后，按故障码匹配该设备适用的 XGSS 图册和配件。')));
  assert.equal(h.nodes.find(n=>n.className==='row research-main-actions').hidden,true);
  gate.children.find(n=>n.textContent==='关联当前设备').onclick();
  assert.equal(switched,'live');
});

test('completed AI results in a standalone web page keep the direct-capable action available',async()=>{
  const saved=activeRecord(),h=harness({focused:true,ready:false,fetchActive:async()=>({ok:true,json:async()=>saved})});
  await tick();
  assert.equal(h.nodes.find(n=>n.id==='research-result-hero').hidden,false);
  assert.equal(h.nodes.find(n=>n.id==='research-run').hidden,false);
  h.send({type:'jilian:research-ready'});
  assert.equal(h.nodes.find(n=>n.id==='research-run').hidden,false);
});

test('unbound stale research query loads the selected device active plan instead of blocking it',async()=>{
  const current=activeRecord({research_id:'d'.repeat(32),symptom:'当前设备的保养问题'});
  const h=harness({search:'?research='+'c'.repeat(32),hash:'',
    fetchActive:async()=>({ok:true,json:async()=>current})});
  await tick();
  assert.equal(h.fetchCalls.some(r=>r.url.endsWith('/active')),true);
  assert.equal(h.fetchCalls.some(r=>r.url.endsWith('/'+'c'.repeat(32))),false);
  assert.equal(h.nodes.find(n=>n.id==='research-symptom').value,current.symptom);
});

test('invalid restored AI advice creates a fresh plan when the engineer retries',async()=>{
  const h=harness({focused:true});
  await restoreResearch(h,maintenanceRecord({advice:undefined,analysis_revision:undefined,
    advice_error:'历史建议未通过来源校验，已隐藏；原始资料仍保留。请重新生成排查计划。'}));
  const models=controlledModels(h),action=h.nodes.find(n=>n.id==='research-run').onclick();
  assert.equal(models.length,1);
  assert.equal(models[0].url,'/assistant/xgss/research/plan');
  assert.equal(JSON.parse(models[0].options.body).analysis_mode,'maintenance');
  h.stop.onclick();models[0].resolve(maintenanceRecord());await action;
});

test('root-only collection retries category capture instead of repeatedly analyzing the machine row',async()=>{
  for(const mode of ['fault','maintenance']){
    const root=activeRecord({analysis_mode:mode,symptom:mode==='maintenance'?'检查保养情况':'显示通讯故障',symptom_source:mode==='maintenance'?'user_question':'operator_report',advice:undefined,analysis_revision:undefined,
      plan:{summary:'查找部件',directions:[{component:'滤清器',reason:'核对保养件',search_terms:['空滤器']}]},
      evidence:{parts:[{name:'越野轮胎起重机',part_number:'127401674',assembly_path:[]}],manuals:[]}});
    const h=harness({focused:true});await restoreResearch(h,root);const models=controlledModels(h);
    let run=h.nodes.find(n=>n.id==='research-run').onclick();await tick();
    assert.equal(models.length,0);assert.equal(h.requests.at(-1).url,'/assistant/xgss/open');
    h.requests.at(-1).resolve({url:'https://xgss.xcmg.com/'});await run;
    await h.send({type:'jilian:research-done',request_id:root.research_id,asset_id:'asset',dataset_id:'a'.repeat(64),result:{status:'partial',unmatched_terms:['空滤器'],unresolved:['整机分类未完成展开']}});
    assert.equal(models.length,0,'whole-machine rows do not trigger the second AI pass');
    assert.ok(h.nodes.some(n=>n.textContent.includes('未完成读取：整机分类未完成展开')));
    assert.ok(h.nodes.some(n=>n.textContent.includes('尚未读到部件或手册内容')));
    assert.equal(h.nodes.find(n=>n.id==='research-preliminary').hidden,false,'AI directions remain available while category sources are missing');
    const count=h.requests.length;run=h.nodes.find(n=>n.id==='research-run').onclick();await tick();
    assert.equal(h.requests.length,count+1);assert.equal(h.requests.at(-1).url,'/assistant/xgss/open');
    h.requests.at(-1).resolve({url:'https://xgss.xcmg.com/'});await run;h.stop.onclick();
  }
});

test('partial collection with real components continues to AI and preserves unread categories',async()=>{
  const data=activeRecord({advice:undefined,analysis_revision:undefined,plan:{summary:'查找风扇',directions:[{component:'风扇',reason:'核对风量',search_terms:['风扇']}]}});
  const h=harness({focused:true});await restoreResearch(h,data);const models=controlledModels(h);
  const collecting=h.start.onclick();await tick();h.requests.at(-1).resolve({url:'https://xgss.xcmg.com/'});await collecting;
  const done=h.send({type:'jilian:research-done',request_id:data.research_id,asset_id:'asset',dataset_id:'a'.repeat(64),result:{status:'partial',unmatched_terms:['水泵'],unresolved:['水泵']}});
  assert.equal(models.length,1);assert.match(models[0].url,/\/analyze$/);models[0].resolve({...data,advice:illustratedRecord().advice,analysis_revision:1});await done;
  assert.ok(h.nodes.some(n=>n.textContent.includes('未完成读取：水泵')));
});

test('email preview reloads a newer result before offering any send action',async()=>{
  for(const change of [{analysis_revision:2},{analyzed_at:'2026-09-22T04:00:00Z'}]){
    const old=activeRecord(),updated={...old,...change,revision:change.analysis_revision||old.revision,advice:{...old.advice,summary:'新的现场检查建议'}};
    const h=harness();await restoreResearch(h,old);
    const run=h.nodes.find(n=>n.id==='research-email-preview').onclick();
    h.requests.at(-1).resolve({research_id:old.research_id,analysis_revision:1,analyzed_at:old.analyzed_at,...change,subject:'UNREVIEWED-MAIL',body:'UNREVIEWED-BODY',can_send:true,preview_hash:'v2'});await tick();
    assert.equal(h.requests.at(-1).url,'/assistant/xgss/research/'+old.research_id);
    h.requests.at(-1).resolve(updated);await run;
    assert.equal(h.nodes.some(n=>n.textContent==='UNREVIEWED-MAIL'||n.textContent==='UNREVIEWED-BODY'),false);
    assert.equal(h.nodes.some(n=>n.id==='research-email-send'),false);
    assert.ok(h.nodes.some(n=>n.textContent==='新的现场检查建议'));
    assert.ok(h.nodes.some(n=>n.textContent.includes('建议已更新，已载入最新结果')));
    const preview=h.nodes.filter(n=>n.id==='research-email-preview').at(-1),next=preview.onclick();
    h.requests.at(-1).resolve({research_id:updated.research_id,analysis_revision:updated.analysis_revision,analyzed_at:updated.analyzed_at,subject:'REVIEWED-MAIL',body:'核对后准备',can_send:true,preview_hash:'v2'});await next;
    assert.equal(h.nodes.filter(n=>n.id==='research-email-send').at(-1).disabled,false);
    assert.equal(h.requests.some(r=>r.url.endsWith('/email-send')),false);
  }
});

test('late result reload after stale email preview cannot replace edited input or another machine',async()=>{
  for(const changed of ['symptom','machine']){
    const old=activeRecord(),h=harness();await restoreResearch(h,old);
    const run=h.nodes.find(n=>n.id==='research-email-preview').onclick();
    h.requests.at(-1).resolve({research_id:old.research_id,analysis_revision:2,analyzed_at:old.analyzed_at,can_send:true});await tick();
    if(changed==='symptom'){const input=h.nodes.find(n=>n.id==='research-symptom');input.value='用户刚改的故障现象';input.oninput();}
    else{h.state.machine={...h.state.machine,machine_id:'other'};h.window.syncXGSSResearch();}
    h.requests.at(-1).resolve({...old,analysis_revision:2,advice:{...old.advice,summary:'LATE-RESULT'}});await run;
    assert.equal(h.nodes.some(n=>n.textContent==='LATE-RESULT'),false);
    assert.equal(h.nodes.some(n=>n.id==='research-email-send'),false);
  }
});


test('visible service reminder enters AI maintenance without claiming a fault code',async()=>{
  const h=harness({focused:true});
  h.send({type:'jilian:trackunit-page-faults',asset_id:'asset',dataset_id:'a'.repeat(64),
    capture:{schema_version:1,source:'trackunit_visible_events_page',asset_id:'asset',
      capture_status:'no_visible_fault_cards',coverage:'rendered_active_events_only',
      observed_at:new Date().toISOString(),faults:[],services:[{kind:'overdue',title:'Overdue Service',
        plan:'Test Plan - Wheel Loaders',target_hours:100,hours_offset:368,displayed_at:'Jul 24, 2026'}]}});
  const banner=h.nodes.find(n=>n.id==='research-page-fault-banner');
  assert.equal(banner.hidden,false);
  assert.match(banner.children[0].textContent,/0 条故障 · 1 条保养提醒/);
  const serviceButtons=banner.children.find(node=>node.className==='research-page-service-actions');
  serviceButtons.children[0].onclick();
  assert.equal(h.nodes.find(n=>n.id==='research-analysis-mode').value,'maintenance');
  assert.match(h.nodes.find(n=>n.id==='research-symptom').value,/368 h 逾期/);
  assert.equal(h.requests.length,0);
  const models=controlledModels(h),action=h.nodes.find(n=>n.id==='research-run').onclick();
  assert.equal(models.length,1);
  const body=JSON.parse(models[0].options.body);
  assert.equal(body.analysis_mode,'maintenance');
  assert.equal(body.fault_event_id,undefined);
  h.stop.onclick();models[0].resolve(maintenanceRecord());await action;
});


test('ready sources expose one primary action that analyzes parts without recreating the plan',async()=>{
  for(const stale of [false,true]){
    const data=activeRecord({revision:2,analysis_revision:stale?1:undefined,...(stale?{}:{advice:undefined})});
    const h=harness({focused:true,ready:false,search:'',fetchActive:async()=>faultReply(data)});await tick();
    const button=h.nodes.find(n=>n.id==='research-run');
    assert.equal(button.hidden,false);
    assert.equal(button.textContent,'生成备件与维修建议');
    assert.equal(h.nodes.find(n=>n.id==='research-input-panel').open,true);
    const calls=controlledModels(h),run=button.onclick();
    assert.equal(calls.length,1);
    assert.equal(calls[0].url,'/assistant/xgss/research/'+data.research_id+'/analyze');
    calls[0].resolve({...data,advice:activeRecord().advice,analysis_revision:2});await run;
    assert.equal(h.nodes.find(n=>n.id==='research-result-hero').hidden,false);
    assert.equal(h.nodes.find(n=>n.id==='research-input-panel').open,false);
    assert.equal(calls.length,1,'no duplicate model request or plan recreation');
  }
});


test('sensor parts handoff rejects changed asset before requesting evidence',async()=>{
  const h=harness();
  await assert.rejects(h.window.openSensorSeriesParts({series_id:'e'.repeat(64),machine_id:'other',dataset_id:'a'.repeat(64),hypothesis_index:0}),/设备已切换/);
  assert.equal(h.requests.length,0);
});
test('sensor parts handoff rejects mismatched VIN without changing fault input',async()=>{
  const h=harness(),symptom=h.nodes.find(n=>n.id==='research-symptom');symptom.value='原始故障';
  const run=h.window.openSensorSeriesParts({series_id:'e'.repeat(64),machine_id:'asset',dataset_id:'a'.repeat(64),hypothesis_index:0});
  h.requests[0].resolve({series_id:'e'.repeat(64),machine_id:'asset',dataset_id:'a'.repeat(64),vin:'OTHER',symptom_source:'user_question',symptom:'wrong',search_terms:['水泵']});
  await assert.rejects(run,/不一致/);assert.equal(symptom.value,'原始故障');
});
test('sensor parts handoff uses saved same-device question and starts separate research',async()=>{
  const h=harness();let planned=null,view=null;
  h.nodes.find(n=>n.id==='research-run').onclick=async args=>{planned=args;};
  h.sandbox.setView=(name)=>{view=name;};
  const run=h.window.openSensorSeriesParts({series_id:'e'.repeat(64),machine_id:'asset',dataset_id:'a'.repeat(64),hypothesis_index:1});
  assert.deepEqual(JSON.parse(h.requests[0].options.body),{machine_id:'asset',dataset_id:'a'.repeat(64),hypothesis_index:1});
  h.requests[0].resolve({series_id:'e'.repeat(64),machine_id:'asset',dataset_id:'a'.repeat(64),vin:h.state.machine.serial_number,symptom_source:'user_question',symptom:'条件性持续升温风险，尚未确认故障',search_terms:['散热器','风扇']});
  await run;
  assert.equal(view,'work');assert.equal(planned.force,true);
  assert.equal(h.nodes.find(n=>n.id==='research-symptom-source').value,'user_question');
  assert.equal(h.nodes.find(n=>n.id==='research-symptom').value,'条件性持续升温风险，尚未确认故障');
});


test('sensor parts handoff ignores unrelated manual draft only for its verified unchanged question',async()=>{
  const h=harness({ready:false});await tick();const calls=controlledModels(h);
  h.sandbox.getManualFaultDraftReference=()=>({code:'H10101',model:'TV12U',applicability_confirmed:false});
  const run=h.window.openSensorSeriesParts({series_id:'e'.repeat(64),machine_id:'asset',dataset_id:'a'.repeat(64),hypothesis_index:0});
  h.requests[0].resolve({series_id:'e'.repeat(64),machine_id:'asset',dataset_id:'a'.repeat(64),vin:h.state.machine.serial_number,
    symptom_source:'user_question',symptom:'依据已保存的同机连续水温趋势核对散热器',search_terms:['散热器']});
  await tick();assert.equal(calls.length,1,'verified sensor question reaches the real research planner');
  const body=JSON.parse(calls[0].options.body);
  assert.equal(calls[0].url,'/assistant/xgss/research/plan');assert.equal(body.symptom_source,'user_question');
  assert.equal(body.manual_fault,undefined);assert.equal(body.engineering_fault,undefined);
  assert.match(body.symptom,/连续水温趋势/);
  h.stop.onclick();calls[0].resolve({research_id:'b'.repeat(32)});await run;
  const symptom=h.nodes.find(n=>n.id==='research-symptom');symptom.value='另外的人工故障问题';symptom.oninput();
  await h.nodes.find(n=>n.id==='research-run').onclick({force:true});
  assert.equal(calls.length,1,'editing the verified question restores ordinary draft validation');
  assert.equal(h.nodes.some(n=>n.textContent.includes('故障码尚未确认适用范围')),true);
});
test('sensor parts handoff exception never bypasses ordinary unconfirmed manual fault drafts',async()=>{
  for(const source of ['operator_report','user_question']){
    const h=harness({ready:false});await tick();const calls=controlledModels(h);
    h.sandbox.getManualFaultDraftReference=()=>({code:'H10101',model:'TV12U',applicability_confirmed:false});
    h.nodes.find(n=>n.id==='research-symptom').value='核对操纵杆控制回路的异常';
    h.nodes.find(n=>n.id==='research-symptom-source').value=source;
    await h.nodes.find(n=>n.id==='research-run').onclick({force:true});
    assert.equal(calls.length,0);
    assert.equal(h.nodes.some(n=>n.textContent.includes('故障码尚未确认适用范围')),true);
  }
});

test('sensor parts handoff manual draft edits restore validation even before a code is confirmed',async()=>{
  const h=harness({ready:false});await tick();const calls=controlledModels(h);
  h.sandbox.getManualFaultDraftReference=()=>({code:'H10101',model:'TV12U',applicability_confirmed:false});
  const run=h.window.openSensorSeriesParts({series_id:'e'.repeat(64),machine_id:'asset',dataset_id:'a'.repeat(64),hypothesis_index:0});
  h.requests[0].resolve({series_id:'e'.repeat(64),machine_id:'asset',dataset_id:'a'.repeat(64),vin:h.state.machine.serial_number,
    symptom_source:'user_question',symptom:'依据已保存的连续曲线核对散热器',search_terms:['散热器']});
  await tick();assert.equal(calls.length,1);
  h.stop.onclick();calls[0].resolve({research_id:'b'.repeat(32)});await run;
  h.sandbox.getManualFaultDraftReference=()=>({code:'H10102',model:'TV12U',applicability_confirmed:false});
  h.window.syncXGSSResearchFaults();
  await h.nodes.find(n=>n.id==='research-run').onclick({force:true});
  assert.equal(calls.length,1);
  assert.equal(h.nodes.some(n=>n.textContent.includes('故障码尚未确认适用范围')),true);
});


test('catalog images: duplicate captures show one card and one estimate with every condition retained',async()=>{
  const saved=focusedPartRecord(),part=saved.advice.parts[0];
  const first={...part,capture_id:'e'.repeat(64),source_id:'xpart:'+'e'.repeat(64)+':0',figure_ref:'9',reason:'第一分类关联',replacement_condition:'必须检查端子损坏'};
  const second={...part,reason:'第二分类关联',replacement_condition:'必须排除接地问题'};
  saved.advice={...saved.advice,parts:[first,second]};
  saved.evidence.parts=[first,second];
  saved.pages.push({capture_id:first.capture_id,content:{assembly_path:['第一分类']},illustrations:[]});
  const mounts=[],h=harness({focused:true,partsFocus:true,estimates:{mount:(root,options)=>{mounts.push(options);return {destroy(){}};}},fetchActive:async()=>faultReply(saved)});
  await tick();
  const cards=h.nodes.filter(node=>node.className==='fault-parts-card');assert.equal(cards.length,1);
  assert.equal(mounts[0].parts.length,1);
  assert.match(visibleText(cards[0]),/必须检查端子损坏/);assert.match(visibleText(cards[0]),/必须排除接地问题/);
  assert.equal(mounts[0].parts[0].capture_id,part.capture_id);
  const image=treeNodes(cards[0]).find(node=>node.tag==='img');
  assert.equal(image.src,`/assistant/xgss/research/${saved.research_id}/images/${'d'.repeat(64)}`);
  assert.ok(treeNodes(cards[0]).some(node=>node.textContent==='图中序号 4'));
  assert.ok(!treeNodes(cards[0]).some(node=>node.className==='fault-parts-image-empty'));
  assert.equal(saved.advice.parts.length,2,'rendering must not mutate saved evidence');
});

test('catalog images: same number with distinct part configuration is not merged or given another part image',async()=>{
  const saved=focusedPartRecord(),part=saved.advice.parts[0];
  saved.advice.parts.push({...part,name:part.name+'（配置B）',capture_id:'e'.repeat(64),source_id:'other'});
  const mounts=[],h=harness({focused:true,partsFocus:true,estimates:{mount:(root,options)=>{mounts.push(options);return {destroy(){}};}},fetchActive:async()=>faultReply(saved)});
  await tick();
  const cards=h.nodes.filter(node=>node.className==='fault-parts-card');assert.equal(cards.length,2);
  assert.equal(mounts[0].parts.length,2);
  assert.equal(treeNodes(cards[0]).filter(node=>node.tag==='img').length,1);
  assert.equal(treeNodes(cards[1]).filter(node=>node.tag==='img').length,0);
  assert.match(visibleText(cards[1]),/该分类尚未采集图示/);
});

test('catalog images: historical duplicate references do not inflate preparation estimates',async()=>{
  const saved=focusedPartRecord(),part=saved.advice.parts[0];
  saved.fault_context={trackunit_page:{status:'RESOLVED',description:'Transmission / Abnormal Update Rate'}};
  saved.advice={...saved.advice,parts:[],analysis_scope:'historical',historical_candidates:[
    {...part,preparation_condition:'先排除总线线缆问题'},
    {...part,capture_id:'e'.repeat(64),source_id:'other',preparation_condition:'再次复发时才考虑备库'}]};
  const mounts=[],h=harness({focused:true,partsFocus:true,estimates:{mount:(root,options)=>{mounts.push(options);return {destroy(){}};}},fetchActive:async()=>faultReply(saved)});
  await tick();
  const cards=h.nodes.filter(node=>node.className==='fault-parts-card');assert.equal(cards.length,1);
  assert.equal(mounts[0].parts.length,1);assert.equal(mounts[0].scope,'historical');
  assert.match(visibleText(cards[0]),/先排除总线线缆问题/);assert.match(visibleText(cards[0]),/再次复发时才考虑备库/);
});

function historicalDEFRecord(overrides={}){
  const saved=focusedPartRecord();
  return {...saved,symptom:'已解除的 DEF 温度历史故障',fault_context:{trackunit_page:{
    asset_id:'asset',source_url:'https://new.manager.trackunit.com/assets/asset/events',observed_at:'2026-09-25T12:00:00Z',
    description:'Aftertreatment 1 Diesel Exhaust Fluid Tank Temperature / Voltage Above Normal',
    code:'',spn:null,fmi:null,sa:null,status:'CLOSED',occurred_at:'Sep 21, 2026',cleared_at:'Sep 22, 2026',page_event_id:'history-def'}},
    advice:{...saved.advice,analysis_scope:'historical',parts:[],historical_candidates:saved.advice.parts},...overrides};
}

test('model schema recovery: a failed historical plan keeps the exact observation and retries planning once',async()=>{
  const saved=historicalDEFRecord({pages:[],evidence:{parts:[],manuals:[]},advice:undefined,analysis_revision:undefined});
  const h=harness({focused:true,partsFocus:true,fetchActive:async()=>faultReply(saved)});await tick();
  const calls=controlledModelErrors(h),button=h.nodes.find(n=>n.id==='research-run'),card=h.nodes.find(n=>n.id==='xgss-research');
  let run=button.onclick({force:true});assert.equal(calls[0].url,'/assistant/xgss/research/plan');
  const firstBody=JSON.parse(calls[0].options.body);calls[0].fail();await run;
  assert.equal(button.disabled,false);assert.equal(button.textContent,'重试配件推荐');
  assert.match(visibleText(card),/检索方向暂未生成。已选故障与补充信息仍保留/);
  assert.doesNotMatch(visibleText(card),/schema_validation|directions\[0\]|value_error/);
  assert.equal(firstBody.page_fault.status,'CLOSED');assert.equal(firstBody.page_fault.code,'');assert.equal(firstBody.page_fault.spn,null);
  assert.equal(calls.length,1,'no automatic model retry');
  run=button.onclick();assert.equal(calls.length,2);assert.equal(calls[1].url,calls[0].url);
  assert.deepEqual(JSON.parse(calls[1].options.body),firstBody,'retry never changes historical status or manufactures a fault code');
  calls[1].fail();await run;
});

test('model schema recovery: advice failure preserves matching cards images and estimate then retries the same research',async()=>{
  const saved=historicalDEFRecord(),mounts=[],h=harness({focused:true,partsFocus:true,
    estimates:{mount:(_root,options)=>{mounts.push(options);return {destroy(){}};}},fetchActive:async()=>faultReply(saved)});await tick();
  const button=h.nodes.find(n=>n.id==='research-run'),card=h.nodes.find(n=>n.id==='xgss-research');
  const originalCard=treeNodes(card).find(n=>n.className==='fault-parts-card');
  const image=treeNodes(originalCard).find(n=>n.tag==='img'),estimate=h.nodes.find(n=>n.id==='fault-parts-estimates');
  const calls=controlledModelErrors(h);let run=button.onclick();assert.match(calls[0].url,/\/analyze$/);calls[0].fail();await run;
  assert.equal(button.textContent,'重试配件分析');assert.equal(button.disabled,false);
  assert.match(visibleText(card),/本次配件分析暂未完成。已选故障和已读取的 XGSS 资料仍保留。下方仍为上次建议，尚未更新/);
  assert.ok(treeNodes(card).includes(originalCard));assert.ok(treeNodes(card).includes(image));
  assert.equal(estimate.hidden,false);assert.equal(mounts.length,1,'failure does not destroy or remount saved price input');
  assert.equal(h.nodes.find(n=>n.id==='research-result-hero').hidden,false);
  run=button.onclick();assert.equal(calls[1].url,calls[0].url);assert.equal(calls.length,2);
  calls[1].result(saved);await run;assert.equal(button.textContent,'更新配件推荐');
  assert.match(visibleText(card),/已生成备件与维修建议/);assert.doesNotMatch(visibleText(card),/尚未更新|schema_validation/);
});

test('model schema recovery: forced plan failure retains same-fault result and retry remains a plan request',async()=>{
  const saved=historicalDEFRecord(),h=harness({focused:true,partsFocus:true,fetchActive:async()=>faultReply(saved)});await tick();
  const card=h.nodes.find(n=>n.id==='xgss-research'),original=treeNodes(card).find(n=>n.className==='fault-parts-card');
  const calls=controlledModelErrors(h),button=h.nodes.find(n=>n.id==='research-run');
  let run=button.onclick({force:true});calls[0].fail();await run;
  assert.equal(h.nodes.find(n=>n.id==='research-result-hero').hidden,false);assert.ok(treeNodes(card).includes(original));
  assert.match(visibleText(card),/下方仍为上次建议，尚未更新/);
  run=button.onclick();assert.match(calls[1].url,/\/plan$/);calls[1].fail();await run;
});

test('model schema recovery: new fault failure never reveals previous fault cards or retries after an input change',async()=>{
  const saved=historicalDEFRecord(),h=harness({focused:true,partsFocus:true,fetchActive:async()=>faultReply(saved)});await tick();
  const symptom=h.nodes.find(n=>n.id==='research-symptom'),card=h.nodes.find(n=>n.id==='xgss-research'),button=h.nodes.find(n=>n.id==='research-run');
  const original=treeNodes(card).find(n=>n.className==='fault-parts-card');
  symptom.value='改变本次检查工况';symptom.oninput();
  const calls=controlledModelErrors(h);const run=button.onclick();calls[0].fail();await run;
  assert.equal(h.nodes.find(n=>n.id==='research-result-hero').hidden,true);
  assert.equal(h.nodes.find(n=>n.id==='fault-parts-estimates').hidden,true);assert.equal(treeNodes(card).includes(original),false);
  assert.doesNotMatch(visibleText(card),/下方仍为上次建议/);
  symptom.value='另一条补充信息';symptom.oninput();assert.equal(button.textContent,'生成配件推荐');
});

test('model schema recovery: other backend failures keep their distinct message',async()=>{
  const saved=historicalDEFRecord(),h=harness({focused:true,partsFocus:true,fetchActive:async()=>faultReply(saved)});await tick();
  const calls=controlledModelErrors(h),button=h.nodes.find(n=>n.id==='research-run'),card=h.nodes.find(n=>n.id==='xgss-research');
  const run=button.onclick();calls[0].fail('rate_limit','请求过于频繁，请稍后重试。');await run;
  assert.match(visibleText(card),/请求过于频繁，请稍后重试/);assert.doesNotMatch(visibleText(card),/检索方向暂未生成|本次配件分析暂未完成/);
  assert.equal(button.disabled,false);assert.equal(button.textContent,'更新配件推荐');
});

test('model schema recovery: late old-device failure does not replace the new device status',async()=>{
  const saved=historicalDEFRecord(),h=harness({focused:true,partsFocus:true,fetchActive:async()=>faultReply(saved)});await tick();
  const calls=controlledModelErrors(h),button=h.nodes.find(n=>n.id==='research-run'),card=h.nodes.find(n=>n.id==='xgss-research');
  const run=button.onclick();h.state.machine={...h.state.machine,machine_id:'other'};h.location.hash='#trackunit-asset=other';h.window.syncXGSSResearch();
  calls[0].fail();await run;
  assert.doesNotMatch(visibleText(card),/本次配件分析暂未完成|schema_validation/);
  assert.equal(button.disabled,true);assert.equal(button.textContent,'生成配件推荐');
});

function directReadyRecord(){
  return historicalDEFRecord({plan:{summary:'核对本机部件',directions:[{component:'风扇',reason:'核对适配与条件',search_terms:['风扇']}]}});
}
function controlledDirectRequests(h){
  const original=h.sandbox.fetch,calls=[];
  h.sandbox.fetch=(url,options)=>/\/(?:collect-direct|analyze|plan)$/.test(url)?new Promise(resolve=>calls.push({url,options,
    result:record=>resolve(streamedRecord(record)),fail:(kind,message)=>resolve(streamedFailure(kind,message)),
    httpFail:(kind,message)=>resolve({ok:false,json:async()=>({detail:{kind,message}})})})):original(url,options);
  return calls;
}
function directCollectedRecord(saved,overrides={}){
  return {...saved,advice:undefined,analysis_revision:undefined,
    direct_collection:{status:'completed',terms:['风扇'],capture_ids:saved.pages.map(p=>p.capture_id),unmatched_terms:[],unresolved:[],cached:false,revision:saved.revision,...overrides}};
}

test('direct collection: standalone saved plan reads XGSS and analyzes after one explicit click without a plugin',async()=>{
  const complete=directReadyRecord(),planned={...complete,revision:0,pages:[],evidence:{parts:[],manuals:[]},advice:undefined,analysis_revision:undefined};
  const h=harness({ready:false,focused:true,partsFocus:true,search:'',fetchActive:async()=>faultReply(planned)});await tick();
  const button=h.nodes.find(n=>n.id==='research-run'),calls=controlledDirectRequests(h);
  assert.equal(button.hidden,false);assert.equal(button.disabled,false);assert.equal(calls.length,0,'restoring a plan never starts cloud analysis');
  const action=button.onclick();await tick();assert.equal(calls.length,1);
  assert.match(calls[0].url,/\/collect-direct$/);assert.deepEqual(JSON.parse(calls[0].options.body),{expected_revision:0,terms:['风扇']});
  calls[0].result(directCollectedRecord(complete));await tick();
  assert.equal(calls.length,2);assert.match(calls[1].url,/\/analyze$/);assert.equal(h.requests.some(r=>r.url==='/assistant/xgss/open'),false);
  calls[1].result(complete);await action;
  assert.equal(button.disabled,false);assert.equal(h.nodes.find(n=>n.id==='research-result-hero').hidden,false);
  assert.ok(h.nodes.some(n=>n.tag==='img'));assert.equal(h.messages.some(m=>m.type==='jilian:research-start'),false);
});

test('direct collection: partial and cached results retain coverage and use their committed revision for AI',async()=>{
  for(const state of [{status:'partial',cached:false,unmatched_terms:['另一分类'],unresolved:['未完成分类']},{status:'completed',cached:true}]){
    const saved=directReadyRecord(),h=harness({focused:true,partsFocus:true,ready:false,search:'',fetchActive:async()=>faultReply(saved)});await tick();
    const calls=controlledDirectRequests(h),run=h.start.onclick();await tick();calls[0].result(directCollectedRecord(saved,state));await tick();
    assert.equal(calls[1].url,'/assistant/xgss/research/'+saved.research_id+'/analyze');
    calls[1].result(saved);await run;
    if(state.status==='partial')assert.ok(h.nodes.some(n=>n.textContent.includes('未完成分类')));
    assert.equal(h.requests.some(r=>r.url==='/assistant/xgss/open'),false);
  }
});

test('direct collection: only explicit unavailable auth schema or no-match errors fall back to the same plugin research',async()=>{
  for(const kind of ['direct_unavailable','direct_auth','direct_schema','direct_no_match']){
    const saved=directReadyRecord(),h=harness({focused:true,partsFocus:true,fetchActive:async()=>faultReply(saved)});await tick();
    const calls=controlledDirectRequests(h),run=h.start.onclick();await tick();calls[0].fail(kind);await tick();
    const open=h.requests.at(-1);assert.equal(open.url,'/assistant/xgss/open',kind);assert.equal(JSON.parse(open.options.body).vin,saved.vin);
    open.resolve({url:'https://xgss.xcmg.com/'});await run;
    const start=h.messages.find(m=>m.type==='jilian:research-start');assert.equal(start.request_id,saved.research_id);
    assert.ok(h.nodes.some(n=>n.textContent.includes('通过插件读取同 VIN 图册')));assert.equal(calls.length,1);h.stop.onclick();
  }
});

test('direct collection: fallback-unavailable standalone keeps original cards images and estimate without false success',async()=>{
  const saved=directReadyRecord(),mounts=[],h=harness({focused:true,partsFocus:true,ready:false,search:'',
    estimates:{mount:(_root,options)=>{mounts.push(options);return {destroy(){}};}},fetchActive:async()=>faultReply(saved)});await tick();
  const card=h.nodes.find(n=>n.id==='xgss-research'),old=treeNodes(card).find(n=>n.className==='fault-parts-card');
  const calls=controlledDirectRequests(h),run=h.start.onclick();await tick();calls[0].fail('direct_auth');await run;
  assert.ok(treeNodes(card).includes(old));assert.equal(h.nodes.find(n=>n.id==='fault-parts-estimates').hidden,false);assert.equal(mounts.length,1);
  assert.match(visibleText(card),/XGSS 暂未完成读取。已保存资料仍保留/);assert.equal(h.start.disabled,false);
  assert.equal(calls.length,1);assert.equal(h.requests.some(r=>r.url==='/assistant/xgss/open'),false);
});

test('direct collection: conflict identity busy evidence limit cancellation and unknown errors never fall back',async()=>{
  for(const kind of ['revision_changed','active_changed','direct_identity','busy','evidence_limit','cancel','network_error']){
    const saved=directReadyRecord(),h=harness({focused:true,partsFocus:true,fetchActive:async()=>faultReply(saved)});await tick();
    const calls=controlledDirectRequests(h),run=h.start.onclick();await tick();calls[0].fail(kind,'读取未完成：'+kind);await run;
    assert.equal(h.requests.some(r=>r.url==='/assistant/xgss/open'),false,kind);assert.equal(calls.length,1);
    assert.equal(h.nodes.find(n=>n.id==='research-result-hero').hidden,false);assert.equal(h.start.disabled,false);
    assert.ok(h.nodes.some(n=>n.textContent==='读取未完成：'+kind));
  }
});

test('direct collection: stop or device change aborts the request and cannot trigger fallback or AI from its late result',async()=>{
  for(const change of ['stop','device']){
    const saved=directReadyRecord(),h=harness({focused:true,partsFocus:true,fetchActive:async()=>faultReply(saved)});await tick();
    const calls=controlledDirectRequests(h),run=h.start.onclick();await tick();
    if(change==='stop')h.stop.onclick();else{h.state.machine={...h.state.machine,machine_id:'other'};h.location.hash='#trackunit-asset=other';h.window.syncXGSSResearch();}
    assert.equal(calls[0].options.signal.aborted,true);calls[0].result(directCollectedRecord(saved));await run;
    assert.equal(calls.length,1);assert.equal(h.requests.some(r=>r.url==='/assistant/xgss/open'),false);
    if(change==='device')assert.equal(h.nodes.find(n=>n.id==='research-result-hero').hidden,true);
  }
});

test('direct collection: a mismatched record identity is rejected without replacing saved parts or falling back',async()=>{
  for(const changed of [{research_id:'d'.repeat(32)},{machine_id:'other'},{dataset_id:'d'.repeat(64)},{vin:'OTHER'},{revision:-1}]){
    const saved=directReadyRecord(),h=harness({focused:true,partsFocus:true,fetchActive:async()=>faultReply(saved)});await tick();
    const card=h.nodes.find(n=>n.id==='xgss-research'),old=treeNodes(card).find(n=>n.className==='fault-parts-card');
    const calls=controlledDirectRequests(h),run=h.start.onclick();await tick();calls[0].result({...directCollectedRecord(saved),...changed});await run;
    assert.ok(treeNodes(card).includes(old));assert.match(visibleText(card),/返回资料与当前排查不一致/);
    assert.equal(calls.length,1);assert.equal(h.requests.some(r=>r.url==='/assistant/xgss/open'),false);
  }
});

test('direct collection: structured HTTP error kind follows the same explicit fallback rule',async()=>{
  for(const kind of ['direct_auth','revision_changed']){
    const saved=directReadyRecord(),h=harness({focused:true,partsFocus:true,fetchActive:async()=>faultReply(saved)});await tick();
    const calls=controlledDirectRequests(h),run=h.start.onclick();await tick();calls[0].httpFail(kind,'读取失败');await tick();
    if(kind==='direct_auth'){assert.equal(h.requests.at(-1).url,'/assistant/xgss/open');h.requests.at(-1).resolve({url:'https://xgss.xcmg.com/'});}
    else assert.equal(h.requests.some(r=>r.url==='/assistant/xgss/open'),false);
    await run;h.stop.onclick();
  }
});

test('direct collection: background source resumption does not introduce an automatic model request',async()=>{
  const full=directReadyRecord(),plan={...full,pages:[],revision:0,evidence:{parts:[],manuals:[]},advice:undefined,analysis_revision:undefined};
  const h=harness({focused:true,fetchActive:async()=>faultReply(plan),fetchDirect:async()=>streamedRecord(directCollectedRecord(full))});await tick();
  assert.equal(h.fetchCalls.filter(call=>call.url.endsWith('/collect-direct')).length,1);
  assert.equal(h.fetchCalls.some(call=>call.url.endsWith('/analyze')||call.url.endsWith('/plan')),false);
  assert.ok(h.nodes.some(n=>n.textContent==='XGSS 资料已读取，可生成配件建议。'));
});

test('direct collection: directory-only evidence does not imply ready parts or start AI',async()=>{
  const full=directReadyRecord(),plan={...full,pages:[],revision:0,evidence:{parts:[],manuals:[]},advice:undefined,analysis_revision:undefined};
  const root={...directCollectedRecord(full),evidence:{parts:[{source_id:'root',name:'整机',part_number:'TEST-ROOT',assembly_path:['整机']}],manuals:[]}};
  const h=harness({focused:true,partsFocus:true,ready:false,search:'',fetchActive:async()=>faultReply(plan)});await tick();
  const calls=controlledDirectRequests(h),button=h.nodes.find(n=>n.id==='research-run'),action=button.onclick();await tick();calls[0].result(root);await action;
  assert.equal(calls.length,1);assert.equal(button.textContent,'继续读取 XGSS 并推荐配件');
  assert.equal(h.nodes.find(n=>n.id==='research-result-hero').hidden,true);
  assert.ok(h.nodes.some(n=>n.textContent.includes('尚未取得可核对的部件')));
});

function appSearchGuidance(h){
  const app=fs.readFileSync(require.resolve('../app/assistant_ui/app.js'),'utf8');
  const begin=app.indexOf('function currentAISearchGuidance(){'),end=app.indexOf('function handleAIGuidanceRequest',begin);
  assert.ok(begin>=0&&end>begin);
  vm.runInNewContext(app.slice(begin,end),h.sandbox);
  return JSON.parse(JSON.stringify(h.sandbox.currentAISearchGuidance()));
}
test('extension guidance uses the current research plan instead of an older report',async()=>{
  const h=harness(),data=activeRecord({catalog_fault_code:'E4030',plan:{summary:'检查通信',directions:[
    {component:'控制器',reason:'核对通信连接',search_terms:['控制器','controller','控制器']}]}});
  await restoreResearch(h,data);
  h.sandbox.report={component_hypotheses:[{component:'旧部件',search_terms:['旧检索词']}]};
  const result=appSearchGuidance(h);
  assert.deepEqual(result.terms,['控制器','controller']);
  assert.deepEqual(result.components,[{name:'控制器',reason:'核对通信连接',reference_ids:[]}]);
  assert.equal(result.fault_code,'E4030');assert.equal(result.has_report,true);
  assert.equal(result.has_search_terms,true);assert.equal(result.machine_model,'XC948U');
  assert.equal('machine_id' in result,false);assert.equal('vin' in result,false);
  assert.deepEqual(data.plan.directions[0].search_terms,['控制器','controller','控制器']);
});
test('extension guidance drops a changed symptom or source without reviving older report terms',async()=>{
  for(const change of ['symptom','source']){
    const h=harness();await restoreResearch(h,activeRecord());
    h.sandbox.report={component_hypotheses:[{component:'旧部件',search_terms:['旧检索词']}]};
    if(change==='symptom'){const input=h.nodes.find(n=>n.id==='research-symptom');input.value='另一个问题';input.oninput();}
    else {const source=h.nodes.find(n=>n.id==='research-symptom-source');source.value='operator_report';source.onchange();}
    const result=appSearchGuidance(h);
    assert.deepEqual(result.terms,[],change);assert.equal(result.has_report,false,change);
  }
});
test('extension guidance cannot carry a plan across device, dataset or VIN changes before sync',async()=>{
  for(const change of ['machine_id','dataset_id','serial_number']){
    const h=harness();await restoreResearch(h,activeRecord());
    h.sandbox.report={component_hypotheses:[{component:'旧部件',search_terms:['旧检索词']}]};
    h.state.machine={...h.state.machine,[change]:'other'};
    const result=appSearchGuidance(h);
    assert.deepEqual(result.terms,[],change);assert.equal(result.has_report,false,change);
  }
});
test('extension guidance preserves legacy opened report search when no research is selected',()=>{
  const h=harness();h.sandbox.openedReport={component_hypotheses:[{component:'风扇',rationale:'检查风量',search_terms:['风扇']}]};
  const result=appSearchGuidance(h);assert.deepEqual(result.terms,['风扇']);assert.equal(result.has_report,true);
});
