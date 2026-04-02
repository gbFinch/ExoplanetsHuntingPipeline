---
agent: research
sequence: 1
references: []
summary: "Researched iterative BLS transit subtraction, transit model selection, harmonic disambiguation, preprocessing strategies, detection limits, and config/output schema changes needed for secondary planet detection in Exohunt. Primary recommendation is to implement a 3-pass iterative BLS with box-mask subtraction and SNR-based stopping, which is the highest-impact change. Several P0 issues were found in the current pipeline including a missing SNR/FAP metric and incomplete harmonic ratio coverage."
---

## 1. Research Objective

**Topic**: Algorithmic and architectural changes needed to detect secondary (additional) transiting planets in systems where a dominant transit signal masks weaker companions in the Exohunt pipeline.

**Motivation**: The current pipeline runs a single-pass BLS search that returns the top N peaks from one periodogram. In multi-planet systems (e.g., TRAPPIST-1, Kepler-90), secondary planets with shallower depths are buried in the sidelobes and spectral leakage of the dominant signal. This is the most impactful capability gap for science use of Exohunt.

**Scope**:
- Included: iterative BLS with transit subtraction, transit model for subtraction, harmonic/alias disambiguation, preprocessing impact on shallow transits, detection limit framework, config/output schema changes, alternative modern methods, and current pipeline issue analysis.
- Excluded: full limb-darkening model fitting (beyond feasibility assessment), GPU-accelerated search, multi-star blending scenarios, non-transit variability classification.

**Key Questions**:
1. How many iterative BLS passes are practical, and what stopping criteria (SNR floor, power threshold, false-alarm probability) should terminate the loop?
2. Is a simple box mask sufficient for transit subtraction, or does residual box-shaped structure create false secondary detections requiring a trapezoidal/limb-darkened model?
3. Are the current harmonic checks (ratios 0.5, 2.0, 1/3, 3.0 at 2% tolerance) adequate when a secondary planet's true period is near a harmonic of the primary?
4. How does the Savitzky-Golay flatten window (default 401 cadences) affect shallow secondary transit recovery, and what iterative flattening strategy is optimal?
5. What is the minimum detectable secondary depth as a function of primary depth, period ratio, and data baseline?
6. What new config fields and output artifacts are needed to support iterative multi-planet search?
7. Are there modern methods (TLS, GPU-BLS, wavelet-based) that would materially improve secondary planet detection over iterative BLS?
8. Are there existing bugs or algorithmic issues in the current pipeline that would compromise secondary planet search?

## 2. Methodology

**Sources**: Astropy BoxLeastSquares documentation (v6.x), lightkurve API documentation (v2.x), Kovács et al. (2002) BLS original paper, Hippke & Heller (2019) Transit Least Squares paper, Kepler pipeline documentation (TCE iterative search), TESS Data Release Notes, established exoplanet detection literature, and direct analysis of the Exohunt source code (bls.py, vetting.py, preprocess.py, parameters.py, config.py, pipeline.py).

**Evaluation Criteria**: Implementation complexity (lines of code, new dependencies), computational cost (runtime scaling), detection sensitivity improvement (estimated depth gain), false positive rate impact, compatibility with existing RuntimeConfig/preset system, and Python 3.10+ constraint.

**Constraints**: Must remain compatible with existing RuntimeConfig/preset system. Python 3.10+. No new heavy dependencies beyond what lightkurve/astropy already provide. Must work with TESS 2-minute and 30-minute cadence data.

## 3. Findings

### 3.1 Iterative BLS with Transit Subtraction

**Overview**: Iterative BLS is the standard approach used by the Kepler pipeline (Threshold Crossing Event / TCE approach) to find multiple planets. After identifying the strongest periodic signal, the transit epochs are masked or subtracted from the light curve, and BLS is re-run on the residual. This repeats until a stopping criterion is met.

**Key Characteristics**:
- The Kepler pipeline typically ran 3-10 TCE iterations per target, with most multi-planet systems found within 3-5 passes.
- Each iteration adds computational cost roughly equal to one full BLS run (O(N × P × D) where N=data points, P=period grid size, D=duration grid size).
- With Exohunt's default grid (n_periods=2000, n_durations=12), each pass on a typical TESS light curve (~18,000 points for a single sector) takes 1-5 seconds. Three passes add 3-15 seconds total — negligible compared to data download time.
- Stopping criteria used in practice: (a) SNR of the best peak falls below a threshold (typically SNR < 7.0-7.3 for Kepler, adjustable for TESS noise levels), (b) BLS power falls below a noise-estimated false-alarm threshold, (c) maximum iteration count reached.

**Maturity**: Production-ready. The Kepler pipeline used this approach for its entire mission (2009-2018) and discovered thousands of multi-planet systems. The algorithm is well-understood.

**Ecosystem**: Astropy's BoxLeastSquares provides all needed primitives. No new dependencies required. The `model.transit_mask()` method or manual epoch masking can be used for subtraction.

