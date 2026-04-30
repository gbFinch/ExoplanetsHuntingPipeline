from __future__ import annotations

import csv
import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from exohunt.bls import BLSCandidate
from exohunt.cache import content_hash, _safe_target_name, _target_artifact_dir
from exohunt.parameters import CandidateParameterEstimate
from exohunt.vetting import CandidateVettingResult

LOGGER = logging.getLogger(__name__)

_CANDIDATE_COLUMNS = [
    "rank",
    "period_days",
    "duration_hours",
    "depth",
    "depth_ppm",
    "power",
    "transit_time",
    "transit_count_estimate",
    "snr",
    "fap",
    "iteration",
    "radius_ratio_rp_over_rs",
    "radius_earth_radii_solar_assumption",
    "duration_expected_hours_central_solar_density",
    "duration_ratio_observed_to_expected",
    "pass_duration_plausibility",
    "parameter_assumptions",
    "parameter_uncertainty_caveats",
    "pass_min_transit_count",
    "pass_odd_even_depth",
    "pass_alias_harmonic",
    "pass_secondary_eclipse",
    "pass_depth_consistency",
    "vetting_pass",
    "transit_count_observed",
    "odd_depth_ppm",
    "even_depth_ppm",
    "odd_even_depth_mismatch_fraction",
    "secondary_eclipse_depth_fraction",
    "depth_consistency_fraction",
    "alias_harmonic_with_rank",
    "vetting_reasons",
    "odd_even_status",
    "is_known",
]


def _candidate_output_key(
    target: str,
    preprocess_mode: str,
    preprocess_enabled: bool,
    outlier_sigma: float,
    flatten_window_length: int,
    no_flatten: bool,
    run_bls: bool,
    bls_period_min_days: float,
    bls_period_max_days: float,
    bls_duration_min_hours: float,
    bls_duration_max_hours: float,
    bls_n_periods: int,
    bls_n_durations: int,
    bls_top_n: int,
    authors: str | None,
    n_points_prepared: int,
    time_min: float,
    time_max: float,
) -> str:
    payload = {
        "version": 1,
        "target": target,
        "preprocess_mode": preprocess_mode,
        "preprocess_enabled": bool(preprocess_enabled),
        "outlier_sigma": round(float(outlier_sigma), 6),
        "flatten_window_length": int(flatten_window_length),
        "no_flatten": bool(no_flatten),
        "run_bls": bool(run_bls),
        "bls_period_min_days": round(float(bls_period_min_days), 6),
        "bls_period_max_days": round(float(bls_period_max_days), 6),
        "bls_duration_min_hours": round(float(bls_duration_min_hours), 6),
        "bls_duration_max_hours": round(float(bls_duration_max_hours), 6),
        "bls_n_periods": int(bls_n_periods),
        "bls_n_durations": int(bls_n_durations),
        "bls_top_n": int(bls_top_n),
        "authors": authors or "",
        "n_points_prepared": int(n_points_prepared),
        "time_min": round(float(time_min), 7),
        "time_max": round(float(time_max), 7),
    }
    return content_hash(payload, length=12)


def _write_bls_candidates(
    target: str,
    output_key: str,
    metadata: dict[str, str | int | float | bool],
    candidates: list[BLSCandidate],
    vetting_by_rank: dict[int, CandidateVettingResult] | None = None,
    parameter_estimates_by_rank: dict[int, CandidateParameterEstimate] | None = None,
    *,
    run_dir: Path,
    known_periods: list[float] | None = None,
) -> tuple[Path, Path]:
    output_dir = _target_artifact_dir(target, "candidates", outputs_root=run_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    base_name = f"{_safe_target_name(target)}__bls_{output_key}"
    csv_path = output_dir / f"{base_name}.csv"
    json_path = output_dir / f"{base_name}.json"

    csv_columns = list(metadata.keys()) + _CANDIDATE_COLUMNS
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=csv_columns)
        writer.writeheader()
        for candidate in candidates:
            row = dict(metadata)
            row.update(asdict(candidate))
            parameter_estimate = (parameter_estimates_by_rank or {}).get(int(candidate.rank))
            if parameter_estimate is not None:
                row.update(asdict(parameter_estimate))
            else:
                row.update(
                    {
                        "radius_ratio_rp_over_rs": None,
                        "radius_earth_radii_solar_assumption": None,
                        "duration_expected_hours_central_solar_density": None,
                        "duration_ratio_observed_to_expected": None,
                        "pass_duration_plausibility": None,
                        "parameter_assumptions": "",
                        "parameter_uncertainty_caveats": "",
                    }
                )
            vetting = (vetting_by_rank or {}).get(int(candidate.rank))
            if vetting is not None:
                row.update(asdict(vetting))
            else:
                row.update(
                    {
                        "pass_min_transit_count": None,
                        "pass_odd_even_depth": None,
                        "pass_alias_harmonic": None,
                        "pass_secondary_eclipse": None,
                        "pass_depth_consistency": None,
                        "vetting_pass": None,
                        "transit_count_observed": None,
                        "odd_depth_ppm": None,
                        "even_depth_ppm": None,
                        "odd_even_depth_mismatch_fraction": None,
                        "secondary_eclipse_depth_fraction": None,
                        "depth_consistency_fraction": None,
                        "alias_harmonic_with_rank": None,
                        "vetting_reasons": "",
                    }
                )
            row["is_known"] = _is_known_period(candidate.period_days, known_periods) if known_periods else False
            writer.writerow(row)

    payload = {
        "metadata": metadata,
        "candidates": [],
    }
    for candidate in candidates:
        row = asdict(candidate)
        parameter_estimate = (parameter_estimates_by_rank or {}).get(int(candidate.rank))
        if parameter_estimate is not None:
            row.update(asdict(parameter_estimate))
        vetting = (vetting_by_rank or {}).get(int(candidate.rank))
        if vetting is not None:
            row.update(asdict(vetting))
        row["is_known"] = _is_known_period(candidate.period_days, known_periods) if known_periods else False
        payload["candidates"].append(row)
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return csv_path, json_path


