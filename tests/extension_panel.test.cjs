const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');const path=require('node:path');
const asset='00000000-0000-0000-0000-000000000001';
const cloud={provider:'gemini',model:'gemini-flash-latest',backend_build:'20260915.9-platform-follow'};
function setup(url='https://example.com',savedPort,auto=false,savedDataMode=null){
 const outgoing=[],tabHandlers={},confirmations=[],scriptCalls=[],scriptResults=[];
 const ids=['assistant','connection','help','context','retry','identify','runtime','standalone','service-form','service-port','workspace','connection-cover','cover-title','cover-detail','connection-detail','start-command','cover-retry','connection-options','catalog-options','open-demo','mode-demo','mode-live','follow','capture-catalog','catalog-open','catalog-status','ai-guidance','ai-guidance-status','ai-guidance-terms','ai-guidance-components'];
 // Minimal element stand-in with the few DOM methods the panel actually calls.
 const makeElement = tag => ({
  tag, children: [], textContent: '', hidden: false, disabled: false, dataset: {}, attributes: {},
  handlers: {},
  append(...nodes) { this.children.push(...nodes); },
  replaceChildren(...nodes) { this.children = [...nodes]; },
  setAttribute(key, value) { this.attributes[key] = value; },
  removeAttribute(key) { delete this.attributes[key]; delete this[key]; },
  // Real elements keep every listener; a later registration must not replace an
  // earlier one. dispatch returns the last handler's value, which is how the tests
  // drive the open handler that returns the guidance promise.
  addEventListener(name, handler) { (this.handlers[name] || (this.handlers[name] = [])).push(handler); },
  dispatch(name, event = {}) {
   const list = this.handlers[name] || [];
   let result;
   for (const handler of list) result = handler(Object.assign({target: this}, event));
   return result;
  },
  // The sheet code resolves its own panel element to keep it hidden while collapsed.
  querySelector(selector) {
   if (!this._panel) this._panel = makeElement('div');
   return selector.includes('settings-panel') ? this._panel : null;
  },
 });
 const elements=Object.fromEntries(ids.map(id=>[id,Object.assign(makeElement(id),
  {contentWindow:{postMessage:(data,origin)=>outgoing.push({data,origin})}})]));
 const storage=new Map(savedPort?[['jilian-service-port',savedPort]]:[]);
 if(savedDataMode)storage.set('jilian-data-mode',savedDataMode);
 const timers=new Map(),handlers={};let counter=0;
 const box={URL,URLSearchParams,Date,
  document:{getElementById:id=>elements[id],createElement:makeElement,
   querySelector:selector=>selector.includes('actionbar')?{getBoundingClientRect:()=>({bottom:83})}:null,
   querySelectorAll:()=>[],
   documentElement:{dataset:{},style:{setProperty(){},removeProperty(){}}}},
  window:{addEventListener:(name,handler)=>handlers[name]=handler,confirm:message=>{confirmations.push(message);return true;}},
  localStorage:{getItem:key=>storage.get(key),setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)},
  chrome:{tabs:{query:async()=>[{url,id:10,windowId:1}],onActivated:{addListener:fn=>tabHandlers.activated=fn},onUpdated:{addListener:fn=>tabHandlers.updated=fn}},
   scripting:{executeScript:async request=>{scriptCalls.push(request);return scriptResults.length?scriptResults.shift():[];}}},
  fetch:()=>{throw new Error('Connection probing must not use fetch');},
  setTimeout:(fn,ms)=>{timers.set(++counter,{fn,ms});return counter;},clearTimeout:id=>timers.delete(id)};
 vm.createContext(box);
 for(const file of ['context.js','xgss-catalog.js','panel.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../extension',file),'utf8'),box);
 // Legacy connection tests isolate startup detection; explicit automatic-follow tests retain it below.
 if(!auto)for(const [id,timer] of timers)if(timer.ms===150)timers.delete(id);
 return {elements,handlers,timers,storage,outgoing,tabHandlers,box,confirmations,scriptCalls,scriptResults,
  tick(){const [id,timer]=timers.entries().next().value;timers.delete(id);timer.fn();},
  async follow(){const entry=[...timers.entries()].find(([,timer])=>timer.ms===150);assert.ok(entry,'automatic lookup scheduled');const [id,timer]=entry;timers.delete(id);timer.fn();await new Promise(resolve=>setImmediate(resolve));}};
}
function reply(panel,type,extra={},url=new URL(panel.elements.assistant.src)){
 panel.handlers.message({origin:url.origin,source:panel.elements.assistant.contentWindow,
  data:{type,protocol:1,connection_id:url.searchParams.get('panel'),...extra}});
}
function ready(panel){reply(panel,'jilian:ready');reply(panel,'jilian:runtime',cloud);}
function state(panel){return panel.elements.workspace.dataset.state;}

test('initial frame stays covered until runtime and readiness both arrive',()=>{
 const p=setup();assert.equal(new URL(p.elements.assistant.src).port,'8890');
 assert.equal(state(p),'connecting');assert.equal(p.elements['connection-cover'].hidden,false);
 assert.equal(p.elements.assistant.attributes['aria-hidden'],'true');assert.equal(p.elements.standalone.href,undefined);
 assert.equal(p.timers.values().next().value.ms,6500);
 reply(p,'jilian:runtime',cloud);assert.equal(state(p),'connecting');assert.equal(p.timers.size,1);
 reply(p,'jilian:ready');assert.equal(state(p),'connected');assert.equal(p.timers.size,0);
 assert.equal(p.elements['connection-cover'].hidden,true);assert.equal(p.elements.assistant.attributes['aria-hidden'],'false');
 assert.match(p.elements.runtime.textContent,/实际分析结果/);assert.doesNotMatch(p.elements.connection.textContent,/Gemini.*成功/);
 const link=new URL(p.elements.standalone.href);assert.equal(link.port,'8890');assert.equal(link.searchParams.has('panel'),false);
});

test('competition panel has no demo controls and a stored demo preference is retired',()=>{
 const html=fs.readFileSync(path.join(__dirname,'../extension/panel.html'),'utf8');
 assert.doesNotMatch(html,/id="mode-demo"|id="mode-live"|id="open-demo"/);
 const p=setup(assetURL(asset),undefined,false,'demo');
 assert.equal(new URL(p.elements.assistant.src).searchParams.get('mode'),'live');
 assert.equal(p.storage.has('jilian-data-mode'),false);
 assert.equal(p.elements.identify.hidden,false);
});
test('legacy data switch isolates demo from Trackunit and re-reads the current asset on return',async()=>{
 const p=setup(assetURL(asset),undefined,true);ready(p);await p.follow();matched(p);
 assert.equal(new URL(p.elements.assistant.src).searchParams.get('mode'),'live');
 p.elements['mode-demo'].onclick();let url=new URL(p.elements.assistant.src);
 assert.equal(url.searchParams.get('mode'),'demo');assert.equal(url.hash,'');
 assert.equal(p.storage.get('jilian-data-mode'),'demo');
 assert.equal(p.elements['mode-demo'].attributes['aria-pressed'],'true');
 ready(p);assert.match(p.elements.context.textContent,/自动跟随已暂停/);
 assert.equal([...p.timers.values()].filter(timer=>timer.ms===150).length,0);
 p.elements['mode-live'].onclick();url=new URL(p.elements.assistant.src);
 assert.equal(url.searchParams.get('mode'),'live');assert.equal(p.elements['mode-live'].attributes['aria-pressed'],'true');
 ready(p);await p.follow();
 assert.equal(new URL(p.elements.assistant.src).hash,'#trackunit-asset='+asset);
});

test('normal automatic association keeps manual device refresh available',async()=>{
 const p=setup(assetURL(asset));ready(p);await p.elements.identify.onclick();matched(p);
 assert.equal(p.elements.identify.hidden,false);
 reply(p,'jilian:context',{asset_id:asset,state:'unavailable'});
 assert.equal(p.elements.identify.hidden,false);
 matched(p);assert.equal(p.elements.identify.hidden,false);
});

test('catalog maintenance opens inside settings without closing its parent',()=>{
 const p=setup();p.elements['connection-options'].open=true;
 p.elements['connection-options'].contains=element=>element===p.elements['catalog-options'];
 p.elements['catalog-options'].open=true;p.elements['catalog-options'].dispatch('toggle');
 assert.equal(p.elements['connection-options'].open,true);
 assert.equal(p.elements['catalog-options']._panel.hidden,false);
});

