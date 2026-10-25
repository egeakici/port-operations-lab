"""Qualified scientific release and honest machine gates, no simulation imports."""
from collections import defaultdict
from pathlib import Path
import io
import json
import numpy as np
from evidence import PROJECT, REPO, read, sha, publish, publish_bytes, s, code_inventory, safe_path
from statistical import ContractError, interval, cargo_noninferiority, nested_mean
from reporting import markdown_table, ci_text
from closure_runtime import campaign_status, verify_cell


def txt(path,value): publish_bytes(path,(value.rstrip()+'\n').encode('utf-8'))


def prepare_documents(ctx,plan,packet,audit):
    from final_closure import packet_path,plan_directory
    directory=packet_path(plan).parent
    publish(directory/'source_method_audit.json',audit)
    publish(directory/'engineering_probe.json',packet['engineering_probe'])
    publish(directory/'focused_test_receipt.json',packet['test_receipt'])
    testlog=REPO/packet['test_receipt']['path']
    if testlog.with_suffix('.log').exists():
        publish_bytes(directory/'focused_tests.log',testlog.with_suffix('.log').read_bytes())
    txt(directory/'README.md',f'''# Project I final scientific decision packet

Plan canonical SHA256: `{s.digest(plan)}`. Packet canonical SHA256: `{s.digest(packet)}`.
Status: **PENDING_EXPLICIT_OWNER_APPROVAL**. These are proposals, never approval records.

Read [the complete exact packet](owner_amendment_packet.json), [source quotations](source_method_audit.json),
[focused-test receipt](focused_test_receipt.json), [engineering evidence](engineering_probe.json).
The three scientific decisions are FC01 post-hoc conservative simultaneous intervals plus Holm tests,
FC02 realistic none/A2 empirical comparison while retaining scoped equality proof,
FC03 explicit N/A accounting of the120 predeclared unsupported Heavy occupancy0.3 cells.
FC04 permits only the three named new operational/handoff paths; original413 source entries remain checked.

No approval for retraining, changed primary policies, held-out selection, or Step7 reruns is requested.
The owner must explicitly accept this complete packet before the13M campaign. Execution of the launcher
with `-AcceptScientificPacket {s.digest(packet)}` is an explicit owner acceptance of all four items;
without it (and without an existing matching receipt), execution fails closed.

The plan contains4480 requirements,40 exact aliases,4440 unique cells,4320 runnable and120 unsupported.
Generated canonical plan/matrix: `experiments/step8_final_closure/{plan_directory(plan).name}/plan.json`.
The default operational workflow is one foreground CPU worker, one Torch thread, no wall-time cap.
Ctrl+C finishes the active episode then stops; restart the SAME command. Any genuine failed cell is
preserved and blocks closure; failures are never ignored to produce a decorative success flag.
''')


