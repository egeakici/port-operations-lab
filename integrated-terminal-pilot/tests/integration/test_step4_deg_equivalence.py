"""Degenerate equivalence gate (implementation roadmap, Step 4).

The integrated kernel with the degenerate physics profile, driven by the Project 03
online FCFS rule (integration fixture) plus P_c / P_y, must reproduce the real
Project 03 ``DynamicBAPEnv`` + ``online_fcfs_action`` on the berth projection.

The fast tests cover the first seed of every family. The full gate (30 medium,
30 heavy, 10 low, 10 bottleneck contiguous development seeds) is the opt-in ``slow``
test (``ITP_RUN_SLOW=1``) and ``scripts/run_degenerate_equivalence.py``.
"""

from __future__ import annotations

import os

import pytest

from integrated_terminal_pilot.scenarios import generate_scenario
from integrated_terminal_pilot.simulator.equivalence import degenerate_equivalence

pytestmark = pytest.mark.integration
FIRST_SEED = 10_000_000
FULL_GATE = {"itp_medium": 30, "itp_heavy": 30, "itp_low": 10, "itp_yard_bottleneck": 10}


@pytest.mark.parametrize("family", ["itp_medium", "itp_heavy", "itp_low", "itp_yard_bottleneck"])
def test_degenerate_equivalence_first_seed(config, family):
    doc = generate_scenario(config, family, "development", FIRST_SEED, "degenerate_equivalence_v1")
    report = degenerate_equivalence(doc)
    assert report["pass"], report
    assert report["errors"]["max_position_m"] <= 1e-9
    assert report["errors"]["max_start_min"] <= 1e-6
    assert report["reference"]["wait_actions"] == 0


@pytest.mark.slow
@pytest.mark.skipif(os.environ.get("ITP_RUN_SLOW") != "1", reason="full gate: set ITP_RUN_SLOW=1 "
                    "(or run scripts/run_degenerate_equivalence.py)")
@pytest.mark.parametrize("family", sorted(FULL_GATE))
def test_degenerate_equivalence_full_gate(config, family):
    failures = []
    for seed in range(FIRST_SEED, FIRST_SEED + FULL_GATE[family]):
        doc = generate_scenario(config, family, "development", seed, "degenerate_equivalence_v1")
        report = degenerate_equivalence(doc, validate=False)
        if not report["pass"]:
            failures.append((seed, report["checks"], report["errors"]))
    assert not failures, failures
