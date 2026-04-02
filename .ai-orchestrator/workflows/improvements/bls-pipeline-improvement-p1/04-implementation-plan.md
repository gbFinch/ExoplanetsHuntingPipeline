---
agent: impl-plan
sequence: 4
references: ["architecture"]
summary: "12-step implementation plan following bottom-up dependency order: R8 (trivial alias fix) → R11 (config schema, most cross-cutting) → R9/R10 (new vetting checks) → R7 (bootstrap FAP) → R12 (diagnostic plots) → R13 (iterative masking). Tests precede implementation per TDD. Each step targets 30–150 lines of code."
---

## Implementation Strategy

- **Build Order**: Bottom-up. Data models and config first (R11), then processing logic (R8, R9, R10, R7), then presentation (R12), then orchestration (R13). This matches the dependency graph from the analysis: config unblocks vetting parameters, vetting results feed into plots, masking interacts with FAP.
- **TDD Approach**: Tests are written in a single test file before implementation. Each implementation step has a corresponding test step that precedes it.
- **Integration Strategy**: Incremental. After each fix pair (test + impl), run `pytest` to verify no regressions. Two integration checkpoints at meaningful boundaries.
- **Scaffolding**: No new files needed — all changes extend existing modules. Step 1 creates the test file.

## File Structure

```
src/exohunt/
  config.py             # Modified: VettingConfig, ParameterConfig, _DEFAULTS, resolve_runtime_config()
  bls.py                # Modified: BLSCandidate.fap, _bootstrap_fap(), run_bls_search() fap params
  vetting.py            # Modified: alias ratios, _secondary_eclipse_check(), _phase_fold_depth_consistency(), CandidateVettingResult fields
  pipeline.py           # Modified: replace hardcoded constants, iterative masking, pass vetting to diagnostics
  plotting.py           # Modified: save_candidate_diagnostics() annotations
  parameters.py         # Unchanged (read only for reference)
  presets/
    quicklook.toml      # Modified: add [vetting] and [parameters] sections
    science-default.toml # Modified: add [vetting] and [parameters] sections
    deep-search.toml    # Modified: add [vetting] and [parameters] sections
tests/
  test_p1_fixes.py      # New: all P1 tests
```

## Implementation Steps

#### Step 1: Create test file with R8 and R11 tests
- **Files**: `tests/test_p1_fixes.py` (create)
- **Dependencies**: None
- **Description**: Create the P1 test file with tests for R8 (alias ratio expansion) and R11 (VettingConfig, ParameterConfig dataclasses, config defaults, preset loading, resolve_runtime_config with new sections, backward compatibility with missing sections).
- **Key Implementation Details**:
  - `test_alias_ratios_include_two_thirds_and_three_halves()`: build two candidates at 2:3 period ratio, verify alias flagging
  - `test_alias_ratios_include_three_halves()`: build two candidates at 3:2 period ratio, verify alias flagging
  - `test_vetting_config_defaults()`: verify VettingConfig fields and default values
  - `test_parameter_config_defaults()`: verify ParameterConfig fields and default values
  - `test_defaults_include_vetting_and_parameters()`: verify `_DEFAULTS` dict has new sections
  - `test_resolve_config_without_vetting_section()`: load config without `[vetting]`, verify defaults applied
  - `test_resolve_config_with_custom_vetting()`: load config with custom `[vetting]` values, verify override
  - `test_presets_include_vetting_and_parameters()`: load each preset, verify new sections present
  - `test_pipeline_constants_removed()`: verify `_VETTING_MIN_TRANSIT_COUNT` etc. no longer exist in pipeline.py
- **Acceptance Check**: `pytest tests/test_p1_fixes.py --collect-only` shows all test names (tests will fail until implementation)
- **Estimated Size**: ~120 lines

#### Step 2: Implement R8 — Add missing alias ratios
- **Files**: `src/exohunt/vetting.py` (modify)
- **Dependencies**: Step 1
- **Description**: Add `2.0/3.0` and `3.0/2.0` to the `ratios` tuple in `_alias_harmonic_reference_rank()` at line 58.
- **Key Implementation Details**:
  - Change `ratios = (0.5, 2.0, 1.0 / 3.0, 3.0)` to `ratios = (0.5, 2.0, 1.0 / 3.0, 3.0, 2.0 / 3.0, 3.0 / 2.0)`
