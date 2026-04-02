# Project: BLS Pipeline P2 Improvements (R16–R20)

## Type
feature

## Description
Implement the five P2 recommendations (R16–R20) from the BLS pipeline quality audit in `.ai-orchestrator/workflows/research/bls-pipeline-issues/01-research.md`. These are lower-priority refinements addressing performance, configurability, parameter accuracy, and visualization polish.

**R16 — Optimize BLS refinement model reuse** (Issue B4)
`refine_bls_candidates()` calls `run_bls_search()` per candidate, which re-instantiates a `BoxLeastSquares` model, re-validates inputs, re-sorts time arrays, and re-checks finite values each time. Extract shared setup via `_prepare_bls_inputs()` once and reuse the model across all candidates. ~30 lines refactor.

**R17 — Widen deduplication filter or make configurable** (Issue B3)
`unique_period_separation_fraction=0.02` (2%) can discard near-resonant multi-planet signals (e.g., periods at 3.0d and 3.05d — 1.7% separation). Increase default to 5% and expose as a configurable parameter in `BLSConfig`. ~10 lines.

**R18 — Add limb darkening correction** (Issue E2)
`depth ≈ (Rp/Rs)²` ignores limb darkening, underestimating radius ratio by ~5–15%. Apply correction: `Rp/Rs = sqrt(depth / (1 - u₁/3 - u₂/6))` with configurable TESS-bandpass coefficients (default u₁=0.4, u₂=0.2). Add fields to `ParameterConfig`. ~15 lines.

**R19 — Reduce binned percentile smoothing** (Issue PL4)
`_binned_summary()` uses `bin_width_days=0.02` (28.8 min) followed by 9-point `_smooth_series()`, which blurs transit dips in the percentile band panel. Reduce default smoothing window and/or make it configurable. ~10 lines.

**R20 — Add TIC stellar density lookup** (Issue E1)
`estimate_candidate_parameters()` assumes solar density (1408 kg/m³) for all hosts. For M-dwarfs (~5000–20000 kg/m³) and subgiants (~200–500 kg/m³), duration expectations and radius estimates are off by 2–5×. Add optional TIC catalog lookup via lightkurve to retrieve stellar density per target. Fall back to solar density with a warning when unavailable. ~30 lines.

## Background
The P0 fixes (R1–R6) addressed critical detection, vetting, preset, normalization, and visualization gaps. The P1 fixes (R7–R13) added FAP, alias ratios, secondary eclipse check, phase-fold consistency, config schema expansion, diagnostic annotations, and iterative masking. The pipeline refactoring (R14) decomposed the monolith. R15 (BLS duplicate code extraction) was addressed as part of the refactoring.

These P2 fixes are polish-level improvements that refine performance, parameter accuracy, and visualization quality. The pipeline score after P0+P1 is ~9/10; P2 targets the remaining gaps.

## Constraints
- Python ≥ 3.10. No new heavy dependencies beyond lightkurve/astropy/numpy/matplotlib.
- Each fix must be independently deployable.
- Must remain compatible with existing `RuntimeConfig`/preset/TOML layered config system.
- New config fields must use `_DEFAULTS` mechanism for backward compatibility.
- TIC lookup (R20) requires network access — must be optional and gracefully degrade when offline or TIC data unavailable.

## Existing Code/System
Repository: `/Users/gbasin/Development/exoplanets-hunting-pipeline`

Key files and locations for each fix:

| Fix | Primary files | Key functions/classes | Lines of interest |
|-----|--------------|----------------------|-------------------|
| R16 | `src/exohunt/bls.py` | `refine_bls_candidates()`, `_prepare_bls_inputs()`, `_BLSInputs` | bls.py:267–318 (refine), bls.py:67–112 (prepare), bls.py:47–64 (inputs class) |
| R17 | `src/exohunt/bls.py`, `src/exohunt/config.py` | `run_bls_search()`, `_unique_period()`, `BLSConfig` | bls.py:37–44 (unique filter), bls.py:153 (`unique_period_separation_fraction=0.02`), config.py:56–69 |
| R18 | `src/exohunt/parameters.py`, `src/exohunt/config.py` | `estimate_candidate_parameters()`, `ParameterConfig` | parameters.py:46–111, parameters.py:80 (`radius_ratio = math.sqrt(depth_non_negative)`), config.py:82–85 |
| R19 | `src/exohunt/plotting.py` | `_binned_summary()`, `_smooth_series()`, `save_raw_vs_prepared_plot()` | plotting.py:64–94 (binned), plotting.py:112–124 (smooth), plotting.py:131–205 |
| R20 | `src/exohunt/parameters.py`, `src/exohunt/config.py` | `estimate_candidate_parameters()`, `_expected_central_duration_hours()`, `ParameterConfig` | parameters.py:10 (`_DEFAULT_STELLAR_DENSITY_KG_M3 = 1408.0`), parameters.py:25–43 |

Current `ParameterConfig` (R18/R20 will add fields):
```python
class ParameterConfig:
    stellar_density_kg_m3: float
    duration_ratio_min: float
    duration_ratio_max: float
```

Current depth-to-radius (R18 adds limb darkening correction):
```python
# parameters.py line ~80
radius_ratio = math.sqrt(depth_non_negative)
radius_earth = radius_ratio * _R_SUN_IN_R_EARTH
```

Current deduplication filter (R17 widens/exposes):
```python
# bls.py _unique_period()
def _unique_period(existing, period_days, min_separation_frac):
    for candidate in existing:
        denom = max(candidate.period_days, period_days, 1e-12)
        if abs(candidate.period_days - period_days) / denom < min_separation_frac:
            return False
    return True
```

Current refinement loop (R16 optimizes):
```python
# bls.py refine_bls_candidates() — calls run_bls_search() per candidate
for candidate in candidates:
    local = run_bls_search(lc_prepared=lc_prepared, ...)
```

Current smoothing (R19 reduces):
```python
# plotting.py _smooth_series() default window=9
# _binned_summary() default bin_width_days=0.02
```

Research: `.ai-orchestrator/workflows/research/bls-pipeline-issues/01-research.md`

## Success Criteria
1. **R16**: `refine_bls_candidates()` calls `_prepare_bls_inputs()` once and reuses the model for all candidates instead of calling `run_bls_search()` per candidate.
2. **R17**: `unique_period_separation_fraction` default is 0.05 (5%). Configurable via `BLSConfig`. Near-resonant periods (e.g., 3.0d and 3.05d) are no longer discarded.
3. **R18**: `estimate_candidate_parameters()` applies limb darkening correction when enabled. `ParameterConfig` has `apply_limb_darkening_correction`, `limb_darkening_u1`, `limb_darkening_u2` fields.
4. **R19**: Smoothing window in percentile band panel is reduced or configurable. Transit dips are more visible in the binned representation.
5. **R20**: When a TIC ID is available, stellar density is looked up from the TIC catalog. Falls back to solar density with a logged warning when unavailable. `ParameterConfig` has `tic_density_lookup` flag.
6. All existing tests pass. Pipeline produces valid output on `TIC 261136679` with each preset.

## Human Gates
impl-plan

## Additional Notes
- R16 is a pure performance refactor — no behavioral change, easiest to validate.
- R17 default change (2% → 5%) could affect existing results — document in changelog.
- R18 correction is small (~5–15% radius change) but improves accuracy for all candidates.
- R20 depends on network access and lightkurve's TIC query capability (`lk.search_targetpixelfile` or `astroquery.mast`). Must handle timeouts and missing data gracefully.
- R19 is cosmetic — affects only the visual appearance of the percentile band panel.
