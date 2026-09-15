const test=require('node:test'), assert=require('node:assert/strict');
const finder=require('../app/assistant_ui/device-finder.js');
const asset='12345678-1234-1234-1234-123456789012';
const device=(id,extra={})=>({selection_id:id,machine_id:asset,model:'XE135U',serial_number:'SIM-001',source:'mock',
  fault_summary:{state:'no_records',unresolved_codes:0,conflicting_codes:0,highest_severity:null,latest_record_at:null},...extra});

test('multiword Unicode and case normalized search retains exact versions',()=>{
  const a=device('dataset:a',{dataset_name:'增压信号告警',dataset_id:'aa'}),b=device('dataset:b',{dataset_name:'增压信号告警',dataset_id:'bb'});
  assert.equal(finder.filter([a,b],{query:' ＸＥ１３５ｕ  增压 '}).length,2);
  assert.deepEqual(finder.filter([a,b],{query:'bb'}),[b]);
  assert.deepEqual(finder.filter([a,b],{query:'does-not-exist'}),[]);
});
test('source and platform constraints never substitute mock or another asset',()=>{
  const a=device('fleet:a'),b=device('dataset:b',{source:'imported_user_supplied'}),c=device('dataset:c',{source:'imported_user_supplied',machine_id:'different'});
  assert.deepEqual(finder.filter([a,b,c],{platformId:asset}),[b]);
  assert.deepEqual(finder.filter([a,b,c],{platformId:''}),[]);
  assert.deepEqual(finder.filter([a,b,c],{platformId:'invalid'}),[]);
  assert.deepEqual(finder.filter([a,b,c],{source:'simulation'}),[a]);
  assert.equal(finder.filter([a,b,c],{source:'real'}).length,2);
});
test('attention uses supplied latest status and stable priority without mutating input',()=>{
  const a=device('a'),b=device('b',{fault_summary:{state:'unresolved',highest_severity:'high',unresolved_codes:1}}),
    c=device('c',{fault_summary:{state:'conflicting',conflicting_codes:1}}),d=device('d',{fault_summary:{state:'resolved_records'}});
  const input=[a,b,c,d];assert.deepEqual(finder.filter(input,{attention:true}),[c,b]);assert.deepEqual(input,[a,b,c,d]);
  assert.equal(finder.faultLabel(a.fault_summary),'未载入故障记录');
  assert.equal(finder.faultLabel(d.fault_summary),'仅有已解决记录');
  assert.match(finder.faultLabel(c.fault_summary),/待核对/);
});
test('recent ordering uses actual accepted fault times, no records last',()=>{
  const a=device('a'),b=device('b',{fault_summary:{latest_record_at:'2026-06-01T10:00:00Z'}}),
    c=device('c',{fault_summary:{latest_record_at:'2026-06-02T10:00:00Z'}});
  assert.deepEqual(finder.filter([a,b,c],{sort:'recent'}),[c,b,a]);
});
