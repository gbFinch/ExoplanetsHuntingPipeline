---
agent: bug-analysis
sequence: 2
references: ["bug-report"]
summary: "Seven independent logic/configuration defects across 6 files in the BLS pipeline. The leading hypothesis is that each defect is an independent implementation gap (not a shared root cause). Investigation should start with preset config inspection (O3), then trace code paths for SNR (B1), vetting (V1), normalization (P2), refinement (O2), window sizing (P1), and plot layout (PL1)."
---

## Bug Classification
- **Bug Type**: Logic error (B1, V1, P2, O2), Configuration error (O3, P1), UI/UX defect (PL1)
- **Failure Mode**: Silent failure (all 7 — no exceptions thrown; incorrect results produced silently)
- **Determinism**: Deterministic — all 7 defects reproduce on every applicable run
- **Scope**: Cross-component — defects span 6 source files and 3 preset files across detection, vetting, preprocessing, orchestration, and visualization subsystems

Justification: The bug report documents 7 distinct defects that produce incorrect results without raising exceptions. Each defect is deterministic and affects every pipeline run that exercises the relevant code path.

## Affected Subsystems

### 1. BLS Search Module (`src/exohunt/bls.py`)
- **Role in Bug**: B1 — `run_bls_search()` returns raw BLS power with no SNR computation. `BLSCandidate` dataclass lacks `snr` field. No threshold filtering exists.
- **Confidence**: High — the bug report identifies exact function and line range (lines 55-115), and code inspection confirms no SNR computation exists.
- **Code Area**: `run_bls_search()` function, `BLSCandidate` dataclass

### 2. Vetting Module (`src/exohunt/vetting.py`)
- **Role in Bug**: V1 — `_group_depth_ppm()` returns NaN when insufficient in-transit points exist. `vet_bls_candidates()` treats NaN as failure (`pass_odd_even = False`) instead of inconclusive.
- **Confidence**: High — code inspection confirms: when `np.isfinite(odd_depth_ppm) and np.isfinite(even_depth_ppm)` is False, `pass_odd_even` remains `False` (its initial value).
- **Code Area**: `_group_depth_ppm()` lines 24-38, `vet_bls_candidates()` lines 75-85, `CandidateVettingResult` dataclass

### 3. Preprocessing Module (`src/exohunt/preprocess.py`)
- **Role in Bug**: P1 — `prepare_lightcurve()` uses `flatten_window_length` directly without adaptive sizing. P2 — normalization skip (when `median_flux` near zero) logs a warning but propagates no flag downstream.
- **Confidence**: High — code inspection confirms both: no adaptive window logic exists, and no `normalized` flag is returned or propagated.
- **Code Area**: `prepare_lightcurve()` lines 140-175

### 4. Pipeline Orchestration (`src/exohunt/pipeline.py`)
- **Role in Bug**: O2 — per-sector BLS code path (lines ~1100-1210) calls `run_bls_search()` and `vet_bls_candidates()` but never calls `refine_bls_candidates()`. The stitched code path (line ~1239) does call it.
- **Confidence**: High — code inspection confirms `refine_bls_candidates` appears only in the stitched branch.
- **Code Area**: Per-sector BLS loop (lines ~1100-1210)

### 5. Preset Configuration Files (`src/exohunt/presets/*.toml`)
- **Role in Bug**: O3 — `science-default.toml` has `plot.enabled = false` and `flatten_window_length = 401`; `quicklook.toml` has `bls.enabled = false`; `deep-search.toml` has `plot.enabled = false`.
- **Confidence**: High — direct file inspection confirms all three preset values.
- **Code Area**: `presets/science-default.toml`, `presets/quicklook.toml`, `presets/deep-search.toml`

### 6. Plotting Module (`src/exohunt/plotting.py`)
- **Role in Bug**: PL1 — `save_raw_vs_prepared_plot()` renders raw and prepared as separate panels with identical scatter-plot style at full-timeseries scale, making them visually indistinguishable.
- **Confidence**: High — code inspection confirms panels 1 and 2 use the same `.plot()` scatter style with no overlay, residual, or zoom.
- **Code Area**: `save_raw_vs_prepared_plot()` lines 120-175

## Evidence Analysis

### Error Messages
No error messages are produced — all 7 defects are silent logic/configuration errors. The only log output is P2's warning: `"preprocessing: skipping normalization (median flux is near zero)."` This warning is informational but does not prevent downstream code from assuming normalized flux.

