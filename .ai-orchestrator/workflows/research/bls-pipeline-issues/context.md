# Project: BLS Pipeline Quality Audit & Improvement Roadmap

## Type
research

## Description
Perform a comprehensive quality audit of the Exohunt transit-search pipeline. The research should cover three areas:

### Area 1: Bug & Issue Identification
Analyze every module in the pipeline for correctness issues, silent failures, edge cases, and algorithmic weaknesses. For each issue found, classify severity as P0 (blocks correct results), P1 (degrades quality), or P2 (cosmetic / performance).

Key modules to audit (with specific concerns):

- **`bls.py`** — `run_bls_search()` returns raw BLS `power` but never computes SNR or false-alarm probability. There is no principled detection threshold — the pipeline returns top-N peaks regardless of statistical significance. The `_unique_period()` 2% deduplication filter may discard real close-period planets. `refine_bls_candidates()` re-instantiates the full BLS model per candidate instead of reusing it. `depth` and `depth_ppm` assume the light curve is normalized to median=1.0, but `prepare_lightcurve` has a fallback path that skips normalization.
- **`vetting.py`** — `_group_depth_ppm()` requires ≥5 in-transit and ≥10 out-of-transit points per parity group; for shallow/long-period candidates this threshold is rarely met, causing the odd/even test to return NaN and the candidate to **fail** instead of being marked "inconclusive". `_alias_harmonic_reference_rank()` checks ratios (0.5, 2.0, 1/3, 3.0) but misses common BLS aliases at 2/3 and 3/2. No phase-fold depth consistency check exists to distinguish real harmonics from aliases.
- **`preprocess.py`** — `prepare_lightcurve()` uses Savitzky-Golay flatten with default window=401 cadences (~13.4 h at 2-min cadence). For long-duration transits (>6 h) the window is <2× the transit duration, which can suppress 10-30% of transit depth. No mechanism exists to mask known transits before flattening. The normalization fallback (skip when median≈0) silently changes the meaning of downstream `depth_ppm` values.
- **`parameters.py`** — `estimate_candidate_parameters()` assumes solar-density host star for all targets. The `depth ≈ (Rp/Rs)²` approximation ignores limb darkening, which underestimates radius ratio by ~5-15% for typical TESS targets.
- **`pipeline.py`** — `fetch_and_plot()` is a ~600-line monolith mixing I/O, caching, preprocessing, BLS, vetting, plotting, and manifest writing. Per-sector BLS mode does not run `refine_bls_candidates()` (only stitched mode does). Vetting constants are hardcoded module-level variables, not exposed through `RuntimeConfig`.
- **`config.py`** — Vetting parameters (`min_transit_count`, `odd_even_mismatch_max_fraction`, `alias_tolerance_fraction`) and parameter estimation settings (`stellar_density`, `duration_ratio_min/max`) are not in the config schema — they're hardcoded in `pipeline.py`. The `science-default` preset disables plotting (`plot.enabled = false`), which means the default science workflow produces no visual output.
- **`plotting.py`** — The raw-vs-prepared plot shows 3 panels but the "old style" panels (panels 1 and 2) are basic scatter plots that look nearly identical for well-behaved light curves, making it hard to see the effect of detrending. There is no panel showing the raw and prepared data overlaid on the same axes for direct comparison. The "new style" panel (panel 3) uses binned percentile bands which smooth out individual transit dips. No residual plot (raw minus prepared) exists. The BLS diagnostics (periodogram + phase-fold) lack: (a) SNR annotation, (b) transit model overlay on phase-fold, (c) odd/even transit comparison subplot, (d) secondary eclipse check.

### Area 2: Chart & Visualization Quality
The current plots don't clearly show the difference between raw and detrended data. Research and recommend:
- What plot types are standard in transit-search pipelines (Kepler, TESS-SPOC, TLS)
- What's missing from the current diagnostic suite
- How to make the raw-vs-prepared comparison visually obvious (overlay, residual, zoom panels)
- What candidate diagnostic plots are essential for vetting (odd/even depth comparison, secondary eclipse phase, centroid motion if available)
- Specific matplotlib/plotly implementation recommendations

