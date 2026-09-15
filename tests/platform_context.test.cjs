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

const now=Date.parse('2026-09-15T12:00:00Z');
const version=(letter,fields={})=>({...imported,selection_id:'dataset:'+letter.repeat(64),dataset_id:letter.repeat(64),...fields});
const choose=(machines,previous='',source='trackunit_cache',assetId=id)=>P.selectDefault(machines,source,assetId,previous,now);

test('automatic default uses newest actual sample instant across time zones without mutating candidates',()=>{
 const older=Object.freeze(version('a',{latest_telemetry_at:'2026-09-15T12:30:00+01:00',sample_count:100}));
 const newest=Object.freeze(version('b',{latest_telemetry_at:'2026-09-15T11:45:00Z',sample_count:1}));
 const machines=Object.freeze([older,newest]);
 assert.deepEqual(choose(machines),{selected:newest,reason:'latest_sample',tied:1});
 assert.deepEqual(choose([newest,older]),{selected:newest,reason:'latest_sample',tied:1});
 assert.equal(machines[0],older);
});

test('equal sample instants use known sample count then stable selection id in either input order',()=>{
 const smaller=version('a',{latest_telemetry_at:'2026-09-15T12:00:00+01:00',sample_count:1});
 const larger=version('b',{latest_telemetry_at:'2026-09-15T11:00:00Z',sample_count:2});
 for(const machines of [[smaller,larger],[larger,smaller]])assert.deepEqual(choose(machines),{selected:larger,reason:'equal_latest_sample',tied:2});
 const first=version('a',{latest_telemetry_at:'2026-09-15T11:00:00Z',sample_count:2});
 for(const machines of [[first,larger],[larger,first]])assert.deepEqual(choose(machines),{selected:first,reason:'equal_latest_sample',tied:2});
});

test('legacy last-seen fallback is used only when latest telemetry metadata is absent',()=>{
 const legacy=version('a',{last_seen_at:'2026-09-15T11:30:00Z'});
 const explicitlyEmpty=version('b',{latest_telemetry_at:null,last_seen_at:'2026-09-15T11:59:00Z',sample_count:100});
 const current=version('c',{latest_telemetry_at:'2026-09-15T11:00:00Z',last_seen_at:'2026-09-15T12:00:00Z'});
 assert.equal(choose([current,explicitlyEmpty,legacy]).selected,legacy);
 assert.deepEqual(choose([explicitlyEmpty]),{selected:explicitlyEmpty,reason:'undated_default',tied:1});
});

test('missing, invalid, unzoned and future samples rank below known dates and still allow a default',()=>{
 const invalidDates=[null,'','Data not available','2026-02-30T12:00:00Z','2026-09-15T24:00:00Z',
  '2026-09-15T11:00:00','2026-09-15T12:00:01Z','2026-09-15T11:00:00-02:00',123];
 const valid=version('a',{latest_telemetry_at:'2026-09-14T11:00:00Z',sample_count:0});
 for(const latest_telemetry_at of invalidDates){
  const unknown=version('b',{latest_telemetry_at,last_seen_at:'2026-09-15T12:00:00Z',sample_count:1000});
  assert.equal(choose([unknown,valid]).selected,valid);
  assert.deepEqual(choose([unknown]),{selected:unknown,reason:'undated_default',tied:1});
 }
 const missing=version('b'),unknown=version('a',{latest_telemetry_at:null});
 for(const machines of [[missing,unknown],[unknown,missing]])assert.deepEqual(choose(machines),{selected:unknown,reason:'undated_default',tied:2});
});

test('unknown sample counts never outrank finite nonnegative counts',()=>{
 const known=version('f',{latest_telemetry_at:'2026-09-15T11:00:00Z',sample_count:0});
 for(const sample_count of [undefined,null,-1,Infinity,NaN,'900']){
  const unknown=version('a',{latest_telemetry_at:'2026-09-15T11:00:00Z',sample_count});
  assert.equal(choose([unknown,known]).selected,known);
 }
});

test('retains a valid previous version even if another version is newer',()=>{
 const previous=version('a',{latest_telemetry_at:null}),latest=version('b',{latest_telemetry_at:'2026-09-15T11:00:00Z'});
 assert.deepEqual(choose([previous,latest],previous.selection_id),{selected:previous,reason:'retained',tied:1});
 assert.equal(choose([previous,latest],'dataset:'+'f'.repeat(64)).selected,latest);
});

test('automatic defaults never select another UUID, mock cache or synthetic import',()=>{
 const wrong=version('a',{machine_id:other}),synthetic=version('b',{provenance:'synthetic'});
 const real=version('c',{latest_telemetry_at:'2026-09-15T11:00:00Z'});
 assert.deepEqual(choose([wrong,synthetic]),{selected:null,reason:'no_match',tied:0});
 assert.deepEqual(choose([cache],'','mock'),{selected:null,reason:'no_match',tied:0});
 assert.deepEqual(choose([{...cache,machine_id:'not-a-uuid'}],'','trackunit_cache','not-a-uuid'),{selected:null,reason:'no_match',tied:0});
 assert.equal(choose([wrong,synthetic,real],wrong.selection_id).selected,real);
 assert.equal(choose([wrong,synthetic,real],synthetic.selection_id).selected,real);
 assert.equal(choose([cache,real],'','mock').selected,real);
});
