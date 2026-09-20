# Synthetic Telematics Implementation Plan

**Goal:** Produce reproducible, engineering-constrained synthetic diesel excavator shifts for diagnosis development, not claims of field accuracy.

**Architecture:** Generate continuous physical states first, then sensor values, then cloud and cache observations. Keep physical truth and labels outside public observations. Split whole machine shifts, never adjacent rows.

**Tech Stack:** Python standard library, CSV/GZIP/JSON; existing pytest for independent invariants.

## Global Constraints

- Every file identifies synthetic origin. No real customers, serial numbers, fault-code assignments or claimed repair outcomes.
- One explicit reference brochure version; operating curves and temporal distributions are uncalibrated assumptions.
- No network/API/model calls during generation; no edits to existing app data or integration behavior.
- Dataset uses fixed simulation timestamps, never wall-clock time for elapsed calculations.

## Implementation

- [ ] Create `scripts/generate_diagnostic_dataset.py`: deterministic CLI `--output`, independent seed per shift, 8-hour sessions at 5-second intervals, 7 scenario classes, physical/sensor/cloud/cache layers, public observations, private truth, check oracle, hashes and dataset card.
- [ ] Create `tests/test_synthetic_dataset.py`: check fuel balance, operating-hour integration, power envelope, thermal continuity, movement only during travel, network outages preserving physical activity, held-out machine separation, and deterministic regeneration.
- [ ] Run `python -m pytest tests/test_synthetic_dataset.py -q`, then generate `data/synthetic_diagnostics_v1`, validate all shifts, and export a small plain CSV preview plus zip.

## Acceptance

Fuel change equals integrated burn; engine-off consumes no fuel; hydraulic output plus auxiliaries does not exceed mechanical shaft power; torque fits the reference maximum; counters monotonic; observed sample times never in future; missing messages do not rewrite physical truth; each split has distinct machines. Holdout exercises new seeds, not proven real-world generalization. Documentation must explain cadence and configuration are simulation choices, not guaranteed Trackunit field availability.
