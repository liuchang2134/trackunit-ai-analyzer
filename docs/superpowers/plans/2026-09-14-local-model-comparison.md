# Local model comparison

Goal: Compare qwen3:4b and qwen3:8b on identical synthetic workflows and judge semantic defects, not only structural pass rate.

Constraints: local Ollama only; no paid/cloud inference, no upload of machine data. Keep production default until measured evidence supports changing it. Official Qwen3/Ollama8b listing checked: Apache-2.0, Q4_K_M, approximately5.2GB. Disk free582GB.

- [x] Download official qwen3:8b with local Ollama.
- [x] Add evaluation CLI model override and model artifact metadata; retain inputs, code hashes and raw decisions.
- [x] Run matching/incorrect model, empty catalog and one-sample cases with same code and constraints.
- [x] Review cumulative counters vs deltas, device vs component identifiers, replay vs live wording, applicability/diagnostic certainty and selected procedures.
- [x] Record decision and limitations. Model change is not evidence of field diagnostic accuracy.

References: https://ollama.com/library/qwen3:8b ; https://github.com/QwenLM/Qwen3

Decision and evidence: docs/evaluation/2026-09-14-model-comparison.md.8b improved observed semantic failures and passed additional single-sample/comprehensive cases. Updated code default, .env.example, ignored local model setting and setup docs.21 affected tests passed; backend restarted; readiness true; live HTTP returned qwen3:8b/completed/history_saved true/one demo candidate/two sourced checks. Broader semantic/field validation and remaining project scope still open.
