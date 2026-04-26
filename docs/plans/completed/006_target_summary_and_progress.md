# Per-Target Summary Markdown + Batch Progress File

## Overview

Two additive features from `.docs/ideas.md`:

1. **Per-target `summary.md`** — human-readable summary inside each target directory: stellar parameters, known planets pre-masked, candidates grouped by iteration with vetting outcomes, physical parameters for passing candidates.
2. **Batch progress file** — single-glance view of a batch run's state at `<run_dir>/progress.{json,txt}`: processed/total, current target, ETA (rolling mean of last 10), last-5 statuses.

Both features are additive — no existing outputs change, no existing behavior changes. Only new files are written.

**Prerequisites:** Plans 001-005 complete. Clean `master` at `aef15df`.

**Files modified:**
- `src/exohunt/manifest.py` — add `write_target_summary()` function
- `src/exohunt/pipeline.py` — call `write_target_summary()` at end of `_search_and_output_stage`
- `src/exohunt/batch.py` — add progress-writing helper; call it after each target
- `tests/` — add unit tests for both writers

**Files NOT modified:**
- No schema changes to `BLSCandidate`, `CandidateVettingResult`, config, or any existing artifacts.
- No changes to preset TOML files.
- No CLI flag additions (both features always-on).

---

## Design

### Per-target summary (Idea 1)

**Path:** `<run_dir>/<target-slug>/summary.md`

**Content structure:**
```markdown
# Run summary: TIC 317597583

- **Run:** 2026-04-25T20-09-19_iterative-search_revert_verify
- **Preset:** `iterative-search` (version 1, hash 43101d445d6cd66e)
- **Runtime:** 2937.6 s
- **Data:** 177378 → 177293 cadences (BTJD 1764.69 → 3662.83)

## Stellar parameters
- **Source:** TIC / astroquery (not defaults)
- **R_star:** 0.831 [0.789, 0.873] R☉
- **M_star:** 0.950 [0.825, 1.075] M☉
- **Limb darkening (u1, u2):** (0.3947, 0.2049)

_Falls back to text `"solar defaults"` when stellar_params.used_defaults=True._

## Known planets / TOIs in this system
- **TOI-1630.01** — P = 12.056 d — pre-masked (1986 cadences NaN-masked)

_If no known planets, section reads: "No known planets or TOI candidates in NASA Exoplanet Archive."_

## Search results

### Iteration 0
Masked: TOI-1630.01 (P=12.056 d)
Candidates found: 5
- rank 1: P = 21.5608 d, depth = 200.9 ppm, SNR = 6.9 — FAIL (`odd_even_depth_mismatch`)
- rank 2: P = 4.5738 d, depth = 136.4 ppm, SNR = 18.0 — **PASS**
- rank 3: P = 24.7321 d, depth = 160.6 ppm, SNR = 4.9 — PASS (`odd_even_inconclusive`)
- rank 4: P = 16.2555 d, depth = 198.9 ppm, SNR = 6.1 — FAIL (`depth_inconsistent`)
- rank 5: P = 22.8571 d, depth = 192.5 ppm, SNR = 3.8 — FAIL (`odd_even_depth_mismatch;alias_or_harmonic_of_rank_2`)

### Iteration 1
Masked: TOI-1630.01 + iter-0 signal at P=21.5608 d
Candidates found: 1
- rank 6: P = 4.5738 d, depth = 135.4 ppm, SNR = 17.6 — **PASS**

## Passing candidates with physical parameters

### rank 2 (P = 4.5738 d) — iteration 0
- Depth: 136.4 ppm
- Duration: 2.0 h
- Transit time (BTJD): 2031.5
- Transit count estimate: 415
- Rp/Rs: 0.0117
- Rp (assuming stellar radius above): 1.056 R⊕
- Expected duration (central, solar density): 1.91 h
- Observed/expected duration ratio: 1.05 — passes plausibility

### rank 3 (P = 24.7321 d) — iteration 0
- ...

### rank 6 (P = 4.5738 d) — iteration 1
- ...

## Artifacts
- Candidates: `candidates/tic_317597583__bls_0c98c7c7c4a9.{csv,json}`
- Diagnostics: `diagnostics/tic_317597583__bls_0c98c7c7c4a9__candidate_*_{periodogram,phasefold}.png`
- Plots: `plots/tic_317597583_prepared_stitched.png`
- Manifest: `manifests/tic_317597583__manifest_<hash>.json`
```

