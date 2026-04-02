---
agent: research
sequence: 1
references: []
summary: "Comprehensive quality audit of the Exohunt BLS transit-search pipeline identifying 28 issues (7 P0, 12 P1, 9 P2) across detection, vetting, preprocessing, visualization, and configuration. The pipeline finds strong signals but lacks statistical significance metrics (no SNR/FAP), silently rejects valid shallow candidates via overly strict vetting thresholds, and produces charts where raw and detrended data are visually indistinguishable. Primary recommendation is to implement BLS SNR computation and false-alarm probability before any other improvement."
---

## 1. Research Objective

**Topic**: Quality audit of the Exohunt exoplanet transit-search pipeline — bug identification, visualization assessment, and improvement roadmap.

**Motivation**: The pipeline currently finds strong transit signals but has no mechanism to assess statistical significance (no SNR/FAP), has vetting logic that silently rejects valid shallow candidates, and produces charts where raw and detrended data look nearly identical. A thorough audit is needed to identify every issue and produce a prioritized improvement roadmap.

**Scope**: All modules in the pipeline: `bls.py`, `vetting.py`, `preprocess.py`, `parameters.py`, `pipeline.py`, `config.py`, `plotting.py`, and the three built-in presets. Excludes: `ingest.py`, `cache.py`, `comparison.py`, `cli.py`, `models.py`, `progress.py` (these are I/O and utility modules not directly involved in the scientific pipeline).

**Key Questions**:
1. What correctness bugs exist in the BLS search, vetting, preprocessing, and parameter estimation modules?
2. Does the pipeline have a principled detection threshold, or does it return candidates regardless of statistical significance?
3. Under what conditions does the vetting logic silently reject valid candidates?
4. Can the Savitzky-Golay flattening suppress real transit signals, and if so, under what conditions?
5. What standard transit-search diagnostic plots are missing from the current visualization suite?
6. What configuration parameters are hardcoded that should be user-configurable?
7. How does the pipeline rate on detection sensitivity, false positive control, preprocessing quality, diagnostic output, code quality, configuration flexibility, and reproducibility?

## 2. Methodology

**Sources**: Direct source code analysis of all 13 Python modules, 3 preset TOML files, and `pyproject.toml`. Evaluation against established transit-search practices from Kepler/K2/TESS literature (BLS algorithm by Kovács et al. 2002, TLS by Hippke & Heller 2019, TESS-SPOC pipeline documentation, lightkurve best practices).

**Evaluation Criteria**: Correctness (does the code do what it claims), completeness (are standard pipeline stages present), robustness (edge case handling), configurability (can behavior be tuned without code changes), diagnostic quality (can a human reviewer assess candidate quality from the outputs), and maintainability (modularity, testability).

**Constraints**: Python 3.10+, must remain compatible with existing `RuntimeConfig`/preset system, no new heavy dependencies beyond lightkurve/astropy/numpy/matplotlib, recommendations must be independently deployable.

## 3. Findings

### 3.1 BLS Search Module (`bls.py`)

#### Issue B1 — No SNR Computation [P0]
**Location**: `run_bls_search()`, lines 55-115
**Description**: The function returns raw BLS `power` values but never computes signal-to-noise ratio. BLS power is not comparable across different light curves or even different period ranges within the same light curve because it depends on the number of in-transit points, baseline scatter, and period grid density. Without SNR, there is no principled way to determine whether a detection is statistically significant.
**Impact**: The pipeline returns the top-N peaks regardless of whether any of them represent a real signal. A light curve with pure noise will still produce 5 "candidates."
**Fix**: After computing the BLS periodogram, estimate the noise floor by computing the median and MAD (median absolute deviation) of the power array, then compute SNR = (peak_power - median_power) / (1.4826 * MAD_power). A standard threshold of SNR ≥ 7 is commonly used in transit surveys. Add `snr` field to `BLSCandidate`.
**Complexity**: ~20 lines of code. No new dependencies.

#### Issue B2 — No False-Alarm Probability [P1]
**Location**: `run_bls_search()`, lines 55-115
**Description**: No false-alarm probability (FAP) is computed. FAP quantifies the probability that a peak of given power would arise from noise alone, accounting for the number of independent frequencies searched.
**Impact**: Without FAP, there is no way to rank candidates by statistical confidence or set a detection threshold that accounts for the search parameter space.
**Fix**: Implement bootstrap FAP estimation: shuffle the flux values N times (e.g., 1000), run BLS on each shuffled light curve, record the maximum power, and compute FAP as the fraction of shuffled maxima exceeding the observed power. Alternatively, use the analytic approximation from Kovács et al. (2002). Add `fap` field to `BLSCandidate`.
**Complexity**: ~40 lines for bootstrap method. Adds ~30s per candidate at N=1000 shuffles. Could be optional via config flag.

