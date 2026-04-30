# Plan 007 — Two-axis parallelism (idea 3) with concurrency safety (ideas 5, 6, 7)

## Goal

Enable two axes of parallelism for the 3000-target AWS campaign:

1. **Single-target (intra-TLS) threads.** TLS accepts `use_threads` — currently hardcoded to `1`. Expose as `bls.tls_threads` so a multi-core EC2 worker actually uses its cores on a single large target. Active only in `exohunt run` mode.
2. **Batch (across-target) process pool.** `run_batch_analysis` is strictly sequential today. Parallelize with `concurrent.futures.ProcessPoolExecutor`, configurable via `batch.parallelism`. Active only in `exohunt batch` mode.

**The two axes are mutually exclusive by design**: in batch mode, each worker forces `tls_threads=1` regardless of config. This eliminates CPU oversubscription entirely — no multiplication, no warnings, no hard caps.

Under parallel execution, three hazards from `.docs/ideas.md` (5, 6, 7) must be resolved:

- **Idea 5.** Per the user: **drop `candidates_live.csv` / `candidates_novel.csv` generation from the hot path entirely.** Replace with an on-demand CLI `exohunt collect-live --run <path>` that walks per-target JSONs to emit the same files. Sidesteps the concurrency problem by removing the shared write.
- **Idea 6.** A `.done` sentinel per target dir, written as the final step of `fetch_and_plot`. Resume requires both `state.completed_targets` membership AND sentinel presence.
- **Idea 7.** Replace the current `30 * 2**attempt` retry backoff with **full jitter** (`random.uniform(0, base * 2**attempt)`) — AWS standard for decorrelating retries across many workers against a shared rate-limited endpoint.

Non-goals (deferred):
- Shared token-bucket rate limiter (needs IPC; full idea 7). Full jitter is sufficient mitigation for the `parallelism ≤ cpu_count()` scale we're building for.
- Archive query caching (idea 8).
- AWS orchestration (idea 9).

## Decisions

From the design discussion:

| Question | Decision |
|---|---|
| Retry jitter flavor | **Full jitter** (`random.uniform(0, base * 2**attempt)`) |
| "Done" marker | **`.done` sentinel** (not `.tmp/` → rename — too invasive) |
| Batch concurrency mechanism | **stdlib `ProcessPoolExecutor`** (not joblib, not shell-level `xargs`) |
| Live CSVs | **Removed from hot path.** New `exohunt collect-live --run <path>` generates them on demand |
| `tls_threads` × `parallelism` | **Mutually exclusive.** Batch forces `tls_threads=1` per worker |
| Default `tls_threads` (run mode) | `os.cpu_count()` (config `-1` = auto) |
| Default `parallelism` (batch mode) | `max(1, os.cpu_count() - 1)` (config `-1` = auto) |
| `mp` start method | **`spawn` on all platforms** (consistency dev↔prod, avoids `tls.py` global `fork` override leaking into the pool) |

## Context

Relevant files (read during planning):

- `src/exohunt/tls.py` — `run_tls_search`, two `.power()` calls with `use_threads=1` on lines 102 and 141. Module also forces `multiprocessing.set_start_method("fork", force=True)` at import time on POSIX.
- `src/exohunt/batch.py` — `run_batch_analysis`, sequential `for idx, target in enumerate(deduped_targets)` loop. Owns `run_state.json`, `run_status.csv/json`, progress writes, hardcoded `max_retries=3` and `wait = 30 * (2 ** attempt)` retry loop.
- `src/exohunt/candidates_io.py` — `_append_live_candidates` writes the shared live CSVs. To be removed from the hot path.
- `src/exohunt/pipeline.py` — `fetch_and_plot`, the per-target entry. Writes per-target outputs under `run_dir/outputs/<slug>/`.
- `src/exohunt/config.py` — `BLSConfig` + `_DEFAULTS["bls"]`. Extend.
- `src/exohunt/cli.py` — parses `run`, `batch`, `init-config`; add `collect-live` subcommand and `--parallelism` / `--tls-threads` overrides.
- `src/exohunt/manifest.py` — `append_manifest_index` appends to `outputs/manifests/run_manifest_index.csv`. Racy under parallelism.
- `pipeline._write_preprocessing_metrics` — appends to `outputs/metrics/preprocessing_summary.csv`. Racy under parallelism.

