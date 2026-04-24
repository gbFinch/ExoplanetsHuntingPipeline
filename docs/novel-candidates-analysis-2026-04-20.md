# Novel Exoplanet Candidate Analysis

**Pipeline:** Exohunt iterative TLS search  
**Date:** 2026-04-20  
**Candidates reviewed:** 92 novel candidates across 52 unique targets  
**Source:** `outputs/batch/candidates_novel.csv`

---

## Summary Statistics

| Category | Count | % of 92 |
|----------|-------|---------|
| Known TOI recovered | 4 | 4% |
| Binary / false positive | 3 | 3% |
| No dip / noise | 4 | 4% |
| Tier 1 — high priority | 10 | 11% |
| Tier 2 — moderate priority | 35 | 38% |
| Tier 3 — marginal / low | 36 | 39% |

## Methodology

1. All 92 novel candidates were scored by TLS SNR, period, depth, duration, and multi-candidate system bonus.
2. All 52 unique target stars were cross-referenced against the NASA Exoplanet Archive (confirmed planets table and full TOI catalog via TAP queries).
3. Multi-candidate systems were checked for period alias / harmonic relationships.
4. Every phase-fold diagnostic plot was visually inspected using the following criteria:
   - Is there a visible dip in the running average (orange line) at phase=0?
   - Is the dip box-shaped or V-shaped (transit-like) vs sinusoidal (binary)?
   - What is the scatter range relative to the claimed depth?
   - Are there systematic patterns outside the transit window?
   - Is the transit duration physically plausible for the orbital period?
5. Candidates were ranked into tiers by estimated probability of being a real planet.

## NASA Archive Cross-Reference

- **All 52 targets have TOI entries** — none are completely unknown stars.
- 4 candidates are known TOIs recovered by the pipeline.
- 5 targets host confirmed planets at different periods, making independent novel signals more plausible.
- 2 targets have False Alarm TOI dispositions, lowering confidence in novel signals.

### Key TOI Matches

| Target | TOI | Disposition | Known Period (d) |
|--------|-----|-------------|-----------------|
| TIC 237232044 | TOI-1443 | CP | 23.54 |
| TIC 159418353 | TOI-1739 | CP | 8.30 |
| TIC 298647682 | TOI-1643 | PC | 20.08 |
| TIC 441797803 | TOI-1302 | PC | 5.67 |
| TIC 260004324 | TOI-704 | CP | (different P) |
| TIC 317597583 | TOI-1630 | CP | 12.06 |
| TIC 402898317 | TOI-2093 | CP | 53.81 |
| TIC 441765914 | TOI-2088 | CP | 124.73 |
| TIC 298663873 | TOI-2180 | CP | 260.17 |
| TIC 41173048 | TOI-2006 | FA | — |
| TIC 377191482 | TOI-1485 | FA | — |

*CP = Confirmed Planet, PC = Planet Candidate, FA = False Alarm*

## Period Alias Flags

| Target | Cand A | P_A (d) | Cand B | P_B (d) | Ratio | Depths | Verdict |
|--------|--------|---------|--------|---------|-------|--------|---------|
| TIC 179580045 | 2 | 1.51 | 5 | 3.53 | 2.33 | 738/739 ppm | Eclipsing/ellipsoidal binary |
| TIC 260130483 | 5 | 6.40 | 4 | 9.51 | 1.49 | 199/164 ppm | Likely alias pair |
| TIC 278895705 | 5 | 13.87 | 2 | 21.02 | 1.51 | 87/92 ppm | Likely alias pair |

---

## Tier 0: Known TOI Recoveries

These are not novel — the pipeline correctly recovered known signals.

| Target | Cand | P (d) | Depth (ppm) | SNR | TOI | Disposition |
|--------|------|-------|-------------|-----|-----|-------------|
| TIC 441797803 | 1 | 5.67 | 4486 | 703.4 | TOI-1302 | PC |
| TIC 237232044 | 1 | 23.54 | 598 | 279.5 | TOI-1443 | CP |
| TIC 159418353 | 1 | 8.30 | 547 | 19.4 | TOI-1739 | CP |
| TIC 298647682 | 1 | 20.08 | 556 | 12.4 | TOI-1643 | PC |

## Tier 0B: Binaries / False Positives

Confidently rejected as non-planetary.

| Target | Cand | P (d) | Depth (ppm) | SNR | Reason |
|--------|------|-------|-------------|-----|--------|
| TIC 287196418 | 2 | 1.06 | 1112 | 122.4 | D=10h / P=1.06d = 40% duty cycle, sinusoidal — eclipsing binary |
| TIC 179580045 | 2 | 1.51 | 738 | 203.1 | Sinusoidal phase-fold, ellipsoidal binary, alias pair with cand 5 |
| TIC 179580045 | 5 | 3.53 | 739 | 70.7 | Alias of cand 2, identical depth |

