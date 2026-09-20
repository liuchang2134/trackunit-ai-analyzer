# Competition Materials v9 Implementation Plan

> Execute inline using the available documents and presentations workflows. Preserve earlier artifacts, credentials and private machine records. No publishing, form submission, provider calls or service restarts.

**Goal:** Deliver a coherent Proposal, editable pitch deck and spoken demonstration script reflecting Gemini, simulated cooling warning and the current device workflow.

**Architecture:** Use the current evidence files as facts, adapt the existing proposal typography and flat pitch style, include editable model comparison data, and render every final page/slide. Artifact version v9 must not imply a v9 software release.

**Files:** New `docs/机联智检_参赛Proposal_v9_Gemini与模拟预警版.{md,docx,pdf}`, `docs/机联智检_答辩演示稿_v9_Gemini与模拟预警版.{pptx,pdf}`, `docs/机联智检_答辩讲稿_v9.md`, `docs/机联智检_五分钟演示脚本_v9.md`; private builders/rendered files under `.tmp` and acceptance under `docs/evaluation`.

- [x] Inspect current proposal, deck, current build/acceptance and model metrics. Retain explicit simulation and integration limits.
- [x] Update Proposal including 120-episode cooling experiment, 8/8 vs 7/8 events, 15 vs 9 minute median lead and 0.268 vs 0.141 false segments per eligible hour. Include current local installation evidence and v8/source version distinction.
- [x] Build DOCX with bundled runtime and existing typography, run packaged renderer, diagnose unavailable render dependencies and use existing verified native Word export fallback when necessary. Render PDF pages and inspect every page.
- [x] Build a new editable pitch deck with the existing flat typography, native comparison table/chart and useful current product evidence. Use Artifact Tool, finalizer, exact sources in notes and 16:9 dimensions.
- [x] Render/inspect every final slide, verify text and editable data against source files, export a final PDF companion.
- [x] Write a five-minute live-demo script using only available local actions, with explicit Gemini/XGSS status and no fabricated success. Update status with deliverable links and preserve prior hashes.

The full project remains active: complete Gemini report/feedback, XGSS production handoff, formal parts, installed extension and field validation are separate outstanding gates.
