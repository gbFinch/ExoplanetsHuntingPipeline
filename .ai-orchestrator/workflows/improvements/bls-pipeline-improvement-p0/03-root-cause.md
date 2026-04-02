---
agent: root-cause
sequence: 3
references: ["bug-analysis"]
summary: "Seven independent root causes confirmed by code inspection: (1) bls.py lacks SNR computation entirely, (2) vetting.py defaults pass_odd_even to False with no NaN-handling branch, (3) preprocess.py has no adaptive window logic and no normalization flag propagation, (4) pipeline.py per-sector branch omits refine_bls_candidates() call, (5) three preset TOML files have incorrect boolean values, (6) plotting.py renders raw and prepared as separate identical-style panels. Each is an independent implementation gap."
---

## Root Cause Statement
The 7 P0 defects share a common pattern — independent implementation gaps — but have no shared root cause. Each defect is a specific missing feature, incorrect default, or incomplete code path in a specific file. The root causes are: (1) `bls.py:run_bls_search()` never computes SNR from the BLS power spectrum; (2) `vetting.py:vet_bls_candidates()` initializes `pass_odd_even = False` and only sets it `True` inside an `if np.isfinite(...)` guard, with no `else` branch for inconclusive; (3) `preprocess.py:prepare_lightcurve()` has no adaptive window sizing and returns no normalization state flag; (4) `pipeline.py` per-sector BLS loop omits the `refine_bls_candidates()` call present in the stitched branch; (5) preset TOML files contain incorrect `enabled` flags; (6) `plotting.py:save_raw_vs_prepared_plot()` uses separate identical-style panels instead of overlay/residual design.

## Causal Chain

### B1 — No SNR Computation
```
[bls.py: no SNR computation in run_bls_search()] → [BLSCandidate has no snr field] → [No threshold filtering possible] → [Pure noise returns 5 "candidates"]
```

- **Link 1**: `run_bls_search()` computes `power` from `BoxLeastSquares.power()` but never computes `SNR = (peak_power - median_power) / (1.4826 × MAD_power)`.
  - Location: `bls.py`, `run_bls_search()`, lines 55-115
  - Mechanism: The function picks top-N peaks by raw power without normalizing against the noise floor.
  - Evidence: Code inspection — no `median`, `MAD`, or `snr` variable exists in the function.

- **Link 2**: `BLSCandidate` dataclass has fields `rank, period_days, duration_hours, depth, depth_ppm, power, transit_time, transit_count_estimate` — no `snr` field.
  - Location: `bls.py`, lines 10-19
  - Mechanism: Without the field, no downstream code can access SNR.
  - Evidence: Dataclass definition inspection.

- **Link 3**: No `min_snr` threshold exists in `BLSConfig` or `run_bls_search()` parameters.
  - Location: `config.py`, `BLSConfig` dataclass; `bls.py`, function signature
  - Mechanism: Without a threshold parameter, filtering cannot be configured.
  - Evidence: Code inspection of both files.

### V1 — Odd/Even Fails Instead of Inconclusive
```
[_group_depth_ppm() returns NaN for insufficient data] → [vet_bls_candidates() if-guard skips NaN case] → [pass_odd_even remains False] → [Valid candidate rejected]
```

- **Link 1**: `_group_depth_ppm()` returns `(float("nan"), 0)` when `in_transit < 5` or `out_transit < 10`.
  - Location: `vetting.py`, lines 24-38
  - Mechanism: Early return with NaN when insufficient points.
  - Evidence: Code: `if int(np.count_nonzero(in_transit)) < 5 or int(np.count_nonzero(out_transit)) < 10: return float("nan"), 0`

- **Link 2**: `vet_bls_candidates()` initializes `pass_odd_even = False`, then only sets it `True` inside `if np.isfinite(odd_depth_ppm) and np.isfinite(even_depth_ppm):`.
  - Location: `vetting.py`, lines ~80-85
  - Mechanism: When either depth is NaN, the `if` block is skipped, `pass_odd_even` stays `False`.
  - Evidence: Code: `pass_odd_even = False` followed by `if np.isfinite(...): ... pass_odd_even = mismatch_fraction <= ...`

- **Link 3**: `CandidateVettingResult` has no `odd_even_status` field to distinguish "fail" from "inconclusive".
  - Location: `vetting.py`, lines 10-21
  - Mechanism: Binary pass/fail with no third state.
  - Evidence: Dataclass inspection — only `pass_odd_even_depth: bool`.

### P1 — Window Suppresses Transit Depth
```
[science-default.toml: flatten_window_length=401] → [prepare_lightcurve() uses 401 directly] → [Window is 2.2× 6h transit] → [10-30% depth suppression]
```

