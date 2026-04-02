---
agent: bug-report
sequence: 1
references: []
summary: "The BLS transit-search pipeline has 7 P0 critical defects: missing SNR computation returns noise as candidates, odd/even vetting silently rejects valid shallow transits, Savitzky-Golay window suppresses long-duration transit depths, normalization fallback corrupts depth semantics, per-sector BLS skips refinement, all three presets have broken enable flags, and the raw-vs-prepared plot fails to show detrending effect. Pipeline scores 4.7/10 overall."
---

## Bug Title
BLS Pipeline: 7 P0 Critical Defects in Detection, Vetting, Preprocessing, Presets, and Visualization

## Severity Assessment
**Severity: Critical**

The pipeline's primary purpose is transit detection, and the most impactful defect (B1: no SNR computation) means there is no principled detection threshold — pure noise produces 5 "candidates." Combined with V1 (valid candidates silently rejected), P1 (transit depths suppressed by 10-30%), P2 (depth_ppm meaningless for non-normalized inputs), and O3 (default preset disables plotting, quicklook disables BLS), the pipeline cannot reliably detect, vet, or visualize transits. These defects affect every run of the pipeline.

## Environment
- **Operating System**: Not specified in context — needs clarification (development observed on macOS)
- **Runtime/Platform**: Python 3.10+
- **Dependencies**: lightkurve, astropy, numpy, matplotlib, pandas (from pyproject.toml)
- **Configuration**: Three built-in TOML presets (science-default, quicklook, deep-search) plus user config files
- **Infrastructure**: Local execution pipeline; no server infrastructure
- **Browser/Client**: Not applicable (CLI tool)

## Description
The BLS exoplanet transit-search pipeline contains 7 P0 critical defects identified during a quality audit. The defects span detection statistics (no SNR), vetting correctness (odd/even test rejects valid candidates), preprocessing safety (window suppresses depth, normalization fallback corrupts semantics), pipeline orchestration (per-sector BLS skips refinement), preset configuration (all three presets have broken enable flags), and diagnostic visualization (raw-vs-prepared plot panels look identical). Together these defects render the pipeline unreliable for its core purpose of transit detection.

## Steps to Reproduce

### B1 — No SNR Computation
**Precondition**: Any target with TESS light curve data.
1. Run `python -m exohunt.cli run --target "TIC 261136679" --config science-default`
2. Inspect candidates output JSON in `outputs/tic_261136679/candidates/`
3. Observe: candidates have `power` field but no `snr` field
4. Observe: pure noise light curves produce 5 "candidates" with no threshold filtering

### V1 — Odd/Even Test Fails Instead of Inconclusive
**Precondition**: Target with shallow or long-period transit (few observed transits, e.g., 3).
1. Run BLS search producing candidates where one parity group has fewer than 5 in-transit points
2. `_group_depth_ppm()` returns NaN for that group
3. `vet_bls_candidates()` sets `pass_odd_even = False` (line ~85 of vetting.py)
4. Observe: valid candidate is rejected; `vetting_reasons` includes `odd_even_depth_mismatch`

### P1 — Savitzky-Golay Window Suppresses Transit Depth
**Precondition**: Light curve with long-duration transit (~6 hours).
1. Run with `science-default` preset (`flatten_window_length = 401`)
2. At 2-min cadence, 401 points = ~13.4 hours; ratio to 6-hour transit = 2.2×
3. Safe minimum ratio is 3× transit duration
4. Observe: transit depth suppressed by 10-30% in prepared light curve

### P2 — Normalization Fallback Silently Changes Depth Semantics
**Precondition**: Light curve where `median_flux` is near zero.
1. `prepare_lightcurve()` skips normalization (line ~152 of preprocess.py)
2. No flag is propagated downstream
3. `run_bls_search()` computes `depth_ppm = depth * 1_000_000` assuming normalized flux ≈ 1.0
4. Observe: all depth_ppm values are meaningless for non-normalized inputs

### O2 — Per-Sector BLS Skips Refinement
**Precondition**: Run with `bls.mode = "per-sector"`.
1. Run pipeline with per-sector BLS mode
2. Inspect pipeline.py per-sector code path (lines ~1100-1210)
3. Observe: `refine_bls_candidates()` is never called for per-sector candidates
4. Compare: stitched-mode code path (line ~1239) does call `refine_bls_candidates()`