test('DeepSeek runtime is displayed without claiming a successful AI request',()=>{
 const p=setup();reply(p,'jilian:ready');
 reply(p,'jilian:runtime',{provider:'deepseek',model:'deepseek-flash',backend_build:cloud.backend_build,
  inference_location:'cloud',investigation_timeout_seconds:120,transient_attempt_limit:3});
 assert.equal(state(p),'connected');assert.match(p.elements.runtime.textContent,/deepseek-flash/);
 assert.match(p.elements.runtime.textContent,/实际分析结果/);assert.doesNotMatch(p.elements.runtime.textContent,/Gemini|认证成功|调用成功/);
});

test('failed default port falls back and partial or stale handshakes cannot combine',()=>{
 const p=setup(),old=new URL(p.elements.assistant.src);reply(p,'jilian:ready');p.tick();
 const current=new URL(p.elements.assistant.src);assert.equal(current.port,'8892');assert.notEqual(current.search,old.search);
 assert.match(p.elements['cover-detail'].textContent,/备用连接/);assert.equal(p.elements['connection-cover'].hidden,false);
 reply(p,'jilian:ready',{},old);reply(p,'jilian:runtime',cloud,old);reply(p,'jilian:runtime',cloud);
 assert.equal(state(p),'connecting');reply(p,'jilian:ready');assert.equal(state(p),'connected');
 assert.match(p.elements['connection-detail'].textContent,/自动连接 8892/);assert.equal(p.storage.size,0);
});

test('both timeouts unload error frame and expose a fresh retry',()=>{
 const p=setup();p.tick();const last=new URL(p.elements.assistant.src);p.tick();
 assert.equal(state(p),'failed');assert.equal(p.elements.assistant.src,undefined);assert.equal(p.elements.help.hidden,false);
 assert.equal(p.elements['cover-retry'].hidden,false);assert.match(p.elements['cover-detail'].textContent,/尚未|未找到/);
 assert.equal(p.elements['start-command'].textContent,'start_local.cmd --port 8890');
 reply(p,'jilian:ready',{},last);reply(p,'jilian:runtime',cloud,last);assert.equal(state(p),'failed');
 let blocked=false;p.elements.standalone.onclick({preventDefault:()=>blocked=true});assert.equal(blocked,true);
 p.elements['cover-retry'].onclick();assert.equal(state(p),'connecting');assert.equal(p.elements.help.hidden,true);
 assert.equal(new URL(p.elements.assistant.src).port,'8890');assert.notEqual(new URL(p.elements.assistant.src).search,last.search);
});

test('saved allowed port is tried first, fallback never overwrites preference',()=>{
 const p=setup(undefined,'8892');assert.equal(new URL(p.elements.assistant.src).port,'8892');p.tick();
 assert.equal(new URL(p.elements.assistant.src).port,'8890');ready(p);assert.equal(p.storage.get('jilian-service-port'),'8892');
 assert.equal(p.elements['service-port'].value,'8892');
 for(const invalid of ['https://evil.test','8888','8890/path']){
  const invalidPanel=setup(undefined,invalid);assert.equal(new URL(invalidPanel.elements.assistant.src).port,'8890');
 }
});

test('only exact frame source, origin, protocol and nonce may establish connection',()=>{
 const p=setup(),url=new URL(p.elements.assistant.src);
 const data={type:'jilian:ready',protocol:1,connection_id:url.searchParams.get('panel')};
 p.handlers.message({origin:'https://evil.test',source:p.elements.assistant.contentWindow,data});
 p.handlers.message({origin:url.origin,source:{},data});
 reply(p,'jilian:ready',{protocol:0});reply(p,'jilian:ready',{connection_id:'wrong'});reply(p,'jilian:runtime',cloud);
 assert.equal(state(p),'connecting');reply(p,'jilian:ready');assert.equal(state(p),'connected');
});

test('malformed runtime is rejected and local configuration does not block offline work',()=>{
 const p=setup();reply(p,'jilian:ready');
 for(const invalid of [{...cloud,provider:''},{...cloud,model:1},{...cloud,backend_build:'x'.repeat(161)}])reply(p,'jilian:runtime',invalid);
 assert.equal(state(p),'connecting');reply(p,'jilian:runtime',{provider:'ollama',model:'local-model',backend_build:cloud.backend_build});
 assert.equal(state(p),'connected');assert.match(p.elements.runtime.textContent,/ollama/);assert.match(p.elements.runtime.textContent,/实际分析结果/);
});

test('manual reconnect creates a new nonce and obsolete timeout cannot move it',()=>{
 const p=setup(),old=new URL(p.elements.assistant.src),oldTimer=p.timers.values().next().value.fn;
 p.elements.retry.onclick();const current=p.elements.assistant.src;assert.notEqual(new URL(current).search,old.search);
 reply(p,'jilian:ready',{},old);reply(p,'jilian:runtime',cloud,old);assert.equal(state(p),'connecting');
 oldTimer();assert.equal(p.elements.assistant.src,current);ready(p);assert.equal(state(p),'connected');oldTimer();assert.equal(state(p),'connected');
});

test('same work document forwards only UUID with unchanged connection and renewed device acknowledgement',async()=>{
 const p=setup(`https://new.manager.trackunit.com/assets/${asset}/status?token=secret`);ready(p);
 const before=new URL(p.elements.assistant.src);await p.elements.identify.onclick();const after=new URL(p.elements.assistant.src);
 assert.equal(after.hash,`#trackunit-asset=${asset}`);assert.equal(after.search,before.search);assert.equal(after.searchParams.has('token'),false);
 assert.equal(state(p),'connected');assert.match(p.elements.context.textContent,/等待/);assert.equal(p.timers.size,1);
 assert.equal(p.outgoing.at(-1).data.asset_id,asset);assert.equal(p.outgoing.at(-1).origin,'http://127.0.0.1:8890');
 assert.equal(new URL(p.elements.standalone.href).hash,after.hash);
 reply(p,'jilian:context',{asset_id:asset,state:'pending'});assert.match(p.elements.context.textContent,/尚未切换/);
 reply(p,'jilian:context',{asset_id:asset,state:'choose_version',available_versions:2});assert.match(p.elements.context.textContent,/版本尚未选定/);
 reply(p,'jilian:context',{asset_id:asset,machine_id:asset,state:'matched',source:'trackunit_cache',dataset_id:null,selection_id:'fleet:'+asset});
 assert.match(p.elements.context.textContent,/已关联/);assert.equal(p.timers.size,0);
 const confirmed=p.elements.context.textContent;reply(p,'jilian:context',{asset_id:'wrong',state:'missing'});assert.equal(p.elements.context.textContent,confirmed);
});

test('reading during initial connection preserves handshake and includes device before readiness',async()=>{
 const p=setup(`https://manager.trackunit.com/assets/${asset}`),old=new URL(p.elements.assistant.src);reply(p,'jilian:runtime',cloud);
 await p.elements.identify.onclick();assert.equal(new URL(p.elements.assistant.src).search,old.search);assert.equal(p.outgoing.length,0);
 reply(p,'jilian:ready');
 assert.equal(state(p),'connected');assert.equal(p.outgoing.length,1);assert.equal(p.outgoing[0].data.asset_id,asset);
 p.tick();assert.match(p.elements.context.textContent,/尚未收到设备匹配确认/);
});

test('service change retains UUID but resets handshake and rejects old origin',async()=>{
 const p=setup(`https://manager.trackunit.com/assets/${asset}`);ready(p);await p.elements.identify.onclick();
 const oldURL=new URL(p.elements.assistant.src);p.elements['service-port'].value='8892';let prevented=false;
 p.elements['service-form'].onsubmit({preventDefault:()=>prevented=true});assert.equal(prevented,true);
 assert.equal(p.storage.get('jilian-service-port'),'8892');const next=new URL(p.elements.assistant.src);
 assert.equal(next.port,'8892');assert.equal(next.hash,`#trackunit-asset=${asset}`);assert.equal(p.timers.size,1);
 p.handlers.message({origin:oldURL.origin,source:p.elements.assistant.contentWindow,data:{type:'jilian:ready',protocol:1,connection_id:next.searchParams.get('panel')}});
 reply(p,'jilian:runtime',cloud);assert.equal(state(p),'connecting');reply(p,'jilian:ready');assert.equal(state(p),'connected');
 reply(p,'jilian:context',{asset_id:asset,state:'missing'});assert.equal(p.timers.size,0);
 p.elements['service-port'].value='https://evil.test';const before=p.elements.assistant.src;
 p.elements['service-form'].onsubmit({preventDefault(){}});assert.equal(p.elements.assistant.src,before);
});

