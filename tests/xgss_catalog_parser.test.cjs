const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const catalog=require('../extension/xgss-catalog.js');
const fixture=require('./fixtures/xgss-visible-catalog-test.json');
test('synthetic XGSS-shaped rows yield labels and exact codes, never fixture text',()=>{
  const result=catalog.parse(fixture);
  assert.equal(result.capture_status,'visible_rows');
  assert.equal(result.vin,'XUGTEST0000000001');
  assert.equal(result.configuration,'XE55U.00III');
  assert.equal(result.source_url,'https://xgss.xcmg.com/');
  assert.deepEqual(result.items.map(r=>r.part_number),['TEST-001','TEST-002']);
  assert.equal(result.items[0].figure_ref,'1');assert.equal(result.items[0].quantity,'2');
  assert.equal(result.skipped_rows,1);assert.equal(result.coverage,'visible_rows_only');
  assert.equal(Object.hasOwn(result,'text'),false);assert.equal(Object.hasOwn(result,'fixture_notice'),false);
});
test('missing or conflicting VIN is not a usable catalog snapshot',()=>{
  assert.equal(catalog.parse({...fixture,text:'Model: XE55U'}).capture_status,'vin_missing');
  assert.equal(catalog.parse({...fixture,text:fixture.text+' VIN: XUGOTHER000000001'}).capture_status,'ambiguous_vin');
  assert.equal(catalog.parse({...fixture,text:fixture.text+' VIN: XUGTEST0000000001'}).capture_status,'visible_rows');
});
test('no table, wrong columns and empty visible grid do not claim a BOM is missing',()=>{
  assert.equal(catalog.parse({...fixture,tables:[]}).capture_status,'unrecognized_table');
  assert.equal(catalog.parse({...fixture,tables:[{headers:['名称','价格'],rows:[['a','12']]}]}).capture_status,'unrecognized_table');
  assert.equal(catalog.parse({...fixture,tables:[{headers:fixture.tables[0].headers,rows:[]}]}).capture_status,'no_visible_rows');
});
test('English columns and repeated fixed-column clones preserve row identity',()=>{
  const table={headers:['Part No.','Description','Pos.','Qty'],rows:[['TEST-003','Test harness','4','1']]};
  const result=catalog.parse({...fixture,tables:[table,table]});
  assert.equal(result.items.length,1);assert.equal(result.items[0].part_number,'TEST-003');
  assert.equal(result.items[0].figure_ref,'4');
});
test('headers, placeholders and URLs are never fabricated into part numbers',()=>{
  const table={headers:['名称','物料编码'],rows:[['test','PARTNUMBER'],['test','https://xgss.xcmg.com/?token=TEST'],['test','--'],['test','TEST-004']]};
  const result=catalog.parse({...fixture,tables:[table]});
  assert.equal(result.items.length,1);assert.equal(result.items[0].part_number,'TEST-004');
});
test('only the exact HTTPS XGSS origin is eligible for DOM reading',()=>{
  assert.equal(catalog.isXGSS('https://xgss.xcmg.com/catalog?token=DO_NOT_RETURN'),true);
  for(const value of ['http://xgss.xcmg.com/','https://xgss.xcmg.com.evil.test/','https://a:b@xgss.xcmg.com/','https://xgss.xcmg.com:444/','https://example.com'])assert.equal(catalog.isXGSS(value),false);
});
test('DOM collector excludes hidden and offscreen rows and keeps column positions',()=>{
  function element(text,{hidden=false,left=0,top=0,width=100,height=24}={}) {return {
    innerText:text,getClientRects:()=>hidden?[]:[{}],getBoundingClientRect:()=>({left,top,width,height,right:left+width,bottom:top+height}),
    closest:()=>null,querySelector:()=>null,querySelectorAll:()=>[],matches:()=>false};}
  const headers=['序号','物料编码','名称','数量'].map(x=>element(x));
  function row(values,options){const el=element('',options);el.querySelectorAll=()=>values.map(v=>element(v,options));return el;}
  const rows=[row(['1','TEST-001','测试保险丝','2']),row(['2','TEST-002','hidden','1'],{hidden:true}),row(['3','TEST-003','offscreen','1'],{top:1000})];
  const clipped=row(['4','TEST-004','测试连接器','1']);const clippedCells=[element('4',{left:-200}),element('TEST-004'),element('测试连接器'),element('1')];clipped.querySelectorAll=()=>clippedCells;rows.push(clipped);
  const table=element('');table.querySelectorAll=s=>s.startsWith('thead')?headers:s.startsWith('tbody')?rows:[];
  const doc={body:{innerText:'PIN/VIN: XUGTEST0000000001'},querySelectorAll:s=>s.startsWith('table')?[table]:[]};
  const result=catalog.collect(doc,{innerHeight:600,innerWidth:800,getComputedStyle:()=>({visibility:'visible',display:'block',opacity:'1'})});
  assert.deepEqual(result.items.map(r=>r.part_number),['TEST-001','TEST-004']);
  assert.equal(result.items[1].name,'测试连接器');assert.equal(result.items[1].figure_ref,null);
});

test('16-character machinery PIN is accepted without imposing road vehicle VIN length',()=>{
  const result=catalog.parse({...fixture,text:'PIN/VIN: XUGTEST000000001'});
  assert.equal(result.capture_status,'visible_rows');assert.equal(result.vin,'XUGTEST000000001');
});
