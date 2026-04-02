---
agent: summary
sequence: 9
references: ["spec", "analysis", "architecture", "impl-plan", "test-spec", "tests", "code", "review"]
summary: "Successfully implemented all 5 P2 improvements (R16–R20) for the Exohunt BLS pipeline. Changes span 8 source files and 3 preset TOMLs. 14 new tests added, 120/120 total tests pass. All changes are backward-compatible."
---

## Project Summary

**BLS Pipeline P2 Improvements (R16–R20)** — Five polish-level improvements to the Exohunt exoplanet transit-search pipeline addressing performance, configurability, parameter accuracy, and visualization quality.

## Completed Improvements

| ID | Description | Files Modified | Lines Changed |
|----|------------|---------------|---------------|
| R16 | BLS refinement model reuse | `bls.py` | ~50 (refactored `refine_bls_candidates()` to call `_prepare_bls_inputs()` once) |
| R17 | Configurable deduplication filter | `bls.py`, `config.py`, `pipeline.py`, `cli.py`, presets | ~15 (new `BLSConfig.unique_period_separation_fraction`, default 0.05) |
| R18 | Limb darkening correction | `parameters.py`, `config.py`, `pipeline.py`, `cli.py`, presets | ~20 (conditional formula `sqrt(depth / (1 - u1/3 - u2/6))`) |
| R19 | Configurable smoothing window | `plotting.py`, `config.py`, `pipeline.py`, `cli.py`, presets | ~10 (new `PlotConfig.smoothing_window`, default 5) |
| R20 | TIC stellar density lookup | `parameters.py`, `config.py`, `pipeline.py`, `cli.py`, presets | ~40 (new `_lookup_tic_density()` with timeout and fallback) |

## Artifacts Produced

### Workflow Documents
| File | Description |
|------|------------|
| `01-spec.md` | Specification with 11 FRs, 5 NFRs, 9 ACs |
| `02-analysis.md` | Feasibility assessment, 5 risks, dependency map |
| `03-architecture.md` | Component design, interface contracts, 4 design decisions |
| `04-implementation-plan.md` | 7-step plan with dependency graph |
| `05-test-spec.md` | 14 test cases across unit and edge-case categories |
| `08-review.md` | Code review with requirement verification matrix |

### Source Code Changes
| File | Changes |
|------|---------|
| `src/exohunt/config.py` | Added fields to `BLSConfig`, `ParameterConfig`, `PlotConfig`; updated `_DEFAULTS` and `resolve_runtime_config()` |
| `src/exohunt/bls.py` | Refactored `refine_bls_candidates()` for model reuse; changed dedup default to 0.05 |
| `src/exohunt/parameters.py` | Added `_lookup_tic_density()`, limb darkening correction, extended `estimate_candidate_parameters()` |
| `src/exohunt/plotting.py` | Added `smoothing_window` parameter to `save_raw_vs_prepared_plot()` |
| `src/exohunt/pipeline.py` | Wired new config fields through `_search_and_output_stage()`, `_plotting_stage()`, `fetch_and_plot()` |
| `src/exohunt/cli.py` | Passed new `RuntimeConfig` fields to `fetch_and_plot()` |
| `src/exohunt/presets/*.toml` | Added new fields to all 3 presets; `deep-search` enables `tic_density_lookup` |

### Test Code
| File | Changes |
|------|---------|
| `tests/test_p2_fixes.py` | Created: 14 tests covering all 5 improvements |
| `tests/test_p1_fixes.py` | Updated: `test_r11_parameter_config_defaults` to include new `ParameterConfig` fields |

## Test Results

- **120/120 tests pass** (0 failures, 1 pre-existing warning)
- All existing tests continue to pass (NFR-5 satisfied)
- 14 new P2-specific tests all pass

## Backward Compatibility

All changes are backward-compatible:
- New config fields have defaults in `_DEFAULTS` — existing TOML files work without modification
- `apply_limb_darkening_correction` defaults to `False` — existing radius estimates unchanged
- `tic_density_lookup` defaults to `False` — no network calls unless opted in
- `smoothing_window` defaults to `5` (reduced from hardcoded `9`) — cosmetic improvement only
