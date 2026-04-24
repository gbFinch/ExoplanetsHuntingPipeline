# Exohunt — Knowledge Base Index (for AI assistants)

This file is the primary entry point for AI assistants working with the Exohunt (`exoplanets-hunting-pipeline`) codebase. Load this file into context first; it tells you which other file to read for any given type of question, and summarizes what is in each.

## How to use this knowledge base

1. Read this `index.md` into agent context.
2. Identify the kind of question the user is asking and follow the routing table below.
3. Load only the specific file(s) you need. Files are designed to be self-contained — you do not need to load all of them at once.
4. When a user's request spans multiple areas (e.g. "add a new vetting check and wire it through the CLI"), load `components.md` + `interfaces.md` + `data_models.md` together.

## Routing table (what to read for what kind of question)

| If the user asks about... | Read |
|---|---|
| "What is this project?" / high-level summary / structure | `codebase_info.md` |
| How components fit together / system design / data flow diagrams | `architecture.md` |
| A specific module, class, or function — where does X live? | `components.md` |
| CLI options, function signatures, config keys, artifact schemas | `interfaces.md` |
| Dataclass fields, CSV columns, JSON schemas | `data_models.md` |
| How to run a search / how the pipeline actually executes / recipes | `workflows.md` |
| Third-party libraries, network calls, dev tooling | `dependencies.md` |
| Doc gaps, assumptions, areas to double-check | `review_notes.md` |
| How to navigate the repo while editing / day-to-day conventions | `../../AGENTS.md` (repo-root consolidated) |

## Document catalog

### `codebase_info.md` — Project identity and structure map

- **When to read**: first contact with the codebase; to get a project overview.
- **Contains**: project name (`exohunt`), purpose (TESS exoplanet transit search), Python 3.10+ constraint, packaging (`setuptools`, `src/` layout, presets as package data), top-level directory tree (mermaid), full per-module roster of `src/exohunt/`, all executable entry points (`python -m exohunt.cli`, `.collect`, `.crossmatch`, `.comparison`), runtime outputs layout, CI and lint summary.
- **Key facts cached here**: TUI subpackage is compiled-only (.pyc). Outputs live in gitignored `outputs/`. `outputs/manifests/run_manifest_index.csv` is the global run index.

### `architecture.md` — System design and staged pipeline

- **When to read**: to understand how a run flows end-to-end or why the code is organized as it is.
- **Contains**: architectural style (stage-oriented pipeline, filesystem as store, no services), high-level mermaid flow, the four pipeline stages (`_ingest_stage`, `_search_and_output_stage`, `_plotting_stage`, `_manifest_stage`), batch orchestration (retries, resumable state, failure isolation, live CSV append), configuration architecture (defaults ← preset ← file ← CLI overrides, deprecated-key rejection, preset hashing), reproducibility design (`config_hash`, `data_fingerprint_hash`, `comparison_key`, `manifest_run_key`), caching architecture (hash-keyed prepared cache), external service boundaries (MAST, NASA archive TAP, TIC, TRILEGAL short-circuit), extensibility hooks.
- **Key facts cached here**: preprocess `global` mode is remapped to `stitched`; plot and BLS modes reject `global`. Each `*Config` dataclass is frozen. Network failures are retried 3× with backoff in batch mode.

### `components.md` — Module-by-module responsibilities

- **When to read**: to find where a specific responsibility or symbol lives.
- **Contains**: a component map (mermaid), then detailed notes per module:
  - CLI / orchestration: `cli`, `pipeline`, `config`, `presets/`.
  - Ingest / preprocess: `ingest`, `cache`, `preprocess`, `models`.
  - Search: `bls` (including `run_iterative_bls_search`, `_build_transit_mask`, `_cross_iteration_unique`, `_bootstrap_fap`), `tls`, `stellar`, `ephemeris`.
  - Vet / validate: `vetting`, `parameters`, `validation` (TRICERATOPS thresholds), `centroid` (TPF-based).
  - Output: `plotting`, `progress`.
  - Aggregation: `collect`, `crossmatch`, `comparison`.
- **Key facts cached here**: TLS wrapper returns `BLSCandidate` for interface parity. `validation.py` patches out TRILEGAL. `cache.py` file-naming conventions (target slug + prep hash).

### `interfaces.md` — Public surface area

- **When to read**: to write code that calls `exohunt` functions or inspect on-disk schemas.
- **Contains**: full CLI reference (`run`, `batch`, `init-config`, legacy form), aggregation CLIs, Python function signatures of every public entry point, complete TOML config schema (sections + defaults + removed keys), on-disk artifact contracts (per-target directory layout, manifest JSON schema, candidate JSON schema, batch status CSV schema), summary JSON schemas produced by `collect` and `crossmatch`, external integrations (MAST, NASA TAP, TIC, TRICERATOPS).
- **Key facts cached here**: `schema_version = 1` is the only accepted value. Deprecated keys (`ingest.sectors`, `plot.time_*_btjd`, `plot.sectors`, `cache_dir`, `max_download_files`) are rejected with migration messages.

### `data_models.md` — Concrete types

