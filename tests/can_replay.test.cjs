const {test} = require('node:test');
const assert = require('node:assert/strict');
const {atTime, visibleEvidence, clock} = require('../app/assistant_ui/can-replay-core.js');
test('cursor cannot read a future sample', () => {
  const signal = {points: [{t: 1.8, value: 76}, {t: 2.8, value: 77}]};
  assert.equal(atTime(signal, 1), null);
  assert.equal(atTime(signal, 2).value, 76);
});
test('stale and unavailable readings remain absent instead of zero', () => {
  assert.equal(atTime({points: [{t: 1, value: 78}]}, 5), null);
  assert.equal(atTime({points: [{t: 1, value: 78}, {t: 2, value: null}]}, 2), null);
  assert.equal(atTime({points: []}, 2), null);
});
test('real zero is retained', () => assert.equal(atTime({points: [{t: 1, value: 0}]}, 1).value, 0));
test('evidence preserves the exact source frame, not a later sample', () => {
  const first = {t: 2.1, value: 78, line: 25, raw: '76'};
  const rows = visibleEvidence({signals: [{key: 'coolant', points: [first, {t: 3.1, value: 79, line: 30}]}]}, 3);
  assert.equal(rows[0].point, first);
});
test('time formatting does not invent an absolute timestamp', () => assert.equal(clock(529.55), '08:49'));
