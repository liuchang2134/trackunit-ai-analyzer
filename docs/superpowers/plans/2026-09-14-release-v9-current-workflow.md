# Current Workflow Release v9 Implementation Plan

> Execute inline under the user's existing authorization. No subagents, commits, publishing, provider calls, service restart or modification of existing release archives.

**Goal:** Deliver the current `.11-ai-request-status` implementation as a new installable v9 software ZIP and verify it in a fresh extracted environment.

**Architecture:** Reuse the existing allowlisted synthetic packaging and integrity checks. Keep v8 defaults compatible, add an explicit v9 recipe/verifier, and extend the installed application smoke check for device discovery and persisted AI request status. The archive contains blank cloud configuration and synthetic data only.

**Tech Stack:** Python standard library ZIP/hash handling, existing FastAPI TestClient, PowerShell setup script and a new Python 3.12 virtual environment.

## Global Constraints

- Preserve `dist/jilian-assistant-gemini-prototype-20260914-v8.zip` and its SHA256 `a1407af41b2d28448cd43fe4b1e25b2e6804c7da462f332dfa3b300d09604184`.
- Current build remains `20260914.11-ai-request-status`; packaging does not require a new application version.
- Gemini remains configured but its API key is blank in the package; no external API or new listening service during application verification.
- Do not copy `.env`, real cache, runtime AI status, private catalog, diagnosis history, user public keys or historical video.
- Source tests and local smoke cannot prove real Gemini, XGSS, official parts, installed extension, field effect or another physical computer.

## Task 1: Versioned recipe and verification

Files: create `scripts/build_release_v9.py`, `scripts/verify_release_v9.py`, `tests/test_release_v9.py`; modify `scripts/verify_release_v8.py` only to accept explicit version/required-resource parameters while keeping defaults unchanged.

- [x] Add optional keyword arguments `release='v8', required=REQUIRED` to `verify_contents`, `verify_archive`, `verify_folder`, and extraction; forward them to the existing checks. Existing calls still require a v8 manifest.
- [x] The v9 verifier requires `.11`, device finder and AI status modules plus v9 docs and smoke entry point. Both archive and folder use the same underlying integrity checks.
- [x] Build entries from the existing synthetic allowlist, replace v8 guide/start page with v9, include the new request-status documentation/evidence and four original screenshots. Recheck configured credential bytes across the final entries before writing a new exclusive ZIP.
- [x] Add current-release tests for required resources, blank/default configuration, no runtime status, all packaged Markdown links resolving and version/file integrity. Run `pytest tests/test_release_v8.py tests/test_release_v9.py -q`.

## Task 2: Installed self-check and instructions

Files: modify `scripts/release_smoke.py`; create `scripts/release_smoke_v9.py`, `docs/RELEASE_V9_GUIDE.md`, `docs/RELEASE_V9_NOTES.md`.

- [x] Let `run(verifier=verify_folder)` reuse the existing installed-app smoke with the strict v9 verifier. Validate a fresh empty AI status, six device/version entries, exact synthetic dataset selection, static finder/status assets, and missing-key failure persisted without successful history. Retain existing CSV, work-state, cooling replay and handoff checks.
- [x] Write installation and five-minute route around current UI: find device/version → local evidence → fault material → AI handoff/status → synthetic warning/replay. Explain source/limitations and that reports/feedback need a real successful model run.
- [x] Run the complete Python suite once after code edits; run Node tests only if frontend source changes. Build a candidate and verify before extracting into a new `.tmp/release-v9-clean-01` directory.

## Task 3: Concrete installable artifact

- [x] Run `setup_local.ps1 -PythonExecutable <existing 3.12 executable>` in the fresh extracted root; inspect completion and `pip check`. Do not alter or stop existing services.
- [x] Run packaged `scripts/release_smoke_v9.py` once in its new virtual environment; capture actual JSON output. This starts/stops an in-process application without a network listener or provider calls. Verify folder hashes afterward.
- [x] Promote the verified candidate bytes to the new final ZIP without rebuilding; record SHA256, file count, setup/smoke results and remaining gates in `docs/evaluation/2026-09-14-release-v9.{md,json}`.
- [x] Update README and project acceptance links to the current software artifact. Do not rewrite sealed v9 competition documents or claim a new video exists.

This plan closes the stale-software-package gap. The overall project remains active until the remaining external and business acceptance gates are met.

Completed: candidate bytes promoted unchanged after new-environment setup, pip check and one successful installed self-check. Python 356 passed. Final archive and exact results: `docs/evaluation/2026-09-14-release-v9.md`. Overall project remains active.