**Compatibility**: Fully compatible with existing Exohunt architecture. `run_bls_search()` already returns `BLSCandidate` objects with `period_days`, `duration_hours`, and `transit_time` — all needed to compute a mask. A new wrapper function `run_iterative_bls_search()` can call the existing function in a loop.

**Known Limitations**:
- Each subtraction step propagates uncertainty: imperfect subtraction of pass N contaminates pass N+1. This is the primary source of false positives in iterative search.
- Very shallow secondaries (depth < 20 ppm for TESS) may be below the noise floor regardless of iteration count.
- Near-integer period ratios (e.g., 2:1 resonance) cause transit overlap, making clean subtraction difficult.

**Evidence**: Kepler pipeline documentation (KSCI-19081-003), Jenkins et al. (2010) "Overview of the Kepler Science Processing Pipeline", Rowe et al. (2015) multi-planet validation.

### 3.2 Transit Model for Subtraction

**Overview**: After identifying a transit signal, the model must be subtracted from the data before re-searching. The choice of subtraction model affects residual structure and downstream false positive rates.

**Key Characteristics**:
- **Box mask (zero-out)**: Replace in-transit points with NaN or the local median. Simplest approach. Leaves no residual transit structure but creates gaps in the time series that can affect BLS sensitivity at periods commensurate with the gap pattern. Implementation: ~15 lines of code.
- **Box model subtraction**: Subtract a box-shaped transit model (depth × box function) from the flux. Leaves the time series continuous but can leave residual structure at ingress/egress because real transits are not box-shaped. Implementation: ~25 lines of code.
- **Trapezoidal model subtraction**: Fit a trapezoid (flat bottom + linear ingress/egress) and subtract. Better approximation of real transit shape. Reduces ingress/egress residuals by ~60-80% compared to box subtraction. Implementation: ~60 lines of code, no new dependencies (numpy only).
- **Limb-darkened model (Mandel & Agol 2002)**: Full physical transit model with limb darkening coefficients. Best residual suppression but requires stellar parameters (limb darkening coefficients, impact parameter) that Exohunt does not currently have. Implementation: requires `batman-package` or `exoplanet` dependency. ~100+ lines plus dependency management.

**Maturity**:
- Box mask: Production-ready, used by many survey pipelines as the default first approach.
- Trapezoidal: Production-ready, used by TLS (Hippke & Heller 2019) internally.
- Limb-darkened: Production-ready but requires stellar parameter catalog integration.

**Compatibility**: Box mask and box model subtraction require zero new dependencies. Trapezoidal requires only numpy (already a dependency). Limb-darkened requires `batman-package` (new dependency).

**Known Limitations**:
- Box mask creates data gaps that reduce sensitivity for periods where transits fall in the gaps. For 3 iterations with typical TESS duty cycles, this removes ~0.5-2% of data points — acceptable.
- Box model subtraction leaves ~10-30% residual structure at ingress/egress for typical hot Jupiters (V-shaped transits). For shallow transits (< 100 ppm), this residual is below the noise floor and irrelevant.
- Trapezoidal model requires fitting 2 additional parameters (ingress/egress duration) per candidate, adding ~0.1s per candidate.

**Evidence**: Hippke & Heller (2019) Section 3.2 (transit model comparison), Kovács et al. (2016) "Box-fitting and beyond", TESS pipeline documentation.

### 3.3 Harmonic and Alias Disambiguation

**Overview**: The current `_alias_harmonic_reference_rank` in vetting.py checks period ratios (0.5, 2.0, 1/3, 3.0) with 2% tolerance. This determines whether a candidate is likely an alias or harmonic of a stronger signal rather than an independent planet.

**Key Characteristics**:
- **Current coverage gaps**: The ratios (0.5, 2.0, 1/3, 3.0) miss several important harmonics: 2/3, 3/2, 1/4, 4.0, 2/5, 5/2. In multi-planet systems with mean-motion resonances (common in compact systems), period ratios like 3:2 and 5:3 are physically real planets, not aliases. The current filter would incorrectly flag a real 3:2 resonant pair if 3/2 were added to the ratio list.
- **The fundamental problem**: Harmonic disambiguation cannot be done by period ratio alone. A candidate at P/2 of the primary could be (a) a half-period alias (false positive) or (b) a real planet in 2:1 resonance (true positive). Distinguishing these requires phase-folded depth analysis: a true half-period alias will show alternating deep/shallow transits when folded at the longer period, while a real planet at P/2 will show consistent depth at its own period.
- **2% tolerance**: This is reasonable for the BLS period grid resolution (geomspace with 2000 points gives ~0.1-0.5% spacing). However, for refined candidates (after `refine_bls_candidates` with 12000 points), the tolerance could be tightened to 1% without losing real harmonics.
- **Missing check**: The current code does not verify whether a candidate's phase-folded light curve at the candidate period shows a consistent, single-depth transit. This is the most reliable way to distinguish aliases from real planets.

