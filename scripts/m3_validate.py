"""M3 validation: iterative TLS on TOI-1260.
Expected: find planet d in pass 0, then b or c in pass 1.
Runtime: ~30-60 minutes.
"""
import multiprocessing
multiprocessing.set_start_method("fork", force=True)

import time as _time
print("M3 validation: iterative TLS on TOI-1260", flush=True)
print(f"Started at {_time.strftime('%H:%M:%S')}", flush=True)

import sys
sys.path.insert(0, "src")

from pathlib import Path
t0 = _time.time()

# Run the pipeline with iterative TLS
from exohunt.cli import _run_single_target
_run_single_target(target="TIC 355867695", config_ref="./configs/iterative.toml")

elapsed = _time.time() - t0
print(f"\nCompleted in {elapsed/60:.1f} minutes", flush=True)

# Check results
import json, glob
known = {'b': 3.1275, 'c': 7.4931, 'd': 16.6082}

files = sorted(glob.glob("outputs/tic_355867695/candidates/*bls_iter_*.json"))
print(f"\n{len(files)} iteration files found")

for f in files:
    with open(f) as fh:
        data = json.load(fh)
    it = data['metadata'].get('bls_iteration', '?')
    for c in data['candidates']:
        match = ''
        for name, kp in known.items():
            if abs(c['period_days']/kp - 1) < 0.005: match = f' <- planet {name}'
        v = 'PASS' if c['vetting_pass'] else 'FAIL'
        print(f"  iter={it} P={c['period_days']:.4f}d  SDE={c['snr']:.1f}  {v}  {c['vetting_reasons']}{match}")

# Combined
combined = sorted(glob.glob("outputs/tic_355867695/candidates/*bls_[!i]*.json"))
if combined:
    with open(combined[-1]) as fh:
        data = json.load(fh)
    passed = [c for c in data['candidates'] if c['vetting_pass']]
    found = []
    for c in passed:
        for name, kp in known.items():
            if abs(c['period_days']/kp - 1) < 0.005:
                found.append(name)
    print(f"\nPassed vetting: {len(passed)}")
    print(f"Known planets found: {found}")
    print(f"M3 success (>=2 planets): {'PASS' if len(found) >= 2 else 'FAIL'}")
