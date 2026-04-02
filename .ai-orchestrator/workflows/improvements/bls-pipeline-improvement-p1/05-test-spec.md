---
agent: test-spec
sequence: 5
references: ["spec", "impl-plan"]
summary: "28 test cases across unit, integration, edge-case, and non-functional categories covering all 33 functional requirements and 14 acceptance criteria. All tests go in a single file tests/test_p1_fixes.py using pytest with numpy/lightkurve fixtures. Mocking strategy: synthetic light curves via numpy arrays wrapped in lightkurve LightCurve objects."
---

## Test Strategy

- **Test Framework**: pytest (already in dev dependencies)
- **Test Runner**: `pytest tests/test_p1_fixes.py -v`
- **Assertion Style**: plain `assert` statements with descriptive messages
- **Mocking Strategy**: No external mocking library needed. Synthetic light curves built from numpy arrays wrapped in `lightkurve.LightCurve`. No network calls — all data is synthetic.
- **Test Naming Convention**: `test_<fix_id>_<scenario>` (e.g., `test_r8_alias_two_thirds_flagged`)
- **Coverage Target**: 100% of new code paths (new functions, new dataclass fields, new config sections)
- **Test Categories**: All tests are unit tests in a single file. Integration verification done via `pytest tests/` (full suite).

## Test Coverage Matrix

| Requirement ID | Summary | Test Case IDs | Coverage Type |
|---------------|---------|---------------|---------------|
| FR-1 | BLSCandidate has fap field | TC-U-07 | Unit |
| FR-2 | BLSConfig has compute_fap | TC-U-05 | Unit |
| FR-3 | FAP computed via bootstrap | TC-U-08 | Unit |
| FR-4 | FAP is NaN when disabled | TC-U-09 | Unit |
| FR-5 | fap_iterations configurable | TC-U-05 | Unit |
| FR-6 | Alias ratios include 2/3 and 3/2 | TC-U-01, TC-U-02 | Unit |
| FR-7 | _secondary_eclipse_check function | TC-U-10 | Unit |
| FR-8 | pass_secondary_eclipse field | TC-U-10 | Unit |
| FR-9 | Secondary eclipse flagging | TC-U-10 | Unit |
| FR-10 | Insufficient secondary data | TC-E-01 | Edge |
| FR-11 | vetting_pass incorporates secondary | TC-U-14 | Unit |
| FR-12 | _phase_fold_depth_consistency function | TC-U-11 | Unit |
| FR-13 | pass_depth_consistency field | TC-U-11 | Unit |
| FR-14 | Depth inconsistency flagging | TC-U-11 | Unit |
| FR-15 | Insufficient half-data | TC-E-02 | Edge |
| FR-16 | vetting_pass incorporates consistency | TC-U-14 | Unit |
| FR-17 | VettingConfig dataclass | TC-U-03 | Unit |
| FR-18 | ParameterConfig dataclass | TC-U-04 | Unit |
| FR-19 | RuntimeConfig has vetting/parameters | TC-U-05 | Unit |
| FR-20 | _DEFAULTS has new sections | TC-U-06 | Unit |
| FR-21 | Presets include new sections | TC-I-01 | Integration |
| FR-22 | resolve_runtime_config handles new sections | TC-I-02 | Integration |
| FR-23 | Hardcoded constants removed | TC-U-15 | Unit |
| FR-24 | Backward compatibility | TC-I-03 | Integration |
| FR-25 | SNR annotation on periodogram | TC-U-16 | Unit |
| FR-26 | Box-model overlay on phase-fold | TC-U-16 | Unit |
| FR-27 | Odd/even comparison subplot | TC-U-16 | Unit |
| FR-28 | Parameter text box | TC-U-16 | Unit |
| FR-29 | Diagnostics accepts new kwargs | TC-U-17, TC-E-05 | Unit + Edge |
| FR-30 | iterative_masking config flag | TC-U-05 | Unit |
| FR-31 | Mask-flatten-search cycle | TC-U-18 | Unit |
| FR-32 | Second pass replaces first | TC-U-18 | Unit |
| FR-33 | FAP on final pass only | TC-U-19 | Unit |
| NFR-2 | Defaults match hardcoded values | TC-U-06 | Unit |
| NFR-3 | Independent deployability | TC-I-04 | Integration |
| NFR-4 | No new dependencies | TC-U-20 | Unit |
| AC-1 | fap=NaN when disabled | TC-U-09 | Unit |
| AC-2 | fap in [0,1] when enabled | TC-U-08 | Unit |
| AC-3 | 2/3 alias flagged | TC-U-01 | Unit |
| AC-4 | Secondary eclipse flagged | TC-U-10 | Unit |
| AC-5 | Insufficient secondary → pass | TC-E-01 | Edge |
| AC-6 | Depth inconsistency flagged | TC-U-11 | Unit |
| AC-7 | Insufficient half → pass | TC-E-02 | Edge |
| AC-8 | Config without new sections → defaults | TC-I-03 | Integration |
| AC-9 | Custom vetting config applied | TC-I-02 | Integration |
| AC-10 | Diagnostic annotations present | TC-U-16 | Unit |
| AC-11 | Iterative masking two passes | TC-U-18 | Unit |
| AC-12 | FAP on second pass only | TC-U-19 | Unit |
| AC-13 | Presets produce valid config | TC-I-01 | Integration |
| AC-14 | Existing tests pass | TC-I-04 | Integration |

