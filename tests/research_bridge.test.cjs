const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function harness(){
  const messages=[],calls=[],scripts=[],listeners={},timers=[];
  const capture={vin:'XUGTEST000000001',title:'test'};
  const frame={contentWindow:{postMessage:d=>messages.push(d)}};
  const state={frame,localOrigin:'http://127.0.0.1:8890',connectionId:'connection',assetId:'asset',
    matchedSelection:{dataset_id:'a'.repeat(64)},state:'connected',mode:'work',pageChanged:false};
  const chrome={tabs:{create:async data=>{calls.push(data);return {id:42};},get:async()=>({url:'https://xgss.xcmg.com/',status:'complete'})},
    scripting:{executeScript:async args=>{scripts.push(args);return args.files?[]:[{frameId:0,result:{status:'ready',vin:'XUGTEST000000001',targets:[{label:'冷却系统'}],capture}}];}}};
  const sandbox={...state,chrome,URL,window:{addEventListener:(n,f)=>listeners[n]=f},
    XGSSCatalog:{isXGSS:url=>url.startsWith('https://xgss.xcmg.com/')},
    XGSSResearchRunner:{run:async(args,io)=>{await io.save({vin:args.vin,title:'test'});return {status:'completed',pages:1};}},
    setTimeout:f=>{timers.push(f);return timers.length;},clearTimeout:()=>{}};
  vm.runInNewContext(fs.readFileSync(require.resolve('../extension/research-bridge.js'),'utf8'),sandbox);
  const send=(data,extra={})=>listeners.message({source:frame.contentWindow,origin:state.localOrigin,
    data:{protocol:1,connection_id:'connection',...data},...extra});
  const start=()=>send({type:'jilian:research-start',request_id:'b'.repeat(32),asset_id:'asset',dataset_id:'a'.repeat(64),
    vin:'XUGTEST000000001',terms:['冷却'],url:'https://xgss.xcmg.com/'});
  return {send,start,messages,calls,scripts,sandbox,timers,capture};
}
test('bridge ignores forged senders and mismatched devices before opening any tab',()=>{
  const h=harness();h.send({type:'jilian:research-probe'},{origin:'https://evil.test'});assert.equal(h.messages.length,0);
  h.sandbox.assetId='other';h.start();assert.equal(h.calls.length,0);
});

test('root expansion is passed through the same checked frame and VIN bridge',async()=>{
  const h=harness();
  h.sandbox.XGSSResearchRunner.run=async(args,io)=>{
    await io.expandRoot(args.vin);return {status:'partial',pages:0};
  };
  h.start();await tick();
  const call=h.scripts.find(args=>args.func?.toString().includes('XGSSResearch.expandRoot'));
  assert.ok(call);assert.deepEqual([...call.args],['XUGTEST000000001']);
  assert.equal(call.target.tabId,42);assert.deepEqual([...call.target.frameIds],[0]);
});
test('capture waits for matching persistence acknowledgement before completion',async()=>{
  const h=harness();h.start();await tick();
  const page=h.messages.find(m=>m.type==='jilian:research-page');assert.ok(page);
  assert.equal(h.messages.some(m=>m.type==='jilian:research-done'),false);
  h.send({type:'jilian:research-ack',request_id:'wrong',page_id:page.page_id,success:true});await tick();
  assert.equal(h.messages.some(m=>m.type==='jilian:research-done'),false);
  h.send({type:'jilian:research-ack',request_id:page.request_id,page_id:page.page_id,success:true});await tick();
  assert.equal(h.messages.some(m=>m.type==='jilian:research-done'),true);
});
test('cancel releases a pending source write wait and never announces completion',async()=>{
  const h=harness();h.start();await tick();
  h.send({type:'jilian:research-cancel',request_id:'b'.repeat(32)});await tick();
  assert.equal(h.messages.some(m=>m.type==='jilian:research-done'),false);
  assert.equal(h.messages.some(m=>m.type==='jilian:research-error'),true);
});

