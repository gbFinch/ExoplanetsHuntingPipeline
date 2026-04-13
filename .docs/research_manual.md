# Exohunt Research Manual

Step-by-step guide for running a systematic planet search with Exohunt.

---

## Overview

The workflow has 4 phases:

1. **Configure** — choose targets and search parameters
2. **Run** — batch analysis (hours to days)
3. **Monitor** — watch live candidate CSVs during the run
4. **Analyze** — review novel candidates, cross-match, validate

---

## Phase 1: Configure

### Choose a target list

Pre-built target lists are in `.docs/`. Start small, expand later:

| File | Targets | Est. runtime |
|------|:-------:|:------------:|
| `.docs/targets_premium.txt` | ~200 | ~40 hours |
| `.docs/targets_standard.txt` | ~1,100 | ~9 days |
| `.docs/targets_extended.txt` | ~1,900 | ~16 days |
| `.docs/targets_iterative_search.txt` | ~3,200 | ~27 days |

Or create your own (one TIC ID per line, `#` comments allowed):

```text
# My custom targets
TIC 261136679
TIC 355867695
```

### Choose a search config

Use the built-in `iterative-search` preset — it's configured for systematic planet hunting:

```
iterative-search:
  TLS search with stellar parameters from TIC
  Iterative masking (3 passes) to find multiple planets
  Batman subtraction of known confirmed planets
  NaN masking of TOI candidates
  Period range 0.5–25 days
  TRICERATOPS disabled (run separately on candidates)
  ~12 min per target (varies with sector count)
```

No config file needed — just pass the preset name directly:

```bash
python -m exohunt.cli batch \
  --targets-file .docs/targets_premium.txt \
  --config iterative-search \
  --resume --no-cache
```

To customize, export and edit:

```bash
python -m exohunt.cli init-config --from iterative-search --out ./configs/my_search.toml
# Edit configs/my_search.toml, then:
python -m exohunt.cli batch --targets-file targets.txt --config ./configs/my_search.toml --resume
```

### What the pipeline does for each target

1. Downloads TESS SPOC light curves from MAST
2. Preprocesses per-sector (outlier removal, flattening)
3. Stitches sectors into one light curve
4. Queries NASA archive for known planets → batman model subtraction (confirmed) or NaN masking (TOI candidates)
5. Runs TLS transit search on the residual
6. If iterative masking is on: masks found signal, repeats TLS
7. Vets each candidate (odd/even, alias, secondary eclipse, depth, centroid, TOI sub-harmonic)
8. Writes candidates, diagnostics, plots, manifests
9. Appends to live summary CSVs

---

## Phase 2: Run

### Start the batch

```bash
python -m exohunt.cli batch \
  --targets-file .docs/targets_premium.txt \
  --config iterative-search \
  --resume --no-cache \
  > outputs/search_run.log 2>&1 &
```

- `--resume` — skips already-completed targets if the run is restarted
- `--no-cache` — forces fresh light curve downloads (recommended for first run)
- `> outputs/search_run.log 2>&1 &` — runs in background, logs to file

On macOS, prevent sleep:

```bash
nohup caffeinate -dims python -m exohunt.cli batch \
  --targets-file .docs/targets_premium.txt \
  --config iterative-search \
  --resume --no-cache \
  > outputs/search_run.log 2>&1 &
echo "PID: $!"
```

### Expand to more targets

After the premium tier finishes, expand with `--resume` (skips already-done targets):

```bash
python -m exohunt.cli batch \
  --targets-file .docs/targets_iterative_search.txt \
  --config iterative-search \
  --resume --no-cache \
  > outputs/search_run_full.log 2>&1 &
```

---

## Phase 3: Monitor

### Live candidate files

During the run, two CSVs are updated in real-time:

| File | Contents |
|------|----------|
| `outputs/batch/candidates_live.csv` | All candidates from all targets (passing and failing) |
| `outputs/batch/candidates_novel.csv` | **Only passing candidates that don't match any known planet or TOI** |

The novel CSV is the one you want to watch:

```bash
# Watch for new novel candidates
tail -f outputs/batch/candidates_novel.csv

# Or grep the log for the 📡 marker
grep "📡" outputs/search_run.log
```

### Batch status

```bash
# Quick status check
cat outputs/batch/run_status.csv

# How many targets done
grep -c "success" outputs/batch/run_status.csv

# Any failures
grep "error" outputs/batch/run_status.csv
```

### Log monitoring

```bash
# Last target being processed
grep "Target:" outputs/search_run.log | tail -1

# Pre-masking activity
grep "Pre-masking:" outputs/search_run.log | tail -5

# BLS completion times
grep "BLS complete" outputs/search_run.log | tail -5
```

---

## Phase 4: Analyze

### Step 1: Review novel candidates

```bash
# View novel candidates sorted by SDE
cat outputs/batch/candidates_novel.csv | sort -t, -k5 -rn
```

Columns: `target, rank, period_days, depth_ppm, snr, duration_hours, transit_time, iteration, vetting_reasons, vetting_pass`

