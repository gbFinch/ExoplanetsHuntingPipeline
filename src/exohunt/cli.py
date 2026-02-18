"""CLI for downloading and plotting TESS light curves."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np
import matplotlib.pyplot as plt
import lightkurve as lk


DEFAULT_TARGET = "TIC 261136679"
LOGGER = logging.getLogger(__name__)


def _safe_target_name(target: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in target).strip("_").lower()


def _cache_path(target: str, cache_dir: Path) -> Path:
    return cache_dir / f"{_safe_target_name(target)}.npz"


@dataclass(frozen=True)
class LightCurveSegment:
    segment_id: str
    sector: int
    author: str
    cadence: float
    lc: lk.LightCurve


def _parse_sectors(value: str | None) -> set[int] | None:
    if not value:
        return None
    items = [chunk.strip() for chunk in value.split(",") if chunk.strip()]
    if not items:
        return None
    return {int(item) for item in items}


def _parse_authors(value: str | None) -> set[str] | None:
    if not value:
        return None
    items = [chunk.strip().upper() for chunk in value.split(",") if chunk.strip()]
    if not items:
        return None
    return set(items)


def _segment_base_dir(target: str, cache_dir: Path) -> Path:
    return cache_dir / "segments" / _safe_target_name(target)


def _segment_manifest_path(target: str, cache_dir: Path) -> Path:
    return _segment_base_dir(target, cache_dir) / "manifest.json"


def _segment_raw_cache_path(target: str, cache_dir: Path, segment_id: str) -> Path:
    return _segment_base_dir(target, cache_dir) / f"{segment_id}__raw.npz"


def _segment_prepared_cache_path(
    target: str,
    cache_dir: Path,
    segment_id: str,
    outlier_sigma: float,
    flatten_window_length: int,
    no_flatten: bool,
) -> Path:
    key = _prepared_cache_key(
        outlier_sigma=outlier_sigma,
        flatten_window_length=flatten_window_length,
        no_flatten=no_flatten,
    )
    return _segment_base_dir(target, cache_dir) / f"{segment_id}__prep_{key}.npz"


def _build_segment_id(index: int, lc: lk.LightCurve) -> str:
    sector = int(lc.meta.get("SECTOR", -1))
    return f"sector_{sector:04d}__idx_{index:03d}"


def _extract_segments(
    lcs: Any,
    selected_sectors: set[int] | None,
    selected_authors: set[str] | None,
) -> list[LightCurveSegment]:
    segments: list[LightCurveSegment] = []
    for idx, lc in enumerate(lcs):
        sector = int(lc.meta.get("SECTOR", -1))
        author = str(lc.meta.get("AUTHOR", "UNKNOWN")).upper()
        cadence = float(lc.meta.get("TIMEDEL", np.nan))
        if selected_sectors is not None and sector not in selected_sectors:
            continue
        if selected_authors is not None and author not in selected_authors:
            continue
        segments.append(
            LightCurveSegment(
                segment_id=_build_segment_id(idx, lc),
                sector=sector,
                author=author,
                cadence=cadence,
                lc=lc.remove_nans(),
            )
        )
    return segments


def _write_segment_manifest(target: str, cache_dir: Path, segments: list[LightCurveSegment]) -> None:
    manifest_path = _segment_manifest_path(target, cache_dir)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "target": target,
        "segments": [
            {
                "segment_id": segment.segment_id,
                "sector": segment.sector,
                "author": segment.author,
                "cadence": segment.cadence,
            }
            for segment in segments
        ],
    }
    manifest_path.write_text(json.dumps(payload, indent=2))


def _load_segment_manifest(target: str, cache_dir: Path) -> list[dict[str, Any]]:
    manifest_path = _segment_manifest_path(target, cache_dir)
    if not manifest_path.exists():
        return []
    payload = json.loads(manifest_path.read_text())
    return list(payload.get("segments", []))

def _prepared_cache_key(
    outlier_sigma: float,
    flatten_window_length: int,
    no_flatten: bool,
) -> str:
    payload = {
        "version": 1,
        "outlier_sigma": round(float(outlier_sigma), 6),
        "flatten_window_length": int(flatten_window_length),
        "no_flatten": bool(no_flatten),
    }
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha1(encoded).hexdigest()[:12]


def _prepared_cache_path(
    target: str,
    cache_dir: Path,
    outlier_sigma: float,
    flatten_window_length: int,
    no_flatten: bool,
) -> Path:
    key = _prepared_cache_key(
        outlier_sigma=outlier_sigma,
        flatten_window_length=flatten_window_length,
        no_flatten=no_flatten,
    )
    return cache_dir / f"{_safe_target_name(target)}__prep_{key}.npz"


def _load_npz_lightcurve(cache_path: Path) -> lk.LightCurve:
    with np.load(cache_path) as cached:
        return lk.LightCurve(time=cached["time"], flux=cached["flux"])


def _save_npz_lightcurve(cache_path: Path, lc: lk.LightCurve) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(cache_path, time=lc.time.value, flux=lc.flux.value)


def _render_progress(prefix: str, current: int, total: int) -> None:
    if total <= 0:
        return
    line = f"\r{prefix}: {current}/{total}"
    sys.stderr.write(line)
    sys.stderr.flush()
    if current >= total:
        sys.stderr.write("\n")
        sys.stderr.flush()


def _stitch_segments(lightcurves: list[lk.LightCurve]) -> tuple[lk.LightCurve, list[float]]:
    if not lightcurves:
        raise RuntimeError("No light-curve segments available to stitch.")
    ordered = sorted(lightcurves, key=lambda item: float(np.nanmin(item.time.value)))
    time_parts = []
    flux_parts = []
    boundaries: list[float] = []
    for idx, lc in enumerate(ordered):
        time_values = np.asarray(lc.time.value, dtype=float)
        flux_values = np.asarray(lc.flux.value, dtype=float)
        if time_values.size == 0:
            continue
        if idx > 0:
            boundaries.append(float(time_values[0]))
        time_parts.append(time_values)
        flux_parts.append(flux_values)
    if not time_parts:
        raise RuntimeError("All stitched segments were empty after preprocessing.")
    stitched = lk.LightCurve(time=np.concatenate(time_parts), flux=np.concatenate(flux_parts))
    return stitched, boundaries


def _resolve_window_length(n_points: int, requested: int) -> int | None:
    if n_points < 15:
        return None

    window = min(requested, n_points - 1)
    if window % 2 == 0:
        window -= 1
    if window < 15:
        return None
    return window


def _estimate_flatten_runtime_seconds(n_points: int, window_length: int) -> tuple[float, float]:
    # Empirical heuristic for laptop-class CPUs; gives a broad expected range.
    scale = (n_points / 20000.0) * (window_length / 401.0)
    lower = max(0.5, 2.0 * scale)
    upper = max(lower + 1.0, 8.0 * scale)
    return lower, upper


def prepare_lightcurve(
    lc: lk.LightCurve,
    outlier_sigma: float = 5.0,
    flatten_window_length: int = 401,
    apply_flatten: bool = True,
) -> lk.LightCurve:
    """Prepare light curve for transit search.

    Theory: transit signals are short, shallow dips, while most instrumental/systematic
    trends vary on longer timescales. This normalizes flux, removes extreme outliers,
    and flattens long-term trends so transit-like structure is easier to detect.
    """
    LOGGER.info("  - preprocessing: remove_nans")
    prepared = lc.remove_nans()
    flux_values = np.asarray(prepared.flux.value, dtype=float)
    finite_flux = flux_values[np.isfinite(flux_values)]
    if finite_flux.size == 0:
        raise RuntimeError("No finite flux values remain after NaN removal.")

    # Normalize manually using robust median scaling to avoid Lightkurve normalize
    # instability/warnings on pathological flux distributions.
    median_flux = float(np.nanmedian(finite_flux))
    if not np.isfinite(median_flux) or abs(median_flux) < 1e-12:
        LOGGER.warning("  - preprocessing: skipping normalization (median flux is near zero).")
    else:
        LOGGER.info("  - preprocessing: median normalization")
        prepared = prepared / median_flux

    LOGGER.info("  - preprocessing: outlier removal (sigma=%.2f)", outlier_sigma)
    prepared = prepared.remove_outliers(sigma=outlier_sigma)
    if not apply_flatten:
        LOGGER.info("  - preprocessing: flatten skipped by config")
        return prepared

    LOGGER.info("  - preprocessing: flatten")
    window_length = _resolve_window_length(len(prepared.time.value), flatten_window_length)
    if window_length is None:
        LOGGER.warning(
            "Skipping flatten: not enough points (%d) for window=%d.",
            len(prepared.time.value),
            flatten_window_length,
        )
        return prepared
    est_low, est_high = _estimate_flatten_runtime_seconds(len(prepared.time.value), window_length)
    LOGGER.info(
        "  - preprocessing: flatten estimate %.1fs to %.1fs (n_points=%d, window=%d)",
        est_low,
        est_high,
        len(prepared.time.value),
        window_length,
    )
    return prepared.flatten(window_length=window_length)


def fetch_and_plot(
    target: str,
    cache_dir: Path,
    refresh_cache: bool = False,
    outlier_sigma: float = 5.0,
    flatten_window_length: int = 401,
    max_download_files: int | None = None,
    no_flatten: bool = False,
    preprocess_mode: str = "per-sector",
    sectors: str | None = None,
    authors: str | None = None,
) -> Path:
    started_at = perf_counter()
    selected_sectors = _parse_sectors(sectors)
    selected_authors = _parse_authors(authors)
    boundaries: list[float] = []
    data_source = "download"

    if preprocess_mode == "global":
        raw_cache_path = _cache_path(target, cache_dir)
        prepared_cache_path = _prepared_cache_path(
            target=target,
            cache_dir=cache_dir,
            outlier_sigma=outlier_sigma,
            flatten_window_length=flatten_window_length,
            no_flatten=no_flatten,
        )

        lc = None
        lc_prepared = None
        LOGGER.info("Step 1/5: checking cache")
        if prepared_cache_path.exists() and not refresh_cache:
            try:
                step_started = perf_counter()
                lc_prepared = _load_npz_lightcurve(prepared_cache_path)
                data_source = "prepared-cache"
                LOGGER.info(
                    "Prepared cache hit: loaded %s in %.2fs",
                    prepared_cache_path,
                    perf_counter() - step_started,
                )
            except Exception as exc:
                LOGGER.warning(
                    "Prepared cache read failed for %s (%s); recomputing.",
                    prepared_cache_path,
                    exc,
                )

        if raw_cache_path.exists() and not refresh_cache:
            try:
                step_started = perf_counter()
                lc = _load_npz_lightcurve(raw_cache_path)
                if data_source == "download":
                    data_source = "raw-cache"
                LOGGER.info(
                    "Raw cache hit: loaded %s in %.2fs",
                    raw_cache_path,
                    perf_counter() - step_started,
                )
            except Exception as exc:
                LOGGER.warning("Raw cache read failed for %s (%s); re-downloading.", raw_cache_path, exc)

        if lc is None and lc_prepared is None:
            LOGGER.info("Step 2/5: searching TESS products")
            step_started = perf_counter()
            search = lk.search_lightcurve(target, mission="TESS", author="SPOC")
            LOGGER.info("Search complete in %.2fs (%d entries)", perf_counter() - step_started, len(search))
            if len(search) == 0:
                raise RuntimeError(f"No TESS light curves found for target: {target}")
            if max_download_files is not None and len(search) > max_download_files:
                LOGGER.info("Limiting download to first %d entries (of %d).", max_download_files, len(search))
                search = search[:max_download_files]

            LOGGER.info("Step 3/5: downloading and stitching light curves")
            step_started = perf_counter()
            lcs = search.download_all(quality_bitmask="default")
            if lcs is None or len(lcs) == 0:
                raise RuntimeError(f"Failed to download TESS light curve for target: {target}")
            lc = lcs.stitch().remove_nans()
            LOGGER.info("Download+stitch complete in %.2fs", perf_counter() - step_started)

            LOGGER.info("Writing raw cache: %s", raw_cache_path)
            _save_npz_lightcurve(raw_cache_path, lc)

        if lc_prepared is None:
            LOGGER.info("Step 4/5: preprocessing light curve")
            step_started = perf_counter()
            lc_prepared = prepare_lightcurve(
                lc,
                outlier_sigma=outlier_sigma,
                flatten_window_length=flatten_window_length,
                apply_flatten=not no_flatten,
            )
            LOGGER.info("Preprocessing complete in %.2fs", perf_counter() - step_started)
            LOGGER.info("Writing prepared cache: %s", prepared_cache_path)
            _save_npz_lightcurve(prepared_cache_path, lc_prepared)
        elif lc is None:
            lc = lc_prepared
    else:
        LOGGER.info("Step 1/5: checking per-segment cache manifest")
        raw_segments: list[LightCurveSegment] = []
        prepared_segments: list[LightCurveSegment] = []
        manifest_rows = [] if refresh_cache else _load_segment_manifest(target, cache_dir)

        for row in manifest_rows:
            segment_id = str(row.get("segment_id"))
            sector = int(row.get("sector", -1))
            author = str(row.get("author", "UNKNOWN")).upper()
            cadence = float(row.get("cadence", np.nan))
            if selected_sectors is not None and sector not in selected_sectors:
                continue
            if selected_authors is not None and author not in selected_authors:
                continue
            raw_path = _segment_raw_cache_path(target, cache_dir, segment_id)
            prep_path = _segment_prepared_cache_path(
                target,
                cache_dir,
                segment_id,
                outlier_sigma=outlier_sigma,
                flatten_window_length=flatten_window_length,
                no_flatten=no_flatten,
            )
            try:
                if prep_path.exists():
                    prepared_segments.append(
                        LightCurveSegment(
                            segment_id=segment_id,
                            sector=sector,
                            author=author,
                            cadence=cadence,
                            lc=_load_npz_lightcurve(prep_path),
                        )
                    )
                if raw_path.exists():
                    raw_segments.append(
                        LightCurveSegment(
                            segment_id=segment_id,
                            sector=sector,
                            author=author,
                            cadence=cadence,
                            lc=_load_npz_lightcurve(raw_path),
                        )
                    )
            except Exception as exc:
                LOGGER.warning("Segment cache read failed (%s): %s", segment_id, exc)

        if not raw_segments:
            LOGGER.info("Step 2/5: searching TESS products")
            step_started = perf_counter()
            search = lk.search_lightcurve(target, mission="TESS", author="SPOC")
            LOGGER.info("Search complete in %.2fs (%d entries)", perf_counter() - step_started, len(search))
            if len(search) == 0:
                raise RuntimeError(f"No TESS light curves found for target: {target}")
            if max_download_files is not None and len(search) > max_download_files:
                LOGGER.info("Limiting download to first %d entries (of %d).", max_download_files, len(search))
                search = search[:max_download_files]

            LOGGER.info("Step 3/5: downloading segment light curves")
            step_started = perf_counter()
            lcs = search.download_all(quality_bitmask="default")
            if lcs is None or len(lcs) == 0:
                raise RuntimeError(f"Failed to download TESS light curve for target: {target}")
            raw_segments = _extract_segments(
                lcs,
                selected_sectors=selected_sectors,
                selected_authors=selected_authors,
            )
            if not raw_segments:
                raise RuntimeError("No segments remain after sector/author filters.")
            LOGGER.info("Download complete in %.2fs (%d segments)", perf_counter() - step_started, len(raw_segments))
            _write_segment_manifest(target, cache_dir, raw_segments)
            for segment in raw_segments:
                raw_path = _segment_raw_cache_path(target, cache_dir, segment.segment_id)
                _save_npz_lightcurve(raw_path, segment.lc)
            data_source = "download"
        else:
            data_source = "segment-cache"
            LOGGER.info("Loaded %d raw segments from cache", len(raw_segments))

        if len(prepared_segments) != len(raw_segments):
            LOGGER.info("Step 4/5: preprocessing segment light curves")
            prep_map = {segment.segment_id: segment for segment in prepared_segments}
            rebuilt_prepared: list[LightCurveSegment] = []
            total_segments = len(raw_segments)
            for idx, segment in enumerate(raw_segments, start=1):
                cached = prep_map.get(segment.segment_id)
                if cached is not None:
                    rebuilt_prepared.append(cached)
                    _render_progress("Prepared segments", idx, total_segments)
                    continue
                prepared_lc = prepare_lightcurve(
                    segment.lc,
                    outlier_sigma=outlier_sigma,
                    flatten_window_length=flatten_window_length,
                    apply_flatten=not no_flatten,
                )
                prep_segment = LightCurveSegment(
                    segment_id=segment.segment_id,
                    sector=segment.sector,
                    author=segment.author,
                    cadence=segment.cadence,
                    lc=prepared_lc,
                )
                rebuilt_prepared.append(prep_segment)
                prep_path = _segment_prepared_cache_path(
                    target,
                    cache_dir,
                    segment.segment_id,
                    outlier_sigma=outlier_sigma,
                    flatten_window_length=flatten_window_length,
                    no_flatten=no_flatten,
                )
                _save_npz_lightcurve(prep_path, prepared_lc)
                _render_progress("Prepared segments", idx, total_segments)
            prepared_segments = rebuilt_prepared
        else:
            LOGGER.info("Step 4/5: skipping preprocessing (prepared segment cache hit)")

        lc, boundaries = _stitch_segments([segment.lc for segment in raw_segments])
        lc_prepared, _ = _stitch_segments([segment.lc for segment in prepared_segments])

        raw_cache_path = _segment_base_dir(target, cache_dir)
        prepared_cache_path = _segment_base_dir(target, cache_dir)

    n_points_raw = len(lc.time.value)
    n_points_prepared = len(lc_prepared.time.value)
    time_min = float(lc_prepared.time.value.min())
    time_max = float(lc_prepared.time.value.max())

    LOGGER.info("Step 5/5: generating plot")
    step_started = perf_counter()
    output_dir = Path("outputs/plots")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{_safe_target_name(target)}_prepared.png"

    fig, (ax_raw, ax_prepared) = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    ax_raw.plot(lc.time.value, lc.flux.value, ".", markersize=0.5, alpha=0.7)
    ax_raw.set_title(f"TESS Light Curve (Raw): {target}")
    ax_raw.set_ylabel("Flux")
    ax_prepared.plot(
        lc_prepared.time.value, lc_prepared.flux.value, ".", markersize=0.5, alpha=0.7
    )
    ax_prepared.set_title("Prepared (normalized, outlier-filtered, flattened)")
    ax_prepared.set_xlabel("Time [BTJD]")
    ax_prepared.set_ylabel("Relative Flux")
    for boundary in boundaries:
        ax_raw.axvline(boundary, color="gray", alpha=0.2, linewidth=0.8)
        ax_prepared.axvline(boundary, color="gray", alpha=0.2, linewidth=0.8)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    LOGGER.info("Plot complete in %.2fs", perf_counter() - step_started)

    LOGGER.info("--------------------------------")
    LOGGER.info("Target: %s", target)
    LOGGER.info("Preprocess mode: %s", preprocess_mode)
    LOGGER.info("Points (raw -> prepared): %d -> %d", n_points_raw, n_points_prepared)
    LOGGER.info("Time range (BTJD): %.5f -> %.5f", time_min, time_max)
    LOGGER.info("Data source: %s", data_source)
    LOGGER.info("Raw cache file: %s", raw_cache_path)
    LOGGER.info("Prepared cache file: %s", prepared_cache_path)
    LOGGER.info(
        "Prep params: outlier_sigma=%.2f flatten_window_length=%d no_flatten=%s",
        outlier_sigma,
        flatten_window_length,
        no_flatten,
    )
    LOGGER.info("Max download files: %s", max_download_files if max_download_files is not None else "all")
    LOGGER.info("Sector filter: %s", sectors if sectors else "all")
    LOGGER.info("Author filter: %s", authors if authors else "all")
    LOGGER.info("Total runtime: %.2fs", perf_counter() - started_at)
    LOGGER.info("Saved plot: %s", output_path)
    LOGGER.info("--------------------------------")

    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download and plot a TESS light curve.")
    parser.add_argument(
        "--target", default=DEFAULT_TARGET, help="Target name, e.g. 'TIC 261136679'."
    )
    parser.add_argument(
        "--cache-dir",
        default="outputs/cache/lightcurves",
        help="Directory for cached stitched light curves.",
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Ignore cached light curve and re-download from TESS.",
    )
    parser.add_argument(
        "--outlier-sigma",
        type=float,
        default=5.0,
        help="Sigma threshold for outlier rejection in preprocessing.",
    )
    parser.add_argument(
        "--flatten-window-length",
        type=int,
        default=401,
        help="Window length used to flatten long-term trends.",
    )
    parser.add_argument(
        "--max-download-files",
        type=int,
        default=None,
        help="Optional cap on number of light-curve files to download before stitching.",
    )
    parser.add_argument(
        "--no-flatten",
        action="store_true",
        help="Disable flatten detrending in preprocessing.",
    )
    parser.add_argument(
        "--preprocess-mode",
        choices=["global", "per-sector"],
        default="per-sector",
        help="Preprocessing strategy. Per-sector is recommended for TESS.",
    )
    parser.add_argument(
        "--sectors",
        default=None,
        help="Optional comma-separated sector filter, e.g. '14,15,16'.",
    )
    parser.add_argument(
        "--authors",
        default="SPOC",
        help="Optional comma-separated author filter, e.g. 'SPOC'.",
    )
    return parser


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = build_parser().parse_args()
    fetch_and_plot(
        args.target,
        cache_dir=Path(args.cache_dir),
        refresh_cache=args.refresh_cache,
        outlier_sigma=args.outlier_sigma,
        flatten_window_length=args.flatten_window_length,
        max_download_files=args.max_download_files,
        no_flatten=args.no_flatten,
        preprocess_mode=args.preprocess_mode,
        sectors=args.sectors,
        authors=args.authors,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