## Tier 0C: No Dip / Noise

Running average flat at phase=0 despite TLS detection.

| Target | Cand | P (d) | Depth (ppm) | SNR | Reason |
|--------|------|-------|-------------|-----|--------|
| TIC 280865159 | 3 | 1.10 | 130 | 13.1 | Flat running average |
| TIC 30853990 | 5 | 3.17 | 175 | 8.2 | Flat running average |
| TIC 55559618 | 2 | 0.84 | 84 | 8.7 | Sinusoidal wobble, no transit dip |
| TIC 424391516 | 5 | 18.45 | 312 | 6.5 | Flat running average |

---

## Tier 1: High Priority — Worth Follow-Up

Estimated ~15% real planet probability per candidate. Clear dips, plausible parameters, some in confirmed planet systems.

| Rank | Target | Cand | P (d) | Depth (ppm) | SNR | D (h) | Visual | Context | Notes |
|------|--------|------|-------|-------------|-----|-------|--------|---------|-------|
| 1 | TIC 317597583 | 2 | 4.57 | 136 | 18.0 | 2.0 | GOOD | TOI-1630 CP host | Clear dip, low scatter, 2nd planet plausible |
| 2 | TIC 167656187 | 1 | 1.48 | 42 | 10.9 | 5.5 | GOOD | TOI system | Very clean dip, lowest scatter of all targets |
| 3 | TIC 260004324 | 1 | 2.47 | 70 | 16.8 | 1.5 | GOOD | TOI-704 CP host | Clean dip, high SNR, 2nd planet plausible |
| 4 | TIC 260004324 | 2 | 15.98 | 131 | 12.2 | 2.5 | GOOD | TOI-704 CP host | Clear box-shaped dip, 3rd signal in system |
| 5 | TIC 357048995 | 1 | 4.69 | 96 | 17.3 | 3.5 | GOOD | TOI system | Clear dip, high SNR |
| 6 | TIC 160440924 | 1 | 11.54 | 301 | 10.3 | 1.5 | GOOD | TOI system | Clean transit dip |
| 7 | TIC 198512478 | 1 | 22.23 | 99 | 11.3 | 7.0 | GOOD | TOI system | Low scatter, clear dip (odd/even inconclusive) |
| 8 | TIC 236817690 | 1 | 14.63 | 88 | 10.2 | 5.5 | GOOD | TOI system | Low scatter ±3000 ppm, clear in running average |
| 9 | TIC 370009806 | 5 | 9.45 | 153 | 6.8 | 1.0 | GOOD | TOI system | Clear dip, low scatter |
| 10 | TIC 298663873 | 3 | 15.31 | 51 | 9.2 | 8.5 | GOOD | TOI-2180 CP host | Clear dip, very shallow but low scatter. D=8.5h long |

## Tier 2: Moderate Priority — Plausible but Uncertain

Estimated ~5–8% real planet probability. Visible dips, reasonable parameters, noisier data or less convincing shapes.

