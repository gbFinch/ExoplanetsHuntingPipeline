#!/usr/bin/env python3
"""P0 validation runner — runs pipeline on test targets and summarizes results.

Usage:
    caffeinate -dims python scripts/p0_validate.py
"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path

def main():
    start = time.time()
    print(f"=== P0 Validation Run — {datetime.now().isoformat()} ===")
    print()

    # Run batch
    import subprocess
    cmd = [
        sys.executable, "-m", "exohunt.cli", "batch",
        "--targets-file", "outputs/p0_validation_targets.txt",
        "--config", "configs/p0_validation.toml",
        "--resume", "--no-cache",
    ]
    print(f"Running: {' '.join(cmd)}")
    print()
    result = subprocess.run(cmd, cwd=Path(__file__).resolve().parent.parent)

    elapsed = time.time() - start
    print(f"\n=== Batch complete in {elapsed/3600:.1f} hours ===\n")

    # Summarize results
    status_path = Path("outputs/batch/run_status.json")
    if status_path.exists():
        statuses = json.loads(status_path.read_text())
        print(f"{'Target':<20} {'Status':<10} {'Runtime':>10}")
        print("-" * 42)
        for s in statuses:
            rt = f"{s['runtime_seconds']/60:.0f}m" if s.get("runtime_seconds") else "?"
            print(f"{s['target']:<20} {s['status']:<10} {rt:>10}")

    # Collect candidates
    print("\n=== Candidate Summary ===")
    for target_dir in sorted(Path("outputs").iterdir()):
        if not target_dir.is_dir() or target_dir.name.startswith(("batch", "cache", "metrics", "manifests")):
            continue
        cand_dir = target_dir / "candidates"
        if not cand_dir.exists():
            continue
        for jf in sorted(cand_dir.glob("*__bls_*.json")):
            if "iter_" in jf.name:
                continue
            data = json.loads(jf.read_text())
            cands = data.get("candidates", [])
            passing = [c for c in cands if c.get("vetting_pass")]
            target = data.get("metadata", {}).get("target", target_dir.name)
            print(f"\n{target}: {len(cands)} candidates, {len(passing)} pass vetting")
            for c in cands:
                status = "✅" if c.get("vetting_pass") else "❌"
                reasons = c.get("vetting_reasons", "")
                print(f"  {status} rank={c['rank']} P={c['period_days']:.4f}d "
                      f"depth={c.get('depth_ppm',0):.0f}ppm "
                      f"SDE={c.get('snr',0):.1f} iter={c.get('iteration',0)} "
                      f"[{reasons}]")

    # Check validation results
    print("\n=== TRICERATOPS Validation ===")
    for target_dir in sorted(Path("outputs").iterdir()):
        val_files = list((target_dir / "candidates").glob("*__validation.json")) if (target_dir / "candidates").exists() else []
        for vf in val_files:
            data = json.loads(vf.read_text())
            print(f"\n{target_dir.name}:")
            for rank, vr in data.items():
                print(f"  rank {rank}: FPP={vr['fpp']:.4f} NFPP={vr['nfpp']:.4f} → {vr['status']}")

    print(f"\n=== Total runtime: {elapsed/3600:.1f} hours ===")

if __name__ == "__main__":
    main()
