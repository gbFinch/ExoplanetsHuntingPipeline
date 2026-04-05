"""M1 validation: TLS blind search on TOI-1260."""
import multiprocessing
multiprocessing.set_start_method("fork", force=True)

import sys
import numpy as np
import lightkurve as lk
import time as _time

print("Downloading...", flush=True)
sr = lk.search_lightcurve("TIC 355867695", mission="TESS", author="SPOC", exptime=120)
lcs = sr.download_all()
print(f"  {len(lcs)} light curves", flush=True)

print("Preprocessing...", flush=True)
from exohunt.preprocess import prepare_lightcurve
from exohunt.pipeline import _stitch_segments
prep = [prepare_lightcurve(lc, outlier_sigma=5.0, flatten_window_length=801)[0] for lc in lcs]
stitched, _ = _stitch_segments(prep)
print(f"  {len(stitched.time)} points", flush=True)

print("Running TLS (single full search + refinements)...", flush=True)
from exohunt.tls import run_tls_search
t0 = _time.time()
candidates = run_tls_search(
    stitched, period_min_days=0.5, period_max_days=25.0,
    top_n=5, min_sde=7.0,
)
elapsed = _time.time() - t0
print(f"  Done in {elapsed:.0f}s, {len(candidates)} candidates\n", flush=True)

known = {'b': 3.1275, 'c': 7.4931, 'd': 16.6082}
for c in candidates:
    match = ''
    for name, kp in known.items():
        if abs(c.period_days / kp - 1) < 0.005: match = f' <- planet {name}'
    print(f"  Rank {c.rank}: P={c.period_days:.4f}d  SDE={c.snr:.1f}  depth={c.depth_ppm:.0f}ppm  dur={c.duration_hours:.1f}h{match}")

print("\n=== SUCCESS CRITERIA ===")
top_sde = candidates[0].snr if candidates else 0
planet_d_top = candidates and abs(candidates[0].period_days / 16.6082 - 1) < 0.005
print(f"Top candidate is planet d: {'PASS' if planet_d_top else 'FAIL'}")
print(f"Top SDE >= 20: {'PASS' if top_sde >= 20 else 'FAIL'} ({top_sde:.1f})")
print(f"Runtime < 10 min: {'PASS' if elapsed < 600 else 'FAIL'} ({elapsed:.0f}s)")
found = [n for n, kp in known.items() if any(abs(c.period_days/kp - 1) < 0.005 for c in candidates)]
print(f"Planets found: {found} ({'PASS' if len(found) >= 2 else 'FAIL'})")