### Log Analysis
- **Entry**: `LOGGER.warning("preprocessing: skipping normalization (median flux is near zero).")`
- **Significance**: Indicates the normalization skip path is exercised, but no flag is set for downstream consumers.
- **Anomaly**: The warning exists but has no programmatic effect — downstream code unconditionally computes `depth_ppm = depth * 1_000_000`.

### Stack Trace Analysis
No stack traces — no exceptions are thrown by any of the 7 defects.

### Pattern Analysis
- **Structural pattern**: Defects B1, V1, O2 share a pattern of missing functionality — code that should exist but was never implemented (SNR computation, inconclusive handling, refinement call).
- **Configuration pattern**: O3 defects share a pattern of incorrect boolean flags in preset TOML files.
- **Interaction pattern**: P2 (normalization) affects the semantics of depth values consumed by B1 (BLS search) and V1 (vetting), creating a potential compound effect.

## Hypotheses

### Hypothesis 1: Seven Independent Implementation Gaps
- **Statement**: Each of the 7 defects is an independent implementation gap or configuration error introduced during initial development, not caused by a shared underlying fault.
- **Likelihood**: High
- **Supporting Evidence**: The defects span 6 different files and 3 preset files. Each has a distinct mechanism (missing computation, incorrect conditional logic, wrong config value, missing function call, inadequate visualization). No shared code path or data structure connects all 7.
- **Contradicting Evidence**: None identified.
- **Explains Symptoms**: All 7 symptoms.
- **Predicted Behavior**: Each defect can be fixed independently without affecting the others. Fixing one does not fix or worsen any other.

### Hypothesis 2: Incomplete Feature Development
- **Statement**: The pipeline was developed incrementally, and certain features (SNR, adaptive window, normalization propagation) were planned but not implemented before the pipeline was put into use.
- **Likelihood**: Medium
- **Supporting Evidence**: The code structure suggests incremental development — e.g., `BLSCandidate` has `power` but no `snr`, suggesting SNR was deferred. The stitched path has refinement but per-sector does not, suggesting per-sector was added later.
- **Contradicting Evidence**: The preset configuration errors (O3) are unlikely to be "planned for later" — they appear to be simple mistakes.
- **Explains Symptoms**: B1, V1, P1, P2, O2 (5 of 7). Does not explain O3 or PL1.
- **Predicted Behavior**: Same as Hypothesis 1 for fix approach — each gap is filled independently.

### Hypothesis 3: Interaction Between Normalization and Depth Computation
- **Statement**: P2 (normalization fallback) is the root cause of incorrect depth values, and B1/V1 are downstream consequences — if normalization were always correct, the lack of SNR and the odd/even test behavior would be less impactful.
- **Likelihood**: Low
- **Supporting Evidence**: P2 does affect depth_ppm values consumed by vetting. If flux is not normalized, `depth * 1_000_000` produces meaningless values.
- **Contradicting Evidence**: B1 (no SNR) is a defect regardless of normalization — even with perfectly normalized flux, there is no SNR computation. V1 (NaN handling) is a defect regardless of depth values — the issue is the NaN conditional, not the depth magnitude. O2, O3, P1, PL1 are unrelated to normalization.
- **Explains Symptoms**: Partially — P2 only, with indirect effect on B1/V1 depth values.
- **Predicted Behavior**: Fixing P2 alone would not resolve B1, V1, or any other defect.

## Investigation Strategy

### Step 1: Verify Preset Configuration Values (O3)
- **Action**: Read `presets/science-default.toml`, `presets/quicklook.toml`, `presets/deep-search.toml` and confirm the exact boolean values for `plot.enabled`, `bls.enabled`, and `flatten_window_length`.
- **Target Hypothesis**: H1 (independent gaps)
- **Expected Result if H1 Correct**: Each preset has the exact incorrect values documented in the bug report.
- **Expected Result if H1 Incorrect**: Values differ from bug report (unlikely).
- **Tools/Access Required**: File system read access.
- **Invasiveness**: Non-invasive.

