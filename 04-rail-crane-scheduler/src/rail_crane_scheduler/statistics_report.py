"""Prespecified scenario-first, family-stratified inference from verified cells.

Bonferroni percentile intervals are approximate bootstrap intervals, not exact
finite-sample coverage guarantees. Failures are unconditional companion endpoints.
"""
from pathlib import Path
import statistics
import numpy as np
from .contracts import require, canonical, digest
from .progress import Progress
from .scenarios import write_new


def infer(rows, profile, directory=None):
    a=profile['analysis']; families=profile['randomness']['family_order']
    seeds=profile['training_config']['seeds']; refs=a['confirmatory_references']
    require(len(set(seeds))==len(seeds) and len(refs)==4,'INFERENCE_PLAN','analysis','four fixed comparisons required')
    by_scenario={}; seen=set(); statuses={}; counts={}
    for row in rows:
        key=(row['scenario_id'],row['policy_id'])
        require(key not in seen,'DUPLICATE_RESULT','analysis',str(key)); seen.add(key)
        require((row['valid_complete'] and type(row['makespan_min']) in (int,float) and np.isfinite(row['makespan_min'])) or
                (not row['valid_complete'] and row['makespan_min'] is None),'FAILED_MAKESPAN','row','failure objective must be null')
        by_scenario.setdefault(row['scenario_id'],{})[row['policy_id']]=row
        arm=row['policy_id']; statuses.setdefault(arm,{})[row['status']]=statuses.setdefault(arm,{}).get(row['status'],0)+1
        counts[arm]=counts.get(arm,0)+1
    expected_arms=set(refs)|{f'crane_ppo_seed_{s}' for s in seeds}|{'cpsat_finite_dispatch_v1'}
    family_groups={f:[] for f in families}
    for scenario,group in sorted(by_scenario.items()):
        require(set(group)==expected_arms,'RESULT_COVERAGE','analysis','every planned arm must be retained')
        family=next(iter(group.values()))['family']
        require(all(r['family']==family for r in group.values()) and family in family_groups,'PAIR_FAMILY','analysis','inconsistent family')
        family_groups[family].append(group)
    require(all(len(g)==profile['cohorts']['test']['count_per_family'] for g in family_groups.values()),'RESULT_COHORT','analysis','all submitted scenarios required')
    rng=np.random.default_rng(a['bootstrap_seed']); draws=a['draws']
    alpha=1-a['confidence']; adjusted_level=1-alpha/(2*len(refs))
    contrasts={}; support={}; failure_differences={}
    with Progress(draws*len(refs),'Stratified bootstrap',directory,unit='resample') as progress:
        for ref in refs:
            # Identical bootstrap index streams for all four comparisons.
            rng=np.random.default_rng(a['bootstrap_seed'])
            deltas={}; percentages={}; failures={}; support[ref]={}
            for family,groups in family_groups.items():
                d=[]; percentages[family]=[]; failures[family]=[]
                for group in groups:
                    ppo=[group[f'crane_ppo_seed_{s}'] for s in seeds]; base=group[ref]
                    failures[family].append(statistics.fmean(not r['valid_complete'] for r in ppo)-int(not base['valid_complete']))
                    if all(r['valid_complete'] for r in ppo) and all(group[r]['valid_complete'] for r in refs):
                        delta=statistics.fmean(r['makespan_min'] for r in ppo)-base['makespan_min']
                        d.append(delta)
                        require(base['makespan_min']>0,'PRIMARY_ZERO_WORK','analysis','nonempty primary tasks must have positive objective')
                        percentages[family].append(100*delta/base['makespan_min'])
                support[ref][family]=len(d); deltas[family]=np.asarray(d,dtype=np.float64)
                failures[family]=np.asarray(failures[family],dtype=np.float64)
            enough=all(n>=a['minimum_pairs_per_family'] for n in support[ref].values())
            samples=np.zeros(draws); failure_samples=np.zeros(draws)
            for start in range(0,draws,256):
                size=min(256,draws-start)
                for family in families:
                    # Identical physical-scenario unit, with seeds averaged
                    # inside each scenario; never pool seed episodes as traffic.
                    f=failures[family]; weight=profile['families'][family]['weight']
                    indices=rng.integers(0,len(f),size=(size,len(f)))
                    failure_samples[start:start+size]+=weight*f[indices].mean(axis=1)
                    if enough:
                        d=deltas[family]; ix=rng.integers(0,len(d),size=(size,len(d)))
                        samples[start:start+size]+=weight*d[ix].mean(axis=1)
                progress.advance(size,method=ref)
            quantiles=[(1-adjusted_level)/2,1-(1-adjusted_level)/2]
            flo,fhi=np.quantile(failure_samples,quantiles,method='linear')
            failure_differences[ref]={'mean':sum(profile['families'][f]['weight']*float(failures[f].mean()) for f in families),
                                     'ci_lower':float(flo),'ci_upper':float(fhi),'simultaneous_confidence':a['confidence']}
            if enough:
                lo,hi=np.quantile(samples,quantiles,method='linear')
                contrasts[ref]={'mean_delta_min':sum(profile['families'][f]['weight']*float(deltas[f].mean()) for f in families),
                    'ci_lower_min':float(lo),'ci_upper_min':float(hi),'per_contrast_confidence':adjusted_level,
                    'n_independent_scenarios':sum(support[ref].values()),'support_by_family':support[ref],
                    'mean_paired_percent':sum(profile['families'][f]['weight']*statistics.fmean(percentages[f]) for f in families),
                    'wins':sum(int(v<0) for d in deltas.values() for v in d),
                    'ties':sum(int(v==0) for d in deltas.values() for v in d),
                    'losses':sum(int(v>0) for d in deltas.values() for v in d),
                    'worst_delta_min':max(float(v) for d in deltas.values() for v in d)}
            else: contrasts[ref]={'status':'INSUFFICIENT_COMPLETE_PAIR_SUPPORT','support_by_family':support[ref]}
    primary=contrasts[a['primary_reference']]; failure=failure_differences[a['primary_reference']]
    improvement=primary.get('ci_upper_min',float('inf'))<0 and failure['ci_upper']<=0
    by_arm={}
    for arm in sorted(expected_arms):
        arm_rows=[r for r in rows if r['policy_id']==arm]
        eligible=[r for r in arm_rows if r['status']!='SKIPPED_NOT_ELIGIBLE']
        valid=[r for r in eligible if r['valid_complete']]
        latencies=[v for r in eligible for v in (r['metrics']['policy_latency_s'] if r.get('metrics') else
                   (r.get('failure_evidence') or {}).get('decision_latencies_s',[]))]
        by_arm[arm]={'submitted':len(arm_rows),'eligible':len(eligible),'skipped_not_eligible':len(arm_rows)-len(eligible),
                     'failures':len(eligible)-len(valid),'unconditional_failure_rate':(len(eligible)-len(valid))/len(eligible) if eligible else None,
                     'valid_makespan_mean_min':statistics.fmean(r['makespan_min'] for r in valid) if valid else None,
                     'latency_n':len(latencies),'latency_mean_s':statistics.fmean(latencies) if latencies else None,
                     'latency_p95_s':float(np.quantile(latencies,.95,method='inverted_cdf')) if latencies else None,
                     'latency_max_s':max(latencies) if latencies else None,'statuses':statuses[arm]}
        by_arm[arm]['by_family']={f:{'submitted':len([r for r in arm_rows if r['family']==f]),
                 'valid':sum(r['valid_complete'] for r in arm_rows if r['family']==f),
                 'failures':sum(not r['valid_complete'] and r['status']!='SKIPPED_NOT_ELIGIBLE' for r in arm_rows if r['family']==f)} for f in families}
        for family in families:
            values=[r['makespan_min'] for r in valid if r['family']==family]
            by_arm[arm]['by_family'][family].update(
                valid_mean_min=statistics.fmean(values) if values else None,
                valid_median_min=statistics.median(values) if values else None,
                valid_p95_min=float(np.quantile(values,.95,method='inverted_cdf')) if values else None)
        completion=[r['metrics']['completed_moves']/r['metrics']['original_moves'] for r in eligible if r.get('metrics') and r['metrics']['original_moves']>0]
        by_arm[arm]['mean_original_move_completion_fraction']=statistics.fmean(completion) if completion else None
        by_arm[arm]['physical_violation_count']=sum(len(r.get('validator_violations',[])) for r in eligible)
        for metric in ('utilization','idle_crane_min','travel_min','travel_m'):
            values=[r['metrics'][metric] for r in valid if r.get('metrics') and r['metrics'][metric] is not None]
            by_arm[arm][metric+'_mean']=statistics.fmean(values) if values else None
    return {'status':'PRESPECIFIED_ANALYSIS_COMPLETE','profile_sha256':digest(profile),'independent_unit':'physical_scenario',
            'ppo_seeds_nested':seeds,'draws':draws,'bootstrap_seed':a['bootstrap_seed'],
            'multiplicity':a['multiplicity'],'contrasts':contrasts,'failure_differences':failure_differences,'by_arm':by_arm,
            'primary_superiority_supported':improvement,'scientifically_closed':False,
            'qualification':'conditional complete-pair makespan plus unconditional failures; finite-sample bootstrap coverage approximate'}


