---
agent: refactor-analysis
sequence: 1
references: []
summary: "The two refactoring targets are bls.py (exact duplication of 25-line setup block across run_bls_search and compute_bls_periodogram) and pipeline.py (886-line fetch_and_plot monolith handling 9 distinct responsibilities). The BLS duplication is low-risk/low-effort. The pipeline monolith is the critical structural issue — it prevents isolated testing, makes changes risky, and has high cognitive complexity from interleaved stitched/per-sector branching. Both refactorings are safe given the existing test suite of 6 files."
---

## 1. Codebase Overview

**Scope**: Two files targeted for refactoring:
- `src/exohunt/bls.py` (299 lines) — BLS transit search, periodogram computation, candidate refinement
- `src/exohunt/pipeline.py` (1656 lines) — pipeline orchestration, batch analysis, I/O helpers

**Purpose**: `bls.py` implements the Box Least Squares transit detection algorithm. `pipeline.py` orchestrates the full analysis workflow: ingest → preprocess → search → vet → output → plot → manifest.

**Boundaries**:
- `bls.py` is consumed by `pipeline.py` (3 public functions: `run_bls_search`, `compute_bls_periodogram`, `refine_bls_candidates`)
- `pipeline.py` exposes two public functions: `fetch_and_plot()` (called by `cli.py` and `run_batch_analysis()`) and `run_batch_analysis()` (called by `cli.py`)
- `pipeline.py` imports from 8 internal modules: `cache`, `bls`, `ingest`, `models`, `plotting`, `preprocess`, `progress`, `parameters`, `vetting`

**Size**: 14 source files, 6 test files. Target files: bls.py (299 lines, 6 functions), pipeline.py (1656 lines, 25 functions)

**Current State**: Functionally correct after P0+P1 fixes. Structural debt concentrated in two areas: copy-pasted BLS setup code and an untestable pipeline monolith.

## 2. Code Smells

| Smell ID | Category | Location | Description | Severity | Refactoring Technique |
|----------|----------|----------|-------------|----------|-----------------------|
| CS-1 | Long Method | pipeline.py:fetch_and_plot() (lines 771–1656) | 886-line function handling 9 distinct responsibilities: parameter setup, stitched ingest, per-sector ingest, metrics, BLS search, candidate output, plotting, manifest writing, summary logging | Critical | Extract Method (decompose into stage functions) |
| CS-2 | Duplicated Code | bls.py:run_bls_search() lines 90–120, compute_bls_periodogram() lines 210–240 | 25 lines of identical input validation, sorting, grid construction, and model instantiation | High | Extract Method (_prepare_bls_inputs) |
| CS-3 | Data Clumps | pipeline.py:fetch_and_plot() signature (lines 771–815) | 42 parameters passed individually rather than as structured config objects. Many are forwarded verbatim to downstream functions. | Medium | Introduce Parameter Object (already partially addressed by RuntimeConfig in config.py — the function receives unpacked values from it) |
| CS-4 | Long Parameter List | pipeline.py:_candidate_output_key() (lines 443–485) | 18 parameters, all individually passed, used only to build a hash | Medium | Introduce Parameter Object |
| CS-5 | Long Parameter List | pipeline.py:_metrics_cache_path() (lines 312–346) | 14 parameters, all individually passed, used only to build a hash | Medium | Introduce Parameter Object |
| CS-6 | Feature Envy | pipeline.py:fetch_and_plot() BLS section (lines 1110–1300) | The per-sector BLS loop builds segment_metadata dicts, calls vetting, parameter estimation, candidate writing, and diagnostics — all logic that belongs in dedicated stage functions, not the orchestrator | High | Extract Method |
| CS-7 | Dead Comment | bls.py lines 131, 139 | `# Fix: Change 5`, `# Fix: Change 10` — implementation comments from P0 fix that are no longer useful | Low | Remove Dead Code |

## 3. Complexity Hotspots

