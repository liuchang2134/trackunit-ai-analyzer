# Local engineering-machine assistant implementation plan

**Goal:** Deliver a sideloadable Chrome/Edge sidebar, local AI tool workflow, traceable risk checks and parts candidates, data import and bilingual report export beside an existing telematics platform.

**Architecture:** Existing FastAPI remains the local service. A separate extension uses explicit local-service access, never Trackunit secrets. A bounded Ollama tool loop queries evidence and a local catalog; deterministic validation enforces machine applicability and source references. Simulation stays visibly separate from real fleet data.

**Constraints:** No paid services; no fabricated real part numbers or measured performance; no equipment writes; no cloud model fallback; no remaining-life claims without labeled data.

## Deliverables and gates
- [x] Local Ollama installed, model downloaded and real inference tested on this PC.
- [x] Parts catalog JSON import with schema validation, model/serial applicability, citations, demo distinction, duplicate rejection, atomic storage; tests.
- [ ] Evidence tools for machine snapshot, time-series anomalies, fault events, parts search; timestamp-aware and missing-data-aware.
- [x] Local agent chooses tools, incorporates check results, produces source-linked explanations; tests cover unknown tools, missing AI, fabricated references and bounded iterations.
- [ ] Sidebar extension with device selection, AI conversation, evidence, parts candidates, imports and report downloads; verified in browser.
- [ ] Trackunit cached read-only adapter with verified snapshot, history and event capabilities; clearly expose inaccessible endpoints.
- [x] Repair date-sensitive baseline tests and hardcoded launch paths; run backend/frontend tests.
- [ ] Create deployment guide, reproducible demo, competition proposal aligned with delivered capabilities, and limitations/evaluation report.

## Current evidence
V2 authentication works and fleet page 1 returns 100 records. Assets v2 returned 401. Local GPU is RTX 5070 Laptop 8151 MiB. No fault/parts manuals supplied; catalog demonstration must be synthetic. Existing snapshot simulator is available but not real-world validated.


## 2026-09-14 implementation checkpoint
- Ollama 0.34.0 official portable runtime installed under C:/Users/liuch/.local/share/jilian/ollama. Authenticode status Valid. qwen3:4b pulled with digest verification, GPU inference works. Server is running loopback-only with OLLAMA_NO_CLOUD=1.
- Local assistant: app/local_assistant.py, app/api/routes_assistant.py, app/assistant_ui/. Catalog: app/parts_catalog.py. Extension: extension/.
- Backend running on port 8890. UI verified in Codex browser; actual model performed snapshot + faults tools, cited valid source IDs, reported insufficient evidence instead of a confirmed failure. Warm sample 3.7 seconds, NOT a benchmark.
- Initial model repeated tools and hit limit. Fixed with dynamically restricted action schema and explicit known-source list. Retest succeeded.
- Report export verified: C:/Users/liuch/Downloads/jilian-investigation.md (3183 bytes).
- 79 backend tests passed before dynamic-action refinement; 8 affected assistant/catalog tests passed after refinement. Frontend TypeScript check passed. Old baseline date-sensitive tests now use fixed mock clock / relative historical dates.
- DATA_SOURCE remains mock. Real Trackunit snapshot previously tested, but not yet cached into this sidebar workflow. No real catalog or manuals supplied.
- Still required: actual Chrome/Edge sideload verification, narrow viewport QA, historical telemetry and event APIs, risk trends and excavator operating-state model, reproducible synthetic-data replay, telemetry import, contextual platform device selection, guided-inspection evidence evaluation, bilingual testing, proposal rewrite and release packaging.
- Deployment instructions in docs/LOCAL_ASSISTANT.md and example demo catalog docs/examples/demo-parts-catalog.json.
- Windows Get-CimInstance may hang: one pending inspection was interrupted. Use Get-Process instead. Current server PID can be read from .tmp/assistant-backend.err.log; do not kill unrelated services.


