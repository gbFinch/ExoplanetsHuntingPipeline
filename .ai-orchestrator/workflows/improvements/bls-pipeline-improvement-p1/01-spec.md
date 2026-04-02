---
agent: spec
sequence: 1
references: []
summary: "Specification for seven P1 improvements (R7–R13) to the Exohunt BLS transit-search pipeline: bootstrap FAP estimation, expanded alias ratios, secondary eclipse check, phase-fold depth consistency, configurable vetting/parameter constants, enhanced diagnostic plots, and iterative transit masking. All changes extend the existing codebase with backward-compatible config, new vetting fields, and opt-in processing modes."
---

## Overview

Exohunt is a Python 3.10+ pipeline for ingesting, preprocessing, and transit-searching TESS light curves using Box Least Squares (BLS). The P0 fixes (R1–R6) addressed SNR computation, odd/even handling, preset correctness, normalization safety, plot redesign, and per-sector refinement. This specification defines seven P1 improvements (R7–R13) that add false-alarm probability estimation, additional vetting checks, configurable constants, richer diagnostic plots, and an optional iterative masking mode. Each improvement is independently deployable and backward-compatible with existing configuration files.

## Functional Requirements

**R7 — Bootstrap FAP Estimation**

- FR-1: The system MUST add a `fap` field (type `float`) to the `BLSCandidate` dataclass, defaulting to `float("nan")`.
- FR-2: The system MUST add a `compute_fap` field (type `bool`, default `False`) to `BLSConfig`.
- FR-3: When `compute_fap` is `True`, the system MUST compute false-alarm probability for each candidate by performing N=1000 bootstrap iterations (shuffle flux values, run BLS, record max power), then setting `fap` = fraction of bootstrap max-powers ≥ candidate's observed power.
- FR-4: When `compute_fap` is `False`, the system MUST set `fap` to `float("nan")` for every candidate.
- FR-5: The bootstrap iteration count MUST be configurable via `bls.fap_iterations` (default 1000) in the TOML config.

**R8 — Add Missing Alias Ratios**

- FR-6: The system MUST add ratios `2.0/3.0` and `3.0/2.0` to the `ratios` tuple in `_alias_harmonic_reference_rank()`, making the full set: `(0.5, 2.0, 1.0/3.0, 3.0, 2.0/3.0, 3.0/2.0)`.

**R9 — Secondary Eclipse Check**

- FR-7: The system MUST add a `_secondary_eclipse_check()` function to `vetting.py` that measures flux depth at phase 0.5 ± duration/2 relative to out-of-transit baseline.
- FR-8: The system MUST add `pass_secondary_eclipse` (bool) and `secondary_eclipse_depth_fraction` (float) fields to `CandidateVettingResult`.
- FR-9: When secondary depth > configurable fraction (default 0.30) of primary depth, the system MUST set `pass_secondary_eclipse=False` and append `"secondary_eclipse"` to `vetting_reasons`.
- FR-10: When secondary depth data is insufficient (fewer than 5 in-eclipse or 10 out-of-eclipse points), the system MUST set `pass_secondary_eclipse=True` and `secondary_eclipse_depth_fraction=float("nan")`.
- FR-11: The `vetting_pass` overall flag MUST incorporate `pass_secondary_eclipse` (AND with existing checks).

**R10 — Phase-Fold Depth Consistency Check**

- FR-12: The system MUST add a `_phase_fold_depth_consistency()` function to `vetting.py` that phase-folds at the candidate period, splits observations into first-half and second-half by time, and measures in-transit depth in each half.
- FR-13: The system MUST add `pass_depth_consistency` (bool) and `depth_consistency_fraction` (float) fields to `CandidateVettingResult`.
- FR-14: When the absolute difference between half-depths divided by the maximum half-depth exceeds a configurable threshold (default 0.50), the system MUST set `pass_depth_consistency=False` and append `"depth_inconsistent"` to `vetting_reasons`.
- FR-15: When either half has insufficient data, the system MUST set `pass_depth_consistency=True` and `depth_consistency_fraction=float("nan")`.
- FR-16: The `vetting_pass` overall flag MUST incorporate `pass_depth_consistency`.

**R11 — VettingConfig and ParameterConfig in Config Schema**

