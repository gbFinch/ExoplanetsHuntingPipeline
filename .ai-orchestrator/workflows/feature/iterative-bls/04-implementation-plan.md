---
agent: impl-plan
sequence: 4
references: ["architecture"]
summary: "8-step implementation plan following bottom-up, TDD ordering. Starts with config extensions and data model changes, then tests for iterative BLS core, then implementation, then pipeline wiring. Critical path: config → data model → transit mask → iterative BLS tests → iterative BLS impl → pipeline wiring → presets. Two integration checkpoints verify iterative BLS in isolation and end-to-end pipeline behavior."
---

## Implementation Strategy

- **Build Order**: Bottom-up. Config and data model changes first (leaf dependencies), then core algorithm, then pipeline integration. This ensures each layer can be tested independently before wiring.
- **TDD Approach**: Tests for iterative BLS behavior are written before the implementation. Config and data model changes are simple enough to verify inline.
- **Integration Strategy**: Incremental. Each step produces testable code. Integration checkpoints after core algorithm and after pipeline wiring.
- **Scaffolding**: No new files or directories needed. All changes are modifications to existing files.

## File Structure

Changes only (existing files modified):

```
src/exohunt/
  config.py             # Add new fields to BLSConfig, PreprocessConfig, _DEFAULTS, resolve_runtime_config
  bls.py                # Add iteration field to BLSCandidate, add run_iterative_bls_search, _build_transit_mask, _cross_iteration_unique
  preprocess.py         # Add transit_mask param to prepare_lightcurve
  pipeline.py           # Wire iterative dispatch in _search_and_output_stage, pass-through in fetch_and_plot
  presets/
    quicklook.toml      # Add iterative defaults
    science-default.toml # Add iterative defaults
    deep-search.toml    # Add iterative defaults
tests/
  test_iterative_bls.py # NEW: tests for iterative BLS, transit mask, cross-iteration uniqueness
```

## Implementation Steps

#### Step 1: Config Extensions
- **Files**: `src/exohunt/config.py`, `src/exohunt/presets/quicklook.toml`, `src/exohunt/presets/science-default.toml`, `src/exohunt/presets/deep-search.toml`
- **Dependencies**: None
- **Description**: Add new fields to `BLSConfig` and `PreprocessConfig` dataclasses. Update `_DEFAULTS` dict with default values. Update `resolve_runtime_config()` to parse the new fields. Update all three preset TOML files with default values that preserve current behavior.
- **Key Implementation Details**:
  - `BLSConfig`: add `iterative_passes: int` (default 1), `subtraction_model: str` (default "box_mask"), `iterative_top_n: int` (default 1), `transit_mask_padding_factor: float` (default 1.5)
  - `PreprocessConfig`: add `iterative_flatten: bool` (default False), `transit_mask_padding_factor: float` (default 1.5)
  - `_DEFAULTS["bls"]`: add matching keys
  - `_DEFAULTS["preprocess"]`: add matching keys
  - `resolve_runtime_config()`: add `_expect_int`/`_expect_float`/`_expect_bool` calls for new fields in the bls and preprocess sections
  - Each TOML preset: add `iterative_masking = false`, `iterative_passes = 1`, `subtraction_model = "box_mask"`, `iterative_top_n = 1`, `transit_mask_padding_factor = 1.5` under `[bls]`; add `iterative_flatten = false`, `transit_mask_padding_factor = 1.5` under `[preprocess]`
- **Acceptance Check**: `pytest tests/test_config.py` passes. Manually verify `resolve_runtime_config()` returns new fields with correct defaults.
- **Estimated Size**: ~80 lines

#### Step 2: BLSCandidate Iteration Field
- **Files**: `src/exohunt/bls.py`
- **Dependencies**: None
- **Description**: Add `iteration: int = 0` field to the `BLSCandidate` dataclass. This is a backward-compatible default — existing code that creates `BLSCandidate` without specifying `iteration` gets 0.
- **Key Implementation Details**:
  - Add `iteration: int = 0` to `BLSCandidate` dataclass (must go after `fap` since it has a default)
- **Acceptance Check**: Existing tests pass. `BLSCandidate` can be instantiated with and without `iteration` kwarg.
- **Estimated Size**: ~5 lines

#### Step 3: Transit Mask and Cross-Iteration Uniqueness Functions
- **Files**: `src/exohunt/bls.py`
- **Dependencies**: Step 2
- **Description**: Implement `_build_transit_mask()` and `_cross_iteration_unique()` helper functions.
- **Key Implementation Details**:
  - `_build_transit_mask(time: np.ndarray, candidates: list[BLSCandidate], padding_factor: float) -> np.ndarray`: For each candidate, compute number of cycles as `int((time_max - transit_time) / period) + 1`. For each cycle, mark points where `|time - (transit_time + cycle * period)| < 0.5 * duration_days * padding_factor`. Return boolean OR of all candidate masks. `duration_days = candidate.duration_hours / 24.0`.
  - `_cross_iteration_unique(candidate: BLSCandidate, accepted: list[BLSCandidate], threshold: float = 0.01) -> bool`: Return True if candidate's period is more than `threshold` fractional separation from every accepted candidate's period.