#### Issue B3 — 2% Deduplication Filter Too Aggressive [P1]
**Location**: `_unique_period()`, lines 35-42
**Description**: The `unique_period_separation_fraction=0.02` (2%) filter discards any candidate whose period is within 2% of an already-selected candidate. For a 10-day period, this means periods within 0.2 days are considered duplicates. In multi-planet systems, close-period planets (e.g., TRAPPIST-1 b at 1.51d and c at 2.42d — ratio 1.60) would not be affected, but near-resonant pairs (e.g., periods at 3.0d and 3.05d — 1.7% separation) would lose the weaker signal.
**Impact**: Real close-period planets in near-resonant configurations could be discarded.
**Fix**: Increase default to 5% or make it configurable via `BLSConfig`. Additionally, check period ratios against known resonance patterns (2:1, 3:2, 4:3) before discarding.
**Complexity**: ~10 lines. Config schema change.

#### Issue B4 — Refinement Re-instantiates Full BLS Model [P2]
**Location**: `refine_bls_candidates()`, lines 165-210
**Description**: For each candidate, `refine_bls_candidates()` calls `run_bls_search()` which creates a new `BoxLeastSquares` model instance, re-validates inputs, re-sorts time arrays, and re-checks finite values. The BLS model could be instantiated once and reused.
**Impact**: Performance only — roughly 5× overhead for the refinement step on a typical 5-candidate run. Not a correctness issue.
**Fix**: Extract model instantiation from `run_bls_search()` into a separate function, or add an internal `_run_bls_on_model()` that accepts a pre-built model.
**Complexity**: ~30 lines refactor.

#### Issue B5 — Duplicate Code Between `run_bls_search` and `compute_bls_periodogram` [P2]
**Location**: `run_bls_search()` lines 55-100, `compute_bls_periodogram()` lines 120-160
**Description**: Both functions contain identical input validation, time sorting, period grid construction, and duration grid construction. This violates DRY and means bug fixes must be applied in two places.
**Fix**: Extract shared setup into a private `_prepare_bls_inputs()` function.
**Complexity**: ~20 lines refactor.

### 3.2 Vetting Module (`vetting.py`)

#### Issue V1 — Odd/Even Test Fails Instead of "Inconclusive" for Shallow/Long-Period Candidates [P0]
**Location**: `_group_depth_ppm()`, lines 24-38; `vet_bls_candidates()`, lines 75-85
**Description**: `_group_depth_ppm()` requires ≥5 in-transit and ≥10 out-of-transit points per parity group. When these thresholds are not met (common for shallow transits with few observed transits, or long-period candidates with only 2-3 transits total), the function returns `NaN`. In `vet_bls_candidates()`, when `odd_depth_ppm` or `even_depth_ppm` is NaN, `pass_odd_even` is set to `False` (line 85: the `if np.isfinite(...)` check fails, so `pass_odd_even` stays `False`). This means the candidate **fails** vetting due to insufficient data rather than being marked "inconclusive."
**Impact**: Valid shallow or long-period candidates are silently rejected. A planet with only 3 observed transits (1 odd, 2 even) will always fail the odd/even test because neither parity group has enough points, even though the odd/even test is simply not applicable in this case.
**Fix**: Add an `inconclusive` state to the odd/even test. When either depth is NaN, set `pass_odd_even = True` (benefit of the doubt) and add `vetting_reasons` entry like `"odd_even_inconclusive(insufficient_data)"`. Add a `odd_even_status` field to `CandidateVettingResult` with values: `"pass"`, `"fail"`, `"inconclusive"`.
**Complexity**: ~15 lines.

#### Issue V2 — Missing Common BLS Alias Ratios [P1]
**Location**: `_alias_harmonic_reference_rank()`, lines 45-65
**Description**: The function checks period ratios of 0.5, 2.0, 1/3, and 3.0 but misses the common BLS aliases at 2/3 (≈0.667) and 3/2 (1.5). These are among the most common BLS aliases because the box-shaped transit model can fit at these harmonic ratios when the true signal has a specific duty cycle.
**Impact**: Candidates that are 2/3 or 3/2 aliases of a stronger signal are not flagged, leading to false positives in the candidate list.
**Fix**: Add `2.0/3.0` and `3.0/2.0` to the `ratios` tuple. Consider also adding `1/4` (0.25) and `4.0` for completeness.
**Complexity**: 1 line change.

#### Issue V3 — No Phase-Fold Depth Consistency Check [P1]
**Location**: `vet_bls_candidates()` — missing functionality
**Description**: The vetting module has no check that compares the BLS-fitted depth with the actual phase-folded depth. A real transit should show consistent depth when phase-folded, while a noise peak or systematic artifact will show inconsistent depth across different subsets of the data.
**Impact**: Noise peaks that happen to produce a high BLS power but have inconsistent phase-folded depths are not caught.
**Fix**: Add a `_phase_fold_depth_consistency()` function that phase-folds the light curve at the candidate period, measures the in-transit depth in multiple subsets (e.g., first half vs. second half of observations), and flags candidates where the depth varies by more than a configurable threshold (e.g., 50%).
**Complexity**: ~40 lines.

