---
agent: architecture
sequence: 3
references: ["spec", "analysis"]
summary: "Extends the existing layered pipeline architecture with minimal new components: two new config dataclasses (VettingConfig, ParameterConfig) wired through the existing _DEFAULTS/resolver pattern, two new vetting functions in vetting.py, a bootstrap FAP function in bls.py, an iterative masking wrapper in pipeline.py, and enhanced matplotlib rendering in plotting.py. All changes follow existing module boundaries and patterns."
---

## Architecture Overview

The existing Exohunt pipeline uses a **layered pipeline architecture**: config → ingest → preprocess → BLS search → vetting → parameter estimation → plotting → output serialization. Each layer is a separate module (`config.py`, `bls.py`, `vetting.py`, `parameters.py`, `plotting.py`) orchestrated by `pipeline.py`.

The P1 changes extend this architecture in-place without introducing new modules or changing the pipeline flow. The pattern is: add config fields → add processing logic → wire through pipeline orchestrator.

```
[config.py]  ──→  [pipeline.py orchestrator]
  VettingConfig        │
  ParameterConfig      ├──→ [bls.py] ── run_bls_search() + bootstrap_fap()
  BLSConfig+new        │         │
                       ├──→ [vetting.py] ── vet_bls_candidates() + 2 new checks
                       │         │
                       ├──→ [plotting.py] ── save_candidate_diagnostics() + annotations
                       │
                       └──→ iterative masking loop (in pipeline.py)
```

This approach was chosen because:
- The existing module boundaries cleanly separate concerns (FR-1–FR-33)
- No new inter-module dependencies are introduced
- The `_DEFAULTS` + `_deep_merge` config pattern generalizes to new sections (RISK-2 mitigation)
- Independent deployability (NFR-3) is preserved since each fix touches isolated code paths

## Component Design

### C1: Config Layer (`config.py`)
- **Responsibility**: Define, validate, and resolve all runtime configuration including new `[vetting]` and `[parameters]` sections.
- **Public Interface**:
  - `VettingConfig` dataclass (FR-17)
  - `ParameterConfig` dataclass (FR-18)
  - `RuntimeConfig` with new `vetting: VettingConfig` and `parameters: ParameterConfig` fields (FR-19)
  - `resolve_runtime_config()` extended to parse new sections (FR-22)
- **Dependencies**: None (leaf module).
- **Requirements Covered**: FR-17, FR-18, FR-19, FR-20, FR-22, FR-24, NFR-2.
- **Internal Structure**: Two new frozen dataclasses. `_DEFAULTS` dict extended with `"vetting"` and `"parameters"` sub-dicts. `resolve_runtime_config()` adds `vetting_data = merged["vetting"]` and `parameters_data = merged["parameters"]` extraction blocks following the existing pattern for `bls_data`, `plot_data`, etc.

### C2: BLS Search Layer (`bls.py`)
- **Responsibility**: Run BLS transit search and optionally compute bootstrap FAP.
- **Public Interface**:
  - `BLSCandidate` dataclass with new `fap: float` field (FR-1)
  - `run_bls_search()` with new `compute_fap` and `fap_iterations` parameters (FR-2, FR-5)
  - New internal `_bootstrap_fap()` function (FR-3)
- **Dependencies**: astropy `BoxLeastSquares`, numpy.
- **Requirements Covered**: FR-1, FR-2, FR-3, FR-4, FR-5, NFR-1.
- **Internal Structure**: `_bootstrap_fap(time, flux, candidate_power, periods, durations, n_iterations)` shuffles flux N times, runs BLS, returns fraction of max-powers ≥ candidate_power. Called from `run_bls_search()` when `compute_fap=True`. Uses reduced period grid (200 periods) for bootstrap to meet NFR-1 (RISK-1 mitigation).

### C3: Vetting Layer (`vetting.py`)
- **Responsibility**: Vet BLS candidates with transit count, odd/even, alias, secondary eclipse, and depth consistency checks.
- **Public Interface**:
  - `CandidateVettingResult` with 4 new fields (FR-8, FR-13)
  - `vet_bls_candidates()` with new threshold parameters (FR-9, FR-14)
  - New `_secondary_eclipse_check()` (FR-7)
  - New `_phase_fold_depth_consistency()` (FR-12)
  - Updated `_alias_harmonic_reference_rank()` ratios (FR-6)
- **Dependencies**: `BLSCandidate` from `bls.py`, numpy, lightkurve.
- **Requirements Covered**: FR-6, FR-7, FR-8, FR-9, FR-10, FR-11, FR-12, FR-13, FR-14, FR-15, FR-16.
- **Internal Structure**:
  - `_secondary_eclipse_check(time, flux, period_days, transit_time, duration_days)` → `(depth_fraction: float, pass: bool)`. Measures depth at phase 0.5 ± duration/2 using the same median-based approach as `_group_depth_ppm()`.
  - `_phase_fold_depth_consistency(time, flux, period_days, transit_time, duration_days)` → `(consistency_fraction: float, pass: bool)`. Splits time array at midpoint, measures in-transit depth in each half.