- **Acceptance Check**: Unit tests in Step 4 will verify. Functions can be tested in isolation.
- **Estimated Size**: ~40 lines

#### Step 4: Tests for Iterative BLS
- **Files**: `tests/test_iterative_bls.py` (NEW)
- **Dependencies**: Steps 1, 2, 3
- **Description**: Write tests for transit mask computation, cross-iteration uniqueness, and the full `run_iterative_bls_search()` function. Tests use synthetic light curves with injected box transits.
- **Key Implementation Details**:
  - `test_build_transit_mask_marks_correct_points`: Create time array, single candidate, verify mask marks expected points within padding.
  - `test_build_transit_mask_multiple_candidates`: Two candidates with different periods, verify both are masked.
  - `test_cross_iteration_unique_rejects_duplicate`: Period within 1% → rejected.
  - `test_cross_iteration_unique_accepts_distinct`: Period >1% apart → accepted.
  - `test_iterative_bls_finds_two_signals`: Synthetic LC with two injected transits (periods 3.0d and 7.0d, depths 500ppm and 300ppm), `iterative_passes=3`, verify ≥2 candidates from different iterations.
  - `test_iterative_bls_single_pass_matches_baseline`: `iterative_passes=1`, verify output matches `run_bls_search()` (excluding `iteration` field).
  - `test_iterative_bls_stops_on_low_snr`: Synthetic LC with one signal, `iterative_passes=5`, verify loop stops after signal is exhausted.
  - `test_iterative_bls_early_termination_few_points`: Mask so many points that <100 remain, verify early termination with warning.
- **Acceptance Check**: Tests exist and are syntactically valid. They will fail until Step 5 implements the function (TDD red phase).
- **Estimated Size**: ~150 lines

#### Step 5: Implement `run_iterative_bls_search()`
- **Files**: `src/exohunt/bls.py`
- **Dependencies**: Steps 1, 2, 3, 4
- **Description**: Implement the main iterative BLS loop function.
- **Key Implementation Details**:
  - `run_iterative_bls_search(time, flux, config, *, normalized=True, preprocess_config=None, lc=None) -> list[BLSCandidate]`:
    1. Initialize `all_candidates = []`, `accepted_for_masking = []`, `current_flux = flux.copy()`
    2. Loop for `config.iterative_passes` iterations:
       a. Count non-NaN points. If < 100, log warning, break.
       b. Call `run_bls_search(time, current_flux, config, normalized=normalized)`
       c. Take top `config.iterative_top_n` candidates by SNR that pass `min_snr`
       d. For each: check `_cross_iteration_unique(candidate, accepted_for_masking)`. If unique, set `candidate.iteration = i`, append to `all_candidates` and `accepted_for_masking`.
       e. If no new candidates accepted this iteration, break.
       f. Build transit mask: `_build_transit_mask(time, accepted_for_masking, config.transit_mask_padding_factor)`
       g. If `preprocess_config` and `preprocess_config.iterative_flatten` and `lc` is not None: call `prepare_lightcurve(lc, ..., transit_mask=cumulative_mask)`, extract new flux.
       h. Else: `current_flux = flux.copy(); current_flux[mask] = NaN`
    3. Return `all_candidates`
- **Acceptance Check**: `pytest tests/test_iterative_bls.py` — all tests from Step 4 pass.
- **Estimated Size**: ~80 lines

#### Step 6: Extend `prepare_lightcurve()` with Transit Mask
- **Files**: `src/exohunt/preprocess.py`
- **Dependencies**: Step 1
- **Description**: Add `transit_mask` parameter to `prepare_lightcurve()`. When provided, pass it to `lc.flatten(mask=transit_mask)`.
- **Key Implementation Details**:
  - Add `transit_mask: np.ndarray | None = None` parameter
  - In the flatten section, change `prepared.flatten(window_length=window_length)` to `prepared.flatten(window_length=window_length, mask=transit_mask)` when `transit_mask` is not None
  - Ensure mask is aligned: if outlier removal changed array length, the transit mask must be recomputed or the caller must handle alignment. Decision: the caller (iterative BLS) passes the mask aligned to the original LC, and `prepare_lightcurve` applies it to the flatten step only. Since `remove_outliers` may change indices, the transit mask should be applied to the pre-outlier-removal LC for flattening. Implementation: pass mask to flatten before outlier removal, or document that the caller must provide a mask aligned to the post-outlier-removal LC. Simplest: apply flatten with mask on the post-outlier-removal LC, require caller to align mask.