## Unit Test Cases

#### TC-U-01: R8 alias 2/3 ratio flagged
- **Covers**: FR-6, AC-3
- **Component**: `_alias_harmonic_reference_rank()` in vetting.py
- **Setup**: Two `BLSCandidate` objects: candidate A at period=3.0d (power=100), candidate B at period=2.0d (power=50). Ratio B/A = 2/3.
- **Input**: `_alias_harmonic_reference_rank(index=1, candidates=[A, B], tolerance_fraction=0.02)`
- **Expected Output**: Returns rank of candidate A (1), indicating B is alias of A.
- **Notes**: This ratio was missing in the original code.

#### TC-U-02: R8 alias 3/2 ratio flagged
- **Covers**: FR-6
- **Component**: `_alias_harmonic_reference_rank()` in vetting.py
- **Setup**: Two `BLSCandidate` objects: candidate A at period=2.0d (power=100), candidate B at period=3.0d (power=50). Ratio B/A = 3/2.
- **Input**: `_alias_harmonic_reference_rank(index=1, candidates=[A, B], tolerance_fraction=0.02)`
- **Expected Output**: Returns rank of candidate A (1).

#### TC-U-03: R11 VettingConfig defaults
- **Covers**: FR-17
- **Component**: `VettingConfig` in config.py
- **Setup**: None
- **Input**: Construct `VettingConfig` with default values
- **Expected Output**: `min_transit_count=2`, `odd_even_max_mismatch_fraction=0.30`, `alias_tolerance_fraction=0.02`, `secondary_eclipse_max_fraction=0.30`, `depth_consistency_max_fraction=0.50`

#### TC-U-04: R11 ParameterConfig defaults
- **Covers**: FR-18
- **Component**: `ParameterConfig` in config.py
- **Setup**: None
- **Input**: Construct `ParameterConfig` with default values
- **Expected Output**: `stellar_density_kg_m3=1408.0`, `duration_ratio_min=0.05`, `duration_ratio_max=1.8`

#### TC-U-05: R11 BLSConfig has new fields
- **Covers**: FR-2, FR-5, FR-19, FR-30
- **Component**: `BLSConfig` in config.py
- **Setup**: None
- **Input**: Check `BLSConfig` has `compute_fap`, `fap_iterations`, `iterative_masking` fields
- **Expected Output**: Fields exist. Defaults: `compute_fap=False`, `fap_iterations=1000`, `iterative_masking=False`

#### TC-U-06: R11 _DEFAULTS includes new sections
- **Covers**: FR-20, NFR-2
- **Component**: `_DEFAULTS` dict in config.py
- **Setup**: Import `_DEFAULTS`
- **Input**: Check keys `"vetting"` and `"parameters"` exist in `_DEFAULTS`
- **Expected Output**: Both present. `_DEFAULTS["vetting"]["min_transit_count"] == 2`. `_DEFAULTS["parameters"]["stellar_density_kg_m3"] == 1408.0`. `_DEFAULTS["bls"]["compute_fap"] == False`.

#### TC-U-07: R7 BLSCandidate has fap field
- **Covers**: FR-1
- **Component**: `BLSCandidate` in bls.py
- **Setup**: None
- **Input**: Construct `BLSCandidate` with `fap=0.05`
- **Expected Output**: `candidate.fap == 0.05`

#### TC-U-08: R7 FAP computed when enabled
- **Covers**: FR-3, AC-2
- **Component**: `run_bls_search()` in bls.py
- **Setup**: Synthetic light curve: 1000 points, 100 days span, sinusoidal signal at period=5d with 0.001 depth dip
- **Input**: `run_bls_search(lc, compute_fap=True, fap_iterations=50, min_snr=0.0, top_n=1)`
- **Expected Output**: Returned candidates have `fap` as float in [0.0, 1.0], not NaN

#### TC-U-09: R7 FAP is NaN when disabled
- **Covers**: FR-4, AC-1
- **Component**: `run_bls_search()` in bls.py
- **Setup**: Same synthetic light curve as TC-U-08
- **Input**: `run_bls_search(lc, compute_fap=False, min_snr=0.0, top_n=1)`
- **Expected Output**: All candidates have `math.isnan(candidate.fap) == True`

