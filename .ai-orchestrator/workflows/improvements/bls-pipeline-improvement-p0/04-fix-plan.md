---
agent: fix-plan
sequence: 4
references: ["root-cause"]
summary: "Fix plan for 7 P0 defects across 9 files. 14 changes ordered: preset fixes (O3, 4 changes) → SNR computation (B1, 3 changes) → vetting inconclusive (V1, 2 changes) → normalization flag (P2, 2 changes) → per-sector refinement (O2, 1 change) → adaptive window (P1, 1 change) → plot redesign (PL1, 1 change). Primary risk: BLSCandidate field addition is a breaking change for any code that unpacks the dataclass positionally."
---

## Fix Strategy
- **Approach**: Fix each of the 7 defects independently in the order recommended by the context (O3 → B1 → V1 → P2 → O2 → P1 → PL1). Each fix is minimal and addresses only the specific root cause. Preset fixes first to unblock visual verification; SNR next as highest-impact; plot redesign last as most complex.
- **Rationale**: The root-cause analysis confirmed all 7 defects are independent. Fixing in dependency order (presets enable visual verification, SNR enables threshold filtering, normalization flag enables correct depth computation) minimizes risk and enables incremental validation.
- **Alternative Approaches Considered**:
  1. **Fix all at once in a single commit**: Rejected — makes it impossible to isolate regressions and harder to review.
  2. **Fix only B1 (SNR) and defer the rest**: Rejected — O3 preset fixes are trivial and unblock verification; V1 silently rejects valid candidates which is a correctness issue independent of SNR.
- **Fix Principle**: Root cause correction for all 7 defects. B1 also adds a defensive threshold. V1 adds a third state (inconclusive) rather than just flipping the default.

## Changes Required

### Change 1: Fix `science-default.toml` — Enable Plots, Update Window (O3)
- **File**: `src/exohunt/presets/science-default.toml`
- **Location**: `[plot]` section and `[preprocess]` section
- **Type**: Modify configuration
- **Description**: Change `plot.enabled = false` to `plot.enabled = true`. Change `flatten_window_length = 401` to `flatten_window_length = 801`.
- **Causal Chain Link**: O3 Link 1, P1 Link 1
- **Dependencies**: None

### Change 2: Fix `quicklook.toml` — Enable BLS (O3)
- **File**: `src/exohunt/presets/quicklook.toml`
- **Location**: `[bls]` section
- **Type**: Modify configuration
- **Description**: Change `bls.enabled = false` to `bls.enabled = true`.
- **Causal Chain Link**: O3 Link 2
- **Dependencies**: None

### Change 3: Fix `deep-search.toml` — Enable Plots (O3)
- **File**: `src/exohunt/presets/deep-search.toml`
- **Location**: `[plot]` section
- **Type**: Modify configuration
- **Description**: Change `plot.enabled = false` to `plot.enabled = true`.
- **Causal Chain Link**: O3 Link 3
- **Dependencies**: None

### Change 4: Add `min_snr` to `BLSConfig` (B1)
- **File**: `src/exohunt/config.py`
- **Location**: `BLSConfig` dataclass and `_DEFAULTS` dict and `resolve_runtime_config()` validation
- **Type**: Add new field
- **Description**: Add `min_snr: float` field to `BLSConfig` dataclass. Add `"min_snr": 7.0` to `_DEFAULTS["bls"]`. Add validation in `resolve_runtime_config()`: `min_snr` must be >= 0. Parse it with `_expect_float`.
- **Causal Chain Link**: B1 Link 3
- **Dependencies**: None

