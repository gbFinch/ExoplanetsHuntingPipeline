from __future__ import annotations

import csv
import json
import logging
import platform
import sys
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path

from exohunt.cache import content_hash, _safe_target_name, _target_artifact_dir

_MANIFEST_INDEX_COLUMNS = [
    "run_started_utc",
    "run_finished_utc",
    "target",
    "manifest_run_key",
    "comparison_key",
    "config_hash",
    "data_fingerprint_hash",
    "preprocess_mode",
    "data_source",
    "n_points_raw",
    "n_points_prepared",
    "time_min_btjd",
    "time_max_btjd",
    "bls_enabled",
    "bls_mode",
    "candidate_csv_count",
    "candidate_json_count",
    "diagnostic_asset_count",
    "manifest_path",
]


def _hash_payload(payload: dict[str, object]) -> str:
    return content_hash(payload)


def _safe_package_version(name: str) -> str:
    try:
        return package_version(name)
    except PackageNotFoundError:
        return "not-installed"
    except Exception:
        return "unknown"


def _runtime_version_map() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "exohunt": _safe_package_version("exohunt"),
        "numpy": _safe_package_version("numpy"),
        "astropy": _safe_package_version("astropy"),
        "lightkurve": _safe_package_version("lightkurve"),
        "matplotlib": _safe_package_version("matplotlib"),
        "pandas": _safe_package_version("pandas"),
        "plotly": _safe_package_version("plotly"),
    }


