const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const page=require('../extension/trackunit-sensor-page.js');
const bridge=require('../extension/sensor-series-bridge.js');
const ASSET='00000000-0000-0000-0000-000004760361',REQUEST='a'.repeat(32),DATASET='b'.repeat(64);
const PAGE='https://new.manager.trackunit.com/assets/'+ASSET+'/insights/advanced-sensors';
const CSV='Date and time,Engine Coolant Temperature (Water Temperature) (CAN 50278),Engine Oil Pressure (CAN 50281)\n'+
  '"9/17/26, 5:00:05 AM EDT",47,512\n"9/17/26, 5:02:05 AM EDT",65,464\n';
const tick=()=>new Promise(resolve=>setImmediate(resolve));

function pageHarness() {
  const listeners={},intervals=[],timeouts=[],downloads=[];let serial=0;
  class TestURL extends URL {static createObjectURL(){return 'blob:'+PAGE+'/'+(++serial);}}
  class Anchor {
    constructor(href,name='sensors.csv'){this.href=href;this.name=name;}
    getAttribute(name){return name==='download'?this.name:null;}
    closest(){return this;}
    click(){downloads.push(this.href);}
    dispatchEvent(event){downloads.push('dispatch:'+event.type);return true;}
  }
  const sandbox={module:{exports:{}},URL:TestURL,HTMLAnchorElement:Anchor,Blob,TextEncoder,Date,Reflect,Map,Set,
    location:{href:PAGE},document:{addEventListener:(n,f)=>listeners[n]=f,
      removeEventListener:(n,f)=>{if(listeners[n]===f)delete listeners[n];}},
    addEventListener:(n,f)=>listeners[n]=f,removeEventListener:(n,f)=>{if(listeners[n]===f)delete listeners[n];},
    setTimeout:(fn)=>{timeouts.push(fn);return timeouts.length;},clearTimeout:()=>{},
    setInterval:(fn)=>{intervals.push(fn);return intervals.length;},clearInterval:()=>{}};
  vm.runInNewContext(fs.readFileSync(require.resolve('../extension/trackunit-sensor-page.js'),'utf8'),sandbox);
  const nativeCreate=TestURL.createObjectURL,nativeClick=Anchor.prototype.click;
  const start=(extra={})=>sandbox.module.exports.observeExport({request_id:REQUEST,asset_id:ASSET,...extra});
  const download=(text=CSV,mime='text/csv',name='sensors.csv')=>{
    const anchor=new Anchor(TestURL.createObjectURL(new Blob([text],{type:mime})),name);anchor.click();return anchor;
  };
  return {sandbox,start,download,api:sandbox.module.exports,TestURL,Anchor,nativeCreate,nativeClick,downloads,listeners,intervals,timeouts};
}

test('CSV accepts real Trackunit date/time and channel structure without changing readings',()=>{
  const result=page.validateCSV(CSV);assert.equal(result.valid,true);assert.equal(result.rows,2);
  assert.deepEqual(result.channels,['Engine Coolant Temperature (Water Temperature) (CAN 50278)','Engine Oil Pressure (CAN 50281)']);
  assert.equal(page.validateCSV(CSV.replaceAll('EDT','EST')).valid,true);
  for(const bad of [CSV.replace('Date and time','Password'),CSV.replace(',47,',',=1+1,'),
    CSV.replace('47,512','47'),CSV.replace('47,512','47,Infinity'),'x'.repeat(4*1024*1024+1)])
    assert.equal(page.validateCSV(bad).valid,false);
});

test('observer returns only a new CSV download and restores native functions after capture',async()=>{
  const h=pageHarness(),p=h.start();h.download();const result=await p;
  assert.equal(result.status,'captured');assert.equal(result.asset_id,ASSET);assert.equal(result.capture.csv_text,CSV);
  assert.equal(result.capture.rows,2);assert.equal(h.downloads.length,1,'native download is preserved');
  assert.equal(h.TestURL.createObjectURL,h.nativeCreate);assert.equal(h.Anchor.prototype.click,h.nativeClick);
  assert.equal(h.sandbox.__jilianSensorExportObserverV1,undefined);assert.equal(h.listeners.click,undefined);
});

