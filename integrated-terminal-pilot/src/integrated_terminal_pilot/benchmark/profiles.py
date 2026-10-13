"""Step 5 protocol profiles: the common yard primitive as a named choice, and the live approval state.

The common P_y is an explicit, recorded configuration of every comparison, never an implicit default:

* ``protocol_v1_first_fit`` - frozen protocol section 3 P_y ``yard_first_fit_v1``. This is the default
  while AM-01 is unapproved.
* ``am01_balanced_diagnostic`` - ``yard_occupancy_balance_v1`` (AM-01, PROPOSED). Development
  diagnostics only; never a finalized A-arm.

Approval state is read from the repository (decision register, AM-01 approval record) at run time,
so a run manifest always states what was and was not approved when it ran. Nothing here approves
anything.
"""

from __future__ import annotations

import re
from typing import Any

import yaml

from integrated_terminal_pilot.scenarios.config import PROJECT_ROOT

DECISIONS_PATH = PROJECT_ROOT / "configs" / "generator" / "itp_generator_v1_decisions.yaml"
AMENDMENTS_PATH = PROJECT_ROOT / "docs" / "protocol_amendments.md"
CRANE_POLICY_ID = "primitive_crane_greedy_v1"
REFERENCE_CRANE_COUNT = 4          # user-approved v1 reference fleet (S2-019), not a selected winner
EFFICIENCY_BASIS = "assigned"       # reference; "working" stays a Step 4 closure diagnostic

YARD_PROFILES: dict[str, dict[str, Any]] = {
    "protocol_v1_first_fit": {
        "yard_policy_id": "yard_first_fit_v1",
        "role": "frozen_protocol_default",
        "label": "Frozen protocol section 3 P_y (default while AM-01 is pending)",
    },
    "am01_balanced_diagnostic": {
        "yard_policy_id": "yard_occupancy_balance_v1",
        "role": "development_diagnostic",
        "label": "AM-01 PROPOSED balanced yard primitive - development diagnostic only, not a finalized A-arm",
    },
}
DEFAULT_YARD_PROFILE = "protocol_v1_first_fit"
PROFILE_BY_POLICY = {p["yard_policy_id"]: name for name, p in YARD_PROFILES.items()}

# Execution rules and coefficients the Step 5 runs exercise without approval.
PENDING_RULES = (
    {"id": "AM-01", "item": "common yard primitive yard_occupancy_balance_v1 for every arm",
     "where": "docs/protocol_amendments.md", "current_execution": "yard_first_fit_v1 (frozen protocol default)"},
    {"id": "D15", "item": "batch size 10 containers of one group", "where": "physics work.batch_size_containers",
     "current_execution": "10 (provisional)"},
    {"id": "D17", "item": "maximum load/rollover wait 240 min", "where": "physics work.max_load_wait_min",
     "current_execution": "240 min (provisional)"},
    {"id": "R5", "item": "at most one concurrent GATE_OUT batch per block, FIFO",
     "where": "docs/step4_physics_approval_audit.md", "current_execution": "on (Step 4 execution rule)"},
    {"id": "CARGO-RULE", "item": "cargo-compliance criterion for comparing arms (proposed in "
                                 "docs/step5_protocol_readiness.md section 4)",
     "where": "docs/step5_protocol_readiness.md", "current_execution": "reported as separate metrics only"},
    {"id": "FLEET", "item": "whether the approved four-crane reference stays the primary scientific fleet",
     "where": "S2-019 approval; Step 4 closure C2 diagnostics", "current_execution": "4 cranes"},
)


def yard_profile(name_or_policy: str) -> tuple[str, dict[str, Any]]:
    name = PROFILE_BY_POLICY.get(name_or_policy, name_or_policy)
    if name not in YARD_PROFILES:
        raise KeyError(f"unknown yard profile {name_or_policy!r}; known: {sorted(YARD_PROFILES)} or "
                       f"policy ids {sorted(PROFILE_BY_POLICY)}")
    return name, YARD_PROFILES[name]


def am01_status() -> str:
    text = AMENDMENTS_PATH.read_text(encoding="utf-8")
    section = text.split("## AM-01", 1)[1].split("\n## ", 1)[0]
    record = section.split("### Approval record", 1)[1] if "### Approval record" in section else ""
    status = re.search(r"\*\*Status:\*\*\s*([^\n]+)", section)
    approved = "APPROVED" in record.upper() and "PENDING" not in record.upper()
    return "APPROVED" if approved else (status.group(1).strip() if status else "UNKNOWN")


def approval_state() -> dict[str, Any]:
    register = yaml.safe_load(DECISIONS_PATH.read_text(encoding="utf-8"))
    records = register["records"]
    frozen = [r for r in records if r["status"] == "FROZEN"]
    pending = [r for r in records if r["status"] == "PROPOSED_PENDING_REVIEW"]
    approved = [r["decision_id"] for r in frozen if r.get("approval")]
    am01 = am01_status()
    lock = "BLOCKED" if pending or am01 != "APPROVED" else "READY_FOR_LOCK_REVIEW"
    return {
        "decision_register": str(DECISIONS_PATH.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "frozen": len(frozen), "proposed_pending_review": len(pending),
        "user_approved_reference_values": approved,
        "pending_records": [{"decision_id": r["decision_id"], "parameter": r["parameter_name"],
                             "value": r["selected_value"]} for r in pending],
        "am01": am01, "pending_rules": list(PENDING_RULES),
        "scientific_protocol_lock": lock,
    }


__all__ = ["CRANE_POLICY_ID", "DEFAULT_YARD_PROFILE", "EFFICIENCY_BASIS", "PENDING_RULES", "REFERENCE_CRANE_COUNT",
           "YARD_PROFILES", "am01_status", "approval_state", "yard_profile"]
