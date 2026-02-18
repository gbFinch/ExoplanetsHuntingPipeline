from __future__ import annotations

import sys


def _render_progress(prefix: str, current: int, total: int) -> None:
    if total <= 0:
        return
    line = f"\r{prefix}: {current}/{total}"
    sys.stderr.write(line)
    sys.stderr.flush()
    if current >= total:
        sys.stderr.write("\n")
        sys.stderr.flush()
