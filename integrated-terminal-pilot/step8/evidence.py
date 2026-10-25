"""Read-only Step7 evidence adapter. Deliberately outside its protected inventory."""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess

from tqdm import tqdm

from integrated_terminal_pilot.benchmark import step7 as s
from statistical import ContractError, SEEDS, d24, validate_cargo, validate_model_checkpoint

PROJECT = Path(__file__).resolve().parents[1]
REPO = PROJECT.parent
DEFAULT_BUNDLE = PROJECT / "experiments/step7_remote/step7_cpu3132_v2"
REVIEW = PROJECT / "experiments/step7_return_review_20261023"
PORTABLE_REVIEW = Path(__file__).resolve().parent / "review_reference"
EXPECTED_MANIFEST = "d180f1dec4fb212185b40658f7be47dc66d0bd08e66b6636f88cb45c42b8357d"
EXPECTED_LOCK = "1e62f58554ad97d29356243b99975f4d494b4ac58009a0fc19d464fb027cbcac"
REPORT = "report_8f17f4357902"


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def publish(path, value):
    """Exclusive, byte-idempotent publication. Never overwrites a prior revision."""
    data = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    publish_bytes(path, data)


def publish_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ContractError("Immutable output collision: " + str(path))
    else:
        with path.open("xb") as stream:
            stream.write(data)


def safe_path(base, rel):
    base = Path(base).resolve()
    target = (base / rel).resolve()
    if not target.is_relative_to(base):
        raise ContractError("Path escapes evidence root")
    return target


def manifest_file(bundle, manifest, path):
    path = Path(path)
    rel = path.relative_to(bundle).as_posix()
    item = manifest["files"].get(rel)
    if item is None or path.stat().st_size != item["bytes"] or sha(path) != item["sha256"]:
        raise ContractError("FAILED_INTEGRITY: " + rel)
    return item["sha256"]


def close(a, b, name):
    if a is None or b is None:
        if a is not b:
            raise ContractError("SOURCE_RECONCILIATION_EXCEPTION: " + name)
    elif not math.isclose(float(a), float(b), abs_tol=1e-7, rel_tol=1e-11):
        raise ContractError(f"SOURCE_RECONCILIATION_EXCEPTION: {name}: {a} != {b}")


def protected_source(lock, bundle):
    current = s.source_manifest()
    if set(current) != set(lock["source_sha256"]):
        raise ContractError("BLOCKED_SOURCE: protected inventory added/removed")
    newline = []
    for rel, expected in lock["source_sha256"].items():
        archived = safe_path(bundle / "source_snapshot", rel)
        local = safe_path(REPO, rel)
        if sha(archived) != expected:
            raise ContractError("FAILED_INTEGRITY: archived source " + rel)
        if current[rel] != expected:
            a = archived.read_bytes().replace(b"\r\n", b"\n")
            b = local.read_bytes().replace(b"\r\n", b"\n")
            if a != b:
                raise ContractError("BLOCKED_SOURCE: scientific source changed " + rel)
            newline.append(rel)
    return dict(count=len(current), inventory=current,
                inventory_sha256=s.digest(current), newline_only=newline,
                original_inventory_sha256=s.digest(lock["source_sha256"]),
                scientific_content="UNCHANGED")


def review_path(name):
    base = REVIEW if (REVIEW / "review_manifest.json").exists() else PORTABLE_REVIEW
    return base / name


def trusted_review(name):
    manifest = read(review_path("review_manifest.json"))
    if sha(review_path("review_manifest.json")) != "1c189d221f1b444a546e2379493333cffbfa7f727905f4eadc2027aa389e9056":
        raise ContractError("Historical reconciliation reference manifest changed")
    path = review_path(name)
    item = manifest["files"][name]
    if sha(path) != item["sha256"] or path.stat().st_size != item["bytes"]:
        raise ContractError("Historical review evidence changed: " + name)
    return read(path)