- **Acceptance Check**: Existing `pytest tests/` pass. Manual verification that `prepare_lightcurve(lc, transit_mask=mask)` produces a flattened LC where masked points are not used in the baseline.
- **Estimated Size**: ~15 lines

#### Step 7: Pipeline Wiring
- **Files**: `src/exohunt/pipeline.py`
- **Dependencies**: Steps 1, 5, 6
- **Description**: Wire `run_iterative_bls_search()` into `_search_and_output_stage()`. Update `fetch_and_plot()` to pass iterative config through. Add per-iteration artifact writing.
- **Key Implementation Details**:
  - In `_search_and_output_stage()`: after obtaining the stitched light curve, check `config.bls.iterative_masking`. If True, call `run_iterative_bls_search(time, flux, config.bls, preprocess_config=config.preprocess, lc=stitched_lc)` instead of `run_bls_search()`.
  - Write per-iteration candidate files: group candidates by `iteration`, write each group as `<target>__bls_iter_<N>_<hash>.json`.
  - Write combined candidate file with all candidates.
  - In `fetch_and_plot()`: ensure `bls_iterative_masking` parameter is used to set `config.bls.iterative_masking` (it's already accepted but unused — wire it through).
- **Acceptance Check**: `pytest tests/` — all existing tests pass. Manual test: run pipeline with `iterative_masking=True` on a target.
- **Estimated Size**: ~60 lines

#### Step 8: Preset TOML Verification and Final Integration
- **Files**: All preset TOML files (already modified in Step 1), `src/exohunt/config.py`
- **Dependencies**: Steps 1-7
- **Description**: Verify all presets load correctly with new fields. Run full test suite. Verify backward compatibility: default config produces identical output to pre-change behavior.
- **Key Implementation Details**:
  - Run `pytest` to verify all tests pass
  - Verify `resolve_runtime_config()` with each preset produces correct defaults
  - Verify `iterative_masking=False` code path is unchanged
- **Acceptance Check**: `pytest` passes with zero failures. All existing tests unmodified and passing.
- **Estimated Size**: ~0 lines (verification only)

## Dependency Graph

```
Step 1 (config) ─────────────────────────────────────┐
Step 2 (BLSCandidate.iteration) ──┐                  │
                                  ▼                  │
Step 3 (transit mask + uniqueness helpers) ──┐       │
                                             ▼       │
Step 4 (iterative BLS tests) ───────────────┐│       │
                                            ▼▼       │
Step 5 (iterative BLS impl) ────────────────┐│       │
                                            ││       │
Step 6 (prepare_lightcurve transit_mask) ◄──┘│◄──────┘
                                            ▼
Step 7 (pipeline wiring) ◄─────────────────┘
                                            │
Step 8 (verification) ◄────────────────────┘
```

**Critical path**: Step 1 → Step 2 → Step 3 → Step 4 → Step 5 → Step 7 → Step 8

## Integration Checkpoints

### After Step 5: Iterative BLS Core
- **What to test**: `run_iterative_bls_search()` works correctly in isolation with synthetic data.
- **Verification Command**: `pytest tests/test_iterative_bls.py -v`
- **Expected Result**: All 8 tests pass. Two-signal synthetic test finds ≥2 candidates. Single-pass test matches baseline. Early termination works.

### After Step 7: End-to-End Pipeline
- **What to test**: Full pipeline runs with `iterative_masking=True` and produces per-iteration artifacts. Default config (iterative_masking=False) produces unchanged output.
- **Verification Command**: `pytest tests/ -v`
- **Expected Result**: All tests pass (existing + new). No regressions.

## Risk Mitigation Steps

### R-1: Astropy BLS NaN Handling
- **Mitigation in Implementation**: In Step 5, before the main loop, add a quick validation: run `run_bls_search()` on a small array with NaN values. If it raises, fall back to replacing NaN with local median instead of leaving as NaN.
- **Fallback Plan**: Replace `current_flux[mask] = NaN` with `current_flux[mask] = np.nanmedian(current_flux)`. This is a one-line change.

### R-2: Lightkurve Flatten Mask API
- **Mitigation in Implementation**: In Step 6, test `lc.flatten(mask=boolean_array)` on a synthetic LightCurve before integrating. Verify masked points remain in output and are not used in the SG fit.
- **Fallback Plan**: If lightkurve's mask parameter doesn't work as expected, manually implement SG flattening with mask exclusion using `scipy.signal.savgol_filter` on non-masked points, then divide the full LC by the interpolated trend. ~20 additional lines.

### R-4: Per-Iteration Artifact Naming Conflicts
- **Mitigation in Implementation**: In Step 7, ensure per-iteration files use a distinct naming pattern (`bls_iter_<N>`) that cannot collide with existing single-pass artifact names (`bls_<hash>`). The combined file uses the existing naming pattern for backward compatibility.
- **Fallback Plan**: If naming conflicts arise, add an `_iterative` suffix to the combined file name.
