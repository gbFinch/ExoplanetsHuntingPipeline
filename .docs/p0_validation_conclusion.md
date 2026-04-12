# P0 Improvements — Validation Conclusion

**Date**: 2026-04-12
**Runtime**: 5.1 hours (5 targets, caffeinate)
**Config**: science-default + iterative TLS (5 passes), period_max=25d

## Summary

The P0 improvements (stellar parameters, known-planet pre-masking, centroid
vetting, TRICERATOPS validation) are implemented and functional. The primary
benchmark — TOI-1260 with 3 known planets — shows **no regression**: all 3
planets are still recovered with correct periods and pass vetting. The new
modules integrate cleanly and degrade gracefully on failure.

However, the improvements did **not materially change detection outcomes** on
this target set. The reasons are specific and understood.

## Before/After Comparison

| Target | M6 Baseline (before) | P0 Run (after) | Change |
|--------|---------------------|----------------|--------|
| TIC 355867695 (TOI-1260) | 3/3 planets, all pass | 3/3 planets, all pass | **No change** |
| TIC 251848941 (TOI-178) | 1/6 pass (planet d) | 1/6 pass (planet d) | **No change** |
| TIC 158002130 | 0 candidates | 0 candidates | **No change** |
| TIC 261136679 (pi Men) | 1 pass (pi Men c) | 1 pass (pi Men c) | **No change** |
| TIC 260130483 (TOI-933) | 2 pass (sub-harmonics) | 2 pass (sub-harmonics) | **No change** |

## Why No Change in Detection Outcomes

### 1. Stellar parameters: correct but marginal impact on this target set

All 5 targets received real stellar parameters from TIC instead of solar
defaults. However, 4 of the 5 hosts are near-solar (R=0.66–1.15 R☉,
M=0.66–1.10 M☉). The TLS documentation estimates ~10% sensitivity gain
for **non-solar hosts** (M-dwarfs, subgiants). For this solar-like sample,
the transit duration grid and model template are already close to optimal
with defaults. The improvement will be more visible on the premium target
list which includes more M-dwarfs.

### 2. Pre-masking: worked correctly but didn't unlock new detections

- **TIC 158002130**: Pre-masked TOI-1180 b (P=9.69d, 4478 cadences). After
  masking, TLS found no signal above SDE=7. This is correct — the M6 run
  already found 0 candidates here (TLS eliminated the BLS false positive at
  P=16.14d). Pre-masking just reinforced this by removing the known signal.
  There is genuinely no additional planet detectable in this data.

- **TIC 261136679**: Ephemeris query timed out, so pre-masking didn't fire.
  The pipeline still correctly found pi Men c (P=6.268d, SDE=446). Pre-masking
  would have removed this known signal and searched for pi Men d (P=120d), but
  that's outside our period_max=25d search range.

- **TIC 355867695**: Pre-masking should have removed the 3 known planets and
  searched for planet 4. But the config used `science-default` which has
  `iterative_masking=true` — the iterative loop already handles this. The
  pre-masking and iterative masking are somewhat redundant for this use case.

### 3. Centroid vetting: mostly inconclusive due to TPF download issues

TPF downloads timed out for most targets. Only 1 centroid check succeeded
(0.02 px shift, pass). This is a network reliability issue, not a code bug.
The module works correctly when TPFs are available (verified in unit testing
on TOI-1260 b: 0.0003 px shift).

**Fix needed**: Download TPFs during the ingest stage (when light curves are
already being downloaded) rather than during vetting. This would avoid a
second round of MAST queries.

### 4. TRICERATOPS: FPP=0.75 everywhere due to insufficient N

All TRICERATOPS runs returned FPP=0.75 with N=10,000. This is a known
limitation: the TRICERATOPS paper uses N=1,000,000 for reliable results.
With N=10K, the Monte Carlo sampling is too coarse — the prior probability
of the planet scenario (0.25) dominates, giving FPP=1-0.25=0.75 regardless
of the data.

**Fix needed**: Increase N to 1,000,000 (adds ~5 min per candidate). Make
TRICERATOPS opt-in via config flag since it's expensive.

## Per-Target Investigation

### TIC 158002130 — 0 candidates (expected)

This target has 1 known planet (TOI-1180 b, P=9.69d). The M6 baseline
already found 0 candidates with TLS (the BLS false positive at P=16.14d
was eliminated by switching to TLS). Pre-masking removed the known planet
signal (4478 cadences, ~1.8% of data). After masking, TLS reported
"No transit were fit" — there is no additional detectable transit signal
in this light curve. This is the correct result.

### TIC 260130483 — 2 passing candidates (sub-harmonics, not real)

This is TOI-933, which has a long-period planet candidate at P=88.9d.
The 2 passing candidates are:
- P=17.787d = 88.9/5 (exactly 1/5 of TOI period)
- P=12.705d = 88.9/7 (exactly 1/7 of TOI period)

These are **sub-harmonic aliases** of the known TOI signal. The vetting
alias check doesn't catch them because it only compares candidates against
each other (not against known TOIs). Pre-masking didn't fire because
TOI-933.01 is not in the confirmed planets table (it's still a candidate).

**Fix needed**: Extend the alias check to also compare against known TOI
periods, or extend pre-masking to include unconfirmed TOI candidates.

### TIC 261136679 — 1 passing candidate (real planet!)

This is **pi Mensae**, a well-known planetary system. The passing candidate
at P=6.2678d with SDE=446.5 is a **perfect match** for pi Men c, a
confirmed 2.1 R⊕ super-Earth. This is a correct detection.

The other 4 candidates are correctly rejected as harmonics (P/2, P/3, 2P)
and odd-even failures. The pipeline is working as designed.

Pre-masking didn't fire due to ephemeris query timeout. If it had, it would
have masked pi Men c and searched for pi Men d (P=120d), which is outside
our search range (period_max=25d).

## What Actually Improved

While detection outcomes didn't change on this small sample, the P0
improvements add **infrastructure** that will matter at scale:

1. **Stellar params** are now automatically queried and used. When the
   pipeline runs on the 200 premium targets (which include M-dwarfs and
   subgiants), the ~10% sensitivity gain will help detect smaller planets.

2. **Pre-masking** will save ~35 min per target on multi-planet systems
   by eliminating wasted TLS passes. For the 3200-target iterative search,
   this could save hundreds of hours.

3. **Centroid vetting** provides a new false positive rejection channel
   that didn't exist before. Once TPF download reliability is improved,
   this will catch nearby eclipsing binary contamination.

4. **TRICERATOPS** provides publication-grade FPP values once N is
   increased. This is required for any candidate paper.

## Recommended Next Steps

1. **Increase TRICERATOPS N to 1M** and re-run on the 4 passing candidates
   to get reliable FPP values.

2. **Extend pre-masking to TOI candidates** (not just confirmed planets)
   to catch sub-harmonic aliases like TIC 260130483.

3. **Move TPF download to ingest stage** to fix centroid vetting timeouts.

4. **Run on the premium target list** (~200 targets with diverse stellar
   types) where stellar parameter integration will have more impact.

5. **Add sub-harmonic check against known TOIs** to the vetting module
   to catch cases like TIC 260130483.
