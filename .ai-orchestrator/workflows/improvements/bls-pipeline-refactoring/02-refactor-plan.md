---
agent: refactor-plan
sequence: 2
references: ["refactor-analysis"]
summary: "7-step refactoring plan: first extract _prepare_bls_inputs() in bls.py (R15), then decompose the 886-line fetch_and_plot() monolith in pipeline.py (R14) into 7 stage functions with typed dataclass I/O. Characterization tests are written before any structural changes. Each step is independently verifiable with pytest."
---

## 1. Refactoring Strategy

- **Guiding Principle**: Single Responsibility — each function does one thing. Stage functions own their logic; the orchestrator owns sequencing.
- **Ordering Strategy**: Tests first (pin current behavior), then small isolated change (bls.py DRY extraction), then large decomposition (pipeline.py stages) bottom-up from leaf stages to orchestrator.
- **Behavior Preservation Method**: Existing test suite (6 files, ~100KB) plus new characterization tests that assert pipeline output structure. All tests run after every step.
- **Change Scope**: Medium — two files modified (bls.py, pipeline.py), no new files created, no public API changes.

## 2. Scope and Constraints

**In Scope**:
- `src/exohunt/bls.py` — extract `_prepare_bls_inputs()` from duplicated setup code
- `src/exohunt/pipeline.py` — decompose `fetch_and_plot()` into stage functions, define stage I/O dataclasses

**Out of Scope**:
- All other source files (vetting.py, plotting.py, preprocess.py, config.py, cli.py, etc.) — no changes
- Public API of `fetch_and_plot()` — signature and return type preserved exactly
- Public API of `run_batch_analysis()` — no changes
- `run_bls_search()`, `compute_bls_periodogram()`, `refine_bls_candidates()` public signatures — preserved
- CS-3, CS-4, CS-5 (long parameter lists) — symptoms of the monolith, addressed naturally by decomposition but public signatures unchanged

**Invariants**:
- `fetch_and_plot()` accepts the same 42 parameters and returns `Path | None`
- `run_batch_analysis()` calls `fetch_and_plot()` unchanged
- All output files (CSV, JSON, plots, manifests) are byte-identical for the same inputs
- Logging output format and content preserved

**Constraints**:
- Python ≥ 3.10, no new dependencies
- Existing tests pass without modification
- Stage functions must be module-level and importable

## 3. Prerequisite Checks

- **Test Coverage**: test_smoke.py covers full pipeline execution with mock lightkurve. test_p0_fixes.py covers BLS SNR, vetting, normalization. test_p1_fixes.py covers FAP, alias ratios, secondary eclipse, depth consistency, config sections, diagnostics, iterative masking. Coverage is adequate for both targets.
- **Build State**: `cd /Users/gbasin/Development/exoplanets-hunting-pipeline && python -m pytest tests/ -x -q` must pass.
- **Version Control**: All changes committed. Start from clean working tree.
- **Dependencies**: No new dependencies required.

## 4. Refactoring Steps

### Step 1: Add Characterization Tests — pipeline.py fetch_and_plot() output structure

- **Analysis Reference**: RR-1 (behavioral regression risk)
- **Technique**: Add Characterization Test
- **Target**: `tests/test_refactoring.py` (new file)
- **Description**: Write tests that call `fetch_and_plot()` with a mock light curve and assert the return type, that the function completes without error, and that key internal functions (`_write_bls_candidates`, `_write_preprocessing_metrics`, `_write_run_manifest`) are called. This pins the current behavior before any structural changes.
- **Detailed Changes**:
  - Create `tests/test_refactoring.py` with characterization tests
  - Tests use existing mock patterns from test_smoke.py
- **Precondition**: All existing tests pass
- **Postcondition**: New characterization tests pass alongside existing tests
- **Verification**: `python -m pytest tests/test_refactoring.py tests/ -x -q`
- **Rollback**: Delete `tests/test_refactoring.py`

### Step 2: Extract Method — `_prepare_bls_inputs()` in bls.py

