# Config Concept (PRD): Current CLI Parameter State

This document captures the **current** CLI surface area as implemented in:
- `src/exohunt/cli.py`
- `src/exohunt/comparison.py`

## 1) Main Pipeline CLI (`python -m exohunt.cli`)

### Command shape
- Single-target mode:
  - `python -m exohunt.cli --target "TIC 261136679" [options]`
- Batch mode:
  - `python -m exohunt.cli --batch-targets-file .docs/targets.txt [options]`

If `--batch-targets-file` is set, the CLI ignores `--target` and runs batch processing.

### Parameter reference

| Flag | Type | Default | Allowed values | Description | Notes / interactions |
|---|---|---:|---|---|---|
| `--target` | string | `TIC 261136679` | any target string | Target identifier for single-target mode. | Ignored when `--batch-targets-file` is provided. |
| `--batch-targets-file` | path string | `None` | existing newline-delimited file | Enables batch mode; one target per line. | Blank lines and `#` comments are ignored. |
| `--batch-resume` | boolean flag | `False` | flag | Resume batch by skipping targets already completed in state file. | Only meaningful in batch mode. |
| `--batch-state-path` | path string | `None` | any writable path | Path to batch resumable state JSON. | If not set, defaults under `outputs/batch/`. |
| `--batch-status-path` | path string | `None` | any writable path | Path to batch status CSV (`.json` sidecar also written). | If not set, defaults under `outputs/batch/`. |
| `--cache-dir` | path string | `outputs/cache/lightcurves` | any writable directory | Root cache directory for raw/prepared light curves and metrics cache. | Used in both single and batch modes. |
| `--refresh-cache` | boolean flag | `False` | flag | Ignore caches and re-download/recompute pipeline inputs. | Applies to raw/prepared cache usage. |
| `--outlier-sigma` | float | `5.0` | float | Sigma threshold for preprocessing outlier rejection. | Affects prepared cache key and run manifest config. |
| `--flatten-window-length` | int | `401` | int | Window length for flatten detrending. | Affects preprocessing behavior and cache key. |
| `--max-download-files` | int or None | `None` | positive int expected | Cap on number of light-curve files downloaded before stitching. | `None` means no cap. |
| `--no-flatten` | boolean flag | `False` | flag | Disable flattening in preprocessing. | Equivalent to `apply_flatten=False`. |
| `--preprocess-mode` | enum string | `per-sector` | `global`, `per-sector` | Preprocessing strategy for caching/processing flow. | `per-sector` uses segment caches and metadata. |
| `--sectors` | comma-separated string | `None` | e.g. `14,15,16` | Optional sector filter for ingest. | Parsed as integers. |
| `--authors` | comma-separated string | `SPOC` | e.g. `SPOC` | Optional author filter for ingest. | Parsed case-insensitive (`upper()`). |
| `--interactive-html` | boolean flag | `False` | flag | Also save interactive Plotly HTML plot. | Only produced when plot generation is enabled. |
| `--interactive-max-points` | int | `200000` | int | Max points per trace in interactive plot downsampling. | Used only with `--interactive-html`. |
| `--plot-time-start` | float or None | `None` | BTJD float | Optional plot x-axis start (BTJD). | Plot generation turns on if start or end is set. |
| `--plot-time-end` | float or None | `None` | BTJD float | Optional plot x-axis end (BTJD). | Plot generation turns on if start or end is set. |
| `--plot-sectors` | comma-separated string | `None` | e.g. `14,15` | Optional sector subset for plotting. | Requires `--preprocess-mode per-sector`, otherwise runtime error. |
| `--no-bls` | boolean flag | `False` | flag | Disable BLS transit search. | Internally mapped to `run_bls=False`. |
| `--bls-period-min-days` | float | `0.5` | float | Minimum trial period for BLS search (days). | Used in both stitched and per-sector BLS. |
| `--bls-period-max-days` | float | `20.0` | float | Maximum trial period for BLS search (days). | Used in both stitched and per-sector BLS. |
| `--bls-duration-min-hours` | float | `0.5` | float | Minimum trial transit duration for BLS (hours). | Used in both stitched and per-sector BLS. |
| `--bls-duration-max-hours` | float | `10.0` | float | Maximum trial transit duration for BLS (hours). | Used in both stitched and per-sector BLS. |
| `--bls-n-periods` | int | `2000` | int | Number of period grid samples for BLS. | Higher values increase runtime and search density. |
| `--bls-n-durations` | int | `12` | int | Number of duration grid samples for BLS. | Higher values increase runtime and search density. |
| `--bls-top-n` | int | `5` | int | Number of top-ranked BLS candidates to return/log. | Controls candidate count per BLS run context. |
| `--bls-mode` | enum string | `stitched` | `stitched`, `per-sector` | Run BLS on stitched prepared curve or per prepared segment. | `per-sector` only actually splits when prepared segments are available; otherwise falls back to stitched with warning. |

