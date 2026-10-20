"""Development-only readiness evidence and one exact 28-value owner packet."""
from __future__ import annotations
import json
import os
import re
from pathlib import Path
import statistics

from integrated_terminal_pilot.benchmark import step7 as s

F3 = s.PROJECT_ROOT / 'experiments/step6_closure/6401af0e2a01'
F3_SHA = 'b745793420a7f48db7a9ebec1100ee7e1a401e24811451c1021b3ae8f1a5a9b9'
GATE_SHA = '7cb84b87c78f3b2a6628a59ce4a2013b90ba8d66c347230eab24d6095f18c5c2'


def packet():
    value = {'schema': 'step7_owner_28_packet_v1', 'status': 'PENDING_EXPLICIT_OWNER_APPROVAL',
             'rows': s.value_rows(), 'scope': 'UNCALIBRATED_SYNTHETIC_V1_MEDIUM_HEAVY_PRIMARY_LOW_BOTTLENECK_DIAGNOSTIC',
             'recommendation': 'retain all exact existing values; synthetic design, no empirical calibration',
             'analysis_review': 'retain protocol section10 bootstrap seed120001; counts20/50 per primary family; analysis contract frozen before results',
             'question': 'Do you explicitly approve all 28 listed current synthetic v1 values and their specified medium/heavy primary vs low/bottleneck diagnostic roles, including their lack of real-terminal calibration, for the Step 7 pre-validation scientific lock? If any row differs, state the replacement now.'}
    s.seal(s.PACKET, value)
    matrix = (s.PROJECT_ROOT / 'docs/pre_step6_synthetic_parameter_approval_matrix.md').read_text(encoding='utf-8')
    original = {re.search(r'S2-\d+', line)[0]: [x.strip() for x in line.split('|')[1:-1]]
                for line in matrix.splitlines() if re.match(r'\| \d+ \| S2-', line)}
    lines = ['# Step 7 single owner approval packet', '', '**All 28 values are still PENDING.**', '',
        f'Canonical packet SHA-256: `{s.digest(value)}`.', '',
        'Recommendation: retain these exact current values as a declared **SYNTHETIC, UNCALIBRATED V1**.',
        'This is a proposal, not approval or a claim that the values describe a real terminal.', '',
        'Exact YAML values and units below come from the live validated register; every covered config leaf matches.',
        'The 15 keep recommendations and 13 deliberate owner decisions are preserved from the prior matrix.', '',
        '| ID | Exact existing values by config path | Unit / source kind | Evidence / uncertainty | KPI impact and interdependence | Recommendation | Status |',
        '| --- | --- | --- | --- | --- | --- | --- |']
    for row in value['rows']:
        m = original[row['decision_id']]
        values = json.dumps(row['values_by_path'], sort_keys=True).replace('|','\\|')
        lines.append(f"| {row['decision_id']} | `{values}` | {row['unit']}; {row['source_kind']} | "
                     f"{m[5]}; {m[7]} | {m[4]} | {m[8]} | PENDING |")
    lines += ['', '## Thirteen consequential decisions', '',
        '- S2-010 / S2-011: 16/24 vessels and 190/120-minute interarrival means define terminal load and PPO support; congestion and N_out follow from those traffic draws.',
        '- S2-014 / S2-015: Medium/Heavy alone supply primary claims. Low/Bottleneck stay development diagnostics; favorable F3 cargo performance cannot promote a family.',
        '- S2-035 / S2-040: three block lines and 100/40/40/100-metre spacing create transfer distances and couple the shared balanced yard primitive to crane transport rate.',
        '- S2-050 / S2-051: 0.4–0.6 discharge share, 30% transshipment load share, 50% discharge limit and 720-minute connection shape outbound denominator and cargo dependencies. Arrival connection does not guarantee yard availability.',
        '- S2-060 / S2-079: lead/dwell/pickup bounds and 360-minute cutoff govern mandatory initial inventory, hidden landside requests, load availability and gate queues.',
        '- S2-073 / S2-074: transport speed/handover/units and yard congestion/sharing coefficients determine effective service; none is real-port calibrated.',
        '- S2-077: 10080-minute drain extension defines common T_end, D24 censoring and the cargo completion cutoff. Shorter turnaround cannot excuse missing outbound obligations.', '',
        'No value has been adjusted using F3. D15=10, D17=240, R5 and QC8 remain separately approved.',
        'Step 7 plan: 40 validation +100 test scenarios; 1260 integrated +700 berth-reference episodes.',
        'All checkpoint seeds are nested inside scenario; they are not extra traffic observations.',
        'The accompanying analysis contract retains the protocol’s existing seed120001 for turnaround bootstrap and AM-06 seed20261013 for cargo; final inference is Step8.', '',
        '## One owner decision', '', value['question'], '',
        'Suggested explicit response: “I approve all 28 exact values in the linked Step 7 packet as uncalibrated synthetic v1, with Medium/Heavy primary and Low/Bottleneck diagnostic roles, for the pre-validation scientific lock. Retain the accompanying source-defined counts and analysis contract.”', '',
        'If any value changes, supply the replacement and rationale before validation/test generation. No held-out outcomes have been read.']
    path = s.PROJECT_ROOT / 'docs/step7_owner_approval_packet.md'
    path.write_text('\n'.join(lines)+'\n', encoding='utf-8')
    return value


