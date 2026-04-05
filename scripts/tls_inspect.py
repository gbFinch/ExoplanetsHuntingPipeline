"""Inspect TLS result object fields."""
import multiprocessing
multiprocessing.set_start_method("fork", force=True)

import numpy as np
from transitleastsquares import transitleastsquares

# Tiny synthetic data with one transit
np.random.seed(42)
t = np.linspace(0, 30, 5000)
f = np.ones_like(t) + np.random.normal(0, 0.001, len(t))
# Add transit at P=5d, depth=0.01
for epoch in np.arange(0, 30, 5.0):
    mask = np.abs(t - epoch - 2.5) < 0.05
    f[mask] -= 0.01

model = transitleastsquares(t, f)
results = model.power(period_min=3, period_max=7, show_progress_bar=False, use_threads=1)

print("Key TLS result fields:")
for attr in ['period', 'T0', 'duration', 'depth', 'SDE', 'snr',
             'snr_per_transit', 'transit_count', 'distinct_transit_count',
             'odd_even_mismatch', 'FAP', 'in_transit_count', 'per_transit_count']:
    val = getattr(results, attr, 'N/A')
    if isinstance(val, (float, int, np.floating)):
        print(f"  {attr}: {val}")
    elif isinstance(val, np.ndarray) and val.size < 5:
        print(f"  {attr}: {val}")
    elif isinstance(val, np.ndarray):
        print(f"  {attr}: array({val.shape})")
    else:
        print(f"  {attr}: {type(val).__name__}")