test('demo asks before replacing connected work and cancel preserves frame and context',async()=>{
 const p=setup(`https://manager.trackunit.com/assets/${asset}`);ready(p);await p.elements.identify.onclick();
 const before=p.elements.assistant.src,context=p.elements.context.textContent;
 p.box.window.confirm=message=>{p.confirmations.push(message);return false;};p.elements['open-demo'].onclick();
 assert.equal(p.elements.assistant.src,before);assert.equal(p.elements.context.textContent,context);assert.equal(state(p),'connected');
 assert.equal(p.confirmations[0],'打开历史分析回放会重新载入工作区，未保存的输入将丢失。是否继续？');
 p.box.window.confirm=()=>true;p.elements['open-demo'].onclick();const demo=new URL(p.elements.assistant.src);
 assert.equal(demo.searchParams.get('demo'),'1');assert.ok(demo.searchParams.get('panel'));assert.equal(demo.hash,'');
 assert.notEqual(demo.searchParams.get('panel'),new URL(before).searchParams.get('panel'));assert.equal(state(p),'connecting');
 reply(p,'jilian:ready',{},new URL(before));reply(p,'jilian:runtime',cloud,new URL(before));assert.equal(state(p),'connecting');
 ready(p);assert.match(p.elements.context.textContent,/模拟案例/);
 assert.equal(new URL(p.elements.standalone.href).searchParams.get('demo'),'1');
 const unchanged=p.elements.assistant.src;p.elements['open-demo'].onclick();assert.equal(p.elements.assistant.src,unchanged);
});

test('initial demo skips confirmation and switching back to device creates fresh handshake',async()=>{
 const p=setup(`https://manager.trackunit.com/assets/${asset}`);p.elements['open-demo'].onclick();assert.equal(p.confirmations.length,0);
 ready(p);const demo=new URL(p.elements.assistant.src);await p.elements.identify.onclick();const work=new URL(p.elements.assistant.src);
 assert.equal(work.searchParams.has('demo'),false);assert.equal(work.hash,`#trackunit-asset=${asset}`);assert.notEqual(work.searchParams.get('panel'),demo.searchParams.get('panel'));
 assert.equal(state(p),'connecting');assert.equal(p.outgoing.length,0);reply(p,'jilian:ready');assert.equal(state(p),'connecting');
 reply(p,'jilian:runtime',cloud);assert.equal(state(p),'connected');assert.equal(p.outgoing.at(-1).data.asset_id,asset);
});

test('invalid current page leaves previous frame and clearly reports no new selection',async()=>{
 const p=setup('https://new.manager.trackunit.com/administration');ready(p);const original=p.elements.assistant.src;
 await p.elements.identify.onclick();assert.equal(p.elements.assistant.src,original);assert.match(p.elements.context.textContent,/无法识别/);
});

test('page navigation notice survives late device acknowledgement until current page is identified',async()=>{
 const p=setup(`https://manager.trackunit.com/assets/${asset}`);ready(p);await p.elements.identify.onclick();
 p.tabHandlers.activated({windowId:2});assert.doesNotMatch(p.elements.context.textContent,/当前页面尚未关联/);
 p.tabHandlers.updated(10,{status:'loading'});assert.match(p.elements.context.textContent,/当前页面尚未关联/);
 reply(p,'jilian:context',{asset_id:asset,machine_id:asset,state:'matched',source:'trackunit_cache',dataset_id:null,selection_id:'fleet:'+asset});
 assert.match(p.elements.context.textContent,/当前页面尚未关联/);await p.elements.identify.onclick();assert.doesNotMatch(p.elements.context.textContent,/当前页面尚未关联/);
});

test('navigation during asynchronous tab lookup cannot commit a stale device',async()=>{
 const p=setup(`https://manager.trackunit.com/assets/${asset}`);let resolve;p.box.chrome.tabs.query=()=>new Promise(done=>resolve=done);
 const before=p.elements.assistant.src,read=p.elements.identify.onclick();p.tabHandlers.activated({windowId:1});
 resolve([{url:`https://manager.trackunit.com/assets/${asset}`,id:10,windowId:1}]);await read;
 assert.equal(p.elements.assistant.src,before);assert.equal(p.elements.identify.disabled,false);
});

test('manifest only permits exact Trackunit and XGSS sites and two loopback frames',()=>{
 const manifest=JSON.parse(fs.readFileSync(path.join(__dirname,'../extension/manifest.json'),'utf8'));
 // The exact version is a release fact that changes every packaging round; what
 // must hold is that it is a well-formed MV3 version and that the advertised
 // package for it exists, so a bump cannot ship without its ZIP.
 assert.match(manifest.version,/^\d+\.\d+\.\d+$/);
 assert.equal(fs.existsSync(path.join(__dirname,'../dist',`jilian-extension-${manifest.version}.zip`)),true,
   `dist/jilian-extension-${manifest.version}.zip must exist for the manifest version`);
 assert.deepEqual(manifest.permissions,['sidePanel','activeTab','scripting']);
 assert.deepEqual(manifest.host_permissions,['https://manager.trackunit.com/*','https://new.manager.trackunit.com/*','https://xgss.xcmg.com/*']);
 assert.equal(manifest.content_scripts,undefined);
 assert.match(manifest.content_security_policy.extension_pages,/frame-src http:\/\/127\.0\.0\.1:8890 http:\/\/127\.0\.0\.1:8892$/);
 assert.equal(manifest.content_security_policy.extension_pages.includes('*'),false);
});

const otherAsset='00000000-0000-0000-0000-000000000002';
const assetURL=id=>`https://new.manager.trackunit.com/assets/${id}/status`;
const flush=()=>new Promise(resolve=>setImmediate(resolve));
const tab=(id=asset,tabId=10,windowId=1)=>({url:assetURL(id),id:tabId,windowId,status:'complete'});
const matched=(p,id=asset)=>reply(p,'jilian:context',{asset_id:id,machine_id:id,state:'matched',source:'trackunit_cache',dataset_id:null,selection_id:'fleet:'+id});

test('installed panel forwards visible Trackunit Events fault cards to the matched machine',async()=>{
 const url=`https://new.manager.trackunit.com/assets/${asset}/events`;
 const p=setup(url,undefined,true);ready(p);await p.follow();matched(p);await flush();
 const capture={schema_version:1,source:'trackunit_visible_events_page',asset_id:asset,
  capture_status:'visible_fault_cards',coverage:'rendered_active_fault_cards_only',
  observed_at:'2026-09-23T06:00:00Z',faults:[{code:'SPN 2664 / FMI 3',spn:2664,fmi:3,sa:160,
   description:'Joystick 1 Theta-Axis Position - Voltage Above Normal',severity:'Low',displayed_at:'Sep 12, 2026, 7:37 AM'}]};
 p.scriptResults.push([],[{result:capture}]);
 const pending=[...p.timers.entries()].find(([,timer])=>timer.ms===900);
 assert.ok(pending,'fault card capture should be scheduled after matching the device');
 p.timers.delete(pending[0]);pending[1].fn();await flush();
 assert.equal(p.scriptCalls.length,2);
 assert.deepEqual(Array.from(p.scriptCalls[0].files),['trackunit-fault-page.js']);
 const forwarded=p.outgoing.find(item=>item.data.type==='jilian:trackunit-page-faults');
 assert.equal(forwarded.origin,'http://127.0.0.1:8890');
 assert.equal(forwarded.data.asset_id,asset);
 assert.equal(forwarded.data.capture.faults[0].code,'SPN 2664 / FMI 3');
});

test('panel reports a same-device page read failure without calling it an empty fault result',async()=>{
 const url=`https://new.manager.trackunit.com/assets/${asset}/events`;
 const p=setup(url,undefined,true);ready(p);await p.follow();matched(p);await flush();
 p.box.chrome.scripting.executeScript=async()=>{throw new Error('site permission denied');};
 const pending=[...p.timers.entries()].find(([,timer])=>timer.ms===900);
 assert.ok(pending);p.timers.delete(pending[0]);pending[1].fn();await flush();
 assert.ok(p.outgoing.some(item=>item.data.type==='jilian:trackunit-page-faults-error'&&item.data.asset_id===asset));
 assert.equal(p.outgoing.some(item=>item.data.type==='jilian:trackunit-page-faults'),false);
});

test('manual page-fault request reads only the matched active Events tab',async()=>{
 const url=`https://new.manager.trackunit.com/assets/${asset}/events`;
 const p=setup(url,undefined,true);ready(p);await p.follow();matched(p);await flush();
 const capture={schema_version:1,source:'trackunit_visible_events_page',asset_id:asset,
  capture_status:'visible_fault_cards',coverage:'rendered_active_fault_cards_only',
  observed_at:'2026-09-23T06:00:00Z',faults:[{code:'SPN 2664 / FMI 3',spn:2664,fmi:3,sa:160,
   description:'Joystick fault',severity:'Low',displayed_at:'Sep 12, 2026'}]};
 p.scriptResults.push([],[{result:capture}]);
 reply(p,'jilian:trackunit-page-faults-request',{asset_id:otherAsset,dataset_id:null});await flush();
 assert.equal(p.scriptCalls.length,0,'wrong device cannot read the page');
 reply(p,'jilian:trackunit-page-faults-request',{asset_id:asset,dataset_id:null});await flush();
 assert.equal(p.scriptCalls.length,2);
 assert.ok(p.outgoing.some(item=>item.data.type==='jilian:trackunit-page-faults'&&item.data.capture.faults[0].spn===2664));
});