## Design

### 1. Config surface

Extend `_DEFAULTS` in `src/exohunt/config.py`:

```toml
[bls]
tls_threads = -1                # -1 = auto (os.cpu_count()); any positive int pins.

[batch]
parallelism = -1                # -1 = auto (max(1, cpu_count()-1)); 1 = sequential.
max_retries = 3
retry_base_seconds = 30.0
retry_jitter_seconds = 15.0     # unused if we go pure full-jitter; see Step 3.
```

Decision on jitter params: with full jitter, the formula is `random.uniform(0, base * 2**attempt)`. No separate `retry_jitter_seconds` needed. Simpler:
```toml
[batch]
parallelism = -1
max_retries = 3
retry_base_seconds = 30.0
```

Add `BatchConfig` dataclass, wire into `RuntimeConfig`. Resolve `-1` → `os.cpu_count()` / `max(1, cpu_count()-1)` at use site (not at load time — keeps the config value serializable/reproducible).

CLI adds `--parallelism N` and `--tls-threads N` overrides for the respective subcommands.

### 2. TLS intra-target threading

In `src/exohunt/tls.py`:
- `run_tls_search` gains `use_threads: int = 1` kwarg.
- Both `.power()` calls receive `use_threads=max(1, int(use_threads))`.

In `src/exohunt/bls.py::run_iterative_bls_search`, forward `config.tls_threads` (after resolving `-1` → cpu_count) to `run_tls_search`.

In `batch._run_one_target` (new worker function), **override to `tls_threads=1`** before invoking the pipeline. The worker constructs a modified `RuntimeConfig` with `bls.tls_threads=1` — the only use of `dataclasses.replace` on the frozen config in the batch path.

### 3. Full-jitter retry backoff

Replace in `batch.py`:
```python
wait = 30 * (2 ** attempt)
```
with:
```python
import random
wait = random.uniform(0, config.batch.retry_base_seconds * (2 ** attempt))
```

Reads `max_retries` and `retry_base_seconds` from `config.batch` instead of hardcodes.

### 4. Drop live CSVs from hot path; add `exohunt collect-live`

- Delete the call to `_append_live_candidates` from `pipeline._search_and_output_stage` (or wherever it is wired in). Delete dead code in `candidates_io.py` only if nothing else uses it; otherwise leave the function available as a library utility.
- New CLI subcommand: `exohunt collect-live --run <path> [--out <dir>]`.
  - Walks `<run>/outputs/*/candidates/*.json` (the per-target candidate JSONs).
  - Emits `<run>/candidates_live.csv` (all candidates) and `<run>/candidates_novel.csv` (filtered by `vetting_pass=True` AND not-known-alias).
  - Uses the same `_LIVE_COLS` schema so any tooling built around the old live CSVs still works.
- Tests: unit test the walk+emit logic on a fixture run dir with two targets.

### 5. `.done` sentinel + `_target_is_done` check

- At the end of `fetch_and_plot`, after the manifest stage returns, write `run_dir / "outputs" / slug / ".done"` containing the ISO timestamp.
- Add `_target_is_done(run_dir, target, completed_set) -> bool` in `batch.py`: True iff target in `completed_set` AND sentinel file exists.
- Replace `if target in completed:` (in both sequential and parallel batch paths) with `if _target_is_done(...)`.

### 6. Per-target file shard + merge for global append files

`outputs/manifests/run_manifest_index.csv` and `outputs/metrics/preprocessing_summary.csv` are global append-only files. Safe under sequential; racy under parallelism.

Under `parallelism > 1`:
- Each worker appends to a PID-sharded file: `run_manifest_index.worker-<pid>.csv`, `preprocessing_summary.worker-<pid>.csv`.
- Parent merges shards into the canonical file at batch end.

