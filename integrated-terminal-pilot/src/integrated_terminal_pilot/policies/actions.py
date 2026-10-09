"""Declarative crane and yard actions (inputs to the Step 4 PhysicalActionValidator).

An action states an intention; it changes nothing. Returning a well-formed action
does not guarantee execution: the Step 4 validator is authoritative and rejects
illegal actions before any state mutation (integration specification §6).

Decision outcome classes:

* ``VALID_NO_ACTION`` — the policy legitimately proposes nothing (an action with
  ``action_type == "NO_ACTION"`` and a deterministic ``no_action_reason``).
* ``INVALID_INPUT`` — the observation is malformed; ``ObservationError`` is
  raised and no action exists.
* ``PHYSICAL_ACTION_REJECTION`` — reserved for the Step 4 validator; policies
  never produce it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from integrated_terminal_pilot.policies.observations import ID_PATTERNS

CRANE_ACTION_SCHEMA = "itp_crane_action_v1"
YARD_ACTION_SCHEMA = "itp_yard_action_v1"
VALID_NO_ACTION = "VALID_NO_ACTION"
INVALID_INPUT = "INVALID_INPUT"
PHYSICAL_ACTION_REJECTION = "PHYSICAL_ACTION_REJECTION"

CRANE_ACTION_TYPES = ("ASSIGN_CRANES", "NO_ACTION")
CRANE_NO_ACTION_REASONS = (
    "NO_ELIGIBLE_VESSEL",     # no berthed vessel in BERTHING_PREP/HANDLING with remaining work
    "MAX_CRANES_REACHED",     # every such vessel already holds max_cranes cranes
    "NO_AVAILABLE_CRANE",     # no crane in status available
    "NO_COMPATIBLE_CRANE",    # available cranes exist but none may serve an eligible vessel
)
YARD_ACTION_TYPES = ("ALLOCATE_BLOCK", "NO_ACTION")
YARD_NO_ACTION_REASONS = (
    "NO_OPEN_BLOCK",              # every block is closed or in maintenance
    "NO_SIZE_COMPATIBLE_BLOCK",   # open blocks exist, none accepts the container size
    "NO_CAPABLE_BLOCK",           # size-compatible open blocks lack the cargo capabilities
    "INSUFFICIENT_CAPACITY",      # eligible blocks exist, none passes the TEU test for the whole batch
)


class ActionContractError(ValueError):
    """An action violates its own contract (a policy implementation defect)."""


def _check_id(value: str, kind: str, where: str) -> None:
    if not isinstance(value, str) or not ID_PATTERNS[kind].match(value):
        raise ActionContractError(f"{where}: invalid {kind} id {value!r}.")


@dataclass(frozen=True)
class CraneAssignment:
    """Assign these currently available cranes to one vessel (crane ids in ascending order)."""

    vessel_id: str
    crane_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _check_id(self.vessel_id, "vessel", "CraneAssignment")
        if not isinstance(self.crane_ids, tuple) or not self.crane_ids:
            raise ActionContractError("CraneAssignment needs a non-empty tuple of crane ids.")
        for crane_id in self.crane_ids:
            _check_id(crane_id, "crane", "CraneAssignment")
        if list(self.crane_ids) != sorted(set(self.crane_ids)):
            raise ActionContractError("CraneAssignment crane ids must be unique and sorted.")


@dataclass(frozen=True)
class CraneAction:
    """Result of one CRANE decision: a set of assignments (and releases), or a no-op (spec §7).

    ``assignments`` are listed in the policy's vessel visit order. ``releases``
    names cranes to release voluntarily (only legal outside a batch, data
    contract §5); P_c never releases.
    """

    policy_id: str
    time_min: float
    action_type: str
    assignments: tuple[CraneAssignment, ...] = ()
    releases: tuple[str, ...] = ()
    no_action_reason: str | None = None
    decision_id: str | None = None
    schema_version: str = field(default=CRANE_ACTION_SCHEMA)

    def __post_init__(self) -> None:
        if self.action_type not in CRANE_ACTION_TYPES:
            raise ActionContractError(f"Unknown crane action type {self.action_type!r}.")
        if self.action_type == "NO_ACTION":
            if self.assignments or self.releases or self.no_action_reason not in CRANE_NO_ACTION_REASONS:
                raise ActionContractError("NO_ACTION carries no assignments and one known reason.")
        else:
            if not self.assignments or self.no_action_reason is not None:
                raise ActionContractError("ASSIGN_CRANES needs assignments and no reason.")
        vessels = [a.vessel_id for a in self.assignments]
        if len(vessels) != len(set(vessels)):
            raise ActionContractError("At most one assignment per vessel.")
        cranes = [c for a in self.assignments for c in a.crane_ids] + list(self.releases)
        if len(cranes) != len(set(cranes)):
            raise ActionContractError("A crane may appear in only one assignment or release.")

    @property
    def assigned_crane_ids(self) -> tuple[str, ...]:
        return tuple(sorted(c for a in self.assignments for c in a.crane_ids))


@dataclass(frozen=True)
class YardAction:
    """Destination-block intention for one request: exact container ids, one block, block level only.

    G0: the action names a block and nothing finer. There is deliberately no
    bay, row or tier field; Project 05 may add a slot action without changing
    this one.
    """

    policy_id: str
    time_min: float
    work_order_id: str
    action_type: str
    container_ids: tuple[str, ...]
    required_teu: float
    block_id: str | None = None
    no_action_reason: str | None = None
    decision_id: str | None = None
    schema_version: str = field(default=YARD_ACTION_SCHEMA)

    def __post_init__(self) -> None:
        if self.action_type not in YARD_ACTION_TYPES:
            raise ActionContractError(f"Unknown yard action type {self.action_type!r}.")
        if not isinstance(self.container_ids, tuple) or not self.container_ids:
            raise ActionContractError("A yard action names its exact container ids.")
        for container_id in self.container_ids:
            _check_id(container_id, "container", "YardAction")
        if list(self.container_ids) != sorted(set(self.container_ids)):
            raise ActionContractError("Yard action container ids must be unique and sorted.")
        if self.action_type == "ALLOCATE_BLOCK":
            _check_id(self.block_id, "block", "YardAction")
            if self.no_action_reason is not None:
                raise ActionContractError("ALLOCATE_BLOCK carries no reason.")
        elif self.block_id is not None or self.no_action_reason not in YARD_NO_ACTION_REASONS:
            raise ActionContractError("NO_ACTION carries no block and one known reason.")

    @property
    def container_count(self) -> int:
        return len(self.container_ids)


__all__ = [
    "CRANE_ACTION_SCHEMA", "CRANE_NO_ACTION_REASONS", "CraneAction", "CraneAssignment",
    "INVALID_INPUT", "PHYSICAL_ACTION_REJECTION", "VALID_NO_ACTION", "YARD_ACTION_SCHEMA",
    "YARD_NO_ACTION_REASONS", "ActionContractError", "YardAction",
]
