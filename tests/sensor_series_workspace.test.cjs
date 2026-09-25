const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const modulePath = require.resolve('../app/assistant_ui/sensor-series-workspace.js');
const {unitsForCSV,channelsForCSV,chartData,reportMatches,capturePageMatches,displayLabel,choiceLabel} = require(modulePath);
const asset = '00000000-0000-0000-0000-000004760361';
const csv = 'Date and time,Engine Coolant Temperature (Water Temperature) (CAN 50278),Engine Speed (CAN 50286)\n"9/17/26, 5:00:05 AM EDT",47,1246.625\n"9/17/26, 5:02:05 AM EDT",65,1371.625';
const tick = () => new Promise(resolve => setImmediate(resolve));
function harness({embedded=true,partsFocus=false}={}) {
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
  const document={documentElement:{classList:{contains:cls=>partsFocus&&cls==='fault-parts-focus'}},getElementById:id=>nodes.find(node=>node.id===id)||null,createElement:element};
  const location={search:embedded?'?panel=connection':'',ancestorOrigins:embedded?['chrome-extension://'+'a'.repeat(32)]:[]};
  const sandbox={window,document,location,setView:(view)=>{state.view=view;},selected:()=>state.machine,URL,URLSearchParams,Date,TextEncoder,Uint8Array,
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
  assert.equal(payload.machine_id,asset);assert.equal(payload.origin,'user_confirmed_export');assert.deepEqual(payload.exports[0].units,{coolant_c:'°C',engine_rpm:'rpm'});
  assert.equal(h.requests[1].path,'/assistant/sensor-series/import-batch');assert.equal(payload.exports.length,1);
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
test('potential parts opens under its risk card with exact saved context and no homepage navigation',async()=>{
  const h=harness({partsFocus:true});let handoff,complete;
  h.window.SensorPotentialParts={cancelAll(){},open:async value=>{handoff=value;await new Promise(resolve=>complete=resolve);}};
  const analysis={summary:'当前保存的风险分析',hypotheses:[{failure_mode:'散热能力待检查',priority:'watch',reason:'温度变化',search_terms:['散热器']}]};
  const load=h.window.renderRiskDemo();h.requests[0].resolve(h.report({ai_analysis:analysis}));await load;
  const button=h.node('sensor-series-parts-0');
  assert.equal(button.textContent,'潜在故障配件');assert.equal(button.disabled,false);
  const opened=button.onclick();assert.equal(button.disabled,true);
  assert.equal(handoff.target.id,'sensor-potential-parts-0');assert.equal(handoff.target.parentNode,h.node('sensor-series-parts-0').parentNode);
  assert.equal(handoff.seriesId,'b'.repeat(64));assert.equal(handoff.hypothesisIndex,0);
  assert.equal(handoff.machine.machine_id,asset);assert.equal(handoff.machine.serial_number,'XUG948TEST');
  assert.equal(JSON.stringify(handoff.hypothesis),JSON.stringify(analysis.hypotheses[0]));
  assert.equal(handoff.analysisKey,JSON.stringify(analysis));assert.equal(handoff.isCurrent(),true);
  assert.equal(h.state.view,undefined);assert.equal(h.requests.length,1);
  h.state.machine={...h.state.machine,serial_number:'OTHER'};assert.equal(handoff.isCurrent(),false);
  complete();await opened;assert.equal(button.disabled,false);
});

test('replacing sensor analysis cancels prior card work and invalidates its callback',async()=>{
  const h=harness();let context,cancellations=0;
  h.window.SensorPotentialParts={cancelAll(){cancellations++;},open:async value=>{context=value;}};
  const analysis={summary:'旧风险',hypotheses:[{failure_mode:'散热能力待检查',search_terms:['散热器']}]};
  let load=h.window.renderRiskDemo();h.requests.at(-1).resolve(h.report({ai_analysis:analysis}));await load;
  await h.node('sensor-series-parts-0').onclick();assert.equal(context.isCurrent(),true);
  const count=cancellations;
  load=h.window.renderRiskDemo();h.requests.at(-1).resolve(h.report({ai_analysis:{...analysis,summary:'新风险'}}));await load;
  assert.equal(context.isCurrent(),false);assert.ok(cancellations>count);
  assert.equal(h.state.view,undefined);
});

test('dynamic CSV columns retain observed units and never infer units for unknown CAN identifiers',()=>{
  const input='Date and time,"Fuel, rate (CAN 55001)",DEF Temperature (°C) (CAN 55002),Packed Fault (CAN 55003)\n2026-09-24T00:00:00Z,1,20,18446744073709551615';
  const columns=channelsForCSV(input,{can_55001:{unit:'L/h'},can_55003:{unit:'raw',kind:'continuous'}});
  assert.deepEqual(columns.map(row=>[row.key,row.unit,row.kind]),[['can_55001','L/h','continuous'],['can_55002','°C','continuous'],['can_55003','raw','code']]);
  assert.equal(channelsForCSV('Date and time,New Sensor (CAN 99999)\n2026-09-24T00:00:00Z,42')[0].unit,'');
  assert.equal(channelsForCSV(csv,{coolant_c:{unit:''}})[0].unit,'');
  assert.equal(channelsForCSV('Date and time,Fuel (CAN 99999)\n2026-09-24T00:00:00Z,42',{}, {},[{name:'Different sensor',unit:'L'}])[0].unit,'');
});

test('all 54 channels are selectable while only four plots are shown and packed codes stay exact text',async()=>{
  const h=harness(),channels=Array.from({length:54},(_,i)=>({key:`can_${55000+i}`,label:`Signal ${i}`,unit:'V',kind:'continuous',count:3,min:1,max:2}));
  channels[4]={...channels[4],label:'Engine state',unit:'state',kind:'state'};
  channels[5]={...channels[5],label:'Packed diagnostic code',unit:'raw',kind:'code'};
  const points=[{timestamp:'2026-09-24T00:00:00Z',...Object.fromEntries(channels.map(channel=>[channel.key,1])),can_55005:'18446744073709551615'}];
  const load=h.window.renderRiskDemo();h.requests[0].resolve(h.report({channels,chart_points:points,ai_available:true}));await load;
  assert.equal(h.options.at(-1).series.length,4);
  assert.equal(h.node('sensor-series-channel-0').children.length,55);
  const first=h.node('sensor-series-channel-0');first.value='can_55005';first.onchange();
  assert.equal(h.options.at(-1).series.length,3);
  assert.ok(h.node('sensor-series-code-readings').children[0].children.some(node=>node.textContent.includes('18446744073709551615')));
  const latest=h.nodes.filter(node=>node.id==='sensor-series-channel-0').at(-1);latest.value='can_55004';latest.onchange();
  assert.equal(h.options.at(-1).series[0].step,'end');
  assert.equal(h.options.at(-1).series[0].connectNulls,false);
});

test('batch capture forwards only validated CSV metadata in one atomic import request',async()=>{
  const h=harness();await h.load();h.ready();h.node('sensor-series-read').onclick();
  const request=h.messages.find(message=>message.type==='jilian:sensor-series-start');
  const extra='Date and time,Engine Fuel Rate (CAN 55001)\n2026-09-24T00:00:00Z,1\n2026-09-24T00:01:00Z,2\n2026-09-24T00:02:00Z,3';
  const capture={schema_version:2,source:'trackunit_csv_export',asset_id:asset,page_url:`https://new.manager.trackunit.com/assets/${asset}/insights/advanced-sensors`,captured_at:'2026-09-24T12:00:00Z',exports:[{csv_text:csv,rows:2,channels:['extra']},{csv_text:extra,units:{can_55001:'L/h'},channel_metadata:{can_55001:{label:'Engine Fuel Rate',unit:'L/h',kind:'continuous'}}}],collection:{complete:false,failed_sensors:['Unread']}};
  h.send({type:'jilian:sensor-series-result',request_id:request.request_id,capture});
  assert.match(h.node('sensor-series-status').textContent,/部分信号未能读取/);
  assert.equal(h.requests.length,1);h.node('sensor-series-confirmed').checked=true;
  const saving=h.node('sensor-series-import-save').onclick();assert.equal(h.requests.length,2);
  const body=JSON.parse(h.requests[1].opts.body);assert.equal(body.exports.length,2);assert.equal(body.exports[1].units.can_55001,'L/h');
  assert.deepEqual(Object.keys(body.exports[0]).sort(),['channel_metadata','csv_text','units']);
  assert.equal(body.exports[1].csv_text,extra);assert.equal(body.page_url,capture.page_url);
  h.requests[1].resolve(h.report({series_id:'c'.repeat(64),ai_available:true,ai_analysis:null}));await saving;
  assert.match(h.node('sensor-series-status').textContent,/仍有未读通道/);
  assert.equal(h.node('sensor-series-analyze').hidden,false);assert.equal(h.requests.length,2);
});

test('multiple manual exports require one confirmation and unknown units remain missing',async()=>{
  const h=harness({embedded:false});await h.load();
  const extra='Date and time,New pressure (CAN 99999)\n2026-09-24T00:00:00Z,100\n2026-09-24T00:01:00Z,101\n2026-09-24T00:02:00Z,102';
  const file=h.node('sensor-series-file');assert.equal(file.multiple,true);
  file.files=[{name:'one.csv',size:csv.length,text:async()=>csv},{name:'two.csv',size:extra.length,text:async()=>extra}];await file.onchange();
  assert.equal(h.node('sensor-series-import-save').disabled,true);assert.equal(h.requests.length,1);
  h.node('sensor-series-confirmed').checked=true;
  const saving=h.node('sensor-series-import-save').onclick(),body=JSON.parse(h.requests[1].opts.body);
  assert.equal(body.exports.length,2);assert.deepEqual(body.exports[1].units,{});
  assert.equal(body.exports[1].channel_metadata.can_99999.label,'New pressure');
  h.requests[1].resolve(h.report({ai_available:true,unit_status:'partially_confirmed'}));await saving;
  assert.equal(h.node('sensor-series-analyze').disabled,false);
});

test('failed batch import preserves prior curves and allows retry without issuing AI',async()=>{
  const h=harness();await h.load();h.node('sensor-series-file').files=[{name:'one.csv',size:csv.length,text:async()=>csv}];await h.node('sensor-series-file').onchange();
  h.node('sensor-series-confirmed').checked=true;
  const saving=h.node('sensor-series-import-save').onclick();h.requests[1].reject(new Error('同一时点存在冲突数据'));await saving;
  assert.match(h.node('sensor-series-status').textContent,/冲突数据/);assert.equal(h.node('sensor-series-result').hidden,false);
  assert.equal(h.node('sensor-series-import-save').disabled,false);assert.equal(h.requests.length,2);assert.equal(h.options.length,1);
});

test('batch rejects a foreign source and conflicting units before any import',async()=>{
  const h=harness();await h.load();h.ready();h.node('sensor-series-read').onclick();
  const request=h.messages.find(message=>message.type==='jilian:sensor-series-start');
  const capture={schema_version:2,source:'trackunit_csv_export',asset_id:asset,page_url:`https://new.manager.trackunit.com/assets/${asset}/insights`,captured_at:'2026-09-24T12:00:00Z',exports:[{csv_text:csv,page_url:'https://new.manager.trackunit.com/assets/00000000-0000-0000-0000-000000000001/insights'}]};
  h.send({type:'jilian:sensor-series-result',request_id:request.request_id,capture});assert.match(h.node('sensor-series-status').textContent,/来源与当前设备不一致/);
  assert.equal(h.node('sensor-series-import-save').disabled,true);assert.equal(h.requests.length,1);
  h.ready();h.node('sensor-series-read').onclick();capture.exports=[{csv_text:csv,units:{coolant_c:'°C'}},{csv_text:csv,units:{coolant_c:'°F'}}];
  h.send({type:'jilian:sensor-series-result',request_id:request.request_id,capture});assert.match(h.node('sensor-series-status').textContent,/单位不一致/);
  assert.equal(h.node('sensor-series-import-save').disabled,true);assert.equal(h.requests.length,1);
});

test('state or code only records remain viewable without enabling AI',async()=>{
  const h=harness(),load=h.window.renderRiskDemo();h.requests[0].resolve(h.report({ai_available:false,unit_status:'confirmed_metric',channels:[{key:'can_55001',label:'Fault code',unit:'raw',kind:'code',count:3,latest:'18446744073709551615',latest_at:'2026-09-24T00:00:00Z'},{key:'can_55002',label:'Engine state',unit:'state',kind:'state',count:3,latest:'Stopped',latest_at:'2026-09-24T00:00:00Z'}],chart_points:[{timestamp:'2026-09-24T00:00:00Z',can_55001:null,can_55002:null}]}));await load;
  assert.equal(h.node('sensor-series-chart').hidden,true);assert.equal(h.node('sensor-series-analyze').disabled,true);
  await h.node('sensor-series-analyze').onclick();assert.equal(h.requests.length,1);
  assert.ok(h.node('sensor-series-code-readings').children[0].children.some(node=>node.textContent.includes('18446744073709551615')));
  assert.ok(h.node('sensor-series-code-readings').children[1].children.some(node=>node.textContent.includes('Stopped')));
});

test('INPUT columns and engine identity exports retain source units and text classification',()=>{
  const source='Date and time,Transmission Current Gear (CAN 50330),Engine Make_Model_Serial (CAN 50580),INPUT1 (INPUT1)\n2026-09-24T00:00:00Z,N,CMMNS*6B S5 D067       *22566122****,';
  const channels=channelsForCSV(source,{}, {},[{name:'Input 1',unit:'Status'}]);
  assert.deepEqual(channels.map(row=>[row.key,row.kind,row.unit]),[['can_50330','state',''],['can_50580','code',''],['input_1','state','Status']]);
  assert.equal(channels[2].label,'Input 1');
  assert.equal(channelsForCSV('Date and time,INPUT 5 (INPUT5)\n2026-09-24T00:00:00Z,1')[0].key,'input_5');
  assert.deepEqual(channelsForCSV('Date and time,OUTPUT1 (OUTPUT1)\n2026-09-24T00:00:00Z,1')[0],{key:'output_1',label:'Output 1',kind:'state',unit:''});
  assert.throws(()=>channelsForCSV('Date and time,INPUT1 (INPUT2)\n2026-09-24T00:00:00Z,1'),/无法识别/);
  assert.throws(()=>channelsForCSV('Date and time,INPUT7 (INPUT7)\n2026-09-24T00:00:00Z,1'),/无法识别/);
});

test('text gear state and engine identity appear as raw readings without numeric coercion',async()=>{
  const h=harness(),load=h.window.renderRiskDemo();
  const identity='CMMNS*6B S5 D067       *22566122**************************************************************';
  h.requests[0].resolve(h.report({ai_available:false,channels:[{key:'can_50580',label:'Engine Make_Model_Serial',kind:'code',latest:identity,latest_at:'2026-09-24T00:00:00Z'},{key:'can_50330',label:'Transmission Current Gear',kind:'state',latest:'N',latest_at:'2026-09-24T00:00:00Z'}],chart_points:[]}));await load;
  const readings=h.node('sensor-series-code-readings');
  assert.ok(readings.children[0].children.some(node=>node.textContent.endsWith(identity)));
  assert.ok(readings.children[1].children.some(node=>node.textContent.endsWith(' · N')));
  assert.equal(h.node('sensor-series-chart').hidden,true);assert.equal(h.node('sensor-series-analyze').disabled,true);
});

test('default charts prefer the original coolant oil load and rpm channels even after batch sorting',async()=>{
  const h=harness();
  const channels=[{key:'can_50252',label:'Intake Air Temp Behind Throttle Valve (Temperature After Intercooling)',kind:'continuous',unit:'°C'},
    {key:'engine_rpm',label:'发动机转速',kind:'continuous',unit:'rpm'},
    {key:'engine_load_percent',label:'发动机负载',kind:'continuous',unit:'%'},
    {key:'coolant_c',label:'冷却液温度',kind:'continuous',unit:'°C'},
    {key:'oil_pressure_kpa',label:'机油压力',kind:'continuous',unit:'kPa'}];
  const original=JSON.stringify(channels),points=[{timestamp:'2026-09-24T00:00:00Z',...Object.fromEntries(channels.map(channel=>[channel.key,10]))}];
  const load=h.window.renderRiskDemo();h.requests[0].resolve(h.report({channels,chart_points:points}));await load;
  assert.deepEqual(Array.from(h.options.at(-1).series,series=>series.name),['冷却液温度 (°C)','机油压力 (kPa)','发动机负载 (%)','发动机转速 (rpm)']);
  assert.equal(JSON.stringify(channels),original);
  assert.ok(h.node('sensor-series-channel-0').children.some(node=>node.textContent.includes('中冷后进气温度')&&node.title.includes('Intake Air Temp Behind Throttle Valve')));
});

test('display translations retain source metadata and repeated code names include the actual CAN identifier',()=>{
  const source={key:'can_50331',label:'Oil Temperature of Torque Converter (Outlet)',source_label:'Oil Temperature of Torque Converter (Outlet)'};
  assert.equal(displayLabel(source),'变矩器出口油温');assert.equal(source.label,'Oil Temperature of Torque Converter (Outlet)');
  assert.equal(displayLabel({key:'can_50332',label:'Transmission Oil Reservoir Temperature'}),'变速箱油池温度');
  assert.equal(displayLabel({key:'can_50322',label:'Torque Converter Output Shaft Speed'}),'变矩器输出轴转速');
  const codes=[{key:'can_50295',label:'SPN'},{key:'can_50324',label:'SPN'}];
  assert.equal(choiceLabel(codes[0],codes),'SPN · CAN 50295');assert.equal(choiceLabel(codes[1],codes),'SPN · CAN 50324');
});

test('multiple DTC values at one timestamp render separate original lines',async()=>{
  const h=harness(),load=h.window.renderRiskDemo();
  h.requests[0].resolve(h.report({ai_available:false,channels:[{key:'can_50578',label:'Active Diagnostic Trouble Codes',kind:'code',latest:['SPN 123 FMI 2','SPN 456 FMI 3'],latest_at:'2026-09-24T00:00:00Z'}],chart_points:[]}));await load;
  const lines=h.node('sensor-series-code-readings').children[0].children.filter(node=>node.tag==='p').map(node=>node.textContent);
  assert.equal(lines.filter(line=>line.includes('SPN ')).length,2);
  assert.ok(lines.some(line=>line.endsWith('SPN 123 FMI 2')));assert.ok(lines.some(line=>line.endsWith('SPN 456 FMI 3')));
  assert.equal(lines.some(line=>line.includes('SPN 123 FMI 2,SPN 456 FMI 3')),false);
});
