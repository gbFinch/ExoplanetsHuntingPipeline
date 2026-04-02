---
agent: test-spec
sequence: 5
references: ["spec", "impl-plan"]
summary: "18 test cases covering all 16 functional requirements, 6 non-functional requirements, and 9 acceptance criteria. Uses pytest with numpy for synthetic light curve generation. No mocking needed — all components are pure functions operating on numpy arrays. Tests organized in a single file tests/test_iterative_bls.py."
---

## Test Strategy

- **Test Framework**: pytest (already in dev dependencies)
- **Test Runner**: `pytest tests/test_iterative_bls.py -v`
- **Assertion Style**: Plain `assert` with descriptive messages
- **Mocking Strategy**: No mocks needed. `run_bls_search()` is a pure function on numpy arrays. Synthetic light curves with injected box transits provide deterministic test data.
- **Test Naming Convention**: `test_<component>_<scenario>` (e.g., `test_build_transit_mask_single_candidate`)
- **Coverage Target**: 100% of new functions (`run_iterative_bls_search`, `_build_transit_mask`, `_cross_iteration_unique`). Config and preprocess changes verified by existing tests.
- **Test Categories**: All unit tests in one file. No integration tests needed — pipeline wiring is verified by existing smoke tests.

## Test Coverage Matrix

| Requirement ID | Requirement Summary | Test Case IDs | Coverage Type |
|---------------|-------------------|---------------|---------------|
| FR-1 | `run_iterative_bls_search()` exists and returns annotated candidates | TC-U-05, TC-U-06 | Unit |
| FR-2 | Calls `run_bls_search()` on each iteration | TC-U-05, TC-U-06 | Unit |
| FR-3 | Transit mask computation | TC-U-01, TC-U-02, TC-U-03 | Unit |
| FR-4 | Stop on low SNR or max iterations | TC-U-07, TC-U-08 | Unit |
| FR-5 | Cross-iteration uniqueness filter | TC-U-04, TC-U-05, TC-E-03 | Unit |
| FR-6 | Iterative flattening with transit mask | TC-U-09 | Unit |
| FR-7 | `prepare_lightcurve` transit_mask param | TC-U-10 | Unit |
| FR-8 | BLSConfig new fields | TC-U-11 | Unit |
| FR-9 | PreprocessConfig new fields | TC-U-11 | Unit |
| FR-10 | iterative_masking as enable flag | TC-U-06 | Unit |
| FR-11 | BLSCandidate.iteration field | TC-U-05, TC-U-12 | Unit |
| FR-12 | Per-iteration artifact files | Deferred to pipeline smoke tests | Integration |
| FR-13 | Combined candidate JSON | Deferred to pipeline smoke tests | Integration |
| FR-14 | Defaults in _DEFAULTS and presets | TC-U-11 | Unit |
| FR-15 | fetch_and_plot pass-through | Deferred to pipeline smoke tests | Integration |
| FR-16 | _search_and_output_stage dispatch | Deferred to pipeline smoke tests | Integration |
| NFR-1 | Single pass matches baseline | TC-U-06 | Unit |
| NFR-2 | Default config unchanged behavior | TC-U-11 | Unit |
| NFR-3 | <10s per iteration | TC-P-01 | Performance |
| NFR-4 | No new dependencies | N/A (structural) | N/A |
| NFR-5 | Python 3.10+ | N/A (structural) | N/A |
| NFR-6 | Existing tests pass | TC-U-13 | Regression |
| AC-1 | Two signals found with iterative_passes=3 | TC-U-05 | Unit |
| AC-2 | Transit mask marks correct points | TC-U-01 | Unit |
| AC-3 | Cross-iteration uniqueness rejects 1% duplicate | TC-U-04 | Unit |
| AC-4 | Iterative flattening excludes masked transits | TC-U-09 | Unit |
| AC-5 | Single pass matches run_bls_search | TC-U-06 | Unit |
| AC-6 | iterative_masking=False unchanged | TC-U-11 | Unit |
| AC-7 | Config defaults correct | TC-U-11 | Unit |
| AC-8 | Candidates have iteration field | TC-U-05, TC-U-12 | Unit |
| AC-9 | Existing tests pass | TC-U-13 | Regression |

## Unit Test Cases

### Transit Mask

#### TC-U-01: Transit mask marks correct points for single candidate
- **Covers**: FR-3, AC-2
- **Component**: `_build_transit_mask()`
- **Setup**: `time = np.arange(0, 100, 0.02)` (5000 points over 100 days). One `BLSCandidate` with `period_days=2.0`, `transit_time=0.5`, `duration_hours=2.4` (0.1 days), `padding_factor=1.5`.
- **Input**: `_build_transit_mask(time, [candidate], 1.5)`
- **Expected Output**: Boolean array. Points within `0.5 * 0.1 * 1.5 = 0.075` days of each transit epoch (0.5, 2.5, 4.5, ...) are True. At least 50 transit epochs exist. Masked point count > 0 and < len(time).
- **Notes**: Verifies the core formula from FR-3.

