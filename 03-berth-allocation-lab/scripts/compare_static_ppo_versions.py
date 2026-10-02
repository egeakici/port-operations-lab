"""Compare v1/v2 paired evaluations on identical frozen scenarios."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


def _load(directory: Path):
    manifest = json.loads((directory / "evaluation_manifest.json").read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in (directory / "per_instance.jsonl").read_text(encoding="utf-8").splitlines()]
    return manifest, rows


def _key(row):
    return row["suite"], row["component"], row["physical_fingerprint"]


def compare(v1_dir: Path, v2_dir: Path) -> dict:
    first_manifest, first_rows = _load(v1_dir)
    second_manifest, second_rows = _load(v2_dir)
    if first_manifest["checkpoint_kind"] != "best_validation" or second_manifest["checkpoint_kind"] != "best_validation":
        raise ValueError("Both evaluations must use best-validation checkpoints.")
    first_suites = {name: [r["physical_fingerprint"] for r in suite["identities"]]
                    for name, suite in first_manifest["suites"].items()}
    second_suites = {name: [r["physical_fingerprint"] for r in suite["identities"]]
                     for name, suite in second_manifest["suites"].items()}
    if first_suites != second_suites:
        raise ValueError("Evaluation suites have non-identical physical scenario fingerprints.")
    if any(not row["is_valid"] for row in (*first_rows, *second_rows)):
        raise ValueError("Invalid schedules must be resolved before paired comparison.")

    def index(rows):
        indexed = {}
        for row in rows:
            key = (*_key(row), row["method"], row.get("training_seed") if row["method"] == "ppo" else None)
            if key in indexed:
                raise ValueError(f"Duplicate evaluation row: {key}")
            indexed[key] = row
        return indexed

    old, new = index(first_rows), index(second_rows)
    old_ppo = {key for key in old if key[3] == "ppo"}
    new_ppo = {key for key in new if key[3] == "ppo"}
    if old_ppo != new_ppo:
        raise ValueError("Evaluations have different PPO seed/scenario coverage.")
    paired = []
    for key in sorted(old_ppo):
        before, after = old[key], new[key]
        references = {}
        for method in ("fcfs", "rollout", "exact"):
            refkey = (*key[:3], method, None)
            if (refkey in old) != (refkey in new):
                raise ValueError(f"Reference coverage differs: {refkey}")
            if refkey in old:
                left, right = old[refkey], new[refkey]
                if left["total_waiting_time_min"] != right["total_waiting_time_min"] or left["exact_certified"] != right["exact_certified"]:
                    raise ValueError(f"Reference results differ: {refkey}")
                references[method] = left["total_waiting_time_min"]
        paired.append({"suite": key[0], "component": key[1], "physical_fingerprint": key[2],
                       "training_seed": key[4], "v1_waiting_min": before["total_waiting_time_min"],
                       "v2_waiting_min": after["total_waiting_time_min"],
                       "v2_minus_v1_min": after["total_waiting_time_min"] - before["total_waiting_time_min"],
                       "fcfs_waiting_min": references["fcfs"],
                       "rollout_waiting_min": references["rollout"],
                       "certified_exact_waiting_min": references.get("exact") if before["exact_certified"] else None})
    groups = []
    for suite, component in sorted({(r["suite"], r["component"]) for r in paired}):
        subset = [r for r in paired if (r["suite"], r["component"]) == (suite, component)]
        seed_means = {}
        for seed in sorted({r["training_seed"] for r in subset}):
            rows = [r for r in subset if r["training_seed"] == seed]
            seed_means[str(seed)] = {
                "v1_mean_waiting_min": statistics.fmean(r["v1_waiting_min"] for r in rows),
                "v2_mean_waiting_min": statistics.fmean(r["v2_waiting_min"] for r in rows),
                "mean_v2_minus_v1_min": statistics.fmean(r["v2_minus_v1_min"] for r in rows),
            }
        diffs = [v["mean_v2_minus_v1_min"] for v in seed_means.values()]
        old_means = [v["v1_mean_waiting_min"] for v in seed_means.values()]
        new_means = [v["v2_mean_waiting_min"] for v in seed_means.values()]
        unique = {r["physical_fingerprint"]: r for r in subset}
        exact = [r["certified_exact_waiting_min"] for r in unique.values()
                 if r["certified_exact_waiting_min"] is not None]
        groups.append({"suite": suite, "component": component, "n_scenarios": len(unique),
                       "per_seed": seed_means,
                       "v1_cross_seed_mean_waiting_min": statistics.fmean(old_means),
                       "v1_cross_seed_sample_sd_min": statistics.stdev(old_means) if len(old_means) > 1 else None,
                       "v2_cross_seed_mean_waiting_min": statistics.fmean(new_means),
                       "v2_cross_seed_sample_sd_min": statistics.stdev(new_means) if len(new_means) > 1 else None,
                       "cross_seed_mean_v2_minus_v1_min": statistics.fmean(diffs),
                       "cross_seed_sample_sd_min": statistics.stdev(diffs) if len(diffs) > 1 else None,
                       "fcfs_mean_waiting_min": statistics.fmean(r["fcfs_waiting_min"] for r in unique.values()),
                       "rollout_mean_waiting_min": statistics.fmean(r["rollout_waiting_min"] for r in unique.values()),
                       "exact_certified_count": len(exact),
                       "certified_exact_mean_waiting_min": statistics.fmean(exact) if exact else None})
    return {"v1_experiment_id": first_manifest["experiment_id"],
            "v2_experiment_id": second_manifest["experiment_id"],
            "suite_fingerprints_identical": True, "paired_rows": paired, "groups": groups}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v1-evaluation", required=True, type=Path)
    parser.add_argument("--v2-evaluation", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = compare(args.v1_evaluation, args.v2_evaluation)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as file:
            json.dump(result, file, indent=2, sort_keys=True)
    print(json.dumps({k: v for k, v in result.items() if k != "paired_rows"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
