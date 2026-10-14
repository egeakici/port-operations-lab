"""Project I Step 6 integrated coordination (development only).

Examples (PowerShell, from integrated-terminal-pilot):
    python scripts/run_step6_coordination.py --audit
    python scripts/run_step6_coordination.py --profile-compute
    python scripts/run_step6_coordination.py --plan
    python scripts/run_step6_coordination.py --run --progress --max-new-runs 4
    python scripts/run_step6_coordination.py --report
"""

import sys

from integrated_terminal_pilot.benchmark.step6 import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