- FR-17: The system MUST add a `VettingConfig` dataclass with fields: `min_transit_count` (int, default 2), `odd_even_max_mismatch_fraction` (float, default 0.30), `alias_tolerance_fraction` (float, default 0.02), `secondary_eclipse_max_fraction` (float, default 0.30), `depth_consistency_max_fraction` (float, default 0.50).
- FR-18: The system MUST add a `ParameterConfig` dataclass with fields: `stellar_density_kg_m3` (float, default 1408.0), `duration_ratio_min` (float, default 0.05), `duration_ratio_max` (float, default 1.8).
- FR-19: The system MUST add `vetting` and `parameters` fields to `RuntimeConfig`.
- FR-20: The system MUST add `[vetting]` and `[parameters]` sections to `_DEFAULTS` with the current hardcoded values.
- FR-21: The system MUST update all three preset TOML files to include `[vetting]` and `[parameters]` sections.
- FR-22: The system MUST update `resolve_runtime_config()` to parse and merge these new sections.
- FR-23: The system MUST replace the six hardcoded constants in `pipeline.py` (lines 110–115) with references to `RuntimeConfig.vetting.*` and `RuntimeConfig.parameters.*`.
- FR-24: Existing TOML config files without `[vetting]` or `[parameters]` sections MUST continue to work, with defaults applied.

**R12 — BLS Diagnostic Annotations**

- FR-25: The system MUST add SNR text annotation on the periodogram plot at the peak power location.
- FR-26: The system MUST add a transit box-model overlay on the phase-fold plot (flat baseline with rectangular dip at transit phase/duration).
- FR-27: The system MUST add an odd/even transit depth comparison subplot to the diagnostic figure.
- FR-28: The system MUST add a candidate parameter text box (period, depth, duration, SNR, vetting status) to the diagnostic figure.
- FR-29: The `save_candidate_diagnostics()` function signature MUST accept additional parameters for vetting results and parameter estimates needed to render the new annotations.

**R13 — Iterative Transit Masking**

- FR-30: The system MUST add a config flag `bls.iterative_masking` (bool, default `False`).
- FR-31: When `iterative_masking` is `True`, the pipeline MUST: (1) flatten without masking, (2) run BLS, (3) mask in-transit points from top candidate, (4) re-flatten masked light curve, (5) re-run BLS on re-flattened data.
- FR-32: Candidates from the second BLS pass MUST replace the first-pass candidates.
- FR-33: When both `iterative_masking` and `compute_fap` are enabled, FAP MUST be computed on the final (post-masking) BLS run only.

## Non-Functional Requirements

- NFR-1: Bootstrap FAP (R7) with N=1000 MUST complete in under 60 seconds per candidate on a modern laptop (single-core).
- NFR-2: All new config fields MUST have defaults matching current hardcoded values, ensuring zero behavioral change for users who do not modify their config.
- NFR-3: Each fix (R7–R13) MUST be independently deployable — no fix may depend on another being present for the code to function correctly.
- NFR-4: No new dependencies beyond the existing set (numpy, matplotlib, astropy, lightkurve, pandas).
- NFR-5: All new public functions and dataclass fields MUST have docstrings or inline comments explaining their purpose.
- NFR-6: Iterative masking (R13) MUST NOT exceed 2.5× the runtime of a single BLS pass.

## Acceptance Criteria

