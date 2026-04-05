"""Quick TLS vs BLS comparison on TOI-1260."""
import multiprocessing
multiprocessing.set_start_method("fork", force=True)

import numpy as np
import lightkurve as lk
from transitleastsquares import transitleastsquares
from exohunt.preprocess import prepare_lightcurve
from exohunt.pipeline import _stitch_segments
from astropy.timeseries import BoxLeastSquares

sr = lk.search_lightcurve("TIC 355867695", mission="TESS", author="SPOC", exptime=120)
lcs = sr.download_all()
prep = [prepare_lightcurve(lc, outlier_sigma=5.0, flatten_window_length=801)[0] for lc in lcs]
stitched, _ = _stitch_segments(prep)

t = np.asarray(stitched.time.value, dtype=float)
f = np.asarray(stitched.flux.value, dtype=float)
ok = np.isfinite(t) & np.isfinite(f)
t, f = t[ok], f[ok]

# Bin to 10-min to speed up TLS
n_bin = 5
n_trim = len(t) - len(t) % n_bin
t_bin = t[:n_trim].reshape(-1, n_bin).mean(axis=1)
f_bin = f[:n_trim].reshape(-1, n_bin).mean(axis=1)
print(f"Binned: {len(t_bin)} points")

known = [("b", 3.1275), ("c", 7.4931), ("d", 16.6082)]

# TLS narrow search around each known planet
for name, period in known:
    print(f"\nTLS around planet {name} (P={period}d)...")
    model = transitleastsquares(t_bin, f_bin)
    results = model.power(
        period_min=period * 0.95,
        period_max=period * 1.05,
        n_transits_min=2,
        show_progress_bar=False,
        use_threads=1,
    )
    print(f"  P={results.period:.4f}d  SDE={results.SDE:.1f}  depth={(1-results.depth)*1e6:.0f}ppm")

# BLS comparison
print("\nBLS SNR at known periods:")
bls = BoxLeastSquares(t, f)
bls_r = bls.power(np.geomspace(0.5, 25.0, 4000), np.geomspace(0.5/24, 10.0/24, 12))
pw = np.asarray(bls_r.power)
fin = np.isfinite(pw)
med = np.nanmedian(pw[fin])
scale = 1.4826 * np.nanmedian(np.abs(pw[fin] - med))
for name, kp in known:
    idx = np.argmin(np.abs(np.asarray(bls_r.period) - kp))
    print(f"  Planet {name}: BLS SNR={(pw[idx]-med)/scale:.1f}")
