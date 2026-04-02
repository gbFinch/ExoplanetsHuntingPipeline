---
agent: impl-plan
sequence: 4
references: ["architecture"]
summary: "7-step implementation plan for P2 improvements. Bottom-up order: config fields first, then module changes (bls.py, parameters.py, plotting.py), then pipeline wiring, preset updates, and tests. Critical path is config.py → module changes → pipeline.py → presets. Estimated ~250 lines of production code and ~200 lines of tests."
---

## Implementation Strategy

- **Build Order**: Bottom-up. Config layer first (all new fields), then leaf modules (bls.py, parameters.py, plotting.py), then pipeline wiring (pipeline.py + cli.py), then preset TOMLs.
- **TDD Approach**: Test file written before implementation code. Tests target the new behaviors specifically.
- **Integration Strategy**: Incremental. Each step produces a buildable state. Integration checkpoint after config + module changes, and after full wiring.
- **Scaffolding**: No new files except `tests/test_p2_fixes.py`. All production changes are modifications to existing files.

## File Structure

```
src/exohunt/
  config.py              # MODIFY: add fields to BLSConfig, ParameterConfig, PlotConfig, _DEFAULTS, resolve_runtime_config()
  bls.py                 # MODIFY: refactor refine_bls_candidates(), change dedup default
  parameters.py          # MODIFY: add limb darkening correction, TIC density lookup
  plotting.py            # MODIFY: wire smoothing_window parameter
  pipeline.py            # MODIFY: pass new config fields to function calls
  cli.py                 # MODIFY: pass new config fields from RuntimeConfig to fetch_and_plot()
  presets/
    quicklook.toml       # MODIFY: add new fields
    science-default.toml # MODIFY: add new fields
    deep-search.toml     # MODIFY: add new fields
tests/
  test_p2_fixes.py       # CREATE: tests for all P2 improvements
```

## Implementation Steps

#### Step 1: Config Layer — Add All New Fields
- **Files**: `src/exohunt/config.py`
- **Dependencies**: None
- **Description**: Add `unique_period_separation_fraction` to `BLSConfig`, add `apply_limb_darkening_correction`, `limb_darkening_u1`, `limb_darkening_u2`, `tic_density_lookup` to `ParameterConfig`, add `smoothing_window` to `PlotConfig`. Update `_DEFAULTS` dict with default values. Update `resolve_runtime_config()` to parse and construct the new fields.
- **Key Implementation Details**:
  - `BLSConfig`: add `unique_period_separation_fraction: float` field
  - `ParameterConfig`: add `apply_limb_darkening_correction: bool`, `limb_darkening_u1: float`, `limb_darkening_u2: float`, `tic_density_lookup: bool`
  - `PlotConfig`: add `smoothing_window: int`
  - `_DEFAULTS["bls"]["unique_period_separation_fraction"] = 0.05`
  - `_DEFAULTS["parameters"]["apply_limb_darkening_correction"] = False`
  - `_DEFAULTS["parameters"]["limb_darkening_u1"] = 0.4`
  - `_DEFAULTS["parameters"]["limb_darkening_u2"] = 0.2`
  - `_DEFAULTS["parameters"]["tic_density_lookup"] = False`
  - `_DEFAULTS["plot"]["smoothing_window"] = 5`
  - In `resolve_runtime_config()`: add `_expect_float(bls_data, "unique_period_separation_fraction", scope="bls")` to `BLSConfig` construction, add 4 new fields to `ParameterConfig` construction, add `_expect_int(plot_data, "smoothing_window", scope="plot")` to `PlotConfig` construction
- **Acceptance Check**: `pytest tests/test_config.py` passes. `resolve_runtime_config()` returns config with new fields at default values.
- **Estimated Size**: ~50 lines

#### Step 2: Tests for P2 Fixes
- **Files**: `tests/test_p2_fixes.py`
- **Dependencies**: Step 1
- **Description**: Create test file covering all five P2 improvements. Tests for: refinement model reuse (R16), dedup filter configurability (R17), limb darkening correction (R18), smoothing window config (R19), TIC density lookup with fallback (R20).
- **Key Implementation Details**:
  - `test_refine_reuses_model()`: mock `_prepare_bls_inputs` and verify it's called once for 3 candidates
  - `test_dedup_filter_05_keeps_close_periods()`: two candidates at 3.00d and 3.05d (1.7% apart) both retained with 0.05 threshold
  - `test_dedup_filter_configurable_via_blsconfig()`: verify `BLSConfig` has `unique_period_separation_fraction` field
  - `test_limb_darkening_correction_applied()`: depth=0.0001, u1=0.4, u2=0.2 → radius_ratio ≈ 0.01069
  - `test_limb_darkening_correction_disabled()`: depth=0.0001, disabled → radius_ratio = 0.01
  - `test_smoothing_window_config()`: verify `PlotConfig` has `smoothing_window` field with default 5
  - `test_tic_density_lookup_fallback()`: mock failed TIC query → falls back to default density
  - `test_tic_density_lookup_success()`: mock successful TIC query → uses returned density
  - `test_new_config_defaults_backward_compatible()`: resolve config without new fields → defaults applied
