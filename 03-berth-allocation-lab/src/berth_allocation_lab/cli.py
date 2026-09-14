from __future__ import annotations

import argparse
import json
from pathlib import Path

from berth_allocation_lab import __version__
from berth_allocation_lab.config import ConfigError, load_yaml_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="berth-allocation-lab",
        description="Project 03 infrastructure utilities.",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print the installed package version and exit.",
    )
    parser.add_argument(
        "--validate-config",
        metavar="PATH",
        help="Load a YAML config file and print its top-level keys.",
    )
    args = parser.parse_args(argv)

    if args.version:
        print(__version__)
        return 0

    if args.validate_config:
        try:
            config = load_yaml_config(Path(args.validate_config))
        except ConfigError as error:
            parser.error(str(error))
        print(json.dumps({"keys": sorted(config)}, indent=2))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