test('prior blobs and unrelated file downloads cannot supply the capture',async()=>{
  const h=pageHarness(),old=h.TestURL.createObjectURL(new Blob([CSV],{type:'text/csv'})),p=h.start();
  new h.Anchor(old).click();h.download(CSV,'text/csv','secret.txt');h.download(CSV,'image/png');await tick();
  assert.ok(h.sandbox.__jilianSensorExportObserverV1);h.download();assert.equal((await p).status,'captured');
});

test('normal dispatched anchor click is captured without suppressing the event',async()=>{
  const h=pageHarness(),p=h.start(),anchor=new h.Anchor(h.TestURL.createObjectURL(new Blob([CSV],{type:'text/plain'})));
  h.listeners.click({target:anchor});assert.equal((await p).capture.rows,2);
});

test('detached CSV anchor dispatch used by download helpers is also captured',async()=>{
  const h=pageHarness(),nativeDispatch=h.Anchor.prototype.dispatchEvent,p=h.start();
  const anchor=new h.Anchor(h.TestURL.createObjectURL(new Blob([CSV],{type:'text/csv'})));
  assert.equal(anchor.dispatchEvent({type:'click'}),true);assert.equal((await p).capture.rows,2);
  assert.equal(h.Anchor.prototype.dispatchEvent,nativeDispatch);assert.equal(h.downloads[0],'dispatch:click');
});

test('automatic export clicks only the observed enabled Export and exact CSV menuitem',async()=>{
  const h=pageHarness();let opened=0,exported=0;
  const visible={getBoundingClientRect:()=>({width:60,height:25}),getAttribute:()=>null,closest:()=>null};
  const button={...visible,textContent:'Export',disabled:false,click:()=>opened++};
  const csvItem={...visible,textContent:'CSV',click:()=>{exported++;h.download();}};
  const excelItem={...visible,textContent:'Excel Sheet',click:()=>assert.fail('must not export Excel')};
  h.sandbox.getComputedStyle=()=>({display:'block',visibility:'visible'});
  h.sandbox.document.querySelectorAll=selector=>selector.startsWith('button')?[button]:opened?[csvItem,excelItem]:[];
  const result=await h.start({auto_export:true});assert.equal(result.status,'captured');assert.equal(opened,1);assert.equal(exported,1);
});

test('disabled or ambiguous export controls fail without clicking or changing channel selection',async()=>{
  for(const variant of ['disabled','ambiguous']){
    const h=pageHarness();let clicks=0;
    const button={textContent:'Export',disabled:variant==='disabled',getAttribute:()=>null,closest:()=>null,
      getBoundingClientRect:()=>({width:50,height:20}),click:()=>clicks++};
    h.sandbox.getComputedStyle=()=>({display:'block',visibility:'visible'});
    h.sandbox.document.querySelectorAll=()=>variant==='disabled'?[button]:[button,button];
    assert.equal((await h.start({auto_export:true})).reason,'export_unavailable');assert.equal(clicks,0);
    assert.equal(h.TestURL.createObjectURL,h.nativeCreate);
  }
});

test('invalid current CSV reports a specific failure and releases observation',async()=>{
  const h=pageHarness(),p=h.start();h.download('Name,Email\nSomeone,person@example.com\n');
  assert.equal((await p).reason,'invalid_csv');assert.equal(h.TestURL.createObjectURL,h.nativeCreate);
});

test('timeout and explicit cancellation restore the observation without leaking CSV',async()=>{
  for(const trigger of ['timeout','cancel']){
    const h=pageHarness(),p=h.start();
    if(trigger==='timeout')h.timeouts[0]();
    else {assert.equal(h.api.cancelExport('f'.repeat(32)),false);assert.equal(h.api.cancelExport(REQUEST),true);}
    const result=await p;assert.equal(result.capture,undefined);assert.equal(result.reason,trigger==='timeout'?'timeout':'cancelled');
    assert.equal(h.TestURL.createObjectURL,h.nativeCreate);assert.equal(h.Anchor.prototype.click,h.nativeClick);
  }
});