| Rank | Target | Cand | P (d) | Depth (ppm) | SNR | D (h) | Visual | Notes |
|------|--------|------|-------|-------------|-----|-------|--------|-------|
| 11 | TIC 357048995 | 2 | 17.11 | 169 | 9.4 | 3.0 | VISIBLE_DIP | 2nd signal, decent |
| 12 | TIC 160440924 | 3 | 1.85 | 130 | 7.4 | 1.0 | VISIBLE_DIP | Visible dip |
| 13 | TIC 229605578 | 3 | 14.83 | 219 | 9.6 | 2.5 | VISIBLE_DIP | Clear dip visible |
| 14 | TIC 33840683 | 1 | 16.64 | 274 | 11.0 | 1.0 | VISIBLE_DIP | Decent |
| 15 | TIC 198206613 | 1 | 18.08 | 237 | 9.8 | 1.0 | VISIBLE_DIP | Visible dip |
| 16 | TIC 198206613 | 2 | 16.03 | 129 | 10.3 | 3.0 | VISIBLE_DIP | Visible dip |
| 17 | TIC 233066156 | 1 | 15.49 | 244 | 10.1 | 1.5 | VISIBLE_DIP | Visible in zoom |
| 18 | TIC 198458010 | 1 | 11.80 | 85 | 9.9 | 4.0 | VISIBLE_DIP | Visible dip |
| 19 | TIC 424388628 | 1 | 18.42 | 94 | 10.1 | 3.5 | VISIBLE_DIP | Decent |
| 20 | TIC 259238498 | 1 | 20.15 | 170 | 10.0 | 3.0 | VISIBLE_DIP | Visible dip |
| 21 | TIC 287326127 | 2 | 19.02 | 92 | 8.3 | 7.0 | VISIBLE_DIP | Low scatter, D=7h long |
| 22 | TIC 233071822 | 2 | 16.04 | 149 | 7.8 | 3.5 | VISIBLE_DIP | Visible dip |
| 23 | TIC 233071822 | 4 | 22.21 | 191 | 7.7 | 3.0 | VISIBLE_DIP | Decent |
| 24 | TIC 272782368 | 1 | 24.29 | 444 | 7.8 | 1.5 | VISIBLE_DIP | Visible dip |
| 25 | TIC 272782368 | 3 | 18.60 | 226 | 8.9 | 4.5 | VISIBLE_DIP | Visible dip |
| 26 | TIC 299945285 | 2 | 19.15 | 131 | 8.6 | 1.5 | VISIBLE_DIP | Moderate |
| 27 | TIC 402898317 | 2 | 24.67 | 214 | 9.7 | 3.5 | VISIBLE_DIP | TOI-2093 CP host, 2nd planet plausible |
| 28 | TIC 198512478 | 2 | 16.60 | 86 | 10.7 | 5.5 | VISIBLE_DIP | Decent |
| 29 | TIC 165527918 | 3 | 22.88 | 422 | 7.7 | 0.5 | VISIBLE_DIP | Visible dip |
| 30 | TIC 165554103 | 5 | 2.18 | 69 | 7.9 | 1.0 | VISIBLE_DIP | Small dip visible |
| 31 | TIC 33840683 | 2 | 3.13 | 106 | 7.7 | 1.0 | VISIBLE_DIP | Moderate |
| 32 | TIC 382045742 | 4 | 8.98 | 188 | 8.1 | 1.5 | VISIBLE_DIP | Moderate |
| 33 | TIC 55559618 | 4 | 12.59 | 202 | 7.1 | 1.0 | VISIBLE_DIP | Moderate |
| 34 | TIC 259238498 | 5 | 23.51 | 297 | 8.6 | 1.0 | VISIBLE_DIP | Moderate |
| 35 | TIC 370009806 | 3 | 7.93 | 187 | 6.7 | 0.5 | VISIBLE_DIP | Low scatter, decent |
| 36 | TIC 224596152 | 2 | 18.11 | 153 | 8.6 | 2.0 | VISIBLE_DIP | Visible in zoom |
| 37 | TIC 219776325 | 1 | 22.24 | 227 | 9.2 | 5.0 | VISIBLE_DIP | Visible but noisy |
| 38 | TIC 255685030 | 1 | 13.92 | 294 | 6.3 | 3.0 | VISIBLE_DIP | Moderate |
| 39 | TIC 38571020 | 4 | 21.58 | 194 | 7.8 | 1.0 | VISIBLE_DIP | Moderate |
| 40 | TIC 424391516 | 1 | 24.49 | 269 | 7.9 | 1.0 | VISIBLE_DIP | Moderate |
| 41 | TIC 424391516 | 2 | 13.95 | 88 | 7.0 | 4.5 | VISIBLE_DIP | Moderate |
| 42 | TIC 198512478 | 5 | 24.58 | 132 | 7.9 | 3.5 | VISIBLE_DIP | Odd/even inconclusive |
| 43 | TIC 260130483 | 5 | 6.40 | 199 | 9.3 | 0.5 | VISIBLE_DIP | ⚠️ Alias pair with cand 4 |
| 44 | TIC 298647682 | 3 | 12.90 | 177 | 6.8 | 7.0 | VISIBLE_DIP | TOI-1643 PC host, D=7h long |
| 45 | TIC 30853990 | 2 | 8.17 | 321 | 10.9 | 0.5 | VISIBLE_DIP | Only credible signal from noisy target |

## Tier 3: Low Priority — Marginal / Suspicious

Estimated ~1–3% real planet probability. Subtle or unconvincing dips, high noise, suspicious durations, alias flags, or FA TOI hosts.