#### Issue V4 — No Secondary Eclipse Check [P1]
**Location**: `vet_bls_candidates()` — missing functionality
**Description**: No check for a secondary eclipse at phase 0.5 (half-period offset from the primary transit). A secondary eclipse of comparable depth to the primary suggests an eclipsing binary rather than a planet transit.
**Impact**: Eclipsing binaries with similar primary and secondary eclipse depths are not flagged, leading to false positives.
**Fix**: Add a `_secondary_eclipse_check()` that measures the depth at phase 0.5 ± duration/2 and compares it to the primary transit depth. Flag if secondary depth > configurable fraction (e.g., 30%) of primary depth.
**Complexity**: ~30 lines.

#### Issue V5 — Hardcoded Vetting Thresholds [P1]
**Location**: `pipeline.py` lines 108-113
**Description**: `_VETTING_MIN_TRANSIT_COUNT`, `_VETTING_ODD_EVEN_MAX_MISMATCH_FRACTION`, `_VETTING_ALIAS_TOLERANCE_FRACTION`, `_PARAMETER_STELLAR_DENSITY_KG_M3`, `_PARAMETER_DURATION_RATIO_MIN`, `_PARAMETER_DURATION_RATIO_MAX` are module-level constants in `pipeline.py`, not exposed through `RuntimeConfig` or the preset system.
**Impact**: Users cannot tune vetting behavior without editing source code. Different science cases (e.g., searching for ultra-short-period planets vs. long-period planets) require different thresholds.
**Fix**: Add a `VettingConfig` dataclass to `config.py` with these parameters. Add a `[vetting]` section to the TOML schema and presets.
**Complexity**: ~50 lines across config.py, pipeline.py, and preset files.

### 3.3 Preprocessing Module (`preprocess.py`)

#### Issue P1 — Savitzky-Golay Window Can Suppress Transit Depth [P0]
**Location**: `prepare_lightcurve()`, lines 140-175
**Description**: The default `flatten_window_length=401` cadences corresponds to ~13.4 hours at TESS 2-minute cadence. For the Savitzky-Golay filter to avoid suppressing a transit signal, the window should be at least 3× the transit duration (a common rule of thumb from Aigrain & Irwin 2004). For a 6-hour transit, the minimum safe window is 18 hours (~540 cadences). The current 401-cadence window is only 2.2× a 6-hour transit duration, which can suppress 10-30% of the transit depth.
**Impact**: Long-duration transits (hot Jupiters around evolved stars, or planets at longer periods) will have their depths systematically underestimated, reducing detection sensitivity and biasing radius estimates.
**Fix**: (a) Increase the default `flatten_window_length` to 801 (already used in `quicklook` and `deep-search` presets but not in `science-default`). (b) Add an adaptive window mode that sets window = max(user_setting, 3 × max_duration_cadences) based on the BLS duration search range. (c) Document the relationship between window length and maximum detectable transit duration.
**Complexity**: 5 lines for (a), ~25 lines for (b).

#### Issue P2 — Normalization Fallback Silently Changes Depth Semantics [P0]
**Location**: `prepare_lightcurve()`, lines 148-152
**Description**: When `median_flux` is near zero (abs < 1e-12), normalization is skipped with a warning. Downstream, `depth_ppm` in `BLSCandidate` is computed as `depth * 1_000_000.0`, which assumes the light curve is normalized to median ≈ 1.0. If normalization was skipped, `depth` is in raw flux units and `depth_ppm` is meaningless.
**Impact**: For any light curve where the median flux is near zero (rare but possible with certain TESS data products or after aggressive outlier removal), all depth and depth_ppm values are wrong by orders of magnitude.
**Fix**: (a) Propagate a `normalized` boolean flag through the pipeline. (b) In `run_bls_search()`, check if the light curve is normalized and either raise an error or compute depth differently. (c) Consider using `depth / median_flux * 1e6` instead of `depth * 1e6` to be robust to non-normalized inputs.
**Complexity**: ~20 lines across preprocess.py and bls.py.

#### Issue P3 — No Transit Masking Before Flattening [P1]
**Location**: `prepare_lightcurve()` — missing functionality
**Description**: The Savitzky-Golay flattening treats transit dips as part of the baseline trend. For deep transits (>1000 ppm), this pulls the baseline down during transit, reducing the apparent transit depth after flattening. Standard practice in transit-search pipelines (e.g., TLS, TESS-SPOC) is to iteratively mask known transits before re-flattening.
**Impact**: Deep transits have their depths reduced by the flattening step. The effect is proportional to transit depth and inversely proportional to window length.
**Fix**: Add an optional iterative masking mode: (1) flatten without masking, (2) run BLS to find candidates, (3) mask in-transit points, (4) re-flatten, (5) re-run BLS. This is a pipeline-level change in `pipeline.py`.
**Complexity**: ~40 lines in pipeline.py. Doubles BLS runtime.

#### Issue P4 — `science-default` Flatten Window Is Suboptimal [P2]
**Location**: `presets/science-default.toml`, line 12
**Description**: `science-default` uses `flatten_window_length = 401` while both `quicklook` and `deep-search` use `flatten_window_length = 801`. The science-default preset is the recommended workflow for actual transit searching, yet it uses the most aggressive (shortest) flattening window.
**Impact**: The default science workflow suppresses more transit depth than the quick-look workflow.
**Fix**: Change `science-default` to `flatten_window_length = 801`.
**Complexity**: 1 line change.