#### TC-U-10: R9 secondary eclipse flagged
- **Covers**: FR-7, FR-8, FR-9, AC-4
- **Component**: `vet_bls_candidates()` in vetting.py
- **Setup**: Synthetic light curve with primary dip at phase 0.0 (depth 1000 ppm) and secondary dip at phase 0.5 (depth 500 ppm, i.e., 50% of primary). 2000 points over 50 days, period=5d.
- **Input**: `vet_bls_candidates(lc, candidates, secondary_eclipse_max_fraction=0.30)`
- **Expected Output**: `result.pass_secondary_eclipse == False`, `"secondary_eclipse" in result.vetting_reasons`

#### TC-U-11: R10 depth inconsistency flagged
- **Covers**: FR-12, FR-13, FR-14, AC-6
- **Component**: `vet_bls_candidates()` in vetting.py
- **Setup**: Synthetic light curve where first half has transit depth 1000 ppm and second half has depth 200 ppm (80% difference). 2000 points over 100 days, period=5d.
- **Input**: `vet_bls_candidates(lc, candidates, depth_consistency_max_fraction=0.50)`
- **Expected Output**: `result.pass_depth_consistency == False`, `"depth_inconsistent" in result.vetting_reasons`

#### TC-U-14: R9/R10 vetting_pass incorporates new checks
- **Covers**: FR-11, FR-16
- **Component**: `vet_bls_candidates()` in vetting.py
- **Setup**: Synthetic light curve where all existing checks pass but secondary eclipse fails
- **Input**: `vet_bls_candidates(lc, candidates, secondary_eclipse_max_fraction=0.01)`
- **Expected Output**: `result.vetting_pass == False` (even though pass_min_transit_count, pass_odd_even, pass_alias are all True)

#### TC-U-15: R11 hardcoded constants removed from pipeline
- **Covers**: FR-23
- **Component**: `pipeline.py` module
- **Setup**: Import pipeline module
- **Input**: Check `hasattr(pipeline, '_VETTING_MIN_TRANSIT_COUNT')`
- **Expected Output**: `False` for all six old constants

#### TC-U-16: R12 diagnostic annotations present
- **Covers**: FR-25, FR-26, FR-27, FR-28, AC-10
- **Component**: `save_candidate_diagnostics()` in plotting.py
- **Setup**: Synthetic light curve, one candidate, mock vetting result, mock parameter estimate, periodogram arrays
- **Input**: Call `save_candidate_diagnostics()` with `vetting_results={1: vetting_result}` and `parameter_estimates={1: param_est}`
- **Expected Output**: Function returns file paths without error. Output PNG files exist. (Visual content verified by file size > baseline without annotations.)

#### TC-U-17: R12 diagnostics backward compatible without new kwargs
- **Covers**: FR-29
- **Component**: `save_candidate_diagnostics()` in plotting.py
- **Setup**: Same as TC-U-16 but without new kwargs
- **Input**: Call `save_candidate_diagnostics(target, key, lc, candidates, periods, power)` — no vetting_results or parameter_estimates
- **Expected Output**: Function returns file paths without error. Output PNG files exist.

#### TC-U-18: R13 iterative masking produces second-pass candidates
- **Covers**: FR-31, FR-32, AC-11
- **Component**: Iterative masking logic in pipeline.py (tested via a helper or integration)
- **Setup**: Synthetic light curve with two signals: strong signal at period=3d and weaker signal at period=7d
- **Input**: Run BLS with `iterative_masking=True`
- **Expected Output**: Final candidates differ from first-pass candidates (rank-1 period changes after masking)

#### TC-U-19: R13+R7 FAP computed on final pass only
- **Covers**: FR-33, AC-12
- **Component**: Pipeline BLS block
- **Setup**: Same as TC-U-18 with `compute_fap=True, fap_iterations=20`
- **Input**: Run with both flags enabled
- **Expected Output**: Candidates have valid FAP values (not NaN), computed on post-masking data

#### TC-U-20: NFR-4 no new dependencies
- **Covers**: NFR-4
- **Component**: pyproject.toml
- **Setup**: Read pyproject.toml
- **Input**: Parse dependencies list
- **Expected Output**: Dependencies are exactly: numpy, matplotlib, astropy, lightkurve, pandas

## Integration Test Cases

#### TC-I-01: Presets produce valid config with new sections
- **Covers**: FR-21, AC-13
- **Components**: config.py + preset TOMLs
- **Setup**: None
- **Scenario**: For each preset name ("quicklook", "science-default", "deep-search"): call `resolve_runtime_config(preset_name=name)`, verify `cfg.vetting` and `cfg.parameters` are populated
- **Expected Result**: All three presets produce `RuntimeConfig` with valid `VettingConfig` and `ParameterConfig`

