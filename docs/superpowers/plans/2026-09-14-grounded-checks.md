# Source-backed check selection

Goal: Prevent invented component procedures in the actionable next-check list; preserve AI tool choice, explanation and evidence-led selection.

Architecture: app/check_options.py produces bounded choices from executed tool evidence and matched catalog records. Decision.next_check_ids selects those choices. Server resolves IDs to exact texts and metadata; unknown IDs rejected. Report.next_checks remains a string list for existing consumers and adds check_recommendations metadata. This does not validate every free-form summary claim.

- [x] Implement source choices with distinct application-rule / user-supplied / demo provenance, replay-aware wording, missing-data and unmatched-catalog requests.
- [x] Model chooses IDs; no rewritten procedures in next_checks; UI shows provenance/document/evidence.
- [x] Regression tests for unknown check IDs, verbatim catalog text, empty/missing evidence and replay wording.23 focused tests passed; JavaScript syntax passed.
- [x] Run four real local-model cases, inspect natural-language summary and selected check sources.
- [ ] Restart backend and inspect browser-generated report, metadata, export compatibility.

Remaining: actual manual corpus not supplied; imported catalog text remains unverified. Summary may still invent suggestions despite the prompt; this gate needs separate semantic assessment. English mode preserves original catalog text deliberately rather than silently translating repair procedures. No OEM certification or predictive accuracy claim.

Verification checkpoint: all133 tests passed (6 existing deprecation warnings). Four-case actual local run045347Z has valid selected-check source references. Restarted backend, ran browser comprehensive simulation:4tools, persisted report, structured metrics, check provenance and parts table visibly rendered in narrow viewport. Export compatibility retains next_checks and full report JSON; actual download still unverified.

Browser summary review found unsupported24-minute interval (actual timestamps25min), conflated fault code with component ID, and long Markdown-like prose. These are open semantic/presentation defects; source-backed check list does not fix free-form summary. Model-selected checks also skipped the available catalog procedure; follow-up should make requested catalog coverage explicit.
