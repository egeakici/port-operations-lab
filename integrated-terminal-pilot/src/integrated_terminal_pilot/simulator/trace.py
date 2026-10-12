"""Canonical runtime trace (export, digest, standalone validation).

A run directory holds deterministic, canonical files (no wall-clock data):

* ``events.jsonl``     every processed kernel event (``KE-`` id, time, D22 priority, type,
                       entity key, generation) in processing order;
* ``decisions.jsonl``  every decision (policy or kernel dispatch, ``DEC-`` id) with its effect;
* ``ledger.jsonl``     the container movement ledger ``itp_ledger_v1`` (its ``causation_id``
                       links each physical effect to the event or decision that caused it);
* ``blocking.jsonl``   crane blocking episodes (crane, vessel, reason, start, end);
* ``rejections.jsonl`` validator rejections recorded by the runner (never in kernel state);
* ``final_state.json`` the ``itp_state_v1`` snapshot at the end of the run;
* ``result.json``      KPIs, status and audits (wall-clock fields removed).

``engineering.json`` (wall-clock timings, host) is written separately and is not part of the
canonical digest. ``manifest.json`` lists the SHA-256 of every canonical file and the combined
``trace_sha256``. Two equivalent runs give identical canonical files.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from integrated_terminal_pilot.simulator.ledger import (
    ALLOWED_STATUS_PAIRS, TRANSITIONS, ledger_jsonl_lines,
)

TRACE_SCHEMA_VERSION = "itp_trace_v1"
CANONICAL_FILES = ("events.jsonl", "decisions.jsonl", "ledger.jsonl", "blocking.jsonl", "rejections.jsonl",
                   "final_state.json", "result.json")
WALL_CLOCK_KEYS = ("wall_seconds",)


def _dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _event_lines(kernel) -> list[str]:
    log = kernel.state.event_log or []
    return [_dumps({"event_id": f"KE-{e[0]:08d}", "time_min": e[1], "priority": e[2], "event_type": e[3],
                    "entity_key": e[4], "generation": e[5]}) for e in log]


def _decision_lines(kernel) -> list[str]:
    return [_dumps({"decision_id": d[0], "time_min": d[1], "kind": d[2], "effect": d[3]})
            for d in kernel.state.decision_log]


def _blocking_lines(kernel) -> list[str]:
    return [_dumps({"crane_id": e[0], "vessel_id": e[1], "reason": e[2], "start_min": e[3], "end_min": e[4]})
            for e in kernel.state.block_episodes]


def canonical_files(kernel, *, rejections: list | None = None, run_id: str | None = None) -> dict[str, str]:
    """Canonical text of every trace file (deterministic for a given scenario, policies and actions)."""
    result = kernel.result(run_id=None)
    for key in WALL_CLOCK_KEYS:
        result.pop(key, None)
    ledger = kernel.state.ledger or []
    scenario_id = kernel.catalog.scenario_id
    return {
        "events.jsonl": "".join(line + "\n" for line in _event_lines(kernel)),
        "decisions.jsonl": "".join(line + "\n" for line in _decision_lines(kernel)),
        "ledger.jsonl": "".join(line + "\n" for line in ledger_jsonl_lines(ledger, run_id=None,
                                                                          scenario_id=scenario_id)),
        "blocking.jsonl": "".join(line + "\n" for line in _blocking_lines(kernel)),
        "rejections.jsonl": "".join(_dumps(r) + "\n" for r in (rejections or [])),
        "final_state.json": _dumps(kernel.snapshot()) + "\n",
        "result.json": json.dumps(result, sort_keys=True, indent=1, allow_nan=False) + "\n",
    }


def digest_files(files: dict[str, str]) -> dict[str, Any]:
    hashes = {name: hashlib.sha256(files[name].encode("utf-8")).hexdigest() for name in CANONICAL_FILES}
    combined = hashlib.sha256("".join(f"{n}:{hashes[n]}\n" for n in CANONICAL_FILES).encode()).hexdigest()
    return {"files": hashes, "trace_sha256": combined}


def trace_digest(kernel, *, rejections: list | None = None) -> str:
    return digest_files(canonical_files(kernel, rejections=rejections))["trace_sha256"]


def write_trace(kernel, out_dir: str | Path, *, run_id: str, rejections: list | None = None,
                engineering: dict | None = None, metadata: dict | None = None) -> dict[str, Any]:
    """Write a run directory exclusively (an existing directory is never overwritten)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=False)
    files = canonical_files(kernel, rejections=rejections)
    for name, text in files.items():
        with (out / name).open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
    digest = digest_files(files)
    manifest = {"schema_version": TRACE_SCHEMA_VERSION, "run_id": run_id,
                "scenario_id": kernel.catalog.scenario_id, "fingerprints": kernel.catalog.fingerprints,
                "status": kernel.status, **digest, **(metadata or {}),
                "sizes_bytes": {name: len(files[name].encode("utf-8")) for name in CANONICAL_FILES}}
    with (out / "manifest.json").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(manifest, sort_keys=True, indent=1) + "\n")
    with (out / "engineering.json").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(engineering or {}, sort_keys=True, indent=1) + "\n")
    return manifest


