const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');const path=require('node:path');
const asset='00000000-0000-0000-0000-000000000001';
const cloud={provider:'gemini',model:'gemini-flash-latest',backend_build:'build-test'};
function setup(url='https://example.com',savedPort,auto=false){
 const outgoing=[],tabHandlers={},confirmations=[];
 const ids=['assistant','connection','help','context','retry','identify','runtime','standalone','service-form','service-port','workspace','connection-cover','cover-title','cover-detail','connection-detail','start-command','cover-retry','connection-options','open-demo','follow','capture-catalog','catalog-status'];
 const elements=Object.fromEntries(ids.map(id=>[id,{textContent:'',hidden:false,dataset:{},attributes:{},
  setAttribute(key,value){this.attributes[key]=value;},removeAttribute(key){delete this.attributes[key];delete this[key];},
  contentWindow:{postMessage:(data,origin)=>outgoing.push({data,origin})}}]));
 const storage=new Map(savedPort?[['jilian-service-port',savedPort]]:[]);
 const timers=new Map(),handlers={};let counter=0;
 const box={URL,URLSearchParams,Date,document:{getElementById:id=>elements[id]},
  window:{addEventListener:(name,handler)=>handlers[name]=handler,confirm:message=>{confirmations.push(message);return true;}},
  localStorage:{getItem:key=>storage.get(key),setItem:(key,value)=>storage.set(key,value)},
  chrome:{tabs:{query:async()=>[{url,id:10,windowId:1}],onActivated:{addListener:fn=>tabHandlers.activated=fn},onUpdated:{addListener:fn=>tabHandlers.updated=fn}}},
  fetch:()=>{throw new Error('Connection probing must not use fetch');},
  setTimeout:(fn,ms)=>{timers.set(++counter,{fn,ms});return counter;},clearTimeout:id=>timers.delete(id)};
 vm.createContext(box);
 for(const file of ['context.js','xgss-catalog.js','panel.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../extension',file),'utf8'),box);
 // Legacy connection tests isolate startup detection; explicit automatic-follow tests retain it below.
 if(!auto)for(const [id,timer] of timers)if(timer.ms===150)timers.delete(id);
 return {elements,handlers,timers,storage,outgoing,tabHandlers,box,confirmations,
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
 const p=setup();assert.equal(new URL(p.elements.assistant.src).port,'8892');
 assert.equal(state(p),'connecting');assert.equal(p.elements['connection-cover'].hidden,false);
 assert.equal(p.elements.assistant.attributes['aria-hidden'],'true');assert.equal(p.elements.standalone.href,undefined);
 assert.equal(p.timers.values().next().value.ms,6500);
 reply(p,'jilian:runtime',cloud);assert.equal(state(p),'connecting');assert.equal(p.timers.size,1);
 reply(p,'jilian:ready');assert.equal(state(p),'connected');assert.equal(p.timers.size,0);
 assert.equal(p.elements['connection-cover'].hidden,true);assert.equal(p.elements.assistant.attributes['aria-hidden'],'false');
 assert.match(p.elements.runtime.textContent,/实际分析结果/);assert.doesNotMatch(p.elements.connection.textContent,/Gemini.*成功/);
 const link=new URL(p.elements.standalone.href);assert.equal(link.port,'8892');assert.equal(link.searchParams.has('panel'),false);
});

test('DeepSeek runtime is displayed without claiming a successful AI request',()=>{
 const p=setup();reply(p,'jilian:ready');
 reply(p,'jilian:runtime',{provider:'deepseek',model:'deepseek-flash',backend_build:'deepseek-build',
  inference_location:'cloud',investigation_timeout_seconds:120,transient_attempt_limit:3});
 assert.equal(state(p),'connected');assert.match(p.elements.runtime.textContent,/deepseek-flash/);
 assert.match(p.elements.runtime.textContent,/实际分析结果/);assert.doesNotMatch(p.elements.runtime.textContent,/Gemini|认证成功|调用成功/);
});

test('failed default port falls back and partial or stale handshakes cannot combine',()=>{
 const p=setup(),old=new URL(p.elements.assistant.src);reply(p,'jilian:ready');p.tick();
 const current=new URL(p.elements.assistant.src);assert.equal(current.port,'8890');assert.notEqual(current.search,old.search);
 assert.match(p.elements['cover-detail'].textContent,/备用端口 8890/);assert.equal(p.elements['connection-cover'].hidden,false);
 reply(p,'jilian:ready',{},old);reply(p,'jilian:runtime',cloud,old);reply(p,'jilian:runtime',cloud);
 assert.equal(state(p),'connecting');reply(p,'jilian:ready');assert.equal(state(p),'connected');
 assert.match(p.elements['connection-detail'].textContent,/自动连接 8890/);assert.equal(p.storage.size,0);
});

