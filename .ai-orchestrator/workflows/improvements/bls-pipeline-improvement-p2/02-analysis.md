---
agent: analysis
sequence: 2
references: ["spec"]
summary: "All five P2 improvements are technically feasible with low-to-medium risk. The highest risk is R20 (TIC density lookup) due to external network dependency and variable TIC catalog completeness. R16-R19 are straightforward changes to existing modules. Critical path: config.py changes (shared by R17, R18, R19, R20) must be implemented first, then module-specific changes can proceed in parallel."
---

## Feasibility Assessment

### R16 — BLS Refinement Model Reuse (FR-1)
- **Technical Feasibility**: Feasible. `_prepare_bls_inputs()` already exists and returns a `_BLSInputs` object with the model. The refactor replaces per-candidate `run_bls_search()` calls with direct model usage.
- **Resource Feasibility**: Low effort (~30 lines). Single-file change in `bls.py`.
- **Integration Feasibility**: No interface changes to callers of `refine_bls_candidates()`. Internal-only refactor.

### R17 — Configurable Deduplication Filter (FR-2, FR-3)
- **Technical Feasibility**: Feasible. Requires adding one field to `BLSConfig`, updating `_DEFAULTS`, and threading the value through `run_bls_search()`.
- **Resource Feasibility**: Low effort (~10 lines across config.py, bls.py, pipeline.py).
- **Integration Feasibility**: Backward compatible — existing configs without the field get the new default (0.05).

### R18 — Limb Darkening Correction (FR-4, FR-5, FR-6)
- **Technical Feasibility**: Feasible. The correction formula is a single-line change gated by a boolean config flag.
- **Resource Feasibility**: Low effort (~15 lines across parameters.py and config.py).
- **Integration Feasibility**: Default `apply_limb_darkening_correction=False` preserves existing behavior exactly.

### R19 — Reduced Percentile Smoothing (FR-7)
- **Technical Feasibility**: Feasible. Requires adding one field to `PlotConfig` and passing it through to `_smooth_series()`.
- **Resource Feasibility**: Low effort (~10 lines across config.py, plotting.py, pipeline.py).
- **Integration Feasibility**: Cosmetic change only. No impact on candidate detection or vetting.

### R20 — TIC Stellar Density Lookup (FR-8, FR-9, FR-10)
- **Technical Feasibility**: Feasible with Risk. lightkurve provides `search_targetpixelfile()` and astroquery provides `Catalogs.query_object()` for TIC access. However, TIC does not always include stellar density directly — it provides `mass`, `rad` (radius), and `logg` from which density must be derived.
- **Resource Feasibility**: Medium effort (~30 lines in parameters.py plus error handling).
- **Integration Feasibility**: Network dependency requires timeout handling, graceful fallback, and optional activation via config flag.

### Non-Functional Requirements
- **NFR-1** (Performance): Feasible. Eliminating 4 redundant `_prepare_bls_inputs()` calls directly reduces overhead.
- **NFR-2** (Timeout): Feasible. Python `signal` or `astroquery` timeout parameters can enforce the 10-second limit.
- **NFR-3** (Python 3.10+): Feasible. No features beyond 3.10 are needed.
- **NFR-4** (No new deps): Feasible. lightkurve and astroquery are already transitive dependencies of lightkurve.
- **NFR-5** (Existing tests pass): Feasible with care. Default values preserve existing behavior.

## Risk Register

| Risk ID | Description | Affected Requirements | Likelihood (1-5) | Impact (1-5) | Risk Score | Mitigation Strategy |
|---------|-------------|----------------------|-------------------|--------------|------------|---------------------|
| RISK-1 | TIC catalog does not contain mass/radius for the target star, making density computation impossible | FR-9, FR-10 | 4 | 2 | 8 | Fall back to configured default density with warning. Log which field was missing. |
| RISK-2 | Changing deduplication default from 0.02 to 0.05 alters candidate lists for existing users, breaking reproducibility of prior runs | FR-2, NFR-5 | 3 | 2 | 6 | Document the change in release notes. Existing user configs that explicitly set the value are unaffected. Manifest system records config fingerprints for comparison. |
| RISK-3 | `_prepare_bls_inputs()` with narrowed period range for refinement may produce empty or degenerate period grids for edge-case candidates | FR-1 | 2 | 3 | 6 | Add guard: if `_prepare_bls_inputs()` returns `None` for a candidate, keep the original unrefined candidate (matching current fallback behavior). |
| RISK-4 | TIC query hangs or is extremely slow in batch mode (many targets), degrading pipeline throughput | FR-9, NFR-2 | 3 | 2 | 6 | Enforce 10-second timeout per query. Cache TIC results per target to avoid repeated lookups. Default `tic_density_lookup=False` so batch users opt in explicitly. |
| RISK-5 | Limb darkening coefficients u₁=0.4, u₂=0.2 are inaccurate for non-solar-type stars, giving worse radius estimates than no correction | FR-4, FR-5 | 2 | 2 | 4 | Default `apply_limb_darkening_correction=False`. Document that coefficients should be adjusted for non-solar hosts. |

## Dependency Map

