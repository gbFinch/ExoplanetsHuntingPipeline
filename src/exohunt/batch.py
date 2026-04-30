from __future__ import annotations

import csv
import json
import logging
import os
import statistics
from dataclasses import asdict, dataclass, replace as _dc_replace
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from exohunt import pipeline as _pipeline_mod
from exohunt.cache import DEFAULT_CACHE_DIR
from exohunt.candidates_io import collect_live_from_run
from exohunt.config import PresetMeta, RuntimeConfig
from exohunt.manifest import write_run_readme
from exohunt.progress import _render_progress

LOGGER = logging.getLogger(__name__)

_BATCH_STATUS_COLUMNS = [
    "run_utc",
    "target",
    "status",
    "error",
    "runtime_seconds",
    "output_path",
]


@dataclass(frozen=True)
class BatchTargetStatus:
    run_utc: str
    target: str
    status: str
    error: str
    runtime_seconds: float
    output_path: str


def _load_batch_state(state_path: Path) -> dict[str, object]:
    if not state_path.exists():
        return {
            "schema_version": 1,
            "created_utc": datetime.now(tz=timezone.utc).isoformat(),
            "last_updated_utc": "",
            "completed_targets": [],
            "failed_targets": [],
            "errors": {},
        }
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Invalid batch state payload: {state_path}")
    payload.setdefault("schema_version", 1)
    payload.setdefault("created_utc", datetime.now(tz=timezone.utc).isoformat())
    payload.setdefault("last_updated_utc", "")
    payload.setdefault("completed_targets", [])
    payload.setdefault("failed_targets", [])
    payload.setdefault("errors", {})
    return payload


def _save_batch_state(state_path: Path, payload: dict[str, object]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload["last_updated_utc"] = datetime.now(tz=timezone.utc).isoformat()
    state_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_batch_status_report(
    status_path: Path,
    statuses: list[BatchTargetStatus],
) -> tuple[Path, Path]:
    statuses = sorted(statuses, key=lambda s: s.target)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    with status_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=_BATCH_STATUS_COLUMNS)
        writer.writeheader()
        for item in statuses:
            writer.writerow(asdict(item))
    json_path = status_path.with_suffix(".json")
    json_path.write_text(
        json.dumps([asdict(item) for item in statuses], indent=2, sort_keys=True), encoding="utf-8"
    )
    return status_path, json_path


_PROGRESS_ROLLING_WINDOW = 10


def _format_duration(seconds: float | None) -> str:
    if seconds is None or not (seconds >= 0):
        return 'n/a'
    s = int(seconds)
    if s < 60:
        return f'{s}s'
    if s < 3600:
        return f'{s // 60}m {s % 60:02d}s'
    h, rem = divmod(s, 3600)
    return f'{h}h {rem // 60:02d}m'


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
    run_dir.mkdir(parents=True, exist_ok=True)
    recent_success_runtimes = [
        s.runtime_seconds for s in statuses[-_PROGRESS_ROLLING_WINDOW:]
        if s.status == 'success'
    ]
    rolling_mean = (
        statistics.mean(recent_success_runtimes) if recent_success_runtimes else None
    )
    remaining = max(0, total - processed)
    eta_seconds = rolling_mean * remaining if rolling_mean is not None else None
    last_5 = [
        {'target': s.target, 'status': s.status, 'runtime_seconds': s.runtime_seconds,
         **({'error': s.error} if s.error else {})}
        for s in statuses[-5:]
    ]
    percent = (100.0 * processed / total) if total > 0 else 0.0
    now_utc = datetime.now(tz=timezone.utc).isoformat()

    json_payload = {
        'schema_version': 1,
        'run_id': run_id,
        'run_started_utc': run_started_utc,
        'last_updated_utc': now_utc,
        'total': total,
        'processed': processed,
        'successes': successes,
        'failures': failures,
        'skipped_completed': skipped,
        'percent_complete': round(percent, 1),
        'current_target': current_target,
        'elapsed_seconds': round(elapsed_seconds, 1),
        'rolling_mean_runtime_seconds': (
            round(rolling_mean, 1) if rolling_mean is not None else None
        ),
        'eta_seconds': round(eta_seconds, 1) if eta_seconds is not None else None,
        'last_5_statuses': last_5,
    }
    json_path = run_dir / 'progress.json'
    json_tmp = run_dir / 'progress.json.tmp'
    json_tmp.write_text(json.dumps(json_payload, indent=2, sort_keys=True), encoding='utf-8')
    os.replace(json_tmp, json_path)

    txt_lines = [
        'Exohunt batch progress',
        '======================',
        f'Run: {run_id}',
        f'Started: {run_started_utc}',
        f'Updated: {now_utc}',
        '',
        f'Progress: {processed} / {total}  ({percent:.1f}%)',
        f'  ✓ {successes} succeeded',
        f'  ✗ {failures} failed',
        f'  → {skipped} skipped (prior runs)',
        '',
        f'Current: {current_target or "(idle)"}',
        f'Elapsed: {_format_duration(elapsed_seconds)}',
        f'ETA:     {_format_duration(eta_seconds)}',
    ]
    if rolling_mean is not None:
        txt_lines.append(
            f'(based on rolling mean of last '
            f'{len(recent_success_runtimes)} runs: {rolling_mean:.1f}s/target)'
        )
    txt_lines.append('')
    txt_lines.append('Recent targets (last 5):')
    status_symbol = {'success': '✓', 'failed': '✗', 'skipped_completed': '→'}
    for s in statuses[-5:]:
        sym = status_symbol.get(s.status, '?')
        line = f'  {sym} {s.target:20s} ({s.runtime_seconds:.1f}s)'
        if s.error:
            line += f'   {s.error}'
        txt_lines.append(line)
    txt = '\n'.join(txt_lines) + '\n'
    txt_path = run_dir / 'progress.txt'
    txt_tmp = run_dir / 'progress.txt.tmp'
    txt_tmp.write_text(txt, encoding='utf-8')
    os.replace(txt_tmp, txt_path)


