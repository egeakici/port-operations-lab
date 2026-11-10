"""Bounded Project04 fixture tests with append-only gate receipts; never train."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

PROJECT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("step", type=int, choices=range(2, 15))
    args = parser.parse_args()
    target = PROJECT / "tests" / f"test_step{args.step:02d}_*.py"
    tests = sorted(target.parent.glob("test_step*.py" if args.step==14 else target.name))
    if not tests: parser.error("no step tests; no PASS can be recorded")
    receipts = PROJECT / "docs/development_run"
    receipts.mkdir(parents=True, exist_ok=True)
    attempt = len(list(receipts.glob(f"step{args.step:02d}_attempt*.json"))) + 1
    stem = f"step{args.step:02d}_attempt{attempt:03d}"
    junit = receipts / (stem + ".xml")
    temp = PROJECT / "experiments/test_tmp" / stem
    if temp.exists(): parser.error("refusing to reuse a previous temporary test directory")
    temp.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "-B", "-m", "pytest", "-q", "--tb=short", "-p", "no:cacheprovider", *[str(x.relative_to(PROJECT)) for x in tests], "--basetemp=" + str(temp), "--junitxml=" + str(junit)]
    start = time.perf_counter()
    try:
        result = subprocess.run(command, cwd=PROJECT, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired as exc:
        def decoded(value): return value.decode(errors="replace") if isinstance(value,bytes) else (value or "")
        result = subprocess.CompletedProcess(command,124,decoded(exc.stdout),decoded(exc.stderr)+"\nBounded fixture test process exceeded 180 seconds and was terminated.\n")
    elapsed = time.perf_counter() - start
    print(result.stdout); print(result.stderr, file=sys.stderr)
    counts = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    if junit.exists():
        for suite in ET.parse(junit).getroot().iter("testsuite"):
            for k in counts: counts[k] += int(suite.attrib.get(k, 0))
    hashes = {str(p.relative_to(PROJECT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((PROJECT / "src").rglob("*.py"))}
    status = "PASS" if result.returncode == 0 and counts["skipped"] == 0 else ("PARTIAL_BLOCKED" if result.returncode == 0 else "FAIL")
    previous = sorted(receipts.glob(f"step{args.step:02d}_attempt*.json"))
    receipt = {"step": args.step, "status": status, "scope": "TEST_FIXTURE_ENGINEERING_ONLY", "command": command, "elapsed_s": elapsed, "returncode": result.returncode, "counts": counts, "source_sha256": hashes, "previous_attempt": previous[-1].name if previous else None, "stdout": result.stdout, "stderr": result.stderr}
    (receipts / (stem + ".json")).write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    pointer = receipts / f"step{args.step:02d}_receipt.json"
    # The pointer is explicitly a mutable index; attempts are immutable evidence.
    pointer.write_text(json.dumps({"current_attempt": stem + ".json", "status": status}, indent=2) + "\n", encoding="utf-8")
    with (receipts / "PROGRESS.md").open("a", encoding="utf-8") as stream:
        stream.write(f"\n- Step {args.step:02d}, {stem}: {status}; {counts}; {elapsed:.3f}s.\n")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
