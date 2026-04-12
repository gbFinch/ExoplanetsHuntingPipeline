"""TRICERATOPS statistical validation for transit candidates.

Computes Bayesian false positive probability (FPP) and nearby false
positive probability (NFPP) by modeling multiple astrophysical scenarios
and comparing their likelihoods given the observed light curve.

Validation thresholds (Giacalone & Dressing 2020):
  FPP < 0.015 and NFPP < 0.001 → statistically validated planet
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

LOGGER = logging.getLogger(__name__)

_FPP_THRESHOLD = 0.015
_NFPP_THRESHOLD = 0.001


@dataclass(frozen=True)
class ValidationResult:
    fpp: float
    nfpp: float
    validated: bool
    status: str  # "validated", "ambiguous", "false_positive", "error"


def validate_candidate(
    tic_id: int,
    sectors: list[int],
    time: np.ndarray,
    flux: np.ndarray,
    flux_err: float,
    period_days: float,
    depth_ppm: float,
    N: int = 1_000_000,
) -> ValidationResult:
    """Run TRICERATOPS on a single candidate.

    Args:
        tic_id: TIC ID of the target
        sectors: TESS sectors observed
        time: time array (BTJD)
        flux: normalized flux array
        flux_err: median flux uncertainty
        period_days: orbital period of the candidate
        depth_ppm: transit depth in parts per million
        N: number of TRICERATOPS simulations
    """
    try:
        from triceratops.triceratops import target as TRITarget

        sector_arr = np.array(sectors, dtype=int)
        tri = TRITarget(ID=tic_id, sectors=sector_arr)

        # calc_depths must be called before calc_probs
        tri.calc_depths(tdepth=float(depth_ppm))

        # Clean input arrays
        finite = np.isfinite(time) & np.isfinite(flux)
        t_clean = time[finite]
        f_clean = flux[finite]

        tri.calc_probs(
            time=t_clean, flux_0=f_clean, flux_err_0=float(flux_err),
            P_orb=float(period_days), N=N, verbose=0,
        )

        fpp = float(tri.FPP)
        nfpp = float(tri.NFPP)

        if fpp < _FPP_THRESHOLD and nfpp < _NFPP_THRESHOLD:
            status = "validated"
        elif fpp < 0.5:
            status = "ambiguous"
        else:
            status = "false_positive"

        validated = status == "validated"
        LOGGER.info(
            "TRICERATOPS TIC %d P=%.3fd: FPP=%.4f NFPP=%.4f → %s",
            tic_id, period_days, fpp, nfpp, status,
        )
        return ValidationResult(fpp=fpp, nfpp=nfpp, validated=validated, status=status)

    except Exception as exc:
        LOGGER.warning("TRICERATOPS failed for TIC %d P=%.3fd: %s", tic_id, period_days, exc)
        return ValidationResult(
            fpp=float("nan"), nfpp=float("nan"), validated=False, status="error",
        )