### C4: Plotting Layer (`plotting.py`)
- **Responsibility**: Generate diagnostic plots with enhanced annotations.
- **Public Interface**:
  - `save_candidate_diagnostics()` with new keyword-only parameters: `vetting_results`, `parameter_estimates` (FR-29)
- **Dependencies**: matplotlib, numpy, `BLSCandidate`, `CandidateVettingResult`.
- **Requirements Covered**: FR-25, FR-26, FR-27, FR-28, FR-29.
- **Internal Structure**: Within the per-candidate loop:
  - SNR text: `ax_p.text()` at peak power location (FR-25)
  - Box-model overlay: `ax_full.fill_between()` with rectangular dip at transit phase (FR-26)
  - Odd/even subplot: new third subplot `ax_oe` with bar chart of odd vs even depth (FR-27)
  - Parameter text box: `fig.text()` with period, depth, duration, SNR, vetting status (FR-28)

### C5: Pipeline Orchestrator (`pipeline.py`)
- **Responsibility**: Wire config values to processing functions; implement iterative masking loop.
- **Public Interface**: No new public API. Internal changes to `fetch_and_plot()`.
- **Dependencies**: All other components.
- **Requirements Covered**: FR-23, FR-30, FR-31, FR-32, FR-33, NFR-3.
- **Internal Structure**:
  - Replace 6 hardcoded constants with `cfg.vetting.*` and `cfg.parameters.*` references (FR-23)
  - Add iterative masking block: `if cfg.bls.iterative_masking: ...` (FR-30–FR-32)
  - FAP ordering: compute FAP only on final candidates (FR-33)

## Data Model

### BLSCandidate (extended)
| Field | Type | Constraint | Notes |
|-------|------|-----------|-------|
| rank | int | ≥ 1 | Existing |
| period_days | float | > 0 | Existing |
| duration_hours | float | > 0 | Existing |
| depth | float | — | Existing |
| depth_ppm | float | — | Existing |
| power | float | — | Existing |
| transit_time | float | — | Existing |
| transit_count_estimate | float | — | Existing |
| snr | float | — | Existing |
| **fap** | **float** | **[0,1] or NaN** | **New (FR-1)** |

### CandidateVettingResult (extended)
| Field | Type | Constraint | Notes |
|-------|------|-----------|-------|
| pass_min_transit_count | bool | — | Existing |
| pass_odd_even_depth | bool | — | Existing |
| pass_alias_harmonic | bool | — | Existing |
| **pass_secondary_eclipse** | **bool** | — | **New (FR-8)** |
| **pass_depth_consistency** | **bool** | — | **New (FR-13)** |
| vetting_pass | bool | — | Existing (AND of all pass_* fields) |
| transit_count_observed | int | ≥ 0 | Existing |
| odd_depth_ppm | float | — | Existing |
| even_depth_ppm | float | — | Existing |
| odd_even_depth_mismatch_fraction | float | — | Existing |
| **secondary_eclipse_depth_fraction** | **float** | **[0,∞) or NaN** | **New (FR-8)** |
| **depth_consistency_fraction** | **float** | **[0,∞) or NaN** | **New (FR-13)** |
| alias_harmonic_with_rank | int | — | Existing |
| vetting_reasons | str | — | Existing |
| odd_even_status | str | — | Existing |

### VettingConfig (new, FR-17)
| Field | Type | Default | Notes |
|-------|------|---------|-------|
| min_transit_count | int | 2 | From pipeline.py line 110 |
| odd_even_max_mismatch_fraction | float | 0.30 | From pipeline.py line 111 |
| alias_tolerance_fraction | float | 0.02 | From pipeline.py line 112 |
| secondary_eclipse_max_fraction | float | 0.30 | New for R9 |
| depth_consistency_max_fraction | float | 0.50 | New for R10 |

### ParameterConfig (new, FR-18)
| Field | Type | Default | Notes |
|-------|------|---------|-------|
| stellar_density_kg_m3 | float | 1408.0 | From pipeline.py line 113 |
| duration_ratio_min | float | 0.05 | From pipeline.py line 114 |
| duration_ratio_max | float | 1.8 | From pipeline.py line 115 |

### BLSConfig (extended)
| Field | Type | Default | Notes |
|-------|------|---------|-------|
| ... (existing fields) | ... | ... | Unchanged |
| **compute_fap** | **bool** | **False** | **New (FR-2)** |
| **fap_iterations** | **int** | **1000** | **New (FR-5)** |
| **iterative_masking** | **bool** | **False** | **New (FR-30)** |