### Change 5: Add `snr` Field to `BLSCandidate` and Compute SNR (B1)
- **File**: `src/exohunt/bls.py`
- **Location**: `BLSCandidate` dataclass and `run_bls_search()` function
- **Type**: Modify existing code
- **Description**: Add `snr: float` field to `BLSCandidate`. In `run_bls_search()`, after computing `power`, compute `median_power = np.nanmedian(power)` and `mad_power = np.nanmedian(np.abs(power - median_power))`. For each candidate, compute `snr = (power[idx] - median_power) / (1.4826 * mad_power)` (guard against zero MAD). Add `min_snr: float = 7.0` parameter to `run_bls_search()`. Skip candidates with `snr < min_snr`. Set `snr` field on each `BLSCandidate`.
- **Causal Chain Link**: B1 Links 1-2
- **Dependencies**: Change 4

### Change 6: Pass `min_snr` Through Pipeline (B1)
- **File**: `src/exohunt/pipeline.py`
- **Location**: All calls to `run_bls_search()`
- **Type**: Modify existing code
- **Description**: Pass `min_snr` from `BLSConfig` to `run_bls_search()` in both stitched and per-sector code paths. This requires reading `min_snr` from the config and passing it as a keyword argument.
- **Causal Chain Link**: B1 Link 3
- **Dependencies**: Changes 4, 5

### Change 7: Add `odd_even_status` Field to `CandidateVettingResult` (V1)
- **File**: `src/exohunt/vetting.py`
- **Location**: `CandidateVettingResult` dataclass
- **Type**: Add new field
- **Description**: Add `odd_even_status: str` field to `CandidateVettingResult`. Values: `"pass"`, `"fail"`, `"inconclusive"`.
- **Causal Chain Link**: V1 Link 3
- **Dependencies**: None

### Change 8: Handle NaN as Inconclusive in `vet_bls_candidates()` (V1)
- **File**: `src/exohunt/vetting.py`
- **Location**: `vet_bls_candidates()` function, odd/even evaluation block
- **Type**: Modify existing code
- **Description**: When either `odd_depth_ppm` or `even_depth_ppm` is NaN, set `pass_odd_even = True` (do not penalize) and set `odd_even_status = "inconclusive"`. When both are finite and mismatch is within threshold, set `odd_even_status = "pass"`. When both are finite and mismatch exceeds threshold, set `odd_even_status = "fail"`. Update `vetting_reasons` to use `"odd_even_inconclusive"` instead of `"odd_even_depth_mismatch"` for the inconclusive case.
- **Causal Chain Link**: V1 Links 1-2
- **Dependencies**: Change 7

### Change 9: Propagate Normalization Flag from `prepare_lightcurve()` (P2)
- **File**: `src/exohunt/preprocess.py`
- **Location**: `prepare_lightcurve()` function
- **Type**: Modify existing code
- **Description**: Change return type to `tuple[lk.LightCurve, bool]` where the bool is `normalized` (True if normalization was applied, False if skipped). Return `(prepared, True)` after normalization, `(prepared, False)` when normalization is skipped.
- **Causal Chain Link**: P2 Links 1-2
- **Dependencies**: None

### Change 10: Handle Non-Normalized Flux in `run_bls_search()` (P2)
- **File**: `src/exohunt/bls.py`
- **Location**: `run_bls_search()` function
- **Type**: Modify existing code
- **Description**: Add `normalized: bool = True` parameter. When `normalized=False`, compute `depth_ppm` as `(depth / median_flux) * 1_000_000` where `median_flux = np.nanmedian(flux)` instead of `depth * 1_000_000`. Update all callers in `pipeline.py` to pass the `normalized` flag from `prepare_lightcurve()`.
- **Causal Chain Link**: P2 Link 3
- **Dependencies**: Change 9