- **Acceptance Check**: Tests are syntactically valid. Tests that don't depend on implementation changes pass (config tests). Tests for unimplemented features fail as expected.
- **Estimated Size**: ~180 lines

#### Step 3: BLS Refinement Reuse and Dedup Filter (R16, R17)
- **Files**: `src/exohunt/bls.py`
- **Dependencies**: Step 1
- **Description**: Refactor `refine_bls_candidates()` to call `_prepare_bls_inputs()` once and reuse the model. Add `_refine_single_candidate()` private function. Change `unique_period_separation_fraction` default from 0.02 to 0.05 in `run_bls_search()`.
- **Key Implementation Details**:
  - New function `_refine_single_candidate(inputs: _BLSInputs, candidate: BLSCandidate, period_min_days: float, period_max_days: float, window_fraction: float, n_periods: int, min_snr: float) -> BLSCandidate`
    - Computes narrowed period window: `local_min = max(period_min_days, candidate.period_days - window)`, `local_max = min(period_max_days, candidate.period_days + window)`
    - Creates narrowed period grid: `np.geomspace(local_min, local_max, n_periods)`
    - Calls `inputs.model.power(inputs.durations, narrowed_periods)` directly
    - Extracts best peak, computes SNR from power array, returns refined `BLSCandidate`
    - Returns original candidate if no valid result
  - `refine_bls_candidates()`: call `_prepare_bls_inputs()` once at top, loop `_refine_single_candidate()` per candidate
  - `run_bls_search()`: change `unique_period_separation_fraction` default from `0.02` to `0.05`
- **Acceptance Check**: `test_refine_reuses_model` and `test_dedup_filter_05_keeps_close_periods` pass.
- **Estimated Size**: ~60 lines (net change after removing old loop code)

#### Step 4: Limb Darkening Correction and TIC Lookup (R18, R20)
- **Files**: `src/exohunt/parameters.py`
- **Dependencies**: Step 1
- **Description**: Add limb darkening correction to `estimate_candidate_parameters()`. Add `_lookup_tic_density()` private function for TIC catalog lookup with timeout and fallback.
- **Key Implementation Details**:
  - Extended `estimate_candidate_parameters()` signature: add `apply_limb_darkening_correction: bool = False`, `limb_darkening_u1: float = 0.4`, `limb_darkening_u2: float = 0.2`, `tic_density_lookup: bool = False`, `tic_id: str | None = None`
  - Limb darkening: when enabled, `radius_ratio = math.sqrt(depth_non_negative / (1.0 - u1 / 3.0 - u2 / 6.0))` instead of `math.sqrt(depth_non_negative)`
  - New `_lookup_tic_density(tic_id: str, timeout_seconds: float = 10.0) -> float | None`:
    - Import `astroquery.mast.Catalogs` inside function (lazy import)
    - Call `Catalogs.query_object(tic_id, catalog="TIC")`
    - Extract `mass` and `rad` fields from first row
    - Compute density: `3.0 * mass * _M_SUN_KG / (4.0 * math.pi * (rad * _R_SUN_M) ** 3)`
    - Return `None` on any exception, log warning
  - At top of `estimate_candidate_parameters()`: if `tic_density_lookup` and `tic_id`, call `_lookup_tic_density()`. If result is not None, use it as `stellar_density_kg_m3`.
  - Add constants: `_M_SUN_KG = 1.989e30`, `_R_SUN_M = 6.957e8`
- **Acceptance Check**: `test_limb_darkening_correction_applied`, `test_limb_darkening_correction_disabled`, `test_tic_density_lookup_fallback`, `test_tic_density_lookup_success` pass.
- **Estimated Size**: ~55 lines

#### Step 5: Smoothing Window Config (R19)
- **Files**: `src/exohunt/plotting.py`
- **Dependencies**: Step 1
- **Description**: Add `smoothing_window` parameter to `save_raw_vs_prepared_plot()` and pass it to `_smooth_series()` calls.
- **Key Implementation Details**:
  - `save_raw_vs_prepared_plot()`: add `smoothing_window: int = 5` parameter
  - Replace all `_smooth_series(values)` calls in this function with `_smooth_series(values, window=smoothing_window)`
  - Same for `save_raw_vs_prepared_plot_interactive()` if it uses `_smooth_series()`
