"""Re-validate (--validate) or audit (--audit) an existing Project I scenario run.

Example (PowerShell, from integrated-terminal-pilot):
    python scripts/validate_integrated_scenarios.py --audit --run-dir experiments/scenarios/development/<run_id>
"""

import sys

from integrated_terminal_pilot.scenarios.cli import main

if __name__ == "__main__":
    args = sys.argv[1:]
    if not {"--validate", "--audit"} & set(args):
        sys.exit("Use --validate or --audit with --run-dir (generation: generate_integrated_scenarios.py).")
    sys.exit(main(args))
