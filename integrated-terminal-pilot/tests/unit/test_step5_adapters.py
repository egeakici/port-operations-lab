"""Step 5 adapter, policy and safety tests (brief section 16, items 1-10, 14).

Hand-built fixtures (tests/step5_support.py) and synthetic ``BerthView`` objects. Checkpoints are
loaded read-only on CPU for inference only; nothing is trained or written.
"""

from __future__ import annotations

import dataclasses
import inspect

import numpy as np
import pytest

from integrated_terminal_pilot.benchmark import adapter as adapter_module
from integrated_terminal_pilot.benchmark import policies as policies_module
from integrated_terminal_pilot.benchmark.adapter import (
    AdapterContractError, adapt_berth_view, dynamic_observation, visible_state,
)
from integrated_terminal_pilot.benchmark.checkpoints import (
    AUDITED_SHA256, CheckpointRef, file_sha256, static_checkpoint_gates, verify_all_hashes,
)
from integrated_terminal_pilot.benchmark.policies import (
    NON_PPO_CANDIDATE_CAPACITY, OnlineFcfsBerthPolicy, create_berth_policy,
)
from integrated_terminal_pilot.benchmark.profiles import (
    DEFAULT_YARD_PROFILE, YARD_PROFILES, am01_status, approval_state, yard_profile,
)
from integrated_terminal_pilot.policies import FirstFitYardPolicy, GreedyBerthOrderCranePolicy
from integrated_terminal_pilot.scenarios.berth_projection import build_berth_projection
from integrated_terminal_pilot.simulator import PhysicalActionRejected, run_episode
from integrated_terminal_pilot.simulator.kernel import DecisionRequest
from integrated_terminal_pilot.simulator.observations import BerthVesselView, BerthView
from integrated_terminal_pilot.simulator.validator import BerthAction
from tests.step4_support import kernel_for, vessel_times
from tests.step5_support import overrun_doc, recording

SEEDS = (11, 23, 37)


def _run(doc, policy):
    kernel = kernel_for(doc)
    rec = recording(policy)
    outcome = run_episode(kernel, berth_policy=rec, crane_policy=GreedyBerthOrderCranePolicy(),
                          yard_policy=FirstFitYardPolicy())
    return kernel, rec, outcome


def _policy(arm, seed=None, doc=None):
    return create_berth_policy(arm, training_seed=seed,
                               host_projection=build_berth_projection(doc or overrun_doc()) if arm == "A3" else None)


ARMS = [("A1", None), ("A2", None), ("A3", 11), ("A3", 23), ("A3", 37)]


def _vessel(vid, slot, status, arrival, length=300.0, service=100.0, position=None, start=None, release=None):
    return BerthVesselView(vid, slot, status, arrival, length, service, position, start, release)


def _view(vessels, legal, wait_legal, t=100.0, quay=1200.0):
    return BerthView(time_min=t, decision_id="D1", berth_length_m=quay, min_clearance_m=20.0,
                     future_horizon_min=240.0, vessels=tuple(vessels), legal_choices=tuple(legal),
                     wait_legal=wait_legal)


# 1 ---------------------------------------------------------------- registry and source contracts
def test_registry_is_deterministic_and_never_pools_checkpoints():
    assert create_berth_policy("A1").policy_id == "a1_p03_dynamic_online_fcfs_v1"
    assert create_berth_policy("A2").policy_id == "a2_p03_dynamic_online_rollout_v1"
    projection = build_berth_projection(overrun_doc())
    ids = {create_berth_policy("A3", training_seed=s, host_projection=projection).policy_id for s in SEEDS}
    assert ids == {f"a3_p03_dynamic_maskable_ppo_v1_medium_heavy_train_seed{s}" for s in SEEDS}
    for bad in ({"arm_id": "A3"}, {"arm_id": "A3", "training_seed": 99}, {"arm_id": "A1", "training_seed": 11}):
        with pytest.raises(ValueError):
            create_berth_policy(**bad, host_projection=projection)
    with pytest.raises(KeyError):
        create_berth_policy("B1")


def test_policy_layer_reads_only_the_berth_view():
    source = inspect.getsource(policies_module) + inspect.getsource(adapter_module)
    for forbidden in ("TerminalKernel", ".clone(", "observable_clone", "peek_next_event", "online_rollout_action(",
                      "state.events", "_scenario_truth"):
        assert forbidden not in source, forbidden
    kernel = kernel_for(overrun_doc())
    with pytest.raises(AdapterContractError) as error:   # a leaky "env-like" truth object is refused
        create_berth_policy("A2").decide(kernel)
    assert error.value.gate == "G20"


