# Next Steps — Exohunt Follow-Up Plan

**Date:** 2026-04-20
**Context:** Follow-up actions after analyzing the 92 novel candidates from the iterative TLS batch run (see `novel-candidates-analysis-2026-04-20.md`).

---

## 1. Fix the phase-fold plot so shallow candidates are actually visible

This is the single most impactful pipeline improvement — we almost threw away a real detection (TIC 317597583 cand 2, P=4.57d, 136 ppm) because the diagnostic plot obscured it.

- Add a 5-minute binned overlay (red dots) on the zoom panel, in addition to the running average
- Add a second, tighter zoom panel (±4×duration instead of ±3×duration) with just binned points and a claimed-depth dashed line
- Autoscale the y-axis of the zoom panel to ±5× the claimed depth (not to raw scatter)
- Show empirical in-transit-vs-out-of-transit depth in the text box, next to the TLS-claimed depth (sanity check)

**Impact:** every future candidate gets vetted more reliably; we also uncover hidden signals that were misclassified as MARGINAL in the current batch.

### Detailed notes for whoever picks this up

#### Where the code lives

- File: `src/exohunt/plotting.py`
- Function that produces the plot: `save_candidate_diagnostics()` (around line 393)
- Helper for the orange running-average line: `_phase_binned_median()` at line 370
- The phasefold PNG is written at line ~508 as `{base}_phasefold.png`
- Full file-path pattern: `outputs/tic_{tic_id}/diagnostics/tic_{tic_id}__bls_{hash}__candidate_{rank:02d}_phasefold.png`

#### What the current plot does (and why it hides real signals)

The plot has two panels (full phase and zoom):

1. Raw scatter points (`markersize=0.6`, `alpha=0.22`) — dominated by photometric noise, ±2000–10000 ppm depending on target
2. A single orange "running median" line computed by `_phase_binned_median(phase_hours, flux_ppm, n_bins=120)`
3. Green box model showing the TLS-claimed depth over the transit window
4. Orange shaded transit window `±duration/2`
5. Text box with `P`, `D`, `Depth`, `SNR`, `Vetting`

The failure mode for shallow candidates is a combination of three things:

a. **Bin-width is period-dependent, not duration-dependent.** `_phase_binned_median` uses `n_bins=120` across the FULL phase range `[-P/2, +P/2]` hours. For a P=20d candidate, that is ~4h per bin — which is 2–4× the typical transit duration, so one bin smears transit and out-of-transit samples together and the running line barely dips. The bins are also computed once on the full phase range, then the same line is reused in both the full AND the zoom panel.

b. **Minimum-count threshold drops bins inside the transit.** `_phase_binned_median` skips bins with fewer than 12 points. When the transit is narrow and bins are wide, the orange line often has a gap or a single shallow point right at phase=0.

c. **Y-axis is shared between full and zoom panels** (`sharey=True` at line 438), and is autoscaled to the raw-scatter range. A 136 ppm dip in a ±2000 ppm window is ~3% of the panel height and essentially invisible.

#### What we actually observed (concrete example)

Target: `TIC 317597583`, candidate 2, P=4.5738d, claimed depth=136 ppm, SNR=18.0, FAP=8e-5, 54 observed transits.

Default plot: the orange running-average line is nearly flat at phase=0 with a tiny wiggle; the user correctly said "I hardly see anything."

Custom replot (independently re-downloaded lightkurve, pre-masked the known TOI-1630.01 at P=12.0557d using NaN masking ±1.5×D, phase-folded on the candidate period, binned at 5-min resolution, zoomed y-axis to ±600 ppm):

