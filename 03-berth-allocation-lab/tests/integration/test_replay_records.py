"""Read-only checks against selected genuine frozen replay scenarios."""

from pathlib import Path

import pytest

from berth_allocation_lab.replay import load_catalog, load_scenario
from berth_allocation_lab.replay.timeline import compare_compatible, decision_context, events_for

ROOT = Path(__file__).resolve().parents[2]


def test_catalog_covers_five_families_and_all_seeds():
    catalog = load_catalog(ROOT)
    assert len(catalog.scenarios) == 250
    assert {o.family for o in catalog.scenarios} == {"tiny_n6", "tiny_n7", "tiny_n8", "medium", "heavy"}
    assert set(catalog.sources) == {(regime, seed)
                                    for regime in ("tiny", "medium_heavy")
                                    for seed in (11, 23, 37)}


@pytest.mark.parametrize("scenario_id,seed", [
    ("dynamic_tiny_n6_test_seed6000023", 11),
    ("dynamic_medium_test_seed6000023", 23),
    ("dynamic_heavy_test_seed6000005", 37),
    ("dynamic_tiny_n8_test_seed6000461", 23),
])
def test_original_records_are_complete_and_physically_replayable(scenario_id, seed):
    catalog = load_catalog(ROOT)
    scenario = load_scenario(catalog, scenario_id, seed)
    compare_compatible(*scenario.runs.values())
    assert len(scenario.runs) == 3
    assert all(r.source_split == "test" and r.schedule_valid and
               len(r.vessels) == scenario.option.vessel_count and r.decisions and r.events
               for r in scenario.runs.values())
    assert all(events_for(r, 240)[-1].time_min >= max(v.service_end_time_min for v in r.vessels)
               for r in scenario.runs.values())
    if scenario_id.endswith("6000461"):
        waits = [d for d in scenario.runs["ppo"].decisions if d["action_type"] == "WAIT"]
        assert len(waits) == 3
        decision, state = decision_context(scenario.runs["ppo"], 240, waits[0]["decision_index"])
        assert decision["action_type"] == "WAIT" and state.waiting