- **Acceptance Check**: `pytest tests/test_p1_fixes.py -k "alias_ratios"` passes
- **Estimated Size**: 1 line changed

#### Step 3: Implement R11 — Config schema (VettingConfig, ParameterConfig, _DEFAULTS, presets)
- **Files**: `src/exohunt/config.py` (modify), `src/exohunt/presets/quicklook.toml` (modify), `src/exohunt/presets/science-default.toml` (modify), `src/exohunt/presets/deep-search.toml` (modify)
- **Dependencies**: Step 1
- **Description**: Add `VettingConfig` and `ParameterConfig` frozen dataclasses. Add `[vetting]` and `[parameters]` to `_DEFAULTS`. Add `vetting: VettingConfig` and `parameters: ParameterConfig` to `RuntimeConfig`. Extend `resolve_runtime_config()` to extract and construct these. Add sections to all three preset TOMLs. Add `compute_fap`, `fap_iterations`, `iterative_masking` to `BLSConfig` and `_DEFAULTS["bls"]`.
- **Key Implementation Details**:
  - `VettingConfig` dataclass: `min_transit_count: int`, `odd_even_max_mismatch_fraction: float`, `alias_tolerance_fraction: float`, `secondary_eclipse_max_fraction: float`, `depth_consistency_max_fraction: float`
  - `ParameterConfig` dataclass: `stellar_density_kg_m3: float`, `duration_ratio_min: float`, `duration_ratio_max: float`
  - `_DEFAULTS["vetting"]` = `{"min_transit_count": 2, "odd_even_max_mismatch_fraction": 0.30, "alias_tolerance_fraction": 0.02, "secondary_eclipse_max_fraction": 0.30, "depth_consistency_max_fraction": 0.50}`
  - `_DEFAULTS["parameters"]` = `{"stellar_density_kg_m3": 1408.0, "duration_ratio_min": 0.05, "duration_ratio_max": 1.8}`
  - `_DEFAULTS["bls"]` extended with `"compute_fap": False, "fap_iterations": 1000, "iterative_masking": False`
  - `resolve_runtime_config()`: add `vetting_data = merged["vetting"]`, construct `VettingConfig`, add `parameters_data = merged["parameters"]`, construct `ParameterConfig`, extend `BLSConfig` construction with new fields
  - Each preset TOML: append `[vetting]` and `[parameters]` sections with default values
- **Acceptance Check**: `pytest tests/test_p1_fixes.py -k "config"` passes; `pytest tests/test_config.py` still passes
- **Estimated Size**: ~100 lines across files

#### Step 4: Implement R11 — Wire config through pipeline.py
- **Files**: `src/exohunt/pipeline.py` (modify)
- **Dependencies**: Step 3
- **Description**: Remove the 6 hardcoded `_VETTING_*` and `_PARAMETER_*` constants. Update `fetch_and_plot()` signature to accept `RuntimeConfig` or pass individual config values. Replace all references to the old constants with `cfg.vetting.*` and `cfg.parameters.*` values. This requires threading the config values through the function — the simplest approach is to add parameters to `fetch_and_plot()` for the new config values and update the call site in `cli.py`.
- **Key Implementation Details**:
  - Add parameters to `fetch_and_plot()`: `vetting_min_transit_count`, `vetting_odd_even_max_mismatch_fraction`, `vetting_alias_tolerance_fraction`, `vetting_secondary_eclipse_max_fraction`, `vetting_depth_consistency_max_fraction`, `parameter_stellar_density_kg_m3`, `parameter_duration_ratio_min`, `parameter_duration_ratio_max`, `bls_compute_fap`, `bls_fap_iterations`, `bls_iterative_masking` — all with defaults matching current hardcoded values
  - Remove `_VETTING_MIN_TRANSIT_COUNT`, `_VETTING_ODD_EVEN_MAX_MISMATCH_FRACTION`, `_VETTING_ALIAS_TOLERANCE_FRACTION`, `_PARAMETER_STELLAR_DENSITY_KG_M3`, `_PARAMETER_DURATION_RATIO_MIN`, `_PARAMETER_DURATION_RATIO_MAX`
  - Replace all usages of old constants with the new parameters
  - Update `_CANDIDATE_COLUMNS` to include `fap`, `pass_secondary_eclipse`, `secondary_eclipse_depth_fraction`, `pass_depth_consistency`, `depth_consistency_fraction`
  - Update `cli.py` `_run_single_target()` to pass config values from `RuntimeConfig` to `fetch_and_plot()`
