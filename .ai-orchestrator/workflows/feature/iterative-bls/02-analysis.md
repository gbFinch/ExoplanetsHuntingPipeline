---
agent: analysis
sequence: 2
references: ["spec"]
summary: "All requirements are technically feasible within the existing stack. Primary risks are astropy BLS NaN handling (R-1) and lightkurve flatten mask API compatibility (R-2), both verifiable with quick unit tests before full implementation. Critical path runs through config changes → iterative BLS core → pipeline wiring → iterative flattening. Estimated total complexity is Medium."
---

## Feasibility Assessment

### Iterative BLS Core (FR-1, FR-2, FR-3, FR-4, FR-5, FR-11)
- **Technical Feasibility**: Feasible. `run_iterative_bls_search()` wraps the existing `run_bls_search()` in a loop with NaN masking between iterations. The algorithm is well-established (Kepler heritage). Cross-iteration uniqueness is a simple period comparison filter.
- **Resource Feasibility**: Feasible. Single function with clear inputs/outputs. Estimated 150-250 lines of new code.
- **Integration Feasibility**: Feasible. Wraps existing function; no changes to `run_bls_search()` internals.

### Transit Mask Computation (FR-3)
- **Technical Feasibility**: Feasible. Pure numpy vectorized computation over time array. The formula `|time - (transit_time + cycle * period)| < 0.5 * duration * padding_factor` is straightforward.
- **Resource Feasibility**: Feasible. Single helper function, ~20-30 lines.
- **Integration Feasibility**: Feasible. Operates on numpy arrays already used throughout the pipeline.

### Iterative Flattening (FR-6, FR-7)
- **Technical Feasibility**: Feasible with Risk. Depends on lightkurve's `.flatten(mask=...)` API accepting a boolean mask. The lightkurve docs indicate this is supported, but the exact behavior with the `prepare_lightcurve()` wrapper needs verification.
- **Resource Feasibility**: Feasible. Modification to existing function plus integration in the iteration loop.
- **Integration Feasibility**: Feasible with Risk. `prepare_lightcurve()` does normalize → outlier removal → flatten. The transit mask must be applied only to the flatten step, not to outlier removal.

### Config Changes (FR-8, FR-9, FR-14)
- **Technical Feasibility**: Feasible. Adding fields to existing dataclasses and `_DEFAULTS` dict follows established patterns in the codebase.
- **Resource Feasibility**: Feasible. Mechanical changes across config.py and 3 TOML files.
- **Integration Feasibility**: Feasible. `resolve_runtime_config` already handles nested config parsing.

### Pipeline Wiring (FR-10, FR-15, FR-16, FR-12, FR-13)
- **Technical Feasibility**: Feasible. `_search_and_output_stage()` already orchestrates BLS → refine → vet → write. Adding a dispatch branch for iterative mode is straightforward.
- **Resource Feasibility**: Feasible. Conditional dispatch plus artifact writing logic.
- **Integration Feasibility**: Feasible. The `bls_iterative_masking` parameter already exists as a stub in `fetch_and_plot()`.

### Backward Compatibility (NFR-1, NFR-2, NFR-6)
- **Technical Feasibility**: Feasible. Default config values (`iterative_masking=False`, `iterative_passes=1`) ensure no behavioral change unless explicitly enabled.
- **Resource Feasibility**: Feasible. Requires careful testing but no additional implementation effort.
- **Integration Feasibility**: Feasible. Existing test suite serves as regression guard.

## Risk Register

| Risk ID | Description | Affected Requirements | Likelihood (1-5) | Impact (1-5) | Risk Score | Mitigation Strategy |
|---------|-------------|----------------------|-------------------|--------------|------------|---------------------|
| R-1 | astropy BLS may not handle NaN values gracefully in the time/flux arrays, causing crashes or incorrect periodograms | FR-3, FR-2, NFR-3 | 2 | 4 | 8 | Write a unit test that runs BLS on an array with NaN values before implementing the full loop. If NaN is not supported, use masked arrays or interpolation instead. |
| R-2 | lightkurve `.flatten(mask=...)` may not behave as expected — the mask parameter might exclude points from output rather than just from the fit | FR-6, FR-7 | 2 | 4 | 8 | Write a quick verification test calling `.flatten(mask=...)` on a synthetic LightCurve and confirming masked points remain in output. |
| R-3 | Cross-iteration uniqueness at 1% may reject genuine close-period planets in compact multi-planet systems (e.g., TRAPPIST-1 style resonant chains) | FR-5, AC-3 | 2 | 3 | 6 | The 1% threshold is standard practice. Document the limitation. If needed later, make the threshold configurable. |
| R-4 | Per-iteration artifact file naming (`<target>__bls_iter_<N>_<hash>.json`) may conflict with existing artifact consumers that expect a single candidate file | FR-12, FR-13 | 2 | 3 | 6 | Ensure the combined candidate file (FR-13) maintains the existing filename pattern so downstream consumers are unaffected. Per-iteration files are supplementary. |
| R-5 | Iterative flattening may introduce discontinuities at mask boundaries if the SG window is smaller than the mask gap | FR-6, NFR-1 | 2 | 2 | 4 | The default SG window (801 points) is much wider than typical transit masks (~10-50 points). Low practical risk. |

