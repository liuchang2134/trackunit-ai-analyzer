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

const markup=fs.readFileSync(require.resolve('../app/assistant_ui/index.html'),'utf8');
function navigationSetup({competitionFocus=false,mode=null}={}){
  const elements=new Map(),messages=[],calls=[],parent={postMessage:data=>messages.push(data)};
  const classes=new Set(competitionFocus?['competition-focus']:[]);
  const node=()=>({hidden:false,textContent:'',attributes:{},setAttribute(name,value){this.attributes[name]=value;}});
  const get=id=>{if(!elements.has(id))elements.set(id,node());return elements.get(id);};
  const navMarkup=markup.match(/<nav aria-label="工作区">([\s\S]*?)<\/nav>/)[1];
  const buttons=[...markup.matchAll(/<button\b([^>]*data-view="([^"]+)"[^>]*)>([^<]+)<\/button>/g)].map(match=>{
    const button=node();button.dataset={view:match[2]};button.label=match[3];
    button.inNavigation=navMarkup.includes(match[0]);button.closest=selector=>selector==='nav'&&button.inNavigation?{}:null;
    return button;
  });
  const context={activeView:'work',$:get,location:{hash:'#trackunit-asset='+asset,search:'?panel=connection',ancestorOrigins:[origin]},
    window:{parent,scrollTo(){},JilianDataMode:{mode},renderRiskDemo:()=>calls.push('risk-demo')},document:{readyState:'complete',getElementById:get,
      documentElement:{classList:{contains:name=>classes.has(name)}},
      querySelector:()=>get('device'),querySelectorAll:()=>buttons},
    URLSearchParams,PlatformContext,updateDemoDisclosure(){},updateRuntimeLabel(){},updateSourceLabel(){},
    updateFlowTrack(){},refreshHistory:()=>calls.push('history'),enterDemoReplay:()=>calls.push('replay'),
    enterWorklist:()=>calls.push('queue'),enterCoolingView:()=>calls.push('cooling'),
    enterCanWorkspace:visible=>calls.push(visible?'can-open':'can-hidden'),requestAnimationFrame:callback=>callback()};
  const views=app.slice(app.indexOf('function setView('),app.indexOf('function clearReport('));
  const notifications=app.slice(app.indexOf('function notifyPanelView('),app.indexOf("document.addEventListener('DOMContentLoaded'"));
  vm.runInNewContext(notifications+'\n'+views,context);
  return {context,get,buttons,messages,calls,classes};
}

test('full mode retains service, risk, CAN, and history workspaces with replay inside history',()=>{
  const h=navigationSetup();
  assert.deepEqual(h.buttons.filter(button=>button.inNavigation).map(button=>button.dataset.view),['work','risk','can','history']);
  const history=markup.slice(markup.indexOf('<div id="history-view"'),markup.indexOf('</main>'));
  const replay=markup.slice(markup.indexOf('<div id="demo-view"'),markup.indexOf('<div id="can-view"'));
  assert.match(history,/<button[^>]*data-view="demo"[^>]*>历史分析回放<\/button>/);
  assert.match(replay,/<button[^>]*data-view="history"[^>]*>返回诊断记录<\/button>/);
  assert.match(markup,/<aside id="demo-entry" hidden><\/aside>/);
});

test('history replay round trip keeps history selected and preserves plugin demo mode',()=>{
  const h=navigationSetup(),pressed=()=>h.buttons.filter(button=>button.inNavigation&&button.attributes['aria-pressed']==='true').map(button=>button.dataset.view);
  h.buttons.find(button=>button.inNavigation&&button.dataset.view==='history').onclick();
  assert.equal(h.get('history-view').hidden,false);assert.deepEqual(pressed(),['history']);
  h.buttons.find(button=>button.label==='历史分析回放').onclick();
  assert.equal(h.context.activeView,'demo');assert.equal(h.get('demo-view').hidden,false);
  assert.equal(h.get('history-view').hidden,true);assert.equal(h.get('flow-track').hidden,true);
  assert.equal(h.get('page-title').textContent,'历史分析回放');assert.deepEqual(pressed(),['history']);
  assert.equal(h.messages.at(-1).view,'demo');assert.equal(h.messages.at(-1).reason,'user');
  assert.equal(h.calls.filter(call=>call==='replay').length,1);
  h.buttons.find(button=>button.label==='返回诊断记录').onclick();
  assert.equal(h.context.activeView,'history');assert.equal(h.get('demo-view').hidden,true);
  assert.equal(h.get('history-view').hidden,false);assert.deepEqual(pressed(),['history']);
  assert.equal(h.messages.at(-1).view,'work');assert.equal(h.calls.filter(call=>call==='history').length,2);
});

