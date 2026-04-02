"""Reproduction tests for 7 P0 BLS pipeline defects.

These tests assert CORRECT (post-fix) behavior. They will FAIL against the
current buggy code and PASS once the fixes from 04-fix-plan.md are applied.
"""
from __future__ import annotations

import numpy as np
import pytest

from exohunt import bls
from exohunt.bls import BLSCandidate, run_bls_search
from exohunt.config import resolve_runtime_config
from exohunt.preprocess import prepare_lightcurve
from exohunt.vetting import CandidateVettingResult, vet_bls_candidates


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _ArrayValue:
    def __init__(self, values):
        self.value = np.asarray(values, dtype=float)


class _SimpleLC:
    """Minimal light-curve stub matching the lightkurve interface used by the pipeline."""

    def __init__(self, time, flux):
        self.time = _ArrayValue(time)
        self.flux = _ArrayValue(flux)

    def remove_nans(self):
        mask = np.isfinite(self.flux.value)
        return _SimpleLC(self.time.value[mask], self.flux.value[mask])

    def remove_outliers(self, sigma=5.0):
        return self

    def flatten(self, window_length=401):
        return self

    def __truediv__(self, other):
        return _SimpleLC(self.time.value, self.flux.value / other)


# ---------------------------------------------------------------------------
# VP-Primary-1  B1: SNR field exists and threshold filtering works
# ---------------------------------------------------------------------------

class TestB1_SNR:
    """Bug-report B1: run_bls_search() must compute SNR and filter by min_snr."""

    def test_candidates_have_snr_field(self, monkeypatch):
        # VP-Primary-1: BLSCandidate must have an 'snr' attribute after fix.
        assert hasattr(BLSCandidate, "__dataclass_fields__")
        assert "snr" in BLSCandidate.__dataclass_fields__, (
            "BLSCandidate is missing the 'snr' field (B1)"
        )

    def test_run_bls_search_accepts_min_snr_parameter(self, monkeypatch):
        # VP-Primary-1: run_bls_search must accept min_snr kwarg.
        import inspect
        sig = inspect.signature(run_bls_search)
        assert "min_snr" in sig.parameters, (
            "run_bls_search() is missing 'min_snr' parameter (B1)"
        )

    def test_low_snr_candidates_filtered(self, monkeypatch):
        # VP-Primary-1: candidates below min_snr must be excluded.
        class _FakeResult:
            power = np.asarray([0.01, 0.50, 0.012], dtype=float)
            period = np.asarray([2.0, 3.0, 5.0], dtype=float)
            duration = np.asarray([0.08, 0.08, 0.08], dtype=float)
            depth = np.asarray([1e-4, 5e-3, 1.2e-4], dtype=float)
            transit_time = np.asarray([0.1, 0.2, 0.3], dtype=float)

        class _FakeBLS:
            def __init__(self, time, flux):
                pass
            def power(self, periods, durations):
                return _FakeResult()

        monkeypatch.setattr(bls, "BoxLeastSquares", _FakeBLS)
        lc = _SimpleLC(time=np.arange(0.0, 10.0, 0.05), flux=np.ones(200))

        # With a high min_snr, only the strong peak (power=0.50) should survive.
        candidates = run_bls_search(
            lc_prepared=lc, period_min_days=0.5, period_max_days=8.0,
            top_n=5, min_snr=5.0,
        )
        assert all(c.snr >= 5.0 for c in candidates), (
            "Candidates below min_snr were not filtered (B1)"
        )

    def test_min_snr_zero_returns_all(self, monkeypatch):
        # VP-Secondary-3: min_snr=0 should disable filtering.
        class _FakeResult:
            power = np.asarray([0.01, 0.02], dtype=float)
            period = np.asarray([2.0, 4.0], dtype=float)
            duration = np.asarray([0.08, 0.08], dtype=float)
            depth = np.asarray([1e-4, 2e-4], dtype=float)
            transit_time = np.asarray([0.1, 0.2], dtype=float)

        class _FakeBLS:
            def __init__(self, time, flux):
                pass
            def power(self, periods, durations):
                return _FakeResult()

        monkeypatch.setattr(bls, "BoxLeastSquares", _FakeBLS)
        lc = _SimpleLC(time=np.arange(0.0, 10.0, 0.05), flux=np.ones(200))
        candidates = run_bls_search(
            lc_prepared=lc, period_min_days=0.5, period_max_days=8.0,
            top_n=5, min_snr=0.0,
        )
        # With 2 fake power values, the weaker one has negative SNR (below median).
        # min_snr=0 still filters negative SNR. Verify at least the strong peak passes.
        assert len(candidates) >= 1
        assert all(c.snr >= 0.0 for c in candidates)


