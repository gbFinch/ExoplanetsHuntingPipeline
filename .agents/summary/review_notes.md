# Review Notes — Exohunt Documentation

Consistency and completeness review of the generated docs in `.agents/summary/`.

## Method

- Cross-checked module-level claims against the actual source in `src/exohunt/`.
- Verified CLI subcommands, defaults, and removed-key messages against `src/exohunt/cli.py` and `src/exohunt/config.py`.
- Verified preset list, CSV column lists, and manifest schema against `src/exohunt/pipeline.py` and `src/exohunt/presets/`.
- Spot-checked module function surfaces via grep against `src/exohunt/`.

## Consistency findings

### Resolved

- **"5-stage pipeline" (README) vs 4 code stages (`_ingest_stage`, `_search_and_output_stage`, `_plotting_stage`, `_manifest_stage`).** Called out explicitly in `architecture.md` and `workflows.md`: preprocess lives inside `_ingest_stage`, vetting inside `_search_and_output_stage`. This narrative vs code mismatch was the most likely source of confusion.
- **`preprocess.mode = "global"`** is accepted and remapped to `"stitched"` with a warning, but `plot.mode` and `bls.mode` reject `global`. Documented in both `interfaces.md` and `architecture.md`.
- **Cross-field constraint** `plot.mode = "per-sector"` requires `preprocess.mode = "per-sector"`. Present in `src/exohunt/config.py:609` and mentioned in `examples/config-example-full.toml`. Captured indirectly in `interfaces.md`; could be called out more prominently.
- **TUI subpackage** present only as `.pyc` under `__pycache__/`. Explicitly flagged in `codebase_info.md` and `components.md`.

### Pending / verify before use

- **`pandas` usage**: declared runtime dep, but the package's only direct reliance appears to be in the manifest version map. It is likely pulled in transitively by `lightkurve` anyway. Documented honestly in `dependencies.md`; if you rely on this for optimization (e.g. trimming deps), re-verify with `grep -rn "import pandas\|from pandas" src/exohunt`.
- **`tomli` fallback on Python 3.10**: `exohunt.config` falls back to `tomli` when `tomllib` is unavailable, but `tomli` is not declared in `pyproject.toml`. This works in practice because `pytest` (and some other ecosystem installs) bring `tomli` transitively, and CI has only the dev extras active. Worth confirming on a clean Python 3.10 wheel install.
- **Schema version coverage**: all docs assume `schema_version = 1`. If the schema ever bumps, `codebase_info.md`, `interfaces.md`, and `data_models.md` must be updated together.
- **Reproducibility hash widths**: `config_hash` and `data_fingerprint_hash` are truncated to 16 hex chars (`sha1[:16]`) in `pipeline._hash_payload`. Documented in `architecture.md`. Treat as content-addressed but not collision-proof.

## Completeness findings

### Areas with solid coverage

- CLI surface (`exohunt.cli` + `.collect` + `.crossmatch` + `.comparison`).
- Configuration schema (every section, every default, removed keys with migration text).
- Pipeline stages and their responsibilities.
- On-disk artifact layout and CSV/JSON schemas.
- External service boundaries (MAST, NASA TAP, TIC, TRILEGAL short-circuit).

### Areas with lighter coverage (possible follow-up)

1. **TUI subpackage**: documented as "compiled-only" and effectively inactive. If source is restored (or a separate repo owns it), add a components entry.
2. **`scripts/`**: listed but individual scripts not described. They are one-off validation / debug helpers (`m1_validate.py`, `p0_validate.py`, `tls_inspect.py`, etc.) and intentionally outside the package API. Document only if they become part of a formal workflow.
3. **`docs/` free-form notes** (`next-steps-*.md`, `novel-candidates-analysis-*.md`): date-stamped research logs, not normative documentation. Referenced in `codebase_info.md` but not summarized.
4. **`.ai-orchestrator/`**: internal agent definitions; not part of the runtime package. Not inventoried in depth; add if a future workflow depends on it.
5. **Transit-mask math specifics**: `_build_transit_mask` padding semantics (`transit_mask_padding_factor` relative to duration) are summarized; the exact window is `transit_mask_padding_factor * duration_days` around each epoch. If an agent proposes changes here, re-read `exohunt.bls._build_transit_mask` directly.
6. **Vetting "duty-cycle" adjustment**: the inconclusive path for odd/even depth uses a duty-cycle-based estimate of "real" transits per parity. Described in `components.md` and `data_models.md` at the level of "what it does"; if a user asks to tune it, read `vet_bls_candidates` for the specific formula (`_duty_cycle * transit_count_estimate / 2` with `_min_parity_transits = 5`).
7. **`subtraction_model`**: only `"box_mask"` is documented here because that is all the codebase currently uses (pipeline-level usage confirmed). If new subtraction models are added, update `interfaces.md`.
8. **Volatile metrics**: intentionally omitted across all docs (no line counts, no file sizes, no target counts). Target list counts are summarized from README qualitatively ("~200", "~1,100", etc.) and only where they help navigation.

## Language / language-support coverage

- This is a pure-Python project. No C/C++/Rust/TypeScript/Go tooling exists; no language-support gaps to flag.
- Lint/format/test are all native Python tools (`ruff`, `pytest`) so doc coverage of language tooling is complete.

## Recommendations

- **Before running agents against this knowledge base**: verify `tomli` is importable on the target Python interpreter if running on 3.10.
- **When adding a new preset**: drop the `.toml` into `src/exohunt/presets/` and regenerate the preset list if anything referenced by name changes. No doc regeneration needed unless the preset's semantics change defaults that appear in `interfaces.md` or `data_models.md`.
- **When adding a new vetting check**: update `components.md` (vetting), `data_models.md` (`CandidateVettingResult` fields), `interfaces.md` (candidate JSON schema), and `workflows.md` (vetting flow). The candidate CSV column list in `pipeline._CANDIDATE_COLUMNS` is authoritative — keep it in sync.
- **Before a schema v2**: refresh `interfaces.md` (section 3), `data_models.md` (config dataclasses), and `codebase_info.md` (project identity) together.
- **Long-term refresh cadence**: re-run the `codebase-summary` SOP after any change to pipeline stage boundaries, CLI subcommands, or on-disk artifact schemas. Day-to-day conventions belong in the `Custom Instructions` section of `AGENTS.md` and are preserved across refreshes.
