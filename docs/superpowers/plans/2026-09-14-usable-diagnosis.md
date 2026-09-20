# Usable diagnosis flow implementation plan

> **For agentic workers:** Use the existing project workflow to implement each task below. The optional superpowers execution skills are unavailable in this installation; execute locally and verify the result.

**Goal:** A selected device can be analyzed without prompt writing, with visible waiting, a readable result, and correctly scoped history using Gemini.

**Architecture:** Keep the existing FastAPI and static assistant UI. Cloud inference uses the backend only; data tools and immutable history stay local. Preserve source and dataset boundaries.

**Tech Stack:** Python, FastAPI, httpx, Gemini REST, plain JavaScript/CSS, pytest.

## Global constraints
- Keep the existing workspace and stored records; no destructive migrations.
- Do not claim production XGSS integration or validated fault prediction.
- Keep credentials in the ignored .env and server only.
- Use synthetic data for live AI verification. Never switch providers or substitute a rule report for an AI result. Bounded retries for explicit transient HTTP failures are permitted, with an overall deadline.

## Task 1 — Honest, usable interaction
Files: app/assistant_ui/index.html, app.js, style.css.
- [x] Collapse repeated device details and optional prompt input; preset tasks supply their own question.
- [x] Show elapsed waiting time, lock inputs while running, preserve prior report on failure, focus the completed result.
- [x] Put the AI summary and checks first, with expandable evidence and a clear XGSS integration limit.
- [x] Refresh cloud/local labels from the actual backend configuration.
- [x] Capture before/after browser states and keyboard/empty-state behavior.

## Task 2 — Device-scoped records
Files: app/investigation_history.py, app/api/routes_assistant.py, tests/test_investigation_history.py.
- [x] Filter by machine, dataset and source before truncating results; retain opt-in all-device view.
- [x] Test interleaved devices and data versions, ensuring old records remain readable.

## Task 3 — Finish Gemini migration
Files: tests/test_ai_provider.py, app/local_assistant.py, README.md, docs/LOCAL_ASSISTANT.md.
- [x] Update the previous local-default expectation to the user's Gemini selection.
- [x] Run pytest and JavaScript syntax checks; start a version-checked preview backend without stopping existing services.
- [ ] Run a synthetic diagnosis through the UI and verify its saved history record and model.
- [x] Record measured results and remaining limits without changing historical release archives.

Verification note: 250 tests pass. Stopping the old backend was blocked by policy; verified preview runs on 8893 with build 20260914.3-device-overview. Full Gemini fault/parts diagnosis still returns upstream 503 on this correct build despite successful simple probes. Successful result/feedback UI branches remain unverified this run. See docs/evaluation/ux-20260914/审查与修正.md.

## Task 4 — Inspect device evidence before asking AI
Files: app/device_overview.py, app/telemetry_evidence.py, app/api/routes_assistant.py, app/assistant_ui/device-overview.js, index.html, style.css, tests/test_device_overview.py.
- [x] Read local source-scoped telemetry and faults without AI calls or upstream synchronization.
- [x] Share timestamp filtering with numerical trends; preserve missing values and reject invalid/future/conflicting records.
- [x] Add ECharts time series, metric/window selection, zoom, accessible description and data-table alternative.
- [x] Preserve full-window accepted-interval statistics when chart data is downsampled or filtered.
- [x] Seed a specific fault question from the fault table without automatic submission.
- [x] Verify real missing-idle state, synthetic time-window changes, narrow and desktop layouts.
- [x] Update current acceptance criteria to Gemini and preserve historical local-model release artifacts.
- [ ] Verify plotted-data CSV download file and complete successful Gemini report/feedback flow.

## Task 5 — Reduce cloud round trips and recover from temporary capacity failures

Evidence: the current full first request returned HTTP 503 / UNAVAILABLE with Google's high-demand message at 2026-09-14T09:08:43Z. This establishes the reason for that request; it does not explain every historical failure. Google's troubleshooting guide recommends bounded exponential backoff for transient failures.

