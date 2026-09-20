# Inspection feedback and continuation

Goal: Save append-only inspection observations against an immutable diagnostic report and reuse them as unverified evidence in a follow-up analysis.

Reference: Atlas CMMS https://github.com/Grashjs/cmms work-order/history workflow (AGPL-3.0; no code copied, no dependency installed).

- [ ] Typed local feedback storage: observation time, outcome, notes, optional known check ID, original check text, report/machine IDs; content hash integrity.
- [ ] Read/write endpoints; reject unknown parent/check, future/naive times and cross-device continuation. Original report unchanged.
- [ ] History feedback editor and continuation action. Follow-up explicitly carries parent ID; last5 observations are labelled unverified, total count disclosed.
- [ ] Tests and actual local browser save/read/continue verification. No automatic fault closure, parts order or external write.