**Semantic notes:**
- "Masked" per iteration: derived. Iteration 0's mask = pre-masked known planets (from `known_ephemerides` list). Iteration N's mask = iter 0's plus every candidate from iterations `<N` that drove the iterative masking.
- The current `bls_candidates` list contains every candidate TLS returned across all passes (raw, pre-refine, pre-dedup). We have `iteration` on each. Grouping by `iteration` is trivial.
- "Which drove masking" = whichever candidate was top-power per pass AFTER the degenerate-duration filter but BEFORE vetting (see `run_iterative_bls_search`: it already takes `config.iterative_top_n` per pass regardless of vetting status, per Plan 004). For summary purposes we report the top-power candidate from each iteration as the "signal masked" for the next iteration.
- Simpler: for iteration N's "Masked" line, list the top-1 candidate from iteration N-1's output.
- The combined candidates JSON already contains all the physical parameter fields (via `estimate_candidate_parameters`). Pull from there.
- Passing candidates = those with `vetting_pass=True` in `stitched_vetting_by_rank`.
- No new data plumbing needed — all inputs (stellar_params, known, bls_candidates, stitched_vetting_by_rank, parameter_estimates) are in scope at the end of `_search_and_output_stage`.

**Triggering:**
- Called from `_search_and_output_stage`, just before return.
- Works even if `run_bls=False` or `bls_candidates=[]` — the summary just shows preprocessing + stellar + known planets + "no BLS performed" or "no candidates".
- Wrapped in try/except so a summary-write failure never aborts the main run (log warning, continue).

### Batch progress file (Idea 2)

**Paths:** `<run_dir>/progress.json` + `<run_dir>/progress.txt`

**JSON fields:**
```json
{
  "schema_version": 1,
  "run_started_utc": "2026-04-25T20:09:19Z",
  "last_updated_utc": "2026-04-25T20:45:02Z",
  "total": 50,
  "processed": 23,
  "successes": 20,
  "failures": 3,
  "skipped_completed": 0,
  "percent_complete": 46.0,
  "current_target": "TIC 261136679",
  "elapsed_seconds": 2143.7,
  "rolling_mean_runtime_seconds": 98.4,
  "eta_seconds": 2657.5,
  "last_5_statuses": [
    {"target": "TIC 355867695", "status": "success", "runtime_seconds": 87.2},
    {"target": "TIC 261136679", "status": "success", "runtime_seconds": 112.5},
    {"target": "TIC 41173048", "status": "failed", "runtime_seconds": 12.3, "error": "No TESS light curves found"},
    ...
  ]
}
```

**TXT rendering:**
```
Exohunt batch progress
======================
Run: 2026-04-25T20-09-19_iterative-search_revert_verify
Started: 2026-04-25 20:09:19 UTC
Updated: 2026-04-25 20:45:02 UTC

Progress: 23 / 50  (46.0%)
  ✓ 20 succeeded
  ✗ 3 failed
  → 0 skipped (prior runs)

Current: TIC 261136679
Elapsed: 35m 43s
ETA:     44m 17s
(based on rolling mean of last 10 runs: 98.4s/target)

Recent targets (last 5):
  ✓ TIC 355867695       (87.2s)
  ✓ TIC 261136679       (112.5s)
  ✗ TIC 41173048        (12.3s)   No TESS light curves found
  ✓ TIC 220194875       (95.1s)
  ✓ TIC 260128333       (89.6s)
```

**Update points:**
- After each target's `_save_batch_state(state_path, state_payload)` call, also call `_write_progress(run_dir, state_payload, statuses, target_running, ...)`.
- `current_target` is set to the target about to be processed at the START of each iteration, cleared at the end.
- Atomic write: write to `progress.json.tmp` → `os.replace()` → overwrites. Same for `.txt`.

**ETA calculation (rolling mean of last 10):**
```python
recent_runtimes = [s.runtime_seconds for s in statuses[-10:] if s.status == "success"]
if recent_runtimes:
    mean = sum(recent_runtimes) / len(recent_runtimes)
    remaining = total - processed
    eta_seconds = mean * remaining
else:
    eta_seconds = None  # not enough data yet
```

**Failure handling:**
- Progress write wrapped in try/except. A progress-write failure must never abort the batch.

---

## Implementation

### Step 1: Add `write_target_summary` to manifest.py

**File:** `src/exohunt/manifest.py`

**What to implement:** New function with this signature:

```python
def write_target_summary(
    *,
    target: str,
    run_dir: Path,
    run_id: str,
    preset_meta: PresetMeta,
    config: RuntimeConfig,
    runtime_seconds: float,
    n_points_raw: int,
    n_points_prepared: int,
    time_min_btjd: float,
    time_max_btjd: float,
    stellar_params: Any | None,
    known_ephemerides: list[Any],
    n_masked_cadences: int,
    bls_candidates: list[BLSCandidate],
    vetting_by_rank: dict[int, Any],
    parameter_estimates_by_rank: dict[int, Any],
    candidate_csv_paths: list[Path],
    diagnostic_assets: list[tuple[Path, Path]],
    plot_paths: list[Path],
    manifest_path: Path,
) -> Path:
    """Write a human-readable summary.md at <run_dir>/<target-slug>/summary.md.

    Best-effort: wrap the caller in try/except — summary-write failures
    MUST NOT abort a successful analysis run.
    """
```

