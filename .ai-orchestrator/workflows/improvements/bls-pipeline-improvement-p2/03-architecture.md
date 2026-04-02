---
agent: architecture
sequence: 3
references: ["spec", "analysis"]
summary: "Modular extension of the existing layered pipeline architecture. Five changes touch four modules (bls.py, parameters.py, plotting.py, config.py) plus pipeline.py wiring and preset TOMLs. No new modules or architectural patterns — all changes are additions to existing dataclasses, functions, and config resolution. TIC lookup is isolated behind an optional adapter function with timeout and fallback."
---

## Architecture Overview

The existing Exohunt pipeline uses a layered architecture: config resolution → preprocessing → BLS search → vetting → parameter estimation → plotting → output. The P2 improvements extend this architecture without changing its structure. All five changes are localized modifications to existing layers:

```
[config.py]  ──→  [bls.py]         (R16: refine reuse, R17: dedup config)
     │        ──→  [parameters.py]  (R18: limb darkening, R20: TIC lookup)
     │        ──→  [plotting.py]    (R19: smoothing config)
     │
     └──→  [pipeline.py]  (wires new config fields to function calls)
     └──→  [presets/*.toml]  (new default values)
```

This approach was chosen because:
- All P2 items are incremental enhancements to existing functions (FR-1 through FR-11)
- The pipeline was already decomposed in the prior refactoring workflow
- No new inter-module dependencies are introduced
- Backward compatibility is maintained via `_DEFAULTS` (FR-11, NFR-5)

## Component Design

### Component: Config Layer (`config.py`)
- **Responsibility**: Define and resolve all runtime configuration including new P2 fields.
- **Public Interface**:
  - `BLSConfig.unique_period_separation_fraction: float` (new field, default 0.05)
  - `ParameterConfig.apply_limb_darkening_correction: bool` (new, default False)
  - `ParameterConfig.limb_darkening_u1: float` (new, default 0.4)
  - `ParameterConfig.limb_darkening_u2: float` (new, default 0.2)
  - `ParameterConfig.tic_density_lookup: bool` (new, default False)
  - `PlotConfig.smoothing_window: int` (new, default 5)
  - `resolve_runtime_config()` — updated to parse new fields
- **Dependencies**: None (leaf module)
- **Requirements Covered**: FR-2, FR-5, FR-7, FR-8, FR-11
- **Internal Structure**: Dataclass field additions + `_DEFAULTS` dict updates + `resolve_runtime_config()` parsing additions

### Component: BLS Search (`bls.py`)
- **Responsibility**: Run BLS transit search and refine candidates.
- **Public Interface**:
  - `refine_bls_candidates()` — signature unchanged, internal implementation refactored to reuse `_BLSInputs`
  - `run_bls_search(unique_period_separation_fraction=0.05)` — default changed from 0.02 to 0.05
- **Dependencies**: `_prepare_bls_inputs()`, `_BLSInputs`, `BoxLeastSquares` (astropy)
- **Requirements Covered**: FR-1, FR-2, FR-3, NFR-1
- **Internal Structure**:
  - New private function `_refine_single_candidate(inputs: _BLSInputs, candidate: BLSCandidate, ...) -> BLSCandidate` — runs BLS on a narrowed period window using a pre-built model
  - `refine_bls_candidates()` calls `_prepare_bls_inputs()` once, then loops `_refine_single_candidate()` per candidate

### Component: Parameter Estimation (`parameters.py`)
- **Responsibility**: Estimate candidate physical parameters from BLS fit values.
- **Public Interface**:
  - `estimate_candidate_parameters(candidates, ..., apply_limb_darkening_correction=False, limb_darkening_u1=0.4, limb_darkening_u2=0.2, tic_density_lookup=False, tic_id=None)` — extended signature
- **Dependencies**: lightkurve/astroquery (for TIC lookup, optional), math, numpy
- **Requirements Covered**: FR-4, FR-5, FR-6, FR-8, FR-9, FR-10
- **Internal Structure**:
  - New private function `_lookup_tic_density(tic_id: str, timeout: float = 10.0) -> float | None` — queries TIC, computes density from mass+radius, returns None on failure
  - Modified depth-to-radius block: conditional limb darkening correction

### Component: Plotting (`plotting.py`)
- **Responsibility**: Generate diagnostic visualizations.
- **Public Interface**:
  - `save_raw_vs_prepared_plot(..., smoothing_window: int = 5)` — new parameter
- **Dependencies**: matplotlib, numpy
- **Requirements Covered**: FR-7
- **Internal Structure**: `_smooth_series()` call receives `window` from the new parameter instead of hardcoded 9

### Component: Pipeline Orchestration (`pipeline.py`)
- **Responsibility**: Wire config values to module function calls.
- **Public Interface**: No changes to external interface.
- **Dependencies**: All above modules
- **Requirements Covered**: FR-3 (threading dedup config), all wiring
- **Internal Structure**: Updated call sites to pass new config fields

## Data Model

