const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const app=fs.readFileSync(require.resolve('../app/assistant_ui/app.js'),'utf8');
const source=app.slice(app.indexOf('function renderDeviceVitals('),app.indexOf('function selectMachine('));
function render(compact){
  const node=()=>({children:[],dataset:{},hidden:false,append(...items){this.children.push(...items);},replaceChildren(...items){this.children=items;}});
  const elements=Object.fromEntries(['device-vitals','device-facts','machine','refresh'].map(id=>[id,node()]));
  const maintenance=node(),details=node();
  const context={document:{documentElement:{classList:{contains:()=>compact}},createElement:node,querySelector:selector=>selector==='.device-maintenance'?maintenance:details},
    $:id=>elements[id],displayDate:v=>v,displayMachineModel:v=>v,machineSampleTime:()=> '2026-09-22 10:00',machineSourceLabel:()=> 'Trackunit 缓存'};
  vm.createContext(context);vm.runInContext(source,context);
  context.renderDeviceFacts({model:'XC948U',serial_number:'TEST-VIN',machine_id:'asset',dataset_id:'a'.repeat(64),sample_count:3,source_document:'资料来源'});
  return {elements,maintenance,details};
}
const entries=root=>root.children.map(cell=>cell.children.map(n=>n.textContent));
test('compact device card retains identity and moves sampling facts and existing maintenance controls into one disclosure',()=>{
  const h=render(true);
  assert.deepEqual(entries(h.elements['device-vitals']),[['机型','XC948U'],['VIN / PIN','TEST-VIN']]);
  for(const label of ['最近采样','数据来源','数据记录','数据版本','来源说明'])assert.ok(entries(h.elements['device-facts']).some(([name])=>name===label));
  assert.equal(h.maintenance.hidden,true);
  assert.equal(h.details.children[0],h.elements.machine,'keep the original select and its event handlers');
  assert.equal(h.details.children[1],h.elements.refresh);
});
test('ordinary device presentation keeps its original visible facts and separate maintenance controls',()=>{
  const h=render(false);
  assert.equal(entries(h.elements['device-vitals']).length,5);
  assert.equal(h.maintenance.hidden,false);assert.equal(h.details.children.length,0);
});
