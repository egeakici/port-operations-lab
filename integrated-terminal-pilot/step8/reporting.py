"""Traceable reports. These never label pending canonical or diagnostic gates PASS."""
import json
from pathlib import Path

from evidence import PROJECT, REPO, publish_bytes, sha


def number(value, places=3):
    return "NA" if value is None else f"{value:.{places}f}"


def ci_text(ci, scale=1):
    if ci is None:
        return "NA"
    return f"{number(scale*ci['estimate'])} [{number(scale*ci['lower'])}, {number(scale*ci['upper'])}]"


def markdown_table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |",
                       "| " + " | ".join("---" for _ in headers) + " |"] +
                      ["| " + " | ".join(str(x) for x in row) + " |" for row in rows])


def documents(output, ctx, data, diagnostics, diagnostic, state, prov):
    # Nested docs are required: frozen source_manifest scans docs/*.md (not
    # subdirectories). No protected source needs an exemption or edited verifier.
    target = PROJECT / "docs/step8" / output.name
    prefix = ("**PROVISIONAL — SYNTHETIC / UNCALIBRATED. Project I is NOT finally closed.**\n\n"
              "Official full canonical return verification is " + ctx["gate"]["RETURN_VERIFY"] +
              ". Primary Holm interval construction and the required diagnostic campaign remain blocked. "
              "The numerical calculations below are conditional previews, not final public inferential claims.\n\n")
    source = (f"Analysis `{prov['analysis_sha256']}`; code `{prov['code_sha256']}`. "
              f"Step7 manifest `{prov['manifest_sha256']}`; lock `{prov['lock_file_sha256']}`. "
              f"Frozen scientific revision `{prov['source_revision']}`; analysis HEAD `{ctx['git_head']}`.\n\n")
    from analysis import diagnostic_cost_proxy
    proxy=diagnostic_cost_proxy(data["groups"],diagnostic)
    result = {(r["family"], r["comparison"]): r for r in data["results"]}
    groups = {(r["family"], r["arm"]): r for r in data["groups"] if r["split"] == "test" and r["world"] == "integrated"}
    families = ("itp_medium", "itp_heavy", "equal_family_overall")
    allrows = []
    for family in families:
        for comparison in ("B1-A1n", "B2-A2", "B1-A1", "A1n-A1", "A2-A1", "A3-A1", "A3-A2", "B2-A1", "B2-T-A2", "B2-B2-T"):
            r = result[family, comparison]
            cargo = r["cargo_NI"]
            allrows.append([family, comparison, r["n_traffic_scenarios"], ci_text(r["time_CI95"]),
                            ci_text(r["paired_percent_CI95"]), number(r["mean_cargo_rate_difference"], 6),
                            number(None if cargo is None else cargo["upper"], 6), r["NI_verdict"],
                            r["time_verdict"], r["combined_time_and_cargo_verdict"]])
    resulttable = markdown_table(["Family", "Policy-comparator", "n", "Delta total TA [raw95%CI] vessel-min",
                                 "Mean paired % [95%CI]", "Delta R fraction", "R upper95 fraction", "NI(+.01)", "Time verdict", "Combined"], allrows)
    cargo_rows = []
    for r in data["results"]:
        c = r["cargo_NI"]
        if c is not None:
            cargo_rows.append([r["family"], r["comparison"], r["n_traffic_scenarios"], number(c["estimate"]*100),
                               number(c["upper"]*100), c["verdict"], c["zero_margin"]])
    cargotable = markdown_table(["Family", "Comparison", "n", "Mean delta R (pp)", "Upper95 (pp)", "+1pp NI", "0pp sensitivity"], cargo_rows)
    outcome_rows = []
    for f in families[:2]:
        for a in ("A1", "A1n", "B1", "A2", "A3-train11", "A3-train23", "A3-train37", "A3", "B2-T", "B2"):
            g = groups[f,a]
            outcome_rows.append([f,a,number(g["mean_TA_per_vessel"],2),number(g["pooled_vessel_median_TA"],2),
                                 number(g["pooled_vessel_p95_TA"],2),number(g["mean_waiting"],2),
                                 number(g["mean_p95_waiting"],2),number(g["mean_U"],2),number(g["mean_R"]*100,4),
                                 f"{g['terminal_completed']}/50; {g['failed']}/{g['deadlock']}/{g['truncated']}"])
    outcomes = markdown_table(["Family","Arm","Mean TA/vessel","Median vessel TA","P95 vessel TA","Mean wait/vessel",
                              "Mean of scenario P95 wait","Mean U containers","Mean R (%)","complete; fail/deadlock/trunc"], outcome_rows)
    s1table = markdown_table(["Family", "S1 source-defined DID", "n", "Delta total TA [95%CI] vessel-min"],
                            [[r["family"],r["comparison"],r["n_traffic_scenarios"],ci_text(r["time_CI95"])]
                             for r in data["S1_difference_in_differences"]])
    ranktable = markdown_table(["Family", "Contrast", "Sign agreement", "Reference delta [95%CI] vessel-min"],
                              [[r["family"],r["contrast"],number(r["sign_agreement"]),ci_text(r["reference_CI95"])]
                               for r in data["S1_sign_agreement"]])
    seedtable = markdown_table(["Family", "Seed comparison (descriptive)", "TA delta [95%CI] vessel-min", "Cargo upper95 (pp)", "NI"],
                              [[r["family"],r["comparison"],ci_text(r["time_CI95"]),number(r["cargo_NI"]["upper"]*100),r["NI_verdict"]]
                               for r in data["seed_results"] if r["family"] != "equal_family_overall"])
    diag = {(r["family"],r["arm"]):r for r in diagnostics["rows"] if r["split"] == "test"}
    costrows=[]; forecastrows=[]
    for f in families[:2]:
        for a in ("A2","A3","B2-T","B2"):
            d=diag[f,a]
            costrows.append([f,a,d["decisions"],d["waits"],number(d["cost"]["mean"],6),number(d["cost"]["p95"],6),
                             number(d["cost"]["max"],6),number(groups[f,a]["mean_wall_seconds"],2)])
        for a in ("B1","B2-T","B2"):
            d=diag[f,a]
            forecastrows.append([f,a,d["cargo_pivotal"],d["one_container_pivotal"],
                                 number(d["cargo_error"]["mean"] if d["cargo_error"] else None),
                                 number(d["cargo_error"]["MAE"] if d["cargo_error"] else None),
                                 number(d["TA_error"]["mean"] if d["TA_error"] else None),
                                 number(d["b1_error"]["MAE"] if d["b1_error"] else None)])
    costtable=markdown_table(["Family","Arm","Decisions","WAIT","Mean selection s","P95 selection s","Max selection s","Mean outer wall s"],costrows)
    forecasttable=markdown_table(["Family","Arm","Cargo pivotal observations","1-container pivots","Mean U forecast error","U MAE","Cohort TA signed error min","B1 release MAE min"],forecastrows)
    def claim(f,c):
        r=result[f,c]; cargo=r["cargo_NI"]
        return (f"{f}: {c}, delta TA/vessel {ci_text(r['TA_per_vessel_CI95'])} min; "
                f"mean paired percentage {ci_text(r['paired_percent_CI95'])}%; mean U delta {number(r['mean_U_difference'],2)}. "
                + (f"Cargo upper95={number(cargo['upper']*100)} pp; +1pp NI {cargo['verdict']}, zero-margin {cargo['zero_margin']}. " if cargo else "Cargo NI is not a registered comparison for this pair. ")
                + f"Time classification: {r['time_verdict']} (unadjusted: {r['unadjusted_time_label']}).")
    findings="\n\n".join(claim(f,c) for c in ("B2-A2","B2-T-A2","B2-B2-T","A3-A1","A3-A2","B1-A1n","B1-A1") for f in families[:2])
    ppo_qualification=("The registered +1pp NI rule allows some cargo deterioration: A3 versus A1 PASSES in Medium "
        "(mean +0.371pp, upper +0.566pp) while its time95%CI is below zero. Thus the provisional registered combined "
        "criterion is met in Medium. It is NOT met in Heavy (mean +2.606pp, upper +2.879pp), nor in the equal-family "
        "summary (upper +1.658pp). Zero-margin sensitivity fails in both families. Do not replace the approved1pp margin "
        "with zero to make Medium fail, and do not call a1pp pass proof of zero cargo harm. This is a formal-method "
        "qualification of the earlier descriptive review, not a numeric discrepancy or redefinition.\n\n")
    plan_table=markdown_table(["Requirement","Authority","Planned scope","Actual coverage","Gate"],[
        ["Matched cargo-first objective","AM07/08","B2 vs B2-T same140 traffic cases","100 test +40 validation paired","COMPUTED, provisional return"],
        ["Model-only coupling ablations","protocol11 + approved scoped equality","none/crane-aware/yard-aware/both; outer physics full","0 new13M; exact coupling episode matrix unspecified","BLOCKED API + scope contract"],
        ["OFAT sensitivity","protocol11 / locked ranges","20 diagnostic cases/family/condition, A1/A2/B2/A3x3",f"0/{len(diagnostic['sensitivity_cells'])} listed cells; {diagnostic['sensitivity_explicit_unsupported']} explicitly unsupported","PENDING MANUAL; implementation blocked"],
        ["D17 120/480","AM03 / locked ranges","included as OFAT conditions","0 new13M","PENDING MANUAL"],
        ["Low/Bottleneck","approved family roles","diagnostic only; not specified as extra primary/condition families","historical development retained","not promoted; no invented new family campaign"]])
    limitations=("The synthetic v1 coefficients have no real-terminal calibration. Fifty test traffic scenarios per family are independent units; "
        "containers, decision epochs, vessels and training seeds are not extra traffic samples. Intervals are conditional on exactly three preselected PPO models. "
        "D24 includes every vessel and censors unfinished vessels at the common T_end; 1260 integrated episodes completed without deadlock/truncation, "
        "which does not imply every cargo obligation was loaded. U counts unique original obligations without LOAD_COMPLETED; TEU, moves and departure are separate facets.\n\n"
        "B2-A2 changes the physical forecast and objective priority (coordination package). B2-T-A2 controls turnaround priority but still changes modelling assumptions. "
        "B2-B2-T is a matched objective ablation, although subsequent states diverge. None establishes universal global optimality or three-agent RL. "
        "No computational budget matching by wall time is claimed. Full cohort, legal candidates and WAIT remain uncapped; 2-second warnings are not timeouts.\n\n"
        "B2 improves cargo against A2 in14/50 Medium and49/50 Heavy cases (all other cases tie), but Medium time worsens18/50 and Heavy6/50. "
        "Against FCFS, one Heavy case has worse B2 cargo. The mean can hide adverse tails; worst IDs and P95 paired deltas are retained in machine tables. "
        "Frozen PPO improves mean time against FCFS but increases cargo loss, especially Heavy; a failed NI result means NI NOT_DEMONSTRATED, not automatic statistical inferiority. "
        "Its mean of scenario P95 waiting increases against FCFS; selecting its best seed post-test is forbidden.\n\n"
        "PPO remaining-occupancy features exceeded the training maximum in1772/3806 Heavy test decisions and1130/2417 Medium test decisions. "
        "This is distribution shift, not a causal diagnosis. B2 forecasts omit future landside gate-in/pickup under Q6-2, and remain UNCALIBRATED_SYNTHETIC_FORECAST. "
        "Selected forecasts belong to different visited states. Observed WAIT/cargo-pivotal coincidence does not identify counterfactual effects. "
        "Cargo primary causal tags are UNKNOWN_OR_MULTIPLE_CONSTRAINTS. Zero one-container pivots does not remove the design's permitted one-container priority.\n\n"
        "Historical campaign stage durations sum28.50h, including profiling/reporting gates; outer episode wall sums20.09h. Sampled RSS maximum769.1MiB is not a continuous peak. "
        "B2 Heavy mean8.258s, P9526.136s, maximum69.540s per policy selection is a research cost, not a certified operational SLA. "
        "Simulation minutes are not CPU/wall seconds. CUDA was not used to accelerate the event simulator.\n\n"
        "The official canonical return PASS is missing. The protocol specifies a Holm-adjusted confidence interval but no construction/inversion/order rule; "
        "the source and locked contract contain no implementation. Raw95% intervals are provided without substituting a Wilcoxon p-value or post-hoc Bonferroni rule. "
        "The required13M study also has genuine source-contract gaps. These block final closure, regardless of favorable estimates.")
    commands=("```powershell\n& {\n"
              "    $ErrorActionPreference = 'Stop'\n"
              "    $env:PYTHONDONTWRITEBYTECODE = '1'\n"
              "    $env:PYTHONUTF8 = '1'\n"
              "    powershell -NoProfile -ExecutionPolicy Bypass -File .\\integrated-terminal-pilot\\scripts\\Complete-Step7.ps1 -Action VerifyReturn\n"
              "    if ($LASTEXITCODE -ne 0) { throw 'Canonical return verification failed; preserve all evidence.' }\n"
              "    $step8Python = (Get-Command python -ErrorAction Stop).Source\n"
              "    if (Test-Path -LiteralPath '.\\.venv\\step7-cpu3132\\Scripts\\python.exe') { $step8Python = '.\\.venv\\step7-cpu3132\\Scripts\\python.exe' }\n"
              "    & $step8Python .\\integrated-terminal-pilot\\step8\\run_tests.py\n"
              "    if ($LASTEXITCODE -ne 0) { throw 'Focused Step8 tests failed.' }\n"
              "    & $step8Python .\\integrated-terminal-pilot\\step8\\run_step8.py --analyze --render\n"
              "    if ($LASTEXITCODE -ne 0) { throw 'Read-only Step8 refresh failed; no original record was changed.' }\n"
              "    & $step8Python .\\integrated-terminal-pilot\\step8\\run_step8.py --status\n"
              "    if ($LASTEXITCODE -ne 0) { throw 'Step8 status audit failed.' }\n"
              "}\n```\n\n"
              "Run from the repository root. This verifies archives and refreshes analysis only; it does NOT start new simulation. "
              "There is deliberately no claimed working13M execution command: current frozen APIs cannot implement the locked model-only switches/scoped equality. "
              "`python integrated-terminal-pilot/step8/run_step8.py --diagnostic-preflight` publishes the exact blockers and exits2. "
              "Do not treat that failure as a reason to rerun Step7. A prospectively specified diagnostic implementation and a scientifically justified Holm construction "
              "are needed before a complete Step8 launch can be provided. They cannot be administratively inferred from the existing approval.\n")
    audit=("# Step8 source and evidence audit\n\n"+prefix+source+
        f"Protected inventory: **{ctx['source']['count']} paths**, content unchanged; actual byte-map hash `{ctx['source']['inventory_sha256']}`. "
        f"Original map hash `{ctx['source']['original_inventory_sha256']}`. CRLF/LF-only paths: {len(ctx['source']['newline_only'])}. "
        "The complete path/hash list is `integrity/source_audit.json`. The real intake Git status is retained in each timestamped invocation receipt; "
        "new Step8 code/docs are uncommitted and no approval/HEAD rewrite occurred.\n\n"+
        markdown_table(["Priority","Authoritative source","Interpretation"],[
            [1,"protocol_lock_v1.json + exact original manifests/records","Scientific numeric truth and locked analysis"],
            [2,"frozen protocol + approved AM01–10 + OP remote lineage","Balanced Yard QC8; D15=10/D17=240; assigned efficiency; authentic A2; all models; uncapped K5-A"],
            [3,"actual approved28 packet/reply + copied approved register","Owner replied1 on14Oct; no reapproval inferred or requested"],
            [4,"original archive return verifier sealed PASS","Required; a metadata receipt is not a replacement"],
            [5,"23Oct owner review","Reconciliation targets; original records override prose"],
            [6,"old readiness/presentation status prose","Historical not-started/pending state; superseded by actual immutable1960-run campaign"]])+
        "\n\nExactly1960 rows:1260 integrated +700 authentic projection references;20validation +50test per family,140 scenarios. "
        "0 FAILED/G_BLOCKED/unrun/interrupted. Step7 historical regression561/561 incl9slow; P03eligible420/420 with original exclusions—not a PASS for excluded modules. "
        "All seven restored original references rechecked against original manifest; restoration/archive hashes retained, no generation/model loading. "
        "Owner approval, effective register, numeric fingerprint, source-bound regression and lock/plan/session linkage rechecked. "
        "D24 recomputed from original per-vessel summaries; cargo classes and U/Nout rechecked. Canonical compressed-stream reinflation remains exclusively the official manual gate.\n\n"
        "The inherited approved scoped gate canonical SHA7cb84b87c78f... matches the original manifested bundle evidence:12 FULL fixtures,20 exact-eligible decisions,5 noneligible fixtures,0 contract defects. "
        "It was read, not re-executed; these counts do not establish universal none/A2 equivalence.\n\n"
        "Discrepancies: no numeric discrepancy against the review at full-precision reconciliation tolerance. "
        "The old review diagnostic P95 used floor-order statistics; Step8 recomputes numpy-linear empirical P95 from original diagnostic archives. "
        "This is a labelled reporter quantile correction, not a changed outcome/policy. Source/presentation pending labels are historical. "
        "The Holm and diagnostic API gaps are implementation/specification discrepancies, not unfavorable results.\n\n"
        "New code lives in `step8/`; these docs live in `docs/step8/<analysis-id>/` because the locked scanner uses `docs/*.md`. "
        "This preserves all413 protected paths without an exemption, monkey patch or edited verifier. "
        "Figures and arrays are ignored under `experiments/step8_analysis/`. No unrelated files changed.\n\n"+commands)
    methods=("# Step8 statistical analysis protocol and results\n\n"+prefix+source+
        "For every traffic scenario, Delta=policy minus comparator; negative time/cargo favors the policy. "
        "TA is D24 sum min(departure,Tend)-arrival over ALL vessels; Tend=last arrival+10080. "
        "Delta R is U(policy)/Nout - U(comparator)/Nout. Unique original container obligations—not TEU/moves—define Nout. "
        "Loaded-but-not-departed and D17 rollover are separately preserved. Nout=0 is NOT_APPLICABLE.\n\n"
        "Time bootstrap:10000 paired scenario draws, PCG64 numpy.default_rng(120001), percentile2.5/97.5 using linear quantile. "
        "Cargo:10000 paired draws, seed20261013, one-sided percentile95 UPPER bound <=.01; zero-margin sensitivity separately. "
        "Sorted family/scenario order; reset RNG per estimand and per single-family result; overall draws families in sorted order and weights each.5. "
        "A3 models11/23/37 average within scenario before resampling; missing/blocked seed invalidates aggregate. No150-scenario fiction. "
        "DEADLOCK/TRUNCATED outcomes retain D24 censoring; FAILED only removes involved contrasts with IDs; exogenous drift quarantines whole scenario. "
        "The actual campaign has no such failures/exclusions. All50 test scenarios per family are retained.\n\n"
        "Primary Holm family: B1-A1n and B2-A2. The frozen construction is unspecified: all primary CIs below are UNADJUSTED95% and primary verdicts BLOCKED. "
        "Wilcoxon Pratt two-sided normal-approximation p-values with continuity correction are supplementary robustness fields, not the decision rule or a substitute Holm implementation. "
        "Secondary lower time requires upper CI<0, higher time lower CI>0, otherwise no detectable difference. "
        "NI failure is NOT_DEMONSTRATED, not automatic inferiority. A combined claim requires the correct time criterion AND the registered NI comparison. "
        "B2-A1 and A3-A2 have no registered cargo NI pair; no new formal comparator is silently added.\n\n"+
        resulttable+"\n\n## Cargo NI (+1pp and 0pp)\n\n"+cargotable+
        "\n\n## S1 reference transfer\n\n"+s1table+"\n\n"+ranktable+
        "\n\n"+ppo_qualification+"The DID is the original protocol estimand of policy-relative effects under different physical models, not raw environment totals or a causal intervention estimate. "
        "Mean ranking and per-scenario Kendall tau-b are in `primary_s1_s2_results.json`; no Project03 held-out archive was opened.\n\n"+
        seedtable+"\n\nConditional on the three models, no training-seed uncertainty or best-seed selection. "
        "Mean paired percentage is computed per scenario before averaging, distinct from percentage change of group means; both fields are retained. "
        "Tail counts, P95 deltas and worst scenario IDs accompany every comparison. All counts/estimates trace to scenario_paired_deltas.csv and hashed cache.\n")
    ablations=("# Step8 ablations and sensitivity\n\n"+prefix+source+plan_table+"\n\n"+
        "\n\n".join(claim(f,"B2-B2-T") for f in families[:2])+"\n\n"+
        f"There are {len(diagnostic['conditions'])} distinct OFAT conditions including shared base; {len(diagnostic['sensitivity_cells'])} explicitly enumerated outer-run cells "
        f"(including {diagnostic['sensitivity_explicit_unsupported']} locked-unsupported Heavy0.3 occupancy cells). "
        "These are planning requirements, NOT completed or currently executable runs; no favorable-case selection or count reduction. "
        "First20 diagnostic namespace seeds13000000..13000019 are explicit proposed plan identities;20/family/condition and seed band are frozen. "
        "The four coupling conditions imply160 B2 diagnostic cells by section6.5's20/family/condition, with A2 controls in the base sensitivity suite. "
        "Both/base may share an identical verified record only if the future adapter proves identity. "
        "The exact model-switch/scoped-contract execution mapping remains unresolved.\n\n"+
        markdown_table(["Factor","Locked levels"],[[k,json.dumps(v)] for k,v in diagnostic["ranges"].items()])+
        "\n\nExecution physics must remain full during information ablations. AM07 cargo-first objective remains unchanged, with B2-T separately measured. "
        "Turning transport/yard off in the outer kernel would violate that distinction. None==A2 is only supported by the prior predeclared exact-eligible predicate "
        "(exclusive fixed-rate cranes, ready cargo, uncensored completion etc.); realistic cargo availability/censoring prevents a universal claim.\n\n"+
        "\n".join("- "+b for b in diagnostic["blockers"])+"\n\n"
        f"Summing each planned cell's matching Step7 arm/checkpoint/family mean outer wall gives a full sensitivity baseline proxy of {proxy['sensitivity_base_wall_proxy_hours']:.2f}h "
        f"(supported cells only: {proxy['remaining_supported_cells_base_wall_proxy_hours']:.2f}h); the four coupling conditions using full-B2 timing as a proxy give {proxy['coupling_full_model_wall_proxy_hours']:.2f}h separately. "
        "These are NOT a guaranteed ETA or upper bound and exclude generation/verification/export; no overlapping both/base rows are silently added into a claimed total. "
        "Historical baseline timing proxy may estimate scale, not a bound; changed traffic/congestion could be slower. "
        "No new episode was used for cost estimation, no180-minute cap was imported, and no diagnostic was auto-launched. "
        "A new properly specified model-only adapter/campaign is required before owner-manual simulation. "
        "The CLI's --diagnostic-preflight intentionally exits2 and does not masquerade as a working run/resume engine. "
        "Automatic final diagnostic ingestion cannot honestly be advertised before those schemas/contracts exist.\n")
    failure=("# Step8 failure modes and limitations\n\n"+prefix+source+limitations+"\n\n"+costtable+"\n\n"+forecasttable+
             "\n\nArchive diagnostics:27244 decisions,2044 WAIT;284 pivotal trajectory observations (B2=114,B2-T=170); zero one-container pivots;4139 compute warnings. "
             "These are repeated trajectory observations, not distinct traffic replications. Full selected-state arrays remain in original diagnostic archives.\n")
    report=("# Project I final scientific report — provisional research manuscript\n\n"+prefix+source+
        "## Abstract\n\nWe evaluated berth-only FCFS, authentic online Rollout and three frozen PPO checkpoints alongside nominal/integrated greedy rules "
        "and model-based integrated rollout in an uncalibrated synthetic terminal. Step7 contains1960 completed episodes over140 traffic scenarios. "
        "Primary test inference uses50 independent scenarios in each Medium/Heavy family; validation remains separate. "
        "Cargo-first B2 reduces mean turnaround and unloaded obligations versus nominal A2, with stronger Heavy effects. "
        "Frozen PPO improves mean time versus FCFS but exhibits cargo deterioration, especially Heavy, and remains slower than A2. "
        "Formal primary confirmation and project closure remain blocked by canonical return verification, unspecified primary Holm construction and missing source-consistent13M diagnostics.\n\n"
        "## Problem, architecture and frozen design\n\nS1 measures transfer of policy-relative performance from authentic P03 nominal BAP projections into "
        "the integrated terminal. S2 asks whether coordinated berth decisions improve outcomes in identical terminal physics. "
        "The event-driven kernel shares quay cranes, transport capacity and a block-level yard. All primary arms use eight cranes, "
        "greedy crane allocation, common occupancy-balancing yard placement, assigned multi-crane efficiency, D15 batch10, D17 wait240 and R5 FIFO release. "
        "A2 uses unchanged P03 visible-cohort lookahead; A3 is unchanged deterministic CPU MaskablePPO with H240 and PASS-FORECAST occupancy substitution. "
        "B1 uses accepted integrated release estimates; B2/B2-T share an integrated forward evaluator. B2 ranks cargo first then time; B2-T ranks time only. "
        "All legal candidates plus WAIT are retained, no timeout or policy fallback. AM01–10 and actual owner28-value approval precede test generation.\n\n"
        "## Scenarios and inference\n\n20validation and50test scenarios per family;9 integrated arm/checkpoint identities and5 reference identities per scenario. "
        "Physics and exogenous fingerprints, Nout and Tend are paired across arms. Three training seeds are nested, not independent traffic units. "
        "D24 and outbound LOAD_COMPLETED metrics prevent departure/completion from substituting for cargo success. "
        "Methods and all confidence/NI results are in the accompanying statistical report; primary Holm ambiguity is disclosed, not repaired after seeing outcomes.\n\n"
        "## Test outcomes\n\n"+outcomes+"\n\nTA columns are simulated minutes. Pooled vessel median/P95 are descriptive; for A3 each vessel's outcomes are averaged across the three models first. "
        "Mean of scenario P95 waiting is explicitly distinct from pooled-vessel P95; both appear in CSV. No vessel is treated as an independent bootstrap scenario.\n\n"
        "## S1 and S2 findings\n\n"+findings+"\n\n"+ppo_qualification+s1table+"\n\n"+
        "## Objective ablation and operational diagnostics\n\nB2 versus B2-T isolates cargo priority within the matched evaluator. "
        "Medium has48/50 time ties; Heavy has a time/cargo tradeoff. This does not make the cargo-first rule universally superior. "
        "The different-method trajectories are not matched states after divergence.\n\n"+costtable+"\n\n"+forecasttable+
        "\n\n## Required sensitivity coverage\n\n"+plan_table+"\n\n## Limitations and failure modes\n\n"+limitations+
        "\n\n## Interpretation and future research\n\nThe narrower supported pattern is that terminal-aware, cargo-first berth coordination can improve synthetic outcomes; "
        "the existing frozen berth PPO does not establish cargo-preserving terminal-wide optimization. There are no three RL agents: crane and yard policies are fixed rules, "
        "and B2 is not RL. No real-terminal savings, universal optimality or field validity follows.\n\n"
        "Future studies should separately examine (1) integrated-physics retraining with berth-only information as a control, "
        "(2) integrated-aware PPO with crane/yard/cargo observations under matched training/objectives, "
        "(3) new crane/yard decision control as a distinct extension, and (4) empirical calibration and prospective port trials. "
        "None was run or authorized as a hidden Step8 rescue. Yard RL performance cannot be inferred from this berth PPO experiment.\n\n"
        "## Reproducibility and closure\n\nAll arrays/tables/figures bind to original manifest, source, lock and analysis hashes. "
        "No original episode was repeated, no model/physics/policy changed, and no automatic commit occurred. "
        "The release manifest binds this manuscript and figures. See the closure note for exact remaining gates.\n")
    figure_names=("01_primary_outcome_table", "02_paired_time_effects", "03_cargo_noninferiority",
                  "04_time_cargo_tradeoff", "05_ppo_all_seeds", "06_wait_and_forecast",
                  "07_compute_cost", "08_cargo_first_objective_ablation")
    available=[name for name in figure_names if (output/"figures"/(name+".png")).exists()]
    report += "\n## Supporting figures\n\n"+"\n\n".join(
        f"![{name.replace('_',' ')}](../../../experiments/step8_analysis/{output.name}/figures/{name}.png)"
        for name in available)+"\n"
    methods += ("\nSign agreement and per-scenario Kendall tau-b use the inherited1e-6 vessel-minute tie convention. "
                "For rankings, sorted complete-link clusters spanning at most1e-6 receive average ranks. "
                "Eight Medium reference A3 contrasts differed from zero only by floating-point noise (about1e-12); treating them as genuine wins/losses "
                "would change sign agreement from0.24 to0.36. The analysis correctly treats these as ties; time/CARGO-NI estimates do not change.\n")
    audit += ("\nAnalysis reporter check: floating-point near-ties in eight Medium A3 reference contrasts are normalized only for sign/ranking descriptions "
              "using the inherited tie tolerance. No outcome, objective or bootstrap sample was changed. Exact Step8 source bytes are exported under source_snapshot/.\n")
    executive=("# Project I executive research summary\n\n"+prefix+source+
        "This study tests whether berth scheduling benefits from forecasting shared cranes, yard and cargo constraints. "
        "It is a controlled synthetic research result, not a calibrated commercial digital twin. The completed campaign contains1960 episodes, "
        "with50 independent test scenarios in each primary traffic family and three preselected PPO models averaged within each scenario.\n\n"
        "**Integrated coordination is promising, particularly under Heavy traffic.**\n\n"+
        "\n\n".join(claim(f,"B2-A2") for f in families[:2])+
        "\n\nThese main-comparison intervals are raw95% previews; the required primary Holm construction was not specified by the frozen source. "
        "No final adjusted superiority claim is issued. B2 also improves cargo counts against A2, but time worsens in18/50 Medium and6/50 Heavy scenarios.\n\n"
        "**The frozen PPO is fast; joint success depends on traffic family and the approved cargo margin.**\n\n"+
        "\n\n".join(claim(f,"A3-A1") for f in families[:2])+
        "\n\n"+ppo_qualification+"PPO is slower than A2 on mean turnaround; all three checkpoint results are retained. Its CPU inference is about3.7ms/decision, "
        "whereas B2 Heavy averages8.258s/decision (P9526.136s, maximum69.540s). Computational feasibility depends on a real operational deadline that this study does not certify.\n\n"
        "**Cargo priority is a real design tradeoff.** B2 versus B2-T reduces Heavy mean unloaded obligations45.12 to0.48, "
        "while mean paired time rises about0.467%; Medium has48/50 time ties. Extra operational information alone does not guarantee improvement: "
        "Heavy B1 has worse mean cargo and time than FCFS. WAIT and forecast diagnostics identify limitations but do not prove a causal explanation.\n\n"
        "**What may be claimed:** coordinated berth decisions that account for terminal dynamics show useful conditional benefits in these synthetic families. "
        "**What may not be claimed:** three problems jointly optimized by RL; successful Yard RL; real-terminal ROI; universal efficiency gains. "
        "PPO controls berths only; shared crane and yard primitives remain fixed, and B2 is model-based.\n\n"
        "**Release decision:** Project I remains open. Finish official canonical archive verification, resolve the missing primary interval construction prospectively, "
        "and implement/execute the source-consistent required diagnostic campaign before final closure. Positive results cannot waive these gates.\n\n"
        "**Türkçe kısa özet:** Entegre, yük öncelikli B2 yaklaşımı özellikle Heavy koşulunda daha iyi ortalama süre/yük sonuçları veriyor. "
        "Bu başarı RL'ye atfedilemez: B2 RL değildir. Mevcut PPO hızlıdır; FCFS'ye göre süreyi azaltırken özellikle Heavy'de yük başarısını koruyamıyor. "
        "Medium'da kabul edilen1yüzde puanlık yük marjı geçiliyor; bu, hiç yük kaybı artışı olmadığı anlamına gelmez. "
        "Yard RL henüz sınanmadı. Resmî arşiv doğrulaması ve zorunlu analiz/duyarlılık kapıları tamamlanmadan proje bilimsel olarak kapatılamaz.\n")
    close_note=("# Project I scientific closure\n\n"+prefix+source+"```json\n"+json.dumps(state,indent=2)+"\n```\n\n"
        "- [x] Existing Step7 campaign completed1960/1960; no rerun.\n"
        "- [x] Source413paths, authentic checkpoints, approvals, parameters and seven restored references preserved.\n"
        "- [x] Read-only scenario pairing, D24/cargo summaries and review reconciliation computed.\n"
        "- [x] Prespecified10k time bootstrap and cargo upper-bound tests calculated provisionally; all checkpoints reported.\n"
        "- [x] Existing matched B2/B2-T objective ablation analysed; eight figure families prepared.\n"
        "- [ ] Official full canonical VerifyReturn PASS.\n"
        "- [ ] Scientifically specified primary Holm CI construction (cannot silently choose after observing results).\n"
        "- [ ] Source-consistent model-only coupling adapter/matrix/scoped equivalence and complete required13M diagnostics.\n"
        "- [ ] Final source-bound verified inference/release.\n\n"
        "A negative result would not prevent closure if these gates passed. Missing required evidence does prevent closure. "
        "No reapproval of unchanged28-values, administrative HEAD change or routine execution is being requested. "
        "The unresolved items are substantive scientific/source contracts. No working full-campaign command is invented.\n\n"+commands)
    payloads={"step8_source_and_evidence_audit.md":audit,
              "step8_statistical_analysis_protocol_and_results.md":methods,
              "step8_ablations_and_sensitivity.md":ablations,
              "step8_failure_modes_and_limitations.md":failure,
              "project_i_final_scientific_report.md":report,
              "project_i_executive_results_summary.md":executive,
              "project_i_scientific_closure.md":close_note}
    inventory={}
    for name,text in payloads.items():
        p=target/name
        publish_bytes(p,text.encode("utf-8"))
        # Export exact documentation alongside ignored immutable numerical release.
        publish_bytes(output/"documents"/name,text.encode("utf-8"))
        inventory[p.relative_to(REPO).as_posix()]=sha(p)
    return inventory
