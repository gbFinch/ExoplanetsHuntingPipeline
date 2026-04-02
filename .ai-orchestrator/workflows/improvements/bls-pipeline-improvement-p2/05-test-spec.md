---
agent: test-spec
sequence: 5
references: ["spec", "impl-plan"]
summary: "14 test cases across unit, integration, and edge-case categories covering all 5 P2 improvements. Uses pytest with unittest.mock for TIC lookup and BLS model mocking. All tests in a single file tests/test_p2_fixes.py."
---

## Test Strategy

- **Test Framework**: pytest
- **Test Runner**: `pytest tests/test_p2_fixes.py -v`
- **Assertion Style**: plain `assert` statements
- **Mocking Strategy**: `unittest.mock.patch` for `_prepare_bls_inputs` (R16 model reuse verification), `_lookup_tic_density` and astroquery (R20 TIC lookup). Real implementations for config resolution, limb darkening math, dedup filter, smoothing.
- **Test Naming Convention**: `test_<feature>_<scenario>`
- **Coverage Target**: 100% of new/modified code paths in bls.py, parameters.py, plotting.py, config.py
- **Test Categories**: All unit tests in a single file `tests/test_p2_fixes.py`

## Test Coverage Matrix

| Requirement ID | Requirement Summary | Test Case IDs | Coverage Type |
|---------------|-------------------|---------------|---------------|
| FR-1 | Reuse _BLSInputs in refine | TC-U-01 | Unit |
| FR-2 | Dedup default 0.05 | TC-U-02, TC-U-03 | Unit |
| FR-3 | Pass dedup config through pipeline | TC-U-03 | Unit |
| FR-4 | Limb darkening correction formula | TC-U-04 | Unit |
| FR-5 | ParameterConfig limb darkening fields | TC-U-06 | Unit |
| FR-6 | Uncorrected formula when disabled | TC-U-05 | Unit |
| FR-7 | Smoothing window configurable | TC-U-07 | Unit |
| FR-8 | tic_density_lookup field | TC-U-06 | Unit |
| FR-9 | TIC density lookup success | TC-U-08 | Unit |
| FR-10 | TIC density lookup fallback | TC-U-09, TC-E-01 | Unit + Edge |
| FR-11 | Backward-compatible defaults | TC-U-10 | Unit |
| NFR-1 | Refinement performance | TC-U-01 (structural) | Unit |
| NFR-2 | TIC timeout | TC-E-02 | Edge |
| NFR-5 | Existing tests pass | TC-I-01 | Integration |
| AC-1 | _prepare_bls_inputs called once | TC-U-01 | Unit |
| AC-2 | Close periods retained at 0.05 | TC-U-02 | Unit |
| AC-3 | Default dedup is 0.05 | TC-U-03 | Unit |
| AC-4 | Limb darkening radius ≈ 0.01069 | TC-U-04 | Unit |
| AC-5 | Uncorrected radius = 0.01 | TC-U-05 | Unit |
| AC-6 | Smoothing window passed through | TC-U-07 | Unit |
| AC-7 | TIC density used when available | TC-U-08 | Unit |
| AC-8 | TIC fallback on failure | TC-U-09 | Unit |
| AC-9 | Config backward compatibility | TC-U-10 | Unit |

## Unit Test Cases

#### TC-U-01: Refinement reuses BLS model
- **Covers**: FR-1, AC-1, NFR-1
- **Component**: `refine_bls_candidates()` in `bls.py`
- **Setup**: Mock `_prepare_bls_inputs` to return a fake `_BLSInputs`. Create 3 dummy `BLSCandidate` objects.
- **Input**: Call `refine_bls_candidates(lc, candidates, ...)` with 3 candidates
- **Expected Output**: `_prepare_bls_inputs` is called exactly once (not 3 times)

#### TC-U-02: Dedup filter 0.05 keeps close periods
- **Covers**: FR-2, AC-2
- **Component**: `_unique_period()` in `bls.py`
- **Input**: existing candidate at 3.00d, new period 3.05d, `min_separation_frac=0.05`
- **Expected Output**: `_unique_period()` returns `True` (1.7% < 5%, so not a duplicate)

#### TC-U-03: BLSConfig has unique_period_separation_fraction with default 0.05
- **Covers**: FR-2, FR-3, AC-3
- **Component**: `BLSConfig` in `config.py`, `resolve_runtime_config()`
- **Input**: Call `resolve_runtime_config()` with no overrides
- **Expected Output**: `config.bls.unique_period_separation_fraction == 0.05`

