"""Tests for TLS thread-count wiring (Step 2 of plan-007)."""
from __future__ import annotations

import sys
import types

import lightkurve as lk
import numpy as np

from exohunt import tls as tls_mod
from exohunt.bls import run_iterative_bls_search
from exohunt.config import resolve_runtime_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakePower:
    power = np.array([0.0])
    periods = np.array([1.0])
    period = 1.0
    depth = 1.0
    SDE = 0.0
    FAP = 1.0
    transit_count = 0


class _FakeModel:
    def __init__(self, *a, **kw):
        pass

    def power(self, **kwargs):
        _FakeModel.last_kwargs = dict(kwargs)
        return _FakePower()


# ---------------------------------------------------------------------------
# Test: run_tls_search honours use_threads
# ---------------------------------------------------------------------------

def test_run_tls_search_honors_use_threads(monkeypatch):
    """run_tls_search forwards use_threads to transitleastsquares.power()."""
    captured = {}

    class _Model:
        def __init__(self, *a, **kw):
            pass

        def power(self, **kwargs):
            captured.update(kwargs)
            return _FakePower()

    fake_mod = types.ModuleType("transitleastsquares")
    fake_mod.transitleastsquares = _Model
    monkeypatch.setitem(sys.modules, "transitleastsquares", fake_mod)

    time = np.linspace(0, 10, 500)
    flux = np.ones_like(time)
    lc = lk.LightCurve(time=time, flux=flux)

    tls_mod.run_tls_search(lc, period_min_days=1.0, period_max_days=5.0, use_threads=4)
    assert captured.get("use_threads") == 4

    tls_mod.run_tls_search(lc, period_min_days=1.0, period_max_days=5.0, use_threads=1)
    assert captured.get("use_threads") == 1


# ---------------------------------------------------------------------------
# Test: run_iterative_bls_search forwards config.tls_threads
# ---------------------------------------------------------------------------

def test_iterative_bls_forwards_tls_threads(monkeypatch):
    """run_iterative_bls_search resolves config.tls_threads and passes it."""
    captured = {}

    def _fake_tls_search(**kwargs):
        captured.update(kwargs)
        return []  # no candidates → loop stops after one pass

    monkeypatch.setattr("exohunt.bls.run_tls_search", _fake_tls_search, raising=False)
    # The TLS branch does a local import; patch the module-level reference too.
    monkeypatch.setattr("exohunt.tls.run_tls_search", _fake_tls_search, raising=False)

    cfg = resolve_runtime_config(cli_overrides={
        "bls": {"search_method": "tls", "tls_threads": 3},
    })

    time = np.linspace(0, 30, 1000)
    flux = np.ones_like(time)
    from astropy.time import Time
    lc = lk.LightCurve(time=Time(time, format="btjd"), flux=flux)

    run_iterative_bls_search(lc, cfg.bls)
    assert captured.get("use_threads") == 3
