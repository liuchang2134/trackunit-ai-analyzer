# AI Request Status and Fault Flow Implementation Plan

> Execute inline in this task. Existing authorization covers local implementation and verification. Preserve earlier artifacts and the v8 ZIP; no provider probes, model changes, service restarts, commits or publishing.

**Goal:** Make the user's next action clear by showing the latest complete-investigation outcome before submission and placing the fault-to-AI action next to the fault state.

**Architecture:** A local, bounded status record stores an outcome, timestamp and whitelisted error category without machine data, prompts, raw errors or credentials. Bind newly recorded outcomes to the backend configuration via a private digest; a prior verification can be imported only as explicitly unverified historical configuration. A read-only endpoint serves the status independently of device selection and reports staleness without claiming recovery.

**Tech Stack:** Existing FastAPI/Pydantic, Python standard library atomic file replacement, existing plain JavaScript and CSS. No new dependencies.

## Global Constraints

- Gemini remains the selected provider; numerical models remain local.
- Do not probe the known exhausted quota or guess an XGSS request contract.
- A report is successful only after the existing investigation checks; history-save failure is a separate outcome.
- Invalid user input does not become a provider failure. Unknown or corrupt status does not imply availability.
- Status refresh calls GET only. Time elapsed never asserts that quota has recovered.
- Preserve current data/version isolation, drafts, failure restoration and return focus.
- All tests use temporary status storage; never overwrite the user's runtime record.

## Task 1: Record complete-investigation outcomes

Files: create `app/ai_request_status.py` and `tests/test_ai_request_status.py`; modify `app/api/routes_assistant.py`, `app/gemini_client.py`, `app/local_assistant.py`, `tests/conftest.py`.

Interfaces:

```python
capture_context() -> dict  # provider, model, configured, private context_id
request_status(context: dict | None = None) -> dict
record_outcome(context: dict, outcome: str, *, error=None) -> dict
```

- [x] Test missing/corrupt/future records, changed credentials/model, and historical configuration ambiguity. Test sanitized error categories and storage failure without changing the completed report outcome.
- [x] Add typed bounded record, atomic replacement, newest-finish ordering, and public summary without context digest or raw strings. New route `GET /assistant/ai-status` returns `Cache-Control: no-store` and never invokes a provider.
- [x] Add whitelisted failure kinds to Gemini errors; retain the existing retry behavior and public error text. Route records failed, report-saved and report-unsaved outcomes after existing validation.
- [x] Extend the global fixture to isolate the status file and verify route tests don't create successful history on failure. Commands: `.tmp/venv/Scripts/python.exe -m pytest tests/test_ai_request_status.py tests/test_gemini_quota.py tests/test_gemini_client.py -q`.

## Task 2: Present status and shorten fault handoff

Files: create `app/assistant_ui/ai-request-status.js` and `tests/ai_request_status.test.cjs`; modify `app/assistant_ui/app.js`, `index.html`, `style.css`, `fault-context.js`, and `app/assistant_version.py`.

- [x] Pure display formatter distinguishes missing config, unknown, last success, unsaved report, quota/service/validation failure, stale time and prior verification. Node tests assert no promise of current availability or quota reset and no arbitrary upstream text display.
- [x] Add a compact status region above the task form, a local-record refresh button, and status updates from actual POST responses. Do not clear it on device switching. On read failure show uncertainty without relabeling an earlier result as current.
- [x] Place the fault-to-AI button after the current fault state. Move record counts, cutoff and source into the expandable original-record section; retain visible candidate applicability and source. Keep the XGSS unavailable state with expandable detail. Disable the action during analysis and preserve the existing focus handoff.
- [x] Recalculate asset hashes and bump the current build. Run Node logic and syntax checks, plus affected Python route tests.

## Task 3: Verify the complete local scope

- [x] Import the existing 09:41 UTC quota evidence as `prior_verification` with no configuration digest. Do not call it a newly observed failure or claim it authenticates the current configuration.
- [x] Reuse the running 8892 reload service. In the real browser verify loaded historical warning, status refresh, device switch persistence, early fault action, expandable original evidence and exact AI-context handoff on desktop/narrow layouts. No AI submission.
- [x] Exercise report-save and feedback-route propagation in a temporary in-process test with a clearly simulated model transport. This verifies application plumbing only; real Gemini report acceptance remains pending.
- [x] Run the full existing Python and Node suites once after the changes. Update runtime and acceptance evidence with exact counts, screenshots and remaining Gemini/XGSS/extension limits.

Completion of this plan improves the requested product workflow; it does not complete the overall project.

Verified: 354 Python tests and 27 Node tests; real browser pre-submit flow at desktop and narrow sizes; runtime build matches. Details: `docs/evaluation/2026-09-14-ai-request-status.md`. The feedback chain uses simulated HTTP transport. Live Gemini and the overall project remain unaccepted.