## Time-window evidence checkpoint
- Added app/telemetry_evidence.py and local AI trends action. Computes operating/idle increments using ordered timestamps; rejects missing/future timestamps, conflicting duplicate observations, negative/reset/impossible counters. Idle share requires >=0.5 valid operating hours. 40% is explicitly an assumed screening threshold, not an OEM failure limit.
- Deduplicates fault code/time, distinguishes resolved/history from recent unresolved event records. No failure probability or remaining-life output.
- Fixed partial trackunit_cache falling back to mock fault/telemetry files. Missing real cache components now return empty lists.
- 86 backend tests passed. Real qwen3:4b run chose snapshot and trends, cited both, identified one-snapshot insufficiency and stale data. No valid time-series trend was invented.
- Tests validate unordered samples, conflicting duplicates, future records, reset counters, stale timestamps, repeated vs copied faults and source isolation.
- Still no historical data ingestion into sidebar: next implement isolated CSV/JSON datasets and synthetic episode replay, then integrate verified Trackunit history/events and finish extension QA.


## Isolated dataset import checkpoint
- Added app/local_datasets.py: validated normalized JSON/CSV, one-machine datasets, content-addressed atomic storage, no cache overwrite, source provenance, synthetic replay clock with future-record rejection.
- /assistant/datasets, /assistant/datasets/import and /assistant/datasets/import-csv wired to sidebar. Imported selection passes dataset_id to AI and uses only that dataset. Real imported datasets cannot use synthetic replay time.
- scripts/export_demo_dataset.py creates docs/examples/excavator-shift.json (114 public observation rows). Reads only public episode and telemetry; skips missing/unavailable samples and observations after decision time. No evaluator truth or labels.
- Entire backend suite: 94 passed. Browser file upload verified: selected imported simulated XE135U, 114 records, explicit synthetic badge. Local saved dataset ID 6f4ea773ed4f43af625372a634a2e0d307a081dd810e86ac646cd9ff8aa07684.
- AI snapshot tool shows latest 8 records and total count to avoid flooding 8k model context; trends computes over full dataset.
- Still pending end-to-end risk/parts evaluation, actual Chrome/Edge extension install QA, Trackunit historical/event endpoints, operating-state classification, updated competition artifacts and release packaging.

- Browser end-to-end imported 114 records, model selected snapshot+trends. First response overstated completeness and approximated duration incorrectly. Added explicit window_duration_hours/completeness/fault_coverage evidence, stronger model constraints and a separate deterministic metrics card. Real model retest correctly reported 1.7333h window/increment and 30.45% idle share with completeness not verified. Model prose remains advisory, not a verified conclusion.
- 18 affected dataset/trend/assistant tests passed after the evidence/UI refinement; complete suite had 94 passing before it. Server restarted for new code. Need continue risk UI narrow-layout QA and actual extension installation.

- UI rerun verified deterministic metrics card (1.7333h window, 1.7333h operating increment, 30.45% idle), explicit completeness limitation. Model next_checks invented normal idle <20%; added percentage-evidence check with rejection/retry and stronger prompt. 14 assistant/dataset tests passed including unsupported percentage rejection. Real retest no longer invented the 20% threshold. This is a partial output check, not general semantic entailment verification; continue checking suggested actions (model can still confuse no findings with event coverage).
- Backend restarted after this patch; existing browser report may be stale until rerun.

## Fault-to-parts demonstration checkpoint
- Added scripts/prepare_parts_demo.py, independent synthetic replay and docs/PARTS_DEMO.md. Catalog and replay installed locally without touching fleet cache.
- Actual HTTP investigation with local qwen3:4b chose faults -> parts -> snapshot, returned DEMO-BOOST-SENSOR via fault_code matching, serial_verified=false, and requested connector/wiring/measurement checks. Report explicitly called data artificial; no confirmed root cause. Private local result saved data/local/parts-demo-report.json.
- Full backend suite 104 passed, 6 dependency/lifecycle deprecation warnings. Tests include end-to-end isolated dataset/catalog matching and exclusion of demo catalog from real sources.
- Still pending: nonempty table browser QA, actual extension sideload, verified Trackunit history/events, wider AI evaluation, operating-state classifier and final competition package/proposal alignment.