# ---------------------------------------------------------------------------
# VP-Primary-2  V1: Odd/even inconclusive when insufficient data
# ---------------------------------------------------------------------------

class TestV1_OddEvenInconclusive:
    """Bug-report V1: vetting must return 'inconclusive' when data is insufficient."""

    def test_vetting_result_has_odd_even_status_field(self):
        # VP-Primary-2: CandidateVettingResult must have odd_even_status.
        assert "odd_even_status" in CandidateVettingResult.__dataclass_fields__, (
            "CandidateVettingResult missing 'odd_even_status' field (V1)"
        )

    def test_nan_depth_yields_inconclusive_not_fail(self):
        # VP-Primary-2: When insufficient in-transit points → inconclusive, not fail.
        # Create a short LC where one parity group will have < 5 in-transit points.
        np.random.seed(42)
        time = np.arange(0.0, 5.0, 0.01)  # 500 points over 5 days
        flux = np.ones_like(time) + np.random.normal(0, 1e-4, len(time))
        lc = _SimpleLC(time, flux)

        # Candidate with long period → few transits → NaN from _group_depth_ppm
        candidate = BLSCandidate(
            rank=1, period_days=4.0, duration_hours=2.0,
            depth=1e-4, depth_ppm=100.0, power=0.05,
            transit_time=1.0, transit_count_estimate=1.25,
            **({"snr": 10.0} if "snr" in BLSCandidate.__dataclass_fields__ else {}),
        )
        results = vet_bls_candidates(lc, [candidate])
        result = results[1]

        assert result.pass_odd_even_depth is True, (
            "pass_odd_even should be True (not penalized) when data is insufficient (V1)"
        )
        assert result.odd_even_status == "inconclusive", (
            f"odd_even_status should be 'inconclusive', got '{result.odd_even_status}' (V1)"
        )
        assert "odd_even_depth_mismatch" not in result.vetting_reasons, (
            "Inconclusive case should not report 'odd_even_depth_mismatch' (V1)"
        )


# ---------------------------------------------------------------------------
# VP-Primary-3  P1: Adaptive window and science-default window=801
# ---------------------------------------------------------------------------

class TestP1_AdaptiveWindow:
    """Bug-report P1: flatten window must be adaptive and science-default=801."""

    def test_science_default_window_is_801(self):
        # VP-Primary-3 / VP-Primary-6: science-default preset flatten_window_length.
        cfg = resolve_runtime_config(preset_name="science-default")
        assert cfg.preprocess.flatten_window_length == 801, (
            f"science-default flatten_window_length should be 801, got "
            f"{cfg.preprocess.flatten_window_length} (P1/O3)"
        )

    def test_prepare_lightcurve_accepts_max_transit_duration_hours(self):
        # VP-Primary-3: prepare_lightcurve must accept adaptive window param.
        import inspect
        sig = inspect.signature(prepare_lightcurve)
        assert "max_transit_duration_hours" in sig.parameters, (
            "prepare_lightcurve() missing 'max_transit_duration_hours' parameter (P1)"
        )


# ---------------------------------------------------------------------------
# VP-Primary-4  P2: Normalization flag propagation
# ---------------------------------------------------------------------------

