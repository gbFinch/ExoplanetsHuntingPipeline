"""M5 stretch test: iterative TLS on TOI-178 (6 known planets)."""
import multiprocessing
multiprocessing.set_start_method("fork", force=True)

import time as _time
print(f"M5 stretch: TOI-178 (6 planets), started {_time.strftime('%H:%M:%S')}", flush=True)

import sys
sys.path.insert(0, "src")
from exohunt.cli import _run_single_target

t0 = _time.time()
_run_single_target(target="TIC 251848941", config_ref="./configs/iterative.toml")
elapsed = _time.time() - t0
print(f"\nCompleted in {elapsed/60:.1f} minutes", flush=True)

import json, glob
known = {'b': 1.9146, 'c': 3.2385, 'd': 6.5576, 'e': 9.9632, 'f': 15.2333, 'g': 20.7166}

files = sorted(glob.glob("outputs/tic_251848941/candidates/*bls_iter_*.json"))
print(f"\n{len(files)} iteration files")
for f in files:
    with open(f) as fh:
        data = json.load(fh)
    it = data['metadata'].get('bls_iteration', '?')
    for c in data['candidates']:
        match = ''
        for name, kp in known.items():
            if abs(c['period_days']/kp - 1) < 0.01: match = f' <- planet {name}'
        v = 'PASS' if c['vetting_pass'] else 'FAIL'
        print(f"  iter={it} P={c['period_days']:.4f}d  SDE={c['snr']:.1f}  {v}  {c['vetting_reasons']}{match}")

combined = sorted(glob.glob("outputs/tic_251848941/candidates/*bls_[!i]*.json"))
if combined:
    with open(combined[-1]) as fh:
        data = json.load(fh)
    passed = [c for c in data['candidates'] if c['vetting_pass']]
    found = [n for n, kp in known.items() if any(abs(c['period_days']/kp - 1) < 0.01 for c in passed)]
    print(f"\nPassed vetting: {len(passed)}, known planets: {found}")
    print(f"M5 stretch (>=2 of 6): {'PASS' if len(found) >= 2 else 'FAIL'}")