- **When to read**: to describe fields precisely, add a column, or serialize/deserialize records.
- **Contains**: a class diagram (mermaid) showing how config, candidates, vetting, parameters, validation, centroid, stellar, ephemeris, and quality metrics relate; every frozen dataclass in the codebase with its fields; CSV column specs (`_PREPROCESSING_SUMMARY_COLUMNS`, `_CANDIDATE_COLUMNS`, `_MANIFEST_INDEX_COLUMNS`, `_BATCH_STATUS_COLUMNS`); cache `.npz` record schema; segment manifest schema; summary JSON schemas for `collect` and `crossmatch`.
- **Key facts cached here**: `BLSCandidate` is the unified search result type (BLS + TLS both produce it). `CandidateVettingResult.vetting_reasons` is a `;`-joined failure-code string. `odd_even_status ∈ {pass, fail, inconclusive}`.

### `workflows.md` — Runbooks and control flow

- **When to read**: to understand what an operator would actually run, or to trace a scenario end-to-end.
- **Contains**: per-command sequence diagrams (single-target run, batch with resume, init-config + edit + re-run), iterative BLS/TLS flow (mask → re-search), vetting + parameter + validation pipeline, reproducibility flow (hashes → keys → manifests), post-run aggregation (`collect` + `crossmatch` + `comparison`), development workflow (`ruff` + `pytest` + pre-commit + CI), copy-paste ops recipes, failure / recovery playbook.
- **Key facts cached here**: the README's "5-stage" narrative (ingest, preprocess, search, vetting, plotting) maps to four code stages — preprocess lives in `_ingest_stage`, vetting lives in `_search_and_output_stage`. `rm -rf outputs/cache/lightcurves` is the standard disk-reclaim move.

### `dependencies.md` — Third-party reliance

- **When to read**: to understand what is required to run or install, what is optional, and what hits the network.
- **Contains**: declared runtime deps (`numpy`, `matplotlib`, `astropy`, `lightkurve`, `pandas`, `transitleastsquares`, `triceratops`), optional extras (`plotting`: Plotly; `dev`: ruff/pytest/mypy/pre-commit), implicit fallback deps (`tomli` on Py 3.10, `astroquery` for optional TIC density lookup), external services with retry/timeout behavior, file-system dependencies, OS / platform notes (macOS `fork` + `caffeinate`), dev tooling, security/trust boundaries, dependency lifecycle risks.
- **Key facts cached here**: `tomllib` stdlib on 3.11+, falls back to `tomli` on 3.10 (not declared in `pyproject.toml`; typically pulled transitively). No secrets are needed; all external services are public archives.

### `review_notes.md` — Known gaps and caveats (meta)

- **When to read**: to sanity-check assumptions about this documentation before relying on it for high-stakes tasks.
- **Contains**: consistency checks across the generated docs, known gaps vs the actual source, and recommendations for deeper verification.

## Quick-lookup cheat sheet

- **Entry modules**: `exohunt.cli`, `exohunt.pipeline`, `exohunt.collect`, `exohunt.crossmatch`, `exohunt.comparison`.
- **Presets**: `quicklook`, `science-default` (default), `deep-search`, `iterative-search`.
- **Two-track modes**: `preprocess.mode`, `plot.mode`, `bls.mode` each independently `stitched | per-sector`.
- **Search method**: `bls.search_method ∈ {bls, tls}`.
- **Canonical candidate type**: `exohunt.bls.BLSCandidate` (used by both BLS and TLS).
- **Batch state**: `outputs/batch/run_state.json` + `outputs/batch/run_status.{csv,json}`.
- **Global run index**: `outputs/manifests/run_manifest_index.csv`.
- **Deterministic keys**: `config_hash`, `data_fingerprint_hash`, `comparison_key`, `manifest_run_key`.

## Worked examples of useful agent queries

- "How do I add a new preset?" → `components.md` ("presets/"), `interfaces.md` (§3 TOML schema), `workflows.md` (config validation flow).
- "What columns end up in the candidates CSV?" → `data_models.md` (`_CANDIDATE_COLUMNS`).
- "Why did my batch skip most targets?" → `workflows.md` (batch flow with `--resume`), `architecture.md` (resumable state).
- "Where do I plug in a new vetting rule?" → `components.md` (`exohunt.vetting`), `data_models.md` (`CandidateVettingResult` fields), `architecture.md` (extensibility hooks), `interfaces.md` (candidate JSON schema).
- "Does the project talk to external services?" → `dependencies.md` (external services table), `architecture.md` (external service boundaries).
- "How does iterative search decide when to stop?" → `workflows.md` (iterative search flow), `components.md` (`run_iterative_bls_search`).
- "Where is the config validation?" → `components.md` (`exohunt.config`), `interfaces.md` (§3 schema).

## Maintenance notes for future refreshes

- Regenerate this file when: a new top-level module is added under `src/exohunt/`, a new CLI subcommand is introduced, or any on-disk artifact schema changes (columns, file names).
- Do not remove the "Maintenance notes" or "How to use this knowledge base" sections.
- Keep `review_notes.md` honest — it is the place to flag anything uncertain in the rest of these documents.