test('plugin replay entry and CAN switching retain their modes without restoring the old home card',()=>{
  const h=navigationSetup();
  h.context.setView('demo');
  assert.equal(h.messages.at(-1).view,'demo');assert.equal(h.messages.at(-1).reason,'initial');
  assert.equal(h.buttons.find(button=>button.inNavigation&&button.dataset.view==='history').attributes['aria-pressed'],'true');
  h.buttons.find(button=>button.inNavigation&&button.dataset.view==='can').onclick();
  assert.equal(h.get('can-view').hidden,false);assert.equal(h.get('demo-view').hidden,true);
  assert.equal(h.buttons.find(button=>button.inNavigation&&button.dataset.view==='can').attributes['aria-pressed'],'true');
  assert.equal(h.calls.at(-1),'can-open');assert.equal(h.get('demo-entry').hidden,true);
  h.context.location.hash='';h.buttons.find(button=>button.inNavigation&&button.dataset.view==='work').onclick();
  assert.equal(h.get('work-view').hidden,false);assert.equal(h.get('flow-track').hidden,false);
  assert.equal(h.get('demo-entry').hidden,true);assert.equal(h.calls.at(-1),'can-hidden');
});

test('competition mode redirects every deferred view before loading it or notifying the plugin',()=>{
  for(const view of ['can','history','demo','queue','data','states','cooling']){
    for(const reason of ['initial','user','platform']){
      const h=navigationSetup({competitionFocus:true});
      h.context.setView(view,{reason});
      assert.equal(h.context.activeView,'work',`${view} / ${reason}`);
      assert.equal(h.get('work-view').hidden,false);
      assert.equal(h.get('device').hidden,false);
      assert.equal(h.get('flow-track').hidden,false);
      assert.equal(h.get('page-title').textContent,'AI 设备服务');
      for(const deferred of ['can','history','demo','queue','data','states','cooling']){
        assert.equal(h.get(deferred+'-view').hidden,true,deferred);
      }
      assert.deepEqual(h.calls,['can-hidden'],'a deferred workspace must not start loading');
      assert.equal(h.messages.length,1);
      assert.equal(h.messages[0].view,'work');
      assert.equal(h.messages[0].reason,reason);
      assert.equal(h.messages[0].asset_id,asset);
      assert.deepEqual(h.buttons.filter(button=>button.inNavigation&&button.attributes['aria-pressed']==='true').map(button=>button.dataset.view),['work']);
    }
  }
});

test('risk view shows the selected device in live mode and keeps the independent synthetic device separate in demo mode',()=>{
  const live=navigationSetup({competitionFocus:true,mode:'live'});live.context.setView('risk');
  assert.equal(live.get('risk-view').hidden,false);assert.equal(live.get('device').hidden,false);
  const demo=navigationSetup({competitionFocus:true,mode:'demo'});demo.context.setView('risk');
  assert.equal(demo.get('risk-view').hidden,false);assert.equal(demo.get('device').hidden,true);
  assert.equal(demo.calls.includes('risk-demo'),true);
});

test('retained navigation handlers obey the display switch and remain usable when it is removed',()=>{
  const h=navigationSetup({competitionFocus:true});
  for(const button of h.buttons.filter(button=>['can','history','demo'].includes(button.dataset.view))){
    button.onclick();
    assert.equal(h.context.activeView,'work',button.label);
    assert.equal(h.messages.at(-1).view,'work');
    assert.equal(h.messages.at(-1).reason,'user');
  }
  assert.ok(h.calls.every(call=>call==='can-hidden'));
  h.classes.delete('competition-focus');
  h.buttons.find(button=>button.label==='历史分析回放').onclick();
  assert.equal(h.context.activeView,'demo');
  assert.equal(h.get('demo-view').hidden,false);
  assert.equal(h.messages.at(-1).view,'demo');
  assert.equal(h.calls.at(-1),'replay');
});