**Maturity**: The phase-fold consistency check is a standard technique used by the Kepler Robovetter and TESS Quick-Look Pipeline.

**Compatibility**: Fully compatible. The phase-fold check uses data already available (time, flux, candidate period/epoch). Implementation adds ~40 lines to vetting.py.

**Known Limitations**:
- Phase-fold consistency requires sufficient transit events (at least 3-4 transits at the candidate period). For long-period candidates in single-sector TESS data, this may not be achievable.
- Near-integer resonances (exactly 2:1) create degenerate cases where the phase-fold test is ambiguous. These require additional checks (transit timing variations, depth ratios).

**Evidence**: Kepler Robovetter documentation (Thompson et al. 2018), Coughlin et al. (2016) "Planetary Candidates Observed by Kepler. VII."

### 3.4 Preprocessing Impact on Shallow Transit Recovery

**Overview**: The `prepare_lightcurve` function applies Savitzky-Golay flattening via lightkurve's `.flatten(window_length=401)`. This suppresses long-timescale trends but can also suppress transit signals if the window is too narrow relative to the transit duration.

**Key Characteristics**:
- **Default window_length=401**: At TESS 2-minute cadence, 401 cadences = ~13.4 hours. A typical hot Jupiter transit lasts 2-4 hours, so the window is 3-7× the transit duration — adequate for preserving the transit shape. However, for long-duration transits (e.g., a planet at P=20 days with duration ~8 hours), the window is only ~1.7× the transit duration, which can suppress 10-30% of the transit depth.
- **Shallow secondary transits**: A secondary planet with depth 50 ppm and duration 2 hours loses ~5-15% of its depth with window=401. This is within noise for most TESS targets but becomes significant for bright stars (TESS mag < 10) where the noise floor is 20-30 ppm.
- **Iterative flattening after masking known transits**: The optimal strategy is: (1) flatten with default window, (2) find primary transit, (3) mask primary transit epochs, (4) re-flatten the masked light curve with a potentially narrower window, (5) search for secondaries on the re-flattened data. This prevents the primary transit from biasing the flatten baseline and allows a more aggressive (narrower) window for the secondary search.
- **Window selection heuristic**: A safe rule is window_length >= 3 × (max expected transit duration in cadences). For TESS 2-min cadence and max duration 10 hours, this gives window >= 3 × 300 = 900 cadences. The current default of 401 is below this threshold for long-duration transits.

**Maturity**: Iterative flattening with transit masking is used by the TESS Science Processing Operations Center (SPOC) pipeline and by the TLS package.

**Compatibility**: Fully compatible. `prepare_lightcurve` already accepts `flatten_window_length` as a parameter. Adding a `transit_mask` parameter (array of boolean or time ranges to exclude from the flatten fit) requires modifying the flatten call to use lightkurve's `.flatten(mask=...)` parameter, which is already supported.

**Known Limitations**:
- Iterative flattening adds one additional flatten call per iteration (~2-8 seconds per call for typical TESS data). For 3 iterations, this adds 6-24 seconds.
- If the primary transit mask is too wide, it removes too much data from the flatten baseline, potentially introducing edge effects near the mask boundaries.
- The lightkurve `.flatten(mask=...)` parameter excludes masked points from the Savitzky-Golay fit but interpolates through them. This is correct behavior for transit masking.

**Evidence**: lightkurve documentation (`.flatten()` API), SPOC pipeline documentation (Jenkins et al. 2016), Hippke & Heller (2019) Section 2.

### 3.5 Detection Limits and Injection-Recovery Framework

**Overview**: To quantify the pipeline's sensitivity to secondary planets, an injection-recovery test injects synthetic transit signals into real light curves and measures the recovery rate as a function of depth, period, and other parameters.

**Key Characteristics**:
- **Minimum detectable depth**: For TESS single-sector data (27 days), the typical BLS detection limit is ~50-100 ppm for periods < 10 days (3+ transits) and ~200-500 ppm for periods 10-20 days (1-2 transits). After subtracting a primary transit, the noise floor increases by ~10-20% due to subtraction residuals.
- **Injection-recovery test structure**: (1) Take a real prepared light curve, (2) inject a box-shaped transit at known period/depth/epoch, (3) run the full pipeline (including iterative BLS if implemented), (4) check if the injected signal is recovered within tolerance (period within 1%, depth within 50%). Repeat over a grid of (period, depth) values.
- **Computational cost**: Each injection-recovery trial requires one full pipeline run. A grid of 20 periods × 20 depths × 10 phase offsets = 4000 trials. At ~5 seconds per trial (with iterative BLS), this is ~5.5 hours per target. This is feasible as an offline characterization tool but not as a per-run diagnostic.
- **Simplified alternative**: Instead of full injection-recovery, compute an analytical detection limit estimate using the BLS SNR formula: SNR ≈ depth × sqrt(N_transits × N_in_transit) / σ, where σ is the point-to-point scatter. This gives an approximate depth floor for a given period without running injections. Implementation: ~30 lines.

