"""Step 4: deterministic, cloneable integrated terminal kernel (D05, ADR ITP-ADR-001).

One authoritative physical transition model for berth occupancy, quay cranes,
transfer, yard storage/handling, landside requests and individual containers.
It executes Step 2 scenarios with the Step 3 primitive policies. It implements
no experimental arm, coordinator, PPO adapter or forward-model search.
"""

from integrated_terminal_pilot.simulator.catalog import PhysicsConfig, ScenarioCatalog
from integrated_terminal_pilot.simulator.drivers import (
    EpisodeRun, FcfsBerthIntegrationDriver, default_policies, run_episode,
)
from integrated_terminal_pilot.simulator.errors import (
    DecisionProtocolError, InvalidStatusTransition, InvariantViolation, KernelError, KernelLivelockError,
    KernelTimeError, PhysicalActionRejected, UnsupportedScenario,
)
from integrated_terminal_pilot.simulator.kernel import (
    DecisionRequest, EpisodeEnd, KERNEL_VERSION, KernelEventView, Paused, TerminalKernel,
)
from integrated_terminal_pilot.simulator.observations import BerthView, BerthVesselView
from integrated_terminal_pilot.simulator.validator import BerthAction, REJECTION_CODES

__all__ = [
    "BerthAction", "BerthView", "BerthVesselView", "DecisionProtocolError", "DecisionRequest", "EpisodeEnd",
    "EpisodeRun", "FcfsBerthIntegrationDriver", "InvalidStatusTransition", "InvariantViolation",
    "KERNEL_VERSION", "KernelError", "KernelEventView", "KernelLivelockError", "KernelTimeError", "Paused",
    "PhysicalActionRejected", "PhysicsConfig", "REJECTION_CODES", "ScenarioCatalog", "TerminalKernel",
    "UnsupportedScenario", "default_policies", "run_episode",
]