- **Acceptance Check**: `pytest tests/test_p1_fixes.py -k "pipeline_constants"` passes; `pytest tests/test_config.py tests/test_cli.py` still pass
- **Estimated Size**: ~80 lines changed

#### Step 5: Add tests for R9 and R10 (vetting checks)
- **Files**: `tests/test_p1_fixes.py` (modify)
- **Dependencies**: Step 1
- **Description**: Add tests for secondary eclipse check (R9) and phase-fold depth consistency (R10).
- **Key Implementation Details**:
  - `test_secondary_eclipse_flagged()`: synthetic light curve with secondary eclipse > 30% primary depth → `pass_secondary_eclipse=False`
  - `test_secondary_eclipse_pass_no_secondary()`: no secondary → `pass_secondary_eclipse=True`
  - `test_secondary_eclipse_insufficient_data()`: few points → `pass_secondary_eclipse=True`, fraction=NaN
  - `test_depth_consistency_flagged()`: first-half depth differs from second-half by >50% → `pass_depth_consistency=False`
  - `test_depth_consistency_pass()`: consistent depth → `pass_depth_consistency=True`
  - `test_depth_consistency_insufficient_data()`: few points → `pass_depth_consistency=True`, fraction=NaN
  - `test_vetting_pass_incorporates_new_checks()`: verify `vetting_pass` is AND of all checks
- **Acceptance Check**: `pytest tests/test_p1_fixes.py -k "secondary_eclipse or depth_consistency" --collect-only` shows tests
- **Estimated Size**: ~100 lines

#### Step 6: Implement R9 and R10 — Secondary eclipse and depth consistency checks
- **Files**: `src/exohunt/vetting.py` (modify)
- **Dependencies**: Steps 3, 5
- **Description**: Add `_secondary_eclipse_check()` and `_phase_fold_depth_consistency()` functions. Add `pass_secondary_eclipse`, `secondary_eclipse_depth_fraction`, `pass_depth_consistency`, `depth_consistency_fraction` fields to `CandidateVettingResult`. Wire new checks into `vet_bls_candidates()` with configurable thresholds. Update `vetting_pass` to AND all checks.
- **Key Implementation Details**:
  - `_secondary_eclipse_check(time, flux, period_days, transit_time, duration_days)` → `(float, bool)`: compute phase = (time - transit_time) / period_days, find points near phase 0.5 ± duration/2, measure depth vs out-of-eclipse baseline
  - `_phase_fold_depth_consistency(time, flux, period_days, transit_time, duration_days)` → `(float, bool)`: split time at midpoint, measure in-transit depth in each half, compute fractional difference
  - Add 4 new fields to `CandidateVettingResult`
  - Add `secondary_eclipse_max_fraction` and `depth_consistency_max_fraction` parameters to `vet_bls_candidates()`
  - Update `vetting_pass = pass_min_count and pass_odd_even and pass_alias and pass_secondary and pass_consistency`
- **Acceptance Check**: `pytest tests/test_p1_fixes.py -k "secondary_eclipse or depth_consistency or vetting_pass"` passes
- **Estimated Size**: ~90 lines

#### Step 7: Add tests for R7 (bootstrap FAP)
- **Files**: `tests/test_p1_fixes.py` (modify)
- **Dependencies**: Step 1
- **Description**: Add tests for bootstrap FAP computation.
- **Key Implementation Details**:
  - `test_bls_candidate_has_fap_field()`: verify `BLSCandidate` has `fap` attribute
  - `test_fap_nan_when_disabled()`: `compute_fap=False` → all candidates have `fap=NaN`
  - `test_fap_computed_when_enabled()`: `compute_fap=True, fap_iterations=50` → `fap` is float in [0, 1]
  - `test_bootstrap_fap_returns_valid_range()`: direct call to `_bootstrap_fap()` returns [0, 1]
- **Acceptance Check**: `pytest tests/test_p1_fixes.py -k "fap" --collect-only` shows tests
- **Estimated Size**: ~60 lines

