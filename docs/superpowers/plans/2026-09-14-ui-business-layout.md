# Device workspace UI Implementation Plan

> Implement sequentially in the current workspace; preserve existing work.

**Goal:** Replace the form-first presentation with a compact device operations workspace.
**Architecture:** Keep the existing local HTML/CSS/JS and API contracts. Borrow layout principles from Tabler and device information organization from ThingsBoard; no external runtime assets or copied platform code.
**Tech Stack:** HTML, CSS, browser JavaScript, existing FastAPI.

## Constraints
- Local deployment, responsive extension sidebar, Chinese UI.
- Preserve source labels, missing-data qualifications, and raw evidence access.
- Never introduce fabricated readings or precision claims.

## Tasks
- [x] Update index.html and style.css: desktop navigation rail, context strip, compact work area; mobile horizontal navigation.
- [x] Update app.js: current device details and structured computed metrics, safe text rendering.
- [ ] Check JavaScript syntax and actual desktop/narrow browser display; verify data/history navigation.

References: https://github.com/tabler/tabler ; https://github.com/thingsboard/thingsboard ; https://github.com/netbox-community/netbox

Checkpoint: Node syntax check passed. Current browser narrow width and 1280px desktop layout inspected; data and history navigation returned correct content/title. Temporary viewport reset. Structured metrics with a completed report still needs browser verification. Broader fault workflow and charts remain unfinished.
