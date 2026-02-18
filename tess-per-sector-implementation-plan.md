# TESS Per-Sector Preprocessing Plan

## Goal
Refactor the pipeline so detrending/preprocessing is done per sector (or per file) before stitching, which is more stable and scientifically safer than flattening one large stitched light curve.

## Why Per-Sector
- Sector products have different baselines/systematics.
- Flattening a fully stitched series can distort boundaries and hide/alter transits.
- Per-sector processing is easier to tune, debug, and cache.

## Implementation Steps

1. Split ingestion into segment-aware structures
- Add a `LightCurveSegment` model with:
  - `sector`, `author`, `cadence`, `time`, `flux`, `quality`, `meta`
- Load `download_all()` outputs as a list of segments instead of immediate global stitch.
- Exit criteria: one target run yields a segment list with sector IDs and point counts.

2. Add per-segment raw cache
- Cache each segment separately:
  - `outputs/cache/segments/<target>/sector_<N>__raw.npz`
- Include metadata sidecar (JSON) for provenance.
- Exit criteria: rerun can load segments from cache without network calls.

3. Implement per-segment preprocessing
- Run `remove_nans`, robust normalization, outlier filtering, optional flatten per segment.
- Auto-tune flatten window by segment length/cadence constraints.
- Exit criteria: each segment emits a prepared segment and per-segment preprocessing metrics.

4. Add per-segment prepared cache
- Cache prepared segment keyed by preprocessing params:
  - `sector_<N>__prep_<hash>.npz`
- Exit criteria: same params skip recompute (including flatten) on rerun.

5. Stitch only after segment preprocessing
- Concatenate prepared segments in time order into analysis-ready series.
- Keep gap metadata so downstream search can account for discontinuities.
- Exit criteria: produce stitched prepared light curve + segment boundary index.

6. Update diagnostics
- Save:
  - per-segment raw vs prepared mini-panels
  - final stitched prepared plot with sector boundary markers
- Exit criteria: visual artifacts clearly show segment behavior and final stitched result.

7. Add CLI controls
- New options:
  - `--preprocess-mode {global,per-sector}` (default `per-sector`)
  - `--sectors 14,15,16` filter
  - `--authors` filter (e.g., `SPOC`)
- Exit criteria: CLI can switch modes and subset sectors deterministically.

8. Test strategy
- Unit tests:
  - segment extraction
  - per-segment cache key/path generation
  - per-segment preprocessing behavior
- Integration tests:
  - cache-hit path skips network+flatten
  - per-sector mode stitches expected length/order
- Exit criteria: tests pass and cover both global and per-sector code paths.

## Rollout Order
1. Segment model + ingestion
2. Segment cache (raw)
3. Per-segment preprocessing + prepared cache
4. Stitch-after-preprocess path
5. CLI switch and diagnostics
6. Tests + default mode flip to `per-sector`
