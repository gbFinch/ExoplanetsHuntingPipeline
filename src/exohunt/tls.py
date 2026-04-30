"""Transit Least Squares (TLS) search wrapper.

Provides `run_tls_search()` with the same interface and return type as
`run_bls_search()` so downstream vetting, output, and iterative logic
work unchanged.
"""
from __future__ import annotations

import logging
import multiprocessing
import os

import numpy as np
import lightkurve as lk

from exohunt.bls import BLSCandidate

LOGGER = logging.getLogger(__name__)

# Prevent TLS fork-bomb on macOS
if os.name == "posix":
    try:
        multiprocessing.set_start_method("fork", force=True)
    except RuntimeError:
        pass


def _bin_lightcurve(
    time: np.ndarray, flux: np.ndarray, bin_minutes: float = 10.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Bin time series to reduce TLS runtime."""
    cadence_days = np.nanmedian(np.diff(time))
    cadence_min = cadence_days * 24 * 60
    if cadence_min >= bin_minutes * 0.9:
        return time, flux
    factor = max(2, int(round(bin_minutes / cadence_min)))
    n_trim = len(time) - len(time) % factor
    t_bin = time[:n_trim].reshape(-1, factor).mean(axis=1)
    f_bin = flux[:n_trim].reshape(-1, factor).mean(axis=1)
    return t_bin, f_bin


def run_tls_search(
    lc_prepared: lk.LightCurve,
    period_min_days: float = 0.5,
    period_max_days: float = 20.0,
    top_n: int = 5,
    min_sde: float = 7.0,
    bin_minutes: float = 10.0,
    unique_period_separation_fraction: float = 0.05,
    stellar_params: "StellarParams | None" = None,
    use_threads: int = 1,
) -> list[BLSCandidate]:
    """Run TLS once, extract top N unique peaks from the SDE periodogram.

    For each peak, runs a narrow TLS refinement to get accurate transit
    parameters (depth, duration, T0).  Returns BLSCandidate objects for
    compatibility with existing pipeline code.
    """
    n_threads = max(1, int(use_threads))
    LOGGER.info("TLS: using %d thread(s)", n_threads)

    from transitleastsquares import transitleastsquares

    time = np.asarray(lc_prepared.time.value, dtype=float)
    flux = np.asarray(lc_prepared.flux.value, dtype=float)
    finite = np.isfinite(time) & np.isfinite(flux)
    time, flux = time[finite], flux[finite]

    if len(time) < 50:
        return []

    span = float(np.nanmax(time) - np.nanmin(time))
    if span <= 0:
        return []

    p_max = min(period_max_days, span * 0.95)
    if p_max <= period_min_days:
        return []

    time_b, flux_b = _bin_lightcurve(time, flux, bin_minutes)
    LOGGER.info(
        "TLS: %d points (binned from %d), period %.2f-%.2fd",
        len(time_b), len(time), period_min_days, p_max,
    )

    # Single full TLS run
    model = transitleastsquares(time_b, flux_b)
    stellar_kw: dict = {}
    if stellar_params is not None and not stellar_params.used_defaults:
        stellar_kw = dict(
            R_star=stellar_params.R_star,
            R_star_min=stellar_params.R_star_min,
            R_star_max=stellar_params.R_star_max,
            M_star=stellar_params.M_star,
            M_star_min=stellar_params.M_star_min,
            M_star_max=stellar_params.M_star_max,
            u=list(stellar_params.limb_darkening),
        )
        LOGGER.info("TLS: using stellar params R=%.3f M=%.3f", stellar_params.R_star, stellar_params.M_star)
    results = model.power(
        period_min=period_min_days,
        period_max=p_max,
        n_transits_min=2,
        show_progress_bar=False,
        use_threads=n_threads,
        **stellar_kw,
    )

    sde = np.asarray(results.power, dtype=float)
    periods = np.asarray(results.periods, dtype=float)

    if len(sde) == 0 or not np.any(np.isfinite(sde)):
        return []

    # Pick top N unique peaks from the SDE spectrum
    ranked_indices = np.argsort(sde)[::-1]
    peak_periods: list[float] = []

    for idx in ranked_indices:
        if not np.isfinite(sde[idx]) or sde[idx] < min_sde:
            break
        p = float(periods[idx])
        if p <= 0:
            continue
        if all(abs(p - pp) / max(p, pp) >= unique_period_separation_fraction
               for pp in peak_periods):
            peak_periods.append(p)
        if len(peak_periods) >= top_n:
            break

    # Refine each peak with a narrow TLS run for accurate parameters,
    # then use BLS to get a reliable duration estimate.
    from astropy.timeseries import BoxLeastSquares
    bls_durations = np.geomspace(0.5 / 24, 10.0 / 24, 20)

    picked: list[BLSCandidate] = []
    for p in peak_periods:
        if len(picked) == 0 and abs(p - float(results.period)) / p < 0.01:
            r = results
        else:
            narrow = transitleastsquares(time_b, flux_b)
            r = narrow.power(
                period_min=p * 0.99, period_max=p * 1.01,
                n_transits_min=2, show_progress_bar=False, use_threads=n_threads,
                **stellar_kw,
            )

        depth_frac = 1.0 - float(r.depth)
        # TLS duration can be unreliable; refine with BLS at the exact period
        bls_model = BoxLeastSquares(time_b, flux_b)
        bls_r = bls_model.power([float(r.period)], bls_durations)
        duration_hours = float(bls_r.duration[0]) * 24.0
        bls_depth = float(bls_r.depth[0])
        transit_time = float(bls_r.transit_time[0])

        picked.append(BLSCandidate(
            rank=len(picked) + 1,
            period_days=float(r.period),
            duration_hours=duration_hours,
            depth=bls_depth,
            depth_ppm=bls_depth * 1_000_000.0,
            power=float(r.SDE),
            transit_time=transit_time,
            transit_count_estimate=float(r.transit_count),
            snr=float(r.SDE),
            fap=float(r.FAP) if np.isfinite(r.FAP) else float("nan"),
        ))

    return picked
