"""Verified descriptive tables; no Step 8 bootstrap, inference or model selection."""
from collections import defaultdict
import csv
import io
import json
import statistics
from integrated_terminal_pilot.benchmark import step7 as s


def average_complete_seeds(rows):
    if {r['training_seed'] for r in rows}!={11,23,37} or len(rows)!=3:
        return None
    if any(r['status']!='COMPLETED' for r in rows):return None
    if len({(r['N_out'],r['T_end_min']) for r in rows})!=1:
        raise s.CampaignError('A3 seeds disagree on denominator/cutoff')
    return {k:statistics.fmean(r[k] for r in rows) for k in ('turnaround','U','R')}


def descriptive_pairs(rows):
    """All three training identities must complete before a scenario contributes."""
    lookup={(r['scenario_id'],r['world'],r['arm']):r for r in rows
            if r['status']=='COMPLETED' and r['arm']!='A3'}
    nested=defaultdict(list)
    for r in rows:
        if r['arm']=='A3':nested[(r['scenario_id'],r['world'])].append(r)
    averaged=[]
    for (sid,world),group in nested.items():
        if len(group)!=3 or {r['training_seed'] for r in group}!={11,23,37} or any(r['status']!='COMPLETED' for r in group):
            continue
        if world=='integrated':values=average_complete_seeds(group)
        else:values={'turnaround':statistics.fmean(r['turnaround'] for r in group)}
        r={k:group[0][k] for k in ('scenario_id','world','arm','family','split','N_out','T_end_min','status')}
        r.update(values,training_seed='SCENARIO_MEAN_11_23_37')
        lookup[(sid,world,'A3')]=r;averaged.append(r)
    pairs=[];s1=[]
    for sid in sorted({r['scenario_id'] for r in rows}):
        for p,c in (('B1','A1'),('B1','A1n'),('A1n','A1'),('A2','A1'),('A3','A1'),('A3','A2'),
                    ('B2','A1'),('B2','A2'),('B2-T','A2'),('B2','B2-T')):
            a,b=lookup.get((sid,'integrated',p)),lookup.get((sid,'integrated',c))
            if a and b:
                pairs.append(dict(scenario_id=sid,family=a['family'],split=a['split'],contrast=p+'-'+c,
                    turnaround_delta_min=a['turnaround']-b['turnaround'],U_delta=a['U']-b['U'],R_delta=a['R']-b['R'],
                    turnaround_delta_percent=100*(a['turnaround']-b['turnaround'])/b['turnaround'] if b['turnaround'] else None))
        for arm in ('A2','A3'):
            ia,ib=lookup.get((sid,'integrated',arm)),lookup.get((sid,'integrated','A1'))
            ra,rb=lookup.get((sid,'reference',arm)),lookup.get((sid,'reference','A1'))
            if all(x is not None for x in (ia,ib,ra,rb)):
                s1.append(dict(scenario_id=sid,family=ia['family'],split=ia['split'],contrast=arm+'-A1',
                    integrated_delta_min=ia['turnaround']-ib['turnaround'],reference_delta_min=ra['turnaround']-rb['turnaround'],
                    difference_in_differences_min=(ia['turnaround']-ib['turnaround'])-(ra['turnaround']-rb['turnaround'])))
        xs={r['contrast']:r for r in pairs if r['scenario_id']==sid}
        if 'B2-A2' in xs and 'B1-A1n' in xs:
            a,b=xs['B2-A2'],xs['B1-A1n']
            pairs.append(dict(scenario_id=sid,family=a['family'],split=a['split'],contrast='(B2-A2)-(B1-A1n)',
                turnaround_delta_min=a['turnaround_delta_min']-b['turnaround_delta_min'],
                U_delta=a['U_delta']-b['U_delta'],R_delta=a['R_delta']-b['R_delta'],turnaround_delta_percent=None))
    return pairs,s1,averaged


def write_csv(path,rows):
    fields=sorted({k for r in rows for k in r})
    stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=fields)
    writer.writeheader()
    for row in rows:
        writer.writerow({k:json.dumps(v,sort_keys=True) if isinstance(v,(dict,list)) else v for k,v in row.items()})
    data=stream.getvalue()
    if path.exists():
        if path.read_bytes()!=data.encode('utf-8'):raise s.CampaignError('immutable table collision')
    else:
        with path.open('x',encoding='utf-8',newline='') as f:f.write(data)