test('VIN header alone does not start a premature empty collection',async()=>{
  const h=harness();let inspections=0,runs=0;
  h.sandbox.chrome.scripting.executeScript=async args=>args.files?[]:[{frameId:0,result:{status:'ready',vin:'XUGTEST000000001',
    targets:++inspections===1?[]:[{label:'冷却系统'}]}}];
  h.sandbox.XGSSResearchRunner.run=async()=>{runs++;return {status:'completed',pages:1};};
  h.start();await tick();assert.equal(runs,0);assert.equal(inspections,1);
  h.timers[0]();await tick();assert.equal(runs,1);
  assert.equal(h.messages.some(m=>m.type==='jilian:research-done'),true);
});

test('a single same-VIN actionable root starts navigation even before a parts table is available',async()=>{
  const h=harness();let runs=0;
  h.sandbox.chrome.scripting.executeScript=async args=>args.files?[]:[{frameId:0,result:{
    status:'ready',vin:'XUGTEST000000001',targets:[],capture:null,can_expand_root:true}}];
  h.sandbox.XGSSResearchRunner.run=async()=>{runs++;return {status:'partial',pages:0};};
  h.start();await tick();assert.equal(runs,1);
  assert.equal(h.messages.some(message=>message.type==='jilian:research-done'),true);
});

test('tree labels without a checked expandable root still time out without running navigation',async()=>{
  for(const canExpand of [false,undefined,'true']) {
    const h=harness();let runs=0;
    h.sandbox.chrome.scripting.executeScript=async args=>args.files?[]:[{frameId:0,result:{
      status:'ready',vin:'XUGTEST000000001',targets:[],capture:null,
      tree_signature:'["unmatched directory"]',can_expand_root:canExpand}}];
    h.sandbox.XGSSResearchRunner.run=async()=>{runs++;return {status:'partial',pages:0};};
    h.start();await tick();
    for(let index=0;index<30;index++){assert.equal(typeof h.timers[index],'function');h.timers[index]();await tick();}
    assert.equal(runs,0);assert.equal(h.messages.some(message=>message.type==='jilian:research-done'),false);
    assert.match(h.messages.find(message=>message.type==='jilian:research-error').message,/等待时间/);
  }
});

test('root-only bootstrap still requires one eligible same-VIN ready frame',async()=>{
  for(const variant of ['wrong-vin','loading','multiple']) {
    const h=harness();let runs=0;
    const row={frameId:0,result:{status:variant==='loading'?'loading':'ready',
      vin:variant==='wrong-vin'?'OTHER':'XUGTEST000000001',targets:[],capture:null,can_expand_root:true}};
    h.sandbox.chrome.scripting.executeScript=async args=>args.files?[]:variant==='multiple'?[row,{...row,frameId:1}]:[row];
    h.sandbox.XGSSResearchRunner.run=async()=>{runs++;return {status:'partial',pages:0};};
    h.start();await tick();assert.equal(runs,0,variant);
    if(variant==='multiple')assert.match(h.messages.find(message=>message.type==='jilian:research-error').message,/多个/);
    else h.send({type:'jilian:research-cancel',request_id:'b'.repeat(32)});
  }
});

test('bridge reads illustrations only when saving settled text and waits for its acknowledgement',async()=>{
  const h=harness(),illustration={title:'冷却系统',document_ref:'3944450.svg',data_url:'data:image/png;base64,TEST'};
  h.sandbox.chrome.scripting.executeScript=async args=>{
    h.scripts.push(args);if(args.files)return [];
    const withImage=args.func.toString().includes('captureWithIllustration');
    return [{frameId:0,result:{status:'ready',vin:h.capture.vin,targets:[{label:'冷却系统'}],
      capture:withImage?{...h.capture,illustrations:[illustration]}:h.capture}}];
  };
  h.sandbox.XGSSResearchRunner.run=async(args,io)=>{
    for(let count=0;count<3;count++)await io.inspect(args.terms);
    await io.save(h.capture);return {status:'completed',pages:1};
  };
  h.start();await tick();
  assert.equal(h.scripts.filter(args=>args.func?.toString().includes('captureWithIllustration')).length,1);
  assert.equal(h.scripts.filter(args=>args.func?.toString().includes('XGSSResearch.inspect')).length,4);
  const page=h.messages.find(message=>message.type==='jilian:research-page');
  assert.equal(page.capture.illustrations[0],illustration);
  assert.equal(h.messages.some(message=>message.type==='jilian:research-done'),false);
  h.send({type:'jilian:research-ack',request_id:page.request_id,page_id:page.page_id,success:true});await tick();
  assert.equal(h.messages.some(message=>message.type==='jilian:research-done'),true);
});