Files: app/local_assistant.py, app/gemini_client.py, app/assistant_ui/app.js, app/assistant_version.py, tests/test_gemini_assistant.py, tests/test_gemini_client.py.

- [x] First add tests asserting that explicit Gemini tasks collect their required snapshot/fault/trend evidence before the first model call, while parts component selection remains model-driven and all existing report guards apply. Keep auto/local tool selection unchanged.
- [x] Extract the existing read-only tool execution into an investigation-scoped helper so prefetch and model-selected calls share source filtering, references, candidates and trace logic. Mark each trace's trigger as task_required or model_selected.
- [x] Limit the Gemini investigation to a 120-second overall deadline. Pass remaining time to generate_structured_with_gemini; preserve the six-step ceiling so free-form questions can still request all four tools and a final report.
- [x] Retry only explicit HTTP 500/502/503/504 responses, at most three attempts per model decision, with 2/4-second exponential delay plus jitter and the same overall remaining deadline. Do not retry authentication/schema/quota errors or ambiguous timeouts. Preserve the provider, key destination and payload across attempts. Include attempt count in terminal errors without response body or secrets.
- [x] Verify transient recovery, terminal failures, non-retryable errors, time limits, evidence/source integrity and model-selected components with tests. Full suite: 262 passed; follow-up import/version adjustment: 11 related tests passed.
- [x] Use the existing automatically reloaded service after verifying both build and runtime behavior; a separate service start was blocked by policy and was not worked around. Full synthetic UI request returned rate/quota limitation, so no saved-report or feedback success is claimed. See docs/evaluation/2026-09-14-gemini-capacity-and-runtime.md.

## Task 6 — Read fault evidence and applicable local parts without waiting for AI

Files: new app/fault_context.py, app/assistant_ui/fault-context.js, tests/test_fault_context.py; modify app/api/routes_assistant.py, app/assistant_ui/device-overview.js, index.html, style.css, app/assistant_version.py.

The product remains an AI-assisted platform companion. Direct source lookup is a separate read-only capability, never a fabricated AI diagnosis. XGSS stays explicitly unavailable until its verified request contract and authorized identity arrive.

- [x] Add get_fault_context(machine_id, fault_code, dataset_id=None), returning the selected device/version, accepted matching-code records before the replay/current cutoff, exact model/serial/code catalog candidates, diagnostics, source text and manual integration status. Return 404 for absent/mismatched records and 503 for unreadable source/catalog. Do not call external services or models.
- [x] Test device/version isolation; wrong-device, future and invalid-time records; resolved/history and conflicting statuses; exact fault code, model and serial filters; demo exclusion on real data; corrupted catalog; no-network execution.
- [x] Add GET /assistant/fault-context with bounded query fields and no-store response headers. Expose only selected-device evidence and read-only source details.
- [x] Add a fault-row “查看资料” action and inline details containing record history, source-aware candidates, model/serial caveats, original checks and document/page/revision. Keep “AI 排查” as a separate action. Clearly indicate deterministic local lookup and unavailable official manual access.
- [x] Cancel stale rendering on device/version/fault changes; restore keyboard focus when closing the detail panel. Use text nodes for catalog and event content. Keep narrow-window tables scrollable.
- [x] Browser review found that changing devices retained the previous device's question and operator notes. Added in-memory drafts scoped by selection/version/source; return-to-device restores its own draft and prior-report link. Three Node tests and browser switching verify isolation, same-context preservation and unmatched-platform handling. Drafts are explicitly unsaved and cleared on page reload.
- [x] Run API tests and syntax checks; use the existing development service after checking current build. Verify synthetic matching candidates, missing candidates, device switching and keyboard close in the browser without sending more Gemini requests. Record completed capabilities and remaining cloud/XGSS gaps. Full Python suite 270 passed, 3 Node draft tests passed. See docs/evaluation/2026-09-14-fault-context.md.

## Task 7 — Downloadable chart data with source identity

Files: new app/observation_export.py and tests/test_observation_export.py; modify app/device_overview.py, app/api/routes_assistant.py, app/assistant_ui/index.html, device-overview.js, style.css and app/assistant_version.py.

