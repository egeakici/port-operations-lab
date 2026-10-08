"""Independently verify the frozen Project 03 results release."""

from __future__ import annotations

import json
from pathlib import Path

from berth_allocation_lab.benchmark.config import BenchmarkError
from berth_allocation_lab.results.release import DEFAULT_RELEASE_ID, DEFAULT_ROOT, verify_release


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    try:
        result = verify_release(root / DEFAULT_ROOT / DEFAULT_RELEASE_ID)
    except (BenchmarkError, OSError, ValueError, KeyError) as exc:
        raise SystemExit(f"Project 03 verification failed: {exc}") from exc
    print(json.dumps(result, indent=2, sort_keys=True))
