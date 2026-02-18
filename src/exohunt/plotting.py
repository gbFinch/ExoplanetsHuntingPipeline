from __future__ import annotations

from pathlib import Path

import lightkurve as lk
import matplotlib.pyplot as plt

from exohunt.cache import _safe_target_name


def save_raw_vs_prepared_plot(
    target: str,
    lc_raw: lk.LightCurve,
    lc_prepared: lk.LightCurve,
    boundaries: list[float],
) -> Path:
    output_dir = Path("outputs/plots")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{_safe_target_name(target)}_prepared.png"

    fig, (ax_raw, ax_prepared) = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    ax_raw.plot(lc_raw.time.value, lc_raw.flux.value, ".", markersize=0.5, alpha=0.7)
    ax_raw.set_title(f"TESS Light Curve (Raw): {target}")
    ax_raw.set_ylabel("Flux")
    ax_prepared.plot(
        lc_prepared.time.value, lc_prepared.flux.value, ".", markersize=0.5, alpha=0.7
    )
    ax_prepared.set_title("Prepared (normalized, outlier-filtered, flattened)")
    ax_prepared.set_xlabel("Time [BTJD]")
    ax_prepared.set_ylabel("Relative Flux")
    for boundary in boundaries:
        ax_raw.axvline(boundary, color="gray", alpha=0.2, linewidth=0.8)
        ax_prepared.axvline(boundary, color="gray", alpha=0.2, linewidth=0.8)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path