test('device navigation cancels even while a Blob read is pending',async()=>{
  const h=pageHarness(),p=h.start();let finishText;
  const blob=new Blob([CSV],{type:'text/csv'});blob.text=()=>new Promise(resolve=>finishText=resolve);
  new h.Anchor(h.TestURL.createObjectURL(blob)).click();h.sandbox.location.href=PAGE.replace(ASSET,'00000000-0000-0000-0000-000000000001');
  h.intervals[0]();finishText(CSV);const result=await p;assert.equal(result.reason,'page_changed');assert.equal(result.capture,undefined);
});

test('cleanup does not overwrite another component replacing a native function',async()=>{
  const h=pageHarness(),p=h.start(),replacement=()=>{};h.TestURL.createObjectURL=replacement;
  h.api.cancelExport(REQUEST);await p;assert.equal(h.TestURL.createObjectURL,replacement);
});

test('page identity is HTTPS Trackunit Insights only and strips query parameters',()=>{
  assert.equal(page.pageIdentity(PAGE+'?token=never-forwarded#fragment').page_url,PAGE);
  for(const bad of [PAGE.replace('/insights/advanced-sensors','/events'),PAGE.replace('https:','http:'),
    PAGE.replace('new.manager.trackunit.com','evil.example'),PAGE.replace('https://','https://user:pass@')])
    assert.equal(page.pageIdentity(bad),null);
});

function bridgeHarness(bridgeImpl=bridge) {
  const messages=[],scripts=[],listeners={};let settle;
  const scope={asset_id:ASSET,dataset_id:DATASET,connection_id:'connection',origin:'http://127.0.0.1:8890',
    generation:1,currentTabId:42,state:'connected',mode:'work',pageChanged:false,matched:true};
  const frame={contentWindow:{postMessage:(data,origin)=>messages.push({...data,targetOrigin:origin})}};
  const tab={id:42,url:PAGE,status:'complete'};
  const chrome={tabs:{query:async()=>[tab],get:async()=>tab},scripting:{executeScript:async args=>{
    scripts.push(args);if(args.func===page.cancelExport){settle?.([{result:{status:'cancelled'}}]);return [{result:true}];}
    if(args.func===page.renewExport)return [{result:true}];
    return new Promise(resolve=>settle=resolve);
  }}};
  const host={addEventListener:(n,f)=>listeners[n]=f,removeEventListener:n=>delete listeners[n]};
  const api=bridgeImpl.create({chrome,frame,current:()=>({...scope}),window:host,page});
  const send=(data,extra={})=>listeners.message({origin:scope.origin,source:frame.contentWindow,
    data:{protocol:1,connection_id:scope.connection_id,request_id:REQUEST,asset_id:ASSET,dataset_id:DATASET,...data},...extra});
  const result=(extra={})=>({status:'captured',request_id:REQUEST,asset_id:ASSET,page_url:PAGE,capture:{schema_version:1,
    source:'trackunit_csv_export',asset_id:ASSET,page_url:PAGE,captured_at:'2026-09-24T20:00:00Z',csv_text:CSV,...extra}});
  return {api,scope,tab,scripts,messages,listeners,send,result,resolve:data=>settle([{result:data}])};
}

test('bridge ignores foreign frames/origins and mismatched device requests',async()=>{
  const h=bridgeHarness();h.send({type:'jilian:sensor-series-start'},{origin:'https://evil.example'});
  h.send({type:'jilian:sensor-series-start'},{source:{}});h.send({type:'jilian:sensor-series-start',asset_id:'other'});
  await tick();assert.equal(h.scripts.length,0);await h.api.dispose();
});

test('bridge requires current Advanced Sensors context before installing its observer',async()=>{
  const h=bridgeHarness();h.tab.url=PAGE.replace('/insights/advanced-sensors','/events');
  h.send({type:'jilian:sensor-series-start'});await tick();assert.equal(h.scripts.length,0);
  assert.equal(h.messages.at(-1).reason,'wrong_page');await h.api.dispose();
});

test('bridge forwards a validated same-device result to local workbench only',async()=>{
  const h=bridgeHarness();h.send({type:'jilian:sensor-series-start'});await tick();
  assert.equal(h.scripts[0].world,'MAIN');assert.deepEqual(h.scripts[0].target,{tabId:42});
  h.resolve(h.result({untrusted_extra:'never-forward'}));await tick();
  const message=h.messages.find(m=>m.type==='jilian:sensor-series-result');assert.ok(message);
  assert.equal(message.capture.rows,2);assert.equal(message.capture.untrusted_extra,undefined);
  assert.equal(message.targetOrigin,'http://127.0.0.1:8890');assert.equal(message.dataset_id,DATASET);
  await h.api.dispose();
});

