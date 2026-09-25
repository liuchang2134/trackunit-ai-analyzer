const test = require('node:test');
const assert = require('node:assert/strict');
const api = require('../app/assistant_ui/part-estimates.js');

const context = {researchId:'research-one',machineId:'machine-one',vin:'VIN-ONE',datasetId:'dataset-one',scope:'historical'};
const parts = [{name:'线缆',part_number:'860513679',capture_id:'capture-one',figure_ref:'2'},
  {name:'控制单元',part_number:'860513680',capture_id:'capture-one',figure_ref:'4'}];
const stamp = '2026-09-24T12:00:00Z';
const quote = (currency='USD', unitPrice='12.34', quantity='1') =>
  api.quoteFromInput({unitPrice,quantity,source:'供应商邮件'},currency,stamp).quote;

test('quantity rejects fractional, nonfinite and out-of-range input',()=>{
  for(const value of [NaN,Infinity,-1,0,1.5,10000,'1e2','1.0','',null,true]) assert.equal(api.parseQuantity(value).ok,false,String(value));
  assert.deepEqual(api.parseQuantity('9999'),{ok:true,value:9999});
});
test('money uses exact two-decimal minor units and rejects invalid prices',()=>{
  for(const value of [NaN,Infinity,-1,'-0.01','1.234','1e2','','.5','9999999999',true]) assert.equal(api.parseUnitPrice(value).ok,false,String(value));
  assert.deepEqual(api.parseUnitPrice('0.10'),{ok:true,minor:10});
  assert.deepEqual(api.parseUnitPrice('12.3'),{ok:true,minor:1230});
  assert.deepEqual(api.parseUnitPrice('0'),{ok:true,minor:0});
});
test('a user-entered zero quote is distinct from an unquoted item',()=>{
  assert.equal(api.summarize([null], 'USD').totalMinor,null);
  assert.deepEqual(api.summarize([quote('USD','0')], 'USD'),
    {currency:'USD',quotedCount:1,pendingCount:0,totalMinor:'0',state:'all'});
});
test('partial totals never silently count a missing or foreign-currency quote as priced',()=>{
  const result=api.summarize([quote('USD','0.10','3'),quote('EUR','999'),null], 'USD');
  assert.equal(result.totalMinor,'30');assert.equal(result.quotedCount,1);assert.equal(result.pendingCount,2);
  assert.equal(result.state,'partial');assert.equal(api.formatMinor(result.totalMinor,'USD'),'USD 0.30');
});
test('large totals remain exact beyond Number.MAX_SAFE_INTEGER',()=>{
  const values=Array.from({length:50},()=>quote('USD','999999999.99','9999'));
  const result=api.summarize(values,'USD');
  assert.equal(result.totalMinor,(99999999999n*9999n*50n).toString());
  assert.match(api.formatMinor(result.totalMinor,'USD'),/^USD [\d,]+\.50$/);
});
test('storage namespace isolates machine, research, dataset, scope, VIN, part, capture and currency',()=>{
  const base=api.storageKey(context,parts[0],'USD');
  for(const key of ['machineId','researchId','datasetId','scope','vin'])
    assert.notEqual(api.storageKey({...context,[key]:'different'},parts[0],'USD'),base,key);
  assert.notEqual(api.storageKey(context,{...parts[0],part_number:'another'},'USD'),base);
  assert.notEqual(api.storageKey(context,{...parts[0],capture_id:'another'},'USD'),base);
  assert.notEqual(api.storageKey(context,parts[0],'EUR'),base);
  assert.equal(api.storageKey({...context,researchId:''},parts[0],'USD'),null);
  assert.equal(api.storageKey(context,parts[0],'BTC'),null);
});
test('malformed stored data cannot become a quote and provenance cannot masquerade as XGSS',()=>{
  const good=quote();
  for(const patch of [{origin:'xgss'},{currency:'EUR'},{unitMinor:Infinity},{unitMinor:-1},{quantity:1.5},
    {quantity:'2'},{source:''},{source:'x'.repeat(161)},{updatedAt:'yesterday'},{version:2}])
    assert.equal(api.normalizeQuote({...good,...patch},'USD'),null);
  assert.equal(api.quoteFromInput({quantity:'1',unitPrice:'10',source:''},'USD',stamp).ok,false);
  assert.equal(api.normalizeQuote(good,'USD').origin,'user');
});
test('only identified source parts render and duplicate capture rows do not double count',()=>{
  const normalized=api.normalizeParts([...parts,parts[0],{name:'没有料号'}, {...parts[0],capture_id:'another'}]);
  assert.equal(normalized.length,3);assert.equal(normalized[0].part_number,parts[0].part_number);
});

