"""Collision audit against Project 03 and the synthetic data-quality summary.

The Project 03 audit rebuilds, in memory, the physical fingerprints of every
Project 03 suite the frozen dynamic campaigns examined (validation, test,
diagnostic, prior static suites, historical fixtures and presets) using Project
03's own builders. Only fingerprints are kept; no Project 03 scenario is stored,
evaluated or used as Project I data, and no checkpoint is touched.
"""

from __future__ import annotations

import statistics
from pathlib import Path
from typing import Any

from integrated_terminal_pilot.scenarios.config import PROJECT_ROOT

P03_ROOT = PROJECT_ROOT.parent / "03-berth-allocation-lab"
P03_DYNAMIC_CONFIGS = ("configs/rl/dynamic_ppo_medium_heavy_extended_cuda.yaml",
                       "configs/rl/dynamic_ppo_tiny_extended_cuda.yaml")
SYNTHETIC_LABEL = "SYNTHETIC - NOT CALIBRATED TO A REAL TERMINAL"


def project03_examined_fingerprints(p03_root: Path = P03_ROOT) -> dict[str, Any]:
    from berth_allocation_lab.rl.dynamic_config import DynamicPPOConfig
    from berth_allocation_lab.rl.dynamic_suites import dynamic_suites, prior_exposure_fingerprints
    from berth_allocation_lab.rl.suites import physical_fingerprint

    fingerprints: set[str] = set()
    suites: dict[str, int] = {}
    for relative in P03_DYNAMIC_CONFIGS:
        config = DynamicPPOConfig.load_yaml(p03_root / relative)
        for name, suite in dynamic_suites(config).items():
            fingerprints.update(physical_fingerprint(s) for s in suite.scenarios)
            suites[f"{config.experiment_id}/{name}"] = len(suite.scenarios)
        fingerprints.update(prior_exposure_fingerprints(config))
    return {"fingerprints": fingerprints, "suite_sizes": suites,
            "source_configs": list(P03_DYNAMIC_CONFIGS)}


def collision_audit(projection_physical_fps: dict[str, str],
                    scenario_physical_fps: dict[str, str]) -> dict[str, Any]:
    examined = project03_examined_fingerprints()
    collisions = sorted(sid for sid, fp in projection_physical_fps.items()
                        if fp in examined["fingerprints"])
    seen: dict[str, str] = {}
    duplicates = []
    for sid, fp in sorted(scenario_physical_fps.items()):
        if fp in seen:
            duplicates.append([seen[fp], sid])
        seen[fp] = sid
    return {
        "project03_examined_fingerprint_count": len(examined["fingerprints"]),
        "project03_suite_sizes": examined["suite_sizes"],
        "project03_source_configs": examined["source_configs"],
        "checked_projection_count": len(projection_physical_fps),
        "project03_collisions": collisions,
        "duplicate_physical_fingerprints": duplicates,
        "passed": not collisions and not duplicates,
    }


