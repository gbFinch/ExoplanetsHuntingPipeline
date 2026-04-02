# Project: Iterative BLS with Transit Masking and Iterative Flattening

## Type
feature

## Description
Implement iterative BLS transit search with box-mask subtraction and iterative flattening with transit masking to enable secondary (multi-planet) detection in Exohunt.

Three work items from the research (01-research.md in `research/secondary-planets-search/`):

### 1. P0 Pipeline Fixes — Status: MOSTLY COMPLETE
The research identified 6 issues in Section 3.8. Current status after code audit:

- **3.8.1 SNR computation**: ✅ Fixed. `run_bls_search` computes `snr = (power - median) / (1.4826 * MAD)`, filters by `min_snr` param, stores in `BLSCandidate.snr`.
- **3.8.2 Depth normalization**: ✅ Fixed. `prepare_lightcurve` returns `was_normalized` flag; `run_bls_search` accepts `normalized` param and computes `depth_ppm` conditionally.
- **3.8.3 Cross-iteration uniqueness**: ⚠️ Partial. Per-iteration `_unique_period` (5% separation) exists. Cross-iteration dedup needed once iterative BLS is built — implement a 1% filter comparing new candidates against all previously subtracted signals.
- **3.8.4 Odd/even vetting inconclusive**: ✅ Fixed. Returns `odd_even_status="inconclusive"` with `pass_odd_even=True` when insufficient data. `CandidateVettingResult` has `odd_even_status` field.
- **3.8.5 Missing harmonic ratios**: ✅ Fixed. `_alias_harmonic_reference_rank` includes `(0.5, 2.0, 1/3, 3.0, 2/3, 3/2)`.
- **3.8.6 Refine reuses BLS model**: ✅ Fixed. `refine_bls_candidates` calls `_prepare_bls_inputs` once, reuses `inputs.model` for all local re-searches.

**Remaining**: Only 3.8.3 (cross-iteration uniqueness) is incomplete — blocked on iterative BLS implementation.

### 2. P0: Implement Iterative BLS with Box Mask Subtraction
Create `run_iterative_bls_search()` that wraps `run_bls_search` in a loop:
1. Run BLS on current light curve
2. Take top candidate (must pass `min_snr` threshold)
3. Mask its transit epochs (set in-transit points to NaN using period, transit_time, duration + padding factor)
4. Re-run BLS on residual
5. Stop when SNR < `bls.snr_floor` or `bls.iterative_passes` reached
6. Apply cross-iteration uniqueness filter (1% period separation against all previously found signals)
7. Return combined candidate list across all iterations with iteration number annotated

**Config fields already present**: `BLSConfig.iterative_masking` (bool, default False). `fetch_and_plot` accepts `bls_iterative_masking` but does nothing with it.

**Config fields to add to `BLSConfig`**:
- `iterative_passes` (int, default 1) — max iterations
- `subtraction_model` (str, default "box_mask") — only "box_mask" for now
- `snr_floor` (float) — can reuse existing `min_snr` (default 7.0)
- `iterative_top_n` (int, default 1) — candidates to subtract per iteration
- `transit_mask_padding_factor` (float, default 1.5) — mask width multiplier on duration

**Key files to modify**:
- `src/exohunt/bls.py` — add `run_iterative_bls_search()`, add `iteration` field to `BLSCandidate`, add cross-iteration uniqueness filter
- `src/exohunt/config.py` — add new fields to `BLSConfig`, update `_DEFAULTS`, update `resolve_runtime_config` parsing
- `src/exohunt/pipeline.py` — wire `run_iterative_bls_search` into `_search_and_output_stage` when `iterative_masking=True`; update `fetch_and_plot` to pass new config
- Preset TOML files — add new defaults (iterative_passes=1 preserves current behavior)

**Output artifacts**: Per-iteration candidate JSON files (`<target>__bls_iter_<N>_<hash>.json`). Combined multi-planet grouping JSON.

**Algorithm reference**: Kepler TCE iterative search (Jenkins et al. 2010). Box mask = set in-transit points to local median or NaN. Transit mask computed as: `|time - (transit_time + cycle * period)| < 0.5 * duration * padding_factor`.

### 3. P1: Implement Iterative Flattening with Transit Masking
Between BLS iterations, re-flatten the light curve with known transit epochs masked from the Savitzky-Golay fit. This prevents the primary transit from biasing the flatten baseline and recovers 5-15% of shallow secondary transit depth.

