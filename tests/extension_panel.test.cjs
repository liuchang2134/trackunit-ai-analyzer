const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');const path=require('node:path');
function setup(url,savedPort){
 const outgoing=[],tabHandlers={};
 const elements=Object.fromEntries(['assistant','connection','help','context','retry','identify','runtime','standalone','service-form','service-port'].map(id=>[id,{textContent:'',hidden:false,contentWindow:{postMessage:(data,origin)=>outgoing.push({data,origin})}}]));
 elements['service-port'].value='8890';
 const storage=new Map(savedPort?[['jilian-service-port',savedPort]]:[]);
 const timers=new Map(),handlers={};let counter=0;
 const box={URL,Date,document:{getElementById:id=>elements[id]},window:{addEventListener:(name,handler)=>handlers[name]=handler},
 localStorage:{getItem:key=>storage.get(key),setItem:(key,value)=>storage.set(key,value)},
 chrome:{tabs:{query:async()=>[{url,id:10,windowId:1}],onActivated:{addListener:fn=>tabHandlers.activated=fn},onUpdated:{addListener:fn=>tabHandlers.updated=fn}}},setTimeout:fn=>{timers.set(++counter,fn);return counter;},clearTimeout:id=>timers.delete(id)};
 vm.createContext(box);
 for(const file of ['context.js','panel.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../extension',file),'utf8'),box);
 return {elements,handlers,timers,storage,outgoing,tabHandlers,box};
}
function send(panel,type,extra={}){
 const url=new URL(panel.elements.assistant.src);
 panel.handlers.message({origin:url.origin,source:panel.elements.assistant.contentWindow,
 data:{type,protocol:1,connection_id:url.searchParams.get('panel'),...extra}});
}
const cloud={provider:'gemini',model:'gemini-flash-latest',backend_build:'build-test',inference_location:'cloud',investigation_timeout_seconds:120,transient_attempt_limit:3};
test('timeout exposes recovery and retry starts a fresh frame',()=>{
 const {elements,timers}=setup('https://example.com');
 [...timers.values()][0]();assert.equal(elements.help.hidden,false);
 elements.retry.onclick();assert.equal(elements.help.hidden,true);assert.match(elements.assistant.src,/^http:\/\/127.0.0.1:8890\/assistant-ui\//);
});
test('only expected iframe origin and source can mark ready',()=>{
 const panel=setup('https://example.com'),{elements,handlers,timers}=panel;
 const initial=elements.connection.textContent;
 const data={type:'jilian:ready',protocol:1,connection_id:new URL(elements.assistant.src).searchParams.get('panel')};
 handlers.message({origin:'https://evil.test',source:elements.assistant.contentWindow,data});
 handlers.message({origin:'http://127.0.0.1:8890',source:{},data});
 assert.equal(elements.connection.textContent,initial);
 send(panel,'jilian:ready');assert.equal(timers.size,1);
 send(panel,'jilian:runtime',cloud);
 assert.equal(timers.size,0);assert.match(elements.connection.textContent,/Gemini 配置已连接/);
 assert.match(elements.runtime.textContent,/实际分析结果/);
});
test('user action forwards only asset ID and invalid pages keep prior selection explicit',async()=>{
 const id='00000000-0000-0000-0000-000000000001';
 const valid=setup(`https://new.manager.trackunit.com/assets/${id}/status?token=secret`);
 const before=new URL(valid.elements.assistant.src);
 await valid.elements.identify.onclick();const after=new URL(valid.elements.assistant.src);
 assert.equal(after.hash,`#trackunit-asset=${id}`);assert.equal(after.search,before.search);
 assert.equal(after.origin,'http://127.0.0.1:8890');assert.equal(after.searchParams.has('token'),false);
 assert.equal(valid.elements.standalone.href,valid.elements.assistant.src);
 const invalid=setup('https://new.manager.trackunit.com/administration');const original=invalid.elements.assistant.src;
 await invalid.elements.identify.onclick();assert.equal(invalid.elements.assistant.src,original);assert.match(invalid.elements.context.textContent,/无法识别/);
});

test('runtime may arrive before initialized data and both are required',()=>{
 const panel=setup('https://example.com');send(panel,'jilian:runtime',cloud);
 assert.equal(panel.timers.size,1);send(panel,'jilian:ready');assert.equal(panel.timers.size,0);
});

test('stale connection replies and old protocol do not mark a new frame ready',()=>{
 const panel=setup('https://example.com');const old=new URL(panel.elements.assistant.src).searchParams.get('panel');
 panel.elements.retry.onclick();assert.notEqual(new URL(panel.elements.assistant.src).searchParams.get('panel'),old);
 send(panel,'jilian:ready',{connection_id:old});send(panel,'jilian:runtime',{...cloud,connection_id:old});
 send(panel,'jilian:ready',{protocol:0});send(panel,'jilian:runtime',{...cloud,protocol:0});
 assert.equal(panel.timers.size,1);[...panel.timers.values()][0]();
 assert.match(panel.elements.connection.textContent,/版本过旧/);assert.equal(panel.elements.help.hidden,false);
});

test('saved port is restricted and iframe, window link and recovery agree',()=>{
 const panel=setup('https://example.com','8892');
 assert.equal(new URL(panel.elements.assistant.src).origin,'http://127.0.0.1:8892');
 assert.equal(panel.elements.assistant.src,panel.elements.standalone.href);
 assert.match(panel.elements.help.textContent,/CMD 运行 start_local\.cmd --port 8892/);
 assert.doesNotMatch(panel.elements.help.textContent,/\.ps1/);
 const invalid=setup('https://example.com','https://evil.test');
 assert.equal(new URL(invalid.elements.assistant.src).origin,'http://127.0.0.1:8890');
 assert.match(invalid.elements.help.textContent,/start_local\.cmd --port 8890/);
});

test('service change retains asset and rejects replies from previous origin',async()=>{
 const id='00000000-0000-0000-0000-000000000001',panel=setup(`https://manager.trackunit.com/assets/${id}`);
 await panel.elements.identify.onclick();const oldURL=new URL(panel.elements.assistant.src);
 panel.elements['service-port'].value='8892';let prevented=false;
 panel.elements['service-form'].onsubmit({preventDefault:()=>prevented=true});
 assert.equal(prevented,true);assert.equal(panel.storage.get('jilian-service-port'),'8892');
 const currentURL=new URL(panel.elements.assistant.src);assert.equal(currentURL.origin,'http://127.0.0.1:8892');
 assert.equal(currentURL.hash,`#trackunit-asset=${id}`);assert.equal(panel.elements.standalone.href,panel.elements.assistant.src);
 panel.handlers.message({origin:oldURL.origin,source:panel.elements.assistant.contentWindow,
 data:{type:'jilian:ready',protocol:1,connection_id:currentURL.searchParams.get('panel')}});
 send(panel,'jilian:runtime',cloud);assert.equal(panel.timers.size,2);
 send(panel,'jilian:ready');assert.equal(panel.timers.size,1);
 send(panel,'jilian:context',{asset_id:id,state:'missing'});assert.equal(panel.timers.size,0);
});

test('legacy local model config is identified without a cloud success claim',()=>{
 const panel=setup('https://example.com');send(panel,'jilian:ready');
 send(panel,'jilian:runtime',{provider:'ollama',model:'local-model',backend_build:'old',inference_location:'local'});
 assert.match(panel.elements.connection.textContent,/未采用新版 Gemini/);
 assert.equal(panel.elements.help.hidden,false);assert.match(panel.elements.runtime.textContent,/ollama/);
});

test('manifest limits the frame to the two loopback services without extra permissions',()=>{
 const manifest=JSON.parse(fs.readFileSync(path.join(__dirname,'../extension/manifest.json'),'utf8'));
 assert.deepEqual(manifest.permissions,['sidePanel','activeTab']);assert.equal(manifest.host_permissions,undefined);
 assert.match(manifest.content_security_policy.extension_pages,/frame-src http:\/\/127\.0\.0\.1:8890 http:\/\/127\.0\.0\.1:8892$/);
 assert.equal(manifest.content_security_policy.extension_pages.includes('*'),false);
});

test('reading an ID waits for exact device acknowledgement, not merely interface readiness',async()=>{
 const id='00000000-0000-0000-0000-000000000001';
 const p=setup(`https://manager.trackunit.com/assets/${id}`);
 await p.elements.identify.onclick();assert.match(p.elements.context.textContent,/等待/);
 assert.equal(p.outgoing.at(-1).data.asset_id,id);assert.equal(p.outgoing.at(-1).origin,'http://127.0.0.1:8890');
 send(p,'jilian:ready');send(p,'jilian:runtime',cloud);assert.match(p.elements.context.textContent,/等待/);
 send(p,'jilian:context',{asset_id:id,state:'pending'});assert.match(p.elements.context.textContent,/尚未切换/);
 send(p,'jilian:context',{asset_id:id,state:'choose_version',available_versions:2});assert.match(p.elements.context.textContent,/版本尚未选定/);
 send(p,'jilian:context',{asset_id:id,machine_id:id,state:'matched',source:'trackunit_cache',dataset_id:null,selection_id:'fleet:'+id});
 assert.match(p.elements.context.textContent,/已关联/);assert.equal(p.timers.size,0);
 const confirmed=p.elements.context.textContent;
 send(p,'jilian:context',{asset_id:'wrong',state:'missing'});assert.equal(p.elements.context.textContent,confirmed);
});

test('page navigation notice survives a late acknowledgement and is cleared only by a new read',async()=>{
 const id='00000000-0000-0000-0000-000000000001';const p=setup(`https://manager.trackunit.com/assets/${id}`);
 await p.elements.identify.onclick();p.tabHandlers.activated({windowId:2});assert.doesNotMatch(p.elements.context.textContent,/浏览器页面已变化/);
 p.tabHandlers.updated(10,{status:'loading'});assert.match(p.elements.context.textContent,/浏览器页面已变化/);
 send(p,'jilian:context',{asset_id:id,machine_id:id,state:'matched',source:'trackunit_cache',dataset_id:null,selection_id:'fleet:'+id});
 assert.match(p.elements.context.textContent,/浏览器页面已变化/);
 await p.elements.identify.onclick();assert.doesNotMatch(p.elements.context.textContent,/浏览器页面已变化/);
});

test('navigation during asynchronous tab lookup does not commit a stale device',async()=>{
 const id='00000000-0000-0000-0000-000000000001';const p=setup(`https://manager.trackunit.com/assets/${id}`);
 let resolve;p.box.chrome.tabs.query=()=>new Promise(done=>resolve=done);
 const before=p.elements.assistant.src,read=p.elements.identify.onclick();
 p.tabHandlers.activated({windowId:1});resolve([{url:`https://manager.trackunit.com/assets/${id}`,id:10,windowId:1}]);await read;
 assert.equal(p.elements.assistant.src,before);assert.match(p.elements.context.textContent,/读取期间/);
});