def diagnostic_analysis(root,plan):
    cells=plan['matrix']['cells']; values={}; groups=defaultdict(list); paired=[]
    plan_hash=s.digest(plan)
    for cell in cells:
        if cell['status']!='RUNNABLE': continue
        result=verify_cell(root,cell,plan_hash)
        if result is not None:
            # Stream full per-cell evidence, retain only bounded numeric arrays.
            # Never hold thousands of cargo/observation dictionaries in RAM.
            d=result['diagnostics']; records=d['decisions']
            compact={k:result[k] for k in ('status','cell_id','physical_document_sha256','terminal_status','TA','TA_per_vessel','compute','decisions')}
            compact['cargo']={k:result['cargo'][k] for k in ('N_out','U_not_loaded','R_loss_rate')}
            compact['diagnostic_stats']=dict(rollovers=d['rollovers'],
                costs=[r['policy_seconds'] for r in records],
                cargo_errors=[r['predicted_minus_actual_unloaded'] for r in records if 'predicted_minus_actual_unloaded' in r],
                TA_errors=[r['predicted_minus_actual_turnaround'] for r in records if 'predicted_minus_actual_turnaround' in r],
                cargo_pivotal=sum(bool(r.get('pivotal',{}).get('cargo_pivotal')) for r in records),
                wait_minutes=[r['wait_observed']['elapsed_min'] for r in records if 'wait_observed' in r],
                same_state_A2=[r['same_state_A2']['agrees'] for r in records if 'same_state_A2' in r])
            result=compact
            values[cell['cell_id']]=(cell,result)
            label=cell['arm'] if cell['training_seed'] is None else f"A3-train{cell['training_seed']}"
            groups[(cell['requirement_kind'],cell['condition'],cell['model_variant'],cell['family'],label)].append((cell,result))
    for alias in (c for c in cells if c['status']=='ALIAS'):
        source=values.get(alias['alias_of'])
        if source is not None:
            groups[('model_coupling','base','both',alias['family'],'B2')].append((alias,source[1]))
    # Nested PPO mean is scenario-first; incomplete triplets never become a seed-selected mean.
    triplets=defaultdict(dict)
    for c,r in values.values():
        if c['arm']=='A3': triplets[c['condition'],c['family'],c['scenario_seed']][c['training_seed']]=(c,r)
    for key,members in triplets.items():
        if set(members)!={11,23,37}: continue
        c,r=members[11]; avg=dict(r)
        if len({p[1]['physical_document_sha256'] for p in members.values()})!=1 or len({p[1]['cargo']['N_out'] for p in members.values()})!=1:
            raise ContractError('Nested diagnostic PPO physics/cargo mismatch')
        for field in ('TA_per_vessel','TA'):
            avg[field]=nested_mean({seed:pair[1][field] for seed,pair in members.items()})
        avg['cargo']=dict(r['cargo'])
        for field in ('U_not_loaded','R_loss_rate'):
            avg['cargo'][field]=nested_mean({seed:pair[1]['cargo'][field] for seed,pair in members.items()}) if r['cargo'][field] is not None else None
        avg['compute']=dict(r['compute'])
        for field in ('wall_seconds','cpu_seconds'):
            avg['compute'][field]=nested_mean({seed:pair[1]['compute'][field] for seed,pair in members.items()})
        avg['nested_model_terminal_statuses']=[p[1]['terminal_status'] for p in members.values()]
        avg['diagnostic_stats']=dict(r['diagnostic_stats'])
        for name in ('costs','cargo_errors','TA_errors','wait_minutes','same_state_A2'):
            avg['diagnostic_stats'][name]=[x for p in members.values() for x in p[1]['diagnostic_stats'][name]]
        for name in ('rollovers','cargo_pivotal'):
            avg['diagnostic_stats'][name]=nested_mean({seed:p[1]['diagnostic_stats'][name] for seed,p in members.items()})
        avg['decisions']=dict(r['decisions'],wait_selected=nested_mean({seed:p[1]['decisions']['wait_selected'] for seed,p in members.items()}))
        groups[('physical_sensitivity',key[0],'both',key[1],'A3')].append((c,avg))
    summaries=[]
    for (kind,condition,variant,family,label),members in sorted(groups.items()):
        rows=[r for c,r in members]
        summaries.append(dict(kind=kind,condition=condition,variant=variant,family=family,arm=label,n=len(rows),
            mean_TA_per_vessel=float(np.mean([r['TA_per_vessel'] for r in rows])),
            mean_U=float(np.mean([r['cargo']['U_not_loaded'] for r in rows])),
            mean_R=float(np.mean([r['cargo']['R_loss_rate'] for r in rows])) if all(r['cargo']['R_loss_rate'] is not None for r in rows) else None,
            terminal_status_counts={name:sum(status==name for r in rows for status in r.get('nested_model_terminal_statuses',[r['terminal_status']])) for name in ('COMPLETED','DEADLOCK','TRUNCATED_DRAIN_LIMIT')},
            completion_denominator_episodes=3*len(rows) if label=='A3' else len(rows),
            mean_wall_seconds=float(np.mean([r['compute']['wall_seconds'] for r in rows])),
            run_ids=[c['cell_id'] for c,r in members],
            source_run_ids=[r['cell_id'] for c,r in members],
            mean_rollovers=float(np.mean([r['diagnostic_stats']['rollovers'] for r in rows])),
            mean_cargo_pivotal=float(np.mean([r['diagnostic_stats']['cargo_pivotal'] for r in rows])),
            waits=sum(r['decisions']['wait_selected'] for r in rows)))
        summary=summaries[-1]
        for name in ('costs','cargo_errors','TA_errors','wait_minutes'):
            vals=[x for r in rows for x in r['diagnostic_stats'][name]]
            summary[name]=None if not vals else dict(n=len(vals),mean=float(np.mean(vals)),
                p95=float(np.quantile(vals,.95,method='linear')),max=float(max(vals)),MAE=float(np.mean(np.abs(vals))))
        agreements=[x for r in rows for x in r['diagnostic_stats']['same_state_A2']]
        summary['same_state_A2']=dict(decisions=len(agreements),agree=sum(agreements),disagree=len(agreements)-sum(agreements))
    # Pair every variant/arm with the same physical baseline A2, and model
    # variants additionally with full B2. No cross-condition causal claims.
    base_lookup={}
    for key,members in groups.items():
        if key[0]=='physical_sensitivity':
            for c,r in members: base_lookup[(key[1],key[3],c['scenario_seed'],key[4])]=(c,r)
    for key,members in sorted(groups.items()):
        kind,condition,variant,family,label=key
        if label.startswith('A3-train'): continue
        for comparator in (('A2','B2') if kind=='model_coupling' else ('A1','A2')):
            if comparator==label and kind=='physical_sensitivity': continue
            rows=[]
            for c,r in members:
                base=base_lookup.get((condition,family,c['scenario_seed'],comparator))
                if base is None: continue
                bc,b=base
                if r['physical_document_sha256']!=b['physical_document_sha256']:
                    raise ContractError('Diagnostic paired physics mismatch')
                rows.append(dict(scenario_seed=c['scenario_seed'],run_id=c['cell_id'],comparator_run_id=bc['cell_id'],
                    dTA=r['TA_per_vessel']-b['TA_per_vessel'],
                    dR=None if r['cargo']['R_loss_rate'] is None else r['cargo']['R_loss_rate']-b['cargo']['R_loss_rate']))
            if rows:
                paired.append(dict(kind=kind,condition=condition,variant=variant,family=family,arm=label,
                    comparator=comparator,n=len(rows),TA_CI95=interval({family:[r['dTA'] for r in rows]}),
                    cargo_NI_diagnostic_only=cargo_noninferiority({family:[r['dR'] for r in rows]}) if all(r['dR'] is not None for r in rows) else None,
                    cargo_delta_CI95=interval({family:[r['dR'] for r in rows]}) if all(r['dR'] is not None for r in rows) else None,
                    rows=rows,classification='13M_DIAGNOSTIC_NOT_PRIMARY_TEST; raw95% intervals, no across-matrix multiplicity claim'))
    return dict(groups=summaries,comparisons=paired,unique_verified=len(values),
        unsupported=[c for c in cells if c['status']=='UNSUPPORTED'],
        objective_ablation='B2/B2-T is reused from completed Step7, not rerun')