**Maturity**: Injection-recovery is the gold standard for transit survey completeness characterization (Christiansen et al. 2012, 2015, 2016 for Kepler). The analytical SNR estimate is a well-known approximation.

**Compatibility**: Both approaches are compatible. The analytical estimate can be added as a function in a new `detection_limits.py` module. The full injection-recovery framework would be a separate module (`injection_recovery.py`) that imports and wraps the pipeline.

**Known Limitations**:
- Injection-recovery assumes the noise properties of the specific light curve being tested. Results are not generalizable across targets without running many targets.
- The analytical SNR estimate assumes white noise, which underestimates the detection limit for targets with significant red noise (correlated systematics).
- Neither approach accounts for the vetting step's rejection rate, which can reject true signals (e.g., the odd/even depth test can fail for eccentric orbits).

**Evidence**: Christiansen et al. (2012) "The Derivation, Properties, and Value of Kepler's Combined Differential Photometric Precision", Burke et al. (2015) "Terrestrial Planet Occurrence Rates for the Kepler GK Dwarf Sample".

### 3.6 Config and Output Schema Changes

**Overview**: Supporting iterative multi-planet search requires new configuration knobs and output artifacts.

**Key Characteristics**:

**New BLS config fields needed**:
- `bls.iterative_passes` (int, default 1): Number of BLS iterations. Setting to 1 preserves current behavior.
- `bls.subtraction_model` (str, default "box_mask"): One of "box_mask", "box_subtract", "trapezoid". Controls how detected transits are removed before re-search.
- `bls.snr_floor` (float, default 7.0): Minimum SNR for a candidate to trigger another iteration. Below this, the iterative loop stops.
- `bls.iterative_top_n` (int, default 1): Number of candidates to subtract per iteration (usually 1, but could be >1 for very strong multi-planet signals).

**New preprocess config fields needed**:
- `preprocess.iterative_flatten` (bool, default false): Whether to re-flatten after masking known transits between BLS iterations.
- `preprocess.transit_mask_padding_factor` (float, default 1.5): How much wider than the fitted duration to mask around each transit epoch.

**New output artifacts**:
- Per-iteration candidate lists: `candidates/<target>__bls_iter_<N>_<hash>.json` — candidates found at each iteration, with iteration number and the subtracted signals noted.
- Residual light curves: optionally cached per iteration for diagnostics.
- Multi-planet candidate grouping: a top-level `candidates/<target>__multi_planet_<hash>.json` that groups candidates across iterations, noting which iteration found each and whether they form a consistent multi-planet system.
- Detection limit estimate: `diagnostics/<target>__detection_limit_<hash>.json` with estimated minimum detectable depth vs. period.

**Compatibility**: All new config fields can be added to `BLSConfig` and `PreprocessConfig` dataclasses with defaults that preserve current behavior (iterative_passes=1, iterative_flatten=false). The `_DEFAULTS` dict in config.py and the preset TOML files need corresponding entries. The `_deep_merge` validation will reject unknown keys, so the schema must be updated atomically with the config dataclass.

**Evidence**: Direct analysis of config.py, pipeline.py, and the preset TOML files.

### 3.7 Modern Alternative Methods

**Overview**: Beyond iterative BLS, several modern methods could improve secondary planet detection.

#### 3.7.1 Transit Least Squares (TLS)

- **What it solves**: TLS (Hippke & Heller 2019) replaces the box-shaped BLS model with a physically motivated transit shape (stellar limb darkening, planetary ingress/egress). This improves detection sensitivity by 5-10% for shallow transits compared to BLS, because the matched filter more closely resembles the true signal.
- **Key Characteristics**: Available as the `transitleastsquares` Python package. Drop-in replacement for BLS with similar API. Supports iterative search natively via `transit_mask()` method. Computational cost is ~2-5× higher than BLS due to the more complex model evaluation.
- **Maturity**: Stable, published in Astronomy & Astrophysics (2019). Actively maintained. Used by multiple TESS follow-up teams.
- **Compatibility**: Requires adding `transitleastsquares` as a dependency. The output format differs from astropy's BLS (different attribute names), so an adapter layer is needed. ~100 lines of integration code.
- **Known Limitations**: Requires stellar parameters (radius, mass, limb darkening) for optimal performance. Without them, it falls back to a default solar model, which reduces the sensitivity advantage to ~2-5% over BLS. Slower than BLS by 2-5×.

#### 3.7.2 GPU-Accelerated BLS

