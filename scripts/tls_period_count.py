"""Check how many trial periods TLS uses."""
import multiprocessing
multiprocessing.set_start_method("fork", force=True)

from transitleastsquares import transitleastsquares
import numpy as np

# Minimal data, just to see the period count
t = np.linspace(0, 1684, 21647)
f = np.ones_like(t)

model = transitleastsquares(t, f)
# TLS has a method to compute the period grid
from transitleastsquares.helpers import period_grid
periods = period_grid(
    R_star=1.0, M_star=1.0,
    time_span=1684,
    period_min=0.5, period_max=25.0,
    oversampling_factor=3,
)
print(f"Period grid 0.5-25d: {len(periods)} periods")

periods2 = period_grid(
    R_star=1.0, M_star=1.0,
    time_span=1684,
    period_min=3.0, period_max=3.3,
    oversampling_factor=3,
)
print(f"Period grid 3.0-3.3d (narrow): {len(periods2)} periods")

# That's the difference
print(f"\nRatio: {len(periods)/len(periods2):.0f}x more periods in blind search")
print(f"If narrow took ~30s, blind would take ~{30 * len(periods)/len(periods2) / 60:.0f} min")