| Rank | Target | Cand | P (d) | Depth (ppm) | SNR | D (h) | Visual | Flags |
|------|--------|------|-------|-------------|-----|-------|--------|-------|
| 46 | TIC 160440924 | 2 | 16.03 | 324 | 8.1 | 1.5 | VISIBLE_DIP | — |
| 47 | TIC 350934357 | 4 | 4.33 | 92 | 8.0 | 3.0 | VISIBLE_DIP | — |
| 48 | TIC 350934357 | 3 | 2.73 | 64 | 10.6 | 5.0 | VISIBLE_DIP | D=5h suspicious for 2.73d period |
| 49 | TIC 272670038 | 1 | 16.33 | 178 | 13.2 | 4.0 | MARGINAL | Scatter ±6000 ppm |
| 50 | TIC 272670038 | 4 | 22.51 | 366 | 9.3 | 1.0 | MARGINAL | Scatter ±6000 ppm |
| 51 | TIC 272670038 | 2 | 2.10 | 102 | 8.4 | 1.0 | MARGINAL | Scatter ±6000 ppm |
| 52 | TIC 272670038 | 5 | 2.63 | 77 | 10.4 | 2.5 | MARGINAL | Scatter ±6000 ppm |
| 53 | TIC 441765914 | 2 | 16.70 | 252 | 8.2 | 1.0 | MARGINAL | TOI-2088 CP host, ±10000 ppm scatter |
| 54 | TIC 260130483 | 4 | 9.51 | 164 | 7.4 | 1.0 | VISIBLE_DIP | ⚠️ Alias pair with cand 5 |
| 55 | TIC 278895705 | 5 | 13.87 | 87 | 8.9 | 4.0 | MARGINAL | ⚠️ Alias pair with cand 2 |
| 56 | TIC 278895705 | 2 | 21.02 | 92 | 6.8 | 4.5 | MARGINAL | ⚠️ Alias pair with cand 5 |
| 57 | TIC 198458010 | 4 | 18.82 | 113 | 7.0 | 3.5 | MARGINAL | Subtle |
| 58 | TIC 154741689 | 2 | 5.96 | 128 | 8.4 | 5.5 | MARGINAL | Subtle dip |
| 59 | TIC 231077395 | 2 | 10.00 | 355 | 8.3 | 0.5 | MARGINAL | Subtle dip |
| 60 | TIC 231077395 | 3 | 4.58 | 77 | 6.5 | 4.0 | MARGINAL | Weak |
| 61 | TIC 382045742 | 2 | 0.96 | 52 | 9.7 | 2.5 | MARGINAL | D/P = 11%, borderline |
| 62 | TIC 38571020 | 1 | 3.45 | 46 | 10.8 | 3.0 | MARGINAL | Very shallow vs ±6000 ppm scatter |
| 63 | TIC 38571020 | 2 | 13.07 | 62 | 7.6 | 5.5 | MARGINAL | Subtle |
| 64 | TIC 299945285 | 1 | 3.57 | 70 | 10.5 | 1.0 | MARGINAL | Very shallow vs ±4000 ppm |
| 65 | TIC 30853990 | 4 | 3.80 | 85 | 8.0 | 2.5 | MARGINAL | Noisy ±7500 ppm |
| 66 | TIC 298600443 | 2 | 24.94 | 503 | 4.6 | 4.5 | MARGINAL | Low SNR |
| 67 | TIC 233071926 | 1 | 19.43 | 375 | 6.9 | 4.5 | MARGINAL | ±15000 ppm scatter |
| 68 | TIC 236817690 | 4 | 19.24 | 74 | 6.1 | 6.0 | MARGINAL | Weak, low SNR |
| 69 | TIC 317597583 | 3 | 24.73 | 161 | 4.9 | 8.5 | MARGINAL | D=8.5h long, low SNR, odd/even inconclusive |
| 70 | TIC 41173048 | 1 | 21.48 | 340 | 8.3 | 4.0 | MARGINAL | FA TOI host, wavy running average |
| 71 | TIC 298647682 | 5 | 7.18 | 109 | 8.0 | 8.0 | MARGINAL | D=8h = 46% of orbit — suspicious |
| 72 | TIC 177308364 | 2 | 24.64 | 274 | 5.0 | 6.5 | WEAK | Extreme outlier spikes |
| 73 | TIC 356311210 | 5 | 12.68 | 152 | 8.0 | 10.0 | MARGINAL | D=10h = 33% of orbit — likely systematic |
| 74 | TIC 150320610 | 1 | 24.74 | 399 | 9.2 | 0.5 | MARGINAL | Noisy periodograms |
| 75 | TIC 150320610 | 2 | 10.14 | 254 | 9.9 | 0.5 | MARGINAL | Noisy periodograms |
| 76 | TIC 150320610 | 3 | 22.92 | 234 | 9.9 | 2.0 | MARGINAL | Slightly clearer box dip |
| 77 | TIC 150320610 | 4 | 13.58 | 237 | 10.0 | 1.5 | MARGINAL | Slightly clearer box dip |
| 78 | TIC 377191482 | 2 | 23.16 | 167 | 8.3 | 6.5 | MARGINAL | FA TOI host, noisy |
| 79 | TIC 377191482 | 3 | 18.92 | 193 | 11.4 | 4.5 | MARGINAL | FA TOI host, noisy |
| 80 | TIC 377191482 | 4 | 13.89 | 145 | 8.0 | 5.0 | MARGINAL | FA TOI host, noisy |
| 81 | TIC 377191482 | 5 | 14.88 | 131 | 6.2 | 6.0 | MARGINAL | FA TOI host, noisy |

