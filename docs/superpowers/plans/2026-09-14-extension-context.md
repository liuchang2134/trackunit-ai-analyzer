# Browser context integration plan

Goal: Match Trackunit asset-detail URLs to local real data with explicit source selection.

Architecture: MV3 sidePanel + activeTab reads only the active tab URL on click. Validate HTTPS host and /assets/UUID path; transfer only UUID via localhost iframe fragment. No DOM, credentials, remote writes or automatic analysis. Multiple datasets require selection.

- [x] extension/context.js + tests/extension_context.test.cjs: strict URL parser, spoofed-host and invalid-path tests.
- [x] extension/panel.js/html/css + manifest: activeTab identification, bounded local readiness handshake and retry (Node harness verified; actual installed side panel pending).
- [x] app/assistant_ui/app.js: exact real-data context matching; missing/ambiguous matches never fall back to mock. Browser fragment handoff verified.
- [ ] docs/EXTENSION.md: installation and actual sideload status; keep unverified gates explicit.

Reference: GoogleChrome/chrome-extensions-samples (Apache-2.0) and official sidePanel documentation. No copied code or added dependency.

Package: dist/jilian-extension-0.2.0.zip, six explicitly allowlisted extension files and INSTALL.md only. No credentials, real data or model weights. Five Node tests and JS syntax checks passed. Actual Edge installation adds activeTab permission and requires action-time confirmation under browser tool policy; pending user confirmation, not a completed installed-plugin gate.