test('scope change drops a late export and cleans the original page observer',async()=>{
  const h=bridgeHarness();h.send({type:'jilian:sensor-series-start'});await tick();
  h.scope.dataset_id='c'.repeat(64);h.resolve(h.result());await tick();
  assert.equal(h.messages.some(m=>m.type==='jilian:sensor-series-result'),false);
  assert.ok(h.scripts.some(s=>s.func===page.cancelExport));await h.api.dispose();
});

test('bridge rejects result with a different request or device and does not forward CSV',async()=>{
  for(const mutate of [r=>({...r,request_id:'f'.repeat(32)}),r=>({...r,capture:{...r.capture,asset_id:'other'}})]){
    const h=bridgeHarness();h.send({type:'jilian:sensor-series-start'});await tick();h.resolve(mutate(h.result()));await tick();
    assert.equal(h.messages.some(m=>m.type==='jilian:sensor-series-result'),false);
    assert.equal(h.messages.at(-1).type,'jilian:sensor-series-error');await h.api.dispose();
  }
});

function batchHarness({count=54,visibleCount=12,failBatch=-1,duplicateNames=false,breakInventory=false,disabledIndexes=[],
  loadingMs=0,loadingIndexes=[],onSelectionClick,omitIndexes=[],itemNames=[],headerFor,valueFor,staleIndexes=[]}={}) {
  const h=pageHarness(),selected=new Set([1,3,5,7].filter(i=>i<count)),original=[...selected],batches=[];
  let position=0,opened=false,selectionClicks=0,clock=Date.now(),lastSelection=clock;
  const dates={textContent:'2026年9月18日 - 2026年9月25日',getAttribute:()=>null};
  const items=Array.from({length:count},(_,i)=>({name:itemNames[i]||(duplicateNames&&i<2?'Shared Sensor':'Sensor '+i),unit:i%2?'°C':'kPa',id:51000+i}));
  const scroller={isConnected:true,clientHeight:visibleCount*50,scrollHeight:count*50,
    get scrollTop(){return position;},set scrollTop(value){position=Math.min(Math.max(0,value),Math.max(0,this.scrollHeight-this.clientHeight));}};
  const visible={getBoundingClientRect:()=>({width:60,height:25}),getAttribute:()=>null,closest:()=>null};
  const rows=()=>{
    let start=Math.floor(position/50);if(breakInventory)start=0;
    return items.slice(start,start+visibleCount).map((item,offset)=>{
      const index=start+offset,checkbox={get checked(){return selected.has(index);},
        get disabled(){return !selected.has(index)&&selected.size>=4;},getAttribute:()=>null,
        click(){selectionClicks++;if(selected.has(index))selected.delete(index);else selected.add(index);
          lastSelection=clock;onSelectionClick?.({index,selected,batches,sandbox:h.sandbox,table,clock});}};
      return {getAttribute:name=>name==='data-index'?String(index):null,
        querySelector:()=>checkbox,querySelectorAll:()=>[{}, {}, {textContent:item.name},{},{textContent:item.unit}]};
    });
  };
  const table={isConnected:true,parentElement:scroller,querySelectorAll:()=>rows()};
  const region={textContent:'Advanced Sensors Showing '+count+' of '+count+' results',querySelectorAll:()=>[table]};
  const heading={textContent:'Advanced Sensors',parentElement:region};
  const isLoading=()=>selected.size>0 && (!loadingIndexes.length || [...selected].every(index=>loadingIndexes.includes(index))) && clock-lastSelection<loadingMs;
  const exporter={...visible,textContent:'Export',get disabled(){return isLoading() || selected.size>0&&[...selected].every(index=>disabledIndexes.includes(index));},click(){opened=true;}};
  const csvItem={...visible,textContent:'CSV',click(){
    opened=false;const selection=[...selected].sort((a,b)=>a-b);batches.push(selection);
    const indexes=selection.filter(i=>!omitIndexes.includes(i));
    let csv='Date and time,'+indexes.map(i=>headerFor?.(i)||items[i].name+' (CAN '+items[staleIndexes.includes(i)?i-4:i].id+')').join(',')+'\n'+
      '"9/17/26, 5:00:05 AM EDT",'+indexes.map(i=>valueFor?.(i,0)??i).join(',')+'\n'+
      '"9/17/26, 5:02:05 AM EDT",'+indexes.map(i=>valueFor?.(i,1)??i+1).join(',')+'\n';
    if(batches.length-1===failBatch)csv=csv.replace('Date and time','Bad Header');
    h.download(csv);
  }};
  h.sandbox.getComputedStyle=()=>({display:'block',visibility:'visible'});
  h.sandbox.document.querySelectorAll=selector=>selector==='h3'?[heading]:selector==='button'?[dates,exporter]:
    selector==='button[data-testid="export-button"]'?[exporter]:
    selector==='[data-testid="insights-page-chart-loading"]'&&isLoading()?[visible]:
    selector==='[role="menuitem"]'&&opened?[csvItem]:[];
  h.sandbox.Date=class extends Date {static now(){return clock;}};
  h.sandbox.setTimeout=(fn,ms)=>setTimeout(()=>{if(ms<1000)clock+=ms;fn();},ms>=1000?1000:0);
  h.sandbox.clearTimeout=clearTimeout;h.sandbox.setInterval=fn=>setInterval(fn,1);h.sandbox.clearInterval=clearInterval;
  const run=(extra={})=>h.start({operation:'batch',timeout_ms:300000,...extra});
  return {...h,run,items,batches,selected,original,dates,scroller,advanceTime:ms=>{clock+=ms;},get selectionClicks(){return selectionClicks;}};
}