test('manual page-fault request explains when the active tab is not this device Events page',async()=>{
  const p=setup(assetURL(asset),undefined,true);ready(p);await p.follow();matched(p);await flush();
  reply(p,'jilian:trackunit-page-faults-request',{asset_id:asset,dataset_id:null});await flush();
  assert.equal(p.scriptCalls.length,0);
  assert.ok(p.outgoing.some(item=>item.data.type==='jilian:trackunit-page-faults-error'&&item.data.reason==='wrong_page'));
});

test('manual fault read reports identity verification instead of silently timing out',async()=>{
  const url=`https://new.manager.trackunit.com/assets/${asset}/events`;
  const p=setup(url,undefined,true);ready(p);await p.follow();matched(p);await flush();
  p.tabHandlers.updated(10,{status:'loading'});
  reply(p,'jilian:trackunit-page-faults-request',{asset_id:asset,dataset_id:null});await flush();
  assert.equal(p.scriptCalls.length,0);
  assert.ok(p.outgoing.some(item=>item.data.type==='jilian:trackunit-page-faults-error'&&item.data.reason==='identity_pending'));
});

test('invalid fault-page capture returns an error instead of leaving manual read pending',async()=>{
  const url=`https://new.manager.trackunit.com/assets/${asset}/events`;
  const p=setup(url,undefined,true);ready(p);await p.follow();matched(p);await flush();
  p.scriptResults.push([],[{result:{schema_version:1,asset_id:otherAsset,capture_status:'visible_fault_cards'}}]);
  reply(p,'jilian:trackunit-page-faults-request',{asset_id:asset,dataset_id:null});await flush();
  assert.ok(p.outgoing.some(item=>item.data.type==='jilian:trackunit-page-faults-error'&&item.data.reason==='read_failed'));
});

test('startup automatically reads UUID during connection without changing its nonce or making API calls',async()=>{
 const p=setup(assetURL(asset)+'?session=do-not-forward',undefined,true),before=new URL(p.elements.assistant.src);
 await p.follow();const after=new URL(p.elements.assistant.src);
 assert.equal(after.hash,'#trackunit-asset='+asset);assert.equal(after.search,before.search);
 assert.equal(after.href.includes('do-not-forward'),false);assert.equal(state(p),'connecting');assert.equal(p.outgoing.length,0);
 ready(p);assert.equal(state(p),'connected');assert.equal(p.outgoing.length,1);assert.equal(p.outgoing[0].data.asset_id,asset);
 matched(p);assert.match(p.elements.context.textContent,/已关联/);
});

test('startup after readiness uses same iframe document and awaits exact local dataset acknowledgement',async()=>{
 const p=setup(assetURL(asset),undefined,true);ready(p);const before=new URL(p.elements.assistant.src);
 await p.follow();assert.equal(new URL(p.elements.assistant.src).search,before.search);
 assert.match(p.elements.context.textContent,/等待/);
 reply(p,'jilian:context',{asset_id:asset,state:'missing'});assert.match(p.elements.context.textContent,/暂无可用数据/);
 assert.doesNotMatch(p.elements.context.textContent,/已关联/);
 reply(p,'jilian:context',{asset_id:asset,state:'choose_version'});assert.match(p.elements.context.textContent,/版本尚未选定/);
});

test('SPA asset change follows automatically by hash and reports in-flight work as pending',async()=>{
 const p=setup(assetURL(asset),undefined,true);ready(p);await p.follow();matched(p);
 const before=new URL(p.elements.assistant.src);p.box.chrome.tabs.query=async()=>[tab(otherAsset)];
 p.tabHandlers.updated(10,{url:assetURL(otherAsset)});
 assert.equal(p.elements.context.dataset.stale,'true');await p.follow();
 const after=new URL(p.elements.assistant.src);assert.equal(after.search,before.search);assert.equal(after.hash,'#trackunit-asset='+otherAsset);
 assert.equal(p.elements.context.dataset.stale,'false');
 reply(p,'jilian:context',{asset_id:otherAsset,state:'pending'});assert.match(p.elements.context.textContent,/尚未切换/);
 matched(p,asset);assert.doesNotMatch(p.elements.context.textContent,/已关联/);
 matched(p,otherAsset);assert.match(p.elements.context.textContent,/已关联/);
});

test('latest navigation wins when earlier asynchronous URL lookup resolves afterward',async()=>{
 const p=setup(assetURL(asset),undefined,true);ready(p);await p.follow();
 const callbacks=[];p.box.chrome.tabs.query=()=>new Promise(resolve=>callbacks.push(resolve));
 p.tabHandlers.updated(10,{url:assetURL(asset)});await p.follow();
 p.tabHandlers.updated(10,{url:assetURL(otherAsset)});await p.follow();assert.equal(callbacks.length,2);
 callbacks[1]([tab(otherAsset)]);await flush();matched(p,otherAsset);
 const before=p.elements.assistant.src,message=p.elements.context.textContent;
 callbacks[0]([tab(asset)]);await flush();
 assert.equal(p.elements.assistant.src,before);assert.equal(p.elements.context.textContent,message);
});

test('loading page never commits old URL and completion reads the newly committed device',async()=>{
 const p=setup(assetURL(asset),undefined,true);ready(p);await p.follow();matched(p);
 const before=p.elements.assistant.src;
 p.box.chrome.tabs.query=async()=>[{...tab(asset),status:'loading',pendingUrl:assetURL(otherAsset)}];
 p.tabHandlers.updated(10,{status:'loading',url:assetURL(otherAsset)});await p.follow();
 assert.equal(p.elements.assistant.src,before);assert.match(p.elements.context.textContent,/页面正在加载/);
 matched(p);assert.doesNotMatch(p.elements.context.textContent,/已关联/);
 p.box.chrome.tabs.query=async()=>[tab(otherAsset)];p.tabHandlers.updated(10,{status:'complete'});await p.follow();
 assert.equal(new URL(p.elements.assistant.src).hash,'#trackunit-asset='+otherAsset);
});

test('navigation bursts debounce and a repeated device does not reset iframe or confirmation deadline',async()=>{
 const p=setup(assetURL(asset),undefined,true);ready(p);await p.follow();matched(p);
 const before=p.elements.assistant.src;let queries=0;p.box.chrome.tabs.query=async()=>{queries++;return [tab()];};
 p.tabHandlers.updated(10,{url:assetURL(asset).replace('/status','/location')});
 p.tabHandlers.updated(10,{status:'complete'});p.tabHandlers.updated(10,{url:assetURL(asset)});
 assert.equal([...p.timers.values()].filter(timer=>timer.ms===150).length,1);await p.follow();
 assert.equal(queries,1);assert.equal(p.elements.assistant.src,before);
 assert.equal([...p.timers.values()].filter(timer=>timer.ms===8000).length,0);assert.match(p.elements.context.textContent,/已关联/);
});

test('only active tabs in the side panel window can change the selected machine',async()=>{
 const p=setup(assetURL(asset),undefined,true);ready(p);await p.follow();matched(p);
 const before=p.elements.assistant.src,message=p.elements.context.textContent;
 p.tabHandlers.updated(99,{url:assetURL(otherAsset),status:'complete'});p.tabHandlers.activated({tabId:99,windowId:2});
 assert.equal(p.elements.assistant.src,before);assert.equal(p.elements.context.textContent,message);
 assert.equal([...p.timers.values()].some(timer=>timer.ms===150),false);
 p.box.chrome.tabs.query=async()=>[tab(otherAsset,12)];p.tabHandlers.activated({tabId:12,windowId:1});await p.follow();
 assert.equal(new URL(p.elements.assistant.src).hash,'#trackunit-asset='+otherAsset);
});