- Empirical depth measured as `median(in_transit) - median(out_of_transit)` = **-143.7 ppm** (matches the pipeline's 136 ppm within 5%)
- The binned points inside the ±1h transit window sit consistently around -130 to -200 ppm
- Out-of-transit binned points scatter symmetrically around 0 ppm with ±80 ppm spread
- Transit is obvious and unambiguous when plotted this way

Saved sample of the working plot: regenerate via the inline script below (the repro script is not in the repo yet).

#### Concrete fix proposal

Modify `save_candidate_diagnostics` in `src/exohunt/plotting.py`:

1. In `_phase_binned_median`, switch from fixed `n_bins=120` across the full period to a physical bin width — roughly `bin_width_hours = max(5/60, candidate.duration_hours / 8)` (5 minutes minimum, or 1/8 of the transit duration, whichever is larger). This guarantees at least ~8 bins inside the transit window.
2. For the ZOOM panel specifically, recompute the bins on only the subset of points within the zoom range (so bins are denser there).
3. Add a finer bin overlay on the zoom panel at 5-min resolution as red dots/squares (keep the 120-bin running line as well for visual context).
4. Remove `sharey=True` from the `subplots()` call so the zoom panel can have its own y-range.
5. Set zoom y-limits to `±max(5 * candidate.depth_ppm, 3 * mad(binned_oot))` so shallow candidates fill the panel.
6. Add an empirical-depth line in the zoom panel: compute `median(flux at |phase| < D/4) - median(flux at D < |phase| < 3D)` and draw it as a dashed horizontal line; also print it in the text box next to the TLS-claimed depth as a sanity-check.
7. Change the transit window `axvspan` color to something higher-contrast (current `#f4a261` at `alpha=0.25` is hard to see on the zoom panel).

Do not break existing artifacts — change only the plotting code and regenerate via a re-run (or add a `replot` CLI subcommand, see Step 2).

#### How to validate the fix

Run the patched plotting on these three targets and eyeball the output:

- `TIC 317597583` cand 2 — shallow real signal (136 ppm), currently looks invisible; should look clearly like a transit
- `TIC 287196418` cand 2 — eclipsing binary (1112 ppm, sinusoidal); should still look obviously binary
- `TIC 280865159` cand 3 — NO_DIP noise detection; should still look flat

If all three render correctly, regenerate all 92 diagnostics (Step 2).

#### Quick repro snippet for validating the fix

```python
# Run from repo root in the activated venv.
# Reproduces the custom replot used to validate TIC 317597583 cand 2.
import warnings; warnings.filterwarnings("ignore")
import numpy as np, matplotlib.pyplot as plt, lightkurve as lk

sr = lk.search_lightcurve("TIC 317597583", author="SPOC", exptime=120)
lc_coll = sr.download_all()
lcs = []
for lc in lc_coll:
    lc = lc.remove_nans().normalize().flatten(window_length=801).remove_outliers(sigma=5.0)
    lcs.append(lc)
lc = lk.LightCurveCollection(lcs).stitch()

# Pre-mask known TOI-1630.01 (P=12.0557d, D=1.959h)
t = lc.time.value
f = lc.flux.value.copy()
t0 = 2458738.9131 - 2457000.0
P_known, D_known = 12.0557353, 1.959 / 24.0
half = 0.5 * D_known * 1.5
n_start = int(np.floor((np.nanmin(t) - t0) / P_known)) - 1
n_end = int(np.ceil((np.nanmax(t) - t0) / P_known)) + 1
for n in range(n_start, n_end + 1):
    f[np.abs(t - (t0 + n * P_known)) < half] = np.nan

# Phase-fold on candidate 2 (P=4.5738d, T0=1765.4676 BTJD)
P, t0_cand = 4.573822493534628, 1765.4675780391747
phase_h = (((t - t0_cand + 0.5*P) % P) - 0.5*P) * 24.0
m = np.isfinite(f) & (np.abs(phase_h) < 4.0)
phase_h, f = phase_h[m], f[m]

# 5-min bins
edges = np.arange(-4, 4.01, 5/60)
ctr = 0.5 * (edges[:-1] + edges[1:])
med = np.array([np.nanmedian(f[(phase_h >= edges[i]) & (phase_h < edges[i+1])]) * 1e6 for i in range(len(edges)-1)])

# Empirical depth sanity-check
in_t = np.abs(phase_h) < 0.5
oot = (np.abs(phase_h) > 2) & (np.abs(phase_h) < 4)
print(f"Empirical depth: {(np.nanmedian(f[in_t]) - np.nanmedian(f[oot])) * 1e6:.1f} ppm  (expect ~136)")
```

## 2. Re-vet the existing 92 candidates with the improved plot

Before spending compute on new targets, re-run just the plotting step on the existing outputs and re-review the ~35 MARGINAL-tier candidates. Suspicion is that a handful of them (especially the shallow ones on quiet stars) are also real but were visually under-sold.

Cheapest way: write a small script that re-plots each candidate from the cached JSON ephemeris without redoing TLS.

## 3. Enable TRICERATOPS for automated false-positive probability

The config has `triceratops_enabled = false`. Enabling it gives every candidate a quantitative FPP (false positive probability) that accounts for:

- Background eclipsing binaries in the aperture
- Hierarchical triple star scenarios
- Brown dwarf transits

FPP < 0.01 is the community standard for "statistically validated planet." This converts subjective TIER rankings into objective probabilities.

## 4. Prioritize TIC 317597583 cand 2 for deeper vetting

For the top novel candidate (P=4.57d, 136 ppm, SNR=18, orbiting TOI-1630 confirmed planet host):

- Pull the TESS Data Validation (DV) report from MAST for this target (SPOC may have already flagged secondary signals)
- Run a centroid-offset analysis — is the transit happening on the target star or on a nearby contaminant?
- Check Gaia DR3 for nearby stars within the 21" TESS pixel that could dilute or mimic the signal
- Search the literature for the TOI-1630 discovery paper — if they did multi-planet fits or ruled out additional signals, that's highly relevant

## 5. Re-run the batch with longer period and iterative passes

Current config: `period_max_days = 25.0`, `iterative_passes = 3`, `min_snr = 7.0`.

- Extend `period_max_days` to 40–50d to catch habitable-zone candidates around cooler stars (currently excluded)
- Increase `iterative_passes` to 5 — the current batch shows all 92 novel candidates from iteration 0, meaning subsequent passes produced nothing that passed vetting. Either the vetting is too strict for masked residuals, or iterations 1–2 are firing but the results are being filtered out. Worth investigating.
- Consider `min_snr = 6.0` with stricter vetting — more detections, fewer that survive

## 6. Investigate why iterations 1+ produced no novel candidates

From the candidates CSV, `iteration: {'0': 92}` — zero candidates from iterative passes. Possibilities:

- The mask-and-reflatten step is killing too many cadences
- Vetting thresholds (especially `min_transit_count = 2`) are cutting iteration-1 candidates because mask gaps reduce observable transits
- Nothing survived the mask (possible for quiet stars)

Quick diagnostic: grep `outputs/batch/candidates_live.csv` for `iteration > 0` to see what iteration 1–2 found before vetting killed it.

## 7. Add multi-sector coherence check

A real planet must produce consistent transits across all sectors. Split the phase-fold by sector and confirm the dip appears in each one. If it only shows up in 1–2 sectors, it's likely a systematic.

This catches:

- Dust on optics / sector-specific noise
- Stellar rotation beating with sampling cadence
- Background variables entering/leaving the aperture

## 8. Push the most promising candidates toward ExoFOP

For the top 3 (TIC 317597583 cand 2, TIC 260004324 cands 1+2, TIC 167656187 cand 1):

- Create TFOP (TESS Follow-up Observing Program) working group proposals
- Request ground-based photometric seasonal-detection observations
- Request SG1 seeing-limited photometry if not already done for the host

These are free to submit and the community does the follow-up. Even if the signal turns out to be a false positive, the analysis gets added to ExoFOP for the next person.

---

## Suggested order of operations

### This week

1. Fix phase-fold plotting (Step 1)
2. Re-vet existing candidates (Step 2)

### Next 1–2 weeks

3. Enable TRICERATOPS (Step 3)
4. Deep-dive on cand 2 of TIC 317597583 (Step 4)
5. Diagnose why iteration 0 is the only iteration producing candidates (Step 6)

### Next 1–2 months

6. Re-run batch with expanded parameters (Step 5)
7. Multi-sector coherence (Step 7)
8. ExoFOP submissions (Step 8)