- **Analysis Reference**: DUP-1, CS-2
- **Technique**: Extract Method
- **Target**: `src/exohunt/bls.py`
- **Description**: Extract the 25-line duplicated setup block (input validation, sorting, period/duration grid construction, BLS model instantiation) from `run_bls_search()` and `compute_bls_periodogram()` into a private `_prepare_bls_inputs()` function. The function returns a `_BLSInputs` NamedTuple containing `(time, flux, model, periods, durations)` or `None` if inputs are invalid. Both callers replace their duplicated blocks with a call to `_prepare_bls_inputs()` and handle the `None` case with their existing early-return patterns.
- **Detailed Changes**:
  - Add `_BLSInputs` NamedTuple (or dataclass) to bls.py
  - Add `_prepare_bls_inputs(lc_prepared, period_min_days, period_max_days, duration_min_hours, duration_max_hours, n_periods, n_durations)` → `_BLSInputs | None`
  - Modify `run_bls_search()`: replace lines 90–120 with call to `_prepare_bls_inputs()`, handle `None` → `return []`
  - Modify `compute_bls_periodogram()`: replace lines 210–240 with call to `_prepare_bls_inputs()`, handle `None` → `return (empty, empty)`
  - Remove stale `# Fix: Change 5` and `# Fix: Change 10` comments (CS-7)
- **Precondition**: Step 1 complete, all tests pass
- **Postcondition**: No duplicated setup code in bls.py. All existing tests pass. `run_bls_search()` and `compute_bls_periodogram()` produce identical results.
- **Verification**: `python -m pytest tests/ -x -q`
- **Rollback**: `git checkout src/exohunt/bls.py`

### Step 3: Introduce Parameter Object — Stage I/O dataclasses in pipeline.py

- **Analysis Reference**: CS-1 (preparation for decomposition)
- **Technique**: Introduce Parameter Object
- **Target**: `src/exohunt/pipeline.py`
- **Description**: Define frozen dataclasses for stage inputs and outputs at module level in pipeline.py. These are: `IngestResult`, `PreprocessResult`, `SearchResult`, `OutputResult`, `PlotResult`, `ManifestResult`. Each captures the data that flows between stages. No behavioral changes — just add the dataclass definitions.
- **Detailed Changes**:
  - Add 6 frozen dataclass definitions to pipeline.py (after existing imports, before existing functions)
  - No existing code modified
- **Precondition**: Step 2 complete, all tests pass
- **Postcondition**: New dataclasses importable from pipeline.py. All existing tests pass unchanged.
- **Verification**: `python -m pytest tests/ -x -q`
- **Rollback**: Remove the added dataclass definitions

### Step 4: Extract Method — `_ingest_stage()` from fetch_and_plot()

- **Analysis Reference**: CS-1, DUP-2
- **Technique**: Extract Method
- **Target**: `src/exohunt/pipeline.py:fetch_and_plot()` lines 821–1070
- **Description**: Extract the stitched-mode ingest (cache check, download, stitch) and per-sector ingest (manifest, download, per-segment preprocessing) into a single `_ingest_stage()` function. It accepts the relevant parameters and returns an `IngestResult` dataclass. The `fetch_and_plot()` body replaces ~250 lines with a single call to `_ingest_stage()` and unpacks the result.
- **Detailed Changes**:
  - Add `_ingest_stage()` function to pipeline.py
  - Modify `fetch_and_plot()`: replace ingest block with call to `_ingest_stage()`, unpack `IngestResult` fields into local variables
  - No changes to any other function
- **Precondition**: Step 3 complete, all tests pass
- **Postcondition**: `fetch_and_plot()` is ~250 lines shorter. All existing tests pass.
- **Verification**: `python -m pytest tests/ -x -q`
- **Rollback**: `git checkout src/exohunt/pipeline.py`

### Step 5: Extract Method — `_search_and_output_stage()` from fetch_and_plot()

- **Analysis Reference**: CS-1, CS-6, DUP-3
- **Technique**: Extract Method
- **Target**: `src/exohunt/pipeline.py:fetch_and_plot()` lines 1110–1410
- **Description**: Extract the BLS search block (per-sector loop and stitched path), vetting, parameter estimation, candidate writing, and diagnostic generation into `_search_and_output_stage()`. Returns a `SearchResult` dataclass. This is the most complex extraction because it handles both per-sector and stitched modes with inline metadata construction.
- **Detailed Changes**:
  - Add `_search_and_output_stage()` function to pipeline.py
  - Modify `fetch_and_plot()`: replace BLS+output block with call to `_search_and_output_stage()`
  - No changes to any other function
- **Precondition**: Step 4 complete, all tests pass
- **Postcondition**: `fetch_and_plot()` is ~300 lines shorter. All existing tests pass.
- **Verification**: `python -m pytest tests/ -x -q`
- **Rollback**: `git checkout src/exohunt/pipeline.py`

### Step 6: Extract Method — `_plotting_stage()` and `_manifest_stage()` from fetch_and_plot()

