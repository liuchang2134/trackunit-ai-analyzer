# Operating-state classification implementation plan

Goal: A runnable local learned work-state classifier with reproducible synthetic evaluation, then a clearly labelled UI demonstration.

Architecture: Derive noisy synthetic sensor observations from the simulator's physical channels. State labels are supervised targets only. Keep original independent episode train/validation/test split. Train a random forest baseline using current/past-only sensor features, export numeric trees as JSON; runtime inference does not load pickle or require scikit-learn.

Scope: digging, swing (loaded/return merged), dump, idle (warmup merged), travel, plus off. Inputs rpm, hydraulic pressure, flow, ground speed; these channels are NOT available in current Trackunit real import. No claim of a validated digital twin or field accuracy.

- [x] Build sensor/label export with fixed independent noise, explicit feature allowlist, inherited episode splits and input hashes.
- [x] Train fixed-parameter baseline, fixed0.65 abstention threshold; report validation/test confusion, macroF1, coverage, accepted accuracy and majority baseline. Do not tune against test.
- [x] Export numeric model; verify runtime matches training implementation and refuses missing/invalid signals.
- [x] Add read-only API and simulator playback UI, mark actual Trackunit capability unavailable.

References: https://scikit-learn.org/stable/modules/cross_validation.html (group-wise split), https://github.com/aeon-toolkit/aeon (time series classifier design; not installed). Use scikit-learn1.7.2 as optional training dependency, not a cloud service.

Checkpoint: run completed161280train/40320validation/40320test samples. Test accuracy.9004, macroF1.9078, accepted coverage.8985 and accepted accuracy.9348. Low dump/swing scores explicitly reported.200sample numeric export parity <1e-10;3 tests passed. Model card docs/WORK_STATE_MODEL.md. Next: API/UI and stress tests; do not apply to current real Trackunit channels.

Playback checkpoint: added sensor-only test-episode registry/replay endpoints with hash/schema/path/window checks, independent states page with seek/play/pause/source labels and sampled-state distribution. Browser loaded360points, seek120showed swing, seek103showed unknown(score.579), playback advanced and paused, leaving page stopped timer, changing episode cleared old results. Narrow view screenshot inspected. Full143tests passed before final nonfinite-source guard; final5route tests including NaN guard passed, JS syntax passed. Backend restarted with final guards. Stress evaluation remains open.

Stress checkpoint: scripts/stress_work_state.py evaluates frozen numeric model on all40320test points under baseline/missing pressure/additional noise/pressure freeze. All8064missing points unknown; addednoise acceptedaccuracy84.11%, highscore>=.9 error4.47%; freeze affectedcoverage41.18%. Baseline exactly reproduced previous coverage/acceptedaccuracy. Raw report051436Z and manual summary stored.3stress-transform/metric tests passed, JSsyntax passed after clarifying score label. No tuning on this held-out test set, no field reliability claim.
