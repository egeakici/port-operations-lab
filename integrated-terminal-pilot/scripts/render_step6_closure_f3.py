"""Render the verified F3 machine report into one immutable owner-review report."""
import argparse
import json
import os
from pathlib import Path
import uuid

from integrated_terminal_pilot.scenarios.config import PROJECT_ROOT


def publish_text(path, text):
    payload = text.encode('utf-8')
    if path.exists():
        assert path.read_bytes() == payload, 'Refuse to overwrite an earlier report'
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with open(temp, 'xb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def render(report, machine_path):
    s = report['summary']
    def f(value):
        return 'N/A' if value is None else f'{value:,.3f}'
    lines = ['# Project I — Step 6 Closure consolidated owner report', '',
        f"**DEVELOPMENT_ONLY — {s['status']}: {s['completed']}/12 F3 runs.**",
        f"Post-run diagnostic status: **{report['diagnostic_status']}**; additional WAIT reconstructions "
        f"not admitted after compute allowance: {report['wait_reconstructions_not_run_budget']}.",
        'All predictions: `UNCALIBRATED_SYNTHETIC_FORECAST`. No winner or primary CARGO-NI inference.', '',
        '## 1. Revision and preservation', '',
        'Phase A began/ended at `76ced62b94e5419fea98933b3cb17debf1bd8a62`. The owner then committed '
        'Phase A as `dac52fd` and `38a4f5c`. F3 used `' + report['git_head'] + '`. No agent commit or staging.', '',
        'All 137 approved source/config hashes, authentic P03 A2, frozen B policies, checkpoints, '
        'QC8 Balanced Yard physics and original historical artifacts are preserved. New work consists '
        'of approval provenance, reporter-only diagnostics and documentation. Projects 01–03 were not modified.', '',
        f"Machine evidence: `{machine_path.relative_to(PROJECT_ROOT)}`. It links every run and per-decision diagnostic hash.", '',
        '## 2. Owner decisions and authority', '',
        'Q6-1 B1 v1 estimator, Q6-2 omission of future landside requests, Q6-3 K5-A uncapped full cohort '
        'and Q6-4 cohort/horizon/censoring/FCFS/WAIT semantics are explicitly **APPROVED**. K5-A preserves '
        'every legal candidate and WAIT. Protocol section 5’s proposed 2-second reduction trigger is '
        'superseded by a compute warning for Step 6/Step 7 research (AM-10); no Step 7 start is authorized.', '',
        f"Approval: `{report['approval_file']}`; canonical SHA `{report['approval_sha256']}`. "
        f"Exact message: `{report['exact_owner_message']}`. The owner explicitly approved the replacement plan; "
        'earlier approval/history records remain unchanged. The small line-break normalization in the initial '
        'JSON is documented by an append-only exact-message provenance artifact.', '',
        '## 3. Independent contract gate', '',
        '**PASS_SCOPED:** 12 FULL fixtures, 20 eligible decisions, 0 PREFIX, 5 noneligible controls, '
        '0 demonstrated contract defects. For uncensored fixed-service branches, integrated turnaround '
        'equals authentic future queue waiting plus a candidate-independent constant. Candidate orders, '
        'ties and WAIT branches match under that predicate. Rate/distance dependence, cargo delays and '
        'censoring are preserved negative findings; no universal equivalence is claimed.', '',
        f"Reviewed gate SHA `{report['degenerate_gate_sha256']}`. Phase A was not repeated.", '',
        '## 4. Algorithms and observation integrity', '',
        'No policy score, tie, continuation, physics, cohort cap, tolerance or checkpoint changed. '
        'The Phase A optional sanitized observation capture is unchanged. All new future-event analysis '
        'is confined to the post-run reporter. The reporter reconstructs WAIT subbranches from archived '
        'inputs; it never supplies those reconstructions or realized outcomes to a policy.', '',
        '## 5. Compute costs and resource envelope', '',
        'One worker; 180-minute cumulative admission allowance; 4096 MiB process-RSS admission check. '
        'Healthy episodes are allowed to finish; no inner candidate is truncated for wall time.', '',
        f"Episode wall sum: **{f(s['completed_episode_wall_seconds']/60)} min**; CPU sum: "
        f"{f(s['cpu_seconds']/60)} min. Max episode-boundary RSS: {f(s['max_episode_boundary_rss_mb'])} MiB; "
        f"max telemetry sample: {f(report['progress_and_budget']['max_sampled_rss_mb'])} MiB. "
        'These are sampled values, not a peak-memory claim. JSON/reporting overhead and post-run reconstruction '
        'are separated from policy/evaluator timings. Full admission checkpoints are in the machine report.', '',
        f"Campaign elapsed at the last recorded checkpoint: "
        f"{f((report['progress_and_budget']['last_checkpoint'] or {}).get('wall_seconds_this_invocation', 0)/60)} min. "
        f"Reporter analysis: {f(report.get('reporter_wall_seconds'))} s. Episode sums exclude final result "
        'serialization/checksum overhead; the campaign admission clock includes it.', '',
        'Historical A2 maxima 10.28 s and 1.86 s use different sampling frames and trajectories. '
        'The Phase A matched-state probe was repeatable but did not reconstruct the missing slowest historical '
        'state. The sparse maximum is not a global A2 bound. Projection build is outside B evaluator timing.', '',
        '| Family / arm | Decisions | WAIT | Policy p50 s | p95 s | Max s | >2 s |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for key, row in report['distributions'].items():
        p = row['policy_seconds']
        lines.append(f"| {key} | {row['decisions']} | {row['waits']} | {f(p.get('p50'))} | {f(p.get('p95'))} | {f(p.get('max'))} | {row['two_second_warnings']} |")
    lines += ['', 'Percentiles use numpy linear interpolation; historical runner quantiles remain labelled separately.', '',
        '## 6. F3 coverage and plan', '', f"Plan SHA: `{report['plan_sha256']}`.", '',
        '| Family | Seed | Arm | Turnaround min | N_out | Loaded | U | D17 rolled | Wall s |',
        '| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for row in report['runs']:
        i, m = row['item'], row['cargo']['metric']
        lines.append(f"| {i['family']} | {i['seed']} | {i['arm']} | {f(row['outcome']['total_turnaround_min'])} | {m['N_out']} | {m['loaded']} | {m['U_not_loaded']} | {m['classes']['NOT_LOADED_ROLLED_OVER']} | {f(row['compute']['wall_seconds'])} |")
    if report['missing_items']:
        lines += ['', '**Remaining, not executed:**'] + [f"- {i['family']} / {i['seed']} / {i['arm']}" for i in report['missing_items']]
    if report['failed_items']:
        lines += ['', '**Failed attempts retained; no automatic rerun:**'] + [str(i) for i in report['failed_items']]
    lines += ['', '### Preserved historical context (not fresh F3 runs)', '',
        '| Scenario | Historical arm | Turnaround min | U containers |',
        '| --- | --- | ---: | ---: |']
    context = report['historical_context']
    for row in context['records']:
        if row['status'] == 'VERIFIED_HISTORICAL_CONTEXT' and not row['arm'].startswith('A3-'):
            lines.append(f"| {row['scenario_id']} | {row['arm']} | {f(row['total_turnaround_min'])} | {row['cargo']['U_not_loaded']} |")
    for row in context['a3_within_scenario_means']:
        lines.append(f"| {row['scenario_id']} | A3 mean of train 11/23/37 | {f(row['mean_turnaround_min'])} | {f(row['mean_U_containers'])} |")
    lines += ['', 'Historical context is admitted only after fingerprint, profile/cutoff/denominator, status/audit '
        'and policy-identity checks. Every original file hash and Git/package provenance is retained. '
        'Missing, blocked or mismatched context is rejected, not repaired. A3 training seeds are averaged '
        'within a scenario only when all three exist and verify. Context is neither a new F3 run nor '
        'independent traffic replication.', '',
        'No completed outer episode was duplicated or silently retried. Safe resume verifies stored hashes '
        'and pairing metadata; incomplete attempts/worker locks require inspection. A budget stop requires further '
        'resource authorization before additional admission; no cap or fallback substitutes for it.', '',
        '## 7. WAIT, pivotal cargo, rollover and forecast diagnostics', '',
        f"Integrated decisions: {s['integrated_decisions']}; unique canonical integrated inputs: {s['unique_integrated_inputs']}; "
        f"inputs with any predicted cargo variation: {s['cargo_difference_unique_inputs']}; cargo-pivotal inputs: "
        f"{s['cargo_pivotal_unique_inputs']}; one-container pivotal inputs: {s['one_container_pivotal_unique_inputs']}.", '',
        report['cargo_pivotal_interpretation'], '',
        f"Maximum observed predicted turnaround sacrifice among pivotal inputs: "
        f"{f(s['max_pivotal_predicted_turnaround_sacrifice_min'])} min. The preserved pure-selector test "
        'documents that one container can override an 8,000-minute predicted cost; observed frequencies '
        'and tradeoffs above are kept separate from that permitted design property.', '',
        'Both selectors are compared on exactly the same stored candidate predictions at each state. '
        'Actual subsequent outcomes belong to the executed outer trajectory, not an unobserved counterfactual. '
        'Full per-decision cohort, legal actions, resources, selected branches, horizon/censoring and realized '
        'same-cohort outcomes are retained. A2 future queue scores and errors are separate from B turnaround '
        'forecasts; A2 does not predict cargo. P03’s scalar-return WAIT implementation does not retain a unique '
        'subbranch identity on ties, so the reporter records all tied minima.', '',
        '| Integrated family / arm | Mean TA error | Median | P95 | Mean absolute | Mean known-cargo U error |',
        '| --- | ---: | ---: | ---: | ---: | ---: |']
    for key, row in report['distributions'].items():
        if key.endswith('/A2'):
            continue
        e = row['forecast_turnaround_errors']
        lines.append(f"| {key} | {f(e.get('mean'))} | {f(e.get('p50'))} | {f(e.get('p95'))} | {f(e.get('mean_absolute'))} | {f(row['forecast_known_cargo_errors'].get('mean'))} |")
    lines += ['', 'Signed error = predicted minus realized outcome for the same cohort at the common inner horizon. '
        'Known forecast obligations and full-cohort obligations have separate denominators and explicit equality '
        'flags. No calibration or posterior forecast correction was applied.', '', '### WAIT illustrations', '',
        'Four preserved historical Medium B2 autopsies (not F3):', '',
        '| Decision | Time min | WAIT to next actual decision min | Branches | TA prediction error min |',
        '| --- | ---: | ---: | ---: | ---: |',
        '| 10 | 1825.155 | 42.588 | 6 | -865.857 |',
        '| 11 | 1867.744 | 64.069 | 6 | -143.334 |',
        '| 14 | 2653.502 | 171.061 | 14 | +32.840 |',
        '| 16 | 2824.564 | 263.016 | 8 | -92.969 |', '',
        'Only decision 10 precedes V016’s announcement. Errors persist without later hidden entrants in '
        'the other three cases; hidden arrivals cannot uniquely explain the historical Medium gap. '
        'These are preserved source-record autopsies, not newly executed Medium episodes.', '',
        'One additional F3 illustration is selected descriptively by largest absolute integrated TA error '
        'among the retained examples. All F3 WAITs remain available in per-decision diagnostics:', '']
    integrated_examples = [d for d in report['wait_autopsies'] if 'predicted_minus_actual_turnaround' in d]
    examples = [max(integrated_examples, key=lambda d: abs(d['predicted_minus_actual_turnaround']))] if integrated_examples else []
    for d in examples:
        w = d['wait_actual']
        lines.append(f"- {d['family']} / {d['seed']} / {d['arm']}, decision {d['ordinal']} at t={f(d['time_min'])}: "
            f"WAIT elapsed {f(w['elapsed_min_to_next_decision_or_stop'])} min; departures {w['departures_in_interval']}; "
            f"new announcements {w['new_announcements_in_interval']}; TA error {f(d.get('predicted_minus_actual_turnaround'))}.")
    lines += ['', 'These time windows do not establish a causal WAIT benefit or loss. The four historical Medium '
        'autopsies and Low/Medium forecast errors remain preserved in `docs/step6_closure_diagnostics.md`. '
        'No new F3 result proves a WAIT-only explanation of the historical Medium gap.', '', '### Cargo evidence', '']
    for row in report['runs']:
        if row['cargo']['metric']['U_not_loaded']:
            lines.append(f"- {row['item']['family']} / {row['item']['seed']} / {row['item']['arm']}: "
                f"overlapping tags {row['cargo']['evidence_tag_counts_overlapping']}; "
                f"D17 status counts {row['cargo']['rollover_by_status']}.")
    lines += ['', 'N_out=loaded+U, ledger/final-status and per-vessel move reconciliations pass. Each D17 loss '
        'links to a timeout event and exact container status, source connection, eventual yard-ready time and '
        'overlapping WAIT windows. Evidence tags can overlap; upstream primary attribution remains '
        '`UNKNOWN_OR_MULTIPLE_CONSTRAINTS`. Departure never substitutes for LOAD_COMPLETED. Loaded-but-not-departed, '
        'vessel-present incomplete obligations and unfinished moves are reported separately by run/flow/vessel.', '',
        '## 8. Pairing, hidden-future boundary and determinism', '',
        'Common scenario/exogenous/physical fingerprints, QC8, max two cranes/vessel, assigned efficiency, '
        'D15/D17/R5, T_end and N_out verify across arms. Run hashes and original ledger/event/blocking digests '
        'are independently checked. Actual archived integrated inputs are checked for redacted identity, '
        'absent hidden vessel catalog entries and future gate/pickup events, normalized event sequences, '
        'and absent ledger/event logs.', '',
        f"Matched integrated canonical inputs with identical candidate predictions: {s['matched_integrated_decisions']}. "
        'Canonical input bytes exclude projection construction wall time; the report separately records whether '
        'raw pickle bytes match. Whole episodes are not claimed to share states after divergence. Matched A2/B2-T '
        'observed contexts still have model/objective differences. Existing Phase A determinism/full-summary '
        'parity tests are preserved; no completed outer episode was repeated. New F3 probes use fixed '
        'B2-T ordinals 1 and 5 per scenario on the exact archived inputs; private event logging measures '
        'processed-event counts while requiring every candidate prediction byte to reproduce.', '',
        f"New F3 determinism probes passed: {report['new_f3_determinism_probes']['executed']}/"
        f"{report['new_f3_determinism_probes']['planned']}. These are inner-input diagnostics, not additional outer runs.", '',
        '## 9. Regression evidence', '',
        'Phase A retained: Project I fast 472 passed / 9 deselected; final focused 47 passed. The original '
        'opt-in command lost its summary to pytest WinError 5 cleanup; exact progress reconstruction records '
        '443 passes / 19 errors / 0 failures / 0 skips. A clean retry covers all affected non-slow nodes. '
        'All nine slow tests passed, including 80/80 Step 4 and 400/400 Step 5. Historical scope counts are '
        '383 FULL / 17 PREFIX; the existing pytest wrapper did not retain new scope counters. This is not '
        'mislabelled as one clean full-suite command.', '',
        'Projects 01/02: 426/55 passed; selected Project 03 suite: 423 passed, 5 deselected. Training and '
        'historical-results/benchmark integration exclusions are documented in Phase A. No old tests were '
        'repeated. New reporter arithmetic tests: 5 passed in 0.27 s; a separate same-timestamp '
        'causal-sequence test also passed. A reporter-only timestamp field mismatch '
        'was repaired by deriving actual times from authoritative assignment records and departure events; '
        'real-record shape/integrity checks then passed. No policy or result was altered.', '',
        '## 10. Status and remaining scientific blockers', '', '```text',
        f"STEP6_CLOSURE_F3          = {s['status']} ({s['completed']}/12)",
        'OWNER_Q6_DECISIONS        = APPROVED', 'K5_FIXED_BUDGET           = APPROVED_FULL_COHORT',
        'DEGENERATE_GATE           = PASS_SCOPED', 'PENDING_PARAMETER_RECORDS = 28',
        'SCIENTIFIC_PROTOCOL_LOCK  = BLOCKED', 'VALIDATION_AUTHORIZED     = NO', 'STEP7_STARTED            = NO', '```', '',
        'Remaining scientific blockers: 28 pending synthetic parameter records and a separate formal Step 7 '
        'lock procedure; uncalibrated/omitted landside forecasts; conditional model/horizon comparability; '
        'n=2 scenarios/family; incomplete causal attribution of WAIT and cargo losses; the missing historical '
        'slowest A2 state; sampled memory rather than peak RSS; and frozen PPO forecast-substitution '
        'domain shift / unestablished equality with the original GPU training runtime. Negative/null/mixed findings are preserved. '
        'No winner, S2 success, primary CARGO-NI conclusion or validation readiness is declared.', '',
        '## 11. Owner review', '',
        'Review this consolidated Step 6 Closure report. Completion of this development characterization '
        'does not approve parameters, create the scientific lock, authorize held-out use, retrain PPO or start Step 7.', '']
    return '\n'.join(lines)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    args = parser.parse_args()
    args.report = args.report.resolve()
    report = json.loads(args.report.read_text(encoding='utf-8'))
    text = render(report, args.report)
    publish_text(args.report.with_suffix('.md'), text)
    publish_text(PROJECT_ROOT / 'docs/step6_closure_final_report.md', text)
    print(PROJECT_ROOT / 'docs/step6_closure_final_report.md')
