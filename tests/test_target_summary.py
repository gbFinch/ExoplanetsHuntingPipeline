"""Tests for write_target_summary (Plan 006)."""
from __future__ import annotations

from pathlib import Path

from exohunt.bls import BLSCandidate
from exohunt.config import PresetMeta
from exohunt.ephemeris import KnownPlanetEphemeris
from exohunt.manifest import write_target_summary
from exohunt.parameters import CandidateParameterEstimate
from exohunt.stellar import StellarParams
from exohunt.vetting import CandidateVettingResult


def _make_candidate(rank=1, period=5.0, depth_ppm=100.0, snr=10.0, iteration=0, power=50.0):
    return BLSCandidate(
        rank=rank, period_days=period, duration_hours=2.0,
        depth=depth_ppm / 1e6, depth_ppm=depth_ppm, power=power,
        transit_time=2000.0, transit_count_estimate=20, snr=snr,
        iteration=iteration,
    )


def _make_vetting(vetting_pass=True, reasons="pass"):
    return CandidateVettingResult(
        pass_min_transit_count=True, pass_odd_even_depth=True,
        pass_alias_harmonic=True, vetting_pass=vetting_pass,
        transit_count_observed=20, odd_depth_ppm=100.0, even_depth_ppm=100.0,
        odd_even_depth_mismatch_fraction=0.0, alias_harmonic_with_rank=-1,
        vetting_reasons=reasons, odd_even_status="consistent",
    )


def _make_params():
    return CandidateParameterEstimate(
        radius_ratio_rp_over_rs=0.01, radius_earth_radii_solar_assumption=1.0,
        duration_expected_hours_central_solar_density=2.0,
        duration_ratio_observed_to_expected=1.0,
        pass_duration_plausibility=True,
        parameter_assumptions="test", parameter_uncertainty_caveats="test",
    )


def _base_kwargs(tmp_path: Path, **overrides):
    run_dir = tmp_path / "test_run"
    run_dir.mkdir()
    kw = dict(
        target="TIC 12345",
        run_dir=run_dir,
        run_id="test_run",
        n_points_raw=1000,
        n_points_prepared=990,
        time_min_btjd=1000.0,
        time_max_btjd=2000.0,
    )
    kw.update(overrides)
    return kw


def test_summary_written_to_correct_path(tmp_path):
    kw = _base_kwargs(tmp_path)
    path = write_target_summary(**kw)
    assert path.exists()
    assert path.name == "summary.md"
    assert "tic_12345" in str(path.parent.name)


def test_summary_with_no_candidates(tmp_path):
    kw = _base_kwargs(tmp_path)
    path = write_target_summary(**kw)
    text = path.read_text()
    assert "# Run summary: TIC 12345" in text
    assert "No BLS candidates found." in text


def test_summary_with_passing_candidate(tmp_path):
    c = _make_candidate(rank=1)
    v = _make_vetting(vetting_pass=True)
    pe = _make_params()
    kw = _base_kwargs(
        tmp_path,
        bls_candidates=[c],
        vetting_by_rank={1: v},
        parameter_estimates_by_rank={1: pe},
    )
    path = write_target_summary(**kw)
    text = path.read_text()
    assert "**PASS**" in text
    assert "## Passing candidates with physical parameters" in text
    assert "Rp/Rs:" in text


def test_summary_groups_by_iteration(tmp_path):
    c0a = _make_candidate(rank=1, iteration=0)
    c0b = _make_candidate(rank=2, iteration=0, period=3.0)
    c1 = _make_candidate(rank=3, iteration=1, period=7.0)
    kw = _base_kwargs(tmp_path, bls_candidates=[c0a, c0b, c1])
    path = write_target_summary(**kw)
    text = path.read_text()
    assert "### Iteration 0" in text
    assert "### Iteration 1" in text
    assert "Candidates found: 2" in text
    assert "Candidates found: 1" in text


def test_summary_with_stellar_defaults(tmp_path):
    sp = StellarParams(
        R_star=1.0, R_star_min=0.13, R_star_max=3.5,
        M_star=1.0, M_star_min=0.1, M_star_max=1.0,
        limb_darkening=(0.48, 0.19), used_defaults=True,
    )
    kw = _base_kwargs(tmp_path, stellar_params=sp)
    path = write_target_summary(**kw)
    text = path.read_text()
    assert "Solar defaults used." in text


def test_summary_with_known_ephemerides(tmp_path):
    eph = KnownPlanetEphemeris(
        name="TOI-1234.01", period_days=12.0567, t0_bjd=2458000.0,
        duration_hours=3.0,
    )
    kw = _base_kwargs(tmp_path, known_ephemerides=[eph])
    path = write_target_summary(**kw)
    text = path.read_text()
    assert "**TOI-1234.01**" in text
    assert "P = 12.0567 d" in text
