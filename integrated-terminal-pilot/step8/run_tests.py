"""One bounded Step8 regression on independent synthetic fixtures only."""
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
import time
import os

from integrated_terminal_pilot.benchmark import step7 as s
from evidence import PROJECT, REPO, code_inventory, publish, publish_bytes, sha


def main():
    started = time.perf_counter()
    inventory = code_inventory()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    root = PROJECT / "experiments/step8_analysis/testing"
    log = root / (stamp + ".log")
    command = [sys.executable, "-B", "-m", "unittest", "discover", "-s",
               str(Path(__file__).resolve().parent / "tests"), "-v"]
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run(command, cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    publish_bytes(log, result.stdout)
    publish(log.with_suffix(".json"), dict(schema="itp_step8_focused_test_receipt_v1", code_sha256=s.digest(inventory),
            code_inventory=inventory, command=command, exit_code=result.returncode, log_sha256=sha(log),
            wall_seconds=time.perf_counter()-started, scientific_episodes=0,
            authority="Owner Final Closure absolute limit4 and sections03/04/06 explicit focused-fixture/engineering authorization; no scientific campaign",
            exclusions="All historical full regressions, Step7 simulations, training, deep canonical inflation"))
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    print(result.stdout.decode("utf-8", errors="replace"))
    print("Evidence:", log)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