# 2 ---------------------------------------------------------------- hidden future does not change decisions
@pytest.mark.parametrize("arm,seed", ARMS)
def test_hidden_future_perturbations_leave_views_and_decisions_unchanged(arm, seed):
    base = overrun_doc()
    perturbed = overrun_doc(hidden_vessel_arrival=4000.0, pickup=7000.0, block_capacity_teu=90.0)
    _, rec_a, _ = _run(base, _policy(arm, seed, base))
    _, rec_b, _ = _run(perturbed, _policy(arm, seed, base))
    assert len(rec_a.views) == 5
    assert rec_a.views == rec_b.views[:5]          # identical admitted observations (dataclass equality)
    assert [r["p03_action"] for r in rec_a.policy.records] == [r["p03_action"] for r in rec_b.policy.records[:5]]
    assert all("V006" not in {v.vessel_id for v in view.vessels} for view in rec_b.views[:5])
    assert all("V006" not in visible_state(adapt_berth_view(v, candidate_capacity=48)).__repr__()
               for v in rec_b.views[:5])


# 3 ---------------------------------------------------------------- A1 FCFS semantics
def test_a1_fcfs_order_ties_positions_and_never_waits():
    vessels = [_vessel("V002", 0, "WAITING", 50.0), _vessel("V001", 1, "WAITING", 50.0),
               _vessel("V003", 2, "ANNOUNCED", 200.0)]
    legal = [("V002", 0, 0.0, 50.0), ("V002", 1, 900.0, 50.0), ("V001", 0, 0.0, 50.0), ("V001", 1, 900.0, 50.0)]
    action = OnlineFcfsBerthPolicy().decide(_view(vessels, legal, True))
    # equal arrival -> lower vessel id; then lowest continuous position; WAIT is legal but never chosen
    assert (action.action_type, action.vessel_id, action.berth_position_m) == ("ASSIGN", "V001", 0.0)


def test_a1_runs_the_overrun_fixture_with_fcfs_positions():
    kernel, rec, outcome = _run(overrun_doc(), create_berth_policy("A1"))
    assert outcome.status == "COMPLETED"
    assert [(r["time_min"], r["vessel_id"], r["berth_position_m"]) for r in rec.policy.records] == [
        (0.0, "V001", 0.0), (0.0, "V002", 380.0), (100.0, "V003", 380.0), (140.0, "V004", 700.0),
        (150.0, "V005", 0.0)]
    assert all(r["action_type"] == "ASSIGN" for r in rec.policy.records)


# 4 ---------------------------------------------------------------- A2 rollout budget and repeatability
def test_a2_scores_every_legal_action_repeatably():
    _, rec, _ = _run(overrun_doc(), create_berth_policy("A2"))
    view = rec.views[2]   # t = 100: V003 waiting, V001 overrunning
    first, second = create_berth_policy("A2"), create_berth_policy("A2")
    a, b = first.decide(view), second.decide(view)
    assert a == b and first.records[0]["scores"] == second.records[0]["scores"]
    state = adapt_berth_view(view, candidate_capacity=NON_PPO_CANDIDATE_CAPACITY)
    expected = len(state.legal_choices) + int(state.wait_legal)
    assert first.records[0]["root_evaluations"] == expected
    assert [s[0] for s in first.records[0]["scores"]] == ([0] if state.wait_legal else []) + [
        c[0] for c in state.legal_choices]
    budget = create_berth_policy("A2").describe()["search_budget"]
    assert budget["timeout"] == "none" and budget["fallback"] == "none"


# 5 ---------------------------------------------------------------- A3 checkpoints
@pytest.mark.parametrize("seed", SEEDS)
def test_a3_checkpoint_hash_shapes_mask_and_deterministic_inference(seed):
    ref = CheckpointRef("medium_heavy", seed)
    assert file_sha256(ref.model_path) == AUDITED_SHA256[("medium_heavy", seed)]
    assert static_checkpoint_gates(ref)["pass"]
    policy = _policy("A3", seed)
    _, rec, outcome = _run(overrun_doc(), policy)
    assert outcome.status == "COMPLETED" and not outcome.rejections
    space = policy.loaded.model.observation_space
    for view, record in zip(rec.views, policy.records):
        observation, mask = dynamic_observation(adapt_berth_view(view, candidate_capacity=48), max_vessels=24)
        assert set(observation) == set(space.spaces) and space.contains(observation)
        assert mask.shape == (1153,) and mask[record["p03_action"]]
        assert mask[0] == view.wait_legal
        assert policy.loaded.predict(observation, mask) == policy.loaded.predict(observation, mask) == \
            record["p03_action"]
    assert policy.describe()["checkpoint"]["sha256"] == AUDITED_SHA256[("medium_heavy", seed)]


