"""Verify TLS duration fix."""
import multiprocessing
multiprocessing.set_start_method("fork", force=True)

import numpy as np
import lightkurve as lk
from exohunt.preprocess import prepare_lightcurve
from exohunt.pipeline import _stitch_segments
from exohunt.tls import run_tls_search

sr = lk.search_lightcurve("TIC 355867695", mission="TESS", author="SPOC", exptime=120)
lcs = sr.download_all()
prep = [prepare_lightcurve(lc, outlier_sigma=5.0, flatten_window_length=801)[0] for lc in lcs]
stitched, _ = _stitch_segments(prep)

# Narrow search around planet b to verify duration
candidates = run_tls_search(stitched, period_min_days=3.0, period_max_days=3.3, top_n=1, min_sde=5.0)
for c in candidates:
    print(f"P={c.period_days:.4f}d  dur={c.duration_hours:.2f}h  depth={c.depth_ppm:.0f}ppm  SDE={c.snr:.1f}")
    print(f"Expected: dur~2.15h  depth~1082ppm")
