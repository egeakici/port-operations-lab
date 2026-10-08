"""Build or verify the immutable Project 03 results release."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from berth_allocation_lab.benchmark.config import BenchmarkError
from berth_allocation_lab.results.release import (
    DEFAULT_RELEASE_ID, DEFAULT_ROOT, build_release, dry_run, verify_release,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--build", action="store_true")
    mode.add_argument("--verify", action="store_true")
    parser.add_argument("--release-id", default=DEFAULT_RELEASE_ID)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        if args.dry_run:
            result = dry_run(root, args.release_id)
        elif args.build:
            target = build_release(root, args.release_id)
            result = {"status": "completed", "path": str(target)}
        else:
            result = verify_release(root / DEFAULT_ROOT / args.release_id)
    except (BenchmarkError, OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"Project 03 release failed: {exc}\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
