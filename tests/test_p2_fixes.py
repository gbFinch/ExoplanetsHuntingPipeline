"""Tests for P2 improvements (R16–R20)."""

from __future__ import annotations

import math
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from exohunt.bls import BLSCandidate, _unique_period
from exohunt.config import resolve_runtime_config


def _make_candidate(rank: int = 1, period: float = 3.0, depth: float = 0.0001) -> BLSCandidate:
    return BLSCandidate(
        rank=rank, period_days=period, duration_hours=2.0,
        depth=depth, depth_ppm=depth * 1e6, power=0.01,
        transit_time=1000.0, transit_count_estimate=5.0, snr=8.0,
    )


# --- R16: Refinement model reuse ---

def test_refine_reuses_prepare_bls_inputs():
    """_prepare_bls_inputs should be called once, not per candidate."""
    mock_model = MagicMock()
    mock_result = MagicMock()
    mock_result.power = np.array([0.01])
    mock_result.period = np.array([3.0])
    mock_result.duration = np.array([0.08])
    mock_result.depth = np.array([0.0001])
    mock_result.transit_time = np.array([1000.0])
    mock_model.power.return_value = mock_result

    from exohunt.bls import _BLSInputs
    fake_inputs = _BLSInputs(
        time=np.linspace(0, 100, 500),
        flux=np.ones(500),
        model=mock_model,
        periods=np.geomspace(0.5, 20, 200),
        durations=np.array([0.04, 0.08]),
    )

    candidates = [_make_candidate(rank=i, period=2.0 + i) for i in range(1, 4)]

    with patch("exohunt.bls._prepare_bls_inputs", return_value=fake_inputs) as mock_prep:
        import lightkurve as lk
        lc = lk.LightCurve(time=np.linspace(0, 100, 500), flux=np.ones(500))
        from exohunt.bls import refine_bls_candidates
        result = refine_bls_candidates(
            lc, candidates, period_min_days=0.5, period_max_days=20.0,
            duration_min_hours=0.5, duration_max_hours=10.0,
        )
        assert mock_prep.call_count == 1, f"Expected 1 call, got {mock_prep.call_count}"
        assert len(result) == 3


# --- R17: Dedup filter ---

def test_dedup_filter_05_keeps_close_periods():
    """Periods 3.00d and 3.20d (6.5% apart) should both be kept at 5% threshold."""
    existing = [_make_candidate(rank=1, period=3.00)]
    assert _unique_period(existing, 3.20, min_separation_frac=0.05) is True


def test_dedup_filter_05_rejects_near_duplicate():
    """Periods 3.00d and 3.05d (1.6% apart) should be rejected at 5% threshold."""
    existing = [_make_candidate(rank=1, period=3.00)]
    assert _unique_period(existing, 3.05, min_separation_frac=0.05) is False


def test_dedup_filter_configurable():
    """Users can set a smaller threshold to keep near-resonant candidates."""
    existing = [_make_candidate(rank=1, period=3.00)]
    # 3.0d and 3.05d are 1.6% apart
    # At 1% threshold: 1.6% > 1% → unique (kept)
    assert _unique_period(existing, 3.05, min_separation_frac=0.01) is True
    # At 5% threshold: 1.6% < 5% → duplicate (rejected)
    assert _unique_period(existing, 3.05, min_separation_frac=0.05) is False


def test_dedup_filter_rejects_identical_periods():
    """Identical periods should be rejected."""
    existing = [_make_candidate(rank=1, period=5.0)]
    assert _unique_period(existing, 5.0, min_separation_frac=0.05) is False


def test_blsconfig_dedup_default_is_005():
    """BLSConfig.unique_period_separation_fraction should default to 0.05."""
    cfg = resolve_runtime_config()
    assert cfg.bls.unique_period_separation_fraction == pytest.approx(0.05)


# --- R18: Limb darkening correction ---

def test_limb_darkening_correction_applied():
    """With correction enabled, radius_ratio should use limb darkening formula."""
    from exohunt.parameters import estimate_candidate_parameters
    candidates = [_make_candidate(depth=0.0001)]
    result = estimate_candidate_parameters(
        candidates,
        apply_limb_darkening_correction=True,
        limb_darkening_u1=0.4,
        limb_darkening_u2=0.2,
    )
    expected = math.sqrt(0.0001 / (1.0 - 0.4 / 3.0 - 0.2 / 6.0))
    assert result[1].radius_ratio_rp_over_rs == pytest.approx(expected, rel=1e-4)


def test_limb_darkening_correction_disabled():
    """With correction disabled, radius_ratio should use sqrt(depth)."""
    from exohunt.parameters import estimate_candidate_parameters
    candidates = [_make_candidate(depth=0.0001)]
    result = estimate_candidate_parameters(
        candidates,
        apply_limb_darkening_correction=False,
    )
    assert result[1].radius_ratio_rp_over_rs == pytest.approx(0.01, rel=1e-6)


# --- R19: Smoothing window ---

def test_smoothing_window_config_default():
    """PlotConfig.smoothing_window should default to 5."""
    cfg = resolve_runtime_config()
    assert cfg.plot.smoothing_window == 5


# --- R20: TIC density lookup ---

def test_lookup_tic_density_success():
    """Successful TIC lookup should return computed density."""
    from exohunt.parameters import _lookup_tic_density

    mock_table = MagicMock()
    mock_table.__len__ = lambda self: 1
    mock_table.__getitem__ = lambda self, key: {
        "mass": [1.0], "rad": [1.0],
    }[key]

    with patch("exohunt.parameters.Catalogs") as mock_cat:
        mock_cat.query_object.return_value = mock_table
        density = _lookup_tic_density("261136679")

    assert density is not None
    assert density == pytest.approx(1408.0, rel=0.05)


def test_lookup_tic_density_fallback_on_error():
    """Failed TIC lookup should return None."""
    from exohunt.parameters import _lookup_tic_density

    with patch("exohunt.parameters.Catalogs") as mock_cat:
        mock_cat.query_object.side_effect = Exception("Network error")
        density = _lookup_tic_density("999999999")

    assert density is None


def test_lookup_tic_density_nan_fields():
    """TIC lookup with NaN mass/radius should return None."""
    from exohunt.parameters import _lookup_tic_density

    mock_table = MagicMock()
    mock_table.__len__ = lambda self: 1
    mock_table.__getitem__ = lambda self, key: {
        "mass": [float("nan")], "rad": [float("nan")],
    }[key]

    with patch("exohunt.parameters.Catalogs") as mock_cat:
        mock_cat.query_object.return_value = mock_table
        density = _lookup_tic_density("123456")

    assert density is None


# --- Config backward compatibility ---

def test_new_config_defaults_backward_compatible():
    """Config without new fields should resolve with defaults."""
    cfg = resolve_runtime_config()
    assert cfg.bls.unique_period_separation_fraction == pytest.approx(0.05)
    assert cfg.parameters.apply_limb_darkening_correction is False
    assert cfg.parameters.limb_darkening_u1 == pytest.approx(0.4)
    assert cfg.parameters.limb_darkening_u2 == pytest.approx(0.2)
    assert cfg.parameters.tic_density_lookup is False
    assert cfg.plot.smoothing_window == 5


def test_parameter_config_fields_exist():
    """ParameterConfig should have all new fields."""
    cfg = resolve_runtime_config()
    # These attribute accesses would raise AttributeError if fields don't exist
    _ = cfg.parameters.apply_limb_darkening_correction
    _ = cfg.parameters.limb_darkening_u1
    _ = cfg.parameters.limb_darkening_u2
    _ = cfg.parameters.tic_density_lookup