**Implementation notes:**
- Uses `_target_output_dir(target, outputs_root=run_dir)` to compute the target dir.
- Groups `bls_candidates` by `c.iteration` (sorted ascending). For each group, emit the iteration section with "Masked" text + candidate list.
  - Iteration 0 "Masked" = list of known_ephemerides names+periods, with cadence-mask count.
  - Iteration N (N>0) "Masked" = same as iter 0, plus bullet summarizing iter 0..N-1's top-power candidate.
- Passing candidates list: filter `bls_candidates` by `vetting_by_rank.get(c.rank, None).vetting_pass`. For each, emit a subsection using `parameter_estimates_by_rank.get(c.rank)` if available, else skip physical params.
- Returns the path. Swallow exceptions in the caller (not in this function).
- Uses only local-module imports to avoid circular import (BLSCandidate from bls, CandidateVettingResult from vetting, stellar from stellar — these already don't depend on manifest/pipeline).

### Step 2: Call `write_target_summary` from `_search_and_output_stage`

**File:** `src/exohunt/pipeline.py`

**What to implement:** Just before `return SearchResult(...)` in `_search_and_output_stage`, invoke `write_target_summary` inside try/except. All required arguments are already in scope (`stellar_params`, `known`, `bls_candidates`, `stitched_vetting_by_rank`, candidate output paths, diagnostic paths, etc.). For `parameter_estimates_by_rank`, the function currently computes estimates inside the `_write_bls_candidates` call — refactor to compute once, reuse for both candidate writing AND the summary:

```python
# Just BEFORE the existing _write_bls_candidates call, compute once:
parameter_estimates_by_rank = estimate_candidate_parameters(
    candidates=bls_candidates,
    stellar_density_kg_m3=parameter_stellar_density_kg_m3,
    duration_ratio_min=parameter_duration_ratio_min,
    duration_ratio_max=parameter_duration_ratio_max,
    apply_limb_darkening_correction=parameter_apply_limb_darkening_correction,
    limb_darkening_u1=parameter_limb_darkening_u1,
    limb_darkening_u2=parameter_limb_darkening_u2,
    tic_density_lookup=parameter_tic_density_lookup,
    tic_id=str(parse_tic_id(target)) if parameter_tic_density_lookup else None,
)
# Pass it explicitly to _write_bls_candidates instead of computing inline.
```

Then pass `parameter_estimates_by_rank` to `write_target_summary`.

**Mask-count tracking:** `mask_known_transits` in `known_transit_masking.py` currently logs `n_masked_cadences` but does not return it. Add a return value: make it return `(lc, n_masked_cadences)` as a tuple. Update the single caller in `pipeline.py`. This is a small interface change; only one caller exists.

Alternative (simpler): skip the masked-cadence count in the summary entirely; say "pre-masked N known signals" without cadence count. Prefer this simpler path.

**Decision:** skip cadence count. Summary just lists which known planets were pre-masked — the user can consult the log if they want the exact count.

### Step 3: Wire `run_id` through

The `run_id` is the directory name (`run_dir.name`). No threading needed — can derive in `write_target_summary` itself via `run_dir.name`.

### Step 4: Add `_write_progress` to batch.py

**File:** `src/exohunt/batch.py`

**What to implement:** A module-private helper:

```python
def _write_progress(
    run_dir: Path,
    *,
    run_id: str,
    run_started_utc: str,
    total: int,
    processed: int,
    successes: int,
    failures: int,
    skipped: int,
    current_target: str | None,
    elapsed_seconds: float,
    statuses: list[BatchTargetStatus],
) -> None:
    """Atomically update progress.json and progress.txt at run root.

    Best-effort — a progress-write failure MUST NOT abort the batch run.
    Caller is expected to wrap in try/except and log on failure.
    """
```

**Content:**
1. Compute rolling mean from `statuses[-10:]` (filter to `status == "success"`, read `.runtime_seconds`).
2. ETA = `mean * (total - processed)` if mean exists, else `None`.
3. Extract last 5 statuses (success/failure/skipped — all types).
4. Write JSON with `json.dumps(..., indent=2, sort_keys=True)` to `progress.json.tmp`, then `os.replace` to `progress.json`.
5. Render text via a small local helper (`_format_duration` for mm:ss / hh:mm:ss / days), write to `progress.txt.tmp`, replace to `progress.txt`.

### Step 5: Call `_write_progress` in the batch loop

**File:** `src/exohunt/batch.py`

**What to implement:** In `run_batch_analysis`, just after `_save_batch_state(state_path, state_payload)` in the `finally:` block, call `_write_progress` wrapped in try/except:

```python
finally:
    state_payload["completed_targets"] = sorted(completed)
    state_payload["failed_targets"] = sorted(failed)
    state_payload["errors"] = errors
    _save_batch_state(state_path, state_payload)
    try:
        _write_progress(
            run_dir,
            run_id=run_dir.name,
            run_started_utc=run_utc,
            total=total,
            processed=idx,
            successes=len(completed),
            failures=len(failed),
            skipped=sum(1 for s in statuses if s.status == "skipped_completed"),
            current_target=None,  # cleared after target completes
            elapsed_seconds=perf_counter() - _batch_start,
            statuses=statuses,
        )
    except Exception as exc:
        LOGGER.warning("Failed to write progress: %s", exc)
    _render_progress("Batch targets", idx, total)
```

Additionally, **before** each target starts (i.e., at the top of the `for` loop body, after the `if target in completed:` skip handler), call `_write_progress` with `current_target=target`, `processed=idx-1`. This ensures `progress.txt` always shows "currently processing X" even during the potentially long-running `fetch_and_plot` call.

### Step 6: Tests

**File:** `tests/test_manifest.py` (new or extend existing)

Unit tests for `write_target_summary`:

1. `test_summary_written_to_correct_path` — writes to `<run_dir>/<slug>/summary.md`, returns that path.
2. `test_summary_with_no_candidates` — empty candidate list → summary contains "No BLS candidates found" or equivalent.
3. `test_summary_with_passing_candidate` — one passing candidate → summary lists it under "Passing candidates" section.
4. `test_summary_groups_by_iteration` — candidates with iterations 0, 0, 1 produce two iteration sections.
5. `test_summary_with_stellar_defaults` — `stellar_params.used_defaults=True` → section reads "solar defaults".
6. `test_summary_with_known_ephemerides` — non-empty list → each gets a bullet.

**File:** `tests/test_batch.py` (new or extend test_runs.py)

Unit tests for `_write_progress`:

7. `test_progress_files_created` — after calling, both `progress.json` and `progress.txt` exist in run_dir.
8. `test_progress_json_schema` — JSON contains expected keys (schema_version, total, processed, successes, failures, last_5_statuses, etc.).
9. `test_progress_eta_with_rolling_mean` — given 3 success statuses with runtimes [100, 90, 110], eta = 100 * remaining.
10. `test_progress_eta_none_with_no_history` — empty status list → `eta_seconds` is null in JSON.
11. `test_progress_atomic_replacement` — when called twice, second call cleanly replaces first (no stale `.tmp` leftover).
12. `test_progress_renders_percent` — `progress.txt` contains `"46.0%"` for 23/50.

No integration tests required — these features are additive and tested via unit + manual integration verification.

### Step 7: Manual integration verification

After code is in place and unit tests pass, run:

```bash
.venv/bin/python -m exohunt.cli run --target "TIC 317597583" --config iterative-search --run-name summary_test
cat outputs/runs/*_summary_test/tic_317597583/summary.md
```

Expected: `summary.md` exists, renders cleanly, shows 6 candidates grouped into iter 0 (5) + iter 1 (1), flags 3 passing candidates.

Batch-style test not strictly necessary (single-target won't produce `progress.*` files by design). For a quick batch test, create a 2-target file:

```bash
cat > /tmp/mini_targets.txt << 'EOF'
TIC 317597583
TIC 261136679
EOF
.venv/bin/python -m exohunt.cli batch --targets-file /tmp/mini_targets.txt --config quicklook --run-name progress_test
cat outputs/runs/*_progress_test/progress.txt
```

Expected: `progress.txt` shows `2/2 (100.0%)`, success counts, last-N list populated.

## Risk Assessment

**Low risk — both features are additive.**

Specific concerns:
1. `_search_and_output_stage` is already complex (~550 lines). Adding ~20 lines at the end for summary-writing is benign but increases weight; justify by keeping `write_target_summary` external (in manifest.py).
2. `parameter_estimates_by_rank` is currently computed inside `_write_bls_candidates` via the `parameter_estimates_by_rank=estimate_candidate_parameters(...)` kwarg. Lifting it to a local variable is a small refactor with one caller change. Verify no duplicate computation sneaks in.
3. Progress file atomic replacement: must use `os.replace` (not `shutil.move`) — Python's `os.replace` is atomic on POSIX and Windows.
4. Per-target summary writes a new file per target. For a 3000-target batch, that's 3000 extra writes. Each is < 10KB. Negligible I/O.

## Out of Scope

- Any schema changes to existing artifacts (candidates CSV, manifest JSON, etc.).
- Gating via CLI flag or config — both features always-on.
- Adding sections for TRICERATOPS results in summary — they're optional and not in the current basic summary spec.
- Interactive web progress UI — ruled out in ideas.md non-goals.
- Rendering summary for failed-vetting candidates as separate sections — basic iteration grouping covers this.
