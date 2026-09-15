const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const PlatformContext=require('../app/assistant_ui/platform-context.js');
const source=fs.readFileSync(require.resolve('../app/assistant_ui/platform-loader.js'),'utf8');
const a='00000000-0000-0000-0000-000000000001',b='00000000-0000-0000-0000-000000000002';
const flush=()=>new Promise(resolve=>setImmediate(resolve));
function setup({busy=false,view='work',rows=[],embedded=false}={}){
  const nodes=new Map(),requests=[],refreshes=[],hints=new Map(),hintRequests=[];
  const get=id=>{if(!nodes.has(id))nodes.set(id,{disabled:false,hidden:false,textContent:'',getAttribute:()=>null});return nodes.get(id);};
  get('run').disabled=busy;
  const context={document:{getElementById:get},PlatformContext,location:{hash:'#trackunit-asset='+a},
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
