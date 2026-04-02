---
agent: spec
sequence: 1
references: []
summary: "Specification for iterative BLS transit search with box-mask subtraction and iterative flattening in Exohunt. Defines requirements for multi-planet detection via iterative periodogram search, transit masking, cross-iteration deduplication, and re-flattening with masked transits. All new behavior is gated behind existing and new config flags that default to preserving current single-pass behavior."
---

## Overview

Exohunt currently performs a single-pass Box Least Squares (BLS) periodogram search, returning the top N peaks from one search. In multi-planet systems, secondary planets with shallower transit depths are buried in sidelobes and spectral leakage of the dominant signal. This specification defines an iterative BLS search that subtracts detected transits via box masking, optionally re-flattens the light curve with known transits excluded from the baseline fit, and repeats the search to recover additional planet candidates. The feature targets TESS 2-minute and 30-minute cadence data and follows the Kepler TCE iterative search heritage (Jenkins et al. 2010).

## Functional Requirements

- **FR-1**: The system MUST provide a function `run_iterative_bls_search()` that accepts a light curve, a `BLSConfig`, and an optional `PreprocessConfig`, and returns a list of `BLSCandidate` objects annotated with iteration number.
- **FR-2**: `run_iterative_bls_search()` MUST call the existing `run_bls_search()` on each iteration, passing the current (possibly masked) light curve.
- **FR-3**: After each iteration, the system MUST build a transit mask for each candidate selected for subtraction. The mask MUST set to NaN all points where `|time - (transit_time + cycle * period)| < 0.5 * duration * transit_mask_padding_factor` for every integer cycle within the time range.
- **FR-4**: The system MUST stop iterating when either (a) the best candidate's SNR is below `bls.min_snr` (the SNR floor), or (b) the number of completed iterations equals `bls.iterative_passes`.
- **FR-5**: The system MUST apply a cross-iteration uniqueness filter: a new candidate is rejected if its period is within 1% of any previously accepted candidate's period from any prior iteration.
- **FR-6**: When `preprocess.iterative_flatten` is `True`, the system MUST re-flatten the light curve between BLS iterations using a cumulative transit mask that excludes all previously detected transit epochs from the Savitzky-Golay baseline fit.
- **FR-7**: The `prepare_lightcurve()` function MUST accept an optional `transit_mask` boolean array parameter. When provided, points where `transit_mask` is `True` MUST be excluded from the flattening fit but retained in the output light curve.
- **FR-8**: `BLSConfig` MUST include the following new fields: `iterative_passes` (int, default 1), `subtraction_model` (str, default "box_mask"), `iterative_top_n` (int, default 1), `transit_mask_padding_factor` (float, default 1.5).
- **FR-9**: `PreprocessConfig` MUST include the following new fields: `iterative_flatten` (bool, default False), `transit_mask_padding_factor` (float, default 1.5).
- **FR-10**: The existing `BLSConfig.iterative_masking` boolean MUST serve as the enable flag. When `iterative_masking` is `False`, the pipeline MUST call `run_bls_search()` directly (current behavior). When `True`, the pipeline MUST call `run_iterative_bls_search()`.
- **FR-11**: Each `BLSCandidate` MUST include an `iteration` field (int, 0-indexed) indicating which BLS pass produced it.
- **FR-12**: The pipeline MUST write per-iteration candidate artifact files named `<target>__bls_iter_<N>_<hash>.json` where N is the iteration number.
- **FR-13**: The pipeline MUST produce a combined multi-iteration candidate JSON file containing all candidates across iterations with iteration metadata.
- **FR-14**: The `_DEFAULTS` dictionary and all preset TOML files MUST include default values for all new config fields.
- **FR-15**: The `fetch_and_plot()` function MUST pass the `bls_iterative_masking` parameter through to `_search_and_output_stage()` to activate iterative BLS when configured.
- **FR-16**: The `_search_and_output_stage()` function MUST dispatch to `run_iterative_bls_search()` when `iterative_masking` is `True` in the resolved config.

## Non-Functional Requirements

- **NFR-1**: Setting `iterative_passes=1` with `iterative_masking=True` MUST produce output identical to the current `run_bls_search()` single-pass behavior (same candidates, same ordering, same fields except the added `iteration=0` field).
- **NFR-2**: Setting `iterative_masking=False` (the default) MUST produce output byte-identical to the current pipeline output (no new fields, no behavioral change).
- **NFR-3**: Each additional BLS iteration on a typical TESS light curve (~18,000 points) MUST complete in under 10 seconds.
- **NFR-4**: No new third-party dependencies MUST be introduced. Only existing astropy BLS, numpy, and lightkurve APIs are permitted.
- **NFR-5**: The implementation MUST be compatible with Python 3.10+.
- **NFR-6**: All existing tests MUST pass without modification after the changes.

