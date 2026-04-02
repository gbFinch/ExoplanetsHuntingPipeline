# Project: Secondary Planet Transit Search

## Type
research

## Description
Analyze the current Exohunt pipeline and determine what changes are needed to detect secondary (additional) transiting planets in systems where a dominant transit signal masks weaker companions.

The current pipeline runs a single-pass BLS search (`src/exohunt/bls.py:run_bls_search`) that returns the top N candidates ranked by power, then vets them (`src/exohunt/vetting.py:vet_bls_candidates`). It has no mechanism to subtract a detected transit and re-search the residuals for additional signals. Secondary planets with shallower depths or periods near harmonics of the primary are effectively invisible.

Research should cover:

1. **Iterative BLS with transit subtraction** — after identifying the strongest candidate, mask or subtract its model transits from the light curve and re-run BLS on the residual. Determine how many iterations are practical, what stopping criteria to use (SNR floor, power threshold, false-alarm probability), and how to propagate uncertainty from each subtraction step.

2. **Transit model for subtraction** — the current pipeline uses box-shaped BLS fits only. Evaluate whether a simple box mask is sufficient for subtraction or whether a trapezoidal/limb-darkened model is needed to avoid leaving residual structure that creates false secondary detections.

3. **Harmonic and alias disambiguation** — `_unique_period` in `bls.py` uses a 2% fractional separation filter and `_alias_harmonic_reference_rank` in `vetting.py` checks ratios (0.5, 2.0, 1/3, 3.0). Research whether these are adequate when a secondary planet's true period is near a harmonic of the primary, and what additional checks (e.g., phase-folded depth consistency at the candidate period vs. the harmonic) would reduce false positives.

4. **Preprocessing impact** — the flatten step (`preprocess.py:prepare_lightcurve`, Savitzky-Golay via lightkurve `.flatten()`) can suppress shallow transits if the window is too narrow relative to the transit duration. Research optimal flatten window strategies for multi-planet searches (e.g., iterative flattening after masking known transits).

5. **Detection limits and injection-recovery** — define a framework for estimating the minimum detectable secondary depth as a function of primary depth, period ratio, and data baseline. Consider whether a simple injection-recovery test module should be part of the deliverable.

6. **Config and output schema changes** — identify what new configuration knobs (e.g., `bls.iterative_passes`, `bls.subtraction_model`, `bls.snr_floor`) and output artifacts (per-iteration candidate lists, residual light curves, multi-planet candidate groupings) are needed.

7. **Other modern methods that might improve the pipeline** - think, research and recommend other technologies, algorithms, methods that might improve the current pipeline for secondary planets search.

8. **Analyze current pipeline and analyze if there are any issues with it** - think, analyze the current state of pipeline and check if there are any issues, like wrong filtering or others. List them as P0 in the final list.

## Background
The pipeline currently finds the strongest periodic transit signal well, but real multi-planet systems (e.g., TRAPPIST-1, Kepler-90) have multiple transiting planets with very different depths. The single-pass BLS approach buries secondary signals in the wings and sidelobes of the dominant peak. This is the most impactful capability gap for science use of Exohunt.
ßß
## Constraints
- Must remain compatible with the existing `RuntimeConfig` / preset system (`src/exohunt/config.py`).
- Python 3.10+

## Existing Code/System
- Repository: `/Users/gbasin/Development/exoplanets-hunting-pipeline`
- BLS search: `src/exohunt/bls.py` — `run_bls_search()`, `refine_bls_candidates()`, `compute_bls_periodogram()`
- Vetting: `src/exohunt/vetting.py` — `vet_bls_candidates()`, `_alias_harmonic_reference_rank()`
- Preprocessing: `src/exohunt/preprocess.py` — `prepare_lightcurve()`
- Parameter estimation: `src/exohunt/parameters.py` — `estimate_candidate_parameters()`
- Pipeline orchestration: `src/exohunt/pipeline.py`
- Config system: `src/exohunt/config.py` — `RuntimeConfig`, `BLSConfig`
- Presets: `src/exohunt/presets/` (quicklook, science-default, deep-search)
- No existing transit subtraction, residual computation, or iterative search logic exists anywhere in the codebase.

## Success Criteria
- A written research document that for each topic above provides: current state analysis, recommended approach with rationale, alternative approaches considered, key risks, and estimated implementation complexity.
- Concrete recommendations for new/modified functions, config fields, and output artifacts.
- Identification of any algorithmic edge cases (e.g., overlapping transits, near-integer period ratios, very shallow secondaries near the noise floor).

## Human Gates
research

## Additional Notes
- The `top_n` BLS parameter (default 5) already returns multiple peaks, but these are from the same single BLS run — they are not independent detections on residual data.
- The `refine_bls_candidates` function does a dense local re-search but only around the original peaks, not on subtracted data.
- Consider referencing established literature: Kovács et al. (2002) BLS, Hippke & Heller (2019) TLS as a BLS alternative, and the Kepler pipeline's iterative planet search (TCE approach).
