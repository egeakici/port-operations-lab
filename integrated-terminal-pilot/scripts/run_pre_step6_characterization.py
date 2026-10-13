"""Pre-Step 6 development characterization of the approved eight-crane research profile.

Examples (PowerShell, from integrated-terminal-pilot):
    python scripts/run_pre_step6_characterization.py --dry-run
    python scripts/run_pre_step6_characterization.py --plan
    python scripts/run_pre_step6_characterization.py --run --progress
    python scripts/run_pre_step6_characterization.py --resume --progress
    python scripts/run_pre_step6_characterization.py --report
"""

import sys

from integrated_terminal_pilot.benchmark.pre_step6 import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
