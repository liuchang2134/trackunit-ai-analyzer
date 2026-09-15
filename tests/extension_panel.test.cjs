const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');const path=require('node:path');
const asset='00000000-0000-0000-0000-000000000001';
const cloud={provider:'gemini',model:'gemini-flash-latest',backend_build:'build-test'};
function setup(url='https://example.com',savedPort){
 const outgoing=[],tabHandlers={},confirmations=[];
 const ids=['assistant','connection','help','context','retry','identify','runtime','standalone','service-form','service-port','workspace','connection-cover','cover-title','cover-detail','connection-detail','start-command','cover-retry','connection-options','open-demo'];
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
 for(const file of ['context.js','panel.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../extension',file),'utf8'),box);
 return {elements,handlers,timers,storage,outgoing,tabHandlers,box,confirmations,
  tick(){const [id,timer]=timers.entries().next().value;timers.delete(id);timer.fn();}};
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

test('reading while disconnected requires new full handshake before sending context request',async()=>{
 const p=setup(`https://manager.trackunit.com/assets/${asset}`),old=new URL(p.elements.assistant.src);reply(p,'jilian:runtime',cloud);
 await p.elements.identify.onclick();assert.notEqual(new URL(p.elements.assistant.src).search,old.search);assert.equal(p.outgoing.length,0);
 reply(p,'jilian:ready');assert.equal(state(p),'connecting');reply(p,'jilian:runtime',cloud);
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

test('page navigation notice survives late device acknowledgement until next explicit read',async()=>{
 const p=setup(`https://manager.trackunit.com/assets/${asset}`);ready(p);await p.elements.identify.onclick();
 p.tabHandlers.activated({windowId:2});assert.doesNotMatch(p.elements.context.textContent,/页面已变化/);
 p.tabHandlers.updated(10,{status:'loading'});assert.match(p.elements.context.textContent,/页面已变化/);
 reply(p,'jilian:context',{asset_id:asset,machine_id:asset,state:'matched',source:'trackunit_cache',dataset_id:null,selection_id:'fleet:'+asset});
 assert.match(p.elements.context.textContent,/页面已变化/);await p.elements.identify.onclick();assert.doesNotMatch(p.elements.context.textContent,/页面已变化/);
});

test('navigation during asynchronous tab lookup cannot commit a stale device',async()=>{
 const p=setup(`https://manager.trackunit.com/assets/${asset}`);let resolve;p.box.chrome.tabs.query=()=>new Promise(done=>resolve=done);
 const before=p.elements.assistant.src,read=p.elements.identify.onclick();p.tabHandlers.activated({windowId:1});
 resolve([{url:`https://manager.trackunit.com/assets/${asset}`,id:10,windowId:1}]);await read;
 assert.equal(p.elements.assistant.src,before);assert.match(p.elements.context.textContent,/读取期间/);assert.equal(p.elements.identify.disabled,false);
});

test('manifest remains restricted to two loopback frames with no extra permissions',()=>{
 const manifest=JSON.parse(fs.readFileSync(path.join(__dirname,'../extension/manifest.json'),'utf8'));
 assert.equal(manifest.version,'0.4.2');assert.deepEqual(manifest.permissions,['sidePanel','activeTab']);assert.equal(manifest.host_permissions,undefined);
 assert.match(manifest.content_security_policy.extension_pages,/frame-src http:\/\/127\.0\.0\.1:8890 http:\/\/127\.0\.0\.1:8892$/);
 assert.equal(manifest.content_security_policy.extension_pages.includes('*'),false);
});
