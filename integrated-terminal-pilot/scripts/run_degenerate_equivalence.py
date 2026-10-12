"""Degenerate equivalence gate: integrated kernel vs Project 03 DynamicBAPEnv + online FCFS.

Example (PowerShell, from integrated-terminal-pilot):
    python scripts/run_degenerate_equivalence.py --family itp_medium=30 --family itp_heavy=30 --family itp_low=10 --family itp_yard_bottleneck=10
"""

import sys

from integrated_terminal_pilot.simulator.cli import main

if __name__ == "__main__":
    sys.exit(main(["equivalence", *sys.argv[1:]]))
