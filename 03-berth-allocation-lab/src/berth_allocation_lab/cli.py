from __future__ import annotations

import argparse
import json
from pathlib import Path

from berth_allocation_lab import __version__
from berth_allocation_lab.config import ConfigError, load_yaml_config
from berth_allocation_lab.data import BAPScenarioInstance
from berth_allocation_lab.evaluation import compare_static_baselines
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
        help="Generated JSON path, or run directory root for comparison.",
    )
    parser.add_argument(
        "--compare-baselines",
        metavar="PATH",
        help="Compare FCFS and Greedy Rollout on one static scenario YAML or JSON.",
    )
    parser.add_argument(
        "--static-twin",
        action="store_true",
        help="Explicitly generate a static twin of a dynamic YAML preset.",
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

    if args.compare_baselines:
        try:
            source = Path(args.compare_baselines)
            if source.suffix.lower() == ".json":
                if args.static_twin:
                    parser.error("--static-twin applies only to YAML configs.")
                instance = BAPScenarioInstance.load_json(source)
            else:
                config = SyntheticScenarioConfig.load_yaml(source)
                if config.formulation == "dynamic" and args.static_twin:
                    config = config.with_formulation("static")
                instance = SyntheticScenarioGenerator().generate(config)
            fcfs, greedy = compare_static_baselines(
                instance,
                args.output or Path("experiments") / "runs",
            )
        except (ConfigError, OSError, ValueError, TypeError) as error:
            parser.error(str(error))
        print(
            f"Scenario: {instance.scenario_id} | seed: {instance.seed} "
            f"| fingerprint: {instance.content_fingerprint}"
        )
        print(f"{'Metric':<28} {'FCFS':>15} {'Greedy Rollout':>15}")
        for name, field in (
            ("Total waiting (min)", "total_waiting_time_min"),
            ("Mean waiting (min)", "mean_waiting_time_min"),
            ("P95 waiting (min)", "p95_waiting_time_min"),
            ("Mean turnaround (min)", "mean_turnaround_time_min"),
            ("P95 turnaround (min)", "p95_turnaround_time_min"),
            ("Berth utilization", "berth_utilization"),
            ("Runtime (s)", "algorithm_runtime_seconds"),
        ):
            first = getattr(fcfs.summary, field)
            second = getattr(greedy.summary, field)
            first_text = f"{first:.4f}" if first is not None else "n/a"
            second_text = f"{second:.4f}" if second is not None else "n/a"
            print(f"{name:<28} {first_text:>15} {second_text:>15}")
        print(f"Runs: {fcfs.manifest.run_id}, {greedy.manifest.run_id}")
        return 0 if fcfs.summary.is_valid and greedy.summary.is_valid else 1

    if args.static_twin:
        parser.error("--static-twin requires --compare-baselines.")

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
