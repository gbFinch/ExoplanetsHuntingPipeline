---
agent: architecture
sequence: 3
references: ["spec", "analysis"]
summary: "Layered extension of the existing Exohunt pipeline. Adds an iterative BLS loop in bls.py that wraps run_bls_search() with transit mask computation and optional re-flattening. Config dataclasses extended with new fields defaulting to current behavior. Pipeline dispatch in _search_and_output_stage() branches on iterative_masking flag. No new modules or dependencies."
---

## Architecture Overview

The architecture extends the existing layered pipeline (ingest → preprocess → search → vet → output) without introducing new modules. The iterative BLS feature is implemented as a new function in the existing `bls.py` module that wraps the current `run_bls_search()` in a loop. The pipeline dispatch layer (`pipeline.py`) gains a conditional branch. The config layer (`config.py`) gains new fields with backward-compatible defaults.

This approach was chosen because:
- The existing pipeline is well-structured with clear module boundaries (FR-1, FR-10, NFR-2)
- No new architectural patterns are needed — this is a loop around existing functionality (NFR-4)
- Backward compatibility requires minimal surface area changes (NFR-1, NFR-2)

```
[config.py]
  BLSConfig (+ new fields) ──────────────────────────────┐
  PreprocessConfig (+ new fields) ────────────────────────┤
                                                          ▼
[pipeline.py]                                        [bls.py]
  _search_and_output_stage() ──if iterative──▶ run_iterative_bls_search()
                               │                    │  ▲  loop
                               │                    ▼  │
                               │              run_bls_search() (existing)
                               │                    │
                               │              _build_transit_mask() (new)
                               │                    │
                               │              _cross_iteration_unique() (new)
                               │                    │
                               ├──if reflatten──▶ [preprocess.py]
                               │                   prepare_lightcurve(transit_mask=...)
                               │
                               └──else──▶ run_bls_search() (existing, unchanged)
```

## Component Design

### Component: IterativeBLSSearch (`bls.py`)
- **Responsibility**: Execute multiple BLS passes with transit masking between iterations, collecting candidates across all passes.
- **Public Interface**:
  - `run_iterative_bls_search(time, flux, config, preprocess_config=None, lc=None) -> list[BLSCandidate]`
  - `_build_transit_mask(time, candidates, padding_factor) -> np.ndarray` (module-private)
  - `_cross_iteration_unique(candidate, accepted, threshold=0.01) -> bool` (module-private)
- **Dependencies**: `run_bls_search()`, `_unique_period()`, `numpy`, optionally `prepare_lightcurve()`
- **Requirements Covered**: FR-1, FR-2, FR-3, FR-4, FR-5, FR-6, FR-11
- **Internal Structure**:
  - `run_iterative_bls_search()`: main loop function
  - `_build_transit_mask()`: computes boolean mask for transit epochs
  - `_cross_iteration_unique()`: checks 1% period separation against all prior candidates

### Component: TransitMaskComputation (`bls.py`)
- **Responsibility**: Compute a boolean array marking in-transit points for given candidate parameters.
- **Public Interface**: `_build_transit_mask(time: np.ndarray, candidates: list[BLSCandidate], padding_factor: float) -> np.ndarray`
- **Dependencies**: `numpy`
- **Requirements Covered**: FR-3
- **Internal Structure**: Single function. For each candidate, computes all transit epochs within the time range and marks points within `0.5 * duration * padding_factor` of each epoch.

### Component: ConfigExtensions (`config.py`)
- **Responsibility**: Define and parse new configuration fields for iterative BLS and iterative flattening.
- **Public Interface**: Extended `BLSConfig` and `PreprocessConfig` dataclasses; updated `_DEFAULTS`; updated `resolve_runtime_config()`.
- **Dependencies**: None (leaf component)
- **Requirements Covered**: FR-8, FR-9, FR-14
- **Internal Structure**:
  - `BLSConfig`: add `iterative_passes`, `subtraction_model`, `iterative_top_n`, `transit_mask_padding_factor`
  - `PreprocessConfig`: add `iterative_flatten`, `transit_mask_padding_factor`
  - `_DEFAULTS`: add default values for all new fields
  - `resolve_runtime_config()`: parse new fields from TOML

### Component: PreprocessExtension (`preprocess.py`)
- **Responsibility**: Accept optional transit mask in `prepare_lightcurve()` to exclude known transits from the flattening baseline fit.
- **Public Interface**: `prepare_lightcurve(..., transit_mask: np.ndarray | None = None) -> tuple[lk.LightCurve, bool]`
- **Dependencies**: `lightkurve`, `numpy`
- **Requirements Covered**: FR-7
- **Internal Structure**: Modified `prepare_lightcurve()` passes `mask=transit_mask` to `lc.flatten()`.

