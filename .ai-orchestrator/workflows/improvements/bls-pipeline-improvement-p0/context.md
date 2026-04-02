# Project: BLS Pipeline P0 Critical Fixes

## Type
bugfix

## Description
Implement all 7 P0 Critical issues identified in the BLS pipeline quality audit. These are the highest-priority fixes required before the pipeline can be considered a reliable transit-search tool.

### B1 — No SNR Computation (`bls.py`, `run_bls_search()` lines 55-115)
The pipeline returns raw BLS power values with no signal-to-noise ratio. Without SNR, there is no principled detection threshold — pure noise produces 5 "candidates." Fix: compute SNR = (peak_power - median_power) / (1.4826 × MAD_power), add `snr` field to `BLSCandidate`, add configurable `min_snr` threshold (default 7.0) to `BLSConfig`, only return candidates above threshold. ~25 lines in bls.py, ~5 lines in config.py.

### V1 — Odd/Even Test Fails Instead of "Inconclusive" (`vetting.py`, `_group_depth_ppm()` lines 24-38, `vet_bls_candidates()` lines 75-85)
When insufficient in-transit points exist per parity group, `_group_depth_ppm()` returns NaN, and `vet_bls_candidates()` sets `pass_odd_even = False`. Valid shallow or long-period candidates (e.g., only 3 observed transits) are silently rejected. Fix: when either depth is NaN, set `pass_odd_even = True` and add `odd_even_status = "inconclusive"` field to `CandidateVettingResult`. ~15 lines.

### P1 — Savitzky-Golay Window Can Suppress Transit Depth (`preprocess.py`, `prepare_lightcurve()` lines 140-175)
Default `flatten_window_length=401` (~13.4h at 2-min cadence) is only 2.2× a 6-hour transit duration. Safe minimum is 3× transit duration. This suppresses 10-30% of long-duration transit depths. Fix: (a) increase `science-default` to 801, (b) add adaptive window mode: `window = max(user_setting, 3 × max_duration_cadences)`. ~5 lines for (a), ~25 lines for (b).

### P2 — Normalization Fallback Silently Changes Depth Semantics (`preprocess.py`, `prepare_lightcurve()` lines 148-152)
When `median_flux` is near zero, normalization is skipped silently. Downstream `depth_ppm = depth * 1_000_000` assumes normalized flux ≈ 1.0, making all depth values meaningless for non-normalized inputs. Fix: propagate a `normalized: bool` flag, check it in `run_bls_search()`, compute depth_ppm correctly for non-normalized inputs. ~20 lines across preprocess.py and bls.py.

### O2 — Per-Sector BLS Skips Refinement (`pipeline.py`, per-sector BLS code path)
`refine_bls_candidates()` is only called in the stitched-mode code path. Per-sector candidates have lower period precision. Fix: call `refine_bls_candidates()` in the per-sector code path. ~5 lines.

### O3 — `science-default` Preset Disables Plotting + `quicklook` Disables BLS + `deep-search` Disables Plots
- `science-default.toml`: `plot.enabled = false` → no visual output from the default science workflow. Also `flatten_window_length = 401` is suboptimal (should be 801).
- `quicklook.toml`: `bls.enabled = false` → quick-look mode cannot find transits at all.
- `deep-search.toml`: `plot.enabled = false` → no plots despite `interactive_html = true`.
Fix: 4 line changes across 3 preset files.

### PL1 — Raw vs. Prepared Panels Look Nearly Identical (`plotting.py`, `save_raw_vs_prepared_plot()` lines 120-175)
Panels 1 (raw) and 2 (prepared) look nearly identical at full-timeseries scale. The plot fails its purpose of showing detrending effect. Fix: redesign to (1) overlay raw+prepared on same axes, (2) residual plot showing removed trend, (3) prepared with binned percentile bands, (4) optional zoom segment. ~60 lines.

## Background
The BLS pipeline quality audit (`.ai-orchestrator/workflows/research/bls-pipeline-issues/01-research.md`) identified 28 issues across the pipeline. These 7 P0 issues represent critical gaps in detection statistics, vetting correctness, preprocessing safety, preset configuration, and diagnostic visualization. The pipeline currently scores 4.7/10 overall; fixing P0 issues would raise it to ~7/10.

## Constraints
- Python 3.10+
- Must remain compatible with existing `RuntimeConfig`/preset system
- No new heavy dependencies beyond lightkurve/astropy/numpy/matplotlib
- Each fix must be independently deployable
- Existing test suite (`test_smoke.py`) must continue to pass
- Backward compatible — existing config files must still work (new config sections use defaults)

## Existing Code/System
- Repository: `/Users/gbasin/Development/exoplanets-hunting-pipeline`
- Key files:
  - `src/exohunt/bls.py` — BLS search and refinement (B1)
  - `src/exohunt/vetting.py` — candidate vetting (V1)
  - `src/exohunt/preprocess.py` — light curve preprocessing (P1, P2)
  - `src/exohunt/pipeline.py` — pipeline orchestration, hardcoded vetting constants (O2)
  - `src/exohunt/plotting.py` — visualization (PL1)
  - `src/exohunt/config.py` — RuntimeConfig and preset loading
  - `src/exohunt/parameters.py` — parameter estimation
  - `presets/science-default.toml`, `presets/quicklook.toml`, `presets/deep-search.toml` (O3)
- Research: `.ai-orchestrator/workflows/research/bls-pipeline-issues/01-research.md`

## Success Criteria
1. `run_bls_search()` returns candidates with `snr` field; candidates below `min_snr` (default 7.0) are excluded
2. Odd/even vetting returns `"inconclusive"` (not fail) when insufficient data; valid shallow candidates are no longer silently rejected
3. `science-default` uses `flatten_window_length = 801`; adaptive window mode available
4. Non-normalized light curves propagate state; `depth_ppm` is correct regardless of normalization
5. Per-sector BLS candidates go through `refine_bls_candidates()`
6. All three presets produce both candidates and plots when applicable
7. Raw-vs-prepared plot clearly shows detrending effect via overlay + residual panels
8. All existing tests pass

## Additional Notes
- Recommended implementation order: preset fixes (O3) → SNR (B1) → vetting inconclusive (V1) → normalization safety (P2) → per-sector refinement (O2) → flatten window (P1) → plot redesign (PL1)
- Preset fixes are trivial 1-line changes and unblock visual verification of all subsequent fixes
- SNR implementation is the single most impactful improvement — enables principled detection thresholds
- After P0 completion, proceed to P1 issues (FAP, alias ratios, secondary eclipse check, pipeline decomposition, etc.)
