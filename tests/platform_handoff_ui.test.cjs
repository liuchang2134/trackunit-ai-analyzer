const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const PlatformContext=require('../app/assistant_ui/platform-context.js');
const {InvestigationDrafts}=require('../app/assistant_ui/investigation-drafts.js');
const source=fs.readFileSync(path.join(__dirname,'../app/assistant_ui/app.js'),'utf8');
const functions=source.slice(source.indexOf('async function refresh('),source.indexOf("window.addEventListener('hashchange'"));
const assetA='00000000-0000-0000-0000-000000000001';
const assetB='00000000-0000-0000-0000-000000000002';
const row=(asset,version)=>({machine_id:asset,trackunit_asset_id:asset,
  selection_id:'dataset:'+version.repeat(64),dataset_id:version.repeat(64),provenance:'user_supplied',
  model:'XE55U',serial_number:'LOCAL-'+asset.slice(-1),dataset_name:'历史工时',sample_count:12,
  last_seen_at:'2026-09-15T09:00:00Z'});
const a1=row(assetA,'a'),a2=row(assetA,'b'),b1=row(assetB,'c'),b2=row(assetB,'d');

class Element {
  constructor(tag='div'){this.tag=tag;this.children=[];this._value='';this.textContent='';this.hidden=true;this.disabled=false;this.dataset={};this.attributes={};}
  options(){return this.children.flatMap(child=>child.tag==='optgroup'?child.options():child.tag==='option'?[child]:[]);}
  get value(){return this._value;}
  set value(value){this._value=this.tag==='select'&&!this.options().some(option=>option.value===value)?'':value;}
  replaceChildren(...children){this.children=[...children];if(this.tag==='select')this._value=this.options()[0]?.value||'';}
  append(...children){this.children.push(...children);}
  prepend(child){this.children.unshift(child);}
  setAttribute(name,value){this.attributes[name]=value;}
  getAttribute(name){return this.attributes[name]??null;}
  focus(){}
  scrollIntoView(){}
}
function harness({machines=[a1],hash=assetA,selection=a1.selection_id}={}){
  const elements=new Map(),selectionEvents=[],notifications=[],requests=[];
  const get=id=>{if(!elements.has(id))elements.set(id,new Element(id==='machine'?'select':'div'));return elements.get(id);};
  get('machine').replaceChildren(...machines.map(m=>Object.assign(new Element('option'),{value:m.selection_id})));
  get('machine').value=selection;
  get('task').value='comprehensive';get('language').value='zh';
  const context={machines,defaultSource:'trackunit_cache',location:{hash:'#trackunit-asset='+hash},
    document:{createElement:tag=>new Element(tag),querySelector:()=>new Element()},$:get,
    platformIndexState:'ready',deviceIndexRequest:0,deviceIndexWarnings:[],pendingPlatformContext:false,report:{summary:'old report'},priorRecordId:null,
    investigationDrafts:new InvestigationDrafts(),PlatformContext,
    api:route=>route==='/assistant/catalog'?Promise.resolve({total:3,demo:1}):new Promise((resolve,reject)=>requests.push({resolve,reject})),
    selected:()=>context.machines.find(m=>m.selection_id===get('machine').value),
    clearReport:()=>{context.report=null;},updateTask:()=>{},displayDate:value=>value||'未知',setView:()=>{},
    refreshDeviceOverview:()=>selectionEvents.push(get('machine').value),
    notifyPlatformContext:()=>notifications.push(PlatformContext.snapshot({hash:context.location.hash,
      machines:context.machines,source:context.defaultSource,selectionId:get('machine').value,indexState:context.platformIndexState,pending:context.pendingPlatformContext})),
    notifyAssistantPanel:()=>{}};
  vm.runInNewContext(functions,context);
  return {context,get,selectionEvents,notifications,requests};
}
const complete=(request,devices)=>request.resolve({devices,data_source:'trackunit_cache',warnings:[]});

