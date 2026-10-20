"""Post-run diagnostics only: future outcomes never reach a policy or selector."""
import base64
from collections import Counter
import gzip
import importlib.util
import json
from pathlib import Path
import pickle
import time

from integrated_terminal_pilot.benchmark import step7 as s
from integrated_terminal_pilot.benchmark.step7_inputs import safe_path


def rows(path):
    with gzip.open(path,'rt',encoding='utf-8') as f:
        for line in f:yield json.loads(line)


def helper():
    path=s.PROJECT_ROOT/'scripts/report_step6_closure_f3.py'
    spec=importlib.util.spec_from_file_location('step7_archived_diagnostic_math',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m


def analyze(envelope, directory, doc, math):
    r=envelope['result'];item=envelope['row'];cutoff=r['T_end_min']
    traces={Path(x['path']).name:x for x in envelope['traces']}
    stream=lambda name:rows(safe_path(directory,traces[name+'.gz']['path']))
    events=list(stream('events.jsonl'));event_ids={x['event_id']:x for x in events}
    departures={x['entity_key']:x['time_min'] for x in events if x['event_type']=='VESSEL_DEPARTED'}
    decisions=r['policy_decisions'];assignments={x['vessel_id']:x['time_min'] for x in decisions if x['action_type']=='ASSIGN'}
    original={x['container_id']:x for x in doc['containers'] if x['destination_vessel_id'] is not None}
    loaded={};rolled={};ready={}
    physical={cid:dict(status='IN_YARD' if c['present_at_episode_start'] else
        'EXPECTED_BY_LANDSIDE' if c['cargo_flow']=='export' else 'EXPECTED_BY_VESSEL',
        location=None,time_min=0,source='EXOGENOUS_INITIAL_STATE') for cid,c in original.items()}
    for x in stream('ledger.jsonl'):
        cid=x['container_id'];kind=x['event_type'];t=x['simulation_time_min']
        if kind=='LOAD_COMPLETED':loaded[cid]=t
        if kind in ('RECEIVE_COMPLETED','DISCHARGE_COMPLETED'):ready.setdefault(cid,t)
        if kind=='ROLLED_OVER':
            cause=event_ids.get(x['causation_id'])
            if cause is None or cause['event_type']!='LOAD_WAIT_TIMEOUT':raise s.CampaignError('D17 causation failed')
            rolled[cid]=dict(time_min=t,ledger=x,physical_before=physical.get(cid),timeout=cause)
        if x['event_class']=='PHYSICAL':physical[cid]=dict(status=x['to_status'],location=x['destination_location'],time_min=t)
    actual_u={cid for cid in original if cid not in loaded or loaded[cid]>cutoff+1e-9}
    if len(actual_u)!=r['outbound_obligations']['U_not_loaded'] or len(original)!=r['outbound_obligations']['N_out']:
        raise s.CampaignError('independent authoritative LOAD_COMPLETED reconciliation failed')
    if set(rolled)&set(loaded):raise s.CampaignError('rolled-over container subsequently loaded')
    cargo=r['outbound_obligations']
    if (len(rolled)!=cargo['classes']['NOT_LOADED_ROLLED_OVER'] or
        len(original)-len(actual_u)!=cargo['loaded']):
        raise s.CampaignError('independent cargo class/loaded count reconciliation failed')
    losses=[]
    for cid in sorted(actual_u):
        c=original[cid];roll=rolled.get(cid)
        losses.append(dict(container_id=cid,flow=c['cargo_flow'],destination_vessel=c['destination_vessel_id'],
            origin_vessel=c['origin_vessel_id'],rollover=roll,state_at_stop=physical.get(cid),
            first_yard_ready_min=0 if c['present_at_episode_start'] else ready.get(cid),
            evidence='D17_ROLLOVER' if roll else 'STOP_OR_CENSORING_BEFORE_LOAD_COMPLETION',
            primary_causal_reason='UNKNOWN_OR_MULTIPLE_CONSTRAINTS'))
    vessel_rows={v['vessel_id']:dict(v,actual_departure_time_min=departures.get(v['vessel_id']),
                 berth_start_time_min=assignments.get(v['vessel_id'])) for v in r['complete_result']['vessels']}
    observations=list(rows(safe_path(directory,envelope['observations']['path'])))
    if len(observations)!=len(decisions):raise s.CampaignError('policy input/decision count mismatch')
    output=[]
    for i,(p,snapshot) in enumerate(zip(decisions,observations)):
        row=dict(ordinal=i+1,decision_id=p['decision_id'],time_min=p['time_min'],action=p['p03_action'],
            kind=p['action_type'],wait_legal=p.get('wait_legal'),policy_seconds=p['policy_seconds'],
            two_second_warning=p['policy_seconds']>2,resources=math.observed_resources(snapshot))
        row['occupying_release_forecasts']=[dict(vessel_id=v['vessel_id'],
            predicted_release_min=v['estimated_release_time_min'],actual_departure_min=departures.get(v['vessel_id']),
            censored=departures.get(v['vessel_id']) is None,
            predicted_minus_actual_min=(v['estimated_release_time_min']-departures[v['vessel_id']]
                if v['vessel_id'] in departures else None)) for v in snapshot['berth']['vessels']
            if v['status']=='OCCUPYING' and v.get('estimated_release_time_min') is not None]
        if item['arm']=='B1':
            selected=next(c for c in p['candidates'] if c['action']==p['p03_action'])
            actual=departures.get(p['vessel_id'])
            row['b1_release_error']=dict(predicted_release_min=selected['release_min'],actual_departure_min=actual,
                censored=actual is None,predicted_minus_actual_min=selected['release_min']-actual if actual is not None else None)
        if item['arm'] in ('A2','B2','B2-T'):
            # Only trusted, locally generated, source/checksum-verified inputs are deserialized here.
            raw=base64.b64decode(snapshot['policy_observation_pickle_base64']);view=pickle.loads(raw)
            berth=view if item['arm']=='A2' else view.berth
            horizon=(max(v.arrival_time_min for v in berth.vessels)+s.load_generator_config().parameters['physics_profiles']['standard_v1']['episode']['max_drain_extension_min']
                     if item['arm']=='A2' else view.projection.catalog.drain_limit_min)
            cohort=[v.vessel_id for v in berth.vessels if v.status!='DEPARTED']
            ta,fw,censored=math.actual_cohort(berth,vessel_rows,horizon,cutoff)
            row.update(cohort=cohort,inner_horizon_min=horizon,actual_same_cohort_turnaround_min=ta,
                actual_censored_vessels=censored,policy_input_sha256=s.hashlib.sha256(raw).hexdigest(),
                forecast_label='UNCALIBRATED_SYNTHETIC_FORECAST')
            if item['arm']=='A2':
                scores={int(a):v for a,v in p['scores']}
                row.update(predicted_future_wait=scores[p['p03_action']],actual_future_wait=fw,
                    future_wait_error=scores[p['p03_action']]-fw,
                    cargo_prediction='NOT_PREDICTED_BY_A2',turnaround_comparability='DIFFERENT_OBJECTIVE')
                if berth.wait_legal:row['wait_prediction']=math.a2_wait_details(berth,scores)
            else:
                e=p['evaluation'];chosen=math.select_candidate(e['candidates'],item['arm'])
                leaf=math.best_leaf(chosen,item['arm'])
                if chosen['action']!=p['p03_action']:raise s.CampaignError('archived selector mismatch')
                known=[c.container_id for c in view.projection.catalog.containers if c.destination_vessel_id in cohort]
                u=sum(cid not in loaded or loaded[cid]>horizon+1e-9 for cid in known)
                row.update(pivotal=p['pivotal'],prediction_digest=e['prediction_digest'],selected_prediction=leaf,
                    known_outbound=len(known),actual_known_unloaded=u,
                    predicted_minus_actual_unloaded=leaf['predicted_unfulfilled_outbound']-u,
                    predicted_minus_actual_turnaround=leaf['predicted_turnaround_min']-ta,
                    evaluation_timing=e['timing'],root_candidates=len(e['candidates']),
                    leaf_paths=sum(len(math.leaves(c)) for c in e['candidates']))
                wait=next((c for c in e['candidates'] if c['kind']=='WAIT'),None)
                if wait:row['wait_prediction']=dict(candidate=wait,selected_branch=math.best_leaf(wait,item['arm']))
        if p['action_type']=='WAIT':
            end=decisions[i+1]['time_min'] if i+1<len(decisions) else min(cutoff,r['end_time_min'])
            interval=[x for x in events if p['time_min']<x['time_min']<=end]
            row['wait_observed']=dict(end_min=end,elapsed_min=end-p['time_min'],events=interval,
                next_resources=math.observed_resources(observations[i+1]) if i+1<len(observations) else None,
                interpretation='Temporal observation only; no counterfactual or causal WAIT claim')
        output.append(row)
    samples=envelope['rss_samples']
    return dict(row=item,decisions=output,losses=losses,cargo_audit='PASS',rollovers=len(rolled),
        rollover_status_counts=dict(Counter((x['physical_before'] or {}).get('status','INITIAL_OR_UNKNOWN') for x in rolled.values())),
        compute=dict(wall_seconds=envelope['wall_seconds'],cpu_seconds=envelope['cpu_seconds'],
            max_sampled_rss_bytes=max([x['rss_bytes'] for x in samples]+[envelope['rss_after_bytes']]),
            rss_note='15-second/boundary samples, not a continuous peak',
            decision_seconds=math.stats([p['policy_seconds'] for p in decisions]),
            two_second_warnings=sum(p['policy_seconds']>2 for p in decisions)),
        limits='Forecast errors are selected-trajectory diagnostics, not calibrated counterfactual errors. '
               'Cargo metrics count containers, not TEU. A2 uses future waiting rather than B2 turnaround/cargo.')


def report(plan_path, *, stop_requested=None):
    s.verify_lock(plan_path);plan=s.load_plan(plan_path);directory=plan_path.parent
    math=helper();summaries=[];t=time.perf_counter();cpu=time.process_time()
    from integrated_terminal_pilot.benchmark.execution import progress_bar
    with progress_bar(len(plan['rows']),description='WAIT/cargo/forecast diagnostics') as bar:
        for row in plan['rows']:
            if stop_requested is not None and stop_requested.is_set():
                from integrated_terminal_pilot.benchmark.execution import ManualStop
                raise ManualStop('stopped between diagnostic rows')
            path=s.run_path(directory,row)
            if not path.exists():bar.update(1);continue
            e=s.verify_result(path,plan,row)
            if e['status']!='COMPLETED' or row['world']!='integrated':bar.update(1);continue
            target=directory/'diagnostics'/(row['row_id']+'.json.gz')
            receipt=target.with_suffix('.receipt.json')
            if receipt.exists():
                old=s.unseal(receipt)
                if old['source_run_sha256']!=s.file_hash(path) or old['gzip_sha256']!=s.file_hash(target):
                    raise s.CampaignError('diagnostic receipt drift')
                summaries.append(old);bar.update(1);continue
            scenario=next(x for x in plan['scenarios'] if x['scenario_id']==row['scenario_id'])
            doc=s.unseal(s.scenario_path(directory,scenario))['document']
            row_wall=time.perf_counter();row_cpu=time.process_time()
            data=analyze(e,directory,doc,math)
            archived=s.install_gzip(target,[json.dumps(data,sort_keys=True,allow_nan=False)+'\n'])
            summary=dict(row=row,source_run_sha256=s.file_hash(path),path=target.relative_to(directory).as_posix(),**archived,
                decisions=len(data['decisions']),waits=sum(d['kind']=='WAIT' for d in data['decisions']),
                cargo_pivotal=sum(d.get('pivotal',{}).get('cargo_pivotal',False) for d in data['decisions']),
                one_container_pivotal=sum(d.get('pivotal',{}).get('one_container_pivotal',False) for d in data['decisions']),
                rollovers=data['rollovers'],compute=data['compute'],cargo_audit='PASS',
                reporter_wall_seconds=time.perf_counter()-row_wall,reporter_cpu_seconds=time.process_time()-row_cpu)
            s.seal(receipt,summary);summaries.append(summary);bar.update(1)
    out=dict(rows=summaries,reporter_wall_seconds=time.perf_counter()-t,reporter_cpu_seconds=time.process_time()-cpu,
        counting='pivotal counts are per decision/trajectory, not unique inputs across B2 and B2-T',
        reconstructive_work='A2 WAIT branches are reporter-only; their runtime is separate from outer policy cost')
    target=directory/'reports'/('diagnostics_'+s.digest(out)[:12]+'.json');s.seal(target,out)
    return dict(report=str(target),rows=len(summaries))
