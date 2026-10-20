"""Consolidated portable evidence, without statistical inference or policy evaluation."""
from collections import defaultdict
from pathlib import Path
import statistics

from integrated_terminal_pilot.benchmark import step7 as s
from integrated_terminal_pilot.benchmark.step7_inputs import safe_path


def write_text(path, text):
    if path.exists():
        if path.read_text(encoding='utf-8') != text:
            raise s.CampaignError('immutable consolidated report collision')
    else:
        with path.open('x', encoding='utf-8', newline='\n') as f:
            f.write(text)


def profile_summary(root):
    invocations=[];seen=set()
    for started in sorted((root/'profiles').glob('*/started.json')):
        start=s.unseal(started);directory=started.parent
        path=directory/'result.json'
        if not path.exists():
            invocations.append(dict(invocation=directory.relative_to(root).as_posix(),split=start['split'],
                status='PROFILE_UNAVAILABLE',reason='interrupted or unsealed invocation; no event total inferred'))
            continue
        result=s.unseal(path)
        if s.file_hash(directory/'cpu.prof')!=result['profile_sha256']:
            raise s.CampaignError('profiling evidence corrupted')
        ids=set(result['newly_executed'])
        if ids & seen:raise s.CampaignError('duplicate profiled execution identities')
        seen.update(ids)
        invocations.append(dict(invocation=directory.relative_to(root).as_posix(),split=start['split'],
            status='PARTIAL_EVENT_PARTITION' if result['physical_inner_events'] is None else 'VERIFIED',**result))
    good=[r for r in invocations if r['status']=='VERIFIED']
    return dict(invocations=invocations,profiled_row_ids=sorted(seen),
        verified_physical_inner_events=sum(r['physical_inner_events'] for r in good),
        verified_physical_process_calls=sum(r['physical_process_calls'] for r in good),
        incomplete_profile_invocations=sum(r['status']!='VERIFIED' for r in invocations),
        scope='Available invocation totals; not per candidate. Missing profiles are not zero work. '
              'Physical kernel calls minus recorded new outer events; not inferred from cycle counts.')


def presentation(report):
    grouped=defaultdict(list)
    for p in report['paired_descriptive_contrasts']:
        if p['contrast']=='B2-A2':grouped[(p['split'],p['family'])].append(p)
    lines=['# Step 7 presentation evidence','','SYNTHETIC / UNCALIBRATED. Descriptive results only.',
        'Berth coordination with shared deterministic crane/yard policies; no real-terminal savings or joint optimum claim.',
        '', '| Split | Family | Paired scenarios | Mean B2-A2 TA (min) | Mean scenario TA change (%) | Mean U change | Mean R change |',
        '| --- | --- | ---: | ---: | ---: | ---: | ---: |']
    claims=[]
    for (split,family),rows in sorted(grouped.items()):
        ta=statistics.fmean(r['turnaround_delta_min'] for r in rows)
        u=statistics.fmean(r['U_delta'] for r in rows);loss=statistics.fmean(r['R_delta'] for r in rows)
        percentages=[r['turnaround_delta_percent'] for r in rows if r['turnaround_delta_percent'] is not None]
        percent=statistics.fmean(percentages) if percentages else None
        supported=('BOTH' if ta<0 and loss<0 else 'TURNAROUND_ONLY' if ta<0 else 'CARGO_ONLY' if loss<0 else 'NEITHER_STRICTLY_IMPROVES')
        lines.append(f'| {split} | {family} | {len(rows)} | {ta:.6f} | {percent} | {u:.6f} | {loss:.8f} |')
        claims.append(dict(split=split,family=family,paired_scenarios=len(rows),descriptive_direction=supported,
            mean_turnaround_delta_min=ta,mean_R_delta=loss,
            turnaround_improved_scenarios=sum(r['turnaround_delta_min']<0 for r in rows),
            turnaround_worsened_scenarios=sum(r['turnaround_delta_min']>0 for r in rows),
            cargo_improved_scenarios=sum(r['R_delta']<0 for r in rows),cargo_worsened_scenarios=sum(r['R_delta']>0 for r in rows)))
    lines+=['','Negative deltas favor B2. Percentages average paired scenario percentages with each A2 denominator; '
        'they are not a pooled real-world saving. U counts unloaded original outbound containers; R=U/N_out.',
        '', 'The full report contains absolute arm U/N_out/R, terminal end modes, per-vessel censoring, all other '
        'predeclared contrasts, the B2-T objective ablation and true Project03 reference context. '
        'PPO training seeds are averaged within traffic scenario only when all three complete.',
        '', 'Directional findings (no significance or noninferiority claim):']
    lines += [f'- {r["split"]}/{r["family"]}: {r["descriptive_direction"]}; '
              f'TA improved/worsened {r["turnaround_improved_scenarios"]}/{r["turnaround_worsened_scenarios"]}, '
              f'cargo improved/worsened {r["cargo_improved_scenarios"]}/{r["cargo_worsened_scenarios"]}.' for r in claims]
    lines+=['','Final S1/S2 inference, paired bootstrap and cargo noninferiority remain Step8. '
        'Low/Bottleneck were not promoted to primary. B3 is NOT_IMPLEMENTED.']
    return '\n'.join(lines)+'\n',claims