test('bridge never combines a fresh diagram with an older text capture',async()=>{
  for(const changed of ['vin','text','loading','loading_other_vin']){
    const h=harness(),execute=h.sandbox.chrome.scripting.executeScript;let imageAttempts=0;
    h.sandbox.chrome.scripting.executeScript=async args=>{
      if(!args.func?.toString().includes('captureWithIllustration'))return execute(args);
      imageAttempts++;
      return [{result:{status:changed.startsWith('loading')?'loading':'ready',vin:changed.includes('vin')?'OTHER':h.capture.vin,
        capture:{...h.capture,title:changed==='text'?'different category':h.capture.title,illustrations:[]}}}];
    };
    h.start();await tick();
    if(changed==='loading'){
      assert.equal(h.messages.some(message=>message.type==='jilian:research-error'),false);
      for(let retry=0;retry<2;retry++){h.timers[retry]();await tick();}
    }
    assert.equal(h.messages.some(message=>message.type==='jilian:research-page'),false,changed);
    assert.ok(h.messages.some(message=>message.type==='jilian:research-error'),changed);
    assert.equal(imageAttempts,changed==='loading'?3:1,changed);
  }
});

test('bridge retries same-VIN image transitions twice and saves only the recovered original text',async()=>{
  const h=harness(),execute=h.sandbox.chrome.scripting.executeScript;let imageAttempts=0;
  const image={title:'冷却系统',document_ref:'3944450.svg',data_url:'data:image/png;base64,TEST'};
  h.sandbox.chrome.scripting.executeScript=async args=>{
    if(!args.func?.toString().includes('captureWithIllustration'))return execute(args);
    return [{result:++imageAttempts<3?{status:'loading',vin:h.capture.vin}:
      {status:'ready',vin:h.capture.vin,capture:{...h.capture,illustrations:[image]}}}];
  };
  h.start();await tick();
  for(let retry=0;retry<2;retry++){
    assert.equal(h.messages.some(message=>message.type==='jilian:research-page'),false);
    assert.equal(h.messages.some(message=>message.type==='jilian:research-error'),false);
    assert.equal(typeof h.timers[retry],'function');h.timers[retry]();await tick();
  }
  assert.equal(imageAttempts,3);
  const page=h.messages.find(message=>message.type==='jilian:research-page');assert.ok(page);
  assert.equal(page.capture.title,h.capture.title);assert.equal(page.capture.illustrations[0],image);
  h.send({type:'jilian:research-ack',request_id:page.request_id,page_id:page.page_id,success:true});await tick();
  assert.equal(h.messages.some(message=>message.type==='jilian:research-done'),true);
});