### 3.4 Parameter Estimation Module (`parameters.py`)

#### Issue E1 — Solar-Density Assumption for All Targets [P1]
**Location**: `estimate_candidate_parameters()`, line 12; `_expected_central_duration_hours()`
**Description**: The module assumes solar density (1408 kg/m³) for all host stars. For M-dwarfs (density ~5000-20000 kg/m³) and subgiants (density ~200-500 kg/m³), this produces incorrect duration expectations and radius estimates.
**Impact**: Duration plausibility checks will incorrectly flag valid candidates around non-solar-type stars. Radius estimates can be off by 2-5× for M-dwarf hosts.
**Fix**: (a) Make `stellar_density_kg_m3` a per-target parameter (could be looked up from TIC catalog via lightkurve). (b) Add a warning to the output when solar density is assumed. (c) Widen the duration ratio bounds to account for unknown stellar type.
**Complexity**: ~30 lines for (a) with TIC lookup, 5 lines for (b) and (c).

#### Issue E2 — Limb Darkening Ignored in Depth-to-Radius Conversion [P2]
**Location**: `estimate_candidate_parameters()`, lines 75-80
**Description**: The `depth ≈ (Rp/Rs)²` approximation ignores limb darkening. For typical TESS bandpass limb darkening coefficients, this underestimates the radius ratio by ~5-15%.
**Impact**: Systematic underestimate of planet radii. Not a detection issue but affects parameter accuracy.
**Fix**: Apply a limb-darkening correction factor. For TESS bandpass with typical solar-type limb darkening (u₁≈0.4, u₂≈0.2), the correction is approximately `Rp/Rs = sqrt(depth / (1 - u₁/3 - u₂/6))`. Add this as an optional correction with configurable limb darkening coefficients.
**Complexity**: ~15 lines.

### 3.5 Pipeline Orchestration (`pipeline.py`)

#### Issue O1 — `fetch_and_plot()` Is a 600-Line Monolith [P1]
**Location**: `pipeline.py`, `fetch_and_plot()` function
**Description**: This single function handles data download, caching, preprocessing, BLS search, refinement, vetting, parameter estimation, plotting, candidate output, metrics, and manifest writing. It is untestable in isolation — you cannot test BLS search without also triggering download, caching, and plotting.
**Impact**: Any change to one pipeline stage risks breaking others. Unit testing individual stages requires mocking the entire pipeline. New features (e.g., iterative transit masking) are difficult to add without increasing the monolith further.
**Fix**: Decompose into a pipeline of discrete stages: `ingest_stage()`, `preprocess_stage()`, `search_stage()`, `vetting_stage()`, `parameter_stage()`, `plotting_stage()`, `output_stage()`. Each stage takes typed inputs and returns typed outputs. `fetch_and_plot()` becomes a thin orchestrator that calls each stage in sequence.
**Complexity**: ~200 lines refactor (moving existing code, not writing new logic).

#### Issue O2 — Per-Sector BLS Skips Refinement [P0]
**Location**: `pipeline.py` — per-sector BLS code path
**Description**: When BLS runs in per-sector mode, `refine_bls_candidates()` is not called. Only the stitched-mode code path includes refinement. This means per-sector BLS candidates have lower period precision than stitched-mode candidates.
**Impact**: Per-sector mode produces less accurate period estimates. Since per-sector mode is useful for detecting transits that appear in only some sectors (e.g., due to systematics), this is a real science impact.
**Fix**: Call `refine_bls_candidates()` in the per-sector code path as well.
**Complexity**: ~5 lines.

#### Issue O3 — `science-default` Preset Disables Plotting [P0]
**Location**: `presets/science-default.toml`, line 16: `enabled = false`
**Description**: The `science-default` preset — the recommended workflow for actual transit searching — has `plot.enabled = false`. This means the default science workflow produces zero visual output. A user running `python -m exohunt.cli run --target "TIC 261136679" --config science-default` gets candidate CSVs and JSONs but no plots to visually inspect the light curve or candidates.
**Impact**: Users cannot visually verify preprocessing quality or candidate validity without manually re-running with a different config. This defeats the purpose of having diagnostic plots.
**Fix**: Change `science-default` to `plot.enabled = true`.
**Complexity**: 1 line change.

#### Issue O4 — `quicklook` Preset Disables BLS [P1]
**Location**: `presets/quicklook.toml`, line 20: `enabled = false`
**Description**: The `quicklook` preset has `bls.enabled = false`. While "quicklook" implies fast inspection, a quick-look mode that cannot find transits is of limited use for a transit-search pipeline.
**Impact**: Users doing quick inspection cannot find transits at all. They must switch to `science-default` (which has no plots) or `deep-search` (which is slow).
**Fix**: Enable BLS in quicklook with reduced parameters (fewer periods, fewer durations, top_n=3) for a fast but functional search. The current quicklook BLS settings (n_periods=1200, top_n=3) are already reasonable — just set `enabled = true`.
**Complexity**: 1 line change.

