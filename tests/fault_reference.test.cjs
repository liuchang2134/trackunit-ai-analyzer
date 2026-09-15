const test = require('node:test');
const assert = require('node:assert/strict');
const { FaultAssociation, xgssSummary } = require('../app/assistant_ui/fault-reference.js');
const machine = { machine_id: 'test-a', selection_id: 'fleet:test-a', model: 'TV12U' };
const catalog = { model: 'TV12U', version: '260224' };
const item = { code: 'H10101' };

test('independent lookup does not attach a code without explicit confirmation', () => {
  const state = new FaultAssociation(); state.switchDevice(machine, 'local'); state.choose(item, catalog);
  assert.equal(state.payload(machine, 'local'), null);
  assert.throws(() => state.attach(machine, 'local', false));
  assert.deepEqual(state.attach(machine, 'local', true), { ...item, ...catalog, applicability_confirmed: true });
});
test('known other models cannot use TV12U definitions even with confirmation', () => {
  const other = { ...machine, model: 'XE55U' }, state = new FaultAssociation();
  state.switchDevice(other, 'local'); state.choose(item, catalog);
  assert.throws(() => state.attach(other, 'local', true), /不是 TV12U/);
  assert.equal(state.payload(other, 'local'), null);
});
test('device, dataset, source and model changes clear association, returning does not restore it', () => {
  for (const [next, source] of [[{ ...machine, selection_id: 'fleet:b', machine_id: 'b' }, 'local'],
    [{ ...machine, dataset_id: 'version-b', provenance: 'user_supplied' }, 'local'], [machine, 'mock'],
    [{ ...machine, model: 'XE55U' }, 'local'], [null, 'local']]) {
    const state = new FaultAssociation(); state.switchDevice(machine, 'local'); state.choose(item, catalog); state.attach(machine, 'local', true);
    state.switchDevice(next, source); assert.equal(state.payload(next, source), null);
    state.switchDevice(machine, 'local'); assert.equal(state.payload(machine, 'local'), null);
  }
});
test('same device refresh keeps association; changing candidate or clearing removes it', () => {
  const state = new FaultAssociation(); state.switchDevice(machine, 'local'); state.choose(item, catalog); state.attach(machine, 'local', true);
  state.switchDevice({ ...machine }, 'local'); assert.equal(state.payload(machine, 'local').code, 'H10101');
  const copy = state.payload(machine, 'local'); copy.code = 'H99999'; assert.equal(state.payload(machine, 'local').code, 'H10101');
  state.choose({ code: 'E10101' }, catalog); assert.equal(state.payload(machine, 'local'), null);
  state.attach(machine, 'local', true); state.clear(); assert.equal(state.payload(machine, 'local'), null);
});
test('wrong protocol or invalid code cannot become diagnostic evidence', () => {
  const state = new FaultAssociation(); state.switchDevice(machine, 'local');
  state.choose(item, { ...catalog, version: 'wrong' }); assert.throws(() => state.attach(machine, 'local', true));
  state.choose({ code: 'SPN10101' }, catalog); assert.throws(() => state.attach(machine, 'local', true));
});
test('XGSS status distinguishes configured catalogue from unconfirmed manual field', () => {
  assert.match(xgssSummary({ catalog_ready: true, fault_ready: false }), /通用图册入口已配置/);
  assert.match(xgssSummary({ catalog_ready: true, fault_ready: false }), /直达字段待确认/);
  assert.match(xgssSummary({ catalog_ready: true, fault_ready: true }), /内容需打开官方页面后核对/);
  assert.match(xgssSummary(null), /读取失败/);
});

const restoredFault={...item,...catalog,applicability_confirmed:true};
test('restored code remains a draft candidate until fresh applicability confirmation',()=>{
  const state=new FaultAssociation();state.switchDevice(machine,'local');
  assert.equal(state.stageRestore(restoredFault,machine,'local'),true);
  assert.equal(state.payload(machine,'local'),null);
  assert.deepEqual(state.draftPayload(machine,'local'),restoredFault);
  state.choose(item,catalog,true);
  assert.deepEqual(state.draftPayload(machine,'local'),restoredFault);
  assert.equal(state.payload(machine,'local'),null);
  assert.throws(()=>state.attach(machine,'local',false));
  state.attach(machine,'local',true);
  assert.deepEqual(state.payload(machine,'local'),restoredFault);
});
test('restored candidates cannot cross device scopes or silently survive removal',()=>{
  const state=new FaultAssociation();state.switchDevice(machine,'local');state.stageRestore(restoredFault,machine,'local');
  const snapshot=state.draftPayload(machine,'local');snapshot.code='H99999';
  assert.equal(state.draftPayload(machine,'local').code,'H10101');
  const other={...machine,machine_id:'other',selection_id:'fleet:other'};
  state.switchDevice(other,'local');assert.equal(state.draftPayload(other,'local'),null);
  state.switchDevice(machine,'local');assert.equal(state.draftPayload(machine,'local'),null);
  state.stageRestore(restoredFault,machine,'local');state.clear();assert.equal(state.draftPayload(machine,'local'),null);
  assert.equal(state.stageRestore(restoredFault,{...machine,model:'XE55U'},'local'),false);
});
