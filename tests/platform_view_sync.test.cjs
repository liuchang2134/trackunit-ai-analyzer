const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const PlatformContext=require('../app/assistant_ui/platform-context.js');
const app=fs.readFileSync(require.resolve('../app/assistant_ui/app.js'),'utf8');
const asset='00000000-0000-0000-0000-000000000001';
const origin='chrome-extension://'+'a'.repeat(32);
const handler=app.slice(app.indexOf('function handlePlatformContextRequest('),app.indexOf("window.addEventListener('message',handlePlatformContextRequest)"));
function setup(){
  const calls=[],elements={run:{disabled:false},form:{getAttribute:()=>null},status:{textContent:''}},parent={};
  const context={window:{parent},location:{hash:'#trackunit-asset='+asset,search:'?panel=connection',ancestorOrigins:[origin]},
    URLSearchParams,PlatformContext,platformEquipmentHints:new Map(),pendingPlatformContext:false,$:id=>elements[id],notifyPlatformContext:()=>calls.push('notify'),
    applyPlatformContext:force=>calls.push(force?'work':'passive')};
  vm.runInNewContext(handler,context);
  const event={source:parent,origin,data:{type:'jilian:context-request',protocol:1,connection_id:'connection',asset_id:asset}};
  return {context,calls,elements,event};
}
test('platform asset always wins over demo query on initial load',()=>{
  assert.equal(PlatformContext.initialDemo('?demo=1','#trackunit-asset='+asset),false);
  assert.equal(PlatformContext.initialDemo('?demo=1','#trackunit-asset=invalid'),false);
  assert.equal(PlatformContext.initialDemo('?demo=1',''),true);
  assert.equal(PlatformContext.initialDemo('?panel=one',''),false);
});
test('passive acknowledgement preserves view while explicit same-asset resume opens work',()=>{
  const h=setup();h.context.handlePlatformContextRequest(h.event);assert.deepEqual(h.calls,['notify']);
  h.calls.length=0;h.event.data.show_work=true;h.context.handlePlatformContextRequest(h.event);assert.deepEqual(h.calls,['work','notify']);
});
test('explicit resume during analysis queues a platform update without changing form or view',()=>{
  const h=setup();h.elements.run.disabled=true;h.event.data.show_work=true;
  h.context.handlePlatformContextRequest(h.event);assert.deepEqual(h.calls,['notify']);
  assert.equal(h.context.pendingPlatformContext,true);assert.match(h.elements.status.textContent,/完成后/);
});
test('wrong iframe sender, origin, connection or asset cannot exit demo',()=>{
  for(const change of [{source:{}},{origin:'https://manager.trackunit.com'},
    {data:{connection_id:'old'}},{data:{asset_id:'other'}},{data:{protocol:2}}]){
    const h=setup(),event={...h.event,...change,data:{...h.event.data,show_work:true,...change.data}};
    h.context.handlePlatformContextRequest(event);assert.deepEqual(h.calls,[]);
  }
});
test('view notifications carry only mode and asset identity, with distinct user/platform reasons',()=>{
  const source=app.slice(app.indexOf('function notifyPanelView('),app.indexOf("document.addEventListener('DOMContentLoaded'"));
  const messages=[],parent={postMessage:(data,target)=>messages.push({data,target})};
  const context={window:{parent},document:{readyState:'complete'},URLSearchParams,PlatformContext,activeView:'demo',
    location:{search:'?panel=connection',hash:'#trackunit-asset='+asset,ancestorOrigins:[origin]}};
  vm.runInNewContext(source,context);context.notifyPanelView('user');
  assert.equal(messages[0].data.view,'demo');assert.equal(messages[0].data.reason,'user');assert.equal(messages[0].target,origin);
  context.activeView='work';context.notifyPanelView('platform');assert.equal(messages[1].data.reason,'platform');
  assert.deepEqual(Object.keys(messages[0].data).sort(),['asset_id','connection_id','protocol','reason','type','view']);
  context.document.readyState='loading';context.notifyPanelView('initial');assert.equal(messages.length,2);
  context.document.readyState='complete';context.location.ancestorOrigins=['https://foreign.example'];context.notifyPanelView('user');assert.equal(messages.length,2);
});


test('lookup hints are bounded plain equipment labels and are kept only for the matching asset',()=>{
  const h=setup();h.event.data.equipment_id_hint=' 10046254 ';h.context.handlePlatformContextRequest(h.event);
  assert.equal(h.context.platformEquipmentHints.get(asset).value,'10046254');
  assert.equal(h.context.platformEquipmentHints.get(asset).confirmed,true);
  for(const value of ['https://example.com/?secret=1','abc?key=one','abc/def','<script>','a'.repeat(101),42]){
    const bad=setup();bad.event.data.equipment_id_hint=value;bad.context.handlePlatformContextRequest(bad.event);
    assert.equal(bad.context.platformEquipmentHints.size,0);assert.deepEqual(bad.calls,[]);
  }
  const wrong=setup();wrong.event.data.asset_id='other';wrong.event.data.equipment_id_hint='10046254';
  wrong.context.handlePlatformContextRequest(wrong.event);assert.equal(wrong.context.platformEquipmentHints.size,0);
  const absent=setup();absent.context.handlePlatformContextRequest(absent.event);
  assert.equal(absent.context.platformEquipmentHints.get(asset).value,null);
  assert.equal(PlatformContext.equipmentHint('Machine A-01._'),'Machine A-01._');
});
