"""Primitive-FCFS physical smoke run of the Step 4 kernel (integration fixture, development data only).

Example (PowerShell, from integrated-terminal-pilot):
    python scripts/run_integrated_smoke.py --family itp_low --seed 10000000 --repeat
"""

import sys

from integrated_terminal_pilot.simulator.cli import main

if __name__ == "__main__":
    sys.exit(main(["smoke", *sys.argv[1:]]))