### Component: PipelineDispatch (`pipeline.py`)
- **Responsibility**: Route BLS execution to iterative or single-pass based on config.
- **Public Interface**: Modified `_search_and_output_stage()` and `fetch_and_plot()`
- **Dependencies**: `run_iterative_bls_search()`, `run_bls_search()`, config
- **Requirements Covered**: FR-10, FR-12, FR-13, FR-15, FR-16
- **Internal Structure**:
  - `_search_and_output_stage()`: conditional dispatch + per-iteration artifact writing
  - `fetch_and_plot()`: pass `bls_iterative_masking` through to search stage

## Data Model

### BLSCandidate (extended)
| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| rank | int | ≥ 1 | Within-iteration rank |
| period_days | float | > 0 | |
| duration_hours | float | > 0 | |
| depth | float | | Raw depth |
| depth_ppm | float | | Parts per million |
| power | float | | BLS power |
| transit_time | float | | Reference epoch (BTJD) |
| transit_count_estimate | float | ≥ 0 | |
| snr | float | | Signal-to-noise ratio |
| fap | float | | False alarm probability |
| **iteration** | **int** | **≥ 0** | **NEW: 0-indexed iteration number** |

Storage: JSON files in `outputs/<target>/candidates/`.

### Config Fields (new)
| Section | Field | Type | Default | Constraint |
|---------|-------|------|---------|------------|
| bls | iterative_passes | int | 1 | ≥ 1 |
| bls | subtraction_model | str | "box_mask" | enum: ["box_mask"] |
| bls | iterative_top_n | int | 1 | ≥ 1 |
| bls | transit_mask_padding_factor | float | 1.5 | > 0 |
| preprocess | iterative_flatten | bool | False | |
| preprocess | transit_mask_padding_factor | float | 1.5 | > 0 |

```
BLSConfig ──1:N──▶ BLSCandidate (per iteration)
RuntimeConfig ──1:1──▶ BLSConfig
RuntimeConfig ──1:1──▶ PreprocessConfig
```

## Interface Contracts

### `run_iterative_bls_search()`
```python
def run_iterative_bls_search(
    time: np.ndarray,           # BTJD time array
    flux: np.ndarray,           # Normalized flux array
    config: BLSConfig,          # Must have iterative_masking=True
    *,
    normalized: bool = True,
    preprocess_config: PreprocessConfig | None = None,
    lc: lk.LightCurve | None = None,  # Required if iterative_flatten=True
) -> list[BLSCandidate]:
    ...
```
- **Preconditions**: `config.iterative_masking` is True. `time` and `flux` are same-length 1D arrays. If `preprocess_config.iterative_flatten` is True, `lc` must not be None.
- **Returns**: List of `BLSCandidate` with `iteration` field set. Candidates from all iterations, ordered by iteration then rank.
- **Errors**: Raises `ValueError` if `lc` is None when iterative flattening is requested.

### `_build_transit_mask()`
```python
def _build_transit_mask(
    time: np.ndarray,
    candidates: list[BLSCandidate],
    padding_factor: float,
) -> np.ndarray:
    ...
```
- **Returns**: Boolean array, same length as `time`. `True` = in-transit (to be masked).

### `prepare_lightcurve()` (extended signature)
```python
def prepare_lightcurve(
    lc: lk.LightCurve,
    outlier_sigma: float = 5.0,
    flatten_window_length: int = 401,
    apply_flatten: bool = True,
    max_transit_duration_hours: float = 0.0,
    transit_mask: np.ndarray | None = None,  # NEW
) -> tuple[lk.LightCurve, bool]:
    ...
```
- **transit_mask**: Boolean array aligned with `lc.time`. When provided, passed as `mask=transit_mask` to `lc.flatten()`. Points where `transit_mask` is True are excluded from the SG fit but retained in the output.

## Technology Choices

| Technology | Purpose | Alternatives Considered | Selection Rationale |
|-----------|---------|------------------------|---------------------|
| numpy NaN masking | Transit point removal between iterations | Masked arrays; interpolation; actual subtraction of model | NaN is simplest, astropy BLS is documented to handle NaN via internal masking (NFR-4, FR-3). Masked arrays add complexity. Model subtraction is out of scope. |
| lightkurve `.flatten(mask=...)` | Exclude transit points from SG baseline fit | Manual SG implementation; scipy.signal.savgol_filter with manual masking | lightkurve already used throughout; its flatten accepts a mask parameter (NFR-4, FR-7). Avoids reimplementing SG. |
| Existing `run_bls_search()` | Per-iteration BLS execution | Reimplementing BLS loop from scratch | Wrapping existing function preserves all current behavior and reduces risk (FR-2, NFR-1). |
| JSON artifacts | Per-iteration candidate output | CSV; database | Consistent with existing artifact format (FR-12, FR-13). |

## Data Flow

