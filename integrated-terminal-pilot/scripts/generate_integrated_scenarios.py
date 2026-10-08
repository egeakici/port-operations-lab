"""Plan (--dry-run) or create (--generate) a Project I development scenario run.

Example (PowerShell, from integrated-terminal-pilot):
    python scripts/generate_integrated_scenarios.py --dry-run
"""

import sys

from integrated_terminal_pilot.scenarios.cli import main

if __name__ == "__main__":
    args = sys.argv[1:]
    if not {"--dry-run", "--generate"} & set(args):
        sys.exit("Use --dry-run or --generate (validation and audit: validate_integrated_scenarios.py).")
    sys.exit(main(args))
