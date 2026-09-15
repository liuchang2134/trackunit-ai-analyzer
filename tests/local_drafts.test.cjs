const test=require('node:test');
const assert=require('node:assert/strict');
const {LocalDraftState,meaningfulDraft}=require('../app/assistant_ui/local-drafts.js');
const value={question:'A',observations:'original',task:'parts',language:'zh',prior_record_id:null};
const saved={revision:'r1',saved_at:'2026-09-14T11:00:00Z',content:value};

test('late device response never becomes another device record',()=>{
  const s=new LocalDraftState();s.select('A');const request=s.beginRead();
  s.select('B');assert.equal(s.acceptRead(request,saved),false);
  assert.equal(s.entry().saved,null);
  s.select('A');assert.deepEqual(s.entry().saved,saved);
});
test('new read supersedes earlier response and errors',()=>{
  const s=new LocalDraftState();s.select('A');const old=s.beginRead(),next=s.beginRead();
  assert.equal(s.acceptRead(old,saved),false);assert.equal(s.failRead(old,'old error'),false);
  s.acceptRead(next,null);assert.equal(s.entry().error,null);assert.equal(s.entry().saved,null);
});
test('saved snapshot does not claim newer input was saved',()=>{
  const s=new LocalDraftState();s.select('A');s.acceptRead(s.beginRead(),null);
  const pending=s.beginSave(value);const newer={...value,observations:'new edit'};
  assert.deepEqual(pending.content,value);s.finishSave(pending,saved);
  assert.equal(s.dirty(newer),true);assert.equal(s.dirty(value),false);
});
test('restore is explicit and undo retains input on the correct device',()=>{
  const s=new LocalDraftState();s.select('A');s.acceptRead(s.beginRead(),saved);
  const edit={...value,observations:'unsaved edit'};
  assert.deepEqual(s.restore(edit),value);
  s.select('B');assert.equal(s.undoRestore(),null);
  s.select('A');assert.deepEqual(s.undoRestore(),edit);assert.equal(s.undoRestore(),null);
});
test('same device dataset variants remain isolated',()=>{
  const s=new LocalDraftState();s.select('A/v1/synthetic');s.acceptRead(s.beginRead(),saved);
  s.select('A/v2/synthetic');assert.equal(s.entry().saved,null);
  s.select('A/v1/real');assert.equal(s.entry().saved,null);
  s.select(null);assert.equal(s.entry(),null);
});
test('conflict requires re-reading before restore can use the new revision',()=>{
  const s=new LocalDraftState();s.select('A');s.acceptRead(s.beginRead(),saved);
  const token=s.beginSave(value);s.failSave(token,'conflict',true);
  assert.equal(s.restore(value),null);
  const newer={...saved,revision:'r2',content:{...value,observations:'other window'}};
  s.acceptRead(s.beginRead(),newer);assert.deepEqual(s.restore(value),newer.content);
  assert.equal(s.beginSave(value).expected_revision,'r2');
});

const fault={code:'H10101',model:'TV12U',version:'260224',applicability_confirmed:true};
test('fault-only draft is meaningful and equal fault values do not create false dirty state',()=>{
  const content={...value,question:'',observations:'',manual_fault:{...fault}};
  assert.equal(meaningfulDraft(content),true);
  assert.equal(meaningfulDraft({...content,manual_fault:null}),false);
  const s=new LocalDraftState();s.select('TV12U');
  s.acceptRead(s.beginRead(),{...saved,content});
  assert.equal(s.dirty({...content,manual_fault:{applicability_confirmed:true,version:'260224',model:'TV12U',code:'H10101'}}),false);
  assert.equal(s.dirty({...content,manual_fault:{...fault,code:'E10101'}}),true);
  assert.equal(s.dirty({...content,manual_fault:null}),true);
});
test('old drafts and explicit null have the same unassociated fault value',()=>{
  const s=new LocalDraftState();s.select('A');s.acceptRead(s.beginRead(),saved);
  assert.equal(s.dirty({...value,manual_fault:null}),false);
  s.acceptRead(s.beginRead(),{...saved,content:{...value,manual_fault:null}});
  assert.equal(s.dirty(value),false);
});
test('saving and accepting a draft copy nested fault context independently of later edits',()=>{
  const s=new LocalDraftState();s.select('A');s.acceptRead(s.beginRead(),null);
  const original={...value,manual_fault:{...fault}},token=s.beginSave(original);
  original.manual_fault.code='E10101';
  assert.equal(token.content.manual_fault.code,'H10101');
  const response={...saved,content:{...value,manual_fault:{...fault}}};
  s.finishSave(token,response);response.content.manual_fault.code='E10101';
  assert.equal(s.entry().saved.content.manual_fault.code,'H10101');
});
test('restore and undo isolate nested fault snapshots on the correct device',()=>{
  const s=new LocalDraftState();s.select('A');
  const response={...saved,content:{...value,manual_fault:{...fault}}};
  s.acceptRead(s.beginRead(),response);response.content.manual_fault.code='H99999';
  const edit={...value,observations:'newest user note',manual_fault:{...fault,code:'E10101'}};
  const restored=s.restore(edit);edit.manual_fault.code='E99999';restored.manual_fault.code='H99999';
  assert.equal(s.entry().saved.content.manual_fault.code,'H10101');
  s.select('B');assert.equal(s.undoRestore(),null);
  s.select('A');const undo=s.undoRestore();
  assert.equal(undo.manual_fault.code,'E10101');assert.equal(undo.observations,'newest user note');
});
