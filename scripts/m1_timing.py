"""M1 validation: TLS search on TOI-1260 — start with just planet d range."""
import multiprocessing
multiprocessing.set_start_method("fork", force=True)

import numpy as np
import lightkurve as lk
import time as _time

print("Downloading...", flush=True)
sr = lk.search_lightcurve("TIC 355867695", mission="TESS", author="SPOC", exptime=120)
lcs = sr.download_all()

print("Preprocessing...", flush=True)
from exohunt.preprocess import prepare_lightcurve
from exohunt.pipeline import _stitch_segments
prep = [prepare_lightcurve(lc, outlier_sigma=5.0, flatten_window_length=801)[0] for lc in lcs]
stitched, _ = _stitch_segments(prep)

t = np.asarray(stitched.time.value, dtype=float)
f = np.asarray(stitched.flux.value, dtype=float)
ok = np.isfinite(t) & np.isfinite(f)
t, f = t[ok], f[ok]

# Bin to 10 min
from exohunt.tls import _bin_lightcurve
t_bin, f_bin = _bin_lightcurve(t, f, 10.0)
print(f"Binned: {len(t_bin)} points", flush=True)

from transitleastsquares import transitleastsquares

known = [("b", 3.1275), ("c", 7.4931), ("d", 16.6082)]

# Test each period range separately to find where it's slow
for pmin, pmax, label in [(1.0, 5.0, "short"), (5.0, 12.0, "mid"), (12.0, 25.0, "long")]:
    print(f"\nTLS {label} ({pmin}-{pmax}d)...", flush=True)
    t0 = _time.time()
    model = transitleastsquares(t_bin, f_bin)
    results = model.power(period_min=pmin, period_max=pmax, n_transits_min=2,
                          show_progress_bar=False, use_threads=1)
    elapsed = _time.time() - t0
    match = ''
    for name, kp in known:
        if abs(results.period / kp - 1) < 0.01: match = f' <- planet {name}'
    print(f"  {elapsed:.0f}s  P={results.period:.4f}d  SDE={results.SDE:.1f}{match}", flush=True)