#### Issue O5 — `deep-search` Preset Disables Static Plots [P1]
**Location**: `presets/deep-search.toml`, line 16: `enabled = false`
**Description**: `deep-search` has `plot.enabled = false` but `interactive_html = true`. However, `interactive_html` only controls whether interactive HTML plots are generated *in addition to* static plots. With `plot.enabled = false`, no plots of any kind are generated.
**Impact**: The deep-search workflow produces no visual output despite having `interactive_html = true`.
**Fix**: Set `plot.enabled = true` in deep-search preset.
**Complexity**: 1 line change.

### 3.6 Plotting Module (`plotting.py`)

#### Issue PL1 — Raw vs. Prepared Panels Look Nearly Identical [P0]
**Location**: `save_raw_vs_prepared_plot()`, lines 120-175
**Description**: The 3-panel plot shows: (1) raw scatter, (2) prepared scatter, (3) prepared binned percentile band. Panels 1 and 2 look nearly identical for typical TESS data because the detrending effect is subtle at full-timeseries scale. The y-axis scales differ (raw flux vs. relative flux) but the visual pattern is the same.
**Impact**: A human reviewer cannot quickly assess whether preprocessing is working correctly. The plot fails its primary purpose of showing the effect of detrending.
**Fix**: Replace the 3-panel layout with a more informative design:
  - Panel 1: Raw and prepared data overlaid on the same axes (raw in gray, prepared in color) with a shared y-axis in ppm
  - Panel 2: Residual plot (raw minus prepared trend) showing what was removed by flattening
  - Panel 3: Prepared data with binned percentile bands (keep current panel 3)
  - Panel 4 (optional): Zoom on a representative segment showing transit-scale features
**Complexity**: ~60 lines to redesign the plot function.

#### Issue PL2 — BLS Diagnostics Lack Key Annotations [P1]
**Location**: `save_candidate_diagnostics()`, lines 260-340
**Description**: The BLS diagnostic plots (periodogram + phase-fold) are functional but lack:
  (a) SNR annotation on the periodogram peak
  (b) Transit model overlay on the phase-fold plot
  (c) Odd/even transit comparison subplot
  (d) Secondary eclipse check panel
  (e) Candidate parameter annotations (period, depth, duration, vetting status)
**Impact**: A human reviewer must cross-reference the candidate CSV/JSON to assess quality. The plots alone are insufficient for vetting.
**Fix**: Add annotations and additional subplots to `save_candidate_diagnostics()`. Standard transit-search diagnostic suites (e.g., TESS-SPOC Data Validation reports, TLS diagnostic plots) include all of these elements.
**Complexity**: ~100 lines for annotations, ~80 lines for odd/even and secondary eclipse subplots.

#### Issue PL3 — No Residual Plot [P1]
**Location**: `save_raw_vs_prepared_plot()` — missing functionality
**Description**: No plot shows the difference between raw and prepared data (the removed trend). This is the most direct way to verify that flattening removed instrumental trends without suppressing transit signals.
**Impact**: Cannot visually verify that the flattening step is working correctly.
**Fix**: Add a residual panel showing `raw_flux / prepared_flux` (the removed trend) or `raw_flux - prepared_flux * median(raw_flux)`.
**Complexity**: ~20 lines (part of PL1 fix).

#### Issue PL4 — Binned Percentile Band Smooths Out Transit Dips [P2]
**Location**: `_binned_summary()`, lines 65-95
**Description**: The binned percentile band in panel 3 uses `bin_width_days=0.02` (28.8 minutes). For a 2-hour transit, this means ~4 bins span the transit. The subsequent 9-point smoothing (`_smooth_series(window=9)`) further blurs the transit signal. Individual transit dips are not visible in this representation.
**Impact**: The "new style" panel cannot show individual transits. It's useful for showing overall scatter but not for transit detection verification.
**Fix**: (a) Reduce smoothing window or make it configurable. (b) Add a separate panel with un-smoothed binned data at finer resolution for transit-scale features.
**Complexity**: ~10 lines.

### 3.7 Configuration Module (`config.py`)

#### Issue C1 — No Vetting Configuration Section [P1]
**Location**: `config.py` — missing `VettingConfig` dataclass
**Description**: Vetting parameters are hardcoded in `pipeline.py` (lines 108-113) and not part of the config schema. The `RuntimeConfig` dataclass has sections for IO, Ingest, Preprocess, Plot, and BLS, but no Vetting section.
**Impact**: Users cannot tune vetting behavior through config files or presets. Same as V5.
**Fix**: Same as V5 — add `VettingConfig` to the schema.
**Complexity**: ~50 lines.

