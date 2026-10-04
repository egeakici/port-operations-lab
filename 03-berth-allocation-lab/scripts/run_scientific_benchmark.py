"""Audit frozen Step 9/11 records and generate the Step 12A benchmark."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from berth_allocation_lab.benchmark.config import BenchmarkConfig, BenchmarkError
from berth_allocation_lab.benchmark.runner import dry_run, run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        config = BenchmarkConfig.load(args.config)
        if args.dry_run:
            print(json.dumps(dry_run(config), indent=2))
        else:
            print(run(config))
        return 0
    except (BenchmarkError, FileNotFoundError, KeyError, ValueError) as error:
        print(json.dumps({"status": "blocked", "reason": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
