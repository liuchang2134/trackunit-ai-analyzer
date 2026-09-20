const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const PlatformContext=require('../app/assistant_ui/platform-context.js');
const source=fs.readFileSync(require.resolve('../app/assistant_ui/platform-loader.js'),'utf8');
const a='00000000-0000-0000-0000-000000000001',b='00000000-0000-0000-0000-000000000002';
const flush=()=>new Promise(resolve=>setImmediate(resolve));
function setup({busy=false,view='work',rows=[],embedded=false}={}){
  const nodes=new Map(),requests=[],refreshes=[],hints=new Map(),hintRequests=[];
  const get=id=>{if(!nodes.has(id))nodes.set(id,{disabled:false,hidden:false,textContent:'',onclick:null,getAttribute:()=>null});return nodes.get(id);};
  get('run').disabled=busy;
  const host={children:[],append(child){this.children.push(child);}};
  const context={document:{getElementById:get,querySelector:()=>host,createElement:()=>({id:'',className:'',type:'',textContent:'',onclick:null,append(){},setAttribute(){}})},PlatformContext,location:{hash:'#trackunit-asset='+a},
    activeView:view,platformIndexState:'ready',machines:rows,defaultSource:'trackunit_cache',
    parent:embedded?{}:undefined,getPlatformEquipmentHint:id=>hints.get(id)||{confirmed:false,value:null},
    notifyAssistantPanel:(type,fields)=>hintRequests.push({type,fields}),addEventListener:()=>{},api:(path,options)=>new Promise((resolve,reject)=>requests.push({path,options,resolve,reject})),
    refresh:async()=>{refreshes.push(context.location.hash);},Date,URLSearchParams};
  vm.runInNewContext(source,context);return {context,requests,refreshes,get,hints,hintRequests};
}
test('unseen platform asset is read once, failure stays visible and does not poll',async()=>{
  const h=setup();assert.equal(h.requests.length,1);assert.equal(h.requests[0].path,'/assistant/platform-asset/'+a+'/load');
  h.requests[0].resolve({asset_id:a,state:'unavailable',status:'upstream_unauthorized',message:'Trackunit 拒绝访问'});await flush();
  h.context.platformLoaderChanged();h.context.platformLoaderChanged();assert.equal(h.requests.length,1);
  assert.match(h.get('platform-load-status').textContent,/拒绝访问/);assert.equal(h.get('platform-load-retry').hidden,false);
  assert.equal(h.refreshes.length,0);
});
test('metadata-only result displays identity without creating selectable or simulated data',async()=>{
  const h=setup();h.requests[0].resolve({asset_id:a,state:'unavailable',status:'metadata_only',message:'仅有设备信息',
    machine:{model:'XC918PRO',serial_number:'TEST-IDENTITY'}});await flush();
  assert.match(h.get('platform-load-identity').textContent,/XC918PRO.*TEST-IDENTITY.*暂无运行样本.*故障记录未读取/);
  assert.equal(h.context.machines.length,0);assert.equal(h.refreshes.length,0);
});
test('loaded asset refreshes index once; late other-asset reply cannot select or refresh current machine',async()=>{
  const h=setup();h.context.location.hash='#trackunit-asset='+b;h.context.platformLoaderChanged();assert.equal(h.requests.length,2);
  h.requests[0].resolve({asset_id:a,state:'loaded',dataset_id:'a'.repeat(64)});await flush();assert.equal(h.refreshes.length,0);
  h.requests[1].resolve({asset_id:b,state:'loaded',dataset_id:'b'.repeat(64)});await flush();
  assert.deepEqual(h.refreshes,['#trackunit-asset='+b]);h.context.platformLoaderChanged();assert.equal(h.refreshes.length,1);
});
test('existing data, intentional demo and busy analysis do not start a platform read',()=>{
  assert.equal(setup({rows:[{machine_id:a,selection_id:'fleet:'+a}]}).requests.length,0);
  assert.equal(setup({view:'demo'}).requests.length,0);
  const h=setup({busy:true});assert.equal(h.requests.length,0);h.get('run').disabled=false;h.context.platformLoaderChanged();assert.equal(h.requests.length,1);
});
test('response with a different asset becomes an error and cannot refresh the current index',async()=>{
  const h=setup();h.requests[0].resolve({asset_id:b,state:'loaded',dataset_id:'b'.repeat(64)});await flush();
  assert.equal(h.refreshes.length,0);assert.match(h.get('platform-load-status').textContent,/不一致/);
});

test('a device that already has local data does not wait for the panel handshake',()=>{
  // The reported symptom: a real machine with imported data looked unassociated
  // because the loader demanded the panel's equipment-number confirmation even
  // though no remote read was needed. Nothing may be requested, and the panel
  // must hand over to the normal device area instead of staying on a status line.
  const h=setup({embedded:true,rows:[{machine_id:a,selection_id:'fleet:'+a}]});
  assert.equal(h.context.getPlatformEquipmentHint(a).confirmed,false);
  assert.equal(h.requests.length,0);
  assert.equal(h.hintRequests.length,0);
  assert.equal(h.get('platform-load').hidden,true);
  assert.doesNotMatch(h.get('platform-load-status').textContent,/正在识别当前设备/);
});

test('switching between two real devices never demands a hint per asset',()=>{
  const h=setup({embedded:true,rows:[{machine_id:a,selection_id:'fleet:'+a},{machine_id:b,selection_id:'fleet:'+b}]});
  h.hints.set(a,{confirmed:true,value:'10046254'});h.context.platformLoaderChanged();
  assert.equal(h.requests.length,0);
  // Confirming one asset must not be reused for another, and the unconfirmed
  // asset that already has local data must still be presented as loaded.
  assert.equal(h.context.getPlatformEquipmentHint(b).confirmed,false);
  h.context.location.hash='#trackunit-asset='+b;h.context.platformLoaderChanged();
  assert.equal(h.requests.length,0);
  assert.equal(h.hintRequests.length,0);
  assert.equal(h.get('platform-load').hidden,true);
  assert.doesNotMatch(h.get('platform-load-status').textContent,/正在识别当前设备/);
});

