"""Step 6 gates G6-01 ... G6-15 on hand-written fixtures (fast; no development scenario needed)."""

from __future__ import annotations

import dataclasses
import pickle

import pytest

from integrated_terminal_pilot.benchmark import coordination_policies as cp
from integrated_terminal_pilot.benchmark.coordination_policies import (
    A1nNominalGreedyPolicy, B1IntegratedGreedyPolicy, CandidatePrediction, EvaluationRecord, IntegratedRolloutPolicy,
    LeafPrediction, SharedRolloutEvaluator, effective_leaf, pivotal_diagnostic, select,
)
from integrated_terminal_pilot.benchmark.coordination_view import (
    ALLOWLIST, UNREVEALED, CoordinationView, CoordinationViewError, build_coordination_view, coordination_observer,
)
from integrated_terminal_pilot.benchmark.policies import OnlineFcfsBerthPolicy, create_berth_policy
from integrated_terminal_pilot.benchmark.profiles import approval_state
from integrated_terminal_pilot.benchmark.protocol_records import load_control_register
from integrated_terminal_pilot.policies import GreedyBerthOrderCranePolicy, create_policy
from integrated_terminal_pilot.simulator import PhysicalActionRejected, run_episode
from integrated_terminal_pilot.simulator.kernel import DecisionRequest
from tests.step4_support import kernel_for
from tests.step6_support import b1_choice_doc, leakage_doc

YARD = "yard_occupancy_balance_v1"
VARIANTS = ("vessel", "landside", "queue", "link", "seed")


def _first_berth_kernel(doc):
    kernel = kernel_for(doc, invariant_mode="cheap")
    crane, yard = GreedyBerthOrderCranePolicy(), create_policy(YARD)
    while True:
        request = kernel.advance()
        assert isinstance(request, DecisionRequest)
        if request.kind == "BERTH":
            return kernel
        if request.kind == "CRANE":
            kernel.apply_crane_action(crane.decide(kernel.crane_observation()))
        else:
            kernel.apply_yard_action(yard.decide(kernel.yard_observation()))


# G6-01 ----------------------------------------------------------------------- protocol preflight
def test_g6_01_protocol_state_is_unchanged_and_locked():
    state = approval_state()
    assert (state["frozen"], state["proposed_pending_review"]) == (24, 28)
    assert state["scientific_protocol_lock"] == "BLOCKED" and state["validation_authorized"] is False
    records = load_control_register()
    assert records["AM-07"]["status"] == records["AM-08"]["status"] == "APPROVED_FOR_STEP6_DESIGN_NOT_VALIDATION_LOCKED"
    assert cp.B1_ESTIMATOR["status"] == "PROPOSED_STEP6_DETAIL_NEEDS_OWNER_APPROVAL"


# G6-02 ----------------------------------------------------------------------- information contract
def test_g6_02_view_is_frozen_allowlisted_and_free_of_hidden_truth():
    view = build_coordination_view(_first_berth_kernel(leakage_doc()), include_projection=True)
    assert set(f.name for f in dataclasses.fields(CoordinationView)) - {"schema", "time_min", "decision_id",
                                                                         "digest"} == set(ALLOWLIST)
    with pytest.raises(dataclasses.FrozenInstanceError):
        view.time_min = 5.0
    assert {v.vessel_id for v in view.vessels} == {"V001", "V002"}          # hidden V003 absent
    assert "V003" not in repr((view.berth, view.vessels, view.cranes, view.blocks))
    catalog = view.projection.catalog
    assert catalog.identity is None and catalog.fingerprints is None and catalog.scenario_id is None
    assert {v.vessel_id for v in catalog.vessels} == {"V001", "V002"}
    assert all(c.gate_in_time_min is None for c in catalog.containers)
    assert all(c.destination_vessel_id in {"V001", "V002", UNREVEALED, None} for c in catalog.containers)
    state = pickle.loads(view.projection.state_bytes)
    assert state.ledger is None and state.event_log is None and set(state.vessels) == {"V001", "V002"}
    assert not any(e[4] in ("GATE_IN_ARRIVAL", "PICKUP_DUE", "VESSEL_ARRIVAL", "HORIZON_ENTRY") and e[2] == "V003"
                   for e in state.events)
    assert [e[3] for e in sorted(state.events)] == list(range(1, len(state.events) + 1))   # renumbered


