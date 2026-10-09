"""Immutable generation runs: plan, generate, validate and audit.

A run directory ``experiments/scenarios/{split}/{run_id}/`` is built in a
``{run_id}.partial`` staging directory and renamed only when complete. An
existing run (or a stale partial) is never overwritten. Every file except
``manifest.json`` is listed with its SHA-256 in the manifest, and the manifest
itself has a ``manifest.json.sha256`` sidecar.
"""

from __future__ import annotations

import csv
import io
import json
import os
import platform
import subprocess
import time
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any

from integrated_terminal_pilot.scenarios.audit import (
    SYNTHETIC_LABEL, collision_audit, quality_markdown, quality_summary,
)
from integrated_terminal_pilot.scenarios.berth_projection import (
    PPO_SUPPORT, assess_ppo_support, build_berth_projection, verify_dynamic_env_reset,
)
from integrated_terminal_pilot.scenarios.config import PROJECT_ROOT, GeneratorConfig
from integrated_terminal_pilot.scenarios.fingerprints import sha256_of
from integrated_terminal_pilot.scenarios.generator import (
    ScenarioGenerationError, generate_scenario_with_diagnostics,
)
from integrated_terminal_pilot.scenarios.models import PHYSICS_PROFILE_STANDARD, scenario_id_for
from integrated_terminal_pilot.scenarios.serialization import (
    SCENARIO_SUFFIX, file_sha256, load_scenario, scenario_filename, write_scenario,
)
from integrated_terminal_pilot.scenarios.validation import validate_scenario

DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "experiments" / "scenarios"
INDEX_COLUMNS = (
    "scenario_id", "family", "split", "scenario_seed", "physics_profile", "status",
    "rejection_code", "rejection_message", "vessel_count", "container_count", "teu_total",
    "crane_moves_total", "mandatory_initial_teu", "optional_initial_teu",
    "initial_occupancy_fraction", "initial_target_status", "physical_fingerprint", "container_manifest_fingerprint",
    "exogenous_schedule_fingerprint", "berth_projection_fingerprint",
    "berth_projection_physical_fingerprint", "ppo_medium_heavy_support", "ppo_tiny_support",
    "dynamic_env_reset", "file_sha256", "file_bytes",
)
# Wall-clock stage timings are kept out of the deterministic index and quality report;
# they are summarized in the manifest only (which already carries a timestamp).
TIMING_KEYS = ("generation_s", "validation_s", "projection_reset_s", "serialization_s")
DEPENDENCIES = ("integrated-terminal-pilot", "terminal-core", "mini-port-sim",
                "berth-allocation-lab", "gymnasium", "numpy", "PyYAML")


class RunExistsError(FileExistsError):
    """A completed or partial run directory already exists."""


def plan_run(config: GeneratorConfig, counts: dict[str, int] | None = None, *,
             split: str = "development", first_seed_offset: int = 0,
             physics_profile: str = PHYSICS_PROFILE_STANDARD, run_id: str | None = None,
             output_root: str | Path = DEFAULT_OUTPUT_ROOT) -> dict[str, Any]:
    if split not in config.parameters["generation_policy"]["allowed_splits"]:
        raise ScenarioGenerationError("SEED_NAMESPACE_VIOLATION",
                                      f"Split {split!r} may not be generated in Step 2.")
    counts = dict(config.parameters["development_batch"] if counts is None else counts)
    first, last = config.seed_band(split)
    families = []
    for family in sorted(counts):
        config.family(family)
        count = int(counts[family])
        seeds = [first + first_seed_offset + k for k in range(count)]
        if seeds and (seeds[0] < first or seeds[-1] > last):
            raise ScenarioGenerationError("SEED_NAMESPACE_VIOLATION",
                                          f"Planned seeds leave the {split} band.")
        blocked = [d["decision_id"] for d in config.blocked_decisions_for_family(family)]
        families.append({"family": family, "count": count, "seeds": seeds,
                         "blocked_by": blocked,
                         "role": config.family(family)["role"],
                         "intended_bottleneck": config.family(family)["intended_bottleneck"],
                         "ppo_regime": config.family(family)["ppo_regime"]})
    plan_key = {"counts": counts, "split": split, "first_seed_offset": first_seed_offset,
                "physics_profile": physics_profile}
    if run_id is None:
        run_id = f"{split[:3]}_{config.parameters_fingerprint[:10]}_{sha256_of(plan_key)[:8]}"
    if not run_id.replace("_", "").replace("-", "").isalnum():
        raise ValueError("run_id may contain only letters, digits, '-' and '_'.")
    output_dir = Path(output_root) / split / run_id
    return {"run_id": run_id, "split": split, "physics_profile": physics_profile,
            "first_seed_offset": first_seed_offset, "families": families,
            "output_dir": str(output_dir), "output_exists": output_dir.exists(),
            "seed_band": [first, last],
            "parameter_decision_status": config.decision_status_counts(),
            "compatibility_expectations": {
                regime: {"max_vessels": env["max_vessels"], "berth_length_m": env["berth_length_m"]}
                for regime, env in PPO_SUPPORT.items()}}