def report(plan_path, *, stop_requested=None):
    s.verify_lock(plan_path)
    plan=s.load_plan(plan_path);directory=plan_path.parent
    rows=[];artifacts={};pairing={}
    from integrated_terminal_pilot.benchmark.execution import progress_bar
    with progress_bar(len(plan['rows']),description='Verify/report episodes') as bar:
        for item in plan['rows']:
            if stop_requested is not None and stop_requested.is_set():
                from integrated_terminal_pilot.benchmark.execution import ManualStop
                raise ManualStop('stopped between report rows')
            path=s.run_path(directory,item)
            if not path.exists():bar.update(1);continue
            e=s.verify_result(path,plan,item)
            artifacts[path.relative_to(directory).as_posix()]=s.file_hash(path)
            paired=e['pairing'];prior=pairing.setdefault(item['scenario_id'],paired)
            if prior!=paired:raise s.CampaignError('EXOGENOUS_INPUT_DRIFT: quarantine entire scenario')
            r=dict(row_id=item['row_id'],family=item['family'],split=item['split'],scenario_id=item['scenario_id'],
                arm=item['arm'],world=item['world'],training_seed=item['ppo_training_seed'],status=e['status'],
                wall_seconds=e['wall_seconds'],cpu_seconds=e['cpu_seconds'],N_out=paired['N_out'],T_end_min=paired['T_end_min'])
            if e['status']=='COMPLETED' and item['world']=='integrated':
                data=e['result'];cargo=data['outbound_obligations']
                r.update(turnaround=data['kpi']['total_turnaround_min'],U=cargo['U_not_loaded'],R=cargo['R_loss_rate'],
                    kpi=data['kpi'],service=data['service_compliance'],counts=data['counts'],terminal_end=data['status'],
                    cargo_classes=cargo['classes'],vessels=data['complete_result']['vessels'],decision_costs=data['decisions'])
            elif e['status']=='COMPLETED':
                r.update(reference=e['result']['reference'],turnaround=e['result']['reference']['total_turnaround_min'])
            rows.append(r);bar.update(1)
    planned=defaultdict(int);groups=defaultdict(list)
    key=lambda r:(r['split'],r['family'],r['world'],r['arm'],r.get('training_seed',r.get('ppo_training_seed')))
    for r in plan['rows']:planned[key(r)]+=1
    for r in rows:groups[key(r)].append(r)
    aggregates=[]
    for group_id,n in planned.items():
        group=groups[group_id];good=[r for r in group if r['status']=='COMPLETED']
        a=dict(split=group_id[0],family=group_id[1],world=group_id[2],arm=group_id[3],training_seed=group_id[4],
            planned=n,completed=len(good),failed=sum(r['status']=='FAILED' for r in group),
            G_blocked=sum(r['status']=='G_BLOCKED' for r in group),not_run=n-len(group),
            wall_seconds=sum(r['wall_seconds'] for r in group),cpu_seconds=sum(r['cpu_seconds'] for r in group))
        if good:
            a.update(mean_total_turnaround=statistics.fmean(r['turnaround'] for r in good),
                     median_total_turnaround=statistics.median(r['turnaround'] for r in good))
            per_vessel=[v['turnaround_min_censored'] for r in good for v in r.get('vessels',[])] if group_id[2]=='integrated' else [
                v['turnaround_time_min'] for r in good for v in r['reference']['vessel_results']]
            if per_vessel:
                a.update(mean_per_vessel_turnaround=statistics.fmean(per_vessel),median_per_vessel_turnaround=statistics.median(per_vessel))
        if good and group_id[2]=='integrated':
            a.update(mean_N_out=statistics.fmean(r['N_out'] for r in good),mean_U=statistics.fmean(r['U'] for r in good),
                mean_R=statistics.fmean(r['R'] for r in good),terminal_end_counts={end:sum(r['terminal_end']==end for r in good)
                for end in ('COMPLETED','TRUNCATED_DRAIN_LIMIT','DEADLOCK')})
            for metric in sorted({k for r in good for k in r['kpi']}):
                values=[r['kpi'][metric] for r in good if isinstance(r['kpi'].get(metric),(int,float)) and not isinstance(r['kpi'][metric],bool)]
                if values:a['scenario_mean_'+metric]=statistics.fmean(values)
        aggregates.append(a)
    pairs,s1,averaged=descriptive_pairs(rows)
    out=dict(status=s.progress(plan_path,authorized=True),rows=rows,aggregates=aggregates,
        paired_descriptive_contrasts=pairs,S1_reference_contrasts=s1,A3_scenario_first=averaged,
        pairing_audit='PASS',source_artifacts=artifacts,plan_sha256=s.digest(plan),
        S1_S2_INFERENCE='DEFERRED_TO_STEP8',step8_started=False,
        limits='Synthetic uncalibrated berth coordination with shared primitive crane/yard policies; no real-port winner claim')
    target=directory/'reports'/('report_'+s.digest(out)[:12]+'.json');s.seal(target,out)
    for name,data in (('episodes',rows),('groups',aggregates),('pairs',pairs),('s1_reference',s1),('a3_scenario_means',averaged)):
        write_csv(target.with_name(target.stem+'_'+name+'.csv'),data)
    vessels=[]
    for row in rows:
        if row['status']!='COMPLETED':continue
        for v in row.get('vessels',row.get('reference',{}).get('vessel_results',[])):
            vessels.append({k:row[k] for k in ('row_id','scenario_id','split','family','world','arm','training_seed')}|v)
    write_csv(target.with_name(target.stem+'_vessels.csv'),vessels)
    lines=['# Step 7 descriptive evidence','','SYNTHETIC / UNCALIBRATED. Final inference belongs to Step 8.',
        '',f'Plan `{s.digest(plan)}`; coverage `{out["status"]["counts"]}`.','',
        '| Split | Family | World | Arm/seed | Completed/planned | Failed | Blocked | Mean total TA | Mean U | Mean R |',
        '| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for a in aggregates:
        lines.append(f'| {a["split"]} | {a["family"]} | {a["world"]} | {a["arm"]}/{a["training_seed"]} | '
            f'{a["completed"]}/{a["planned"]} | {a["failed"]} | {a["G_blocked"]} | {a.get("mean_total_turnaround")} | {a.get("mean_U")} | {a.get("mean_R")} |')
    lines += ['','Seed-level JSON/CSV, per-vessel records and compressed ledgers accompany this table. '
        'A3 averages require all three models; reference cargo is not an integrated cargo outcome. '
        'Signed descriptive contrasts and reference S1 tables are exported; no bootstrap/NI verdict is computed.']
    md=target.with_suffix('.md');text='\n'.join(lines)+'\n'
    if not md.exists():
        with md.open('x',encoding='utf-8') as f:f.write(text)
    elif md.read_text(encoding='utf-8')!=text:raise s.CampaignError('immutable report collision')
    return dict(report=str(target),canonical_sha256=s.digest(out),coverage=out['status']['counts'])
