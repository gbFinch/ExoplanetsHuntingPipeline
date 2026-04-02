# Project: BLS Pipeline Refactoring (R14 + R15)

## Type
refactoring

## Description
Implement R14 and R15 from the BLS pipeline quality audit.

**R14 — Decompose `pipeline.py` monolith** (Issue O1, P1 priority)
Split `fetch_and_plot()` (~886 lines, lines 771–1656) into discrete typed stages. Currently this single function handles: data download, caching, preprocessing, BLS search, refinement, vetting, parameter estimation, plotting, candidate output, metrics, and manifest writing. It is untestable in isolation — you cannot test BLS search without also triggering download, caching, and plotting.

Target decomposition into pipeline stages:
1. **Ingest stage** — TESS product search, download, caching (both stitched and per-sector paths)
2. **Preprocess stage** — outlier removal, flattening, normalization, segment preparation, metrics computation
3. **Search stage** — BLS search, refinement, iterative masking (both stitched and per-sector)
4. **Vetting stage** — candidate vetting and parameter estimation
5. **Output stage** — candidate CSV/JSON writing, diagnostic plot generation, metrics writing
6. **Plotting stage** — raw-vs-prepared plots (static and interactive)
7. **Manifest stage** — run manifest and index writing, summary logging

`fetch_and_plot()` becomes a thin orchestrator calling each stage in sequence. Each stage takes typed inputs and returns typed outputs (use dataclasses for stage I/O).

**R15 — Refactor BLS duplicate code** (Issue B5, P2 priority)
`run_bls_search()` (lines 76–199) and `compute_bls_periodogram()` (lines 202–245) share identical logic:
- Input validation (finite check, min 50 points)
- Time sorting (`np.argsort`)
- Span computation and validation
- Period grid construction (`np.geomspace` with clamping)
- Duration grid construction (`_duration_grid_days` + filtering)
- BLS model instantiation (`BoxLeastSquares(time, flux)`)
- `model.power(periods, durations)` call

Extract shared setup into a private `_prepare_bls_inputs()` that returns `(model, periods, durations)` or an empty sentinel. Both public functions call this helper and diverge only in post-processing.

## Background
P0 fixes (R1–R6) and P1 fixes (R7–R13) have been applied. The pipeline is functionally correct but the 886-line `fetch_and_plot()` monolith makes further changes risky and testing difficult. The BLS module has copy-pasted setup code across two public functions. These are the remaining structural debt items before the codebase is clean.

Research source: `.ai-orchestrator/workflows/research/bls-pipeline-issues/01-research.md`
Prior work: `.ai-orchestrator/workflows/improvements/bls-pipeline-improvement-p0/` and `bls-pipeline-improvement-p1/`

## Constraints
- Python ≥ 3.10. No new dependencies.
- Pure refactoring — no behavioral changes. All existing outputs must be byte-identical for the same inputs.
- Existing test suite must pass without modification.
- Must remain compatible with `RuntimeConfig`/preset/TOML config system.
- `fetch_and_plot()` public signature and return type must not change (backward compatibility for `cli.py` and `run_batch_analysis()`).
- Stage functions should be importable and callable independently for future unit testing.

## Existing Code/System
Repository: `/Users/gbasin/Development/exoplanets-hunting-pipeline`

### R14 — Pipeline monolith

Primary file: `src/exohunt/pipeline.py`
- `fetch_and_plot()` — lines 771–1656 (886 lines), the monolith to decompose
- `run_batch_analysis()` — lines 622–768, calls `fetch_and_plot()` (must continue to work)
- Helper functions already extracted: `_write_bls_candidates()`, `_candidate_output_key()`, `_stitch_segments()`, `_write_preprocessing_metrics()`, `_write_run_manifest()`, `_write_manifest_index_row()`, `_metrics_cache_path()`, `_load_cached_metrics()`, `_save_cached_metrics()`

Current `fetch_and_plot()` logical sections:
1. Lines 771–820: Parameter setup and mode resolution
2. Lines 821–930: Stitched-mode ingest (cache check → download → stitch)
3. Lines 930–1070: Per-sector ingest (segment manifest → download → per-segment preprocessing)
4. Lines 1070–1110: Metrics computation and writing
5. Lines 1110–1300: BLS search (per-sector and stitched paths, refinement, vetting, parameter estimation, candidate writing, diagnostics)
6. Lines 1300–1410: Stitched-mode candidate output and diagnostics
7. Lines 1410–1510: Plotting (stitched and per-sector)
8. Lines 1510–1580: Manifest writing
9. Lines 1580–1656: Summary logging

Imports used by `fetch_and_plot()`:
- `lightkurve as lk`, `numpy as np`
- `exohunt.cache.*`, `exohunt.bls.*`, `exohunt.ingest.*`, `exohunt.models.LightCurveSegment`
- `exohunt.plotting.*`, `exohunt.preprocess.*`, `exohunt.progress.*`
- `exohunt.parameters.*`, `exohunt.vetting.*`

### R15 — BLS duplicate code

Primary file: `src/exohunt/bls.py`

Duplicated block in `run_bls_search()` (lines 90–120) and `compute_bls_periodogram()` (lines 210–240):
```python
time = np.asarray(lc_prepared.time.value, dtype=float)
flux = np.asarray(lc_prepared.flux.value, dtype=float)
finite = np.isfinite(time) & np.isfinite(flux)
time, flux = time[finite], flux[finite]
if len(time) < 50: return ...
order = np.argsort(time)
time, flux = time[order], flux[order]
span_days = float(np.nanmax(time) - np.nanmin(time))
if not np.isfinite(span_days) or span_days <= 0: return ...
p_min = max(0.05, float(period_min_days))
p_max_limit = max(p_min * 1.05, span_days * 0.95)
p_max = min(float(period_max_days), p_max_limit)
if p_max <= p_min: return ...
periods = np.geomspace(p_min, p_max, num=max(200, int(n_periods)))
durations = _duration_grid_days(...)
durations = durations[durations < 0.25 * p_max]
if len(durations) == 0: durations = ...
model = BoxLeastSquares(time, flux)
result = model.power(periods, durations)
```

`refine_bls_candidates()` (lines 248–299) calls `run_bls_search()` per candidate, re-instantiating the full BLS model each time. After R15, it could optionally use `_prepare_bls_inputs()` directly for efficiency (Issue B4, but that's a separate optimization — R15 scope is just DRY extraction).

## Success Criteria
1. `fetch_and_plot()` is ≤80 lines — a thin orchestrator calling stage functions
2. Each stage function has a clear typed signature (dataclass inputs/outputs)
3. Stage functions are defined at module level and importable
4. `run_bls_search()` and `compute_bls_periodogram()` share a single `_prepare_bls_inputs()` helper with no duplicated validation/setup code
5. All existing tests pass without modification
6. Running `python -m exohunt.cli run --target "TIC 261136679" --config science-default` produces identical output before and after refactoring
7. No behavioral changes — same candidates, same plots, same manifests for same inputs

## Human Gates
architecture, impl-plan

## Additional Notes
- R15 should be done first — it's a small, self-contained change in `bls.py` (~20 lines) with no cross-module impact.
- R14 is the larger effort. Recommended approach: define stage dataclasses first, then extract stages bottom-up (manifest → plotting → output → search → preprocess → ingest), testing after each extraction.
- The per-sector vs stitched branching is the main complexity in `fetch_and_plot()`. Consider whether stages should handle both modes internally or whether the orchestrator selects the mode and passes it as a parameter.
- Do NOT change the public API of `fetch_and_plot()` — `cli.py` and `run_batch_analysis()` depend on its signature and return type.