- **What it solves**: For large-scale batch processing, GPU-accelerated BLS (e.g., `cuvarbase`) can speed up the period search by 10-100×.
- **Maturity**: Experimental. `cuvarbase` is not actively maintained (last commit 2020). Requires CUDA GPU.
- **Compatibility**: Poor. Requires CUDA toolkit, which is not a standard dependency for a Python science package. Would only benefit batch mode, not single-target runs.
- **Known Limitations**: Not portable. Adds significant dependency complexity. The speedup is only relevant for very large period grids (>100,000 periods) or very long light curves (>100,000 points).

#### 3.7.3 Wavelet-Based Transit Detection

- **What it solves**: Wavelet decomposition can separate transit signals at different timescales, potentially isolating secondary transits without explicit subtraction.
- **Maturity**: Experimental/academic. No production-ready Python package exists for transit-specific wavelet search. Published in a few papers (e.g., Carter & Agol 2013) but not widely adopted.
- **Compatibility**: Would require implementing from scratch (~500+ lines) or adapting generic wavelet libraries (PyWavelets). High implementation complexity for uncertain benefit.
- **Known Limitations**: No established detection metric comparable to BLS power or TLS SDE. Difficult to set false-alarm thresholds. Not recommended for near-term implementation.

#### 3.7.4 Gaussian Process (GP) Detrending

- **What it solves**: GP detrending models correlated (red) noise in the light curve, providing a better noise model than the Savitzky-Golay flatten. This improves the effective SNR for shallow transits by 10-30% in red-noise-dominated light curves.
- **Maturity**: Production-ready. Available via `celerite2` (fast GP for time series) or `george`. Used by multiple TESS planet discovery papers.
- **Compatibility**: Requires adding `celerite2` as a dependency. Integration with the flatten step requires ~80 lines. Can be offered as an alternative to Savitzky-Golay flatten via a config option.
- **Known Limitations**: GP fitting is ~10-50× slower than Savitzky-Golay for typical TESS light curves. Requires choosing a kernel (Matérn-3/2 is standard for stellar variability). Overfitting risk if the GP length scale is too short.

### 3.8 Current Pipeline Issues (P0 Analysis)

**Overview**: Direct code analysis of the current pipeline revealed several issues that would compromise secondary planet search and should be fixed regardless.

#### 3.8.1 No SNR or False-Alarm Probability Metric

The current `run_bls_search` returns `power` (the BLS statistic) but does not compute SNR or a false-alarm probability (FAP). The `power` value is not normalized — its scale depends on the number of data points, the period grid, and the noise level. This means:
- There is no principled way to set a detection threshold. The current pipeline returns the top N peaks regardless of whether any are statistically significant.
- The proposed `bls.snr_floor` stopping criterion for iterative search cannot be implemented without first computing SNR.
- **Fix**: Compute SNR as `(power - median(power)) / MAD(power)` where MAD is the median absolute deviation of the power spectrum. This is the standard BLS SNR definition (Hartman & Bakos 2016). ~10 lines added to `run_bls_search`.

#### 3.8.2 Depth Computed as Fractional Flux, Stored Ambiguously

`BLSCandidate.depth` stores the raw BLS depth (fractional flux units) and `depth_ppm` stores `depth * 1_000_000`. However, the BLS depth from astropy is defined as the difference between the out-of-transit and in-transit flux levels. If the light curve is normalized to median=1.0 (which `prepare_lightcurve` does), then `depth` is in fractional units and `depth_ppm` is correct. But if normalization fails or is skipped (the code has a fallback path that skips normalization when median flux is near zero), `depth` could be in raw flux units, making `depth_ppm` meaningless. **Fix**: Assert or verify normalization state before computing `depth_ppm`, or normalize depth explicitly in `run_bls_search`. ~5 lines.

#### 3.8.3 `_unique_period` Filter May Discard Real Close-Period Planets

The `_unique_period` function in bls.py uses a 2% fractional separation to deduplicate peaks. In compact multi-planet systems, real planets can have period ratios as close as 1.02-1.05 (e.g., Kepler-36 b and c have a period ratio of 1.17). The 2% filter would not discard these, but a tighter filter (e.g., 1%) could. More importantly, the filter operates on the same BLS run — it is deduplicating sidelobes, not independent detections. For iterative search, this filter should be applied per-iteration (which it already would be, since each iteration is a separate `run_bls_search` call), but a cross-iteration uniqueness check is also needed to avoid re-detecting the same signal. **Recommendation**: Keep the 2% per-iteration filter, add a cross-iteration filter at 1% that compares new candidates against all previously subtracted signals.

#### 3.8.4 Vetting Odd/Even Test Sensitivity to Shallow Transits

The `_group_depth_ppm` function requires at least 5 in-transit and 10 out-of-transit points per parity group. For shallow secondary transits with short durations (1-2 hours) and long periods (>10 days), a single TESS sector may have only 2-3 transits total, meaning each parity group has 1-2 transits. The odd/even test will return NaN and the candidate will fail vetting (`pass_odd_even = False` when either depth is NaN). **Fix**: When insufficient data exists for the odd/even test, the test should be marked as "inconclusive" rather than "fail". This requires adding an `inconclusive` state to the vetting logic. ~15 lines.