class Node {
  constructor(tag,doc){this.tagName=tag;this.ownerDocument=doc;this.children=[];this.attributes={};this.listeners=new Map();this.value='';this._text='';this.hidden=false;}
  set textContent(value){this._text=String(value);this.children=[];}
  get textContent(){return this._text+this.children.map(child=>child.textContent).join('');}
  set innerHTML(value){throw new Error('Unsafe HTML write');}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this._text='';this.children=children;}
  setAttribute(key,value){this.attributes[key]=String(value);}
  addEventListener(type,handler){if(!this.listeners.has(type))this.listeners.set(type,new Set());this.listeners.get(type).add(handler);}
  removeEventListener(type,handler){this.listeners.get(type)?.delete(handler);}
  fire(type){for(const callback of [...(this.listeners.get(type)||[])])callback({target:this});}
}
function all(node){return [node,...node.children.flatMap(all)];}
function find(node,predicate){const item=all(node).find(predicate);assert.ok(item,'Expected DOM node');return item;}
function memoryStorage(){const values=new Map();return {values,getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,String(value)),removeItem:key=>values.delete(key)};}
function dom(storage=memoryStorage()){
  const doc={defaultView:{localStorage:storage},createElement(tag){return new Node(tag,doc);}};
  return {container:new Node('div',doc),storage,doc};
}
function edit(container,index,values){
  const row=all(container).filter(node=>node.className==='part-estimate-row')[index];assert.ok(row);
  for(const [label,value] of Object.entries(values))find(row,node=>node.attributes['aria-label']===label).value=value;
  find(row,node=>node.tagName==='button'&&node.textContent==='保存参考价').fire('click');
}
function switchCurrency(container,currency){const select=find(container,node=>node.tagName==='select');select.value=currency;select.fire('change');}