def cost_forecast(ctx,plan,packet):
    from final_closure import predecessor_json
    prior=predecessor_json('derived_arrays.json')
    costs={(r['family'],r['arm']):r['mean_wall_seconds'] for r in prior['groups'] if r['split']=='test' and r['world']=='integrated'}
    seconds=0.
    rows=ctx['plan']['rows']; manifest=ctx['manifest']['files']
    bytes_by_group=defaultdict(list)
    for row in rows:
        if row['split']!='test' or row['world']!='integrated': continue
        size=sum(item['bytes'] for rel,item in manifest.items() if row['row_id'] in rel)
        label=row['arm'] if row['ppo_training_seed'] is None else f"A3-train{row['ppo_training_seed']}"
        bytes_by_group[(row['family'],label)].append(size)
    storage=0.
    for c in plan['matrix']['cells']:
        if c['status']!='RUNNABLE':continue
        label=c['arm'] if c['training_seed'] is None else f"A3-train{c['training_seed']}"
        seconds += costs[(c['family'],label)]
        storage += float(np.mean(bytes_by_group[(c['family'],label)]))
    evidence=packet['engineering_probe']['evidence']
    return dict(proxy_CPU_sequential_wall_hours=seconds/3600,matched_historical_archive_proxy_bytes=int(storage),
        matched_historical_archive_proxy_GiB=storage/1024**3,
        engineering_measured=evidence['full_episode_compute'],engineering_10_container_trace_bytes=evidence['compressed_trace_bytes'],
        engineering_candidate_timings=[{k:r[k] for k in ('variant','wall_seconds','cpu_seconds','candidates')} for r in evidence['timings']],
        method='Sum4320 matching family/arm empirical Step7 wall means; coupling full-model proxy. Disk sums actual manifested per-row archived bytes then matches diagnostic identities; generation/scenario caches and final report overhead excluded.',
        limitations='Historical hardware and full-model proxies, NOT guaranteed runtime/storage bounds. Smaller fixtures validate IO but cannot extrapolate congestion. This runner omits old bulky pickle observations and directly gzip-compresses exact streams; physical sensitivity may still be slower. No arbitrary admission duration.',
        recommended_disk_headroom='Provide substantially more free space than proxy plus original bundle; preflight pauses below5GiB, never deletes evidence')