- **Link 1**: `science-default.toml` sets `flatten_window_length = 401`.
  - Location: `presets/science-default.toml`
  - Evidence: File inspection.

- **Link 2**: `prepare_lightcurve()` passes `flatten_window_length` to `_resolve_window_length()` which only clamps to `n_points - 1` and ensures odd — no adaptive sizing based on transit duration.
  - Location: `preprocess.py`, `_resolve_window_length()` and `prepare_lightcurve()`
  - Mechanism: No comparison against expected transit duration.
  - Evidence: Code inspection — no duration parameter or adaptive logic exists.

### P2 — Normalization Fallback Corrupts Depth Semantics
```
[median_flux near zero] → [normalization skipped with warning] → [No flag propagated] → [depth_ppm = depth * 1e6 assumes normalized flux] → [Meaningless depth values]
```

- **Link 1**: `prepare_lightcurve()` checks `abs(median_flux) < 1e-12` and skips normalization.
  - Location: `preprocess.py`, lines ~148-152
  - Evidence: Code: `if not np.isfinite(median_flux) or abs(median_flux) < 1e-12: LOGGER.warning(...)`

- **Link 2**: Function returns `lk.LightCurve` with no metadata about normalization state.
  - Location: `preprocess.py`, return statement
  - Mechanism: `LightCurve` object carries no `normalized` flag.
  - Evidence: Function signature returns `lk.LightCurve` only.

- **Link 3**: `run_bls_search()` computes `depth_ppm = d * 1_000_000.0` unconditionally.
  - Location: `bls.py`, line within candidate construction
  - Mechanism: Assumes flux is normalized to ~1.0; if not, `d` is in raw flux units and `d * 1e6` is meaningless.
  - Evidence: Code: `depth_ppm=d * 1_000_000.0`

### O2 — Per-Sector BLS Skips Refinement
```
[pipeline.py per-sector branch] → [run_bls_search() called] → [refine_bls_candidates() NOT called] → [Lower period precision]
```

- **Link 1**: Per-sector branch (lines ~1100-1210) calls `run_bls_search()` but not `refine_bls_candidates()`.
  - Location: `pipeline.py`, per-sector BLS loop
  - Evidence: grep confirms `refine_bls_candidates` only appears at line 1239 (stitched branch).

- **Link 2**: Stitched branch (line ~1239) calls `refine_bls_candidates()` after `run_bls_search()`.
  - Location: `pipeline.py`, line 1239
  - Evidence: Code inspection.

### O3 — Preset Configuration Defects
```
[Incorrect TOML values] → [RuntimeConfig resolves with wrong flags] → [Features disabled/enabled incorrectly]
```

- **Link 1**: `science-default.toml`: `plot.enabled = false`, `flatten_window_length = 401`
- **Link 2**: `quicklook.toml`: `bls.enabled = false`
- **Link 3**: `deep-search.toml`: `plot.enabled = false`
- Evidence: Direct file inspection of all three preset files.

### PL1 — Raw vs. Prepared Panels Identical
```
[save_raw_vs_prepared_plot() renders 3 separate panels] → [Panels 1 and 2 use same scatter style] → [No overlay or residual] → [Detrending effect invisible]
```

- **Link 1**: Function creates `fig, (ax_raw_old, ax_prepared_old, ax_prepared_new) = plt.subplots(3, 1, ...)`.
  - Location: `plotting.py`, `save_raw_vs_prepared_plot()`
  - Evidence: Code inspection.

- **Link 2**: Panel 1 uses `ax_raw_old.plot(raw_time, raw_flux, ".", ...)` and Panel 2 uses `ax_prepared_old.plot(prep_time, prep_flux, ".", ...)` — identical style.
  - Location: `plotting.py`, lines within `save_raw_vs_prepared_plot()`
  - Evidence: Code inspection — both use `.plot()` with `markersize=0.5, alpha=0.7`.

## Evidence

### Direct Evidence
- **B1**: `bls.py` contains no variable named `snr`, `signal_to_noise`, `median_power`, or `mad_power`. `BLSCandidate` fields confirmed by dataclass definition.
- **V1**: `pass_odd_even = False` initialization and `if np.isfinite(...)` guard confirmed by code lines ~80-85.
- **O2**: `refine_bls_candidates` grep shows only one call site at line 1239 (stitched branch).
- **O3**: All three TOML files inspected; values match bug report exactly.

### Corroborating Evidence
- The quality audit scored the pipeline 4.7/10, consistent with 7 critical defects.
- The per-sector branch structure mirrors the stitched branch except for the missing refinement call, consistent with copy-paste omission.