def _git_state() -> tuple[str | None, bool | None]:
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, capture_output=True,
                                text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=PROJECT_ROOT,
                                    capture_output=True, text=True, check=True).stdout.strip())
        return commit, dirty
    except (OSError, subprocess.CalledProcessError):
        return None, None


def _versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {"python": platform.python_version()}
    for name in DEPENDENCIES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def _timing_stats(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    return {"count": len(values), "min": min(values), "max": max(values),
            "mean": sum(values) / len(values), "total": sum(values)}


def _write_json(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def _index_csv(rows: list[dict[str, Any]]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=INDEX_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key, "") for key in INDEX_COLUMNS})
    return buffer.getvalue()


def generate_run(config: GeneratorConfig, plan: dict[str, Any],
                 *, run_collision_audit: bool = True) -> dict[str, Any]:
    output_dir = Path(plan["output_dir"])
    staging = output_dir.with_name(output_dir.name + ".partial")
    if output_dir.exists() or staging.exists():
        raise RunExistsError(f"Refusing to overwrite existing run directory {output_dir} "
                             f"(or stale {staging.name}).")
    staging.mkdir(parents=True)
    scenario_dir = staging / "scenarios"
    scenario_dir.mkdir()
    rows: list[dict[str, Any]] = []
    accepted_docs: list[dict[str, Any]] = []
    diagnostics: dict[str, dict[str, Any]] = {}
    validation_reports: list[dict[str, Any]] = []
    timings: list[float] = []
    for family_plan in plan["families"]:
        family = family_plan["family"]
        for seed in family_plan["seeds"]:
            sid = scenario_id_for(family, plan["split"], seed, plan["physics_profile"])
            row = {"scenario_id": sid, "family": family, "split": plan["split"],
                   "scenario_seed": seed, "physics_profile": plan["physics_profile"]}
            started = time.perf_counter()
            try:
                result = generate_scenario_with_diagnostics(config, family, plan["split"], seed,
                                                            plan["physics_profile"])
            except ScenarioGenerationError as error:
                row.update(status="blocked" if family_plan["blocked_by"] else "rejected",
                           rejection_code=error.code, rejection_message=error.message)
                rows.append(row)
                continue
            generated = time.perf_counter()
            doc = result.scenario
            report = validate_scenario(doc, generator_config=config)
            validated = time.perf_counter()
            validation_reports.append(report.to_dict())
            if not report.ok:
                row.update(status="rejected", rejection_code=sorted(report.codes)[0],
                           rejection_message="failed scenario-stage validation")
                rows.append(row)
                continue
            projection = build_berth_projection(doc)
            support = assess_ppo_support(doc)
            regime = family_plan["ppo_regime"]
            if (doc["terminal"]["quay"]["berth_length_m"] == PPO_SUPPORT[regime]["berth_length_m"]
                    and len(doc["vessels"]) <= PPO_SUPPORT[regime]["max_vessels"]):
                reset = verify_dynamic_env_reset(projection, PPO_SUPPORT[regime]["max_vessels"])
                reset_status = "ok" if reset["reset_ok"] and reset["observation_in_space"] and \
                    reset["projection_fingerprint_matches"] else "failed"
            else:
                reset_status = "not_supported"
            projected = time.perf_counter()
            path = write_scenario(doc, scenario_dir)
            written = time.perf_counter()
            timings.append(written - started)
            fps = doc["fingerprints"]
            inventory = result.diagnostics["initial_inventory"]
            row.update(
                mandatory_initial_teu=inventory["mandatory_initial_teu"],
                optional_initial_teu=inventory["optional_initial_teu"],
                initial_occupancy_fraction=inventory["realized_initial_occupancy_fraction"],
                initial_target_status=inventory["target_status"],
                generation_s=round(generated - started, 3), validation_s=round(validated - generated, 3),
                projection_reset_s=round(projected - validated, 3),
                serialization_s=round(written - projected, 3))
            row.update(
                status="accepted", rejection_code="", rejection_message="",
                vessel_count=len(doc["vessels"]), container_count=len(doc["containers"]),
                teu_total=sum(c["size_teu"] for c in doc["containers"]),
                crane_moves_total=sum(v["workload_moves"] for v in doc["vessels"]),
                physical_fingerprint=fps["physical_fingerprint"],
                container_manifest_fingerprint=fps["container_manifest_fingerprint"],
                exogenous_schedule_fingerprint=fps["exogenous_schedule_fingerprint"],
                berth_projection_fingerprint=fps["berth_projection_fingerprint"],
                berth_projection_physical_fingerprint=fps["berth_projection_physical_fingerprint"],
                ppo_medium_heavy_support=support["medium_heavy"]["status"],
                ppo_tiny_support=support["tiny"]["status"], dynamic_env_reset=reset_status,
                file_sha256=file_sha256(path), file_bytes=path.stat().st_size)
            rows.append(row)
            accepted_docs.append(doc)
            diagnostics[sid] = result.diagnostics
    accepted = [r for r in rows if r["status"] == "accepted"]
    fingerprint_audit = {
        "physical_fingerprints": {r["scenario_id"]: r["physical_fingerprint"] for r in accepted},
        "container_manifest_fingerprints": {r["scenario_id"]: r["container_manifest_fingerprint"] for r in accepted},
        "berth_projection_fingerprints": {r["scenario_id"]: r["berth_projection_fingerprint"] for r in accepted},
    }
    if run_collision_audit:
        fingerprint_audit["collision_audit"] = collision_audit(
            {r["scenario_id"]: r["berth_projection_physical_fingerprint"] for r in accepted},
            {r["scenario_id"]: r["physical_fingerprint"] for r in accepted})
    else:
        fingerprint_audit["collision_audit"] = {"passed": None, "skipped": True}
    summary = quality_summary(
        accepted_docs, diagnostics, rows,
        config_info={"generator_version": config.parameters["generator_version"],
                     "config_schema_version": config.parameters["config_schema_version"],
                     "config_file_sha256": config.config_file_sha256,
                     "decisions_file_sha256": config.decisions_file_sha256,
                     "generator_config_fingerprint": config.parameters_fingerprint})

    _write_json(staging / "generation_config.json", {
        "config_path": Path(config.config_path).name, "decisions_path": Path(config.decisions_path).name,
        "config_file_sha256": config.config_file_sha256,
        "decisions_file_sha256": config.decisions_file_sha256,
        "generator_config_fingerprint": config.parameters_fingerprint,
        "parameters": config.parameters, "plan": {k: v for k, v in plan.items()
                                                  if k not in ("output_dir", "output_exists")}})
    _write_json(staging / "decisions.json", {"records": list(config.decisions),
                                             "status_counts": config.decision_status_counts()})
    _write_json(staging / "validation_report.json", {
        "stage": "scenario (generator-time); runtime invariants are Step 4",
        "scenario_reports": validation_reports,
        "rows": [{k: r.get(k, "") for k in ("scenario_id", "status", "rejection_code", "rejection_message")}
                 for r in rows]})
    _write_json(staging / "fingerprint_audit.json", fingerprint_audit)
    _write_json(staging / "generation_diagnostics.json", diagnostics)
    _write_json(staging / "quality_report.json", summary)
    with (staging / "quality_report.md").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(quality_markdown(summary))
    with (staging / "scenario_index.csv").open("x", encoding="utf-8", newline="") as stream:
        stream.write(_index_csv(rows))

    commit, dirty = _git_state()
    file_hashes = {
        path.relative_to(staging).as_posix(): file_sha256(path)
        for path in sorted(staging.rglob("*")) if path.is_file()}
    status_counts = summary["row_status_counts"]
    manifest = {
        "label": SYNTHETIC_LABEL,
        "run_id": plan["run_id"],
        "generator_version": config.parameters["generator_version"],
        "scenario_schema_version": config.parameters["scenario_schema_version"],
        "configuration_hash": config.config_file_sha256,
        "decisions_hash": config.decisions_file_sha256,
        "generator_config_fingerprint": config.parameters_fingerprint,
        "source_git_commit": commit,
        "source_git_dirty": dirty,
        "source_dependency_versions": _versions(),
        "seed_namespace": {"stream_namespace": config.parameters["stream_namespace"],
                           "split": plan["split"], "band": plan["seed_band"]},
        "split": plan["split"],
        "physics_profile": plan["physics_profile"],
        "scenario_family_counts": {f["family"]: {"planned": f["count"],
                                                 "accepted": sum(1 for r in accepted if r["family"] == f["family"]),
                                                 "not_accepted": sum(1 for r in rows if r["family"] == f["family"]
                                                                     and r["status"] != "accepted"),
                                                 "blocked_by": f["blocked_by"],
                                                 "intended_bottleneck": f.get("intended_bottleneck")}
                                   for f in plan["families"]},
        "row_status_counts": status_counts,
        "initial_occupancy_target_infeasible": sorted(
            r["scenario_id"] for r in accepted if r["initial_target_status"] != "MET"),
        "physical_fingerprint_digest": sha256_of(sorted(r["physical_fingerprint"] for r in accepted)),
        "container_manifest_fingerprint_digest": sha256_of(sorted(r["container_manifest_fingerprint"] for r in accepted)),
        "projection_fingerprint_digest": sha256_of(sorted(r["berth_projection_fingerprint"] for r in accepted)),
        "file_hashes": file_hashes,
        "validation_status": "all_accepted_valid" if all(rep["valid"] for rep in validation_reports) else "invalid_present",
        "collision_audit_passed": fingerprint_audit["collision_audit"]["passed"],
        "parameter_decision_status": {**config.decision_status_counts(),
                                      "final_experiments_authorized": False},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "performance": {"seconds_per_accepted_scenario_mean": (sum(timings) / len(timings)) if timings else None,
                        "stage_seconds": {key: _timing_stats([r[key] for r in accepted]) for key in TIMING_KEYS},
                        "max_scenario_file_bytes": max((r["file_bytes"] for r in accepted), default=None),
                        "total_scenario_bytes": sum(r["file_bytes"] for r in accepted)},
        "generation_performed": True,
        "policy_executed": False,
        "rl_training_performed": False,
        "ppo_checkpoint_loaded": False,
        "test_evaluation_performed": False,
        "held_out_test_generated": False,
    }
    _write_json(staging / "manifest.json", manifest)
    manifest_hash = file_sha256(staging / "manifest.json")
    with (staging / "manifest.json.sha256").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(f"{manifest_hash}  manifest.json\n")
    if output_dir.exists():
        raise RunExistsError(f"{output_dir} appeared during generation; staging kept at {staging}.")
    os.replace(staging, output_dir)
    return manifest


