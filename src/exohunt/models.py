from __future__ import annotations

from dataclasses import dataclass

import lightkurve as lk


@dataclass(frozen=True)
class LightCurveSegment:
    segment_id: str
    sector: int
    author: str
    cadence: float
    lc: lk.LightCurve