### Extended `BLSConfig` Dataclass
```
BLSConfig:
  enabled: bool
  mode: str
  period_min_days: float
  period_max_days: float
  duration_min_hours: float
  duration_max_hours: float
  n_periods: int
  n_durations: int
  top_n: int
  min_snr: float
  compute_fap: bool
  fap_iterations: int
  iterative_masking: bool
  unique_period_separation_fraction: float  ← NEW (default 0.05)
```

### Extended `ParameterConfig` Dataclass
```
ParameterConfig:
  stellar_density_kg_m3: float
  duration_ratio_min: float
  duration_ratio_max: float
  apply_limb_darkening_correction: bool  ← NEW (default False)
  limb_darkening_u1: float               ← NEW (default 0.4)
  limb_darkening_u2: float               ← NEW (default 0.2)
  tic_density_lookup: bool               ← NEW (default False)
```

### Extended `PlotConfig` Dataclass
```
PlotConfig:
  enabled: bool
  interactive_html: bool
  dpi: int
  smoothing_window: int  ← NEW (default 5)
```

### `_BLSInputs` (unchanged)
```
_BLSInputs:
  time: np.ndarray
  flux: np.ndarray
  model: BoxLeastSquares
  periods: np.ndarray
  durations: np.ndarray
```

No new entities. No database. All data is in-memory dataclasses and numpy arrays.

## Interface Contracts

### `_refine_single_candidate()` (new private function)
```python
def _refine_single_candidate(
    inputs: _BLSInputs,
    candidate: BLSCandidate,
    period_min_days: float,
    period_max_days: float,
    window_fraction: float,
    n_periods: int,
    n_durations: int,
) -> BLSCandidate
```
- **Input**: Pre-built `_BLSInputs` with full period range, candidate to refine, refinement parameters.
- **Output**: Refined `BLSCandidate` with updated period/duration/depth/power/snr. Returns original candidate if refinement fails.
- **Error handling**: Returns original candidate on any failure (empty results, degenerate grid).

### `_lookup_tic_density()` (new private function)
```python
def _lookup_tic_density(
    tic_id: str,
    timeout_seconds: float = 10.0,
) -> float | None
```
- **Input**: TIC identifier string (e.g., "261136679"), timeout in seconds.
- **Output**: Stellar density in kg/m³, or `None` if lookup fails.
- **Error handling**: Returns `None` and logs warning on: network timeout, missing mass/radius fields, non-finite values, any exception.

### `estimate_candidate_parameters()` (extended)
```python
def estimate_candidate_parameters(
    candidates: list[BLSCandidate],
    stellar_density_kg_m3: float = 1408.0,
    duration_ratio_min: float = 0.05,
    duration_ratio_max: float = 1.8,
    apply_limb_darkening_correction: bool = False,
    limb_darkening_u1: float = 0.4,
    limb_darkening_u2: float = 0.2,
    tic_density_lookup: bool = False,
    tic_id: str | None = None,
) -> dict[int, CandidateParameterEstimate]
```

### `save_raw_vs_prepared_plot()` (extended)
Adds `smoothing_window: int = 5` parameter. Passes it to `_smooth_series(window=smoothing_window)`.

## Technology Choices

| Technology | Purpose | Alternatives Considered | Selection Rationale |
|-----------|---------|------------------------|---------------------|
| astroquery.mast `Catalogs` | TIC stellar parameter lookup (R20) | lightkurve `search_targetpixelfile` metadata, direct MAST API HTTP calls | astroquery is already a transitive dependency of lightkurve, provides typed catalog query interface, handles pagination. NFR-4 compliance. |
| Python `logging` module | Warning on TIC lookup failure (FR-10) | print statements, custom logger | Already used throughout the codebase. Consistent with existing warning patterns. |
| Existing `_prepare_bls_inputs()` | Model reuse in refinement (R16) | Creating a new lightweight BLS wrapper | Function already exists and returns the exact `_BLSInputs` object needed. No new code required for model instantiation. |

## Data Flow

### Primary Flow: Refinement with Model Reuse (R16)
1. `pipeline.py` calls `refine_bls_candidates(lc_prepared, candidates, ...)`
2. `refine_bls_candidates()` calls `_prepare_bls_inputs(lc_prepared, period_min, period_max, ...)` once → returns `_BLSInputs` with model
3. For each candidate: calls `_refine_single_candidate(inputs, candidate, ...)` which:
   a. Computes narrowed period window around `candidate.period_days`
   b. Creates narrowed period grid via `np.geomspace(local_min, local_max, n_periods)`
   c. Calls `inputs.model.power(inputs.durations, narrowed_periods)` directly
   d. Extracts best peak, computes SNR, returns refined `BLSCandidate`
4. Returns list of refined candidates

### TIC Lookup Flow (R20)
1. `pipeline.py` passes `tic_density_lookup=True` and `tic_id="261136679"` to `estimate_candidate_parameters()`
2. `estimate_candidate_parameters()` calls `_lookup_tic_density(tic_id, timeout_seconds=10.0)`
3. `_lookup_tic_density()` calls `Catalogs.query_object(tic_id, catalog="TIC")`
4. If successful: extracts `mass` and `rad` fields, computes `density = 3 * mass * M_sun / (4 * pi * (rad * R_sun)^3)`, returns density
5. If failed: logs warning, returns `None`
6. `estimate_candidate_parameters()` uses returned density or falls back to `stellar_density_kg_m3` default