### Behavior and coupling (current implementation)

- Plot generation is **opt-in**:
  - A plot is generated only if at least one of:
    - `--plot-time-start`
    - `--plot-time-end`
    - `--plot-sectors`
- `--plot-sectors` requires per-segment metadata:
  - Runtime error unless `--preprocess-mode per-sector`.
- `--authors` defaults to `SPOC`:
  - So current default ingest is already author-filtered.
- Batch mode execution:
  - Uses the same processing parameters as single-target mode and applies them per target.
  - With `--batch-resume`, completed targets in state are skipped.

---

## 2) Comparison Report CLI (`python -m exohunt.comparison`)

This is a second CLI entrypoint currently used to build preprocessing-comparison reports from metrics.

| Flag | Type | Default | Description |
|---|---|---:|---|
| `--metrics-csv` | path string | `outputs/metrics/preprocessing_summary.csv` | Input metrics summary CSV. |
| `--cache-dir` | path string | `outputs/cache/lightcurves` | Cache directory used to infer cadence/span metadata. |
| `--report-path` | path string | `outputs/reports/preprocessing-method-comparison.md` | Output markdown report path. |

---

## 3) Current UX Observations (Baseline for redesign)

- The primary pipeline CLI exposes many knobs in one flat command.
- Parameters mix several concerns in a single interface:
  - target selection
  - batch orchestration
  - cache strategy
  - preprocessing controls
  - plotting controls
  - BLS search controls
- Several parameters are mode-coupled but not structurally separated (e.g. batch-only flags, plot-sector + preprocess-mode dependency).

This baseline can be used as the “Current State” section for upcoming usability-focused redesign work.

---

## 4) Proposed Direction: Preset + User Config Workflow

### Goal
Replace long flag-heavy invocation with a config-first model:
- built-in preset configs (for fast start)
- user-defined config files (for reproducibility and customization)
- optional one-off CLI overrides

Target UX:

```bash
exohunt run --target "TIC 261136679" --config quicklook
```

### CLI contract (draft)

- Run with built-in preset:
  - `exohunt run --target "TIC 261136679" --config quicklook`
- Run with user config file:
  - `exohunt run --target "TIC 261136679" --config ./configs/myrun.toml`
- Create starter config from preset:
  - `exohunt init-config --from quicklook --out ./configs/myrun.toml`
- Show resolved config without executing:
  - `exohunt run --target "TIC 261136679" --config quicklook --dry-run`
- Optional single-key override:
  - `exohunt run --target "TIC 261136679" --config quicklook --set bls.top_n=10`

Batch is a separate command, not a config toggle:
- `exohunt batch --targets-file .docs/targets.txt --config science-default`

Compatibility path:
- Keep `python -m exohunt.cli` temporarily, but route it through the same config resolver.

### Built-in presets (draft)

- `quicklook`
  - Fast sanity run, low compute.
- `science-default`
  - Recommended default for most analyses.
- `deep-search`
  - Denser BLS search, slower runtime, higher sensitivity.

Preset policy:
- Presets are versioned and shipped with the package.
- Manifest records both preset name and preset version/hash.

### Built-in preset definitions (v1 draft)

These are the proposed built-ins users can reference via `--config <name>`.