def audit():
    from integrated_terminal_pilot.benchmark.checkpoints import verify_all_hashes, all_checkpoints, static_checkpoint_gates
    from integrated_terminal_pilot.benchmark.development import source_audit
    from integrated_terminal_pilot.benchmark.profiles import approval_state
    plan6 = s.read_json(F3 / 'plan.json')
    report = s.read_json(F3 / 'reports/f3_b745793420a7.json')
    final = s.read_json(F3 / 'reports/final_review_manifest.json')
    if s.digest(report) != F3_SHA or final['machine_report_file_sha256'] != s.file_hash(F3/'reports/f3_b745793420a7.json'):
        raise s.CampaignError('F3 report integrity mismatch')
    if s.file_hash(s.PROJECT_ROOT / 'docs/step6_closure_final_report.md') != final['owner_report_file_sha256']:
        raise s.CampaignError('Step 6 owner report changed')
    preserved, exceptions = {}, {}
    register_key = 'integrated-terminal-pilot/configs/generator/itp_generator_v1_decisions.yaml'
    for p, sha in plan6['source_sha256'].items():
        preserved[p] = s.file_hash(s.REPO / p) == sha
        if not preserved[p]:
            if p != register_key:
                raise s.CampaignError(f'protected Step6 source changed: {p}')
            s.require_owner()  # only explicit 28 status/provenance changes can explain this difference
            old_text = s.subprocess.run(['git','show','e364b80:'+p], cwd=s.REPO, check=True,
                                        capture_output=True, encoding='utf-8').stdout
            import yaml
            old = yaml.safe_load(old_text)['records']
            current = list(s.load_generator_config().decisions)
            strip = lambda r: {k:v for k,v in r.items() if k not in ('status','approval')}
            if [strip(r) for r in old] != [strip(r) for r in current]:
                raise s.CampaignError('parameter content changed beyond authorized approval metadata')
            exceptions[p] = 'explicit 28 approval metadata only; values/source kind unchanged'
    gate_path = s.PROJECT_ROOT / 'experiments/step6_closure/gates' / (GATE_SHA+'.json')
    gate = s.read_json(gate_path)
    if s.digest(gate) != GATE_SHA or gate['contract_defects'] != 0:
        raise s.CampaignError('Step6 contract gate mismatch')
    owner6=s.read_json(s.PROJECT_ROOT/'configs/protocol/step6_closure_owner_approval.json')
    if s.digest(owner6)!='ef4dc4463d108c31e3013e6361388aabc89e7e5c7b94b9ffaef89bad01af9118':
        raise s.CampaignError('Q6 approval provenance changed')
    runs = []
    for path, meta in report['run_artifacts'].items():
        p = s.PROJECT_ROOT / path
        if s.file_hash(p) != meta['file_sha256']:
            raise s.CampaignError(f'F3 run changed: {path}')
        e = s.read_json(p)
        r = e['record']
        if r['status'] != 'COMPLETED' or not r['audits']['ok']:
            raise s.CampaignError('F3 baseline not complete/audited')
        runs.append({'file': path, 'sha256': meta['file_sha256'], 'family': r['scenario']['family'],
                     'seed': r['scenario']['scenario_seed'], 'arm': r['arm']['arm_id'],
                     'N_out': r['outbound_obligations']['N_out'], 'U': r['outbound_obligations']['U_not_loaded'],
                     'total_turnaround_min': r['kpi']['total_turnaround_min'],
                     'wall_seconds': e['wall_seconds'], 'bytes': p.stat().st_size,
                     'trace_sha256': r['digests']['trace_sha256']})
    if len(runs) != 12 or report['summary']['failed'] or report['summary']['missing']:
        raise s.CampaignError('F3 coverage mismatch')
    historical = {}
    for path in ('experiments/step4_equivalence/eq_20261013T213721Z/report.json',
                 'experiments/step5_development/exact_gate_20261013T224141Z/report.json'):
        p = s.PROJECT_ROOT / path
        data = s.read_json(p)
        historical[path] = {'file_sha256': s.file_hash(p), 'summary': data['summary']}
    checkpoints = verify_all_hashes()
    gates = [static_checkpoint_gates(r) for r in all_checkpoints()]
    sources = source_audit()
    if not checkpoints['ok'] or not all(g['pass'] for g in gates) or not sources['pass']:
        raise s.CampaignError('P03 source/checkpoint gate failed')
    out = {'version': 'itp_step7_readiness_v1', 'head': s.git('rev-parse','HEAD'),
           'tracked_status': s.git('status','--short'), 'source_sha256': s.source_manifest(),
           'step6_verified': True, 'F3_report_sha256': F3_SHA, 'F3_gate_sha256': GATE_SHA,
           'F3_plan_sha256': s.digest(plan6), 'F3_rows': runs, 'step6_preserved_hashes': preserved,
           'authorized_metadata_exceptions': exceptions, 'historical_gates': historical,
           'checkpoint_hashes': checkpoints, 'checkpoint_static_gates': gates, 'P03_source_audit': sources,
           'approval_state': approval_state(), 'sensitive_scenarios_generated_or_read': 0,
           'runtime': s.runtime(), 'packet_sha256': s.digest(s.unseal(s.PACKET))}
    path = s.ROOT / 'readiness' / (s.digest(out)+'.json')
    s.seal(path, out)
    # Stable reference to the latest audited input state; historical content-addressed audits survive.
    for target, value in ((s.ROOT/'readiness_manifest.json', out),):
        temp = target.with_name(target.name+'.tmp')
        temp.write_text(json.dumps(value,sort_keys=True,indent=2), encoding='utf-8')
        os.replace(temp,target)
        side = target.with_suffix('.json.sha256.json')
        side.write_text(json.dumps({'file_sha256':s.file_hash(target),'canonical_sha256':s.digest(value)}),encoding='utf-8')
    return {'status': 'LOCK_BLOCKED_OWNER_APPROVAL' if approval_state()['proposed_pending_review'] else 'READY_FOR_LOCK_REVIEW',
            'manifest': str(path), 'manifest_sha256': s.digest(out), 'step6_verified': True,
            'pending': approval_state()['proposed_pending_review'], 'F3_runs': 12}


