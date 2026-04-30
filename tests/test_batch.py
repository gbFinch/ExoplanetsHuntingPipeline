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


def test_retry_uses_full_jitter(monkeypatch, tmp_path):
    """Retry backoff uses random.uniform(0, base * 2**attempt), not lockstep.

    NOTE: This test exercises the sequential in-process path (parallelism=1 via
    _run_one_target). The monkeypatches on `time.sleep` and `random.uniform`
    at the module level work because Python's `import random` inside a function
    body returns the same module object that was monkeypatched. If this test
    ever exercises the parallel ProcessPoolExecutor path, the monkeypatch would
    NOT propagate to spawned workers, and the test would need restructuring.
    """
    from exohunt import batch as batch_mod
    from exohunt import pipeline
    from exohunt.config import resolve_runtime_config

    config = resolve_runtime_config(
        cli_overrides={"batch": {"max_retries": 2, "retry_base_seconds": 10.0, "parallelism": 1}},
    )

    sleep_calls: list[float] = []
    uniform_calls: list[tuple[float, float]] = []
    call_count = [0]

    def _fake_sleep(seconds):
        sleep_calls.append(float(seconds))

    def _fake_uniform(a, b):
        uniform_calls.append((a, b))
        return b  # deterministic: return the upper bound

    def _fake_fetch(target, config, run_dir, preset_meta=None, **kwargs):
        call_count[0] += 1
        if call_count[0] < 3:
            raise ConnectionError("simulated network failure")
        return tmp_path / "ok.txt"

    monkeypatch.setattr("time.sleep", _fake_sleep)
    monkeypatch.setattr("random.uniform", _fake_uniform)
    monkeypatch.setattr(pipeline, "fetch_and_plot", _fake_fetch)

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    batch_mod.run_batch_analysis(
        targets=["TIC 1"], config=config, run_dir=run_dir,
    )

    # Attempt 0 failed → wait uniform(0, 10*1)=10
    # Attempt 1 failed → wait uniform(0, 10*2)=20
    # Attempt 2 succeeded → no wait
    assert uniform_calls == [(0, 10.0), (0, 20.0)]
    assert sleep_calls == [10.0, 20.0]
    assert call_count[0] == 3


def test_retry_respects_max_retries(monkeypatch, tmp_path):
    """After max_retries, failures are recorded as failed, not infinite loop."""
    from exohunt import batch as batch_mod
    from exohunt import pipeline
    from exohunt.config import resolve_runtime_config

    config = resolve_runtime_config(
        cli_overrides={"batch": {"max_retries": 1, "retry_base_seconds": 1.0, "parallelism": 1}},
    )

    def _always_fail(target, config, run_dir, preset_meta=None, **kwargs):
        raise ConnectionError("persistent")

    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setattr("random.uniform", lambda a, b: 0.0)
    monkeypatch.setattr(pipeline, "fetch_and_plot", _always_fail)

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    state_path, status_csv, _ = batch_mod.run_batch_analysis(
        targets=["TIC 1"], config=config, run_dir=run_dir,
    )

    state = json.loads(state_path.read_text())
    assert "TIC 1" in state["failed_targets"]
    assert "TIC 1" not in state["completed_targets"]


def test_batch_calls_collect_live(monkeypatch, tmp_path):
    """run_batch_analysis auto-calls collect_live_from_run at the end."""
    from exohunt import batch as batch_mod
    from exohunt import pipeline
    from exohunt.config import resolve_runtime_config

    config = resolve_runtime_config(cli_overrides={"batch": {"parallelism": 1}})
    called_with = []

    def _fake_fetch(target, config, run_dir, preset_meta=None, **kwargs):
        return None

    def _fake_collect(run_dir):
        called_with.append(run_dir)
        return run_dir / "candidates_live.csv", run_dir / "candidates_novel.csv"

    monkeypatch.setattr(pipeline, "fetch_and_plot", _fake_fetch)
    monkeypatch.setattr(batch_mod, "collect_live_from_run", _fake_collect)

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    batch_mod.run_batch_analysis(
        targets=["TIC 1"], config=config, run_dir=run_dir,
    )
    assert len(called_with) == 1
    assert called_with[0] == run_dir


