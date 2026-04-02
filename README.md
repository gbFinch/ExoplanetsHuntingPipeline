# Exohunt

![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
![CI](https://github.com/gbFinch/ExoplanetsHuntingPipeline/actions/workflows/ci.yml/badge.svg)
![License](https://img.shields.io/github/license/gbFinch/ExoplanetsHuntingPipeline)
![Status](https://img.shields.io/badge/status-experimental-orange)

Tools for ingesting, preprocessing, plotting, and transit-searching TESS light curves.

## Why Exohunt

- Built for repeatable exoplanet light-curve workflows.
- Supports single-target and resumable multi-target batch analysis.
- Produces deterministic artifacts: plots, candidate tables, diagnostics, and manifests.
- Includes built-in runtime presets for quick inspection through deeper search.

## Example Screenshots

These are illustrative examples showing the type of outputs Exohunt generates.

![Prepared light curve example](assets/screenshots/example-prepared-lightcurve.png)
![BLS diagnostics example](assets/screenshots/example-bls-diagnostics.png)

## Quick Start

### 1. Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Optional extras:

```bash
pip install -e .[plotting]   # Plotly interactive HTML plots
pip install -e .[dev]        # lint/test tooling
```

### 2. Run a target

```bash
python -m exohunt.cli run --target "TIC 261136679" --config science-default
```

### 3. Start from a config file

```bash
python -m exohunt.cli init-config --from science-default --out ./configs/myrun.toml
python -m exohunt.cli run --target "TIC 261136679" --config ./configs/myrun.toml
```

Reference: `examples/config-example-full.toml`

## Built-In Presets

- `quicklook`: fast inspection
- `science-default`: balanced, default workflow
- `deep-search`: heavier search with iterative BLS enabled (3 passes)

## Iterative BLS Planet Search

Exohunt supports iterative BLS transit search for multi-planet detection. After each BLS pass, detected transit epochs are masked and the search repeats on the residual light curve. This recovers secondary planets hidden under the primary signal's sidelobes and harmonics.

### How it works

1. Run BLS → find strongest signal
2. Mask that signal's transit epochs (set to NaN)
3. Optionally re-flatten the light curve excluding known transits
4. Repeat BLS on the residual
5. Stop when SNR drops below threshold or max iterations reached

### Enable iterative search

Create `configs/iterative.toml`:

```toml
schema_version = 1
preset = "science-default"

[bls]
iterative_masking = true
iterative_passes = 5
min_snr = 5.0
n_periods = 4000
period_max_days = 25.0
```

Or use the `deep-search` preset which has iterative BLS enabled by default.

### Systematic planet search workflow

```bash
# 1. Run batch analysis on high-value targets
python -m exohunt.cli batch \
  --targets-file .docs/targets_iterative_search.txt \
  --config ./configs/iterative.toml \
  --resume --no-cache

# 2. Collect all passed candidates into one file
python -m exohunt.collect

# 3. Cross-reference against NASA Exoplanet Archive
python -m exohunt.crossmatch

# 4. Clean up light curve cache to reclaim disk space (~1MB per target)
rm -rf outputs/cache/lightcurves
```

The collect step produces `outputs/candidates_summary.json` with all vetted candidates across every target. The crossmatch step queries the NASA Exoplanet Archive and labels each candidate as:

- **KNOWN** — matches a confirmed exoplanet period
- **HARMONIC** — matches a harmonic (0.5x, 2x, 3x, etc.) of a known planet
- **NEW** — no match found in the archive (worth manual review)

Results are saved to `outputs/candidates_crossmatched.json`.

Options:

```bash
python -m exohunt.collect --iterative-only   # only candidates from iteration >= 1
python -m exohunt.collect --all              # include failed vetting too
```

### Target lists

Pre-built target lists are generated from the ExoFOP TOI catalog — single-TOI systems (1 known planet, no eclipsing binaries) sorted by TESS sector count. The iterative BLS masks the known planet and searches for additional signals.

| File | Targets | Criteria | Est. runtime |
|------|---------|----------|-------------|
| `.docs/targets_premium.txt` | ~200 | Tmag<11, ≥10 sectors | ~3 hours |
| `.docs/targets_standard.txt` | ~1,100 | Tmag<13, ≥5 sectors | ~14 hours |
| `.docs/targets_extended.txt` | ~1,900 | Tmag<14, ≥3 sectors | ~24 hours |
| `.docs/targets_iterative_search.txt` | ~3,200 | All tiers combined | ~41 hours |

Start with premium, then expand:

```bash
# Best targets first
python -m exohunt.cli batch \
  --targets-file .docs/targets_premium.txt \
  --config ./configs/iterative.toml --resume --no-cache

# Then add more (--resume skips already-processed targets)
python -m exohunt.cli batch \
  --targets-file .docs/targets_iterative_search.txt \
  --config ./configs/iterative.toml --resume --no-cache
```

## CLI Usage

Single target:

```bash
python -m exohunt.cli run --target "TIC 261136679" --config quicklook
```

Batch mode (resumable):

```bash
python -m exohunt.cli batch --targets-file .docs/targets.txt --config science-default --resume
```

Example targets file:

```text
# One target per line. Blank lines/comments are ignored.
TIC 261136679
TIC 172900988
TIC 139270665
```

## Output Layout

Exohunt writes analysis artifacts under `outputs/`:

```text
outputs/
  cache/lightcurves/...
  <target>/
    plots/
    candidates/
    diagnostics/
    metrics/
    manifests/
  metrics/preprocessing_summary.csv
  manifests/run_manifest_index.csv
  batch/
```

Notable artifacts:

- Plots: `outputs/<target>/plots/`
- BLS candidates (CSV/JSON): `outputs/<target>/candidates/`
- Candidate diagnostics: `outputs/<target>/diagnostics/`
- Run manifests and comparison keys: `outputs/<target>/manifests/`
- Batch status reports and resumable state: `outputs/batch/`

## Candidate JSON Example

Real example source:
`outputs/tic_261136679/candidates/tic_261136679__bls_cf473890ae95.json`

Curated example file:
`examples/output-example-candidates.json`

```json
{
  "candidates": [
    {
      "rank": 1,
      "period_days": 1.5669543338043215,
      "depth_ppm": 43.98520228435891,
      "vetting_pass": false,
      "vetting_reasons": "odd_even_depth_mismatch",
      "iteration": 0
    },
    {
      "rank": 2,
      "period_days": 6.267835516128348,
      "depth_ppm": 179.90382892442165,
      "vetting_pass": true,
      "vetting_reasons": "pass",
      "iteration": 1
    }
  ]
}
```

This demonstrates an important behavior: the strongest-ranked BLS peak is not always the real planet candidate, so vetting fields should drive interpretation. The `iteration` field indicates which BLS pass found the candidate (0 = first pass, 1+ = found after masking prior signals).

## Reproducibility

Each run records:

- runtime configuration and preset metadata
- software versions
- data/config fingerprint hashes
- manifest index rows for run-to-run comparisons

## Development

Run tests:

```bash
pytest
```

Lint:

```bash
ruff check .
```

## Notes

- Python requirement: `>=3.10`
- This project is currently experimental and evolving
