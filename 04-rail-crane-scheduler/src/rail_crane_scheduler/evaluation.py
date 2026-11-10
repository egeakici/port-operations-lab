"""Owner-manual test evaluation, committed-cell integrity and honest reports."""
from pathlib import Path
import hashlib
import statistics
import time
from uuid import uuid4
from .contracts import *
from .baselines import POLICIES, run, metrics
from .research import manual_gate, source_snapshot, nested_seed_means, paired_summary
from .scenarios import write_new, no_leakage


def _local(path):
    root=Path(__file__).resolve().parents[2]
    resolved=(root/path).resolve()
    require(resolved.is_relative_to(root),"INPUT_PATH","path","only Project04-local evidence")
    return resolved


def _locked_problem(item,role):
    p=QCSPProblem.from_json(_local(item['path']).read_text(encoding='utf-8'))
    require(p.fingerprint==item['problem_hash'] and p.metadata.role==role,"INPUT_LOCK","input","hash/role mismatch")
    return p


def verify_cell(directory):
    directory=Path(directory); commit=strict_json((directory/'COMMIT.json').read_text(encoding='utf-8'))
    require(set(commit)=={'files'},"CELL_COMMIT","commit","unexpected fields")
    for name,sha in commit['files'].items():
        require(Path(name).name==name and name!='COMMIT.json',"UNSAFE_PATH","commit",name)
        require(hashlib.sha256((directory/name).read_bytes()).hexdigest()==sha,"CELL_HASH","cell",name)
    require('result.json' in commit['files'],"CELL_COMMIT","commit","missing result")
    return strict_json((directory/'result.json').read_text(encoding='utf-8'))


def commit_cell(directory,result,schedule):
    directory=Path(directory)
    require(not directory.exists(),"OUTPUT_EXISTS","cell","immutable cell exists")
    stage=directory.with_name(directory.name+'.partial_'+uuid4().hex); stage.mkdir(parents=True)
    write_new(stage/'result.json',canonical(result))
    if schedule is not None: write_new(stage/'schedule.json',canonical(schedule.to_dict()))
    files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in stage.iterdir() if p.is_file()}
    write_new(stage/'COMMIT.json',canonical({'files':files})); stage.rename(directory)


def evaluate_policy(model,problem,config,permit,arm):
    from .training import make_env
    env=None
    try:
        env=make_env(problem,config,permit); obs,info=env.reset(seed=problem.metadata.seed); latencies=[]
        require(not info['success'],'ZERO_WORK_PRIMARY','test','empty correctness fixture is not primary performance')
        for _ in range(config.max_episode_steps):
            t=time.perf_counter(); obs=env._observation(); action,_=model.predict(obs,deterministic=True,action_masks=env.action_masks()); latencies.append(time.perf_counter()-t)
            obs,_,done,truncated,info=env.step(int(action))
            if done or truncated: break
        schedule=env.kernel.schedule(arm)
        return info['status'],metrics(problem,schedule,tuple(latencies),permit),schedule,None
    except ContractError as exc:
        status={'DEADLOCK_INITIAL':'DEADLOCK','PHYSICAL_VALIDATION_FAILURE':'INVALID_PLAN','ZERO_WORK_PRIMARY':'UNSUPPORTED_PRIMARY_ZERO_WORK'}.get(exc.code,'INVALID_INPUT_OR_UNSUPPORTED_PROFILE')
        schedule=env.kernel.schedule(arm) if env is not None and env.kernel is not None else None
        return status,None,schedule,{'code':exc.code,'message':exc.message}


