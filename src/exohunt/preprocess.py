from __future__ import annotations

import logging
from dataclasses import dataclass

import lightkurve as lk
import numpy as np


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreprocessingQualityMetrics:
    n_points_raw: int
    n_points_prepared: int
    retained_cadence_fraction: float
    raw_rms: float
    prepared_rms: float
    raw_mad: float
    prepared_mad: float
    raw_trend_proxy: float
    prepared_trend_proxy: float
    rms_improvement_ratio: float
    mad_improvement_ratio: float
    trend_improvement_ratio: float


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


def _relative_flux(flux: np.ndarray) -> np.ndarray:
    median = float(np.nanmedian(flux))
    if np.isfinite(median) and abs(median) > 1e-12:
        return flux / median
    return flux


def _rms_around_median(values: np.ndarray) -> float:
    center = float(np.nanmedian(values))
    residuals = values - center
    return float(np.sqrt(np.nanmean(residuals * residuals)))


def _median_absolute_deviation(values: np.ndarray) -> float:
    center = float(np.nanmedian(values))
    return float(np.nanmedian(np.abs(values - center)))


def _trend_proxy(values: np.ndarray) -> float:
    # Approximate long-timescale baseline amplitude via a broad moving average.
    if len(values) == 0:
        return float("nan")
    if len(values) < 15:
        return float(np.nanstd(values))
    window = max(15, len(values) // 40)
    if window % 2 == 0:
        window += 1
    kernel = np.ones(window, dtype=float) / float(window)
    padded = np.pad(values, (window // 2, window // 2), mode="edge")
    baseline = np.convolve(padded, kernel, mode="valid")
    low, high = np.nanpercentile(baseline, [5.0, 95.0])
    return float(high - low)


def _improvement_ratio(raw_value: float, prepared_value: float) -> float:
    if not np.isfinite(raw_value) or raw_value <= 0:
        return float("nan")
    if not np.isfinite(prepared_value):
        return float("nan")
    if prepared_value <= 0:
        return float("inf")
    return float(raw_value / prepared_value)


def compute_preprocessing_quality_metrics(
    lc_raw: lk.LightCurve,
    lc_prepared: lk.LightCurve,
) -> PreprocessingQualityMetrics:
    """Compute before/after quality metrics for preprocessing validation.

    Theory: good transit preprocessing should reduce broadband scatter (RMS, MAD)
    and suppress long-timescale baseline wander (trend proxy) while retaining as
    many valid cadences as possible.
    """
    raw_flux = np.asarray(lc_raw.flux.value, dtype=float)
    prepared_flux = np.asarray(lc_prepared.flux.value, dtype=float)

    raw_finite = raw_flux[np.isfinite(raw_flux)]
    prepared_finite = prepared_flux[np.isfinite(prepared_flux)]
    if len(raw_finite) == 0:
        raise RuntimeError("Cannot compute preprocessing metrics: raw flux has no finite points.")
    if len(prepared_finite) == 0:
        raise RuntimeError(
            "Cannot compute preprocessing metrics: prepared flux has no finite points."
        )

    raw_relative = _relative_flux(raw_finite)
    prepared_relative = _relative_flux(prepared_finite)

    raw_rms = _rms_around_median(raw_relative)
    prepared_rms = _rms_around_median(prepared_relative)
    raw_mad = _median_absolute_deviation(raw_relative)
    prepared_mad = _median_absolute_deviation(prepared_relative)
    raw_trend = _trend_proxy(raw_relative)
    prepared_trend = _trend_proxy(prepared_relative)
    retained_fraction = float(len(prepared_finite) / len(raw_finite))

    return PreprocessingQualityMetrics(
        n_points_raw=int(len(raw_finite)),
        n_points_prepared=int(len(prepared_finite)),
        retained_cadence_fraction=retained_fraction,
        raw_rms=raw_rms,
        prepared_rms=prepared_rms,
        raw_mad=raw_mad,
        prepared_mad=prepared_mad,
        raw_trend_proxy=raw_trend,
        prepared_trend_proxy=prepared_trend,
        rms_improvement_ratio=_improvement_ratio(raw_rms, prepared_rms),
        mad_improvement_ratio=_improvement_ratio(raw_mad, prepared_mad),
        trend_improvement_ratio=_improvement_ratio(raw_trend, prepared_trend),
    )


def prepare_lightcurve(
    lc: lk.LightCurve,
    outlier_sigma: float = 5.0,
    flatten_window_length: int = 401,
    apply_flatten: bool = True,
    max_transit_duration_hours: float = 0.0,
    transit_mask: np.ndarray | None = None,
) -> tuple[lk.LightCurve, bool]:
    """Prepare light curve for transit search.

    Theory: transit signals are short, shallow dips, while most instrumental/systematic
    trends vary on longer timescales. This normalizes flux, removes extreme outliers,
    and flattens long-term trends so transit-like structure is easier to detect.

    Returns (prepared_lc, normalized) where normalized indicates whether median
    normalization was applied.
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
    # Fix: Change 9 — Track normalization state (P2)
    was_normalized = True
    if not np.isfinite(median_flux) or abs(median_flux) < 1e-12:
        LOGGER.warning("  - preprocessing: skipping normalization (median flux is near zero).")
        was_normalized = False
    else:
        LOGGER.info("  - preprocessing: median normalization")
        prepared = prepared / median_flux

    LOGGER.info("  - preprocessing: outlier removal (sigma=%.2f)", outlier_sigma)
    prepared = prepared.remove_outliers(sigma=outlier_sigma)
    if not apply_flatten:
        LOGGER.info("  - preprocessing: flatten skipped by config")
        return prepared, was_normalized

    LOGGER.info("  - preprocessing: flatten")
    # Fix: Change 12 — Adaptive window mode (P1)
    effective_window = flatten_window_length
    if max_transit_duration_hours > 0:
        min_window = int(3 * max_transit_duration_hours * 60 / 2)
        if min_window % 2 == 0:
            min_window += 1
        effective_window = max(flatten_window_length, min_window)
    window_length = _resolve_window_length(len(prepared.time.value), effective_window)
    if window_length is None:
        LOGGER.warning(
            "Skipping flatten: not enough points (%d) for window=%d.",
            len(prepared.time.value),
            effective_window,
        )
        return prepared, was_normalized
    est_low, est_high = _estimate_flatten_runtime_seconds(len(prepared.time.value), window_length)
    LOGGER.info(
        "  - preprocessing: flatten estimate %.1fs to %.1fs (n_points=%d, window=%d)",
        est_low,
        est_high,
        len(prepared.time.value),
        window_length,
    )
    return prepared.flatten(window_length=window_length, mask=transit_mask), was_normalized