| Key | `quicklook` | `science-default` | `deep-search` |
|---|---:|---:|---:|
| `io.refresh_cache` | `false` | `false` | `false` |
| `ingest.authors` | `["SPOC"]` | `["SPOC"]` | `["SPOC"]` |
| `preprocess.enabled` | `true` | `true` | `true` |
| `preprocess.mode` | `per-sector` | `per-sector` | `per-sector` |
| `preprocess.outlier_sigma` | `6.0` | `5.0` | `4.0` |
| `preprocess.flatten_window_length` | `201` | `401` | `801` |
| `preprocess.flatten` | `true` | `true` | `true` |
| `plot.enabled` | `true` | `false` | `false` |
| `plot.mode` | `stitched` | `stitched` | `stitched` |
| `plot.interactive_html` | `false` | `false` | `true` |
| `plot.interactive_max_points` | `120000` | `200000` | `300000` |
| `bls.enabled` | `true` | `true` | `true` |
| `bls.mode` | `stitched` | `stitched` | `stitched` |
| `bls.period_min_days` | `0.8` | `0.5` | `0.3` |
| `bls.period_max_days` | `12.0` | `20.0` | `40.0` |
| `bls.duration_min_hours` | `0.75` | `0.5` | `0.5` |
| `bls.duration_max_hours` | `8.0` | `10.0` | `12.0` |
| `bls.n_periods` | `1200` | `2000` | `8000` |
| `bls.n_durations` | `10` | `12` | `20` |
| `bls.top_n` | `3` | `5` | `10` |

Batch note:
- There is no batch-specific config preset.
- `batch` is just orchestration over targets and reuses normal run configs per iteration.
- Example:
  - `exohunt batch --targets-file .docs/targets.txt --config science-default`

### Full TOML drafts for built-ins (v1)

#### `quicklook`

```toml
schema_version = 1                                      # 1
preset = "quicklook"                                    # quicklook|science-default|deep-search

[io]
refresh_cache = false                                   # true|false

[ingest]
authors = ["SPOC"]                                      # [<author>, ...]

[preprocess]
enabled = true                                          # true|false
mode = "per-sector"                                     # stitched|per-sector
outlier_sigma = 6.0                                     # float>0
flatten_window_length = 201                             # odd int>0
flatten = true                                          # true|false

[plot]
enabled = true                                          # true|false
mode = "stitched"                                       # stitched|per-sector
interactive_html = false                                # true|false
interactive_max_points = 120000                         # int>=1000

[bls]
enabled = true                                          # true|false
mode = "stitched"                                       # stitched|per-sector
period_min_days = 0.8                                   # float>0, <period_max_days
period_max_days = 12.0                                  # float>period_min_days
duration_min_hours = 0.75                               # float>0, <duration_max_hours
duration_max_hours = 8.0                                # float>duration_min_hours
n_periods = 1200                                        # int>=1
n_durations = 10                                        # int>=1
top_n = 3                                               # int>=1
```

#### `science-default`

```toml
schema_version = 1                                      # 1
preset = "science-default"                              # quicklook|science-default|deep-search

[io]
refresh_cache = false                                   # true|false

[ingest]
authors = ["SPOC"]                                      # [<author>, ...]

[preprocess]
enabled = true                                          # true|false
mode = "per-sector"                                     # stitched|per-sector
outlier_sigma = 5.0                                     # float>0
flatten_window_length = 401                             # odd int>0
flatten = true                                          # true|false

[plot]
enabled = false                                         # true|false
mode = "stitched"                                       # stitched|per-sector
interactive_html = false                                # true|false
interactive_max_points = 200000                         # int>=1000

[bls]
enabled = true                                          # true|false
mode = "stitched"                                       # stitched|per-sector
period_min_days = 0.5                                   # float>0, <period_max_days
period_max_days = 20.0                                  # float>period_min_days
duration_min_hours = 0.5                                # float>0, <duration_max_hours
duration_max_hours = 10.0                               # float>duration_min_hours
n_periods = 2000                                        # int>=1
n_durations = 12                                        # int>=1
top_n = 5                                               # int>=1
```

#### `deep-search`

