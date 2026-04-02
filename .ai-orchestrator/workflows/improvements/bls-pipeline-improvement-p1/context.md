# Project: BLS Pipeline P1 Improvements (R7–R13)

## Type
feature

## Description
Implement the seven P1 recommendations (R7–R13) from the BLS pipeline quality audit in `.ai-orchestrator/workflows/research/bls-pipeline-issues/01-research.md`. These address false-alarm probability, vetting completeness, configurability, diagnostic quality, and transit-depth preservation.

**R7 — Bootstrap FAP estimation** (Issue B2)
Add optional false-alarm probability via bootstrap (N=1000 flux shuffles). Add `fap` field to `BLSCandidate`. Controlled by `BLSConfig.compute_fap` (default `false`).

**R8 — Add missing alias ratios** (Issue V2)
Add `2/3` and `3/2` to the `ratios` tuple in `_alias_harmonic_reference_rank()`.

**R9 — Secondary eclipse check** (Issue V4)
Add `_secondary_eclipse_check()` to `vetting.py`. Measure depth at phase 0.5 ± duration/2 and flag if secondary depth > configurable fraction (default 30%) of primary depth.

**R10 — Phase-fold depth consistency check** (Issue V3)
Add `_phase_fold_depth_consistency()` to `vetting.py`. Phase-fold at candidate period, measure in-transit depth in first-half vs second-half of observations, flag if depth varies by more than a configurable threshold (default 50%).

**R11 — VettingConfig and ParameterConfig in config schema** (Issues V5, C1, C2)
Add `[vetting]` and `[parameters]` sections to `config.py` schema, `_DEFAULTS`, all three presets, and `resolve_runtime_config()`. Move the six hardcoded constants from `pipeline.py` lines 110–115 into these config sections. Wire them through `pipeline.py` call sites.

**R12 — BLS diagnostic annotations** (Issue PL2)
Enhance `save_candidate_diagnostics()` in `plotting.py` with: SNR annotation on periodogram peak, transit box-model overlay on phase-fold, odd/even transit comparison subplot, candidate parameter text annotations (period, depth, duration, SNR, vetting status).

**R13 — Iterative transit masking** (Issue P3)
Add optional iterative mask-flatten-search cycle in `pipeline.py`: (1) flatten without masking, (2) run BLS, (3) mask in-transit points, (4) re-flatten, (5) re-run BLS. Controlled by a new config flag (default off).

## Background
The P0 fixes (R1–R6) have already been applied:
- R1 (SNR computation): `BLSCandidate.snr` field exists; SNR = (peak − median) / (1.4826 × MAD) computed in `run_bls_search()`; `min_snr` in `BLSConfig`.
- R2 (Odd/even inconclusive): `odd_even_status` field on `CandidateVettingResult`; NaN depths → `pass_odd_even=True`, status `"inconclusive"`.
- R3 (Preset fixes): All three presets now have `plot.enabled = true`, `bls.enabled = true`, `flatten_window_length = 801`.
- R4 (Normalization safety): `normalized` param on `run_bls_search()`; depth_ppm uses `depth / median_flux * 1e6` when not normalized.
- R5 (Raw-vs-prepared plot redesign): 3-panel overlay + residual + percentile band layout implemented.
- R6 (Per-sector refinement): `refine_bls_candidates()` called in per-sector code path.

The pipeline overall score is 4.7/10. P0 fixes raised it to ~7/10. These P1 fixes target ~9/10.

## Constraints
- Python ≥ 3.10. No new heavy dependencies beyond lightkurve/astropy/numpy/matplotlib.
- Each fix must be independently deployable — no fix should depend on another being present.
- Must remain compatible with existing `RuntimeConfig`/preset/TOML layered config system.
- New config sections must use `_DEFAULTS` mechanism so existing user config files continue to work without changes.
- Bootstrap FAP (R7) adds ~30s per candidate at N=1000 — must be opt-in via config flag.
- Iterative masking (R13) roughly doubles BLS runtime — must be opt-in via config flag.

## Existing Code/System
Repository: `/Users/gbasin/Development/exoplanets-hunting-pipeline`

Key files and locations for each fix:

| Fix | Primary files | Key functions/classes | Lines of interest |
|-----|--------------|----------------------|-------------------|
| R7 | `src/exohunt/bls.py`, `src/exohunt/config.py` | `run_bls_search()`, `BLSCandidate`, `BLSConfig` | bls.py:46–147 (search), bls.py:11–20 (dataclass) |
| R8 | `src/exohunt/vetting.py` | `_alias_harmonic_reference_rank()` | vetting.py:48–68, line 58: `ratios = (0.5, 2.0, 1.0 / 3.0, 3.0)` |
| R9 | `src/exohunt/vetting.py` | `vet_bls_candidates()` — new `_secondary_eclipse_check()` | vetting.py:71–155 |
| R10 | `src/exohunt/vetting.py` | `vet_bls_candidates()` — new `_phase_fold_depth_consistency()` | vetting.py:71–155 |
| R11 | `src/exohunt/config.py`, `src/exohunt/pipeline.py`, `src/exohunt/presets/*.toml` | `RuntimeConfig`, `resolve_runtime_config()`, `_DEFAULTS` | config.py:56–77 (dataclasses), config.py:80–120 (defaults), config.py:356–492 (resolver), pipeline.py:110–115 (hardcoded constants) |
| R12 | `src/exohunt/plotting.py` | `save_candidate_diagnostics()` | plotting.py:391–481 |
| R13 | `src/exohunt/pipeline.py` | `fetch_and_plot()` — BLS section | pipeline.py:1110–1300 (BLS execution block) |

Hardcoded constants to move into config (R11):
```python
# pipeline.py lines 110-115
_VETTING_MIN_TRANSIT_COUNT = 2
_VETTING_ODD_EVEN_MAX_MISMATCH_FRACTION = 0.30
_VETTING_ALIAS_TOLERANCE_FRACTION = 0.02
_PARAMETER_STELLAR_DENSITY_KG_M3 = 1408.0
_PARAMETER_DURATION_RATIO_MIN = 0.05
_PARAMETER_DURATION_RATIO_MAX = 1.8
```

Current `CandidateVettingResult` fields (R9/R10 will add new fields):
```python
class CandidateVettingResult:
    pass_min_transit_count: bool
    pass_odd_even_depth: bool
    pass_alias_harmonic: bool
    vetting_pass: bool
    transit_count_observed: int
    odd_depth_ppm: float
    even_depth_ppm: float
    odd_even_depth_mismatch_fraction: float
    alias_harmonic_with_rank: int
    vetting_reasons: str
    odd_even_status: str
```

Current alias ratios (R8 adds `2/3` and `3/2`):
```python
ratios = (0.5, 2.0, 1.0 / 3.0, 3.0)
```

`save_candidate_diagnostics()` currently produces: periodogram with period line, phase-fold with binned median and transit window shading. No SNR annotation, no model overlay, no odd/even subplot, no parameter text.

## Success Criteria
1. **R7**: `BLSCandidate` has `fap` field. When `compute_fap=true`, FAP is computed via bootstrap. When `false`, `fap` is `NaN`. Configurable via `bls.compute_fap` in TOML.
2. **R8**: Alias check catches 2:3 and 3:2 period ratios. A candidate at 2/3× or 3/2× a stronger candidate's period is flagged.
3. **R9**: Candidates with secondary eclipse depth > threshold fraction of primary depth get `pass_secondary_eclipse=False` and a vetting reason.
4. **R10**: Candidates with inconsistent phase-folded depth across data halves get `pass_depth_consistency=False` and a vetting reason.
5. **R11**: All six hardcoded constants are configurable via `[vetting]` and `[parameters]` TOML sections. Existing config files without these sections still work (defaults applied).
6. **R12**: Diagnostic plots include SNR text on periodogram, box-model overlay on phase-fold, odd/even comparison subplot, and parameter annotation text box.
7. **R13**: When enabled via config, pipeline runs mask-flatten-search iteration. Candidates from the second pass replace the first pass. Default off.
8. All existing tests pass. Pipeline produces valid output on `TIC 261136679` with each preset.

## Human Gates
architecture, impl-plan

## Additional Notes
- R8 is a 1-line change — lowest effort, highest confidence.
- R11 is the most cross-cutting change (config, pipeline, presets) — implement carefully to avoid breaking the config resolver.
- R12 needs access to vetting results and parameter estimates, so `save_candidate_diagnostics()` signature will need additional parameters.
- R13 interacts with R7 (FAP) — if both are enabled, FAP should be computed on the final (post-masking) BLS run, not the initial one.
- The `_DEFAULTS` dict in `config.py` must include new `[vetting]` and `[parameters]` sections with the current hardcoded values as defaults, ensuring backward compatibility.