test('a same-VIN transition retry still rejects changed text or VIN and never retries persistence failures',async()=>{
  for(const changed of ['text','vin','persistence']){
    const h=harness(),execute=h.sandbox.chrome.scripting.executeScript;let imageAttempts=0;
    h.sandbox.chrome.scripting.executeScript=async args=>{
      if(!args.func?.toString().includes('captureWithIllustration'))return execute(args);
      return [{result:++imageAttempts===1?{status:'loading',vin:h.capture.vin}:
        {status:'ready',vin:changed==='vin'?'OTHER':h.capture.vin,
          capture:{...h.capture,title:changed==='text'?'another category':h.capture.title,illustrations:[]}}}];
    };
    h.start();await tick();assert.equal(typeof h.timers[0],'function');h.timers[0]();await tick();
    const page=h.messages.find(message=>message.type==='jilian:research-page');
    if(changed==='persistence'){
      assert.ok(page);h.send({type:'jilian:research-ack',request_id:page.request_id,page_id:page.page_id,success:false});await tick();
    }else assert.equal(page,undefined,changed);
    assert.equal(imageAttempts,2,changed);
    assert.equal(h.messages.some(message=>message.type==='jilian:research-done'),false,changed);
    assert.equal(h.messages.some(message=>message.type==='jilian:research-error'),true,changed);
  }
});

test('cancel or device switching during the image retry wait prevents another capture',async()=>{
  for(const changed of ['cancel','device']){
    const h=harness(),execute=h.sandbox.chrome.scripting.executeScript;let imageAttempts=0;
    h.sandbox.chrome.scripting.executeScript=async args=>{
      if(!args.func?.toString().includes('captureWithIllustration'))return execute(args);
      imageAttempts++;return [{result:{status:'loading',vin:h.capture.vin}}];
    };
    h.start();await tick();assert.equal(typeof h.timers[0],'function');
    if(changed==='cancel')h.send({type:'jilian:research-cancel',request_id:'b'.repeat(32)});
    else h.sandbox.assetId='other';
    h.timers[0]();await tick();
    assert.equal(imageAttempts,1,changed);
    assert.equal(h.messages.some(message=>message.type==='jilian:research-page'),false,changed);
    assert.equal(h.messages.some(message=>message.type==='jilian:research-done'),false,changed);
  }
});

test('bridge discards diagram completion after cancellation or a device change',async()=>{
  for(const change of ['cancel','device']){
    const h=harness(),execute=h.sandbox.chrome.scripting.executeScript;let resolveImage;
    h.sandbox.chrome.scripting.executeScript=async args=>args.func?.toString().includes('captureWithIllustration')?
      new Promise(resolve=>resolveImage=resolve):execute(args);
    h.start();await tick();assert.equal(typeof resolveImage,'function');
    if(change==='cancel')h.send({type:'jilian:research-cancel',request_id:'b'.repeat(32)});
    else h.sandbox.assetId='other';
    resolveImage([{result:{status:'ready',vin:h.capture.vin,capture:{...h.capture,illustrations:[]}}}]);await tick();
    assert.equal(h.messages.some(message=>message.type==='jilian:research-page'),false,change);
    assert.equal(h.messages.some(message=>message.type==='jilian:research-done'),false,change);
  }
});

test('an image failure can still save the unchanged text but navigation away cannot',async()=>{
  const h=harness(),execute=h.sandbox.chrome.scripting.executeScript;
  h.sandbox.chrome.scripting.executeScript=async args=>args.func?.toString().includes('captureWithIllustration')?
    [{result:{status:'ready',vin:h.capture.vin,capture:h.capture,illustration_issue:'图示读取失败，保留文字资料。'}}]:execute(args);
  h.start();await tick();
  const page=h.messages.find(message=>message.type==='jilian:research-page');assert.ok(page);
  assert.equal(page.capture.illustrations,undefined);assert.equal(page.capture.title,'test');
  h.send({type:'jilian:research-ack',request_id:page.request_id,page_id:page.page_id,success:true});await tick();
  const moved=harness();let reads=0;
  moved.sandbox.chrome.tabs.get=async()=>++reads===1?{url:'https://xgss.xcmg.com/',status:'complete'}:
    {url:'https://xgss.xcmg.com/',status:'loading',pendingUrl:'https://other.example/'};
  moved.start();await tick();
  assert.equal(moved.messages.some(message=>message.type==='jilian:research-page'),false);
  assert.equal(moved.scripts.some(args=>args.func?.toString().includes('captureWithIllustration')),false);
});