## Live historical API verification
- 2026-09-14: AEMP selected XE55U operating-hour timeseries returned 36 records for requested Sep7–14 window; actual samples start Sep12. Idle timeseries succeeded with empty array. Asset-event read-only POST query returned401, no retries. Private raw responses/capability statuses under ignored data/local/trackunit-probe.
- Added app/aemp_history.py exact-timestamp counter normalizer. Preserves zeros, missing idle remains null, rejects conflicting same-time values. Three tests passed. Imported36 actual records as isolated user_supplied dataset named Trackunit 实测历史 · XE55U. Source document records idle absence and event401; fault coverage unknown.
- Remaining integration work: current trend engine requires idle for operating counter intervals; must independently calculate operating increments without implying idle ratio coverage. Sidebar actual-source label remains imported/unverified. Need reusable history fetch adapter and visible capability status, not just manual probe.

## Independent operating-counter analysis
- Operating increments no longer require idle counters. Idle-only timestamps do not break operating series. Invalid/reset idle counters do not discard independently valid operating increments. Partial paired idle coverage yields no idle ratio. Added four regression tests;26 affected tests pass.
- Actual36-record XE55U data:20 accepted intervals,15 rejected, accepted increments sum3.9h; idle unknown. This is partial accepted-interval sum, not full-window total. UI and model prompt now explicitly identify this distinction. Need investigate source counter granularity/timestamp semantics before relaxing consistency limits; no inferred calibration applied.

## Integration capability UI checkpoint
- Added typed public-safe last-verification endpoint and data-management table. Shows operating36, idle empty0, events unauthorized401 with unknown event count, timestamp and non-live/single-sample limitation. Reads a separate local status file, not private raw API payloads.
- Two tests pass: missing/corrupt report fails unknown; private extra fields omitted and old report marked stale. Node syntax passed. Backend restarted, actual browser endpoint/render verified (including narrow layout). Still requires reusable explicit probe/sync action and tied per-dataset capability metadata.

## Reusable history sync command
- Added scripts/sync_trackunit_history.py and docs/TRACKUNIT_HISTORY_SYNC.md. Explicit single-equipment AEMP sync with timezone/max14day/future validation, encoded OEM identifier, retries0, persistent15min attempt cooldown, per-device exclusive lock, exact timestamp normalization, partial-channel preservation and atomic public-safe status update. Events explicitly not_checked.
- Eight sync/normalizer tests pass; CLI help verified. No extra live request made this checkpoint, preserving upstream quota after earlier confirmed historical read. New CLI still needs its own live end-to-end run and UI trigger. No completion claim for full Trackunit adapter.

## Startup delivery checkpoint
- Added scripts/check_local_runtime.py; checks Python>=3.11, imports, loopback Ollama and configured model without Trackunit calls or secrets. Live result ready=true.
- Startup now waits boundedly for Ollama, checks prerequisites, detects/reuses this backend on8890, and prefers .venv with existing .tmp/venv compatibility. Actual start_local.ps1 while backend running returned successfully without port conflict. Updated extension fallback and setup instructions. Default model aligned to qwen3:4b.
- No cold-start test on clean machine yet. Live sync CLI remains pending15min upstream cooldown after earlier probe; no sleeping or repeated requests used to bypass it.

## Proposal alignment checkpoint
- Rewrote docs/机联智检_完整参赛Proposal.md around existing-platform sidebar + local AI + evidence-based risk checks + parts candidates. Preserved early draft as docs/机联智检_早期主动排查方案_存档.md.
- Includes delivered/pending functionality matrix, simulation vs actual data, phased fault prediction, evaluation, deliverables, zero incremental cash constraint, trial/commercial hypotheses and IP/submission caveats. Removes obsolete exclusion of parts recommendations and stale planned status for implemented imports.
- Markdown coverage check passed. Existing DOCX/PDF still represent the previous draft; must regenerate and visually verify before presenting as updated Word proposal. No claim of final submission-ready package.