def _stats(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    return {"count": len(values), "min": min(values), "max": max(values),
            "mean": statistics.fmean(values)}


def quality_summary(scenarios: list[dict[str, Any]], diagnostics: dict[str, dict[str, Any]],
                    rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Descriptive statistics of accepted scenarios, per family (no performance metrics)."""
    families: dict[str, list[dict[str, Any]]] = {}
    for doc in scenarios:
        families.setdefault(doc["identity"]["scenario_family"], []).append(doc)
    per_family = {}
    for family, docs in sorted(families.items()):
        vessels = [v for d in docs for v in d["vessels"]]
        containers = [c for d in docs for c in d["containers"]]
        flows: dict[str, int] = {}
        sizes: dict[str, int] = {}
        for record in containers:
            flows[record["cargo_flow"]] = flows.get(record["cargo_flow"], 0) + 1
            sizes[record["container_size"]] = sizes.get(record["container_size"], 0) + 1
        initial_fraction, balance, distances = [], [], []
        for d in docs:
            capacity = sum(b["capacity_teu"] for b in d["terminal"]["yard_blocks"])
            present = sum(c["size_teu"] for c in d["containers"] if c["present_at_episode_start"])
            inbound = sum(c["size_teu"] for c in d["containers"]
                          if not c["present_at_episode_start"] and c["cargo_flow"] != "export")
            gated = sum(c["size_teu"] for c in d["containers"]
                        if c["scheduled_gate_in_time_min"] is not None)
            initial_fraction.append(present / capacity)
            balance.append((present + inbound + gated) / capacity)
            quay = d["terminal"]["quay"]["berth_length_m"]
            for block in d["terminal"]["yard_blocks"]:
                tx, ty = block["transfer_point_x_m"], block["transfer_point_y_m"]
                distances.extend((ty, max(abs(tx), abs(quay - tx)) + ty))
        per_family[family] = {
            "scenario_count": len(docs),
            "vessels_per_scenario": _stats([float(len(d["vessels"])) for d in docs]),
            "vessel_length_m": _stats([v["length_m"] for v in vessels]),
            "workload_moves": _stats([float(v["workload_moves"]) for v in vessels]),
            "nominal_service_time_min": _stats([v["nominal_service_time_min"] for v in vessels]),
            "containers_per_scenario": _stats([float(len(d["containers"])) for d in docs]),
            "teu_per_scenario": _stats([sum(c["size_teu"] for c in d["containers"]) for d in docs]),
            "crane_moves_per_scenario": _stats([float(sum(v["workload_moves"] for v in d["vessels"]))
                                                for d in docs]),
            "cargo_flow_counts": dict(sorted(flows.items())),
            "cargo_flow_shares": {k: v / len(containers) for k, v in sorted(flows.items())},
            "size_counts": dict(sorted(sizes.items())),
            "gross_weight_kg": _stats([float(c["gross_weight_kg"]) for c in containers]),
            "initial_occupancy_fraction": _stats(initial_fraction),
            "teu_pressure_ratio": _stats(balance),
            "yard_block_capacity_teu": sorted({b["capacity_teu"] for d in docs
                                               for b in d["terminal"]["yard_blocks"]}),
            "yard_blocks_per_scenario": sorted({len(d["terminal"]["yard_blocks"]) for d in docs}),
            "quay_to_block_distance_m": _stats(distances),
            "quay_cranes": sorted({(len(d["resources"]["quay_cranes"]),
                                    d["resources"]["quay_cranes"][0]["nominal_moves_per_hour"])
                                   for d in docs}),
            "transshipment_service": {
                "demand": sum(diagnostics[d["identity"]["scenario_id"]]["transshipment"]["transshipment_demand"] for d in docs),
                "served_by_scenario_vessels": sum(diagnostics[d["identity"]["scenario_id"]]["transshipment"]["served_by_scenario_vessels"] for d in docs),
                "served_by_pre_episode_inventory": sum(diagnostics[d["identity"]["scenario_id"]]["transshipment"]["served_by_pre_episode_inventory"] for d in docs),
            },
            "initial_inventory_exceeds_target": sum(
                diagnostics[d["identity"]["scenario_id"]]["initial_inventory"]["exceeds_target"] for d in docs),
        }
    status_counts: dict[str, int] = {}
    for row in rows:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
    accepted = [r for r in rows if r["status"] == "accepted"]
    return {
        "label": SYNTHETIC_LABEL,
        "teu_pressure_ratio_definition": ("(initial TEU + TEU arriving by vessel for discharge + "
                                          "TEU requesting gate-in) / total yard capacity; a static "
                                          "indicator, not a simulation result"),
        "row_status_counts": status_counts,
        "projection_success": sum(r["dynamic_env_reset"] == "ok" for r in accepted),
        "projection_attempts": len(accepted),
        "duplicate_scenario_ids": len(rows) - len({r["scenario_id"] for r in rows}),
        "unique_physical_fingerprints": len({r["physical_fingerprint"] for r in accepted}),
        "families": per_family,
    }


def quality_markdown(summary: dict[str, Any]) -> str:
    lines = [f"# Development scenario quality summary", "", f"**{summary['label']}**", "",
             f"Row status counts: {summary['row_status_counts']}",
             f"BAP projection / DynamicBAPEnv reset success: {summary['projection_success']} of "
             f"{summary['projection_attempts']}",
             f"Unique physical fingerprints: {summary['unique_physical_fingerprints']}", "",
             "| Family | Scenarios | Vessels | Containers (mean) | TEU (mean) | Moves (mean) | "
             "Import / export / transshipment share | 40 ft share | Initial occupancy (mean) | "
             "TEU pressure ratio (mean) |",
             "| --- | ---: | --- | ---: | ---: | ---: | --- | ---: | ---: | ---: |"]
    for family, f in summary["families"].items():
        shares = f["cargo_flow_shares"]
        sizes = f["size_counts"]
        forty = sizes.get("40_ft", 0) / max(1, sum(sizes.values()))
        lines.append(
            f"| {family} | {f['scenario_count']} | {f['vessels_per_scenario']['min']:.0f}-"
            f"{f['vessels_per_scenario']['max']:.0f} | {f['containers_per_scenario']['mean']:.0f} | "
            f"{f['teu_per_scenario']['mean']:.0f} | {f['crane_moves_per_scenario']['mean']:.0f} | "
            f"{shares.get('import', 0):.3f} / {shares.get('export', 0):.3f} / "
            f"{shares.get('transshipment', 0):.3f} | {forty:.3f} | "
            f"{f['initial_occupancy_fraction']['mean']:.3f} | {f['teu_pressure_ratio']['mean']:.2f} |")
    lines.append("")
    return "\n".join(lines)
