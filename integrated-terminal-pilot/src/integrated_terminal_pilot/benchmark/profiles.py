"""Protocol profiles and the live approval / lock state.

Two families of named configurations exist; neither is an implicit default:

* **Yard profiles** (Step 5, historical names kept so the Step 5 smoke plan stays reproducible):
  ``protocol_v1_first_fit`` (``yard_first_fit_v1``) and ``am01_balanced_diagnostic``
  (``yard_occupancy_balance_v1``). They run on the scenario's own four-crane fleet.
* **Research profiles** (pre-Step 6, AM-01/AM-02, 2026-10-13): a versioned physical configuration
  = crane fleet (derived in memory from the unchanged source scenario) + common P_c + common P_y +
  efficiency basis. ``itp_primary_balanced_qc8_v1`` is the approved primary research profile;
  ``itp_v1_reference_qc4_first_fit`` is the approved historical v1 reference; the balanced 4/6-crane
  profiles are predeclared capacity sensitivity levels, never "losing" arms.

Approval state is read from the repository at run time (decision register + protocol control
register). Nothing here approves anything, and the lock is never reported beyond
``READY_FOR_LOCK_REVIEW``; validation is never authorized by code.
"""

from __future__ import annotations

from typing import Any

import yaml

from integrated_terminal_pilot.benchmark.protocol_records import control_record_gaps, load_control_register
from integrated_terminal_pilot.scenarios.config import PROJECT_ROOT

DECISIONS_PATH = PROJECT_ROOT / "configs" / "generator" / "itp_generator_v1_decisions.yaml"
AMENDMENTS_PATH = PROJECT_ROOT / "docs" / "protocol_amendments.md"
# Protocol section 9: written exclusively at Step 7 from a clean worktree. Never created by Steps 1-6.
FORMAL_LOCK_PATH = PROJECT_ROOT / "protocol_lock_v1.json"
CRANE_POLICY_ID = "primitive_crane_greedy_v1"
REFERENCE_CRANE_COUNT = 4          # user-approved historical v1 reference fleet (S2-019)
EFFICIENCY_BASIS = "assigned"       # AM-05 / R1; "working" stays a Step 4 closure diagnostic

YARD_PROFILES: dict[str, dict[str, Any]] = {
    "protocol_v1_first_fit": {
        "yard_policy_id": "yard_first_fit_v1",
        "role": "frozen_protocol_default",
        "label": "Original protocol section 3 P_y on the historical four-crane fleet (Step 5 smoke "
                 "default; superseded as the primary P_y by AM-01 on 2026-10-13)",
    },
    "am01_balanced_diagnostic": {
        "yard_policy_id": "yard_occupancy_balance_v1",
        "role": "development_diagnostic",
        "label": "Balanced yard on the historical four-crane fleet (Step 5 diagnostic name, kept for "
                 "reproducibility; AM-01 approved 2026-10-13 - primary use is via research profiles)",
    },
}
DEFAULT_YARD_PROFILE = "protocol_v1_first_fit"
PROFILE_BY_POLICY = {p["yard_policy_id"]: name for name, p in YARD_PROFILES.items()}

PRIMARY_RESEARCH_PROFILE = "itp_primary_balanced_qc8_v1"
FLEET_DERIVATION_VERSION = "itp_fleet_derivation_v1 (simulator.diagnostics.derive_fleet)"
RESEARCH_PROFILES: dict[str, dict[str, Any]] = {
    "itp_v1_reference_qc4_first_fit": {
        "role": "APPROVED_HISTORICAL_V1_4QC", "quay_crane_count": 4, "yard_policy_id": "yard_first_fit_v1",
        "control_records": ["P3-PY-FF"],
        "label": "Approved historical v1 reference (S2-019 four cranes, original first-fit P_y); reproduction only",
    },
    PRIMARY_RESEARCH_PROFILE: {
        "role": "APPROVED_PRIMARY_RESEARCH_QC8", "quay_crane_count": 8,
        "yard_policy_id": "yard_occupancy_balance_v1", "control_records": ["AM-01", "AM-02"],
        "label": "Approved primary synthetic research profile: eight quay cranes, common balanced P_y",
    },
    "itp_sensitivity_balanced_qc4_v1": {
        "role": "SENSITIVITY_ONLY_QC4_QC6", "quay_crane_count": 4, "yard_policy_id": "yard_occupancy_balance_v1",
        "control_records": ["AM-01", "AM-02"],
        "label": "Predeclared capacity sensitivity level (4 cranes, balanced P_y); not a selectable primary",
    },
    "itp_sensitivity_balanced_qc6_v1": {
        "role": "SENSITIVITY_ONLY_QC4_QC6", "quay_crane_count": 6, "yard_policy_id": "yard_occupancy_balance_v1",
        "control_records": ["AM-01", "AM-02"],
        "label": "Predeclared capacity sensitivity level (6 cranes, balanced P_y); not a selectable primary",
    },
}
for _profile in RESEARCH_PROFILES.values():
    _profile.update(efficiency_basis=EFFICIENCY_BASIS, crane_policy_id=CRANE_POLICY_ID, max_cranes_per_vessel=2,
                    derivation_version=FLEET_DERIVATION_VERSION)


