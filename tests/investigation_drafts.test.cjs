const test=require('node:test');
const assert=require('node:assert/strict');
const {InvestigationDrafts}=require('../app/assistant_ui/investigation-drafts.js');
const empty={question:'',observations:'',task:'parts',language:'zh',priorRecordId:null};

test('device and dataset drafts do not cross and return without losing observations',()=>{
  const store=new InvestigationDrafts();
  store.switchTo('device-a/version-one/synthetic',empty);
  const first={...empty,question:'fault A',observations:'observed A',priorRecordId:'record-a'};
  assert.deepEqual(store.switchTo('device-b/version-one/synthetic',first),empty);
  const second={...empty,question:'fault B',observations:'observed B',language:'en'};
  assert.deepEqual(store.switchTo('device-a/version-one/synthetic',second),first);
  assert.deepEqual(store.switchTo('device-a/version-two/synthetic',first),empty);
  assert.deepEqual(store.switchTo('device-a/version-one/real',empty),empty);
  assert.deepEqual(store.switchTo('device-b/version-one/synthetic',empty),second);
});
test('refreshing the same selection keeps the currently edited draft',()=>{
  const store=new InvestigationDrafts();
  store.switchTo('a',empty);
  const edit={...empty,question:'new observation'};
  assert.deepEqual(store.switchTo('a',edit),edit);
});
test('unmatched platform device clears the form while preserving the previous draft',()=>{
  const store=new InvestigationDrafts();
  store.switchTo('a',empty);
  const edit={...empty,question:'only for A',observations:'operator A'};
  assert.deepEqual(store.switchTo(null,edit),empty);
  assert.deepEqual(store.switchTo('a',empty),edit);
});
