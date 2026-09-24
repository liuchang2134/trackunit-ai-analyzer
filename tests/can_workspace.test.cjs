const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require.resolve('../app/assistant_ui/can-workspace.js'), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));
function harness() {
  const messages=[],requests=[],views=[],listeners={};
  const state={asset:'asset-a',machine:{machine_id:'asset-a',selection_id:'dataset:a',dataset_id:'a',model:'A',serial_number:'VIN-A',source:'imported_user_supplied',provenance:'user_supplied'}};
  const frame={src:'',getAttribute(){return this.src;},contentWindow:{postMessage(data){messages.push(structuredClone(data));}}};
  const window={addEventListener(name,fn){listeners[name]=fn;}};
  vm.runInNewContext(source,{window,document:{getElementById(){return frame;}},location:{origin:'http://127.0.0.1:8890',hash:''},
    PlatformContext:{asset:()=>state.asset},selected:()=>state.machine,getPlatformEquipmentHint:()=>({value:'NUMBER'}),URLSearchParams,
    api:url=>new Promise(resolve=>requests.push({url,resolve})),setView:view=>views.push(view)});
  const message=(type,overrides={})=>listeners.message({origin:'http://127.0.0.1:8890',source:frame.contentWindow,data:{type},...overrides});
  const open=()=>{window.enterCanWorkspace(true);message('jilian:can-ready');};
  return {messages,requests,views,state,window,message,open};
}
test('only its own same-origin frame may request device context',()=>{
  const h=harness();h.window.enterCanWorkspace(true);
  h.message('jilian:can-ready',{origin:'https://example.test'});
  h.message('jilian:can-ready',{source:{}});
  assert.equal(h.requests.length,0);assert.equal(h.messages.length,0);
});
test('previous selected machine is not announced as newly selected Trackunit asset',()=>{
  const h=harness();h.state.asset='asset-b';h.open();
  assert.equal(h.requests.length,0);
  assert.equal(h.messages.at(-1).context.state,'unmatched');
  assert.equal(h.messages.at(-1).context.serial,null);
});
test('late old-device response cannot overwrite current context',async()=>{
  const h=harness();h.open();
  h.state.asset='asset-b';h.state.machine={...h.state.machine,machine_id:'asset-b',selection_id:'dataset:b',dataset_id:'b',serial_number:'VIN-B'};
  h.window.syncCanWorkspace();
  h.requests[1].resolve({machine_id:'asset-b',dataset_id:'b',series:[{recorded_at:'2026-09-21',operating_hours:22,latitude:1,raw_payload:'private'}]});
  await tick();
  h.requests[0].resolve({machine_id:'asset-a',dataset_id:'a',series:[{operating_hours:99}]});await tick();
  const final=h.messages.at(-1).context;
  assert.equal(final.serial,'VIN-B');assert.equal(final.sample.operating_hours,22);
  assert.equal('latitude' in final.sample,false);assert.equal('raw_payload' in final.sample,false);
});
test('hiding the CAN view sends cancellation and returning preserves parent device',()=>{
  const h=harness();h.open();h.window.enterCanWorkspace(false);
  assert.equal(h.messages.at(-1).type,'jilian:can-hidden');
  h.message('jilian:can-open-work');assert.deepEqual(h.views,['work']);assert.equal(h.state.asset,'asset-a');
});