def return_gate(bundle, manifest):
    """Only the original verifier's sealed complete receipt can pass this gate.

    No synthetic replacement receipt is ever written to the Step7 bundle here.
    """
    valid = []
    for path in sorted((bundle / "return_verification").glob("*.json")):
        if path.name.endswith(".sha256.json"):
            continue
        receipt = s.unseal(path)
        if (receipt.get("status") != "VERIFIED_RETURN_AUDIT_ONLY" or
                receipt.get("manifest_sha256") != s.digest(manifest) or
                receipt.get("coverage") != manifest["coverage"] or
                receipt.get("scientific_status") != "COMPLETE_FOR_OWNER_REVIEW"):
            raise ContractError("FAILED_INTEGRITY: incompatible official return receipt")
        valid.append(dict(path=path.relative_to(REPO).as_posix(), sha256=sha(path)))
    if valid:
        return dict(RETURN_VERIFY="VERIFIED_FULL_CANONICAL", receipts=valid,
                    method="Original step7_remote.verify_return sealed receipt; no rerun")
    audit = trusted_review("bytes_metadata_audit.json")
    if audit["manifest_sha256"] != s.digest(manifest) or audit["paired_rows_verified"] != 1960:
        raise ContractError("Historical byte/metadata receipt belongs to different campaign")
    return dict(RETURN_VERIFY="BYTES_METADATA_ONLY_PENDING", receipts=[],
                historical_byte_metadata_receipt_sha256=sha(review_path("bytes_metadata_audit.json")),
                full_canonical_reinflation_complete=False,
                manual_command="powershell -NoProfile -ExecutionPolicy Bypass -File .\\integrated-terminal-pilot\\scripts\\Complete-Step7.ps1 -Action VerifyReturn")


def intake(bundle):
    bundle = Path(bundle).resolve()
    from integrated_terminal_pilot.benchmark.step7_workspace import configure
    configure(bundle)  # read-only path binding; never calls scenario generation
    manifest = s.unseal(bundle / "transfer_manifest.json")
    if s.digest(manifest) != EXPECTED_MANIFEST or sha(bundle / "protocol_lock_v1.json") != EXPECTED_LOCK:
        raise ContractError("FAILED_INTEGRITY: authoritative manifest/lock differs")
    lock = read(bundle / "protocol_lock_v1.json")
    if (bundle / "protocol_lock_v1.json.sha256").read_text().split()[0] != EXPECTED_LOCK:
        raise ContractError("FAILED_INTEGRITY: lock sidecar")
    session = s.unseal(bundle / "session.json")
    if (sha(bundle / "session.json") != manifest["session_sha256"] or
            session["head"] != lock["source_revision"] or
            session["head"] != manifest["source_revision"]):
        raise ContractError("FAILED_INTEGRITY: execution revision/session")
    source = protected_source(lock, bundle)
    planpath = safe_path(bundle, manifest["plan"])
    manifest_file(bundle, manifest, planpath)
    plan = s.unseal(planpath)
    s.validate_plan(plan)
    if s.digest(plan) != lock["plan_sha256"] or plan["analysis_contract"] != lock["analysis"]:
        raise ContractError("FAILED_INTEGRITY: locked analysis/plan mismatch")
    if s.digest(s.require_owner()) != lock["owner_approval_sha256"]:
        raise ContractError("FAILED_INTEGRITY: original owner approval")
    if sha(bundle / "inputs/approved_generator_decisions.yaml") != lock["effective_register_sha256"]:
        raise ContractError("FAILED_INTEGRITY: approved values overlay")
    reg = s.unseal(PROJECT / lock["regression_evidence"])
    if (s.digest(reg) != lock["regression_sha256"] or reg["implementation_digest"] !=
            s.digest({p: h for p, h in lock["source_sha256"].items() if p.endswith((".py", ".ps1", ".toml"))})):
        raise ContractError("FAILED_INTEGRITY: source-bound regression proof")
    if reg["parameter_values_sha256"] != s.load_generator_config().parameters_fingerprint:
        raise ContractError("FAILED_INTEGRITY: numeric parameter fingerprint")
    scoped_gate_path = bundle / "inputs/prerequisites/evidence/step6_gate.json"
    manifest_file(bundle, manifest, scoped_gate_path)
    scoped_gate = read(scoped_gate_path)
    if (s.digest(scoped_gate) != "7cb84b87c78f3b2a6628a59ce4a2013b90ba8d66c347230eab24d6095f18c5c2"
            or scoped_gate["contract_defects"] != 0):
        raise ContractError("FAILED_INTEGRITY: inherited approved scoped equivalence evidence")
    restoration = trusted_review("reference_restoration.json")
    # Independently recheck the seven original manifested files, without copying.
    verify_restoration(restoration, manifest, bundle)
    reports = planpath.parent / "reports"
    required = [reports / f"{REPORT}_{name}.csv" for name in
                ("episodes", "groups", "pairs", "a3_scenario_means", "s1_reference", "vessels")]
    required += [reports / "diagnostics_fd979c5222b3.json", bundle / "compute_summary.json"]
    inputs = {p.relative_to(bundle).as_posix(): manifest_file(bundle, manifest, p) for p in required}
    git_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    status = subprocess.check_output(["git", "status", "--short"], cwd=REPO, text=True).strip()
    return dict(bundle=bundle, manifest=manifest, lock=lock, plan=plan, directory=planpath.parent,
                source=source, gate=return_gate(bundle, manifest), inputs=inputs,
                git_head=git_head, git_status=status,
                inherited_gate=dict(path=scoped_gate_path.relative_to(REPO).as_posix(),
                                    file_sha256=sha(scoped_gate_path), canonical_sha256=s.digest(scoped_gate),
                                    status=scoped_gate["gate"], eligible_decisions=scoped_gate["eligible_decisions"],
                                    full=scoped_gate["full"], noneligible=scoped_gate["noneligible"]))