test('an inconclusive fleet search is not dressed up as a retryable failure',async()=>{
  // The account can only read devices through a paged AEMP search. When that
  // search stops at its page cap the device is simply not covered yet: showing
  // "请稍后重试" there promises something a retry cannot deliver.
  const h=setup();
  h.requests[0].resolve({asset_id:a,state:'unavailable',status:'search_incomplete',search_complete:false,
    message:'已查询前 3 页设备快照（该账户车队共 11 页），未找到当前设备。本次未覆盖整个车队，未关联其他设备；重复读取会得到同样的结果。',
    searched_pages:3,pages_total:11,retry_after_seconds:300});
  await flush();
  const status=h.get('platform-load-status').textContent;
  assert.match(status,/共 11 页/);
  assert.doesNotMatch(status,/请稍后重试/, 'an incomplete search must not promise a retry');
  assert.equal(h.get('platform-load-retry').hidden,true, 'no retry button for a search that cannot change');
});

test('a conclusive search keeps the retry path for genuinely temporary failures',async()=>{
  const h=setup();
  h.requests[0].resolve({asset_id:a,state:'unavailable',status:'upstream_unauthorized',search_complete:true,
    message:'AEMP 设备快照暂不可读取；未关联其他设备，故障数据未读取。',retry_after_seconds:120});
  await flush();
  assert.match(h.get('platform-load-status').textContent,/请稍后重试/);
  assert.equal(h.get('platform-load-retry').hidden,false);
});

test('an unanswered hint request is not repeated on its own, but never becomes a dead end',()=>{
  // The panel discards a hint request when it is not connected yet. The page
  // remembers that it asked, so it does not spam the panel — and an unanswered
  // request must never be treated as a confirmed one, which would start a read
  // with no hint at all and silently keep the device unassociated.
  const h=setup({embedded:true});
  assert.equal(h.hintRequests.length,1);
  h.context.platformLoaderChanged();
  assert.equal(h.hintRequests.length,1,'an unanswered request is not repeated on its own');
  assert.equal(h.requests.length,0,'no read may start before the panel answers');
  // The hint button stays reachable so the user can ask again; the ownership of
  // that recovery is asserted here rather than through the DOM stub.
  assert.equal(h.get('platform-load-status').textContent,'正在识别当前设备…');
  // Once the panel does answer, the read carries the hint it supplied.
  h.hints.set(a,{confirmed:true,value:'10046254'});h.context.platformLoaderChanged();
  assert.equal(h.requests.length,1);
  assert.deepEqual(JSON.parse(h.requests[0].options.body),{equipment_id_hint:'10046254'});
});


test('embedded view waits for the parent hint handshake and explicitly requests it once per asset',()=>{
  const h=setup({embedded:true});assert.equal(h.requests.length,0);
  assert.equal(h.hintRequests.length,1);assert.equal(h.hintRequests[0].type,'jilian:asset-hint-request');
  assert.equal(h.hintRequests[0].fields.asset_id,a);
  h.context.platformLoaderChanged();assert.equal(h.hintRequests.length,1);
  h.hints.set(a,{confirmed:true,value:'10046254'});h.context.platformLoaderChanged();
  assert.equal(h.requests.length,1);assert.deepEqual(JSON.parse(h.requests[0].options.body),{equipment_id_hint:'10046254'});
});

test('late new hint waits for the no-hint request then adds only one bounded follow-up',async()=>{
  const h=setup({embedded:true});h.hints.set(a,{confirmed:true,value:null});h.context.platformLoaderChanged();
  assert.equal(h.requests.length,1);assert.equal(h.requests[0].options.body,undefined);
  h.hints.set(a,{confirmed:true,value:'10046254'});h.context.platformLoaderChanged();assert.equal(h.requests.length,1);
  h.requests[0].resolve({asset_id:a,state:'unavailable',status:'limited_search',retry_after_seconds:60,message:'范围内未找到'});await flush();
  assert.equal(h.requests.length,2);assert.equal(JSON.parse(h.requests[1].options.body).equipment_id_hint,'10046254');
  h.hints.set(a,{confirmed:true,value:'10046255'});h.context.platformLoaderChanged();assert.equal(h.requests.length,2);
  h.requests[1].resolve({asset_id:a,state:'unavailable',status:'metadata_only',message:'只有资料'});await flush();
  h.context.platformLoaderChanged();assert.equal(h.requests.length,2);assert.match(h.get('platform-load-status').textContent,/只有资料/);
});

test('successful load ignores later changed hints and a new asset never inherits a prior hint',async()=>{
  const h=setup({embedded:true});h.hints.set(a,{confirmed:true,value:'10046254'});h.context.platformLoaderChanged();
  h.requests[0].resolve({asset_id:a,state:'loaded',dataset_id:'a'.repeat(64)});await flush();
  h.hints.set(a,{confirmed:true,value:'changed'});h.context.platformLoaderChanged();assert.equal(h.requests.length,1);
  h.context.location.hash='#trackunit-asset='+b;h.context.platformLoaderChanged();assert.equal(h.requests.length,1);
  assert.equal(h.hintRequests.at(-1).fields.asset_id,b);
  h.hints.set(b,{confirmed:true,value:null});h.context.platformLoaderChanged();assert.equal(h.requests.length,2);
  assert.equal(h.requests[1].options.body,undefined);assert.equal(h.requests[1].path,'/assistant/platform-asset/'+b+'/load');
});