def final_gate(ctx,counts,approval,tests,verification):
    reasons=[]
    if ctx['gate']['RETURN_VERIFY']!='VERIFIED_FULL_CANONICAL':reasons.append('Original return receipt not verified')
    if not approval: reasons.append('Owner scientific packet acceptance pending')
    if counts['pending'] or counts['failed']: reasons.append('Mandatory new13M diagnostic cells incomplete or failed')
    if (counts['runnable'],counts['unsupported'],counts['aliases'],counts['unique'])!=(4320,120,40,4440):
        reasons.append('Diagnostic matrix accounting differs from exact reviewed contract')
    if counts['verified']!=4320 or counts['verified_aliases']!=40:
        reasons.append('All4320 unique runnable cells and40 aliases must be verified')
    if not verification: reasons.append('Full canonical verification of NEW diagnostic traces pending')
    if not tests: reasons.append('Current analysis implementation fixture PASS absent')
    return dict(STEP7_CAMPAIGN_EXECUTION='COMPLETED_1960_OF_1960',STEP7_OFFICIAL_RETURN_GATE=ctx['gate']['RETURN_VERIFY'],
        STEP7_OUTER_RERUNS=0,FROZEN_SCIENTIFIC_LOCK_AND_CHECKPOINTS='VERIFIED',
        STEP8_PRIMARY_ANALYSIS='COMPLETE_WITH_POST_HOC_QUALIFICATION',STEP8_S1_INFERENCE='COMPLETE',
        STEP8_S2_INFERENCE='POST_HOC_QUALIFIED',STEP8_CARGO_NONINFERIORITY='VERIFIED_NAMED_COMPARATORS_AM06',
        STEP8_DIAGNOSTIC_CELLS=counts,STEP8_ABLATION_SENSITIVITY='COMPLETE_WITH120_APPROVED_PREDECLARED_UNSUPPORTED' if not counts['pending'] and not counts['failed'] and approval else 'BLOCKED',
        STEP8_FINAL_REPORT='VERIFIED_QUALIFIED' if not reasons else 'PROVISIONAL_DIAGNOSTICS_PENDING',
        OWNER_SCIENTIFIC_AMENDMENTS='EXPLICIT_OWNER_ACCEPTANCE' if approval else 'AWAITING_EXPLICIT_OWNER',
        PROJECT_I_FINAL_CLOSED='YES' if not reasons else 'NO',reasons=reasons,PPO_RETRAINING='NONE',
        ORIGINAL_POLICIES_CHECKPOINTS_PHYSICS='UNCHANGED',qualification='POST_HOC_MULTIPLICITY_COMPLETION; SYNTHETIC_UNCALIBRATED; no fully-preregistered primary adjusted superiority claim')


def plots(output,adjusted,diagnostics):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams['svg.hashsalt']='itp-final-closure-v1'
    names=[]
    def save(fig,name):
        for ext in ('png','svg'):
            buf=io.BytesIO(); metadata={'Date':None} if ext=='svg' else {'Software':'ProjectI'}
            fig.savefig(buf,format=ext,dpi=200,bbox_inches='tight',metadata=metadata)
            publish_bytes(output/'figures'/(name+'.'+ext),buf.getvalue())
        plt.close(fig); names.append(name)
    fig,ax=plt.subplots(figsize=(10,5))
    fig.subplots_adjust(bottom=.25)
    rows=[r for r in adjusted['rows'] if r['metric']=='difference_per_vessel' and r['population']!='equal_family_overall']
    for i,r in enumerate(rows):
        ax.errorbar(r['estimate'],i,xerr=[[r['estimate']-r['lower']],[r['upper']-r['estimate']]],fmt='o',color='#0072B2' if r['hypothesis']=='B2-A2' else '#CC79A7')
    ax.set_yticks(range(len(rows)),[r['population'].removeprefix('itp_').title()+' '+r['hypothesis'] for r in rows]);ax.axvline(0,color='gray')
    ax.set_xlabel('Paired turnaround change (minutes/vessel); lower is better')
    ax.set_title('Post-hoc conservative simultaneous intervals (m=2 per population)')
    fig.text(.01,.025,'Post-hoc97.5% marginal percentile intervals; approximate95% coverage per m=2 family.\nNot preregistered Holm-inverted CIs; no joint coverage across populations or metrics.',fontsize=7)
    save(fig,'post_hoc_primary_intervals')
    for kind in ('physical_sensitivity','model_coupling'):
        rows=[r for r in diagnostics['comparisons'] if r['kind']==kind and r['comparator']=='A2' and r['arm']=='B2']
        if not rows:continue
        fig,axes=plt.subplots(1,2,figsize=(15,max(4,len(rows)*.23)),sharey=True)
        ax=axes[0]
        for i,r in enumerate(rows):
            ci=r['TA_CI95']; ax.errorbar(ci['estimate'],i,xerr=[[ci['estimate']-ci['lower']],[ci['upper']-ci['estimate']]],fmt='o',color='#009E73')
        ax.set_yticks(range(len(rows)),[f"{r['family']} {r['condition']} {r['variant']} n={r['n']}" for r in rows]);ax.axvline(0,color='gray')
        ax.set_xlabel('13M paired B2 - A2 minutes/vessel; raw95% diagnostic intervals')
        ax.set_title(kind+'; diagnostic time')
        for i,r in enumerate(rows):
            ci=r['cargo_delta_CI95']
            if ci: axes[1].errorbar(100*ci['estimate'],i,xerr=[[100*(ci['estimate']-ci['lower'])],[100*(ci['upper']-ci['estimate'])]],fmt='o',color='#D55E00')
        axes[1].axvline(0,color='gray');axes[1].set_xlabel('Paired cargo loss-rate change (pp); raw95% CI')
        axes[1].set_title('Cargo; no matrix-wide confirmatory claim')
        save(fig,kind)
    groups=[r for r in diagnostics['groups'] if r['arm']=='B2' and r['costs']]
    if groups:
        fig,ax=plt.subplots(figsize=(10,max(4,len(groups)*.23)))
        ax.barh(range(len(groups)),[r['costs']['mean'] for r in groups],color='#009E73')
        ax.set_yticks(range(len(groups)),[r['family']+' '+r['condition']+' '+r['variant'] for r in groups])
        ax.set_xlabel('Observed mean selection seconds; repeated decisions, not independent scenarios')
        ax.set_title('13M predictive-model computation cost');save(fig,'diagnostic_compute_cost')
    return names