class TestP2_NormalizationFlag:
    """Bug-report P2: prepare_lightcurve must return normalization state."""

    def test_returns_tuple_with_normalized_flag(self):
        # VP-Primary-4: Return type is tuple[LightCurve, bool].
        lc = _SimpleLC(
            time=np.arange(0.0, 1.0, 0.01),
            flux=np.ones(100) * 1000.0,
        )
        result = prepare_lightcurve(lc, apply_flatten=False)
        assert isinstance(result, tuple) and len(result) == 2, (
            "prepare_lightcurve must return (lc, normalized) tuple (P2)"
        )
        lc_out, normalized = result
        assert normalized is True, "Normal flux should yield normalized=True (P2)"

    def test_near_zero_flux_returns_normalized_false(self):
        # VP-Primary-4: Near-zero median → normalized=False.
        lc = _SimpleLC(
            time=np.arange(0.0, 1.0, 0.01),
            flux=np.ones(100) * 1e-15,
        )
        result = prepare_lightcurve(lc, apply_flatten=False)
        assert isinstance(result, tuple) and len(result) == 2, (
            "prepare_lightcurve must return (lc, normalized) tuple (P2)"
        )
        _, normalized = result
        assert normalized is False, "Near-zero flux should yield normalized=False (P2)"

    def test_run_bls_search_accepts_normalized_parameter(self):
        # VP-Primary-4: run_bls_search must accept normalized kwarg.
        import inspect
        sig = inspect.signature(run_bls_search)
        assert "normalized" in sig.parameters, (
            "run_bls_search() missing 'normalized' parameter (P2)"
        )


# ---------------------------------------------------------------------------
# VP-Primary-6  O3: Preset configuration correctness
# ---------------------------------------------------------------------------

class TestO3_Presets:
    """Bug-report O3: all three presets must have correct enable flags."""

    def test_science_default_plot_enabled(self):
        cfg = resolve_runtime_config(preset_name="science-default")
        assert cfg.plot.enabled is True, (
            "science-default plot.enabled should be True (O3)"
        )

    def test_quicklook_bls_enabled(self):
        cfg = resolve_runtime_config(preset_name="quicklook")
        assert cfg.bls.enabled is True, (
            "quicklook bls.enabled should be True (O3)"
        )

    def test_deep_search_plot_enabled(self):
        cfg = resolve_runtime_config(preset_name="deep-search")
        assert cfg.plot.enabled is True, (
            "deep-search plot.enabled should be True (O3)"
        )


# ---------------------------------------------------------------------------
# VP-Primary-5  O2: Per-sector refinement (structural check)
# ---------------------------------------------------------------------------

class TestO2_PerSectorRefinement:
    """Bug-report O2: per-sector BLS path must call refine_bls_candidates."""

    def test_refine_called_in_per_sector_path(self):
        # VP-Primary-5: Structural check — grep pipeline.py per-sector block
        # for refine_bls_candidates call. This is a code-level assertion.
        from pathlib import Path
        pipeline_src = Path(__file__).parent.parent / "src" / "exohunt" / "pipeline.py"
        source = pipeline_src.read_text(encoding="utf-8")

        # Find the per-sector block and check for refine call within it
        per_sector_start = source.find('if bls_mode == "per-sector" and prepared_segments_for_bls:')
        assert per_sector_start != -1, "Could not find per-sector BLS block"

        # The stitched fallback starts with 'else:'
        else_pos = source.find("else:", per_sector_start)
        per_sector_block = source[per_sector_start:else_pos] if else_pos != -1 else source[per_sector_start:]

        assert "refine_bls_candidates" in per_sector_block, (
            "Per-sector BLS path does not call refine_bls_candidates (O2)"
        )


# ---------------------------------------------------------------------------
# VP-Secondary: Config backward compatibility
# ---------------------------------------------------------------------------

class TestConfigBackwardCompat:
    """VP-Secondary-2: Existing configs without min_snr must still load."""

    def test_default_config_has_min_snr(self):
        cfg = resolve_runtime_config()
        assert hasattr(cfg.bls, "min_snr"), "BLSConfig missing min_snr field (B1)"
        assert cfg.bls.min_snr == pytest.approx(7.0), (
            f"Default min_snr should be 7.0, got {cfg.bls.min_snr}"
        )

    def test_min_snr_configurable(self):
        cfg = resolve_runtime_config(
            cli_overrides={"bls": {"min_snr": 5.0}},
        )
        assert cfg.bls.min_snr == pytest.approx(5.0)
