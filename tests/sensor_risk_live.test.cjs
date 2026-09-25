const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const modulePath=require.resolve('../app/assistant_ui/sensor-risk-live.js');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const asset='00000000-0000-0000-0000-000004760361';
const machine=(overrides={})=>({machine_id:asset,dataset_id:'a'.repeat(64),selection_id:'old',serial_number:'XUGTEST00000001',source_document:'Trackunit sensor snapshot',...overrides});
function harness(){
  const nodes=new Map(),events={},requests=[],refreshes=[],selections=[];
  function node(id){if(!nodes.has(id))nodes.set(id,{id,textContent:'',value:'',children:[],events:{},hidden:false,disabled:false,
    append(...children){this.children.push(...children);},replaceChildren(...children){this.children=children;},
    addEventListener(name,callback){this.events[name]=callback;}});return nodes.get(id);}
  const state={machine:machine()},catalog=[state.machine];
  const sandbox={document:{getElementById:node,createElement:tag=>({...node(Symbol(tag)),tag})},
    window:{addEventListener:(name,fn)=>events[name]=fn},selected:()=>state.machine,machines:catalog,
    api:(url,options)=>new Promise((resolve,reject)=>requests.push({url,options,resolve,reject})),
    refresh:()=>new Promise((resolve,reject)=>refreshes.push({resolve,reject})),
    selectMachine:()=>{selections.push(node('machine').value);state.machine=catalog.find(row=>row.selection_id===node('machine').value);},
    getPlatformEquipmentHint:()=>({value:'10046254'})};
  vm.runInNewContext(fs.readFileSync(modulePath,'utf8'),sandbox);
  const report=()=>({model:'XC948U',source:'Trackunit',observations:[],checks:[],limit:''});
  const change=(next,event='change')=>{state.machine=next;node('risk-status').textContent='CURRENT DEVICE';
    if(event==='change')node('machine').events.change();else if(event)events[event]();};
  return {node,state,catalog,events,requests,refreshes,selections,report,change,
    run:()=>node('risk-snapshot-refresh').onclick()};
}

test('snapshot refresh selects its returned same-machine dataset and loads that snapshot',async()=>{
  const h=harness(),updated=machine({dataset_id:'b'.repeat(64),selection_id:'new'}),task=h.run();
  assert.equal(h.node('risk-snapshot-refresh').disabled,true);
  assert.deepEqual(JSON.parse(h.requests[0].options.body),{equipment_id_hint:'10046254'});
  h.requests[0].resolve({state:'loaded',dataset_id:updated.dataset_id});await tick();
  h.catalog.push(updated);h.refreshes[0].resolve();await tick();
  assert.deepEqual(h.selections,['new']);assert.match(h.requests[1].url,new RegExp('dataset_id='+updated.dataset_id));
  h.requests[1].resolve(h.report());await task;
  assert.equal(h.state.machine.selection_id,'new');assert.equal(h.node('risk-snapshot-refresh').disabled,false);
});

test('snapshot refresh discards a response after another machine, dataset or VIN is selected',async()=>{
  for(const next of [machine({machine_id:'00000000-0000-0000-0000-000004760999',selection_id:'other'}),
    machine({dataset_id:'c'.repeat(64),selection_id:'other-version'}),machine({serial_number:'XUGOTHER00000001'})]){
    const h=harness(),task=h.run();h.change(next,null);
    h.requests[0].resolve({state:'loaded',dataset_id:'b'.repeat(64)});await task;
    assert.equal(h.refreshes.length,0);assert.equal(h.selections.length,0);assert.equal(h.state.machine,next);
    assert.equal(h.node('risk-status').textContent,'CURRENT DEVICE');
  }
});

test('snapshot refresh never reselects its old machine after a switch while the device list is loading',async()=>{
  const h=harness(),task=h.run(),updated=machine({dataset_id:'b'.repeat(64),selection_id:'new'});
  h.requests[0].resolve({state:'loaded',dataset_id:updated.dataset_id});await tick();
  const other=machine({dataset_id:'c'.repeat(64),selection_id:'other-version'});h.change(other);
  h.catalog.push(updated);h.refreshes[0].resolve();await task;
  assert.equal(h.state.machine,other);assert.deepEqual(h.selections,[]);assert.equal(h.requests.length,1);
});

test('refresh may automatically select exactly its returned dataset without losing the snapshot read',async()=>{
  const h=harness(),task=h.run(),updated=machine({dataset_id:'b'.repeat(64),selection_id:'new'});
  h.requests[0].resolve({state:'loaded',dataset_id:updated.dataset_id});await tick();
  h.catalog.push(updated);h.state.machine=updated;h.refreshes[0].resolve();await tick();
  assert.match(h.requests[1].url,new RegExp('dataset_id='+updated.dataset_id));
  h.requests[1].resolve(h.report());await task;assert.equal(h.state.machine,updated);
});

test('explicit navigation away and back invalidates the old snapshot refresh',async()=>{
  const h=harness(),task=h.run(),original=h.state.machine;
  h.change(machine({machine_id:'00000000-0000-0000-0000-000004760999'}),'hashchange');h.change(original,'hashchange');
  h.requests[0].resolve({state:'loaded',dataset_id:'b'.repeat(64)});await task;
  assert.equal(h.refreshes.length,0);assert.equal(h.node('risk-status').textContent,'CURRENT DEVICE');
});

test('old snapshot errors and completion do not alter a newer request or its current status',async()=>{
  const h=harness(),first=h.run();h.change(machine({dataset_id:'c'.repeat(64),selection_id:'current'}));
  const second=h.run();const currentStatus=h.node('risk-status').textContent;
  h.requests[0].reject(new Error('OLD DEVICE FAILURE'));await first;
  assert.equal(h.node('risk-status').textContent,currentStatus);assert.equal(h.node('risk-snapshot-refresh').disabled,true);
  h.requests[1].reject(new Error('CURRENT FAILURE'));await second;
  assert.equal(h.node('risk-status').textContent,'CURRENT FAILURE');assert.equal(h.node('risk-snapshot-refresh').disabled,false);
});

test('a stale device-list refresh error is not shown on the newly selected equipment',async()=>{
  const h=harness(),task=h.run();h.requests[0].resolve({state:'loaded',dataset_id:'b'.repeat(64)});await tick();
  h.change(machine({dataset_id:'c'.repeat(64),selection_id:'other'}));h.refreshes[0].reject(new Error('OLD INDEX FAILURE'));await task;
  assert.equal(h.node('risk-status').textContent,'CURRENT DEVICE');assert.equal(h.selections.length,0);
});

test('the final snapshot read cannot clear the next device when its old response fails',async()=>{
  const h=harness(),task=h.run(),updated=machine({dataset_id:'b'.repeat(64),selection_id:'new'});
  h.requests[0].resolve({state:'loaded',dataset_id:updated.dataset_id});await tick();
  h.catalog.push(updated);h.refreshes[0].resolve();await tick();assert.equal(h.requests.length,2);
  h.change(machine({machine_id:'00000000-0000-0000-0000-000004760999',selection_id:'other'}));
  h.requests[1].reject(new Error('OLD OVERVIEW FAILURE'));await task;
  assert.equal(h.node('risk-status').textContent,'CURRENT DEVICE');assert.equal(h.state.machine.selection_id,'other');
});
