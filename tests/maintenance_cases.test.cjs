const test=require('node:test');
const assert=require('node:assert/strict');
const {Gate,matches,handoff,ensureSaved,scopeKey,newest,linkEntry}=require('../app/assistant_ui/maintenance-cases.js');

test('task opened from worklist retains its unsaved note when reopened from device context',()=>{
  const scope={machine_id:'A',serial_number:'S',dataset_id:'one',source:'imported_synthetic'};
  const entry={note:'尚未保存的文字'},entries=new Map();
  linkEntry(entries,entry,{case_id:'case-a',scope,state:'waiting'});
  assert.equal(entries.get('case:case-a'),entries.get('scope:'+scopeKey(scope)));
  assert.equal(entries.get('scope:'+scopeKey(scope)).note,'尚未保存的文字');
  assert.equal(entries.get('scope:'+scopeKey({...scope,dataset_id:'two'})),undefined);
  linkEntry(entries,entry,{case_id:'case-a',scope,state:'archived'});
  assert.equal(entries.has('scope:'+scopeKey(scope)),false);
  assert.equal(entries.get('case:case-a').note,'尚未保存的文字');
});

test('a delayed read cannot roll back a mutation which already succeeded',()=>{
  const saved={case_id:'a',revision:3,state:'waiting'};
  assert.equal(newest(saved,{case_id:'a',revision:2,state:'open'}),saved);
  assert.equal(newest(saved,{case_id:'a',revision:4,state:'archived'}).revision,4);
  assert.equal(newest(saved,{case_id:'b',revision:1}).case_id,'b');
});

test('late case reads cannot populate another case or a reopened dialog',()=>{
  const gate=new Gate();
  const first=gate.begin('case-a'),second=gate.begin('case-b');
  assert.equal(gate.accepts(first),false);
  assert.equal(gate.accepts(second),true);
  gate.close();assert.equal(gate.accepts(second),false);
  const reopened=gate.begin('case-b');
  assert.equal(gate.accepts(second),false);assert.equal(gate.accepts(reopened),true);
});

test('case context requires device, source, serial and exact dataset version',()=>{
  const scope={machine_id:'A',serial_number:'S',dataset_id:'one',source:'imported_synthetic'};
  assert(matches(scope,{...scope}));
  for(const patch of [{machine_id:'B'},{serial_number:'other'},{dataset_id:'two'},{source:'imported_user_supplied'}])assert(!matches(scope,{...scope,...patch}));
  assert.notEqual(scopeKey(scope),scopeKey({...scope,dataset_id:'two'}));
});

test('AI handoff preserves the original symptom and latest notes without duplicating them',()=>{
  const record={case_id:'case-a',title:'排查压力信号',events:[1,2,3,4].map(n=>({note:'原文'+n,created_at:'date'+n,to_state:'waiting'}))};
  const values=handoff(record,{question:'已有故障问题',observations:'用户未保存的观察'});
  assert.equal(values.question,'已有故障问题');assert(values.observations.startsWith('用户未保存的观察\n\n'));
  assert(values.observations.includes('原文1'));assert(values.observations.includes('原文4'));assert(values.observations.includes('未经验证'));
  for(let n=1;n<=4;n++)assert.equal(values.observations.split('原文'+n).length-1,1);
  assert.deepEqual(handoff(record,values),values);
  assert.throws(()=>handoff(record,{question:'',observations:'x'.repeat(4000)}),/超出输入长度/);
});

test('AI handoff retains the initial manual fault code after many updates and discloses omissions',()=>{
  const record={case_id:'case-a',title:'TV12U 排查',events:[
    {note:'机手报告 H10101，低速动作异常，尚未核实。',created_at:'date1',to_state:'open'},
    ...[2,3,4,5,6].map(n=>({note:'检查记录'+n,created_at:'date'+n,to_state:'waiting'}))]};
  const values=handoff(record,{question:'',observations:''});
  assert(values.observations.includes('H10101'));
  assert(values.observations.includes('检查记录4'));
  assert(values.observations.includes('检查记录6'));
  assert(!values.observations.includes('检查记录2'));
  assert(values.observations.includes('其余 2 条仍在任务历史中'));
  assert(values.observations.includes('未经验证'));
  assert.equal(record.events.length,6);
});

test('unsaved checks and progress cannot silently disappear from an AI handoff',()=>{
  const record={state:'waiting'},pending={note:'已检查连接器，无松脱；尚未测量。',desired:'waiting'};
  assert.throws(()=>ensureSaved(record,pending),/请先保存/);
  assert.equal(pending.note,'已检查连接器，无松脱；尚未测量。');
  assert.throws(()=>ensureSaved(record,{note:'',desired:'archived'}),/当前输入已保留/);
  assert.doesNotThrow(()=>ensureSaved(record,{note:'',desired:'waiting'}));
});