def verify_restoration(restoration, manifest, bundle):
    rows = restoration["restored"]
    if len(rows) != 7 or len({r["path"] for r in rows}) != 7:
        raise ContractError("Restoration must retain exactly seven distinct reference paths")
    if restoration["scientific_results_modified"] or restoration["models_loaded"]:
        raise ContractError("Restoration was not original-byte transport repair")
    archive = PROJECT / "assets/step7_remote_inputs_v2.zip"
    if sha(archive) != restoration["archive_sha256"]:
        raise ContractError("Authentic v2 transport archive changed")
    for row in rows:
        expected = manifest["files"].get(row["path"])
        if not expected or expected["sha256"] != row["sha256"] or expected["bytes"] != row["bytes"]:
            raise ContractError("Restored reference digest differs from original manifest")
        manifest_file(bundle, manifest, safe_path(bundle, row["path"]))


def identity(row):
    return (row["split"], row["family"], row["scenario_id"], row["world"], row["arm"], row["training_seed"])


def load_panel(ctx):
    """One bounded pass over original summary envelopes; no trace inflation/pickle.

    Validates original per-vessel D24 and ledger-derived cargo partitions against
    CSV. Deep canonical stream verification remains exclusively the official gate.
    """
    csv.field_size_limit(2**31 - 1)
    path = ctx["directory"] / "reports" / f"{REPORT}_episodes.csv"
    csvrows = {}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["row_id"] in csvrows:
                raise ContractError("Duplicate source row_id")
            csvrows[row["row_id"]] = row
    if len(csvrows) != len(ctx["plan"]["rows"]):
        raise ContractError("Missing/unplanned original rows")
    panel, pairs, exceptions, scenarios = [], {}, [], {}
    recipes = {x["scenario_id"]: x for x in ctx["plan"]["scenarios"]}
    plan_hash = s.digest(ctx["plan"])
    modelhash = {r["training_seed"]: r["sha256"] for r in ctx["lock"]["checkpoints"]["checkpoints"]
                 if r["regime"] == "medium_heavy"}
    for item in tqdm(ctx["plan"]["rows"], desc="Step8 read-only summary audit", unit="row", ascii=True):
        path = s.run_path(ctx["directory"], item)
        manifest_file(ctx["bundle"], ctx["manifest"], path)
        envelope = s.unseal(path)
        raw = csvrows[item["row_id"]]
        if envelope["row"] != item or envelope["plan_sha256"] != plan_hash:
            raise ContractError("Result is not paired to exact plan")
        if envelope["lock_file_sha256"] != EXPECTED_LOCK:
            raise ContractError("Episode source lock drift")
        pairing = envelope["pairing"]
        sid = item["scenario_id"]
        if sid not in scenarios:
            scenario_path = s.scenario_path(ctx["directory"], recipes[sid])
            source_hash = manifest_file(ctx["bundle"], ctx["manifest"], scenario_path)
            doc = s.unseal(scenario_path)
            if doc["recipe_sha256"] != recipes[sid]["recipe_sha256"]:
                raise ContractError("Scenario recipe drift")
            document = doc["document"]
            if (document["identity"]["scenario_id"] != sid or
                    document["identity"]["scenario_family"] != item["family"] or
                    document["identity"]["split"] != item["split"]):
                raise ContractError("Scenario source identity mismatch")
            expected_t_end = max(v["arrival_time_min"] for v in document["vessels"]) + 10080.
            outbound = [c["container_id"] for c in document["containers"] if c["destination_vessel_id"] is not None]
            if len(outbound) != len(set(outbound)):
                raise ContractError("Original outbound obligation identities duplicate")
            n_out = len(outbound)
            scenarios[sid] = (source_hash, document["fingerprints"], n_out, expected_t_end,
                              sorted(v["vessel_id"] for v in document["vessels"]))
        source_hash, fingerprints, n_out, expected_t_end, source_vessel_ids = scenarios[sid]
        if (envelope["scenario_file_sha256"] != source_hash or fingerprints != pairing["fingerprints"]
                or pairing["N_out"] != n_out or pairing["T_end_min"] != expected_t_end):
            raise ContractError("Authoritative source traffic/N_out/T_end differs")
        if pairs.setdefault(sid, pairing) != pairing:
            raise ContractError("EXOGENOUS_INPUT_DRIFT: quarantine " + sid)
        for k in ("scenario_id", "family", "split", "world", "arm"):
            if raw[k] != item[k]:
                raise ContractError("CSV row identity differs")
        seed = int(raw["training_seed"]) if raw["training_seed"] else None
        if seed != item["ppo_training_seed"] or raw["status"] != envelope["status"]:
            raise ContractError("Checkpoint seed/status differs")
        r = dict(row_id=item["row_id"], scenario_id=sid, split=item["split"], family=item["family"],
                 world=item["world"], arm=item["arm"], training_seed=seed,
                 status=envelope["status"], pairing=pairing, source_file_sha256=sha(path),
                 N_out=pairing["N_out"], T_end=pairing["T_end_min"],
                 wall=envelope["wall_seconds"], cpu=envelope["cpu_seconds"])
        if r["status"] not in ("COMPLETED", "FAILED", "G_BLOCKED"):
            raise ContractError("Unrecognized eligibility status")
        if r["status"] != "COMPLETED":
            exceptions.append(dict(row_id=r["row_id"], reason=r["status"],
                                   treatment="exclude only affected contrast; no survivor-seed mean"))
            panel.append(r)
            continue
        data = envelope["result"]
        if item["world"] == "integrated":
            shared = data["shared"]
            if (shared["quay_crane_count"], shared["yard_policy_id"], shared["max_load_wait_min"],
                    shared["batch_size_containers"], shared["efficiency_basis"]) != (
                    8, "yard_occupancy_balance_v1", 240., 10, "assigned"):
                raise ContractError("Shared primary physics/profile drift")
            if (data["comparison_fingerprint"] != pairing["comparison_fingerprint"] or
                    data["scenario"]["fingerprints"] != pairing["fingerprints"] or
                    not data["audits"]["ok"] or data["rejections"]):
                raise ContractError("Original audit/comparison fingerprint mismatch")
            if item["arm"] == "A3":
                ck = data["policy"]["checkpoint"]
                validate_model_checkpoint(ck, seed, modelhash[seed])
            cargo = data["outbound_obligations"]
            r["R"] = validate_cargo(cargo, r["N_out"], r["T_end"])
            vessels = sorted(data["complete_result"]["vessels"], key=lambda v: v["vessel_id"])
            if [v["vessel_id"] for v in vessels] != source_vessel_ids:
                raise ContractError("D24 must include exactly every original vessel")
            total = d24(vessels, r["T_end"])
            close(total, data["kpi"]["total_turnaround_min"], item["row_id"] + " D24")
            waiting = sum((v["berth_start_time_min"] if v["berth_start_time_min"] is not None
                           else r["T_end"]) - v["arrival_time_min"] for v in vessels)
            close(waiting, data["kpi"]["total_berth_waiting_min"], "all-vessel waiting")
            if data["status"] not in s.VALID_ENDS:
                raise ContractError("Ineligible terminal end")
            r.update(TA=total, U=cargo["U_not_loaded"], loaded=cargo["loaded"],
                     cargo_classes=cargo["classes"], cargo_teu=cargo["teu"],
                     loaded_not_departed=cargo["loaded_but_vessel_not_departed"],
                     terminal_end=data["status"], n_vessels=len(vessels),
                     waiting_total=waiting, waiting=waiting / len(vessels),
                     p95_waiting=data["kpi"]["p95_berth_waiting_min"],
                     vessel_TA=[v["turnaround_min_censored"] for v in vessels],
                     vessel_wait=[v["waiting_time_min"] for v in vessels],
                     kpi=data["kpi"], service=data["service_compliance"],
                     decisions=data["decisions"], model_sha256=modelhash.get(seed))
        else:
            ref = data["reference"]
            if ref["status"] != "completed_valid":
                raise ContractError("Reference not completed valid")
            refv = sorted(ref["vessel_results"], key=lambda v: v["vessel_id"])
            if [v["vessel_id"] for v in refv] != source_vessel_ids:
                raise ContractError("Reference omitted original vessels")
            r.update(TA=ref["total_turnaround_min"], U=None, R=None,
                     n_vessels=ref["vessel_count"], terminal_end="REFERENCE_COMPLETED_VALID",
                     waiting_total=ref["total_waiting_time_min"],
                     vessel_TA=[v["turnaround_time_min"] for v in refv],
                     model_sha256=modelhash.get(seed))
        for key, value in (("turnaround", r["TA"]), ("N_out", r["N_out"]), ("T_end_min", r["T_end"])):
            close(value, float(raw[key]), item["row_id"] + " " + key)
        if r["world"] == "integrated":
            close(r["U"], float(raw["U"]), "CSV U")
            close(r["R"], float(raw["R"]) if raw["R"] else None, "CSV R")
        panel.append(r)
    verify_panel(panel)
    return dict(rows=panel, pairing_index=pairs, exceptions=exceptions,
                status_counts=dict(Counter(r["status"] for r in panel)),
                verification_scope="Original summary envelopes + manifested CSV + D24/cargo partitions; NOT canonical trace reinflation")