test('virtualized batch collector discovers all 54 sensors and exports every CAN once in groups of four',async()=>{
  const h=batchHarness(),result=await h.run();
  assert.equal(result.status,'captured');const capture=result.capture;
  assert.equal(capture.schema_version,2);assert.equal(capture.exports.length,14);
  assert.equal(capture.collection.discovered_sensors,54);assert.equal(capture.collection.exported_sensors,54);
  assert.equal(capture.collection.complete,true);assert.equal(capture.collection.selection_restored,true);
  assert.equal(capture.partial,false);assert.deepEqual([...h.selected],h.original);
  assert.equal(new Set(capture.exports.flatMap(item=>item.channels)).size,54);
  assert.ok(h.batches.every(batch=>batch.length<=4));
  assert.equal(capture.exports[0].units.can_51000,'kPa');assert.equal(capture.exports[0].units.can_51001,'°C');
  assert.equal(h.sandbox.__jilianSensorBatchV1,undefined);assert.equal(h.TestURL.createObjectURL,h.nativeCreate);
});

test('same-name channels keep distinct actual CAN IDs and do not guess conflicting units',async()=>{
  const h=batchHarness({count:8,duplicateNames:true}),result=await h.run();
  assert.equal(result.status,'captured');assert.equal(result.capture.collection.exported_sensors,8);
  assert.equal(result.capture.exports[0].channel_metadata.can_51000.unit,'');
  assert.equal(result.capture.exports[0].channel_metadata.can_51001.unit,'');
  assert.notEqual(result.capture.exports[0].channels[0],result.capture.exports[0].channels[1]);
});

test('source-omitted selected columns are reported while real text states remain intact',async()=>{
  const h=batchHarness({count:8,omitIndexes:[0],valueFor:i=>i===1?'N ':i===2?'2F':i}),result=await h.run();
  assert.equal(result.status,'captured');assert.equal(result.capture.collection.exported_sensors,7);
  assert.equal(result.capture.partial,true);assert.equal(result.capture.collection.failed_sensors[0].name,'Sensor 0');
  assert.equal(result.capture.collection.failed_sensors[0].reason,'column_not_exported');
  assert.equal(result.capture.exports[0].channel_metadata.can_51001.kind,'state');
  assert.match(result.capture.exports[0].csv_text,/,N ,2F,/);
});

