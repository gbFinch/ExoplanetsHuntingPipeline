# AGENTS.md — Exohunt

Starting point for AI agents navigating the `exoplanets-hunting-pipeline` repo (package: `exohunt`). Focuses on repo-specific conventions and discoverability; do not re-derive standard Python / build tooling defaults from here.

For deeper detail, use the knowledge base in `.agents/summary/` (start with `.agents/summary/index.md`).

## Table of contents

- [What Exohunt is](#what-exohunt-is)
- [Repo layout at a glance](#repo-layout-at-a-glance)
- [Subsystem map](#subsystem-map)
- [Key entry points](#key-entry-points)
- [Configuration model (important)](#configuration-model-important)
- [Reproducibility and on-disk conventions](#reproducibility-and-on-disk-conventions)
- [Non-obvious things to know](#non-obvious-things-to-know)
- [Tooling discoverable from config](#tooling-discoverable-from-config)
- [Knowledge base pointers](#knowledge-base-pointers)
- [Custom Instructions](#custom-instructions)

## What Exohunt is

Pure-Python pipeline for TESS light-curve ingest → preprocess → BLS/TLS transit search → vetting → reproducible artifacts. Single-target and resumable multi-target batch workflows. Filesystem is the store; no services, no DB.

## Repo layout at a glance

```text
exoplanets-hunting-pipeline/
├── src/exohunt/              # the package (pipeline, cli, config, presets, bls, tls, ...)
├── tests/                    # pytest suite (testpaths configured in pyproject.toml)
├── configs/                  # user-authored TOML configs (e.g. iterative.toml)
├── examples/                 # config-example-full.toml + output-example-candidates.json
├── .docs/                    # research manual + pre-built target lists (targets_*.txt)
├── docs/                     # dated research notes (novel-candidates-analysis-*.md)
├── scripts/                  # one-off validation/debug scripts, NOT part of package API
├── outputs/                  # runtime artifacts (gitignored) — cache, per-target, batch, summaries
├── .agents/summary/          # agent knowledge base (this doc is consolidated from it)
├── .ai-orchestrator/         # internal agent definitions, not loaded at runtime
├── .github/workflows/ci.yml  # ruff + pytest on Py 3.10 and 3.11
├── .pre-commit-config.yaml   # ruff + ruff-format
└── pyproject.toml            # setuptools, src/ layout, exohunt/presets as package_data
```

## Subsystem map

- **CLI** (`src/exohunt/cli.py`) — argparse subcommands `run`, `batch`, `init-config` plus a legacy flat-flag mode (still supported, emits deprecation warning).
- **Orchestration** (`src/exohunt/pipeline.py`) — public entry points `fetch_and_plot(...)` and `run_batch_analysis(...)`. Internally split into `_ingest_stage`, `_search_and_output_stage`, `_plotting_stage`, `_manifest_stage`. Owns the canonical column schemas (`_CANDIDATE_COLUMNS`, `_PREPROCESSING_SUMMARY_COLUMNS`, `_MANIFEST_INDEX_COLUMNS`, `_BATCH_STATUS_COLUMNS`).
- **Config** (`src/exohunt/config.py` + `src/exohunt/presets/*.toml`) — frozen dataclasses (`RuntimeConfig` and children), deep-merge `defaults ← preset ← file ← cli_overrides`, deprecated-key rejection with actionable messages. Loader is schema-versioned (`schema_version = 1`).
- **Search** — `exohunt.bls` (`astropy.timeseries.BoxLeastSquares` + iterative masking) and `exohunt.tls` (`transitleastsquares` wrapper that returns `BLSCandidate` for interface parity). Both use `exohunt.stellar` and `exohunt.ephemeris` for stellar params and known-transit pre-masking.
- **Vet / validate** — `exohunt.vetting` (5 automated checks → `CandidateVettingResult`), `exohunt.parameters` (Rp/Rs + duration plausibility → `CandidateParameterEstimate`), `exohunt.validation` (TRICERATOPS FPP/NFPP, optional), `exohunt.centroid` (TPF shift check, optional).
- **I/O helpers** — `exohunt.ingest`, `exohunt.cache` (hash-keyed prepared cache), `exohunt.preprocess`, `exohunt.plotting`, `exohunt.progress`, `exohunt.models`.
- **Aggregation tools** — `exohunt.collect`, `exohunt.crossmatch`, `exohunt.comparison`. Each is runnable as `python -m exohunt.<module>` and operates on the artifact tree under `outputs/`.

## Key entry points

- `python -m exohunt.cli run --target "TIC ..." --config <preset|path>`
- `python -m exohunt.cli batch --targets-file <path> --config <preset|path> [--resume] [--no-cache]`
- `python -m exohunt.cli init-config --from <preset> --out <path>`
- `python -m exohunt.collect [--iterative-only|--all] [-o PATH]`
- `python -m exohunt.crossmatch [SUMMARY_PATH] [-o PATH]`
- `python -m exohunt.comparison [--metrics-csv ...] [--cache-dir ...] [--report-path ...]`

No `[project.scripts]` is declared in `pyproject.toml` — always invoke via `python -m exohunt.<module>`.

## Configuration model (important)

- **Builtin presets** (in `src/exohunt/presets/`): `quicklook`, `science-default` (default), `deep-search`, `iterative-search`. Loaded via `importlib.resources`; auto-discovered by dropping new `.toml` files into that directory.
- **Three independent two-track modes** (each `"stitched" | "per-sector"`): `preprocess.mode`, `plot.mode`, `bls.mode`.
  - `preprocess.mode = "global"` is accepted as a legacy alias for `"stitched"` (warning logged).
  - `plot.mode` and `bls.mode` reject `"global"` outright.
  - `plot.mode = "per-sector"` requires `preprocess.mode = "per-sector"` (validated in `config.py`).
- **Search backend**: `bls.search_method ∈ {"bls", "tls"}`. TLS path pulls stellar params (`exohunt.stellar`) and pre-masks known planets / TOIs (`exohunt.ephemeris`) before running.
- **Removed / deprecated keys** raise `ConfigValidationError` with a migration message: `ingest.sectors`, `plot.time_start_btjd`, `plot.time_end_btjd`, `plot.sectors`, `cache_dir`, `max_download_files`. Do not reintroduce these.
- `examples/config-example-full.toml` is the canonical annotated schema reference — read it before designing a new config.

## Reproducibility and on-disk conventions

Per run, the pipeline computes:

- `config_hash` — 16-hex SHA-1 of the flat config payload.
- `data_fingerprint_hash` — 16-hex SHA-1 of the data summary (n points, time range, mode, source).
- `comparison_key = sha1({target, config_hash, data_fingerprint_hash})[:16]` — stable grouping key for "same run with the same data".
- `manifest_run_key = sha1({comparison_key, run_started_utc})[:16]` — per-run uniqueness key, used in manifest filenames.

Artifacts:

- `outputs/<slug>/plots/`, `candidates/`, `diagnostics/`, `metrics/`, `manifests/` — per-target, where `<slug>` is a lowercased, `_`-separated safe-slug of the target string (e.g. `"TIC 261136679"` → `tic_261136679`).
- `outputs/manifests/run_manifest_index.csv` — global append-only index of all runs.
- `outputs/metrics/preprocessing_summary.csv` — global append-only preprocessing quality metrics.
- `outputs/batch/run_state.json` + `run_status.csv`/`.json` + `candidates_live.csv` + `candidates_novel.csv` — batch bookkeeping and live observability.
- `outputs/candidates_summary.json` — produced by `exohunt.collect`.
- `outputs/candidates_crossmatched.json` — produced by `exohunt.crossmatch`.

Light-curve cache (`outputs/cache/lightcurves/`) uses hash-keyed prepared filenames (`<slug>__prep_<hashkey>.npz`) so different preprocessing settings never collide. `--no-cache` suppresses cache writes but still reads.

## Non-obvious things to know

- **Canonical candidate type is `BLSCandidate`** (`exohunt.bls`). Both BLS and TLS code paths produce lists of this type; TLS stores SDE in the `power`/`snr` fields for interface parity.
- **Network work is intentionally fault-tolerant**. NASA archive TAP calls retry with exponential backoff; TIC stellar queries wrap a thread-pool timeout with solar fallback. TRICERATOPS's internal TRILEGAL call is monkey-patched to a no-op at import time in `exohunt.validation` because that upstream web service is often unavailable; affected background false-positive scenarios are dropped gracefully.
- **`_append_live_candidates` writes the batch CSVs** as each target finishes. Monitor `outputs/batch/candidates_novel.csv` during long runs.
- **`run_batch_analysis` isolates per-target failures** and retries transient network errors up to 3 times before recording `status=error` and moving on. Re-running with `--resume` skips already-completed targets.
- **TUI subpackage** (`src/exohunt/tui/`) exists only as compiled `.pyc` under `__pycache__/`. Treat as inactive unless the `.py` source is restored. The CLI does not depend on it.
- **macOS / TLS**: `exohunt.tls` forces multiprocessing start method to `fork` at import time (POSIX only). `.docs/research_manual.md` recommends `nohup caffeinate -dims ...` for long overnight batches.
- **Python 3.10 subtlety**: `exohunt.config` falls back from `tomllib` to `tomli`, but `tomli` is not declared in `pyproject.toml`. On clean 3.10 installs, confirm `tomli` is importable (it typically comes in via `pytest`). Python 3.11+ is unaffected.
- **Scripts directory (`scripts/`)** is intentionally outside the package. Don't import from it and don't treat it as public API.
- **`BLSCandidate.iteration`** encodes which iterative pass found the signal (0 = first pass, 1+ = found after masking prior detections). Multi-planet systems typically show up at iteration ≥ 1.

## Tooling discoverable from config

- **Lint**: `ruff` pinned via `.pre-commit-config.yaml` (`v0.6.9`). CI runs `ruff check .`.
- **Format**: `ruff-format` via pre-commit (not run in CI).
- **Tests**: `pytest` with `testpaths = ["tests"]` (`pyproject.toml`).
- **CI matrix**: Python 3.10 and 3.11 (`.github/workflows/ci.yml`).
- **Pre-commit**: optional for contributors; not enforced in CI.
- **Dev extras**: `pip install -e .[dev]` → `ruff`, `pytest`, `pytest-cov`, `mypy`, `pre-commit`. `mypy` has no config checked in and is not used in CI.
- **Plotting extras**: `pip install -e .[plotting]` enables Plotly HTML output (`plot.interactive_html = true`).

## Knowledge base pointers

For anything beyond this quick reference:

- `.agents/summary/index.md` — routing index for the rest of the knowledge base.
- `.agents/summary/codebase_info.md` — identity + directory map + module roster.
- `.agents/summary/architecture.md` — staged pipeline, batch orchestration, reproducibility, caching, service boundaries.
- `.agents/summary/components.md` — per-module responsibilities and function surfaces.
- `.agents/summary/interfaces.md` — CLI, Python APIs, TOML schema, on-disk contracts, external services.
- `.agents/summary/data_models.md` — all dataclasses, CSV columns, JSON schemas.
- `.agents/summary/workflows.md` — runbooks, control flow diagrams, failure playbook.
- `.agents/summary/dependencies.md` — runtime/optional deps, network calls, dev tooling.
- `.agents/summary/review_notes.md` — known gaps and caveats in the knowledge base itself.

## Custom Instructions

<!-- This section is maintained by developers and agents during day-to-day work.
     It is NOT auto-generated by codebase-summary and MUST be preserved during refreshes.
     Add project-specific conventions, gotchas, and workflow requirements here. -->