- **Acceptance Check**: `test_smoothing_window_config` passes.
- **Estimated Size**: ~10 lines

#### Step 6: Pipeline Wiring and CLI
- **Files**: `src/exohunt/pipeline.py`, `src/exohunt/cli.py`
- **Dependencies**: Steps 3, 4, 5
- **Description**: Thread new config fields from `fetch_and_plot()` parameters through to the module function calls. Update `cli.py` to pass new `RuntimeConfig` fields.
- **Key Implementation Details**:
  - `fetch_and_plot()` signature: add `bls_unique_period_separation_fraction: float = 0.05`, `parameter_apply_limb_darkening_correction: bool = False`, `parameter_limb_darkening_u1: float = 0.4`, `parameter_limb_darkening_u2: float = 0.2`, `parameter_tic_density_lookup: bool = False`, `plot_smoothing_window: int = 5`
  - Pass `unique_period_separation_fraction` to `run_bls_search()` calls
  - Pass limb darkening and TIC params to `estimate_candidate_parameters()` calls
  - Pass `smoothing_window` to `save_raw_vs_prepared_plot()` calls
  - Extract TIC ID from target string (strip "TIC " prefix) for `tic_id` parameter
  - `cli.py`: add new fields to `_run_single_target()` call: `bls_unique_period_separation_fraction=runtime_config.bls.unique_period_separation_fraction`, etc.
- **Acceptance Check**: `pytest tests/test_p2_fixes.py` all pass. `pytest tests/test_config.py` passes. `pytest tests/test_smoke.py` passes.
- **Estimated Size**: ~50 lines

#### Step 7: Preset TOML Updates
- **Files**: `src/exohunt/presets/quicklook.toml`, `src/exohunt/presets/science-default.toml`, `src/exohunt/presets/deep-search.toml`
- **Dependencies**: Step 1
- **Description**: Add new config fields to all three preset files with appropriate values.
- **Key Implementation Details**:
  - All presets: add `unique_period_separation_fraction = 0.05` under `[bls]`
  - All presets: add `apply_limb_darkening_correction = false`, `limb_darkening_u1 = 0.4`, `limb_darkening_u2 = 0.2`, `tic_density_lookup = false` under `[parameters]`
  - All presets: add `smoothing_window = 5` under `[plot]`
  - `deep-search.toml`: set `tic_density_lookup = true` (deep search benefits from better stellar parameters)
- **Acceptance Check**: `pytest tests/test_config.py` passes. Each preset resolves without error.
- **Estimated Size**: ~20 lines across 3 files

## Dependency Graph

```
Step 1 (config.py)
  ├── Step 2 (tests)
  ├── Step 3 (bls.py: R16, R17) ──┐
  ├── Step 4 (parameters.py: R18, R20) ──┤── Step 6 (pipeline.py + cli.py wiring)
  ├── Step 5 (plotting.py: R19) ──┘
  └── Step 7 (preset TOMLs)
```

Critical path: Step 1 → Step 3/4/5 (parallel) → Step 6

## Integration Checkpoints

- **After Step 1 + Step 7**: Run `pytest tests/test_config.py` — all config resolution tests pass with new fields at default values. Presets resolve without error.
  - **Verification Command**: `pytest tests/test_config.py -v`
  - **Expected Result**: All tests pass. No `ConfigValidationError` from new fields.

- **After Step 6 (all production code complete)**: Run full test suite.
  - **Verification Command**: `pytest tests/ -v`
  - **Expected Result**: All existing tests pass. All new `test_p2_fixes.py` tests pass. No regressions.

## Risk Mitigation Steps

- **RISK-1 (TIC missing data)**: In Step 4, `_lookup_tic_density()` catches all exceptions and returns `None`. The caller falls back to configured default. Test `test_tic_density_lookup_fallback` verifies this path.
- **RISK-2 (Dedup default change)**: In Step 3, the default changes from 0.02 to 0.05. Step 7 updates presets to match. Existing user configs with explicit values are unaffected by `_deep_merge()` behavior.
- **RISK-3 (Refinement edge cases)**: In Step 3, `_refine_single_candidate()` returns the original candidate if `_prepare_bls_inputs()` returns `None` or if the narrowed search produces no results. This matches the current fallback behavior.
- **RISK-4 (TIC timeout)**: In Step 4, `_lookup_tic_density()` uses `concurrent.futures.ThreadPoolExecutor` with a 10-second timeout to enforce NFR-2. Default `tic_density_lookup=False` means batch users are unaffected unless they opt in.