def _write_manifest_index_row(path: Path, row: dict[str, str | int | float | bool]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=_MANIFEST_INDEX_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def _write_run_manifest(
    *,
    target: str,
    run_started_utc: str,
    run_finished_utc: str,
    runtime_seconds: float,
    config_payload: dict[str, str | int | float | bool],
    data_payload: dict[str, str | int | float | bool],
    artifacts_payload: dict[str, object],
    run_dir: Path,
) -> tuple[Path, Path, Path]:
    """Persist run manifest for reproducibility and run-to-run comparison.

    Theory: reproducibility depends on three dimensions: settings, input-data
    summary, and software environment. Hashing settings+data creates a stable
    comparison key for grouping reruns target-by-target, while per-run manifests
    preserve exact timestamps and produced artifacts.
    """
    config_hash = _hash_payload(dict(config_payload))
    data_fingerprint_hash = _hash_payload(dict(data_payload))
    comparison_key = _hash_payload(
        {
            "target": target,
            "config_hash": config_hash,
            "data_fingerprint_hash": data_fingerprint_hash,
        }
    )
    manifest_run_key = _hash_payload(
        {"comparison_key": comparison_key, "run_started_utc": run_started_utc}
    )

    target_manifest_dir = _target_artifact_dir(target, "manifests", outputs_root=run_dir)
    target_manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = (
        target_manifest_dir / f"{_safe_target_name(target)}__manifest_{manifest_run_key}.json"
    )

    manifest_payload = {
        "schema_version": 1,
        "target": target,
        "run": {
            "run_started_utc": run_started_utc,
            "run_finished_utc": run_finished_utc,
            "runtime_seconds": float(runtime_seconds),
        },
        "comparison": {
            "comparison_key": comparison_key,
            "config_hash": config_hash,
            "data_fingerprint_hash": data_fingerprint_hash,
        },
        "config": config_payload,
        "data_summary": data_payload,
        "artifacts": artifacts_payload,
        "versions": _runtime_version_map(),
        "platform": {
            "python_executable": sys.executable,
            "platform": platform.platform(),
        },
    }
    manifest_path.write_text(
        json.dumps(manifest_payload, indent=2, sort_keys=True), encoding="utf-8"
    )

    index_row: dict[str, str | int | float | bool] = {
        "run_started_utc": run_started_utc,
        "run_finished_utc": run_finished_utc,
        "target": target,
        "manifest_run_key": manifest_run_key,
        "comparison_key": comparison_key,
        "config_hash": config_hash,
        "data_fingerprint_hash": data_fingerprint_hash,
        "preprocess_mode": str(config_payload["preprocess_mode"]),
        "data_source": str(data_payload["data_source"]),
        "n_points_raw": int(data_payload["n_points_raw"]),
        "n_points_prepared": int(data_payload["n_points_prepared"]),
        "time_min_btjd": float(data_payload["time_min_btjd"]),
        "time_max_btjd": float(data_payload["time_max_btjd"]),
        "bls_enabled": bool(config_payload["run_bls"]),
        "bls_mode": str(config_payload["bls_mode"]),
        "candidate_csv_count": int(artifacts_payload["candidate_csv_count"]),
        "candidate_json_count": int(artifacts_payload["candidate_json_count"]),
        "diagnostic_asset_count": int(artifacts_payload["diagnostic_asset_count"]),
        "manifest_path": str(manifest_path),
    }

    run_index_path = run_dir / "run_manifest_index.csv"
    target_index_path = target_manifest_dir / "run_manifest_index.csv"
    _write_manifest_index_row(run_index_path, index_row)
    _write_manifest_index_row(target_index_path, index_row)
    return manifest_path, run_index_path, target_index_path


_README_LOGGER = logging.getLogger(__name__)


def write_run_readme(
    run_dir: Path, config, preset_meta,
    *, targets: list[str],
    started_utc: str, finished_utc: str, runtime_seconds: float,
    success_count: int, failure_count: int,
    errors: dict[str, str] | None = None,
) -> Path:
    """Write a human-readable README.md describing this run."""
    try:
        preset_label = (
            f"`{preset_meta.name}` (version={preset_meta.version}, hash=`{preset_meta.hash}`)"
            if preset_meta.is_set
            else "custom (no preset)"
        )
        lines = [
            f"# Run: {run_dir.name}",
            "",
            f"- **Started (UTC):** {started_utc}",
            f"- **Finished (UTC):** {finished_utc}",
            f"- **Runtime:** {runtime_seconds:.1f}s",
            f"- **Preset:** {preset_label}",
            f"- **Targets:** {len(targets)} "
            f"({success_count} succeeded, {failure_count} failed)",
            "",
            "## Targets",
            "",
        ]
        for t in targets:
            err = (errors or {}).get(t)
            status = f"❌ {err}" if err else "✓"
            lines.append(f"- `{t}` — {status}")
        lines.append("")
        readme_path = run_dir / "README.md"
        readme_path.write_text("\n".join(lines), encoding="utf-8")
        return readme_path
    except Exception as exc:
        _README_LOGGER.warning("Failed to write run README: %s", exc)
        return run_dir / "README.md"


def write_target_summary(
    *,
    target: str,
    run_dir: Path,
    run_id: str,
    preset_meta: object | None = None,
    config: object | None = None,
    runtime_seconds: float | None = None,
    n_points_raw: int,
    n_points_prepared: int,
    time_min_btjd: float,
    time_max_btjd: float,
    stellar_params: object | None = None,
    known_ephemerides: list | None = None,
    bls_candidates: list | None = None,
    vetting_by_rank: dict | None = None,
    parameter_estimates_by_rank: dict | None = None,
    candidate_csv_paths: list | None = None,
    diagnostic_assets: list | None = None,
    plot_paths: list | None = None,
    manifest_path: Path | None = None,
) -> Path:
    """Write a human-readable summary.md at <run_dir>/<target-slug>/summary.md."""
    from exohunt.cache import _target_output_dir

    known_ephemerides = known_ephemerides or []
    bls_candidates = bls_candidates or []
    vetting_by_rank = vetting_by_rank or {}
    parameter_estimates_by_rank = parameter_estimates_by_rank or {}
    candidate_csv_paths = candidate_csv_paths or []
    diagnostic_assets = diagnostic_assets or []
    plot_paths = plot_paths or []

    lines: list[str] = [f"# Run summary: {target}", ""]

    # Section 1: Run metadata
    lines.append(f"- **Run:** {run_id}")
    if preset_meta is not None and getattr(preset_meta, "is_set", False):
        lines.append(
            f"- **Preset:** `{preset_meta.name}` "
            f"(version={preset_meta.version}, hash=`{preset_meta.hash}`)"
        )
    else:
        lines.append("- **Preset:** custom (no preset)")
    if runtime_seconds is not None:
        lines.append(f"- **Runtime:** {runtime_seconds:.1f}s")
    lines.append(
        f"- **Data:** {n_points_raw} → {n_points_prepared} cadences "
        f"(BTJD {time_min_btjd:.2f} → {time_max_btjd:.2f})"
    )
    lines.append("")

    # Section 2: Stellar parameters
    lines.append("## Stellar parameters")
    lines.append("")
    if stellar_params is None or getattr(stellar_params, "used_defaults", True):
        lines.append("Solar defaults used.")
    else:
        sp = stellar_params
        lines.append(f"- **R_star:** {sp.R_star:.3f} [{sp.R_star_min:.3f}, {sp.R_star_max:.3f}] R☉")
        lines.append(f"- **M_star:** {sp.M_star:.3f} [{sp.M_star_min:.3f}, {sp.M_star_max:.3f}] M☉")
        lines.append(f"- **Limb darkening (u1, u2):** ({sp.limb_darkening[0]:.4f}, {sp.limb_darkening[1]:.4f})")
    lines.append("")

    # Section 3: Known planets/TOIs
    lines.append("## Known planets / TOIs")
    lines.append("")
    if not known_ephemerides:
        lines.append("No known planets or TOI candidates in NASA Exoplanet Archive.")
    else:
        for eph in known_ephemerides:
            lines.append(f"- **{eph.name}** — P = {eph.period_days:.4f} d")
    lines.append("")

    # Section 4: Search results grouped by iteration
    if bls_candidates:
        lines.append("## Search results")
        lines.append("")
        # Group by iteration
        iters: dict[int, list] = {}
        for c in bls_candidates:
            iters.setdefault(c.iteration, []).append(c)
        # Top-power candidate per iteration (for masked text)
        top_by_iter: dict[int, object] = {}
        for it, cands in iters.items():
            top_by_iter[it] = max(cands, key=lambda x: x.power)

        for iter_n in sorted(iters):
            cands = iters[iter_n]
            lines.append(f"### Iteration {iter_n}")
            # Masked text
            if iter_n == 0:
                if known_ephemerides:
                    masked_parts = [f"{e.name} (P={e.period_days:.4f} d)" for e in known_ephemerides]
                    lines.append(f"Masked: {', '.join(masked_parts)}")
                else:
                    lines.append("Masked: none")
            else:
                prior_parts = []
                for prev_it in sorted(iters):
                    if prev_it >= iter_n:
                        break
                    top = top_by_iter[prev_it]
                    prior_parts.append(f"P = {top.period_days:.4f} d")
                lines.append(f"Masked: known planets + prior iterations (top candidates at {', '.join(prior_parts)})")
            lines.append(f"Candidates found: {len(cands)}")
            for c in cands:
                bullet = f"- rank {c.rank}: P = {c.period_days:.4f} d, depth = {c.depth_ppm:.1f} ppm, SNR = {c.snr:.1f}"
                vr = vetting_by_rank.get(c.rank)
                if vr is not None:
                    if vr.vetting_pass:
                        if vr.vetting_reasons == "pass":
                            bullet += " — **PASS**"
                        else:
                            bullet += f" — PASS ({vr.vetting_reasons})"
                    else:
                        bullet += f" — FAIL ({vr.vetting_reasons})"
                lines.append(bullet)
            lines.append("")
    else:
        lines.append("## Search results")
        lines.append("")
        lines.append("No BLS candidates found.")
        lines.append("")

    # Section 5: Passing candidates with physical parameters
    passing = [
        c for c in bls_candidates
        if vetting_by_rank.get(c.rank) and vetting_by_rank[c.rank].vetting_pass
    ]
    if passing:
        lines.append("## Passing candidates with physical parameters")
        lines.append("")
        for c in passing:
            lines.append(f"### rank {c.rank} (P = {c.period_days:.4f} d) — iteration {c.iteration}")
            lines.append(f"- Depth: {c.depth_ppm:.1f} ppm")
            lines.append(f"- Duration: {c.duration_hours:.1f} h")
            lines.append(f"- Transit time (BTJD): {c.transit_time:.1f}")
            lines.append(f"- Transit count estimate: {c.transit_count_estimate:.0f}")
            pe = parameter_estimates_by_rank.get(c.rank)
            if pe is not None:
                lines.append(f"- Rp/Rs: {pe.radius_ratio_rp_over_rs:.4f}")
                lines.append(f"- Rp: {pe.radius_earth_radii_solar_assumption:.3f} R⊕")
                lines.append(f"- Expected duration (central, solar density): {pe.duration_expected_hours_central_solar_density:.2f} h")
                lines.append(f"- Observed/expected duration ratio: {pe.duration_ratio_observed_to_expected:.2f}")
                lines.append(f"- Duration plausibility: {'pass' if pe.pass_duration_plausibility else 'fail'}")
            lines.append("")

    # Section 6: Artifacts
    lines.append("## Artifacts")
    lines.append("")

    def _rel(p: Path) -> str:
        try:
            return str(p.relative_to(run_dir))
        except ValueError:
            return str(p)

    if candidate_csv_paths:
        lines.append(f"- Candidates: {', '.join(f'`{_rel(p)}`' for p in candidate_csv_paths)}")
    if diagnostic_assets:
        lines.append(f"- Diagnostic asset pairs: {len(diagnostic_assets)}")
    if plot_paths:
        lines.append(f"- Plots: {', '.join(f'`{_rel(p)}`' for p in plot_paths)}")
    if manifest_path is not None:
        lines.append(f"- Manifest: `{_rel(manifest_path)}`")
    lines.append("")

    summary_path = _target_output_dir(target, outputs_root=run_dir) / "summary.md"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("\n".join(lines), encoding="utf-8")
    return summary_path