test('mounted component starts collapsed and unquoted, then saves explicit user data',()=>{
  const {container,storage}=dom();api.mount(container,{...context,parts});
  assert.equal(find(container,node=>node.tagName==='details').open,false);
  assert.match(container.textContent,/2 项待询价/);assert.doesNotMatch(container.textContent,/合计 USD 0/);
  edit(container,0,{'数量':'2','单价（USD）':'12.34','价格来源':'采购记录'});
  assert.match(container.textContent,/已录金额 USD 24.68 · 1 项待询价/);
  assert.match(container.textContent,/用户录入 ·/);assert.match(container.textContent,/非 XGSS 报价/);
  const saved=JSON.parse(storage.getItem(api.storageKey(context,parts[0],'USD')));
  assert.equal(saved.quantity,2);assert.equal(saved.unitMinor,1234);assert.equal(saved.source,'采购记录');
});
test('switching currency never reuses unconverted numbers and restoring a currency recovers its quote',()=>{
  const {container}=dom();api.mount(container,{...context,parts:[parts[0]]});
  edit(container,0,{'单价（USD）':'20','价格来源':'美元报价'});
  switchCurrency(container,'EUR');assert.match(container.textContent,/1 项待询价/);assert.doesNotMatch(container.textContent,/合计 EUR 20/);
  edit(container,0,{'单价（EUR）':'18','价格来源':'欧元报价'});assert.match(container.textContent,/合计 EUR 18.00/);
  switchCurrency(container,'USD');assert.match(container.textContent,/合计 USD 20.00/);
});
test('invalid edits do not overwrite an existing quote or save a partial quote',()=>{
  const {container,storage}=dom();api.mount(container,{...context,parts:[parts[0]]});
  edit(container,0,{'数量':'1.5','单价（USD）':'10','价格来源':'供应商'});
  assert.match(container.textContent,/数量须为/);assert.equal(storage.getItem(api.storageKey(context,parts[0],'USD')),null);
  edit(container,0,{'数量':'1','单价（USD）':'10','价格来源':'供应商'});
  edit(container,0,{'单价（USD）':'-5'});
  assert.equal(JSON.parse(storage.getItem(api.storageKey(context,parts[0],'USD'))).unitMinor,1000);
});
test('clearing a quote restores pending status and a different fault does not inherit prices',()=>{
  const {container,storage}=dom();let mounted=api.mount(container,{...context,parts:[parts[0]]});
  edit(container,0,{'单价（USD）':'10','价格来源':'供应商'});mounted.destroy();
  mounted=api.mount(container,{...context,researchId:'other-fault',parts:[parts[0]]});assert.match(container.textContent,/1 项待询价/);
  mounted.destroy();api.mount(container,{...context,parts:[parts[0]]});assert.match(container.textContent,/合计 USD 10.00/);
  find(container,node=>node.tagName==='button'&&node.textContent==='清除价格').fire('click');
  assert.match(container.textContent,/1 项待询价/);assert.equal(storage.getItem(api.storageKey(context,parts[0],'USD')),null);
});
test('storage denial degrades to page-local estimates without throwing',()=>{
  const {container,doc}=dom();Object.defineProperty(doc.defaultView,'localStorage',{get(){throw new Error('Denied');}});
  api.mount(container,{...context,parts:[parts[0]]});
  edit(container,0,{'单价（USD）':'15','价格来源':'人工参考'});
  assert.match(container.textContent,/合计 USD 15.00/);assert.match(container.textContent,/仅保存在当前页面/);
});
test('quota failure retains quotes already loaded and the new local estimate',()=>{
  const storage=memoryStorage();storage.setItem(api.storageKey(context,parts[0],'USD'),JSON.stringify(quote('USD','10')));
  storage.setItem=()=>{throw new Error('Quota');};const {container}=dom(storage);
  api.mount(container,{...context,parts});edit(container,1,{'单价（USD）':'20','价格来源':'新报价'});
  assert.match(container.textContent,/合计 USD 30.00/);assert.match(container.textContent,/仅保存在当前页面/);
});
test('missing identity never writes globally reusable part prices',()=>{
  const {container,storage}=dom();api.mount(container,{parts:[parts[0]],scope:'current'});
  edit(container,0,{'单价（USD）':'15','价格来源':'人工参考'});
  assert.match(container.textContent,/合计 USD 15.00/);assert.equal(storage.values.size,0);
});
test('part and source text cannot become HTML, and destroy detaches actions',()=>{
  const {container}=dom();const mounted=api.mount(container,{...context,parts:[{...parts[0],name:'<img onerror=alert(1)>'}]});
  edit(container,0,{'单价（USD）':'1','价格来源':'<script>not executable</script>'});
  assert.match(container.textContent,/<img onerror=/);assert.equal(all(container).some(node=>node.tagName==='img'||node.tagName==='script'),false);
  const oldSave=find(container,node=>node.tagName==='button'&&node.textContent==='保存参考价');mounted.destroy();
  oldSave.fire('click');mounted.refresh();assert.equal(container.children.length,0);
});

test('collapsed estimates preserve evidence labels without treating every row as a replacement',()=>{
  const {container}=dom();
  api.mount(container,{...context,parts:[
    {...parts[0],evidence_level:'inspection_only'},
    {...parts[1],evidence_level:'historical_reference'},
    {...parts[0],part_number:'PART-3',evidence_level:'conditional_candidate'},
    {...parts[0],part_number:'PART-4'}]});
  const details=find(container,node=>node.tagName==='details');assert.equal(details.open,false);
  const rows=all(container).filter(node=>node.className==='part-estimate-row');
  for(const [index,label] of ['核查候选','历史备库参考','条件性备件'].entries())
    assert.ok(rows[index].children.some(node=>node.textContent===label));
  assert.doesNotMatch(rows[3].textContent,/核查候选|历史备库参考|条件性备件/);
  assert.match(container.textContent,/用户参考价 · 非 XGSS 报价，不代表全部需要更换。/);
});
