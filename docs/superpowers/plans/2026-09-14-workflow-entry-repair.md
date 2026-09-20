# Workflow Entry Repair Implementation Plan

> **For agentic workers:** Execute inline in this task. No delegation or commits; user workflow and higher-priority session instructions govern execution.

**Goal:** 修复本次实际走查发现的旧入口与排查操作层级问题，不将原型包装成已完成产品。

**Architecture:** 沿用现有页面、控件 ID、事件处理与后端，只调整排查表单顺序和预警提示块高度。用户旧标签页导航至已经运行且核实过的 8892，不停止或另起服务。

**Tech Stack:** Existing HTML/CSS, FastAPI, CUA browser verification.

## Global Constraints

- 不请求 Gemini、Trackunit 或 XGSS，不改密钥和模型。
- 不替换用户数据；此次交互仅选择已有 SIM 设备。
- 不重建封存软件包或参赛材料；不以此小修正宣称完整项目完成。

## Task 1: Existing form hierarchy

Files: app/assistant_ui/index.html, app/assistant_ui/style.css, app/assistant_version.py.

- [x] Capture current old entry, current workspace, fault materials and AI handoff.
- [x] Move the existing run-actions block before local-draft, preserving all IDs and form ownership. Keep optional question and observations before submission.
- [x] Put only the draft help paragraph inside a details disclosure labeled “草稿保存说明”; keep save state and buttons visible.
- [x] Add `.output > #selected-cooling { min-height: 0; }` so a short linked warning does not reserve a full panel height.
- [x] Keep backend build `20260914.12-local-drafts` because backend behavior is unchanged; refresh the CSS SHA-256 query in index.html and verify the served asset. A proposed `.13` label was reverted when the process did not reload; no restart was attempted.

## Task 2: Verify and return the working entry

- [x] Check served runtime/build and HTML resource hash using localhost GET only.
- [x] Inspect the existing DOM before reload; only the agent's unsaved SIM question is present on the test tab.
- [x] Verify at the natural narrow viewport: warning height follows content; run action precedes draft controls; fault handoff preserves exact code and focuses question.
- [x] Verify the same structure at 1280×820, then clear viewport override.
- [x] Navigate the user's stale 8890 tab to the already-running 8892 UI and mark the resulting tab as a deliverable.
- [x] Save an audit with current screenshots, explicit status boundaries and prioritized remaining work. No new mirror tests for this reversible presentation-only change.