### O3 — Preset Configuration Defects
1. Inspect `presets/science-default.toml`: `plot.enabled = false` — no visual output from default science workflow; `flatten_window_length = 401` (suboptimal, should be 801)
2. Inspect `presets/quicklook.toml`: `bls.enabled = false` — quick-look mode cannot find transits
3. Inspect `presets/deep-search.toml`: `plot.enabled = false` despite `interactive_html = true` — no plots generated

### PL1 — Raw vs. Prepared Panels Look Nearly Identical
1. Run pipeline with plotting enabled
2. Open generated `*_prepared_*.png` file
3. Observe: Panel 1 (raw) and Panel 2 (prepared) look nearly identical at full-timeseries scale
4. The plot fails to show the detrending effect

## Expected Behavior
1. **B1**: `run_bls_search()` returns candidates with `snr` field; candidates below configurable `min_snr` (default 7.0) are excluded
2. **V1**: When insufficient in-transit points exist per parity group, odd/even test returns `"inconclusive"` (not fail); valid shallow candidates are not rejected
3. **P1**: `science-default` uses `flatten_window_length = 801`; adaptive window mode ensures window ≥ 3× max transit duration
4. **P2**: Non-normalized light curves propagate a `normalized` flag; `depth_ppm` is computed correctly regardless of normalization state
5. **O2**: Per-sector BLS candidates go through `refine_bls_candidates()` for improved period precision
6. **O3**: All three presets produce both candidates and plots when applicable
7. **PL1**: Raw-vs-prepared plot clearly shows detrending effect via overlay and residual panels

## Actual Behavior
1. **B1**: No `snr` field exists on `BLSCandidate`; no threshold filtering; pure noise returns 5 candidates
2. **V1**: `pass_odd_even = False` when either depth is NaN; valid candidates silently rejected with reason `odd_even_depth_mismatch`
3. **P1**: `flatten_window_length = 401` (~13.4h at 2-min cadence) is only 2.2× a 6-hour transit; 10-30% depth suppression
4. **P2**: Normalization skip is logged as warning but no flag propagated; `depth_ppm = depth * 1_000_000` assumes normalized flux
5. **O2**: `refine_bls_candidates()` only called in stitched-mode code path; per-sector candidates have lower period precision
6. **O3**: `science-default` disables plots; `quicklook` disables BLS; `deep-search` disables plots
7. **PL1**: Panels 1 and 2 are nearly identical scatter plots at full-timeseries scale

## Frequency and Scope
- **Frequency**: Always — all 7 defects are deterministic and present in every applicable run
- **Affected Users**: All users of the pipeline
- **Affected Environments**: All environments (local development, CI)
- **First Observed**: Identified during BLS pipeline quality audit
- **Regression**: Not a regression — these are original implementation gaps

## Available Evidence

### Error Messages
None — these are silent logic defects, not crashes.

### Log Excerpts
- P2 produces: `"preprocessing: skipping normalization (median flux is near zero)."` — but no downstream flag is set.

### Stack Traces
None provided — no exceptions are thrown.

### Screenshots or Visual Evidence
- PL1: The README shows example screenshots (`assets/screenshots/example-prepared-lightcurve.png`) demonstrating the current 3-panel plot layout where panels 1 and 2 are visually similar.

### Metrics or Monitoring Data
- Quality audit scored the pipeline 4.7/10 overall; fixing P0 issues would raise it to ~7/10.

## Initial Observations
- **Observation**: B1 (no SNR) is the single most impactful defect — without SNR, there is no principled way to distinguish real detections from noise.
- **Observation**: V1 and P2 interact — if normalization is skipped (P2), depth values are wrong, which could further confuse the odd/even test (V1).
- **Observation**: O3 preset fixes are trivial 1-line changes per file and unblock visual verification of all subsequent fixes.
- **Observation**: The per-sector code path in pipeline.py (O2) is structurally similar to the stitched path but missing the `refine_bls_candidates()` call — likely an oversight during implementation.
- **Observation**: PL1 requires the most significant code change (~60 lines) as it involves redesigning the plot layout.
- **Observation**: The context recommends implementation order: O3 → B1 → V1 → P2 → O2 → P1 → PL1.
- **Observation**: All fixes must maintain backward compatibility with existing config files and pass the existing test suite.