test('both timeouts unload error frame and expose a fresh retry',()=>{
 const p=setup();p.tick();const last=new URL(p.elements.assistant.src);p.tick();
 assert.equal(state(p),'failed');assert.equal(p.elements.assistant.src,undefined);assert.equal(p.elements.help.hidden,false);
 assert.equal(p.elements['cover-retry'].hidden,false);assert.match(p.elements['cover-detail'].textContent,/8892、8890/);
 assert.equal(p.elements['start-command'].textContent,'start_local.cmd --port 8892');
 reply(p,'jilian:ready',{},last);reply(p,'jilian:runtime',cloud,last);assert.equal(state(p),'failed');
 let blocked=false;p.elements.standalone.onclick({preventDefault:()=>blocked=true});assert.equal(blocked,true);
 p.elements['cover-retry'].onclick();assert.equal(state(p),'connecting');assert.equal(p.elements.help.hidden,true);
 assert.equal(new URL(p.elements.assistant.src).port,'8892');assert.notEqual(new URL(p.elements.assistant.src).search,last.search);
});

test('saved allowed port is tried first, fallback never overwrites preference',()=>{
 const p=setup(undefined,'8890');assert.equal(new URL(p.elements.assistant.src).port,'8890');p.tick();
 assert.equal(new URL(p.elements.assistant.src).port,'8892');ready(p);assert.equal(p.storage.get('jilian-service-port'),'8890');
 assert.equal(p.elements['service-port'].value,'8890');
 for(const invalid of ['https://evil.test','8888','8890/path']){
  const invalidPanel=setup(undefined,invalid);assert.equal(new URL(invalidPanel.elements.assistant.src).port,'8892');
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
 assert.equal(state(p),'connecting');reply(p,'jilian:runtime',{provider:'ollama',model:'local-model',backend_build:'old'});
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
 assert.equal(p.outgoing.at(-1).data.asset_id,asset);assert.equal(p.outgoing.at(-1).origin,'http://127.0.0.1:8892');
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
 const oldURL=new URL(p.elements.assistant.src);p.elements['service-port'].value='8890';let prevented=false;
 p.elements['service-form'].onsubmit({preventDefault:()=>prevented=true});assert.equal(prevented,true);
 assert.equal(p.storage.get('jilian-service-port'),'8890');const next=new URL(p.elements.assistant.src);
 assert.equal(next.port,'8890');assert.equal(next.hash,`#trackunit-asset=${asset}`);assert.equal(p.timers.size,1);
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
 assert.match(p.confirmations[0],/保存本机草稿/);
 p.box.window.confirm=()=>true;p.elements['open-demo'].onclick();const demo=new URL(p.elements.assistant.src);
 assert.equal(demo.searchParams.get('demo'),'1');assert.ok(demo.searchParams.get('panel'));assert.equal(demo.hash,'');
 assert.notEqual(demo.searchParams.get('panel'),new URL(before).searchParams.get('panel'));assert.equal(state(p),'connecting');
 reply(p,'jilian:ready',{},new URL(before));reply(p,'jilian:runtime',cloud,new URL(before));assert.equal(state(p),'connecting');
 ready(p);assert.match(p.elements.context.textContent,/模拟案例/);assert.equal(new URL(p.elements.standalone.href).search,'?demo=1');
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
 assert.equal(manifest.version,'0.6.0');assert.deepEqual(manifest.permissions,['sidePanel','activeTab','scripting']);
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
 reply(p,'jilian:context',{asset_id:asset,state:'missing'});assert.match(p.elements.context.textContent,/没有对应的本地实测数据/);
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
 const posted=p.outgoing.at(-1);assert.equal(posted.origin,'http://127.0.0.1:8892');
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
 const capture=require('../extension/xgss-catalog.js').parse(require('./fixtures/xgss-visible-catalog-test.json'));
 resolve([{result:capture}]);await pending;
 assert.match(p.elements['catalog-status'].textContent,/设备或数据版本已切换/);
 assert.equal(p.outgoing.some(item=>item.data.type==='jilian:xgss-catalog-capture'),false);
});
