---
agent: review
sequence: 8
references: ["spec", "impl-plan", "tests", "code"]
summary: "Code review of P2 improvements. All 5 fixes implemented correctly. 120/120 tests pass. One P1 test required update for new ParameterConfig fields (expected — backward-compatible dataclass extension). No security, performance, or correctness issues found."
---

## Review Summary

All five P2 improvements (R16–R20) have been implemented and verified against the specification.

## Requirement Verification

| Requirement | Status | Evidence |
|------------|--------|---------|
| FR-1 (Refinement reuse) | ✅ Pass | `refine_bls_candidates()` calls `_prepare_bls_inputs()` once. `test_refine_reuses_prepare_bls_inputs` verifies call count = 1. |
| FR-2 (Dedup default 0.05) | ✅ Pass | `run_bls_search()` default changed to 0.05. `test_blsconfig_dedup_default_is_005` verifies. |
| FR-3 (Dedup config threading) | ✅ Pass | `pipeline.py` passes `bls_unique_period_separation_fraction` to `run_bls_search()` calls. |
| FR-4 (Limb darkening formula) | ✅ Pass | `test_limb_darkening_correction_applied` verifies formula `sqrt(depth / (1 - u1/3 - u2/6))`. |
| FR-5 (ParameterConfig fields) | ✅ Pass | `test_parameter_config_fields_exist` verifies all 4 new fields. |
| FR-6 (Uncorrected when disabled) | ✅ Pass | `test_limb_darkening_correction_disabled` verifies `sqrt(depth)` when disabled. |
| FR-7 (Smoothing window) | ✅ Pass | `PlotConfig.smoothing_window` added. `save_raw_vs_prepared_plot()` accepts and uses it. |
| FR-8 (tic_density_lookup field) | ✅ Pass | Field exists in `ParameterConfig` with default `False`. |
| FR-9 (TIC lookup success) | ✅ Pass | `_lookup_tic_density()` implemented with astroquery. `test_lookup_tic_density_success` verifies. |
| FR-10 (TIC fallback) | ✅ Pass | Returns `None` on any exception. `test_lookup_tic_density_fallback_on_error` and `test_lookup_tic_density_nan_fields` verify. |
| FR-11 (Backward compatibility) | ✅ Pass | `_DEFAULTS` updated. `test_new_config_defaults_backward_compatible` verifies. |

## Code Quality Assessment

- **Config changes**: Clean extension of existing pattern. New fields follow the same `_expect_*` validation pattern. `_DEFAULTS` updated consistently.
- **BLS refinement**: Clean refactor. `_prepare_bls_inputs()` called once, model reused via `inputs.model.power()`. Fallback to original candidate on any failure.
- **Limb darkening**: Minimal change — `ld_factor` computed once, applied in the existing radius computation. Default `False` preserves backward compatibility.
- **TIC lookup**: Properly isolated in `_lookup_tic_density()` with lazy import, ThreadPoolExecutor timeout, and comprehensive exception handling.
- **Smoothing**: Minimal wiring change. Default reduced from 9 to 5.

## Issues Found

1. **Minor**: The P1 test `test_r11_parameter_config_defaults` needed updating because it directly constructed `ParameterConfig` without the new fields. Fixed by adding the new fields with defaults. This is expected behavior for a frozen dataclass extension.

## Test Results

- 120/120 tests pass
- 0 failures
- 1 warning (lightkurve/oktopus — pre-existing)

## Recommendation

**Approve.** All changes are backward-compatible, well-tested, and follow existing code patterns.
