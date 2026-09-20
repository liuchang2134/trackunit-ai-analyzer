const {test} = require('node:test');
const assert = require('node:assert/strict');

const {xgssPresentation} = require('../app/assistant_ui/xgss-viewer.js');

/* The official catalog is a wide two-pane page. Embedding it in the narrow side
   panel produced three stacked scrollbars and an unreadable table, so the panel
   must hand the address over as a single next action instead. */
test('the side panel never embeds the wide catalog page', () => {
  for (const width of [320, 360, 390, 480, 600, 759]) {
    const view = xgssPresentation(width);
    assert.equal(view.embed, false, `${width}px must not embed the catalog`);
    assert.equal(view.reason, 'narrow');
    assert.match(view.message, /独立标签页/);
  }
});

test('the standalone page keeps the embedded catalog', () => {
  for (const width of [760, 1024, 1440, 1920]) {
    const view = xgssPresentation(width);
    assert.equal(view.embed, true, `${width}px may embed the catalog`);
    assert.equal(view.reason, 'wide');
  }
});

test('the threshold itself is treated as wide enough', () => {
  assert.equal(xgssPresentation(759.9).embed, false);
  assert.equal(xgssPresentation(760).embed, true);
});