def verify_manifest(run_dir: str | Path) -> dict[str, Any]:
    run_dir = Path(run_dir)
    problems = []
    manifest_path = run_dir / "manifest.json"
    sidecar = run_dir / "manifest.json.sha256"
    if not manifest_path.is_file() or not sidecar.is_file():
        return {"passed": False, "problems": ["manifest.json or its .sha256 sidecar is missing"]}
    if sidecar.read_text(encoding="utf-8").split()[0] != file_sha256(manifest_path):
        problems.append("manifest.json does not match its SHA-256 sidecar")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    listed = manifest["file_hashes"]
    actual = {p.relative_to(run_dir).as_posix() for p in run_dir.rglob("*") if p.is_file()}
    expected = set(listed) | {"manifest.json", "manifest.json.sha256"}
    for extra in sorted(actual - expected):
        problems.append(f"unlisted file {extra}")
    for missing in sorted(expected - actual):
        problems.append(f"missing file {missing}")
    for relative, digest in sorted(listed.items()):
        path = run_dir / relative
        if path.is_file() and file_sha256(path) != digest:
            problems.append(f"hash mismatch {relative}")
    return {"passed": not problems, "problems": problems, "manifest": manifest}


def _read_index(run_dir: Path) -> list[dict[str, str]]:
    with (run_dir / "scenario_index.csv").open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def validate_run(run_dir: str | Path, config: GeneratorConfig | None = None) -> dict[str, Any]:
    """Re-validate every stored scenario: schema, DQ rules, fingerprints and index reconciliation."""
    run_dir = Path(run_dir)
    rows = {row["scenario_id"]: row for row in _read_index(run_dir)}
    results = []
    for path in sorted((run_dir / "scenarios").glob(f"*{SCENARIO_SUFFIX}")):
        doc = load_scenario(path)
        use_config = config if (config is not None and doc.get("fingerprints", {}).get(
            "generator_config_fingerprint") == config.parameters_fingerprint) else None
        report = validate_scenario(doc, generator_config=use_config)
        sid = doc.get("identity", {}).get("scenario_id")
        row = rows.get(sid)
        problems = []
        if row is None:
            problems.append("scenario missing from index")
        else:
            if path.name != scenario_filename(doc):
                problems.append("file name does not match scenario_id")
            if row["file_sha256"] != file_sha256(path):
                problems.append("file hash differs from index")
            if row["physical_fingerprint"] != doc["fingerprints"]["physical_fingerprint"]:
                problems.append("physical fingerprint differs from index")
            if int(row["container_count"]) != len(doc["containers"]):
                problems.append("container count differs from index")
        results.append({"scenario_id": sid, "valid": report.ok and not problems,
                        "issue_counts": report.to_dict()["issue_counts"], "index_problems": problems,
                        "generator_bounds_checked": use_config is not None})
    accepted = [sid for sid, row in rows.items() if row["status"] == "accepted"]
    missing = sorted(set(accepted) - {r["scenario_id"] for r in results})
    return {"run_dir": str(run_dir), "scenarios_checked": len(results),
            "valid": sum(r["valid"] for r in results), "invalid": [r for r in results if not r["valid"]],
            "accepted_in_index_but_missing": missing,
            "passed": all(r["valid"] for r in results) and not missing}