test('unsupported, list and permission-redacted pages keep drafts but never claim current machine association',async()=>{
 for(const url of ['https://example.com','https://new.manager.trackunit.com/assets',undefined]){
  const p=setup(assetURL(asset),undefined,true);ready(p);await p.follow();matched(p);const before=p.elements.assistant.src;
  p.box.chrome.tabs.query=async()=>[{id:12,windowId:1,url,status:'complete'}];
  p.tabHandlers.activated({tabId:12,windowId:1});await p.follow();
  assert.equal(p.elements.assistant.src,before);assert.equal(p.elements.context.dataset.stale,'true');
  assert.match(p.elements.context.textContent,/当前页面尚未关联/);assert.match(p.elements.context.textContent,/无法识别/);
  const message=p.elements.context.textContent;matched(p);assert.equal(p.elements.context.textContent,message);
  p.box.chrome.tabs.query=async()=>[tab(otherAsset,12)];p.tabHandlers.updated(12,{url:assetURL(otherAsset),status:'complete'});await p.follow();
  assert.equal(new URL(p.elements.assistant.src).hash,'#trackunit-asset='+otherAsset);
 }
});

test('demo pauses queued automatic reads and only an explicit read resumes machine following',async()=>{
 const p=setup(assetURL(asset),undefined,true);ready(p);await p.follow();
 p.tabHandlers.updated(10,{url:assetURL(otherAsset)});p.elements['open-demo'].onclick();ready(p);
 const before=p.elements.assistant.src;assert.equal(p.elements.follow.attributes['aria-pressed'],'false');
 assert.match(p.elements.context.textContent,/自动跟随已暂停/);
 p.box.chrome.tabs.query=async()=>[tab(otherAsset)];p.tabHandlers.updated(10,{status:'complete'});
 assert.equal([...p.timers.values()].some(timer=>timer.ms===150),false);assert.equal(p.elements.assistant.src,before);
 await p.elements.identify.onclick();assert.equal(p.elements.follow.attributes['aria-pressed'],'true');
 assert.equal(new URL(p.elements.assistant.src).hash,'#trackunit-asset='+otherAsset);assert.equal(new URL(p.elements.assistant.src).searchParams.has('demo'),false);
});

test('follow can pause without reloading work and manual read resumes it',async()=>{
 const p=setup(assetURL(asset),undefined,true);ready(p);await p.follow();matched(p);
 const before=p.elements.assistant.src;p.elements.follow.onclick();assert.match(p.elements.context.textContent,/自动跟随已暂停/);
 p.box.chrome.tabs.query=async()=>[tab(otherAsset)];p.tabHandlers.updated(10,{url:assetURL(otherAsset)});
 assert.equal(p.elements.assistant.src,before);assert.equal([...p.timers.values()].some(timer=>timer.ms===150),false);
 matched(p);assert.doesNotMatch(p.elements.context.textContent,/已关联/);
 await p.elements.identify.onclick();assert.equal(new URL(p.elements.assistant.src).hash,'#trackunit-asset='+otherAsset);
 assert.equal(p.elements.follow.attributes['aria-pressed'],'true');
});

test('an outstanding auto-read cannot replace explicit demo or manual selection',async()=>{
 const p=setup(assetURL(asset),undefined,true);ready(p);await p.follow();
 let resolve;p.box.chrome.tabs.query=()=>new Promise(done=>resolve=done);
 p.tabHandlers.updated(10,{url:assetURL(otherAsset)});await p.follow();p.elements['open-demo'].onclick();const demo=p.elements.assistant.src;
 resolve([tab(otherAsset)]);await flush();assert.equal(p.elements.assistant.src,demo);
 assert.equal(p.elements.follow.attributes['aria-pressed'],'false');
});

test('automatic identification while connection failed retains UUID without a reconnect loop',async()=>{
 const p=setup(assetURL(asset),undefined,true);await p.follow();p.tick();p.tick();assert.equal(state(p),'failed');
 p.box.chrome.tabs.query=async()=>[tab(otherAsset)];p.tabHandlers.updated(10,{url:assetURL(otherAsset)});await p.follow();
 assert.equal(state(p),'failed');assert.equal(p.elements.assistant.src,undefined);assert.equal(p.timers.size,0);
 assert.match(p.elements.context.textContent,/本机服务尚未连接/);p.elements.retry.onclick();
 assert.equal(new URL(p.elements.assistant.src).hash,'#trackunit-asset='+otherAsset);ready(p);matched(p,otherAsset);
 assert.match(p.elements.context.textContent,/已关联/);
});

test('browser lookup errors do not expose raw URLs or secret-bearing browser messages',async()=>{
 const p=setup(assetURL(asset),undefined,true);ready(p);await p.follow();matched(p);
 p.box.chrome.tabs.query=async()=>{throw new Error('https://private.example/?token=do-not-display');};
 p.tabHandlers.updated(10,{status:'complete'});await p.follow();
 assert.match(p.elements.context.textContent,/站点访问权限/);assert.equal(p.elements.context.dataset.stale,'true');
 assert.equal(p.elements.context.textContent.includes('do-not-display'),false);assert.equal(p.elements.context.textContent.includes('private.example'),false);
});

test('switching to XGSS retains matched device and does not reload its investigation',async()=>{
 const p=setup(assetURL(asset),undefined,true);ready(p);await p.follow();matched(p);
 const before=p.elements.assistant.src;
 p.box.chrome.tabs.query=async()=>[{url:'https://xgss.xcmg.com/catalog?token=SECRET',id:11,windowId:1,status:'complete'}];
 p.tabHandlers.activated({windowId:1,tabId:11});await p.follow();
 assert.equal(p.elements.assistant.src,before);assert.match(p.elements.context.textContent,/保留当前设备调查/);
 assert.equal(p.elements.context.textContent.includes('SECRET'),false);
});

test('catalog capture forwards only rows and matched dataset through the current iframe',async()=>{
 const p=setup(assetURL(asset),undefined,true);ready(p);await p.follow();
 reply(p,'jilian:context',{asset_id:asset,machine_id:asset,state:'matched',source:'imported_user_supplied',dataset_id:'a'.repeat(64),selection_id:'dataset:'+'a'.repeat(64)});
 const capture=require('../extension/xgss-catalog.js').parse(require('./fixtures/xgss-visible-catalog-test.json'));
 const injections=[];p.box.chrome.scripting={executeScript:async options=>{injections.push(options);return options.files?[]:[{frameId:0,result:capture}];}};
 p.box.chrome.tabs.query=async()=>[{url:'https://xgss.xcmg.com/catalog?token=SECRET',id:11,windowId:1,status:'complete'}];
 await p.elements['capture-catalog'].onclick();
 assert.equal(injections.length,2);assert.equal(injections[0].target.tabId,11);
 const posted=p.outgoing.at(-1);assert.equal(posted.origin,'http://127.0.0.1:8890');
 assert.equal(posted.data.type,'jilian:xgss-catalog-capture');assert.equal(posted.data.dataset_id,'a'.repeat(64));
 assert.equal(posted.data.asset_id,asset);assert.equal(posted.data.capture.source_url,'https://xgss.xcmg.com/');
 assert.equal(JSON.stringify(posted).includes('SECRET'),false);assert.equal(p.elements['capture-catalog'].disabled,true);
 reply(p,'jilian:xgss-catalog-result',{request_id:'wrong',success:true,message:'wrong'});
 assert.equal(p.elements['capture-catalog'].disabled,true);
 reply(p,'jilian:xgss-catalog-result',{request_id:posted.data.request_id,success:true,message:'已核对 VIN 并保存 2 行。'});
 assert.equal(p.elements['capture-catalog'].disabled,false);assert.match(p.elements['catalog-status'].textContent,/保存 2 行/);
});

test('catalog read rejects missing device, unreadable rows and ambiguous frames',async()=>{
 const p=setup(assetURL(asset));ready(p);
 await p.elements['capture-catalog'].onclick();assert.match(p.elements['catalog-status'].textContent,/确认实测数据/);
 await p.elements.identify.onclick();matched(p);
 p.box.chrome.tabs.query=async()=>[{url:'https://xgss.xcmg.com/catalog',id:11,windowId:1,status:'complete'}];
 let result={capture_status:'vin_missing'};p.box.chrome.scripting={executeScript:async options=>options.files?[]:[{result}]};
 await p.elements['capture-catalog'].onclick();assert.match(p.elements['catalog-status'].textContent,/未显示可识别/);
 const capture=require('../extension/xgss-catalog.js').parse(require('./fixtures/xgss-visible-catalog-test.json'));
 p.box.chrome.scripting.executeScript=async options=>options.files?[]:[{result:capture},{result:capture}];
 await p.elements['capture-catalog'].onclick();assert.match(p.elements['catalog-status'].textContent,/多个图册区域/);
 assert.equal(p.outgoing.some(item=>item.data.type==='jilian:xgss-catalog-capture'),false);
});

