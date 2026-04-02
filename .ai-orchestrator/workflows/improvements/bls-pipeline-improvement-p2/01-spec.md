---
agent: spec
sequence: 1
references: []
summary: "Specification for five P2 improvements to the Exohunt BLS transit-search pipeline: BLS refinement model reuse (R16), configurable deduplication filter (R17), limb darkening correction (R18), reduced percentile smoothing (R19), and TIC stellar density lookup (R20). All changes target existing modules with backward-compatible config extensions."
---

## Overview

The Exohunt BLS transit-search pipeline requires five P2-priority improvements that refine performance, parameter accuracy, configurability, and visualization quality. These changes modify `bls.py` (refinement optimization, deduplication filter), `parameters.py` (limb darkening correction, TIC density lookup), `plotting.py` (smoothing reduction), and `config.py` (new configuration fields). Each improvement is independently deployable and backward-compatible with existing configuration files via the `_DEFAULTS` mechanism.

## Functional Requirements

- **FR-1**: The system MUST reuse a single `_BLSInputs` instance (containing the `BoxLeastSquares` model, validated time/flux arrays, and period/duration grids) across all candidates in `refine_bls_candidates()` instead of calling `run_bls_search()` per candidate.
- **FR-2**: The system MUST accept a `unique_period_separation_fraction` parameter in `BLSConfig` with a default value of `0.05` (5%), replacing the current hardcoded `0.02` (2%).
- **FR-3**: The system MUST pass the configured `unique_period_separation_fraction` from `BLSConfig` through to `run_bls_search()` calls in the pipeline.
- **FR-4**: The system MUST apply a limb darkening correction to the depth-to-radius conversion when `ParameterConfig.apply_limb_darkening_correction` is `True`, using the formula `Rp/Rs = sqrt(depth / (1 - u1/3 - u2/6))`.
- **FR-5**: The system MUST expose `apply_limb_darkening_correction` (default `False`), `limb_darkening_u1` (default `0.4`), and `limb_darkening_u2` (default `0.2`) as fields in `ParameterConfig`.
- **FR-6**: When `apply_limb_darkening_correction` is `False`, the system MUST use the existing uncorrected formula `Rp/Rs = sqrt(depth)`.
- **FR-7**: The system MUST accept a `smoothing_window` parameter in `PlotConfig` (default `5`) that controls the `_smooth_series()` window size used in the percentile band panel of `save_raw_vs_prepared_plot()`.
- **FR-8**: The system MUST expose a `tic_density_lookup` boolean field in `ParameterConfig` (default `False`).
- **FR-9**: When `tic_density_lookup` is `True` and a TIC ID is available, the system MUST attempt to retrieve stellar density from the TIC catalog via lightkurve/astroquery.
- **FR-10**: When TIC density lookup fails (network error, missing data, timeout), the system MUST fall back to the configured `stellar_density_kg_m3` default and log a warning.
- **FR-11**: All new configuration fields MUST be present in `_DEFAULTS` so that existing TOML config files without these fields continue to work.

## Non-Functional Requirements

- **NFR-1**: `refine_bls_candidates()` with 5 candidates MUST complete in ≤40% of the time of the current implementation (which calls `run_bls_search()` 5 times with full setup overhead each time).
- **NFR-2**: TIC density lookup MUST time out after 10 seconds per query and fall back to the default density without crashing.
- **NFR-3**: All changes MUST maintain Python 3.10+ compatibility.
- **NFR-4**: No new dependencies beyond lightkurve, astropy, numpy, matplotlib, and their existing transitive dependencies.
- **NFR-5**: All existing tests (test_smoke.py, test_config.py, test_p0_fixes.py, test_p1_fixes.py, test_refactoring.py, test_analysis_modules.py, test_cli.py) MUST continue to pass.

## Acceptance Criteria