Storage: All data is in-memory dataclasses. Candidates are serialized to JSON/CSV files in `outputs/<target>/candidates/`. Config is serialized to manifest JSON.

```
BLSCandidate 1──* CandidateVettingResult (keyed by rank)
RuntimeConfig 1──1 VettingConfig
RuntimeConfig 1──1 ParameterConfig
RuntimeConfig 1──1 BLSConfig (extended)
```

## Interface Contracts

### `_bootstrap_fap()` (new internal function in bls.py)
```python
def _bootstrap_fap(
    time: np.ndarray,
    flux: np.ndarray,
    observed_power: float,
    periods: np.ndarray,
    durations: np.ndarray,
    n_iterations: int = 1000,
) -> float:
    """Return fraction of bootstrap max-powers >= observed_power. Range [0.0, 1.0]."""
```

### `_secondary_eclipse_check()` (new in vetting.py)
```python
def _secondary_eclipse_check(
    time: np.ndarray,
    flux: np.ndarray,
    period_days: float,
    transit_time: float,
    duration_days: float,
) -> tuple[float, bool]:
    """Return (secondary_depth_fraction, pass). NaN fraction if insufficient data."""
```

### `_phase_fold_depth_consistency()` (new in vetting.py)
```python
def _phase_fold_depth_consistency(
    time: np.ndarray,
    flux: np.ndarray,
    period_days: float,
    transit_time: float,
    duration_days: float,
) -> tuple[float, bool]:
    """Return (consistency_fraction, pass). NaN fraction if insufficient data."""
```

### `save_candidate_diagnostics()` (extended signature)
```python
def save_candidate_diagnostics(
    target: str,
    output_key: str,
    lc_prepared: lk.LightCurve,
    candidates: list[BLSCandidate],
    period_grid_days: np.ndarray,
    power_grid: np.ndarray,
    *,
    vetting_results: dict[int, CandidateVettingResult] | None = None,
    parameter_estimates: dict[int, Any] | None = None,
) -> list[tuple[Path, Path]]:
```

### `vet_bls_candidates()` (extended signature)
```python
def vet_bls_candidates(
    lc_prepared: lk.LightCurve,
    candidates: list[BLSCandidate],
    min_transit_count: int = 2,
    odd_even_mismatch_max_fraction: float = 0.3,
    alias_tolerance_fraction: float = 0.02,
    secondary_eclipse_max_fraction: float = 0.3,
    depth_consistency_max_fraction: float = 0.5,
) -> dict[int, CandidateVettingResult]:
```

## Technology Choices

| Technology | Purpose | Alternatives Considered | Selection Rationale |
|-----------|---------|------------------------|---------------------|
| numpy random shuffle | Bootstrap flux permutation (R7) | scipy.stats permutation_test, custom Cython | numpy is already a dependency; shuffle is sufficient for FAP; no new dependency (NFR-4) |
| matplotlib text/patches | Diagnostic annotations (R12) | plotly annotations, custom SVG | matplotlib is the existing plotting backend; consistency with current plots; no new dependency (NFR-4) |
| Existing `_deep_merge` + `_DEFAULTS` | Config extension (R11) | pydantic, attrs, new config library | Existing pattern works; proven by 5 existing sections; no new dependency (NFR-4) |

## Data Flow

### Primary Flow: BLS Search with FAP (R7 enabled)
1. `pipeline.py` reads `cfg.bls.compute_fap` and `cfg.bls.fap_iterations` from `RuntimeConfig`
2. Calls `run_bls_search()` with `compute_fap=True, fap_iterations=N`
3. `run_bls_search()` finds candidates via BLS power spectrum (existing logic)
4. For each candidate, calls `_bootstrap_fap(time, flux, candidate.power, periods, durations, N)`
5. `_bootstrap_fap()` shuffles flux N times, runs BLS with reduced grid, returns FAP
6. `BLSCandidate` is constructed with `fap=computed_value`
7. Candidates returned to pipeline for vetting

### Iterative Masking Flow (R13 enabled)
1. `pipeline.py` checks `cfg.bls.iterative_masking`
2. First pass: flatten light curve (no mask) → run BLS → get initial candidates
3. Build boolean mask: True for in-transit points of rank-1 candidate
4. Second pass: re-flatten with mask → run BLS on re-flattened data → get final candidates
5. Final candidates replace initial candidates
6. If `compute_fap` also enabled, FAP computed only on final candidates (FR-33)