test('catalog read does not expose raw browser errors and rejects mid-read device changes',async()=>{
 const p=setup(assetURL(asset));ready(p);await p.elements.identify.onclick();matched(p);
 p.box.chrome.tabs.query=async()=>[{url:'https://xgss.xcmg.com/catalog',id:11,windowId:1,status:'complete'}];
 p.box.chrome.scripting={executeScript:async()=>{throw new Error('https://private.example/?token=SECRET');}};
 await p.elements['capture-catalog'].onclick();assert.equal(p.elements['catalog-status'].textContent.includes('SECRET'),false);
 let resolve;p.box.chrome.scripting.executeScript=async options=>options.files?[]:new Promise(done=>resolve=done);
 const pending=p.elements['capture-catalog'].onclick();await flush();
 p.box.chrome.tabs.query=async()=>[tab(otherAsset)];await p.elements.identify.onclick();matched(p,otherAsset);
 const currentStatus=p.elements['catalog-status'].textContent;
 const capture=require('../extension/xgss-catalog.js').parse(require('./fixtures/xgss-visible-catalog-test.json'));
 resolve([{result:capture}]);await pending;
 assert.equal(p.elements['catalog-status'].textContent,currentStatus,'an old read must not overwrite the new device status');
 assert.match(currentStatus,/设备已切换/);
 assert.equal(p.outgoing.some(item=>item.data.type==='jilian:xgss-catalog-capture'),false);
});

test('old running backend cannot masquerade as a compatible connection',()=>{
 const p=setup();reply(p,'jilian:ready');const old=new URL(p.elements.assistant.src);
 reply(p,'jilian:runtime',{...cloud,backend_build:'20260915.8-xe55u-components'});
 assert.equal(new URL(p.elements.assistant.src).port,'8892');assert.equal(state(p),'connecting');
 assert.match(p.elements['connection-detail'].textContent,/服务版本较旧/);
 reply(p,'jilian:runtime',cloud,old);assert.equal(state(p),'connecting');
 ready(p);assert.equal(state(p),'connected');
 const noCompatible=setup();reply(noCompatible,'jilian:runtime',{...cloud,backend_build:'unknown'});
 reply(noCompatible,'jilian:runtime',{...cloud,backend_build:'20260914.99-old'});
 assert.equal(state(noCompatible),'failed');assert.match(noCompatible.elements['cover-detail'].textContent,/兼容/);
});

test('iframe demo navigation synchronizes pause and manual read really returns to the same asset',async()=>{
 const p=setup(assetURL(asset));ready(p);await p.elements.identify.onclick();matched(p);
 reply(p,'jilian:view',{view:'demo',reason:'user',asset_id:asset});
 assert.equal(p.elements.follow.attributes['aria-pressed'],'false');assert.match(p.elements.context.textContent,/模拟案例.*暂停/);
 const before=p.elements.assistant.src;
 p.tabHandlers.updated(10,{status:'complete'});assert.equal(p.elements.assistant.src,before);
 await p.elements.follow.onclick();
 assert.equal(p.elements.follow.attributes['aria-pressed'],'true');
 assert.doesNotMatch(p.elements.context.textContent,/自动跟随已暂停/);
 ready(p);assert.equal(new URL(p.elements.assistant.src).searchParams.has('demo'),false);
 assert.equal(p.outgoing.at(-1).data.show_work,true);
});

test('resuming paused following removes stale paused copy immediately and requests work view for same asset',async()=>{
 const p=setup(assetURL(asset));ready(p);await p.elements.identify.onclick();matched(p);
 p.elements.follow.onclick();assert.match(p.elements.context.textContent,/已暂停/);
 const resumed=p.elements.follow.onclick();
 assert.equal(p.elements.follow.attributes['aria-pressed'],'true');assert.doesNotMatch(p.elements.context.textContent,/已暂停/);
 await resumed;assert.equal(p.outgoing.at(-1).data.show_work,true);
 assert.equal(new URL(p.elements.assistant.src).hash,'#trackunit-asset='+asset);
});

test('view sync rejects wrong frame, asset and unsupported reasons',async()=>{
 const p=setup(assetURL(asset));ready(p);await p.elements.identify.onclick();matched(p);
 reply(p,'jilian:view',{view:'demo',reason:'user',asset_id:otherAsset});
 reply(p,'jilian:view',{view:'demo',reason:'untrusted',asset_id:asset});
 const url=new URL(p.elements.assistant.src);
 p.handlers.message({origin:url.origin,source:{},data:{type:'jilian:view',protocol:1,connection_id:url.searchParams.get('panel'),view:'demo',reason:'user',asset_id:asset}});
 assert.equal(p.elements.follow.attributes['aria-pressed'],'true');
 reply(p,'jilian:view',{view:'demo',reason:'user',asset_id:asset});
 reply(p,'jilian:view',{view:'work',reason:'user',asset_id:asset});await flush();
 assert.equal(p.elements.follow.attributes['aria-pressed'],'true');assert.equal(p.outgoing.at(-1).data.show_work,true);
});

test('ordinary history or data navigation within work mode is not forced back to diagnosis',async()=>{
 const p=setup(assetURL(asset));ready(p);await p.elements.identify.onclick();matched(p);
 const before=p.outgoing.length,frame=p.elements.assistant.src;
 let queries=0;p.box.chrome.tabs.query=async()=>{queries++;return [tab(asset)];};
 reply(p,'jilian:view',{view:'work',reason:'user',asset_id:asset});await flush();
 assert.equal(queries,0);assert.equal(p.outgoing.length,before);assert.equal(p.elements.assistant.src,frame);
});

test('resume from demo during page loading completes automatically after navigation',async()=>{
 const p=setup(assetURL(asset));ready(p);await p.elements.identify.onclick();matched(p);
 reply(p,'jilian:view',{view:'demo',reason:'user',asset_id:asset});
 p.box.chrome.tabs.query=async()=>[{...tab(asset),status:'loading',pendingUrl:assetURL(asset)}];
 await p.elements.follow.onclick();
 assert.equal(p.elements.follow.attributes['aria-pressed'],'true');assert.match(p.elements.context.textContent,/页面正在加载/);
 p.box.chrome.tabs.query=async()=>[tab(asset)];p.tabHandlers.updated(10,{status:'complete'});await p.follow();
 assert.equal(p.outgoing.at(-1).data.show_work,true);assert.equal(p.elements.follow.attributes['aria-pressed'],'true');
});

test('only the active Trackunit title identifier is forwarded as a same-asset lookup hint',async()=>{
 const p=setup(assetURL(asset));ready(p);
 p.box.chrome.tabs.query=async()=>[{...tab(asset),title:'10046254 - Trackunit Manager'}];
 await p.elements.identify.onclick();
 assert.equal(p.outgoing.at(-1).data.equipment_id_hint,'10046254');
 assert.equal(new URL(p.elements.assistant.src).search.includes('10046254'),false);
 p.box.chrome.tabs.query=async()=>[{...tab(otherAsset),title:'XUG-TEST-B - Trackunit Manager'}];
 await p.elements.identify.onclick();assert.equal(p.outgoing.at(-1).data.asset_id,otherAsset);
 assert.equal(p.outgoing.at(-1).data.equipment_id_hint,'XUG-TEST-B');
 p.box.chrome.tabs.query=async()=>[{...tab(otherAsset),title:'https://private.test/?token=SECRET - Trackunit Manager'}];
 await p.elements.identify.onclick();assert.equal(p.outgoing.at(-1).data.equipment_id_hint,null);
 assert.equal(JSON.stringify(p.outgoing).includes('SECRET'),false);
});

test('late SPA title update supplies its lookup hint without reloading the current investigation',async()=>{
 const p=setup(assetURL(asset));ready(p);await p.elements.identify.onclick();matched(p);
 const before=p.elements.assistant.src;
 p.box.chrome.tabs.query=async()=>[{...tab(asset),title:'10046254 - Trackunit Manager'}];
 p.tabHandlers.updated(10,{title:'10046254 - Trackunit Manager'});await p.follow();
 assert.equal(p.elements.assistant.src,before);assert.equal(p.outgoing.at(-1).data.equipment_id_hint,'10046254');
});

test('newly ready asset frame can request the current hint without an acknowledgement loop',async()=>{
 const p=setup(assetURL(asset));ready(p);
 p.box.chrome.tabs.query=async()=>[{...tab(asset),title:'10046254 - Trackunit Manager'}];
 await p.elements.identify.onclick();const before=p.outgoing.length;
 reply(p,'jilian:asset-hint-request',{asset_id:otherAsset});assert.equal(p.outgoing.length,before);
 reply(p,'jilian:asset-hint-request',{asset_id:asset});assert.equal(p.outgoing.length,before+1);
 assert.equal(p.outgoing.at(-1).data.equipment_id_hint,'10046254');
 reply(p,'jilian:context',{asset_id:asset,state:'missing'});assert.equal(p.outgoing.length,before+1);
});