### Change 11: Add `refine_bls_candidates()` Call to Per-Sector Path (O2)
- **File**: `src/exohunt/pipeline.py`
- **Location**: Per-sector BLS loop, after `run_bls_search()` call
- **Type**: Add new code
- **Description**: After `segment_candidates = run_bls_search(...)` in the per-sector loop, add refinement: `if segment_candidates: segment_candidates = refine_bls_candidates(lc_prepared=segment.lc, candidates=segment_candidates, period_min_days=bls_period_min_days, period_max_days=bls_period_max_days, duration_min_hours=bls_duration_min_hours, duration_max_hours=bls_duration_max_hours, n_periods=max(12000, bls_n_periods * 6), n_durations=max(20, bls_n_durations), window_fraction=0.02)`. Mirror the stitched-mode refinement call.
- **Causal Chain Link**: O2 Link 1
- **Dependencies**: None

### Change 12: Add Adaptive Window Mode to `prepare_lightcurve()` (P1)
- **File**: `src/exohunt/preprocess.py`
- **Location**: `prepare_lightcurve()` function, before flatten call
- **Type**: Add new code
- **Description**: Add `max_transit_duration_hours: float = 0.0` parameter. When `max_transit_duration_hours > 0`, compute `min_window = int(3 * max_transit_duration_hours * 60 / 2) | 1` (3× transit duration in cadences, ensure odd). Use `window = max(flatten_window_length, min_window)`. This ensures the window is never smaller than 3× the expected maximum transit duration. When `max_transit_duration_hours` is 0 (default), use `flatten_window_length` as-is for backward compatibility.
- **Causal Chain Link**: P1 Link 2
- **Dependencies**: None

### Change 13: Pass `max_transit_duration_hours` Through Pipeline (P1)
- **File**: `src/exohunt/pipeline.py`
- **Location**: Calls to `prepare_lightcurve()`
- **Type**: Modify existing code
- **Description**: Pass `max_transit_duration_hours=bls_duration_max_hours` from the BLS config to `prepare_lightcurve()` when BLS is enabled. This connects the BLS duration range to the preprocessing window sizing.
- **Causal Chain Link**: P1 Link 2
- **Dependencies**: Change 12

### Change 14: Redesign `save_raw_vs_prepared_plot()` (PL1)
- **File**: `src/exohunt/plotting.py`
- **Location**: `save_raw_vs_prepared_plot()` function
- **Type**: Modify existing code
- **Description**: Redesign the 3-panel plot to: (1) Top panel: overlay raw (gray) and prepared (purple) on same axes with shared time axis, showing the detrending effect directly. (2) Middle panel: residual plot showing `raw - prepared` trend (the removed signal). (3) Bottom panel: prepared flux with binned percentile bands (existing "new style" panel, kept as-is). Update the interactive version `save_raw_vs_prepared_plot_interactive()` with the same layout changes.
- **Causal Chain Link**: PL1 Links 1-2
- **Dependencies**: None

## Risk Assessment

| Risk | Likelihood (1-5) | Impact (1-5) | Affected Area | Mitigation |
|------|-------------------|---------------|---------------|------------|
| `BLSCandidate` field addition breaks positional unpacking | 2 | 3 | Any code constructing BLSCandidate positionally | Dataclass is frozen; add `snr` at end. Search codebase for positional construction. |
| `prepare_lightcurve()` return type change breaks callers | 3 | 4 | All callers in pipeline.py | Update all callers simultaneously. Search for all call sites. |
| `min_snr=7.0` default filters out real weak signals | 2 | 3 | Shallow transit detection | 7.0 is standard in literature; configurable via config. |
| Adaptive window increases flatten runtime for long-duration searches | 2 | 2 | Preprocessing performance | Window only increases when transit duration demands it; logged. |
| Plot redesign changes visual output format | 1 | 1 | User expectations for plot layout | Improvement over current layout; no data loss. |
| `CandidateVettingResult` field addition breaks consumers | 2 | 3 | JSON/CSV output, pipeline.py | Add field at end of dataclass. Update serialization. |

## Regression Considerations

- **Existing test suite**: All 4 test files must continue to pass. Changes 4, 5, 7, 8, 9 modify dataclass signatures which may affect test assertions. Run full test suite after each change group.
  - Likelihood: Medium (for Changes 5, 9 which change return types/signatures)
  - Detection: `pytest` run

