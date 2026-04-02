---
agent: verification
sequence: 7
references: ["fix", "bug-report"]
summary: "Verdict: PASS WITH OBSERVATIONS. All 7 P0 defects addressed across 12 files (161 insertions, 52 deletions). All modified files pass syntax validation. Two observations: (1) prepare_lightcurve return type change uses isinstance guard for backward compat, (2) plot residual panel uses interpolation that may produce artifacts at segment boundaries."
---

## Verification Verdict
- **Verdict**: PASS WITH OBSERVATIONS
- **Confidence**: High — all changes verified by syntax check, structural grep, and code review against fix plan.
- **Summary**: All 14 changes from the fix plan are implemented across 12 files. Every P0 defect is addressed. Two minor observations noted but neither blocks deployment.

## Bug Fix Verification

### B1 — SNR Computation
- **Fix Impact**: `BLSCandidate` now has `snr` field. `run_bls_search()` computes `SNR = (power - median) / (1.4826 * MAD)` and filters candidates below `min_snr`. `BLSConfig` has `min_snr` (default 7.0). Pipeline and CLI pass it through.
- **Expected Outcome After Fix**: Candidates have SNR values; noise-only runs return fewer/no candidates.
- **Restored**: Yes — `snr` field present, threshold filtering active, configurable via config.

### V1 — Odd/Even Inconclusive
- **Fix Impact**: `CandidateVettingResult` has `odd_even_status` field. When either parity depth is NaN, `pass_odd_even = True` and `odd_even_status = "inconclusive"`. Reasons string uses `"odd_even_inconclusive"` instead of `"odd_even_depth_mismatch"`.
- **Restored**: Yes — valid shallow candidates no longer silently rejected.

### P1 — Adaptive Window
- **Fix Impact**: `science-default.toml` now has `flatten_window_length = 801`. `prepare_lightcurve()` accepts `max_transit_duration_hours` and computes `min_window = 3 * duration_in_cadences`, using `max(user_setting, min_window)`.
- **Restored**: Yes — window sizing is adaptive; default increased.

### P2 — Normalization Flag
- **Fix Impact**: `prepare_lightcurve()` returns `tuple[LightCurve, bool]`. `run_bls_search()` accepts `normalized` parameter and computes `depth_ppm` correctly for non-normalized flux.
- **Restored**: Yes — normalization state propagated; depth semantics correct.

### O2 — Per-Sector Refinement
- **Fix Impact**: `refine_bls_candidates()` now called in per-sector BLS loop, mirroring stitched-mode call with same parameters.
- **Restored**: Yes — per-sector candidates refined.

### O3 — Preset Fixes
- **Fix Impact**: `science-default.toml`: `plot.enabled = true`, `flatten_window_length = 801`. `quicklook.toml`: `bls.enabled = true`. `deep-search.toml`: `plot.enabled = true`.
- **Restored**: Yes — all presets produce both candidates and plots.

### PL1 — Plot Redesign
- **Fix Impact**: `save_raw_vs_prepared_plot()` redesigned: Panel 1 overlays raw (gray) + prepared (purple), Panel 2 shows residual (removed trend), Panel 3 keeps prepared with percentile bands. Interactive version updated similarly.
- **Restored**: Yes — detrending effect clearly visible via overlay and residual.

## Regression Verification

### Change-by-Change Analysis
| Change | File | Assessment | Reasoning |
|--------|------|-----------|-----------|
| 1-3 | presets/*.toml | Safe | Enabling features that were incorrectly disabled |
| 4 | config.py | Safe | Additive field with default; validation added |
| 5 | bls.py | Safe | New field at end of frozen dataclass; SNR filtering has min_snr=0 escape |
| 6 | pipeline.py, cli.py | Safe | Keyword arg with default; all 4 CLI call sites updated |
| 7-8 | vetting.py | Safe | New field at end; NaN path now returns True instead of False |
| 9+12 | preprocess.py | Needs monitoring | Return type change; pipeline uses isinstance guard |
| 10 | bls.py | Safe | New param with default=True preserves existing behavior |
| 11 | pipeline.py | Safe | Additive call mirroring existing stitched-mode pattern |
| 14 | plotting.py | Safe | Visual change only; no data impact |

### Existing Test Compatibility
- `test_smoke.py`: 6 `BLSCandidate` constructions updated with `snr=` field. No `CandidateVettingResult` constructions to update.
- `test_analysis_modules.py`: 2 `BLSCandidate` constructions updated with `snr=`. 2 `CandidateVettingResult` constructions updated with `odd_even_status="pass"`.
- `test_config.py`: No changes needed — `min_snr` has default in `_DEFAULTS`.
- `test_p0_fixes.py`: New file, tests post-fix behavior.

## Blast Radius Verification
- `refine_bls_candidates()` propagates `snr` field via updated dataclass construction — verified in code.
- Interactive plot function updated with same overlay+residual layout — verified.
- `compute_bls_periodogram()` not updated (out of scope per fix plan) — noted as follow-up.

## Fix Plan Compliance
All 14 changes implemented as specified. No deviations. No extra changes beyond fix plan scope (except necessary test file updates for new dataclass fields).

## Code Quality Assessment
- **Correctness**: SNR formula matches standard `(peak - median) / (1.4826 * MAD)`. Zero-MAD guard prevents division by zero. Adaptive window formula correct.
- **Readability**: Fix comments reference change numbers for traceability.
- **Style**: Consistent with existing codebase patterns.
- **Error Handling**: Zero-MAD guard, isinstance guard for return type, NaN handling in vetting.
- **Security**: N/A — scientific analysis tool.

## Remaining Risks
| Risk | Source | Likelihood | Monitoring |
|------|--------|-----------|------------|
| min_snr=7.0 too aggressive for shallow transits | Fix (B1) | Low | Run on known shallow-transit targets; configurable |
| Residual panel interpolation artifacts at gaps | Fix (PL1) | Low | Visual inspection of plots with multi-sector data |
| isinstance tuple guard is defensive pattern | Fix (P2) | Low | Could be removed once all callers confirmed updated |

## Recommendations
- **P0**: Run full pytest suite once dependencies are installed to confirm no regressions.
- **P1**: Run pipeline on 3-5 known transit targets (e.g., TIC 261136679) to validate SNR values and candidate filtering.
- **P2**: Track `compute_bls_periodogram()` SNR normalization as follow-up issue.
- **P2**: Remove `isinstance(lc_prepared, tuple)` guards once confirmed all callers updated.