```toml
schema_version = 1                                      # 1
preset = "deep-search"                                  # quicklook|science-default|deep-search

[io]
refresh_cache = false                                   # true|false

[ingest]
authors = ["SPOC"]                                      # [<author>, ...]

[preprocess]
enabled = true                                          # true|false
mode = "per-sector"                                     # stitched|per-sector
outlier_sigma = 4.0                                     # float>0
flatten_window_length = 801                             # odd int>0
flatten = true                                          # true|false

[plot]
enabled = false                                         # true|false
mode = "stitched"                                       # stitched|per-sector
interactive_html = true                                 # true|false
interactive_max_points = 300000                         # int>=1000

[bls]
enabled = true                                          # true|false
mode = "stitched"                                       # stitched|per-sector
period_min_days = 0.3                                   # float>0, <period_max_days
period_max_days = 40.0                                  # float>period_min_days
duration_min_hours = 0.5                                # float>0, <duration_max_hours
duration_max_hours = 12.0                               # float>duration_min_hours
n_periods = 8000                                        # int>=1
n_durations = 20                                        # int>=1
top_n = 10                                              # int>=1
```

### Resolution model (draft)

Final run config is produced by deterministic layering:

1. schema defaults
2. preset values (if `--config` is a preset name)
3. user config file values (if `--config` is a file path)
4. CLI explicit flags (`--target`, `--dry-run`, `--set`, and transition-era flags if supported)

Rules:
- Later layers override earlier layers.
- Unknown keys are hard errors.
- Invalid types are hard errors.
- Mode-coupling checks run after merge (e.g. `plot.mode="per-sector"` requires `preprocess.mode = "per-sector"`).
- `target` is not part of config; it is required CLI input for `run`.
- `batch` is not part of config; it is a separate command with its own required CLI inputs.

### Config schema (TOML draft)

```toml
schema_version = 1                                      # 1
preset = "quicklook"                                    # quicklook|science-default|deep-search

[io]
refresh_cache = false                                   # true|false

[ingest]
authors = ["SPOC"]                                      # [<author>, ...]

[preprocess]
enabled = true                                          # true|false
mode = "per-sector"                                     # stitched|per-sector
outlier_sigma = 5.0                                     # float>0
flatten_window_length = 401                             # odd int>0
flatten = true                                          # true|false

[plot]
enabled = false                                         # true|false
mode = "stitched"                                       # stitched|per-sector
interactive_html = false                                # true|false
interactive_max_points = 200000                         # int>=1000

[bls]
enabled = true                                          # true|false
mode = "stitched"                                       # stitched|per-sector
period_min_days = 0.5                                   # float>0, <period_max_days
period_max_days = 20.0                                  # float>period_min_days
duration_min_hours = 0.5                                # float>0, <duration_max_hours
duration_max_hours = 10.0                               # float>duration_min_hours
n_periods = 2000                                        # int>=1
n_durations = 12                                        # int>=1
top_n = 5                                               # int>=1
```

### Mapping from current flags to config keys (draft)

| Current flag | New key |
|---|---|
| `--target` | CLI-only (not in config) |
| `--batch-targets-file` | `exohunt batch --targets-file` (command arg) |
| `--batch-resume` | `exohunt batch --resume` (command arg) |
| `--batch-state-path` | `exohunt batch --state-path` (command arg) |
| `--batch-status-path` | `exohunt batch --status-path` (command arg) |
| `--cache-dir` | removed (fixed internal path: `outputs/cache/lightcurves`) |
| `--refresh-cache` | `io.refresh_cache` |
| `--max-download-files` | removed (always unlimited downloads) |
| `--sectors` | removed (always ingest all sectors) |
| `--authors` | `ingest.authors` |
| `--preprocess-mode` | `preprocess.mode` (`global` maps to `stitched`) |
| `--outlier-sigma` | `preprocess.outlier_sigma` |
| `--flatten-window-length` | `preprocess.flatten_window_length` |
| `--no-flatten` | `preprocess.flatten=false` |
| `--plot-time-start` | removed |
| `--plot-time-end` | removed |
| `--plot-sectors` | removed |
| (new) | `plot.mode` |
| `--interactive-html` | `plot.interactive_html` |
| `--interactive-max-points` | `plot.interactive_max_points` |
| `--no-bls` | `bls.enabled=false` |
| `--bls-mode` | `bls.mode` |
| `--bls-period-min-days` | `bls.period_min_days` |
| `--bls-period-max-days` | `bls.period_max_days` |
| `--bls-duration-min-hours` | `bls.duration_min_hours` |
| `--bls-duration-max-hours` | `bls.duration_max_hours` |
| `--bls-n-periods` | `bls.n_periods` |
| `--bls-n-durations` | `bls.n_durations` |
| `--bls-top-n` | `bls.top_n` |