#### TC-I-02: Custom vetting config overrides defaults
- **Covers**: FR-22, AC-9
- **Components**: config.py + TOML parsing
- **Setup**: Write a temp TOML file with `[vetting]\nmin_transit_count = 5`
- **Scenario**: Call `resolve_runtime_config(config_path=temp_path)`
- **Expected Result**: `cfg.vetting.min_transit_count == 5`, other vetting fields at defaults

#### TC-I-03: Config without new sections uses defaults
- **Covers**: FR-24, AC-8
- **Components**: config.py
- **Setup**: Write a temp TOML file with only `schema_version = 1` and `[bls]\nenabled = true`
- **Scenario**: Call `resolve_runtime_config(config_path=temp_path)`
- **Expected Result**: `cfg.vetting.min_transit_count == 2`, `cfg.parameters.stellar_density_kg_m3 == 1408.0`

#### TC-I-04: All existing tests still pass
- **Covers**: AC-14, NFR-3
- **Components**: All
- **Setup**: None
- **Scenario**: Run `pytest tests/test_config.py tests/test_p0_fixes.py tests/test_analysis_modules.py tests/test_cli.py`
- **Expected Result**: All pass (0 failures)

## Edge Case and Error Test Cases

#### TC-E-01: Secondary eclipse insufficient data
- **Covers**: FR-10, AC-5
- **Setup**: Synthetic light curve with only 20 points (too few for secondary eclipse measurement)
- **Input**: `vet_bls_candidates(lc, candidates, secondary_eclipse_max_fraction=0.30)`
- **Expected Behavior**: `pass_secondary_eclipse=True`, `math.isnan(result.secondary_eclipse_depth_fraction)`
- **Why This Matters**: Prevents false negatives on short light curves

#### TC-E-02: Depth consistency insufficient half-data
- **Covers**: FR-15, AC-7
- **Setup**: Synthetic light curve where one time-half has < 5 in-transit points
- **Input**: `vet_bls_candidates(lc, candidates, depth_consistency_max_fraction=0.50)`
- **Expected Behavior**: `pass_depth_consistency=True`, `math.isnan(result.depth_consistency_fraction)`
- **Why This Matters**: Prevents false negatives on sparse data

#### TC-E-03: FAP with zero-variance flux
- **Covers**: FR-3
- **Setup**: Synthetic light curve with constant flux (all values = 1.0)
- **Input**: `run_bls_search(lc, compute_fap=True, fap_iterations=10, min_snr=0.0)`
- **Expected Behavior**: Returns empty list or candidates with `fap=NaN` (no meaningful signal)
- **Why This Matters**: Bootstrap on flat data should not crash

#### TC-E-04: Secondary eclipse with zero primary depth
- **Covers**: FR-9
- **Setup**: Candidate with depth=0 (no transit)
- **Input**: `_secondary_eclipse_check()` with zero primary depth
- **Expected Behavior**: Returns `(NaN, True)` — pass by default
- **Why This Matters**: Division by zero protection

#### TC-E-05: Diagnostics with empty vetting dict
- **Covers**: FR-29
- **Setup**: Call `save_candidate_diagnostics()` with `vetting_results={}` (no matching rank)
- **Input**: Candidate rank=1 but vetting_results is empty dict
- **Expected Behavior**: Function completes without error, produces plots without annotations
- **Why This Matters**: Graceful degradation when vetting data is missing for a candidate

## Non-Functional Test Cases

#### TC-P-01: Bootstrap FAP completes in reasonable time
- **Covers**: NFR-1
- **Type**: Performance
- **Setup**: Synthetic light curve with 5000 points, 50-day span
- **Procedure**: Time `run_bls_search(lc, compute_fap=True, fap_iterations=100, min_snr=0.0, n_periods=200)`
- **Threshold**: Completes in < 30 seconds (scaled from NFR-1's 60s for N=1000, using N=100)
- **Measurement Method**: `time.perf_counter()` before and after call

## Test Data Requirements

**Fixtures**:
- `make_synthetic_lc(n_points, span_days, period_days=None, depth=None, secondary_depth=None)`: Factory function that creates a `lightkurve.LightCurve` with optional transit dips. Uses `np.linspace` for time, `np.ones` for baseline flux, and subtracts `depth` at in-transit phases.
- `make_candidate(rank, period_days, duration_hours, depth, power, transit_time, snr, fap=float("nan"))`: Factory for `BLSCandidate` with sensible defaults.

**Mocks**: None needed — all data is synthetic numpy arrays.

## Test File Map

| Test File | Test Case IDs | Tests For |
|----------|---------------|-----------|
| `tests/test_p1_fixes.py` | TC-U-01 through TC-U-20, TC-I-01 through TC-I-04, TC-E-01 through TC-E-05, TC-P-01 | vetting.py, bls.py, config.py, pipeline.py, plotting.py |