#### Step 8: Implement R7 — Bootstrap FAP
- **Files**: `src/exohunt/bls.py` (modify)
- **Dependencies**: Steps 3, 7
- **Description**: Add `fap` field to `BLSCandidate`. Add `_bootstrap_fap()` internal function. Add `compute_fap` and `fap_iterations` parameters to `run_bls_search()`. When enabled, compute FAP for each candidate using reduced period grid (200 periods).
- **Key Implementation Details**:
  - `BLSCandidate`: add `fap: float` field (after `snr`)
  - `_bootstrap_fap(time, flux, observed_power, periods, durations, n_iterations)`: shuffle flux with `np.random.default_rng().shuffle()`, run `BoxLeastSquares(time, shuffled).power(reduced_periods, durations)`, record max power, return fraction ≥ observed_power
  - `run_bls_search()`: add `compute_fap: bool = False`, `fap_iterations: int = 1000` params. After picking candidates, if `compute_fap`, call `_bootstrap_fap()` for each. Use `np.geomspace(p_min, p_max, 200)` for bootstrap period grid.
  - All existing `BLSCandidate` constructions: add `fap=float("nan")` (default) or computed value
  - Update `refine_bls_candidates()` to preserve/pass-through `fap` field
- **Acceptance Check**: `pytest tests/test_p1_fixes.py -k "fap"` passes
- **Estimated Size**: ~60 lines

#### Step 9: Add tests for R12 (diagnostic annotations)
- **Files**: `tests/test_p1_fixes.py` (modify)
- **Dependencies**: Step 1
- **Description**: Add tests for enhanced diagnostic plot annotations.
- **Key Implementation Details**:
  - `test_diagnostics_accepts_vetting_kwarg()`: call `save_candidate_diagnostics()` with `vetting_results={}` — no error
  - `test_diagnostics_accepts_parameter_kwarg()`: call with `parameter_estimates={}` — no error
  - `test_diagnostics_backward_compatible()`: call without new kwargs — no error, produces files
- **Acceptance Check**: `pytest tests/test_p1_fixes.py -k "diagnostics" --collect-only` shows tests
- **Estimated Size**: ~40 lines

#### Step 10: Implement R12 — Diagnostic plot annotations
- **Files**: `src/exohunt/plotting.py` (modify)
- **Dependencies**: Steps 6, 9
- **Description**: Extend `save_candidate_diagnostics()` with keyword-only `vetting_results` and `parameter_estimates` parameters. Add SNR annotation on periodogram, box-model overlay on phase-fold, odd/even comparison subplot, and parameter text box. When new params are None, skip annotations (backward compatible).
- **Key Implementation Details**:
  - Add `*, vetting_results: dict | None = None, parameter_estimates: dict | None = None` to signature
  - SNR annotation: `ax_p.annotate(f"SNR={candidate.snr:.1f}", xy=(candidate.period_days, peak_power), ...)`
  - Box-model overlay: draw flat line at 0 ppm with rectangular dip of `candidate.depth_ppm` at phase 0 ± duration/2
  - Odd/even subplot: change figure layout to 3 rows when vetting data available; bar chart of odd_depth_ppm vs even_depth_ppm
  - Parameter text box: `fig.text()` with period, depth_ppm, duration, SNR, vetting_pass
  - Update pipeline.py call sites to pass `vetting_results=` and `parameter_estimates=`
- **Acceptance Check**: `pytest tests/test_p1_fixes.py -k "diagnostics"` passes
- **Estimated Size**: ~100 lines

#### Step 11: Add tests for R13 and implement R13 — Iterative masking
- **Files**: `tests/test_p1_fixes.py` (modify), `src/exohunt/pipeline.py` (modify)
- **Dependencies**: Steps 4, 8
- **Description**: Add test for iterative masking config flag. Implement the mask-flatten-search cycle in pipeline.py's BLS execution block. When `bls_iterative_masking=True`: (1) run BLS (first pass), (2) mask rank-1 candidate's in-transit points, (3) re-flatten with mask, (4) re-run BLS (second pass), (5) replace candidates. If `compute_fap` also enabled, compute FAP only on second-pass candidates.
- **Key Implementation Details**:
  - Test: `test_iterative_masking_config_flag()`: verify `BLSConfig` has `iterative_masking` field
  - In pipeline.py stitched BLS block: after initial `run_bls_search()` and before vetting, add masking loop
  - Mask construction: `mask = np.zeros(len(time), dtype=bool)` then set True for points within ±duration/2 of each transit epoch of rank-1 candidate
  - Re-flatten: use lightkurve's `flatten(window_length=..., mask=mask)` or manually exclude masked points
  - Second BLS pass: call `run_bls_search()` on re-flattened data
  - FAP ordering: only pass `compute_fap=True` to the final `run_bls_search()` call
