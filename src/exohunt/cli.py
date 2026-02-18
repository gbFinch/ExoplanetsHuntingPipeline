"""CLI for downloading and plotting TESS light curves."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import lightkurve as lk


DEFAULT_TARGET = "TIC 261136679"


def _safe_target_name(target: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in target).strip("_").lower()


def fetch_and_plot(target: str) -> Path:
    search = lk.search_lightcurve(target, mission="TESS")
    if len(search) == 0:
        raise RuntimeError(f"No TESS light curves found for target: {target}")

    lc = search[0].download()
    if lc is None:
        raise RuntimeError(f"Failed to download TESS light curve for target: {target}")
    n_points = len(lc.time.value)
    time_min = float(lc.time.value.min())
    time_max = float(lc.time.value.max())

    output_dir = Path("outputs/plots")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{_safe_target_name(target)}_raw.png"

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(lc.time.value, lc.flux.value, ".", markersize=1)
    ax.set_title(f"TESS Light Curve: {target}")
    ax.set_xlabel("Time [BTJD]")
    ax.set_ylabel("Flux")
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)

    print(f"Target: {target}")
    print(f"Points: {n_points}")
    print(f"Time range (BTJD): {time_min:.5f} -> {time_max:.5f}")
    print(f"Saved plot: {output_path}")

    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download and plot a TESS light curve.")
    parser.add_argument(
        "--target", default=DEFAULT_TARGET, help="Target name, e.g. 'TIC 261136679'."
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    fetch_and_plot(args.target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