Key fields to check:
- `snr` — higher is more significant (>10 is strong, 7-10 is marginal)
- `depth_ppm` — transit depth; <100 ppm is very shallow, >1000 ppm is deep
- `iteration` — 0 = found in first pass, 1+ = found after masking prior signals
- `vetting_reasons` — why it passed (e.g., `odd_even_inconclusive` means too few transits to test)

### Step 2: Collect all candidates

```bash
python -m exohunt.collect
```

Produces `outputs/candidates_summary.json` with all vetted candidates across every target.

Options:
```bash
python -m exohunt.collect --iterative-only   # only candidates from iteration >= 1
python -m exohunt.collect --all              # include failed vetting too
```

### Step 3: Cross-match against NASA archive

```bash
python -m exohunt.crossmatch
```

Labels each candidate as:
- **KNOWN** — matches a confirmed exoplanet period
- **HARMONIC** — matches a harmonic (0.5×, 2×, 3×) of a known planet
- **NEW** — no match found (worth manual review)

Results: `outputs/candidates_crossmatched.json`

### Step 4: Manual review of NEW candidates

For each NEW candidate, check:

1. **Diagnostics plots** — `outputs/<target>/diagnostics/`
   - Periodogram: is the peak clean or surrounded by aliases?
   - Phase-folded light curve: does it look like a transit?

2. **Duration plausibility** — is the transit duration consistent with the period and stellar radius?

3. **Depth consistency** — is the depth consistent across sectors?

4. **ExoFOP check** — search the target on [ExoFOP](https://exofop.ipac.caltech.edu/tess/) for community notes, dispositions, or ground-based follow-up

5. **Centroid check** — `outputs/<target>/diagnostics/` centroid plots (if available)

### Step 5: TRICERATOPS validation (for promising candidates)

For candidates that survive manual review, run TRICERATOPS:

```bash
python -m exohunt.cli run \
  --target "TIC 123456789" \
  --config ./configs/validate.toml
```

With `configs/validate.toml`:
```toml
schema_version = 1
preset = "deep-search"

[bls]
search_method = "tls"
iterative_masking = true
iterative_passes = 3
period_max_days = 25.0

[parameters]
tic_density_lookup = true

[vetting]
triceratops_enabled = true
triceratops_n = 1000000
```

TRICERATOPS thresholds (Giacalone & Dressing 2020):
- FPP < 0.015 and NFPP < 0.001 → **statistically validated planet**
- FPP < 0.5 → ambiguous, needs more data
- FPP > 0.5 → likely false positive

---

## Quick Reference

### Useful commands

```bash
# Single target quick look
python -m exohunt.cli run --target "TIC 261136679" --config quicklook

# Single target full analysis
python -m exohunt.cli run --target "TIC 261136679" --config deep-search

# Batch with resume
python -m exohunt.cli batch --targets-file targets.txt --config my_search.toml --resume

# Collect results
python -m exohunt.collect

# Cross-match
python -m exohunt.crossmatch

# Clean light curve cache (reclaim disk space)
rm -rf outputs/cache/lightcurves
```

### Output structure

```
outputs/
  batch/
    candidates_live.csv      ← all candidates (live, append-mode)
    candidates_novel.csv     ← novel candidates only (live, append-mode)
    run_state.json           ← resumable batch state
    run_status.csv           ← per-target status
  <target>/
    candidates/              ← candidate JSON/CSV per target
    diagnostics/             ← periodograms, phase-folded plots
    plots/                   ← prepared light curve plots
    manifests/               ← run metadata, config hashes
  candidates_summary.json    ← collected candidates (after collect)
  candidates_crossmatched.json ← cross-matched (after crossmatch)
```

### Built-in presets

| Preset | Use case | TLS? | Iterative? | Period range |
|--------|----------|:----:|:----------:|:------------:|
| `quicklook` | Fast inspection | No (BLS) | No | 0.5–20d |
| `science-default` | Balanced analysis | Yes | No | 0.5–20d |
| `iterative-search` | **Batch planet hunting** | Yes | Yes (3 passes) | 0.5–25d |
| `deep-search` | Maximum sensitivity | Yes | Yes (3 passes) | 0.5–40d |

---

## Tips

- **Start with premium targets** — they have the best data (bright, many sectors). If the pipeline finds nothing there, it won't find anything in noisier data.
- **Clean old batch CSVs before a new run** — `rm outputs/batch/candidates_*.csv` to avoid mixing results from different runs.
- **Watch disk space** — each target produces ~1MB of artifacts. 3200 targets ≈ 3.2 GB.
- **MAST rate limits** — if you see many timeouts, the MAST server may be overloaded. The pipeline retries automatically, but very long runs may benefit from running overnight when MAST traffic is lower.
- **Iteration 0 vs 1+** — iteration 0 candidates are found after pre-masking known planets. Iteration 1+ candidates are found after additionally masking the iteration 0 signal. Multi-planet systems show up at iteration 1+.