### Internal Dependencies
- **config.py changes** (R17, R18, R19, R20) → all other modules. Config fields must exist before module code can reference them.
- **R20 (TIC lookup)** depends on R18 (limb darkening) only in the sense that both modify `parameters.py` and `ParameterConfig`. No functional dependency — they can be implemented independently.
- **R16 (refinement reuse)** is fully independent of all other R-items.
- **R19 (smoothing)** is fully independent of all other R-items.

### External Dependencies
- **lightkurve / astroquery.mast** (R20): TIC catalog access. Hard dependency for R20 when `tic_density_lookup=True`. Soft dependency overall (feature is optional).
- **MAST API** (R20): Remote service. Network access required. Subject to availability and rate limits.

### Critical Path
```
config.py (add all new fields) → parameters.py (R18 + R20) → pipeline.py (wire config) → preset TOMLs
                                → bls.py (R16 + R17)
                                → plotting.py (R19)
```
Config changes are the single blocking dependency. After that, bls.py, parameters.py, and plotting.py changes can proceed in parallel.

## Requirements Gaps

1. **FR-9 does not specify how to extract density from TIC**: TIC provides `mass` (solar masses) and `rad` (solar radii), not density directly. The spec should state: "When TIC provides stellar mass and radius, compute density as `density = (mass * M_sun) / ((4/3) * pi * (radius * R_sun)^3)`. When TIC provides `logg` and `rad`, compute density from surface gravity."
   - Affected: FR-9
   - Suggested addition to FR-9: "The system MUST compute stellar density from TIC `mass` and `rad` fields using `ρ = 3M / (4πR³)`. If mass or radius is unavailable, fall back per FR-10."

2. **No acceptance criterion for NFR-1 (performance)**: The spec states "≤40% of current time" but no AC verifies this.
   - Affected: NFR-1
   - Suggested: Add AC-10: "Given 5 candidates, when `refine_bls_candidates()` is timed with the old and new implementations on the same input, then the new implementation completes in ≤40% of the old implementation's wall time."

3. **FR-7 does not specify the smoothing window's valid range**: A window of 0 or 1 would disable smoothing; a very large window would over-smooth.
   - Affected: FR-7
   - Suggested addition: "The `smoothing_window` value MUST be an odd integer ≥ 3. If an even value is provided, it MUST be decremented by 1. If < 3, smoothing MUST be skipped."

4. **Preset TOML updates not specified per-preset**: The spec says "update preset TOML files" but does not specify which presets get which values.
   - Affected: FR-11, Scope
   - Suggested: All three presets get the same defaults as `_DEFAULTS`. No preset-specific overrides for P2 fields.

## Complexity Estimate

| Component | Complexity | Rationale | Key Challenges |
|-----------|-----------|-----------|----------------|
| R16 (Refinement reuse) | Medium | Requires extracting the inner loop of `refine_bls_candidates()` to use `_BLSInputs` directly instead of `run_bls_search()`. Must replicate the candidate extraction logic from `run_bls_search()` for a single-period-window search. | Correctly replicating the peak extraction and SNR computation for a narrowed period range without `run_bls_search()`. |
| R17 (Dedup filter) | Low | One new config field, one default change, one parameter threading. | None significant. |
| R18 (Limb darkening) | Low | Single conditional formula change gated by boolean. | None significant. |
| R19 (Smoothing) | Low | One new config field, one parameter threading. | None significant. |
| R20 (TIC lookup) | Medium | Network I/O, error handling, TIC field parsing, density computation from mass/radius, timeout enforcement, logging. | TIC field availability varies per target. Must handle missing fields, NaN values, and network failures gracefully. |

## Open Questions

1. **Should TIC lookup results be cached to disk for batch mode?**
   - Affects: FR-9, NFR-2
   - Impact: Without caching, batch mode with 100 targets makes 100 network requests. With caching, repeated runs skip the lookup.
   - Default assumption: No disk caching in P2 scope. TIC lookup is per-run only. Caching can be added later.

2. **Should the refinement reuse (R16) create a new `_refine_single_candidate()` internal function or inline the logic?**
   - Affects: FR-1, code maintainability
   - Impact: A separate function is cleaner but adds indirection.
   - Default assumption: Create a private `_refine_single_candidate()` that takes a `_BLSInputs` and a `BLSCandidate` and returns a refined `BLSCandidate`.

## Recommendations

1. **P0**: Implement config.py changes first (all new fields for R17, R18, R19, R20) as a single coherent change, since all module changes depend on config fields existing.
   - Rationale: Critical path dependency. All other changes are blocked until config fields exist.
   - Owner: Implementation agent.

2. **P1**: Add the density computation formula to FR-9 specification (gap #1 above) before implementation.
   - Rationale: RISK-1. Without specifying how to derive density from TIC fields, the implementation may make incorrect assumptions.
   - Owner: Spec clarification (default assumption from gap #1 is sufficient to proceed).

3. **P1**: Add a guard clause in R16 for `_prepare_bls_inputs()` returning `None` on narrowed period ranges.
   - Rationale: RISK-3. Edge-case candidates near period boundaries could produce degenerate grids.
   - Owner: Implementation agent.

4. **P2**: Document the deduplication default change (0.02 → 0.05) in a changelog or release notes.
   - Rationale: RISK-2. Existing users may notice different candidate lists.
   - Owner: Human (documentation).