def verify_panel(rows):
    seen = set()
    pairing = {}
    for row in rows:
        key = identity(row)
        if key in seen:
            raise ContractError("Duplicate scientific identity")
        seen.add(key)
        sid = row["scenario_id"]
        prefix = row["family"] + "_" + row["split"] + "_seed"
        if (row["family"] not in ("itp_medium", "itp_heavy") or row["split"] not in ("validation", "test")
                or not sid.startswith(prefix)):
            raise ContractError("Cross-family/split scenario identity")
        if pairing.setdefault(sid, row["pairing"]) != row["pairing"]:
            raise ContractError("EXOGENOUS_INPUT_DRIFT")
        if row["training_seed"] not in (None, *SEEDS):
            raise ContractError("Unapproved training seed")
        if row["arm"] == "A3" and row["training_seed"] not in SEEDS:
            raise ContractError("A3 seed missing")
        if row["arm"] != "A3" and row["training_seed"] is not None:
            raise ContractError("Unexpected training seed")
    groups = defaultdict(list)
    for r in rows:
        groups[(r["split"], r["family"], r["scenario_id"], r["world"])].append(r)
    for key, members in groups.items():
        arms = Counter((r["arm"], r["training_seed"]) for r in members)
        required = {(a, seed) for a, seed in (s.ARMS if key[-1] == "integrated" else s.REFERENCE_ARMS)}
        if set(arms) != required or any(n != 1 for n in arms.values()):
            raise ContractError("Missing/duplicate paired row (no silent deletion)")


def code_inventory():
    base = Path(__file__).resolve().parent
    return {p.relative_to(REPO).as_posix(): sha(p) for p in sorted(base.rglob("*"))
            if p.is_file() and p.suffix in (".py", ".ps1", ".json", ".md") and "__pycache__" not in p.parts}
