from __future__ import annotations

import csv
import json
import logging
import os
import statistics
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from exohunt import pipeline as _pipeline_mod
from exohunt.cache import DEFAULT_CACHE_DIR
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
    for idx, target in enumerate(deduped_targets, start=1):
        if target in completed:
            statuses.append(
                BatchTargetStatus(
                    run_utc=run_utc,
                    target=target,
                    status="skipped_completed",
                    error="",
                    runtime_seconds=0.0,
                    output_path="",
                )
            )
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
        max_retries = 3
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
                    break  # success
                except (OSError, ConnectionError, TimeoutError) as net_exc:
                    if attempt < max_retries:
                        wait = 30 * (2 ** attempt)
                        LOGGER.warning(
                            "Network error on %s (attempt %d/%d), retrying in %ds: %s",
                            target, attempt + 1, max_retries, wait, net_exc,
                        )
                        import time as _time
                        _time.sleep(wait)
                    else:
                        raise
        except Exception as exc:
            failed.add(target)
            errors[target] = str(exc)
            statuses.append(
                BatchTargetStatus(
                    run_utc=run_utc,
                    target=target,
                    status="failed",
                    error=str(exc),
                    runtime_seconds=float(perf_counter() - target_started),
                    output_path="",
                )
            )
            LOGGER.exception("Batch target failed: %s (%s)", target, exc)
        else:
            completed.add(target)
            failed.discard(target)
            errors.pop(target, None)
            statuses.append(
                BatchTargetStatus(
                    run_utc=run_utc,
                    target=target,
                    status="success",
                    error="",
                    runtime_seconds=float(perf_counter() - target_started),
                    output_path=str(output_path) if output_path is not None else "",
                )
            )
        finally:
            state_payload["completed_targets"] = sorted(completed)
            state_payload["failed_targets"] = sorted(failed)
            state_payload["errors"] = errors
            _save_batch_state(state_path, state_payload)
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

    return state_path, status_csv, status_json
