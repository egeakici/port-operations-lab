"""Engineering timings: load, init, event step, action, clone time/memory, run, trace size.

Example (PowerShell, from integrated-terminal-pilot):
    python scripts/measure_step4_performance.py --family itp_heavy --clone-at-min 1500
"""

import sys

from integrated_terminal_pilot.simulator.cli import main

if __name__ == "__main__":
    sys.exit(main(["measure", *sys.argv[1:]]))
