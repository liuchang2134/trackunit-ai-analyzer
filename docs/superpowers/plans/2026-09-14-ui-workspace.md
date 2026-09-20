# Compact maintenance workspace

Goal: Replace the oversized sequential form with a compact local maintenance workspace while preserving the existing backend and import/export behavior.

References: Ant Design Pro enterprise lists (https://github.com/ant-design/ant-design-pro), ThingsBoard alarm workflows (https://github.com/thingsboard/thingsboard), Traccar device context (https://github.com/traccar/traccar-web). Reference patterns only; no upstream code copied.

- [x] Restructure app/assistant_ui/index.html: compact device context, analysis workspace, separately navigable data management; retain all existing element IDs and API contracts.
- [x] Replace app/assistant_ui/style.css with neutral compact styling, visible focus, narrow side-panel support and desktop two-column analysis layout.
- [x] Update app/assistant_ui/app.js navigation, preserve selection on refresh, readable dates and parts table built with textContent.
- [ ] Verify browser navigation, empty/result states, device switching and a local model analysis. Inspect wide and narrow layout where available.

Scope: Visual/workflow improvement. No new claims about fault prediction accuracy, no generated evidence, no changes to credentials or private cache.


Validation 2026-09-14: Node syntax check passed; 18 assistant/dataset/catalog tests passed. Browser verified data-management navigation and return, actual qwen3:4b analysis completed with two tool calls. Wide 1280px and narrow 390px layouts inspected, viewport reset. Result-empty and populated result visible. Non-empty parts table and refresh selection preservation still need interactive verification.

Observed model issue: live mock analysis translated 2485.58 hours into “约1年”, which is incorrect. Deterministic evidence remains separate. This is an unresolved model-output validation issue, not evidence that predictive accuracy is acceptable.

Follow-up: Added a scoped calendar-duration approximation guard and froze the investigation clock. 27 related tests pass. Actual local qwen3:4b replay of the same question completed with snapshot/trends, quoted 2485.6 hours and no year approximation. Backend restarted and health verified. This guard does not validate all numerical or semantic claims; broader evaluation remains required.
