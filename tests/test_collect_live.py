from pathlib import Path
import json

from exohunt.candidates_io import collect_live_from_run, _is_known_period


def _write_target_json(run_dir: Path, slug: str, target: str, rows: list[dict]) -> None:
    d = run_dir / slug / "candidates"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{slug}__bls_abc123.json").write_text(
        json.dumps({
            "metadata": {"target": target},
            "candidates": rows,
        }),
        encoding="utf-8",
    )


def test_is_known_period_exact_match():
    assert _is_known_period(3.5, [3.5]) is True


def test_is_known_period_harmonic():
    assert _is_known_period(7.0, [3.5]) is True  # 2x
    assert _is_known_period(1.75, [3.5]) is True  # 0.5x


def test_is_known_period_not_matched():
    assert _is_known_period(2.0, [3.5]) is False


def test_collect_live_from_run(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_target_json(run_dir, "tic_1", "TIC 1", [
        {"rank": 1, "period_days": 3.5, "depth_ppm": 500.0, "snr": 8.0,
         "duration_hours": 2.0, "transit_time": 100.0, "iteration": 0,
         "vetting_reasons": "pass", "vetting_pass": True, "is_known": False},
        {"rank": 2, "period_days": 7.0, "depth_ppm": 300.0, "snr": 6.0,
         "duration_hours": 1.5, "transit_time": 101.0, "iteration": 0,
         "vetting_reasons": "odd_even_depth_mismatch", "vetting_pass": False, "is_known": False},
    ])
    _write_target_json(run_dir, "tic_2", "TIC 2", [
        {"rank": 1, "period_days": 2.5, "depth_ppm": 400.0, "snr": 7.5,
         "duration_hours": 1.8, "transit_time": 200.0, "iteration": 0,
         "vetting_reasons": "pass", "vetting_pass": True, "is_known": True},
    ])

    live, novel = collect_live_from_run(run_dir)

    live_rows = live.read_text().strip().splitlines()
    novel_rows = novel.read_text().strip().splitlines()

    # Header + 3 rows
    assert len(live_rows) == 4
    # Header + 1 novel (TIC 1 rank 1, not known, vetting pass)
    assert len(novel_rows) == 2
    assert "TIC 1" in novel_rows[1]


def test_collect_live_ignores_validation_json(tmp_path):
    """collect_live_from_run must skip non-candidate JSONs (e.g. __validation.json)."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    # A valid candidate JSON
    _write_target_json(run_dir, "tic_1", "TIC 1", [
        {"rank": 1, "period_days": 3.5, "depth_ppm": 500.0, "snr": 8.0,
         "duration_hours": 2.0, "transit_time": 100.0, "iteration": 0,
         "vetting_reasons": "pass", "vetting_pass": True, "is_known": False},
    ])
    # A validation JSON with a DIFFERENT schema that happens to contain a "candidates" key
    # to prove the filter catches it before it can corrupt output.
    import json as _json
    (run_dir / "tic_1" / "candidates" / "tic_1__validation.json").write_text(
        _json.dumps({"metadata": {"target": "HACKED"}, "candidates": [
            {"rank": 999, "period_days": 1.0, "depth_ppm": 0, "snr": 0,
             "duration_hours": 0, "transit_time": 0, "iteration": 0,
             "vetting_reasons": "", "vetting_pass": True, "is_known": False},
        ]}),
        encoding="utf-8",
    )
    live, _ = collect_live_from_run(run_dir)
    live_text = live.read_text()
    assert "HACKED" not in live_text
    assert "999" not in live_text