class ProfileSelectionError(ValueError):
    """An unknown profile, or an attempt to change the approved primary profile at run time."""


def research_profile(profile_id: str) -> dict[str, Any]:
    if profile_id not in RESEARCH_PROFILES:
        raise ProfileSelectionError(f"unknown research profile {profile_id!r}; known: {sorted(RESEARCH_PROFILES)}")
    return dict(RESEARCH_PROFILES[profile_id], profile_id=profile_id)


def assert_primary_profile_unchanged(proposed_primary: str, *, reason: str = "") -> None:
    """Safeguard S3: the primary fleet/profile is final for this protocol stage.

    Any code path that would switch the primary profile (e.g. after viewing policy diagnostics or PPO
    distribution shift) must call this and is refused. Reopening needs a recorded physical invalidity
    and a new owner decision, made outside the code.
    """
    if proposed_primary != PRIMARY_RESEARCH_PROFILE:
        raise ProfileSelectionError(
            f"automatic primary-profile change to {proposed_primary!r} refused ({reason or 'no reason given'}); "
            f"{PRIMARY_RESEARCH_PROFILE} is final (AM-02, safeguard S3)")


def yard_profile(name_or_policy: str) -> tuple[str, dict[str, Any]]:
    name = PROFILE_BY_POLICY.get(name_or_policy, name_or_policy)
    if name not in YARD_PROFILES:
        raise KeyError(f"unknown yard profile {name_or_policy!r}; known: {sorted(YARD_PROFILES)} or "
                       f"policy ids {sorted(PROFILE_BY_POLICY)}")
    return name, YARD_PROFILES[name]


def am01_status() -> str:
    """AM-01 status from the machine-readable control register (APPROVED_IN_EFFECT once approved)."""
    record = load_control_register().get("AM-01")
    return "UNKNOWN" if record is None else record["status"]


def approval_state() -> dict[str, Any]:
    register = yaml.safe_load(DECISIONS_PATH.read_text(encoding="utf-8"))
    records = register["records"]
    frozen = [r for r in records if r["status"] == "FROZEN"]
    pending = [r for r in records if r["status"] == "PROPOSED_PENDING_REVIEW"]
    approved = [r["decision_id"] for r in frozen if r.get("approval")]
    control = load_control_register()
    gaps = control_record_gaps(control)
    lock_present = FORMAL_LOCK_PATH.exists()
    blockers = ([f"{len(pending)} decision-register records PROPOSED_PENDING_REVIEW"] if pending else []) \
        + [f"control record {g}" for g in gaps] \
        + ([] if lock_present else ["formal Step 7 protocol_lock_v1.json not written (Step 7 only)"])
    review_ready = not pending and not gaps
    return {
        "decision_register": (str(DECISIONS_PATH.relative_to(PROJECT_ROOT)) if DECISIONS_PATH.is_relative_to(
            PROJECT_ROOT) else str(DECISIONS_PATH)).replace("\\", "/"),
        "frozen": len(frozen), "proposed_pending_review": len(pending),
        "user_approved_reference_values": approved,
        "pending_records": [{"decision_id": r["decision_id"], "parameter": r["parameter_name"],
                             "value": r["selected_value"]} for r in pending],
        "control_records": {k: v["status"] for k, v in control.items()},
        "control_record_gaps": gaps,
        "am01": control.get("AM-01", {}).get("status", "UNKNOWN"),
        "primary_research_profile": PRIMARY_RESEARCH_PROFILE,
        "formal_step7_lock_present": lock_present,
        "lock_blockers": blockers,
        "lock_review_readiness": "READY_FOR_LOCK_REVIEW" if review_ready else "NOT_READY",
        # Code never reports a lock beyond review readiness and never authorizes validation.
        "scientific_protocol_lock": "BLOCKED" if blockers else "READY_FOR_LOCK_REVIEW",
        "validation_authorized": False,
    }


__all__ = ["CRANE_POLICY_ID", "DEFAULT_YARD_PROFILE", "EFFICIENCY_BASIS", "FLEET_DERIVATION_VERSION",
           "FORMAL_LOCK_PATH", "PRIMARY_RESEARCH_PROFILE", "ProfileSelectionError", "REFERENCE_CRANE_COUNT",
           "RESEARCH_PROFILES", "YARD_PROFILES", "am01_status", "approval_state", "assert_primary_profile_unchanged",
           "research_profile", "yard_profile"]