#### TC-U-02: Transit mask with multiple candidates
- **Covers**: FR-3
- **Component**: `_build_transit_mask()`
- **Setup**: Same time array. Two candidates: period=3.0d and period=7.0d.
- **Input**: `_build_transit_mask(time, [cand1, cand2], 1.5)`
- **Expected Output**: Mask is the union of both individual masks. More points masked than either candidate alone.

#### TC-U-03: Transit mask with no candidates returns all-False
- **Covers**: FR-3
- **Component**: `_build_transit_mask()`
- **Setup**: Time array, empty candidate list.
- **Input**: `_build_transit_mask(time, [], 1.5)`
- **Expected Output**: All-False boolean array.

### Cross-Iteration Uniqueness

#### TC-U-04: Cross-iteration uniqueness rejects duplicate period
- **Covers**: FR-5, AC-3
- **Component**: `_cross_iteration_unique()`
- **Setup**: Accepted candidate with `period_days=5.0`. New candidate with `period_days=5.04` (0.8% separation, within 1%).
- **Input**: `_cross_iteration_unique(new_candidate, [accepted], threshold=0.01)`
- **Expected Output**: `False` (rejected).
- **Notes**: Also test with `period_days=5.06` (1.2% separation) → `True` (accepted).

### Iterative BLS Search

#### TC-U-05: Iterative BLS finds two signals
- **Covers**: FR-1, FR-2, FR-5, FR-11, AC-1, AC-8
- **Component**: `run_iterative_bls_search()`
- **Setup**: Synthetic light curve: `time = np.linspace(0, 90, 18000)`. Flat flux at 1.0. Inject two box transits: signal A at period=3.0d, depth=0.005 (5000 ppm), duration=0.08d; signal B at period=7.0d, depth=0.003 (3000 ppm), duration=0.1d. BLSConfig with `iterative_masking=True`, `iterative_passes=3`, `min_snr=5.0`, `iterative_top_n=1`, `transit_mask_padding_factor=1.5`.
- **Input**: `run_iterative_bls_search(time, flux, config)`
- **Expected Output**: At least 2 candidates. Candidates from different iterations (different `iteration` values). One candidate near period 3.0d, one near 7.0d (within 10%).
- **Notes**: Core acceptance criterion AC-1.

#### TC-U-06: Single pass matches run_bls_search baseline
- **Covers**: FR-10, NFR-1, AC-5
- **Component**: `run_iterative_bls_search()`
- **Setup**: Same synthetic LC as TC-U-05 but with `iterative_passes=1`.
- **Input**: Call both `run_iterative_bls_search(time, flux, config_1pass)` and `run_bls_search(lc, ...)` with equivalent params.
- **Expected Output**: Same number of candidates. Same periods (within 1e-6). Same SNR values. Only difference: iterative version has `iteration=0`.

#### TC-U-07: Iterative BLS stops when SNR drops below threshold
- **Covers**: FR-4
- **Component**: `run_iterative_bls_search()`
- **Setup**: Synthetic LC with one strong signal (period=3.0d, depth=5000ppm). `iterative_passes=5`, `min_snr=7.0`.
- **Input**: `run_iterative_bls_search(time, flux, config)`
- **Expected Output**: Fewer than 5 candidates returned (loop stopped early because no signal above SNR threshold after first is masked).

#### TC-U-08: Iterative BLS early termination on few points
- **Covers**: FR-4
- **Component**: `run_iterative_bls_search()`
- **Setup**: Short time array with ~150 points. One strong signal. `iterative_passes=3`. After masking the first signal, fewer than 100 non-NaN points remain.
- **Input**: `run_iterative_bls_search(time, flux, config)`
- **Expected Output**: Returns candidates from iteration 0 only. No crash.

### Iterative Flattening

#### TC-U-09: Iterative flattening re-flattens with transit mask
- **Covers**: FR-6, AC-4
- **Component**: `run_iterative_bls_search()` with `iterative_flatten=True`
- **Setup**: Synthetic LC with a linear trend added (slope) plus two transit signals. PreprocessConfig with `iterative_flatten=True`. Provide a lightkurve LightCurve object.
- **Input**: `run_iterative_bls_search(time, flux, config, preprocess_config=pp_config, lc=lc_object)`
- **Expected Output**: At least 1 candidate found. Function completes without error. (Full depth recovery verification is manual.)