---

## Overall Assessment

Out of 81 truly novel candidates (excluding 4 known TOI recoveries, 3 binaries, and 4 noise detections), an estimated **3–8 may be real planets** (~4–10% yield).

### Top 3 Most Likely Real Planets

1. **TIC 317597583 cand 2** (P=4.57d) — Clearest novel signal. Known confirmed planet host (TOI-1630 at P=12.06d), SNR=18, clean box-shaped dip, physically plausible duration. A 2nd planet in this system is credible.

2. **TIC 260004324 cands 1+2** (P=2.47d, 15.98d) — Confirmed planet host (TOI-704), both show clean dips with high SNR (17, 12). Multi-planet system detection is plausible.

3. **TIC 167656187 cand 1** (P=1.48d) — Very clean dip in the lowest-scatter data of any target (~±1500 ppm). Ultra-short period planet candidate.

### Caveats

- The pipeline uses `min_snr = 7.0` which is aggressive — many detections near this threshold are noise.
- Many candidates have depths (50–200 ppm) well below the photometric scatter of their host stars (±3000–10000 ppm), relying entirely on phase-folding to beat down noise.
- All candidates are from iteration 0 (first TLS pass), meaning the iterative masking did not produce additional independent detections in this run.
- Visual inspection of phase-fold plots is subjective. Independent vetting (e.g., TRICERATOPS, centroid analysis, RV follow-up) is needed before any candidate can be considered robust.

---

## Appendix A: Run Configuration

**Config file:** `configs/iterative.toml` overriding preset `iterative-search`

### Search Parameters

```toml
[bls]
search_method = "tls"
period_min_days = 0.5
period_max_days = 25.0
duration_min_hours = 0.5
duration_max_hours = 10.0
n_periods = 4000
n_durations = 12
top_n = 5
unique_period_separation_fraction = 0.05
iterative_masking = true
iterative_passes = 3
subtraction_model = "box_mask"
iterative_top_n = 1
transit_mask_padding_factor = 1.5
min_snr = 7.0
compute_fap = false
```

### Preprocessing

```toml
[preprocess]
enabled = true
mode = "per-sector"
outlier_sigma = 5.0
flatten_window_length = 801
flatten = true
iterative_flatten = false
transit_mask_padding_factor = 1.5
```

### Ingest

```toml
[ingest]
authors = ["SPOC"]
```

### Vetting

```toml
[vetting]
min_transit_count = 2
odd_even_max_mismatch_fraction = 0.30
alias_tolerance_fraction = 0.02
secondary_eclipse_max_fraction = 0.30
depth_consistency_max_fraction = 0.50
triceratops_enabled = false
```

### Stellar Parameters

```toml
[parameters]
stellar_density_kg_m3 = 1408.0
duration_ratio_min = 0.05
duration_ratio_max = 1.8
apply_limb_darkening_correction = false
limb_darkening_u1 = 0.4
limb_darkening_u2 = 0.2
tic_density_lookup = true
```

### Plotting

```toml
[plot]
enabled = true
mode = "stitched"
interactive_html = false
```

## Appendix B: Batch Run Statistics

| Metric | Value |
|--------|-------|
| Target list | `.docs/targets_iterative_search.txt` |
| Targets in list | ~3,185 |
| Targets with novel candidates | 52 |
| Total novel candidates (passed vetting) | 92 |
| Total candidates including failed vetting | 360 |
| All candidates from iteration | 0 (first TLS pass) |
| Pipeline | Exohunt (Python ≥3.10) |
| Search engine | Transit Least Squares (TLS) |
| Crossmatch result | 94 NEW, 2 KNOWN, 2 HARMONIC |

## Appendix C: Phase-Fold Diagnostic File Pattern

```
outputs/tic_{tic_id}/diagnostics/tic_{tic_id}__bls_{hash}__candidate_{rank:02d}_phasefold.png
```

Note: File names use `bls_` prefix for historical reasons, but the actual search engine is TLS (Transit Least Squares) with stellar parameters, not BLS (Box Least Squares).