### Step 2: Trace SNR Absence in BLS Module (B1)
- **Action**: Search `bls.py` for any SNR-related computation, field, or variable. Inspect `BLSCandidate` dataclass fields. Inspect `run_bls_search()` return logic.
- **Target Hypothesis**: H1
- **Expected Result if H1 Correct**: No SNR computation exists anywhere in `bls.py`. `BLSCandidate` has no `snr` field.
- **Expected Result if H1 Incorrect**: SNR exists but is not surfaced (unlikely based on code review).
- **Tools/Access Required**: Code inspection.
- **Invasiveness**: Non-invasive.

### Step 3: Trace Odd/Even NaN Handling in Vetting (V1)
- **Action**: Read `vet_bls_candidates()` and trace the code path when `_group_depth_ppm()` returns NaN. Confirm that `pass_odd_even` defaults to `False` and is never set to `True` when depths are NaN.
- **Target Hypothesis**: H1
- **Expected Result if H1 Correct**: `pass_odd_even = False` is the initial value, and the `if np.isfinite(...)` block is the only place it can become `True`.
- **Tools/Access Required**: Code inspection.
- **Invasiveness**: Non-invasive.

### Step 4: Trace Normalization Flag Propagation (P2)
- **Action**: Follow the return value of `prepare_lightcurve()` through `pipeline.py` to `run_bls_search()`. Confirm no `normalized` flag is returned or checked.
- **Target Hypothesis**: H1, H3
- **Expected Result if H1 Correct**: `prepare_lightcurve()` returns only a `LightCurve` object with no metadata about normalization state.
- **Expected Result if H3 Correct**: Same observation, but fixing this would cascade improvements to depth values.
- **Tools/Access Required**: Code inspection.
- **Invasiveness**: Non-invasive.

### Step 5: Trace Per-Sector Refinement Path (O2)
- **Action**: Search `pipeline.py` for all calls to `refine_bls_candidates()`. Confirm it is called only in the stitched branch.
- **Target Hypothesis**: H1
- **Expected Result if H1 Correct**: `refine_bls_candidates()` appears only in the `else` branch (stitched mode), not in the `if bls_mode == "per-sector"` branch.
- **Tools/Access Required**: Code inspection.
- **Invasiveness**: Non-invasive.

### Step 6: Inspect Plot Layout (PL1)
- **Action**: Read `save_raw_vs_prepared_plot()` and confirm panels 1 and 2 use identical rendering approaches with no overlay or residual.
- **Target Hypothesis**: H1
- **Expected Result if H1 Correct**: Both panels use `.plot()` with similar marker styles; no overlay, residual, or zoom panel exists.
- **Tools/Access Required**: Code inspection.
- **Invasiveness**: Non-invasive.

## Information Gaps

### Gap 1: Frequency of Near-Zero Median Flux
- **Gap**: How often does `median_flux` fall near zero in real TESS data?
- **Impact**: Determines how frequently P2 is triggered in practice.
- **How to Fill**: Run pipeline on a sample of 50+ targets and count normalization skip warnings.
- **Default Assumption**: Rare but possible — fix should handle it correctly regardless of frequency.

### Gap 2: Actual Depth Suppression Magnitude for P1
- **Gap**: The bug report states "10-30% depth suppression" but does not provide measured values.
- **Impact**: Affects severity assessment of P1.
- **How to Fill**: Run pipeline with window=401 and window=801 on a known transit target and compare measured depths.
- **Default Assumption**: Accept the 10-30% range from the audit; the fix (increase to 801 + adaptive mode) addresses it regardless.

## Risk Assessment

### Risks of the Bug Persisting
- **User Impact**: Every pipeline run produces unreliable results — candidates without SNR, valid candidates rejected, depth values potentially meaningless, no plots from default preset. Users cannot trust pipeline output for scientific analysis.
- **Data Risk**: No data corruption — the pipeline writes output files but does not modify input data. However, published results based on pipeline output could be scientifically incorrect.
- **Security Risk**: None — this is a scientific analysis tool with no authentication, network access, or user data handling.
- **Escalation Risk**: Low — defects are stable and deterministic. They will not worsen over time, but they block all downstream P1 improvements.

### Risks of Investigation
- **False Positive Risk**: Low — all 7 defects are confirmed by direct code inspection. The risk of misdiagnosis is minimal.
- **Scope Creep Risk**: Medium — the quality audit identified 28 total issues (21 beyond P0). Investigation may reveal additional interactions between P0 and P1 issues.
- **Regression Risk**: Low — investigation is read-only code inspection. No code changes during investigation.