def test_g6_02_policies_refuse_a_raw_kernel_or_foreign_objects():
    kernel = _first_berth_kernel(leakage_doc())
    for policy in (B1IntegratedGreedyPolicy(), IntegratedRolloutPolicy("B2", YARD), IntegratedRolloutPolicy("B2-T", YARD)):
        for bad in (kernel, kernel.state, kernel.catalog, {"berth": kernel.berth_view()}):
            with pytest.raises(CoordinationViewError):
                policy.decide(bad)
    no_projection = build_coordination_view(kernel, include_projection=False)
    with pytest.raises(CoordinationViewError):
        IntegratedRolloutPolicy("B2", YARD).decide(no_projection)


# G6-03 / G6-10 ---------------------------------------------------------------- hidden-future isolation
@pytest.mark.parametrize("variant", VARIANTS)
def test_g6_03_hidden_future_perturbations_do_not_change_inputs_predictions_or_actions(variant):
    base_kernel, other_kernel = _first_berth_kernel(leakage_doc()), _first_berth_kernel(leakage_doc(variant))
    assert base_kernel.catalog.fingerprints != other_kernel.catalog.fingerprints     # the truths differ
    base = build_coordination_view(base_kernel, include_projection=True)
    other = build_coordination_view(other_kernel, include_projection=True)
    assert base.digest == other.digest and base.projection.digest == other.projection.digest
    evaluator = SharedRolloutEvaluator(YARD)
    a, b = evaluator.evaluate(base), evaluator.evaluate(other)
    assert a.prediction_digest == b.prediction_digest and a.candidates == b.candidates
    for selector in ("B2", "B2-T"):
        assert select(a, selector).action == select(b, selector).action
    assert B1IntegratedGreedyPolicy().decide(base) == B1IntegratedGreedyPolicy().decide(other)


def test_g6_03_visible_resource_perturbation_reaches_b_arms_but_not_a_arms():
    near, far = _first_berth_kernel(b1_choice_doc(None)), _first_berth_kernel(b1_choice_doc("V001"))
    assert near.berth_view() == far.berth_view()                      # A arms: identical BerthView
    assert OnlineFcfsBerthPolicy().decide(near.berth_view()) == OnlineFcfsBerthPolicy().decide(far.berth_view())
    v_near = build_coordination_view(near, include_projection=False)
    v_far = build_coordination_view(far, include_projection=False)
    assert v_near.digest != v_far.digest                              # B arms: observable yard state differs
    choice_near = B1IntegratedGreedyPolicy().decide(v_near)
    choice_far = B1IntegratedGreedyPolicy().decide(v_far)
    assert choice_near.vessel_id == "V001" and choice_far.vessel_id == "V002"


def test_g6_10_decisions_never_reach_back_into_the_live_kernel():
    kernel = _first_berth_kernel(leakage_doc())
    view = build_coordination_view(kernel, include_projection=True)
    kernel.state, kernel.catalog = None, None                          # poison the real kernel
    for policy in (B1IntegratedGreedyPolicy(), IntegratedRolloutPolicy("B2", YARD)):
        policy.decide(view)                                           # still works: no path back


# G6-04 ----------------------------------------------------------------------- legality
def test_g6_04_actions_come_from_the_physical_legal_set_and_pass_the_validator():
    kernel = _first_berth_kernel(leakage_doc())
    view = build_coordination_view(kernel, include_projection=True)
    legal = {(v, x) for v, _, x, _ in kernel.berth_view().legal_choices}
    for policy in (B1IntegratedGreedyPolicy(), IntegratedRolloutPolicy("B2", YARD),
                   IntegratedRolloutPolicy("B2-T", YARD)):
        action = policy.decide(view)
        assert action.action_type == "WAIT" and kernel.berth_wait_legal() or \
            (action.vessel_id, action.berth_position_m) in legal
        clone = kernel.clone()
        clone.apply_berth_action(action)                              # the Step 4 validator accepts it
    stale = dataclasses.replace(B1IntegratedGreedyPolicy().decide(view), decision_id="DEC-99999999")
    with pytest.raises(PhysicalActionRejected):
        kernel.clone().apply_berth_action(stale)


