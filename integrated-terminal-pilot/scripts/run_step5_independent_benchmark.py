"""Project I Step 5: independent integrated berth-policy benchmark (development-only tools).

Examples (PowerShell, from integrated-terminal-pilot):
    python scripts/run_step5_independent_benchmark.py --check-compatibility
    python scripts/run_step5_independent_benchmark.py --dry-run
    python scripts/run_step5_independent_benchmark.py --smoke --policy A1 --progress
    python scripts/run_step5_independent_benchmark.py --report
"""

import sys

from integrated_terminal_pilot.benchmark.development import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