- AC-1 (FR-1, FR-2, FR-4): Given `compute_fap=False` (default), when `run_bls_search()` returns candidates, then every `BLSCandidate.fap` is `float("nan")`.
- AC-2 (FR-3, FR-5): Given `compute_fap=True` and `fap_iterations=100`, when `run_bls_search()` returns candidates, then every `BLSCandidate.fap` is a float in [0.0, 1.0].
- AC-3 (FR-6): Given two candidates where one has period = 2/3× the other's period, when vetting runs, then the weaker candidate is flagged as `alias_or_harmonic_of_rank_N`.
- AC-4 (FR-7, FR-8, FR-9): Given a candidate with secondary eclipse depth > 30% of primary depth, when vetting runs, then `pass_secondary_eclipse=False` and `vetting_reasons` contains `"secondary_eclipse"`.
- AC-5 (FR-10): Given a candidate with insufficient secondary eclipse data, when vetting runs, then `pass_secondary_eclipse=True` and `secondary_eclipse_depth_fraction` is NaN.
- AC-6 (FR-12, FR-13, FR-14): Given a candidate where first-half transit depth differs from second-half by >50%, when vetting runs, then `pass_depth_consistency=False` and `vetting_reasons` contains `"depth_inconsistent"`.
- AC-7 (FR-15): Given a candidate with insufficient half-data, when vetting runs, then `pass_depth_consistency=True` and `depth_consistency_fraction` is NaN.
- AC-8 (FR-17–FR-24): Given a TOML config file without `[vetting]` or `[parameters]` sections, when `resolve_runtime_config()` runs, then `RuntimeConfig.vetting` and `RuntimeConfig.parameters` are populated with default values.
- AC-9 (FR-23): Given a config with `vetting.min_transit_count=5`, when the pipeline runs vetting, then the minimum transit count threshold is 5 (not the old hardcoded 2).
- AC-10 (FR-25–FR-29): Given a candidate with vetting results, when `save_candidate_diagnostics()` runs, then the periodogram PNG contains SNR text, the phase-fold PNG contains a box-model overlay, an odd/even subplot is present, and a parameter text box is present.
- AC-11 (FR-30, FR-31, FR-32): Given `iterative_masking=True`, when the pipeline runs BLS, then two BLS passes occur and the final candidates come from the second pass.
- AC-12 (FR-33): Given both `iterative_masking=True` and `compute_fap=True`, when the pipeline runs, then FAP is computed only on the second-pass BLS results.
- AC-13 (NFR-2, FR-24): Given the three existing preset TOML files, when loaded, then they produce `RuntimeConfig` objects with valid `vetting` and `parameters` fields matching the current hardcoded defaults.
- AC-14: All existing tests pass without modification after all changes are applied.

## Scope

- Adding `fap` field and bootstrap computation to `bls.py`
- Adding `compute_fap` and `fap_iterations` to `BLSConfig`
- Adding `2/3` and `3/2` ratios to alias check in `vetting.py`
- Adding `_secondary_eclipse_check()` and `_phase_fold_depth_consistency()` to `vetting.py`
- Adding `pass_secondary_eclipse`, `secondary_eclipse_depth_fraction`, `pass_depth_consistency`, `depth_consistency_fraction` to `CandidateVettingResult`
- Adding `VettingConfig` and `ParameterConfig` dataclasses to `config.py`
- Adding `[vetting]` and `[parameters]` to `_DEFAULTS` and all three preset TOMLs
- Updating `resolve_runtime_config()` to handle new sections
- Replacing hardcoded constants in `pipeline.py` with config references
- Enhancing `save_candidate_diagnostics()` with SNR annotation, box-model overlay, odd/even subplot, parameter text box
- Adding `iterative_masking` config flag and mask-flatten-search cycle to `pipeline.py`
- Updating `BLSCandidate` serialization in pipeline output (candidates JSON/CSV)

## Non-Goals

- Changing the BLS algorithm itself (astropy BoxLeastSquares) — out of scope.
- Adding new CLI arguments — all new options are config-driven via TOML.
- Multi-planet iterative masking (masking multiple candidates) — deferred to P2.
- Interactive/HTML versions of diagnostic plots — deferred.
- Performance optimization of the bootstrap FAP beyond the opt-in flag — deferred.
- Changes to the batch processing system — out of scope.
- Changes to the caching system — out of scope.

## Assumptions

- The existing `_group_depth_ppm()` helper in `vetting.py` can be reused for secondary eclipse measurement with a phase offset. (Medium risk: may need adaptation for phase 0.5 alignment.)
- The `save_candidate_diagnostics()` function can accept additional keyword arguments without breaking existing callers, since all current call sites can be updated in this change. (Low risk.)
- Bootstrap FAP with N=1000 on typical TESS light curves (~20k–50k points) completes within the 60-second NFR. (Medium risk: depends on BLS grid size; mitigated by opt-in flag.)
- The `flatten()` method on lightkurve `LightCurve` objects accepts a mask parameter for iterative masking. (Low risk: documented in lightkurve API.)

## Open Questions

None identified. The context.md provides sufficient detail for all seven fixes, including default values, function locations, and interaction rules (R7/R13 FAP ordering).
