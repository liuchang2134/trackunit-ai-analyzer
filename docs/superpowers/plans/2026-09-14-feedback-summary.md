# Feedback Summary Implementation Plan

> Execute inline under the user's existing authorization to complete the project.

**Goal:** Reject unsupported normal-counter claims and preserve the scope of operator feedback in local AI summaries.

**Architecture:** Extend the existing bounded health-claim validation and clarify feedback interpretation in the current system prompt. Retain original feedback as unverified evidence; do not rewrite saved historical reports.

**Tech Stack:** Python, pytest, local Ollama qwen3:8b.

## Constraints

No new dependency, cloud inference, fabricated inspection or confirmed diagnosis. A prompt change is not proof of semantic correctness.

## Explicit contradiction guard

Add app/feedback_validation.py with feedback_conflict(summary, evidence). Recognize reported visual observations in notes and reject known blanket denials of inspection; reject assertions of no sensor damage when notes explicitly say damage cannot be confirmed. Return the original note and conflicting clause to the bounded rewrite loop. Do not infer completion from check_text or not_observed alone. Tests in tests/test_feedback_validation.py cover remaining measurements, unrelated component inspection, uncertainty and absent feedback; integration tests cover successful rewrite and step-limit rejection. Keep raw local model outputs in a new evaluation file without overwriting prior experiments. This scoped guard does not validate arbitrary wording or all diagnostic conclusions.

## Steps

Follow-up implementation: add an `operator-feedback:<feedback_id>` entry per included saved feedback in app/report_facts.py. Preserve notes verbatim, observation timestamp and translated outcome label; explicitly state unverified operator source and that a negative observation does not exclude a fault. Test multiple records, English labels with Chinese original text, absent feedback and input immutability. Existing UI textContent and Markdown export consume these entries; verify both source paths and an actual generated report. This preserves evidence visibility, not AI semantic correctness.

- [ ] Add regression tests in tests/test_local_assistant.py for affirmative counter-normal claims and uncertainty statements. Use `agent.unsupported_health_claim(text)` with the actual failed Chinese phrase, an English equivalent, and negated versions.
- [ ] Extend the existing claim pattern in app/local_assistant.py to cover operating/idle hours and Chinese 工时、怠速时间、空闲时间 followed by normal/正常. Keep the existing negation handling and bounded retry.
- [ ] Explain in the system prompt that a selected check can contain multiple activities; notes describe the performed subset. Require summaries to distinguish reported observations from unperformed measurements and cite operator evidence when discussing it.
- [ ] Run `.tmp/venv/Scripts/python.exe -m pytest tests/test_local_assistant.py -q`, then the full suite. Replay the stored request linked to parent 34d055644d64526b9cae820a5066cfde1bc62eede734758b08803196bfec2ef2 through local investigate(), preserving decisions and final output for semantic review.
- [ ] Record actual results and remaining limits. Do not amend the historical report or overwrite the v4 release.