/* The AI's contribution has to be visible before the parts page is opened: the
   panel asks the workbench what the AI suspects, shows it, and uses those terms
   to mark the page. It never invents terms of its own. */
const guidance={terms:['液压泵','先导阀','hydraulic pump'],
 components:[{name:'液压泵总成',reason:'E4030 指向先导压力异常',reference_ids:['m1']},
             {name:'先导阀',reason:'手册第286页',reference_ids:['m2']}],
 fault_code:'E4030',has_report:true};

/* Opening the sheet runs every toggle listener; the guidance request is the one
   that returns a promise, so dispatch gives it back. */
function openSheet(p){p.elements['catalog-options'].open=true;return p.elements['catalog-options'].dispatch('toggle');}
/* Answer one guidance request in order: start it, reply synchronously, then let it settle.
   A timeout turns a missing reply into a clear failure instead of a hang. */
async function guidanceRound(p,payload){
 const pending=openSheet(p);
 const request=p.outgoing.at(-1);
 assert.equal(request.data.type,'jilian:ai-guidance-request');
 reply(p,'jilian:ai-guidance',{request_id:request.data.request_id,...payload});
 await Promise.race([pending,new Promise((resolve,reject)=>setTimeout(()=>reject(
   new Error('guidance request was never answered for '+(request.data.request_id||'(no id)'))),3000))]);
}

test('the panel asks the workbench for AI guidance and shows the terms it returns',async()=>{
 const p=setup(assetURL(asset));ready(p);await p.elements.identify.onclick();matched(p);
 p.outgoing.length=0;
 await guidanceRound(p,guidance);
 const request=p.outgoing.at(-1);
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(request.data.type,'jilian:ai-guidance-request');
 assert.match(request.data.request_id,/^guidance-/);
 assert.match(p.elements['ai-guidance-status'].textContent,/E4030/);
 assert.equal(p.elements['ai-guidance-terms'].hidden,false);
 assert.deepEqual(p.elements['ai-guidance-terms'].children.map(node=>node.textContent),
   ['液压泵','先导阀','hydraulic pump']);
 assert.deepEqual(p.elements['ai-guidance-components'].children.map(node=>node.children[0].textContent),
   ['液压泵总成','先导阀']);
});

test('without an AI report the panel says so instead of offering empty marks',async()=>{
 const p=setup(assetURL(asset));ready(p);await p.elements.identify.onclick();matched(p);
 await guidanceRound(p,{terms:[],components:[],fault_code:null,has_report:false});
 assert.match(p.elements['ai-guidance-status'].textContent,/尚无 AI 检索词/);
 assert.equal(p.elements['ai-guidance-terms'].hidden,true);
 assert.equal(p.elements['ai-guidance-components'].hidden,true);
});

test('marking on the XGSS page passes exactly the AI terms and reports what was marked',async()=>{
 const p=setup(assetURL(asset));ready(p);await p.elements.identify.onclick();matched(p);
 p.box.chrome.tabs.query=async()=>[{url:'https://xgss.xcmg.com/catalog',id:11,windowId:1,status:'complete'}];
 await guidanceRound(p,guidance);
 p.scriptCalls.length=0;
 // First injection loads the helper file (no result), second runs the mark call.
 p.scriptResults.push([], [{result:{schema_version:1,marked_rows:2,terms:['液压泵','先导阀'],unmatched:['hydraulic pump'],page_terms:3}}]);
 await p.elements['catalog-open'].onclick();
 const markCall=p.scriptCalls.find(call=>call.func);
 assert.deepEqual(markCall.args[0],['液压泵','先导阀','hydraulic pump'],
   'the page is asked to mark exactly the terms the AI returned');
 assert.match(p.elements['catalog-status'].textContent,/标出 2 行/);
 assert.match(p.elements['catalog-status'].textContent,/本页未出现：hydraulic pump/);
 assert.equal(p.elements['catalog-open'].disabled,false);
});

test('marking tells the engineer where to open the catalog when the tab is not XGSS',async()=>{
 const p=setup('https://manager.trackunit.com/assets/'+asset,undefined);ready(p);
 await p.elements.identify.onclick();matched(p);
 await guidanceRound(p,guidance);
 p.scriptCalls.length=0;
 await p.elements['catalog-open'].onclick();
 assert.equal(p.scriptCalls.length,0,'nothing may be injected into a non-XGSS page');
 assert.match(p.elements['catalog-status'].textContent,/XGSS 图册/);
 assert.match(p.elements['catalog-status'].textContent,/标出 AI 检索条目/);
});

test('late AI guidance cannot survive device, dataset, connection or scope round trips',async()=>{
 for(const change of ['device','dataset','connection','roundtrip']){
  const p=setup(assetURL(asset));ready(p);await p.elements.identify.onclick();matched(p);
  const oldURL=new URL(p.elements.assistant.src),old=openSheet(p),oldRequest=p.outgoing.at(-1).data;
  if(change==='dataset'){
   reply(p,'jilian:context',{asset_id:asset,machine_id:asset,state:'matched',source:'imported_user_supplied',
    dataset_id:'a'.repeat(64),selection_id:'dataset:'+'a'.repeat(64)});
  }else if(change==='connection'){
   p.elements.retry.onclick();ready(p);matched(p);
  }else{
   p.box.chrome.tabs.query=async()=>[tab(otherAsset)];await p.elements.identify.onclick();matched(p,otherAsset);
   if(change==='roundtrip'){
    p.box.chrome.tabs.query=async()=>[tab(asset)];await p.elements.identify.onclick();matched(p);
   }
  }
  const current=openSheet(p),currentRequest=p.outgoing.at(-1).data;
  reply(p,'jilian:ai-guidance',{request_id:currentRequest.request_id,terms:['current-device-part'],components:[],has_report:true});await current;
  reply(p,'jilian:ai-guidance',{request_id:oldRequest.request_id,terms:['old-device-part'],components:[],has_report:true},oldURL);await old;
  assert.deepEqual(p.elements['ai-guidance-terms'].children.map(node=>node.textContent),['current-device-part'],change);
  p.box.chrome.tabs.query=async()=>[{url:'https://xgss.xcmg.com/catalog',id:11,windowId:1,status:'complete'}];
  p.scriptResults.push([], [{result:{marked_rows:1,terms:['current-device-part'],unmatched:[]}}]);
  await p.elements['catalog-open'].onclick();
  assert.deepEqual(p.scriptCalls.find(call=>call.func).args[0],['current-device-part'],change);
 }
});

test('AI guidance waits for a confirmed device instead of reading the previous iframe selection',async()=>{
 const p=setup(assetURL(asset));ready(p);await p.elements.identify.onclick();
 p.outgoing.length=0;await openSheet(p);
 assert.equal(p.outgoing.length,0);
 assert.equal(p.elements['ai-guidance-terms'].hidden,true);
 assert.match(p.elements['ai-guidance-status'].textContent,/确认实测数据/);
 await p.elements['catalog-open'].onclick();assert.equal(p.scriptCalls.length,0);
 matched(p);await guidanceRound(p,guidance);
 assert.deepEqual(p.elements['ai-guidance-terms'].children.map(node=>node.textContent),guidance.terms);
});

test('only the newest concurrent AI guidance response may update the same device',async()=>{
 const p=setup(assetURL(asset));ready(p);await p.elements.identify.onclick();matched(p);
 const old=openSheet(p),oldRequest=p.outgoing.at(-1).data;
 const current=openSheet(p),currentRequest=p.outgoing.at(-1).data;
 reply(p,'jilian:ai-guidance',{request_id:currentRequest.request_id,terms:['latest-part'],components:[],has_report:true});await current;
 reply(p,'jilian:ai-guidance',{request_id:oldRequest.request_id,terms:['outdated-part'],components:[],has_report:true});await old;
 assert.deepEqual(p.elements['ai-guidance-terms'].children.map(node=>node.textContent),['latest-part']);
});

test('cached AI guidance is retired when the device, dataset or connection changes',async()=>{
 for(const change of ['device','dataset','connection']){
  const p=setup(assetURL(asset));ready(p);await p.elements.identify.onclick();matched(p);
  await guidanceRound(p,guidance);
  if(change==='device'){
   p.box.chrome.tabs.query=async()=>[tab(otherAsset)];await p.elements.identify.onclick();matched(p,otherAsset);
  }else if(change==='dataset'){
   reply(p,'jilian:context',{asset_id:asset,machine_id:asset,state:'matched',source:'imported_user_supplied',
    dataset_id:'a'.repeat(64),selection_id:'dataset:'+'a'.repeat(64)});
  }else{
   p.elements.retry.onclick();ready(p);matched(p);
  }
  assert.equal(p.elements['ai-guidance-terms'].hidden,true,change);
  assert.equal(p.elements['ai-guidance-components'].hidden,true,change);
  assert.deepEqual(p.elements['ai-guidance-terms'].children,[],change);
 }
});