test('only observed INPUT and OUTPUT names are accepted with stable identity and original text codes',async()=>{
  const h=batchHarness({count:4,itemNames:['Input 1','Input 6','Output 1','Engine Make_Model_Serial'],
    headerFor:i=>['INPUT1 (INPUT1)','INPUT6 (INPUT6)','OUTPUT1 (OUTPUT1)','Engine Make_Model_Serial (CAN 50580)'][i],
    valueFor:i=>i===3?'CMMNS*6B S5 D067       *22566122**************************************************************':i%2}),result=await h.run();
  assert.equal(result.status,'captured');const meta=result.capture.exports[0].channel_metadata;
  assert.equal(meta.input_1.kind,'state');assert.equal(meta.input_6.kind,'state');assert.equal(meta.output_1.kind,'state');
  assert.equal(meta.can_50580.kind,'code');
  assert.equal(page.channelIdentity('PASSWORD (PASSWORD)'),null);assert.equal(page.channelIdentity('INPUT99 (INPUT99)'),null);
  assert.equal(page.channelIdentity('INPUT1 (INPUT2)'),null);
});

test('stale same-name CSV with earlier CAN IDs retries then preserves earlier successful batches',async()=>{
  const h=batchHarness({count:8,itemNames:['A','B','C','D','A','B','C','D'],staleIndexes:[4,5,6,7]}),result=await h.run();
  assert.equal(result.status,'captured');assert.equal(result.capture.collection.exported_sensors,4);
  assert.equal(result.capture.exports.length,1);assert.equal(h.batches.length,3);
  assert.equal(result.capture.collection.failed_sensors.length,4);
  assert.ok(result.capture.collection.failed_sensors.every(item=>item.reason==='wrong_channels'));
});

test('failed export remains explicit while successful batches are returned and selection restored',async()=>{
  const h=batchHarness({count:12,failBatch:1}),result=await h.run();
  assert.equal(result.status,'captured');assert.equal(result.capture.exports.length,2);
  assert.equal(result.capture.partial,true);assert.equal(result.capture.collection.exported_sensors,8);
  assert.equal(result.capture.collection.failed_sensors.length,4);assert.equal(result.capture.collection.complete,false);
  assert.deepEqual([...h.selected],h.original);
});

test('incomplete virtual inventory fails before changing any checkbox',async()=>{
  const h=batchHarness({breakInventory:true}),result=await h.run();
  assert.equal(result.status,'error');assert.equal(result.reason,'sensor_inventory_incomplete');
  assert.equal(h.selectionClicks,0);assert.deepEqual([...h.selected],h.original);assert.equal(h.batches.length,0);
});

test('a disabled export for a no-data state batch is explicit and does not block later sensors',async()=>{
  const h=batchHarness({count:12,disabledIndexes:[4,5,6,7]}),result=await h.run();
  assert.equal(result.status,'captured');assert.equal(result.capture.collection.exported_sensors,8);
  assert.equal(result.capture.collection.failed_sensors.length,4);
  assert.ok(result.capture.collection.failed_sensors.every(sensor=>sensor.reason==='not_exportable'));
  assert.deepEqual([...h.selected],h.original);
});

test('slow chart loading longer than six seconds is awaited before exporting',async()=>{
  const h=batchHarness({count:8,loadingMs:20000}),result=await h.run();
  assert.equal(result.status,'captured');assert.equal(result.capture.collection.exported_sensors,8);
  assert.equal(result.capture.partial,false);assert.equal(h.batches.length,2);
});

test('a chart still loading at the batch deadline is timeout, never no-data',async()=>{
  const h=batchHarness({count:12,loadingMs:Infinity,loadingIndexes:[4,5,6,7]}),result=await h.run();
  assert.equal(result.status,'captured');assert.equal(result.capture.collection.exported_sensors,8);
  assert.equal(result.capture.collection.failed_sensors.length,4);
  assert.ok(result.capture.collection.failed_sensors.every(sensor=>sensor.reason==='timeout'));
  assert.deepEqual([...h.selected],h.original);
});

test('loading must end and remain idle before a disabled export is called non-exportable',async()=>{
  const h=batchHarness({count:12,loadingMs:18000,loadingIndexes:[4,5,6,7],disabledIndexes:[4,5,6,7]}),result=await h.run();
  assert.equal(result.status,'captured');assert.equal(result.capture.collection.exported_sensors,8);
  assert.ok(result.capture.collection.failed_sensors.every(sensor=>sensor.reason==='not_exportable'));
});