#### Issue C2 — No Parameter Estimation Configuration Section [P2]
**Location**: `config.py` — missing `ParameterConfig` dataclass
**Description**: Parameter estimation settings (`stellar_density`, `duration_ratio_min/max`) are hardcoded in `pipeline.py`. Not configurable.
**Impact**: Users cannot adjust parameter estimation assumptions without editing source code.
**Fix**: Add `ParameterConfig` dataclass with `stellar_density_kg_m3`, `duration_ratio_min`, `duration_ratio_max`, `apply_limb_darkening_correction`, `limb_darkening_u1`, `limb_darkening_u2`.
**Complexity**: ~30 lines.

## 4. Comparison Matrix

This is a single-system deep audit rather than a multi-option comparison. The following Capability Assessment rates the current pipeline against standard transit-search pipeline requirements.

| Capability | Current State | Standard Practice | Gap Severity |
|-----------|--------------|-------------------|-------------|
| Detection threshold | Top-N by raw BLS power, no significance test | SNR ≥ 7 or FAP < 0.1% threshold | P0 — Critical |
| SNR computation | Not implemented | SNR = (peak - median) / (1.4826 × MAD) | P0 — Critical |
| False-alarm probability | Not implemented | Bootstrap or analytic FAP | P1 — High |
| Odd/even transit test | Fails on insufficient data instead of inconclusive | Inconclusive when data insufficient | P0 — Critical |
| Alias detection | Checks 0.5, 2, 1/3, 3 ratios | Also checks 2/3, 3/2, 1/4, 4 | P1 — High |
| Secondary eclipse check | Not implemented | Check depth at phase 0.5 | P1 — High |
| Phase-fold consistency | Not implemented | Compare depth across data subsets | P1 — High |
| Transit masking before flatten | Not implemented | Iterative mask-flatten-search | P1 — High |
| Adaptive flatten window | Fixed window, no transit-aware sizing | Window ≥ 3× max transit duration | P0 — Critical |
| Normalization safety | Silent fallback skips normalization | Error or explicit flag propagation | P0 — Critical |
| Raw vs. prepared visualization | 3 panels, panels 1-2 nearly identical | Overlay + residual + zoom | P0 — Critical |
| BLS diagnostic annotations | Period line only | SNR, model overlay, odd/even, secondary | P1 — High |
| Vetting configurability | Hardcoded in pipeline.py | Config file / preset tunable | P1 — High |
| Pipeline modularity | 600-line monolith | Discrete typed stages | P1 — High |
| Preset correctness | science-default has no plots, quicklook has no BLS | All presets produce useful output | P0 — Critical |

## 5. Trade-offs

### Approach A: Incremental Fixes (Recommended)
- **Advantages**:
  - Each fix is independently deployable (constraint from context)
  - Low risk — each change is small and testable
  - Can prioritize P0 issues first for immediate science impact
  - No architectural disruption to existing users
- **Disadvantages**:
  - The 600-line monolith in pipeline.py gets harder to maintain with each incremental fix
  - Some fixes interact (e.g., SNR computation needs to happen before vetting can use it)
  - Total effort is higher than a clean rewrite of the pipeline orchestration
- **Best Suited For**: Active project with existing users who need backward compatibility
- **Worst Suited For**: Greenfield rewrite where clean architecture is more important than backward compatibility

### Approach B: Pipeline Architecture Refactor First, Then Fixes
- **Advantages**:
  - Decomposing the monolith first makes all subsequent fixes cleaner
  - Each stage becomes independently testable
  - New features (iterative masking, multi-planet search) are easier to add
- **Disadvantages**:
  - Larger upfront investment (~200 lines of refactoring) before any science improvement
  - Risk of introducing regressions during refactoring
  - Delays P0 science fixes
- **Best Suited For**: Project with good test coverage that can catch regressions
- **Worst Suited For**: Project needing immediate science improvements (current situation)

### Recommended Sequence
Fix P0 issues first (SNR, vetting inconclusive, preset fixes, normalization safety, raw-vs-prepared plot redesign), then refactor the pipeline monolith, then address P1 and P2 issues in the cleaner architecture.

## 6. Risks and Limitations

### Research Risks

**Risk R1**: SNR threshold of 7 may be too aggressive or too conservative for TESS data specifically.
- **Likelihood**: Medium
- **Impact**: Too aggressive → missed real planets. Too conservative → too many false positives.
- **Mitigation**: Implement SNR computation first, then calibrate the threshold empirically by running on known planet hosts and known non-detections. Make threshold configurable.

**Risk R2**: Iterative transit masking doubles BLS runtime.
- **Likelihood**: High (by design)
- **Impact**: `deep-search` preset already takes significant time; doubling it may be impractical for batch mode.
- **Mitigation**: Make iterative masking optional via config flag. Default off for quicklook, optional for science-default, default on for deep-search.

**Risk R3**: Refactoring pipeline.py monolith may introduce regressions.
- **Likelihood**: Medium
- **Impact**: Existing test suite (test_smoke.py at 30K lines) provides some coverage but may not catch subtle behavioral changes.
- **Mitigation**: Add integration tests that compare full pipeline output (candidate list, metrics) before and after refactoring. Use the existing comparison/manifest system.