def release(ctx,plan,packet,root,*,finalize=False):
    from final_closure import (predecessor,predecessor_json,predecessor_bytes,PREVIOUS_RELEASE_SHA,
                               scientific_audit,require_approval,packet_path)
    from multiplicity import complete
    from run_step8 import matching_tests, table
    old=predecessor();data=predecessor_json('derived_arrays.json')
    adjusted=complete(data)
    counts=campaign_status(root,plan)
    try: approval=require_approval(root,packet)
    except ContractError:
        if finalize:raise
        approval=[]
    tests=matching_tests(s.digest(code_inventory()))
    if tests is None and packet['test_receipt']['receipt']['code_sha256']==s.digest(code_inventory()):
        receipt=packet['test_receipt']['receipt']
        log=packet_path(plan).parent/'focused_tests.log'
        if receipt['exit_code']==0 and sha(log)==receipt['log_sha256']:tests=packet['test_receipt']
    verification=None
    if (root/'VERIFIED_CANONICAL.json').exists():
        v=read(root/'VERIFIED_CANONICAL.json')
        if v['canonical'] and v['counts']==counts and v['plan_sha256']==s.digest(plan):verification=v
    gate=final_gate(ctx,counts,approval,tests,verification)
    diag=diagnostic_analysis(root,plan)
    signature=dict(plan_sha256=s.digest(plan),packet_sha256=s.digest(packet),counts=counts,analysis_git_head=ctx['git_head'],
                   approved=approval,tests=tests,canonical_verification=verification,
                   predecessor_manifest_file_sha256=PREVIOUS_RELEASE_SHA,method_sha256=adjusted['method_file_sha256'])
    rid=s.digest(signature)[:16]; output=root/'releases'/rid
    publish(output/'provenance.json',dict(**signature,official_return_gate=ctx['gate'],
        frozen_checkpoints=ctx['lock']['checkpoints'],original_source=ctx['source'],git_head_at_analysis=ctx['git_head']))
    publish(output/'closure_status.json',gate);publish(output/'primary_multiplicity_completion.json',adjusted)
    publish(output/'diagnostic_analysis.json',diag);publish(output/'source_method_audit.json',scientific_audit())
    publish(output/'owner_amendment_packet.json',packet);publish(output/'diagnostic_plan.json',plan)
    publish(output/'compute_forecast.json',cost_forecast(ctx,plan,packet))
    cell_evidence={}
    for c in plan['matrix']['cells']:
        item=dict(status=c['status'],cell_fingerprint=c['fingerprint'],alias_of=c['alias_of'],reason=c['reason'])
        if c['status']=='RUNNABLE' and (root/'cells'/c['fingerprint']/'COMMIT.json').exists():
            folder=root/'cells'/c['fingerprint']
            item.update(status='VERIFIED',commit_sha256=sha(folder/'COMMIT.json'),
                result_sha256=sha(folder/'result.json'),files=read(folder/'COMMIT.json')['files'])
        cell_evidence[c['cell_id']]=item
    publish(output/'cell_evidence_manifest.json',cell_evidence)
    publish(output/'engineering_probe.json',packet['engineering_probe'])
    for name in ('derived_arrays.json','cargo_noninferiority.json','wait_cargo_forecast_diagnostics.json',
                 'policy_seed_diagnostics.json','compute_cost.json'):
        publish_bytes(output/name,predecessor_bytes(name))
    for name,item in old['files'].items():
        if name.startswith('figures/'):
            raw=predecessor_bytes(name)
            import hashlib
            if hashlib.sha256(raw).hexdigest()!=item['sha256']: raise ContractError('Historical figure corruption')
            publish_bytes(output/'historical_raw_figures'/Path(name).name,raw)
    for rel,expected in plan['code_inventory'].items():
        if sha(REPO/rel)!=expected:raise ContractError('New source changed during report')
        publish_bytes(output/'source_snapshot'/rel,(REPO/rel).read_bytes())
    table(output/'tables/adjusted_primary.csv',adjusted['rows'])
    table(output/'tables/diagnostic_cell_matrix.csv',plan['matrix']['cells'])
    table(output/'tables/diagnostic_groups.csv',diag['groups'])
    table(output/'tables/diagnostic_comparisons.csv',diag['comparisons'])
    publish(output/'figures/inventory.json',dict(new=plots(output,adjusted,diag),
        historical='Eight preserved Step8 PNG/SVG families in historical_raw_figures; their raw95/provisional labels retained'))
    docs=write_reports(output,ctx,data,adjusted,diag,gate,packet,plan)
    files={p.relative_to(output).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size)
           for p in sorted(output.rglob('*')) if p.is_file() and p.name!='release_manifest.json'}
    manifest=dict(schema='project_i_qualified_final_release_v1',signature=signature,files=files,documents=docs,status=gate)
    publish(output/'release_manifest.json',manifest)
    # Independently rehash newly published report artifacts; no old archive inflation.
    for rel,item in files.items():
        if sha(safe_path(output,rel))!=item['sha256']:raise ContractError('Published release verification failed')
    for rel,expected in docs.items():
        if sha(REPO/rel)!=expected:raise ContractError('Published document verification failed')
    from evidence import protected_source
    protected_source(ctx['lock'],ctx['bundle'])
    pointer=dict(output=output.relative_to(REPO).as_posix(),manifest_sha256=sha(output/'release_manifest.json'),status=gate)
    # Only current pointers are replaceable. Immutable releases remain untouched.
    target=PROJECT/'docs/step8/CURRENT_FINAL_CLOSURE.json';target.write_text(json.dumps(pointer,indent=2)+'\n',encoding='utf-8')
    (PROJECT/'docs/step8/README.md').write_text('# Step8 current scientific release\n\n'
        f"Current verified derived bundle: `{pointer['output']}`.\n\n"
        f"Manifest SHA256: `{pointer['manifest_sha256']}`.\n\n"
        f"PROJECT_I_FINAL_CLOSED = {gate['PROJECT_I_FINAL_CLOSED']}; qualified primary methodology.\n\n"
        '[Current machine status](CURRENT_FINAL_CLOSURE.json); '
        '[owner packet](final_closure/'+s.digest(plan)[:16]+'/README.md); '
        '[execution guide](../../step8/FINAL_CLOSURE_RUNBOOK.md).\n\n'
        'Original1960 episodes and all earlier Step8 releases remain immutable. '
        'The ac9db68020c4079d release is the verified original unadjusted baseline. '
        'New diagnostic execution is owner-manual; no Step7 reruns or automatic training.\n',encoding='utf-8')
    (PROJECT/'PROJECT_I_SCIENTIFIC_CLOSURE.md').write_text(closure_note(pointer),encoding='utf-8')
    return dict(output=str(output),release_sha256=sha(output/'release_manifest.json'),**gate)