### Validation rules (draft, minimum set)

- `run` command requires `--target`.
- `batch` command requires `--targets-file`.
- `preprocess.enabled` must be `true` or `false`.
- `preprocess.mode` must be `stitched` or `per-sector`.
- `bls.mode` must be `stitched` or `per-sector`.
- `plot.mode` must be `stitched` or `per-sector`.
- `preprocess.flatten_window_length` must be positive odd integer.
- `preprocess.outlier_sigma` must be `> 0`.
- If `plot.mode = "per-sector"`, require `preprocess.mode = "per-sector"`.
- `bls.period_min_days < bls.period_max_days`.
- `bls.duration_min_hours < bls.duration_max_hours`.
- `bls.n_periods >= 1`, `bls.n_durations >= 1`, `bls.top_n >= 1`.
- `plot.interactive_max_points >= 1000` (sane lower bound).

### Transition plan (draft)

1. Add config loader + schema validator + resolver (no behavior change yet).
2. Add `exohunt run --target ... --config ...` and map resolved config into existing pipeline calls.
3. Add `exohunt batch --targets-file ... --config ...` as separate command.
4. Add `init-config` for scaffold generation from built-in presets.
5. Deprecate most direct low-level flags (keep a minimal compatibility set temporarily).
6. Update docs/examples to config-first usage.

---

## 5) Parameter Refactoring Chapter (Start)

### Refactor 01: Remove ingest sector filtering

Decision:
- Remove sector selection from ingest configuration and CLI.
- Ingest always downloads and processes all available sectors.

Rationale:
- Sector filtering at ingest is a high-complexity knob for most users.
- It introduces hidden completeness tradeoffs and frequent misconfiguration.
- Full-ingest defaults are safer for discovery workflows.

Scope changes:
- Remove legacy `--sectors` from user-facing run/batch CLI.
- Remove `ingest.sectors` from config schema.
- Keep plotting independent from ingest (see Refactor 02 plot mode changes).
- Keep internal per-sector data structures and `preprocess.mode=per-sector` behavior.

Migration notes:
- Existing commands/configs using ingest sectors should fail with a clear message:
  - `"ingest sector filtering has been removed; exohunt now ingests all sectors."`

Open follow-up:
- Decide whether a future advanced mode should allow explicit exclusion lists for operational constraints (not scientific default).

### Refactor 02: Simplify plot controls

Decision:
- Remove plot-time window parameters and plot-sector selection parameters from config/CLI.
- Introduce a single plotting assembly mode:
  - `plot.mode = "stitched" | "per-sector"`

Behavior:
- `plot.mode = "stitched"`:
  - Generate one stitched plot file.
- `plot.mode = "per-sector"`:
  - Generate one plot file per sector.

Scope changes:
- Remove legacy `--plot-time-start`, `--plot-time-end`, and `--plot-sectors`.
- Remove `plot.time_start_btjd`, `plot.time_end_btjd`, and `plot.sectors` from schema.
- Add `--plot-mode` (or config-only key `plot.mode`) with values `stitched` / `per-sector`.

Rationale:
- Time-window/sector selection is advanced tuning that complicates the default UX.
- Plot output mode is the user decision that matters most for normal workflows.
- Per-sector output still preserves sector-level inspection without extra filters.

Migration notes:
- Existing commands/configs using removed plot parameters should fail with a clear message:
  - `"plot time-window and sector filters have been removed; use plot.mode=stitched or plot.mode=per-sector."`