The previous browser Blob download did not produce a verifiable file. Replace the chart export with a normal same-origin download link served by the backend; preserve the current selected metric and chart-window semantics.

- [x] Add a content-derived plot_revision to device overview, based on device/version/source and plotted observations, excluding wall-clock-only fields.
- [x] Implement CSV generation using Python csv.writer, UTF-8 BOM and CRLF; include device, dataset/source, metric/unit, timestamp and value. Preserve missing values as empty cells; guard formula-like identifiers. Filter the same all/6h/1h point window as the UI.
- [x] Expose GET /assistant/device-overview.csv with bounded identity fields, metric/window enums and optional expected_revision. Reject changed evidence with 409; use no-store and Content-Disposition attachment with a safe filename.
- [x] Render an actual download link only after the selected overview is loaded; update its href on metric/window changes and clear it on device changes. Explain that slider zoom does not change the exported point window. Do not invoke AI or synchronize external data.
- [x] Test CSV round-trip parsing, missing values, source identity, window filtering, data revisions, invalid input and device mismatch. Nineteen export/overview tests passed. Actual embedded-browser download triggered and produced a 61-row CSV in Downloads; device, dataset, source, metric/unit, revision and UTC boundaries match the selected synthetic one-hour chart.

## Task 8 — Make the side panel select and identify its local backend

Files: extension/panel.js, panel.html, panel.css, manifest.json; app/assistant_ui/app.js; tests/extension_panel.test.cjs; docs/EXTENSION.md.

- [x] Add a restricted service selector for the standard 8890 and the verified development 8892 loopback endpoints; persist only this choice locally, update iframe/independent-window link and recovery instructions together. No additional extension permissions or remote hosts.
- [x] Version the readiness protocol and correlate replies to the current connection nonce, origin and iframe window. Wait for both initialized data and runtime configuration; show provider/build and state that connection is not proof of a successful model response. Older backends or missing replies must produce a recovery message.
- [x] Preserve the selected Trackunit asset when reconnecting or changing service; transfer only the verified UUID. Device identification changes the current iframe fragment so the page's device-draft isolation remains effective. Do not automatically call AI.
- [x] Add meaningful Node checks for saved/invalid service choice, current versus stale replies, timeout, recovery, link/iframe consistency and asset forwarding. Fourteen draft/extension tests passed.
- [ ] Verify installed Chrome/Edge side panel and real iframe handshake. Opening local panel.html was rejected by browser URL policy, and no indirect workaround was attempted. Packaged 0.3.0 remains explicitly unverified in a real side panel.

## Task 9 — Explain the actual Gemini quota failure and update the competition proposal

On 2026-09-14 at 09:41 UTC, one synthetic comprehensive request returned HTTP 429 RESOURCE_EXHAUSTED with GenerateRequestsPerDayPerProjectPerModel-FreeTier, quotaValue 20, resolved model gemini-3.8-flash. The application made one attempt and saved no report. The retryDelay of 44 seconds is not proof that the daily quota will reset then. Official documentation says project-level daily request quotas reset at midnight Pacific time.

- [x] Parse only recognized quota windows/measures and bounded numeric limits; preserve unknown errors without inventing a daily diagnosis. Do not echo provider messages, project IDs or credentials. No automatic 429 retries.
- [x] Return structured quota information alongside the existing error detail. Show a specific daily-quota explanation and retain local evidence/parts access. Eleven quota tests, four UI message tests, and API propagation checks passed without a second live call. Full suite: 296 Python and 18 Node tests. Existing service verified on build 20260914.7-quota-status.
- [x] Update the full competition proposal to Gemini cloud inference plus local application/data, current evidence, truthful prediction/XGSS/extension limits, budget, deliverables and stage gates. Generated separate v7 Markdown/Word/PDF and preserved v6. Standard renderer failed because LibreOffice is absent; native Word PDF export and Poppler produced seven pages, all inspected. Last two pages revised; first five image hashes unchanged and last two re-inspected.