test('an old catalog read cannot clear a replacement read or its persistence acknowledgement',async()=>{
 for(const replacementPhase of ['reading','saving'])for(const oldOutcome of ['capture','error']){
  const p=setup(assetURL(asset));ready(p);await p.elements.identify.onclick();matched(p);
  const xgss=async()=>[{url:'https://xgss.xcmg.com/catalog',id:11,windowId:1,status:'complete'}];
  p.box.chrome.tabs.query=xgss;
  let resolveOld,rejectOld;
  p.box.chrome.scripting.executeScript=async options=>options.files?[]:new Promise((done,fail)=>{resolveOld=done;rejectOld=fail;});
  const old=p.elements['capture-catalog'].onclick();await flush();
  p.box.chrome.tabs.query=async()=>[tab(otherAsset)];await p.elements.identify.onclick();matched(p,otherAsset);
  p.box.chrome.tabs.query=xgss;
  const capture=require('../extension/xgss-catalog.js').parse(require('./fixtures/xgss-visible-catalog-test.json'));
  let resolveCurrent;
  p.box.chrome.scripting.executeScript=async options=>options.files?[]:
   replacementPhase==='reading'?new Promise(done=>resolveCurrent=done):[{result:capture}];
  const current=p.elements['capture-catalog'].onclick();await flush();
  const status=p.elements['catalog-status'].textContent;
  if(oldOutcome==='capture')resolveOld([{result:capture}]);else rejectOld(new Error('old browser read failed'));
  await old;
  assert.equal(p.elements['capture-catalog'].disabled,true,replacementPhase);
  assert.equal(p.elements['catalog-status'].textContent,status,replacementPhase);
  if(resolveCurrent)resolveCurrent([{result:capture}]);await current;
  const request=p.outgoing.at(-1).data;
  assert.equal(request.type,'jilian:xgss-catalog-capture');assert.equal(request.asset_id,otherAsset);
  reply(p,'jilian:xgss-catalog-result',{request_id:request.request_id,success:true,message:'Current device capture saved'});
  assert.equal(p.elements['capture-catalog'].disabled,false);
  assert.equal(p.elements['catalog-status'].textContent,'Current device capture saved');
 }
});

test('active research opens in the standalone link without changing or reloading the embedded workbench',async()=>{
 const p=setup(assetURL(asset));ready(p);await p.elements.identify.onclick();matched(p);
 const embedded=p.elements.assistant.src,researchId='1a'.repeat(16);
 reply(p,'jilian:research-active',{asset_id:asset,dataset_id:null,research_id:researchId});
 const link=new URL(p.elements.standalone.href);
 assert.equal(link.searchParams.get('research'),researchId);
 assert.equal(link.searchParams.has('dataset'),false,'fleet-cache links do not invent a dataset');
 assert.equal(link.searchParams.has('panel'),false);assert.equal(link.hash,'#trackunit-asset='+asset);
 assert.equal(p.elements.assistant.src,embedded);
 assert.equal(new URL(p.elements.assistant.src).searchParams.has('research'),false);
 matched(p);await guidanceRound(p,guidance);
 assert.equal(new URL(p.elements.standalone.href).searchParams.get('research'),researchId,
  'same-device acknowledgement and AI guidance refresh must preserve the active record');
 reply(p,'jilian:research-active',{asset_id:asset,dataset_id:null,research_id:null});
 assert.equal(new URL(p.elements.standalone.href).searchParams.has('research'),false);
 assert.equal(p.elements.assistant.src,embedded);
});

test('active research messages require the current trusted frame, connection and matched device scope',async()=>{
 const p=setup(assetURL(asset));ready(p);await p.elements.identify.onclick();
 const researchId='2b'.repeat(16),message={asset_id:asset,dataset_id:null,research_id:researchId};
 reply(p,'jilian:research-active',message);
 assert.equal(new URL(p.elements.standalone.href).searchParams.has('research'),false,'unmatched device');
 matched(p);reply(p,'jilian:research-active',message);
 const original=p.elements.standalone.href,url=new URL(p.elements.assistant.src);
 for(const fields of [
  {asset_id:otherAsset,research_id:null},{dataset_id:'c'.repeat(64),research_id:null},
  {dataset_id:undefined,research_id:null},{connection_id:'obsolete',research_id:null},{protocol:2,research_id:null},
  ...['bad','a'.repeat(31),'a'.repeat(33),'A'.repeat(32),'a'.repeat(32)+'&panel=old',123,{},undefined].map(research_id=>({research_id})),
 ]){
  reply(p,'jilian:research-active',{...message,...fields});
  assert.equal(p.elements.standalone.href,original);
 }
 const envelope={type:'jilian:research-active',protocol:1,connection_id:url.searchParams.get('panel'),...message,research_id:null};
 p.handlers.message({origin:'https://xgss.xcmg.com',source:p.elements.assistant.contentWindow,data:envelope});
 p.handlers.message({origin:url.origin,source:{},data:envelope});
 assert.equal(p.elements.standalone.href,original);
 p.tabHandlers.updated(10,{status:'loading'});
 reply(p,'jilian:research-active',{...message,research_id:null});
 assert.equal(p.elements.standalone.href,original,'unconfirmed navigation cannot mutate the record');
});

test('active research is cleared on device, dataset, context, connection and demo changes',async()=>{
 for(const change of ['device','dataset','context','connection','failed-connection','demo']){
  const p=setup(assetURL(asset));ready(p);await p.elements.identify.onclick();matched(p);
  const oldURL=new URL(p.elements.assistant.src),researchId='3c'.repeat(16);
  reply(p,'jilian:research-active',{asset_id:asset,dataset_id:null,research_id:researchId});
  if(change==='device'){
   p.box.chrome.tabs.query=async()=>[tab(otherAsset)];await p.elements.identify.onclick();matched(p,otherAsset);
  }else if(change==='dataset'){
   reply(p,'jilian:context',{asset_id:asset,machine_id:asset,state:'matched',source:'imported_user_supplied',
    dataset_id:'d'.repeat(64),selection_id:'dataset:'+'d'.repeat(64)});
  }else if(change==='context'){
   reply(p,'jilian:context',{asset_id:asset,state:'missing'});
  }else if(change==='demo'){
   reply(p,'jilian:view',{view:'demo',reason:'user',asset_id:asset});
  }else{
   p.elements.retry.onclick();assert.equal(p.elements.standalone.href,undefined);
   reply(p,'jilian:research-active',{asset_id:asset,dataset_id:null,research_id:researchId});
   if(change==='failed-connection'){p.tick();p.tick();assert.equal(state(p),'failed');}
   else {ready(p);matched(p);}
  }
  reply(p,'jilian:research-active',{asset_id:asset,dataset_id:null,research_id:researchId},oldURL);
  assert.equal(p.elements.standalone.href ? new URL(p.elements.standalone.href).searchParams.has('research') : false,false,change);
  assert.equal(new URL(p.elements.assistant.src||'http://127.0.0.1:8890').searchParams.has('research'),false,change);
 }
});

test('active research matches the selected imported dataset exactly',async()=>{
 const p=setup(assetURL(asset));ready(p);await p.elements.identify.onclick();matched(p);
 const datasetId='a'.repeat(64),researchId='4d'.repeat(16);
 reply(p,'jilian:context',{asset_id:asset,machine_id:asset,state:'matched',source:'imported_user_supplied',
  dataset_id:datasetId,selection_id:'dataset:'+datasetId});
 reply(p,'jilian:research-active',{asset_id:asset,dataset_id:datasetId,research_id:researchId});
 assert.equal(new URL(p.elements.standalone.href).searchParams.get('research'),researchId);
 assert.equal(new URL(p.elements.standalone.href).searchParams.get('dataset'),datasetId);
 assert.equal(new URL(p.elements.assistant.src).searchParams.has('dataset'),false);
 reply(p,'jilian:research-active',{asset_id:asset,dataset_id:null,research_id:null});
 assert.equal(new URL(p.elements.standalone.href).searchParams.get('research'),researchId);
 reply(p,'jilian:research-active',{asset_id:asset,dataset_id:datasetId,research_id:null});
 assert.equal(new URL(p.elements.standalone.href).searchParams.has('research'),false);
 assert.equal(new URL(p.elements.standalone.href).searchParams.has('dataset'),false);
});
