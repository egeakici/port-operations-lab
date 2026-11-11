"""Candidate locks, pairing, nested scenario summaries and deterministic inference."""
from pathlib import Path
import random
import statistics
from .contracts import *
from .baselines import RunRecord, metrics
from .scenarios import write_new


def source_snapshot():
    root=Path(__file__).resolve().parents[2]
    return {str(p.relative_to(root)).replace("\\","/"):__import__('hashlib').sha256(p.read_bytes()).hexdigest() for p in sorted((root/'src').rglob('*.py'))}


def candidate_lock():
    return {"schema_version":"p04_protocol_candidate_v1","status":"PENDING_OWNER_APPROVAL","primary_profile":"PRIMARY_PROFILE_NOT_LOCKED","endpoint":"valid_complete_makespan_min","failure_policy":"null quality, unconditional failure rate companion","independent_unit":"physical_scenario","training_seeds":"nested_within_scenario","comparators":["PPO-vs-ordered","PPO-vs-nearest","PPO-vs-longest","PPO-vs-balanced","PPO-vs-CP-SAT-eligible-finite-subclass"],"source_sha256":source_snapshot(),"sample_sizes":None,"bootstrap_seed":None,"bootstrap_draws":None,"confidence_level":None,"multiplicity":"Holm prespecified family; simultaneous interval design requires approval","roles":["train","development","validation","test","diagnostic"]}


def manual_gate(payload,approval_path,confirmation):
    expected=digest(payload)
    require(confirmation==expected,"MANUAL_CONFIRMATION","confirmation","exact payload digest required")
    approval=strict_json(Path(approval_path).read_text(encoding="utf-8"))
    require(approval.get("status")=="OWNER_APPROVED" and bool(approval.get("owner_evidence")),"OWNER_APPROVAL_REQUIRED","approval","candidate lock is not authorization")
    if approval.get('approved_payload_sha256') != expected:
        # An explicit root approval can authorize only exactly re-derived child
        # plans, under the rule named in that approved root. Never manufacture
        # child approval receipts or infer approval from proposed metadata.
        from .campaign import verify_derived_plan
        verify_derived_plan(payload, approval)
    require(payload.get("source_sha256")==source_snapshot(),"SOURCE_CHANGED","payload.source_sha256","re-review source before scientific execution")
    return expected


def verify_records(records,problem):
    policies=set()
    for r in records:
        require(r.problem_hash==problem.fingerprint and r.physical_hash==problem.physical_fingerprint,"PAIR_MISMATCH","records","inputs differ")
        require(r.policy_id not in policies,"DUPLICATE_RESULT","records",r.policy_id)
        policies.add(r.policy_id)
        recalculated=metrics(problem,r.schedule,r.metrics.policy_latency_s)
        require(recalculated==r.metrics,"RESULT_METRICS_MISMATCH","records",r.policy_id)
    return True


def nested_seed_means(rows,required_seeds):
    require(len(set(required_seeds))==len(required_seeds) and bool(required_seeds),"TRAINING_SEEDS","required_seeds","unique nonempty predeclared seeds required")
    grouped={}
    for scenario,seed,value in rows:
        require(type(value) in (float,int) and math.isfinite(value),"RESULT_VALUE","rows","finite values required")
        group=grouped.setdefault(scenario,{})
        require(seed not in group,"DUPLICATE_RESULT","rows",str((scenario,seed)))
        group[seed]=value
    for scenario,group in grouped.items(): require(set(group)==set(required_seeds),"MISSING_SEED","rows",scenario)
    return {s:statistics.fmean(group.values()) for s,group in sorted(grouped.items())}


def paired_summary(candidate,reference,*,draws,seed,confidence,min_scenarios):
    require(set(candidate)==set(reference) and len(candidate)>=min_scenarios>=1,"PAIR_COVERAGE","results","matching scenario identities and prespecified count required")
    require(type(draws) is int and draws>0 and type(seed) is int and 0<confidence<1,"INFERENCE_CONFIG","bootstrap","invalid resampling configuration")
    ids=sorted(candidate); delta=[candidate[s]-reference[s] for s in ids]
    require(all(type(v) in (float,int) and math.isfinite(v) for v in list(candidate.values())+list(reference.values())),"RESULT_VALUE","results","nonfinite result")
    rng=random.Random(seed)
    samples=sorted(statistics.fmean(delta[rng.randrange(len(delta))] for _ in delta) for _ in range(draws))
    alpha=(1-confidence)/2
    lower=samples[max(0,math.ceil(draws*alpha)-1)]; upper=samples[min(draws-1,math.ceil(draws*(1-alpha))-1)]
    pct=[100*(candidate[s]-reference[s])/reference[s] for s in ids if reference[s]>0]
    return {"n_independent_scenarios":len(ids),"mean_delta_min":statistics.fmean(delta),"mean_paired_percent":statistics.fmean(pct) if pct else None,"percent_denominator_n":len(pct),"ci_lower_min":lower,"ci_upper_min":upper,"wins":sum(d<0 for d in delta),"ties":sum(d==0 for d in delta),"losses":sum(d>0 for d in delta),"worst_delta_min":max(delta),"bootstrap_seed":seed,"draws":draws,"confidence":confidence}


def holm(pvalues,alpha):
    require(0<alpha<1 and bool(pvalues) and all(type(p) in (int,float) and 0<=p<=1 for p in pvalues.values()),"MULTIPLICITY","pvalues","invalid probabilities")
    result={}; stopped=False
    for rank,(name,p) in enumerate(sorted(pvalues.items(),key=lambda item:(item[1],item[0]))):
        reject=not stopped and p<=alpha/(len(pvalues)-rank)
        result[name]=reject
        if not reject: stopped=True
    return result


def write_development(problem,records,directory):
    verify_records(records,problem)
    out=Path(directory); require(not out.exists(),"OUTPUT_EXISTS","output","immutable run exists")
    out.mkdir(parents=True)
    write_new(out/'problem.json',canonical(problem.to_dict()))
    for record in records: write_new(out/(record.policy_id+'.json'),canonical(record.to_dict()))
    manifest={"origin":"TEST_FIXTURE_SYNTHETIC","problem_hash":problem.fingerprint,"source_sha256":source_snapshot(),"files":{p.name:__import__('hashlib').sha256(p.read_bytes()).hexdigest() for p in sorted(out.glob('*.json'))}}
    write_new(out/'manifest.json',canonical(manifest))
    import csv
    with (out/'summary.csv').open('x',newline='',encoding='utf-8') as stream:
        writer=csv.writer(stream); writer.writerow(['policy_id','status','valid_complete','makespan_min','completed_moves'])
        for r in records: writer.writerow([r.policy_id,r.status,r.metrics.valid_complete,r.metrics.makespan_min,r.metrics.completed_moves])
    return manifest
