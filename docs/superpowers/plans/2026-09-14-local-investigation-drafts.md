# Local Investigation Drafts Implementation Plan

> Execute inline in this session, task by task. Do not spawn agents, commit, restart services, request cloud providers, or replace sealed releases. Existing user authorization covers this repair.

**Goal:** Save and restore device-specific investigation questions and field observations before a successful AI report exists, so a page refresh does not destroy explicitly saved work.

**Architecture:** A local-only GET/PUT draft endpoint resolves the existing machine and imported dataset, validates source and prior-report ownership, and writes an atomic revision-checked record under ignored `data/local/investigation-drafts/`. The existing in-memory device draft remains; explicit Save/Restore controls read local storage through the backend, never invoke Gemini, and never silently replace current input. Restoring can be undone.

**Tech Stack:** Existing FastAPI/Pydantic, Python standard library, plain browser JavaScript, pytest and Node built-in tests. No dependency or provider changes.

## Global constraints

- All browser acceptance uses the existing 8892 service and explicit SIM equipment. No cloud submissions, extension installation or another process.
- Keep mock, imported synthetic, imported user-supplied, and Trackunit cache scopes separate. Dataset-to-machine and prior-report-to-scope mismatch must be rejected.
- Saved text is unverified operator input, not a diagnosis or completed report. Save does not transmit it to Gemini.
- A stale concurrent save returns 409; corrupt or unavailable storage must not be reported as saved. Late responses cannot populate another device.
- Keep original v9 ZIP, documents and video unchanged. Current development build advances to `.12-local-drafts`; record that the sealed v9 remains `.11`.

## Task 1: Local storage and API

Files: create `app/investigation_drafts.py`, `app/api/routes_drafts.py`, `tests/test_investigation_drafts.py`; modify router registration in `app/main.py` and test isolation in `tests/conftest.py`.

Interfaces:

```python
read_draft(machine_id: str, dataset_id: str | None, source: str) -> dict
save_draft(request: DraftSaveRequest) -> dict
# GET /assistant/draft?machine_id=...&source=...&dataset_id=...
# response: {draft: null | {revision, saved_at, scope, content}, ai_used: False}
# PUT /assistant/draft: scope fields + content + expected_revision
# content: question, observations, task, language, prior_record_id
```

- [x] Write/run failing tests for persistence after recreating the reader, source/dataset isolation, invalid prior report, stale concurrent saves, corruption and interrupted storage. Assert saved text does not create a report and calls no provider.
- [x] Resolve scope from `find_machine`/`load_dataset` and `get_data_source`; hash the validated source/device/serial/dataset identity. Validate text and content with Pydantic, use revision compare-and-swap under a lock and atomic replace. Read verifies the checksum and model.
- [x] Map unknown scopes to 404, stale revisions to 409, invalid payloads to 422 and unavailable storage to 503. Responses use `Cache-Control: no-store`. Run `python -m pytest tests/test_investigation_drafts.py -q`.

## Task 2: Explicit UI Save/Restore

Files: create `app/assistant_ui/local-drafts.js`, `tests/local_drafts.test.cjs`; modify `app/assistant_ui/index.html`, `app.js`, `style.css`, and programmatic handoff notifications in `fault-context.js` and `cooling-warning.js`.

- [x] Add visible “保存本机草稿 / 恢复已存草稿 / 撤销恢复 / 重新读取” controls below observation input, a local-only explanation and a live save state. Existing analysis button remains the only cloud submission.
- [x] Read per-selection draft metadata with a request generation guard, compare current input with stored content, and preserve input typed while save/read is pending. Restore is explicit and undoable; device switching retains each device's in-memory values.
- [x] Block stale saves until the user reviews/restores the current stored version. Disable draft actions during AI analysis. Bind typing and all fault/cooling/history handoffs to update the unsaved state.
- [x] Add focused Node tests for late response isolation, save snapshot versus newer input and restore/undo. Update resource hashes and development build. Run Node tests and relevant Python tests, then the complete existing suites once.

## Task 3: Actual browser acceptance and current status

- [x] Existing `.11` UI reproduced: enter a clearly simulated observation, reload, reselect the same SIM cooling dataset, expand observations; text is empty.
- [x] In the new UI save a SIM observation without Gemini, reload, select the same version and explicitly restore the exact question/observation/task. Switch to a different SIM device and verify isolation. Edit, restore and undo, then verify the edit survives. Inspect narrow layout and controls.
- [x] Check actual draft file and API response, record screenshots and evidence under `docs/evaluation/2026-09-14-local-drafts.*`, and update README/acceptance status with scope and the still-open live API gates. Do not claim original v9 artifacts include this later development change.