test('refresh applies only the latest platform asset and never selects an unrelated first row',async()=>{
  const h=harness();h.context.selectMachine();h.selectionEvents.length=0;
  h.get('question').value='A only';h.get('observations').value='observed A';
  const loading=h.context.refresh();
  h.context.location.hash='#trackunit-asset='+assetB;
  complete(h.requests[0],[a1,b1]);await loading;
  assert.deepEqual(h.selectionEvents,[b1.selection_id]);
  assert.equal(h.get('question').value,'');assert.equal(h.get('observations').value,'');
  assert.equal(h.get('machine').value,b1.selection_id);
  h.context.location.hash='#trackunit-asset='+assetA;h.context.applyPlatformContext();
  assert.equal(h.get('question').value,'A only');assert.equal(h.get('observations').value,'observed A');
});

test('refresh preserves the operator-selected version including a selection made while loading',async()=>{
  const h=harness({machines:[a1,a2]});h.context.selectMachine();
  const loading=h.context.refresh();
  h.get('machine').value=a2.selection_id;h.context.selectMachine();h.get('observations').value='version two';
  h.selectionEvents.length=0;complete(h.requests[0],[a1,a2]);await loading;
  assert.equal(h.get('machine').value,a2.selection_id);assert.equal(h.get('observations').value,'version two');
  assert.deepEqual(h.selectionEvents,[a2.selection_id]);
  assert.match(h.get('machine-note').textContent,/XE55U.*LOCAL-1.*2 个本地数据版本.*已保留/);
  assert.match(h.get('machine').options()[1].textContent,/最近采样 2026-09-15T09:00:00Z/);
});

test('same-asset acknowledgement preserves the report and draft without reselecting',()=>{
  const h=harness({machines:[a1,a2],selection:a2.selection_id});
  h.context.selectMachine();h.context.report={summary:'completed analysis'};h.selectionEvents.length=0;
  h.get('observations').value='keep this';h.context.applyPlatformContext();
  assert.equal(h.context.report.summary,'completed analysis');assert.equal(h.get('observations').value,'keep this');
  assert.equal(h.get('machine').value,a2.selection_id);assert.deepEqual(h.selectionEvents,[]);
  assert.equal(h.notifications.at(-1).state,'matched');
});

test('new ambiguous or missing platform asset stays unselected with no fallback machine',()=>{
  const h=harness({machines:[a1,b1,b2]});h.context.selectMachine();h.get('observations').value='A only';
  h.context.location.hash='#trackunit-asset='+assetB;h.context.applyPlatformContext();
  assert.equal(h.get('machine').value,'');assert.equal(h.get('observations').value,'');
  assert.equal(h.notifications.at(-1).state,'choose_version');
  assert.match(h.get('machine-note').textContent,/LOCAL-2.*2 个本地数据版本/);
  h.context.location.hash='#trackunit-asset=00000000-0000-0000-0000-000000000003';h.context.applyPlatformContext();
  assert.equal(h.get('machine').value,'');assert.equal(h.notifications.at(-1).state,'missing');
});

test('a late index response or error cannot overwrite a newer refresh',async()=>{
  for(const olderFails of [false,true]){
    const h=harness();const older=h.context.refresh();const newer=h.context.refresh();
    h.context.location.hash='#trackunit-asset='+assetB;complete(h.requests[1],[b1]);await newer;
    if(olderFails)h.requests[0].reject(new Error('stale failure'));else complete(h.requests[0],[a1]);
    await older;
    assert.equal(h.context.platformIndexState,'ready');assert.equal(h.get('machine').value,b1.selection_id);
    assert.deepEqual(h.context.machines,[b1]);assert.doesNotMatch(h.get('status').textContent,/stale failure/);
  }
});

test('an already-loading index cannot switch device while AI is using its evidence',async()=>{
  const h=harness();h.context.selectMachine();h.selectionEvents.length=0;
  const loading=h.context.refresh();
  h.get('form').setAttribute('aria-busy','true');
  h.context.location.hash='#trackunit-asset='+assetB;
  complete(h.requests[0],[a1,b1]);await loading;
  assert.equal(h.context.pendingPlatformContext,true);assert.equal(h.get('machine').value,a1.selection_id);
  assert.deepEqual(h.selectionEvents,[]);assert.equal(h.notifications.at(-1).state,'pending');
  h.get('form').setAttribute('aria-busy','false');h.context.pendingPlatformContext=false;
  const afterAnalysis=h.context.refresh(true);complete(h.requests[1],[a1,b1]);await afterAnalysis;
  assert.equal(h.get('machine').value,b1.selection_id);assert.deepEqual(h.selectionEvents,[b1.selection_id]);
});
