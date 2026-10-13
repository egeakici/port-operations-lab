"""Hand-written Step 5 fixtures (synthetic; 1200 m quay so every arm, including A3, can act on them).

``overrun_doc``: quiet physics (no transport, no yard limits), cranes at 30 moves/h = 2 min/move,
nominal service = 30 + 0.5 * moves + 20 (D20). Realized handling is 2 min/move, so every vessel
occupies the quay longer than its nominal service:

* V001 (360 m, 50 imports) arrives 0: nominal end 75, handling 30-130, departure prep 130-150.
* V002 (300 m, 10 imports) arrives 0: nominal end 55, handling 30-50, departs 70.
* V003 (300 m, 5 imports) arrives 100: V001 still occupies [0, 360] (nominal end 75 has passed).
* V004 (200 m, 5 imports) arrives 140: V001 has no remaining work but is in departure preparation.
* V005 (360 m, 5 imports) arrives 150, exactly when V001 departs.
"""

from __future__ import annotations

from typing import Any

from tests.step4_support import block, build_doc, container, crane, vessel


def recording(policy):
    """Wrap a berth policy and keep every BerthView it receives."""

    class Recorder:
        def __init__(self) -> None:
            self.policy = policy
            self.views = []

        def decide(self, view):
            self.views.append(view)
            return policy.decide(view)

    return Recorder()


def overrun_doc(*, hidden_vessel_arrival: float | None = None, pickup: float = 5000.0,
                block_capacity_teu: float = 96.0) -> dict[str, Any]:
    """The overrun timeline; the keyword arguments perturb only hidden or non-berth information:
    an extra vessel far beyond the 240 min horizon, landside pickup times, yard block capacity."""
    vessels = [vessel("V001", 0.0, 360.0), vessel("V002", 0.0, 300.0), vessel("V003", 100.0, 300.0),
               vessel("V004", 140.0, 200.0), vessel("V005", 150.0, 360.0)]
    plan = [("V001", 50), ("V002", 10), ("V003", 5), ("V004", 5), ("V005", 5)]
    if hidden_vessel_arrival is not None:
        vessels.append(vessel("V006", hidden_vessel_arrival, 250.0))
        plan.append(("V006", 5))
    containers, number = [], 0
    for vessel_id, count in plan:
        for _ in range(count):
            number += 1
            containers.append(container(number, "import", origin=vessel_id, pickup=pickup))
    return build_doc(vessels=vessels, containers=containers, blocks=[block("B01", 100.0, capacity=block_capacity_teu)],
                     cranes=[crane("QC01"), crane("QC02"), crane("QC03"), crane("QC04")])


def flows_doc() -> dict[str, Any]:
    """Import, export and transshipment with 20 ft and 40 ft boxes; every container reconciled."""
    vessels = [vessel("V001", 0.0, 300.0), vessel("V002", 600.0, 250.0)]
    containers = [
        container(1, "import", origin="V001", pickup=900.0),
        container(2, "import", size="40_ft", origin="V001", pickup=950.0),
        container(3, "export", dest="V001", block="B01"),
        container(4, "export", size="40_ft", dest="V002", gate_in=10.0),
        container(5, "transshipment", origin="V001", dest="V002"),
        container(6, "transshipment", size="40_ft", origin="V001", dest="V002"),
        container(7, "import", origin="V002", pickup=1200.0),
    ]
    return build_doc(vessels=vessels, containers=containers, cranes=[crane("QC01"), crane("QC02")])


__all__ = ["flows_doc", "overrun_doc", "recording"]