## Updated proposal document outputs
- Regenerated latest proposal DOCX and PDF (7 pages), fixed UTF8-BOM title parsing and updated document metadata to local AI/parts scope.
- Required render_docx.py attempted; failed because soffice.exe absent. Used installed native Word COM PDF export and bundled pdf2image/Poppler for page PNGs instead. All7 pages visually inspected: legible headings, repeated table header, no overlap/clipping. Verified Title style and key scope terms in PDF text.
- Final docs/机联智检_完整参赛Proposal.docx and .pdf now match latest Markdown. Still working draft, not final competition package or performance certification.

## Persistent investigation records
- Added local content-addressed immutable report/request storage, list/read endpoints, history navigation and JSON download. Stores user question/observations with original source evidence. Failed storage explicitly reported without discarding analysis. Integrity/path traversal/immutability tests included;24 affected tests passed.
- Actual local model via HTTP completed, record_saved true, readback matched question/observations/summary. Browser refreshed and showed saved record/summary/export control.
- Live test returned no parts candidate despite user asking to match parts. Need inspect trace and add task-completion enforcement; a generated answer alone must not count as fulfilling requested investigation. No prediction accuracy claim.

## Required investigation tasks
- Added request.task enum and UI task selector (comprehensive/parts/trends/overview/auto). Required queries gate finish; requested trends/parts must cite returned tool evidence or an actual catalog candidate. Auto mode uses limited keyword hints, explicit task mode controls behavior. Task stored in historical request/report.
- Regression tests prove early finish cannot bypass parts and legitimate catalog-level references accepted. Initial live stricter guard incorrectly rejected catalog reference; corrected and real local retest completed snapshot/faults/parts with DEMO-BOOST-SENSOR.17 assistant tests passed. Backend restarted for final patch.
- Still does not prove all natural-language obligations fulfilled or semantic correctness; auto keyword intent limited and comprehensive mode needs broader scenario evaluation.

## Live reusable sync verification
- After honoring15min cooldown (seeded from original manual probe), ran actual sync_trackunit_history.py Sep7–14 query at04:40UTC. Success:36 operating samples, empty idle, events not_checked; dataset saved and visible through live /assistant/datasets, status endpoint updated.
- TrackunitError now carries status_code; sync distinguishes401/403 unauthorized,429 rate_limited and general error without raw response leakage. Full suite126 passed with6 deprecation warnings.
- CLI independent live gate now passed. UI trigger, extension sideload, classification/evaluation and release packaging remain pending.

## UI history sync integration
- Moved reusable sync logic to app/history_sync.py; CLI imports it. Added allowlisted local source registry, bounded source_id/days endpoint and UI source/day selectors. Successful sync selects imported dataset, status refreshed; no arbitrary URL/path from browser.
- Registered existing authorized snapshot locally.12 relevant sync/status/route tests passed, Node syntax passed. Live browser displayed source and1/7/14day options; click returned expected15min cooldown without another provider request. Shared underlying sync previously passed live36-record CLI run; UI successful click branch still needs live or controlled end-to-end verification.
- No goal completion: actual extension install, operating-state recognition, rigorous evaluation and release package remain.

## Local model smoke evaluation and recovery
- Added selected-case CLI and raw decision/control capture to evaluator; synthetic-only isolated files, no production catalog mutation. Preserved failed runs.
- Reproduced cumulative-counter ratio hallucination and rejected-answer repetition. Internal correction messages are now system instructions, identify invalid numbers; rejected drafts excluded from future context, raw outputs retained by evaluator.
- Final four-case run docs/evaluation/local-assistant-20260914T045103Z.json structurally passed;25 relevant tests passed. Backend restarted and health ok.
- Manual review docs/evaluation/2026-09-14-manual-review.md identifies unsupported engineering suggestions, replay/current-state conflation and weak scenario wording. These semantic gates remain open; not a validated diagnostic product or goal completion.