### Absence of Counter-Evidence
- No code path exists that computes SNR anywhere in the codebase (searched for `snr`, `signal_to_noise`, `mad`).
- No `normalized` flag or metadata exists on any `LightCurve` return path.
- No adaptive window logic exists anywhere in `preprocess.py`.

## Eliminated Hypotheses

### Hypothesis 2: Incomplete Feature Development
- **Status**: Partially eliminated
- **Reasoning**: While the pattern of missing features is consistent with incremental development, this hypothesis does not explain O3 (preset config errors are not "deferred features") or PL1 (the plot was implemented, just poorly). The hypothesis adds no actionable information beyond H1.
- **Key Differentiator**: H1 treats each defect independently; H2 implies a shared development timeline cause. For fix planning, the distinction is irrelevant — each defect requires its own fix.

### Hypothesis 3: Interaction Between Normalization and Depth
- **Status**: Eliminated
- **Reasoning**: While P2 does affect depth values, B1 (no SNR) is a defect regardless of normalization state. V1 (NaN handling) is a conditional logic error unrelated to depth magnitude. O2, O3, P1, PL1 are entirely unrelated to normalization. Fixing P2 alone resolves only P2.
- **Key Differentiator**: H3 predicts fixing P2 would cascade improvements; code inspection shows B1 and V1 have independent root causes.

## Affected Code Locations

| File | Function/Area | Nature of Fault | Relationship |
|------|--------------|-----------------|--------------|
| `src/exohunt/bls.py` | `BLSCandidate` dataclass | Missing `snr` field | Fault origin (B1) |
| `src/exohunt/bls.py` | `run_bls_search()` | No SNR computation; no threshold filtering | Fault origin (B1) |
| `src/exohunt/config.py` | `BLSConfig` dataclass | Missing `min_snr` field | Fault origin (B1) |
| `src/exohunt/vetting.py` | `CandidateVettingResult` | Missing `odd_even_status` field | Fault origin (V1) |
| `src/exohunt/vetting.py` | `vet_bls_candidates()` | No NaN→inconclusive branch | Fault origin (V1) |
| `src/exohunt/preprocess.py` | `prepare_lightcurve()` | No adaptive window; no normalized flag | Fault origin (P1, P2) |
| `src/exohunt/bls.py` | `run_bls_search()` | `depth_ppm` assumes normalized flux | Fault propagation (P2) |
| `src/exohunt/pipeline.py` | Per-sector BLS loop | Missing `refine_bls_candidates()` call | Fault origin (O2) |
| `presets/science-default.toml` | `plot.enabled`, `flatten_window_length` | Wrong values | Fault origin (O3) |
| `presets/quicklook.toml` | `bls.enabled` | Wrong value | Fault origin (O3) |
| `presets/deep-search.toml` | `plot.enabled` | Wrong value | Fault origin (O3) |
| `src/exohunt/plotting.py` | `save_raw_vs_prepared_plot()` | Separate identical panels | Fault origin (PL1) |

## Blast Radius

### Same Fault, Other Symptoms
- **B1**: `compute_bls_periodogram()` also returns raw power without SNR — diagnostic plots show unnormalized power.
- **P2**: Any code path that reads `depth_ppm` from candidates (parameter estimation, JSON output, CSV output) produces incorrect values when normalization was skipped.
- **V1**: The `vetting_reasons` string propagates to candidate JSON/CSV output, so downstream consumers see `odd_even_depth_mismatch` for candidates that should show `inconclusive`.

### Related Faults
- The `refine_bls_candidates()` function itself does not compute SNR either — after B1 is fixed, refinement should also propagate SNR values.
- The interactive plot function `save_raw_vs_prepared_plot_interactive()` has the same panel layout issue as PL1.

### Data Impact
- No data corruption — the pipeline writes output files but does not modify input data. However, any published candidate lists generated before the fix may contain incorrect depth_ppm values and false rejections.

## Confidence Assessment
- **Confidence Level**: High — all 7 root causes are confirmed by direct code inspection with no ambiguity.
- **Strongest Evidence**: The `BLSCandidate` dataclass definition explicitly lacks an `snr` field, and no SNR-related variable exists anywhere in `bls.py`.
- **Biggest Uncertainty**: The magnitude of P1's depth suppression (10-30%) is estimated, not measured.
- **What Would Change the Determination**: Nothing — all root causes are confirmed by code inspection. The only uncertainty is in impact magnitude, not in cause identification.
- **Recommended Validation**: Run the existing test suite to confirm all tests pass before any changes, establishing the baseline.