### Primary Flow: Iterative BLS Search (3 iterations)
1. `fetch_and_plot()` resolves config with `iterative_masking=True`, `iterative_passes=3`
2. `_search_and_output_stage()` detects `iterative_masking=True`, calls `run_iterative_bls_search(time, flux, config, lc=lc)`
3. **Iteration 0**: `run_bls_search(time, flux, config)` → returns candidates. Top candidate (by SNR) selected.
4. `_build_transit_mask(time, [top_candidate], padding_factor)` → boolean mask
5. `flux[mask] = NaN` → masked flux for next iteration
6. (If `iterative_flatten=True`): `prepare_lightcurve(lc, transit_mask=cumulative_mask)` → re-flattened lc; extract new time/flux
7. **Iteration 1**: `run_bls_search(time, masked_flux, config)` → candidates. `_cross_iteration_unique()` filters duplicates.
8. Repeat for iteration 2. Stop if SNR < `min_snr` or iteration count reached.
9. Return combined candidate list with `iteration` field set.
10. `_search_and_output_stage()` writes per-iteration JSON files and combined JSON file.
11. Proceeds to refine → vet → manifest as normal.

### Error Flow: Insufficient Points After Masking
1. After masking in iteration N, fewer than 100 non-NaN points remain.
2. `run_iterative_bls_search()` logs a warning and terminates the loop early.
3. Returns candidates collected from iterations 0 through N-1.
4. Pipeline continues normally with partial results.

### Backward-Compatible Flow: Single Pass
1. `fetch_and_plot()` resolves config with `iterative_masking=False` (default).
2. `_search_and_output_stage()` calls `run_bls_search()` directly (existing code path, unchanged).
3. No iterative code is executed. Output is identical to current behavior.

## Error Handling Strategy

- **Input Validation**: `run_iterative_bls_search()` validates that `lc` is provided when `iterative_flatten` is True. Raises `ValueError` with descriptive message.
- **Insufficient Data**: If non-NaN point count drops below 100 after masking, the iteration loop terminates early with a `logging.warning()`. No exception raised — partial results are returned.
- **BLS Failure**: If `run_bls_search()` raises an exception during any iteration, it propagates up. The existing pipeline error handling in `_search_and_output_stage()` catches it.
- **No Candidates Found**: If an iteration produces zero candidates above `min_snr`, the loop terminates. This is the normal stopping condition (FR-4).
- **Config Validation**: `resolve_runtime_config()` validates new fields using existing `_expect_int`, `_expect_float`, `_expect_bool` helpers. Invalid values raise `ConfigValidationError`.

## Security Design

Not applicable. This is a local data processing pipeline with no network services, authentication, authorization, or user-facing APIs. All data is read from local files or public MAST archive. No sensitive data is processed.

## Design Decisions

### DD-1: Wrap `run_bls_search()` rather than modifying it
- **Context**: FR-2 requires iterative BLS to use the existing BLS function. NFR-1 requires identical output when `iterative_passes=1`.
- **Alternatives**: (A) Modify `run_bls_search()` to accept iteration state internally. (B) Create a completely independent iterative BLS implementation.
- **Rationale**: Wrapping preserves the existing function as-is, guaranteeing backward compatibility. Option A risks breaking existing callers. Option B duplicates logic.
- **Consequences**: The iterative function depends on `run_bls_search()`'s interface stability. Any future changes to `run_bls_search()` must be reflected in the wrapper.

### DD-2: Use NaN masking rather than array truncation for transit removal
- **Context**: FR-3 requires removing in-transit points between iterations. R-1 from analysis identifies NaN handling as a risk.
- **Alternatives**: (A) Set in-transit points to NaN. (B) Remove in-transit points from the array entirely. (C) Replace in-transit points with local median.
- **Rationale**: NaN preserves array alignment (time indices stay consistent across iterations), which simplifies cumulative mask building. Array truncation would require index remapping. Local median replacement could introduce artificial periodicity. Astropy BLS documentation indicates NaN handling via internal finite-value filtering.
- **Consequences**: Must verify astropy BLS NaN handling (R-1 mitigation). If NaN causes issues, fallback to option C (local median replacement) with minimal code change.

### DD-3: Keep `iterative_masking` bool as enable flag, `iterative_passes` as count
- **Context**: FR-10 requires a clear on/off switch. The `iterative_masking` field already exists as a stub.
- **Alternatives**: (A) Use only `iterative_passes` where 1 means single-pass (no separate bool). (B) Keep both fields.
- **Rationale**: Option B matches the existing codebase pattern where `bls.enabled` is a separate bool from the BLS parameters. The bool provides a clear semantic toggle. `iterative_passes=1` with `iterative_masking=True` is a valid configuration (single pass through the iterative code path, useful for testing).
- **Consequences**: Two fields to maintain. Config validation must ensure `iterative_passes ≥ 1` when `iterative_masking=True`.

### DD-4: Transit mask as boolean array rather than index list
- **Context**: FR-3 and FR-7 both need to identify in-transit points. lightkurve `.flatten(mask=...)` accepts a boolean array.
- **Alternatives**: (A) Boolean array. (B) Integer index array. (C) Time range list.
- **Rationale**: Boolean array is directly compatible with both numpy NaN assignment (`flux[mask] = NaN`) and lightkurve flatten (`mask=mask`). Index arrays require conversion. Time ranges require per-point evaluation.
- **Consequences**: Memory cost is one boolean per time point per mask operation — negligible for TESS data sizes (~18k points).
