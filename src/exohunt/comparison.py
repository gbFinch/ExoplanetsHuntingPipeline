from __future__ import annotations

import argparse
import csv
import json
import logging
from dataclasses import dataclass
from math import isfinite, log10
from pathlib import Path

import numpy as np

from exohunt.cache import _safe_target_name


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreprocessingRun:
    target: str
    run_utc: str
    outlier_sigma: float
    flatten_window_length: int
    no_flatten: bool
    retained_cadence_fraction: float
    rms_improvement_ratio: float
    mad_improvement_ratio: float
    trend_improvement_ratio: float
    cadence_minutes: float
    sector_span_days: float
    cadence_class: str
    sector_span_class: str

    @property
    def config_label(self) -> str:
        flatten_state = "off" if self.no_flatten else "on"
        return (
            f"sigma={self.outlier_sigma:g},"
            f"window={self.flatten_window_length},"
            f"flatten={flatten_state}"
        )


def _cadence_class(cadence_minutes: float) -> str:
    if not isfinite(cadence_minutes):
        return "unknown-cadence"
    if cadence_minutes <= 3.0:
        return "short-cadence"
    if cadence_minutes <= 15.0:
        return "medium-cadence"
    return "long-cadence"


def _sector_span_class(sector_span_days: float) -> str:
    if not isfinite(sector_span_days):
        return "unknown-span"
    if sector_span_days <= 10.0:
        return "short-span"
    if sector_span_days <= 30.0:
        return "standard-span"
    return "extended-span"


def _robust_mean(values: list[float]) -> float:
    finite = [value for value in values if isfinite(value)]
    if not finite:
        return float("nan")
    return float(np.mean(finite))


def _parse_float(row: dict[str, str], key: str) -> float:
    value = row.get(key, "")
    try:
        return float(value)
    except ValueError:
        return float("nan")


def _parse_bool(row: dict[str, str], key: str) -> bool:
    value = row.get(key, "").strip().lower()
    return value in {"1", "true", "t", "yes", "y"}


def _parse_int(row: dict[str, str], key: str, default: int = 0) -> int:
    value = _parse_float(row, key)
    if not isfinite(value):
        return default
    return int(value)


def _metrics_score(run: PreprocessingRun) -> float:
    ratios = [
        run.rms_improvement_ratio,
        run.mad_improvement_ratio,
        run.trend_improvement_ratio,
    ]
    if any((not isfinite(value)) or value <= 0 for value in ratios):
        return float("-inf")
    base = log10(ratios[0]) + log10(ratios[1]) + 0.5 * log10(ratios[2])
    retention_penalty = max(0.0, 0.99 - run.retained_cadence_fraction) * 40.0
    return base - retention_penalty


def _segment_metadata(target: str, cache_dir: Path) -> tuple[float, float]:
    segment_root = cache_dir / "segments" / _safe_target_name(target)
    manifest_path = segment_root / "manifest.json"
    cadence_minutes = float("nan")
    sector_span_days = float("nan")
    if manifest_path.exists():
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        segments = list(payload.get("segments", []))
        cadences = []
        spans = []
        for segment in segments:
            cadence = float(segment.get("cadence", float("nan")))
            if isfinite(cadence) and cadence > 0:
                cadences.append(cadence * 24.0 * 60.0)
            segment_id = str(segment.get("segment_id", ""))
            if not segment_id:
                continue
            raw_path = segment_root / f"{segment_id}__raw.npz"
            if not raw_path.exists():
                continue
            with np.load(raw_path) as npz:
                times = np.asarray(npz["time"], dtype=float)
            finite_time = times[np.isfinite(times)]
            if len(finite_time) > 1:
                spans.append(float(np.nanmax(finite_time) - np.nanmin(finite_time)))
        if cadences:
            cadence_minutes = float(np.median(cadences))
        if spans:
            sector_span_days = float(np.median(spans))
    else:
        raw_path = cache_dir / f"{_safe_target_name(target)}.npz"
        if raw_path.exists():
            with np.load(raw_path) as npz:
                times = np.asarray(npz["time"], dtype=float)
            finite_time = times[np.isfinite(times)]
            if len(finite_time) > 1:
                sector_span_days = float(np.nanmax(finite_time) - np.nanmin(finite_time))

    return cadence_minutes, sector_span_days


def _load_runs(metrics_csv_path: Path, cache_dir: Path) -> list[PreprocessingRun]:
    if not metrics_csv_path.exists():
        raise FileNotFoundError(f"Metrics CSV not found: {metrics_csv_path}")
    rows: list[PreprocessingRun] = []
    cache: dict[str, tuple[float, float]] = {}
    with metrics_csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            target = row.get("target", "").strip()
            if not target:
                continue
            if target not in cache:
                cache[target] = _segment_metadata(target=target, cache_dir=cache_dir)
            cadence_minutes, sector_span_days = cache[target]
            run = PreprocessingRun(
                target=target,
                run_utc=row.get("run_utc", ""),
                outlier_sigma=_parse_float(row, "outlier_sigma"),
                flatten_window_length=_parse_int(row, "flatten_window_length", default=0),
                no_flatten=_parse_bool(row, "no_flatten"),
                retained_cadence_fraction=_parse_float(row, "retained_cadence_fraction"),
                rms_improvement_ratio=_parse_float(row, "rms_improvement_ratio"),
                mad_improvement_ratio=_parse_float(row, "mad_improvement_ratio"),
                trend_improvement_ratio=_parse_float(row, "trend_improvement_ratio"),
                cadence_minutes=cadence_minutes,
                sector_span_days=sector_span_days,
                cadence_class=_cadence_class(cadence_minutes),
                sector_span_class=_sector_span_class(sector_span_days),
            )
            rows.append(run)
    return rows