def estimates():
    """Measured model, not a guarantee. Medium is not measured by the heavy/bottleneck F3."""
    report = s.read_json(F3 / 'reports/f3_b745793420a7.json')
    runs = []
    for path in report['run_artifacts']:
        e = s.read_json(s.PROJECT_ROOT / path)
        r = e['record']
        runs.append((r['scenario']['family'],r['arm']['arm_id'],e['wall_seconds'],(s.PROJECT_ROOT/path).stat().st_size))
    h = {a: [t for f,b,t,_ in runs if f=='itp_heavy' and a==b] for a in ('A2','B2','B2-T')}
    model = {'heavy_A2_B2_B2T_seconds_per_scenario': sum(statistics.mean(x) for x in h.values()),
             'heavy_observed_maxsum_seconds_per_scenario': sum(max(x) for x in h.values()),
             'heavy_observed_minsum_seconds_per_scenario': sum(min(x) for x in h.values()),
             'sample_size': 'two development Heavy scenarios per arm; not a general runtime bound',
             'other_arms_and_references': 'unmeasured in F3; must add real observed costs; never assumed free',
             'medium': 'unmeasured in F3; illustrative Heavy proxy only, not measured Medium estimate',
             'episode_total': 1960, 'integrated_total':1260,'reference_total':700,
             'no_admission_deadline': True,
             'memory': 'F3 maximum sampled729.203 MiB, boundary675.277 MiB; full compressed traces streamed; one worker; no peak guarantee',
             'disk': 'F3 raw observations and new streamed gzip traces have different layouts; report raw-byte scale proxy and measure gzip on development fixture; no guaranteed bound',
             'F3_raw_bytes_per_episode_min_max': [min(x[3] for x in runs),max(x[3] for x in runs)],
             'free_disk_bytes': __import__('shutil').disk_usage(s.PROJECT_ROOT).free}
    # 70 scenarios per primary family. Proxy only for the three measured integrated arms.
    model['140_scenario_three_arm_proxy_seconds'] = [140*sum(fn(x) for x in h.values())
                                                    for fn in (min,statistics.mean,max)]
    model['1260_integrated_F3_raw_layout_proxy_bytes'] = [1260*fn([x[3] for x in runs]) for fn in (min,max)]
    s.seal(s.ROOT / 'cost_model.json', model)
    return model


if __name__ == '__main__':
    packet()
    print(json.dumps(audit(),indent=2))