| Rank | Location | Cyclomatic Complexity | Max Nesting | Cognitive Complexity | Why It Matters | Simplification |
|------|----------|----------------------|-------------|---------------------|----------------|----------------|
| 1 | pipeline.py:fetch_and_plot() | ~45 (estimated: 15+ if/else branches, 5 for-loops, multiple try/except) | 5 levels (for → if → try → if → if) | Very High — reader must track stitched vs per-sector mode across 886 lines with shared mutable state | Untestable, any change risks regression, impossible to understand in one reading | Extract into 7 stage functions with typed I/O dataclasses |
| 2 | pipeline.py:fetch_and_plot() per-sector BLS loop (lines 1110–1260) | ~12 | 4 levels | High — nested loop with inline metadata construction, vetting, parameter estimation, candidate writing, and diagnostic generation | 150 lines of inline logic that should be a single function call | Extract _run_per_sector_bls() |
| 3 | pipeline.py:fetch_and_plot() per-sector ingest (lines 930–1070) | ~10 | 4 levels | High — manifest loading, cache checking, download fallback, per-segment preprocessing with progress tracking | Interleaves I/O, caching, and preprocessing in a single block | Extract _ingest_per_sector() |
| 4 | bls.py:run_bls_search() | ~10 | 3 levels | Medium — linear flow with early returns, but 124 lines is longer than necessary due to duplicated setup | Setup code obscures the actual search logic | Extract _prepare_bls_inputs() |

## 4. Coupling Analysis

**Tight Coupling**

| From | To | Nature | Problem | Decoupling Strategy |
|------|----|--------|---------|---------------------|
| pipeline.py:fetch_and_plot() | bls, vetting, parameters, plotting, preprocess, cache, ingest, models, progress | Direct function calls with 40+ parameters threaded through | Cannot test any stage without the full pipeline context | Extract stages with typed dataclass I/O; each stage depends only on its input dataclass |
| pipeline.py:fetch_and_plot() | Internal mutable state (boundaries, data_source, prepared_segments_for_bls, etc.) | 12+ local variables shared across the 886-line function body | State mutations are invisible — a change in the ingest section can silently affect the BLS section 300 lines later | Stage functions return immutable dataclasses; no shared mutable state |

**Circular Dependencies**: None detected. Dependency graph is acyclic: cli → pipeline → {bls, vetting, parameters, plotting, preprocess, cache, ingest, models, progress}.

**Dependency Direction**: Correct. pipeline.py depends on domain modules, not the reverse. No domain module imports from pipeline.py.

## 5. Duplication Analysis

| DUP ID | Locations | Lines | Occurrences | Type | Extraction Strategy |
|--------|-----------|-------|-------------|------|---------------------|
| DUP-1 | bls.py:run_bls_search() lines 90–120, bls.py:compute_bls_periodogram() lines 210–240 | 25 per occurrence | 2 | Exact duplicate | Extract `_prepare_bls_inputs(lc_prepared, period_min_days, period_max_days, duration_min_hours, duration_max_hours, n_periods, n_durations)` returning `(model, periods, durations, time, flux)` or `None` |
| DUP-2 | pipeline.py:fetch_and_plot() stitched ingest (lines 821–905) vs per-sector download (lines 960–1010) | ~15 (TESS search + download pattern) | 2 | Structural duplicate (same search/download/error pattern, different post-processing) | Both paths share: lk.search_lightcurve → len check → limit → download_all → None check. Extract `_search_and_download()` |
| DUP-3 | pipeline.py:fetch_and_plot() per-sector BLS metadata construction (lines 1150–1190) vs stitched metadata construction (lines 1340–1380) | ~30 per occurrence | 2 | Structural duplicate (same dict keys, slightly different values) | Extract `_build_candidate_metadata()` helper |

## 6. Improvement Opportunities