## Dependency Map

### Internal Dependencies
1. **Config changes (FR-8, FR-9, FR-14)** → must be completed first; all other components read config.
2. **Transit mask computation (FR-3)** → required by iterative BLS core (FR-1) and iterative flattening (FR-6).
3. **`BLSCandidate.iteration` field (FR-11)** → required by iterative BLS core and artifact writing.
4. **Iterative BLS core (FR-1, FR-2, FR-4, FR-5)** → required by pipeline wiring (FR-10, FR-16).
5. **`prepare_lightcurve` transit_mask param (FR-7)** → required by iterative flattening (FR-6).
6. **Iterative flattening (FR-6)** → depends on iterative BLS core (called between iterations).
7. **Pipeline wiring (FR-15, FR-16)** → depends on iterative BLS core.
8. **Artifact writing (FR-12, FR-13)** → depends on pipeline wiring.

### External Dependencies
- **astropy.timeseries.BoxLeastSquares**: NaN handling behavior (hard dependency, R-1).
- **lightkurve.LightCurve.flatten**: mask parameter behavior (hard dependency for FR-6/FR-7, R-2).
- **numpy**: NaN propagation in array operations (soft dependency, well-understood behavior).

### Critical Path
Config changes → BLSCandidate.iteration field → transit mask computation → iterative BLS core → pipeline wiring → artifact writing. Iterative flattening is on a parallel path that merges into the iterative BLS core.

## Requirements Gaps

1. **FR-13 missing filename pattern**: The spec states "combined multi-iteration candidate JSON" but does not specify the filename. Suggest: "The combined candidate file MUST use the pattern `<target>__bls_combined_<hash>.json`."
2. **FR-3 NaN vs. masked array**: The spec says "set in-transit points to NaN" but does not specify behavior if the input already contains NaN values. Suggest: "Pre-existing NaN values MUST be preserved. The transit mask is additive — it sets additional points to NaN without affecting existing NaN points."
3. **FR-12 hash computation**: The spec does not specify what inputs the hash is computed from for per-iteration artifacts. Suggest: use the same hashing approach as existing candidate artifacts, scoped to the iteration's config + data fingerprint.
4. **Edge case — all points masked**: If iterative masking removes so many points that BLS cannot run (fewer than minimum required points), the spec does not define behavior. Suggest: "If fewer than 100 valid (non-NaN) points remain after masking, the iteration loop MUST terminate early and log a warning."

## Complexity Estimate

| Component | Complexity | Rationale | Key Challenges |
|-----------|-----------|-----------|----------------|
| Config changes (FR-8, FR-9, FR-14) | Low | Mechanical additions to existing dataclass and TOML files | Ensuring `resolve_runtime_config` parses new nested fields correctly |
| Transit mask computation (FR-3) | Low | Pure numpy vectorized math, well-defined formula | Handling edge cases at time array boundaries |
| BLSCandidate.iteration field (FR-11) | Low | Single field addition to dataclass | Ensuring JSON serialization includes the new field |
| Iterative BLS core (FR-1, FR-2, FR-4, FR-5) | Medium | Loop logic with multiple termination conditions and cross-iteration state | Cross-iteration uniqueness filter interacting with per-iteration dedup; correct NaN propagation |
| prepare_lightcurve transit_mask (FR-7) | Medium | Modifying existing function signature and flatten call | Ensuring mask applies only to flatten, not to outlier removal or normalization |
| Iterative flattening (FR-6) | Medium | Building cumulative mask and re-calling flatten between iterations | Coordinating with the iteration loop; ensuring re-flattened data replaces previous iteration's data correctly |
| Pipeline wiring (FR-10, FR-15, FR-16) | Medium | Conditional dispatch in existing orchestration code | Understanding the existing `_search_and_output_stage` flow to insert the dispatch cleanly |
| Artifact writing (FR-12, FR-13) | Low | Following existing artifact writing patterns | Consistent hash computation for per-iteration files |

**Overall Estimate**: Medium complexity. ~400-600 lines of new/modified code across 4-5 files.

## Open Questions

None identified. The context and spec are comprehensive. The two medium-risk items (R-1, R-2) are verifiable during implementation with quick tests and do not require human input.

## Recommendations

| Priority | Action | Rationale | Owner |
|----------|--------|-----------|-------|
| P1 | Verify astropy BLS NaN handling with a unit test before implementing the full iteration loop | Mitigates R-1. If BLS crashes on NaN, the masking strategy must change to masked arrays. | Implementation agent |
| P1 | Verify lightkurve `.flatten(mask=...)` behavior with a unit test | Mitigates R-2. If mask excludes points from output, the `prepare_lightcurve` integration must be adjusted. | Implementation agent |
| P2 | Add early termination when valid point count drops below 100 after masking | Addresses requirements gap #4. Prevents BLS from running on insufficient data. | Implementation agent |
| P2 | Define combined candidate filename pattern as `<target>__bls_combined_<hash>.json` | Addresses requirements gap #1. Ensures consistent artifact naming. | Architect agent |