def test_done_sentinel_written_after_success(monkeypatch, tmp_path):
    """Successful fetch_and_plot writes a .done sentinel in the target dir."""
    from exohunt import batch as batch_mod
    from exohunt.cache import _target_output_dir
    from exohunt.config import resolve_runtime_config

    config = resolve_runtime_config(cli_overrides={"batch": {"parallelism": 1}})
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    def _fake_fetch(*, target, run_dir, **kwargs):
        out = _target_output_dir(target, run_dir)
        out.mkdir(parents=True, exist_ok=True)
        from datetime import datetime, timezone
        (out / ".done").write_text(datetime.now(tz=timezone.utc).isoformat())
        return out

    monkeypatch.setattr(batch_mod._pipeline_mod, "fetch_and_plot", _fake_fetch)
    batch_mod.run_batch_analysis(targets=["TIC 1"], config=config, run_dir=run_dir)

    assert (_target_output_dir("TIC 1", run_dir) / ".done").exists()


def test_resume_reprocesses_target_without_sentinel(monkeypatch, tmp_path):
    """A target in state.completed_targets but missing .done sentinel is re-run."""
    from exohunt import batch as batch_mod
    from exohunt.cache import _target_output_dir
    from exohunt.config import resolve_runtime_config
    import json

    config = resolve_runtime_config(cli_overrides={"batch": {"parallelism": 1}})
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    state = {
        "schema_version": 1, "created_utc": "2026-01-01T00:00:00+00:00",
        "last_updated_utc": "2026-01-01T00:00:00+00:00",
        "completed_targets": ["TIC 1"], "failed_targets": [], "errors": {},
    }
    (run_dir / "run_state.json").write_text(json.dumps(state))

    calls = []
    def _fake_fetch(*, target, run_dir, **kwargs):
        calls.append(target)
        out = _target_output_dir(target, run_dir)
        out.mkdir(parents=True, exist_ok=True)
        from datetime import datetime, timezone
        (out / ".done").write_text(datetime.now(tz=timezone.utc).isoformat())
        return out

    monkeypatch.setattr(batch_mod._pipeline_mod, "fetch_and_plot", _fake_fetch)
    batch_mod.run_batch_analysis(targets=["TIC 1"], config=config, run_dir=run_dir)

    assert calls == ["TIC 1"]


def test_resume_skips_target_with_sentinel(monkeypatch, tmp_path):
    """A target in state.completed_targets WITH a .done sentinel is skipped."""
    from exohunt import batch as batch_mod
    from exohunt.cache import _target_output_dir
    from exohunt.config import resolve_runtime_config
    import json

    config = resolve_runtime_config(cli_overrides={"batch": {"parallelism": 1}})
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    state = {
        "schema_version": 1, "created_utc": "2026-01-01T00:00:00+00:00",
        "last_updated_utc": "2026-01-01T00:00:00+00:00",
        "completed_targets": ["TIC 1"], "failed_targets": [], "errors": {},
    }
    (run_dir / "run_state.json").write_text(json.dumps(state))
    out = _target_output_dir("TIC 1", run_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / ".done").write_text("2026-01-01T00:00:00+00:00")

    calls = []
    def _fake_fetch(*, target, run_dir, **kwargs):
        calls.append(target)
        return out

    monkeypatch.setattr(batch_mod._pipeline_mod, "fetch_and_plot", _fake_fetch)
    batch_mod.run_batch_analysis(targets=["TIC 1"], config=config, run_dir=run_dir)

    assert calls == []


def test_shard_path_routes_when_env_set(monkeypatch, tmp_path):
    from exohunt.manifest import _shard_path_if_requested
    canonical = tmp_path / "run_manifest_index.csv"
    monkeypatch.delenv("EXOHUNT_SHARD_WRITES", raising=False)
    assert _shard_path_if_requested(canonical) == canonical
    monkeypatch.setenv("EXOHUNT_SHARD_WRITES", "1")
    sharded = _shard_path_if_requested(canonical)
    import os
    assert sharded.name == f"run_manifest_index.worker-{os.getpid()}.csv"


def test_merge_shards_concatenates_and_removes(tmp_path):
    from exohunt.batch import _merge_shards
    canonical = tmp_path / "foo.csv"
    shard1 = tmp_path / "foo.worker-1234.csv"
    shard2 = tmp_path / "foo.worker-5678.csv"
    shard1.write_text("col_a,col_b\n1,2\n3,4\n")
    shard2.write_text("col_a,col_b\n5,6\n")

    _merge_shards(canonical)

    merged = canonical.read_text()
    assert merged.startswith("col_a,col_b\n")
    assert "1,2\n" in merged and "3,4\n" in merged and "5,6\n" in merged
    assert merged.count("col_a,col_b") == 1
    assert not shard1.exists() and not shard2.exists()


def test_merge_shards_no_op_when_absent(tmp_path):
    from exohunt.batch import _merge_shards
    canonical = tmp_path / "foo.csv"
    _merge_shards(canonical)
    assert not canonical.exists()


