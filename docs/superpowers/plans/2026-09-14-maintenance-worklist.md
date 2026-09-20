# Maintenance Worklist Implementation Plan

> **For agentic workers:** Execute inline in the current task. No subagents or commits. Existing project and user workflow take priority over generic execution templates.

**Goal:** 用户可从待处理工作台进入准确设备，建立本机排查任务，追加现场记录、更新进度、归档并导出。

**Architecture:** 新增独立 SQLite 任务存储和追加事件表，事务内校验修订号防止旧页面覆盖。任务绑定设备、来源及数据版本，保留建立时摘要；原始设备故障和 AI 报告不被改写。原生 HTML/JS/CSS 工作台及任务对话框复用现有设备索引、选择和排查流程。

**Tech Stack:** Python sqlite3, Pydantic, FastAPI; existing native JavaScript/CSS; pytest, Node tests, browser acceptance.

## Constraints

- 本机数据；不请求外部 API，不改认证、不切换模型、不增加依赖。
- 状态：待开始 open、排查中 in_progress、待补充 waiting、已归档 archived。
- 每个设备/来源/数据版本至多一个未归档任务；归档必须有处理说明，可带说明重新打开。
- 人工记录始终标记未经验证，不生成假的 AI 结论，不将任务归档等同于设备修复。
- 打开列表不创建任务；用户点击创建/保存才写入。
- 版本切换及响应乱序不能把记录写入另一设备；保存冲突保留输入。

## 1. Transactional task and history

Files: app/maintenance_cases.py, app/api/routes_cases.py, app/main.py, tests/test_maintenance_cases.py, tests/conftest.py.

- [x] Implement `create_case(request)` resolving the exact device index scope, snapshot only allowlisted identity/fault summary; atomically deduplicate an active scope.
- [x] Implement `read_case(case_id)`, `current_case(machine_id, dataset_id, source)`, paged `list_cases(state, limit, offset, machine_id, real_only)`.
- [x] Implement `append_event(case_id, request)` with expected integer revision, nonempty note, explicit state, optional same-scope report link. SQLite BEGIN IMMEDIATE; insert history and revision together.
- [x] Implement UTF-8 Markdown attachment export preserving all event text, scope and unverified-source labels.
- [x] Test create → note/progress → waiting → archive → reopen; duplicate/concurrent writes; cross-device/report rejection; corrupt/unavailable storage errors; exact export and no network calls.

## 2. Worklist and device task dialog

Files: app/assistant_ui/maintenance-cases.js, index.html, style.css, app.js; tests/maintenance_cases.test.cjs.

- [x] Add default “待处理” view with active/archived task tabs, 20-row pagination, device source filtering and a separate device-record attention list. Platform asset context remains restricted to its real versions and opens the device view.
- [x] Existing task action selects its exact device version and opens a native dialog; unavailable scope remains readable/exportable without falling back to another machine.
- [x] Device “排查任务” action displays create form or active task. Save note/status and reread conflict keep input. No AI needed.
- [x] Dialog exposes “查看设备证据” and explicit “带记录进入 AI 排查”; append selected recent operator notes to existing observations within limits, never submit automatically or replace another device's inputs.
- [x] Guard late responses and mutations using immutable captured case/scope and request tickets. Keep unsaved note inputs by case/scope across dialog close and device switch.
- [x] Verify pure filtering, scope matching and stale-response guards with Node tests.

## 3. Actual acceptance

- [x] Run targeted tests then complete existing Python and Node suites once changes settle; inspect failures for real contract regressions.
- [x] Confirm existing 8892 reloads new route/build without new helper service. Allow normal reload latency; do not restart merely for observation timeout.
- [x] Browser: worklist → SIM device → create → save observation/progress → waiting → refresh recovery → archive → archived list → reopen; verify export bytes and record immutability.
- [x] Browser: switch devices, keyboard dialog close/focus, natural narrow screen and desktop 1280×820; restore viewport.
- [x] Add current screenshots and evidence, update status and open-source reference. Preserve v9 sealed package/materials. Full project completion still requires real AI/XGSS and platform integration.
