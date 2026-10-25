"""Literal protocol11 inventory. No diagnostic generation or execution side effects.

The frozen runner has no model-only coupling-switch API and restricts B2 to
the primary profile. A plan describing those gaps is not an executable campaign.
Failing this preflight is a scientific implementation blocker, not a resource cap.
"""
from statistical import FAMILIES, SEEDS


def make_plan():
    ranges = {
        "cranes": [4, 6, 8], "crane_moves_per_hour": [25, 30, 35],
        "efficiency": ["Project02 table", "ideal all 1.0"],
        "transport_units": [3, 4, 6], "transport_speed_m_per_min": [150, 250, 400],
        "yard_capacity_multiplier": [.5, 1, 2], "g_min": [1., .5, .3],
        "initial_occupancy": [.3, .5, .7], "D17_wait_min": [120, 480],
    }
    bases = dict(cranes=8, crane_moves_per_hour=30, efficiency="Project02 table",
                 transport_units=4, transport_speed_m_per_min=250,
                 yard_capacity_multiplier=1, g_min=.5, initial_occupancy=.5, D17_wait_min=240)
    conditions = [{"id": "base", "changes": {}, "source": "protocol11/AM01/02/03/05/10"}]
    for factor, levels in ranges.items():
        for level in levels:
            if level != bases[factor]:
                conditions.append(dict(id=f"{factor}={level}", changes={factor: level},
                                       source="AM03" if factor == "D17_wait_min" else "protocol11 + locked step8_ranges"))
    cells = []
    for condition in conditions:
        for family in FAMILIES:
            for seed in range(13_000_000, 13_000_020):
                for arm, training_seed in (("A1", None), ("A2", None), ("B2", None),
                                           *(("A3", k) for k in SEEDS)):
                    unsupported = family == "itp_heavy" and condition["changes"].get("initial_occupancy") == .3
                    cells.append(dict(cell_id=f"{condition['id']}__{family}__seed{seed}__{arm}" +
                                      (f"-train{training_seed}" if training_seed else ""),
                                      condition=condition["id"], family=family, role="DIAGNOSTIC_ONLY_NOT_PRIMARY_TEST",
                                      split="diagnostic", scenario_seed=seed, arm=arm, training_seed=training_seed,
                                      status="UNSUPPORTED_LOCKED_HEAVY_OCCUPANCY_0_3" if unsupported else
                                      "PRE_REGISTERED_PENDING_MANUAL_EXECUTION_IMPLEMENTATION_BLOCKED",
                                      changed_values=condition["changes"], source=condition["source"]))
    coupling = [dict(variant=name, forward_crane=crane, forward_transport=transport,
                     forward_yard=yard, execution_physics="FULL_QC8_BALANCED_UNCHANGED",
                     status="BLOCKED_MODEL_ONLY_SWITCH_API_ABSENT" if name != "both" else
                     "STEP7_FULL_MODEL_OBSERVED_FRESH_13M_CONDITION_PENDING",
                     source="protocol11; AM07 objective unchanged; AM09/closure scoped none gate")
                for name, crane, transport, yard in (("none", False, False, False),
                    ("crane-aware", True, False, False), ("yard-aware", False, True, True),
                    ("both", True, True, True))]
    return dict(schema="itp_step8_diagnostic_plan_v1", authority="Original protocol11 + locked ranges; AM03 D17",
                plan_role="PRE_EXECUTION_REQUIREMENTS_AND_CAPABILITY_AUDIT_NOT_EXECUTION_AUTHORIZATION",
                source_band=[13_000_000, 13_999_999], proposed_explicit_seed_list=list(range(13_000_000, 13_000_020)),
                seed_choice="First20 in frozen diagnostic namespace; planning only, no outcomes inspected/generated",
                independent_scenarios_per_family_condition=20, training_seeds=list(SEEDS),
                allowed_arms=["A1", "A2", "B2", "A3"], ranges=ranges, base=bases,
                conditions=conditions, sensitivity_cells=cells,
                sensitivity_planned_outer_runs_including_explicit_unsupported=len(cells),
                sensitivity_explicit_unsupported=sum(c["status"].startswith("UNSUPPORTED") for c in cells),
                coupling_variants=coupling, coupling_episode_count=160,
                coupling_count_reason="Derived requirement:4 model-coupling conditions *2 primary families *20 diagnostic scenarios (protocol6.5/11); both/base can share identical verified records only once an adapter matches",
                coupling_cells=[dict(variant=v["variant"], family=f, scenario_seed=seed,
                                     split="diagnostic", arm="B2", role="DIAGNOSTIC_ONLY",
                                     status="BLOCKED_MODEL_ONLY_ADAPTER_AND_SCOPED_GATE_MAPPING")
                                for v in coupling for f in FAMILIES for seed in range(13_000_000,13_000_020)],
                matched_objective_ablation=dict(status="EXISTING_STEP7_140_MATCHED_SCENARIOS_100_TEST_40_VALIDATION",
                                               arms=["B2", "B2-T"], replaces_coupling_sensitivity=False),
                comparison_rule="Compare A1/A2/B2/A3 on the SAME scenario and physics within each condition; different physics never pooled as primary",
                kpis=["D24", "all-vessel waiting", "N_out/U/R", "D17", "LOAD_COMPLETED vs departed", "completion/censor", "resource use", "CPU policy seconds", "outer wall seconds"],
                resource_projection=dict(method="Historical Step7 per-episode costs only; no new timing episode",
                    baseline_proxy="20 * number_of_conditions * sum per-family A1+A2+B2+3*A3 historical episode walls; analysis separately",
                    limitation="Changed congestion/fleet may exceed historical cost; no guaranteed ETA or artificial admission budget"),
                resume_contract="No campaign launched. Future executable must seal starts/results, verify source/plan/scenario/model hashes, skip only verified complete cells, preserve failed/partial cells and reject concurrent workers; no timeout/cap/substitution",
                blockers=[
                    "Frozen SharedRolloutEvaluator/runner exposes no model-only crane/transport/yard coupling switches; changing execution physics is not a valid substitute.",
                    "Frozen runner rejects B2 outside PRIMARY_RESEARCH_PROFILE; QC4/QC6 cannot be passed through that API as-is.",
                    "Nominal 0.5min/move crane-off service is not achieved merely by transport/yard-off with shared cranes; realistic transshipment availability differs from A2 nominal semantics.",
                    "Protocol11 universal none==A2 text is only supported by the approved scoped closure equivalence gate; no amended mapping to a realistic 13M coupling campaign is specified.",
                    "Heavy occupancy0.3 explicitly unsupported in locked analysis note. Retain these cells, do not regenerate cargo or silently drop them.",
                    "Coupling counts derive from protocol6.5/11 and the objective stays AM07; the operational mapping of model-only crane-off state and scoped none/A2 gate must be specified before new diagnostic results.",
                ], status="BLOCKED_SOURCE_CONTRACT_NOT_EXECUTABLE", generated_scenarios=0, executed_episodes=0)
