# Event facts and catalog-check coverage

Goal: Compute event chronology before AI interpretation, expose it in the UI and ensure requested parts investigations include matched source procedures.

- [x] app/fault_evidence.py: timezone-aware cutoff/machine filtering, code+time grouping, status conflicts, exact minute spans; no inferred independent failures.
- [x] app/local_assistant.py: use computed event evidence, concise plain-text summary instructions, require a matched catalog check when available for requested parts task.
- [x] app/assistant_ui/app.js: event table with source, distinct timestamp count and first-to-last span; limitations alongside data.
- [x] Unit/regression verification plus actual local evaluation and browser check.

The deterministic event fields do not prove that all AI prose obeys their semantics. Tests must distinguish structured facts, catalog coverage and free-text review. No claim of calibrated failure probability or remaining life.

Evidence:136 tests passed,6 existing deprecation warnings. Final4case run045712Z structurally passed, correct-model catalog check selected, all event cases25min. Browser comprehensive run returned4tools, persisted report, visible25min event row and verbatim catalog check/provenance. Narrow table inspected without clipping at current width.

Open defects: browser summary mislabels XE135U as sensor model and prints internal IDs; one-sample evaluation still mislabels cumulative counters. See manual review. Need model comparison and/or structured factual interpretation; not a full semantic completion.
