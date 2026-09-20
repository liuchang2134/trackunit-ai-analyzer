# Gemini Prototype Release v8 Implementation Plan

> **For agentic workers:** Execute inline in this existing workspace; the optional superpowers execution skills are unavailable. Preserve previous archives, credentials and local data. Do not commit or publish.

**Goal:** Deliver a coherent, verifiable software package for the current Gemini-based assistant and synthetic cooling/work-state demonstrations.

**Architecture:** Add an explicitly versioned v8 release recipe with an allowlist of current app assets, third-party notices, synthetic model resources and installation documentation. Preserve the historical build/verification scripts. Keep no credentials or private runtime records. A fresh extracted checkout and a fresh virtual environment exercise the actual FastAPI lifespan and local workflows without contacting cloud services.

**Tech Stack:** Python 3.11–3.13, existing pinned runtime requirements, ZIP/SHA-256 manifests, PowerShell setup, FastAPI TestClient.

## Constraints
- Previous ZIP files are immutable. Use a new v8 filename and fail if it exists.
- Gemini remains the configured LLM; local demonstration access is not a substitute AI model or fabricated report.
- Never distribute .env, real caches, local catalogs/history, user keys or XGSS public-key files.
- Default data source is mock; automatic Trackunit synchronization is disabled.
- Preserve the complete project scope; the package does not establish Gemini, XGSS, real-machine or installed-extension acceptance.
- Do not restart existing services or work around earlier rejected background-service/extension actions. Test extracted application startup in-process, not through a new listening helper.

## Task 1 — Installation and readiness
Files: scripts/check_local_runtime.py, start_local.ps1, setup_local.ps1, tests/test_runtime_readiness.py.
- [x] Separate local runtime readiness from configured Gemini readiness; never make a provider call in Gemini checks.
- [x] Add an explicit `-DemoOnly`/`--demo-only` option allowing local observations with a blank key while AI readiness remains false. Default startup still requires configured Gemini.
- [x] Accept an explicit PythonExecutable for setup, validate Python 3.11–3.13, preserve existing .env and virtual environments, and seed only the documented synthetic examples.
- [x] Test missing dependencies, blank credentials, invalid provider/endpoint, supported Python range and demo-only exit status without network.

## Task 2 — Current release recipe
Files: scripts/build_release_v8.py, scripts/verify_release_v8.py, scripts/release_smoke.py, tests/test_release_v8.py, docs/RELEASE_V8_GUIDE.md, docs/RELEASE_V8_NOTES.md.
- [x] Use clean Gemini config in the current recipe. Include every cooling runtime resource, seven work-state test episodes, official ECharts LICENSE/NOTICE/SOURCE, extension source and current explanations.
- [x] Anonymize every mock equipment identity and linked telemetry/fault identifier consistently; remove mock customer/location identifiers and coordinates. Include only specifically reviewed synthetic examples.
- [x] Record build, provider, scope, exclusions and per-file SHA-256. Reject path escapes, duplicate/case-colliding paths, secret matches and missing required files before writing.
- [x] Verify manifest and critical Gemini/model/asset contracts before extraction. Preserve historical build_release.py and verify_release.py for old archives; the new verifier intentionally accepts v8 only.
- [x] Write an extracted-copy smoke script that forbids external network, validates local imports/storage boundaries and demo initialization, checks device/fault/parts/CSV/work-state/cooling flows, and verifies missing-key AI failure creates no report. Setup seeds the initial demo; smoke adds its own synthetic cooling handoff dataset.
- [x] Test archive safety, defaults, resource completeness, fixture identity joins, secret rejection and non-overwrite behavior.

## Task 3 — Independent package verification
Files: dist/jilian-assistant-gemini-prototype-20260914-v8.zip, docs/evaluation/2026-09-14-release-v8.*.
- [x] Build and inspect the actual package, extract to a new workspace-contained directory and create a new virtual environment from the known local Python runtime.
- [x] Run the included setup command with blank Gemini credentials; install pinned dependencies and record Python/package versions and pip check. No cloud request or new listening service.
- [x] Run the packaged smoke script in the fresh interpreter, verify app startup/shutdown and local-only workflow results, record archive and file hashes.
- [x] Update current acceptance and README with the exact verified package, explicit missing cloud/XGSS/extension gates and reproduction steps. Preserve old artifacts and leave the project goal active.

## Result

Delivered `dist/jilian-assistant-gemini-prototype-20260914-v8.zip`, 28,840,769 bytes, SHA-256 `a1407af41b2d28448cd43fe4b1e25b2e6804c7da462f332dfa3b300d09604184`. Independent extracted checkout, new Python 3.12.14 venv, pip check and in-process application smoke passed. Source suite: Python 336 and Node 18 passed. Evidence: [release verification](../../evaluation/2026-09-14-release-v8.md). This completes this bounded packaging plan, not the overall project goal.