- **Acceptance Check**: `pytest tests/test_p1_fixes.py -k "iterative_masking"` passes
- **Estimated Size**: ~80 lines

#### Step 12: Integration verification and cleanup
- **Files**: All modified files (read-only verification)
- **Dependencies**: Steps 2, 4, 6, 8, 10, 11
- **Description**: Run full test suite. Verify all existing tests pass. Verify new tests pass. Check that no hardcoded constants remain.
- **Key Implementation Details**:
  - Run `pytest` (full suite)
  - Run `ruff check src/exohunt/`
  - Verify `_VETTING_MIN_TRANSIT_COUNT` etc. do not appear in pipeline.py
- **Acceptance Check**: `pytest` exits 0; `ruff check src/exohunt/` exits 0
- **Estimated Size**: 0 lines (verification only)

## Dependency Graph

```
Step 1 (test file: R8+R11 tests)
  ├──→ Step 2 (R8 impl: alias ratios)
  ├──→ Step 3 (R11 impl: config schema)
  │      └──→ Step 4 (R11 impl: pipeline wiring)
  │             └──→ Step 11 (R13 tests+impl: iterative masking)
  │                    └──→ Step 12 (integration verification)
  ├──→ Step 5 (R9/R10 tests)
  │      └──→ Step 6 (R9/R10 impl: vetting checks) [depends on Step 3]
  │             └──→ Step 10 (R12 impl: diagnostic plots) [depends on Step 9]
  │                    └──→ Step 12
  ├──→ Step 7 (R7 tests)
  │      └──→ Step 8 (R7 impl: bootstrap FAP) [depends on Step 3]
  │             └──→ Step 11
  └──→ Step 9 (R12 tests)
         └──→ Step 10
```

**Critical path**: Step 1 → Step 3 → Step 4 → Step 11 → Step 12

## Integration Checkpoints

**After Step 4** (config fully wired):
- **What to test**: Config resolution with new sections, pipeline uses config values instead of hardcoded constants, backward compatibility with old config files.
- **Verification Command**: `pytest tests/test_p1_fixes.py tests/test_config.py tests/test_cli.py -v`
- **Expected Result**: All tests pass. Config tests verify new sections. Pipeline tests verify no hardcoded constants.

**After Step 10** (all processing logic complete, before R13):
- **What to test**: Full vetting pipeline with new checks, diagnostic plots with annotations, FAP computation.
- **Verification Command**: `pytest tests/ -v`
- **Expected Result**: All tests pass including new P1 tests for R7, R8, R9, R10, R11, R12.

**After Step 12** (final):
- **What to test**: Complete integration including iterative masking.
- **Verification Command**: `pytest tests/ -v && ruff check src/exohunt/`
- **Expected Result**: All tests pass. No lint errors.

## Risk Mitigation Steps

**RISK-1 (Bootstrap FAP performance)**:
- Mitigation: Use 200-period reduced grid in `_bootstrap_fap()`. Add early-exit if all bootstrap powers exceed observed power after 100 iterations (FAP ≈ 1.0).
- Fallback: If still too slow, reduce default `fap_iterations` to 500 or add a timeout.

**RISK-2 (Config resolver complexity)**:
- Mitigation: Follow the exact pattern used for existing sections (`bls_data = merged["bls"]` → construct dataclass). The `_deep_merge` function is schema-driven and handles new sections automatically when added to `_DEFAULTS`.
- Fallback: If `_deep_merge` has unexpected behavior, add explicit handling for new sections before the merge call.

**RISK-4 (Diagnostic signature change)**:
- Mitigation: Use keyword-only arguments with `None` defaults. All existing call sites work unchanged. New functionality activates only when kwargs are explicitly passed.
- Fallback: If any call site breaks, add the kwargs with `None` at that call site.

**RISK-6 (CSV column list)**:
- Mitigation: Add new fields (`fap`, `pass_secondary_eclipse`, `secondary_eclipse_depth_fraction`, `pass_depth_consistency`, `depth_consistency_fraction`) to `_CANDIDATE_COLUMNS` in Step 4. The JSON output uses `asdict()` and auto-includes new fields.
- Fallback: If CSV column ordering matters for downstream consumers, append new columns at the end.