### Error Flow: TIC Lookup Failure
1. `_lookup_tic_density()` catches any exception (timeout, network error, missing fields)
2. Logs `logger.warning("TIC density lookup failed for %s: %s. Using default density.", tic_id, error)`
3. Returns `None`
4. `estimate_candidate_parameters()` proceeds with configured `stellar_density_kg_m3`

## Error Handling Strategy

- **Input Validation**: New config fields are validated in `resolve_runtime_config()` using existing `_expect_float()`, `_expect_bool()`, `_expect_int()` helpers. Invalid values raise `ConfigValidationError`.
- **TIC Lookup Errors**: All exceptions caught in `_lookup_tic_density()`. Returns `None`. Warning logged. Pipeline continues with default density. No crash path. (Mitigates RISK-1, RISK-4)
- **Refinement Edge Cases**: If `_prepare_bls_inputs()` returns `None` (degenerate input), `refine_bls_candidates()` returns original candidates unchanged. If `_refine_single_candidate()` produces no results for a candidate, the original candidate is kept. (Mitigates RISK-3)
- **Smoothing Edge Cases**: `_smooth_series()` already handles `window < 3` by returning input unchanged. New `smoothing_window` config is validated as `int >= 1`.

## Security Design

- **Authentication**: Not applicable — local CLI tool with no network services.
- **Authorization**: Not applicable — single-user local execution.
- **Data Protection**: TIC queries use HTTPS (astroquery default). No credentials stored. No PII processed.
- **Input Sanitization**: TIC ID is validated as numeric string before query. Config values are type-checked by `resolve_runtime_config()`.
- **Threat Mitigations**: TIC lookup timeout (NFR-2) prevents denial-of-service from slow network. No user-supplied code execution paths.

## Design Decisions

### DD-1: Reuse `_prepare_bls_inputs()` for refinement instead of creating a new lightweight wrapper
- **Context**: FR-1 requires eliminating redundant model instantiation in `refine_bls_candidates()`.
- **Alternatives**:
  - (A) Call `_prepare_bls_inputs()` once with full period range, then narrow the period grid per candidate → chosen
  - (B) Create a new `_prepare_bls_model_only()` that skips grid construction → requires duplicating validation logic
  - (C) Cache the model in a module-level variable → introduces global state, not thread-safe
- **Rationale**: Option A reuses existing validated code. The period grid from `_prepare_bls_inputs()` is not used directly — each candidate gets a narrowed grid computed inline. The model and validated time/flux arrays are the reused parts.
- **Consequences**: `_refine_single_candidate()` must construct its own narrowed period grid, but this is a single `np.geomspace()` call.

### DD-2: Default `apply_limb_darkening_correction=False` to preserve backward compatibility
- **Context**: FR-6 requires the uncorrected formula when disabled. RISK-5 notes coefficients may be inaccurate for non-solar stars.
- **Alternatives**:
  - (A) Default True with solar coefficients → changes existing output for all users
  - (B) Default False, opt-in → preserves existing behavior, chosen
- **Rationale**: P2 improvements should not change existing output by default. Users who want the correction enable it explicitly.
- **Consequences**: Users must opt in. The improvement is not visible until configured.

### DD-3: Use astroquery `Catalogs.query_object()` for TIC lookup instead of lightkurve metadata
- **Context**: FR-9 requires TIC stellar density retrieval.
- **Alternatives**:
  - (A) `astroquery.mast.Catalogs.query_object(tic_id, catalog="TIC")` → direct catalog access, returns full TIC row, chosen
  - (B) `lightkurve.search_targetpixelfile(tic_id)` and extract metadata → indirect, returns observation metadata not stellar parameters
  - (C) Direct MAST API HTTP request → requires manual URL construction, JSON parsing, error handling
- **Rationale**: astroquery is already installed (lightkurve dependency), provides typed access to TIC fields including `mass`, `rad`, `logg`, and handles MAST API details.
- **Consequences**: Depends on astroquery's MAST interface stability. Timeout must be enforced externally (astroquery does not expose per-query timeout natively — use `signal.alarm` or `concurrent.futures.ThreadPoolExecutor` with timeout).

### DD-4: Change deduplication default from 0.02 to 0.05 globally
- **Context**: FR-2 requires widening the filter. RISK-2 notes this changes candidate lists.
- **Alternatives**:
  - (A) Change default to 0.05 in `_DEFAULTS` and all presets → chosen
  - (B) Change only `_DEFAULTS`, leave presets at 0.02 → inconsistent
  - (C) Keep 0.02 default, only make it configurable → does not address the scientific issue (near-resonant planets discarded)
- **Rationale**: The 2% threshold is scientifically too aggressive. 5% is a better default that preserves near-resonant signals while still filtering obvious duplicates.
- **Consequences**: Existing users without explicit config may see additional candidates in their results. Manifest fingerprints will differ.
