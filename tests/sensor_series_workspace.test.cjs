const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const modulePath = require.resolve('../app/assistant_ui/sensor-series-workspace.js');
const {unitsForCSV,chartData,reportMatches,capturePageMatches} = require(modulePath);
const asset = '00000000-0000-0000-0000-000004760361';
const csv = 'Date and time,Engine Coolant Temperature (Water Temperature) (CAN 50278),Engine Speed (CAN 50286)\n"9/17/26, 5:00:05 AM EDT",47,1246.625\n"9/17/26, 5:02:05 AM EDT",65,1371.625';
const tick = () => new Promise(resolve => setImmediate(resolve));
function harness({embedded=true}={}) {
  const nodes=[],requests=[],messages=[],listeners={},options=[];
  function element(tag) {
    const n={tag,children:[],attributes:{},events:{},style:{},textContent:'',hidden:false,disabled:false,value:'',checked:false,
      append(...children){for(const child of children){if(child.parentNode)child.parentNode.children=child.parentNode.children.filter(row=>row!==child);child.parentNode=this;this.children.push(child);}},
      insertBefore(child,before){if(child.parentNode)child.parentNode.children=child.parentNode.children.filter(row=>row!==child);const index=this.children.indexOf(before);child.parentNode=this;this.children.splice(index<0?this.children.length:index,0,child);},
      replaceChildren(...children){for(const child of this.children)child.parentNode=null;this.children=[];this.append(...children);},
      setAttribute(key,value){this.attributes[key]=value;},addEventListener(key,fn){this.events[key]=fn;},click(){this.onclick?.();}};
    nodes.push(n);return n;
  }
  const risk=element('main');risk.id='risk-view';const snapshot=element('div');snapshot.id='risk-live';risk.append(snapshot);
  const title=element('h2');title.id='risk-title';const machineSelect=element('select');machineSelect.id='machine';
  const state={machine:{machine_id:asset,dataset_id:'a'.repeat(64),serial_number:'XUG948TEST',model:'XC948U',provenance:'user_supplied'}};
  const parent={postMessage:data=>messages.push(data)};
  const window={parent,addEventListener:(name,fn)=>listeners[name]=fn,renderRiskDemo:()=>{state.snapshotLoads=(state.snapshotLoads||0)+1;},
    echarts:{init:()=>({setOption:option=>options.push(option),clear(){},resize(){}})}};
  if(!embedded)window.parent=window;
  const document={getElementById:id=>nodes.find(node=>node.id===id)||null,createElement:element};
  const location={search:embedded?'?panel=connection':'',ancestorOrigins:embedded?['chrome-extension://'+'a'.repeat(32)]:[]};
  const sandbox={window,document,location,selected:()=>state.machine,URL,URLSearchParams,Date,TextEncoder,Uint8Array,
    crypto:{getRandomValues:bytes=>bytes.fill(2)},setTimeout:()=>1,clearTimeout:()=>{},
    api:(path,opts)=>new Promise((resolve,reject)=>requests.push({path,opts,resolve,reject}))};
  vm.runInNewContext(fs.readFileSync(modulePath,'utf8'),sandbox);
  const node=id=>document.getElementById(id);
  const report=extra=>({series_id:'b'.repeat(64),machine_id:asset,dataset_id:'a'.repeat(64),model:'XC948U',binding:'当前资产导出',unit_status:'confirmed_metric',
    sample_count:2,window:{start:'2026-09-17T05:00:05-04:00',end:'2026-09-17T05:02:05-04:00'},
    channels:[{key:'coolant_c',label:'冷却液温度',unit:'°C',count:2,min:47,max:65}],
    chart_points:[{timestamp:'2026-09-17T05:00:05-04:00',coolant_c:47},{timestamp:'2026-09-17T05:02:05-04:00',coolant_c:65}],
    segments:[{}],quality:{gap_count:0,median_interval_seconds:120,max_gap_seconds:120},evidence:[],ai_analysis:null,...extra});
  const send=(data,extra={})=>listeners.message({source:parent,origin:location.ancestorOrigins[0],data:{protocol:1,connection_id:'connection',asset_id:state.machine.machine_id,dataset_id:state.machine.dataset_id,...data},...extra});
  const ready=()=>send({type:'jilian:sensor-series-ready',available:true});
  const load=async()=>{const promise=window.renderRiskDemo();requests.at(-1).resolve(report());await promise;};
  return {nodes,node,state,requests,messages,listeners,window,report,send,ready,load,options};
}
test('CSV unit confirmation covers only supported exported columns',()=>{
  assert.deepEqual(unitsForCSV(csv),{coolant_c:'°C',engine_rpm:'rpm'});
  assert.deepEqual(unitsForCSV('Date and time,Fuel (CAN 12345)\n1,2'),{});
});
test('chart gaps and missing samples cannot become continuous lines or zeroes',()=>{
  const points=[{timestamp:'2026-09-17T05:00:00Z',coolant_c:40},{timestamp:'2026-09-17T05:02:00Z',coolant_c:null},
    {timestamp:'2026-09-18T05:00:00Z',coolant_c:60,break_before:true}];
  const result=chartData(points,'coolant_c');
  assert.equal(result.length,4);assert.equal(result[1][1],null);assert.equal(result[2][1],null);assert.equal(result[3][1],60);
  assert.equal(chartData(points,'engine_rpm').every(row=>row[1]===null),true);
});
test('report and export source matching reject foreign devices and hostile URLs',()=>{
  assert.equal(reportMatches({machine_id:'a',dataset_id:'x'},{machine_id:'a',dataset_id:'y'}),false);
  assert.equal(capturePageMatches(`https://manager.trackunit.com/assets/${asset}/insights`,asset),true);
  assert.equal(capturePageMatches(`https://evil.example/assets/${asset}/insights`,asset),false);
  assert.equal(capturePageMatches(`https://new.manager.trackunit.com/assets/${asset}/insights?token=x`,asset),false);
  assert.equal(capturePageMatches(`https://new.manager.trackunit.com/assets/other/insights`,asset),false);
});
test('continuous view loads stored observations without calling AI and leaves snapshot collapsed',async()=>{
  const h=harness();await h.load();assert.equal(h.requests.length,1);assert.match(h.requests[0].path,/\/latest\?/);
  assert.equal(h.node('sensor-series-result').hidden,false);assert.equal(h.state.snapshotLoads,undefined);
  assert.equal(h.options.length,1);assert.equal(h.options[0].series[0].connectNulls,false);
  assert.equal(h.node('sensor-series-read').hidden,false);
  const standalone=harness({embedded:false});await standalone.load();
  assert.equal(standalone.node('sensor-series-read').hidden,true);
  assert.equal(standalone.node('sensor-series-import-open').hidden,false);
  assert.equal(standalone.node('sensor-series-import-open').disabled,false);
});
test('late AI results are discarded after switching devices',async()=>{
  const h=harness();await h.load();const task=h.node('sensor-series-analyze').onclick();
  h.state.machine={...h.state.machine,machine_id:'other'};const next=h.window.renderRiskDemo();
  h.requests[1].resolve(h.report({ai_analysis:{summary:'OLD AI RESULT',hypotheses:[]}}));await task;
  h.requests[2].reject(Object.assign(new Error('missing'),{status:404}));await next;
  assert.equal(h.node('sensor-series-result').hidden,true);
  assert.equal(h.nodes.some(node=>node.textContent==='OLD AI RESULT'),false);
});
test('CSV import requires explicit unit and asset confirmation and sends captured units only',async()=>{
  const h=harness();await h.load();const input=h.node('sensor-series-file');input.files=[{size:csv.length,name:'sensors.csv',text:async()=>csv}];
  await input.onchange();assert.equal(h.node('sensor-series-import-save').disabled,true);
  await h.node('sensor-series-import-save').onclick();assert.equal(h.requests.length,1);
  h.node('sensor-series-confirmed').checked=true;h.node('sensor-series-confirmed').onchange();
  const saving=h.node('sensor-series-import-save').onclick();const payload=JSON.parse(h.requests[1].opts.body);
  assert.equal(payload.machine_id,asset);assert.equal(payload.origin,'user_confirmed_export');assert.deepEqual(payload.units,{coolant_c:'°C',engine_rpm:'rpm'});
  h.requests[1].resolve(h.report());await saving;assert.equal(h.node('sensor-series-result').hidden,false);
  let fileRead=false;
  input.files=[{size:3000001,name:'large.csv',text:async()=>{fileRead=true;return csv;}}];
  await input.onchange();assert.equal(fileRead,false);assert.match(h.node('sensor-series-status').textContent,/3 MB/);
  input.files=[{size:1,name:'oversized-content.csv',text:async()=>csv+' '.repeat(3000001)}];
  await input.onchange();assert.equal(h.node('sensor-series-import-save').disabled,true);
  assert.match(h.node('sensor-series-status').textContent,/3 MB/);
});
test('extension capture rejects messages from other windows and mismatched requests',async()=>{
  const h=harness();await h.load();h.ready();h.node('sensor-series-read').onclick();
  const request=h.messages.find(message=>message.type==='jilian:sensor-series-start');
  const capture={schema_version:1,source:'trackunit_csv_export',asset_id:asset,page_url:`https://new.manager.trackunit.com/assets/${asset}/insights`,captured_at:'2026-09-24T12:00:00Z',csv_text:csv};
  h.send({type:'jilian:sensor-series-result',request_id:request.request_id,capture},{source:{}});
  h.send({type:'jilian:sensor-series-result',request_id:'0'.repeat(32),capture});
  assert.equal(h.node('sensor-series-import-save').disabled,true);assert.equal(h.node('sensor-series-stop').hidden,false);
  h.send({type:'jilian:sensor-series-result',request_id:request.request_id,capture});
  assert.equal(h.node('sensor-series-stop').hidden,true);assert.match(h.node('sensor-series-status').textContent,/核对设备与单位/);
});
test('a late local file read cannot attach another machines data after selection changes',async()=>{
  const h=harness();await h.load();let complete;
  h.node('sensor-series-file').files=[{size:csv.length,name:'old.csv',text:()=>new Promise(resolve=>complete=resolve)}];
  const read=h.node('sensor-series-file').onchange();h.state.machine={...h.state.machine,machine_id:'other'};
  complete(csv);await read;assert.equal(h.node('sensor-series-import-save').disabled,true);
});
test('parts handoff passes saved series and hypothesis identity without overwriting fault text',async()=>{
  const h=harness();let handoff;
  h.window.openSensorSeriesParts=async value=>{handoff=value;};
  const load=h.window.renderRiskDemo();h.requests[0].resolve(h.report({ai_analysis:{summary:'已发现趋势线索',hypotheses:[{failure_mode:'散热能力待检查',priority:'watch',reason:'温度与负载变化',evidence_ids:[],search_terms:['散热器'],inspection:'核对散热器清洁度'}]}}));await load;
  await h.node('sensor-series-parts-0').onclick();
  assert.equal(handoff.series_id,'b'.repeat(64));assert.equal(handoff.hypothesis_index,0);assert.equal(handoff.machine_id,asset);
  assert.equal('symptom' in handoff,false);assert.equal('fault_code' in handoff,false);
});