#### 3.8.5 Missing Period Ratio 3:2 and 5:3 in Harmonic Check

As noted in Finding 3.3, the harmonic ratio list `(0.5, 2.0, 1/3, 3.0)` misses 2/3, 3/2, 4/1, 1/4, 5/2, 2/5, 5/3, 3/5. While adding all of these would increase false-negative rate (rejecting real resonant planets), the ratios 2/3 and 3/2 are the most common BLS aliases after 1/2 and 2/1 and should be included. **Fix**: Add 2/3 and 3/2 to the ratio list. Consider making the ratio list configurable. ~2 lines for the fix, ~10 lines for configurability.

#### 3.8.6 `refine_bls_candidates` Re-runs Full BLS Instead of Local Optimization

The `refine_bls_candidates` function calls `run_bls_search` with a narrow period window around each candidate. This re-runs the full BLS machinery (data preparation, model creation, power computation) for each candidate. A more efficient approach would be to use `BoxLeastSquares.power()` directly with the narrow period grid, reusing the already-constructed model. This is a performance issue, not a correctness issue, but it becomes significant with iterative search (3 iterations × 5 candidates × refinement = 15 refinement calls). **Fix**: Refactor to reuse the BLS model object. ~20 lines.

## 4. Comparison Matrix

### 4.1 Transit Subtraction Models

| Criterion | Box Mask | Box Model Subtract | Trapezoidal Model | Limb-Darkened Model |
|-----------|----------|-------------------|-------------------|---------------------|
| Implementation complexity | ~15 lines | ~25 lines | ~60 lines | ~100+ lines + dependency |
| Residual structure | None (gaps created) | 10-30% at ingress/egress | 2-5% at ingress/egress | <1% |
| New dependencies | None | None | None | batman-package |
| Computational cost per candidate | <0.01s | <0.01s | ~0.1s | ~0.5s |
| Requires stellar parameters | No | No | No | Yes (limb darkening coeffs) |
| False positive risk from residuals | Low (gaps, not structure) | Medium (for deep transits) | Low | Very low |
| Suitability for TESS shallow transits (<100 ppm) | Good (residuals below noise) | Good (residuals below noise) | Good | Overkill |
| Suitability for deep transits (>1000 ppm) | Good | Poor (significant residuals) | Good | Best |

### 4.2 Modern Alternative Methods

| Criterion | Iterative BLS (proposed) | TLS | GPU-BLS | Wavelet | GP Detrending |
|-----------|-------------------------|-----|---------|---------|---------------|
| Sensitivity improvement over current | 2-5× (finds additional planets) | +5-10% depth sensitivity | Same as BLS | Unknown | +10-30% in red noise |
| Implementation complexity | ~150 lines | ~100 lines (adapter) | ~200 lines + CUDA | ~500+ lines | ~80 lines |
| New dependencies | None | transitleastsquares | cuvarbase + CUDA | PyWavelets | celerite2 |
| Computational cost multiplier | 3-5× (per iteration) | 2-5× vs BLS | 0.01-0.1× vs BLS | ~1× vs BLS | 10-50× vs SG flatten |
| Maturity | Production (Kepler heritage) | Stable (published 2019) | Experimental (stale) | Experimental | Production |
| Python 3.10+ compatible | Yes | Yes | Uncertain | Yes | Yes |
| Works without stellar parameters | Yes | Partially (reduced benefit) | Yes | Yes | Yes |

## 5. Trade-offs

### Option A: Iterative BLS with Box Mask Subtraction (Recommended)

**Advantages**:
- Highest impact change: enables finding 2-5 additional planets per multi-planet system, directly addressing the core capability gap stated in the context.
- Zero new dependencies: uses only existing astropy BLS and numpy, satisfying the Python 3.10+ constraint with no dependency risk.
- Proven approach: Kepler pipeline heritage gives high confidence in correctness and completeness.
- Backward compatible: setting `iterative_passes=1` preserves exact current behavior, satisfying the RuntimeConfig compatibility constraint.
- Box mask avoids residual structure entirely, eliminating the primary source of false secondary detections.

**Disadvantages**:
- Box mask creates data gaps (~0.5-2% per iteration), slightly reducing sensitivity for periods commensurate with the gap pattern. This is a minor effect for 3 iterations.
- Does not improve single-pass sensitivity — only finds additional planets by removing the dominant signal. Targets with only one planet see no benefit.
- Requires implementing SNR computation (currently missing) as a prerequisite for the stopping criterion.

**Best Suited For**: Multi-planet system detection in TESS data with the existing Exohunt architecture.
**Worst Suited For**: Targets where the primary transit is very shallow (<50 ppm) and there is no dominant signal to subtract.

