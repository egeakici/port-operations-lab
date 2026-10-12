"""Validate a written Step 4 trace; --replay re-runs it and compares canonical digests.

Example (PowerShell, from integrated-terminal-pilot):
    python scripts/validate_integrated_trace.py --run-dir experiments/step4_smoke/<run_id> --replay --show-state
"""

import sys

from integrated_terminal_pilot.simulator.cli import main

if __name__ == "__main__":
    sys.exit(main(["validate", *sys.argv[1:]]))