# G6-06 ----------------------------------------------------------------------- B1 / A1n
def test_g6_06_b1_is_deterministic_greedy_and_differs_from_a1n_only_through_observable_resources():
    kernel = _first_berth_kernel(b1_choice_doc("V001"))
    view = build_coordination_view(kernel, include_projection=False)
    b1 = B1IntegratedGreedyPolicy()
    first, again = b1.decide(view), B1IntegratedGreedyPolicy().decide(view)
    assert first == again and first.vessel_id == "V002"               # V001's cargo is transport-bound
    record = b1.records[0]
    assert record["tie_break"] == "(estimated release, arrival, vessel_id, position)"
    assert all(c["release_min"] > view.time_min for c in record["candidates"])
    a1n = A1nNominalGreedyPolicy().decide(view.berth)
    assert a1n.vessel_id == "V001"                                    # equal nominal service: FCFS tie -> V001
    same = build_coordination_view(_first_berth_kernel(b1_choice_doc(None)), include_projection=False)
    assert B1IntegratedGreedyPolicy().decide(same).vessel_id == A1nNominalGreedyPolicy().decide(same.berth).vessel_id


def test_g6_06_b1_and_a1n_never_wait():
    kernel = _first_berth_kernel(leakage_doc())
    assert kernel.berth_wait_legal()
    view = build_coordination_view(kernel, include_projection=False)
    assert B1IntegratedGreedyPolicy().decide(view).action_type == "ASSIGN"
    assert A1nNominalGreedyPolicy().decide(view.berth).action_type == "ASSIGN"


# G6-07 / G6-08 / G6-09 ---------------------------------------------------------- shared evaluator, selectors
def _leaf(action, unfulfilled, turnaround, censored=0):
    return LeafPrediction(action, f"V{action:03d}", float(action), "COMPLETED", unfulfilled, turnaround, censored,
                          1000.0, 10)


def _record(*candidates):
    return EvaluationRecord("v", "DEC-1", 0.0, "view", "proj", ("V001",), 10, tuple(candidates), "budget", "pred", {})


def _assign(action, unfulfilled, turnaround):
    return CandidatePrediction(action, "ASSIGN", f"V{action:03d}", float(action), _leaf(action, unfulfilled, turnaround),
                               (), None)


def test_g6_08_b2_is_strictly_lexicographic_with_no_tolerance():
    record = _record(_assign(1, 3, 1000.0), _assign(2, 2, 9000.0), _assign(3, 2, 9000.0))
    assert select(record, "B2").action == 2                           # one container beats 8000 min; tie -> index
    assert select(record, "B2-T").action == 1
    diagnostic = pivotal_diagnostic(record)
    assert diagnostic["choices_differ"] and diagnostic["one_container_pivotal"]
    assert diagnostic["predicted_cargo_advantage"] == 1
    assert diagnostic["predicted_turnaround_sacrifice_min"] == 8000.0


def test_g6_09_b2t_ignores_cargo_and_wait_uses_each_selectors_own_key():
    wait = CandidatePrediction(0, "WAIT", None, None, None, (_leaf(7, 0, 5000.0), _leaf(9, 4, 100.0)), None)
    record = _record(wait, _assign(1, 1, 200.0))
    assert effective_leaf(wait, "B2").action == 7 and effective_leaf(wait, "B2-T").action == 9
    assert select(record, "B2").action == 0                           # WAIT via its cargo-best branch (0 < 1)
    assert select(record, "B2-T").action == 0                         # WAIT via its fastest branch (100 < 200)
    flipped = _record(_assign(1, 9, 50.0), _assign(2, 0, 60.0))
    assert select(flipped, "B2-T").action == 1 and select(flipped, "B2").action == 2


def test_g6_07_b2_and_b2t_share_byte_identical_predictions_and_budget():
    kernel = _first_berth_kernel(leakage_doc())
    view = build_coordination_view(kernel, include_projection=True)
    b2, b2t = IntegratedRolloutPolicy("B2", YARD), IntegratedRolloutPolicy("B2-T", YARD)
    b2.decide(view)
    b2t.decide(view)
    e2, et = b2.records[0]["evaluation"], b2t.records[0]["evaluation"]
    assert e2["candidates"] == et["candidates"] and e2["prediction_digest"] == et["prediction_digest"]
    assert e2["budget_fingerprint"] == et["budget_fingerprint"] == b2.evaluator.fingerprint
    assert b2.describe()["policy_id"] != b2t.describe()["policy_id"]
    reverse = b2.evaluator.evaluate(view, reverse_order=True)
    assert reverse.prediction_digest == e2["prediction_digest"]       # candidate-order invariance
    assert e2["candidates"][0]["kind"] == "WAIT"                       # WAIT legal -> evaluated as a candidate
    assert pickle.loads(view.projection.state_bytes).pending.decision_id == view.decision_id