def validate_trace_dir(run_dir: str | Path, scenario_doc: dict[str, Any]) -> dict[str, Any]:
    """Standalone trace validation: hashes, ordering, causal links, ledger replay, conservation."""
    run_dir = Path(run_dir)
    issues: list[str] = []
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    files = {name: (run_dir / name).read_text(encoding="utf-8") for name in CANONICAL_FILES}
    digest = digest_files(files)
    if digest != {"files": manifest["files"], "trace_sha256": manifest["trace_sha256"]}:
        issues.append("file hashes differ from manifest")
    events = [json.loads(line) for line in files["events.jsonl"].splitlines()]
    decisions = [json.loads(line) for line in files["decisions.jsonl"].splitlines()]
    ledger = [json.loads(line) for line in files["ledger.jsonl"].splitlines()]
    blocking = [json.loads(line) for line in files["blocking.jsonl"].splitlines()]
    state = json.loads(files["final_state.json"])
    for name, rows, key in (("events", events, "event_id"), ("decisions", decisions, "decision_id")):
        ids = [r[key] for r in rows]
        if len(ids) != len(set(ids)):
            issues.append(f"duplicate {name} ids")
        times = [r["time_min"] for r in rows]
        if any(b < a - 1e-9 for a, b in zip(times, times[1:])):
            issues.append(f"{name} times decrease")
    causes = {e["event_id"] for e in events} | {d["decision_id"] for d in decisions}
    if any(b["end_min"] < b["start_min"] for b in blocking):
        issues.append("blocking episode ends before it starts")
    # Ledger replay from the scenario's initial locations.
    loc = {}
    for entry in scenario_doc["initial_state"]["container_locations"]:
        loc[entry["container_id"]] = (entry["status"], entry["location"]["kind"], entry["location"]["location_id"])
    teu = {c["container_id"]: c["size_teu"] for c in scenario_doc["containers"]}
    keys, previous = set(), (0, -1.0)
    counts = {"crane_moves": 0, "throughput": 0}
    for row in ledger:
        if (row["sequence_number"], row["simulation_time_min"]) <= previous or \
                row["simulation_time_min"] < previous[1] - 1e-9:
            issues.append(f"ledger order broken at {row['event_id']}")
        previous = (row["sequence_number"], row["simulation_time_min"])
        if row["idempotency_key"] in keys:
            issues.append(f"duplicate idempotency key {row['idempotency_key']}")
        keys.add(row["idempotency_key"])
        if row["causation_id"] not in causes:
            issues.append(f"{row['event_id']}: unknown causation {row['causation_id']}")
        if row["container_id"] not in loc:
            issues.append(f"{row['event_id']}: unknown container")
            continue
        if row["quantity_teu"] != teu[row["container_id"]]:
            issues.append(f"{row['event_id']}: TEU differs from the container record")
        if row["event_class"] != "PHYSICAL":
            continue
        status, kind, location_id = loc[row["container_id"]]
        source, dest = row["source_location"], row["destination_location"]
        expected = TRANSITIONS.get(row["event_type"])
        if (source["kind"], source["location_id"]) != (kind, location_id) or row["from_status"] != status \
                or (row["from_status"], row["to_status"]) not in ALLOWED_STATUS_PAIRS or expected is None \
                or expected != (row["from_status"], row["to_status"], source["kind"], dest["kind"]):
            issues.append(f"{row['event_id']}: illegal transition for {row['container_id']}")
        if dest["kind"] == "YARD_BLOCK" and (dest["bay"], dest["row"], dest["tier"]) != (None, None, None):
            issues.append(f"{row['event_id']}: fabricated G0 slot")
        loc[row["container_id"]] = (row["to_status"], dest["kind"], dest["location_id"])
        counts["crane_moves"] += row["crane_moves"]
        counts["throughput"] += row["event_type"] in ("RELEASE_COMPLETED", "DEPARTED_WITH_VESSEL")
    ids = sorted(loc)
    final = list(zip(state["c_status"], state["c_loc_kind"], state["c_loc_id"]))
    if len(final) != len(ids) or any(loc[cid] != tuple(f) for cid, f in zip(ids, final)):
        issues.append("replayed final locations differ from the final state")
    occupied: dict[str, float] = {}
    for cid, (_status, kind, location_id) in loc.items():
        if kind == "YARD_BLOCK":
            occupied[location_id] = occupied.get(location_id, 0.0) + teu[cid]
    for block_id, block in state["blocks"].items():
        if abs(occupied.get(block_id, 0.0) - block["occupied_teu"]) > 1e-9:
            issues.append(f"{block_id}: replayed occupancy differs from the final state")
    result = json.loads(files["result.json"])
    if counts["crane_moves"] != result["kpi"]["crane_moves_completed"]:
        issues.append("ledger crane moves differ from the KPI")
    if counts["throughput"] != result["kpi"]["container_throughput"]:
        issues.append("ledger throughput differs from the KPI")
    return {"ok": not issues, "issues": issues[:50], "events": len(events), "decisions": len(decisions),
            "ledger_records": len(ledger), "containers": len(loc), "trace_sha256": manifest["trace_sha256"]}


__all__ = ["CANONICAL_FILES", "TRACE_SCHEMA_VERSION", "canonical_files", "digest_files", "trace_digest",
           "validate_trace_dir", "write_trace"]