def produce_report(campaign):
    from .evaluation import read_existing, certified_gap
    from .replay import png_bytes
    campaign.verify_results()
    rows=read_existing(campaign.work/'evaluation')
    out=campaign.work/'reports'/('report_'+digest({'profile':campaign.profile_hash,'evaluation':digest(rows)})[:16])
    require(not out.exists(),'OUTPUT_EXISTS','report','immutable report already exists')
    out.mkdir(parents=True)
    analysis=infer(rows,campaign.profile,out)
    cp=[]; by_scenario={}
    for row in rows: by_scenario.setdefault(row['scenario_id'],{})[row['policy_id']]=row
    for scenario,group in by_scenario.items():
        ref=group['cpsat_finite_dispatch_v1']
        if ref.get('solver_status')=='OPTIMAL' and ref['valid_complete']:
            for arm,row in group.items():
                if row['valid_complete'] and arm!='cpsat_finite_dispatch_v1':
                    cp.append({'scenario_id':scenario,'policy_id':arm,'finite_subclass_gap_min':certified_gap(row,ref)})
    write_new(out/'analysis.json',canonical(analysis)); write_new(out/'cp_certified_gaps.json',canonical(cp))
    import csv
    with (out/'cells.csv').open('x',newline='',encoding='utf-8') as stream:
        fields=['scenario_id','family','policy_id','training_seed','status','valid_complete','makespan_min','episode_wall_s','checkpoint_hash']
        writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore'); writer.writeheader(); writer.writerows(rows)
    from matplotlib.figure import Figure
    figure=Figure(figsize=(9,4)); ax=figure.subplots(); names=[]; means=[]; lows=[]; highs=[]
    for name,contrast in analysis['contrasts'].items():
        if 'mean_delta_min' in contrast:
            names.append(name); means.append(contrast['mean_delta_min']); lows.append(contrast['ci_lower_min']); highs.append(contrast['ci_upper_min'])
    for i,(mean,low,high) in enumerate(zip(means,lows,highs)):
        ax.hlines(i,low,high); ax.plot(mean,i,'o')
    ax.set_yticks(range(len(names)),names); ax.axvline(0,color='gray',linestyle='--')
    ax.set_xlabel('PPO seed mean minus comparator makespan (min)'); ax.set_title('Family-stratified paired intervals; Bonferroni four contrasts')
    figure.tight_layout(); write_new(out/'paired_effects.png',png_bytes(figure))
    failure_figure=Figure(figsize=(10,4)); f_ax=failure_figure.subplots()
    names=list(analysis['by_arm']); values=[analysis['by_arm'][n]['unconditional_failure_rate'] for n in names]
    f_ax.bar(range(len(names)),[v if v is not None else 0 for v in values]); f_ax.set_xticks(range(len(names)),names,rotation=35,ha='right')
    f_ax.set_ylabel('Failure rate among eligible submitted scenarios'); f_ax.set_ylim(0,1); failure_figure.tight_layout()
    write_new(out/'failure_rates.png',png_bytes(failure_figure))
    lines=['# Project 04 recorded scientific report','',f'Profile: `{campaign.profile_hash}`.',
           'Evidence: HELDOUT_TEST_RESULTS. No automatic full scientific closure.',
           f'Primary improvement supported under the approved rule: {analysis["primary_superiority_supported"]}.','',
           '| Arm | Submitted | Eligible | Failures | Valid mean min |','| --- | ---: | ---: | ---: | ---: |']
    for arm,v in analysis['by_arm'].items():
        lines.append(f"| {arm} | {v['submitted']} | {v['eligible']} | {v['failures']} | {v['valid_makespan_mean_min']} |")
    lines+=['','See analysis.json for all adjusted intervals, pair support and unconditional failure endpoints.',
            'CP gaps apply only to validated OPTIMAL finite-event-dispatch tiny references.',
            'Synthetic geometry/rates are uncalibrated. Reference-point safety excludes body envelopes.',
            'Project I live interoperability remains DATA_GAP. No joint berth/crane PPO claim.',
            'A negative or inconclusive result remains a valid research outcome; do not choose favorable seeds.']
    write_new(out/'REPORT.md','\n'.join(lines).encode('utf-8'))
    from .readiness import file_hash
    files={p.name:file_hash(p) for p in out.iterdir() if p.is_file() and p.name!='progress.jsonl'}
    write_new(out/'COMMIT.json',canonical({'files':files,'profile_sha256':campaign.profile_hash,
        'source_sha256':campaign.profile['source_sha256'],'environment_lock_sha256':campaign.profile['environment_lock_sha256']}))
    return {'status':'REPORT_GENERATED_SCIENTIFIC_REVIEW_REQUIRED','directory':str(out),'scientifically_closed':False}