def _merge_shards(canonical: Path) -> None:
    """Concatenate <canonical>.worker-*.csv shards into <canonical> and remove them."""
    import glob
    stem = canonical.stem
    pattern = str(canonical.with_name(f"{stem}.worker-*{canonical.suffix}"))
    shards = sorted(glob.glob(pattern))
    if not shards:
        return
    canonical.parent.mkdir(parents=True, exist_ok=True)
    canonical_exists = canonical.exists()
    with canonical.open("a", encoding="utf-8") as out:
        for i, shard in enumerate(shards):
            try:
                with open(shard, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            except OSError:
                continue
            if not lines:
                continue
            start = 1 if (canonical_exists or i > 0) else 0
            out.writelines(lines[start:])
            canonical_exists = True
            try:
                Path(shard).unlink()
            except OSError:
                pass


def _target_is_done(run_dir: Path, target: str, completed: set[str]) -> bool:
    """True iff target is in completed set AND .done sentinel exists."""
    if target not in completed:
        return False
    from exohunt.cache import _target_output_dir
    return (_target_output_dir(target, run_dir) / ".done").exists()


def _resolve_parallelism(n: int) -> int:
    """Resolve config.batch.parallelism sentinel. -1 => max(1, cpu_count()-1)."""
    if n > 0:
        return n
    cpu = os.cpu_count() or 1
    return max(1, cpu - 1)


def _run_one_target(
    target: str,
    config: RuntimeConfig,
    run_dir: Path,
    preset_meta: PresetMeta | None,
    cache_dir: Path,
    no_cache: bool,
    max_download_files: int | None,
) -> tuple[str, str, str, str]:
    """Run fetch_and_plot for one target with full-jitter retries.

    Returns (status, output_path, error_str, target) where status is
    'success' or 'failed'. Picklable; runs in any process.
    """
    import random as _random
    import time as _time

    max_retries = int(config.batch.max_retries)
    base_seconds = float(config.batch.retry_base_seconds)

    try:
        for attempt in range(max_retries + 1):
            try:
                output_path = _pipeline_mod.fetch_and_plot(
                    target=target,
                    config=config,
                    run_dir=run_dir,
                    preset_meta=preset_meta,
                    cache_dir=cache_dir,
                    no_cache=no_cache,
                    max_download_files=max_download_files,
                )
                return ("success", str(output_path) if output_path else "", "", target)
            except (OSError, ConnectionError, TimeoutError) as net_exc:
                if attempt < max_retries:
                    wait = _random.uniform(0, base_seconds * (2 ** attempt))
                    LOGGER.warning(
                        "Network error on %s (attempt %d/%d), retrying in %.1fs: %s",
                        target, attempt + 1, max_retries, wait, net_exc,
                    )
                    _time.sleep(wait)
                else:
                    raise
    except Exception as exc:
        LOGGER.exception("Batch target failed: %s (%s)", target, exc)
        return ("failed", "", str(exc), target)
    return ("failed", "", "unknown error", target)


def _record_result(
    statuses: list[BatchTargetStatus],
    state_payload: dict,
    state_path: Path,
    completed: set[str],
    failed: set[str],
    errors: dict,
    *,
    target: str,
    status: str,
    output_path: str,
    error_str: str,
    runtime: float,
    run_utc: str,
) -> None:
    """Append a status row, update batch state, persist to disk. Parent-only."""
    if status == "success":
        completed.add(target)
        failed.discard(target)
        errors.pop(target, None)
    else:
        failed.add(target)
        errors[target] = error_str
    statuses.append(BatchTargetStatus(
        run_utc=run_utc, target=target, status=status,
        error=error_str, runtime_seconds=float(runtime),
        output_path=output_path,
    ))
    state_payload["completed_targets"] = sorted(completed)
    state_payload["failed_targets"] = sorted(failed)
    state_payload["errors"] = errors
    _save_batch_state(state_path, state_payload)


def run_batch_analysis(
    targets: list[str],
    config: RuntimeConfig,
    run_dir: Path,
    preset_meta: PresetMeta | None = None,
    *,
    no_cache: bool = False,
    cache_dir: Path | None = None,
    max_download_files: int | None = None,
) -> tuple[Path, Path, Path]:
    """Run analysis for many targets with failure isolation and resumable state.

    Theory: batch workflows should make forward progress even when individual
    targets fail. Persisting per-target completion state enables resumability,
    while a status report captures deterministic run outcomes for auditing.
    """
    unique_targets = [item.strip() for item in targets if item.strip()]
    cache_dir = cache_dir or DEFAULT_CACHE_DIR
    deduped_targets: list[str] = []
    seen: set[str] = set()
    for target in unique_targets:
        if target in seen:
            continue
        deduped_targets.append(target)
        seen.add(target)

    run_dir.mkdir(parents=True, exist_ok=True)
    state_path = run_dir / "run_state.json"
    status_path = run_dir / "run_status.csv"
    state_payload = _load_batch_state(state_path)
    completed = set(str(item) for item in state_payload.get("completed_targets", []))
    failed = set(str(item) for item in state_payload.get("failed_targets", []))
    errors = dict(state_payload.get("errors", {}))

    statuses: list[BatchTargetStatus] = []
    run_utc = datetime.now(tz=timezone.utc).isoformat()
    _batch_start = perf_counter()
    total = len(deduped_targets)
    parallelism = _resolve_parallelism(int(config.batch.parallelism))
    LOGGER.info("Batch parallelism: %d worker(s)", parallelism)

    if parallelism > 1:
        worker_config = _dc_replace(config, bls=_dc_replace(config.bls, tls_threads=1))
        _prev_shard_env = os.environ.get("EXOHUNT_SHARD_WRITES")
        _prev_mpl_backend = os.environ.get("MPLBACKEND")
        _prev_numba_threads = os.environ.get("NUMBA_NUM_THREADS")
        os.environ["EXOHUNT_SHARD_WRITES"] = "1"
        # Force non-GUI matplotlib backend in workers. macOS's default `MacOSX`
        # backend initializes AppKit, which crashes (SIGABRT) when imported in
        # a spawn()-ed subprocess. Agg is headless and safe in any process.
        os.environ["MPLBACKEND"] = "Agg"
        # Serialize numba in workers. TLS uses numba; if each worker has its own
        # numba thread pool AND parallelism > 1, the interaction with spawn's
        # process teardown can hang the parent waiting on worker results.
        os.environ["NUMBA_NUM_THREADS"] = "1"
    else:
        worker_config = config
        _prev_shard_env = None
        _prev_mpl_backend = None
        _prev_numba_threads = None

    try:
        if parallelism <= 1:
            for idx, target in enumerate(deduped_targets, start=1):
                if _target_is_done(run_dir, target, completed):
                    statuses.append(BatchTargetStatus(
                        run_utc=run_utc, target=target, status="skipped_completed",
                        error="", runtime_seconds=0.0, output_path="",
                    ))
                    _render_progress("Batch targets", idx, total)
                    continue
                try:
                    _write_progress(
                        run_dir, run_id=run_dir.name, run_started_utc=run_utc,
                        total=total, processed=idx - 1,
                        successes=sum(1 for s in statuses if s.status == 'success'),
                        failures=sum(1 for s in statuses if s.status == 'failed'),
                        skipped=sum(1 for s in statuses if s.status == 'skipped_completed'),
                        current_target=target, elapsed_seconds=perf_counter() - _batch_start,
                        statuses=statuses,
                    )
                except Exception as exc:
                    LOGGER.warning('Failed to write progress: %s', exc)

                target_started = perf_counter()
                status, output_path, error_str, _ = _run_one_target(
                    target, worker_config, run_dir, preset_meta,
                    cache_dir, no_cache, max_download_files,
                )
                _record_result(
                    statuses, state_payload, state_path,
                    completed, failed, errors,
                    target=target, status=status, output_path=output_path,
                    error_str=error_str, runtime=perf_counter() - target_started,
                    run_utc=run_utc,
                )
                try:
                    _write_progress(
                        run_dir, run_id=run_dir.name, run_started_utc=run_utc,
                        total=total, processed=idx,
                        successes=sum(1 for s in statuses if s.status == 'success'),
                        failures=sum(1 for s in statuses if s.status == 'failed'),
                        skipped=sum(1 for s in statuses if s.status == 'skipped_completed'),
                        current_target=None, elapsed_seconds=perf_counter() - _batch_start,
                        statuses=statuses,
                    )
                except Exception as exc:
                    LOGGER.warning('Failed to write progress: %s', exc)
                _render_progress("Batch targets", idx, total)
        else:
            from concurrent.futures import ProcessPoolExecutor, as_completed
            import multiprocessing

            pending: list[str] = []
            for target in deduped_targets:
                if _target_is_done(run_dir, target, completed):
                    statuses.append(BatchTargetStatus(
                        run_utc=run_utc, target=target, status="skipped_completed",
                        error="", runtime_seconds=0.0, output_path="",
                    ))
                else:
                    pending.append(target)

            target_start_times: dict[str, float] = {}
            ctx = multiprocessing.get_context('spawn')
            with ProcessPoolExecutor(max_workers=parallelism, mp_context=ctx) as pool:
                future_to_target = {}
                for target in pending:
                    target_start_times[target] = perf_counter()
                    fut = pool.submit(
                        _run_one_target, target, worker_config, run_dir, preset_meta,
                        cache_dir, no_cache, max_download_files,
                    )
                    future_to_target[fut] = target

                processed_count = len(statuses)
                for fut in as_completed(future_to_target):
                    target = future_to_target[fut]
                    try:
                        status, output_path, error_str, _ = fut.result()
                    except Exception as exc:
                        status, output_path, error_str = "failed", "", str(exc)
                    runtime = perf_counter() - target_start_times[target]
                    _record_result(
                        statuses, state_payload, state_path,
                        completed, failed, errors,
                        target=target, status=status, output_path=output_path,
                        error_str=error_str, runtime=runtime, run_utc=run_utc,
                    )
                    processed_count += 1
                    try:
                        _write_progress(
                            run_dir, run_id=run_dir.name, run_started_utc=run_utc,
                            total=total, processed=processed_count,
                            successes=sum(1 for s in statuses if s.status == 'success'),
                            failures=sum(1 for s in statuses if s.status == 'failed'),
                            skipped=sum(1 for s in statuses if s.status == 'skipped_completed'),
                            current_target=None,
                            elapsed_seconds=perf_counter() - _batch_start,
                            statuses=statuses,
                        )
                    except Exception as exc:
                        LOGGER.warning('Failed to write progress: %s', exc)
                    _render_progress("Batch targets", processed_count, total)
    finally:
        if parallelism > 1:
            if _prev_shard_env is None:
                os.environ.pop("EXOHUNT_SHARD_WRITES", None)
            else:
                os.environ["EXOHUNT_SHARD_WRITES"] = _prev_shard_env
            if _prev_mpl_backend is None:
                os.environ.pop("MPLBACKEND", None)
            else:
                os.environ["MPLBACKEND"] = _prev_mpl_backend

    status_csv, status_json = _write_batch_status_report(status_path, statuses)
    LOGGER.info("Batch run complete: %d targets", total)
    LOGGER.info("Batch state: %s", state_path)
    LOGGER.info("Batch status CSV: %s", status_csv)
    LOGGER.info("Batch status JSON: %s", status_json)

    finished_utc = datetime.now(tz=timezone.utc).isoformat()
    total_runtime = perf_counter() - _batch_start
    try:
        write_run_readme(
            run_dir, config, preset_meta,
            targets=deduped_targets,
            started_utc=run_utc, finished_utc=finished_utc,
            runtime_seconds=total_runtime,
            success_count=len(completed), failure_count=len(failed),
            errors=errors,
        )
    except Exception as exc:
        LOGGER.warning("Failed to write run README: %s", exc)

    try:
        collect_live_from_run(run_dir)
    except Exception as exc:
        LOGGER.warning("Failed to collect live candidates: %s", exc)

    try:
        _merge_shards(run_dir / "run_manifest_index.csv")
        _merge_shards(run_dir / "preprocessing_summary.csv")
    except Exception as exc:
        LOGGER.warning("Failed to merge worker shards: %s", exc)

    return state_path, status_csv, status_json
