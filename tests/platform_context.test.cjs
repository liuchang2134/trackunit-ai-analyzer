const {test}=require('node:test');const assert=require('node:assert/strict');
const P=require('../app/assistant_ui/platform-context.js');
const {trackunitContextLabel}=require('../extension/context.js');
const id='00000000-0000-0000-0000-000000000001',other='00000000-0000-0000-0000-000000000002';
const cache={machine_id:id,selection_id:'fleet:'+id,serial_number:'DO_NOT_SEND',model:'DO_NOT_SEND'};
const imported={machine_id:id,selection_id:'dataset:'+'a'.repeat(64),dataset_id:'a'.repeat(64),provenance:'user_supplied'};
const input={hash:'#trackunit-asset='+id,machines:[cache],source:'trackunit_cache',selectionId:cache.selection_id,indexState:'ready',pending:false};
test('acknowledges exact cache and imported version without serial or machine content',()=>{
 for(const [machines,selectionId] of [[[cache],cache.selection_id],[[cache,imported],imported.selection_id]]){
  const ack=P.snapshot({...input,machines,selectionId});assert.equal(ack.state,'matched');
  assert.match(trackunitContextLabel(ack,id),/已关联/);
  assert.equal(JSON.stringify(ack).includes('DO_NOT_SEND'),false);
 }
});
test('missing, ambiguous, loading, unavailable and pending never become matched',()=>{
 const changes=[[{machines:[]},'missing'],[{selectionId:''},'choose_version'],[{indexState:'loading'},'loading'],
  [{indexState:'error'},'unavailable'],[{pending:true},'pending'],[{selectionId:'fleet:'+other},'choose_version']];
 for(const [change,state] of changes){const ack=P.snapshot({...input,...change});assert.equal(ack.state,state);assert.doesNotMatch(trackunitContextLabel(ack,id),/已关联/);}
});
test('mock fleet or synthetic imports cannot masquerade as platform data',()=>{
 assert.equal(P.snapshot({...input,source:'mock'}).state,'missing');
 assert.equal(P.snapshot({...input,machines:[{...imported,provenance:'synthetic'}],selectionId:imported.selection_id}).state,'missing');
});
test('wrong IDs, forged versions and unsupported acknowledgements are ignored',()=>{
 const ack=P.snapshot(input);
 for(const change of [{asset_id:other},{machine_id:other},{source:'mock'},{selection_id:'fleet:'+other},{dataset_id:'a'.repeat(64)},{state:'__proto__'}])
  assert.equal(trackunitContextLabel({...ack,...change},id),null);
 assert.equal(trackunitContextLabel({...P.snapshot({...input,machines:[imported],selectionId:imported.selection_id}),dataset_id:'b'.repeat(64)},id),null);
 assert.equal(P.snapshot({...input,hash:''}),null);
});
