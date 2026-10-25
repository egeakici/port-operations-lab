"""Downstream WAIT/cargo/rollover/forecast diagnostics; never feeds a policy."""
from collections import Counter
import gzip
import json
from statistical import ContractError


def stream(path):
    with gzip.open(path,'rt',encoding='utf-8') as f:
        for line in f: yield json.loads(line)


def post_run(trace_dir,doc,records,observations,result):
    events=list(stream(trace_dir/'events.jsonl.gz'))
    event_ids={e['event_id']:e for e in events}
    departures={e['entity_key']:e['time_min'] for e in events if e['event_type']=='VESSEL_DEPARTED'}
    original={c['container_id']:c for c in doc['containers'] if c['destination_vessel_id'] is not None}
    loaded,rolled,ready,last={},{},{},{}
    for cid,c in original.items():
        last[cid]=dict(status='IN_YARD' if c['present_at_episode_start'] else 'EXPECTED_BY_LANDSIDE' if c['cargo_flow']=='export' else 'EXPECTED_BY_VESSEL',time_min=0.)
    for entry in stream(trace_dir/'ledger.jsonl.gz'):
        cid=entry['container_id']; kind=entry['event_type']; t=entry['simulation_time_min']
        if kind=='LOAD_COMPLETED': loaded[cid]=t
        if kind in ('RECEIVE_COMPLETED','DISCHARGE_COMPLETED'): ready.setdefault(cid,t)
        if kind=='ROLLED_OVER':
            cause=event_ids.get(entry['causation_id'])
            if cause is None or cause['event_type']!='LOAD_WAIT_TIMEOUT':
                raise ContractError('D17 rollover missing timeout causation')
            rolled[cid]=dict(time_min=t,physical_before=last.get(cid),timeout=cause,ledger=entry)
        if entry['event_class']=='PHYSICAL': last[cid]=dict(status=entry['to_status'],time_min=t,location=entry['destination_location'])
    cutoff=result['T_end_min']
    losses=sorted(cid for cid in original if cid not in loaded or loaded[cid]>cutoff+1e-9)
    # Independent ledger counts, not TEU, not simulator summary-derived flags.
    if set(rolled)&set(loaded): raise ContractError('Rolled-over container subsequently loaded')
    output=[]
    if len(records)!=len(observations): raise ContractError('Decision observation count mismatch')
    for index,(r,o) in enumerate(zip(records,observations)):
        row=dict(decision_id=r['decision_id'],time_min=r['time_min'],kind=r['action_type'],
                 wait_legal=r.get('wait_legal'),policy_seconds=r['policy_seconds'],two_second_warning=r['policy_seconds']>2,
                 cohort=o['cohort'],inner_horizon_min=o['inner_horizon_min'])
        if 'same_state_A2' in r:row['same_state_A2']=r['same_state_A2']
        if 'evaluation' in r:
            e=r['evaluation']; candidate=next(c for c in e['candidates'] if c['action']==r['p03_action'])
            leaf=candidate['leaf'] if candidate['kind']=='ASSIGN' else candidate['wait_terminal']
            if leaf is None:
                leaf=min(candidate['wait_branches'],key=lambda x:(x['predicted_unfulfilled_outbound'],x['predicted_turnaround_min'],x['action']))
            horizon=o['inner_horizon_min']
            actual_ta=sum(min(departures.get(v,cutoff),horizon)-o['arrivals'][v] for v in o['cohort'])
            actual_u=sum(cid not in loaded or loaded[cid]>horizon+1e-9 for cid in o['known_outbound_ids'])
            row.update(selected_prediction=leaf,pivotal=r['pivotal'],root_candidates=len(e['candidates']),
                leaf_paths=sum(1 if c['kind']=='ASSIGN' or c['wait_terminal'] else len(c['wait_branches']) for c in e['candidates']),
                actual_same_cohort_turnaround_min=actual_ta,actual_known_unloaded=actual_u,
                predicted_minus_actual_turnaround=leaf['predicted_turnaround_min']-actual_ta,
                predicted_minus_actual_unloaded=leaf['predicted_unfulfilled_outbound']-actual_u,
                wait_prediction=next((c for c in e['candidates'] if c['kind']=='WAIT'),None))
        row['occupying_release_forecasts']=[dict(x,actual=departures.get(x['vessel_id']),
            error=None if x['vessel_id'] not in departures else x['predicted']-departures[x['vessel_id']])
            for x in o['occupying_release_forecasts']]
        if r['action_type']=='WAIT':
            end=records[index+1]['time_min'] if index+1<len(records) else result['end_time_min']
            row['wait_observed']=dict(end_min=end,elapsed_min=end-r['time_min'],
                events=[e for e in events if r['time_min']<e['time_min']<=end])
        output.append(row)
    return dict(decisions=output,rollovers=len(rolled),ledger_N_out=len(original),ledger_U=len(losses),
        losses=[dict(container_id=cid,flow=original[cid]['cargo_flow'],destination_vessel=original[cid]['destination_vessel_id'],
            origin_vessel=original[cid]['origin_vessel_id'],rollover=rolled.get(cid),state_at_stop=last.get(cid),
            first_yard_ready_min=0. if original[cid]['present_at_episode_start'] else ready.get(cid),
            reason='D17_ROLLOVER' if cid in rolled else 'CENSOR_OR_STOP_BEFORE_LOAD_COMPLETED',
            primary_causal_reason='UNKNOWN_OR_MULTIPLE_CONSTRAINTS') for cid in losses],
        rollover_status_counts=dict(Counter((r['physical_before'] or {}).get('status','UNKNOWN') for r in rolled.values())),
        limits='Selected-trajectory diagnostics; UNCAlIBRATED_SYNTHETIC_FORECAST; WAIT associations are not causal effects')