def closure_note(pointer):
    state=pointer['status']
    return f'''# Project I scientific closure

`PROJECT_I_FINAL_CLOSED = {state['PROJECT_I_FINAL_CLOSED']}`

Current verified derived bundle: `{pointer['output']}`.
Release manifest SHA256: `{pointer['manifest_sha256']}`.

Step7 completed1960/1960 and official full canonical return receipt is verified and reused.
No Step7 reruns or PPO retraining. Primary inference is explicitly post-hoc qualified.
Remaining conditions: {json.dumps(state['reasons'])}.
Diagnostic accounting: {json.dumps(state['STEP8_DIAGNOSTIC_CELLS'])}.

See [research handoff](docs/PROJECT_I_RESEARCH_HANDOFF.md),
[current analysis pointer](docs/step8/CURRENT_FINAL_CLOSURE.json),
[Project04 transition](docs/PROJECT_04_TRANSITION_NOTE.md).
The immutable release contains the complete machine gate, source snapshots, reports, tables and figures.
'''


def write_reports(output,ctx,data,adjusted,diag,gate,packet,plan):
    target=PROJECT/'docs/step8'/output.name
    target.mkdir(parents=True,exist_ok=True)
    pre=f"**SYNTHETIC / UNCALIBRATED. PROJECT_I_FINAL_CLOSED={gate['PROJECT_I_FINAL_CLOSED']}. Primary adjusted inference is POST_HOC_MULTIPLICITY_COMPLETION.**\n\n"
    pre+=f"Step7 source `{ctx['lock']['source_revision']}`; lock `{ctx['manifest']['lock_sha256']}`; return VERIFIED_FULL_CANONICAL reused. Current analysis HEAD `{ctx['git_head']}`.\n\n"
    pre+=f"Bundle `{output.relative_to(REPO).as_posix()}`. Primary method `{adjusted['method_file_sha256']}`. Packet `{s.digest(packet)}`; approval {gate['OWNER_SCIENTIFIC_AMENDMENTS']}.\n\n"
    primary=markdown_table(['Family','Contrast','Delta min/vessel [simultaneous interval]','Direction','Holm p'],
        [[r['population'],r['hypothesis'],ci_text(r),r['verdict'],f"{r['p_holm']:.5g}"] for r in adjusted['rows'] if r['metric']=='difference_per_vessel'])
    raw=markdown_table(['Family','Contrast','n scenarios','Delta min/vessel [raw95]','Paired % [raw95]','Cargo upper pp','+1pp / zero NI'],
        [[r['family'],r['comparison'],r['n_traffic_scenarios'],ci_text(r['TA_per_vessel_CI95']),ci_text(r['paired_percent_CI95']),
          'not registered' if r['cargo_NI'] is None else f"{100*r['cargo_NI']['upper']:.6f}",
          'not registered' if r['cargo_NI'] is None else r['cargo_NI']['verdict']+' / '+r['cargo_NI']['zero_margin']]
         for r in data['results']])
    s1=markdown_table(['Population','S1 contrast','Delta total vessel-min [raw95]'],
        [[r['family'],r['comparison'],ci_text(r['time_CI95'])] for r in data['S1_difference_in_differences']])
    findings='''B2 versus A2 improves average turnaround and cargo loss in both primary families. The adjusted
time evidence is a disclosed post-hoc methodological completion, not a fully preregistered adjusted test.
Medium has18/50 worse-time scenarios and Heavy6/50; average benefit is not dominance. B2 is model-based, not RL.

PPO versus FCFS improves time in both families. The approved +1pp cargo non-inferiority passes in Medium
(upper +0.566327pp) but is NOT_DEMONSTRATED in Heavy (upper +2.879220pp) and equal-family overall.
Zero-margin sensitivity fails in both. PPO versus A2 is slower on mean time. All11/23/37 seeds are retained;
their within-scenario average is one traffic replicate, not three independent scenarios.

B2 versus B2-T on Heavy reduces mean original unloaded containers45.12 to0.48, with mean time cost
+7.48857min/vessel and raw95% interval[-0.76182,15.66806]. That positive time cost is not statistically
established. AM07 cargo-first objective shows a tradeoff; this is not an RL effect. B1's simple integrated
release estimator can perform worse than its nominal control; more information alone is not sufficient.

The S1 reference is the authentic unchanged Project03 nominal BAP environment. Negative difference-in-differences
means the comparator-relative advantage is stronger in the integrated environment, not that the two environments
have directly comparable absolute physical times. Rankings, signs and tails remain in derived_arrays.json.
'''
    limits='''All data are synthetic and uncalibrated; no real port savings, optimality, universal transfer or yard-RL
effect is established. PPO controls berths; crane and yard policies are common fixed primitives.
Projected remaining-occupancy features exceed the training maximum in1772/3806 Heavy and1130/2417 Medium
PPO test decisions. This distribution shift is not proof of the causal reason for cargo loss.

Archived diagnostics contain27244 decisions,2044 WAIT selections,284 cargo-pivotal choices and4139
two-second warnings. Repeated selected-trajectory WAIT/forecast records are not independent scenarios or
causal counterfactuals. Future unobserved gate-in/pickup requests are omitted; observed requests continue.
Heavy B2 selection mean8.258s, P95~26.136s, max~69.540s. This does not certify an online deadline.
Scenarios may be D24-censored and D17-rolled over; cargo U counts original containers, not TEU or moves.

The post-hoc method fixes m2 separately per population/metric. Bonferroni97.5% marginal percentile intervals
are conservative approximate95% simultaneous intervals; supporting Holm p-values use centered bootstrap
tests. No exact finite-sample coverage or simultaneous coverage over all secondary/diagnostic contrasts is claimed.
The method was fixed before computing these new adjusted results, after raw outcomes had been seen.
'''
    matrixtext=f"Counts: `{json.dumps(gate['STEP8_DIAGNOSTIC_CELLS'])}`.\n\n"
    matrixtext+='''Physical OFAT sensitivity and candidate-model-only coupling are different estimands. Full model
both reuses40 byte-identical baseB2 cells. All120 Heavy0.3 cells remain unsupported, never successful runs.
MODEL_COUPLING_NONE supplies dedicated nominal.5min/move per-vessel capacity and disables transport/yard
rate couplings, preserving availability, storage feasibility, D15/D17 and AM07. Ready-cargo uncensored
fixed-service equality proof remains valid in its exact scope; realistic none/A2 agreement is empirical.
The engineering two-vessel short-horizon counterexample demonstrates why universal equality is invalid.
'''
    matrixtext+=markdown_table(['kind','condition','variant','family','arm','n','mean TA/vessel','mean U'],
        [[r[k] for k in ('kind','condition','variant','family','arm','n','mean_TA_per_vessel','mean_U')] for r in diag['groups']])
    abstracts='''This study compares berth-only and terminal-aware berth decisions under shared crane, transport,
yard and cargo constraints in a synthetic integrated terminal. A locked paired campaign of1960 episodes
includes50 independent test scenarios in each of Medium and Heavy and three frozen PPO checkpoints.
Cargo-first model-based B2 reduces average turnaround and original outbound cargo loss relative to
berth-only A2; frozen berth PPO offers faster inference but mixed cargo safety. Primary multiplicity
analysis is completed with an explicitly post-hoc conservative simultaneous-bootstrap procedure and
supporting Holm tests. Independent13M sensitivity/coupling diagnostics have the exact execution status
shown below; unfinished diagnostics prevent scientific closure. Results support conditional terminal-aware
decision support, not joint three-problem RL or calibrated real-terminal productivity claims.
'''
    contents={
        'project_i_executive_results_summary.md':abstracts+'\n'+primary+'\n\n'+findings,
        'project_i_final_scientific_report.md':abstracts+'\n'+findings+'\n'+primary+'\n\n'+raw+'\n\n'+s1+'\n\n'+matrixtext+'\n\n'+limits,
        'step8_statistical_analysis_protocol_and_results.md':json.dumps(adjusted['method'],indent=2)+'\n\n'+primary+'\n\n'+raw+'\n\n'+s1,
        'step8_ablations_and_sensitivity.md':matrixtext+'\n\nSee diagnostic_analysis.json for paired intervals, run IDs, completion and cargo; no unexecuted cell is a measured result.',
        'step8_failure_modes_and_limitations.md':findings+'\n'+limits,
        'step8_source_and_evidence_audit.md':'Original413 paths verified unchanged (newline-only transport differences documented). Only three explicitly named NEW files extend Step8 operational inventory; Step7 verifier is untouched.\n\n'+json.dumps(ctx['gate'],indent=2)+'\n\nExact source quotations/line numbers and all model hashes are in source_method_audit.json and provenance.json. No original archive verification rerun.\n\nFocused test receipt and engineering proof are linked in owner_amendment_packet.json; canonical new diagnostic verification is an independent gate.',
        'project_i_scientific_closure.md':json.dumps(gate,indent=2)+'\n\nClosure requires the actual records and explicit scientific acceptance. No stage9 is introduced.'}
    docs={}
    for name,body in contents.items():
        txt(output/'reports'/name,'# '+name.replace('_',' ').removesuffix('.md')+'\n\n'+pre+body)
        publish_bytes(target/name,(output/'reports'/name).read_bytes())
        docs[(target/name).relative_to(REPO).as_posix()]=sha(target/name)
    return docs