- **Config validation**: Change 4 adds `min_snr` to `BLSConfig` and `_DEFAULTS`. Existing config files without `min_snr` must still work (default value applies).
  - Likelihood: Low (defaults handle missing keys)
  - Detection: `test_config.py`

- **Candidate JSON/CSV output**: Changes 5, 7 add fields to output dataclasses. Existing output consumers must handle new fields gracefully.
  - Likelihood: Low (additive change)
  - Detection: Inspect output format after fix

- **Pipeline.py callers of `prepare_lightcurve()`**: Change 9 changes return type from `LightCurve` to `tuple[LightCurve, bool]`. Every caller must be updated.
  - Likelihood: High if any caller is missed
  - Detection: `pytest`, runtime errors

## Verification Plan

### Primary Verification: Bugs Are Fixed
1. **B1**: Call `run_bls_search()` on synthetic data with known signal; verify `snr` field exists and candidates below `min_snr` are excluded.
2. **V1**: Call `vet_bls_candidates()` with candidate where one parity group has < 5 in-transit points; verify `pass_odd_even = True` and `odd_even_status = "inconclusive"`.
3. **P1**: Verify `science-default.toml` has `flatten_window_length = 801`. Call `prepare_lightcurve()` with `max_transit_duration_hours=6.0` and `flatten_window_length=401`; verify effective window ≥ 3×6h in cadences.
4. **P2**: Call `prepare_lightcurve()` on light curve with near-zero median; verify returns `(lc, False)`. Pass `normalized=False` to `run_bls_search()`; verify `depth_ppm` uses median-relative computation.
5. **O2**: Run pipeline in per-sector mode; verify `refine_bls_candidates()` is called (mock or trace).
6. **O3**: Load each preset and verify: `science-default` has `plot.enabled=True`, `quicklook` has `bls.enabled=True`, `deep-search` has `plot.enabled=True`.
7. **PL1**: Call `save_raw_vs_prepared_plot()` and verify output has overlay panel and residual panel (check axes titles or panel count).

### Secondary Verification: No Regressions
1. Full `pytest` suite passes.
2. Existing config files (without `min_snr`) load without error.
3. `run_bls_search()` with default parameters produces same candidates for normalized input (SNR filtering may reduce count — this is correct behavior).
4. `prepare_lightcurve()` with normal flux returns `(lc, True)` — normalized path unchanged.

### Tertiary Verification: Blast Radius
1. `refine_bls_candidates()` propagates `snr` field correctly.
2. Candidate JSON/CSV output includes new fields (`snr`, `odd_even_status`).
3. Interactive plot function `save_raw_vs_prepared_plot_interactive()` also updated with new layout.

## Rollback Plan
- **Rollback Method**: `git revert` of the fix commits. Each defect fix should be a separate commit for granular rollback.
- **Rollback Trigger**: Any existing test failure, or pipeline producing no candidates on known-transit targets (over-aggressive SNR filtering).
- **Rollback Impact**: Original bugs return. Acceptable as temporary state since the pipeline has been operating with these defects.
- **Time Window**: Run on 5+ known transit targets after fix to validate before considering stable.

## Fix Scope Boundary

### In Scope
- All 7 P0 defects (B1, V1, P1, P2, O2, O3, PL1)
- Config schema additions (`min_snr`)
- Return type change for `prepare_lightcurve()`
- Plot redesign for static and interactive versions

### Out of Scope
- P1 issues from the quality audit (FAP computation, alias ratios, secondary eclipse check, pipeline decomposition) — tracked separately for next phase
- `compute_bls_periodogram()` SNR normalization — related to B1 but diagnostic-only; track as follow-up
- Comprehensive test coverage expansion — current tests must pass; new tests added only for P0 fixes
- Performance optimization of adaptive window — functional correctness only