def audit_run(run_dir: str | Path, *, output_root: str | Path = DEFAULT_OUTPUT_ROOT,
              run_collision_audit: bool = True) -> dict[str, Any]:
    run_dir = Path(run_dir)
    manifest_check = verify_manifest(run_dir)
    rows = _read_index(run_dir)
    accepted = [r for r in rows if r["status"] == "accepted"]
    from integrated_terminal_pilot.scenarios.validation import SEED_BANDS

    namespace_problems = []
    for row in rows:
        first, last = SEED_BANDS.get(row["split"], (None, None))
        if row["split"] != "development":
            namespace_problems.append(f"{row['scenario_id']}: split {row['split']} not allowed in Step 2")
        if first is None or not first <= int(row["scenario_seed"]) <= last:
            namespace_problems.append(f"{row['scenario_id']}: seed outside its band")
    forbidden_dirs = [str(p) for name in ("validation", "test", "diagnostic")
                      if (p := Path(output_root) / name).exists()]
    ids = [r["scenario_id"] for r in rows]
    fps = [r["physical_fingerprint"] for r in accepted]
    collision = (collision_audit({r["scenario_id"]: r["berth_projection_physical_fingerprint"] for r in accepted},
                                 {r["scenario_id"]: r["physical_fingerprint"] for r in accepted})
                 if run_collision_audit else {"passed": None, "skipped": True})
    validation = json.loads((run_dir / "validation_report.json").read_text(encoding="utf-8"))
    issue_total = sum(sum(rep["issue_counts"].values()) for rep in validation["scenario_reports"])
    status_counts: dict[str, int] = {}
    for row in rows:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
    coverage = {
        "ppo_medium_heavy_in_support": sum(r["ppo_medium_heavy_support"] == "IN_SUPPORT" for r in accepted),
        "ppo_tiny_in_support": sum(r["ppo_tiny_support"] == "IN_SUPPORT" for r in accepted),
        "dynamic_env_reset_ok": sum(r["dynamic_env_reset"] == "ok" for r in accepted),
        "accepted": len(accepted),
    }
    passed = (manifest_check["passed"] and not namespace_problems and not forbidden_dirs
              and len(ids) == len(set(ids)) and len(fps) == len(set(fps))
              and collision.get("passed") is not False and issue_total == 0)
    return {
        "run_dir": str(run_dir), "passed": passed,
        "manifest_and_file_hashes": {"passed": manifest_check["passed"], "problems": manifest_check["problems"]},
        "row_status_counts": status_counts,
        "unique_scenario_ids": len(set(ids)) == len(ids),
        "unique_physical_fingerprints": len(set(fps)) == len(fps),
        "split_seed_problems": namespace_problems,
        "forbidden_namespace_directories": forbidden_dirs,
        "project03_collision_audit": collision,
        "data_quality_issue_total": issue_total,
        "compatibility_coverage": coverage,
        "manifest_flags": {k: manifest_check.get("manifest", {}).get(k) for k in (
            "policy_executed", "rl_training_performed", "ppo_checkpoint_loaded",
            "test_evaluation_performed", "held_out_test_generated")},
    }


def canonical_run_contents(run_dir: str | Path) -> dict[str, str]:
    """SHA-256 of every deterministic file (excludes manifest, which has timestamps)."""
    run_dir = Path(run_dir)
    return {p.relative_to(run_dir).as_posix(): file_sha256(p)
            for p in sorted(run_dir.rglob("*"))
            if p.is_file() and not p.name.startswith("manifest.json")}


__all__ = ["DEFAULT_OUTPUT_ROOT", "RunExistsError", "audit_run", "canonical_run_contents",
           "generate_run", "plan_run", "validate_run", "verify_manifest"]
