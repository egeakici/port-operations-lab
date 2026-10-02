"""Opt-in terminal display only; never included in scientific records."""

import sys
from contextlib import nullcontext


def progress_bar(*, enabled: bool, total: int, description: str, unit: str = "scenario",
                 position: int | None = None):
    if not enabled:
        return nullcontext(None)
    from tqdm import tqdm

    return tqdm(total=total, desc=description, unit=unit, file=sys.stderr,
                position=position, dynamic_ncols=True)
