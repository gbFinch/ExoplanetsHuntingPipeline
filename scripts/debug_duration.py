"""Debug TLS duration issue."""
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
t_b, f_b = _bin_lightcurve(t, f, 10.0)
print(f"Binned: {len(t_b)} points\n")

# Full search result for planet b
print("Full search (3.0-3.3d):")
m = transitleastsquares(t_b, f_b)
r = m.power(period_min=3.0, period_max=3.3, n_transits_min=2,
            show_progress_bar=False, use_threads=1)
print(f"  P={r.period:.4f}d  dur={r.duration*24:.2f}h  depth={1-r.depth:.6f}  SDE={r.SDE:.1f}")

# Narrow search like run_tls_search does for refinement
p = 3.1274
print(f"\nNarrow search ({p*0.99:.4f}-{p*1.01:.4f}d):")
m2 = transitleastsquares(t_b, f_b)
r2 = m2.power(period_min=p*0.99, period_max=p*1.01, n_transits_min=2,
              show_progress_bar=False, use_threads=1)
print(f"  P={r2.period:.4f}d  dur={r2.duration*24:.2f}h  depth={1-r2.depth:.6f}  SDE={r2.SDE:.1f}")
print(f"  duration grid: {r2.duration_result if hasattr(r2, 'duration_result') else 'N/A'}")
