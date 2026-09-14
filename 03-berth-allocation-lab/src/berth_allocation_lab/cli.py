from __future__ import annotations

import argparse
import json
from pathlib import Path

from berth_allocation_lab import __version__
from berth_allocation_lab.config import ConfigError, load_yaml_config
from berth_allocation_lab.scenarios import (
    SyntheticScenarioConfig,
    SyntheticScenarioGenerator,
)


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
    parser.add_argument(
        "--generate-scenario",
        metavar="PATH",
        help="Generate a synthetic scenario from a YAML config.",
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        help="Output JSON path for --generate-scenario.",
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

    if args.generate_scenario:
        if not args.output:
            parser.error("--generate-scenario requires --output.")
        try:
            config = SyntheticScenarioConfig.load_yaml(args.generate_scenario)
            instance = SyntheticScenarioGenerator().generate(config)
        except (ConfigError, ValueError, TypeError) as error:
            parser.error(str(error))
        instance.save_json(Path(args.output))
        print(
            json.dumps(
                {
                    "scenario_id": instance.scenario_id,
                    "vessel_count": instance.vessel_count,
                    "content_fingerprint": instance.content_fingerprint,
                },
                indent=2,
            )
        )
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
