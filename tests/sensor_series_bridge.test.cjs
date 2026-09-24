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

function bridgeHarness() {
  const messages=[],scripts=[],listeners={};let settle;
  const scope={asset_id:ASSET,dataset_id:DATASET,connection_id:'connection',origin:'http://127.0.0.1:8890',
    generation:1,currentTabId:42,state:'connected',mode:'work',pageChanged:false,matched:true};
  const frame={contentWindow:{postMessage:(data,origin)=>messages.push({...data,targetOrigin:origin})}};
  const tab={id:42,url:PAGE,status:'complete'};
  const chrome={tabs:{query:async()=>[tab],get:async()=>tab},scripting:{executeScript:async args=>{
    scripts.push(args);if(args.func===page.cancelExport){settle?.([{result:{status:'cancelled'}}]);return [{result:true}];}
    return new Promise(resolve=>settle=resolve);
  }}};
  const host={addEventListener:(n,f)=>listeners[n]=f,removeEventListener:n=>delete listeners[n]};
  const api=bridge.create({chrome,frame,current:()=>({...scope}),window:host,page});
  const send=(data,extra={})=>listeners.message({origin:scope.origin,source:frame.contentWindow,
    data:{protocol:1,connection_id:scope.connection_id,request_id:REQUEST,asset_id:ASSET,dataset_id:DATASET,...data},...extra});
  const result=(extra={})=>({status:'captured',request_id:REQUEST,asset_id:ASSET,page_url:PAGE,capture:{schema_version:1,
    source:'trackunit_csv_export',asset_id:ASSET,page_url:PAGE,captured_at:'2026-09-24T20:00:00Z',csv_text:CSV,...extra}});
  return {api,scope,tab,scripts,messages,send,result,resolve:data=>settle([{result:data}])};
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
