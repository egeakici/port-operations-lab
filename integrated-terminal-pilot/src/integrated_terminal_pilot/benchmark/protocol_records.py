"""Strict loader for the protocol control register (``configs/protocol/itp_protocol_control_register_v1.yaml``).

Approvals that are not generator parameter values (amendments, execution rules, analysis and Step 6
pre-registrations) are recorded there append-only. The loader rejects unknown fields, unknown
statuses, duplicate ids and dangling ``supersedes`` / ``superseded_by`` links, so a malformed record
can never silently count as an approval.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from integrated_terminal_pilot.scenarios.config import PROJECT_ROOT

CONTROL_REGISTER_PATH = PROJECT_ROOT / "configs" / "protocol" / "itp_protocol_control_register_v1.yaml"
CONTROL_STATUSES = ("APPROVED_IN_EFFECT", "APPROVED_FOR_STEP6_DESIGN_NOT_VALIDATION_LOCKED", "SUPERSEDED")
REQUIRED_FIELDS = ("record_id", "title", "status", "approval_date", "approval_source", "scope", "value", "affects")
OPTIONAL_FIELDS = ("supersedes", "superseded_by")
# The pre-Step 6 package (2026-10-13). Every id must be present with an approved status for the lock
# review to be reachable; their presence never makes the lock READY on its own.
REQUIRED_CONTROL_RECORDS = {
    "AM-01": "APPROVED_IN_EFFECT", "AM-02": "APPROVED_IN_EFFECT", "AM-03": "APPROVED_IN_EFFECT",
    "AM-04": "APPROVED_IN_EFFECT", "AM-05": "APPROVED_IN_EFFECT",
    "AM-06": "APPROVED_FOR_STEP6_DESIGN_NOT_VALIDATION_LOCKED",
    "AM-07": "APPROVED_FOR_STEP6_DESIGN_NOT_VALIDATION_LOCKED",
    "AM-08": "APPROVED_FOR_STEP6_DESIGN_NOT_VALIDATION_LOCKED",
    "AM-09": "APPROVED_IN_EFFECT",
}


class ControlRegisterError(ValueError):
    pass


def load_control_register(path: Path = CONTROL_REGISTER_PATH) -> dict[str, dict[str, Any]]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("register_version") != 1 or not isinstance(data.get("records"), list):
        raise ControlRegisterError("control register must have register_version 1 and a records list")
    records: dict[str, dict[str, Any]] = {}
    for record in data["records"]:
        if not isinstance(record, dict):
            raise ControlRegisterError("every record must be a mapping")
        missing = [f for f in REQUIRED_FIELDS if f not in record]
        extra = set(record) - set(REQUIRED_FIELDS) - set(OPTIONAL_FIELDS)
        if missing or extra:
            raise ControlRegisterError(f"record {record.get('record_id')!r}: missing {missing}, unknown {sorted(extra)}")
        if record["status"] not in CONTROL_STATUSES:
            raise ControlRegisterError(f"record {record['record_id']}: unknown status {record['status']!r}")
        if record["record_id"] in records:
            raise ControlRegisterError(f"duplicate record id {record['record_id']}")
        if not all(isinstance(record[f], str) and record[f] for f in
                   ("record_id", "title", "approval_date", "approval_source", "scope")):
            raise ControlRegisterError(f"record {record['record_id']}: empty provenance field")
        if record["status"] == "SUPERSEDED" and "superseded_by" not in record:
            raise ControlRegisterError(f"record {record['record_id']}: SUPERSEDED needs superseded_by")
        records[record["record_id"]] = record
    for record in records.values():
        for link in ("supersedes", "superseded_by"):
            if link in record and record[link] not in records:
                raise ControlRegisterError(f"record {record['record_id']}: {link} -> unknown {record[link]}")
    return records


def control_record_gaps(records: dict[str, dict[str, Any]]) -> list[str]:
    """Required pre-Step 6 control records that are absent or not in their required status."""
    gaps = []
    for record_id, status in REQUIRED_CONTROL_RECORDS.items():
        record = records.get(record_id)
        if record is None:
            gaps.append(f"{record_id}: missing")
        elif record["status"] != status:
            gaps.append(f"{record_id}: status {record['status']} != {status}")
    return gaps


__all__ = ["CONTROL_REGISTER_PATH", "CONTROL_STATUSES", "ControlRegisterError", "REQUIRED_CONTROL_RECORDS",
           "control_record_gaps", "load_control_register"]