#### TC-U-04: Limb darkening correction applied
- **Covers**: FR-4, AC-4
- **Component**: `estimate_candidate_parameters()` in `parameters.py`
- **Input**: candidate with `depth=0.0001`, `apply_limb_darkening_correction=True`, `u1=0.4`, `u2=0.2`
- **Expected Output**: `radius_ratio ≈ sqrt(0.0001 / (1 - 0.4/3 - 0.2/6)) ≈ 0.010690`

#### TC-U-05: Limb darkening correction disabled
- **Covers**: FR-6, AC-5
- **Component**: `estimate_candidate_parameters()` in `parameters.py`
- **Input**: candidate with `depth=0.0001`, `apply_limb_darkening_correction=False`
- **Expected Output**: `radius_ratio == sqrt(0.0001) == 0.01`

#### TC-U-06: New config fields exist with correct defaults
- **Covers**: FR-5, FR-8
- **Component**: `ParameterConfig`, `PlotConfig` in `config.py`
- **Input**: `resolve_runtime_config()` with no overrides
- **Expected Output**: `parameters.apply_limb_darkening_correction == False`, `parameters.limb_darkening_u1 == 0.4`, `parameters.limb_darkening_u2 == 0.2`, `parameters.tic_density_lookup == False`, `plot.smoothing_window == 5`

#### TC-U-07: Smoothing window passed to _smooth_series
- **Covers**: FR-7, AC-6
- **Component**: `save_raw_vs_prepared_plot()` in `plotting.py`
- **Input**: Mock `_smooth_series`, call `save_raw_vs_prepared_plot(..., smoothing_window=5)`
- **Expected Output**: `_smooth_series` called with `window=5` for percentile band panel

#### TC-U-08: TIC density lookup success
- **Covers**: FR-9, AC-7
- **Component**: `_lookup_tic_density()` in `parameters.py`
- **Setup**: Mock `astroquery.mast.Catalogs.query_object` to return a table with `mass=1.0`, `rad=1.0`
- **Input**: `_lookup_tic_density("261136679")`
- **Expected Output**: Returns solar density ≈ 1408 kg/m³ (since mass=1 solar, radius=1 solar)

#### TC-U-09: TIC density lookup fallback on failure
- **Covers**: FR-10, AC-8
- **Component**: `_lookup_tic_density()` in `parameters.py`
- **Setup**: Mock `astroquery.mast.Catalogs.query_object` to raise `Exception`
- **Input**: `_lookup_tic_density("999999999")`
- **Expected Output**: Returns `None`

#### TC-U-10: Config backward compatibility
- **Covers**: FR-11, AC-9
- **Component**: `resolve_runtime_config()` in `config.py`
- **Input**: Preset values dict without new fields (simulating old config)
- **Expected Output**: All new fields get default values, no error raised

## Edge Case and Error Test Cases

#### TC-E-01: TIC lookup with missing mass/radius fields
- **Covers**: FR-10
- **Category**: Invalid input
- **Setup**: Mock TIC query returning table with `mass=NaN`, `rad=NaN`
- **Input**: `_lookup_tic_density("123456")`
- **Expected Behavior**: Returns `None`, does not crash

#### TC-E-02: TIC lookup timeout
- **Covers**: NFR-2
- **Category**: Resource exhaustion
- **Setup**: Mock TIC query to hang (sleep > 10s)
- **Input**: `_lookup_tic_density("123456", timeout_seconds=0.1)`
- **Expected Behavior**: Returns `None` within ~0.2s, does not hang

#### TC-E-03: Dedup filter with identical periods
- **Covers**: FR-2
- **Category**: Boundary condition
- **Input**: existing candidate at 5.0d, new period 5.0d, `min_separation_frac=0.05`
- **Expected Behavior**: `_unique_period()` returns `False` (0% separation < 5%)

## Non-Functional Test Cases

Covered structurally by TC-U-01 (model reuse implies performance improvement) and TC-E-02 (timeout enforcement).

## Test Data Requirements

- **BLSCandidate fixtures**: Create via `BLSCandidate(rank=1, period_days=3.0, duration_hours=2.0, depth=0.0001, depth_ppm=100.0, power=0.01, transit_time=1000.0, transit_count_estimate=5.0, snr=8.0)`
- **Mock _BLSInputs**: Object with `model` attribute (MagicMock), `time`/`flux`/`periods`/`durations` as numpy arrays
- **Mock TIC table**: `astropy.table.Table` with columns `mass`, `rad` containing float values
- **Mock _prepare_bls_inputs**: Returns mock `_BLSInputs` or `None`

## Test File Map

| Test File | Test Case IDs | Tests For |
|----------|---------------|-----------|
| `tests/test_p2_fixes.py` | TC-U-01 through TC-U-10, TC-E-01 through TC-E-03 | `bls.py`, `parameters.py`, `plotting.py`, `config.py` |
