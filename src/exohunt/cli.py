"""CLI for downloading and plotting TESS light curves."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from pathlib import Path
from time import perf_counter

import numpy as np
import matplotlib.pyplot as plt
import lightkurve as lk


DEFAULT_TARGET = "TIC 261136679"
LOGGER = logging.getLogger(__name__)


def _safe_target_name(target: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in target).strip("_").lower()


def _cache_path(target: str, cache_dir: Path) -> Path:
    return cache_dir / f"{_safe_target_name(target)}.npz"


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
) -> Path:
    started_at = perf_counter()
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
    data_source = "download"
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
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    LOGGER.info("Plot complete in %.2fs", perf_counter() - step_started)

    LOGGER.info("--------------------------------")
    LOGGER.info("Target: %s", target)
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
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
