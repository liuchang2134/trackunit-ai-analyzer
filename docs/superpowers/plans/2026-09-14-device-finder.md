# Device Finder Implementation Plan

> **For agentic workers:** Execute inline in the existing workspace. Optional superpowers execution skills are unavailable; preserve prior packages, private configuration and data. Do not commit, publish, restart services or install browser extensions.

**Goal:** Find a device/data version by identifier or model, distinguish imported measurements from simulations, prioritize supplied unresolved fault records, and enter the existing investigation without losing device context.

**Architecture:** A read-only local index loads each fleet source once and each import once, summarizes latest supplied status per fault code at its cutoff, and exposes `/assistant/device-index`. A native dialog filters and paginates this index while preserving the original select control and strict platform-asset matching. Existing diagnosis, chart and draft state transitions remain authoritative.

**Tech Stack:** FastAPI, Python, existing vanilla JavaScript/CSS, native dialog, pytest and Node tests. No new dependencies or provider calls.

## Constraints
- Gemini and XGSS success gates remain outstanding. Search must never call or synchronize external services.
- Empty/unreadable fault records do not imply normal equipment. Summaries describe supplied records, not health or independent failure counts.
- Use only fault timestamps at/before the applicable cutoff; a later resolved record supersedes an earlier open record. Same-time status or severity conflicts remain explicit.
- Keep dataset and fleet selection IDs separate, including multiple versions for the same serial number. Platform hashes can only select matching real machine IDs.
- Filtering must not change the current device. Choosing an exact result follows `selectMachine()`; closing/Escape restores focus and preserves drafts.
- Versioned v8 ZIP remains immutable. Update development build and document the difference.

## Task 1 — Trustworthy index
Files: `app/device_index.py`, `app/api/routes_assistant.py`, `tests/test_device_index.py`.

Interfaces:
```python
summarize_faults(machine_id, faults, cutoff) -> dict
device_index() -> dict  # data_source, devices, warnings, as_of, ai_used=False, upstream_sync_performed=False
```
Each device retains machine fields and selection_id; imports retain dataset_id/name/provenance/sample_count/replay_at/cooling_reference. `fault_summary` contains state, unresolved_codes, conflicting_codes, highest_severity, latest_record_at, valid_records and excluded_records.

- [x] Test resolved-after-open, duplicate timestamps, status/severity conflicts, other-machine/invalid/future exclusions and no-records behavior.
- [x] Implement deterministic latest-per-code aggregation, using `timestamp()`; no existing heuristic risk-level labels.
- [x] Test/load each local source once, keep partial imports if another is corrupt, expose warnings without private paths, return no-store route response.
- [x] Run `.tmp/venv/Scripts/python.exe -m pytest tests/test_device_index.py -q` and verify no-network route behavior.

## Task 2 — Find and select a device
Files: `app/assistant_ui/device-finder.js`, `app/assistant_ui/app.js`, `app/assistant_ui/index.html`, `app/assistant_ui/style.css`, `tests/device_finder.test.cjs`.

Interfaces:
```javascript
DeviceFinder.filter(devices, {query,source,attention,sort,platformId}) // pure, stable, does not mutate
DeviceFinder.faultLabel(summary) // concise record-based labels
openDeviceFinder() // native dialog; selection remains unchanged until explicit choice
```

- [x] Test case/Unicode/whitespace-normalized multiword search, source filtering, exact platform matching, stable severity/date sorting and duplicate-version retention.
- [x] Add native dialog with labeled search/source/sort/attention controls, clear filters, result count, explicit data source/version, latest fault status/time, and 20-result pagination.
- [x] Change refresh to consume local index; preserve selection across refresh and platform hash rules. Lock finder during AI analysis. Add selected-record summary with a direct jump to fault records.
- [x] Add responsive layout and keyboard focus treatment using current visual styles. Empty matches provide a clear reset action; unreadable data warnings stay visible.
- [x] Run Node tests and JavaScript syntax check; update backend build and hashed assets.

## Task 3 — Actual interaction and handoff
Files: `docs/evaluation/2026-09-14-device-finder.md`, screenshots in `docs/evaluation/ux-20260914/device-finder/`, acceptance/README/open-source reference notes.

- [x] Capture current screen and verify the device lookup limitation before edits.
- [x] Reload existing 8892 tab. Verify search by model and serial, simulated/real filtering, unresolved-record filter, empty/reset, exact version choice and draft restoration.
- [x] Verify platform hash with no match never exposes unrelated simulated devices; return to normal page afterward.
- [x] Verify Escape/focus and desktop/narrow layout; screenshot accepted states and inspect files.
- [x] Run relevant regression suite, record evidence and update current status. Preserve all outstanding whole-project gates.

Reference: Traccar Web MainToolbar and DeviceList official sources inspected 2026-09-14. Adopt search/filter/order and compact device rows; implement independently without copying source or adding its framework.

## Result

Development build `20260914.10-device-finder` verified on existing port 8892. Python 342 and Node 22 tests passed; actual search, filter, version selection, draft isolation/restoration, fault jump, platform no-match, Escape and desktop/narrow flow verified. No provider calls. More-than-20-result pagination has not been exercised in the actual browser and remains explicit follow-up coverage; the implementation limits each page to 20. Evidence: [device finder](../../evaluation/2026-09-14-device-finder.md). Overall project goal remains active.