### Error Flow: Insufficient Data for Vetting Checks
1. `_secondary_eclipse_check()` finds < 5 in-eclipse points
2. Returns `(float("nan"), True)` — pass by default, NaN fraction
3. `vet_bls_candidates()` sets `pass_secondary_eclipse=True`, `secondary_eclipse_depth_fraction=NaN`
4. `vetting_pass` is not penalized
5. Same pattern for `_phase_fold_depth_consistency()` with insufficient half-data

## Error Handling Strategy

- **Input Validation**: Config validation in `resolve_runtime_config()` — new fields validated with same `_expect_float`, `_expect_int`, `_expect_bool` helpers. Invalid values raise `ConfigValidationError`.
- **Insufficient Data**: Vetting functions return pass=True with NaN metrics when data is insufficient (FR-10, FR-15). This follows the existing pattern from odd/even inconclusive handling (R2).
- **Bootstrap Failure**: If BLS raises during a bootstrap iteration (e.g., degenerate shuffled data), catch the exception, skip that iteration, and adjust the denominator. If all iterations fail, set `fap=NaN`.
- **Plotting Graceful Degradation**: If `vetting_results` is `None` (not passed), skip annotations that require vetting data. Existing plot output is preserved.
- **Error Propagation**: All errors propagate as exceptions through the pipeline. `ConfigValidationError` for config issues, standard Python exceptions for runtime errors. No new exception types needed.

## Security Design

This is a local data-processing pipeline with no network services, authentication, or user-facing APIs. Security considerations are minimal:
- **Data Protection**: Light curve data is publicly available TESS data. No sensitive data handling required.
- **Input Sanitization**: TOML config parsing uses Python's `tomllib` (safe parser, no code execution). New config fields are validated with type-checking helpers.
- **No New Attack Surface**: All changes are internal computation. No new file I/O paths beyond existing output directories.

## Design Decisions

### DD-1: Reduced Period Grid for Bootstrap FAP
- **Decision**: Use 200 periods (vs full grid of 2000+) for bootstrap BLS iterations.
- **Context**: NFR-1 requires <60s per candidate. Full grid × 1000 iterations would take ~500–2000s (RISK-1).
- **Alternatives**: (A) Full grid with parallelism — adds complexity, not portable. (B) Analytical FAP approximation — less accurate, different statistical properties. (C) Reduced grid — trades precision for speed.
- **Rationale**: 200 periods captures the same power distribution shape at lower resolution. FAP is a statistical measure where exact period precision matters less than power distribution sampling. Opt-in flag further limits blast radius.
- **Consequences**: FAP values may differ slightly from a full-grid bootstrap. Acceptable for a screening metric.

### DD-2: Keyword-Only Arguments for Extended Function Signatures
- **Decision**: New parameters on `save_candidate_diagnostics()` and `vet_bls_candidates()` are keyword-only with defaults.
- **Context**: RISK-4 — signature changes could break existing callers.
- **Alternatives**: (A) New wrapper functions — duplicates code. (B) Positional args — breaks existing callers. (C) Keyword-only with defaults — backward compatible.
- **Rationale**: Keyword-only args with `None`/default values ensure all existing call sites work without modification. New functionality activates only when new args are explicitly passed.
- **Consequences**: Callers that want new features must use keyword syntax. This is standard Python practice.

### DD-3: Config Extension via Existing `_DEFAULTS` Pattern
- **Decision**: Add `[vetting]` and `[parameters]` sections to `_DEFAULTS` and use the same `_deep_merge` + extraction pattern as existing sections.
- **Context**: RISK-2 — config resolver might have section-specific logic.
- **Alternatives**: (A) Separate config file for vetting — breaks single-file config model. (B) Flat keys in existing sections — pollutes BLS config namespace. (C) New sections following existing pattern — clean, consistent.
- **Rationale**: Reading the resolver code confirms `_deep_merge` is generic (schema-driven, not section-specific). Adding new top-level keys to `_DEFAULTS` and extracting them in `resolve_runtime_config()` follows the exact pattern used for `io`, `ingest`, `preprocess`, `plot`, and `bls`.
- **Consequences**: `_DEFAULTS` grows by ~15 lines. `resolve_runtime_config()` grows by ~20 lines. Three preset TOMLs each grow by ~8 lines.

### DD-4: Single-Candidate Masking for Iterative Mode
- **Decision**: Mask only the rank-1 candidate's in-transit points during iterative masking.
- **Context**: FR-31 says "mask in-transit points" without specifying how many candidates.
- **Alternatives**: (A) Mask all candidates — aggressive, may remove real signals. (B) Mask top-N — complex, diminishing returns. (C) Mask rank-1 only — simple, addresses the dominant systematic.
- **Rationale**: The primary purpose of iterative masking is to remove the strongest signal so weaker signals can emerge. Masking rank-1 only is the standard approach in transit search literature.
- **Consequences**: Multi-planet masking deferred to P2 (listed in Non-Goals).