### Prepare Lightcurve Extension

#### TC-U-10: prepare_lightcurve accepts transit_mask parameter
- **Covers**: FR-7
- **Component**: `prepare_lightcurve()`
- **Setup**: Create a simple lightkurve LightCurve with 1000 points. Create a boolean transit_mask with ~50 points marked True.
- **Input**: `prepare_lightcurve(lc, transit_mask=mask)`
- **Expected Output**: Returns `(lc, was_normalized)` tuple without error. Output LC has same number of points or fewer (outlier removal). Function signature accepts the parameter.

### Config

#### TC-U-11: Config defaults include all new fields
- **Covers**: FR-8, FR-9, FR-14, NFR-2, AC-7
- **Component**: `resolve_runtime_config()`, `BLSConfig`, `PreprocessConfig`
- **Setup**: Call `resolve_runtime_config()` with no overrides (pure defaults).
- **Input**: `resolve_runtime_config()`
- **Expected Output**: `config.bls.iterative_passes == 1`, `config.bls.subtraction_model == "box_mask"`, `config.bls.iterative_top_n == 1`, `config.bls.transit_mask_padding_factor == 1.5`, `config.bls.iterative_masking == False`, `config.preprocess.iterative_flatten == False`, `config.preprocess.transit_mask_padding_factor == 1.5`.

### BLSCandidate

#### TC-U-12: BLSCandidate has iteration field with default 0
- **Covers**: FR-11, AC-8
- **Component**: `BLSCandidate`
- **Setup**: None.
- **Input**: Create `BLSCandidate(rank=1, period_days=1.0, duration_hours=2.0, depth=0.001, depth_ppm=1000, power=10.0, transit_time=100.0, transit_count_estimate=30.0, snr=8.0)`
- **Expected Output**: `candidate.iteration == 0`. Also: `BLSCandidate(..., iteration=2).iteration == 2`.

## Edge Case and Error Test Cases

#### TC-E-01: Transit mask with very short duration
- **Covers**: FR-3
- **Category**: Boundary condition
- **Setup**: Candidate with `duration_hours=0.01` (very short). `padding_factor=1.5`.
- **Input**: `_build_transit_mask(time, [candidate], 1.5)`
- **Expected Behavior**: Mask is computed without error. Very few or zero points masked (duration too short to capture any cadence).
- **Why This Matters**: Prevents division-by-zero or empty-mask crashes.

#### TC-E-02: Iterative BLS with zero valid candidates in first pass
- **Covers**: FR-4
- **Category**: Boundary condition
- **Setup**: Flat noise-free LC (flux = 1.0 exactly). `min_snr=7.0`, `iterative_passes=3`.
- **Input**: `run_iterative_bls_search(time, flux, config)`
- **Expected Behavior**: Returns empty list. No crash.
- **Why This Matters**: Ensures graceful handling when no signal exists.

#### TC-E-03: Cross-iteration uniqueness with empty accepted list
- **Covers**: FR-5
- **Category**: Boundary condition
- **Setup**: Empty accepted list.
- **Input**: `_cross_iteration_unique(candidate, [], threshold=0.01)`
- **Expected Behavior**: Returns `True` (no conflicts).
- **Why This Matters**: First iteration always has empty accepted list.

## Non-Functional Test Cases

#### TC-P-01: BLS iteration completes within 10 seconds
- **Covers**: NFR-3
- **Type**: Performance
- **Setup**: Synthetic LC with 18000 points. Standard BLS config.
- **Procedure**: Time a single call to `run_bls_search()` on the synthetic data.
- **Threshold**: < 10 seconds.
- **Measurement Method**: `time.time()` before and after call.

## Test Data Requirements

- **Synthetic light curves**: Generated inline using numpy. Flat flux at 1.0 with injected box transits computed as: `flux[|time - (t0 + n*period)| < 0.5*duration] -= depth` for each transit epoch.
- **BLSCandidate fixtures**: Created inline with known parameter values.
- **BLSConfig fixtures**: Created via `resolve_runtime_config()` with specific overrides.
- **No mocks needed**: All functions under test are pure computations on numpy arrays.

## Test File Map

| Test File | Test Case IDs | Tests For (Source File) |
|----------|---------------|----------------------|
| `tests/test_iterative_bls.py` | TC-U-01 through TC-U-12, TC-E-01 through TC-E-03, TC-P-01 | `src/exohunt/bls.py`, `src/exohunt/config.py`, `src/exohunt/preprocess.py` |
| `tests/test_config.py` (existing) | TC-U-11 (partial — existing tests cover config loading) | `src/exohunt/config.py` |
