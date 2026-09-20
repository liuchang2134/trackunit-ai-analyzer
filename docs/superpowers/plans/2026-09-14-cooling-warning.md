# Cooling Warning Implementation Plan

> **For agentic workers:** Implement inline in this existing workspace. The optional superpowers execution skills are unavailable; preserve the user's current work and do not commit or publish it.

**Goal:** A usable, causal cooling-event early-warning demonstration connected to the selected-device investigation flow.

**Architecture:** Generate a separate synthetic thermal dataset using the existing excavator duty cycles and an explicit heat balance. Train a numeric random forest on complete independent episodes, select its threshold using validation episodes, and expose prefix-only inference. The UI offers observations, an early-warning state, evaluation and an explicit handoff to a matching synthetic device and data cutoff.

**Tech Stack:** Standard-library simulation, existing scikit-learn training environment, FastAPI, existing ECharts and plain JavaScript.

## Global Constraints
- Synthetic-only validation; no manufacturer-calibrated thermal coefficients, official fault codes, remaining life or real failure accuracy claims.
- Preserve all existing v1 data, releases and real Trackunit datasets. No new paid dependency or Gemini request while its quota is exhausted.
- Event definition is an experimental coolant-temperature threshold, not component damage. Model scores are not calibrated probabilities.
- Runtime reads observations and model only, never latent states or future event labels. All features use the current/past prefix.
- Missing, stale, unordered or out-of-range sensors and insufficient history return unknown; engine-off/high-temperature observations have separate states.
- Exact synthetic device and replay cutoff must accompany any handoff; never transfer a warning onto the currently selected real machine.

## Task 1 — Thermal data and model
Files: scripts/generate_cooling_dataset.py, scripts/train_cooling_warning.py, app/cooling_warning.py, tests/test_cooling_warning.py; data/cooling_warning_v1.
- [x] Test causal features, ten-minute warmup, timestamp gaps and invalid readings before implementation.
- [x] Implement `CoolingWindow.add(row)` and `predict_prefix(model, rows)` with 60-second sensor contract, two consecutive threshold votes, and separate unknown/stopped/current_high states.
- [x] Reuse `simulate(seed, 'healthy')` duty cycles. Integrate `T += dt * (Q - UA * (T - ambient)) / C` at five seconds. Export noisy minute observations separately from evaluator-only temperature/cooling effectiveness and event time.
- [x] Generate 120 independent eight-hour equipment episodes, split 72/24/24 before training. Include healthy, hot ambient, gradual loss, severe loss, partial loss and recovery conditions. Record all assumptions and invariant checks.
- [x] Train on pre-event eligible windows for an event within 15 minutes. Use only validation episodes to choose the alarm threshold. Freeze model before test evaluation; compare against a fixed 95°C observed-temperature baseline using the same eligible windows and two-sample persistence.
- [x] Report event recall/count, warning lead times, false-alert episodes per eligible hour, window confusion counts, parity with sklearn and dataset/model hashes. Preserve failures and negatives.

## Task 2 — Source-aware API and investigation handoff
Files: app/cooling_demo.py, app/api/routes_assistant.py, app/local_datasets.py, app/local_assistant.py, app/check_options.py, tests/test_cooling_demo.py.
- [x] Serve episodes and replay at an explicit bounded cursor. Return only observations at/before the cursor, never the future event or scenario labels. Verify artifact integrity.
- [x] Prepare a `LocalDataset` whose machine ID, telemetry and replay time match the selected synthetic episode prefix; use no invented fault code.
- [x] Bind a structured cooling reference to that dataset. Server recomputes/verifies the reference and includes the resulting evidence in the model context and report citations. Reject real-device, cutoff and dataset mismatches.
- [x] Test path bounds, model tampering, future-prefix independence, data identity and Gemini context using a stub (no network request).

## Task 3 — Interactive warning workspace
Files: app/assistant_ui/index.html, cooling-warning.js, app.js, style.css, app/assistant_version.py.
- [x] Add a clearly labelled “故障预警” view with episode selection, minute cursor, previous/next controls, keyboard slider and explicit prediction action.
- [x] Show temperature chart and accessible observation table for the past prefix, risk score/threshold, data adequacy and next action; place evaluation in an expandable, separately labelled section.
- [x] Disable stale handoffs while a cursor/request changes. Provide “带入设备排查” which creates/selects the exact synthetic dataset and seeds the question without starting Gemini.
- [x] Verify in the existing browser service: loading, healthy/warning/unknown/stopped cases, cursor updates, responsive layout, source identity, handoff and no automatic AI request.

## Task 4 — Record actual acceptance
Files: docs/COOLING_WARNING.md, docs/PROJECT_ACCEPTANCE_STATUS.md, README.md, docs/evaluation.
- [x] Record actual metrics, reproducibility commands, source references, model/data assumptions and current limitations. Update only current acceptance, preserving historical claims in prior releases.
- [x] Run focused prediction and handoff tests, then the full existing Python and Node checks once integration is complete. Capture actual browser evidence.

Acceptance: implementation and browser evidence are recorded in docs/evaluation/2026-09-14-cooling-warning.md. Frozen model test false-alert rate is 0.268 per eligible hour, above the validation-stage budget; no field or Gemini success is claimed. Project-wide goal remains incomplete.
