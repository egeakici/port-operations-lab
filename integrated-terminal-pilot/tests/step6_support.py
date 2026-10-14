"""Hand-written Step 6 fixtures (synthetic, development only).

``leakage_doc(variant)``: identical *observable* state at the first berth decision (t = 0), with the
hidden future perturbed per variant:

* ``base``     - V001 (arr 0) waiting, V002 announced (arr 120); hidden V003 arrives at 2000.
* ``vessel``   - hidden V003 arrives at 3000 with another length and more cargo (a: unrevealed vessel).
* ``landside`` - different future export gate-in times and import pickup times (b).
* ``queue``    - extra hidden landside events that tie in time with visible kernel events (c).
* ``link``     - the pre-staged transshipment box in the yard is linked to hidden V004 instead of V003 (d).
* ``seed``     - different scenario seed / identity (e).

Hidden-only containers carry the highest numbers so visible container and group ids never shift.
"""

from __future__ import annotations

from typing import Any

from integrated_terminal_pilot.scenarios.fingerprints import with_fingerprints
from tests.step4_support import block, build_doc, container, crane, physics, vessel


def _vessel(vessel_id, arrival, length):
    return vessel(vessel_id, arrival, length, max_cranes=2)


def leakage_doc(variant: str = "base") -> dict[str, Any]:
    hidden_arrival, hidden_length, hidden_extra = 2000.0, 250.0, 0
    gate_in, pickup = 1000.0, 3000.0
    link = "V003"
    if variant == "vessel":
        hidden_arrival, hidden_length, hidden_extra = 3000.0, 300.0, 6
    elif variant == "landside":
        gate_in, pickup = 1200.0, 4000.0
    elif variant == "queue":
        gate_in = 30.0          # ties with V001's berthing-preparation completion (if berthed at 0)
    elif variant == "link":
        link = "V004"
    vessels = [_vessel("V001", 0.0, 300.0), _vessel("V002", 120.0, 250.0), _vessel("V003", hidden_arrival, hidden_length)]
    if variant == "link":
        vessels.append(_vessel("V004", 2500.0, 250.0))
    containers = [
        container(1, "import", origin="V001", pickup=pickup),
        container(2, "import", size="40_ft", origin="V001", pickup=pickup + 50.0),
        container(3, "export", dest="V001", block="B01"),
        container(4, "export", size="40_ft", dest="V002", block="B02"),
        container(5, "import", origin="V002", pickup=pickup),
        container(6, "export", dest="V002", block="B01"),
        # hidden future (numbers >= 50): cargo of the unannounced vessel(s)
        container(50, "export", dest="V003", gate_in=gate_in),
        container(51, "import", origin="V003", pickup=hidden_arrival + 900.0),
        container(52, "transshipment", dest=link, block="B02"),
    ]
    containers += [container(60 + k, "import", origin="V003", pickup=hidden_arrival + 950.0) for k in range(hidden_extra)]
    if variant == "link":
        containers.append(container(53, "export", dest="V003", gate_in=gate_in))
    doc = build_doc(vessels=vessels, containers=containers,
                    blocks=[block("B01", 100.0), block("B02", 600.0)],
                    cranes=[crane(f"QC{n:02d}") for n in range(1, 5)],
                    physics_doc=physics(**{"yard.constraints_enabled": False}))
    if variant == "seed":
        new_id = "itp_fixture_development_seed10000042"
        doc["identity"]["scenario_seed"] = 10_000_042
        doc["identity"]["scenario_id"] = new_id
        for record in doc["containers"]:
            record["source_scenario_id"] = new_id
        doc = with_fingerprints(doc, generator_config_fingerprint=None)
    return doc


def b1_choice_doc(far_cargo_vessel: str | None = "V001") -> dict[str, Any]:
    """Two vessels with equal workload waiting at t = 0. ``far_cargo_vessel``'s export cargo sits in a
    far block (transport-bound); the other vessel's in a near block. ``None``: both near (no
    resource difference)."""
    far = {"V001": "B02", "V002": "B01"} if far_cargo_vessel == "V001" else (
        {"V001": "B01", "V002": "B02"} if far_cargo_vessel == "V002" else {"V001": "B01", "V002": "B01"})
    containers, number = [], 0
    for vid in ("V001", "V002"):
        for _ in range(12):
            number += 1
            containers.append(container(number, "export", dest=vid, block=far[vid]))
    return build_doc(vessels=[_vessel("V001", 0.0, 300.0), _vessel("V002", 0.0, 300.0)], containers=containers,
                     blocks=[block("B01", 100.0, capacity=96.0), block("B02", 1100.0, y=900.0, capacity=96.0)],
                     cranes=[crane(f"QC{n:02d}") for n in range(1, 5)],
                     physics_doc=physics(**{"yard.constraints_enabled": False}))


__all__ = ["b1_choice_doc", "leakage_doc"]