test('restoration stops immediately when the user navigates to another asset',async()=>{
  let afterChangeClicks=0,changed=false;
  const h=batchHarness({count:12,onSelectionClick:({index,batches,sandbox})=>{
    if(changed)afterChangeClicks++;
    if(batches.length===3 && index===3){changed=true;sandbox.location.href=PAGE.replace(ASSET,'00000000-0000-0000-0000-000000000002');}
  }}),result=await h.run();
  assert.equal(changed,true);assert.equal(afterChangeClicks,0);
  assert.equal(result.status,'cancelled');assert.equal(result.reason,'page_changed');assert.equal(result.capture,undefined);
});

test('restoration stops immediately when the original table is disconnected',async()=>{
  let afterChangeClicks=0,changed=false;
  const h=batchHarness({count:12,onSelectionClick:({index,batches,table})=>{
    if(changed)afterChangeClicks++;
    if(batches.length===3 && index===3){changed=true;table.isConnected=false;}
  }}),result=await h.run();
  assert.equal(changed,true);assert.equal(afterChangeClicks,0);
  assert.equal(result.status,'cancelled');assert.equal(result.capture,undefined);
});

test('changing visible time range invalidates every pending batch',async()=>{
  const h=batchHarness(),pending=h.run();
  await new Promise(resolve=>setTimeout(resolve,3));h.dates.textContent='2026年9月10日 - 2026年9月11日';
  const result=await pending;assert.equal(result.status,'cancelled');assert.equal(result.reason,'range_changed');
  assert.equal(result.capture,undefined);assert.equal(h.sandbox.__jilianSensorBatchV1,undefined);
});

test('batch cancellation restores original checks without publishing partial readings',async()=>{
  const h=batchHarness({count:12}),pending=h.run();
  await new Promise(resolve=>setTimeout(resolve,12));assert.equal(h.api.cancelExport(REQUEST),true);
  const result=await pending;assert.equal(result.status,'cancelled');assert.equal(result.capture,undefined);
  assert.deepEqual([...h.selected].sort((a,b)=>a-b),h.original);assert.equal(h.sandbox.__jilianSensorBatchV1,undefined);
});

test('bridge validates and forwards the batch contract while dropping untrusted fields',async()=>{
  const batch=batchHarness({count:8}),capture=(await batch.run()).capture;
  capture.untrusted_extra='private';capture.exports[0].untrusted_extra='private';
  const h=bridgeHarness();h.send({type:'jilian:sensor-series-start'});await tick();
  assert.equal(h.scripts[0].args[0].operation,'batch');assert.equal(h.scripts[0].args[0].timeout_ms,600000);
  h.resolve({...h.result(),capture});await tick();
  const message=h.messages.find(m=>m.type==='jilian:sensor-series-result');assert.ok(message);
  assert.equal(message.capture.exports.length,2);assert.equal(message.capture.untrusted_extra,undefined);
  assert.equal(message.capture.exports[0].untrusted_extra,undefined);await h.api.dispose();
});

test('bridge rejects duplicate CAN IDs and false complete coverage across batches',async()=>{
  const batch=batchHarness({count:8}),original=(await batch.run()).capture;
  for(const mutate of [capture=>capture.exports[1]=capture.exports[0],capture=>capture.collection.exported_sensors=4]){
    const capture=JSON.parse(JSON.stringify(original));mutate(capture);
    const h=bridgeHarness();h.send({type:'jilian:sensor-series-start'});await tick();h.resolve({...h.result(),capture});await tick();
    assert.equal(h.messages.some(m=>m.type==='jilian:sensor-series-result'),false);
    assert.equal(h.messages.at(-1).type,'jilian:sensor-series-error');await h.api.dispose();
  }
});