## Source-backed actionable checks
- Added check_options source choices and model-selected next_check_ids; unknown IDs rejected, server renders exact rule/catalog text with evidence/provenance. UI displays check sources; old next_checks API field remains generated strings.
-133 tests passed,4 actual local model cases structurally passed. Live browser comprehensive report completed4tools, saved history and displayed metrics/source metadata/parts table.
- Summary semantics remain failing: wrong event interval and fault-code/component confusion; selected catalog-check coverage weak. Detailed evidence in grounded-checks plan and manual review. Project still requires semantic reliability, classification, extension integration, final proposal alignment and release materials.

## Event facts and requested catalog coverage
- Added deterministic fault event chronology with cutoff/machine/timestamp handling, code+timestamp uniqueness, status conflicts and explicit unknown independent failure count. UI displays event table with calculated span, source and limits.
- Requested parts analyses must select a matched catalog procedure when one exists.136 tests passed; local4case eval045712Z passed structural gates; browser comprehensive run displayed25min and exact matched catalog instruction.
- Free-text summary still fails some semantic gates (cumulative counter labels, machine model vs sensor model, internal ID leakage). Do not claim diagnostic reliability. Next work should compare a stronger local model or redesign structured factual interpretation rather than endless prompt-only patches.

## Measured local model upgrade
- Downloaded official qwen3:8b; Q4_K_M,5.23GB artifact. Actual runtime6.19GB GPU residency at8192context. Added eval --model and artifact digest metadata.
- Identical-input/code comparison4b045945Z vs8b050151Z: both4/4 structure;8b avoids observed single-sample counter mislabeling, more concise missing-catalog wording. Extra8b one-sample/comprehensive050243Z passed,25min correct and matched catalog procedure selected. Manual report records remaining defects and unequal loading conditions.
- Default8b in code, .env.example and ignored local setting; setup docs updated.21 relevant tests passed; restarted backend, readiness true; live HTTP confirmed8b completed/saved/one catalog candidate/two sourced checks.
- Still not goal complete: need expanded semantic eval, classification, real extension integration, feedback/export/offline packaging and final competition deliverables. Proposal model references need refresh before final export.

## Synthetic operating-state classifier baseline
- Added optional training dependency, sensor-only observation export and RandomForest64/depth10 learner over12 current/past features. Train/validation/test original episode split28/7/7; no IDs, state labels, scenarios or future samples as features.
- Generated numeric JSON forest1.66MB and evaluation/model card. Test40320samples accuracy90.04%, macroF1.9078; confidence-score threshold.65 leaves10.15%unknown. Dump/swing weakness and simulator simplifications explicitly documented; no field accuracy claim.
- PurePython inference matches sklearn on200heldout samples (<1e-10).3feature/invalidinput regression tests passed. API/UI playback and noise/missingness stress tests remain; current real Trackunit data lacks required detailed channels.

## Work-state demo API and UI
- Read-only registry/replay uses test sensor files only, validates fixedschema/modelhash/sourcepath/window; no hidden truth or real-device claims. New independent 工况回放 page with30min window,20xplayback, seeking, sensor table, unknown states and sample distribution.
- Live browser verified360pointload, seek/play/pause, unknown.579, source label separation, navigation stop and episode-change clearing.143fulltests before final NaN guard;5finalroute tests passed and JS syntax passed. Finalbackendrestarted.
- Next remaining scope: stress tests; real extension/platform context integration; feedback/report packaging; broaderAIsemantic evaluation and final competition artifacts. This UI completion does not complete overall goal.