| Priority | Issue IDs | Refactoring | Expected Benefit | Effort |
|----------|-----------|-------------|------------------|--------|
| 1 | CS-1, CS-6 | Decompose fetch_and_plot() into 7 stage functions with typed dataclass I/O | Enables isolated testing of each stage; reduces cognitive complexity from ~45 to ~5 per function; makes future features (e.g., multi-planet search) safe to add | High (4-8 hours) |
| 2 | DUP-1, CS-2 | Extract _prepare_bls_inputs() in bls.py | Eliminates 25 lines of duplication; single source of truth for BLS setup; bug fixes apply once | Low (< 1 hour) |
| 3 | DUP-2 | Extract _search_and_download() from pipeline.py ingest paths | Eliminates ~15 lines of structural duplication; simplifies both ingest paths | Low (< 1 hour) |
| 4 | DUP-3 | Extract _build_candidate_metadata() | Eliminates ~30 lines of structural duplication in metadata construction | Low (< 1 hour) |
| 5 | CS-7 | Remove stale fix comments from bls.py | Improves readability | Trivial |

## 7. Risk Assessment

| Risk ID | Code Area | Risk Factor | Likelihood (1-5) | Impact (1-5) | Score | Mitigation |
|---------|-----------|-------------|-------------------|--------------|-------|------------|
| RR-1 | pipeline.py:fetch_and_plot() decomposition | Behavioral regression — stage extraction could subtly change execution order or state flow | 3 | 4 | 12 | Existing test suite (test_smoke.py 31KB, test_p0_fixes.py, test_p1_fixes.py) provides coverage. Write characterization tests capturing current output before refactoring. |
| RR-2 | pipeline.py:fetch_and_plot() per-sector/stitched branching | Mode-dependent logic may be incorrectly split across stages | 2 | 4 | 8 | Keep mode branching within stage functions rather than in the orchestrator. Test both modes. |
| RR-3 | bls.py:_prepare_bls_inputs() extraction | Early-return sentinel handling differs between callers (empty list vs empty tuple) | 2 | 3 | 6 | Return None on invalid input; each caller handles None with its own empty return. |
| RR-4 | pipeline.py shared mutable state | Variables like `boundaries`, `data_source`, `prepared_segments_for_bls` are mutated across sections — extraction must capture all state correctly | 3 | 3 | 9 | Use dataclasses for stage outputs; verify all fields are populated by diffing variable usage before/after. |
| RR-5 | External consumers | `fetch_and_plot()` signature used by cli.py and run_batch_analysis() | 1 | 5 | 5 | Preserve exact public signature and return type. Stage functions are internal. |

## 8. Recommendations

**P0 — Address First**

1. **Extract `_prepare_bls_inputs()` in bls.py** (DUP-1, CS-2)
   - Technique: Extract Method
   - Prerequisite: Existing tests in test_p0_fixes.py and test_smoke.py cover BLS search and periodogram
   - Scope: bls.py only, no cross-module impact
   - Do this first — smallest, safest change

2. **Decompose `fetch_and_plot()` into typed stage functions** (CS-1, CS-6, DUP-2, DUP-3)
   - Technique: Extract Method + Introduce Parameter Object (dataclasses for stage I/O)
   - Prerequisite: Write characterization tests that capture current pipeline output (candidate JSON, metrics, manifest) for a synthetic light curve. These tests pin behavior before refactoring.
   - Stages: `_ingest_stage()`, `_preprocess_stage()`, `_search_stage()`, `_vetting_stage()`, `_output_stage()`, `_plotting_stage()`, `_manifest_stage()`
   - `fetch_and_plot()` becomes a thin orchestrator (~60-80 lines) calling stages in sequence
   - Each stage returns a frozen dataclass; no shared mutable state between stages

**P1 — Address Second**

3. **Remove stale fix comments** (CS-7)
   - Technique: Remove Dead Code
   - Prerequisite: None
   - Trivial cleanup, can be done alongside P0 changes

**Out of Scope** (noted but not recommended for this refactoring):

- CS-3, CS-4, CS-5 (long parameter lists in fetch_and_plot, _candidate_output_key, _metrics_cache_path): These are symptoms of the monolith. After decomposition, the stage dataclasses naturally group parameters. The public signature of fetch_and_plot() must not change per constraints.