test('closing the owner panel cancels the exact page job and ignores any late result',async()=>{
  const h=bridgeHarness();h.send({type:'jilian:sensor-series-start'});await tick();
  assert.equal(h.scripts[0].args[0].owner_lease_ms,30000);
  const leave=h.listeners.pagehide;assert.equal(typeof leave,'function');leave();await tick();
  assert.equal(h.listeners.message,undefined);assert.equal(h.listeners.pagehide,undefined);
  const cancels=h.scripts.filter(script=>script.func===page.cancelExport);
  assert.equal(cancels.length,1);assert.deepEqual(cancels[0].target,{tabId:42});
  assert.deepEqual(cancels[0].args,[REQUEST]);
  assert.equal(h.messages.some(message=>message.type==='jilian:sensor-series-result'),false);
  await h.api.dispose();assert.equal(h.scripts.filter(script=>script.func===page.cancelExport).length,1);
});

test('closing before injection completes does not install a new page observer',async()=>{
  const h=bridgeHarness();h.send({type:'jilian:sensor-series-start'});
  h.listeners.pagehide();await tick();
  assert.equal(h.scripts.length,0);assert.equal(h.listeners.message,undefined);
  await h.api.dispose();
});

test('lost owner lease cancels and restores original selected channels without returning data',async()=>{
  const h=batchHarness({count:12}),pending=h.run({owner_lease_ms:5000});
  for(let wait=0;wait<100 && !h.selectionClicks;wait++)await new Promise(resolve=>setTimeout(resolve,1));
  assert.ok(h.selectionClicks>0);
  assert.equal(h.api.renewExport('f'.repeat(32)),false);
  h.advanceTime(6000);
  assert.equal(h.api.renewExport(REQUEST),false,'an expired owner cannot resurrect its batch');
  const result=await pending;
  assert.equal(result.status,'cancelled');assert.equal(result.capture,undefined);
  assert.deepEqual([...h.selected].sort((a,b)=>a-b),h.original);
  assert.equal(h.sandbox.__jilianSensorBatchV1,undefined);
  assert.equal(h.TestURL.createObjectURL,h.nativeCreate);
});

test('matching owner renewals keep long batch collection alive',async()=>{
  let h,renewals=0;
  h=batchHarness({count:54,onSelectionClick:()=>{if(h.api.renewExport(REQUEST))renewals++;}});
  const result=await h.run({owner_lease_ms:5000});
  assert.equal(result.status,'captured');assert.equal(result.capture.collection.exported_sensors,54);
  assert.equal(result.capture.collection.selection_restored,true);assert.ok(renewals>50);
  assert.deepEqual([...h.selected],h.original);
});

test('lease expiry also cancels a pending CSV observer and restores native download functions',async()=>{
  const h=pageHarness();let owns=true;
  h.sandbox.__jilianSensorBatchV1={request_id:REQUEST,owned:()=>owns};
  const pending=h.start({owned_batch_request_id:REQUEST});
  owns=false;h.intervals[0]();const result=await pending;
  assert.equal(result.status,'cancelled');assert.equal(result.capture,undefined);
  assert.equal(h.TestURL.createObjectURL,h.nativeCreate);assert.equal(h.Anchor.prototype.click,h.nativeClick);
  assert.equal(h.sandbox.__jilianSensorExportObserverV1,undefined);
});

test('bridge renews only its live page job and clears the lease timer on close',async()=>{
  const intervals=new Map();let sequence=0;
  const box={module:{exports:{}},setInterval:(fn,ms)=>{const id=++sequence;intervals.set(id,{fn,ms});return id;},
    clearInterval:id=>{const timer=intervals.get(id);if(timer)timer.cleared=true;}};
  vm.runInNewContext(fs.readFileSync(require.resolve('../extension/sensor-series-bridge.js'),'utf8'),box);
  const h=bridgeHarness(box.module.exports);h.send({type:'jilian:sensor-series-start'});await tick();
  const lease=[...intervals.values()].find(timer=>timer.ms===5000);assert.ok(lease);
  lease.fn();await tick();
  const renewal=h.scripts.find(script=>script.func===page.renewExport);assert.ok(renewal);
  assert.equal(renewal.target.tabId,42);assert.equal(renewal.args[0],REQUEST);
  h.listeners.pagehide();await tick();assert.equal(lease.cleared,true);
  const count=h.scripts.length;lease.fn();await tick();assert.equal(h.scripts.length,count);
  await h.api.dispose();
});