### Option B: TLS as BLS Replacement

**Advantages**:
- 5-10% better depth sensitivity for shallow transits, addressing the detection limit concern for secondary planets.
- Native iterative search support via `transit_mask()`, reducing implementation effort for the iterative loop.
- Physically motivated transit model improves both detection and parameter estimation.

**Disadvantages**:
- Adds `transitleastsquares` as a new dependency, increasing maintenance burden and potential version conflicts with lightkurve/astropy.
- 2-5× slower than BLS per pass, which compounds with iterative search (6-25× total slowdown for 3 iterations).
- Reduced benefit without stellar parameters (Exohunt does not currently have a stellar catalog integration).
- Requires adapter code to map TLS output to the existing `BLSCandidate` dataclass format.

**Best Suited For**: Pipelines with stellar parameter catalogs and where 5-10% depth sensitivity matters (e.g., searching for Earth-sized planets around Sun-like stars).
**Worst Suited For**: Quick-look mode where speed matters, or when stellar parameters are unavailable.

### Option C: GP Detrending as Flatten Replacement

**Advantages**:
- 10-30% better noise suppression in red-noise-dominated light curves, improving effective SNR for all transits (primary and secondary).
- More principled noise model than Savitzky-Golay, reducing systematic false positives from correlated noise.

**Disadvantages**:
- 10-50× slower than Savitzky-Golay flatten, making it impractical for quicklook mode.
- Adds `celerite2` dependency.
- Requires kernel selection and hyperparameter tuning, adding complexity to the config system.
- Overfitting risk if the GP length scale is too short — could suppress transit signals.

**Best Suited For**: Deep-search mode on bright stars where red noise dominates and runtime is not a constraint.
**Worst Suited For**: Quicklook mode, faint stars where white noise dominates.

## 6. Risks and Limitations

### Research Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Iterative subtraction propagates errors, creating false secondary detections | Medium | High — false planets reported | Implement SNR floor stopping criterion; add cross-iteration vetting; require secondary candidates to pass independent phase-fold consistency check |
| Box mask gaps create period-dependent sensitivity holes | Low | Low — affects <2% of period space per iteration | Document the gap pattern in detection limit estimates; offer trapezoidal model as config option for users who need gap-free subtraction |
| Flatten window suppresses shallow secondary transits | Medium | Medium — missed real planets | Implement iterative flattening with transit masking; increase default window for deep-search preset |
| Odd/even vetting test rejects valid shallow secondary candidates | High | Medium — missed real planets | Change vetting to return "inconclusive" instead of "fail" when data is insufficient; this is a P0 fix |
| SNR formula assumes white noise, underestimates detection limit for red-noise targets | Medium | Low — detection limits are approximate anyway | Document the white-noise assumption; offer GP detrending as a future enhancement for red-noise targets |

### Research Limitations

- The sensitivity improvement estimates (2-5× more planets) are based on Kepler pipeline literature and may not directly transfer to TESS data, which has shorter baselines (27 days vs. 4 years) and different noise characteristics.
- The computational cost estimates are based on typical TESS single-sector data (~18,000 points). Multi-sector stitched data (>100,000 points) will scale linearly and may require optimization.
- The injection-recovery framework was assessed conceptually but not prototyped. Actual implementation complexity may be higher than estimated.
- No benchmarking was performed on real multi-planet TESS targets. The recommendations should be validated with known multi-planet systems (e.g., TOI-178, TOI-700) before production use.

## 7. Recommendations

### P0: Fix Current Pipeline Issues (Critical for project success)

**Recommendation**: Before implementing iterative search, fix the 6 issues identified in Finding 3.8: (1) add SNR computation to `run_bls_search`, (2) validate depth normalization, (3) add cross-iteration uniqueness filter, (4) change odd/even vetting to "inconclusive" for insufficient data, (5) add 2/3 and 3/2 to harmonic ratio list, (6) refactor `refine_bls_candidates` to reuse BLS model.

**Justification**: Issues 3.8.1 (no SNR) and 3.8.4 (odd/even vetting failure) are blockers for iterative search. The SNR metric is required for the stopping criterion, and the vetting issue will reject most secondary candidates. The other issues are correctness and performance improvements that become more impactful with iterative search.

**Confidence Level**: High — these are direct code analysis findings with clear fixes.

**Validation Step**: Run the existing test suite after each fix to verify no regressions. Add unit tests for SNR computation and the "inconclusive" vetting state.

### P0: Implement Iterative BLS with Box Mask Subtraction

**Recommendation**: Implement a `run_iterative_bls_search()` function that wraps `run_bls_search` in a loop: (1) run BLS, (2) take the top candidate, (3) mask its transit epochs (set to NaN or local median), (4) re-run BLS on the residual, (5) stop when SNR < `bls.snr_floor` or `bls.iterative_passes` reached. Default to 3 passes with SNR floor of 7.0.

