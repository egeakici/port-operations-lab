"""Command-line workflow: --dry-run, --generate, --validate, --audit.

Exit status is 0 on success and 1 when validation or audit fails.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from integrated_terminal_pilot.scenarios.config import (
    DEFAULT_CONFIG_PATH, DEFAULT_DECISIONS_PATH, load_generator_config,
)
from integrated_terminal_pilot.scenarios.models import PHYSICS_PROFILE_STANDARD
from integrated_terminal_pilot.scenarios.outputs import (
    DEFAULT_OUTPUT_ROOT, audit_run, generate_run, plan_run, validate_run,
)


def _counts(values: list[str] | None) -> dict[str, int] | None:
    if not values:
        return None
    counts = {}
    for value in values:
        family, _, count = value.partition("=")
        if not family or not count.isdigit():
            raise SystemExit(f"--family expects NAME=COUNT, got {value!r}")
        counts[family] = int(count)
    return counts


def _print(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, default=str))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Project I synthetic scenario generator (Step 2).")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Show the plan; write nothing.")
    mode.add_argument("--generate", action="store_true", help="Generate a new immutable run.")
    mode.add_argument("--validate", action="store_true", help="Re-validate an existing run.")
    mode.add_argument("--audit", action="store_true", help="Audit hashes, namespaces and collisions.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--decisions", default=str(DEFAULT_DECISIONS_PATH))
    parser.add_argument("--family", action="append", metavar="NAME=COUNT",
                        help="Override planned counts (repeatable); default: development_batch.")
    parser.add_argument("--first-seed-offset", type=int, default=0)
    parser.add_argument("--profile", default=PHYSICS_PROFILE_STANDARD,
                        choices=(PHYSICS_PROFILE_STANDARD, "degenerate_equivalence_v1"))
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--run-dir", default=None, help="Run directory for --validate / --audit.")
    args = parser.parse_args(argv)

    config = load_generator_config(args.config, args.decisions)
    if args.dry_run or args.generate:
        plan = plan_run(config, _counts(args.family), first_seed_offset=args.first_seed_offset,
                        physics_profile=args.profile, run_id=args.run_id,
                        output_root=args.output_root)
        if args.dry_run:
            _print({"mode": "dry-run (nothing written)", **plan,
                    "proposed_or_blocked_decisions": [
                        {"decision_id": d["decision_id"], "parameter_name": d["parameter_name"],
                         "status": d["status"]}
                        for d in config.decisions if d["status"] != "FROZEN"]})
            return 0
        manifest = generate_run(config, plan)
        _print({k: manifest[k] for k in ("run_id", "row_status_counts", "scenario_family_counts",
                                         "validation_status", "collision_audit_passed",
                                         "performance")} | {"output_dir": plan["output_dir"]})
        return 0
    if not args.run_dir:
        parser.error("--run-dir is required for --validate and --audit")
    run_dir = Path(args.run_dir)
    result = validate_run(run_dir, config) if args.validate else audit_run(
        run_dir, output_root=args.output_root)
    _print(result)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