def test_merge_shards_appends_to_existing_canonical(tmp_path):
    """If canonical already has a header + rows, shard rows are appended without duplicating header."""
    from exohunt.batch import _merge_shards
    canonical = tmp_path / "foo.csv"
    canonical.write_text("col_a,col_b\nexisting,row\n")
    shard = tmp_path / "foo.worker-1234.csv"
    shard.write_text("col_a,col_b\nnew,row\n")
    _merge_shards(canonical)
    merged = canonical.read_text()
    assert merged.count("col_a,col_b") == 1
    assert "existing,row" in merged and "new,row" in merged
    assert not shard.exists()


def test_resolve_parallelism_auto():
    from exohunt.batch import _resolve_parallelism
    import os
    cpu = os.cpu_count() or 1
    assert _resolve_parallelism(-1) == max(1, cpu - 1)
    assert _resolve_parallelism(1) == 1
    assert _resolve_parallelism(4) == 4


def test_parallelism_1_preserves_sequential_behavior(monkeypatch, tmp_path):
    """parallelism=1 must produce identical state to today's code path."""
    from exohunt import batch as batch_mod
    from exohunt.cache import _target_output_dir
    from exohunt.config import resolve_runtime_config
    import json

    config = resolve_runtime_config(cli_overrides={"batch": {"parallelism": 1}})

    def _fake_fetch(*, target, run_dir, **kwargs):
        out = _target_output_dir(target, run_dir)
        out.mkdir(parents=True, exist_ok=True)
        from datetime import datetime, timezone
        (out / ".done").write_text(datetime.now(tz=timezone.utc).isoformat())
        return out
    monkeypatch.setattr(batch_mod._pipeline_mod, "fetch_and_plot", _fake_fetch)

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    state_path, status_csv, status_json = batch_mod.run_batch_analysis(
        targets=["TIC 1", "TIC 2"], config=config, run_dir=run_dir,
    )

    state = json.loads(state_path.read_text())
    assert state["completed_targets"] == ["TIC 1", "TIC 2"]
    assert state["failed_targets"] == []


def test_status_csv_is_target_sorted(monkeypatch, tmp_path):
    """run_status.csv rows are sorted by target for deterministic output."""
    from exohunt import batch as batch_mod
    from exohunt.cache import _target_output_dir
    from exohunt.config import resolve_runtime_config
    import csv

    config = resolve_runtime_config(cli_overrides={"batch": {"parallelism": 1}})

    def _fake_fetch(*, target, run_dir, **kwargs):
        out = _target_output_dir(target, run_dir)
        out.mkdir(parents=True, exist_ok=True)
        from datetime import datetime, timezone
        (out / ".done").write_text(datetime.now(tz=timezone.utc).isoformat())
        return out
    monkeypatch.setattr(batch_mod._pipeline_mod, "fetch_and_plot", _fake_fetch)

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    batch_mod.run_batch_analysis(
        targets=["TIC Z", "TIC A", "TIC M"], config=config, run_dir=run_dir,
    )

    rows = list(csv.DictReader((run_dir / "run_status.csv").open()))
    targets = [r["target"] for r in rows]
    assert targets == sorted(targets)


def test_run_one_target_success(monkeypatch, tmp_path):
    from exohunt import batch as batch_mod
    from exohunt.config import resolve_runtime_config

    config = resolve_runtime_config()
    def _fake_fetch(**kwargs):
        return tmp_path / "out.txt"
    monkeypatch.setattr(batch_mod._pipeline_mod, "fetch_and_plot", _fake_fetch)

    result = batch_mod._run_one_target(
        "TIC 1", config, tmp_path, None, tmp_path, False, None,
    )
    assert result[0] == "success"
    assert result[3] == "TIC 1"


def test_run_one_target_failure_after_max_retries(monkeypatch, tmp_path):
    from exohunt import batch as batch_mod
    from exohunt.config import resolve_runtime_config

    config = resolve_runtime_config(cli_overrides={"batch": {"max_retries": 1, "retry_base_seconds": 0.01}})
    def _fake_fetch(**kwargs):
        raise ConnectionError("permanent")
    monkeypatch.setattr(batch_mod._pipeline_mod, "fetch_and_plot", _fake_fetch)
    monkeypatch.setattr("time.sleep", lambda s: None)

    result = batch_mod._run_one_target(
        "TIC 1", config, tmp_path, None, tmp_path, False, None,
    )
    assert result[0] == "failed"
    assert "permanent" in result[2]