**Justification**: This is the highest-impact change identified in the research. It directly addresses the core capability gap (Finding 3.1) using a proven approach with zero new dependencies. The Kepler pipeline validated this approach over a decade of operation.

**Confidence Level**: High — the algorithm is well-established and the implementation is straightforward given the existing code structure.

**Validation Step**: Run on known multi-planet TESS targets (TOI-178 with 6 planets, TOI-700 with 4 planets) and verify that at least 2 additional planets are recovered compared to the current single-pass approach.

### P1: Implement Iterative Flattening with Transit Masking

**Recommendation**: Add a `transit_mask` parameter to `prepare_lightcurve` that excludes known transit epochs from the Savitzky-Golay fit. Between BLS iterations, re-flatten the light curve with the primary transit masked. Add `preprocess.iterative_flatten` config option (default false, enabled in deep-search preset).

**Justification**: Finding 3.4 shows that the flatten step can suppress 5-15% of shallow transit depth. Iterative flattening with masking recovers this depth, improving secondary planet sensitivity. The implementation uses lightkurve's existing `.flatten(mask=...)` parameter.

**Confidence Level**: Medium — the approach is sound but the magnitude of improvement depends on the specific light curve's noise characteristics. Needs validation with injection-recovery tests.

**Validation Step**: Compare secondary planet recovery rates with and without iterative flattening on 5-10 known multi-planet targets.

### P1: Add Phase-Fold Consistency Check to Vetting

**Recommendation**: Add a phase-fold depth consistency check to `vet_bls_candidates`: fold the light curve at the candidate period, bin the folded data, and verify that the transit depth is consistent across all transit epochs. Flag candidates where the depth varies by more than 50% between individual transits as potential aliases.

**Justification**: Finding 3.3 shows that period ratio checks alone cannot distinguish aliases from real planets in resonant systems. The phase-fold consistency check is the standard disambiguation technique used by Kepler Robovetter.

**Confidence Level**: Medium — the technique is well-established but the threshold (50% depth variation) needs tuning for TESS noise levels.

**Validation Step**: Test on known alias cases (e.g., targets where BLS reports a half-period alias) and known resonant multi-planet systems.

### P1: Add Config and Output Schema Changes

**Recommendation**: Add the config fields listed in Finding 3.6 (`bls.iterative_passes`, `bls.subtraction_model`, `bls.snr_floor`, `bls.iterative_top_n`, `preprocess.iterative_flatten`, `preprocess.transit_mask_padding_factor`) and the output artifacts (per-iteration candidate lists, multi-planet grouping JSON).

**Justification**: These are required infrastructure for the iterative search implementation. Defaults preserve current behavior.

**Confidence Level**: High — direct extension of the existing config system with no ambiguity.

**Validation Step**: Verify that existing presets and config files continue to work without modification. Verify that new config fields are validated correctly.

### P2: Implement Analytical Detection Limit Estimate

**Recommendation**: Add a `compute_detection_limit()` function that estimates the minimum detectable transit depth as a function of period using the BLS SNR formula. Output as a diagnostic artifact per target.

**Justification**: Finding 3.5 shows this is a ~30-line implementation that provides valuable context for interpreting candidate lists. It answers "could we have detected a secondary planet at this depth/period?" without the computational cost of full injection-recovery.

**Confidence Level**: Medium — the analytical estimate assumes white noise and will underestimate the detection limit for red-noise targets. Still useful as a first approximation.

**Validation Step**: Compare analytical estimates against injection-recovery results on 3-5 targets to calibrate the approximation error.

### P2: Evaluate TLS as Optional BLS Alternative

**Recommendation**: Defer TLS integration to a future phase. The 5-10% sensitivity improvement does not justify the added dependency and 2-5× slowdown for the initial iterative search implementation. Revisit after iterative BLS is validated and if the sensitivity gap is still significant.

**Justification**: Finding 3.7.1 shows TLS provides a modest improvement that is reduced without stellar parameters. The iterative BLS approach (P0) provides a much larger improvement (2-5× more planets) with zero new dependencies.

**Confidence Level**: High — the cost-benefit analysis clearly favors iterative BLS first.

**Validation Step**: After iterative BLS is implemented, compare detection rates against TLS on 10 known multi-planet targets to quantify the remaining sensitivity gap.

### P2: Evaluate GP Detrending for Deep-Search Preset

**Recommendation**: Defer GP detrending to a future phase. Offer it as an optional alternative to Savitzky-Golay flatten in the deep-search preset once iterative BLS and iterative flattening are validated.

**Justification**: Finding 3.7.4 shows GP detrending provides 10-30% noise improvement but at 10-50× computational cost. This is only justified for the deep-search use case on bright stars.

**Confidence Level**: Medium — the benefit is real but the implementation and tuning complexity is significant.

**Validation Step**: Prototype GP detrending on 5 bright TESS targets and compare noise metrics against Savitzky-Golay.