**Risk R4**: Adding VettingConfig and ParameterConfig to the schema is a breaking change for existing config files.
- **Likelihood**: Low (new sections with defaults are additive, not breaking)
- **Impact**: Existing config files continue to work because new sections use defaults.
- **Mitigation**: Use the existing `_DEFAULTS` mechanism in config.py — new sections get default values when not specified in user config.

### Research Limitations
- Runtime performance impact of SNR/FAP computation was estimated, not benchmarked. Actual impact depends on light curve length and BLS grid density.
- The limb darkening correction factor (Issue E2) uses a simplified approximation. A full treatment would require per-target stellar parameters from TIC.
- The assessment of transit depth suppression by Savitzky-Golay flattening (Issue P1) is based on the 3× rule of thumb. Actual suppression depends on transit shape, noise level, and the specific SG polynomial order used by lightkurve's `flatten()`.
- This audit did not examine `ingest.py`, `cache.py`, `comparison.py`, `cli.py`, `models.py`, or `progress.py` as they are I/O and utility modules outside the scientific pipeline scope.

## 7. Recommendations

### P0 — Critical (implement first)

**R1: Implement BLS SNR computation**
- **Priority**: P0
- **Recommendation**: Add SNR = (peak_power - median_power) / (1.4826 × MAD_power) to `run_bls_search()`. Add `snr` field to `BLSCandidate`. Add configurable `min_snr` threshold (default 7.0) to `BLSConfig`. Only return candidates above threshold.
- **Justification**: Issues B1. Without SNR, the pipeline has no principled detection threshold. This is the single most impactful improvement.
- **Confidence Level**: High — SNR-based thresholding is standard practice in every major transit survey.
- **Validation Step**: Run on TIC 261136679 (known planet host) and verify the real planet candidate has SNR > 7 while noise peaks have SNR < 5.
- **Complexity**: ~25 lines in bls.py, ~5 lines in config.py.

**R2: Fix odd/even vetting to return "inconclusive" instead of "fail"**
- **Priority**: P0
- **Recommendation**: When `_group_depth_ppm()` returns NaN for either parity, set `pass_odd_even = True` and `odd_even_status = "inconclusive"`. Add `odd_even_status` field to `CandidateVettingResult`.
- **Justification**: Issue V1. Currently silently rejects valid shallow/long-period candidates.
- **Confidence Level**: High — this is a clear logic bug.
- **Validation Step**: Run on a target with only 3 observed transits and verify the candidate is not rejected due to odd/even test.
- **Complexity**: ~15 lines in vetting.py.

**R3: Fix all three preset files**
- **Priority**: P0
- **Recommendation**: (a) `science-default.toml`: set `plot.enabled = true`, change `flatten_window_length = 801`. (b) `quicklook.toml`: set `bls.enabled = true`. (c) `deep-search.toml`: set `plot.enabled = true`.
- **Justification**: Issues O3, O4, O5, P4. The default science workflow produces no plots, the quick-look mode cannot find transits, and the deep-search mode produces no visual output.
- **Confidence Level**: High — these are configuration errors, not design trade-offs.
- **Validation Step**: Run each preset and verify it produces both candidates and plots.
- **Complexity**: 4 line changes across 3 files.

**R4: Fix normalization fallback to propagate state**
- **Priority**: P0
- **Recommendation**: Add a `normalized: bool` attribute to the returned light curve (or return a tuple). In `run_bls_search()`, check normalization state and compute depth_ppm correctly for non-normalized inputs.
- **Justification**: Issue P2. Silent normalization skip makes all downstream depth values meaningless.
- **Confidence Level**: High — clear correctness bug.
- **Validation Step**: Create a test with a light curve whose median flux is near zero and verify depth_ppm is handled correctly.
- **Complexity**: ~20 lines across preprocess.py and bls.py.

**R5: Redesign raw-vs-prepared plot**
- **Priority**: P0
- **Recommendation**: Replace the current 3-panel layout with: (1) overlay of raw and prepared on same axes, (2) residual (removed trend), (3) prepared with binned percentile bands, (4) optional zoom on representative segment.
- **Justification**: Issue PL1. The current plot fails its primary purpose — panels 1 and 2 look identical.
- **Confidence Level**: High — overlay + residual is standard in every transit-search pipeline.
- **Validation Step**: Generate plots for TIC 261136679 and visually confirm the detrending effect is clearly visible.
- **Complexity**: ~60 lines in plotting.py.

**R6: Fix per-sector BLS to include refinement**
- **Priority**: P0
- **Recommendation**: Call `refine_bls_candidates()` in the per-sector BLS code path.
- **Justification**: Issue O2. Per-sector candidates have lower period precision than stitched candidates.
- **Confidence Level**: High — clear omission.
- **Validation Step**: Run per-sector BLS and verify refined periods match stitched-mode precision.
- **Complexity**: ~5 lines in pipeline.py.

### P1 — High Priority (implement after P0)

**R7: Implement bootstrap FAP estimation**
- **Priority**: P1
- **Recommendation**: Add optional FAP computation via bootstrap (N=1000 shuffles). Add `fap` field to `BLSCandidate`. Make it configurable via `BLSConfig.compute_fap` (default False for quicklook, True for science-default and deep-search).
- **Justification**: Issue B2.
- **Confidence Level**: Medium — bootstrap FAP is standard but adds significant runtime.
- **Complexity**: ~40 lines in bls.py, ~5 lines in config.py.