def test_a3_masked_wait_and_no_out_of_support_padding():
    vessels = [_vessel("V001", 0, "WAITING", 50.0)]
    observation, mask = dynamic_observation(adapt_berth_view(_view(
        vessels, [("V001", 0, 0.0, 50.0), ("V001", 1, 900.0, 50.0)], False), candidate_capacity=48), max_vessels=24)
    assert not mask[0] and mask[1] and mask[2] and mask.sum() == 2
    crowded = [_vessel(f"V{n:03d}", n, "DEPARTED", 0.0) for n in range(24)] + [_vessel("V099", 24, "WAITING", 50.0)]
    state = adapt_berth_view(_view(crowded, [("V099", 0, 0.0, 50.0), ("V099", 1, 900.0, 50.0)], False),
                             candidate_capacity=48)
    with pytest.raises(AdapterContractError) as error:
        dynamic_observation(state, max_vessels=24)
    assert error.value.gate == "G11"


def test_tiny_checkpoints_are_blocked_for_every_project_i_family():
    from integrated_terminal_pilot.benchmark.development import family_matrix

    tiny = [r for r in family_matrix() if r.get("regime") == "tiny"]
    assert len(tiny) == 12 and all(r["status"] == "BLOCK" and any("G12" in x for x in r["reasons"]) for r in tiny)
    medium = [r for r in family_matrix() if r.get("regime") == "medium_heavy"]
    assert all(r["status"].startswith("PASS") for r in medium)


# 6 / 10 (service mapping) ------------------------------------------ estimated vs realized service
def test_overrun_keeps_the_berth_blocked_and_substitutes_the_forecast():
    kernel, rec, outcome = _run(overrun_doc(), create_berth_policy("A1"))
    view = rec.views[2]                                        # t = 100, V001 nominal end 75 has passed
    v001 = next(v for v in view.vessels if v.vessel_id == "V001")
    assert (view.time_min, v001.status, v001.estimated_release_time_min) == (100.0, "OCCUPYING", 150.0)
    state = adapt_berth_view(view, candidate_capacity=48)
    placement = dict(state.placement_by_id)["V001"]
    assert placement.service_end_time_min == 150.0 and placement.service_time_min == 150.0   # not nominal 75
    assert state.forecast_epoch_mode == "FORECAST"
    assert all(position >= 380.0 for _, _, _, position, _ in state.legal_choices)   # [0, 360] + clearance stays blocked
    observation, _ = dynamic_observation(state, max_vessels=24)
    assert observation["placement_features"][0, 2] == np.float32((150.0 - 100.0) / 1440.0) > 0
    assert observation["vessel_features"][0, 2] == np.float32(75.0 / 1440.0)       # nominal service immutable
    assert vessel_times(kernel, "V001")["departure"] == 150.0


def test_zero_remaining_work_in_departure_prep_still_occupies_until_departure():
    kernel, rec, _ = _run(overrun_doc(), create_berth_policy("A1"))
    view = rec.views[3]                                        # t = 140, V001 handling ended at 130
    assert vessel_times(kernel, "V001")["handling_end"] == 130.0
    v001 = next(v for v in view.vessels if v.vessel_id == "V001")
    assert (view.time_min, v001.status, v001.estimated_release_time_min) == (140.0, "OCCUPYING", 150.0)
    assert all(x >= 380.0 for _, _, x, _ in view.legal_choices)


def test_exact_boundary_departure_is_processed_before_the_decision():
    _, rec, _ = _run(overrun_doc(), create_berth_policy("A1"))
    view = rec.views[4]                                        # t = 150 = V001 departure = V005 arrival
    statuses = {v.vessel_id: v.status for v in view.vessels}
    assert view.time_min == 150.0 and statuses["V001"] == "DEPARTED" and statuses["V005"] == "WAITING"
    assert view.legal_choices == (("V005", 0, 0.0, 150.0),)


def test_waiting_vessel_exposes_nominal_service_only():
    _, rec, _ = _run(overrun_doc(), create_berth_policy("A1"))
    v003 = next(v for v in rec.views[2].vessels if v.vessel_id == "V003")
    assert v003.status == "WAITING" and v003.estimated_release_time_min is None
    assert v003.nominal_service_time_min == 52.5


def test_forecast_at_or_before_now_is_a_kernel_defect_not_clamped():
    occupying = _vessel("V001", 0, "OCCUPYING", 0.0, position=0.0, start=0.0, release=100.0)
    with pytest.raises(AdapterContractError) as error:
        adapt_berth_view(_view([occupying, _vessel("V002", 1, "WAITING", 50.0)], [], False), candidate_capacity=48)
    assert error.value.gate == "G17"