### Area 3: Pipeline Rating & Improvement Roadmap
Rate the current pipeline on a 0-10 scale across these dimensions:
- **Detection sensitivity**: ability to find real transits at various depths/periods
- **False positive control**: ability to reject non-planetary signals
- **Preprocessing quality**: detrending effectiveness without signal suppression
- **Diagnostic output**: quality and completeness of plots and artifacts
- **Code quality**: modularity, testability, maintainability
- **Configuration flexibility**: ability to tune behavior without code changes
- **Reproducibility**: deterministic runs, manifest tracking

For each dimension, explain the current score and list concrete steps to reach 10/10.

## Background
The pipeline currently finds strong transit signals well but has no mechanism to assess statistical significance (no SNR/FAP), has vetting logic that silently rejects valid shallow candidates, and produces charts where raw and detrended data look nearly identical — making it hard to verify preprocessing is working correctly. The goal is a thorough audit that identifies every issue and produces a prioritized improvement roadmap.

## Constraints
- Python 3.10+
- Must remain compatible with existing `RuntimeConfig` / preset system (`src/exohunt/config.py`)
- No new heavy dependencies (lightkurve, astropy, numpy, matplotlib already available)
- Recommendations should be implementable incrementally — each fix should be independently deployable

## Existing Code/System
- Repository: `/Users/gbasin/Development/exoplanets-hunting-pipeline`
- BLS search: `src/exohunt/bls.py` — `run_bls_search()`, `refine_bls_candidates()`, `compute_bls_periodogram()`, `_unique_period()`
- Vetting: `src/exohunt/vetting.py` — `vet_bls_candidates()`, `_alias_harmonic_reference_rank()`, `_group_depth_ppm()`
- Preprocessing: `src/exohunt/preprocess.py` — `prepare_lightcurve()`, `compute_preprocessing_quality_metrics()`
- Parameter estimation: `src/exohunt/parameters.py` — `estimate_candidate_parameters()`
- Pipeline orchestration: `src/exohunt/pipeline.py` — `fetch_and_plot()` (main entry), `run_batch_analysis()`
- Config system: `src/exohunt/config.py` — `RuntimeConfig`, `BLSConfig`, `PreprocessConfig`
- Plotting: `src/exohunt/plotting.py` — `save_raw_vs_prepared_plot()`, `save_candidate_diagnostics()`
- Presets: `src/exohunt/presets/` — quicklook (BLS disabled, plots enabled), science-default (BLS enabled, plots disabled), deep-search (wider search, interactive HTML)
- Tests: `tests/test_smoke.py`, `tests/test_config.py`, `tests/test_cli.py`, `tests/test_analysis_modules.py`

## Success Criteria
- Every bug/issue in the pipeline is identified with severity classification (P0/P1/P2), affected code location, and concrete fix description
- Chart analysis includes specific before/after recommendations with references to standard transit-search visualization practices
- Pipeline rating is provided per-dimension (0-10) with current score justification and specific steps to reach 10/10
- All recommendations are prioritized and estimated for implementation complexity (lines of code, new dependencies if any)
- The research document is actionable enough that a developer can implement fixes directly from it without further investigation

## Human Gates
research

## Additional Notes
- The `science-default` preset has `plot.enabled = false` — this means the most common science workflow produces zero visual output, which is a significant usability issue
- The `quicklook` preset has `bls.enabled = false` — so the quick inspection mode cannot find transits at all
- The 3-panel raw/prepared plot currently shows: (1) raw scatter, (2) prepared scatter, (3) prepared binned percentile band. Panels 1 and 2 look nearly identical for typical TESS data because the detrending effect is subtle at full-timeseries scale
- The BLS diagnostic plots (periodogram + phase-fold) are functional but lack annotations that would help a human reviewer quickly assess candidate quality
- Vetting hardcoded constants in `pipeline.py` lines ~100-106: `_VETTING_MIN_TRANSIT_COUNT = 2`, `_VETTING_ODD_EVEN_MAX_MISMATCH_FRACTION = 0.30`, `_VETTING_ALIAS_TOLERANCE_FRACTION = 0.02`, `_PARAMETER_STELLAR_DENSITY_KG_M3 = 1408.0`
- `fetch_and_plot()` is ~600 lines and handles everything from download to manifest writing — this monolith makes it hard to test individual pipeline stages in isolation