def finalize(root,plan_path,stages):
    from integrated_terminal_pilot.benchmark.checkpoints import verify_all_hashes
    lock=s.verify_lock(plan_path);plan=s.load_plan(plan_path)
    report=s.unseal(safe_path(root,stages['descriptive-report']['report']))
    diagnostics=s.unseal(safe_path(root,stages['detailed-diagnostics']['report']))
    evidence=s.verify_regressions(s.PROJECT_ROOT/lock['regression_evidence'])
    checkpoints=verify_all_hashes()
    if checkpoints!=lock['checkpoints']:raise s.CampaignError('final checkpoint drift')
    coverage=s.progress(plan_path,authorized=True)
    if coverage['status']!='COMPLETE':raise s.CampaignError('final summary requires complete coverage')
    completed=[r for r in report['rows'] if r['status']=='COMPLETED' and r['world']=='integrated']
    if len(diagnostics['rows'])!=len(completed) or any(r['cargo_audit']!='PASS' for r in diagnostics['rows']):
        raise s.CampaignError('diagnostics do not cover every completed integrated episode')
    profiles=profile_summary(root)
    compute=dict(outer_episode_wall_seconds=sum(r['wall_seconds'] for r in report['rows']),
        outer_episode_cpu_seconds=sum(r['cpu_seconds'] for r in report['rows']),
        diagnostic_reconstruction_wall_seconds=sum(r['reporter_wall_seconds'] for r in diagnostics['rows']),
        diagnostic_reconstruction_cpu_seconds=sum(r['reporter_cpu_seconds'] for r in diagnostics['rows']),
        max_sampled_rss_bytes=max((r['compute']['max_sampled_rss_bytes'] for r in diagnostics['rows']),default=None),
        two_second_compute_warnings=sum(r['compute']['two_second_warnings'] for r in diagnostics['rows']),
        stage_wall_seconds={k:s.unseal(root/'pipeline/stages'/(k+'.json'))['wall_seconds'] for k in stages},
        rss_limit='Boundary/15-second samples are not continuous peak; profile and reporter overhead are explicit',
        profiles=profiles)
    s.seal(root/'compute_summary.json',compute)
    text,claims=presentation(report);write_text(root/'presentation_evidence.md',text)
    summary=dict(
        ACTUAL_HEAD_AND_SOURCE_DIGESTS=dict(head=lock['source_revision'],source_sha256=lock['source_sha256'],
                                          implementation_digest=evidence['implementation_digest']),
        STEP6_F3_REFERENCE='VERIFIED_DEVELOPMENT_ONLY_TRANSPORTED_RECEIPT_SCOPE',
        OWNER_28_SYNTHETIC_RECORDS=dict(status='APPROVED_WITH_PROVENANCE',count=28,sha256=lock['owner_approval_sha256']),
        CLEAN_REGRESSION_PROJECT_I=evidence['project_i_full'],
        PROJECT03_ELIGIBLE_FAST_REGRESSION=evidence['project03_eligible_fast'],
        STEP7_LOCK=dict(status='VERIFIED_LOCKED',sha256=s.file_hash(s.FORMAL_LOCK_PATH)),
        VALIDATION_AUTHORIZATION='SOURCE_AUTHORIZED',
        EXPERIMENT_PLAN=dict(canonical_sha256=s.digest(plan),scenarios=140,episodes=1960,
            integrated_episodes=1260,reference_episodes=700,scenario_counts_per_family=plan['scenario_counts_per_family']),
        CAMPAIGN_COVERAGE=coverage['counts'],EXOGENOUS_FINGERPRINT_PAIRING=report['pairing_audit'],
        PPO_CHECKPOINT_HASHES=dict(status='UNCHANGED',before=lock['checkpoints'],after=checkpoints),
        CARGO_LEDGER_AUDITS=dict(status='PASS',completed_integrated_episodes=len(completed)),
        STEP7_SCIENTIFIC_STATUS='CAMPAIGN_EXECUTION_COMPLETE_PENDING_RETURN_AUDIT',
        S1_S2_INFERENCE='DEFERRED_TO_STEP8',PRESENTATION_EVIDENCE='presentation_evidence.md',
        STEP8_STARTED='NO',REPRODUCTION_COMMAND='powershell -NoProfile -ExecutionPolicy Bypass -File .\\integrated-terminal-pilot\\scripts\\Start-Step7Remote.ps1',
        artifacts=dict(descriptive=stages['descriptive-report'],diagnostics=stages['detailed-diagnostics'],compute='compute_summary.json'),
        descriptive_hypothesis_directions=claims,
        warnings=['Synthetic values lack real-terminal calibration; cargo and turnaround must be assessed together.',
            'Q6 future landside requests omitted; UNCALIBRATED_SYNTHETIC_FORECAST.',
            'A3 integrated control is distribution-shifted frozen PPO; no new training.',
            'WAIT coexistence does not establish causality; pivotal counts are per decision/trajectory.',
            'Missing invocation profiles remain explicit; no inferred zero work or guaranteed ETA.',
            'Transfer manifest and independent return audit are required before owner closure.'])
    s.seal(root/'final_summary.json',summary)
    return summary