- **Analysis Reference**: CS-1
- **Technique**: Extract Method
- **Target**: `src/exohunt/pipeline.py:fetch_and_plot()` lines 1410–1656
- **Description**: Extract the plotting block (stitched and per-sector) into `_plotting_stage()` returning `PlotResult`, and the manifest+logging block into `_manifest_stage()` returning `ManifestResult`. After this step, `fetch_and_plot()` is a thin orchestrator: setup → ingest → metrics → search+output → plotting → manifest.
- **Detailed Changes**:
  - Add `_plotting_stage()` function to pipeline.py
  - Add `_manifest_stage()` function to pipeline.py
  - Modify `fetch_and_plot()`: replace plotting and manifest blocks with calls
  - No changes to any other function
- **Precondition**: Step 5 complete, all tests pass
- **Postcondition**: `fetch_and_plot()` is ≤80 lines. All existing tests pass.
- **Verification**: `python -m pytest tests/ -x -q`
- **Rollback**: `git checkout src/exohunt/pipeline.py`

### Step 7: Clean Up — Remove dead code, finalize naming

- **Analysis Reference**: CS-7
- **Technique**: Remove Dead Code, Rename
- **Target**: `src/exohunt/bls.py`, `src/exohunt/pipeline.py`
- **Description**: Final cleanup pass. Verify no orphaned local variables remain in `fetch_and_plot()`. Ensure all stage functions have docstrings. Verify import ordering. Remove any remaining stale comments.
- **Detailed Changes**:
  - Review and clean `fetch_and_plot()` for unused variables
  - Add docstrings to stage functions if missing
  - Verify import ordering in pipeline.py
- **Precondition**: Step 6 complete, all tests pass
- **Postcondition**: Clean code, all tests pass, no dead code
- **Verification**: `python -m pytest tests/ -x -q && python -m ruff check src/exohunt/bls.py src/exohunt/pipeline.py`
- **Rollback**: `git checkout src/exohunt/bls.py src/exohunt/pipeline.py`

## 5. Dependency Graph

```
Step 1 (characterization tests)
  ├── Step 2 (extract _prepare_bls_inputs in bls.py)
  │     └── Step 3 (define stage dataclasses)
  │           └── Step 4 (extract _ingest_stage)
  │                 └── Step 5 (extract _search_and_output_stage)
  │                       └── Step 6 (extract _plotting_stage + _manifest_stage)
  │                             └── Step 7 (cleanup)
```

Critical path: Steps 1 → 2 → 3 → 4 → 5 → 6 → 7 (fully linear — each step depends on the previous).

## 6. Verification Checkpoints

**Checkpoint A — After Step 1 (before any code changes)**:
- **Run**: `python -m pytest tests/ -x -q`
- **Expected**: All tests pass including new characterization tests
- **Metrics Check**: Note current line count of `fetch_and_plot()` (886 lines) and bls.py duplication (25 lines × 2)

**Checkpoint B — After Step 2 (bls.py refactoring complete)**:
- **Run**: `python -m pytest tests/ -x -q`
- **Expected**: All tests pass. bls.py has zero duplicated setup blocks.
- **Metrics Check**: bls.py `run_bls_search()` and `compute_bls_periodogram()` each ~25 lines shorter. `_prepare_bls_inputs()` is ~25 lines.

**Checkpoint C — After Step 4 (ingest extracted)**:
- **Run**: `python -m pytest tests/ -x -q`
- **Expected**: All tests pass. `fetch_and_plot()` is ~250 lines shorter.
- **Metrics Check**: `fetch_and_plot()` line count reduced from 886 to ~636.

**Checkpoint D — After Step 6 (all stages extracted)**:
- **Run**: `python -m pytest tests/ -x -q`
- **Expected**: All tests pass. `fetch_and_plot()` is ≤80 lines.
- **Metrics Check**: `fetch_and_plot()` line count ≤80. Stage functions are module-level and importable.

**Checkpoint E — After Step 7 (final)**:
- **Run**: `python -m pytest tests/ -x -q && python -m ruff check src/exohunt/bls.py src/exohunt/pipeline.py`
- **Expected**: All tests pass, no lint errors.

## 7. Rollback Plan

- **Full Rollback**: `git checkout src/exohunt/bls.py src/exohunt/pipeline.py` restores both files to pre-refactoring state. Delete `tests/test_refactoring.py` if characterization tests should also be removed.
- **Partial Rollback**: Each step modifies at most 2 files. `git checkout <file>` reverts to the state after the previous step's commit.
- **Rollback Triggers**: Any test failure after a step. Any behavioral change detected (different output files for same input). Ruff lint errors that indicate structural problems (unused imports, undefined names).
- **Rollback Verification**: After rollback, run `python -m pytest tests/ -x -q` to confirm all tests pass with the reverted code.