## Acceptance Criteria

- **AC-1** (FR-1, FR-2, FR-4): Given a synthetic light curve containing two injected transit signals with SNR > 7, when `run_iterative_bls_search()` is called with `iterative_passes=3` and `min_snr=7.0`, then the returned list contains at least 2 candidates from different iterations.
- **AC-2** (FR-3): Given a candidate with period=2.0d, transit_time=100.0, duration=0.1d, and padding_factor=1.5, when the transit mask is computed over a time array spanning 100 days, then all points within `0.5 * 0.1 * 1.5 = 0.075` days of each transit epoch are set to NaN.
- **AC-3** (FR-5): Given a first-iteration candidate with period=5.0d, when a second-iteration candidate has period=5.04d (within 1%), then the second candidate is rejected by the cross-iteration uniqueness filter.
- **AC-4** (FR-6, FR-7): Given a light curve with `iterative_flatten=True`, when re-flattening occurs between iterations, then the flattening baseline fit excludes points marked in the cumulative transit mask.
- **AC-5** (NFR-1): Given `iterative_masking=True` and `iterative_passes=1`, when `run_iterative_bls_search()` is called, then the output candidates (excluding the `iteration` field) match the output of `run_bls_search()` on the same input.
- **AC-6** (NFR-2): Given `iterative_masking=False`, when the pipeline runs, then no iterative BLS code path is executed and output is identical to the current pipeline.
- **AC-7** (FR-8, FR-9, FR-14): Given a fresh config resolution with no user overrides, then `iterative_passes=1`, `subtraction_model="box_mask"`, `iterative_top_n=1`, `bls.transit_mask_padding_factor=1.5`, `preprocess.iterative_flatten=False`, and `preprocess.transit_mask_padding_factor=1.5`.
- **AC-8** (FR-11, FR-12): Given a 3-iteration run producing candidates, then each candidate JSON includes an `iteration` field, and separate per-iteration artifact files exist.
- **AC-9** (NFR-6): Given the full existing test suite, when `pytest` is run after implementation, then all tests pass with zero failures.

## Scope

- `run_iterative_bls_search()` function in `bls.py`
- Transit mask computation (box-mask model)
- Cross-iteration uniqueness filter (1% period separation)
- `iteration` field on `BLSCandidate`
- `transit_mask` parameter on `prepare_lightcurve()`
- Re-flattening between iterations using cumulative transit mask
- New config fields on `BLSConfig` and `PreprocessConfig`
- Default values in `_DEFAULTS` and all three preset TOML files
- Pipeline wiring in `_search_and_output_stage()` and `fetch_and_plot()`
- Per-iteration and combined candidate artifact output

## Non-Goals

- **Model-based transit subtraction** (e.g., trapezoidal or Mandel-Agol model subtraction): deferred to a future iteration. Only box masking (set to NaN) is in scope.
- **Per-sector iterative BLS mode**: stitched mode is the priority. Per-sector support is deferred.
- **Automatic validation against known multi-planet systems** (TOI-178, TOI-700): manual validation only; no automated regression test against real TESS data.
- **Interactive plotting of iterative results**: existing plotting infrastructure is unchanged.
- **Changes to vetting logic**: vetting runs on the combined candidate list as-is.
- **Parallelization of BLS iterations**: iterations are inherently sequential.

## Assumptions

- The existing `run_bls_search()` function is correct and stable. Iterative BLS wraps it without modifying its internals. **(Low risk)**
- lightkurve's `.flatten(mask=...)` parameter accepts a boolean array and excludes masked points from the Savitzky-Golay fit. **(Medium risk — needs verification against lightkurve API)**
- The existing `BLSCandidate` dataclass can be extended with an `iteration` field without breaking serialization or downstream consumers. **(Low risk)**
- Setting in-transit points to NaN is sufficient for box-mask subtraction; astropy BLS handles NaN values gracefully. **(Medium risk — needs verification)**
- The 1% period separation threshold for cross-iteration uniqueness is sufficient to prevent re-detection without rejecting genuinely distinct signals. **(Low risk — standard practice)**

## Open Questions

None identified. The context document is comprehensive and all design decisions are specified. The medium-risk assumptions (lightkurve flatten mask API, astropy BLS NaN handling) can be verified during implementation without blocking specification.
