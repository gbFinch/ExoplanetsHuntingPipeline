"""Debug TLS duration vs binning."""
import multiprocessing
multiprocessing.set_start_method("fork", force=True)

import numpy as np
import lightkurve as lk
from transitleastsquares import transitleastsquares
from exohunt.preprocess import prepare_lightcurve
from exohunt.pipeline import _stitch_segments
from exohunt.tls import _bin_lightcurve

sr = lk.search_lightcurve("TIC 355867695", mission="TESS", author="SPOC", exptime=120)
lcs = sr.download_all()
prep = [prepare_lightcurve(lc, outlier_sigma=5.0, flatten_window_length=801)[0] for lc in lcs]
stitched, _ = _stitch_segments(prep)

t = np.asarray(stitched.time.value, dtype=float)
f = np.asarray(stitched.flux.value, dtype=float)
ok = np.isfinite(t) & np.isfinite(f)
t, f = t[ok], f[ok]

for bin_min in [2, 5, 10]:
    t_b, f_b = _bin_lightcurve(t, f, bin_min)
    print(f"\nBin={bin_min}min ({len(t_b)} points):", flush=True)
    m = transitleastsquares(t_b, f_b)
    r = m.power(period_min=3.0, period_max=3.3, n_transits_min=2,
                show_progress_bar=False, use_threads=1)
    print(f"  P={r.period:.4f}d  dur={r.duration*24:.2f}h  depth={(1-r.depth)*1e6:.0f}ppm  SDE={r.SDE:.1f}", flush=True)