## Frozen-model work-state stress evaluation
- Evaluated baseline and three sensor degradations against held-out40320samples, no retraining/threshold changes. Baseline matches prior report; all8064missingpressure samplesunknown, but short-window recovery and addednoise still produce highscore errors.
- Addednoise acceptedaccuracy84.11%, highscore>=.9 error4.47%; freeze affected-only coverage41.18%. Saved complete report/input/model/code hashes and error examples; docs/evaluation/2026-09-14-work-state-stress.md records scope and denominators.
- UI score caption now explicitly says score is not accuracy and high scores can be wrong.3tests passed, JSsyntax passed. Continue extension integration, inspection feedback, deliverable packaging and broadersemantic/real-data validation; goal remains incomplete.

## Inspection feedback and extension context
- Inspection feedback completed with append-only local records, source/check/time validation, original dataset/device scoping and latest-five continuation. Live browser and qwen3:8b followed a synthetic note, cited operator:feedback and saved linked report. Full Python suite155passed.
- Extension0.2.0 reads activeTab URL only and transfers validated Trackunit asset UUID to local iframe; no DOM or credentials. Current Trackunit asset list confirmed ID alignment. Browser local URL handoff verified ambiguous datasets require selection and unknown IDs do not fallback to mock.
- Five Node tests cover parser, denied paths, timeout/retry and trusted readiness messages. Whitelisted extension ZIP built; actual Edge installation and side-panel execution pending action-time user confirmation for new activeTab access. Final competition artifacts and broader semantic/release validation still incomplete; goal remains active.

## Real snapshot normalization repair
- Fixed zero/false values, metadata ID casing, string/object locations, and display-name-as-serial fallback. AEMP fields now split by their own aware timestamps; no GPS/update-time borrowing. Both sync and live read paths ingest the expanded series. Latest known telemetry observation updates last_seen without metadata modification times.
- Offline authorized 100-equipment snapshot verified193rows,50multi-time equipment,100aligned asset IDs and13preservedzeros. Raw input remains private and unchanged. Existing persisted caches are not silently migrated.
- Full159tests passed before final last_seen correction; final12targeted tests including that new case passed. Backend restarted. Actual plugin install still pending user confirmation; continue competition artifact alignment and remaining semantic/release validation.

## Competition proposal aligned with implementation
- Updated full Chinese proposal Markdown/DOCX/PDF to default8b, measured model comparison, six-state synthetic classifier with40320heldouts, coverage/abstention and stress failures, persistent feedback, extension0.2.0 context mapping and verified CLI sync.
- Explicitly retains pending installed-sidepanel validation, successful UI sync gate, bilingual/semantic evaluation, real manuals/field validation, slides/video and overallrelease. No real predictive-accuracy, revenue, IP or fieldcase claims added.
- DOCX builder now keeps table header with firstdata row to avoid isolatedheader. render_docx.py attempted but LibreOffice unavailable; exported via native Word COM and rendered8PDFpages with Poppler. All8pageimages inspected; finalheaders/tables/body clear, no clipping or overflow. Final outputs docs/机联智检_完整参赛Proposal.docx and .pdf. Goal remains active.

## Local release and extracted-package verification
- Added setup_local.ps1, fixed runtime/core default8b consistency, explicit build_release.py and verify_release.py. Built1.76MB release with105files+manifest, excludes credentials/private data/runtime weights, anonymizes public base fixtures. Package configuration defaults mock/ollama_local/autosyncoff.
- Fresh extracted checkout passed model/data imports, isolatedDB, syntheticdemo install,7testepisodes, actual12sample replay and8b3query/1candidate/savedreport. Existing dependencies/runtime reused; newPC, full offline and installedextension gates remain open.
- Two initial model-smoke failures exposed fabricated method-name citation and anchored tool-selection prose. Added dynamic JSONSchema enum IDs and retained only action/component for tool decisions; rebuiltpackage passed.164tests passed. Semantics still imperfect (repeated suggestions, vague replay-time claim), full evaluation still required.
- Evidence and exactarchivehash in docs/evaluation/2026-09-14-release-smoke.md. Goal remains active; presentation/video/export/offline/extension and semantic validation unfinished.