def test_adapter_rejects_mismatched_legal_sets_slots_and_wait_bits():
    vessels = [_vessel("V001", 0, "WAITING", 50.0)]
    good = [("V001", 0, 0.0, 50.0), ("V001", 1, 900.0, 50.0)]
    adapt_berth_view(_view(vessels, good, False), candidate_capacity=48)
    for legal, wait, slot, gate in ((good[:1], False, 0, "G08"), (good, True, 0, "G08"), (good, False, 3, "G10")):
        bad = [dataclasses.replace(vessels[0], slot_index=slot)]
        with pytest.raises(AdapterContractError) as error:
            adapt_berth_view(_view(bad, legal, wait), candidate_capacity=48)
        assert error.value.gate == gate
    with pytest.raises(AdapterContractError) as error:
        adapt_berth_view(_view(vessels, good, False), candidate_capacity=1)
    assert error.value.gate == "G09"


# 7 ---------------------------------------------------------------- invalid / stale actions
def test_invalid_and_stale_actions_are_rejected_without_state_mutation():
    kernel = kernel_for(overrun_doc())
    policy = create_berth_policy("A1")
    while True:
        request = kernel.advance()
        assert isinstance(request, DecisionRequest)
        if request.kind == "BERTH" and kernel.current_time_min == 100.0:
            break
        if request.kind == "BERTH":
            kernel.apply_berth_action(policy.decide(kernel.berth_view()))
        elif request.kind == "CRANE":
            kernel.apply_crane_action(GreedyBerthOrderCranePolicy().decide(kernel.crane_observation()))
        else:
            kernel.apply_yard_action(FirstFitYardPolicy().decide(kernel.yard_observation()))
    decision_id = kernel.state.pending.decision_id
    before = kernel.snapshot()
    for action, code in ((BerthAction.assign("x", "V003", 0.0, decision_id), "BERTH_OCCUPIED"),
                         (BerthAction.assign("x", "V001", 900.0, decision_id), "VESSEL_NOT_WAITING"),
                         (BerthAction.assign("x", "V003", 380.0, "STALE-ID"), "STALE_ACTION")):
        with pytest.raises(PhysicalActionRejected) as error:
            kernel.apply_berth_action(action)
        assert error.value.rejection_code == code
        assert kernel.snapshot() == before


def test_illegal_policy_output_fails_the_run_without_repair():
    class Illegal(OnlineFcfsBerthPolicy):
        policy_id = "test_illegal"

        def _choose(self, state):
            return 1 + 23 * 48, {}          # a well-formed index that is not in the legal set

    class IllegalWait(OnlineFcfsBerthPolicy):
        policy_id = "test_illegal_wait"

        def _choose(self, state):
            return 0, {}

    kernel, _, outcome = _run(overrun_doc(), Illegal())
    assert outcome.status == "FAILED" and "BERTH_POLICY_GATE_G19" in outcome.failure
    assert all(v.berth_start_time_min is None for v in kernel.state.vessels.values())
    # Always-WAIT: legal while a visible future event exists; once none exists
    # the masked WAIT fails the run (G19) instead of being replaced by an assignment. Nothing is berthed,
    # so at t = 150 (last arrival) no visible future event remains.
    kernel, rec, outcome = _run(overrun_doc(), IllegalWait())
    assert outcome.status == "FAILED" and "BERTH_POLICY_GATE_G19" in outcome.failure
    assert rec.views[-1].wait_legal is False and rec.views[-1].time_min == 150.0
    assert all(v.berth_start_time_min is None for v in kernel.state.vessels.values())


# 8 / 9 ------------------------------------------------------------ fairness and metadata
def test_profiles_are_explicit_and_am01_is_not_approved():
    assert DEFAULT_YARD_PROFILE == "protocol_v1_first_fit"
    assert yard_profile("yard_first_fit_v1")[0] == "protocol_v1_first_fit"
    assert YARD_PROFILES["am01_balanced_diagnostic"]["role"] == "development_diagnostic"
    assert am01_status() != "APPROVED"
    state = approval_state()
    assert state["scientific_protocol_lock"] == "BLOCKED"
    assert state["frozen"] == 23 and state["proposed_pending_review"] == 29
    assert len(state["user_approved_reference_values"]) == 10


# 14 --------------------------------------------------------------- integrity
def test_frozen_checkpoints_and_decision_file_are_unchanged():
    report = verify_all_hashes()
    assert report["ok"], report
    assert len(report["checkpoints"]) == 6