def evaluate_manual(payload,approval_path,confirmation,output,*,resume=False):
    token=manual_gate(payload,approval_path,confirmation)
    from .training import TrainingConfig, make_env, load_checkpoint
    config=TrainingConfig.from_dict(payload['training_config'])
    selected={}
    train_inputs=[]
    for item in payload['selection_receipts']:
        path=_local(item['path'])
        require(hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256'],"SELECTION_HASH","selection","changed validation selection")
        receipt=strict_json(path.read_text(encoding='utf-8'))
        require(receipt['status']=='TRAINING_COMPLETE_VALIDATION_SELECTED' and receipt['source_sha256']==source_snapshot(),"SELECTION_STATUS","selection","training/selection incomplete or stale")
        require(receipt['seed'] not in selected,"DUPLICATE_SEED","selection","duplicate selection")
        selected[receipt['seed']]=_local(receipt['selected_checkpoint'])
        training_plan=strict_json((path.parent.parent/'plan.json').read_text(encoding='utf-8'))
        require(digest(training_plan)==receipt['plan_hash'] and training_plan['training_config']==payload['training_config'],"TRAINING_PLAN","selection","selection is not bound to original training plan")
        train_inputs.extend(_locked_problem(i,'train') for i in training_plan['train_inputs'])
        train_inputs.extend(_locked_problem(i,'validation') for i in training_plan['validation_inputs'])
    require(set(selected)==set(config.seeds),"MISSING_SEED","selection","all predeclared model seeds required")
    # Test inputs are read only after owner/source/selection guards above.
    tests=[_locked_problem(i,'test') for i in payload['test_inputs']]
    require(bool(tests),"EMPTY_TEST","test_inputs","nonempty locked cohort required")
    no_leakage(tests)
    prior={p.physical_fingerprint for p in train_inputs}
    require(not any(p.physical_fingerprint in prior for p in tests),"SPLIT_LEAKAGE","test_inputs","physical training/validation duplicate")
    permit=ExecutionPermit(token,tuple(p.fingerprint for p in tests),('test',))
    out=Path(output)
    if out.exists():
        require(resume and digest(strict_json((out/'plan.json').read_text(encoding='utf-8')))==token,"RESUME_PLAN","output","new run or exact compatible resume required")
    else:
        out.mkdir(parents=True); write_new(out/'plan.json',canonical(payload))
        write_new(out/'approval_snapshot.json',canonical(strict_json(Path(approval_path).read_text(encoding='utf-8'))))
    models={seed:load_checkpoint(path,config,make_env(tests[0],config,permit),expected_seed=seed,require_trained=True) for seed,path in selected.items()}
    expected=[]
    for problem in tests:
        arms=[*POLICIES,*[f'crane_ppo_seed_{s}' for s in config.seeds]]
        if payload.get('cp_reference') is not None: arms.append('cpsat_finite_dispatch_v1')
        for arm in arms:
            key=digest([token,problem.fingerprint,arm]); expected.append(key); cell=out/'cells'/key
            if cell.exists():
                row=verify_cell(cell)
                require(row['plan_hash']==token and row['problem_hash']==problem.fingerprint and row['policy_id']==arm,"RESUME_CELL","cell","identity mismatch")
                continue
            started=time.perf_counter()
            solver_result=None; failure=None
            if arm in POLICIES:
                record=run(problem,arm,permit); schedule=record.schedule; values=record.metrics
                seed=None; model_hash=None; status=record.status
            elif arm=='cpsat_finite_dispatch_v1':
                from .cpsat import solve
                solver_result=solve(problem,permit=permit,**payload['cp_reference'])
                schedule=solver_result.schedule
                values=metrics(problem,schedule,(),permit) if schedule is not None else None
                seed=None; model_hash=None; status=solver_result.status
            else:
                seed=int(arm.rsplit('_',1)[1]); model,metadata=models[seed]
                status,values,schedule,failure=evaluate_policy(model,problem,config,permit,arm)
                model_hash=metadata['model_sha256']
            row={'plan_hash':token,'problem_hash':problem.fingerprint,'physical_hash':problem.physical_fingerprint,'scenario_id':problem.metadata.scenario_id,'family':problem.metadata.family,'origin':problem.metadata.origin,'policy_id':arm,'training_seed':seed,'checkpoint_hash':model_hash,'status':status,'valid_complete':values.valid_complete if values else False,'makespan_min':values.makespan_min if values else None,'metrics':values.to_dict() if values else None,'episode_wall_s':time.perf_counter()-started,'source_sha256':source_snapshot(),'solver_status':solver_result.status if solver_result else None,'solver_bound_min':solver_result.bound_min if solver_result else None,'solver_relative_gap':solver_result.relative_gap if solver_result else None,'solver_formulation':solver_result.formulation if solver_result else None}
            row['failure_evidence']=failure
            commit_cell(cell,row,schedule)
    summary={'status':'HELD_OUT_EXECUTION_COMPLETE_ANALYSIS_PENDING','plan_hash':token,'expected_cells':expected,'scientifically_closed':False}
    if not (out/'EXECUTION_COMPLETE.json').exists(): write_new(out/'EXECUTION_COMPLETE.json',canonical(summary))
    return summary


def analyze_rows(rows,*,seeds,reference_policy,draws,bootstrap_seed,confidence,min_scenarios):
    seen=set(); failure={}; reference={}; nested=[]; attempted={}
    for row in rows:
        key=(row['scenario_id'],row['policy_id'])
        require(key not in seen,"DUPLICATE_RESULT","analysis",str(key)); seen.add(key)
        arm=row['policy_id']; attempted[arm]=attempted.get(arm,0)+1
        failure[arm]=failure.get(arm,0)+int(not row['valid_complete'])
        require((row['valid_complete'] and row['makespan_min'] is not None) or (not row['valid_complete'] and row['makespan_min'] is None),"FAILED_MAKESPAN","analysis","incomplete plan cannot report valid objective")
        if row['valid_complete']:
            if arm==reference_policy: reference[row['scenario_id']]=row['makespan_min']
            if row['training_seed'] in seeds: nested.append((row['scenario_id'],row['training_seed'],row['makespan_min']))
    complete_seed_sets={}
    for s,seed,value in nested: complete_seed_sets.setdefault(s,set()).add(seed)
    eligible={s for s,group in complete_seed_sets.items() if group==set(seeds)}
    means=nested_seed_means([r for r in nested if r[0] in eligible],seeds)
    common=set(means)&set(reference)
    paired=paired_summary({s:means[s] for s in common},{s:reference[s] for s in common},draws=draws,seed=bootstrap_seed,confidence=confidence,min_scenarios=min_scenarios) if len(common)>=min_scenarios else None
    return {'attempted_by_arm':attempted,'failures_by_arm':failure,'unconditional_failure_rate':{a:failure[a]/n for a,n in attempted.items()},'paired_eligible_scenarios':len(common),'paired':paired,'qualification':'conditional complete-pair quality plus unconditional failures; no missingness suppression'}


def render_report(rows,analysis=None,manifest_reference=None):
    if not rows:
        return '# Project04 scientific evidence\n\nSCIENTIFIC_EVIDENCE_NOT_YET_RUN\n\nActual trained checkpoints: 0. Held-out runs: 0. No superiority claim.\n\n| Policy | Valid makespan min |\n| --- | --- |\n'
    fixture_only=any(r.get('origin')=='TEST_FIXTURE_SYNTHETIC' for r in rows)
    lines=['# Project04 recorded results','', 'FIXTURE_ONLY_NOT_SCIENTIFIC' if fixture_only else 'RECORDED_EVIDENCE_REQUIRES_PROTOCOL_AND_INFERENCE_AUDIT','',f'Actual rows: {len(rows)}. No automatic scientific closure.','', '| Scenario | Policy | Status | Makespan min |','| --- | --- | --- | --- |']
    for r in rows: lines.append(f"| {r['scenario_id']} | {r['policy_id']} | {r['status']} | {r['makespan_min']} |")
    lines+=['','## Source and failure accounting','',f"Manifest: {manifest_reference or 'not supplied; this rendering alone is not a verified scientific release'}.",'']
    statuses={}
    for row in rows: statuses[row['status']]=statuses.get(row['status'],0)+1
    lines+=['| Recorded status | Actual rows |','| --- | --- |']+[f'| {name} | {count} |' for name,count in sorted(statuses.items())]
    if analysis is not None:
        lines+=['','## Prespecified paired analysis','','Conditional complete-pair quality must be read with unconditional failure rates. Raw bootstrap intervals are not simultaneous intervals.','','```json',json.dumps(analysis,sort_keys=True,indent=2),'```']
    lines+=['','## Limitations and claim boundary','','No automatic scientific closure, real-terminal calibration, commercial gain or joint terminal RL is established. CP certificates apply only to the named finite subclass. Report exact source/model/input hashes and approved inference configuration with any exported conclusion.']
    return '\n'.join(lines)+'\n'


def analysis_figures(rows,analysis=None):
    """Standalone Matplotlib figures from recorded values; no invented empty data."""
    from matplotlib.figure import Figure
    valid=[r for r in rows if r.get('valid_complete') and r.get('makespan_min') is not None]
    require(bool(valid),'NO_EVIDENCE','plots','no complete recorded rows; do not fabricate charts')
    fig=Figure(figsize=(7,4)); ax=fig.subplots()
    groups={}
    for row in valid:
        wall=row.get('episode_wall_s')
        require(type(wall) in (int,float) and math.isfinite(wall) and wall>=0,'RUNTIME_VALUE','plots','actual whole-episode runtime required')
        groups.setdefault(row['policy_id'],[]).append(row)
    for name,group in sorted(groups.items()):
        ax.scatter([r['episode_wall_s'] for r in group],[r['makespan_min'] for r in group],label=name)
    ax.set_xlabel('Whole-episode wall time (s), not policy-only latency')
    ax.set_ylabel('Valid complete makespan (simulation min)')
    ax.set_title('Recorded runtime/quality points — descriptive, not superiority')
    ax.legend(fontsize=7); fig.tight_layout(); result={'runtime_quality':fig}
    paired=analysis.get('paired') if analysis else None
    if paired:
        low,high,mean=(paired[k] for k in ('ci_lower_min','ci_upper_min','mean_delta_min'))
        require(all(type(x) in (int,float) and math.isfinite(x) for x in (low,high,mean)) and low<=high,'CI_VALUE','plots','valid recorded interval required')
        ci=Figure(figsize=(7,2.5)); a=ci.subplots()
        a.hlines(0,low,high,color='#4c78a8',linewidth=3); a.plot(mean,0,'o',color='#e15759'); a.axvline(0,color='gray',linestyle='--')
        a.set_yticks([0],['Paired scenario mean']); a.set_xlabel('Candidate minus reference (simulation min)')
        a.set_title('Conditional paired bootstrap interval; see failure-rate endpoint')
        ci.tight_layout(); result['paired_interval']=ci
    return result


def read_existing(directory):
    directory=Path(directory)
    if not directory.exists(): return []
    complete=directory/'EXECUTION_COMPLETE.json'
    require(complete.exists(),"INCOMPLETE_CAMPAIGN","results","missing committed campaign completion record")
    manifest=strict_json(complete.read_text(encoding='utf-8'))
    plan=strict_json((directory/'plan.json').read_text(encoding='utf-8'))
    require(digest(plan)==manifest['plan_hash'],"PLAN_HASH","results","changed plan")
    approval=strict_json((directory/'approval_snapshot.json').read_text(encoding='utf-8'))
    require(approval.get('status')=='OWNER_APPROVED' and approval.get('approved_payload_sha256')==manifest['plan_hash'] and bool(approval.get('owner_evidence')),"OWNER_APPROVAL_REQUIRED","results","missing matching owner execution receipt")
    rows=[verify_cell(directory/'cells'/key) for key in manifest['expected_cells']]
    require(all(r['plan_hash']==manifest['plan_hash'] for r in rows),"ROW_PLAN","results","row/plan mismatch")
    for row in rows:
        require(type(row.get('valid_complete')) is bool,"RESULT_TYPE","results","boolean validity required")
        value=row.get('makespan_min')
        require((not row['valid_complete'] and value is None) or (row['valid_complete'] and type(value) in (int,float) and math.isfinite(value) and value>=0),"RESULT_VALUE","results","only finite complete-plan objectives allowed")
        require(row['source_sha256']==plan['source_sha256'],"RESULT_SOURCE","results","row source differs from approved execution plan")
    require(len({(r['problem_hash'],r['policy_id']) for r in rows})==len(rows),"DUPLICATE_RESULT","results","repeated scenario-arm")
    return rows


def certified_gap(row,reference):
    require(reference.get('solver_status')=='OPTIMAL' and reference.get('valid_complete') and reference.get('solver_formulation')=='p04_exact_finite_event_dispatch_paths_v1',"NO_CERTIFIED_REFERENCE","reference","FEASIBLE/dependency/other model is not an optimum")
    require(row['problem_hash']==reference['problem_hash'] and row['valid_complete'] and reference['solver_bound_min']==reference['makespan_min'],"REFERENCE_MISMATCH","reference","matching validated optimum/bound required")
    return row['makespan_min']-reference['makespan_min']