_LIVE_COLS = "target,rank,period_days,depth_ppm,snr,duration_hours,transit_time,iteration,vetting_reasons,vetting_pass"


def _row_values(target, c, vr):
    return [
        target, str(c.rank), f"{c.period_days:.6f}",
        f"{c.depth_ppm:.1f}", f"{c.snr:.2f}",
        f"{c.duration_hours:.3f}", f"{c.transit_time:.6f}",
        str(getattr(c, 'iteration', 0)),
        vr.vetting_reasons, str(vr.vetting_pass),
    ]


def _is_known_period(period_days: float, known_periods: list[float], tolerance: float = 0.03) -> bool:
    for kp in known_periods:
        if kp <= 0:
            continue
        ratio = period_days / kp
        for mult in (1, 2, 3, 0.5, 1 / 3):
            if abs(ratio - mult) < tolerance:
                return True
    return False


def collect_live_from_run(run_dir: Path) -> tuple[Path, Path]:
    """Walk per-target candidate JSONs and emit live/novel CSVs."""
    live_csv = run_dir / "candidates_live.csv"
    novel_csv = run_dir / "candidates_novel.csv"
    live_rows: list[list[str]] = []
    novel_rows: list[list[str]] = []
    for json_path in sorted(run_dir.glob("*/candidates/*__bls_*.json")):
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        target = payload.get("metadata", {}).get("target", "")
        for c in payload.get("candidates", []):
            row = [
                target,
                str(c.get("rank", "")),
                f"{float(c.get('period_days', 0)):.6f}",
                f"{float(c.get('depth_ppm', 0)):.1f}",
                f"{float(c.get('snr', 0)):.2f}",
                f"{float(c.get('duration_hours', 0)):.3f}",
                f"{float(c.get('transit_time', 0)):.6f}",
                str(c.get("iteration", 0)),
                str(c.get("vetting_reasons", "")),
                str(c.get("vetting_pass", "")),
            ]
            live_rows.append(row)
            if c.get("vetting_pass") is True and not c.get("is_known", False):
                novel_rows.append(row)
    for csv_path, rows in ((live_csv, live_rows), (novel_csv, novel_rows)):
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(_LIVE_COLS.split(","))
            w.writerows(rows)
    return live_csv, novel_csv


def _append_live_candidates(
    target: str, candidates: list, vetting: dict, known_ephemerides: list,
    *, run_dir: Path,
) -> None:
    """# Deprecated: no longer called from the hot path; use collect_live_from_run instead.
    Append candidates to live summary CSV; novel-only to a second CSV."""
    live_csv = run_dir / "candidates_live.csv"
    novel_csv = run_dir / "candidates_novel.csv"
    for csv_path in (live_csv, novel_csv):
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        if not csv_path.exists():
            try:
                csv_path.write_text(_LIVE_COLS + "\n", encoding="utf-8")
            except OSError as exc:
                LOGGER.warning("Failed to create live candidates CSV: %s", exc)

    known_periods = [e.period_days for e in known_ephemerides] if known_ephemerides else []

    for c in candidates:
        vr = vetting.get(c.rank)
        if not vr:
            continue
        values = _row_values(target, c, vr)
        try:
            with open(live_csv, "a", encoding="utf-8", newline="") as f:
                csv.writer(f).writerow(values)
        except OSError as exc:
            LOGGER.warning("Failed to append to live candidates CSV: %s", exc)
        if not vr.vetting_pass:
            continue
        is_known = False
        for kp in known_periods:
            ratio = c.period_days / kp if kp > 0 else 0
            for mult in (1, 2, 3, 0.5, 1 / 3):
                if abs(ratio - mult) < 0.03:
                    is_known = True
                    break
            if is_known:
                break
        if not is_known:
            try:
                with open(novel_csv, "a", encoding="utf-8", newline="") as f:
                    csv.writer(f).writerow(values)
            except OSError as exc:
                LOGGER.warning("Failed to append to novel candidates CSV: %s", exc)
            LOGGER.info(
                "📡 NOVEL candidate: %s rank=%d P=%.4fd depth=%.0fppm SDE=%.1f",
                target, c.rank, c.period_days, c.depth_ppm, c.snr,
            )
