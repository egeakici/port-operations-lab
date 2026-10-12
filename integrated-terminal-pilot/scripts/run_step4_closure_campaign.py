"""Step 4 closure: development-only FCFS characterization campaign (380 planned runs).

Examples (PowerShell, from integrated-terminal-pilot):
    python scripts/run_step4_closure_campaign.py --plan
    python scripts/run_step4_closure_campaign.py --dry-run
    python scripts/run_step4_closure_campaign.py --progress --resume
    python scripts/run_step4_closure_campaign.py --report
"""

import sys

from integrated_terminal_pilot.simulator.cli import main

if __name__ == "__main__":
    sys.exit(main(["closure", *sys.argv[1:]]))
