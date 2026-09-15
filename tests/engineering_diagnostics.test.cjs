const { test } = require('node:test');
const assert = require('node:assert/strict');
const { EngineeringState, isXE55U, normalizeFault, trustedCapture, safeSourceUrl } = require('../app/assistant_ui/engineering-diagnostics.js');
const { LocalDraftState, meaningfulDraft } = require('../app/assistant_ui/local-drafts.js');
const machine = { machine_id: '00000000-0000-0000-0000-000000000001', selection_id: 'dataset:first', dataset_id: 'a'.repeat(64),
  model: 'XE55U', serial_number: 'TEST0000000000001', provenance: 'user_supplied' };
const fault = { code: 'E4030', model: 'XE55U', configuration: 'unknown', source: 'test' };

test('test fault remains an explicit separate input and does not mutate the device or imply a configuration', () => {
  const before = JSON.stringify(machine), state = new EngineeringState(); state.select(machine, 'trackunit_cache');
  assert.equal(state.payload(machine, 'trackunit_cache'), null);
  const payload = state.attach(fault, machine, 'trackunit_cache');
  assert.equal(payload.source, 'test'); assert.equal(payload.configuration, 'unknown');
  payload.code = 'E9999'; assert.equal(state.payload(machine, 'trackunit_cache').code, 'E4030');
  assert.equal(JSON.stringify(machine), before);
});

test('XE55U engineering codes cannot be attached to TV12U or a different machine selection', () => {
  const state = new EngineeringState(); state.select(machine, 'trackunit_cache');
  for (const changed of [{ ...machine, model: 'TV12U' }, { ...machine, machine_id: 'other' }, { ...machine, dataset_id: 'b'.repeat(64) }]) {
    assert.throws(() => state.attach(fault, changed, 'trackunit_cache'));
    assert.equal(state.payload(changed, 'trackunit_cache'), null);
  }
  assert.equal(isXE55U({ model: 'XE55UX' }), false);
  assert.equal(isXE55U({ model: 'XE55U.00III' }), false);
});

test('device and dataset drafts stay isolated; late results are rejected even after switching back', () => {
  const state = new EngineeringState(); state.select(machine, 'trackunit_cache'); state.attach(fault, machine, 'trackunit_cache');
  const request = state.ticket(), second = { ...machine, dataset_id: 'b'.repeat(64), selection_id: 'dataset:second' };
  state.select(second, 'trackunit_cache'); assert.equal(state.payload(second, 'trackunit_cache'), null);
  assert.equal(state.accepts(request), false);
  state.select(machine, 'trackunit_cache'); assert.equal(state.payload(machine, 'trackunit_cache').code, 'E4030');
  assert.equal(state.accepts(request), false);
  state.clear(); assert.equal(state.payload(machine, 'trackunit_cache'), null);
});

test('invalid source/configuration and nonengineering codes do not become evidence', () => {
  for (const invalid of [{ ...fault, source: 'trackunit' }, { ...fault, configuration: 'guessed' },
    { ...fault, model: 'TV12U' }, { ...fault, code: 'H10101' }, { ...fault, code: '<script>' }, null]) assert.equal(normalizeFault(invalid), null);
  assert.equal(normalizeFault({ ...fault, code: ' e4030 ' }).code, 'E4030');
});

const expectedOrigin = 'chrome-extension://' + 'a'.repeat(32);
const captureMessage = { type: 'jilian:xgss-catalog-capture', protocol: 1, connection_id: 'panel-one', request_id: 'capture:123',
  asset_id: machine.machine_id, dataset_id: machine.dataset_id, capture: { vin: machine.serial_number } };
const context = { origin: expectedOrigin, expectedOrigin, isParent: true, connectionId: 'panel-one', machine,
  hash: '#trackunit-asset=' + machine.machine_id, busy: false };

test('XGSS import requires parent extension origin, nonce, selected asset and exact dataset', () => {
  assert.equal(trustedCapture(captureMessage, context), true);
  for (const changed of [{ origin: 'https://xgss.xcmg.com' }, { isParent: false }, { connectionId: 'other' }, { busy: true },
    { hash: '#trackunit-asset=other' }, { machine: { ...machine, dataset_id: 'b'.repeat(64) } }, { machine: null }])
    assert.equal(trustedCapture(captureMessage, { ...context, ...changed }), false);
  for (const changed of [{ asset_id: 'other' }, { dataset_id: null }, { request_id: '' }, { connection_id: null }])
    assert.equal(trustedCapture({ ...captureMessage, ...changed }, context), false);
});

test('reference links accept HTTPS sources and reject executable or local URLs', () => {
  assert.equal(safeSourceUrl('https://example.com/manual.pdf#page=286'), 'https://example.com/manual.pdf#page=286');
  for (const value of ['javascript:alert(1)', 'file:///C:/private', 'data:text/html,test', '/relative', 'https://user:secret@example.com/']) assert.equal(safeSourceUrl(value), null);
});

test('engineering-only drafts save, detect config/source edits, restore and undo without mutation', () => {
  const content = { question: '', observations: '', task: 'comprehensive', language: 'zh', prior_record_id: null, engineering_fault: { ...fault } };
  assert.equal(meaningfulDraft(content), true); assert.equal(meaningfulDraft({ ...content, engineering_fault: null }), false);
  const drafts = new LocalDraftState(); drafts.select('A'); drafts.acceptRead(drafts.beginRead(), null);
  const token = drafts.beginSave(content); content.engineering_fault.code = 'E9999';
  assert.equal(token.content.engineering_fault.code, 'E4030');
  const saved = { revision: 'r1', content: { ...content, engineering_fault: { ...fault } } };
  drafts.finishSave(token, saved); saved.content.engineering_fault.source = 'operator_report';
  assert.equal(drafts.entry().saved.content.engineering_fault.source, 'test');
  assert.equal(drafts.dirty({ ...content, engineering_fault: { ...fault } }), false);
  for (const field of [{ configuration: 'XE55U.00III' }, { source: 'operator_report' }])
    assert.equal(drafts.dirty({ ...content, engineering_fault: { ...fault, ...field } }), true);
  const restored = drafts.restore(content); restored.engineering_fault.source = 'operator_report';
  assert.equal(drafts.entry().saved.content.engineering_fault.source, 'test');
  drafts.select('B'); assert.equal(drafts.undoRestore(), null);
  drafts.select('A'); assert.equal(drafts.undoRestore().engineering_fault.code, 'E9999');
});

test('existing drafts without engineering_fault remain compatible with explicit null', () => {
  const content = { question: 'old task', observations: '', task: 'comprehensive', language: 'zh', prior_record_id: null };
  const drafts = new LocalDraftState(); drafts.select('A'); drafts.acceptRead(drafts.beginRead(), { revision: 'r1', content });
  assert.equal(drafts.dirty({ ...content, engineering_fault: null }), false);
});
