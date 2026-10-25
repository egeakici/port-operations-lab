"""Read-only Step8 CLI. Never launches VerifyReturn, a simulator, or training."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import platform
import sys
import time

import numpy as np
import scipy
import matplotlib

from integrated_terminal_pilot.benchmark import step7 as s
from evidence import (PROJECT, REPO, DEFAULT_BUNDLE, ContractError, intake, sha, read,
                      publish, publish_bytes, code_inventory, protected_source, review_path)
from statistical import TIME_SEED, CARGO_SEED, RESAMPLES
from diagnostic_plan import make_plan

OUTPUT_ROOT = PROJECT / "experiments/step8_analysis"


def table(path, rows):
    fields = sorted({k for r in rows for k in r})
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: json.dumps(v, sort_keys=True, allow_nan=False) if isinstance(v, (dict, list)) else v
                         for k, v in row.items()})
    publish_bytes(path, stream.getvalue().encode("utf-8"))


def closure(gate, diagnostic, tests_pass):
    verified = gate["RETURN_VERIFY"] == "VERIFIED_FULL_CANONICAL"
    failed = gate["RETURN_VERIFY"] in ("FAILED_INTEGRITY", "BLOCKED_SOURCE")
    return dict(STEP7_CAMPAIGN_EXECUTION="COMPLETED_1960_OF_1960", STEP7_TRANSFER_METADATA_AUDIT="VERIFIED",
                STEP7_OFFICIAL_RETURN_GATE="FAILED" if failed else ("VERIFIED_FULL_CANONICAL" if verified else "PENDING_MANUAL"),
                STEP8_PRIMARY_ANALYSIS="BLOCKED" if verified else "PROVISIONAL_PENDING_RETURN",
                STEP8_S1_INFERENCE="COMPLETE" if verified else "PROVISIONAL",
                STEP8_S2_INFERENCE="BLOCKED",
                STEP8_CARGO_NONINFERIORITY="COMPUTED" if verified else "PROVISIONAL",
                STEP8_DIAGNOSTIC_ABLATIONS="COMPLETE" if diagnostic["status"] == "COMPLETE" else "BLOCKED",
                diagnostic_capability_status=diagnostic["status"],
                primary_inference_blocker="HOLM_CI_CONSTRUCTION_UNSPECIFIED_IN_FROZEN_SOURCE",
                STEP8_ANALYSIS_TESTS="PASS" if tests_pass else "PENDING_SOURCE_MATCHING_FOCUSED_TESTS",
                STEP8_FINAL_REPORT="PROVISIONAL", PROJECT_I_FINAL_CLOSED="NO",
                reasons=[*([] if verified else ["Official full canonical VerifyReturn pending owner execution"]),
                         "Frozen primary Holm CI construction unspecified; raw95% intervals cannot replace adjusted primary gate",
                         *diagnostic["blockers"],
                         *([] if tests_pass else ["Current Step8 code has no matching focused-test PASS receipt"])],
                STEP7_OUTER_RERUNS=0, PPO_RETRAINING="NONE", CHECKPOINTS_AND_PHYSICS="UNCHANGED",
                new_diagnostic_episodes=0)


def matching_tests(code_hash):
    for path in sorted((OUTPUT_ROOT / "testing").glob("*.json")):
        receipt = read(path)
        if receipt.get("code_sha256") == code_hash and receipt.get("exit_code") == 0:
            if sha(path.with_suffix(".log")) != receipt["log_sha256"]:
                raise ContractError("Test stdout evidence corrupted")
            return dict(path=path.relative_to(REPO).as_posix(), sha256=sha(path), receipt=receipt)
    return None


def cached_panel(ctx, inventory):
    from evidence import load_panel
    inputs = dict(manifest=s.digest(ctx["manifest"]), inputs=ctx["inputs"],
                  reader={k: v for k, v in inventory.items() if k.endswith(("evidence.py", "statistical.py"))})
    key = s.digest(inputs)
    target = OUTPUT_ROOT / "cache" / key / "scenario_panel.json"
    if target.exists():
        stamp = read(target.with_suffix(".sha256.json"))
        if stamp["sha256"] != sha(target) or stamp["inputs"] != inputs:
            raise ContractError("Derived scenario cache integrity mismatch")
        panel = read(target)
        # Reuse avoids parsing envelopes again, never ignores original byte drift.
        from evidence import manifest_file
        from tqdm import tqdm
        for row in tqdm(panel["rows"], desc="Step8 cached source bytes", unit="row", ascii=True):
            item = next(x for x in ctx["plan"]["rows"] if x["row_id"] == row["row_id"])
            digest = manifest_file(ctx["bundle"], ctx["manifest"], s.run_path(ctx["directory"], item))
            if digest != row["source_file_sha256"]:
                raise ContractError("Cached raw source changed")
        return panel, dict(path=target.relative_to(REPO).as_posix(), sha256=sha(target), cache_key=key)
    panel = load_panel(ctx)
    publish(target, panel)
    publish(target.with_suffix(".sha256.json"), dict(inputs=inputs, sha256=sha(target)))
    return panel, dict(path=target.relative_to(REPO).as_posix(), sha256=sha(target), cache_key=key)


def cached_diagnostics(ctx):
    from analysis import diagnostic_summary
    key = s.digest(dict(source=s.digest(ctx["manifest"]), reader=sha(Path(__file__).with_name("analysis.py"))))
    target = OUTPUT_ROOT / "cache" / key / "diagnostics.json"
    if target.exists():
        digest = read(target.with_suffix(".sha256.json"))["sha256"]
        if sha(target) != digest:
            raise ContractError("Diagnostic cache changed")
        data = read(target)
        from evidence import manifest_file, safe_path
        for name, expected in data["input_hashes"].items():
            if manifest_file(ctx["bundle"], ctx["manifest"], safe_path(ctx["bundle"], name)) != expected:
                raise ContractError("Archived diagnostic source changed")
        return data
    data = diagnostic_summary(ctx)
    publish(target, data)
    publish(target.with_suffix(".sha256.json"), dict(sha256=sha(target)))
    return data


def execute(args):
    start, cpu = time.perf_counter(), time.process_time()
    ctx = intake(args.bundle)
    diagnostic = make_plan()
    frozen_ranges = ctx["lock"]["analysis"]["step8_ranges_only_not_executed"]
    if any(frozen_ranges[k] != v for k, v in diagnostic["ranges"].items()):
        raise ContractError("Diagnostic plan differs from locked ranges")
    inventory = code_inventory()
    code_hash = s.digest(inventory)
    test = matching_tests(code_hash)
    plan = dict(schema="itp_step8_analysis_v1", manifest_sha256=s.digest(ctx["manifest"]),
                lock_file_sha256=ctx["manifest"]["lock_sha256"], plan_sha256=ctx["manifest"]["plan_sha256"],
                scientific_source_revision=ctx["lock"]["source_revision"],
                inherited_scoped_equivalence=ctx["inherited_gate"],
                analysis_contract=ctx["lock"]["analysis"], code_inventory=inventory, code_sha256=code_hash,
                input_files=ctx["inputs"], return_gate=ctx["gate"],
                historical_review_inputs={name:sha(review_path(name)) for name in
                                          ("review_manifest.json", "descriptive_review.json", "bytes_metadata_audit.json", "reference_restoration.json")},
                analysis_git_head=ctx["git_head"], figures_requested=bool(args.render),
                method=dict(time_seed=TIME_SEED, cargo_seed=CARGO_SEED, resamples=RESAMPLES,
                            rng="numpy.default_rng / PCG64", quantile="numpy linear",
                            resampling="reset RNG per estimand; sorted families then sorted scenario IDs; equal family weights",
                            A3="all11/23/37 within scenario first; conditional on frozen models",
                            primary_Holm="UNSPECIFIED_CONSTRUCTION_IN_FROZEN_SOURCE; no confirmatory claim from raw95%CI",
                            wilcoxon="supplementary robustness; Pratt zero handling; two-sided normal approximation; not a decision rule"),
                runtime=dict(python=platform.python_version(), numpy=np.__version__, scipy=scipy.__version__,
                             matplotlib=matplotlib.__version__, model_device="NONE", analysis_device="CPU"),
                diagnostic_plan_sha256=s.digest(diagnostic))
    digest = s.digest(plan)
    output = OUTPUT_ROOT / digest[:16]
    if args.verify and not (args.analyze or args.render or args.diagnostic_preflight):
        print(json.dumps(dict(status="READ_ONLY_INTAKE_VERIFIED", gate=ctx["gate"],
                              protected_files=ctx["source"]["count"], scientific_source="UNCHANGED"), indent=2))
        return 0
    if args.diagnostic_preflight and not (args.analyze or args.render):
        target = OUTPUT_ROOT / "diagnostic_plans" / s.digest(diagnostic)[:16] / "plan.json"
        publish(target, diagnostic)
        print(json.dumps(dict(status=diagnostic["status"], plan=str(target), blockers=diagnostic["blockers"]), indent=2))
        return 2
    if not (args.analyze or args.render):
        releases = sorted(OUTPUT_ROOT.glob("*/step8_release_manifest.json"), key=lambda p: p.stat().st_mtime)
        latest = read(releases[-1]) if releases else None
        print(json.dumps(dict(current_gate=ctx["gate"], diagnostic_status=diagnostic["status"],
                              latest_release=str(releases[-1]) if releases else None,
                              latest_release_matches_current_code=(latest is not None and latest["provenance"]["code_sha256"] == code_hash),
                              closure_status=closure(ctx["gate"], diagnostic, test is not None),
                              current_code_test_receipt=None if test is None else
                              {k: test[k] for k in ("path", "sha256")}), indent=2))
        return 0
    panel, cache = cached_panel(ctx, inventory)
    from analysis import analyze, ppo_support, diagnostic_cost_proxy
    data = analyze(panel)
    diagnostics = cached_diagnostics(ctx)
    state = closure(ctx["gate"], diagnostic, test is not None)
    provenance = dict(manifest_sha256=s.digest(ctx["manifest"]), lock_file_sha256=ctx["manifest"]["lock_sha256"],
                      source_revision=ctx["lock"]["source_revision"], analysis_sha256=digest,
                      code_sha256=code_hash, return_gate=ctx["gate"], test_receipt=test,
                      scope="SYNTHETIC_UNCALIBRATED; provisional until all scientific gates pass")
    publish(output / "analysis_plan.json", plan)
    for rel, expected_hash in inventory.items():
        original=REPO / rel
        if sha(original)!=expected_hash:
            raise ContractError("Step8 source changed during analysis; refuse release")
        publish_bytes(output / "source_snapshot" / rel, original.read_bytes())
    publish_bytes(output / "analysis_plan.json.sha256", (sha(output / "analysis_plan.json") + "\n").encode())
    publish(output / "step7_return_verification_status.json", ctx["gate"])
    publish(output / "scenario_pair_index.json", panel["pairing_index"])
    table(output / "scenario_pair_index.csv", [dict(scenario_id=k, **v) for k, v in panel["pairing_index"].items()])
    publish(output / "integrity/exception_registry.json", panel["exceptions"])
    publish(output / "integrity/source_audit.json", ctx["source"])
    publish(output / "integrity/scenario_cache.json", cache)
    publish(output / "integrity/reconciliation.json", data["reconciliation"])
    publish(output / "primary_s1_s2_results.json", dict(provenance=provenance, results=data["results"],
                                                     S1=data["S1_difference_in_differences"],
                                                     S1_signs=data["S1_sign_agreement"], S1_rankings=data["S1_rankings"]))
    table(output / "primary_s1_s2_results.csv", data["results"] + data["S1_difference_in_differences"])
    cargo = [dict(comparison=r["comparison"], family=r["family"], **r["cargo_NI"])
             for r in data["results"] if r["cargo_NI"] is not None]
    publish(output / "cargo_noninferiority.json", dict(provenance=provenance, rows=cargo))
    table(output / "cargo_noninferiority.csv", cargo)
    support = ppo_support(panel)
    publish(output / "policy_seed_diagnostics.json", dict(provenance=provenance, rows=data["seed_results"], OOD_support=support))
    publish(output / "wait_cargo_forecast_diagnostics.json", dict(provenance=provenance, **diagnostics))
    from evidence import read as read_json
    compute = read_json(ctx["bundle"] / "compute_summary.json")
    publish(output / "compute_cost.json", dict(provenance=provenance,
               campaign={k: v for k, v in compute.items() if k != "profiles"},
               empirical_decision_latency=[r for r in diagnostics["rows"] if r["split"] == "test"],
               outer_episode_wall_cpu=[{k: r[k] for k in ("family", "world", "arm", "mean_wall_seconds", "mean_cpu_seconds")}
                                       for r in data["groups"] if r["split"] == "test"]))
    publish(output / "ablation_and_sensitivity_manifest.json", diagnostic)
    publish(output / "diagnostic_cost_proxy.json", diagnostic_cost_proxy(data["groups"], diagnostic))
    publish(output / "integrity/inherited_scoped_equivalence.json", ctx["inherited_gate"])
    table(output / "tables/diagnostic_cell_inventory.csv", diagnostic["sensitivity_cells"])
    table(output / "tables/coupling_cell_inventory.csv", diagnostic["coupling_cells"])
    table(output / "tables/outcome_groups.csv", data["groups"])
    table(output / "tables/scenario_paired_deltas.csv", [dict(comparison=k, **r) for k, rows in data["source_pairs"].items() for r in rows])
    # Full arrays retained for independent re-render; no scientific records copied.
    publish(output / "derived_arrays.json", data)
    publish(output / "closure_status.json", state)
    if args.render:
        from figures import render
        names = render(output, data, diagnostics, provenance)
        publish(output / "figures/figure_inventory.json", dict(names=names, provenance=provenance))
    from reporting import documents
    docs = documents(output, ctx, data, diagnostics, diagnostic, state, provenance)
    # Recheck inventory after every derived output/doc; new paths cannot silently
    # contaminate the original gate. No clean-tree rule or approval is bypassed.
    protected_source(ctx["lock"], ctx["bundle"])
    if code_inventory()!=inventory:
        raise ContractError("Step8 source inventory changed during analysis; refuse release")
    files = {p.relative_to(output).as_posix(): dict(sha256=sha(p), bytes=p.stat().st_size)
             for p in sorted(output.rglob("*")) if p.is_file() and p.name != "step8_release_manifest.json"}
    release = dict(schema="itp_step8_release_manifest_v1", analysis_sha256=digest, provenance=provenance,
                   status=state, files=files, documents=docs, frozen_source_unchanged=True)
    publish(output / "step8_release_manifest.json", release)
    # Timing varies, so exclusive invocation receipts live outside deterministic outputs.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    publish(OUTPUT_ROOT / "invocations" / (stamp + ".json"), dict(analysis_sha256=digest,
            wall_seconds=time.perf_counter()-start, cpu_seconds=time.process_time()-cpu,
            code_sha256=code_hash, git_head=ctx["git_head"], git_status=ctx["git_status"],
            action="read-only analysis", new_episodes=0))
    print(json.dumps(dict(output=str(output), release_sha256=sha(output / "step8_release_manifest.json"),
                          status=state, wall_seconds=time.perf_counter()-start), indent=2))
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    p.add_argument("--verify", action="store_true", help="bounded read-only input/source/receipt audit; NOT full canonical VerifyReturn")
    p.add_argument("--analyze", action="store_true", help="compute frozen paired bootstrap/NI; never evaluate policies")
    p.add_argument("--render", action="store_true", help="write 8 scientific figures from derived arrays")
    p.add_argument("--status", action="store_true", help="inspect real gates and latest release")
    p.add_argument("--diagnostic-preflight", action="store_true", help="publish literal protocol11 capability gaps; exit2 until resolved")
    args = p.parse_args()
    try:
        return execute(args)
    except (ContractError, s.CampaignError) as exc:
        print(json.dumps(dict(status="BLOCKED_NO_SCIENTIFIC_SOURCE_MODIFIED", error=str(exc))), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
