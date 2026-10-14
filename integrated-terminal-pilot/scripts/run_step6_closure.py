"""Development-only Step 6 closure CLI; no implicit owner approvals."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from integrated_terminal_pilot.benchmark.step6_closure import main

if __name__ == '__main__':
    raise SystemExit(main())