def build_preprocessing_comparison_report(
    metrics_csv_path: Path,
    cache_dir: Path,
    report_path: Path,
) -> Path:
    runs = _load_runs(metrics_csv_path=metrics_csv_path, cache_dir=cache_dir)
    if not runs:
        raise RuntimeError("No rows available in preprocessing summary CSV.")

    groups: dict[tuple[str, str, str], list[PreprocessingRun]] = {}
    for run in runs:
        key = (run.cadence_class, run.sector_span_class, run.config_label)
        groups.setdefault(key, []).append(run)

    report_rows = []
    for (cadence_class, span_class, config_label), grouped_runs in groups.items():
        scores = [_metrics_score(run) for run in grouped_runs]
        report_rows.append(
            {
                "cadence_class": cadence_class,
                "sector_span_class": span_class,
                "config_label": config_label,
                "samples": len(grouped_runs),
                "score": _robust_mean(scores),
                "retained_fraction": _robust_mean(
                    [run.retained_cadence_fraction for run in grouped_runs]
                ),
                "rms_ratio": _robust_mean([run.rms_improvement_ratio for run in grouped_runs]),
                "mad_ratio": _robust_mean([run.mad_improvement_ratio for run in grouped_runs]),
                "trend_ratio": _robust_mean([run.trend_improvement_ratio for run in grouped_runs]),
                "flatten_window_length": grouped_runs[0].flatten_window_length,
                "no_flatten": grouped_runs[0].no_flatten,
            }
        )

    recommendations = []
    class_pairs = sorted({(row["cadence_class"], row["sector_span_class"]) for row in report_rows})
    for cadence_class, span_class in class_pairs:
        candidates = [
            row
            for row in report_rows
            if row["cadence_class"] == cadence_class and row["sector_span_class"] == span_class
        ]
        ordered = sorted(
            candidates,
            key=lambda row: (
                row["score"],
                row["retained_fraction"],
                -float(row["flatten_window_length"]),
                not bool(row["no_flatten"]),
            ),
            reverse=True,
        )
        recommendations.append((cadence_class, span_class, ordered[0], len(candidates)))

    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    lines.append("# Preprocessing Method Comparison Report")
    lines.append("")
    lines.append(f"- Source metrics: `{metrics_csv_path}`")
    lines.append(f"- Source cache: `{cache_dir}`")
    lines.append(f"- Total runs analyzed: {len(runs)}")
    lines.append(f"- Distinct targets analyzed: {len({run.target for run in runs})}")
    lines.append("")
    lines.append("## Recommendation by Cadence and Sector Span")
    lines.append("")
    lines.append(
        "| Cadence Class | Sector Span Class | Recommended Config | Mean Score | Mean Retained Fraction | Samples | Rationale |"
    )
    lines.append("|---|---|---|---:|---:|---:|---|")
    for cadence_class, span_class, row, n_configs in recommendations:
        lines.append(
            "| "
            f"{cadence_class} | {span_class} | `{row['config_label']}` | "
            f"{row['score']:.3f} | {row['retained_fraction']:.4f} | {row['samples']} | "
            f"Best composite denoise score across {n_configs} compared configs |"
        )
    lines.append("")
    lines.append("## Compared Configurations")
    lines.append("")
    lines.append(
        "| Cadence Class | Sector Span Class | Config | Score | Retained | RMS x | MAD x | Trend x | Samples |"
    )
    lines.append("|---|---|---|---:|---:|---:|---:|---:|---:|")
    for row in sorted(
        report_rows,
        key=lambda item: (
            item["cadence_class"],
            item["sector_span_class"],
            -item["score"],
            item["config_label"],
        ),
    ):
        lines.append(
            "| "
            f"{row['cadence_class']} | {row['sector_span_class']} | `{row['config_label']}` | "
            f"{row['score']:.3f} | {row['retained_fraction']:.4f} | "
            f"{row['rms_ratio']:.2f} | {row['mad_ratio']:.2f} | {row['trend_ratio']:.2f} | "
            f"{row['samples']} |"
        )
    lines.append("")
    lines.append("## Scoring Notes")
    lines.append("")
    lines.append(
        "- Composite score = `log10(RMS improvement) + log10(MAD improvement) + 0.5*log10(trend improvement)`."
    )
    lines.append(
        "- A retention penalty is applied when retained cadence fraction drops below 0.99."
    )
    lines.append("- Higher score is better.")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    LOGGER.info("Wrote preprocessing comparison report: %s", report_path)
    return report_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build preprocessing comparison report from run metrics."
    )
    parser.add_argument(
        "--metrics-csv",
        default="outputs/metrics/preprocessing_summary.csv",
        help="Path to preprocessing summary CSV.",
    )
    parser.add_argument(
        "--cache-dir",
        default="outputs/cache/lightcurves",
        help="Light-curve cache directory used to infer cadence and span metadata.",
    )
    parser.add_argument(
        "--report-path",
        default="outputs/reports/preprocessing-method-comparison.md",
        help="Output markdown report path.",
    )
    return parser


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = build_parser().parse_args()
    build_preprocessing_comparison_report(
        metrics_csv_path=Path(args.metrics_csv),
        cache_dir=Path(args.cache_dir),
        report_path=Path(args.report_path),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