**R8: Add missing alias ratios to vetting**
- **Priority**: P1
- **Recommendation**: Add 2/3 and 3/2 to the alias ratio check in `_alias_harmonic_reference_rank()`.
- **Justification**: Issue V2.
- **Confidence Level**: High.
- **Complexity**: 1 line in vetting.py.

**R9: Add secondary eclipse check**
- **Priority**: P1
- **Recommendation**: Add `_secondary_eclipse_check()` to vetting.py.
- **Justification**: Issue V4.
- **Confidence Level**: High.
- **Complexity**: ~30 lines.

**R10: Add phase-fold depth consistency check**
- **Priority**: P1
- **Recommendation**: Add `_phase_fold_depth_consistency()` to vetting.py.
- **Justification**: Issue V3.
- **Confidence Level**: Medium.
- **Complexity**: ~40 lines.

**R11: Add VettingConfig and ParameterConfig to config schema**
- **Priority**: P1
- **Recommendation**: Add `[vetting]` and `[parameters]` sections to config.py schema and all presets.
- **Justification**: Issues V5, C1, C2.
- **Confidence Level**: High.
- **Complexity**: ~80 lines across config.py, pipeline.py, and preset files.

**R12: Add BLS diagnostic annotations**
- **Priority**: P1
- **Recommendation**: Add SNR annotation, transit model overlay, odd/even comparison subplot, and secondary eclipse panel to `save_candidate_diagnostics()`.
- **Justification**: Issue PL2.
- **Confidence Level**: High.
- **Complexity**: ~180 lines in plotting.py.

**R13: Implement iterative transit masking**
- **Priority**: P1
- **Recommendation**: Add optional iterative mask-flatten-search cycle in pipeline.py.
- **Justification**: Issue P3.
- **Confidence Level**: Medium — significant runtime impact.
- **Complexity**: ~40 lines in pipeline.py.

**R14: Decompose pipeline.py monolith**
- **Priority**: P1
- **Recommendation**: Split `fetch_and_plot()` into discrete typed stages.
- **Justification**: Issue O1.
- **Confidence Level**: High.
- **Complexity**: ~200 lines refactor.

### P2 — Nice to Have

**R15: Refactor BLS duplicate code** — Issue B5. ~20 lines.
**R16: Optimize BLS refinement model reuse** — Issue B4. ~30 lines.
**R17: Widen deduplication filter or make configurable** — Issue B3. ~10 lines.
**R18: Add limb darkening correction** — Issue E2. ~15 lines.
**R19: Reduce binned percentile smoothing** — Issue PL4. ~10 lines.
**R20: Add TIC stellar density lookup** — Issue E1. ~30 lines.

## 8. Pipeline Rating

| Dimension | Score | Justification | Steps to 10/10 |
|-----------|-------|---------------|-----------------|
| Detection sensitivity | 4/10 | Finds strong signals but no SNR threshold means noise peaks are returned as candidates. No FAP. Fixed flatten window can suppress long-duration transits. | Implement SNR (R1), FAP (R7), adaptive flatten window (P1 fix), iterative masking (R13). |
| False positive control | 3/10 | Odd/even test silently rejects valid candidates (V1). Missing alias ratios (V2). No secondary eclipse check (V4). No phase-fold consistency (V3). | Fix odd/even inconclusive (R2), add alias ratios (R8), secondary eclipse (R9), phase-fold consistency (R10). |
| Preprocessing quality | 5/10 | Savitzky-Golay flattening works but window is too short for long transits in science-default. Normalization fallback is unsafe. No transit masking. | Fix window (R3), fix normalization (R4), add iterative masking (R13). |
| Diagnostic output | 3/10 | science-default produces no plots. Raw-vs-prepared panels look identical. BLS diagnostics lack annotations. No residual plot. | Fix presets (R3), redesign raw-vs-prepared (R5), add annotations (R12). |
| Code quality | 5/10 | Clean individual modules but pipeline.py is a 600-line monolith. Duplicate code in bls.py. Good use of dataclasses and type hints. | Decompose monolith (R14), extract shared BLS code (R15). |
| Configuration flexibility | 5/10 | Good config system with presets and layered overrides, but vetting and parameter estimation are hardcoded. | Add VettingConfig and ParameterConfig (R11). |
| Reproducibility | 8/10 | Strong manifest system with config fingerprints, software versions, and comparison keys. Run-to-run comparison is built in. | Minor: include SNR/FAP parameters in manifest once implemented. Already near 10/10. |

**Overall Pipeline Score: 4.7/10**

The pipeline has a solid foundation (good config system, reproducibility tracking, clean module structure) but critical gaps in detection statistics, vetting logic, and diagnostic output prevent it from being a reliable transit-search tool. The P0 fixes (R1-R6) would raise the score to approximately 7/10. Completing all P1 fixes would bring it to 9/10.
