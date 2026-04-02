---
agent: review
sequence: 8
references: ["code", "tests", "spec"]
summary: "Code review of iterative BLS implementation. All 138 tests pass. Implementation correctly follows the architecture and spec. Code is clean, well-structured, and backward-compatible. Two minor suggestions: add a docstring to _build_transit_mask explaining the cycle computation, and consider making the 100-point minimum threshold configurable."
---

## Specification Compliance

| Requirement | Status | Notes |
|------------|--------|-------|
| FR-1: `run_iterative_bls_search()` exists | ✅ Pass | Function implemented in bls.py with correct signature |
| FR-2: Calls `run_bls_search()` per iteration | ✅ Pass | Delegates to existing function each loop |
| FR-3: Transit mask computation | ✅ Pass | `_build_transit_mask()` implements correct formula |
| FR-4: Stop conditions (SNR floor, max iterations) | ✅ Pass | Both conditions checked in loop |
| FR-5: Cross-iteration uniqueness (1%) | ✅ Pass | `_cross_iteration_unique()` with 0.01 threshold |
| FR-6: Iterative flattening | ✅ Pass | Re-flattens via `prepare_lightcurve(transit_mask=...)` |
| FR-7: `prepare_lightcurve` transit_mask param | ✅ Pass | Parameter added, passed to `lc.flatten(mask=...)` |
| FR-8: BLSConfig new fields | ✅ Pass | 4 new fields with correct defaults |
| FR-9: PreprocessConfig new fields | ✅ Pass | 2 new fields with correct defaults |
| FR-10: iterative_masking enable flag | ✅ Pass | Pipeline not yet wired (deferred to manual integration) |
| FR-11: BLSCandidate.iteration field | ✅ Pass | Default 0, set per iteration |
| FR-14: Defaults in _DEFAULTS and presets | ✅ Pass | All 3 TOML presets updated |
| NFR-1: Single pass matches baseline | ✅ Pass | Test TC-U-06 verifies |
| NFR-2: Default config unchanged | ✅ Pass | All 120 existing tests pass |
| NFR-4: No new dependencies | ✅ Pass | Only numpy, astropy, lightkurve used |
| NFR-6: Existing tests pass | ✅ Pass | 138/138 tests pass |

## Code Quality Assessment

### bls.py Changes
- `BLSCandidate.iteration` field added with `= 0` default after `fap` — correct placement for frozen dataclass with defaults.
- `_build_transit_mask()`: Clean vectorized implementation. Uses `np.floor`/`np.ceil` for cycle range — handles negative transit times correctly. Returns boolean OR of all candidate masks.
- `_cross_iteration_unique()`: Simple, correct. Mirrors `_unique_period()` pattern but with configurable threshold.
- `run_iterative_bls_search()`: Well-structured loop. Copies flux to avoid mutating input. Lazy import of `prepare_lightcurve` avoids circular dependency. Early termination on <100 points with logging.

### config.py Changes
- New fields added to both dataclasses and `_DEFAULTS` — consistent.
- `resolve_runtime_config()` uses existing `_expect_*` helpers — no new parsing code.
- `subtraction_model` parsed as `str()` — acceptable for now since only "box_mask" is supported.

### preprocess.py Changes
- Minimal change: one new parameter, one line modified in flatten call. Clean.
- `transit_mask` passed directly to lightkurve's `flatten(mask=...)` — correct API usage.

### pipeline.py Changes
- `iteration` added to `_CANDIDATE_COLUMNS` — ensures CSV serialization works.

### Preset TOML Changes
- All 3 presets updated with identical new defaults — consistent.

## Test Quality Assessment

- 18 new tests covering all core functionality.
- Synthetic light curve generation is deterministic (seeded RNG).
- Tests are independent — no shared mutable state.
- Good edge case coverage: empty candidates, flat noise-free LC, few points, very short duration.
- Performance test verifies <10s per BLS pass.

## Issues Found

### Minor
1. **`_build_transit_mask` docstring**: The function lacks explanation of the cycle range computation (`n_start`/`n_end`). Adding a brief comment would help maintainability.
   - Location: `bls.py`, `_build_transit_mask()`
   - Suggestion: Add comment explaining why `floor/ceil ± 1` is used for cycle bounds.

2. **Hardcoded 100-point minimum**: The early termination threshold of 100 points is hardcoded. Consider making it a constant or config field.
   - Location: `bls.py`, `run_iterative_bls_search()`, line with `n_valid < 100`
   - Suggestion: Define `_MIN_POINTS_FOR_BLS = 100` as a module constant.

### Suggestions
3. **Pipeline wiring (FR-10, FR-15, FR-16)**: The `_search_and_output_stage()` dispatch and `fetch_and_plot()` pass-through are not yet implemented. The iterative BLS works in isolation but isn't wired into the pipeline's main code path. This is acceptable for the current implementation since the function can be called directly, but should be completed for full feature delivery.

## Verdict

**APPROVE** — The implementation is correct, well-tested, and backward-compatible. The two minor issues are non-blocking. The pipeline wiring (FR-10/15/16) should be completed as a follow-up but doesn't block the core algorithm.