# G6-11 ----------------------------------------------------------------------- censoring honesty
def test_g6_11_inner_truncation_is_charged_not_rewarded():
    from integrated_terminal_pilot.scenarios.fingerprints import with_fingerprints

    doc = leakage_doc()
    doc["physics"]["episode"]["max_drain_extension_min"] = 20.0   # inner T_end = 120 + 20 = 140
    doc = with_fingerprints(doc, generator_config_fingerprint=None)
    view = build_coordination_view(_first_berth_kernel(doc), include_projection=True)
    record = SharedRolloutEvaluator(YARD).evaluate(view)
    leaves = [c.leaf for c in record.candidates if c.leaf] + [b for c in record.candidates for b in c.wait_branches]
    assert leaves and all(leaf.status == "TRUNCATED_DRAIN_LIMIT" and leaf.censored_vessels > 0 for leaf in leaves)
    t_end = view.projection.catalog.drain_limit_min
    for leaf in leaves:
        assert leaf.inner_end_min == t_end
        assert leaf.predicted_turnaround_min >= leaf.censored_vessels * (t_end - 120.0)   # censored at T_end
        assert leaf.predicted_unfulfilled_outbound > 0                                    # unloaded cargo counted


# G6-12 / G6-15 ----------------------------------------------------------------- compute guard, failures
def test_g6_12_engineering_guard_fails_closed_instead_of_truncating():
    view = build_coordination_view(_first_berth_kernel(leakage_doc()), include_projection=True)
    with pytest.raises(cp.B2EvaluationError) as error:
        SharedRolloutEvaluator(YARD, cycle_guard=2).evaluate(view)
    assert error.value.gate == "G6-12"
    assert SharedRolloutEvaluator(YARD, cycle_guard=2).fingerprint != SharedRolloutEvaluator(YARD).fingerprint


def test_g6_15_step6_arms_refuse_non_primary_profiles():
    from integrated_terminal_pilot.benchmark.runner import run_arm

    for profile in (None, "itp_sensitivity_balanced_qc4_v1", "itp_v1_reference_qc4_first_fit"):
        with pytest.raises(ValueError, match="primary research profile"):
            run_arm(leakage_doc(), arm_id="B1", research_profile=profile)
    with pytest.raises(KeyError):
        create_berth_policy("B2")                                     # not in the Step 5 A-arm registry


# end-to-end on the shared kernel ---------------------------------------------------------------------
@pytest.mark.parametrize("arm", ["B1", "B2", "B2-T"])
def test_b_arms_drive_the_shared_kernel_end_to_end(arm):
    kernel = kernel_for(leakage_doc(), invariant_mode="full")
    policy = (B1IntegratedGreedyPolicy() if arm == "B1" else IntegratedRolloutPolicy(arm, YARD))
    run = run_episode(kernel, berth_policy=policy, crane_policy=GreedyBerthOrderCranePolicy(),
                      yard_policy=create_policy(YARD),
                      berth_observer=coordination_observer(include_projection=arm != "B1"))
    assert run.status == "COMPLETED" and not run.rejections and kernel.result()["audits"]["ok"]
    assert len(policy.records) == run.decisions["BERTH"]


# G6-13 ----------------------------------------------------------------------- cargo reporting clarification
def test_g6_13_noninferiority_reporting_labels_are_additive_and_honest():
    from integrated_terminal_pilot.benchmark import cargo_ni

    clear = cargo_ni.noninferiority([0.0] * 12)
    assert clear["verdict"] == "NON_INFERIOR" and clear["reporting_label"]["label"] == "NON_INFERIOR"
    noisy = cargo_ni.noninferiority([0.0, 0.08, -0.05, 0.06, -0.04, 0.05, 0.0, 0.0])
    assert noisy["verdict"] == "INFERIOR"                                  # historical field unchanged
    assert noisy["reporting_label"] == {"label": "NON_INFERIORITY_NOT_ESTABLISHED",
                                        "diagnostic": "POINT_ESTIMATE_ABOVE_MARGIN"}
    worse = cargo_ni.noninferiority([0.05, 0.06, 0.04, 0.05, 0.07, 0.05, 0.06, 0.05, 0.04, 0.06])
    assert worse["reporting_label"]["label"] == "STATISTICALLY_INFERIOR" and worse["lower_bound"] > 0.01
    assert cargo_ni.comparison("B2", "B2-T")["kind"] == "objective_ablation_within_coordinated"
    assert cargo_ni.comparison("B1", "A1") and cargo_ni.comparison("B2-T", "A2")
