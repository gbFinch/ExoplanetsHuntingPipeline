"""Tests for _write_progress (Plan 006)."""
from __future__ import annotations

import json

from exohunt.batch import BatchTargetStatus, _write_progress


def _make_status(target="TIC 1", status="success", runtime=100.0, error=""):
    return BatchTargetStatus(
        run_utc="2026-01-01T00:00:00+00:00",
        target=target, status=status, error=error,
        runtime_seconds=runtime, output_path="",
    )


_COMMON = dict(
    run_id="test_run",
    run_started_utc="2026-01-01T00:00:00+00:00",
    total=50,
    processed=23,
    successes=20,
    failures=3,
    skipped=0,
    current_target="TIC 99",
    elapsed_seconds=1200.0,
)

_REQUIRED_KEYS = {
    "schema_version", "run_id", "run_started_utc", "last_updated_utc",
    "total", "processed", "successes", "failures", "skipped_completed",
    "percent_complete", "current_target", "elapsed_seconds",
    "rolling_mean_runtime_seconds", "eta_seconds", "last_5_statuses",
}


def test_progress_files_created(tmp_path):
    _write_progress(tmp_path, **_COMMON, statuses=[])
    assert (tmp_path / "progress.json").exists()
    assert (tmp_path / "progress.txt").exists()


def test_progress_json_schema(tmp_path):
    _write_progress(tmp_path, **_COMMON, statuses=[])
    data = json.loads((tmp_path / "progress.json").read_text())
    assert _REQUIRED_KEYS <= set(data.keys())


def test_progress_eta_with_rolling_mean(tmp_path):
    statuses = [_make_status(runtime=r) for r in [100.0, 90.0, 110.0]]
    _write_progress(
        tmp_path, run_id="r", run_started_utc="x",
        total=10, processed=3, successes=3, failures=0, skipped=0,
        current_target=None, elapsed_seconds=300.0, statuses=statuses,
    )
    data = json.loads((tmp_path / "progress.json").read_text())
    assert data["rolling_mean_runtime_seconds"] == 100.0
    assert data["eta_seconds"] == 700.0  # 100 * 7


def test_progress_eta_none_with_no_history(tmp_path):
    _write_progress(
        tmp_path, run_id="r", run_started_utc="x",
        total=10, processed=0, successes=0, failures=0, skipped=0,
        current_target=None, elapsed_seconds=0.0, statuses=[],
    )
    data = json.loads((tmp_path / "progress.json").read_text())
    assert data["eta_seconds"] is None
    assert data["rolling_mean_runtime_seconds"] is None


def test_progress_atomic_replacement(tmp_path):
    _write_progress(
        tmp_path, run_id="r", run_started_utc="x",
        total=10, processed=1, successes=1, failures=0, skipped=0,
        current_target=None, elapsed_seconds=10.0,
        statuses=[_make_status()],
    )
    _write_progress(
        tmp_path, run_id="r", run_started_utc="x",
        total=10, processed=5, successes=5, failures=0, skipped=0,
        current_target=None, elapsed_seconds=50.0,
        statuses=[_make_status()] * 5,
    )
    assert not (tmp_path / "progress.json.tmp").exists()
    assert not (tmp_path / "progress.txt.tmp").exists()
    data = json.loads((tmp_path / "progress.json").read_text())
    assert data["processed"] == 5


def test_progress_renders_percent(tmp_path):
    _write_progress(
        tmp_path, run_id="r", run_started_utc="x",
        total=50, processed=23, successes=20, failures=3, skipped=0,
        current_target=None, elapsed_seconds=100.0, statuses=[],
    )
    txt = (tmp_path / "progress.txt").read_text()
    assert "46.0%" in txt
