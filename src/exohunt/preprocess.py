from __future__ import annotations

import logging

import lightkurve as lk
import numpy as np


LOGGER = logging.getLogger(__name__)


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