**Implementation**:
- Add `transit_mask` parameter to `prepare_lightcurve` (boolean array, points to exclude from flatten fit)
- Use lightkurve's `.flatten(mask=transit_mask)` — already supported by the API
- Between iterations in `run_iterative_bls_search`: build cumulative transit mask from all found candidates, call `prepare_lightcurve` (or just `.flatten`) with that mask, then re-run BLS on the re-flattened data

**Config fields to add to `PreprocessConfig`**:
- `iterative_flatten` (bool, default False) — enable re-flattening between BLS iterations
- `transit_mask_padding_factor` (float, default 1.5) — how wide to mask around each transit epoch (can share with BLS config or keep separate)

**Key files to modify**:
- `src/exohunt/preprocess.py` — add `transit_mask` param to `prepare_lightcurve`
- `src/exohunt/config.py` — add fields to `PreprocessConfig`, update `_DEFAULTS` and parsing
- `src/exohunt/bls.py` or `pipeline.py` — integrate re-flatten step into the iterative loop

## Background
The current pipeline runs single-pass BLS returning top N peaks from one periodogram. In multi-planet systems, secondary planets with shallower depths are buried in sidelobes and spectral leakage of the dominant signal. Iterative BLS with transit subtraction is the standard approach (Kepler pipeline heritage, 2009-2018) to find multiple planets. This is the most impactful capability gap for science use of Exohunt.

## Constraints
- Python 3.10+
- No new dependencies — use existing astropy BLS and numpy only
- Must remain compatible with existing RuntimeConfig/preset system
- Setting `iterative_passes=1` (or `iterative_masking=False`) must preserve exact current behavior
- Works with TESS 2-minute and 30-minute cadence data
- Each BLS pass on typical TESS data (~18k points) takes 1-5s; 3 passes add 3-15s total — acceptable
- Iterative flattening adds ~2-8s per re-flatten call

## Existing Code/System
- **Repository**: `/Users/gbasin/Development/exoplanets-hunting-pipeline/`
- **BLS search**: `src/exohunt/bls.py` — `run_bls_search()` returns `list[BLSCandidate]` with period, duration, transit_time, snr, depth. `refine_bls_candidates()` does local re-search. `_unique_period()` deduplicates sidelobes at 5% separation.
- **Preprocessing**: `src/exohunt/preprocess.py` — `prepare_lightcurve()` does normalize → outlier removal → SG flatten. Returns `(lc, was_normalized)`. Already accepts `flatten_window_length` and adaptive window via `max_transit_duration_hours`.
- **Vetting**: `src/exohunt/vetting.py` — `vet_bls_candidates()` runs odd/even, alias/harmonic, secondary eclipse, depth consistency checks. Already handles inconclusive odd/even. Harmonic ratios include 2/3 and 3/2.
- **Config**: `src/exohunt/config.py` — `BLSConfig` dataclass has `iterative_masking` bool field. `PreprocessConfig` has flatten params. `_DEFAULTS` dict, `_deep_merge` validation, preset TOML loading.
- **Pipeline**: `src/exohunt/pipeline.py` — `_search_and_output_stage()` orchestrates BLS → refine → vet → write. `fetch_and_plot()` is the top-level entry point; accepts `bls_iterative_masking` but doesn't use it. Supports stitched and per-sector BLS modes.

## Success Criteria
1. `run_iterative_bls_search()` exists and finds ≥2 candidates on a synthetic multi-signal light curve when `iterative_passes≥2`
2. Setting `iterative_passes=1` produces identical output to current `run_bls_search`
3. Cross-iteration uniqueness filter prevents re-detecting the same signal
4. Transit mask correctly zeroes in-transit points with configurable padding
5. Iterative flattening with `transit_mask` param re-flattens excluding known transits
6. All new config fields have defaults that preserve current behavior
7. Existing tests pass without modification
8. Per-iteration candidate artifacts are written with iteration metadata

## Human Gates
impl-plan

## Additional Notes
- Research source: `.ai-orchestrator/workflows/research/secondary-planets-search/01-research.md`
- The `bls_iterative_masking` config field and `fetch_and_plot` parameter already exist as stubs — wire them up rather than creating parallel config paths
- Consider whether `iterative_passes` should replace or complement `iterative_masking` bool — recommend keeping the bool as the enable flag and `iterative_passes` as the count (only used when bool is True)
- Validation targets: TOI-178 (6 planets), TOI-700 (4 planets) — verify ≥2 additional planets recovered vs single-pass
- The per-sector BLS mode should also support iterative masking, but stitched mode is the priority