- **AC-1** (FR-1): Given a light curve with 5 BLS candidates, when `refine_bls_candidates()` is called, then `_prepare_bls_inputs()` is invoked exactly once (not 5 times) and the `BoxLeastSquares` model object is reused for all candidates.
- **AC-2** (FR-2, FR-3): Given a `BLSConfig` with `unique_period_separation_fraction = 0.05`, when `run_bls_search()` finds two candidates at periods 3.00d and 3.05d (1.7% separation), then both candidates are retained.
- **AC-3** (FR-2): Given a `BLSConfig` without `unique_period_separation_fraction` specified, when `run_bls_search()` is called, then the default value `0.05` is used.
- **AC-4** (FR-4, FR-5): Given `apply_limb_darkening_correction=True`, `limb_darkening_u1=0.4`, `limb_darkening_u2=0.2`, and a candidate with `depth=0.0001`, when `estimate_candidate_parameters()` is called, then `radius_ratio` equals `sqrt(0.0001 / (1 - 0.4/3 - 0.2/6))` ≈ `0.01069` (not `0.01`).
- **AC-5** (FR-6): Given `apply_limb_darkening_correction=False` and a candidate with `depth=0.0001`, when `estimate_candidate_parameters()` is called, then `radius_ratio` equals `sqrt(0.0001)` = `0.01`.
- **AC-6** (FR-7): Given `PlotConfig.smoothing_window=5`, when `save_raw_vs_prepared_plot()` generates the percentile band panel, then `_smooth_series()` is called with `window=5` instead of the previous hardcoded `9`.
- **AC-7** (FR-8, FR-9, FR-10): Given `tic_density_lookup=True` and a valid TIC ID, when `estimate_candidate_parameters()` is called and the TIC catalog returns a stellar density, then that density is used instead of the default.
- **AC-8** (FR-10): Given `tic_density_lookup=True` and a network timeout, when `estimate_candidate_parameters()` is called, then the default `stellar_density_kg_m3` is used and a warning is logged.
- **AC-9** (FR-11): Given an existing TOML config file that does not contain `unique_period_separation_fraction`, `apply_limb_darkening_correction`, `smoothing_window`, or `tic_density_lookup`, when `resolve_runtime_config()` is called, then all new fields receive their default values and no error is raised.

## Scope

- Modification of `src/exohunt/bls.py`: refactor `refine_bls_candidates()` to reuse `_BLSInputs`; change default `unique_period_separation_fraction` from 0.02 to 0.05
- Modification of `src/exohunt/config.py`: add `unique_period_separation_fraction` to `BLSConfig`; add `apply_limb_darkening_correction`, `limb_darkening_u1`, `limb_darkening_u2`, `tic_density_lookup` to `ParameterConfig`; add `smoothing_window` to `PlotConfig`; update `_DEFAULTS` and `resolve_runtime_config()`
- Modification of `src/exohunt/parameters.py`: implement limb darkening correction; implement TIC density lookup with fallback
- Modification of `src/exohunt/plotting.py`: wire `smoothing_window` config into `_smooth_series()` calls
- Modification of `src/exohunt/pipeline.py`: pass new config fields through to function calls
- Update of preset TOML files with new default values
- New test file for P2 fixes

## Non-Goals

- Changing the BLS algorithm itself or the SNR/FAP computation (already implemented in P0/P1)
- Adding new vetting checks (completed in P1)
- Refactoring pipeline.py architecture (completed in prior refactoring workflow)
- Adding new plot types or diagnostic panels (completed in P1)
- Supporting non-TESS data sources or instruments
- Implementing per-target limb darkening coefficient lookup from TIC (only density lookup is in scope; limb darkening uses fixed configurable coefficients)

## Assumptions

- The existing `_prepare_bls_inputs()` function can be called with a narrowed period range for refinement without modification to its interface. **Risk: Low** — the function already accepts `period_min_days` and `period_max_days`.
- lightkurve or astroquery provides access to TIC stellar parameters including density or mass/radius (from which density can be derived). **Risk: Medium** — TIC may not have density for all targets; mass+radius may need to be converted.
- The TESS bandpass limb darkening coefficients u₁=0.4, u₂=0.2 are reasonable defaults for solar-type stars. **Risk: Low** — these are standard literature values; the coefficients are configurable for users who need different values.
- The `_smooth_series()` function is only called from `save_raw_vs_prepared_plot()` for the percentile band panel. **Risk: Low** — verified by code inspection.

## Open Questions

1. **Should TIC density lookup use `stellar_density` directly or compute it from `mass` and `radius`?**
   - Affects: FR-9 implementation complexity
   - Default: Use mass and radius from TIC (more commonly available) and compute density as `density = mass_solar * M_sun / ((4/3) * pi * (radius_solar * R_sun)^3)`. Fall back to direct density field if mass/radius unavailable.

2. **Should the deduplication filter change (0.02 → 0.05) be applied retroactively to all presets or only as a new default?**
   - Affects: FR-2, preset files
   - Default: Apply to all presets and the `_DEFAULTS` dict. Existing user config files that explicitly set `unique_period_separation_fraction = 0.02` will keep their value.