Under `parallelism == 1`: append directly to the canonical file (today's behavior).

Branch in `manifest.append_manifest_index` and `pipeline._write_preprocessing_metrics` on a new env var or kwarg `shard_writes: bool` set by the batch parent before `ProcessPoolExecutor.submit`. Simplest: env var `EXOHUNT_SHARD_WRITES=1` set by parent, read by the helper.

### 7. ProcessPoolExecutor batch loop

In `batch.py`:

- Factor per-target work into a top-level `_run_one_target(target, config_dict, run_dir, preset_meta, cache_dir, no_cache, max_download_files) -> BatchTargetStatus`.
  - Takes primitives + path + **serialized config** (dataclasses.asdict) — pickling frozen dataclasses is fine but asdict is safer against future additions.
  - Inside: reconstruct `RuntimeConfig` via `dataclasses.replace(config, bls=replace(config.bls, tls_threads=1))`, then wrap the retry-with-full-jitter loop around `fetch_and_plot`, return status.
- In `run_batch_analysis`:
  - Resolve `parallelism`: if `-1`, use `max(1, os.cpu_count()-1)`.
  - Set `os.environ["EXOHUNT_SHARD_WRITES"] = "1"` if `parallelism > 1`.
  - If `parallelism == 1`: keep existing sequential path (calls `_run_one_target` in-process).
  - Else: `ProcessPoolExecutor(max_workers=parallelism, mp_context=multiprocessing.get_context('spawn'))`; submit pending targets (skip those where `_target_is_done`); iterate `as_completed`; parent updates `state_payload`, `statuses`, progress after each future.
  - At end: merge manifest-index + preprocessing-summary shards. Unset env var.
- Add `--parallelism N` flag to `exohunt batch` CLI.
- **Determinism:** sort `run_status.csv` rows by `target` at write time (already implicit in current code; verify).

## Step-by-step

Each step is small enough for one `ft-coder` subagent call. Tests are written alongside and run at the end of each step.

### Step 1 — Config: `bls.tls_threads` + `[batch]` section

Files: `src/exohunt/config.py`, `tests/test_config.py`.

Add `tls_threads: int` to `BLSConfig` (default `-1`). Add `BatchConfig(parallelism: int, max_retries: int, retry_base_seconds: float)` with defaults `(-1, 3, 30.0)`. Wire into `RuntimeConfig`. Update `_DEFAULTS`. Handle TOML loading. Update `resolve_runtime_config` to pass through new keys.

Tests:
- Defaults resolve correctly.
- TOML round-trip for new keys.
- CLI override via `cli_overrides={"batch": {"parallelism": 4}}`.
- Invalid type on `parallelism` rejected.

### Step 2 — TLS: honor `tls_threads`

Files: `src/exohunt/tls.py`, `src/exohunt/bls.py`, `tests/test_iterative_bls.py` (or `test_smoke.py`).

- `run_tls_search(..., use_threads: int = 1)`.
- `run_iterative_bls_search` resolves `config.tls_threads`: `n = config.tls_threads if config.tls_threads > 0 else (os.cpu_count() or 1)`; forwards as `use_threads=n`.
- Test: monkeypatch `transitleastsquares` module to a fake whose `.power()` records kwargs; assert `use_threads` reflects config.

### Step 3 — Full-jitter retry backoff

Files: `src/exohunt/batch.py`, `tests/test_batch.py`.

Replace hardcoded `max_retries = 3` and `wait = 30 * (2 ** attempt)` with config-driven values and `random.uniform(0, base * 2**attempt)`.

Test: patch `time.sleep` + `random.uniform` + inject `ConnectionError` from a mocked `fetch_and_plot`; assert the correct number of retries and that each `random.uniform` call uses the right upper bound.

### Step 4 — Drop live CSVs; add `exohunt collect-live`

Files: `src/exohunt/pipeline.py` (remove `_append_live_candidates` call), `src/exohunt/candidates_io.py` (new `collect_live_from_run(run_dir)` function), `src/exohunt/cli.py` (new `collect-live` subcommand), `tests/test_batch.py` or new `tests/test_collect_live.py`.

- Remove the call site for `_append_live_candidates`.
- Implement `collect_live_from_run(run_dir: Path) -> tuple[Path, Path]`: walks `<run>/outputs/*/candidates/*.json`, writes `<run>/candidates_live.csv` and `<run>/candidates_novel.csv`. Use `_LIVE_COLS` schema.
- CLI: `exohunt collect-live --run <path>`.
- Test: create fake run dir with 2 targets × 3 candidates (1 novel); assert merged CSVs match expected.
- Verify no existing test depends on live CSVs being written during batch — if any does, update it to invoke `collect_live_from_run` after the batch.

### Step 5 — `.done` sentinel + `_target_is_done`

Files: `src/exohunt/pipeline.py`, `src/exohunt/batch.py`, `tests/test_batch.py`.

- End of `fetch_and_plot`: `(run_dir / "outputs" / slug / ".done").write_text(datetime.now(timezone.utc).isoformat())`.
- `_target_is_done(run_dir, target, completed) -> bool`: checks membership + sentinel.
- Use it in `run_batch_analysis` skip logic (applies to both sequential and upcoming parallel path).
- Test: target in `completed` set but missing sentinel → reprocessed. Target with sentinel + in completed set → skipped.

### Step 6 — Shard + merge for manifest-index and preprocessing-summary

Files: `src/exohunt/manifest.py`, `src/exohunt/pipeline.py` (`_write_preprocessing_metrics`), `src/exohunt/batch.py` (merge at end), tests.

- Both append helpers check `os.environ.get("EXOHUNT_SHARD_WRITES") == "1"`; if set, append to `<base>.worker-<pid>.csv` instead of `<base>.csv`.
- `batch._merge_shards(base_path: Path)` concatenates all `base_path.worker-*.csv` into `base_path`, then deletes shards. Header deduplicated (take from first shard, skip from rest).
- Called at end of `run_batch_analysis` for both files.
- Test: simulated two-PID writes, verify merged file and shards removed.

### Step 7 — ProcessPoolExecutor batch path

Files: `src/exohunt/batch.py`, `src/exohunt/cli.py`, `tests/test_batch.py`.

- `_run_one_target(target, config, run_dir, preset_meta, cache_dir, no_cache, max_download_files) -> BatchTargetStatus` — top-level picklable function. Forces `bls.tls_threads=1` via `dataclasses.replace`. Wraps retry-with-full-jitter around `fetch_and_plot`. Returns a `BatchTargetStatus`.
- `run_batch_analysis`:
  - Resolve `parallelism` (`-1` → `max(1, cpu_count()-1)`).
  - Set `EXOHUNT_SHARD_WRITES=1` if `parallelism > 1`.
  - If `parallelism == 1`: existing loop body, but delegating to `_run_one_target` in-process.
  - Else: `ProcessPoolExecutor(max_workers=parallelism, mp_context=multiprocessing.get_context('spawn'))`; submit pending targets; `as_completed` iteration; parent updates state + progress after each future.
  - Merge manifest + preprocessing shards at end. Unset env var.
- `cli.py`: add `--parallelism N` to `batch` subparser; plumb as `cli_overrides={"batch": {"parallelism": N}}`.
- Tests:
  - `parallelism=1` path: snapshot parity with current `test_batch.py` expectations (no regressions).
  - `parallelism=2` path with monkeypatched `fetch_and_plot` (picklable fake): correct state, status rows, done sentinels, merged shards.
  - Verify `EXOHUNT_SHARD_WRITES` is cleaned up after the batch.

### Step 8 — Full test suite + lint

- `pytest -q`
- `ruff check .`
- Coverage spot-check on changed modules.

### Step 9 — ft-reviewer + cleanup

Spawn `ft-reviewer` with modified file list and summary. Address findings. Move plan to `docs/plans/completed/`.

## Test plan (summary)

- `tests/test_config.py` — new BatchConfig + `bls.tls_threads` defaults + TOML round-trip + CLI overrides.
- `tests/test_iterative_bls.py` — TLS receives correct `use_threads` via monkeypatched `transitleastsquares`.
- `tests/test_batch.py`
  - Full-jitter backoff: patched `random.uniform` + `time.sleep` with injected failures.
  - `.done` sentinel skip logic.
  - Shard + merge for manifest/preprocessing files.
  - `parallelism=1` parity.
  - `parallelism=2` end-to-end with stub target fn.
- `tests/test_collect_live.py` — `collect_live_from_run` on a fixture run dir.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| `_run_one_target` closure captures unpicklable objects | Function is top-level. Args are primitives + frozen dataclasses + `Path`. Frozen dataclasses pickle cleanly. |
| `tls.py` module-level `set_start_method("fork")` side-effect | `ProcessPoolExecutor(mp_context=get_context('spawn'))` bypasses the global default. `spawn` works on Linux and macOS identically. |
| `EXOHUNT_SHARD_WRITES` leaks to subprocesses and sticks across runs | Parent sets before pool, unsets in `finally`. Workers inherit at spawn time (correct). Tests assert cleanup. |
| Existing tests depend on live CSVs being written during batch | Audited in Step 4; migrate those tests to call `collect_live_from_run` explicitly. |
| Shard-file merge race if batch is interrupted | Shards are ephemeral, tolerated. Next `--resume` run starts with no shards on disk (cleaned at start by deleting any `*.worker-*.csv` in the canonical dirs — add to the batch init block). |
| `run_status.csv` ordering changes under parallelism | Sort rows by `target` at write time. |

## Rollback plan

All new behavior is gated by `batch.parallelism != 1` and `bls.tls_threads != 1`. Defaults (`-1` → auto) land a real behavior change: `exohunt run` becomes multi-threaded TLS, `exohunt batch` becomes parallel. If either regresses, the user can set `tls_threads=1` / `parallelism=1` in config or via `--tls-threads 1` / `--parallelism 1`.

Live CSV removal IS a behavior change (they're no longer auto-generated during batch). Mitigated by the new `collect-live` subcommand and by calling it automatically at batch end (just like before — but from per-target JSONs, no races).

**Decision on auto-collect:** call `collect_live_from_run(run_dir)` at the end of `run_batch_analysis` so users see the same `candidates_live.csv` / `candidates_novel.csv` artifacts they see today. Only the mechanism changes (per-worker writes → walk at end).

## Acceptance criteria

1. `exohunt batch --targets-file ... --parallelism 4` completes with per-target outputs matching `--parallelism 1` on a 5-target fixture.
2. `candidates_live.csv` and `candidates_novel.csv` at batch end are produced by `collect_live_from_run`, not by in-loop appends. Content matches what the old path would have produced.
3. A worker killed mid-target does NOT mark that target completed on `--resume` (sentinel missing → reprocessed).
4. Retry log lines show full-jittered waits (not lockstep).
5. `exohunt run --target ... --tls-threads 4` measurably increases TLS CPU utilization on a single large target.
6. Full pytest suite passes; ruff clean.

## Execution results (2026-04-26)

**Single-target TLS threading (`exohunt run --tls-threads 8`):**
- TIC 317597583, iterative-search preset, 3 TLS iterations.
- Baseline `tls_threads=1`: 3063 s.
- With `tls_threads=8`: 892 s.
- **3.43× speedup.** All artifacts correct, `.done` sentinel written.

**Batch parallelism (`exohunt batch --parallelism 2`):**
- TIC 317597583 + TIC 167656187, iterative-search preset.
- Both targets completed successfully.
- Runtime: 4635 s wall clock (dominated by the slower target).
- All concurrency-safety properties verified: `.done` sentinels, PID-shard files merged into canonical CSVs, shard files cleaned up, `run_status.csv` sorted deterministically, `candidates_live.csv`/`candidates_novel.csv` auto-generated at batch end.

## macOS notes (important)

The parent sets `MPLBACKEND=Agg` in the environment before spawning workers. This is required on macOS because matplotlib's default `MacOSX` backend initializes AppKit and crashes with SIGABRT inside spawn-started child processes. The env var is inherited at spawn time, so workers pick up Agg automatically. No platform-specific branching — Linux tolerates `Agg` just fine.

`NUMBA_NUM_THREADS=1` is also set for workers. This is defensive: each worker is already forced to `tls_threads=1`, so numba's internal thread pool size is irrelevant for correctness, but keeping it at 1 avoids CPU oversubscription when `parallelism * (numba_default_threads) > cpu_count()`.

**Diagnostic tip for macOS users:** `pgrep -l -P <parent_pid> python` does NOT reliably list spawn children (returns empty even when workers are alive). Use `ps -axo pid,ppid,pcpu,etime,command | awk '$2==<parent_pid>'` instead.
